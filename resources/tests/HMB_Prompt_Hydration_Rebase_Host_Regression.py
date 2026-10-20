"""Actual saved five-Prompt workflow: bounded per-document publisher rebasing."""
from __future__ import annotations

import asyncio
from contextlib import ExitStack
from copy import deepcopy
import importlib.util
import hashlib
import json
import logging
import os
from pathlib import Path
import socket
import sys
import tempfile
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
os.environ.setdefault("HMB_GRIPTAPE_STANDARD_LIBRARY_PATH", str(
    Path.home() / "Documents/GriptapeNodes/libraries/griptape-nodes-library-standard"))
ATTEMPTS = []


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":")).encode("utf-8")).hexdigest()


def deny_external(*args, **kwargs):
    ATTEMPTS.append(True)
    raise AssertionError("Publisher hydration regression attempted external work")


def load_helpers():
    path = ROOT / "resources/tests/HMB_Workflow_Consolidation_Host_Regression.py"
    spec = importlib.util.spec_from_file_location("hmb_prompt_rebase_saved_fixture", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def snapshots(images, picker, source, catalog):
    rows = [{**row, "selected_source_uids": []} for row in catalog["shots"]]
    document = {"channel_uuid": catalog["channel_uuid"], "generation": 1,
        "project_id": source._hmb_project_identity()["project_id"], "shots": rows, "ordered_assets": []}
    image = {"schema": images.SHOT_ROUTING_SNAPSHOT_SCHEMA, "version": 1,
        "publisher_instance_uuid": catalog["publisher_instance_uuid"], **document,
        "metadata_sha256": digest(document),
        "media_sha256": digest({"media_descriptors": []}), "media_by_source_uid": {}}
    payload, _media = picker._build_synchronized_video_outputs(picker._default_widget_state())
    picker_rows = [{**row, "picker_payload": deepcopy(payload)} for row in rows]
    video_document = {"channel_uuid": catalog["channel_uuid"], "generation": 1,
        "shots": picker_rows, "ordered_videos": []}
    video = {"schema": "hmb-picker-shot-routing-snapshot", "version": 1,
        "publisher_instance_uuid": "77777777-7777-4777-8777-777777777777", **video_document,
        "metadata_sha256": digest(video_document),
        "media_sha256": digest({"media_descriptors": []}), "media_by_source_uid": {}}
    return image, video


async def exercise(engine, directory, helpers, native_hydration, native_schedule):
    import HMBPromptLibrary as prompts
    import HMBImageAssetLibrary as images
    import HMBVideoPickerLibrary as picker
    import _hmb_shot_routing as routing
    from griptape_nodes.node_library.library_registry import LibraryRegistry
    from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
    from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest, DeleteConnectionRequest
    helpers.NATIVE_HYDRATION_SCHEDULER = native_hydration
    await helpers.actual_saved_file_case(engine, directory, complete_manual_rebind=True)
    library, advanced, _images, _prompts, _agents, _generators = helpers.register_library(engine)
    try:
        flow = next(engine.flow_manager.get_flow_by_name(name) for name in engine.flow_manager._name_to_parent_name
            if any(node.metadata.get("node_type") == "HMBPromptLibrary"
                for node in engine.flow_manager.get_flow_by_name(name).nodes.values()))
        while engine.context_manager.has_current_flow():
            engine.context_manager.pop_flow()
        engine.context_manager.push_flow(flow)
        manager = next(node for node in flow.nodes.values() if node.metadata.get("node_type") == "HMBPromptLibrary")
        source = next(node for node in flow.nodes.values() if node.metadata.get("node_type") == "HMBImageAssetLibrary")
        picker_node = next(node for node in flow.nodes.values() if node.metadata.get("node_type") == "HMBVideoPickerLibrary")
        catalog = source._hmb_shot_routing_catalog()
        assert len(catalog["shots"]) == 5
        image_snapshot, picker_snapshot = snapshots(images, picker, source, catalog)
        prompts._validate_shot_routing_snapshot(image_snapshot)
        prompts._validate_picker_shot_routing_snapshot(picker_snapshot, expected_channel_uuid=catalog["channel_uuid"])
        source._hmb_shot_routing_snapshot = lambda **kwargs: deepcopy(image_snapshot)
        # Both official readers represent this fixture's same synthetic,
        # no-media source epoch. Real target-isolation is tested separately.
        source._hmb_shot_routing_snapshot_for = lambda **kwargs: deepcopy(image_snapshot)
        picker_node._hmb_shot_routing_snapshot = lambda **kwargs: deepcopy(picker_snapshot)
        picker_node._hmb_shot_routing_snapshot_for = lambda **kwargs: deepcopy(picker_snapshot)
        picker_node._hmb_shot_channel_subscription = lambda: {"participant_kind": "video_picker",
            "enabled": True, "channel_uuid": catalog["channel_uuid"]}
        manager._reconcile_connected_source_inputs_from_graph()
        # Consume the visible legacy one-shot allowance first, reproducing the
        # state that previously broke every dormant document on a later read.
        manager._consume_routing_hydration_rebase()
        raw_before = deepcopy(manager.get_parameter_value(prompts.WIDGET_PARAMETER_NAME))
        outputs_before = deepcopy(dict(manager.parameter_output_values))
        documents = [manager._hmb_prompt_shot_document(channel_uuid=catalog["channel_uuid"], shot_uuid=row["shot_uuid"])
            for row in catalog["shots"]]
        assert len(documents) == 5 and len({document["fingerprint"] for document in documents}) == 5
        for row, document in zip(catalog["shots"], documents):
            assert document["shot"]["shot_uuid"] == row["shot_uuid"] and document["shot"]["name"] == row["name"]
            assert document["image_media"] == document["video_media"] == []
        for _ in range(3):
            for row in reversed(catalog["shots"]):
                manager._hmb_prompt_shot_document(channel_uuid=catalog["channel_uuid"], shot_uuid=row["shot_uuid"])
        assert manager.get_parameter_value(prompts.WIDGET_PARAMETER_NAME) == raw_before
        assert dict(manager.parameter_output_values) == outputs_before
        print("PASS untouched real saved Prompt5 -> one manager; all five dormant documents recompile after global rebase consumption without UI/output mutation")

        # A new publisher object, even with the same valid UUID and snapshot,
        # cannot inherit this epoch's already pinned physical source identity.
        old_sources = dict(manager._hmb_connected_source_nodes)
        created = helpers.send(engine, CreateNodeRequest(node_type="HMBVideoPickerLibrary",
            specific_library_name="HMB_GP_Production", node_name="Foreign Epoch Picker", initial_setup=True))
        foreign = engine.node_manager.get_node_by_name(created.node_name)
        foreign._hmb_shot_routing_snapshot = lambda **kwargs: deepcopy(picker_snapshot)
        foreign._hmb_shot_routing_snapshot_for = lambda **kwargs: deepcopy(picker_snapshot)
        foreign._hmb_shot_channel_subscription = picker_node._hmb_shot_channel_subscription
        row = catalog["shots"][1]
        def must_reject():
            try:
                manager._hmb_prompt_shot_document(channel_uuid=catalog["channel_uuid"], shot_uuid=row["shot_uuid"])
            except prompts._ShotRoutingContractError:
                return
            raise AssertionError("A foreign/replaced or inconsistent publisher was accepted")
        manager._hmb_connected_source_nodes[prompts.SHOT_PICKER_INPUT_PARAMETER_NAME] = foreign
        must_reject()
        manager._hmb_connected_source_nodes = old_sources
        edge = dict(source_node_name=picker_node.name, source_parameter_name="SHOT_PICKER_OUT",
            target_node_name=manager.name, target_parameter_name="SHOT_PICKER_IN")
        helpers.send(engine, DeleteConnectionRequest(**edge))
        replacement = {**edge, "source_node_name": foreign.name}
        helpers.send(engine, CreateConnectionRequest(**replacement, initial_setup=True))
        manager._reconcile_connected_source_inputs_from_graph()
        must_reject()
        helpers.send(engine, DeleteConnectionRequest(**replacement))
        helpers.send(engine, CreateConnectionRequest(**edge, initial_setup=True))
        manager._reconcile_connected_source_inputs_from_graph()
        saved_snapshot = deepcopy(picker_snapshot)
        picker_snapshot["shots"][1]["revision"] += 1
        picker_snapshot["metadata_sha256"] = prompts._canonical_sha256({key: picker_snapshot[key]
            for key in ("channel_uuid", "generation", "shots", "ordered_videos")})
        must_reject()
        picker_snapshot.clear();picker_snapshot.update(saved_snapshot)
        manager._hmb_prompt_shot_document(channel_uuid=catalog["channel_uuid"], shot_uuid=row["shot_uuid"])
        print("PASS unconnected foreign object, actual physical replacement and same-generation changed metadata remain rejected after hydration")

        # Schedule sequential unchanged refreshes rather than one same-turn
        # burst: the first failure must log/compile once, then remain quiet.
        calls, errors = [], []
        def failing_sync(**kwargs):
            calls.append(True)
            raise prompts._ShotRoutingContractError("Offline repeated invalid source")
        native_now = prompts.HMBPromptLibrary._sync_prompt_output_now
        with mock.patch.object(manager, "_sync_prompt_output_from_state", failing_sync), \
                mock.patch.object(prompts, "_diagnostic_exception", lambda context, exc: errors.append(context)):
            manager._hmb_prompt_sync_failure = None
            for _ in range(30):
                native_schedule(manager, source_burst=True)
                await asyncio.sleep(prompts.PROMPT_SOURCE_BURST_DELAY_SECONDS + 0.005)
            assert len(calls) == len(errors) == 1, (len(calls), len(errors))
            state = manager._hmb_prompt_merge_snapshot()["state"]
            state[prompts.SOURCE_SYNC_REVISION_KEY] += 1
            manager._hmb_write_merged_prompt_state(prompts._json_dumps(state))
            native_schedule(manager, source_burst=True)
            await asyncio.sleep(prompts.PROMPT_SOURCE_BURST_DELAY_SECONDS + 0.005)
            assert len(calls) == len(errors) == 2
            # Presentation edits must not spin an unchanged failed source;
            # a real authored text change is an intentional new attempt.
            state["ui"]["shot_editor_expanded"] = not state["ui"].get("shot_editor_expanded", True)
            state[prompts.UI_EDIT_REVISION_KEY] += 1
            manager._hmb_write_merged_prompt_state(prompts._json_dumps(state))
            native_schedule(manager)
            await asyncio.sleep(prompts.PROMPT_SOURCE_BURST_DELAY_SECONDS + 0.005)
            assert len(calls) == 2
            state["text"][next(iter(prompts.TEXT_FIELD_DEFAULTS))] = "Authored retry text {keep exact}"
            state[prompts.UI_EDIT_REVISION_KEY] += 1
            manager._hmb_write_merged_prompt_state(prompts._json_dumps(state))
            native_schedule(manager)
            await asyncio.sleep(prompts.PROMPT_SOURCE_BURST_DELAY_SECONDS + 0.005)
            assert len(calls) == len(errors) == 3
            try:
                native_now(manager)
            except prompts._ShotRoutingContractError:
                pass
            else:
                raise AssertionError("Explicit refresh hid the persistent source error")
            assert len(calls) == 4
            native_schedule(manager, source_burst=True)
            await asyncio.sleep(prompts.PROMPT_SOURCE_BURST_DELAY_SECONDS + 0.005)
            assert len(calls) == 4
        print("PASS thirty unchanged source failures compile/log once; source revision, authored text and explicit Run retry while presentation edits stay quiet")
    finally:
        LibraryRegistry.unregister_library("HMB_GP_Production", event_manager=engine.event_manager)


def main():
    with tempfile.TemporaryDirectory(prefix="hmb-prompt-rebase-") as directory, ExitStack() as stack:
        root = Path(directory)
        for name in ("APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "GTN_CONFIG_WORKSPACE_DIRECTORY", "HMB_IMAGE_PROJECTS_ROOT"):
            target = root / name
            target.mkdir()
            stack.enter_context(mock.patch.dict(os.environ, {name: str(target)}))
        stack.enter_context(mock.patch.object(socket, "create_connection", deny_external))
        try:
            from griptape_nodes.retained_mode.engine import engine_scope
        except ImportError:
            print("HMB_PROMPT_HYDRATION_REBASE_HOST=SKIP (installed SDK required)")
            return
        import HMBPromptLibrary as prompts
        import HMBImageAssetLibrary as images
        import HMBSeedanceGeneration as generators
        import HMBAgentLibrary as agents
        import _hmb_library_bootstrap as bootstrap
        import _hmb_shot_routing as routing
        native_hydration = routing.schedule_post_hydration_reconcile
        native_schedule = prompts.HMBPromptLibrary._schedule_prompt_sync
        stack.enter_context(mock.patch.object(bootstrap._Registration, "start_web_worker", lambda *a, **k: None))
        for name in ("schedule_post_registration_reconcile", "schedule_post_hydration_reconcile"):
            stack.enter_context(mock.patch.object(routing, name, lambda *a, **k: False))
        stack.enter_context(mock.patch.object(prompts.HMBPromptLibrary, "_schedule_prompt_sync", lambda *a, **k: None))
        stack.enter_context(mock.patch.object(images.HMBImageAssetLibrary, "_schedule_catalog_scan", lambda *a, **k: None))
        stack.enter_context(mock.patch.object(agents.HMBAgentLibrary, "process", deny_external))
        stack.enter_context(mock.patch.object(generators.HMBSeedanceGeneration, "_process_generation", deny_external))
        logging.disable(logging.CRITICAL)
        helpers = load_helpers()
        with engine_scope() as engine:
            asyncio.run(exercise(engine, root, helpers, native_hydration, native_schedule))
        assert ATTEMPTS == []
    print("HMB_PROMPT_HYDRATION_REBASE_HOST=PASS (actual saved workflow and SDK; external/model/render/user graph changes zero)")


if __name__ == "__main__":
    main()
