from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "hmb_prompt_registration_identity", ROOT / "HMBPromptLibrary.py"
)
prompt = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = prompt
SPEC.loader.exec_module(prompt)


def external(name: str) -> dict:
    uid = "import:" + hashlib.sha256(name.encode()).hexdigest()[:24]
    return {
        "source_uid": uid,
        "order_key": uid,
        "image_name": name,
        "source_kind": "user",
        "verified_asset": False,
        "binding_mode": "external_image",
    }


def registered(source: dict, *, name: str = "Registered A") -> dict:
    library_id = hashlib.sha256(name.encode()).hexdigest()[:24]
    uid = f"project:{library_id}"
    return {
        "source_uid": uid,
        "order_key": uid,
        "import_source_uid": source["source_uid"],
        "image_name": name,
        "source_kind": "project",
        "verified_asset": True,
        "binding_mode": "verified_asset",
        "asset_library_id": library_id,
        "asset_id": name.replace(" ", "_"),
        "asset_project_uid": "test:project",
        "path": f"C:/Test/Character/{name}.png",
        "image_main_type": "Character",
        "image_sub_type": "Full Appearance",
    }


def payload(rows: list[dict]) -> dict:
    rows = deepcopy(rows)
    for index, row in enumerate(rows, start=1):
        row["selection_order"] = index
    return {
        "schema": "hmb-image-asset-library-binding",
        "version": 2,
        "mode": "image_asset",
        "project_uid": "test:project",
        "ordered_images": rows,
        "verified_assets": [row for row in rows if row["verified_asset"]],
        "imported_images": [row for row in rows if not row["verified_asset"]],
    }


def apply(state: dict, rows: list[dict]) -> dict:
    return prompt._apply_image_asset_payload(state, payload(rows), connected=True)


def authored(rows: list[dict]) -> dict:
    state = apply(prompt._default_widget_state(), rows)
    for index, row in enumerate(state["images"]):
        row.update({
            "image_main_type": "Character",
            "image_sub_type": "Head / Face",
            "owner": f"Authored Target {index + 1}",
            "color_picks": ["Red"],
            "binding_scopes": ["Head / face only"],
            "frame_range_intent": {
                "version": 1,
                "enabled": True,
                "start_frame": 10,
                "end_frame": 35,
                "ranges": [{"start_frame": 10, "end_frame": 35}],
                "selected_index": 0,
            },
        })
    state["text"]["SCENE_CONTEXT"] = "Use @image1 with @image3."
    state["text"]["PRESERVED_TEXT"] = "Literal @image1."
    return prompt._normalize_state(state)


class RegistrationIdentityTests(unittest.TestCase):
    def setUp(self):
        self.sources = [external(name) for name in ("A", "B", "C")]
        self.state = authored(self.sources)
        self.saved = registered(self.sources[0])

    def assert_authored(self, old: dict, new: dict):
        for key in (
            "owner", "image_sub_type", "custom_source_type", "color_picks",
            "binding_scopes", "binding_custom_scopes", "binding_video_slots",
            "frame_range_intent", "frame_range_bindings", "look_custom_instruction",
        ):
            self.assertEqual(new[key], old[key], key)

    def test_add_preserves_authored_row_and_image_tokens(self):
        result = apply(self.state, [self.saved, *self.sources[1:]])
        self.assert_authored(self.state["images"][0], result["images"][0])
        self.assertEqual(result["text"], self.state["text"])
        self.assertEqual(result["images"][1:], self.state["images"][1:])
        self.assertEqual(result["images"][0]["asset_source_uid"], self.saved["source_uid"])
        self.assertTrue(result["images"][0]["asset_verified"])
        self.assertEqual(result["images"][0]["asset_id"], self.saved["asset_id"])
        self.assertFalse(result["image_asset"]["dormant_asset_rows"])
        self.assertEqual(apply(result, [self.saved, *self.sources[1:]]), result)

    def test_add_with_reorder_preserves_identity_and_remaps_tokens(self):
        result = apply(self.state, [self.sources[2], self.saved, self.sources[1]])
        self.assert_authored(self.state["images"][0], result["images"][1])
        self.assertEqual(result["text"]["SCENE_CONTEXT"], "Use @image2 with @image1.")
        self.assertEqual(result["text"]["PRESERVED_TEXT"], "Literal @image1.")

    def test_dormant_external_row_resumes_under_registered_identity(self):
        deselected = apply(self.state, self.sources[1:])
        result = apply(deselected, [self.saved, *self.sources[1:]])
        self.assert_authored(self.state["images"][0], result["images"][0])
        self.assertFalse(result["image_asset"]["dormant_asset_rows"])

    def test_no_alias_keeps_distinct_source_separate_even_with_same_name(self):
        self.saved.pop("import_source_uid")
        self.saved["image_name"] = "A"
        result = apply(self.state, [self.saved, *self.sources[1:]])
        self.assertNotEqual(result["images"][0]["owner"], "Authored Target 1")
        self.assertIn("[deselected image source #1]", result["text"]["SCENE_CONTEXT"])
        self.assertEqual(result["image_asset"]["dormant_asset_rows"][0]["owner"], "Authored Target 1")

    def test_unverified_alias_cannot_take_over_an_import_row(self):
        replacement = external("Different source")
        replacement["import_source_uid"] = self.sources[0]["source_uid"]
        result = apply(self.state, [replacement, *self.sources[1:]])
        self.assertNotEqual(result["images"][0]["owner"], "Authored Target 1")

    def test_inconsistent_verified_identity_cannot_handover(self):
        for key, value in (("asset_library_id", "other"), ("source_uid", "project:other")):
            with self.subTest(key=key):
                saved = deepcopy(self.saved)
                saved[key] = value
                result = apply(self.state, [saved, *self.sources[1:]])
                self.assertNotEqual(result["images"][0]["owner"], "Authored Target 1")

    def test_ambiguous_registration_aliases_cannot_claim_one_row(self):
        other = registered(self.sources[0], name="Another registration")
        result = apply(self.state, [self.saved, other, *self.sources[1:]])
        self.assertTrue(all(row["owner"] != "Authored Target 1" for row in result["images"][:2]))

    def test_still_selected_external_source_keeps_its_own_row(self):
        result = apply(self.state, [self.saved, *self.sources])
        self.assertNotEqual(result["images"][0]["owner"], "Authored Target 1")
        self.assertEqual(result["images"][1]["owner"], "Authored Target 1")

    def test_existing_durable_row_wins_over_old_import_cache(self):
        result = apply(self.state, [self.saved, *self.sources[1:]])
        old_import = deepcopy(self.state["images"][0])
        old_import["owner"] = "Stale import target"
        result["image_asset"]["dormant_asset_rows"] = [old_import]
        result["images"][0]["owner"] = "Durable target"
        refreshed = apply(result, [self.saved, *self.sources[1:]])
        self.assertEqual(refreshed["images"][0]["owner"], "Durable target")

    def test_authored_custom_type_survives_handover(self):
        self.state["images"][0].update({
            "image_main_type": "Custom / Context", "image_sub_type": "Custom",
            "custom_source_type": "Authored role",
        })
        self.saved.update({
            "image_main_type": "Custom / Context", "image_sub_type": "Context",
            "custom_source_type": "Catalog role",
        })
        before = prompt._normalize_state(self.state)
        result = apply(before, [self.saved, *self.sources[1:]])
        self.assert_authored(before["images"][0], result["images"][0])
        self.assertEqual(result["images"][0]["asset_image_sub_type_candidate"], "Context")

    def test_handover_uses_existing_registered_metadata_update_rules(self):
        already_addressed = deepcopy(self.state)
        already_addressed["images"][0].update({
            "asset_source_uid": self.saved["source_uid"],
            "asset_library_id": self.saved["asset_library_id"],
            "asset_source_kind": "project",
            "asset_verified": True,
        })
        rows = [self.saved, *self.sources[1:]]
        expected = apply(already_addressed, rows)
        result = apply(self.state, rows)
        self.assertEqual(result["images"], expected["images"])
        self.assertEqual(result["text"], expected["text"])

    def test_shot_payload_keeps_registration_handover(self):
        rows = [self.saved, *self.sources[1:]]
        uids = [row["source_uid"] for row in rows]
        snapshot = {
            "channel_uuid": "channel", "generation": 2,
            "ordered_assets": [{"source_uid": row["source_uid"], "metadata": row} for row in rows],
            "media_by_source_uid": {uid: f"media-{index}" for index, uid in enumerate(uids)},
        }
        shot = {"shot_uuid": "shot", "selected_source_uids": uids}
        routed, media = prompt._shot_image_payload_from_snapshot(snapshot, shot)
        result = prompt._apply_image_asset_payload(self.state, routed, connected=True)
        self.assert_authored(self.state["images"][0], result["images"][0])
        self.assertEqual(result["text"], self.state["text"])
        self.assertEqual(media, ["media-0", "media-1", "media-2"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
