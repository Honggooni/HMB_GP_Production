"""Python/widget delete and independent edit-source identity regression.

No source files are removed and no Maya/render service is started. Use
--runtime-root to validate the installed package after the source suite.
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
from unittest.mock import patch

parser = argparse.ArgumentParser()
parser.add_argument("--runtime-root", type=Path, default=Path(__file__).resolve().parents[2])
root = parser.parse_args().runtime_root.resolve()
sys.path.insert(0, str(root))
spec = importlib.util.spec_from_file_location("edit_delete_roundtrip_picker", root / "HMBVideoPickerLibrary.py")
assert spec and spec.loader
picker = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = picker
spec.loader.exec_module(picker)
node_binary = os.environ.get("HMB_NODE_BINARY") or shutil.which("node")
assert node_binary, "Set HMB_NODE_BINARY to the Node.js executable."

JS = r"""
import fs from 'node:fs';
const text=fs.readFileSync(process.argv[1],'utf8');
const picker=await import(`data:text/javascript;base64,${Buffer.from(text).toString('base64')}`);
const req=JSON.parse(fs.readFileSync(0,'utf8'));
const container={__hmbPickerVideoDeletions:new Map(req.records||[])};
let state=req.state;
for(const source of req.sources||[]) state=picker.hmbApplyPickerToolSource(state,source.uid,source.tool,source.index??-1);
for(const removal of req.toolRemovals||[]) state=picker.hmbRemovePickerToolInput(state,removal.tool,removal.index??0);
for(const uid of req.remove||[]) state=picker.hmbBeginOptimisticPickerVideoDeletion(container,state,uid,`delete-${uid}`).state;
if(req.apply) state=picker.hmbApplyOptimisticPickerVideoDeletions(container,state);
console.log(JSON.stringify({state,records:[...container.__hmbPickerVideoDeletions]}));
"""


def widget(state, *, remove=(), records=(), apply=False, sources=(), tool_removals=()):
    result = subprocess.run(
        [node_binary, "--input-type=module", "-e", JS,
         str(root / "widgets/HMBVideoPickerLibraryWidget_v032.js")],
        input=json.dumps({"state": state, "remove": list(remove), "records": list(records), "apply": apply,
                         "sources": list(sources), "toolRemovals": list(tool_removals)}),
        capture_output=True, text=True, encoding="utf-8", timeout=30, check=True,
    )
    return json.loads(result.stdout)


shots = [f"11111111-1111-4111-8111-{i:012d}" for i in range(1, 6)]
paths = {"a": "C:/edit-delete/a.mp4", "b": "C:/edit-delete/b.mp4", "alias": "C:/edit-delete/a.mp4"}
state = picker._default_widget_state()
state.update({
    "runtime_instance_id": "edit-delete-roundtrip", "state_writer": "python", "state_revision": 10,
    "shot_publisher_instance_uuid": "33333333-3333-4333-8333-333333333333",
    "channel_uuid": "44444444-4444-4444-8444-444444444444",
    "active_picker_shot_uuid": shots[3], "shot_uuid": shots[3], "shot_number": 4, "shot_name": "Shot 4",
    "picker_shots": [picker._new_picker_workspace_row(i, workspace_uuid=uid, bound_shot_uuid=uid)
                     for i, uid in enumerate(shots, 1)],
    "shot_selections": [{"shot_uuid": uid, "number": i, "name": f"Shot {i}", "revision": 1}
                        for i, uid in enumerate(shots, 1)],
})
for index, uid in enumerate(("a", "b", "alias")):
    state = picker._append_video_asset(state, {
        "video_uid": uid, "source_uid": uid, "video_path": paths[uid], "project_video_path": paths[uid],
        "label": uid, "generation_role": "manual",
    }, picker_shot_uuid=shots[index])
state = picker._activate_picker_workspace_projection(state, shots[3])
assert state is not None
tools = state["video_tools_by_shot"][shots[3]]
tools["revision"] = 3
tools["concatenate"].update(
    inputs=[paths["a"], paths["b"], paths["a"], paths["alias"], paths["a"]],
    input_uids=["a", "b", "a", "alias", "external-a"],
    output_path="C:/custom/joined.mp4", manual_output_enabled=True,
)
tools["crop"].update(input=paths["a"], source_uid="a", output_path="C:/custom/crop.mp4", manual_output_enabled=True)
tools["crop_by_source"] = {"a": copy.deepcopy(tools["crop"])}
tools["external_sources"] = [{"source_uid": "external-a", "label": "External A",
                              "local_path": paths["a"], "browser_url": "http://localhost/external-a.mp4",
                              "width": 640, "height": 360, "duration": 2.0}]
other = state["video_tools_by_shot"][shots[4]]
other["concatenate"].update(inputs=[paths["a"], paths["alias"]], input_uids=["a", "alias"])
original = picker._parse_state(state)
ownership = {row["workspace_uuid"]: row["video_asset_uids"][:] for row in original["picker_shots"]}

# Dragging cross-Shot or independent external cards adds references only, with
# identity/path pairing preserved by both implementations and saved JSON.
empty_edit = copy.deepcopy(original)
empty_edit["video_tools_by_shot"][shots[3]]["concatenate"].update(inputs=[], input_uids=[])
dragged = widget(empty_edit, sources=[{"uid": uid, "tool": "concatenate"}
                                    for uid in ("b", "a", "external-a", "a")])["state"]
dragged = picker._parse_state(json.dumps(dragged))
assert dragged["active_picker_shot_uuid"] == shots[3]
assert dragged["video_tools_by_shot"][shots[3]]["concatenate"]["input_uids"] == ["b", "a", "external-a", "a"]
assert dragged["video_tools_by_shot"][shots[3]]["concatenate"]["inputs"] == [paths["b"], paths["a"], paths["a"], paths["a"]]
assert {row["workspace_uuid"]: row["video_asset_uids"] for row in dragged["picker_shots"]} == ownership
cropped = widget(dragged, sources=[{"uid": "external-a", "tool": "crop"}])["state"]
crop_draft = picker._parse_state(cropped)["video_tools_by_shot"][shots[3]]["crop"]
assert crop_draft["source_uid"] == "external-a"
assert crop_draft["manual_output_enabled"] is True
assert crop_draft["output_path"] == "C:/custom/crop.mp4"

# Loaded Picker cards and hidden external metadata are NOT tool inputs.
# Only an explicit per-tool drag/import can fill the two independent drafts.
independent = copy.deepcopy(original)
independent_tools = independent["video_tools_by_shot"][shots[3]]
independent_tools["concatenate"].update(inputs=[], input_uids=[])
independent_tools["crop"].update(input="", source_uid="")
empty_roundtrip = picker._parse_state(json.dumps(widget(independent)["state"]))
assert empty_roundtrip["video_tools_by_shot"][shots[3]]["concatenate"]["inputs"] == []
assert empty_roundtrip["video_tools_by_shot"][shots[3]]["crop"]["input"] == ""
concat_only = widget(empty_roundtrip, sources=[{"uid": "b", "tool": "concatenate"}])["state"]
concat_tools = picker._parse_state(concat_only)["video_tools_by_shot"][shots[3]]
assert concat_tools["concatenate"]["input_uids"] == ["b"]
assert concat_tools["crop"]["input"] == ""
single_crop = widget(concat_only, sources=[{"uid": "a", "tool": "crop"},
                                         {"uid": "external-a", "tool": "crop"}])["state"]
single_tools = picker._parse_state(single_crop)["video_tools_by_shot"][shots[3]]
assert single_tools["crop"]["source_uid"] == "external-a"
assert isinstance(single_tools["crop"]["input"], str)
assert single_tools["concatenate"] == concat_tools["concatenate"]

# A tool-card X removes only that tool's input, never the other tool, source
# catalog, selections, other destination Shot, or files.
removed_concat = picker._parse_state(widget(original, tool_removals=[{"tool": "concatenate", "index": 0}])["state"])
removed_concat_tools = removed_concat["video_tools_by_shot"][shots[3]]
assert removed_concat_tools["concatenate"]["input_uids"] == ["b", "a", "alias", "external-a"]
assert removed_concat_tools["crop"] == original["video_tools_by_shot"][shots[3]]["crop"]
removed_crop = picker._parse_state(widget(original, tool_removals=[{"tool": "crop"}])["state"])
removed_crop_tools = removed_crop["video_tools_by_shot"][shots[3]]
assert removed_crop_tools["crop"]["input"] == removed_crop_tools["crop"]["source_uid"] == ""
assert removed_crop_tools["crop"]["manual_output_enabled"] is True
assert removed_crop_tools["crop"]["output_path"] == "C:/custom/crop.mp4"
assert removed_crop_tools["concatenate"] == original["video_tools_by_shot"][shots[3]]["concatenate"]
for independent_removal in (removed_concat, removed_crop):
    assert independent_removal["videos"] == original["videos"]
    assert independent_removal["picker_shots"] == original["picker_shots"]
    assert independent_removal["video_tools_by_shot"][shots[4]] == original["video_tools_by_shot"][shots[4]]

# UI removal precedes a backend acknowledgement, including repeated source
# references in a different Shot's independent edit queue.
optimistic = widget(original, remove=("a", "b"))
shown = picker._parse_state(optimistic["state"])
assert shown["active_picker_shot_uuid"] == shots[3]
assert [item["video_uid"] for item in shown["videos"]] == ["alias"]
assert shown["video_tools_by_shot"][shots[3]]["concatenate"]["input_uids"] == ["alias", "external-a"]
assert shown["video_tools_by_shot"][shots[4]]["concatenate"]["input_uids"] == ["alias"]
assert shown["video_tools_by_shot"][shots[3]]["crop"]["source_uid"] == ""
assert shown["video_tools_by_shot"][shots[3]]["crop"]["output_path"] == "C:/custom/crop.mp4"

# Authoritative removal uses production command/state methods. Suppress only
# external graph publication; all catalog/draft/acknowledgement logic is real.
with patch.object(picker, "_request_parameter_value", return_value=False):
    node = picker.HMBVideoPickerLibrary(name="Edit Delete RoundTrip")
    node._sync_outputs_from_state = lambda *_args, **_kwargs: None
    backend_initial = copy.deepcopy(original)
    backend_initial["runtime_instance_id"] = node._hmb_runtime_instance_id
    node._write_state(backend_initial)
    for uid in ("b", "a"):
        node._handle_picker_command({"runtime_instance_id": node._hmb_runtime_instance_id,
                                    "action": "delete_video_asset", "action_id": f"delete-{uid}",
                                    "payload": {"video_uid": uid}})
    authoritative = node._picker_state()
    assert [item["video_uid"] for item in authoritative["videos"]] == ["alias"]
    assert authoritative["video_tools_by_shot"][shots[3]]["concatenate"]["input_uids"] == ["alias", "external-a"]
    stale = copy.deepcopy(backend_initial)
    for draft in stale["video_tools_by_shot"].values():
        draft["revision"] += 100
    merged = node._merge_widget_state(authoritative, stale)
    assert merged["video_tools_by_shot"][shots[3]]["concatenate"]["input_uids"] == ["alias", "external-a"]
    assert merged["video_tools_by_shot"][shots[4]]["concatenate"]["input_uids"] == ["alias"]

# Crossed old props may not resurrect the deleted UID. A fresh import with the
# same physical path has a new UID and must remain usable.
late = widget(original, records=optimistic["records"], apply=True)["state"]
assert [item["video_uid"] for item in late["videos"]] == ["alias"]
reimported = picker._append_video_asset(shown, {
    "video_uid": "a-new", "source_uid": "a-new", "video_path": paths["a"],
    "project_video_path": paths["a"], "label": "a reimported", "generation_role": "manual",
}, picker_shot_uuid=shots[0])
reimported["video_tools_by_shot"][shots[3]]["concatenate"].update(
    inputs=[paths["a"]], input_uids=["a-new"])
retained = widget(reimported, records=optimistic["records"], apply=True)["state"]
assert any(item["video_uid"] == "a-new" for item in retained["videos"])
assert retained["video_tools_by_shot"][shots[3]]["concatenate"]["input_uids"] == ["a-new"]
assert next(row for row in retained["picker_shots"] if row["workspace_uuid"] == shots[2])["video_asset_uids"] == ownership[shots[2]]
print(json.dumps({"result": "PASS", "cross_shot_delete": True, "same_path_identity": True,
                  "stale_echo": True, "reimport": True, "tool_input_independence": True,
                  "single_crop_source": True, "runtime_root": str(root)}))
