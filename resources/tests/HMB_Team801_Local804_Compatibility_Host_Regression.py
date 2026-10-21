"""Two fresh SDK processes: published Team801 save -> current Local804.

Requires the SHA-pinned, already downloaded official Team runtime archive.
Only synthetic authoring is serialized; no user workflow or provider is used.
This is a manual installed-SDK/archive integration test, not a portable test.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import importlib
import json
import logging
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import zipfile
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = ROOT / ".test-cache/release-v801-local-v802-20261015/published/HMB_GP_Production_v0.8.01_Runtime.zip"
ARCHIVE_SHA = "c48448f86090eabfbdab909c16b3f63a3e2c612246bcf1ae7994927e114f5b46"
OUT = ROOT / "reports/release-readiness-local804-20261016/team-compatibility"
KINDS = ("HMBImageAssetLibrary", "HMBVideoPickerLibrary", "HMBPromptLibrary",
         "HMBAgentLibrary", "HMBFinishLookLibrary", "HMBSeedanceGeneration")
CHANNEL = "11111111-1111-4111-8111-111111111111"
PUBLISHER = "22222222-2222-4222-8222-222222222222"
SHOTS = [dict(channel_uuid=CHANNEL, shot_uuid=f"33333333-3333-4333-8333-{n:012d}",
    number=n, name=f"Team authored asset {n}", revision=n, selected_source_uids=[])
    for n in range(1, 6)]
ATTEMPTS = []


def deny(*args, **kwargs):
    ATTEMPTS.append("external execution")
    raise AssertionError("Team compatibility must not execute models, rendering or transport")


def sha(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":")).encode()).hexdigest()


def send(engine, request):
    request.broadcast_result = False
    result = engine.handle_request(request)
    assert result.succeeded(), str(result.result_details)
    return result


def edges(engine, flow):
    return sorted((edge.source_node.name, edge.source_parameter.name,
        edge.target_node.name, edge.target_parameter.name)
        for edge in engine.flow_manager._get_connections_for_flow(flow))


def register(engine, package, modules):
    from griptape_nodes.node_library.library_registry import LibraryRegistry, LibrarySchema
    schema = LibrarySchema.model_validate_json((package / "griptape-nodes-library.json").read_text("utf-8-sig"))
    from _hmb_library_bootstrap import HMBProductionLibrary
    advanced = HMBProductionLibrary()
    library = LibraryRegistry.generate_new_library(schema, advanced_library=advanced)
    for definition in schema.nodes:
        if definition.class_name in modules:
            cls = getattr(modules[definition.class_name], definition.class_name)
            library.register_lazy_node_type(definition.class_name, definition.metadata, lambda cls=cls: cls)
    advanced.before_library_nodes_loaded(schema, library)
    return library, schema


async def build_team(engine, package, modules):
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
    from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest
    from griptape_nodes.retained_mode.events.flow_events import SerializeFlowToCommandsRequest
    from griptape_nodes.serialization.values import encode_value
    images, pickers, prompts, agents, finishes, generators = (modules[k] for k in KINDS)
    library, schema = register(engine, package, modules)
    engine.event_manager.initialize_queue()
    flow = engine.flow_manager.get_flow_by_name(send(engine, EnsureWorkflowAndFlowRequest(flow_name="PublishedTeam801SyntheticLegacy")).flow_name)
    def create(kind, name, number=0):
        result = send(engine, CreateNodeRequest(node_type=kind, node_name=name,
            specific_library_name=schema.name, initial_setup=True,
            metadata={"position": {"x": number * 270, "y": number * 160}, "team_compat_literal": f"Metadata {name} {{literal}}"}))
        return engine.node_manager.get_node_by_name(result.node_name)
    image, picker = create(KINDS[0], "Legacy Asset"), create(KINDS[1], "Legacy Picker")
    project = OUT / "synthetic-projects/Katuri8"
    project.mkdir(parents=True, exist_ok=True)
    (project / "hmb_image_assets.json").write_text('{"assets": []}', encoding="utf-8")
    state = images._select_catalog_project(images._load_project_catalog(project.parent, images._default_state()), project)
    state["shot_routing"].update(channel_uuid=CHANNEL, publisher_instance_uuid=PUBLISHER,
        generation=10, shots=deepcopy(SHOTS), active_shot_uuid=SHOTS[0]["shot_uuid"])
    image.set_parameter_value(images.WIDGET_STATE_PARAMETER, json.dumps(state, ensure_ascii=False), initial_setup=True)
    catalog = image._hmb_shot_routing_catalog()
    expected = {"prompt": {}, "agent": {}, "finish": {}, "generators": {}, "metadata": {}}
    for n, shot in enumerate(SHOTS, 1):
        prompt, agent, finish, generator = (create(kind, f"Team {kind} {n}", n)
            for kind in KINDS[2:])
        state = prompts._default_widget_state()
        state["shot"] = deepcopy(shot)
        state["text"]["PRESERVED_TEXT"] = f"Team literal {n} {{RGB(12, 34, 56)}} OFF 0 한국어"
        state["images"][0].update(label=f"Team image {n}", owner=f"Team Target {n}",
            image_main_type="Character", image_sub_type="Full Appearance", color_picks=["Red" if n % 2 else "Blue"])
        state["videos"][0].update(label=f"Team reference {n}", keep_out=f"Keep literal {n} OFF 0")
        state["ui"]["textarea_heights"] = {"video:1:keep_out": 90 + n}
        prompt.set_parameter_value(prompts.WIDGET_PARAMETER_NAME, prompts._json_dumps(state), initial_setup=True)
        expected["prompt"][shot["shot_uuid"]] = deepcopy(prompt._current_state())
        agent.set_parameter_value(agents._AGENT_WIDGET_PARAMETER,
            agents._agent_widget_value(shot=shot, shot_catalog=catalog), initial_setup=True)
        native = {"prompt": f"Team native input {n} {{literal}}", "additional_context": f"Team context {n}",
            "include_details": n % 2 == 1, "output_schema": {"type": "object", "properties": {f"team{n}": {"type": "string"}}}}
        for key, value in native.items():
            agent.set_parameter_value(key, value, initial_setup=True)
        rule = agent.get_parameter_by_name("rulesets").add_child_parameter()
        rule_value = {"name": f"Team rule {n}", "rules": [f"Literal rule {n} OFF 0"]}
        agent.set_parameter_value(rule.name, rule_value, initial_setup=True)
        agent.parameter_output_values["output"] = f"Team cached result {n} {{literal}}"
        native.update({"model_provider": agent.get_parameter_value("model_provider"), "model": agent.get_parameter_value("model")})
        expected["agent"][shot["shot_uuid"]] = {"values": encode_value(native), "rule": rule_value,
            "output": agent.parameter_output_values["output"]}
        fstate = finishes.default_widget_state()
        fstate.update(shot=deepcopy(shot), shot_catalog=deepcopy(catalog))
        fstate["finish_look"]["beauty"].update(enabled=n % 2 == 1, brightness=1 + n / 10, blur_amount=0)
        finish.set_parameter_value(finishes.WIDGET_PARAMETER_NAME, fstate, initial_setup=True)
        finish_saved = finish.get_parameter_value(finishes.WIDGET_PARAMETER_NAME)
        finish_saved = json.loads(finish_saved) if isinstance(finish_saved, str) else finish_saved
        expected["finish"][shot["shot_uuid"]] = deepcopy(finish_saved["finish_look"])
        gen_values = dict(shot_channel_uuid=CHANNEL, shot_uuid=shot["shot_uuid"], shot_number=n, shot_name=shot["name"],
            resolution="480p", duration=4, output_format="mov", generate_audio=False,
            draft_job_id="job-" + str(n) * 32, resume_generation_id="job-" + str(n + 1) * 32,
            model_id=generators.SEEDANCE_2_5_MODEL_ID)
        for key, value in gen_values.items():
            generator.set_parameter_value(key, value, initial_setup=True)
        expected["generators"][generator.name] = {k: encode_value(generator._get_raw_parameter_value(k)) for k in gen_values}
        for field, extension in (("reference_images", "png"), (generators.VIDEO_REFERENCES_PARAMETER, "mp4"), ("reference_audio", "wav")):
            values = [f"https://media.invalid/team-{n}-{index}.{extension}" for index in (1, 2)]
            for value in values:
                child = generator.get_parameter_by_name(field).add_child_parameter()
                generator.set_parameter_value(child.name, value, initial_setup=True)
            expected["generators"][generator.name][field] = encode_value(generator._get_list_input(field))
        for src, output, dst, input_name in ((image, "SHOT_ASSET_OUT", prompt, "SHOT_ASSET_IN"),
            (picker, "SHOT_PICKER_OUT", prompt, "SHOT_PICKER_IN"), (prompt, "PROMPT_OUT", agent, "SHOT_PROMPT_IN"),
            (agent, "output", generator, "prompt"), (image, "SHOT_ASSET_OUT", generator, "SHOT_ASSET_IN"),
            (picker, "SHOT_PICKER_OUT", generator, "SHOT_PICKER_IN"), (finish, "SHOT_FINISH_LOOK_OUT", generator, "SHOT_FINISH_LOOK_IN")):
            send(engine, CreateConnectionRequest(source_node_name=src.name, source_parameter_name=output,
                target_node_name=dst.name, target_parameter_name=input_name, initial_setup=True))
    # Capture what the real Team serializer receives after native connection
    # hooks. A connected Prompt legitimately authors the Agent preview input;
    # comparing against its superseded pre-connection scalar would be false.
    for n, shot in enumerate(SHOTS, 1):
        pnode = flow.nodes[f"Team HMBPromptLibrary {n}"]
        anode = flow.nodes[f"Team HMBAgentLibrary {n}"]
        expected["prompt"][shot["shot_uuid"]] = deepcopy(pnode._current_state())
        for field in expected["agent"][shot["shot_uuid"]]["values"]:
            expected["agent"][shot["shot_uuid"]]["values"][field] = encode_value(anode.get_parameter_value(field))
        anode.parameter_output_values["output"] = expected["agent"][shot["shot_uuid"]]["output"]
    expected["edges"] = edges(engine, flow)
    expected["metadata"] = {node.name: encode_value(deepcopy(node.metadata)) for node in flow.nodes.values()}
    serialized = send(engine, SerializeFlowToCommandsRequest(flow_name=flow.name)).serialized_flow_commands
    (OUT / "team801-synthetic-commands.json").write_text(json.dumps(encode_value(serialized), ensure_ascii=False), encoding="utf-8")
    (OUT / "team801-synthetic-expected.json").write_text(json.dumps(expected, ensure_ascii=False), encoding="utf-8")
    assert len(flow.nodes) == 22
    print("TEAM801_BUILD=PASS nodes22 actual published legacy classes; five Prompt/Agent/Finish documents; no execution")


async def serialize_after_native_dispatch(engine, flow):
    """Let detached native completion hooks release their own admissions."""
    from griptape_nodes.retained_mode.events.flow_events import SerializeFlowToCommandsRequest
    deadline = time.monotonic() + 10
    refused = 0
    while True:
        request = SerializeFlowToCommandsRequest(flow_name=flow.name)
        request.broadcast_result = False
        result = engine.handle_request(request)
        if result.succeeded():
            print(f"NATIVE_SERIALIZE_SETTLED=PASS busy_refusals={refused}")
            return result.serialized_flow_commands
        message = str(result.result_details)
        assert "The workflow is still loading, consolidating, or being serialized." in message, message
        refused += 1
        assert time.monotonic() < deadline, ("Native post-dispatch did not settle", refused, message)
        await asyncio.sleep(.01)


async def consume_current(engine, package, modules, *, resume_native_dispatch):
    from griptape_nodes.retained_mode.events.flow_events import DeserializeFlowFromCommandsRequest, SerializeFlowToCommandsRequest, DeleteFlowRequest
    from griptape_nodes.serialization.values import decode_value, encode_value
    import _hmb_workflow_migration as migration
    prompts, agents, finishes = (modules[k] for k in KINDS[2:5])
    register(engine, package, modules)
    engine.event_manager.initialize_queue()
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    context = send(engine, EnsureWorkflowAndFlowRequest(flow_name="Current804CompatibilityContext"))
    while engine.context_manager.has_current_flow():
        engine.context_manager.pop_flow()
    send(engine, DeleteFlowRequest(flow_name=context.flow_name))
    expected = json.loads((OUT / "team801-synthetic-expected.json").read_text("utf-8"))
    serialized = decode_value(json.loads((OUT / "team801-synthetic-commands.json").read_text("utf-8")))
    loaded = await engine.ahandle_request(DeserializeFlowFromCommandsRequest(serialized_flow_commands=serialized, broadcast_result=False))
    assert loaded.succeeded(), str(loaded.result_details)
    flow = engine.flow_manager.get_flow_by_name(loaded.flow_name)
    engine.context_manager.push_flow(flow)
    assert len(flow.nodes) == 22
    pre = {}
    for n in range(1,6):
        anode = flow.nodes[f"Team HMBAgentLibrary {n}"]
        exported = anode._hmb_export_agent_authoring_state()
        value = exported["native_slot"]["values"].get("prompt")
        pre[str(n)] = dict(raw_prompt_length=len(str(anode.get_parameter_value("prompt") or "")),
            native_prompt_length=len(str(value or "")), native_prompt_sha256=sha(value),
            legacy_widget=exported.get("legacy_widget"), active=exported.get("active_subscription"),
            slots={key:{"prompt_length":len(str(slot.get("values",{}).get("prompt") or "")),"prompt_sha256":sha(slot.get("values",{}).get("prompt"))} for key,slot in getattr(anode,"_hmb_shot_slots",{}).items()},
            before_preview_length=len(str(getattr(anode,"_hmb_prompt_before_preview","") or "")),
            before_preview_sha256=sha(getattr(anode,"_hmb_prompt_before_preview",None)))
    (OUT / "current-pre-migration-agent-summary.json").write_text(json.dumps(pre,ensure_ascii=False,indent=2),encoding="utf-8")
    migration.mark_flow_migration_pending(engine, flow.name)
    result = await migration.migrate_flow(engine, flow.name, backup_root=OUT / "migration-backups")
    assert result["ok"] and result["code"] == "consolidated", result
    # The pre-migration capture is complete. Restore the real notification
    # scheduler before serialization and the second native deserialize.
    resume_native_dispatch()
    assert len(flow.nodes) == 10 and len(result["removed_nodes"]) == 12
    prompt = next(n for n in flow.nodes.values() if n.metadata.get("node_type") == KINDS[2])
    agent = next(n for n in flow.nodes.values() if n.metadata.get("node_type") == KINDS[3])
    finish = next(n for n in flow.nodes.values() if n.metadata.get("node_type") == KINDS[4])
    def verify():
        issues = []
        docs = prompt._hmb_prompt_merge_snapshot()["materialized_documents"]
        for shot in SHOTS:
            key = CHANNEL + "/" + shot["shot_uuid"]
            before = expected["prompt"][shot["shot_uuid"]]
            document = json.loads(docs[key])
            for field in ("text", "images", "videos", "ui"):
                original, restored = before[field], document[field]
                if field == "ui":
                    assert set(restored) - set(original) <= {"shot_editor_expanded"}
                    restored = {key: restored[key] for key in original}
                if field in {"images", "videos"}:
                    # Blank legacy default rows may collapse to one placeholder;
                    # every authored row/control must remain byte-equivalent.
                    original = [row for row in original if str(row.get("label", "")).startswith("Team ")]
                    restored = [row for row in restored if str(row.get("label", "")).startswith("Team ")]
                if restored != original:
                    (OUT / "synthetic-field-difference.json").write_text(json.dumps(dict(shot=shot["number"],field=field,before=original,after=restored),ensure_ascii=False,indent=2),encoding="utf-8")
                assert restored == original, (shot["number"], field)
            slot = agent._hmb_shot_slots[agent._hmb_slot_key(CHANNEL, shot["shot_uuid"])]
            for field, value in expected["agent"][shot["shot_uuid"]]["values"].items():
                if encode_value(slot["values"][field]) != value:
                    (OUT / "synthetic-agent-difference.json").write_text(json.dumps(dict(shot=shot["number"],field=field,before=value,after=encode_value(slot["values"][field])),ensure_ascii=False,indent=2),encoding="utf-8")
                if encode_value(slot["values"][field]) != value:
                    issues.append((shot["number"], "Agent", field))
            assert slot["outputs"]["output"] == expected["agent"][shot["shot_uuid"]]["output"]
            assert any(value == expected["agent"][shot["shot_uuid"]]["rule"] for value in slot["children"].values()), (shot["number"], "native ruleset child")
            fdoc = finish._hmb_finish_documents[finish._hmb_finish_key(CHANNEL, shot["shot_uuid"])]
            if fdoc["finish_look"] != expected["finish"][shot["shot_uuid"]]:
                (OUT / "synthetic-finish-difference.json").write_text(json.dumps(dict(shot=shot["number"],before=expected["finish"][shot["shot_uuid"]],after=fdoc["finish_look"]),ensure_ascii=False,indent=2),encoding="utf-8")
            assert fdoc["finish_look"] == expected["finish"][shot["shot_uuid"]], (shot["number"], "Finish authoring")
        for name, values in expected["generators"].items():
            node = flow.nodes[name]
            actual = {key: encode_value(node._get_list_input(key) if key in {"reference_images", "VIDEO_REFERENCES", "reference_audio"} else node._get_raw_parameter_value(key)) for key in values}
            assert actual == values, (name, "Generator settings or reference list")
            # Original native node metadata, including authored layout/literals,
            # is preserved for every surviving Generator.
            for key, value in expected["metadata"][name].items():
                assert encode_value(node.metadata[key]) == value, (name, key)
        return issues
    issues_before = verify()
    first_edges = edges(engine, flow)
    aliases = {name: record["node_name"] for name, record in result["aliases"].items()}
    expected_edges = sorted({(aliases.get(src, src), output, aliases.get(dst, dst), input_name)
        for src, output, dst, input_name in expected["edges"]})
    assert first_edges == expected_edges, "Migration must preserve exactly the contracted legacy connections"
    backup = decode_value(json.loads(Path(result["backup_path"]).read_text("utf-8")))
    assert len(backup["nodes"]) == 22 and len(backup["edges"]) == len(expected["edges"])
    serialized = await serialize_after_native_dispatch(engine, flow)
    # SDK enforces current-context ordering during DeleteFlow. Explicitly pop
    # its child Node context before deleting only this isolated test flow.
    while engine.context_manager.has_current_flow():
        engine.context_manager.pop_flow()
    send(engine, DeleteFlowRequest(flow_name=flow.name))
    loaded = await engine.ahandle_request(DeserializeFlowFromCommandsRequest(serialized_flow_commands=serialized, broadcast_result=False))
    assert loaded.succeeded(), str(loaded.result_details)
    flow = engine.flow_manager.get_flow_by_name(loaded.flow_name)
    engine.context_manager.push_flow(flow)
    await serialize_after_native_dispatch(engine, flow)
    prompt = flow.nodes[prompt.name];agent = flow.nodes[agent.name];finish = flow.nodes[finish.name]
    issues_after = verify()
    assert edges(engine, flow) == first_edges
    (OUT / "compatibility-issues.json").write_text(json.dumps(dict(before_roundtrip=issues_before,after_roundtrip=issues_after),indent=2),encoding="utf-8")
    assert not issues_before and not issues_after, (issues_before, issues_after)
    summary = dict(status="PASS", team_archive_sha256=ARCHIVE_SHA, legacy_nodes=22, local_nodes=10,
        prompt_documents=5, agent_documents=5, finish_documents=5, exact_roundtrip_edges=len(first_edges),
        generator_settings_exact=5, provider_or_model_calls=0, live_graph_writes=0, installed_writes=0)
    (OUT / "team801-local804-native-result.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("TEAM801_LOCAL804_COMPATIBILITY=PASS legacy22->10; exact five authored Prompt/Agent/Finish documents; native schema/provider/model/rules/results; Generator Draft/Resume/settings; save/reload edges")


def phase(which):
    sys.dont_write_bytecode = True
    package = OUT / "team-package/HMB_GP_Production" if which == "team" else ROOT
    sys.path.insert(0, str(package))
    # The fixture compares authored state, not dependency discovery. Use the
    # installed Standard edit dependencies append-only; its separate cold-load
    # and cross-library discovery regressions cover that platform contract.
    standard = Path.home() / "Documents/GriptapeNodes/libraries/griptape-nodes-library-standard"
    os.environ.setdefault("HMB_GRIPTAPE_STANDARD_LIBRARY_PATH", str(standard))
    standard_site = standard / ".venv/Lib/site-packages"
    if str(standard_site) not in sys.path:
        sys.path.append(str(standard_site))
    modules = {kind: importlib.import_module(kind) for kind in KINDS}
    import _hmb_shot_routing as routing
    with ExitStack() as guard:
        resume_native_dispatch = lambda: None
        import _hmb_library_bootstrap as bootstrap
        guard.enter_context(mock.patch.object(bootstrap._Registration, "start_web_worker", lambda *a, **k: None))
        if which == "current":
            import _hmb_workflow_migration as migration
            # The public deserialize pre-dispatch capture remains real. Keep
            # its coordinator paused only until pre-migration diagnostics are
            # captured; the native migrate/rollback implementation runs below.
            pause = mock.patch.object(migration, "schedule_loaded_flow_migrations", lambda *a, **k: None)
            pause.start()
            guard.callback(pause.stop)
            resume_native_dispatch = pause.stop
        for name in ("schedule_post_registration_reconcile", "schedule_post_hydration_reconcile"):
            guard.enter_context(mock.patch.object(routing, name, lambda *a, **k: False))
        guard.enter_context(mock.patch.object(modules[KINDS[0]].HMBImageAssetLibrary, "_schedule_catalog_scan", lambda *a, **k: None))
        guard.enter_context(mock.patch.object(modules[KINDS[3]].HMBAgentLibrary, "process", deny))
        guard.enter_context(mock.patch.object(modules[KINDS[5]].HMBSeedanceGeneration, "_process_generation", deny))
        logging.disable(logging.CRITICAL)
        from griptape_nodes.retained_mode.engine import engine_scope
        with engine_scope() as engine:
            asyncio.run(build_team(engine, package, modules) if which == "team" else consume_current(
                engine, package, modules, resume_native_dispatch=resume_native_dispatch))
        assert not ATTEMPTS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("team", "current"))
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    assert ARCHIVE.exists() and hashlib.sha256(ARCHIVE.read_bytes()).hexdigest() == ARCHIVE_SHA, "Published Team801 fixture missing or changed"
    if args.phase:
        phase(args.phase)
        return
    with zipfile.ZipFile(ARCHIVE) as archive:
        for member in archive.infolist():
            target = (OUT / "team-package" / member.filename).resolve()
            assert target.is_relative_to((OUT / "team-package").resolve())
            archive.extract(member, OUT / "team-package")
    sdk = Path.home() / "AppData/Local/ai.griptape.nodes.desktop/current/resources/engine-bundle/python/python.exe"
    wrapper = ROOT / "reports/release-v95-local-v96-20261015/even94-guarded-child.py"
    offline = ROOT / ".test-cache/full-library-audit-v90-20261013/sdk-offline-child.py"
    pinned_files = [*map(lambda kind: ROOT / f"{kind}.py", KINDS), ROOT / "_hmb_common.py",
        ROOT / "_hmb_library_bootstrap.py", ROOT / "_hmb_shot_routing.py", ROOT / "_hmb_workflow_migration.py",
        ROOT / "griptape-nodes-library.json", Path(__file__).resolve()]
    pins = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in pinned_files}
    for mode in ("team", "current"):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1",
            HMB_SDK_GUARD_RECEIPT=str(OUT / f"{mode}-offline-guard.json"),
            HMB_SDK_ISOLATED_ROOT=str(OUT / f"{mode}-isolated"))
        completed = subprocess.run([str(sdk), "-I", "-B", str(wrapper), str(offline), str(Path(__file__).resolve()),
            "--phase", mode], cwd=ROOT, env=env, text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=120)
        (OUT / f"{mode}-stdout-stderr.txt").write_text(completed.stdout + completed.stderr, encoding="utf-8")
        print(completed.stdout[-2500:])
        assert completed.returncode == 0, completed.stderr[-5000:]
        receipt = json.loads((OUT / f"{mode}-offline-guard.json").read_text("utf-8"))
        assert receipt["external_network_attempt_count"] == 0
    assert pins == {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in pinned_files}, "Source changed during the two-process compatibility run"
    final = json.loads((OUT / "team801-local804-native-result.json").read_text("utf-8"))
    final.update(source_and_test_sha256=pins, source_and_test_stable=True,
        team_offline_guard=json.loads((OUT / "team-offline-guard.json").read_text("utf-8")),
        current_offline_guard=json.loads((OUT / "current-offline-guard.json").read_text("utf-8")))
    (OUT / "team801-local804-native-result.json").write_text(json.dumps(final, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
