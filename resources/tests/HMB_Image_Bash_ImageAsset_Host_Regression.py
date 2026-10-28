"""ImageAsset's independent Image Bash workspace, using the installed SDK.

Synthetic PNG data URLs only. No user workflow, application, install, provider,
Broker or external network. The actual Image Bash adapter remains unmodified.
"""
from __future__ import annotations

from collections import OrderedDict
from contextlib import ExitStack
from copy import deepcopy
import asyncio
import ast
import base64
import importlib.util
from io import BytesIO
import json
import logging
import os
from pathlib import Path
import socket
import sys
import tempfile
from unittest import mock
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main():
    if importlib.util.find_spec("griptape_nodes") is None:
        print("HMB_IMAGE_BASH_IMAGEASSET_HOST=SKIP (installed SDK required)")
        return
    previous = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="hmb-image-bash-workspace-", ignore_cleanup_errors=True) as temporary:
        directory = Path(temporary)
        environment = {key: str(directory / key) for key in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME",
            "XDG_CACHE_HOME", "LOCALAPPDATA", "APPDATA", "GTN_CONFIG_WORKSPACE_DIRECTORY")}
        environment.update(HMB_IMAGE_BASH_STANDARD_LIBRARY_PATH=str(Path.home() / "Documents/GriptapeNodes/libraries/griptape-nodes-library-standard"),
            HMB_IMAGE_BASH_EDITOR_BUNDLE_PATH=str(Path.home() / "AppData/Local/ai.griptape.nodes.desktop/current/resources/editor-bundle"))
        with mock.patch.dict(os.environ, environment), mock.patch.object(socket, "create_connection", side_effect=AssertionError("Network forbidden")):
            os.chdir(directory)
            logging.disable(logging.CRITICAL)
            try:
                from griptape_nodes.retained_mode.engine import engine_scope
                with engine_scope() as engine:
                    asyncio.run(exercise(engine))
            finally:
                os.chdir(previous)
                logging.shutdown()


async def exercise(engine):
    from PIL import Image
    from griptape_nodes.node_library.library_registry import LibraryRegistry, LibrarySchema
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    from griptape_nodes.retained_mode.events.flow_events import (CreateFlowRequest,
        SerializeFlowToCommandsRequest, DeserializeFlowFromCommandsRequest, DeleteFlowRequest)
    from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest, DeleteNodeRequest, SerializeNodeToCommandsRequest, DeserializeNodeFromCommandsRequest, SetNodeMetadataRequest
    from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest, CreateConnectionResultFailure, ListConnectionsForNodeRequest
    from griptape_nodes.retained_mode.events.parameter_events import AddParameterToNodeRequest, SetParameterValueRequest, SetParameterValueResultFailure
    from griptape_nodes.retained_mode.events.execution_events import ResolveNodeRequest
    from griptape_nodes.retained_mode.events.workflow_events import SaveWorkflowFileFromSerializedFlowRequest
    from griptape_nodes.exe_types.node_types import NodeResolutionState
    from griptape_nodes.files.file import File
    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
    import HMBImageAssetLibrary as source
    import _hmb_shot_routing as routing
    from HMBImageBash import HMBImageBash

    def data_url(color):
        buffer = BytesIO()
        Image.new("RGB", (3, 2), color).save(buffer, "PNG")
        return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()

    urls = [data_url("red"), data_url("blue")]
    state = source._default_state()
    assert state["image_bash_workspace"] == {} and not state["image_bash_active"]
    state["assets"] = [dict(asset_library_id="import:" + name, source_uid="import:" + name,
        source_kind="user", asset_id=name, image_name=name, path=url, selected=index == 0,
        selection_order=1 if index == 0 else 0, import_index=index + 1, connected=True,
        registered=False, media_ref_kind="url", media_signature="synthetic-" + name)
        for index, (name, url) in enumerate(zip(("a", "b"), urls))]
    first = state["shot_routing"]["shots"][0]
    state["shot_routing"]["shots"] = [dict(first, shot_uuid=str(uuid4()), number=number,
        name="Authored " + str(number), name_is_custom=True, selected_source_uids=["import:a"])
        for number in range(1, 6)]
    state["shot_routing"]["active_shot_uuid"] = state["shot_routing"]["shots"][2]["shot_uuid"]
    state = source._normalize_state(state)
    shots_before = deepcopy(state["shot_routing"])
    instances = [dict(instance_id=str(uuid4()), source_uid=uid) for uid in ("import:b", "import:a", "import:b")]
    state.update(image_bash_workspace=dict(workspace_id=str(uuid4()), revision=0, instances=instances), image_bash_active=True)
    state = source._normalize_state(state)
    images, context = source._build_image_bash_outputs(state)
    assert [item.value for item in images] == [urls[1], urls[0], urls[1]]
    assert [row["url"] for row in context["records"]] == [item.value for item in images]
    assert [row["source_uid"] for row in context["records"]] == [row["instance_id"] for row in instances]
    assert len({row["source_uid"] for row in context["records"]}) == 3
    assert state["shot_routing"] == shots_before
    restored = source._normalize_state(json.dumps(state))
    assert restored["image_bash_workspace"] == state["image_bash_workspace"]
    assert restored["shot_routing"] == shots_before
    reordered = deepcopy(state)
    reordered["image_bash_workspace"]["instances"].reverse()
    reordered["image_bash_workspace"]["revision"] += 1
    _, reordered_context = source._build_image_bash_outputs(reordered)
    assert [row["source_uid"] for row in reordered_context["records"]] == [row["instance_id"] for row in reversed(instances)]
    assert reordered["shot_routing"] == shots_before
    reset = source._reset_image_asset_state_preserving_shot_media(restored)
    assert reset["image_bash_workspace"] == restored["image_bash_workspace"]

    schema = LibrarySchema.model_validate_json((ROOT / "griptape-nodes-library.json").read_text("utf-8"))
    library = LibraryRegistry.generate_new_library(schema)
    for name, cls in (("HMBImageAssetLibrary", source.HMBImageAssetLibrary), ("HMBImageBash", HMBImageBash)):
        definition = next((row for row in schema.nodes if row.class_name == name), None)
        metadata = definition.metadata if definition else next(row.metadata for row in schema.nodes if row.class_name == "HMBImageAssetLibrary")
        library.register_lazy_node_type(name, metadata, lambda cls=cls: cls)
    engine.event_manager.initialize_queue()
    ensured = engine.handle_request(EnsureWorkflowAndFlowRequest(flow_name="SyntheticImageBashWorkspace"))
    assert ensured.succeeded(), ensured.result_details
    with ExitStack() as patches:
        for name in ("schedule_post_registration_reconcile", "schedule_post_hydration_reconcile", "reconcile_shot_routing"):
            patches.enter_context(mock.patch.object(routing, name))
        created = engine.handle_request(CreateNodeRequest(node_type="HMBImageAssetLibrary", specific_library_name=schema.name,
            node_name="SyntheticImageAsset", override_parent_flow_name=ensured.flow_name, create_error_proxy_on_failure=False))
        assert created.succeeded(), created.result_details
        node = engine.node_manager.get_node_by_name(created.node_name)
        image_output = node.get_parameter_by_name(source.IMAGE_BASH_IMAGES_OUTPUT_PARAMETER)
        context_output = node.get_parameter_by_name(source.IMAGE_BASH_CONTEXT_OUTPUT_PARAMETER)
        assert image_output.type == image_output.output_type == "list[ImageUrlArtifact]"
        assert "display_name" not in image_output.ui_options
        assert image_output.ui_options["hide"] is True and image_output.ui_options["hide_handles"] is True
        assert image_output.ui_options["hide_property"] is True
        assert context_output.ui_options["hide"] is True and context_output.ui_options["hide_handles"] is True
        node._hmb_import_media_by_uid = {}
        node._hmb_resolution_cache = OrderedDict()
        legacy = deepcopy(state)
        legacy.update(image_bash_workspace={}, image_bash_active=False)
        node.set_parameter_value(source.WIDGET_STATE_PARAMETER, source._json_text(legacy), initial_setup=True)
        # Every compact UI edit includes the absent workspace too. That
        # default must not prevent editing an existing five-Shot workflow.
        legacy_edit = dict(schema=source.IMAGE_ASSET_EDIT_SCHEMA, version=1, ui_edit_revision=1,
            catalog_identity={key: legacy.get(key) for key in ("catalog_root", "project_root", "project_uid",
                "project_cache_uid", "manifest_signature", "folder_signature", "scan_revision")},
            selected_source_uids=[row["source_uid"] for row in legacy["assets"] if row["selected"]],
            edits=dict(shot_routing=deepcopy(legacy["shot_routing"]), image_bash_workspace={}, image_bash_active=False))
        edited = engine.handle_request(SetParameterValueRequest(node_name=node.name,
            parameter_name=source.WIDGET_STATE_PARAMETER, value=source._json_text(legacy_edit)))
        assert edited.succeeded(), edited.result_details
        assert node._current_state()["image_bash_workspace"] == {}
        assert [row["shot_uuid"] for row in node._current_state()["shot_routing"]["shots"]] == [
            row["shot_uuid"] for row in shots_before["shots"]]
        # Restore through the native initial-setup setter; no command may be
        # executed by saving/reopening or selecting the dedicated workspace.
        state[source.UI_EDIT_REVISION_KEY] = 2
        node.set_parameter_value(source.WIDGET_STATE_PARAMETER, source._json_text(state), initial_setup=True)
        compact = deepcopy(legacy_edit)
        compact.update(ui_edit_revision=3,
            edits=dict(shot_routing=deepcopy(state["shot_routing"]),
                image_bash_workspace=deepcopy(state["image_bash_workspace"]), image_bash_active=False))
        assert node._expand_widget_edit(compact)["image_bash_workspace"] == state["image_bash_workspace"]
        for fault in ("clear", "workspace_id", "stale_revision", "remap_instance", "unknown_source"):
            bad = deepcopy(compact)
            workspace = bad["edits"]["image_bash_workspace"]
            if fault == "clear":
                bad["edits"]["image_bash_workspace"] = {}
            elif fault == "workspace_id":
                workspace["workspace_id"] = str(uuid4())
            elif fault == "stale_revision":
                workspace["instances"].reverse()
            elif fault == "remap_instance":
                workspace["instances"][0]["source_uid"] = "import:a"
                workspace["revision"] += 1
            else:
                workspace["instances"].append(dict(instance_id=str(uuid4()), source_uid="not-in-catalog"))
                workspace["revision"] += 1
            try:
                node._expand_widget_edit(bad)
            except ValueError:
                pass
            else:
                raise AssertionError("Workspace authority guard accepted " + fault)
        before_count = len(engine.flow_manager.get_flow_by_name(ensured.flow_name).nodes)
        node._sync_image_bash_output(state)
        assert len(engine.flow_manager.get_flow_by_name(ensured.flow_name).nodes) == before_count
        command = dict(schema=source.IMAGE_BASH_WORKSPACE_REQUEST_SCHEMA, version=1, operation="create",
            request_id=str(uuid4()), workspace_id=state["image_bash_workspace"]["workspace_id"], expected_revision=0)
        dispatch = GriptapeNodes.handle_request
        def partial_connection_failure(request):
            if isinstance(request, CreateConnectionRequest) and request.target_parameter_name == "image_bash_context":
                return CreateConnectionResultFailure(result_details="Synthetic second-wire failure")
            return dispatch(request)
        with mock.patch.object(GriptapeNodes, "handle_request", side_effect=partial_connection_failure):
            try:
                node._create_image_bash_workspace_node(command)
            except ValueError:
                pass
            else:
                raise AssertionError("A partial two-port connection was accepted")
        assert node._current_state()["shot_routing"] == shots_before
        assert len(engine.flow_manager.get_flow_by_name(ensured.flow_name).nodes) == before_count + 1
        partial_target = next(item for item in engine.flow_manager.get_flow_by_name(ensured.flow_name).nodes.values()
                              if isinstance(item, HMBImageBash))
        assert not engine.handle_request(ListConnectionsForNodeRequest(node_name=partial_target.name)).incoming_connections
        first_wire = engine.handle_request(CreateConnectionRequest(source_node_name=node.name,
            source_parameter_name=source.IMAGE_BASH_IMAGES_OUTPUT_PARAMETER,
            target_node_name=partial_target.name, target_parameter_name="input_images"))
        assert first_wire.succeeded(), first_wire.result_details
        with mock.patch.object(GriptapeNodes, "handle_request", side_effect=partial_connection_failure):
            try:
                node._create_image_bash_workspace_node(command)
            except ValueError:
                pass
            else:
                raise AssertionError("Existing one-edge recovery accepted a missing context edge")
        retained_edges = engine.handle_request(ListConnectionsForNodeRequest(node_name=partial_target.name))
        assert len(retained_edges.incoming_connections) == 1
        assert retained_edges.incoming_connections[0].source_parameter_name == source.IMAGE_BASH_IMAGES_OUTPUT_PARAMETER
        name = node._create_image_bash_workspace_node(command)
        target = engine.node_manager.get_node_by_name(name)
        assert isinstance(target, HMBImageBash)
        assert target.metadata.get("size") == {"width": 800, "height": 680}, target.metadata
        assert target.name == "HMBImageBash", target.name
        connections = engine.handle_request(ListConnectionsForNodeRequest(node_name=name))
        assert connections.succeeded() and len(connections.incoming_connections) == 2, connections
        assert {edge.source_parameter_name for edge in connections.incoming_connections} == {
            source.IMAGE_BASH_IMAGES_OUTPUT_PARAMETER, source.IMAGE_BASH_CONTEXT_OUTPUT_PARAMETER}
        assert [row["source_uid"] for row in target._records()] == [row["instance_id"] for row in instances]
        assert node._create_image_bash_workspace_node(command) == name
        assert len(engine.flow_manager.get_flow_by_name(ensured.flow_name).nodes) == before_count + 1
        assert node._current_state()["shot_routing"] == shots_before
        # Palette-first or explicitly unbound Bash nodes no longer carry a
        # workspace lease. The explicit Asset create command must reuse that
        # exact retained editor and preserve its authored scene, not add one.
        scene_before_reuse = deepcopy(target.get_parameter_value("bash_image"))
        workspace_before_reuse = deepcopy(node._current_state()["image_bash_workspace"])
        node._hmb_bind_image_bash_workspace(target, command["workspace_id"], False)
        assert "hmb_image_bash_workspace_id" not in target.metadata
        assert not engine.handle_request(ListConnectionsForNodeRequest(node_name=name)).incoming_connections
        assert target.get_parameter_value("bash_image") == scene_before_reuse
        assert node._create_image_bash_workspace_node(command) == name
        assert engine.node_manager.get_node_by_name(name) is target
        assert len(engine.flow_manager.get_flow_by_name(ensured.flow_name).nodes) == before_count + 1
        assert target.get_parameter_value("bash_image") == scene_before_reuse
        assert node._current_state()["image_bash_workspace"] == workspace_before_reuse
        assert node._current_state()["shot_routing"] == shots_before
        # The real property command path consumes an explicit create intent;
        # duplicate UI commands reuse the same node and do not persist intent.
        submitted = deepcopy(state)
        submitted.update(image_bash_workspace_request=deepcopy(command), ui_edit_revision=3)
        accepted = engine.handle_request(SetParameterValueRequest(node_name=node.name,
            parameter_name=source.WIDGET_STATE_PARAMETER, value=source._json_text(submitted)))
        assert accepted.succeeded(), accepted.result_details
        assert len(engine.flow_manager.get_flow_by_name(ensured.flow_name).nodes) == before_count + 1
        assert node._current_state()["image_bash_workspace_request"] == {}
        # Exercise the actual UI edit transport. A workspace edit must publish
        # the native port pair and update the connected Bash without Run.
        initial_instances = deepcopy(node._current_state()["image_bash_workspace"]["instances"])
        added = dict(instance_id=str(uuid4()), source_uid="import:a")
        sequences = [initial_instances + [added], [added] + initial_instances,
                     [added] + initial_instances[1:], initial_instances]
        with mock.patch.object(node, "process", side_effect=AssertionError("ImageAsset Run forbidden")), \
             mock.patch.object(target, "process", side_effect=AssertionError("Image Bash Run forbidden")):
            for requested_instances in sequences:
                current = node._current_state()
                workspace = deepcopy(current["image_bash_workspace"])
                workspace["instances"] = deepcopy(requested_instances)
                workspace["revision"] += 1
                edit = dict(schema=source.IMAGE_ASSET_EDIT_SCHEMA, version=1,
                    ui_edit_revision=current[source.UI_EDIT_REVISION_KEY] + 1,
                    catalog_identity={key: current.get(key) for key in ("catalog_root", "project_root", "project_uid",
                        "project_cache_uid", "manifest_signature", "folder_signature", "scan_revision")},
                    selected_source_uids=[row["source_uid"] for row in current["assets"] if row["selected"]],
                    edits=dict(shot_routing=deepcopy(current["shot_routing"]), image_bash_workspace=workspace,
                               image_bash_active=True))
                changed = engine.handle_request(SetParameterValueRequest(node_name=node.name,
                    parameter_name=source.WIDGET_STATE_PARAMETER, value=source._json_text(edit)))
                assert changed.succeeded(), changed.result_details
                assert [row["source_uid"] for row in target._records()] == [row["instance_id"] for row in requested_instances]
                assert target.get_parameter_value("image_bash_context")["revision"] == workspace["revision"]
                scene = target.get_parameter_value("bash_image")
                scene_uids = {row.get("source_uid") for row in scene.get("meta", {}).get("input_images", [])}
                assert scene_uids == {row["instance_id"] for row in requested_instances}, (scene_uids, target.get_parameter_value("HMB_BASH_STATUS"))
        if os.environ.get("HMB_BASH_LIVE_SYNC_ONLY") == "1":
            from HMB_Image_Bash_Live_Sync_Host_Regression import exercise_live_sync
            await exercise_live_sync(engine, node, target, source, schema, shots_before)
            return
        # Normal publication refreshes derived media hashes/counts only.
        for old, current in zip(shots_before["shots"], node._current_state()["shot_routing"]["shots"]):
            for key in ("shot_uuid", "number", "name", "name_is_custom", "revision", "selected_source_uids"):
                assert old[key] == current[key]
        state = node._current_state()
        shots_before = deepcopy(state["shot_routing"])

        pool = {}
        serialized = engine.handle_request(SerializeNodeToCommandsRequest(node_name=node.name,
            unique_parameter_uuid_to_values=pool, serialize_all_parameter_values=True))
        assert serialized.succeeded(), serialized.result_details
        from griptape_nodes.serialization.values import decode_value
        saved = next(decode_value(deepcopy(pool[item.unique_value_uuid])) for item in serialized.set_parameter_value_commands
                     if item.set_parameter_value_command.parameter_name == source.WIDGET_STATE_PARAMETER)
        assert source._normalize_state(saved)["image_bash_workspace"] == state["image_bash_workspace"]
        assert source._normalize_state(saved)["shot_routing"] == shots_before
        cold_flow = engine.handle_request(CreateFlowRequest(parent_flow_name=None,
            flow_name="ImageBashColdReopen", set_as_new_context=False))
        assert cold_flow.succeeded(), cold_flow.result_details
        with engine.context_manager.flow(cold_flow.flow_name):
            cold = engine.handle_request(DeserializeNodeFromCommandsRequest(
                serialized_node_commands=deepcopy(serialized.serialized_node_commands)))
            assert cold.succeeded(), cold.result_details
            cold_source = engine.node_manager.get_node_by_name(cold.node_name)
            restored = engine.handle_request(SetParameterValueRequest(node_name=cold_source.name,
                parameter_name=source.WIDGET_STATE_PARAMETER, value=saved, initial_setup=True))
            assert restored.succeeded(), restored.result_details
            cold_source._sync_image_bash_output(cold_source._current_state())
            assert cold_source._current_state()["image_bash_workspace"] == state["image_bash_workspace"]
            assert cold_source._current_state()["shot_routing"] == shots_before
            assert cold_source.get_parameter_by_name(source.IMAGE_BASH_IMAGES_OUTPUT_PARAMETER).ui_options["hide_handles"] is True
            assert cold_source.get_parameter_by_name(source.IMAGE_BASH_CONTEXT_OUTPUT_PARAMETER).ui_options["hide_handles"] is True
            assert len(engine.flow_manager.get_flow_by_name(cold_flow.flow_name).nodes) == 1
        calls = []
        original_publish = node.publish_update_to_parameter
        def publish(port, value):
            calls.append(port)
            assert [item.value for item in node.parameter_output_values[source.IMAGE_BASH_IMAGES_OUTPUT_PARAMETER]] == [
                row["url"] for row in node.parameter_output_values[source.IMAGE_BASH_CONTEXT_OUTPUT_PARAMETER]["records"]]
            return original_publish(port, value)
        with mock.patch.object(node, "publish_update_to_parameter", side_effect=publish):
            node._sync_image_bash_output(reordered)
        assert calls == [source.IMAGE_BASH_IMAGES_OUTPUT_PARAMETER, source.IMAGE_BASH_CONTEXT_OUTPUT_PARAMETER]
        assert [row["source_uid"] for row in target._records()] == [row["instance_id"] for row in reversed(instances)]
        with mock.patch.object(source, "_resolve_selected_assets", side_effect=AssertionError("Page selection must use cached media")):
            node._sync_image_bash_output(dict(reordered, image_bash_active=False))
        missing = deepcopy(reordered)
        missing["assets"] = [row for row in missing["assets"] if row["source_uid"] != "import:b"]
        missing["image_bash_workspace"]["revision"] += 1
        previous_pair = node._hmb_last_image_bash_pair
        previous_scene = deepcopy(target.get_parameter_value("bash_image"))
        node._sync_image_bash_output(missing)
        assert node._hmb_last_image_bash_pair == previous_pair
        blocked_context = node.parameter_output_values[source.IMAGE_BASH_CONTEXT_OUTPUT_PARAMETER]
        assert blocked_context["ready"] is False and blocked_context["revision"] == missing["image_bash_workspace"]["revision"]
        assert [item.value for item in node.parameter_output_values[source.IMAGE_BASH_IMAGES_OUTPUT_PARAMETER]] == [item.value for item in previous_pair[0]]
        assert target.get_parameter_value("bash_image") == previous_scene
        try:
            target.process()
        except ValueError as exc:
            assert "원본" in str(exc) or "준비" in str(exc)
        else:
            raise AssertionError("A missing newly requested input reused the previous Apply as a new Run")
        node._sync_image_bash_output(reordered)
        assert node.parameter_output_values[source.IMAGE_BASH_CONTEXT_OUTPUT_PARAMETER]["ready"] is True
        assert target._records() == reordered_context["records"]
        # A notification may fail after the retained sibling caches were
        # staged. The identical next sync must retry that port, without
        # resolving media again or losing a newer reentrant publication.
        notification_state = deepcopy(reordered)
        for failure_kind in ("publisher", "graph"):
            previous_revision = target.get_parameter_value("image_bash_context")["revision"]
            notification_state["image_bash_workspace"]["revision"] += 1
            if failure_kind == "publisher":
                def fail_context_publish(port, value):
                    if port == source.IMAGE_BASH_CONTEXT_OUTPUT_PARAMETER:
                        raise RuntimeError("Synthetic context publication failure")
                    return original_publish(port, value)
                failing_patch = mock.patch.object(node, "publish_update_to_parameter", side_effect=fail_context_publish)
            else:
                original_propagate = source._propagate_image_output_to_connections
                def fail_context_propagation(owner, port, value, **kwargs):
                    if port == source.IMAGE_BASH_CONTEXT_OUTPUT_PARAMETER:
                        raise RuntimeError("Synthetic context propagation failure")
                    return original_propagate(owner, port, value, **kwargs)
                failing_patch = mock.patch.object(source, "_propagate_image_output_to_connections", side_effect=fail_context_propagation)
            with failing_patch:
                node._sync_image_bash_output(notification_state)
            assert list(node._hmb_image_bash_pending_notifications) == [source.IMAGE_BASH_CONTEXT_OUTPUT_PARAMETER]
            assert target.get_parameter_value("image_bash_context")["revision"] == previous_revision
            with mock.patch.object(source, "_resolve_selected_assets", side_effect=AssertionError("Retry must use cached media")):
                node._sync_image_bash_output(notification_state)
            assert not node._hmb_image_bash_pending_notifications
            assert target.get_parameter_value("image_bash_context")["revision"] == notification_state["image_bash_workspace"]["revision"]
        latest = deepcopy(notification_state)
        latest["image_bash_workspace"]["revision"] += 2
        latest["image_bash_workspace"]["instances"] = latest["image_bash_workspace"]["instances"][1:] + latest["image_bash_workspace"]["instances"][:1]
        obsolete = deepcopy(notification_state)
        obsolete["image_bash_workspace"]["revision"] += 1
        def publish_reentrantly(port, value):
            if port == source.IMAGE_BASH_IMAGES_OUTPUT_PARAMETER:
                with mock.patch.object(node, "publish_update_to_parameter", side_effect=original_publish):
                    node._sync_image_bash_output(latest)
            return original_publish(port, value)
        with mock.patch.object(node, "publish_update_to_parameter", side_effect=publish_reentrantly):
            node._sync_image_bash_output(obsolete)
        assert not node._hmb_image_bash_pending_notifications
        assert target._records() == source._build_image_bash_outputs(latest)[1]["records"]
        remapped = deepcopy(state)
        original_ids = [row["instance_id"] for row in remapped["image_bash_workspace"]["instances"]]
        source._remap_shot_routing_source_uid(remapped, "import:b", "project:registered-b")
        assert [row["instance_id"] for row in remapped["image_bash_workspace"]["instances"]] == original_ids
        assert [row["source_uid"] for row in remapped["image_bash_workspace"]["instances"]].count("project:registered-b") == 2
        # The editor Run button uses ResolveNodeRequest, which performs native
        # ParameterList-child validation before the scheduler calls process.
        # Keep the real upstream DataNode pre-resolved, as in a precomputed
        # ImageAsset selection; no user/share catalog is loaded by this test.
        node._sync_image_bash_output(node._current_state(), force=True)
        node.state = NodeResolutionState.RESOLVED
        for parameter, value in (("width", 4), ("height", 2),
                                 ("output_file", str(Path.cwd() / "native-two-wire-run.png"))):
            updated = engine.handle_request(SetParameterValueRequest(node_name=target.name,
                parameter_name=parameter, value=value, broadcast_result=False))
            assert updated.succeeded(), updated.result_details
        project = deepcopy(target.get_parameter_value("bash_image"))
        png_buffer = BytesIO()
        Image.new("RGBA", (4, 2), (25, 50, 100, 255)).save(png_buffer, "PNG")
        applied_png = png_buffer.getvalue()
        project["value"] = "data:image/png;base64," + base64.b64encode(applied_png).decode("ascii")
        applied = engine.handle_request(SetParameterValueRequest(node_name=target.name,
            parameter_name="bash_image", value=project, broadcast_result=False))
        assert applied.succeeded(), applied.result_details
        input_parameter = target.get_parameter_by_name("input_images")
        children = list(input_parameter.get_child_parameters())
        live_connections = engine.handle_request(ListConnectionsForNodeRequest(node_name=target.name))
        image_edges = [edge for edge in live_connections.incoming_connections
                       if edge.source_parameter_name == source.IMAGE_BASH_IMAGES_OUTPUT_PARAMETER]
        assert len(image_edges) == 1
        connected_child_name = image_edges[0].target_parameter_name
        assert connected_child_name == "input_images" or connected_child_name in {child.name for child in children}
        child_images = target.get_parameter_value(connected_child_name)
        assert isinstance(child_images, list) and len(child_images) == 3
        assert [image.value for image in child_images] == [row["url"] for row in target._records()]
        resolved = await asyncio.wait_for(engine.ahandle_request(ResolveNodeRequest(node_name=target.name)), timeout=15)
        assert resolved.succeeded(), str(getattr(resolved, "validation_exceptions", resolved.result_details))
        assert target.state == NodeResolutionState.RESOLVED
        assert File(target.parameter_output_values["output_image"].value).read_bytes() == applied_png
        assert target.get_parameter_value("HMB_BASH_VERIFICATION")["apply_pixel_equal"] is True
        # A list-typed source belongs on the ParameterList parent. A child
        # accepts one image only; native rejection must not disturb the
        # working whole-list pair, scene, Apply or existing output file.
        pair_before_bad_connection = deepcopy((node.parameter_output_values[source.IMAGE_BASH_IMAGES_OUTPUT_PARAMETER],
            node.parameter_output_values[source.IMAGE_BASH_CONTEXT_OUTPUT_PARAMETER]))
        scene_before_bad_connection = deepcopy(target.get_parameter_value("bash_image"))
        records_before_bad_connection = deepcopy(target._records())
        child_created = engine.handle_request(CreateNodeRequest(node_type="HMBImageBash", specific_library_name=schema.name,
            node_name="SyntheticLegacyChildBash", override_parent_flow_name=ensured.flow_name, create_error_proxy_on_failure=False))
        assert child_created.succeeded(), child_created.result_details
        child_target = engine.node_manager.get_node_by_name(child_created.node_name)
        child_parameter = child_target.get_parameter_by_name("input_images").add_child_parameter()
        wired = engine.handle_request(CreateConnectionRequest(source_node_name=node.name,
            source_parameter_name=source.IMAGE_BASH_IMAGES_OUTPUT_PARAMETER,
            target_node_name=child_target.name, target_parameter_name=child_parameter.name))
        details = str(wired.result_details).casefold()
        assert wired.failed() and ("type mismatch" in details or "rejected the connection" in details), (
            wired.succeeded(), wired.failed(), wired.result_details)
        assert (node.parameter_output_values[source.IMAGE_BASH_IMAGES_OUTPUT_PARAMETER],
            node.parameter_output_values[source.IMAGE_BASH_CONTEXT_OUTPUT_PARAMETER]) == pair_before_bad_connection
        assert target.get_parameter_value("bash_image") == scene_before_bad_connection
        assert target._records() == records_before_bad_connection
        assert File(target.parameter_output_values["output_image"].value).read_bytes() == applied_png
        good_edges = engine.handle_request(ListConnectionsForNodeRequest(node_name=target.name))
        assert len(good_edges.incoming_connections) == 2
        bad_edges = engine.handle_request(ListConnectionsForNodeRequest(node_name=child_target.name))
        assert not bad_edges.incoming_connections
        # Legacy workflows can still contain two authored editors. Never
        # choose one by lease metadata or delete either while adding from Asset.
        legacy_nodes = tuple(engine.flow_manager.get_flow_by_name(ensured.flow_name).nodes.values())
        legacy_workspace = deepcopy(node._current_state()["image_bash_workspace"])
        legacy_scenes = [deepcopy(item.get_parameter_value("bash_image")) for item in (target, child_target)]
        legacy_command = dict(command, workspace_id=legacy_workspace["workspace_id"],
                              expected_revision=legacy_workspace["revision"])
        try:
            node._create_image_bash_workspace_node(legacy_command)
        except ValueError:
            pass
        else:
            raise AssertionError("Multiple legacy Bash nodes were silently selected or replaced")
        assert tuple(engine.flow_manager.get_flow_by_name(ensured.flow_name).nodes.values()) == legacy_nodes
        assert [item.get_parameter_value("bash_image") for item in (target, child_target)] == legacy_scenes
        assert node._current_state()["image_bash_workspace"] == legacy_workspace
        # Exercise the actual custom-header property command path, rather
        # than invoking its Python callback or source hooks directly.
        def header_command(operation, **payload):
            request = {"hmb_image_bash_command": {"operation": operation, **payload}}
            sent = engine.handle_request(SetParameterValueRequest(node_name=target.name,
                parameter_name="HMB_IMAGE_BASH_UI", value=request, broadcast_result=False))
            assert sent.succeeded(), sent.result_details
            return target.get_parameter_value("HMB_IMAGE_BASH_UI")
        workspace_id = node._current_state()["image_bash_workspace"]["workspace_id"]
        shots_before_remote = deepcopy(node._current_state()["shot_routing"])
        with mock.patch.object(node, "_current_state", side_effect=AssertionError("Header discovery must use scalar authority")), \
             mock.patch.object(source, "_resolve_selected_assets", side_effect=AssertionError("Header discovery must not resolve media")):
            for _ in range(20):
                header = header_command("refresh")
                assert header["bound_source"] == node.name
                assert header["sources"] == [{"id": node.name, "label": node.name + " · HMBImageBash", "workspace_id": workspace_id}]
                cached_images, cached_context = node._hmb_image_bash_snapshot(workspace_id)
                assert [image.value for image in cached_images] == [row["url"] for row in cached_context["records"]]
        scene_before_unbind = deepcopy(target.get_parameter_value("bash_image"))
        pair_before_unbind = node._hmb_image_bash_snapshot(workspace_id)
        header = header_command("unbind")
        assert header["bound_source"] == ""
        assert target.get_parameter_value("input_images") == []
        assert target.get_parameter_value("image_bash_context") == {}
        assert target.get_parameter_value("bash_image") == scene_before_unbind
        assert target.parameter_output_values["output_image"] is None
        assert target.get_parameter_value("HMB_BASH_VERIFICATION") == {}
        assert node._hmb_image_bash_snapshot(workspace_id) == pair_before_unbind
        assert Path("native-two-wire-run.png").read_bytes() == applied_png
        assert not engine.handle_request(ListConnectionsForNodeRequest(node_name=target.name)).incoming_connections
        header = header_command("bind", source_node_name=node.name, workspace_id=workspace_id)
        assert header["bound_source"] == node.name
        assert target.get_parameter_value("HMB_BASH_STATUS") != "REMOTE 연결 해제 · 편집 내용은 유지됩니다"
        assert target.get_parameter_value("bash_image") == scene_before_unbind
        assert node._current_state()["shot_routing"] == shots_before_remote
        node.state = NodeResolutionState.RESOLVED
        rebound = await asyncio.wait_for(engine.ahandle_request(ResolveNodeRequest(node_name=target.name)), timeout=15)
        assert rebound.succeeded(), str(getattr(rebound, "validation_exceptions", rebound.result_details))
        assert File(target.parameter_output_values["output_image"].value).read_bytes() == applied_png
        def expect_rejected(action, description):
            try:
                action()
            except ValueError:
                return
            raise AssertionError("REMOTE authority guard accepted " + description)
        def transport_view(item):
            return deepcopy({"images": item.get_parameter_value("input_images"),
                "context": item.get_parameter_value("image_bash_context"), "scene": item.get_parameter_value("bash_image"),
                "output": item.parameter_output_values.get("output_image"),
                "proof": item.get_parameter_value("HMB_BASH_VERIFICATION"),
                "metadata": {key: item.metadata[key] for key in ("hmb_image_bash_workspace_id", "hmb_image_bash_channel_uuid")
                             if key in item.metadata}})
        before_guard = transport_view(target)
        source_pair_before_guard = node._hmb_image_bash_snapshot(workspace_id)
        for guarded in (node, target):
            previous_lock, previous_state = guarded.lock, guarded.state
            for guard in ("lock", "resolving"):
                guarded.lock = guard == "lock"
                guarded.state = NodeResolutionState.RESOLVING if guard == "resolving" else previous_state
                try:
                    for enabled in (True, False):
                        with mock.patch.object(node, "_sync_image_bash_output", side_effect=AssertionError("A preflight failure published media")):
                            expect_rejected(lambda: node._hmb_bind_image_bash_workspace(target, workspace_id, enabled), guard)
                finally:
                    guarded.lock, guarded.state = previous_lock, previous_state
        expect_rejected(lambda: node._hmb_bind_image_bash_workspace(target, str(uuid4())), "different workspace")
        expect_rejected(lambda: cold_source._hmb_bind_image_bash_workspace(target, workspace_id), "cross-flow source")
        with mock.patch.object(node, "_sync_image_bash_output", side_effect=AssertionError("Occupied workspace published media")):
            expect_rejected(lambda: node._hmb_bind_image_bash_workspace(child_target, workspace_id), "occupied workspace")
        assert transport_view(target) == before_guard
        assert node._hmb_image_bash_snapshot(workspace_id) == source_pair_before_guard

        # A second synthetic source exposes the foreign-edge and transactional
        # switch boundaries. Production singleton routing stays patched out in
        # this isolated test; existing five-Shot data is never reassigned.
        second_created = engine.handle_request(CreateNodeRequest(node_type="HMBImageAssetLibrary", specific_library_name=schema.name,
            node_name="SyntheticOtherImageAsset", override_parent_flow_name=ensured.flow_name, create_error_proxy_on_failure=False))
        assert second_created.succeeded(), second_created.result_details
        second = engine.node_manager.get_node_by_name(second_created.node_name)
        second_state = deepcopy(node._current_state())
        second_state["shot_routing"].update(channel_uuid=str(uuid4()), publisher_instance_uuid=str(uuid4()))
        second_state["image_bash_workspace"]["workspace_id"] = str(uuid4())
        for instance in second_state["image_bash_workspace"]["instances"]:
            instance["instance_id"] = str(uuid4())
        second.set_parameter_value(source.WIDGET_STATE_PARAMETER, source._json_text(second_state), initial_setup=True)
        second._sync_image_bash_output(second_state)
        second_id = second_state["image_bash_workspace"]["workspace_id"]
        second_pair = second._hmb_image_bash_snapshot(second_id)
        with mock.patch.object(second, "_sync_image_bash_output", side_effect=AssertionError("Foreign wire preflight published media")):
            for enabled in (True, False):
                expect_rejected(lambda: second._hmb_bind_image_bash_workspace(target, second_id, enabled), "foreign source pair")
        assert transport_view(target) == before_guard
        assert second._hmb_image_bash_snapshot(second_id) == second_pair
        empty_target = transport_view(child_target)
        expect_rejected(lambda: second._hmb_bind_image_bash_workspace(child_target, second_id, False), "unowned local inputs")
        assert transport_view(child_target) == empty_target
        for mutation in ("revision", "channel"):
            fired = []
            def change_workspace_mid_connection(request):
                result = dispatch(request)
                if (isinstance(request, CreateConnectionRequest) and request.target_node_name == child_target.name
                        and request.source_parameter_name == source.IMAGE_BASH_IMAGES_OUTPUT_PARAMETER and not fired):
                    fired.append(True)
                    newer = deepcopy(second_state)
                    if mutation == "revision":
                        newer["image_bash_workspace"]["revision"] += 1
                    else:
                        newer["shot_routing"]["channel_uuid"] = str(uuid4())
                    second.set_parameter_value(source.WIDGET_STATE_PARAMETER, source._json_text(newer), initial_setup=True)
                return result
            with mock.patch.object(GriptapeNodes, "handle_request", side_effect=change_workspace_mid_connection):
                expect_rejected(lambda: second._hmb_bind_image_bash_workspace(child_target, second_id), "mid-bind " + mutation)
            assert fired
            assert not engine.handle_request(ListConnectionsForNodeRequest(node_name=child_target.name)).incoming_connections
            assert transport_view(child_target) == empty_target
            second.set_parameter_value(source.WIDGET_STATE_PARAMETER, source._json_text(second_state), initial_setup=True)
            assert second._hmb_image_bash_snapshot(second_id) == second_pair
        def fail_new_context(request):
            if isinstance(request, CreateConnectionRequest) and request.target_node_name == child_target.name and request.target_parameter_name == "image_bash_context":
                return CreateConnectionResultFailure(result_details="Synthetic transactional second-wire failure")
            return dispatch(request)
        with mock.patch.object(GriptapeNodes, "handle_request", side_effect=fail_new_context):
            expect_rejected(lambda: second._hmb_bind_image_bash_workspace(child_target, second_id), "second-wire failure")
        assert transport_view(child_target) == empty_target
        assert not engine.handle_request(ListConnectionsForNodeRequest(node_name=child_target.name)).incoming_connections
        assert transport_view(target) == before_guard
        # The actual header performs old-source release -> new-source bind.
        header = header_command("bind", source_node_name=second.name, workspace_id=second_id)
        assert header["bound_source"] == second.name
        header = header_command("bind", source_node_name=node.name, workspace_id=workspace_id)
        assert header["bound_source"] == node.name
        assert node._current_state()["shot_routing"] == shots_before_remote
        # An unavailable newly selected source revokes current Run authority
        # while the cached read retains the exact ready=False envelope.
        ready_state = deepcopy(node._current_state())
        missing_state = deepcopy(ready_state)
        missing_state["assets"] = [row for row in missing_state["assets"] if row["source_uid"] != "import:b"]
        missing_state["image_bash_workspace"]["revision"] += 1
        missing_state[source.UI_EDIT_REVISION_KEY] += 1
        held_scene = deepcopy(target.get_parameter_value("bash_image"))
        held_images, _ = node._hmb_image_bash_snapshot(workspace_id)
        node._publish_state(missing_state)
        with mock.patch.object(node, "_current_state", side_effect=AssertionError("Unready cached read must not normalize catalog")), \
             mock.patch.object(source, "_resolve_selected_assets", side_effect=AssertionError("Unready cached read must not resolve files")):
            held, unready = node._hmb_image_bash_snapshot(workspace_id)
            assert unready["ready"] is False
            assert unready["revision"] == missing_state["image_bash_workspace"]["revision"]
            assert held == held_images
            assert header_command("refresh")["bound_source"] == node.name
        assert target.get_parameter_value("bash_image") == held_scene
        node._publish_state(ready_state)
        assert node._hmb_image_bash_snapshot(workspace_id)[1]["ready"] is True

        # A previously local single-image child is overridden by the parent
        # remote list and must not reappear after an explicit release.
        local_input = engine.handle_request(SetParameterValueRequest(node_name=child_target.name,
            parameter_name=child_parameter.name, value=images[0], initial_setup=True))
        assert local_input.succeeded(), local_input.result_details
        local_before_release = transport_view(child_target)
        expect_rejected(lambda: second._hmb_bind_image_bash_workspace(child_target, second_id, False), "unowned local image child")
        assert transport_view(child_target) == local_before_release
        second._hmb_bind_image_bash_workspace(child_target, second_id)
        secondary_scene = deepcopy(child_target.get_parameter_value("bash_image"))
        before_failed_unbind = transport_view(child_target)
        old_child = list(child_target.get_parameter_by_name("input_images").get_child_parameters())
        old_child_values = {c.name: deepcopy(child_target.get_parameter_value(c.name)) for c in old_child}
        fired_unbind_failure = []
        def fail_after_parent_cleared(request):
            if (isinstance(request, SetParameterValueRequest) and request.node_name == child_target.name
                    and request.parameter_name == "image_bash_context" and request.value == {}
                    and not getattr(request, "initial_setup", False) and not fired_unbind_failure):
                fired_unbind_failure.append(True)
                return SetParameterValueResultFailure(result_details="Synthetic unbind failure after parent clear")
            return dispatch(request)
        with mock.patch.object(GriptapeNodes, "handle_request", side_effect=fail_after_parent_cleared):
            expect_rejected(lambda: second._hmb_bind_image_bash_workspace(child_target, second_id, False),
                            "injected failure after parent clear")
        assert fired_unbind_failure
        restored_children = list(child_target.get_parameter_by_name("input_images").get_child_parameters())
        assert [c.name for c in restored_children] == [c.name for c in old_child], ([c.name for c in restored_children], [c.name for c in old_child])
        assert all(current is original for current, original in zip(restored_children, old_child))
        assert {c.name: child_target.get_parameter_value(c.name) for c in restored_children} == old_child_values
        assert transport_view(child_target) == before_failed_unbind
        assert len(engine.handle_request(ListConnectionsForNodeRequest(node_name=child_target.name)).incoming_connections) == 2
        foreign_child = []
        def foreign_edit_after_parent_clear(request):
            if (isinstance(request, SetParameterValueRequest) and request.node_name == child_target.name
                    and request.parameter_name == "image_bash_context" and request.value == {}
                    and not getattr(request, "initial_setup", False) and not foreign_child):
                foreign_child.append(child_target.get_parameter_by_name("input_images").add_child_parameter())
                return SetParameterValueResultFailure(result_details="Synthetic concurrent edit")
            return dispatch(request)
        with mock.patch.object(GriptapeNodes, "handle_request", side_effect=foreign_edit_after_parent_clear):
            try:
                second._hmb_bind_image_bash_workspace(child_target, second_id, False)
            except ValueError as exc:
                assert "연결 복원이 완료되지 않았습니다" in str(exc)
            else:
                raise AssertionError("Concurrent foreign child was overwritten")
        assert list(child_target.get_parameter_by_name("input_images").get_child_parameters()) == foreign_child
        assert child_target.get_parameter_value("bash_image") == secondary_scene
        # Explicit synthetic recovery: retire only the test's foreign row,
        # restore the original instance, then reconnect the original lease.
        input_list = child_target.get_parameter_by_name("input_images")
        input_list.remove_child(foreign_child[0])
        for child in old_child:
            input_list.add_child(child)
            result = engine.handle_request(SetParameterValueRequest(node_name=child_target.name,
                parameter_name=child.name, value=old_child_values[child.name], initial_setup=True))
            assert result.succeeded(), result.result_details
        second._hmb_bind_image_bash_workspace(child_target, second_id)
        assert len(engine.handle_request(ListConnectionsForNodeRequest(node_name=child_target.name)).incoming_connections) == 2
        assert child_target.get_parameter_value("bash_image") == secondary_scene
        second._hmb_bind_image_bash_workspace(child_target, second_id, False)
        assert child_target.get_parameter_value("input_images") == []
        assert child_target.get_parameter_value("image_bash_context") == {}
        assert child_target.get_parameter_value("bash_image") == secondary_scene
        # Save a real two-node/two-wire flow, retire both instances and cold
        # reopen it through the native SDK. No explicit create command is
        # persisted or replayed; the normal saved native edges own the route.
        existing_size = {"width": 1139, "height": 779}
        loaded_sized = engine.handle_request(CreateNodeRequest(node_type="HMBImageBash", specific_library_name=schema.name,
            node_name="SyntheticExistingSizedBash", override_parent_flow_name=cold_flow.flow_name,
            metadata={"size": existing_size, "synthetic_tag": "preserved"}, create_error_proxy_on_failure=False))
        assert loaded_sized.succeeded(), loaded_sized.result_details
        loaded_node = engine.node_manager.get_node_by_name(loaded_sized.node_name)
        assert loaded_node.metadata.get("size") == existing_size and loaded_node.metadata.get("synthetic_tag") == "preserved"
        removed_sized = engine.handle_request(DeleteNodeRequest(node_name=loaded_node.name))
        assert removed_sized.succeeded(), removed_sized.result_details
        cold_target_created = engine.handle_request(CreateNodeRequest(node_type="HMBImageBash", specific_library_name=schema.name,
            node_name="SyntheticColdRemoteBash", override_parent_flow_name=cold_flow.flow_name, create_error_proxy_on_failure=False))
        assert cold_target_created.succeeded(), cold_target_created.result_details
        cold_target = engine.node_manager.get_node_by_name(cold_target_created.node_name)
        assert cold_target.metadata.get("size") == {"width": 800, "height": 680}
        custom_size = {"width": 1013, "height": 817}
        resized = engine.handle_request(SetNodeMetadataRequest(node_name=cold_target.name,
            metadata={"size": custom_size, "collapsed": True, "hmb_native_studio_expanded_size": custom_size}))
        assert resized.succeeded(), resized.result_details
        cold_source._hmb_bind_image_bash_workspace(cold_target, workspace_id)
        for parameter, value in (("width", 4), ("height", 2), ("output_file", str(Path.cwd() / "cold-two-wire-run.png"))):
            changed = engine.handle_request(SetParameterValueRequest(node_name=cold_target.name,
                parameter_name=parameter, value=value, broadcast_result=False))
            assert changed.succeeded(), changed.result_details
        cold_scene = deepcopy(cold_target.get_parameter_value("bash_image"))
        cold_scene["value"] = "data:image/png;base64," + base64.b64encode(applied_png).decode("ascii")
        cold_scene.setdefault("meta", {})["created_at"] = "2026-10-23T08:20:01.000Z"
        changed = engine.handle_request(SetParameterValueRequest(node_name=cold_target.name,
            parameter_name="bash_image", value=cold_scene, broadcast_result=False))
        assert changed.succeeded(), changed.result_details
        cold_source.state = NodeResolutionState.RESOLVED
        cold_run = await asyncio.wait_for(engine.ahandle_request(ResolveNodeRequest(node_name=cold_target.name)), timeout=15)
        assert cold_run.succeeded(), str(getattr(cold_run, "validation_exceptions", cold_run.result_details))
        await asyncio.sleep(0)
        cold_scene = deepcopy(cold_target.get_parameter_value("bash_image"))
        original_cold_source, original_cold_target = cold_source, cold_target
        cold_commands = engine.handle_request(SerializeFlowToCommandsRequest(flow_name=cold_flow.flow_name,
            include_create_flow_command=True))
        assert cold_commands.succeeded(), cold_commands.result_details
        save_path = Path.cwd() / "synthetic-imageasset-bash-remote.py"
        saved_flow = await engine.ahandle_request(SaveWorkflowFileFromSerializedFlowRequest(
            serialized_flow_commands=cold_commands.serialized_flow_commands, file_name=save_path.stem,
            file_path=str(save_path), display_name="Synthetic ImageAsset Bash Remote", broadcast_result=False))
        assert saved_flow.succeeded(), saved_flow.result_details
        compile(ast.parse(save_path.read_text("utf-8")), str(save_path), "exec")
        deleted = engine.handle_request(DeleteFlowRequest(flow_name=cold_flow.flow_name))
        assert deleted.succeeded(), deleted.result_details
        reopened_flow = await engine.ahandle_request(DeserializeFlowFromCommandsRequest(
            serialized_flow_commands=deepcopy(cold_commands.serialized_flow_commands), broadcast_result=False))
        assert reopened_flow.succeeded(), reopened_flow.result_details
        reopened_nodes = engine.flow_manager.get_flow_by_name(reopened_flow.flow_name).nodes
        cold_source = reopened_nodes[original_cold_source.name]
        cold_target = reopened_nodes[original_cold_target.name]
        assert len(reopened_nodes) == 2 and cold_source is not original_cold_source and cold_target is not original_cold_target
        assert cold_target.get_parameter_value("bash_image") == cold_scene
        assert cold_target.metadata.get("size") == custom_size
        assert cold_target.metadata.get("collapsed") is True
        assert cold_target.metadata.get("hmb_native_studio_expanded_size") == custom_size
        expanded = engine.handle_request(SetNodeMetadataRequest(node_name=cold_target.name,
            metadata={"collapsed": False, "size": custom_size}))
        assert expanded.succeeded(), expanded.result_details
        assert cold_target.metadata.get("size") == custom_size and cold_target.metadata.get("collapsed") is False
        assert cold_target.get_parameter_value("bash_image") == cold_scene
        assert cold_source._current_state()["image_bash_workspace"] == state["image_bash_workspace"]
        assert cold_source._current_state()["shot_routing"] == shots_before
        assert len(engine.handle_request(ListConnectionsForNodeRequest(node_name=cold_target.name)).incoming_connections) == 2
        # Restore must rebuild the accepted lightweight catalog before any
        # header refresh. A stale derived Bash header must never be mistaken
        # for a missing ImageAsset workspace or trigger a catalog-file parse.
        with mock.patch.object(cold_source, "_current_state", side_effect=AssertionError("Cold catalog read must stay cached")), \
             mock.patch.object(source, "_resolve_selected_assets", side_effect=AssertionError("Cold snapshot must stay cached")):
            cold_catalog = cold_source._hmb_image_bash_catalog()
            assert cold_catalog["workspaces"][0]["workspace_id"] == workspace_id
            assert cold_source._hmb_image_bash_catalog_baseline[0] == source._get_parameter_raw(cold_source, source.WIDGET_STATE_PARAMETER)
            assert cold_source._hmb_image_bash_snapshot(workspace_id)[1]["records"] == cold_target._records()
        cold_source.state = NodeResolutionState.RESOLVED
        cold_run = await asyncio.wait_for(engine.ahandle_request(ResolveNodeRequest(node_name=cold_target.name)), timeout=15)
        assert cold_run.succeeded(), str(getattr(cold_run, "validation_exceptions", cold_run.result_details))
        assert File(cold_target.parameter_output_values["output_image"].value).read_bytes() == applied_png
        cold_target._publish_header()
        assert cold_target.get_parameter_value("HMB_IMAGE_BASH_UI")["bound_source"] == cold_source.name

        # External user images are usable by Bash before explicit library
        # registration. Exercise native IMAGE_IMPORT_IN children, the compact
        # edit contract, two native edges, Apply/Run and cold workflow restore.
        # Neither a manifest nor an implicit registration may be touched.
        import_flow = engine.handle_request(CreateFlowRequest(parent_flow_name=None,
            flow_name="UnregisteredImageBashImports", set_as_new_context=False))
        assert import_flow.succeeded(), import_flow.result_details
        import_directory = Path.cwd() / "unregistered-external-images"
        import_directory.mkdir()
        import_paths = [import_directory / (name + ".png") for name in ("External red", "External blue", "External green")]
        for path, color in zip(import_paths, ("red", "blue", "green")):
            Image.new("RGB", (3, 2), color).save(path, "PNG")
        original_files = {path.name: path.read_bytes() for path in import_paths}
        with ExitStack() as imports_guard:
            for function in ("_read_asset_manifest", "_write_asset_manifest_record", "_apply_asset_registration"):
                imports_guard.enter_context(mock.patch.object(source, function,
                    side_effect=AssertionError("Unregistered user import attempted manifest/registration: " + function)))
            imports_guard.enter_context(mock.patch.object(source.HMBImageAssetLibrary, "_schedule_live_import_thumbnail_hydration"))
            imported_created = engine.handle_request(CreateNodeRequest(node_type="HMBImageAssetLibrary", specific_library_name=schema.name,
                node_name="UnregisteredExternalImageAsset", override_parent_flow_name=import_flow.flow_name,
                create_error_proxy_on_failure=False))
            assert imported_created.succeeded(), imported_created.result_details
            imported_source = engine.node_manager.get_node_by_name(imported_created.node_name)
            from griptape.artifacts.image_url_artifact import ImageUrlArtifact
            for path in import_paths[:2]:
                slot = engine.handle_request(AddParameterToNodeRequest(node_name=imported_source.name,
                    parent_container_name=source.IMAGE_IMPORT_PARAMETER))
                assert slot.succeeded(), slot.result_details
                assigned = engine.handle_request(SetParameterValueRequest(node_name=imported_source.name,
                    parameter_name=slot.parameter_name, value=ImageUrlArtifact(value=str(path)), broadcast_result=False))
                assert assigned.succeeded(), assigned.result_details
            imported_state = imported_source._apply_import_value(source._get_parameter_raw(imported_source, source.IMAGE_IMPORT_PARAMETER))
            assert len(imported_state["assets"]) == 2
            assert all(row["source_kind"] == "user" and not row["registered"] for row in imported_state["assets"])
            imported_uids = [row["source_uid"] for row in imported_state["assets"]]
            first_imported_shot = imported_state["shot_routing"]["shots"][0]
            imported_state["shot_routing"]["shots"] = [dict(first_imported_shot, shot_uuid=str(uuid4()), number=number,
                name="Existing external Shot " + str(number), name_is_custom=True, selected_source_uids=imported_uids[:1])
                for number in range(1, 6)]
            imported_state["shot_routing"]["active_shot_uuid"] = imported_state["shot_routing"]["shots"][3]["shot_uuid"]
            import_workspace = dict(workspace_id=str(uuid4()), revision=0, instances=[
                dict(instance_id=str(uuid4()), source_uid=uid) for uid in (imported_uids[1], imported_uids[0], imported_uids[1])])
            imported_state.update(image_bash_workspace=import_workspace, image_bash_active=True)
            imported_state = imported_source._publish_state(source._normalize_state(imported_state))
            import_shots = deepcopy(imported_state["shot_routing"])
            slot = engine.handle_request(AddParameterToNodeRequest(node_name=imported_source.name,
                parent_container_name=source.IMAGE_IMPORT_PARAMETER))
            assert slot.succeeded(), slot.result_details
            assigned = engine.handle_request(SetParameterValueRequest(node_name=imported_source.name,
                parameter_name=slot.parameter_name, value=ImageUrlArtifact(value=str(import_paths[2])), broadcast_result=False))
            assert assigned.succeeded(), assigned.result_details
            imported_state = imported_source._apply_import_value(source._get_parameter_raw(imported_source, source.IMAGE_IMPORT_PARAMETER))
            assert len(imported_state["assets"]) == 3
            def authored_shots(routing_state):
                authored = deepcopy(routing_state)
                authored.pop("generation", None)
                for shot in authored["shots"]:
                    shot.pop("metadata_sha256", None)
                return authored
            # A new imported catalog member advances derived media metadata,
            # while every authored Shot field and selection remains intact.
            assert authored_shots(imported_state["shot_routing"]) == authored_shots(import_shots)
            import_shots = deepcopy(imported_state["shot_routing"])
            new_uid = next(row["source_uid"] for row in imported_state["assets"] if row["source_uid"] not in imported_uids)
            next_workspace = deepcopy(import_workspace)
            next_workspace["revision"] += 1
            next_workspace["instances"].append(dict(instance_id=str(uuid4()), source_uid=new_uid))
            import_edit = dict(schema=source.IMAGE_ASSET_EDIT_SCHEMA, version=1,
                ui_edit_revision=imported_state[source.UI_EDIT_REVISION_KEY] + 1,
                catalog_identity={key: imported_state.get(key) for key in ("catalog_root", "project_root", "project_uid",
                    "project_cache_uid", "manifest_signature", "folder_signature", "scan_revision")},
                selected_source_uids=[row["source_uid"] for row in imported_state["assets"] if row["selected"]],
                edits=dict(shot_routing=deepcopy(import_shots), image_bash_workspace=next_workspace, image_bash_active=True))
            accepted = engine.handle_request(SetParameterValueRequest(node_name=imported_source.name,
                parameter_name=source.WIDGET_STATE_PARAMETER, value=source._json_text(import_edit), broadcast_result=False))
            assert accepted.succeeded(), accepted.result_details
            assert imported_source._current_state()["shot_routing"] == import_shots
            import_target_created = engine.handle_request(CreateNodeRequest(node_type="HMBImageBash", specific_library_name=schema.name,
                node_name="UnregisteredExternalBash", override_parent_flow_name=import_flow.flow_name, create_error_proxy_on_failure=False))
            assert import_target_created.succeeded(), import_target_created.result_details
            import_target = engine.node_manager.get_node_by_name(import_target_created.node_name)
            imported_source._hmb_bind_image_bash_workspace(import_target, import_workspace["workspace_id"])
            import_pair = imported_source._hmb_image_bash_snapshot(import_workspace["workspace_id"])
            assert len(import_pair[0]) == 4 and import_pair[1]["ready"] is True
            assert [row["source_uid"] for row in import_pair[1]["records"]] == [row["instance_id"] for row in next_workspace["instances"]]
            assert [row["url"] for row in import_pair[1]["records"]] == [item.value for item in import_pair[0]]
            assert all(not row["registered"] for row in imported_source._current_state()["assets"])
            # The existing project-card restriction is independent: an
            # unregistered project file cannot borrow the user-import path.
            blocked_project = deepcopy(imported_source._current_state())
            blocked_uid = next_workspace["instances"][0]["source_uid"]
            next(row for row in blocked_project["assets"] if row["source_uid"] == blocked_uid)["source_kind"] = "project"
            assert source._build_image_bash_outputs(source._normalize_state(blocked_project)) is None
            for parameter, value in (("width", 4), ("height", 2), ("output_file", str(Path.cwd() / "unregistered-bash.png"))):
                assigned = engine.handle_request(SetParameterValueRequest(node_name=import_target.name,
                    parameter_name=parameter, value=value, broadcast_result=False))
                assert assigned.succeeded(), assigned.result_details
            import_scene = deepcopy(import_target.get_parameter_value("bash_image"))
            import_scene["value"] = "data:image/png;base64," + base64.b64encode(applied_png).decode("ascii")
            assigned = engine.handle_request(SetParameterValueRequest(node_name=import_target.name,
                parameter_name="bash_image", value=import_scene, broadcast_result=False))
            assert assigned.succeeded(), assigned.result_details
            imported_source.state = NodeResolutionState.RESOLVED
            imported_run = await asyncio.wait_for(engine.ahandle_request(ResolveNodeRequest(node_name=import_target.name)), timeout=15)
            assert imported_run.succeeded(), str(getattr(imported_run, "validation_exceptions", imported_run.result_details))
            await asyncio.sleep(0)
            import_scene = deepcopy(import_target.get_parameter_value("bash_image"))
            assert File(import_target.parameter_output_values["output_image"].value).read_bytes() == applied_png
            import_commands = engine.handle_request(SerializeFlowToCommandsRequest(flow_name=import_flow.flow_name,
                include_create_flow_command=True))
            assert import_commands.succeeded(), import_commands.result_details
            import_save_path = Path.cwd() / "synthetic-unregistered-image-bash.py"
            saved_import = await engine.ahandle_request(SaveWorkflowFileFromSerializedFlowRequest(
                serialized_flow_commands=import_commands.serialized_flow_commands, file_name=import_save_path.stem,
                file_path=str(import_save_path), display_name="Synthetic Unregistered Image Bash", broadcast_result=False))
            assert saved_import.succeeded(), saved_import.result_details
            source_name, target_name = imported_source.name, import_target.name
            deleted = engine.handle_request(DeleteFlowRequest(flow_name=import_flow.flow_name))
            assert deleted.succeeded(), deleted.result_details
            reopened = await engine.ahandle_request(DeserializeFlowFromCommandsRequest(
                serialized_flow_commands=deepcopy(import_commands.serialized_flow_commands), broadcast_result=False))
            assert reopened.succeeded(), reopened.result_details
            imported_source, import_target = (engine.node_manager.get_node_by_name(name) for name in (source_name, target_name))
            with mock.patch.object(imported_source, "_current_state", side_effect=AssertionError("Cold user snapshot must stay cached")), \
                 mock.patch.object(source, "_resolve_selected_assets", side_effect=AssertionError("Cold user snapshot must not register/resolve")):
                assert imported_source._hmb_image_bash_catalog()["workspaces"][0]["count"] == 4
                assert imported_source._hmb_image_bash_snapshot(import_workspace["workspace_id"]) == import_pair
            assert imported_source._current_state()["shot_routing"] == import_shots
            assert imported_source._current_state()["image_bash_workspace"] == next_workspace
            assert all(row["source_kind"] == "user" and not row["registered"] for row in imported_source._current_state()["assets"])
            assert import_target.get_parameter_value("bash_image") == import_scene
            assert len(engine.handle_request(ListConnectionsForNodeRequest(node_name=import_target.name)).incoming_connections) == 2
            imported_source.state = NodeResolutionState.RESOLVED
            imported_run = await asyncio.wait_for(engine.ahandle_request(ResolveNodeRequest(node_name=import_target.name)), timeout=15)
            assert imported_run.succeeded(), str(getattr(imported_run, "validation_exceptions", imported_run.result_details))
            assert File(import_target.parameter_output_values["output_image"].value).read_bytes() == applied_png
            assert not list(import_directory.rglob("*.json"))
            assert {path.name: path.read_bytes() for path in import_paths} == original_files
    print(json.dumps({"status": "PASS", "shot_rows_preserved": 5, "image_instances": 3,
        "bash_new_node_size": {"width": 800, "height": 680},
        "bash_saved_resized_node": {"size": {"width": 1013, "height": 817}, "collapsed": True,
            "expanded_size": {"width": 1013, "height": 817}},
        "duplicate_asset_instances": "distinct stable IDs", "native_connections": 2,
        "auto_created_node_name": "HMBImageBash",
        "image_transport_handles": "hidden; list[ImageUrlArtifact] two-wire contract retained",
        "explicit_create_only": True, "save_restore": True, "reorder_atomic_pair": True,
        "legacy_empty_workspace_edit": True,
        "workspace_authority_guards": 5,
        "partial_wire_retry": "reuses same node", "missing_input_run": "blocked; layers preserved",
        "notification_retry": "cached; newest publication retained",
        "native_two_wire_resolve": True,
        "native_child_list_connection": "type mismatch rejected; original pair preserved",
        "remote_header_commands": "native refresh/unbind/bind/resolve; scene and Apply preserved",
        "remote_authority_guards": "locks/resolving/foreign/occupied/workspace-change; atomic rollback",
        "remote_unready_cached_pair": "ready=False retained; no normalization or media resolve",
        "remote_native_save_cold_reopen": "two nodes/two wires/scene/Apply/exact PNG restored",
        "cold_source_catalog": "accepted cached authority restored before header refresh",
        "unregistered_user_import": "native import/compact edit/duplicate instances/Resolve/save/cold reopen",
        "implicit_manifest_registration": 0,
        "unregistered_project_policy": "unchanged; Bash output remains blocked",
        "page_media_recalculation": 0, "paid_requests": 0, "user_workflow_changes": 0}))


if __name__ == "__main__":
    main()
