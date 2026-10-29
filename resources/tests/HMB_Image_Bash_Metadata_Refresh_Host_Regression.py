"""Actual SDK header Refresh is metadata-only; object leases reject stale binds.

Disposable retained graph only. No live application, install, server, raster
reads, provider, or workflow file is touched. Full Apply/Run pixel validation
is covered by HMB_Image_Bash_Host_Regression.py separately.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
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
STANDARD = Path.home() / "Documents/GriptapeNodes/libraries/griptape-nodes-library-standard"
EDITOR = Path.home() / "AppData/Local/ai.griptape.nodes.desktop/current/resources/editor-bundle"


async def exercise(engine):
    import HMBImageBash as product
    from griptape.artifacts import ImageUrlArtifact
    from griptape_nodes.exe_types.node_types import DataNode
    from griptape_nodes.node_library.library_registry import LibraryRegistry, LibrarySchema
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest, DeleteNodeRequest
    from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest

    workspace = "synthetic-workspace-preserved-across-replacement"

    class Source(DataNode):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.calls = []

        def _hmb_image_bash_catalog(self):
            return {"schema": "hmb-image-bash-workspace-catalog-v1", "source_node": self.name,
                    "channel_uuid": "synthetic-channel", "publisher_instance_uuid": "synthetic-publisher",
                    "workspaces": [{"workspace_id": workspace, "name": "HMBImageBash", "revision": 1, "count": 2}]}

        def _hmb_bind_image_bash_workspace(self, target_node, workspace_id, enabled=True):
            self.calls.append((target_node, workspace_id, enabled))

    def send(request):
        request.broadcast_result = False
        result = engine.handle_request(request)
        assert result.succeeded(), result.result_details
        return result

    schema = LibrarySchema.model_validate_json((ROOT / "griptape-nodes-library.json").read_text("utf-8-sig"))
    library = LibraryRegistry.generate_new_library(schema)
    metadata = next(row.metadata for row in schema.nodes if row.class_name == "HMBImageBash")
    library.register_lazy_node_type("HMBImageBash", metadata, lambda: product.HMBImageBash)
    # Source discovery accepts only the exact class registered for the HMB
    # ImageAsset node type. Keep this metadata-only stand-in inside that real
    # registry contract rather than weakening the production identity guard.
    source_metadata = next(row.metadata for row in schema.nodes if row.class_name == "HMBImageAssetLibrary")
    library.register_lazy_node_type("HMBImageAssetLibrary", source_metadata, lambda: Source)
    engine.event_manager.initialize_queue()
    ensured = send(EnsureWorkflowAndFlowRequest(flow_name="SyntheticBashMetadataRefresh"))

    def create(kind, name):
        result = send(CreateNodeRequest(node_type=kind, node_name=name, specific_library_name=schema.name,
            override_parent_flow_name=ensured.flow_name, initial_setup=True, create_error_proxy_on_failure=False))
        return engine.node_manager.get_node_by_name(result.node_name)

    def command(node, operation="refresh", **payload):
        return send(SetParameterValueRequest(node_name=node.name, parameter_name=product.HEADER_PARAMETER,
            value={"hmb_image_bash_command": {"operation": operation, **payload}}))

    try:
        node = create("HMBImageBash", "Synthetic Bash metadata target")
        source = create("HMBImageAssetLibrary", "Synthetic source")
        assert product._hmb_is_registered_node(source, "HMBImageAssetLibrary")
        # Authored dirty data, embedded receipt and prior output are kept even
        # when no live ImageAsset is bound. Merely listing sources cannot edit it.
        dirty = deepcopy(node.get_parameter_value("bash_image"))
        dirty.setdefault("meta", {}).update(future_authored={"zero": 0, "off": False, "literal": ""},
            hmb_image_bash={"apply": {"schema": product.RECEIPT_SCHEMA, "png_base64": "synthetic-not-read"}})
        node.set_parameter_value("bash_image", dirty, initial_setup=True)
        retained_output = ImageUrlArtifact("data:image/png;base64,retained-output-not-read")
        node.set_parameter_value("output_image", retained_output, initial_setup=True)
        node.parameter_output_values["output_image"] = retained_output
        node.set_parameter_value("image_bash_context", {"schema": product.CONTEXT_SCHEMA,
            "workspace_id": workspace, "revision": 1, "records": []}, initial_setup=True)
        node.set_parameter_value("HMB_BASH_VERIFICATION", {"previous": "retained"}, initial_setup=True)
        before = {key: deepcopy(node.get_parameter_value(key)) for key in
                  ("bash_image", "input_images", "image_bash_context", "output_image", "HMB_BASH_VERIFICATION", "HMB_BASH_STATUS")}
        forbidden = ("_sync_metadata_with_input_images", "_sync_project", "_source_hashes", "_clear_output", "_set_project")
        with mock.patch.object(product, "_read_bytes", side_effect=AssertionError("Refresh read source pixels")):
            from contextlib import ExitStack
            with ExitStack() as patches:
                probes = [patches.enter_context(mock.patch.object(node, name,
                    side_effect=AssertionError("Refresh touched " + name))) for name in forbidden]
                for _ in range(3):
                    command(node)
                assert all(probe.call_count == 0 for probe in probes)
                assert {key: node.get_parameter_value(key) for key in before} == before
                assert node.parameter_output_values["output_image"] is retained_output
                header = node.get_parameter_value(product.HEADER_PARAMETER)
                assert len(header["sources"]) == 1 and not header["bound_source"]
                old_lease = header["source_instances"][source.name]
                assert old_lease and old_lease == node._remote_source_instance(source)

                send(DeleteNodeRequest(node_name=source.name))
                command(node)
                assert node.get_parameter_value(product.HEADER_PARAMETER)["sources"] == []
                assert {key: node.get_parameter_value(key) for key in before} == before

                replacement = create("HMBImageAssetLibrary", "Synthetic source")
                assert product._hmb_is_registered_node(replacement, "HMBImageAssetLibrary")
                command(node)
                new_lease = node.get_parameter_value(product.HEADER_PARAMETER)["source_instances"][replacement.name]
                assert new_lease != old_lease
                assert all(probe.call_count == 0 for probe in probes)

        # Old delayed UI command has the same name/workspace but a retired
        # object lease. It must not invoke either source's binding hook.
        command(node, "bind", source_node_name=replacement.name, workspace_id=workspace, source_instance_id=old_lease)
        assert not replacement.calls and not source.calls
        assert "교체" in node.get_parameter_value("HMB_BASH_STATUS")
        assert node.get_parameter_value("bash_image") == before["bash_image"]
        command(node, "bind", source_node_name=replacement.name, workspace_id=workspace, source_instance_id=new_lease)
        assert replacement.calls == [(node, workspace, True)]

        # A delayed deselect is also an edit: it must not sever a newly bound
        # same-name source or a changed workspace. Fake only edge discovery;
        # the command still enters through the actual native parameter request.
        with mock.patch.object(node, "_remote_bound_source", return_value=replacement):
            command(node, "unbind", workspace_id=workspace, source_instance_id=old_lease)
            assert replacement.calls == [(node, workspace, True)]
            assert "교체" in node.get_parameter_value("HMB_BASH_STATUS")
            command(node, "unbind", workspace_id="retired-workspace", source_instance_id=new_lease)
            assert replacement.calls == [(node, workspace, True)]
            assert "작업 공간" in node.get_parameter_value("HMB_BASH_STATUS")
            command(node, "unbind", workspace_id=workspace, source_instance_id=new_lease)
            assert replacement.calls[-1] == (node, workspace, False)
            # Older direct SDK callers do not carry this transient header lease.
            command(node, "unbind")
            assert replacement.calls[-2:] == [(node, workspace, False)] * 2
        assert node.get_parameter_value("bash_image") == before["bash_image"]
        assert node.parameter_output_values["output_image"] is retained_output

        # Real input updates retain the existing deep validation path.
        with mock.patch.object(node, "_sync_metadata_with_input_images") as deep_sync:
            send(SetParameterValueRequest(node_name=node.name, parameter_name="image_bash_context",
                value={"schema": product.CONTEXT_SCHEMA, "workspace_id": workspace, "revision": 2, "records": []}))
            assert deep_sync.call_count == 1

        print(json.dumps({"status": "PASS", "scope": "actual installed SDK disposable graph",
            "metadata_refresh_preserves_dirty_scene_receipt_output": True,
            "raster_reads_scene_sync_output_clear": 0, "same_name_replacement_stale_bind_rejected": True,
            "stale_unbind_and_changed_workspace_rejected": True, "legacy_direct_unbind_preserved": True,
            "source_delete_create_projection": True, "input_change_deep_validation_retained": True,
            "network_calls": 0, "provider_calls": 0, "live_application_calls": 0}))
    finally:
        LibraryRegistry.unregister_library(schema.name, event_manager=engine.event_manager)


def main():
    previous = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="hmb-bash-metadata-") as folder:
        path = Path(folder)
        env = {key: str(path / key) for key in ("APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME", "XDG_DATA_HOME",
            "XDG_CACHE_HOME", "XDG_STATE_HOME", "GTN_CONFIG_WORKSPACE_DIRECTORY")}
        env.update(HMB_IMAGE_BASH_STANDARD_LIBRARY_PATH=str(STANDARD), HMB_IMAGE_BASH_EDITOR_BUNDLE_PATH=str(EDITOR))
        for key, value in env.items():
            if not key.startswith("HMB_"): Path(value).mkdir()
        with mock.patch.dict(os.environ, env), mock.patch.object(socket, "create_connection", side_effect=AssertionError("Network forbidden")):
            os.chdir(path)
            logging.disable(logging.CRITICAL)
            try:
                from griptape_nodes.retained_mode.engine import engine_scope
                with engine_scope() as engine:
                    asyncio.run(exercise(engine))
            finally:
                os.chdir(previous)
                logging.shutdown()


if __name__ == "__main__":
    main()
