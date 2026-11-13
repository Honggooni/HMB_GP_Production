"""Native SDK palette, two Analysis roles, and cold reopen. No network or models."""
from __future__ import annotations

import argparse
import asyncio
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(Path(__file__).parent)]
import HMB_Seedance_Execution_Mode_Host_Regression as host
import HMB_Finish_Multishot_Consolidation_Host_Regression as media_fixture

CHANNEL = "11cf36cd-d9ef-4a17-ab2a-9d1299b417da"
SHOTS = [{"shot_uuid": f"9053222b-7492-41ae-bf92-{number:012d}", "number": number,
          "name": f"Analysis fixture {number}"} for number in range(1, 6)]


async def exercise(engine, phase: str, out: Path) -> None:
    import HMBAnalysisAgent as analysis
    import HMBImageAssetLibrary as images
    import HMBPromptLibrary as prompt_module
    import _hmb_connection_management as connections
    import _hmb_library_bootstrap as bootstrap
    import _hmb_reference_analysis as backend
    from PIL import Image
    from griptape_nodes.node_library.library_registry import LibraryRegistry
    from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    from griptape_nodes.retained_mode.events.flow_events import SerializeFlowToCommandsRequest
    from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest, CreateNodeResultFailure
    from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
    from griptape_nodes.retained_mode.events.workflow_events import (
        RunWorkflowWithCurrentStateRequest, SaveWorkflowFileFromSerializedFlowRequest,
    )

    schema = host.register(engine, {"HMBAnalysisAgent": analysis, "HMBPromptLibrary": prompt_module,
        "HMBImageAssetLibrary": images})
    engine.event_manager.initialize_queue()
    library = LibraryRegistry.get_library(schema.name)
    owner = bootstrap.HMBProductionLibrary.__new__(bootstrap.HMBProductionLibrary)
    owner._registrations = set()
    with mock.patch.object(bootstrap._Registration, "start_web_worker", lambda *a: None), \
         mock.patch.object(bootstrap, "_hmb_coordinate_native_editor_update", return_value=None):
        owner.before_library_nodes_loaded(schema, library)
    assert len(owner._registrations) == 1
    saved = out / "analysis-agent-cold.py"
    expected_file = out / "expected-analysis-state.json"
    calls = []

    def source(shot_uuid: str) -> dict:
        path = out / f"{shot_uuid}.png"
        return {"kind": "image", "source_id": shot_uuid, "name": path.name, "path": str(path)}

    def fixture_sources(self, *, channel_uuid: str, shot_uuid: str) -> list[dict]:
        assert channel_uuid == CHANNEL and shot_uuid in {row["shot_uuid"] for row in SHOTS}
        return [{key: value for key, value in source(shot_uuid).items() if key != "path"}]

    def fixture_reference(self, *, channel_uuid: str, shot_uuid: str, kind: str, source_id: str) -> dict:
        rows = fixture_sources(self, channel_uuid=channel_uuid, shot_uuid=shot_uuid)
        return source(shot_uuid) if rows[0]["kind"] == kind and source_id == shot_uuid else {}

    def fixture_originals(self, *, channel_uuid: str, shot_uuid: str) -> list[dict]:
        assert channel_uuid == CHANNEL and shot_uuid in {row["shot_uuid"] for row in SHOTS}
        return [] if shot_uuid == SHOTS[1]["shot_uuid"] else [source(shot_uuid)]

    def fixture_analysis(node, *, source: str, kind: str, **kwargs) -> dict:
        assert kind == "image" and kwargs["is_live"]()
        assert kwargs["model_config"] is config and kwargs["model"] == config.model
        digest = hashlib.sha256(Path(source).read_bytes()).hexdigest()
        calls.append(digest)
        return {"kind": "image", "source_digest": digest, "cache_key": digest, "model": "fixture-only",
                "model_settings_sha256": backend.analysis_model_settings_digest(config),
                "range": {"start": None, "end": None}, "cache_hit": False,
                "observations": {"composition": [{"observation": f"Composition {digest[:12]}"}],
                    "lighting_reference": [{"observation": f"Lighting {digest[12:24]}"}]}}

    def get(name: str):
        return engine.node_manager.get_node_by_name(name)

    def palette_request(node_type: str, name: str, flow: str):
        return CreateNodeRequest(node_type=node_type, specific_library_name=schema.name,
            node_name=name, override_parent_flow_name=flow, initial_setup=False, create_error_proxy_on_failure=False)

    async def create(node_type: str, name: str, flow: str):
        result = await host.asend(engine, palette_request(node_type, name, flow))
        registration = next(iter(owner._registrations))
        # Palette results are followed by the SDK's detached admission release.
        async with asyncio.timeout(5):
            while registration.prompt_pending:
                await asyncio.sleep(.01)
        return get(result.node_name)

    def command(node, action: str, shot_uuid: str, *, expected_error: str = "", **values) -> dict:
        state = node.get_parameter_value(analysis.UI)
        request_id = f"{phase}-{action}-{state['revision']}-{shot_uuid}"
        host.send(engine, SetParameterValueRequest(node_name=node.name, parameter_name=analysis.UI,
            value={"__hmb_analysis_command": {"id": request_id, "action": action, "channel_uuid": CHANNEL,
                "shot_uuid": shot_uuid, "revision": state["revision"], **values}}))
        current = node.get_parameter_value(analysis.UI)
        assert current["ack"] == request_id and current["error"] == expected_error, current
        return current

    def prompt_document(prompt, shot_uuid: str) -> dict:
        state = prompt._current_state()
        key = prompt_module._prompt_document_key({"channel_uuid": CHANNEL, "shot_uuid": shot_uuid})
        return prompt_module._parse_state(state["shot_documents"][key])

    def seed_prompt_documents(prompt) -> None:
        state = prompt_module._normalize_state(prompt._current_state())
        catalog = prompt_module._verified_prompt_shot_catalog(state)
        assert state["multi_shot_enabled"] and [row["shot_uuid"] for row in catalog] == [row["shot_uuid"] for row in SHOTS]
        for index in (2, 3, 0):
            state = prompt_module._select_prompt_shot_document(state, catalog[index])
            state["text"]["PROJECT_STYLE_LOOK"] = f"Artist-authored style {index + 1}"
            state["text"]["PRESERVED_TEXT"] = f"[Dialogue] Exact text {index + 1}"
            prompt_module._store_prompt_shot_document(state)
        host.send(engine, SetParameterValueRequest(node_name=prompt.name,
            parameter_name=prompt_module.WIDGET_PARAMETER_NAME, value=json.dumps(state), initial_setup=True))

    def configure_image_source(source_node, prompt) -> None:
        shots = [{**row, "revision": row["number"], "selected_source_uids": []} for row in SHOTS]
        with mock.patch.multiple(media_fixture, CHANNEL=CHANNEL, SHOTS=shots):
            catalog = media_fixture.media_fixture(source_node)
        prompt._hmb_reconcile_shot_routing(deepcopy(catalog))

    def assert_delivery(prompt, index: int) -> None:
        shot_uuid = SHOTS[index]["shot_uuid"]
        context = analysis.get_analysis_context(prompt, channel_uuid=CHANNEL, shot_uuid=shot_uuid, destination="agent")
        sent = analysis.get_analysis_context(prompt, channel_uuid=CHANNEL, shot_uuid=shot_uuid, destination="generator")
        assert sent == {}
        assert context["shot_uuid"] == shot_uuid
        if index == 0:
            assert context["edited_result"] == "Revised lighting from the current shot"
            assert context["items"] == []
        else:
            assert [item["category"] for item in context["items"]] == ["composition"]
        originals = analysis.get_analysis_originals(prompt, channel_uuid=CHANNEL, shot_uuid=shot_uuid)
        assert [item["path"] for item in originals] == ([source(shot_uuid)["path"]] if index == 1 else [])

    def manage(node, action: str) -> dict:
        view = connections.describe(engine, node.name)
        return connections.manage(engine, node.name, action, view["state_token"])

    config = SimpleNamespace(model="fixture-only", to_wire=lambda: {"model": "fixture-only"})
    with mock.patch.object(prompt_module.HMBPromptLibrary, "_hmb_analysis_sources_for", fixture_sources), \
         mock.patch.object(prompt_module.HMBPromptLibrary, "_hmb_analysis_originals_for", fixture_originals), \
         mock.patch.object(prompt_module.HMBPromptLibrary, "_hmb_analysis_reference_for", fixture_reference), \
         mock.patch.object(prompt_module.HMBPromptLibrary, "_hmb_analysis_upstream_sources_for", fixture_sources), \
         mock.patch.object(prompt_module.HMBPromptLibrary, "_hmb_analysis_upstream_reference_for", fixture_reference), \
         mock.patch("HMBAgentLibrary.get_same_shot_analysis_model", return_value=config), \
         mock.patch.object(backend, "analyze_reference", fixture_analysis):
        if phase == "save":
            flow_name = host.send(engine, EnsureWorkflowAndFlowRequest(flow_name="AnalysisSaveReopenFixture")).flow_name
            node = await create("HMBAnalysisAgent", "Cold Analysis Agent", flow_name)
            prompt = await create("HMBPromptLibrary", "Cold Prompt", flow_name)
            source_node = await create("HMBImageAssetLibrary", "Cold Analysis Image Publisher", flow_name)
            configure_image_source(source_node, prompt)
            host.send(engine, CreateConnectionRequest(source_node_name=source_node.name,
                source_parameter_name="SHOT_ASSET_OUT", target_node_name=prompt.name,
                target_parameter_name="SHOT_ASSET_IN", initial_setup=True))
            before = await create("HMBAnalysisAgent", "Cold Upstream Analysis Agent", flow_name)
            assert node.metadata["size"] == before.metadata["size"] == {"width": 780, "height": 1160}
            node.metadata["size"] = {"width": 650, "height": 730}
            before.metadata["size"] = {"width": 840, "height": 900}
            command(node, "refresh", "")
            command(before, "refresh", "")
            assert node.get_parameter_value(analysis.STATE)["role"] == "after"
            assert before.get_parameter_value(analysis.STATE)["role"] == "before"
            duplicate = palette_request("HMBAnalysisAgent", "Forbidden Third Analysis", flow_name)
            duplicate.broadcast_result = False
            rejected = engine.handle_request(duplicate)
            assert type(rejected) is CreateNodeResultFailure and not rejected.succeeded(), rejected
            assert "one Prompt-before and one Prompt-after" in str(rejected.result_details), rejected
            flow = engine.flow_manager.get_flow_by_name(flow_name)
            assert set(flow.nodes.values()) == {node, before, prompt, source_node}
            before_conflict = deepcopy(before.get_parameter_value(analysis.STATE))
            conflict = command(before, "set_role", "", role="after", expected_error="ANALYSIS_REQUEST_INVALID")
            assert conflict["role"] == "before" and conflict["available_roles"] == ["before"]
            assert "이미 있습니다" in conflict["status"]
            assert before.get_parameter_value(analysis.STATE) == before_conflict
            host.record("native_palette_assigns_after_then_before_rejects_third_and_same_role_change")
            assert len(node.get_parameter_value(analysis.UI)["shots"]) == 5
            for index, row in enumerate(SHOTS):
                shot_uuid = row["shot_uuid"]
                media = source(shot_uuid)
                Image.new("RGB", (12, 10), color=(30 + index * 25, 90, 150)).save(media["path"])
                command(node, "select_shot", shot_uuid)
                if index == 1:
                    host.send(engine, SetParameterValueRequest(node_name=node.name, parameter_name=analysis.FILE,
                        value=media["path"]))
                    assert node.get_parameter_value(analysis.UI)["slot"]["origin"] == "direct"
                    assert node.get_parameter_value(analysis.FILE) == ""
                else:
                    selected = command(node, "select_source", shot_uuid, kind="image", source_id=media["source_id"])
                    assert selected["slot"]["origin"] == "prompt"
                    assert selected["slot"]["source_id"] == media["source_id"]
                if index > 1:
                    continue
                pending = command(node, "analyze", shot_uuid, confirmed_paid=True,
                    guidance=f"Fixture direction {index}" if index == 0 else "")
                assert pending["running"]
                async with asyncio.timeout(10):
                    while node.get_parameter_value(analysis.UI)["running"]:
                        await asyncio.sleep(.01)
                assert not node.get_parameter_value(analysis.UI)["error"]
                auto = analysis.get_analysis_context(prompt, channel_uuid=CHANNEL, shot_uuid=shot_uuid, destination="agent")
                assert [item["category"] for item in auto["items"]] == ["composition", "lighting_reference"]
                edits = {"result_text": "Revised lighting from the current shot"} if index == 0 else {}
                command(node, "delivery", shot_uuid, categories=["lighting_reference" if index == 0 else "composition"],
                    results_only=index == 0, **edits)
                assert_delivery(prompt, index)
            assert len(calls) == 2 and calls[0] != calls[1]
            seed_prompt_documents(prompt)
            active_shot, upstream_shot, dormant_shot = (SHOTS[index]["shot_uuid"] for index in (0, 2, 3))
            active_original = deepcopy(prompt._current_state()["text"])
            dormant_original = prompt_document(prompt, dormant_shot)["text"]
            upstream_original = prompt_document(prompt, upstream_shot)["text"]
            command(before, "select_shot", upstream_shot)
            command(before, "select_source", upstream_shot, kind="image", source_id=upstream_shot)
            command(before, "analyze", upstream_shot, confirmed_paid=True)
            async with asyncio.timeout(10):
                while before.get_parameter_value(analysis.UI)["running"]:
                    await asyncio.sleep(.01)
            assert not before.get_parameter_value(analysis.UI)["error"]
            assert len(calls) == len(set(calls)) == 3
            upstream_fields = prompt_document(prompt, upstream_shot)["text"]
            assert upstream_fields["PROJECT_STYLE_LOOK"].startswith(upstream_original["PROJECT_STYLE_LOOK"] + "\n\n"), (
                upstream_fields, upstream_original, before.get_parameter_value(analysis.UI)["status"],
                prompt_module._verified_prompt_shot_catalog(prompt._current_state()))
            assert "Lighting " in upstream_fields["PROJECT_STYLE_LOOK"]
            assert upstream_fields["PRESERVED_TEXT"] == upstream_original["PRESERVED_TEXT"]
            assert prompt._current_state()["shot"]["shot_uuid"] == active_shot
            assert prompt._current_state()["text"] == active_original
            assert prompt_document(prompt, dormant_shot)["text"] == dormant_original
            assert analysis.get_analysis_context(prompt, channel_uuid=CHANNEL, shot_uuid=upstream_shot, destination="agent") == {}
            host.record("upstream_analysis_commits_to_exact_dormant_shot_and_preserves_artist_text_and_other_shots")
            state = deepcopy(node.get_parameter_value(analysis.STATE))
            assert len(state["slots"]) == 5 and state["active"] == [CHANNEL, SHOTS[4]["shot_uuid"]]
            view = connections.describe(engine, node.name)
            assert view["can_refresh"] and view["can_disconnect"] and len(view["connections"]) == 1
            assert view["connections"][0]["kind"] == "remote" and len(view["connections"][0]["shots"]) == 5
            assert manage(node, "refresh")["can_refresh"]
            detached = manage(node, "disconnect")
            assert detached["detached"] and not detached["can_refresh"] and detached["can_reconnect"]
            scope = {"channel_uuid": CHANNEL, "shot_uuid": SHOTS[1]["shot_uuid"]}
            assert not analysis.get_analysis_context(prompt, **scope, destination="agent")
            assert not analysis.get_analysis_originals(prompt, **scope)
            assert not analysis.get_analysis_originals(prompt, **scope, preview=True)
            assert node.get_parameter_value(analysis.STATE) == state
            host.record("exact_Prompt_to_Analysis_remote_can_refresh_and_detach_without_erasing_slots")
            expected_file.write_text(json.dumps({"after": state, "before": before.get_parameter_value(analysis.STATE),
                "upstream_fields": upstream_fields, "dormant_fields": dormant_original}), encoding="utf-8")
            serialized = host.send(engine, SerializeFlowToCommandsRequest(flow_name=flow_name)).serialized_flow_commands
            await host.asend(engine, SaveWorkflowFileFromSerializedFlowRequest(serialized_flow_commands=serialized,
                file_name=saved.stem, file_path=str(saved), display_name="Synthetic Analysis cold reopen fixture"))
            assert saved.is_file()
            host.record("real_sdk_native_save_five_slots_and_two_selected_results_with_independent_upstream_state",
                mock_analysis_calls=len(calls))
            return

        loaded = await host.asend(engine, RunWorkflowWithCurrentStateRequest(file_path=str(saved)))
        assert str(getattr(loaded.status, "name", loaded.status)) == "GOOD"
        node, before, prompt = get("Cold Analysis Agent"), get("Cold Upstream Analysis Agent"), get("Cold Prompt")
        configure_image_source(get("Cold Analysis Image Publisher"), prompt)
        assert type(node) is type(before) is analysis.HMBAnalysisAgent and type(prompt) is prompt_module.HMBPromptLibrary
        assert node.metadata["size"] == {"width": 650, "height": 730}
        assert before.metadata["size"] == {"width": 840, "height": 900}
        expected = json.loads(expected_file.read_text("utf-8"))
        assert node.get_parameter_value(analysis.STATE) == expected["after"]
        assert before.get_parameter_value(analysis.STATE) == expected["before"]
        assert prompt_document(prompt, SHOTS[2]["shot_uuid"])["text"] == expected["upstream_fields"]
        assert prompt_document(prompt, SHOTS[3]["shot_uuid"])["text"] == expected["dormant_fields"]
        host.record("cold_reopen_restores_both_roles_separate_slots_and_exact_upstream_prompt_fields")
        view = connections.describe(engine, node.name)
        assert view["detached"] and not view["can_refresh"] and view["can_reconnect"]
        with mock.patch.object(prompt_module.HMBPromptLibrary, "_hmb_analysis_catalog",
                lambda _node: {"channel_uuid": CHANNEL, "shots": SHOTS[:-1]}):
            assert not connections.describe(engine, node.name)["can_reconnect"]
        assert manage(node, "reconnect")["can_refresh"]
        host.record("cold_detached_Analysis_requires_exact_saved_Prompt_and_all_Shots_before_reconnecting")
        async with asyncio.timeout(10):
            while len(node.get_parameter_value(analysis.UI)["shots"]) != 5:
                await asyncio.sleep(.01)
        assert node.get_parameter_value(analysis.UI)["shot_uuid"] == SHOTS[4]["shot_uuid"]
        for index in range(5):
            shot_uuid = SHOTS[index]["shot_uuid"]
            view = command(node, "select_shot", shot_uuid)
            assert "path" not in view["slot"] and "stamp" not in view["slot"] and view["shot_uuid"] == shot_uuid
            if index < 2:
                assert_delivery(prompt, index)
                reused = command(node, "analyze", shot_uuid, confirmed_paid=True, guidance=view["slot"]["guidance"])
                assert not reused["running"] and "재사용" in reused["status"]
            else:
                assert not analysis.get_analysis_context(prompt, channel_uuid=CHANNEL, shot_uuid=shot_uuid, destination="agent")
        assert calls == []
        first = SHOTS[0]["shot_uuid"]
        Image.new("RGB", (15, 11), color=(0, 0, 0)).save(source(first)["path"])
        assert analysis.get_analysis_context(prompt, channel_uuid=CHANNEL, shot_uuid=first, destination="agent") == {}
        assert_delivery(prompt, 1)
        host.record("second_process_restored_all_slots_reused_results_and_rejected_replaced_source", mock_analysis_calls=len(calls))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("save", "reopen"))
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if args.phase:
        host.exercise = exercise
        host.PRODUCTS = ("HMBAnalysisAgent.py", "griptape-nodes-library.json", "HMBPromptLibrary.py", "_hmb_reference_analysis.py", "_hmb_analysis_delivery.py",
            "HMBImageAssetLibrary.py", "_hmb_library_bootstrap.py", "_hmb_connection_management.py", "_hmb_workflow_migration.py",
            Path(__file__).resolve().relative_to(ROOT).as_posix())
        # This fixture only registers its three HMB classes. Keep the desktop
        # SDK's own dependencies ahead of an unrelated Standard virtualenv.
        host.STANDARD = out / "unused-standard-library"
        host.run_phase(args.phase, out)
        result_path = out / f"{args.phase}-result.json"
        report = json.loads(result_path.read_text("utf-8"))
        report["schema"] = "hmb-analysis-agent-save-reopen-sdk/v1"
        result_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return
    reports = []
    for phase in ("save", "reopen"):
        result = subprocess.run([sys.executable, "-I", "-B", str(Path(__file__).resolve()),
            "--phase", phase, "--out", str(out)], cwd=ROOT,
            env=dict(os.environ, PYTHONIOENCODING="utf-8"), capture_output=True, timeout=100)
        (out / f"{phase}-stdout-stderr.txt").write_bytes(result.stdout + result.stderr)
        if result.returncode:
            sys.stdout.buffer.write(result.stdout + result.stderr)
            raise SystemExit(result.returncode)
        report = json.loads((out / f"{phase}-result.json").read_text("utf-8"))
        assert report["passed"], report
        reports.append(report)
    print(json.dumps({"native_processes": len(reports), "cases": [r["cases"] for r in reports],
        "external_or_live_socket_attempts": sum(r["external_or_live_socket_attempts"] for r in reports)}))


if __name__ == "__main__":
    main()
