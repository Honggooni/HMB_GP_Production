"""Exercise the native HMB 로동마트 request with the real retained Desktop SDK.

Two fresh processes share only the fixture files and serialized workflow.
No StartFlow, provider, Broker, or render request is allowed.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import ExitStack
import hashlib
import importlib
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
import traceback
from unittest import mock
from uuid import UUID
import wave

TESTS = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("HMB_SHOT_BASKET_TEST_ROOT", str(TESTS.parents[1]))).resolve()
sys.path[:0] = [str(ROOT), str(TESTS)]
import HMB_Seedance_Execution_Mode_Host_Regression as harness


NODE_MODULES = {
    "image": "HMBImageAssetLibrary",
    "video": "HMBVideoPickerLibrary",
    "sound": "HMBSoundLibrary",
    "prompt": "HMBPromptLibrary",
    "agent": "HMBAgentLibrary",
    "generator": "HMBSeedanceGeneration",
}
PROJECT_ID = "katuri8"
SHOT_NAME = "로동마트 Offline Reference Shot"


def media_files(out):
    from PIL import Image

    projects = out / "fixtures" / "projects"
    project = projects / PROJECT_ID
    images = project / "Ai_Ct_image" / "BG"
    audio = project / "Ai_Ct_audio" / "SFX"
    images.mkdir(parents=True, exist_ok=True)
    audio.mkdir(parents=True, exist_ok=True)
    registered_names = ("basket-cyan", "basket-magenta")
    for name, color in zip((*registered_names, "basket-unregistered"), ("cyan", "magenta", "black"), strict=True):
        path = images / f"{name}.png"
        if not path.exists():
            Image.new("RGB", (32, 24), color).save(path)
    manifest = images.parent / ".json" / "hmb_image_assets.json"
    if not manifest.exists():
        manifest.parent.mkdir()
        manifest.write_text(json.dumps({"schema": "hmb-image-assets", "version": 1, "assets": [
            {"relative_path": f"BG/{name}.png", "asset_id": name, "image_name": name} for name in registered_names]}), "utf-8")
    sound = audio / "basket-tick.wav"
    if not sound.exists():
        with wave.open(str(sound), "wb") as output:
            output.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
            output.writeframes(b"\x00\x10\x00\xf0" * 1000)
    return projects


def project_available(data):
    return any(project["project_id"].casefold() == PROJECT_ID for project in data["projects"])


async def wait_for(read, ready, *, timeout=30):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        value = await read()
        if ready(value):
            return value
        assert loop.time() < deadline, value
        await asyncio.sleep(.05)


def media_id(data, name):
    ids = [item["source_uid"] for item in data["items"] if name in item["name"].casefold()]
    assert len(ids) == 1, (name, data["items"])
    return ids[0]


def retained_edges(engine):
    return sorted((edge.source_node.name, edge.source_parameter.name, edge.target_node.name, edge.target_parameter.name)
                  for edge in engine.flow_manager.get_connections().connections.values())


async def exercise(engine, phase, out):
    logging.disable(logging.NOTSET)
    basket_log = logging.getLogger("_hmb_shot_basket")
    basket_log.setLevel(logging.DEBUG)
    basket_log.addHandler(logging.StreamHandler())
    os.environ["HMB_IMAGE_PROJECTS_ROOT"] = str(media_files(out))
    modules = {kind: importlib.import_module(name) for kind, name in NODE_MODULES.items()}
    from _hmb_library_bootstrap import HMBProductionLibrary
    from griptape_nodes.node_library.library_registry import LibraryRegistry, LibrarySchema
    from griptape_nodes.retained_mode import engine as sdk_engine
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    from griptape_nodes.retained_mode.events.flow_events import SerializeFlowToCommandsRequest
    from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry
    from griptape_nodes.retained_mode.events.workflow_events import (
        RunWorkflowWithCurrentStateRequest, SaveWorkflowFileFromSerializedFlowRequest,
    )

    # Desktop worker threads use the process root and do not inherit ContextVars.
    # Point the isolated process root at the same real engine as the harness.
    assert sdk_engine._root_engine in (None, engine)
    sdk_engine._root_engine = engine
    descriptor = LibrarySchema.model_validate_json((ROOT / "griptape-nodes-library.json").read_text("utf-8-sig"))
    advanced = HMBProductionLibrary()
    library = LibraryRegistry.generate_new_library(descriptor, advanced_library=advanced)
    classes = {name: getattr(modules[kind], name) for kind, name in NODE_MODULES.items()}
    for definition in descriptor.nodes:
        cls = classes.get(definition.class_name)
        if cls is not None:
            library.register_lazy_node_type(definition.class_name, definition.metadata, lambda cls=cls: cls)
    engine.event_manager.initialize_queue()
    advanced.before_library_nodes_loaded(descriptor, library)
    request_type = PayloadRegistry.get_type("HMBShotBasketRequest")
    assert request_type is not None, "HMB library bootstrap did not register the native basket event"

    async def request(action, *, flow_name="", success=True, **payload):
        harness.REQUESTS += 1
        event = request_type(action=action, payload={"flow_name": flow_name, **payload}, broadcast_result=False)
        result = await engine.ahandle_request(event)
        data = getattr(result, "data", {})
        assert result.succeeded() is success, (result.result_details, data)
        return data

    async def catalog(flow_name, shot_id, kind, name):
        return await wait_for(lambda: request("catalog", flow_name=flow_name, shot_uuid=shot_id, kind=kind, query=name),
                              lambda data: any(name in item["name"].casefold() for item in data.get("items", [])))

    def active_nodes():
        flow = engine.context_manager.get_current_flow()
        by_type = {node.metadata.get("node_type"): node for node in flow.nodes.values()}
        assert len(flow.nodes) == len(by_type) == len(NODE_MODULES), sorted(by_type)
        return {kind: by_type[name] for kind, name in NODE_MODULES.items()}

    def verify_routes(nodes, shot_id):
        image, video, sound, prompt, agent, generator = (nodes[kind] for kind in NODE_MODULES)
        for node in (video, prompt, agent, generator):
            subscription = node._hmb_shot_channel_subscription()
            assert subscription["shot_uuid"] == shot_id and subscription["channel_uuid"], (node.name, subscription)
        assert sound._hmb_shot_channel_subscription()["channel_uuid"] == image._current_state()["shot_routing"]["channel_uuid"]
        edges = retained_edges(engine)
        expected = {
            (image.name, "SHOT_ASSET_OUT", prompt.name, "SHOT_ASSET_IN"),
            (video.name, "SHOT_PICKER_OUT", prompt.name, "SHOT_PICKER_IN"),
            (sound.name, "SHOT_SOUND_OUT", prompt.name, "SOUND_IN"),
            (prompt.name, "PROMPT_OUT", agent.name, "SHOT_PROMPT_IN"),
            (agent.name, "output", generator.name, "prompt"),
        }
        assert expected <= set(edges), (expected - set(edges), edges)
        return edges

    async def verify_selection(nodes, flow_name, shot_id, selection):
        image_state = nodes["image"]._current_state()
        image_shot = next(row for row in image_state["shot_routing"]["shots"] if row["shot_uuid"] == shot_id)
        assert image_shot["selected_source_uids"] == selection["image"], image_shot
        for kind, ids in selection.items():
            await wait_for(lambda: request("catalog", flow_name=flow_name, shot_uuid=shot_id, kind=kind),
                           lambda data: data["status"] == "ready"
                           and {row["source_uid"] for row in data["items"] if row["selected"]} == set(ids))

    async def verify_delivery(nodes, shot_id, sound_uid):
        prompt = nodes["prompt"]
        channel_uuid = nodes["image"]._current_state()["shot_routing"]["channel_uuid"]

        async def document():
            try:
                return prompt._hmb_prompt_shot_document(channel_uuid=channel_uuid, shot_uuid=shot_id)
            except (modules["image"]._ImageAssetSelectionPreparing, modules["video"]._HMBPickerMediaPreparing) as preparing:
                return {"preparing": str(preparing)}
            except ValueError as preparing:
                if str(preparing) != "VideoPicker has no validated ImageAsset Shot catalog.":
                    raise
                return {"preparing": str(preparing)}

        selected = await wait_for(document, lambda doc: (len(doc.get("image_media", [])) == 2
                                                        and len(doc.get("video_media", [])) == 1
                                                        and len(doc.get("audio_sources", {}).get("tracks", [])) == 1))
        assert [row["source_uid"] for row in selected["audio_sources"]["tracks"]] == [sound_uid], selected["audio_sources"]
        machine_prompt = selected["machine_prompt"].casefold()
        assert machine_prompt.index("basket-magenta") < machine_prompt.index("basket-cyan")
        assert "basket-clip" in machine_prompt, machine_prompt
        node = nodes["generator"]
        generator = modules["generator"]
        params = node._get_parameters()
        params.update(model_id=generator.SEEDANCE_2_5_MODEL_ID, task=generator.TASK_REFERENCE_TO_VIDEO,
                      prompt="Use @image1, @image2, @video1 in their shot roles.", duration=5, resolution="480p")
        resolved = node._resolve_exact_shot_generation_inputs(params)
        assert resolved["_hmb_generation_mode"] == "shot", resolved["_hmb_generation_mode"]
        assert len(resolved["reference_images"]) == 2 and len(resolved["video_references"]) == 1
        assert [row["source_uid"] for row in resolved["_hmb_sound_tracks"]] == [sound_uid]

    saved = out / "basket-workflow.py"
    identity = out / "basket-expected.json"

    def deny(*args, **kwargs):
        traceback.print_stack(limit=10)
        return harness.deny(*args, **kwargs)

    with ExitStack() as guards:
        generator = modules["generator"]
        guards.enter_context(mock.patch.object(generator._HMBAIBrokerBridge, "_request_json", deny))
        guards.enter_context(mock.patch.object(generator.HMBSeedanceGeneration, "_process_generation", deny))
        guards.enter_context(mock.patch.object(modules["agent"]._BaseAgent, "_process", deny))
        if phase == "reopen":
            expected = json.loads(identity.read_text("utf-8"))
            reopened = await harness.asend(engine, RunWorkflowWithCurrentStateRequest(file_path=str(saved)))
            assert reopened.status.name == "GOOD", reopened.status
            flow_name = engine.context_manager.get_current_flow().name
            status = await wait_for(lambda: request("status", flow_name=flow_name),
                                    lambda data: data["status"] == "ready" and data["shot_uuid"] == expected["shot_id"])
            assert status["shots"] == expected["shots"]
            nodes = active_nodes()
            assert {kind: node.name for kind, node in nodes.items()} == expected["nodes"]
            await verify_selection(nodes, flow_name, expected["shot_id"], expected["selection"])
            assert verify_routes(nodes, expected["shot_id"]) == [tuple(edge) for edge in expected["edges"]]
            await verify_delivery(nodes, expected["shot_id"], expected["selection"]["sound"][0])
            harness.record("cold_native_open_retains_shot_media_order_nodes_and_routes", shot_id=expected["shot_id"],
                           applied=expected["selection"], connections=len(expected["edges"]))
            return

        assert not engine.context_manager.has_current_flow()
        before = await wait_for(lambda: request("status"), project_available)
        assert before["status"] == "empty" and not before["shot_uuid"] and not engine.context_manager.has_current_flow()
        project_id = next(row["project_id"] for row in before["projects"] if row["project_id"].casefold() == PROJECT_ID)
        ensured = await harness.asend(engine, EnsureWorkflowAndFlowRequest(display_name="Rodong Mart regression"))
        flow_name, workflow_name = ensured.flow_name, ensured.workflow_name
        prepared = await request("prepare", flow_name=flow_name, workflow_name=workflow_name)
        assert prepared["prepared"] and prepared["created"]
        created = await request("create", flow_name=flow_name, workflow_name=workflow_name,
                                project_id=project_id, shot_name=SHOT_NAME)
        assert created["bound"] and created["flow_name"] == flow_name
        status = await wait_for(lambda: request("status", flow_name=flow_name),
                                lambda data: data["status"] == "ready" and data["shot_uuid"])
        shot_id = str(UUID(status["shot_uuid"]))
        assert status["project_id"].casefold() == PROJECT_ID
        assert [row["name"] for row in status["shots"]] == [SHOT_NAME], status
        nodes = active_nodes()
        harness.record("native_empty_launcher_discovers_project_and_creates_six_nodes", flow=flow_name, shot_id=shot_id)

        first = media_id(await catalog(flow_name, shot_id, "image", "basket-cyan"), "basket-cyan")
        second = media_id(await catalog(flow_name, shot_id, "image", "basket-magenta"), "basket-magenta")
        unregistered = await request("catalog", flow_name=flow_name, shot_uuid=shot_id,
                                     kind="image", query="basket-unregistered")
        assert unregistered["status"] == "ready" and not unregistered["items"], unregistered
        sound = media_id(await catalog(flow_name, shot_id, "sound", "basket-tick"), "basket-tick")
        from _hmb_video_tools import _find_ffmpeg
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        GriptapeNodes.StaticFilesManager()._static_server_base_url = "http://127.0.0.1:43219"
        clip = out / "fixtures" / "basket-clip.mp4"
        subprocess.run([_find_ffmpeg(), "-nostdin", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=96x64:r=24",
                        "-t", "0.25", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip)], check=True)
        with mock.patch.object(modules["video"], "_choose_video_asset_files", return_value=[str(clip)]) as choose:
            await request("browse", flow_name=flow_name, shot_uuid=shot_id, kind="video", request_id="native-browse")
            staged_rows = await catalog(flow_name, shot_id, "video", "basket-clip")
            choose.assert_called_once()
        staged = media_id(staged_rows, "basket-clip")
        assert staged_rows["items"][0].get("staged") is True and staged_rows["items"][0]["selected"] is False
        selection = {"image": [second, first], "video": [staged], "sound": [sound]}
        items = [{"kind": kind, "source_uid": uid, "selected": True}
                 for kind, ids in selection.items() for uid in ids]
        foreign_shot = "11111111-1111-4111-8111-111111111111"
        await request("apply", flow_name=flow_name, shot_uuid=foreign_shot, items=items, success=False)
        await request("apply", flow_name=flow_name, shot_uuid=shot_id, items=items + [items[0]], success=False)
        await verify_selection(nodes, flow_name, shot_id, {kind: [] for kind in selection})
        applied = await request("apply", flow_name=flow_name, shot_uuid=shot_id, request_id="first", items=items)
        first_statuses = [row["status"] for row in applied["items"]]
        assert first_statuses == ["applied", "applied", "pending", "pending"], (
            applied, nodes["image"]._current_state()["shot_routing"]["shots"])
        finished = await wait_for(lambda: request("apply", flow_name=flow_name, shot_uuid=shot_id,
                                                  request_id="first", items=items), lambda data: data["ok"])
        assert all(row["ok"] for row in finished["items"]), finished
        registered_rows = await catalog(flow_name, shot_id, "video", "basket-clip")
        video = media_id(registered_rows, "basket-clip")
        assert video != staged and not registered_rows["items"][0].get("staged")
        selection["video"] = [video]
        harness.record("native_picker_browse_then_apply_imports_real_local_mp4_to_exact_shot", source_uid=video)
        await verify_selection(nodes, flow_name, shot_id, selection)
        items = [{"kind": kind, "source_uid": uid, "selected": True}
                 for kind, ids in selection.items() for uid in ids]
        retry = await request("apply", flow_name=flow_name, shot_uuid=shot_id, request_id="retry", items=items)
        assert retry["ok"] and all(row["status"] == "unchanged" for row in retry["items"]), retry
        assert retry == await request("apply", flow_name=flow_name, shot_uuid=shot_id, request_id="retry", items=items)
        unselect_video = {"kind": "video", "source_uid": video, "selected": False}
        removed = await request("apply", flow_name=flow_name, shot_uuid=shot_id, request_id="drop-video", items=[unselect_video])
        assert removed["ok"] and removed["items"][0]["status"] == "applied", removed
        await verify_selection(nodes, flow_name, shot_id, {**selection, "video": []})
        restored = await request("apply", flow_name=flow_name, shot_uuid=shot_id, request_id="restore-video",
                                 items=[{**unselect_video, "selected": True}])
        assert restored["ok"] and restored["items"][0]["status"] == "applied", restored
        await verify_selection(nodes, flow_name, shot_id, selection)
        harness.record("native_apply_rejects_foreign_shot_preserves_order_and_is_idempotent", applied=selection)

        edges = verify_routes(nodes, shot_id)
        await verify_delivery(nodes, shot_id, sound)
        harness.record("selected_image_video_sound_reach_prompt_and_generator_preparation", shot_id=shot_id)
        serialized = harness.send(engine, SerializeFlowToCommandsRequest(flow_name=flow_name)).serialized_flow_commands
        await harness.asend(engine, SaveWorkflowFileFromSerializedFlowRequest(file_name=saved.stem,
            file_path=str(saved), display_name=SHOT_NAME, serialized_flow_commands=serialized))
        identity.write_text(json.dumps({"shot_id": shot_id, "shots": status["shots"], "selection": selection,
            "nodes": {kind: node.name for kind, node in nodes.items()}, "edges": edges}, ensure_ascii=False), "utf-8")
        harness.record("native_workflow_saved_without_executing_the_graph", workflow_sha256=hashlib.sha256(saved.read_bytes()).hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("save", "reopen"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    if args.phase:
        harness.ROOT = ROOT
        harness.exercise = exercise
        harness.PRODUCTS = (*[f"{name}.py" for name in NODE_MODULES.values()],
                            "_hmb_shot_basket.py", "_hmb_library_bootstrap.py", "_hmb_workflow_migration.py")
        harness.run_phase(args.phase, out)
        return
    out.mkdir(parents=True, exist_ok=False)
    for phase in ("save", "reopen"):
        if phase == "reopen":
            # Retain the imported workspace media, while config, caches and the
            # engine itself all start fresh in the reopen process.
            for directory in ("inputs", ".griptape-nodes-metadata"):
                saved = out / "save-profile" / "workspace" / directory
                if directory == "inputs" or saved.is_dir():
                    shutil.copytree(saved, out / "reopen-profile" / "workspace" / directory)
        child = subprocess.run([sys.executable, "-I", "-B", "-X", "utf8", __file__, "--phase", phase, "--out", str(out)],
                               capture_output=True, timeout=120, check=False)
        (out / f"{phase}-stdout-stderr.txt").write_bytes(child.stdout + child.stderr)
        if child.returncode:
            sys.stdout.buffer.write(child.stdout + child.stderr)
            raise SystemExit(child.returncode)
        result = json.loads((out / f"{phase}-result.json").read_text("utf-8"))
        assert result["passed"] and not result["external_or_live_socket_attempts"], result
    print("HMB_SHOT_BASKET_HOST=PASS (fresh native save/reopen, no provider calls)")


if __name__ == "__main__":
    main()
