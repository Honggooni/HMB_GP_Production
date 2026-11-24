"""Real installed Griptape project-copy/sidecar APIs, isolated from user data."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from unittest import mock


ROOT = Path(os.environ.get("HMB_PICKER_TEST_ROOT", str(Path(__file__).resolve().parents[2])))
sys.path.insert(0, str(ROOT))


def main() -> None:
    from griptape_nodes.retained_mode.engine import engine_scope
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest

    with tempfile.TemporaryDirectory(prefix="hmb-picker-sidecar-host-") as directory:
        root = Path(directory)
        workspace = root / "workspace"
        workspace.mkdir()
        env = {key: str(root / key) for key in (
            "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "LOCALAPPDATA", "APPDATA",
        )}
        env["GTN_CONFIG_WORKSPACE_DIRECTORY"] = str(workspace)
        blocked = {"griptape_nodes_library": None, "griptape_nodes_library.utils.macro_path_utils": None}
        with mock.patch.dict(sys.modules, blocked), mock.patch.dict(os.environ, env), mock.patch.object(
            socket, "create_connection", side_effect=AssertionError("Network forbidden")
        ):
            logging.disable(logging.CRITICAL)
            with engine_scope() as engine:
                from griptape_nodes.files.file import File
                from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
                from griptape_nodes.retained_mode.file_metadata.sidecar_metadata import _resolve_sidecar_path
                import HMBVideoPickerLibrary as picker
                from _hmb_video_tools import _find_ffmpeg

                GriptapeNodes.StaticFilesManager()._static_server_base_url = "http://127.0.0.1:43219"
                ensured = engine.handle_request(EnsureWorkflowAndFlowRequest(
                    display_name="Picker publication", flow_name="PickerPublication"
                ))
                assert ensured.succeeded(), ensured.result_details
                workflow = engine.open_workflows.get(ensured.workflow_id)
                source = root / "external-depth.mp4"
                subprocess.run([
                    _find_ffmpeg(), "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=96x64:r=24",
                    "-t", "0.25", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source),
                ], check=True)
                assert picker._picker_project_macro(source, workflow) is None
                # Each output uses the same publication API, regardless of Maya version.
                for slot, role in enumerate(("Original", "Mask", "Depth", "MotionGuide"), 1):
                    records = []
                    artifact, macro = picker._copy_video_to_griptape_project(
                        SimpleNamespace(name=f"Picker_{role}", workflow=workflow), source, slot,
                        transaction_records=records, backup_folder=root / f"backup-{slot}",
                    )
                    target = Path(File(macro).resolve()).resolve()
                    assert target.is_relative_to(workspace.resolve()), target
                    assert target.read_bytes() == source.read_bytes()
                    assert picker._picker_project_macro(target, workflow) == macro
                    reopened = Path(File(macro, workflow=workflow).resolve()).resolve()
                    assert reopened == target and reopened.read_bytes() == source.read_bytes()
                    with engine.bind_workflow(workflow):
                        assert picker._picker_tools_reference_path(macro) == reopened
                    duplicate_records = []
                    _, same_macro = picker._copy_video_to_griptape_project(
                        SimpleNamespace(name=f"Picker_{role}", workflow=workflow), reopened, slot,
                        transaction_records=duplicate_records, backup_folder=root / f"duplicate-{slot}",
                    )
                    assert same_macro == macro and not duplicate_records
                    metadata = _resolve_sidecar_path(target, engine, workflow)
                    assert metadata.is_relative_to(workspace.resolve()), metadata
                    document = json.loads(metadata.read_text(encoding="utf-8"))
                    assert document["schema_version"] and document["situation"]
                    assert artifact is not None and len(records) >= 2
                    picker.HMBVideoPickerLibrary._restore_playblast_bundle(records)
                    assert not target.exists() and not metadata.exists()
                    assert source.is_file(), "Rollback must not remove the source video."
    print("HMB_PICKER_SIDECAR_HOST=PASS (real host project copy, macro reopen without duplicate, metadata, rollback; 4 output roles, Standard blocked)")


if __name__ == "__main__":
    main()
