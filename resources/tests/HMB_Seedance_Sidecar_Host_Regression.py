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


def check_competing_directory_versions(workspace, owner, content):
    from griptape_nodes.common.macro_parser import ParsedMacro
    import griptape_nodes.files.file as sdk_files
    from griptape_nodes.files.project_file import ProjectFileDestination
    from griptape_nodes.retained_mode.engine import engine_scope
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    from griptape_nodes.retained_mode.events.os_events import ExistingFilePolicy, WriteFileRequest
    from griptape_nodes.retained_mode.events.project_events import GetPathForMacroRequest, MacroPath
    from HMBSeedanceGeneration import HMBSeedanceGeneration as Node

    template = ParsedMacro(workspace.as_posix() + "/take_{###}/video.mp4")
    destination = ProjectFileDestination(MacroPath(template, {}), workflow=owner,
        existing_file_policy=ExistingFilePolicy.CREATE_NEW)
    def path(index):
        return workspace / f"take_{index:03}" / "video.mp4"

    for index in (*range(1, 18), 19):
        existing = path(index)
        existing.parent.mkdir(parents=True)
        existing.write_bytes(b"existing version")
    resolved = []
    writes = []
    dispatch = sdk_files.handle_request_in
    async_dispatch = sdk_files.ahandle_request_in
    claim = Node._publish_output_without_overwrite

    def observe(workflow, request):
        if isinstance(request, GetPathForMacroRequest) and request.parsed_macro == template:
            resolved.append((workflow, request.variables["_index"]))
        return dispatch(workflow, request)

    async def observe_write(workflow, request):
        if isinstance(request, WriteFileRequest):
            writes.append(workflow)
        return await async_dispatch(workflow, request)

    def race(stage, candidate):
        if candidate == path(18):
            candidate.write_bytes(b"concurrent version")
        return claim(stage, candidate)

    with engine_scope() as editor:
        opened = editor.handle_request(EnsureWorkflowAndFlowRequest(display_name="Other editor", flow_name="Other"))
        other = editor.open_workflows.get(opened.workflow_id)
        assert other is not owner
        with editor.bind_workflow(other), mock.patch.object(sdk_files, "handle_request_in", side_effect=observe), \
             mock.patch.object(sdk_files, "ahandle_request_in", side_effect=observe_write), \
             mock.patch.object(Node, "_publish_output_without_overwrite", side_effect=race):
            assert Node._preflight_output_destination(destination, "mp4") == path(18)
            assert resolved == [(owner, index) for index in range(1, 19)], "Preflight lost the output's workflow or scanned twice"
            resolved.clear()
            saved = asyncio.run(Node._atomic_publish_completed_video(destination, content, "mp4"))
            assert resolved == [(owner, index) for index in range(1, 21)], "Publication repeated a scan or lost the output's workflow"
            assert writes == [owner, owner], "Staging did not use the connected output's workflow"
            assert Path(saved.resolve()) == path(20) and saved.read_bytes() == content
    assert path(18).read_bytes() == b"concurrent version" and path(19).read_bytes() == b"existing version"
    assert not list(workspace.rglob("*.partial*")) and not list(workspace.rglob("*.output-probe"))


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
                from griptape_nodes.retained_mode.events.app_events import AppInitializationComplete
                from griptape_nodes.retained_mode.file_metadata.sidecar_metadata import SituationMetadata, _resolve_sidecar_path
                from HMBSeedanceGeneration import HMBSeedanceGeneration
                from _hmb_video_tools import _find_ffmpeg
                ensured = engine.handle_request(EnsureWorkflowAndFlowRequest(
                    display_name="Offline publication", flow_name="OfflinePublication"))
                assert ensured.succeeded(), ensured.result_details
                workflow = engine.open_workflows.get(ensured.workflow_id)
                for extension in ("mp4", "mov", "png"):
                    source = root / ("external." + extension)
                    encode = ["-frames:v", "1"] if extension == "png" else ["-t", "0.25", "-c:v", "libx264", "-pix_fmt", "yuv420p"]
                    subprocess.run([_find_ffmpeg(), "-v", "error", "-f", "lavfi", "-i",
                        "testsrc2=s=96x64:r=24", *encode, str(source)], check=True)
                    content = source.read_bytes()
                    destination = ProjectFileDestination.from_situation_in_workflow(workflow,
                        filename="published." + extension, situation="save_node_output",
                        node_name="OfflineSeedance", parameter_name="video_url")
                    published_paths = []
                    for expected_index in ("1", "2"):
                        if extension == "png" and expected_index == "2":
                            # Once Desktop has initialized, its PNG writer can embed
                            # workflow metadata. Both states must preserve the original.
                            asyncio.run(engine.artifact_manager.on_app_initialization_complete(AppInitializationComplete()))
                        publication = (
                            HMBSeedanceGeneration._atomic_publish_completed_png(destination, content)
                            if extension == "png" else
                            HMBSeedanceGeneration._atomic_publish_completed_video(destination, content, extension)
                        )
                        published = asyncio.run(publication)
                        target = Path(published.resolve()).resolve()
                        assert target.is_relative_to(workspace.resolve()) and target not in published_paths, target
                        published_paths.append(target)
                        assert published.read_bytes() == content
                        metadata = _resolve_sidecar_path(target, engine, workflow)
                        assert metadata.is_relative_to(workspace.resolve()), metadata
                        document = json.loads(metadata.read_text(encoding="utf-8"))
                        assert document["schema_version"]
                        situation = SituationMetadata.model_validate(document["situation"])
                        assert situation.variables["file_extension"] == extension
                        assert situation.variables["_index"] == expected_index
                        assert not list(target.parent.glob("*.partial*"))
                    assert source.read_bytes() == content
                    assert all(path.read_bytes() == content for path in published_paths)
                check_competing_directory_versions(workspace, workflow, (root / "external.mp4").read_bytes())
    print("HMB_SEEDANCE_SIDECAR_HOST=PASS (actual SDK atomic MP4/MOV/PNG, collision versions and typed metadata; no generation/network)")


if __name__ == "__main__":
    main()
