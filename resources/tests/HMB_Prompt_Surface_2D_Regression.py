from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest


ROOT = Path(os.environ.get("HMB_TEST_LIBRARY_ROOT", Path(__file__).resolve().parents[2]))


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


prompt = load("_hmb_surface_prompt", "HMBPromptLibrary.py")
agent = load("_hmb_surface_agent", "HMBAgentLibrary.py")


def character(uid="hero", enabled=False):
    return {
        "present": True, "label": uid, "asset_source_uid": uid,
        "image_main_type": "Character", "image_sub_type": "Full Appearance",
        "owner": uid, "surface_2d": enabled,
        "color_picks": ["Red", "Green", "Blue"], "binding_video_slots": [1, 2, 3],
    }


def state_for(images):
    return prompt._normalize_state({
        "images": images,
        "videos": [{"present": True, "label": f"clip-{i}",
                    "video_main_type": "Maya Preview / Playblast", "video_sub_type": "Original Preview"}
                   for i in range(3)],
        "text": {"SCENE_CONTEXT": "Keep the approved forest.", "PRESERVED_TEXT": "[Dialogue] 안녕!"},
    })


def job(state):
    return json.loads(prompt._build_data_only_prompt_package(state).splitlines()[2])


class Surface2DTests(unittest.TestCase):
    def test_default_off_is_not_a_3d_instruction(self):
        implicit = character()
        del implicit["surface_2d"]
        original = state_for([implicit])
        explicit = state_for([character(enabled=False)])
        self.assertEqual(prompt._build_data_only_prompt_package(original), prompt._build_data_only_prompt_package(explicit))
        self.assertNotIn("2DSurface", prompt._build_user_readable_prompt_package(original))
        self.assertNotIn("surface_2d", job(original)["images"][0])

    def test_exact_scoped_prompt_and_no_other_authority_changes(self):
        off = state_for([character("hero"), character("partner")])
        on = copy.deepcopy(off)
        on["images"][0]["surface_2d"] = True
        off_job, on_job = job(off), job(on)
        record = on_job["images"][0]
        self.assertTrue(record.pop("surface_2d"))
        instruction = record.pop("surface_2d_instruction")
        for fragment in ("@image1", 'Target "hero"', "surface-conforming graphic mouth only",
                         "curved 3D facial surface", "shared scene-lighting response", "recessed oral depth",
                         "lip-sync authority", "do not freeze the mouth", "not other targets"):
            self.assertIn(fragment, instruction)
        self.assertEqual(off_job, on_job)
        visible = prompt._build_user_readable_prompt_package(on)
        self.assertNotIn(instruction, visible)
        self.assertIn("2D표현: 사용", visible)
        self.assertEqual(visible.count("2D표현: 사용"), 1)
        self.assertEqual(off["text"], on["text"])

    def test_summary_language_does_not_change_machine_instructions(self):
        state = state_for([character(enabled=True), character("partner")])
        korean_machine = prompt._build_data_only_prompt_package(state)
        korean_visible = prompt._build_user_readable_prompt_package(state)
        state["ui"]["language"] = "en"
        english_visible = prompt._build_user_readable_prompt_package(state)
        self.assertIn("2DSurface: On", english_visible)
        self.assertEqual(english_visible.count("2DSurface: On"), 1)
        self.assertEqual(korean_machine, prompt._build_data_only_prompt_package(state))
        for visible in (korean_visible, english_visible):
            for detailed in ("User-selected 2DSurface", "graphic mouth", "Custom:",
                             "Custom Type:", "Custom Role:", "Keep Out:", "TARGET GENERATOR:"):
                self.assertNotIn(detailed, visible)
        state["images"][0]["surface_2d"] = False
        self.assertNotIn("2DSurface", prompt._build_user_readable_prompt_package(state))

    def test_no_stale_instruction_after_uncheck_or_main_type_change(self):
        for main in prompt.IMAGE_MAIN_TYPE_CHOICES:
            row = character(enabled=True)
            row["image_main_type"] = main
            state = state_for([row])
            expected = main == "Character"
            self.assertEqual(state["images"][0]["surface_2d"], expected)
            self.assertEqual(bool(job(state)["images"][0].get("surface_2d_instruction")), expected)
        row = character(enabled=True)
        row["surface_2d"] = False
        self.assertNotIn("surface_2d_instruction", job(state_for([row]))["images"][0])
        for raw in ("false", "true", 1, None):
            row["surface_2d"] = raw
            self.assertFalse(state_for([row])["images"][0]["surface_2d"])

    def test_optional_subtype_and_empty_target_do_not_block(self):
        row = character(enabled=True)
        row.update(image_sub_type="", owner="")
        record = job(state_for([row]))["images"][0]
        self.assertIn("@image1, its assigned character", record["surface_2d_instruction"])
        self.assertEqual(record["target_id"], "")

    def test_roundtrip_reorder_and_five_shot_drafts(self):
        for shot in range(1, 6):
            state = state_for([character("hero", shot % 2 == 1), character("partner")])
            state["shot"]["number"] = shot
            for _ in range(20):
                state = prompt._normalize_state(json.loads(json.dumps(state)))
            source = copy.deepcopy(state)
            source[prompt.SOURCE_SYNC_REVISION_KEY] = 9
            state[prompt.UI_EDIT_REVISION_KEY] = 8
            source["images"] = list(reversed(source["images"]))
            for row in source["images"]:
                row["surface_2d"] = False
            merged = prompt._merge_prompt_revision_axes(source, state)
            rows = {row["asset_source_uid"]: row for row in merged["images"] if row.get("asset_source_uid")}
            self.assertEqual(rows["hero"]["surface_2d"], shot % 2 == 1)
            self.assertFalse(rows["partner"]["surface_2d"])
            self.assertEqual(rows["hero"]["color_picks"], ["Red", "Green", "Blue"])
            self.assertEqual(rows["hero"]["binding_video_slots"], [1, 2, 3])

    def test_manual_context_retains_checked_and_unchecked(self):
        state = state_for([character(enabled=True), character("partner")])
        snapshot = prompt._manual_video_context_snapshot(state)
        restored = prompt._normalize_manual_video_context_snapshot(json.loads(json.dumps(snapshot)))
        self.assertEqual([r["fields"]["surface_2d"] for r in restored["images"][:2]], [True, False])

    def test_asset_reconnect_and_reorder_keep_only_user_selection(self):
        def payload(order):
            return {
                "schema": "hmb-image-asset-library-binding", "mode": "image_asset", "project_uid": "surface-test",
                "ordered_images": [{"order_key": uid, "source_uid": uid, "image_name": uid} for uid in order],
                "verified_assets": [{
                    "order_key": uid, "source_uid": uid, "selection_order": index + 1,
                    "verified_asset": True, "source_kind": "project", "binding_mode": "verified_asset",
                    "asset_id": uid, "asset_library_id": f"lib-{uid}", "image_main_type": "Character",
                    "image_sub_type": "Full Appearance", "surface_2d": True,
                } for index, uid in enumerate(order)],
            }
        state = prompt._apply_image_asset_payload(prompt._default_widget_state(), payload(["hero", "partner"]), connected=True)
        self.assertFalse(state["images"][0]["surface_2d"], "Incoming asset metadata must not auto-enable this Prompt option.")
        state["images"][0]["surface_2d"] = True
        for _ in range(5):
            state = prompt._apply_image_asset_payload(state, payload(["partner", "hero"]), connected=True)
            self.assertEqual([row["surface_2d"] for row in state["images"][:2]], [False, True])
            state = prompt._apply_image_asset_payload(state, {}, connected=False)
            state = prompt._apply_image_asset_payload(state, payload(["hero", "partner"]), connected=True)
            self.assertEqual([row["surface_2d"] for row in state["images"][:2]], [True, False])

    def test_performance_roles_are_unchanged(self):
        for main, sub in prompt.VIDEO_TAXONOMY_WIRE_MAP:
            state = state_for([character()])
            state["videos"][0].update(video_main_type=main, video_sub_type=sub)
            before = job(state)["videos"]
            state["images"][0]["surface_2d"] = True
            self.assertEqual(before, job(state)["videos"])

    def test_exact_opaque_agent_transport(self):
        state = state_for([character(enabled=True)])
        visible = prompt._build_user_readable_prompt_package(state)
        machine = prompt._build_data_only_prompt_package(state)
        snapshot = {
            "schema": "hmb-prompt-paired-snapshot", "version": 1, "generation": 1,
            "visible_sha256": hashlib.sha256(visible.encode()).hexdigest(),
            "machine_sha256": hashlib.sha256(machine.encode()).hexdigest(),
            "machine_prompt": machine,
        }
        source = SimpleNamespace(_hmb_agent_prompt_snapshot=lambda _: dict(snapshot))
        self.assertEqual(agent._paired_machine_prompt(
            SimpleNamespace(_hmb_verified_prompt_source_node=source), visible), machine)


if __name__ == "__main__":
    unittest.main(verbosity=2)
