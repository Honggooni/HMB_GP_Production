"""Actual SDK no-Run workspace transport, share worker and cold restore.

All media and workflow data are synthetic under the host fixture's tempdir.
"""
from __future__ import annotations

from copy import deepcopy
from io import BytesIO
import asyncio
import json
import os
import platform
from pathlib import Path
import socket
import subprocess
import sys
import threading
from unittest import mock
from uuid import uuid4


async def exercise_live_sync(engine, node, target, source, schema, original_shots):
    from PIL import Image
    from griptape_nodes.retained_mode.events.flow_events import (
        SerializeFlowToCommandsRequest, DeserializeFlowFromCommandsRequest, DeleteFlowRequest)
    from griptape_nodes.retained_mode.events.workflow_events import SaveWorkflowFileFromSerializedFlowRequest
    from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest, AddParameterToNodeRequest
    from griptape_nodes.retained_mode.events.connection_events import ListConnectionsForNodeRequest, CreateConnectionRequest
    import HMBImageBash as bash

    flow = engine.node_manager.get_node_parent_flow_by_name(node.name)
    workspace = deepcopy(node._current_state()["image_bash_workspace"])
    scene = deepcopy(target.get_parameter_value("bash_image"))
    with mock.patch.object(source.HMBImageAssetLibrary, "process", side_effect=AssertionError("Run forbidden")), \
         mock.patch.object(bash.HMBImageBash, "process", side_effect=AssertionError("Run forbidden")):
        commands = engine.handle_request(SerializeFlowToCommandsRequest(flow_name=flow, include_create_flow_command=True))
        assert commands.succeeded(), commands.result_details
        path = Path.cwd() / "live-sync-save.py"
        saved = await engine.ahandle_request(SaveWorkflowFileFromSerializedFlowRequest(
            serialized_flow_commands=commands.serialized_flow_commands, file_name=path.stem,
            file_path=str(path), display_name="Synthetic Live Sync", broadcast_result=False))
        assert saved.succeeded(), saved.result_details
        deleted = engine.handle_request(DeleteFlowRequest(flow_name=flow))
        assert deleted.succeeded(), deleted.result_details
        reopened = await engine.ahandle_request(DeserializeFlowFromCommandsRequest(
            serialized_flow_commands=deepcopy(commands.serialized_flow_commands), broadcast_result=False))
        assert reopened.succeeded(), reopened.result_details
        nodes = engine.flow_manager.get_flow_by_name(reopened.flow_name).nodes
        node, target = nodes[node.name], nodes[target.name]
        assert node._current_state()["image_bash_workspace"] == workspace
        assert target.get_parameter_value("bash_image") == scene
        assert len(engine.handle_request(ListConnectionsForNodeRequest(node_name=target.name)).incoming_connections) == 2
        assert [r["source_uid"] for r in target._records()] == [r["instance_id"] for r in workspace["instances"]]
        for before, after in zip(original_shots["shots"], node._current_state()["shot_routing"]["shots"]):
            for key in ("shot_uuid", "number", "name", "selected_source_uids"):
                assert before[key] == after[key]

        # Synthetic project share: the Bash-only asset is not selected in any
        # Shot. Detect blocking filesystem resolution on the host event loop.
        root = Path.cwd() / "projects" / "show" / "Ai_Ct_image"
        (root / "CH").mkdir(parents=True)
        (root / ".json").mkdir()
        Image.new("RGB", (3, 2), "green").save(root / "CH" / "Hero.png")
        (root / ".json" / "hmb_image_assets.json").write_text(json.dumps({"schema": "hmb-image-assets", "version": 1,
            "project_cache_uid": "hmbpc1:" + "1" * 32,
            "assets": [{"path": "CH/Hero.png", "asset_id": "hero", "image_name": "Hero",
                        "image_main_type": "Character", "image_sub_type": "Full Appearance"}]}), encoding="utf-8")
        project = source._load_project_catalog(root.parent.parent, source._default_state(), use_shared_cache=False)
        project = source._select_catalog_project(project, root)
        assert len(project["assets"]) == 1
        asset = project["assets"][0]
        asset["selected"] = False
        project["shot_routing"] = deepcopy(node._current_state()["shot_routing"])
        for shot in project["shot_routing"]["shots"]:
            shot["selected_source_uids"] = []
        project["image_bash_workspace"] = deepcopy(workspace)
        project["image_bash_workspace"]["instances"] = []
        project["image_bash_active"] = True
        project[source.UI_EDIT_REVISION_KEY] = 100
        project = source._normalize_state(project)
        node.set_parameter_value(source.PROJECT_ROOT_PARAMETER, project["catalog_root"], initial_setup=True)
        node.set_parameter_value(source.WIDGET_STATE_PARAMETER, source._json_text(project), initial_setup=True)
        await asyncio.sleep(.1)
        current = node._current_state()
        node._hmb_resolution_cache.clear()
        selected = deepcopy(current["image_bash_workspace"])
        item = {"instance_id": str(uuid4()), "source_uid": asset["source_uid"]}
        selected["instances"] = [item]
        selected["revision"] += 1
        edit = dict(schema=source.IMAGE_ASSET_EDIT_SCHEMA, version=1,
            ui_edit_revision=current[source.UI_EDIT_REVISION_KEY] + 1,
            catalog_identity={key: current.get(key) for key in ("catalog_root", "project_root", "project_uid",
                "project_cache_uid", "manifest_signature", "folder_signature", "scan_revision")},
            selected_source_uids=[], edits=dict(shot_routing=deepcopy(current["shot_routing"]),
                image_bash_workspace=selected, image_bash_active=True))
        host_thread = threading.get_ident()
        assert node._sync_output.__func__.__globals__ is source.__dict__
        original_resolve = source._resolve_selected_assets
        resolved_threads = []
        entered, release = threading.Event(), threading.Event()
        def checked_resolution(state, *args, **kwargs):
            cache = kwargs.get("resolution_cache") or {}
            revision = kwargs.get("import_revision", 0)
            if any(row.get("selected") and row.get("source_kind") == "project"
                   and source._asset_resolution_cache_key(row, state, revision) not in cache
                   for row in state.get("assets", [])):
                resolved_threads.append(threading.get_ident())
                assert threading.get_ident() != host_thread, "Project resolution blocked the UI callback"
                entered.set()
                assert release.wait(3), "Synthetic share worker was not released"
            return original_resolve(state, *args, **kwargs)
        errors = []
        with mock.patch.object(source, "_diagnostic_exception", side_effect=lambda *a: errors.append(a)), \
             mock.patch.object(source, "_resolve_selected_assets", side_effect=checked_resolution), \
             mock.patch.object(node, "_sync_output", wraps=node._sync_output) as output_calls, \
             mock.patch.object(node, "_schedule_catalog_scan", wraps=node._schedule_catalog_scan) as scan_calls:
            result = engine.handle_request(SetParameterValueRequest(node_name=node.name,
                parameter_name=source.WIDGET_STATE_PARAMETER, value=source._json_text(edit)))
            assert result.succeeded(), result.result_details
            assert entered.wait(1), "Project verification was not queued"
            pending = target.get_parameter_value("image_bash_context")
            assert pending.get("revision") == selected["revision"] and pending.get("ready") is False
            assert target.get_parameter_value("bash_image") == scene
            release.set()
            for _ in range(100):
                context = target.get_parameter_value("image_bash_context")
                if context.get("revision") == selected["revision"] and context.get("ready") is True:
                    break
                await asyncio.sleep(.05)
            assert resolved_threads and all(t != host_thread for t in resolved_threads), (errors, output_calls.call_count, scan_calls.call_count, node._hmb_selection_resolution_work)
            assert not errors, errors
        assert target._records()[0]["source_uid"] == item["instance_id"]
        assert target.get_parameter_value("bash_image")["meta"]["input_images"][0]["source_uid"] == item["instance_id"]
        assert len(node._current_state()["shot_routing"]["shots"]) == 5
        workspace = deepcopy(node._current_state()["image_bash_workspace"])
        # Apply into an ImageAsset import must not erase the same workspace's
        # selected instance identities or recursively invalidate its receipt.
        slot = engine.handle_request(AddParameterToNodeRequest(node_name=node.name,
            parent_container_name=source.IMAGE_IMPORT_PARAMETER))
        assert slot.succeeded(), slot.result_details
        input_child = list(node.get_parameter_by_name(source.IMAGE_IMPORT_PARAMETER).get_child_parameters())[-1].name
        loop_edge = engine.handle_request(CreateConnectionRequest(source_node_name=target.name,
            source_parameter_name="output_image", target_node_name=node.name, target_parameter_name=input_child))
        assert loop_edge.succeeded(), loop_edge.result_details
        assert target.get_parameter_value("image_bash_context").get("ready") is True, (
            node._current_state()["image_bash_workspace"], node._current_state()["assets"],
            target.get_parameter_value("image_bash_context"))
        for name, value in (("width", 4), ("height", 2), ("output_file", str(Path.cwd() / "feedback-apply.png"))):
            result = engine.handle_request(SetParameterValueRequest(node_name=target.name, parameter_name=name,
                value=value, broadcast_result=False))
            assert result.succeeded(), result.result_details
        from base64 import b64encode
        png = BytesIO()
        Image.new("RGBA", (4, 2), (10, 20, 30, 255)).save(png, "PNG")
        apply_scene = deepcopy(target.get_parameter_value("bash_image"))
        apply_scene["value"] = "data:image/png;base64," + b64encode(png.getvalue()).decode("ascii")
        result = engine.handle_request(SetParameterValueRequest(node_name=target.name,
            parameter_name="bash_image", value=apply_scene, broadcast_result=False))
        assert result.succeeded(), result.result_details
        for _ in range(100):
            if target.parameter_output_values.get("output_image") is not None:
                break
            await asyncio.sleep(.05)
        assert target.parameter_output_values.get("output_image") is not None, (target.get_parameter_value("HMB_BASH_STATUS"), target.get_parameter_value("image_bash_context"), node._current_state()["image_bash_workspace"], node._current_state()["assets"], node._hmb_selection_resolution_work)
        assert Path.cwd().joinpath("feedback-apply.png").read_bytes() == png.getvalue()
        assert node._current_state()["image_bash_workspace"] == workspace
        assert len(node._current_state()["shot_routing"]["shots"]) == 5
        assert target.get_parameter_value("HMB_BASH_VERIFICATION").get("apply_pixel_equal") is True
        feedback_rows = [a for a in node._current_state()["assets"] if a.get("source_kind") == "user"]
        assert len(feedback_rows) == 1 and feedback_rows[0]["selected"] is False, feedback_rows
        receipt = deepcopy(target.get_parameter_value("HMB_BASH_VERIFICATION"))
        await asyncio.sleep(.25)
        assert target.get_parameter_value("HMB_BASH_VERIFICATION") == receipt
        assert target.parameter_output_values.get("output_image") is not None
        assert len([a for a in node._current_state()["assets"] if a.get("source_kind") == "user"]) == 1

    print("HMB_IMAGE_BASH_LIVE_SYNC_HOST=PASS (add/remove/reorder, actual SDK, no Run, save/reopen, project worker)")


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    import HMB_Image_Bash_ImageAsset_Host_Regression as host
    import _hmb_cgt
    from griptape_nodes.retained_mode.managers.os_manager import OSManager
    os.environ["HMB_BASH_LIVE_SYNC_ONLY"] = "1"
    platform.uname()  # SDK dependencies cache the OS version during import.
    original_connect = socket.socket.connect
    def local_connect(sock, address):
        if isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1", "localhost"}:
            return original_connect(sock, address)
        raise AssertionError("External network forbidden")
    with mock.patch.object(socket.socket, "connect", local_connect), \
         mock.patch.object(_hmb_cgt, "start_own_wait_after_commit", side_effect=AssertionError("CGT write forbidden")), \
         mock.patch.object(OSManager, "_is_cuda_available", return_value=False), \
         mock.patch.object(subprocess, "Popen", side_effect=AssertionError("Subprocess forbidden")):
        host.main()
