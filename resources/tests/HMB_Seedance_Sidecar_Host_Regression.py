"""Actual SDK atomic video publication and metadata save, without generation."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
from unittest import mock

ROOT = Path(os.environ.get("HMB_SEEDANCE_TEST_ROOT", str(Path(__file__).resolve().parents[2])))
STANDARD = Path(os.environ.get("HMB_GRIPTAPE_STANDARD_LIBRARY_PATH",
    str(Path.home() / "Documents/GriptapeNodes/libraries/griptape-nodes-library-standard")))
sys.path[:0] = [str(ROOT), str(STANDARD)]


def main() -> None:
    from griptape_nodes.retained_mode.engine import engine_scope
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    with tempfile.TemporaryDirectory(prefix="hmb-seedance-publication-") as directory:
        root = Path(directory)
        workspace = root / "workspace"
        workspace.mkdir()
        env = {key: str(root / key) for key in (
            "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "LOCALAPPDATA", "APPDATA")}
        env["GTN_CONFIG_WORKSPACE_DIRECTORY"] = str(workspace)
        with mock.patch.dict(os.environ, env), mock.patch.object(
            socket, "create_connection", side_effect=AssertionError("Network forbidden")
        ):
            logging.disable(logging.CRITICAL)
            with engine_scope() as engine:
                from griptape_nodes.files.project_file import ProjectFileDestination
                from griptape_nodes.retained_mode.file_metadata.sidecar_metadata import _resolve_sidecar_path
                from HMBSeedanceGeneration import HMBSeedanceGeneration
                from _hmb_video_tools import _find_ffmpeg
                ensured = engine.handle_request(EnsureWorkflowAndFlowRequest(
                    display_name="Offline publication", flow_name="OfflinePublication"))
                assert ensured.succeeded(), ensured.result_details
                workflow = engine.open_workflows.get(ensured.workflow_id)
                for extension in ("mp4", "mov"):
                    source = root / ("external." + extension)
                    subprocess.run([_find_ffmpeg(), "-v", "error", "-f", "lavfi", "-i",
                        "testsrc2=s=96x64:r=24", "-t", "0.25", "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", str(source)], check=True)
                    content = source.read_bytes()
                    destination = ProjectFileDestination.from_situation_in_workflow(workflow,
                        filename="published." + extension, situation="save_node_output",
                        node_name="OfflineSeedance", parameter_name="video_url")
                    published = asyncio.run(HMBSeedanceGeneration._atomic_publish_completed_video(
                        destination, content, extension))
                    target = Path(published.resolve()).resolve()
                    assert target.is_relative_to(workspace.resolve()), target
                    assert target.read_bytes() == content
                    metadata = _resolve_sidecar_path(target, engine, workflow)
                    assert metadata.is_relative_to(workspace.resolve()), metadata
                    document = json.loads(metadata.read_text(encoding="utf-8"))
                    assert document["schema_version"] and document["situation"]
                    assert document["situation"]["variables"]["file_extension"] == extension
                    assert source.read_bytes() == content
                    assert not list(target.parent.glob("*.partial*"))
    print("HMB_SEEDANCE_SIDECAR_HOST=PASS (actual SDK atomic MP4/MOV and metadata; no generation/network)")


if __name__ == "__main__":
    main()
