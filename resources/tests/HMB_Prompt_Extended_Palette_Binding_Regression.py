"""Current catalog markers must survive Maya/Blender Picker to Prompt handoff."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import sys


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "hmb_prompt_extended_palette_binding_regression", ROOT / "HMBPromptLibrary.py"
)
assert SPEC is not None and SPEC.loader is not None
prompt = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = prompt
SPEC.loader.exec_module(prompt)
AGENT_SPEC = importlib.util.spec_from_file_location(
    "hmb_prompt_extended_palette_agent_regression", ROOT / "HMBAgentLibrary.py"
)
assert AGENT_SPEC is not None and AGENT_SPEC.loader is not None
agent = importlib.util.module_from_spec(AGENT_SPEC)
sys.modules[AGENT_SPEC.name] = agent
AGENT_SPEC.loader.exec_module(agent)
catalog = json.loads((ROOT / "resources/picker/HMB_Marker_Catalog.json").read_text(encoding="utf-8"))
actor = [item["name"] for item in catalog["character"]]
objects = [item["name"] for item in catalog["background"]]
colors = actor + objects
assert "Cyan" in actor and "Lavender" in objects


def fixture(engine: str) -> tuple[dict, dict]:
    state = prompt._default_widget_state()
    state["images"] = []
    for index, color in enumerate(colors, 1):
        image = prompt._default_image_item(index)
        image.update({
            "present": True,
            "label": f"{color} asset",
            "asset_id": f"asset-{index}",
            "asset_source_uid": f"source-{index}",
            "owner": f"target-{index}",
            "image_main_type": "Character" if color in actor else "Background Prop",
            "image_sub_type": "Full Appearance" if color in actor else "Independent Scene Prop",
        })
        state["images"].append(image)

    rows = []
    metadata = []
    for slot, role in enumerate(("depth", "motion_guide", "mask", "original"), 1):
        uid = f"palette-{role}"
        row = {
            "video_uid": uid, "source_uid": uid, "order_key": uid,
            "selection_order": slot, "video_slot": slot, "selected": True,
            "video_path": f"C:/palette-fixture/{engine}/{role}.mp4",
            "generation_role": role, "bundle_run_id": "palette-bundle",
        }
        if role == "mask":
            row.update({
                "media_kind": f"{engine}_color_assignment_mask",
                "video_role": f"{engine}_color_assignment_mask",
            })
        elif role == "depth":
            row.update({
                "media_kind": "blender_depth_render" if engine == "blender" else "maya_depth_playblast",
                "video_role": f"{engine}_depth_companion",
                "depth_profile": prompt.BLENDER_DEPTH_PROFILE if engine == "blender" else prompt.PICKER_DEPTH_PROFILE,
                "source_video_uid": "palette-mask", "source_video_slot": 3,
                "companion_of_video_slot": 3,
            })
        elif role == "motion_guide":
            row.update({
                "media_kind": f"{engine}_motion_guide",
                "video_role": f"{engine}_motion_guide_companion",
                "motion_guide_profile": prompt.BLENDER_MOTION_GUIDE_PROFILE if engine == "blender" else prompt.PICKER_MOTION_GUIDE_PROFILE,
                "source_video_uid": "palette-mask", "source_video_slot": 3,
                "companion_of_video_slot": 3,
            })
        else:
            row.update({
                "media_kind": "blender_original_render" if engine == "blender" else "maya_original_playblast",
                "video_role": "blender_original_render" if engine == "blender" else "maya_original_playblast",
            })
        rows.append(row)
        metadata.append({
            "video_uid": uid, "source_uid": uid, "order_key": uid,
            "selection_order": slot, "video_slot": slot,
            "fps": 24, "timebase": "24/1", "start_frame": 101,
            "end_frame": 124, "frame_count": 24, "duration_seconds": 1,
            "width": 1280, "height": 720, "valid": True, "conflict": False,
            "available_color_picks": colors if role == "mask" else [],
        })
    return state, {
        "schema": "hmb-prompt-library-picker-binding", "schema_version": 5,
        "marker_catalog_version": catalog["version"], "mode": engine,
        "scene_engine": engine, "media_ready": True,
        "run_id": "palette-run", "selection_id": "palette-selection",
        "selected_video_count": len(rows), "active_slot_count": len(rows),
        "videos": rows, "frame_metadata": metadata,
        "markers": [{
            "asset_id": f"asset-{index}", "subject_root": f"target-{index}",
            "color": color, "video_uid": "palette-mask", "video_slot": 3,
            "picker_order": index,
        } for index, color in enumerate(colors, 1)],
    }


for engine in ("maya", "blender"):
    state, payload = fixture(engine)
    applied = prompt._apply_picker_payload(state, payload, connected=True)
    assert applied["image_taxonomy"]["actor_color_pick_choices"] == actor
    assert applied["image_taxonomy"]["object_color_pick_choices"] == objects
    assert [image["color_picks"] for image in applied["images"]] == [[color] for color in colors]
    assert all(image["binding_video_slots"] == [3] for image in applied["images"])
    assert [marker["color"] for marker in applied["picker"]["markers"]] == colors
    assert applied["videos"][0]["picker_companion_validated"] is True
    assert applied["videos"][1]["picker_companion_validated"] is True
    assert applied["videos"][0]["picker_companion_source_slot"] == 3
    assert applied["videos"][1]["picker_companion_source_slot"] == 3

    # The UI language and a save/reload must not rename canonical marker values
    # or move them onto generated Depth/Motion companion slots.
    machine_outputs = []
    for language in ("ko", "en"):
        restored = copy.deepcopy(applied)
        restored["ui"]["language"] = language
        restored = prompt._normalize_state(json.loads(json.dumps(restored)))
        visible = prompt._build_user_readable_prompt_package(restored)
        machine = prompt._build_data_only_prompt_package(restored)
        lines = machine.splitlines()
        job = json.loads(lines[lines.index(prompt.PUBLIC_JOB_CONTRACT_HEADER) + 1])
        assert len(job["images"]) == len(colors)
        assert [item["bindings"][0]["marker_color"] for item in job["images"]] == colors
        assert all(item["bindings"][0]["video"] == "@video3" for item in job["images"])
        assert [item["video"] for item in job["videos"]] == ["@video1", "@video2", "@video3", "@video4"]
        for color in colors:
            assert any(
                "Video: @video3" in line.split(" / ")
                and f"Color: {color}" in line.split(" / ")
                for line in visible.splitlines()
            )
        # Use a real Prompt instance and its private paired snapshot, as the
        # Agent does after workflow hydration; no provider call is needed.
        node = prompt.HMBPromptLibrary(name=f"palette-{engine}-{language}")
        node.set_parameter_value(
            prompt.WIDGET_PARAMETER_NAME, json.dumps(restored), initial_setup=True
        )
        transported = agent._paired_machine_prompt(
            SimpleNamespace(_hmb_verified_prompt_source_node=node), visible
        )
        assert transported == machine
        machine_outputs.append(machine)
    assert machine_outputs[0] == machine_outputs[1]

print(f"HMB Prompt extended palette binding regression: PASS ({len(colors)} markers, Maya/Blender, Korean/English save/reload, Agent paired snapshot)")
