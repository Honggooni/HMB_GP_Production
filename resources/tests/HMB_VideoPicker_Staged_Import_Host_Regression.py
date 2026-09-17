"""Real retained event queue, with blocked media I/O and isolated configuration."""
from __future__ import annotations

import asyncio
from contextlib import nullcontext
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main():
    with tempfile.TemporaryDirectory(prefix="hmb-picker-staged-host-") as temporary:
        root = Path(temporary)
        env = {key: str(root / key) for key in (
            "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "LOCALAPPDATA", "APPDATA",
        )}
        with patch.dict(os.environ, env), patch.object(
            socket, "create_connection", side_effect=AssertionError("Network forbidden")
        ):
            try:
                from griptape_nodes.retained_mode.engine import current_engine
                from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
                from griptape_nodes.exe_types.flow import ControlFlow
                from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
            except ImportError:
                if os.environ.get("HMB_PICKER_REQUIRE_HOST") == "1":
                    raise
                print("Picker staged import host: SKIP (Griptape engine unavailable)")
                return
            import HMBVideoPickerLibrary as picker

            # Desktop workers use the process engine. A context-local test
            # engine is not inherited by Python 3.12 threads; this whole process
            # and its configuration are already private to the regression.
            with nullcontext(current_engine()) as engine:
                async def scenario():
                    manager = GriptapeNodes.EventManager()
                    manager.initialize_queue()
                    flow = ControlFlow(name="IsolatedStagedImport", engine=engine)
                    GriptapeNodes.ObjectManager().add_object_by_name(flow.name, flow)
                    node = picker.HMBVideoPickerLibrary(name="StagedImport")
                    flow.add_node(node)
                    GriptapeNodes.ObjectManager().add_object_by_name(node.name, node)
                    GriptapeNodes.NodeManager()._name_to_parent_flow_name[node.name] = flow.name
                    node._schedule_video_removal_output_sync = lambda: None
                    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
                    worker_errors = []
                    process_batch = node._process_video_import_batch

                    def settled_batch(*args):
                        try:
                            return process_batch(*args)
                        finally:
                            finished.set()

                    def slow_import(state, path, **kwargs):
                        entered.set()
                        assert release.wait(8), "Host test did not release media I/O"
                        return picker._append_video_asset(state, {
                            "video_path": path, "import_source_path": path, "label": "server.mp4",
                        }, picker_shot_uuid=kwargs["picker_shot_uuid"], defer_thumbnail=True)

                    command = {
                        "schema": picker.COMMAND_SCHEMA, "version": picker.COMMAND_VERSION,
                        "runtime_instance_id": node._hmb_runtime_instance_id,
                        "action": "import_video_assets", "action_id": "host-stage",
                        "payload": {"picker_shot_uuid": node._picker_state()["active_picker_shot_uuid"],
                                    "sources": [{"source_path": "//server/share/server.mp4"}]},
                    }
                    with patch.object(node, "_import_video_asset", side_effect=slow_import), \
                            patch.object(picker, "_resolved_video_asset_path", return_value=None), \
                            patch.object(node, "_process_video_import_batch", side_effect=settled_batch), \
                            patch.object(threading, "excepthook", side_effect=lambda error: worker_errors.append(str(error.exc_value))):
                        try:
                            result = engine.handle_request(SetParameterValueRequest(
                                node_name=node.name, parameter_name=picker.WIDGET_COMMAND_PARAMETER,
                                value=command, data_type="dict",
                            ))
                            assert "Success" in type(result).__name__, type(result).__name__
                            assert not entered.is_set(), "I/O began inside the initial UI request"
                            received_loading = False
                            deadline = asyncio.get_running_loop().time() + 5
                            while asyncio.get_running_loop().time() < deadline:
                                event = await asyncio.wait_for(manager.event_queue.get(), timeout=5)
                                payload = event.model_dump(mode="python") if hasattr(event, "model_dump") else vars(event)
                                if '"video_imports"' in json.dumps(payload, default=str):
                                    received_loading = True
                                    break
                            assert received_loading, "No loading snapshot reached the real event queue"
                            assert not node._picker_state()["videos"], "Unfinished media leaked into the catalog"
                            assert len(node._picker_state()["video_imports"]) == 1
                        finally:
                            release.set()
                            deadline = asyncio.get_running_loop().time() + 5
                            while not finished.is_set() and asyncio.get_running_loop().time() < deadline:
                                await asyncio.sleep(0.01)
                        assert finished.is_set(), "Copy worker must settle before closing the engine event loop"
                        assert not worker_errors, worker_errors
                        assert entered.is_set()
                        assert len(node._picker_state()["videos"]) == 1
                        assert not node._picker_state().get("video_imports")
                asyncio.run(scenario())
    print("Picker staged import host: PASS (real request, event queue, deferred worker, loading before ready; no network)")


if __name__ == "__main__":
    main()
