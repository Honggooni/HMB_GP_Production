from __future__ import annotations

from copy import deepcopy
import importlib.util
import inspect
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "HMBVideoPickerLibrary.py"
SPEC = importlib.util.spec_from_file_location(
    "hmb_video_picker_maya_shot_authoring_regression",
    MODULE_PATH,
)
assert SPEC is not None and SPEC.loader is not None
picker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = picker
SPEC.loader.exec_module(picker)

read_source = inspect.getsource(picker.HMBVideoPickerLibrary._read_scene_mode)
assert "_outliner_selection_after_read(" in read_source
assert '"selected_outliner_path": outliner_selection["path"]' in read_source


outliner = [
    {
        "name": "Actor_MESH",
        "full_path": "|Actor_GRP|Actor_MESH",
        "parent_path": "|Actor_GRP",
        "maya_uuid": "actor-mesh-uuid",
    },
    {
        "name": "Actor_GRP",
        "full_path": "|Actor_GRP",
        "parent_path": "",
        "maya_uuid": "actor-root-uuid",
    },
]

# A new Maya READ must leave a concrete target selected, otherwise the widget
# disables every Color Pick even though the Outliner was loaded successfully.
selection = picker._outliner_selection_after_read(outliner, [], 1)
assert selection == {
    "path": "|Actor_GRP",
    "name": "Actor_GRP",
    "uuid": "actor-root-uuid",
    "color": "",
}

# A re-read follows stable Maya UUID even when a DAG path changes, and restores
# only the color belonging to the slot currently being authored.
renamed_outliner = [
    {
        "name": "Hero_GRP",
        "full_path": "|Hero_GRP",
        "parent_path": "",
        "maya_uuid": "actor-root-uuid",
    },
]
assignments = [
    {
        "video_slot": 1,
        "bindings": [{
            "full_dag_path": "|Old_Actor_GRP",
            "maya_uuid": "actor-root-uuid",
            "color": "Red",
        }],
    },
    {
        "video_slot": 2,
        "bindings": [{
            "full_dag_path": "|Old_Actor_GRP",
            "maya_uuid": "actor-root-uuid",
            "color": "Green",
        }],
    },
]
selection = picker._outliner_selection_after_read(
    renamed_outliner,
    assignments,
    2,
    "|Old_Actor_GRP",
    "actor-root-uuid",
)
assert selection == {
    "path": "|Hero_GRP",
    "name": "Hero_GRP",
    "uuid": "actor-root-uuid",
    "color": "Green",
}


# A generated/imported asset is owned by the Shot UUID captured at operation
# start. It cannot leak into the active or adjacent Shot.
state = picker._default_widget_state()
shot_1 = deepcopy(state["picker_shots"][0])
shot_1.update({
    "bound_shot_uuid": "10000000-0000-4000-8000-000000000001",
    "name": "Shot 1",
})
shot_2 = deepcopy(shot_1)
shot_2.update({
    "workspace_uuid": "00000000-0000-4000-8000-000000000002",
    "bound_shot_uuid": "10000000-0000-4000-8000-000000000002",
    "number": 2,
    "name": "Shot 2",
    "video_asset_uids": [],
    "selected_video_uids": [],
    "preview_video_uid": "",
})
state["picker_shots"] = [shot_1, shot_2]
state["active_picker_shot_uuid"] = shot_1["workspace_uuid"]
state = picker._append_video_asset(
    state,
    {
        "video_uid": "shot-2-playblast",
        "source_uid": "shot-2-playblast",
        "video_path": "C:/renders/shot-2-playblast.mp4",
        "label": "Shot 2 Playblast",
        "generation_role": "mask",
    },
    picker_shot_uuid=shot_2["workspace_uuid"],
)
rows = {row["workspace_uuid"]: row for row in state["picker_shots"]}
asset = next(item for item in state["videos"] if item["video_uid"] == "shot-2-playblast")
assert asset["picker_shot_uuid"] == shot_2["workspace_uuid"]
assert "shot-2-playblast" not in rows[shot_1["workspace_uuid"]]["video_asset_uids"]
assert rows[shot_2["workspace_uuid"]]["video_asset_uids"] == ["shot-2-playblast"]
assert rows[shot_2["workspace_uuid"]]["selected_video_uids"] == ["shot-2-playblast"]


# Selecting another Maya scene resets scene-only authoring data but retains the
# complete Picker catalog, Shot ownership, selection, and captured active Shot.
node = picker.HMBVideoPickerLibrary(name="Maya Shot Authoring Contract")
with tempfile.TemporaryDirectory() as temp_dir:
    scene_path = Path(temp_dir) / "another_scene.ma"
    scene_path.write_text("// Maya ASCII placeholder", encoding="utf-8")
    original_find_mayabatch = picker._find_mayabatch
    original_maya_version = picker._maya_display_version
    try:
        picker._find_mayabatch = lambda: Path("C:/Program Files/Autodesk/Maya2027/bin/mayabatch.exe")
        picker._maya_display_version = lambda _path: "2027"
        changed_scene_state = node._build_native_scene_selection_state(
            str(scene_path),
            state,
        )
    finally:
        picker._find_mayabatch = original_find_mayabatch
        picker._maya_display_version = original_maya_version

assert changed_scene_state["status"] == "SCANNING_SCENE"
assert changed_scene_state["active_picker_shot_uuid"] == shot_1["workspace_uuid"]
assert [item["video_uid"] for item in changed_scene_state["videos"]] == ["shot-2-playblast"]
changed_rows = {row["workspace_uuid"]: row for row in changed_scene_state["picker_shots"]}
assert changed_rows[shot_2["workspace_uuid"]]["video_asset_uids"] == ["shot-2-playblast"]
assert changed_scene_state["outliner_nodes"] == []
assert changed_scene_state["slot_assignments"] == [{"video_slot": 1, "bindings": []}]

print("HMB VideoPicker Maya Shot authoring regression: PASS")
