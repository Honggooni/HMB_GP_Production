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


# The complete Maya authoring surface is scoped by Picker Shot. Switching to a
# fresh Shot resets READ/Outliner/Color Pick state while retaining every video
# in the Shot where it was generated; returning restores Shot 1 authoring.
shot_state = picker._default_widget_state()
shot_1 = deepcopy(shot_state["picker_shots"][0])
shot_1["bound_shot_uuid"] = "10000000-0000-4000-8000-000000000001"
shot_2 = deepcopy(shot_1)
shot_2.update({
    "workspace_uuid": "00000000-0000-4000-8000-000000000002",
    "bound_shot_uuid": "10000000-0000-4000-8000-000000000002",
    "number": 2,
    "name": "Shot 2",
    "video_asset_uids": [],
    "selected_video_uids": [],
    "preview_video_uid": "",
    "authoring_context": picker._empty_picker_authoring_context(),
})
shot_state.update({
    "picker_shots": [shot_1, shot_2],
    "active_picker_shot_uuid": shot_1["workspace_uuid"],
    "scene_stage": "READ_DONE",
    "scene_draft_path": "C:/maya/shot_1.ma",
    "scene_request_path": "C:/maya/shot_1.ma",
    "scene_path": "C:/maya/shot_1.ma",
    "native_read_ready": True,
    "native_metadata": {"scene_path": "C:/maya/shot_1.ma"},
    "selected_outliner_path": "|Shot1_GRP",
    "selected_outliner_name": "Shot1_GRP",
    "selected_outliner_uuid": "shot-1-root",
    "selected_color": "Green",
    "outliner_nodes": [{
        "name": "Shot1_GRP",
        "full_path": "|Shot1_GRP",
        "maya_uuid": "shot-1-root",
    }],
    "slot_assignments": [{"video_slot": 1, "bindings": [{
        "group_name": "Shot1_GRP",
        "full_dag_path": "|Shot1_GRP",
        "maya_uuid": "shot-1-root",
        "color": "Green",
    }]}],
})
shot_state = picker._parse_state(shot_state)
on_shot_2 = picker._activate_picker_workspace_projection(
    shot_state,
    shot_2["workspace_uuid"],
)
assert on_shot_2 is not None
assert on_shot_2["native_read_ready"] is False
assert on_shot_2["scene_path"] == ""
assert on_shot_2["outliner_nodes"] == []
assert on_shot_2["slot_assignments"] == [{"video_slot": 1, "bindings": []}]

on_shot_2.update({
    "scene_stage": "READ_DONE",
    "scene_draft_path": "C:/maya/shot_2.ma",
    "scene_request_path": "C:/maya/shot_2.ma",
    "scene_path": "C:/maya/shot_2.ma",
    "native_read_ready": True,
    "selected_outliner_path": "|Shot2_GRP",
    "selected_outliner_name": "Shot2_GRP",
    "selected_outliner_uuid": "shot-2-root",
    "selected_color": "Red",
    "outliner_nodes": [{
        "name": "Shot2_GRP",
        "full_path": "|Shot2_GRP",
        "maya_uuid": "shot-2-root",
    }],
    "slot_assignments": [{"video_slot": 1, "bindings": [{
        "group_name": "Shot2_GRP",
        "full_dag_path": "|Shot2_GRP",
        "maya_uuid": "shot-2-root",
        "color": "Red",
    }]}],
})
on_shot_2 = picker._parse_state(on_shot_2)
restored_shot_1 = picker._activate_picker_workspace_projection(
    on_shot_2,
    shot_1["workspace_uuid"],
)
assert restored_shot_1 is not None
assert restored_shot_1["native_read_ready"] is True
assert restored_shot_1["scene_path"] == "C:/maya/shot_1.ma"
assert restored_shot_1["selected_outliner_uuid"] == "shot-1-root"
assert restored_shot_1["selected_color"] == "Green"
assert restored_shot_1["slot_assignments"][0]["bindings"][0]["color"] == "Green"


# A delayed browser echo from before READ cannot erase the backend's loaded
# Outliner or newly selected Color Pick.
authoritative = deepcopy(restored_shot_1)
authoritative["state_revision"] = 20
stale = deepcopy(restored_shot_1)
stale.update({
    "state_revision": 19,
    "native_read_ready": False,
    "selected_outliner_path": "",
    "selected_outliner_name": "",
    "selected_outliner_uuid": "",
    "selected_color": "",
    "outliner_nodes": [],
    "slot_assignments": [{"video_slot": 1, "bindings": []}],
})
merged = picker.HMBVideoPickerLibrary._merge_widget_state(authoritative, stale)
assert merged["native_read_ready"] is True
assert merged["selected_outliner_uuid"] == "shot-1-root"
assert merged["selected_color"] == "Green"
assert merged["slot_assignments"][0]["bindings"][0]["color"] == "Green"

print("HMB VideoPicker Maya Shot authoring regression: PASS")
