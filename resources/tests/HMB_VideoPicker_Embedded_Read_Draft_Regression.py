"""Embedded READ preserves its Shot draft across equal-global-revision echoes.

Exercises production setter hooks and command scheduling without Maya, media
execution, network, Desktop, or real user state. SDK dispatch is covered by the
separate exact browser-publication replay in the incident report.
"""
from __future__ import annotations
import copy
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import HMBVideoPickerLibrary as picker

SHOTS = [f"11111111-1111-4111-8111-{number:012d}" for number in range(1, 6)]
BOUND = [f"22222222-2222-4222-8222-{number:012d}" for number in range(1, 6)]


def preserved(state):
    return {
        "videos": [(row["video_uid"], row["picker_shot_uuid"], row["video_path"]) for row in state["videos"]],
        "shots": [(row["workspace_uuid"], row["bound_shot_uuid"], row["video_asset_uids"]) for row in state["picker_shots"]],
    }


def publish(node, value):
    parameter = picker._get_parameter_obj(node, picker.WIDGET_STATE_PARAMETER)
    accepted = node.before_value_set(parameter, copy.deepcopy(value))
    node._store_initial_parameter_value(picker.WIDGET_STATE_PARAMETER, accepted)
    node.after_value_set(parameter, accepted)


def main():
    with tempfile.TemporaryDirectory(prefix="hmb-read-draft-") as temporary, \
            patch.object(picker, "_request_parameter_value", return_value=False):
        base = Path(temporary)
        scene = base / "Shot2.mb"
        scene.write_bytes(b"Isolated metadata-only scene identity")
        for order in ("equal_global_command_first", "state_first", "new_global_command_first", "stale_global"):
            node = picker.HMBVideoPickerLibrary(name="Embedded READ " + order)
            node._schedule_missing_video_thumbnail_recovery = lambda: None
            node._sync_outputs_from_state = lambda *_args, **_kwargs: None
            node._reconcile_shared_shot_routing = lambda: None
            scheduled = []
            node._schedule_action_worker = lambda action, action_id, target: scheduled.append((action, action_id, target))
            state = picker._default_widget_state()
            state["picker_shots"] = [picker._new_picker_workspace_row(number, workspace_uuid=shot, bound_shot_uuid=bound)
                                     for number, (shot, bound) in enumerate(zip(SHOTS, BOUND), 1)]
            state["active_picker_shot_uuid"] = SHOTS[0]
            for number, shot in enumerate(SHOTS, 1):
                video = base / f"old-{number}.mp4"
                video.write_bytes(f"preserved-{number}".encode())
                state = picker._append_video_asset(state, {"video_uid": f"old-{number}",
                    "source_uid": f"old-{number}", "video_path": str(video), "generation_role": "mask"},
                    picker_shot_uuid=shot, defer_thumbnail=True)
            state["state_revision"] = 50
            node._write_state(state)
            authoritative = node._picker_state()
            prior = preserved(authoritative)
            prior_row = next(row for row in authoritative["picker_shots"] if row["workspace_uuid"] == SHOTS[0])
            incoming = copy.deepcopy(authoritative)
            incoming["state_writer"] = "widget"
            incoming["active_picker_shot_uuid"] = SHOTS[1]
            incoming["scene_request_path"] = str(scene)
            incoming["scene_draft_path"] = str(scene)
            selected_row = next(row for row in incoming["picker_shots"] if row["workspace_uuid"] == SHOTS[0])
            selected_row["revision"] = prior_row["revision"] + 1
            # A selection change on the previous Shot is exactly what a real
            # navigation publication carries beside a READ for the next Shot.
            selected_row["selected_video_uids"] = []
            if order == "new_global_command_first":
                incoming["state_revision"] += 1
            elif order == "stale_global":
                incoming["state_revision"] -= 1
            command = {"schema": "hmb-picker-command", "version": 1,
                       "runtime_instance_id": node._hmb_runtime_instance_id,
                       "action": "read_scene", "action_id": "draft-" + order,
                       "payload": {"picker_shot_uuid": SHOTS[1], "scene_path": str(scene)}}
            if order == "state_first":
                publish(node, incoming)
            publish(node, {**incoming, picker.WIDGET_STATE_EMBEDDED_COMMAND_FIELD: command})
            assert len(scheduled) == 1 and scheduled[0][:2] == ("read_scene", command["action_id"])
            retained = node._picker_state()
            retained_row = next(row for row in retained["picker_shots"] if row["workspace_uuid"] == SHOTS[0])
            assert preserved(retained) == prior, "READ draft changed media membership or bindings"
            if order == "stale_global":
                assert retained_row["revision"] == prior_row["revision"], "Stale UI must not replace newer authority"
            else:
                assert retained_row["revision"] == selected_row["revision"], (order, retained_row, selected_row)
                assert retained_row["selected_video_uids"] == [], "READ discarded the pending deselection"
                assert retained["active_picker_shot_uuid"] == SHOTS[1], "READ revived the previous Shot"
                assert retained["state_writer"] == "python", "Draft must be committed before worker dispatch"
                # A later stale echo cannot undo the accepted row or its media.
                publish(node, authoritative)
                after_echo = node._picker_state()
                after_row = next(row for row in after_echo["picker_shots"] if row["workspace_uuid"] == SHOTS[0])
                assert after_row["revision"] == selected_row["revision"]
                assert after_row["selected_video_uids"] == []
                assert preserved(after_echo) == prior
            print(order + ": PASS")
    print("Embedded READ draft ordering, selection, binding/media preservation and stale guards: PASS")


if __name__ == "__main__":
    main()
