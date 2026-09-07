"""Cross-language shared Maya input / Shot-owned media regression.

Exercises the real widget helpers and Python normalizer, not a Maya render.
Set HMB_NODE_BINARY if node is not on PATH. --runtime-root can point at the
actual installed package to run the same contract against installation bytes.
"""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


parser = argparse.ArgumentParser()
parser.add_argument("--runtime-root", type=Path, default=Path(__file__).resolve().parents[2])
args = parser.parse_args()
root = args.runtime_root.resolve()
sys.path.insert(0, str(root))
spec = importlib.util.spec_from_file_location("shared_maya_roundtrip_picker", root / "HMBVideoPickerLibrary.py")
assert spec and spec.loader
picker = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = picker
spec.loader.exec_module(picker)
node = os.environ.get("HMB_NODE_BINARY") or shutil.which("node")
assert node, "Set HMB_NODE_BINARY to the Node.js executable."

JS_SWITCH = r"""
const fs = await import('node:fs');
const source = fs.readFileSync(process.argv[1], 'utf8');
const widget = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
const request = JSON.parse(fs.readFileSync(0, 'utf8'));
let state = widget.hmbSwitchLocalPickerShot(request.state, request.workspace);
const command = widget.hmbPickerCommandPayload(state, {});
console.log(JSON.stringify({state, command}));
"""


def switch_through_widget(state: dict, workspace: str) -> dict:
    completed = subprocess.run(
        [node, "--input-type=module", "-e", JS_SWITCH,
         str(root / "widgets/HMBVideoPickerLibraryWidget_v032.js")],
        input=json.dumps({"state": state, "workspace": workspace}),
        text=True, encoding="utf-8", capture_output=True, timeout=30, check=True,
    )
    response = json.loads(completed.stdout)
    assert response["command"]["picker_shot_uuid"] == workspace
    restored = picker._parse_state(response["state"])
    assert restored["active_picker_shot_uuid"] == workspace
    return restored


workspaces = [f"11111111-1111-4111-8111-{i:012d}" for i in range(1, 6)]
state = picker._default_widget_state()
state["picker_shots"] = [
    picker._new_picker_workspace_row(
        i, workspace_uuid=workspace,
        bound_shot_uuid=f"22222222-2222-4222-8222-{i:012d}",
    )
    for i, workspace in enumerate(workspaces, 1)
]
state["active_picker_shot_uuid"] = workspaces[0]
state.update({
    "shot_publisher_instance_uuid": "33333333-3333-4333-8333-333333333333",
    "channel_uuid": "44444444-4444-4444-8444-444444444444",
    "shot_uuid": "22222222-2222-4222-8222-000000000001",
    "shot_number": 1, "shot_name": "Shot 1",
    "shot_selections": [
        {"shot_uuid": f"22222222-2222-4222-8222-{i:012d}",
         "number": i, "name": f"Shot {i}", "revision": 1}
        for i in range(1, 6)
    ],
})


def current_maya_fields(value: dict) -> dict:
    return {
        key: copy.deepcopy(value.get(key))
        for key in (
            "scene_path", "scene_draft_path", "scene_request_path",
            "native_read_ready", "native_metadata", "selected_camera",
            "outliner_nodes", "selected_outliner_uuid", "selected_color",
            "slot_assignments", "slot_visibility",
        )
    }


# Five files replace one staging input in sequence. Results stay with the
# destination captured after selecting the Shot, regardless of old Shot data.
for index, workspace in enumerate(workspaces, 1):
    scene_path = f"C:/shared-maya-contract/scene-{index}.ma"
    state.update({
        "scene_path": scene_path, "scene_draft_path": scene_path,
        "scene_request_path": scene_path, "scene_stage": "READ_DONE",
        "native_read_ready": True,
        "native_metadata": {"scene_path": scene_path, "start_frame": 101, "end_frame": 148},
        "camera": f"camera{index}", "selected_camera": f"camera{index}",
        "cameras": [{"full_path": f"camera{index}", "name": f"camera{index}"}],
        "outliner_nodes": [{"name": f"Actor{index}", "full_path": f"|Actor{index}", "maya_uuid": f"actor-{index}"}],
        "selected_outliner_path": f"|Actor{index}",
        "selected_outliner_name": f"Actor{index}",
        "selected_outliner_uuid": f"actor-{index}", "selected_color": "Red",
        "slot_assignments": [{"video_slot": 1, "bindings": [{"full_dag_path": f"|Actor{index}", "maya_uuid": f"actor-{index}", "color": "Red"}]}],
        "slot_visibility": [{"video_slot": 1, "hidden_paths": []}],
    })
    state = picker._parse_state(state)
    expected = current_maya_fields(state)
    state = switch_through_widget(state, workspace)
    assert current_maya_fields(state) == expected, f"Shot {index} replaced shared Maya input"
    state = picker._append_video_asset(state, {
        "video_uid": f"result-{index}", "source_uid": f"result-{index}",
        "video_path": f"C:/shared-maya-contract/result-{index}.mp4",
        "label": f"Shot {index} result", "generation_role": "mask",
    }, picker_shot_uuid=workspace)

expected = current_maya_fields(state)
owned = {row["workspace_uuid"]: list(row["video_asset_uids"]) for row in state["picker_shots"]}
for index, workspace in enumerate(workspaces, 1):
    assert owned[workspace] == [f"result-{index}"]

# Every directed navigation pair keeps the last loaded (fifth) Maya file and
# all previous media, including repeated Python -> JS -> Python serialization.
transitions = 0
for source in workspaces:
    state = switch_through_widget(state, source)
    for target in workspaces:
        if source == target:
            continue
        changed = switch_through_widget(state, target)
        assert current_maya_fields(changed) == expected
        assert {row["workspace_uuid"]: list(row["video_asset_uids"]) for row in changed["picker_shots"]} == owned
        assert not any("authoring_context" in row for row in changed["picker_shots"])
        transitions += 1

restored = picker._parse_state(json.dumps(state))
assert current_maya_fields(restored) == expected
assert restored["scene_path"].endswith("scene-5.ma")

# Snapshot completion and navigation must never copy a previous Shot's scalar
# preview into a blank Shot or synthesize a duplicate history record. Exercise
# both existing histories (different frames) and blank destinations through JS.
state = switch_through_widget(state, workspaces[4])
for number in (1, 3):
    state = picker._append_snapshot_history_record(state, {
        "snapshot_uid": f"snapshot-{number}", "video_uid": f"result-{number}",
        "path": f"C:/shared-maya-contract/snapshot-{number}.png",
        "frame": float(100 + number * 25), "render_video_slot": 1,
        "created_at_ms": number * 1000,
    }, picker_shot_uuid=workspaces[number - 1])
    assert state["active_picker_shot_uuid"] == workspaces[4]
    assert state["active_snapshot_uid"] == ""
    assert state["snapshot_path"] == ""

expected_snapshot_pointers = {
    workspace: f"snapshot-{number}" if number in (1, 3) else ""
    for number, workspace in enumerate(workspaces, 1)
}


def snapshot_semantics(value: dict) -> list[tuple]:
    return sorted((record["snapshot_uid"], record["video_uid"], record["path"], record["frame"])
                  for record in value["snapshots"])


expected_snapshots = snapshot_semantics(state)
assert len(expected_snapshots) == 2
snapshot_transitions = 0
for source in workspaces:
    source_state = switch_through_widget(state, source)
    for target in workspaces:
        if source == target:
            continue
        changed = switch_through_widget(source_state, target)
        assert snapshot_semantics(changed) == expected_snapshots
        assert {row["workspace_uuid"]: row["active_snapshot_uid"] for row in changed["picker_shots"]} == expected_snapshot_pointers
        assert changed["active_snapshot_uid"] == expected_snapshot_pointers[target]
        assert current_maya_fields(changed) == expected
        if not expected_snapshot_pointers[target]:
            assert changed["snapshot_path"] == ""
            assert changed["snapshot_active"] is False
        reloaded = picker._parse_state(json.dumps(changed))
        assert snapshot_semantics(reloaded) == expected_snapshots
        assert reloaded["active_snapshot_uid"] == expected_snapshot_pointers[target]
        snapshot_transitions += 1

print(json.dumps({"result": "PASS", "maya_replacements": 5, "shot_transitions": transitions,
                  "shot_owned_results": 5, "snapshot_transitions": snapshot_transitions,
                  "runtime_root": str(root)}))
