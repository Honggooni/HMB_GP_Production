"""Fresh palette Bash / ImageAsset preparation using an isolated real SDK."""
from __future__ import annotations
import asyncio, json, os, platform, socket, subprocess, sys, tempfile
from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

async def exercise(engine):
    from griptape_nodes.node_library.library_registry import LibraryRegistry, LibrarySchema
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    from griptape_nodes.retained_mode.events.flow_events import (CreateFlowRequest, DeleteFlowRequest,
        SerializeFlowToCommandsRequest, DeserializeFlowFromCommandsRequest)
    from griptape_nodes.retained_mode.events.workflow_events import SaveWorkflowFileFromSerializedFlowRequest
    from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest, DeleteNodeRequest
    from griptape_nodes.retained_mode.events.connection_events import ListConnectionsForNodeRequest, CreateConnectionRequest, DeleteConnectionRequest
    from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest, AddParameterToNodeRequest, RemoveParameterFromNodeRequest
    import HMBImageAssetLibrary as asset
    import HMBImageBash as bash
    import _hmb_shot_routing as routing
    import _hmb_connection_management as connections
    schema = LibrarySchema.model_validate_json((ROOT / "griptape-nodes-library.json").read_text("utf-8"))
    library = LibraryRegistry.generate_new_library(schema)
    for name, cls in (("HMBImageAssetLibrary", asset.HMBImageAssetLibrary), ("HMBImageBash", bash.HMBImageBash)):
        meta = next(row.metadata for row in schema.nodes if row.class_name == name)
        library.register_lazy_node_type(name, meta, lambda cls=cls: cls)
    foreign_schema = schema.model_copy(deep=True)
    foreign_schema.name = "Foreign_Same_Class_Names"
    foreign = LibraryRegistry.generate_new_library(foreign_schema)
    for name, cls in (("HMBImageAssetLibrary", asset.HMBImageAssetLibrary), ("HMBImageBash", bash._StockImageBash)):
        meta = next(row.metadata for row in schema.nodes if row.class_name == name)
        fake = type(name, (cls,), {})
        foreign.register_lazy_node_type(name, meta, lambda fake=fake: fake)
    engine.event_manager.initialize_queue()
    class ActiveRegistration:
        active = True
    registration = ActiveRegistration()
    connections.install_request_handlers(engine, registration)
    observed = []
    def observe_create(request, result):
        observed.append((request.node_type, request.initial_setup, result.succeeded(), request.metadata))
    engine.event_manager.add_post_dispatch_hook(CreateNodeRequest, observe_create)
    ensured = engine.handle_request(EnsureWorkflowAndFlowRequest(flow_name="TwoWayA"))
    assert ensured.succeeded(), ensured.result_details

    def create(flow, kind, name, *, initial=False, owner=None):
        result = engine.handle_request(CreateNodeRequest(node_type=kind, specific_library_name=owner or schema.name,
            node_name=name, override_parent_flow_name=flow, initial_setup=initial, create_error_proxy_on_failure=False))
        assert result.succeeded(), result.result_details
        return engine.node_manager.get_node_by_name(result.node_name)
    def flow(name):
        result = engine.handle_request(CreateFlowRequest(parent_flow_name=None, flow_name=name, set_as_new_context=False))
        assert result.succeeded(), result.result_details
        return result.flow_name
    async def settle():
        for _ in range(10): await asyncio.sleep(.03)
    def incoming(node):
        result = engine.handle_request(ListConnectionsForNodeRequest(node_name=node.name, broadcast_result=False))
        assert result.succeeded(), result.result_details
        return result.incoming_connections
    def command(node, operation, **args):
        result = engine.handle_request(SetParameterValueRequest(node_name=node.name, parameter_name="HMB_IMAGE_BASH_UI",
            value={"hmb_image_bash_command": {"operation": operation, **args}}, broadcast_result=False))
        assert result.succeeded(), result.result_details

    with ExitStack() as guard:
        for name in ("schedule_post_registration_reconcile", "schedule_post_hydration_reconcile", "reconcile_shot_routing"):
            guard.enter_context(mock.patch.object(routing, name))
        # Asset first, then the freshly created palette node.
        first = create(ensured.flow_name, "HMBImageAssetLibrary", "FirstAsset")
        shots = deepcopy(first._current_state()["shot_routing"])
        fresh = create(ensured.flow_name, "HMBImageBash", "FreshBash")
        await settle()
        workspace = first._current_state()["image_bash_workspace"]
        assert workspace and len(incoming(fresh)) == 2, (workspace, fresh.get_parameter_value("HMB_BASH_STATUS"),
            fresh._hmb_auto_workspace_pending, bool(getattr(engine.event_manager, "_hmb_bash_creation_observer", None)),
            bool(first._hmb_image_bash_catalog()), engine.event_manager.event_loop is not None, observed,
            fresh.get_parameter_value("bash_image"), fresh.get_parameter_value("image_bash_context"),
            asset._get_parameter_raw(first, asset.WIDGET_STATE_PARAMETER) == getattr(first, "_hmb_last_accepted_widget_state", None),
            [k for k in json.loads(asset._get_parameter_raw(first, asset.WIDGET_STATE_PARAMETER))
             if json.loads(asset._get_parameter_raw(first, asset.WIDGET_STATE_PARAMETER)).get(k)
             != json.loads(first._hmb_last_accepted_widget_state).get(k)])
        assert [r["shot_uuid"] for r in shots["shots"]] == [r["shot_uuid"] for r in first._current_state()["shot_routing"]["shots"]]
        live_meta = fresh.get_parameter_value("bash_image")["meta"]["hmb_image_bash"]
        assert live_meta["workspace_id"] == workspace["workspace_id"]
        assert live_meta["channel_uuid"] == fresh.metadata["hmb_image_bash_channel_uuid"]
        assert live_meta["workspace_revision"] == fresh.get_parameter_value("image_bash_context")["revision"]
        assert live_meta["node_instance_uuid"] == fresh._remote_source_instance(fresh)
        # The desktop removes an empty dynamic input after disconnect. The
        # original child and its parent must remain leased for exact reconnect.
        added = engine.handle_request(AddParameterToNodeRequest(node_name=first.name,
            parent_container_name=asset.IMAGE_IMPORT_PARAMETER))
        assert added.succeeded(), added.result_details
        child = list(first.get_parameter_by_name(asset.IMAGE_IMPORT_PARAMETER).get_child_parameters())[-1].name
        wire = dict(source_node_name=fresh.name, source_parameter_name="output_image",
                    target_node_name=first.name, target_parameter_name=child)
        assert engine.handle_request(CreateConnectionRequest(**wire)).succeeded()
        snapshot = deepcopy(first._current_state())
        scene_before = deepcopy(fresh.get_parameter_value("bash_image"))
        view = connections.describe(engine, fresh.name)
        detached = connections.manage(engine, fresh.name, "disconnect", view["state_token"])
        assert detached["detached"] and not incoming(fresh)
        for parameter in (child, asset.IMAGE_IMPORT_PARAMETER):
            removed = engine.handle_request(RemoveParameterFromNodeRequest(node_name=first.name, parameter_name=parameter))
            assert not removed.succeeded() and first.get_parameter_by_name(child) is not None
            assert "[HMB_CONNECTION_PORT_RETAINED]" in str(removed.result_details)
        unrelated = engine.handle_request(AddParameterToNodeRequest(node_name=first.name,
            parent_container_name=asset.IMAGE_IMPORT_PARAMETER))
        assert unrelated.succeeded()
        extra = list(first.get_parameter_by_name(asset.IMAGE_IMPORT_PARAMETER).get_child_parameters())[-1].name
        assert extra != child and engine.handle_request(RemoveParameterFromNodeRequest(node_name=first.name, parameter_name=extra)).succeeded()
        detached_commands = engine.handle_request(SerializeFlowToCommandsRequest(flow_name=ensured.flow_name,
            include_create_flow_command=True))
        assert detached_commands.succeeded(), detached_commands.result_details
        detached_path = Path.cwd() / "synthetic-detached-lease.py"
        detached_save = await engine.ahandle_request(SaveWorkflowFileFromSerializedFlowRequest(
            serialized_flow_commands=detached_commands.serialized_flow_commands, file_name=detached_path.stem,
            file_path=str(detached_path), display_name="Synthetic Detached Lease", broadcast_result=False))
        assert detached_save.succeeded(), detached_save.result_details
        assert engine.handle_request(DeleteFlowRequest(flow_name=ensured.flow_name)).succeeded()
        detached_reopen = await engine.ahandle_request(DeserializeFlowFromCommandsRequest(
            serialized_flow_commands=deepcopy(detached_commands.serialized_flow_commands), broadcast_result=False))
        assert detached_reopen.succeeded(), detached_reopen.result_details
        reopened_nodes = engine.flow_manager.get_flow_by_name(detached_reopen.flow_name).nodes
        first, fresh = reopened_nodes[first.name], reopened_nodes[fresh.name]
        retained = engine.handle_request(RemoveParameterFromNodeRequest(node_name=first.name, parameter_name=child))
        assert not retained.succeeded() and "[HMB_CONNECTION_PORT_RETAINED]" in str(retained.result_details)
        view = connections.describe(engine, fresh.name)
        reconnected = connections.manage(engine, fresh.name, "reconnect", view["state_token"])
        assert not reconnected["detached"] and len(incoming(fresh)) == 2
        assert any(e.source_node_name == fresh.name and e.target_parameter_name == child
                   for e in incoming(first))
        assert first._current_state() == snapshot and fresh.get_parameter_value("bash_image") == scene_before
        assert engine.handle_request(DeleteConnectionRequest(**wire)).succeeded()
        # Explicit unbind and subsequent refresh must never reconnect it.
        command(fresh, "unbind")
        assert not incoming(fresh)
        command(fresh, "refresh")
        await settle()
        assert not incoming(fresh)
        projection = fresh.get_parameter_value("HMB_IMAGE_BASH_UI")
        choice = next(item for item in projection["sources"] if item["id"] == first.name)
        command(fresh, "bind", source_node_name=first.name, workspace_id=choice["workspace_id"],
                source_instance_id=projection["source_instances"][first.name])
        assert len(incoming(fresh)) == 2
        orphan_slot = engine.handle_request(AddParameterToNodeRequest(node_name=first.name,
            parent_container_name=asset.IMAGE_IMPORT_PARAMETER))
        assert orphan_slot.succeeded()
        orphan_child = list(first.get_parameter_by_name(asset.IMAGE_IMPORT_PARAMETER).get_child_parameters())[-1].name
        orphan_wire = dict(source_node_name=fresh.name, source_parameter_name="output_image",
            target_node_name=first.name, target_parameter_name=orphan_child)
        assert engine.handle_request(CreateConnectionRequest(**orphan_wire)).succeeded()
        view = connections.describe(engine, fresh.name)
        assert connections.manage(engine, fresh.name, "disconnect", view["state_token"])["detached"]
        assert engine.handle_request(DeleteNodeRequest(node_name=fresh.name)).succeeded()
        assert engine.handle_request(RemoveParameterFromNodeRequest(node_name=first.name, parameter_name=orphan_child)).succeeded()
        # Reverse order: fresh Bash remains pending until the asset is created.
        fb = flow("TwoWayB")
        pending = create(fb, "HMBImageBash", "PendingBash")
        await settle()
        assert pending._hmb_auto_workspace_pending and not incoming(pending)
        late = create(fb, "HMBImageAssetLibrary", "LateAsset")
        await settle()
        assert late._current_state()["image_bash_workspace"] and len(incoming(pending)) == 2
        # Two assets: no implicit selection; explicit dropdown target can
        # create just the selected workspace through the same lease checks.
        fc = flow("TwoWayC")
        a = create(fc, "HMBImageAssetLibrary", "ChoiceA")
        b = create(fc, "HMBImageAssetLibrary", "ChoiceB")
        chooser = create(fc, "HMBImageBash", "Chooser")
        await settle()
        assert not incoming(chooser) and not a._current_state()["image_bash_workspace"] and not b._current_state()["image_bash_workspace"]
        projection = chooser.get_parameter_value("HMB_IMAGE_BASH_UI")
        choices = {row["id"]: row for row in projection["sources"]}
        assert {a.name,b.name} <= set(choices) and all(choices[n]["workspace_id"] == bash._PREPARE_WORKSPACE for n in (a.name,b.name))
        command(chooser, "bind", source_node_name=b.name, workspace_id=bash._PREPARE_WORKSPACE,
                source_instance_id=projection["source_instances"][b.name])
        assert len(incoming(chooser)) == 2 and b._current_state()["image_bash_workspace"] and not a._current_state()["image_bash_workspace"]
        # A restored/duplicated node must not create or reconnect a workspace.
        fd = flow("TwoWayD")
        restored_asset = create(fd, "HMBImageAssetLibrary", "RestoreAsset")
        restored = create(fd, "HMBImageBash", "RestoredBash", initial=True)
        await settle()
        command(restored, "refresh")
        assert not incoming(restored) and not restored_asset._current_state()["image_bash_workspace"]
        # An occupied workspace is never stolen by a second fresh node.
        occupied = create(fb, "HMBImageBash", "SecondBash")
        await settle()
        assert not incoming(occupied) and len(incoming(pending)) == 2
        assert late._current_state()["image_bash_workspace"]["workspace_id"] == pending.get_parameter_value("image_bash_context")["workspace_id"]
        projection = occupied.get_parameter_value("HMB_IMAGE_BASH_UI")
        target = next(item for item in projection["sources"] if item["id"] == late.name)
        command(occupied, "bind", source_node_name=late.name, workspace_id=target["workspace_id"],
                source_instance_id=projection["source_instances"][late.name])
        assert not incoming(occupied) and len(incoming(pending)) == 2
        # An edit while a source is absent cancels automatic setup; creating a
        # source later cannot replace a user's edited canvas or settings.
        fe = flow("TwoWayEdited")
        edited = create(fe, "HMBImageBash", "EditedWhilePending")
        await settle()
        assert edited._hmb_auto_workspace_pending
        edited.set_parameter_value("width", 777)
        later_asset = create(fe, "HMBImageAssetLibrary", "AfterEditAsset")
        await settle()
        assert edited.get_parameter_value("width") == 777 and not incoming(edited)
        assert not later_asset._current_state()["image_bash_workspace"]
        # A different library may use the same class name; neither its Bash
        # nor its Asset is a target for HMB's creation observer or selector.
        ff = flow("ForeignBash")
        real_asset = create(ff, "HMBImageAssetLibrary", "RealAssetForeignBash")
        foreign_bash = create(ff, "HMBImageBash", "ForeignBashNode", owner=foreign_schema.name)
        await settle()
        assert not real_asset._current_state()["image_bash_workspace"] and not incoming(foreign_bash)
        fg = flow("ForeignAsset")
        foreign_asset = create(fg, "HMBImageAssetLibrary", "ForeignAssetNode", owner=foreign_schema.name)
        real_bash = create(fg, "HMBImageBash", "RealBashForeignAsset")
        await settle()
        assert not incoming(real_bash) and real_bash._hmb_auto_workspace_pending
        assert not foreign_asset._current_state()["image_bash_workspace"] and not real_bash._remote_sources()
        fh = flow("LockedSource")
        locked_asset = create(fh, "HMBImageAssetLibrary", "LockedAsset")
        locked_asset.lock = True
        locked_before = deepcopy(locked_asset._current_state())
        waiting = create(fh, "HMBImageBash", "WaitingForUnlock")
        await settle()
        assert waiting._hmb_auto_workspace_pending and not incoming(waiting)
        assert locked_asset._current_state() == locked_before
        locked_asset.lock = False
        command(waiting, "refresh")
        await settle()
        assert len(incoming(waiting)) == 2 and locked_asset._current_state()["image_bash_workspace"]
    print(json.dumps({"status":"PASS","scope":"isolated real SDK; no user workflow","asset_first":True,
        "bash_first":True,"two_assets_explicit":True,"unbind_no_reconnect":True,"restore_no_reconnect":True,
        "occupied_not_stolen":True,"edited_pending_preserved":True,"foreign_same_name_ignored":True,
        "locked_source_untouched_then_refresh":True,"dynamic_port_cleanup_blocked_then_three_wires_restored":True,
        "detached_delete_and_orphan_port_cleanup_allowed":True,
        "network":0,"cgt_writes":0,"paid":0}))

def main():
    import _hmb_cgt
    from griptape_nodes.retained_mode.engine import engine_scope
    from griptape_nodes.retained_mode.managers.os_manager import OSManager
    platform.uname()
    real_connect = socket.socket.connect
    def local(sock, addr):
        if isinstance(addr, tuple) and addr[0] in {"127.0.0.1", "::1", "localhost"}:
            return real_connect(sock, addr)
        raise AssertionError("External network forbidden")
    with tempfile.TemporaryDirectory(prefix="hmb-two-way-",ignore_cleanup_errors=True) as tmp:
        environment = {key: str(Path(tmp) / key) for key in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME", "LOCALAPPDATA", "APPDATA", "GTN_CONFIG_WORKSPACE_DIRECTORY")}
        environment.update(HMB_IMAGE_BASH_STANDARD_LIBRARY_PATH=str(Path.home()/"Documents/GriptapeNodes/libraries/griptape-nodes-library-standard"),
            HMB_IMAGE_BASH_EDITOR_BUNDLE_PATH=str(Path.home()/"AppData/Local/ai.griptape.nodes.desktop/current/resources/editor-bundle"))
        with mock.patch.dict(os.environ, environment), mock.patch.object(socket.socket,"connect",local), \
             mock.patch.object(_hmb_cgt,"start_own_wait_after_commit",side_effect=AssertionError("CGT write forbidden")), \
             mock.patch.object(OSManager,"_is_cuda_available",return_value=False), \
             mock.patch.object(subprocess,"Popen",side_effect=AssertionError("Subprocess forbidden")):
            previous = Path.cwd()
            try:
                os.chdir(tmp)
                with engine_scope() as engine:
                    asyncio.run(exercise(engine))
            finally:
                os.chdir(previous)

if __name__ == "__main__": main()
