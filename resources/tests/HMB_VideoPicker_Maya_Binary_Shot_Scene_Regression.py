"""Verify one Maya binary scene per shot and READ without changing rendered media."""
from __future__ import annotations

import copy
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile
import threading
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import HMBVideoPickerLibrary as picker


SHOTS = [f"11111111-1111-4111-8111-{number:012d}" for number in range(1, 6)]
BOUND = [f"22222222-2222-4222-8222-{number:012d}" for number in range(1, 6)]


def set_scene(state: dict, scene: Path, label: str) -> dict:
    scene_path = scene.as_posix()
    state.update({
        "scene_path": scene_path, "scene_draft_path": scene_path, "scene_request_path": scene_path,
        "scene_stage": "OUTLINER_READY", "status": "OUTLINER_READY", "native_read_ready": True,
        "native_metadata": {"scene_path": scene_path},
        "camera": f"{label}Camera", "selected_camera": f"{label}Camera",
        "cameras": [{"name": f"{label}Camera", "full_path": f"|{label}Camera"}],
        "outliner_nodes": [{"name": label, "full_path": f"|{label}", "maya_uuid": f"{label}-root"}],
        "outliner_expanded": [f"|{label}"], "selected_outliner_path": f"|{label}",
        "selected_outliner_uuid": f"{label}-root", "selected_color": "Red",
        "slot_assignments": [{"video_slot": 1, "bindings": [
            {"full_dag_path": f"|{label}", "maya_uuid": f"{label}-root", "color": "Red"},
        ]}],
        "slot_visibility": [{"video_slot": 1, "hidden_paths": [f"|{label}Hidden"]}],
        "start_frame": 101, "end_frame": 124, "current_frame": 105, "source_fps": 24,
        "has_maya_frame_range": True,
    })
    return picker._parse_state(state)


def switch(state: dict, shot: str) -> dict:
    projected = picker._activate_picker_workspace_projection(state, shot)
    assert projected is not None
    assert projected["active_picker_shot_uuid"] == shot
    return projected


def authored_scene(state: dict) -> dict:
    return {key: copy.deepcopy(state.get(key)) for key in (
        "scene_path", "scene_request_path", "native_read_ready", "native_metadata", "selected_camera",
        "outliner_nodes", "selected_outliner_path", "selected_color", "slot_assignments", "slot_visibility",
    )}


def rendered_media(state: dict) -> dict:
    return {
        "videos": sorted((row["video_uid"], row["picker_shot_uuid"], row["video_path"]) for row in state["videos"]),
        "shots": [(
            row["workspace_uuid"], row["bound_shot_uuid"], row["video_asset_uids"], row["selected_video_uids"],
            row["preview_video_uid"],
        ) for row in state["picker_shots"]],
    }


def install_test_state(node: picker.HMBVideoPickerLibrary, state: dict) -> None:
    node._store_initial_parameter_value(picker.WIDGET_STATE_PARAMETER, json.dumps(state))
    node._restore_dynamic_state(adopt_serialized=True)


def read_command(node: picker.HMBVideoPickerLibrary, shot: str, scene: Path, action_id: str) -> None:
    node._handle_picker_command({
        "runtime_instance_id": node._hmb_runtime_instance_id,
        "action": "read_scene", "action_id": action_id,
        "payload": {"picker_shot_uuid": shot, "scene_path": scene.as_posix()},
    })


def run() -> None:
    with tempfile.TemporaryDirectory(prefix="hmb-picker-binary-shots-") as directory:
        folder = Path(directory).resolve()
        scenes = [folder / f"Shot-{number}.mb" for number in range(1, 6)]
        scene_a, scene_b = scenes[:2]
        replacement = folder / "Replacement.mb"
        for scene in [*scenes, replacement]:
            scene.write_bytes(f"Maya binary fixture for mocked scan {scene.stem}".encode())
        videos = [folder / f"render-{number}.mp4" for number in range(1, 6)]
        for video in videos:
            video.write_bytes(f"existing render {video.stem}".encode())
        source_hashes = {path: sha256(path.read_bytes()).hexdigest() for path in [*videos, *scenes, replacement]}

        state = picker._default_widget_state()
        state["picker_shots"] = [picker._new_picker_workspace_row(number, workspace_uuid=shot, bound_shot_uuid=bound)
                                 for number, (shot, bound) in enumerate(zip(SHOTS, BOUND), 1)]
        state["active_picker_shot_uuid"] = SHOTS[0]
        for number, (shot, video) in enumerate(zip(SHOTS, videos), 1):
            state = picker._append_video_asset(state, {
                "video_uid": f"saved-render-{number}", "source_uid": f"saved-render-{number}",
                "video_path": video.as_posix(), "label": video.stem, "generation_role": "mask",
            }, picker_shot_uuid=shot)

        # Saved ASCII Maya and Blender states keep the shared authoring behavior
        # when they contain no binary scene or existing per-shot ownership.
        for extension in ("ma", "blend"):
            legacy = set_scene(copy.deepcopy(state), folder / f"legacy.{extension}", "LegacyActor")
            assert authored_scene(switch(legacy, SHOTS[4])) == authored_scene(legacy)

        # A saved workflow predating per-shot scene state owns its binary scene
        # only in the saved active workspace. Its media is already shot-owned.
        state.pop("picker_scene_states", None)
        state.pop("picker_scene_owner_uuid", None)
        state = set_scene(state, scene_a, "ActorA")
        expected_a = authored_scene(state)
        expected_media = rendered_media(state)
        blank_b = switch(state, SHOTS[1])
        assert not blank_b["scene_path"] and not blank_b["native_read_ready"]
        assert not blank_b["outliner_nodes"]
        assert rendered_media(blank_b) == expected_media
        state = set_scene(blank_b, scene_b, "ActorB")
        expected_b = authored_scene(state)
        assert authored_scene(switch(state, SHOTS[0])) == expected_a
        assert not switch(state, SHOTS[2])["scene_path"]

        # Reopen using the retained serialized parameter and the SDK's ordinary
        # adoption hook. Neither the old native scene parameter nor an inactive
        # workspace may overwrite the saved active owner's path.
        node = picker.HMBVideoPickerLibrary(name="Maya binary shot scene regression")
        node._schedule_missing_video_thumbnail_recovery = lambda: None
        node._sync_outputs_from_state = lambda _state: None
        with patch.object(picker, "_request_parameter_value", return_value=False):
            node._store_initial_parameter_value("MAYA_SCENE", replacement.as_posix())
            install_test_state(node, state)
            restored = node._picker_state()
            assert authored_scene(restored) == expected_b
            assert authored_scene(switch(restored, SHOTS[0])) == expected_a
            assert not switch(restored, SHOTS[2])["scene_path"]
            assert rendered_media(restored) == expected_media

            # Use the normal READ command and operation reservation. Substitute
            # only the Maya scan so the test needs neither Maya nor media codecs.
            reads = []

            def scan(scene_text, context=None):
                assert context is not None and context.picker_shot_uuid == SHOTS[0]
                node._assert_operation_current(context, "binary READ regression scan")
                reads.append((Path(scene_text), switch(node._picker_state(), SHOTS[0])))

            with patch.object(node, "_read_scene_mode", side_effect=scan):
                for index, scene in enumerate((scene_a, replacement), 1):
                    active = switch(node._picker_state(), SHOTS[0])
                    node._write_state(set_scene(active, scene_a, "ActorA"))
                    read_command(node, SHOTS[0], scene, f"binary-read-{index}")
                    assert len(reads) == index, node._picker_state().get("message")
                    captured_scene, accepted = reads[-1]
                    assert captured_scene.resolve() == scene.resolve()
                    assert not accepted["native_read_ready"] and not accepted["native_metadata"]
                    assert not accepted["outliner_nodes"] and not accepted["selected_camera"]
                    assert not any(row["bindings"] for row in accepted["slot_assignments"])
                    assert not any(row["hidden_paths"] for row in accepted["slot_visibility"])
                    assert rendered_media(accepted) == expected_media
                    assert authored_scene(switch(node._picker_state(), SHOTS[1])) == expected_b

            # A READ started on A must still commit to A while B is visible.
            # Only the external scan is simulated. Projection and the worker's
            # authoritative merge run against the real node state.
            entered, finish = threading.Event(), threading.Event()
            published = []

            def complete_after_navigation(scene_text, context=None):
                entered.set()
                assert finish.wait(10), "navigation did not finish"
                node._assert_operation_current(context, "binary READ after navigation")
                assert node._picker_state()["active_picker_shot_uuid"] == SHOTS[1]
                authored = node._operation_stage_state(context)
                assert authored["active_picker_shot_uuid"] == SHOTS[0]
                authored = set_scene(authored, Path(scene_text), "FreshActor")
                node._write_state(node._mark_operation_finished(authored))
                published.append(authored_scene(authored))

            node._write_state(switch(node._picker_state(), SHOTS[0]))
            with patch.object(node, "_read_scene_mode", side_effect=complete_after_navigation):
                worker = threading.Thread(
                    target=read_command, args=(node, SHOTS[0], replacement, "binary-read-navigate"),
                )
                worker.start()
                try:
                    assert entered.wait(10), node._picker_state().get("message")
                    node._write_state(switch(node._picker_state(), SHOTS[1]))
                finally:
                    finish.set()
                    worker.join(10)
                assert not worker.is_alive()
            completed = node._picker_state()
            assert published, completed.get("message")
            assert completed["active_picker_shot_uuid"] == SHOTS[1]
            assert authored_scene(completed) == expected_b
            assert authored_scene(switch(completed, SHOTS[0])) == published[0]
            assert rendered_media(completed) == expected_media

            # Read five different scene identities through the same command
            # path. Every next READ leaves the prior results in their own shot.
            expected_scenes = {}

            def complete_scan(scene_text, context=None):
                node._assert_operation_current(context, "five-scene READ")
                owner = context.picker_shot_uuid
                scene = Path(scene_text)
                assert scene.resolve() == scenes[SHOTS.index(owner)].resolve()
                authored = node._operation_stage_state(context)
                assert not authored["native_read_ready"] and not authored["outliner_nodes"]
                authored = set_scene(authored, scene, f"Fresh{scene.stem}")
                node._write_state(node._mark_operation_finished(authored))
                expected_scenes[owner] = authored_scene(authored)

            with patch.object(node, "_read_scene_mode", side_effect=complete_scan):
                for index, (shot, scene) in enumerate(zip(SHOTS, scenes), 1):
                    node._write_state(switch(node._picker_state(), shot))
                    read_command(node, shot, scene, f"binary-five-read-{index}")
                    snapshot = node._picker_state()
                    assert len(expected_scenes) == index, snapshot.get("message")
                    assert rendered_media(snapshot) == expected_media
                    for owner, expected in expected_scenes.items():
                        assert authored_scene(switch(snapshot, owner)) == expected

            saved = node._picker_state()
            reopened = picker.HMBVideoPickerLibrary(name="Five Maya binary scenes reopened")
            reopened._schedule_missing_video_thumbnail_recovery = lambda: None
            reopened._sync_outputs_from_state = lambda _state: None
            install_test_state(reopened, saved)
            reopened_state = reopened._picker_state()
            assert rendered_media(reopened_state) == expected_media
            assert len({entry["scene_path"] for entry in expected_scenes.values()}) == 5
            for start in SHOTS:
                current = switch(reopened_state, start)
                for destination in SHOTS:
                    changed = switch(current, destination)
                    assert authored_scene(changed) == expected_scenes[destination]
                    assert rendered_media(changed) == expected_media

        assert all(sha256(path.read_bytes()).hexdigest() == expected for path, expected in source_hashes.items())
    print("Five mocked Maya binary scans, 20 directed shot transitions, reopen, READ reset and media preservation: PASS")


if __name__ == "__main__":
    run()
