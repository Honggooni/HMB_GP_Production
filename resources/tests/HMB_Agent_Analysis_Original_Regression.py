"""Pure, provider-free Agent analysis source routing regression."""
from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import _hmb_agent_media as media


class AgentAnalysisOriginal(unittest.TestCase):
    def setUp(self):
        self.snapshot = {"schema": "hmb-agent-reference-media", "version": 1,
                         "machine_sha256": "a" * 64,
                         "images": [{"token": "@image1", "source": "C:/shot/normal.png"}],
                         "videos": []}

    def test_one_verified_original_and_ordinary_sources_are_preserved(self):
        before = copy.deepcopy(self.snapshot)
        original = {"kind": "image", "path": "C:/shot/analysis.png", "source_id": "uid-1"}
        routed = media.merge_analysis_original(self.snapshot, original)
        self.assertEqual(self.snapshot, before)
        self.assertEqual(len(routed["images"]), 2)
        self.assertEqual(routed["images"][1]["token"], "@analysis_original")
        self.assertEqual(routed["images"][1]["identity"]["source_uid"], "uid-1")
        self.assertEqual(media.merge_analysis_original(routed, original), routed)

    def test_normal_source_prevents_duplicate_original(self):
        original = {"kind": "image", "path": "C:/shot/normal.png", "source_id": "uid-1"}
        routed = media.merge_analysis_original(self.snapshot, original)
        self.assertEqual(len(routed["images"]), 1)
        self.assertEqual(routed["images"][0]["token"], "@image1")
        self.assertTrue(routed["images"][0]["_hmb_verified_analysis_original"])
        self.assertEqual(media._label(routed["images"][0], "image")["reference_usage"], "analysis_reference")

    def test_video_range_samples_only_selected_interval(self):
        original = {"kind": "video", "path": "C:/shot/analysis.mov", "source_id": "uid-2",
                    "start": 4.0, "end": 8.0}
        routed = media.merge_analysis_original(self.snapshot, original)
        self.assertEqual(len(routed["videos"]), 1)
        samples = media._sample_plan(routed["videos"], 10.0)
        self.assertEqual([row["seek"] for row in samples], [4.0, 6.0, 7.9])

    def test_audio_is_exact_one_source_and_unselected_is_noop(self):
        original = {"kind": "audio", "path": "C:/shot/dialogue.wav", "source_id": "uid-3"}
        routed = media.merge_analysis_original(self.snapshot, original)
        self.assertEqual(routed["audios"][0]["token"], "@analysis_original")
        self.assertIs(media.merge_analysis_original(self.snapshot, {}), self.snapshot)
        self.assertEqual(media.merge_analysis_original({}, original), {})

    def test_multiple_originals_keep_distinct_verified_tokens(self):
        originals = [
            {"kind": "video", "path": "C:/shot/camera.mov", "source_id": "video-1",
             "shot_reference": "@video3"},
            {"kind": "audio", "path": "C:/shot/dialogue.wav", "source_id": "audio-1",
             "shot_reference": "@analysis_original_audio_2"},
            {"kind": "image", "path": "C:/shot/pose.png", "source_id": "image-1",
             "shot_reference": "@analysis_original_image_3"},
        ]
        routed = media.merge_analysis_originals(self.snapshot, originals)
        self.assertEqual(routed["videos"][0]["token"], "@video3")
        self.assertEqual(routed["audios"][0]["token"], "@analysis_original_audio_2")
        self.assertEqual(routed["images"][1]["token"], "@analysis_original_image_3")
        for kind, key in (("video", "videos"), ("audio", "audios"), ("image", "images")):
            record = next(row for row in routed[key] if row["source"] == next(
                original["path"] for original in originals if original["kind"] == kind))
            self.assertEqual(media._token(record), record["token"])
        self.assertEqual(self.snapshot["videos"], [])

    def test_generator_reference_mapping_keeps_identity_after_filter_and_reorder(self):
        from _hmb_analysis_delivery import analysis_video_reference_bindings, route_analysis_media

        first, second = "C:/reference/a.mov", "C:/reference/b.mov"
        originals = [{"kind": "video", "path": second, "shot_reference": "@video2"}]
        routed, bindings = route_analysis_media("video", [first, second], [first, second], originals)
        self.assertEqual(routed, [second])
        self.assertEqual(analysis_video_reference_bindings(routed, originals, bindings), [
            {"shot_reference": "@video2", "provider_reference": "@video1", "usage": "analysis_reference"}])
        self.assertEqual(analysis_video_reference_bindings([], originals, bindings), [])
        self.assertEqual(analysis_video_reference_bindings(routed, originals * 2, bindings),
                         analysis_video_reference_bindings(routed, originals, bindings))
        direct = [{"kind": "video", "path": second, "shot_reference": "@analysis_original_video_2"}]
        self.assertEqual(analysis_video_reference_bindings([first, second], direct, [])[0]["provider_reference"], "@video2")


if __name__ == "__main__":
    unittest.main(verbosity=2)
