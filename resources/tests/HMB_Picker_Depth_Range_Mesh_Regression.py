"""Three ranges and mesh authoring stay in the existing Picker transaction."""
import ast
import copy
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("picker_depth_mesh_test", ROOT / "HMBVideoPickerLibrary.py")
picker = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = picker
spec.loader.exec_module(picker)
runner_source = (ROOT / "resources/maya/HMB_Maya_Background_Preview.py").read_text(encoding="utf-8")
tree = ast.parse(runner_source)
namespace = {}
for node in tree.body:
    if isinstance(node, ast.FunctionDef) and node.name == "_depth_distance_far":
        exec(compile(ast.Module(body=[node], type_ignores=[]), "depth", "exec"), namespace)
distance = namespace["_depth_distance_far"]
for near_far, shot_far in ((10., 100.), (25., 25.), (40., 30.), (1., 10000.)):
    values = [distance(near_far, shot_far, mode) for mode in ("close", "middle", "far")]
    assert values[0] == near_far
    assert values[2] == max(near_far, shot_far)
    assert values[1] == (values[0] + values[2]) / 2
assert picker._parse_state({})["depth_settings"] == {"range": "close", "expanded_roots": []}
root = {"name": "Room", "full_path": "|Room", "maya_uuid": "room", "node_kind": "asset_root"}
child = {"name": "Glass", "full_path": "|Room|Glass", "maya_uuid": "glass", "parent_path": "|Room", "node_kind": "mesh"}
root["depth_meshes"] = [child]
state = picker._parse_state({"outliner_nodes": [root], "depth_settings": {"range": "far", "expanded_roots": ["|Room"]},
    "slot_visibility": [{"video_slot": 1, "hidden_paths": ["|Room|Glass"]}],
    "slot_assignments": [{"video_slot": 1, "bindings": [{"group_name": "Glass", "full_dag_path": "|Room|Glass", "maya_uuid": "glass", "color": "Red", "enabled": True}]}]})
assert picker._parse_state(json.dumps(state))["depth_settings"] == state["depth_settings"]
assert picker._picker_hidden_mesh_identities(state) == {"|Room|Glass": "glass"}
new_root = copy.deepcopy(root)
new_root["depth_meshes"][0].update(full_path="|Room|Renamed", name="Renamed")
updated = picker._reconcile_picker_mesh_authoring(state, [new_root])
assert updated["slot_visibility"][0]["hidden_paths"] == ["|Room|Renamed"]
assert updated["slot_assignments"][0]["bindings"][0]["full_dag_path"] == "|Room|Renamed"
selection = picker._outliner_selection_after_read([new_root], updated["slot_assignments"], 1, child["full_path"], "glass")
assert selection["path"] == "|Room|Renamed" and selection["color"] == "Red"
new_root["depth_meshes"][0]["maya_uuid"] = "replacement"
updated = picker._reconcile_picker_mesh_authoring(state, [new_root])
assert updated["slot_visibility"][0]["hidden_paths"] == []
assert updated["slot_assignments"][0]["bindings"] == []
assert state["slot_visibility"][0]["hidden_paths"] == ["|Room|Glass"], "Reconciliation must not mutate its input"
state.update(depth_enabled=True, native_read_ready=True)
digests = []
for mode in ("close", "middle", "far"):
    state["depth_settings"]["range"] = mode
    digests.append(picker._operation_input_digest("run_video", "", state))
assert len(set(digests)) == 3
state["depth_settings"]["expanded_roots"] = []
assert picker._operation_input_digest("run_video", "", state) == digests[-1]
assert "depth_settings" in picker._MAYA_OPERATION_AUTHORING_FIELDS
assert 'job["_render_scope_shapes"] = allowed' in runner_source
assert "hidden_mesh_identities" in runner_source
print("Picker three Depth ranges and child mesh state regression: PASS")
