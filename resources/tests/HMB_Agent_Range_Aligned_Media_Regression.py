"""Offline Range/PTS/role coverage and same-run diagnostics regression.

Uses real local PNG/video decoders and installed Griptape artifacts. No paid
provider, upload, Maya, engine graph or persisted workflow is contacted.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import _hmb_agent_media as media
from griptape.artifacts import ListArtifact
from griptape.drivers.prompt.griptape_cloud_prompt_driver import GriptapeCloudPromptDriver
from griptape_nodes.drivers.cloud_models import VISION_MODEL_CHOICES
from PIL import Image


def load(name):
    spec = importlib.util.spec_from_file_location("_range_aligned_" + name, ROOT / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


agent_module = load("HMBAgentLibrary")
prompt_module = load("HMBPromptLibrary")
MACHINE = "same-shot-machine"
MACHINE_HASH = hashlib.sha256(MACHINE.encode()).hexdigest()


def driver_agent():
    return SimpleNamespace(tasks=[SimpleNamespace(prompt_driver=GriptapeCloudPromptDriver(
        model=VISION_MODEL_CHOICES[0], api_key="offline-never-sent"))])


def metadata(uid="uid-original", bundle="capture-1", fps=10):
    return {"video_uid": uid, "source_uid": uid, "bundle_run_id": bundle,
            "fps": fps, "start_frame": 101, "end_frame": 150, "frame_count": 50,
            "valid": True, "conflict": False}


def video(token, subtype, source, **overrides):
    result = {"token": token, "video": token, "source": str(source),
              "source_type": "Maya Preview / Playblast", "video_sub_type": subtype,
              "control_role": "Primary Unified Shot Control", "target_id": "authored-hero",
              "frame_metadata": metadata("uid-" + token[1:]),
              "frame_ranges": [{"enabled": True, "segments": [{"start_frame": 131, "end_frame": 139}]}],
              "timing": {"authored_timing_cues": [{"frame": 121, "cue_type": "impact"}]}}
    result.update(overrides)
    return result


def snapshot(images=None, videos=None):
    return {"schema": "hmb-agent-reference-media", "version": 1,
            "machine_sha256": MACHINE_HASH, "images": images or [], "videos": videos or []}


def labels(result):
    if not isinstance(result, ListArtifact):
        return []
    return [json.loads(item.value.split(": ", 1)[1]) for item in result.value
            if item.__class__.__name__ == "TextArtifact" and item.value.startswith("HMB REFERENCE PIXELS")]


class AlignedMediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.root = Path(cls.directory.name)
        cls.ffmpeg, cls.probe = media._binaries()
        cls.hero = cls.root / "hero.png"
        Image.new("RGB", (96, 96), "blue").save(cls.hero)
        cls.sources = []
        if cls.ffmpeg and cls.probe:
            for name, color, offset in [("original", "red", 0), ("mask", "green", 5), ("depth", "white", 0)]:
                path = cls.root / (name + ".mp4")
                args = [str(cls.ffmpeg), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                        "-i", f"color=c={color}:s=96x96:r=10:d=5", "-an"]
                if offset:
                    args += ["-vf", f"setpts=PTS+{offset}/TB"]
                args += ["-c:v", "mpeg4", "-q:v", "2", "-fps_mode", "passthrough", str(path)]
                subprocess.run(args, check=True, timeout=15, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                cls.sources.append(path)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def call(self, value, **kwargs):
        reports = []
        with patch.object(socket.socket, "connect", side_effect=AssertionError("network forbidden")):
            result = media.augment_prompt("Keep {{SIGN}} and all authored roles.", value, driver_agent(),
                                          report_sink=reports.append, **kwargs)
        self.assertEqual(len(reports), 1)
        return result, reports[0]

    def test_event_and_disjoint_range_priority_does_not_mutate_authority(self):
        records = [video("@video1", "Original Preview", self.hero)]
        before = copy.deepcopy(records)
        plan = media._sample_plan(records, 5)
        self.assertEqual([(v["seek"], v["reason"], v["requested_source_frame"]) for v in plan[:4]],
                         [(2, "authored_event", 121), (3.4, "range_midpoint", 135),
                          (3, "range_start", 131), (3.8, "range_end", 139)])
        self.assertEqual(records, before)
        records[0]["timing"]["authored_timing_cues"] += [{"frame": 122}, {"frame": 123}]
        self.assertEqual([v["requested_source_frame"] for v in media._sample_plan(records, 5)[:3]], [121, 135, 122])
        records[0]["timing"] = {}
        records[0]["frame_ranges"][0]["enabled"] = False
        self.assertEqual(media._sample_plan(records, 5)[0]["reason"], "fallback_start")
        records[0]["frame_metadata"]["conflict"] = True
        records[0]["timing"] = {"authored_timing_cues": [{"frame": 121}]}
        self.assertEqual(media._sample_plan(records, 5)[0]["seek"], 0)

    def test_real_three_pass_nonzero_pts_and_character_role_reservation(self):
        if not self.sources:
            self.skipTest("local FFmpeg/FFprobe unavailable")
        value = snapshot(images=[{"token": f"@image{i}", "source": str(self.hero),
                                   "image_main_type": "Character", "target_id": "authored-hero"} for i in range(1, 7)],
                         videos=[video(f"@video{i}", role, path) for i, (role, path) in enumerate(
                             zip(("Original Preview", "Mask", "Depth"), self.sources), 1)])
        before = copy.deepcopy(value)
        result, report = self.call(value)
        actual = labels(result)
        first = [v for v in actual if v.get("kind") == "video"][:3]
        self.assertEqual([v["observation_role"] for v in first], ["original", "mask", "depth"])
        self.assertEqual([v["requested_source_frame"] for v in first], [121] * 3)
        self.assertEqual([v["normalized_pts_seconds"] for v in first], [2] * 3)
        self.assertAlmostEqual(first[1]["decoded_pts_seconds"], 7)
        self.assertEqual(report["groups"][0]["alignment_status"], "pts_aligned")
        self.assertEqual(len({v["sample_group_id"] for v in first}), 1)
        self.assertIn("character", report["budget_summary"]["role_counts"])
        self.assertEqual(value, before)
        self.assertTrue(all(v["control_role"] == "Primary Unified Shot Control" for v in first))
        self.assertNotIn(str(self.root), json.dumps(report))
        self.assertNotIn("authored-hero", json.dumps(report))

    def test_missing_clock_or_capture_identity_never_invents_pairing(self):
        fake = self.hero.read_bytes()
        for changed in ("bundle", "clock"):
            records = [video("@video1", "Original Preview", self.hero), video("@video2", "Mask", self.hero)]
            if changed == "bundle":
                records[1]["frame_metadata"]["bundle_run_id"] = "capture-other-shot"
            else:
                records[1]["frame_metadata"]["fps"] = 25
            with patch.object(media, "_decode", return_value=(fake, 96, 96, 2)), \
                 patch.object(media, "_video_info", return_value={"duration": 5, "start_pts": 0}):
                _result, report = self.call(snapshot(videos=records))
            self.assertEqual(report["groups"], [])

    def test_unknown_pts_is_explicit_and_alignment_retry_is_bounded(self):
        fake = self.hero.read_bytes()
        records = [video("@video1", "Original Preview", self.hero), video("@video2", "Mask", self.hero)]
        with patch.object(media, "_decode", return_value=(fake, 96, 96, None)), \
             patch.object(media, "_video_info", return_value={"duration": 5, "start_pts": 0}):
            _result, report = self.call(snapshot(videos=records))
        self.assertTrue(all(v["alignment_status"] == "pts_unknown" for v in report["groups"]))
        media._PROBE_CACHE.clear()
        def shifted(source, identity, seek, *args):
            return fake, 96, 96, seek + (.2 if identity[0].endswith("mask.mp4") else 0)
        records[1]["source"] = str(self.root / "mask.mp4")
        (self.root / "mask.mp4").touch() if not self.sources else None
        with patch.object(media, "_source", side_effect=lambda value, kind: (Path(value), (str(value),))), \
             patch.object(media, "_decode", side_effect=shifted), \
             patch.object(media, "_video_info", return_value={"duration": 5, "start_pts": 0}):
            result, report = self.call(snapshot(videos=records))
        self.assertEqual(report["groups"][0]["alignment_status"], "pts_aligned")
        self.assertTrue(labels(result)[1]["alignment_retry"])
        self.assertAlmostEqual(labels(result)[1]["decode_seek_seconds"], 1.8)

    def test_large_images_keep_byte_capacity_for_each_control_role(self):
        noisy = self.root / "noisy.png"
        Image.effect_noise((768, 768), 100).convert("RGB").save(noisy)
        value = snapshot(images=[{"token": f"@image{i}", "source": str(noisy), "image_main_type": "Character"}
                                 for i in range(1, 6)], videos=[video(f"@video{i}", role, self.hero)
                                     for i, role in enumerate(("Original Preview", "Mask", "Depth"), 1)])
        fake = self.hero.read_bytes()
        original_decode = media._decode
        def decode(source, identity, seek, *args):
            return (fake, 96, 96, seek) if seek is not None else original_decode(source, identity, seek, *args)
        with patch.object(media, "_decode", side_effect=decode), \
             patch.object(media, "_video_info", return_value={"duration": 5, "start_pts": 0}):
            _result, report = self.call(value)
        self.assertTrue({"character", "original", "mask", "depth"}.issubset(report["budget_summary"]["role_counts"]))
        self.assertLessEqual(report["budget_summary"]["encoded_bytes_prepared"], media.MAX_ENCODED_BYTES)
        self.assertLessEqual(report["budget_summary"]["attachments_delivered"], media.MAX_ATTACHMENTS)

    def test_remote_nonvision_deadline_cap_and_diagnostic_redaction(self):
        remote = snapshot(images=[{"token": "@image1", "source": "https://private.invalid/image?signature=SECRET",
                                   "identity": {"video_uid": "https://private.invalid/SECRET"}}])
        result, report = self.call(remote)
        self.assertIsInstance(result, str)
        self.assertEqual(report["skips"][0]["reason"], "nonlocal")
        self.assertNotIn("SECRET", json.dumps(report))
        with patch.object(media, "driver_accepts_images", return_value=False), \
             patch.object(media, "_source", side_effect=AssertionError("no decoder for nonvision")):
            _result, report = self.call(remote)
        self.assertEqual(report["skips"][0]["reason"], "no_vision_driver")
        with patch.object(media, "PREPARATION_SECONDS", 0):
            _result, report = self.call(remote)
        self.assertEqual(report["skips"][0]["reason"], "deadline")
        _result, report = self.call(snapshot(images=[{"token": f"@image{i}", "source": str(self.hero)}
                                                    for i in range(1, 10)]))
        self.assertTrue(any(v["reason"] == "image_cap" for v in report["skips"]))

    def test_cancelled_preparation_has_no_delivered_pixel_claim(self):
        _result, report = self.call(snapshot(images=[{"token": "@image1", "source": str(self.hero)}]), is_live=lambda: False)
        self.assertEqual(report["status"], "cancelled")
        self.assertEqual(report["coverage"], [])
        self.assertEqual(report["budget_summary"]["attachments_delivered"], 0)

    def test_missing_first_source_does_not_spend_later_available_role_reservation(self):
        fake = self.hero.read_bytes()
        value = snapshot(images=[{"token": f"@image{i}", "source": str(self.hero), "image_main_type": "Character"}
                                 for i in range(1, 7)], videos=[
            video("@video1", "Original Preview", "https://unavailable.invalid/video"),
            video("@video2", "Original Preview", self.hero), video("@video3", "Mask", self.hero),
            video("@video4", "Depth", self.hero)])
        value["videos"][0]["frame_metadata"]["bundle_run_id"] = "unavailable-bundle"
        with patch.object(media, "_decode", return_value=(fake, 96, 96, 2)), \
             patch.object(media, "_video_info", return_value={"duration": 5, "start_pts": 0}):
            _result, report = self.call(value)
        self.assertTrue({"original", "mask", "depth"}.issubset(report["budget_summary"]["role_counts"]))
        self.assertIn("@video1", report["unobserved_media_tokens"])

    def test_attachment_cap_admits_whole_paired_observation_groups(self):
        fake = self.hero.read_bytes()
        value = snapshot(images=[{"token": "@image1", "source": str(self.hero), "image_main_type": "Character"}],
                         videos=[video(f"@video{i}", role, self.hero) for i, role in enumerate(
                             ("Original Preview", "Mask", "Depth"), 1)])
        with patch.object(media, "_decode", side_effect=lambda _source, _identity, seek, *_args: (fake, 96, 96, seek)), \
             patch.object(media, "_video_info", return_value={"duration": 5, "start_pts": 0}):
            _result, report = self.call(value)
        self.assertEqual(report["budget_summary"]["attachments_delivered"], 7)
        self.assertEqual(len(report["groups"]), 2)
        self.assertTrue(all(v["alignment_status"] == "pts_aligned" for v in report["groups"]))
        self.assertEqual({v["media_token"] for v in report["skips"] if v["reason"] == "attachment_cap"},
                         {"@video1", "@video2", "@video3"})


class AuthorityAndRunTests(unittest.TestCase):
    def test_cancellation_after_pixels_prepare_does_not_claim_native_delivery(self):
        cls = agent_module.HMBAgentLibrary
        node = object.__new__(cls)
        node._hmb_rules_active = True
        node._hmb_node_deleted = False
        node._hmb_lifecycle_generation = 1
        node._hmb_runtime_prompt = MACHINE
        node._hmb_execution_result = {"status": "running", "run_id": "cancelled-run"}
        node.parameter_values = {}
        node.parameter_output_values = {}
        cancelled = [False]
        original = media.augment_prompt
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "source.png"
            Image.new("RGB", (16, 16), "blue").save(path)
            value = snapshot(images=[{"token": "@image1", "source": str(path), "image_main_type": "Character"}])
            setattr(node, agent_module._VERIFIED_PROMPT_SOURCE_ATTRIBUTE,
                    SimpleNamespace(_hmb_agent_reference_media=lambda _machine: value))
            def prepare_then_cancel(*args, **kwargs):
                prepared = original(*args, **kwargs)
                self.assertIsInstance(prepared, ListArtifact)
                cancelled[0] = True
                return prepared
            with patch.object(cls, "is_cancellation_requested", property(lambda _self: cancelled[0])), \
                 patch.object(media, "augment_prompt", side_effect=prepare_then_cancel), \
                 patch.object(agent_module._BaseAgent, "_process", side_effect=AssertionError("cancelled native call")) as native:
                target = driver_agent()
                self.assertIs(node._process(target, "authored context"), target)
                self.assertEqual(native.call_count, 0)
                report = node._hmb_agent_reference_observation_snapshot()
                self.assertEqual(report["native_input_status"], "not_submitted")
                self.assertEqual(report["coverage"], [])
                self.assertEqual(report["budget_summary"]["attachments_delivered"], 0)
                self.assertEqual(report["skips"][0]["reason"], "cancelled_before_native_submission")

    def test_real_agent_seam_exposes_only_exact_machine_observation(self):
        cls = agent_module.HMBAgentLibrary
        node = object.__new__(cls)
        node._hmb_rules_active = True
        node._hmb_node_deleted = False
        node._hmb_lifecycle_generation = 1
        node._hmb_runtime_prompt = MACHINE
        node._hmb_execution_result = {"status": "running", "run_id": "native-run-one"}
        node.parameter_values = {}
        node.parameter_output_values = {}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "native-source.png"
            Image.new("RGB", (16, 16), "blue").save(path)
            record = snapshot(images=[{"token": "@image1", "source": str(path), "image_main_type": "Character"}])
            source = SimpleNamespace(_hmb_agent_reference_media=lambda _machine: copy.deepcopy(record))
            setattr(node, agent_module._VERIFIED_PROMPT_SOURCE_ATTRIBUTE, source)
            with patch.object(cls, "is_cancellation_requested", False), \
                 patch.object(agent_module._BaseAgent, "_process", side_effect=lambda _agent, value: value) as native, \
                 patch.object(socket.socket, "connect", side_effect=AssertionError("network forbidden")):
                result = node._process(driver_agent(), "unchanged authored context")
                self.assertIsInstance(result, ListArtifact)
                self.assertEqual(native.call_count, 1)
                report = node._hmb_agent_reference_observation_snapshot()
                self.assertEqual(report["run_id"], "native-run-one")
                self.assertEqual(report["machine_sha256"], MACHINE_HASH)
                self.assertEqual(report["coverage"][0]["media_token"], "@image1")
                record["machine_sha256"] = "0" * 64
                result = node._process(driver_agent(), "unchanged authored context")
                self.assertIsInstance(result, str)
                self.assertEqual(node._hmb_agent_reference_observation_snapshot()["coverage"], [])
                self.assertEqual(native.call_count, 2)

    def test_picker_pair_ids_come_only_from_exact_selected_uid(self):
        p = prompt_module
        payload = {"schema": "hmb-prompt-library-picker-binding", "version": 2, "mode": "maya",
                   "run_id": "global-must-not-be-used", "bundle_run_id": "global-must-not-be-used",
                   "videos": [{"video_slot": 1, "video_uid": "selected-a", "video_path": "C:/selected/a.mp4", "bundle_run_id": "capture-a",
                               "pair_run_id": "pair-a", "source_type": "Maya Preview / Playblast"},
                              {"video_slot": 2, "video_uid": "selected-b", "video_path": "C:/selected/b.mp4", "source_type": "Maya Preview / Playblast"}],
                   "frame_metadata": [{**metadata("selected-a", "forged-row"), "video_slot": 2},
                                      {**metadata("selected-b", "forged-row"), "video_slot": 2}]}
        result = p._apply_picker_payload(p._default_widget_state(), payload, connected=True)
        rows = {v["video_slot"]: v for v in result["picker"]["frame_metadata"]}
        self.assertEqual(rows["@video1"]["bundle_run_id"], "capture-a")
        self.assertEqual(rows["@video1"]["pair_run_id"], "pair-a")
        self.assertEqual(rows["@video2"]["bundle_run_id"], "")
        payload["frame_metadata"] = [{**metadata("unknown-stale-uid", "forged-row"), "video_slot": 1}]
        result = p._apply_picker_payload(p._default_widget_state(), payload, connected=True)
        self.assertTrue(all(not v["bundle_run_id"] for v in result["picker"]["frame_metadata"]))
        legacy = {**metadata("selected-a", "forged-row"), "video_slot": 1}
        legacy.pop("video_uid")
        legacy.pop("source_uid")
        payload["frame_metadata"] = [legacy]
        result = p._apply_picker_payload(p._default_widget_state(), payload, connected=True)
        self.assertTrue(all(not v["bundle_run_id"] for v in result["picker"]["frame_metadata"]))

    def test_observation_same_run_hash_lifecycle_and_deepcopy(self):
        cls = agent_module.HMBAgentLibrary
        node = object.__new__(cls)
        node._hmb_node_deleted = False
        node._hmb_lifecycle_generation = 1
        node._hmb_runtime_prompt = MACHINE
        node._hmb_execution_result = {"status": "running", "run_id": "run-one"}
        node.parameter_values = {}
        node.parameter_output_values = {"output": "completed production prompt"}
        node.show_message_by_name = node.hide_message_by_name = lambda *args: None
        report = {"schema": "hmb-agent-reference-observation", "version": 1, "machine_sha256": MACHINE_HASH,
                  "status": "observed", "coverage": [{"media_token": "@video1", "observation_role": "original"}],
                  "skips": [], "groups": [], "budget_summary": {}}
        with patch.object(cls, "is_cancellation_requested", False):
            run = node._begin_hmb_reference_observation(MACHINE)
            node._store_hmb_reference_observation(report, run, 1, MACHINE_HASH)
            read = node._hmb_agent_reference_observation_snapshot()
            read["coverage"].clear()
            self.assertEqual(len(node._hmb_agent_reference_observation_snapshot()["coverage"]), 1)
            node._set_hmb_execution_result("succeeded")
            self.assertEqual(node._hmb_execution_result_snapshot()["reference_observation"]["run_id"], "run-one")
            node._set_hmb_execution_result("running")
            self.assertEqual(node._hmb_agent_reference_observation_snapshot(), {})
            next_run = node._begin_hmb_reference_observation(MACHINE)
            for wrong_run, generation, wrong_hash in [(run, 1, MACHINE_HASH), (next_run, 0, MACHINE_HASH),
                                                        (next_run, 1, "0" * 64)]:
                node._store_hmb_reference_observation(report, wrong_run, generation, wrong_hash)
                self.assertEqual(node._hmb_agent_reference_observation_snapshot()["coverage"], [])
            node._hmb_runtime_prompt = "other-shot-machine"
            node._store_hmb_reference_observation(report, next_run, 1, MACHINE_HASH)
            self.assertEqual(node._hmb_agent_reference_observation_snapshot()["coverage"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
