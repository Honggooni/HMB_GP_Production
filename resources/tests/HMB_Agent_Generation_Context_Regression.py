"""Offline settings/media boundary and final Beauty regression; no provider calls."""
from __future__ import annotations

import copy
import importlib.util
import itertools
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def load(name):
    spec = importlib.util.spec_from_file_location("_generation_context_" + name, ROOT / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


prompt = load("HMBPromptLibrary")
generator = load("HMBSeedanceGeneration")
finish = load("HMBFinishLookLibrary")
import _hmb_shot_routing as routing


def subscription(kind="seedance", shot="shot-1", channel="channel-1", enabled=True):
    return {
        "schema": "hmb-shot-channel-subscription", "version": 1,
        "participant_kind": kind, "enabled": enabled,
        "channel_uuid": channel, "shot_uuid": shot,
        "shot_number": 1, "shot_name": "Shot 1",
    }


def make_generator(name="Render A", **overrides):
    values = {
        "model_id": generator.MODEL_NAME_SEEDANCE_2_5,
        generator.TASK_PARAMETER: generator.TASK_REFERENCE_TO_VIDEO,
        "duration": 8, "ratio": "16:9", "resolution": "1080p",
    }
    values.update(overrides)
    node = SimpleNamespace(name=name, values=values)
    node.get_parameter_value = lambda key: values.get(key)
    node._hmb_shot_channel_subscription = lambda: subscription()
    node._hmb_agent_generation_settings = lambda: generator.HMBSeedanceGeneration._hmb_agent_generation_settings(node)
    node.set_parameter_value = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("read mutated controls"))
    return node


# The defaults and per-model normalization reflect the effective Shot request,
# including task-specific values retained from Only mode.
cases = [
    ({}, (8, "explicit", "16:9", "1080p")),
    ({"duration": -1}, (5, "explicit", "16:9", "1080p")),
    ({generator.TASK_PARAMETER: generator.TASK_VIDEO_EDITING, "duration": 8}, (5, "explicit", "adaptive", "1080p")),
    ({generator.TASK_PARAMETER: generator.TASK_VIDEO_EXTENSION, "duration": -1}, (5, "explicit", "16:9", "1080p")),
    ({"model_id": generator.MODEL_NAME_SEEDANCE_2_0, "duration": -1}, (None, "provider_smart", "16:9", "1080p")),
    ({"model_id": generator.MODEL_NAME_SEEDANCE_2_0_FAST, "resolution": "1080p"}, (8, "explicit", "16:9", "720p")),
    ({"duration": True, "ratio": "invalid", "resolution": "invalid"}, (5, "explicit", "adaptive", "720p")),
]
for overrides, expected in cases:
    node = make_generator(**overrides)
    before = copy.deepcopy(node.values)
    result = node._hmb_agent_generation_settings()
    assert tuple(result[key] for key in ("duration_seconds", "duration_mode", "aspect_ratio", "resolution")) == expected
    assert result["task"] == generator.TASK_REFERENCE_TO_VIDEO
    assert node.values == before
only = make_generator()
only._hmb_shot_channel_subscription = lambda: subscription(enabled=False)
assert only._hmb_agent_generation_settings() == {}
assert make_generator(model_id="unknown")._hmb_agent_generation_settings() == {}

# Compare the read-only observer against the real existing UI synchronizer for
# model/task migrations and hydrated values; no engine graph is involved.
normalization_count = 0
for model, task, duration, ratio, resolution in itertools.product(
    generator.MODEL_RESOLUTIONS,
    generator.TASK_STORAGE_CHOICES,
    (-1, 4, 8, 16, 30, 0, True, None),
    ("adaptive", "16:9", "invalid"),
    ("4k", "1080p", "720p", "invalid"),
):
    node = make_generator(model_id=model, duration=duration, ratio=ratio, resolution=resolution,
                          **{generator.TASK_PARAMETER: task})
    observed = node._hmb_agent_generation_settings()
    native = make_generator(model_id=model, duration=duration, ratio=ratio, resolution=resolution,
                            **{generator.TASK_PARAMETER: task})
    native._hmb_retired_model_migration_pending = False
    native._hmb_model_migration_active = False
    native.get_parameter_by_name = lambda key: SimpleNamespace(ui_options={})
    native.set_parameter_value = lambda key, value, **kwargs: native.values.__setitem__(key, value)
    native._synchronize_model_output_contract = lambda model_id: None
    generator.HMBSeedanceGeneration._synchronize_model_resolution(native)
    effective_duration = native.values["duration"]
    if effective_duration not in generator.MODEL_DURATION_CHOICES[model]:
        effective_duration = 5
    assert observed["duration_seconds"] == (effective_duration if effective_duration > 0 else None)
    assert observed["resolution"] == native.values["resolution"]
    assert observed["aspect_ratio"] == native.values["ratio"]
    normalization_count += 1


state = prompt._default_widget_state()
state["shot"].update(channel_uuid="channel-1", shot_uuid="shot-1", number=1, name="Shot 1")
state["images"][0].update(present=True, label="Approved hero", image_main_type="Character", image_sub_type="Full Appearance", owner="hero")
state["videos"][0].update(present=True, label="Preview", video_main_type="Maya Preview / Playblast", video_sub_type="Original Preview")
state["picker"]["frame_metadata"] = [{
    "video_slot": "@video1", "fps": 24, "start_frame": 101, "end_frame": 292,
    "frame_count": 192, "duration_seconds": 8, "width": 1920, "height": 1080,
}]
state["images"][0]["frame_range_intent"] = {
    "version": 1, "enabled": True, "start_frame": 101, "end_frame": 292,
    "ranges": [{"start": 101, "end": 140}, {"start": 200, "end": 240}], "selected_index": 0,
}
state = prompt._normalize_state(state)


def current_pair(**kwargs):
    assert kwargs == {"refresh_sources": False}
    return (copy.deepcopy(state), prompt._build_prompt_package(state), prompt._build_data_only_prompt_package(state), "fixture")


source = SimpleNamespace(name="Prompt", _hmb_sync_lock=threading.RLock())
source._compile_current_prompt_pair = current_pair
source._hmb_current_shot_images = ["C:/selected/hero.png"]
source._hmb_current_shot_videos = ["C:/selected/preview.mp4"]
machine = current_pair(refresh_sources=False)[2]

render_a = make_generator()
render_b = make_generator("Render B", duration=12, ratio="9:16")
other_shot = make_generator("Other Shot", duration=20)
other_shot._hmb_shot_channel_subscription = lambda: subscription(shot="shot-2")
other_channel = make_generator("Other Channel", duration=24)
other_channel._hmb_shot_channel_subscription = lambda: subscription(channel="channel-2")
deleted = make_generator("Deleted", duration=30)
deleted._hmb_node_deleted = True
unavailable = make_generator("Unavailable")
unavailable._hmb_agent_generation_settings = lambda: (_ for _ in ()).throw(RuntimeError("unavailable"))

get_context = lambda expected=machine: prompt.HMBPromptLibrary._hmb_agent_generation_context(source, expected)
with patch.object(routing, "_same_flow_nodes", return_value=("flow-1", [render_a, other_shot, other_channel, deleted, unavailable])):
    first = get_context()
    assert len(first["sources"]) == 1
    assert first["common"]["duration_seconds"] == 8
    assert first["conflicting_fields"] == []
    render_a.values["duration"] = 10
    refreshed = get_context()
    assert refreshed["common"]["duration_seconds"] == 10
    assert refreshed["settings_sha256"] != first["settings_sha256"]
    assert get_context("stale") == {}
    render_a.values["duration"] = 8
with patch.object(routing, "_same_flow_nodes", return_value=("flow-1", [render_b, render_a])):
    multiple = get_context()
    assert multiple["common"]["resolution"] == "1080p"
    assert set(multiple["conflicting_fields"]) == {"duration_seconds", "aspect_ratio"}
    assert "duration_seconds" not in multiple["common"]
    assert [row["generator"] for row in multiple["sources"]] == ["Render A", "Render B"]

# A compatible publisher is discovered by its callable typed settings
# capability. Its participant kind and arbitrary model/task labels are not a
# provider allowlist. Read-only observation retains registered identity even
# when optional publisher metadata attempts to supply a different name.
generic_values = {
    "model_id": "studio-custom-motion-v4", "task": "storyboard-motion",
    "duration_seconds": 6.25, "duration_mode": "explicit",
    "aspect_ratio": "2:1", "resolution": "2048x1024",
    "generator": "Forged publisher identity", "private_note": "not context",
}
generic_reads = []
generic = SimpleNamespace(name="Generic publisher", values=copy.deepcopy(generic_values))
generic._hmb_shot_channel_subscription = lambda: subscription(kind="prompt")
generic._hmb_agent_generation_settings = lambda: (generic_reads.append("settings"), copy.deepcopy(generic.values))[1]
generic.set_parameter_value = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("generic read mutated controls"))
no_getter = SimpleNamespace(name="No settings capability")
no_getter._hmb_shot_channel_subscription = lambda: subscription(kind="agent")
no_getter.get_parameter_value = lambda *args: (_ for _ in ()).throw(AssertionError("invented settings from controls"))
wrong_shot = SimpleNamespace(name="Unrelated generic publisher")
wrong_shot._hmb_shot_channel_subscription = lambda: subscription(kind="prompt", shot="shot-2")
wrong_shot_reads = []
wrong_shot._hmb_agent_generation_settings = lambda: (wrong_shot_reads.append("settings"), copy.deepcopy(generic_values))[1]
prompt_before = copy.deepcopy(state)
values_before = copy.deepcopy(generic.values)
with patch.object(routing, "_same_flow_nodes", return_value=("flow-1", [generic, no_getter, wrong_shot])):
    generic_context = get_context()
    assert len(generic_context["sources"]) == 1 and generic_reads == ["settings"]
    assert wrong_shot_reads == []
    assert generic_context["sources"][0]["generator"] == generic.name
    assert generic_context["common"]["model_id"] == "studio-custom-motion-v4"
    assert generic_context["common"]["task"] == "storyboard-motion"
    assert generic_context["common"]["duration_seconds"] == 6.25
    assert "private_note" not in generic_context["sources"][0]
    assert generic_context["settings_sha256"] == prompt._canonical_sha256({"sources": generic_context["sources"]})
    assert generic.values == values_before and state == prompt_before
    generic.values.update(duration_seconds=None, duration_mode="provider_smart", aspect_ratio="adaptive")
    unresolved = get_context()
    assert unresolved["common"]["duration_seconds"] is None
    assert unresolved["common"]["aspect_ratio"] == "adaptive"
    assert unresolved["settings_sha256"] != generic_context["settings_sha256"]
generic.values = copy.deepcopy(generic_values)

# Malformed capabilities are isolated; they cannot contribute partial or
# contradictory output values to otherwise valid publisher observations.
invalid_values = [
    {"duration_seconds": True}, {"duration_seconds": float("nan")},
    {"duration_seconds": 10 ** 400},
    {"duration_seconds": 0}, {"duration_seconds": -1},
    {"duration_mode": "provider_smart"}, {"duration_mode": "unknown"},
    {"model_id": None}, {"task": ""}, {"resolution": []},
]
for invalid in invalid_values:
    malformed = SimpleNamespace(name="Malformed publisher")
    malformed._hmb_shot_channel_subscription = lambda: subscription(kind="prompt")
    malformed._hmb_agent_generation_settings = lambda invalid=invalid: {**generic_values, **invalid}
    with patch.object(routing, "_same_flow_nodes", return_value=("flow-1", [malformed, generic])):
        assert [row["generator"] for row in get_context()["sources"]] == [generic.name]
missing = SimpleNamespace(name="Partial publisher")
missing._hmb_shot_channel_subscription = lambda: subscription(kind="prompt")
missing._hmb_agent_generation_settings = lambda: {"model_id": "studio-custom-motion-v4"}
with patch.object(routing, "_same_flow_nodes", return_value=("flow-1", [missing])):
    assert get_context() == {}

# A concurrent Shot switch, deletion, object replacement with the same name,
# or source prompt edit during discovery invalidates that observation.
switching = SimpleNamespace(name="Switching publisher", selection=subscription(kind="prompt"))
switching._hmb_shot_channel_subscription = lambda: switching.selection
def switching_settings():
    switching.selection = subscription(kind="prompt", shot="shot-2")
    return copy.deepcopy(generic_values)
switching._hmb_agent_generation_settings = switching_settings
with patch.object(routing, "_same_flow_nodes", return_value=("flow-1", [switching])):
    assert get_context() == {}
removed = SimpleNamespace(name="Removed publisher")
removed._hmb_shot_channel_subscription = lambda: subscription(kind="prompt")
def removed_settings():
    removed._hmb_node_deleted = True
    return copy.deepcopy(generic_values)
removed._hmb_agent_generation_settings = removed_settings
with patch.object(routing, "_same_flow_nodes", return_value=("flow-1", [removed])):
    assert get_context() == {}
replacement = SimpleNamespace(name=generic.name)
with patch.object(routing, "_same_flow_nodes", side_effect=[("flow-1", [generic]), ("flow-1", [replacement])]):
    assert get_context() == {}
with patch.object(routing, "_same_flow_nodes", side_effect=[("flow-1", [generic]), ("flow-2", [generic])]):
    assert get_context() == {}
original_generic_getter = generic._hmb_agent_generation_settings
def edited_source_settings():
    state["text"]["EMOTION_INTENT"] = "Changed during settings discovery."
    return copy.deepcopy(generic.values)
generic._hmb_agent_generation_settings = edited_source_settings
try:
    with patch.object(routing, "_same_flow_nodes", return_value=("flow-1", [generic])):
        assert get_context() == {}
finally:
    generic._hmb_agent_generation_settings = original_generic_getter
    state["text"]["EMOTION_INTENT"] = ""
with patch.object(routing, "_same_flow_nodes", side_effect=RuntimeError("host unavailable")):
    assert get_context() == {}

# Media references retain exact generator order, role/Target and disjoint
# Range addresses. Paths supplied as prose/labels do not become media inputs.
get_media = lambda expected=machine: prompt.HMBPromptLibrary._hmb_agent_reference_media(source, expected)
media = get_media()
assert media["images"][0]["source"] == "C:/selected/hero.png"
assert media["images"][0]["token"] == "@image1"
assert media["images"][0]["target_id"] == "hero"
assert media["videos"][0]["source"] == "C:/selected/preview.mp4"
assert media["videos"][0]["video_sub_type"] == "Original Preview"
assert media["videos"][0]["frame_metadata"]["start_frame"] == 101
ranges = media["images"][0]["frame_ranges"]
assert ranges and ranges[0]["enabled"] is True
assert ranges[0]["segments"] == [{"start_frame": 101, "end_frame": 140}, {"start_frame": 200, "end_frame": 240}]
assert get_media("stale") == {}
before_visible = current_pair(refresh_sources=False)[1]
state["text"]["EMOTION_INTENT"] = "Keep the authored smile."
assert get_media(machine) == {}  # exact machine generation, not a loose role match
state["text"]["EMOTION_INTENT"] = ""
source._hmb_current_shot_images = []
assert get_media()["images"] == []
source._hmb_current_shot_images = ["C:/selected/hero.png"]

# User-authored grading values survive the expanded identity guard. Disabled
# Beauty continues to add no block and leaves base text byte-for-byte intact.
beauty = finish.default_finish_look_state()
base = "User approved asymmetric hero, roll camera left.\n{{SIGN}}"
assert generator.HMBSeedanceGeneration._compose_finish_look_prompt(base, "") == base
beauty["beauty"].update(enabled=True, brightness=1.25, saturation=0, soft_focus=0.3)
compiled = finish.compile_finish_look_prompt(beauty)
combined = generator.HMBSeedanceGeneration._compose_finish_look_prompt(base, compiled)
assert base in combined and compiled in combined
for phrase in ("feature placement", "proportions", "silhouette", "material boundaries", "markings", "asymmetries"):
    assert phrase in combined and phrase in compiled
assert finish._beauty_brightness_clause(1.25) in compiled
assert "monochrome character-surface color response" in compiled
assert "camera movement" in compiled and "camera motion" in combined
assert "soft-focus" in compiled
print(f"PASS: {normalization_count} actual-normalizer comparisons + 7 specified cases; neutral typed publishers/read-only/exact registered identity, fresh/same-Shot settings, conflict isolation, exact media/Range binding, user Beauty controls")
