"""Offline advanced option boundaries and exact request/recovery semantics.

Uses the real Generator validator and payload builder with the existing
clean-CI node fixture. No provider, Broker, upload or active workflow is used.
"""
from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(TESTS))
spec = importlib.util.spec_from_file_location(
    "advanced_transport_option_fixture", TESTS / "HMB_Seedance_Draft_Regression.py",
)
assert spec and spec.loader
fixture = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fixture
spec.loader.exec_module(fixture)
t = fixture.t


class AdvancedTransportOptionsRegression(unittest.TestCase):
    def tearDown(self):
        while fixture.TEMPORARIES:
            fixture.TEMPORARIES.pop().cleanup()

    def values(self, **changes):
        values = fixture.params()
        values.update(changes)
        return values

    def validate(self, values):
        node = fixture.Node(values)
        node._validate_parameters(values)
        self.assertEqual(node.bridge.posts, [])
        self.assertEqual(node.bridge.refresh_ids, [])
        self.assertEqual(node.upload_calls, 0)
        return node

    def invalid(self, **changes):
        values = self.values(**changes)
        node = fixture.Node(values)
        with self.assertRaises(ValueError):
            node._build_broker_payload(values)
        self.assertEqual(node.bridge.posts, [])
        self.assertEqual(node.bridge.refresh_ids, [])
        self.assertEqual(node.upload_calls, 0)

    def test_poll_interval_and_local_timeout_exact_positive_integer_boundaries(self):
        for interval, timeout in ((1, 1), (1, 3600), (30, 3600), (3600, 3600)):
            with self.subTest(interval=interval, timeout=timeout):
                values = self.values(poll_interval_seconds=interval,
                                     generation_timeout_seconds=timeout)
                node = self.validate(values)
                body = node._build_broker_payload(values)
                self.assertEqual(values["poll_interval_seconds"], interval)
                self.assertEqual(values["generation_timeout_seconds"], timeout)
                self.assertNotIn("poll_interval_seconds", body)
                self.assertNotIn("generation_timeout_seconds", body)

    def test_invalid_polling_controls_fail_before_payload_or_upload(self):
        for name in ("poll_interval_seconds", "generation_timeout_seconds"):
            for value in (0, -1, True, False, 1.5, "30", None):
                with self.subTest(name=name, value=value):
                    self.invalid(**{name: value})
        self.invalid(poll_interval_seconds=61, generation_timeout_seconds=60)

    def test_provider_expiry_both_limits_and_default_survive_into_wire(self):
        for expiry in (3600, 172800, 259200):
            with self.subTest(expiry=expiry):
                values = self.values(execution_expires_after=expiry)
                node = self.validate(values)
                self.assertEqual(node._build_broker_payload(values)["execution_expires_after"], expiry)

    def test_invalid_expiry_is_never_clamped_or_posted(self):
        for value in (3599, 259201, 0, -1, True, False, 3600.0, "3600", None):
            with self.subTest(value=value):
                self.invalid(execution_expires_after=value)

    def test_full_seedance20_priorities_zero_through_nine_survive_wire(self):
        for priority in range(10):
            with self.subTest(priority=priority):
                values = self.values(model_id=t.SEEDANCE_2_0_MODEL_ID, priority=priority)
                node = self.validate(values)
                self.assertEqual(node._build_broker_payload(values)["priority"], priority)

    def test_invalid_priorities_fail_before_payload_or_upload(self):
        for value in (-1, 10, True, False, 1.0, "0", None):
            with self.subTest(value=value):
                self.invalid(model_id=t.SEEDANCE_2_0_MODEL_ID, priority=value)

    def test_fast_and_seedance25_allow_zero_and_omit_unsupported_priority(self):
        for model in (t.SEEDANCE_2_0_FAST_MODEL_ID, t.SEEDANCE_2_5_MODEL_ID):
            with self.subTest(model=model):
                values = self.values(model_id=model, priority=0)
                node = self.validate(values)
                self.assertNotIn("priority", node._build_broker_payload(values))
                self.assertEqual(values["priority"], 0)
                for unsupported in (1, 9):
                    self.invalid(model_id=model, priority=unsupported)

    def test_false_audio_watermark_and_last_frame_are_not_replaced_by_defaults(self):
        values = self.values(generate_audio=False, watermark=False, return_last_frame=False,
                             output_format="mov", priority=0)
        original = deepcopy(values)
        node = self.validate(values)
        body = node._build_broker_payload(values)
        for key in ("generate_audio", "watermark", "return_last_frame"):
            self.assertIs(body[key], False)
        self.assertEqual(body["output_format"], "mov")
        self.assertEqual(values, original)

    def test_cloud_and_tos_selection_are_local_transport_controls_not_provider_fields(self):
        for service in t.LOCAL_VIDEO_UPLOAD_SERVICES:
            for auto_publish in (False, True):
                with self.subTest(service=service, auto_publish=auto_publish):
                    values = self.values(local_video_upload_service=service,
                        auto_publish_local_videos=auto_publish, tos_url_validity_seconds=86400,
                        tos_region=t.DEFAULT_TOS_REGION, tos_endpoint=t.DEFAULT_TOS_ENDPOINT)
                    original = deepcopy(values)
                    node = self.validate(values)
                    body = node._build_broker_payload(values)
                    for field in ("local_video_upload_service", "auto_publish_local_videos", "tos_region",
                                  "tos_endpoint", "tos_url_validity_seconds"):
                        self.assertNotIn(field, body)
                    self.assertEqual(values, original)
        self.invalid(local_video_upload_service="unsupported uploader")

    def test_tos_signed_url_exact_one_hour_and_thirty_day_limits(self):
        for ttl in (3600, 86400, 2592000):
            with self.subTest(ttl=ttl):
                values = self.values(local_video_upload_service=t.LOCAL_VIDEO_UPLOAD_TOS,
                    tos_url_validity_seconds=ttl, tos_region=t.DEFAULT_TOS_REGION,
                    tos_endpoint=t.DEFAULT_TOS_ENDPOINT)
                self.validate(values)
                self.assertEqual(values["tos_url_validity_seconds"], ttl)
        for ttl in (3599, 2592001, 0, True, False, 3600.0, "3600", None):
            with self.subTest(ttl=ttl):
                self.invalid(local_video_upload_service=t.LOCAL_VIDEO_UPLOAD_TOS,
                    tos_url_validity_seconds=ttl, tos_region=t.DEFAULT_TOS_REGION,
                    tos_endpoint=t.DEFAULT_TOS_ENDPOINT)

    def test_tos_endpoint_host_and_scheme_are_validated_before_upload(self):
        for endpoint in ("http://tos-cn-beijing.volces.com", "https://attacker.example",
                         "https://tos-cn-beijing.volces.com/path",
                         "https://secret@tos-cn-beijing.volces.com",
                         "https://tos-cn-beijing.volces.com?token=fixture",
                         "https://tos-cn-beijing.volces.com:444"):
            with self.subTest(endpoint=endpoint):
                self.invalid(local_video_upload_service=t.LOCAL_VIDEO_UPLOAD_TOS,
                    tos_url_validity_seconds=86400, tos_region=t.DEFAULT_TOS_REGION,
                    tos_endpoint=endpoint)

    def test_cloud_selection_is_not_blocked_by_unused_stale_tos_options(self):
        values = self.values(local_video_upload_service=t.LOCAL_VIDEO_UPLOAD_GRIPTAPE,
                             tos_url_validity_seconds=0, tos_region="", tos_endpoint="invalid")
        self.validate(values)

    def test_resume_validates_only_existing_identity_and_polling_not_new_render_controls(self):
        values = self.values(resume_generation_id=fixture.JOB, model_id="old-model",
            execution_expires_after=-1, priority=99, local_video_upload_service="old-uploader",
            tos_url_validity_seconds=0, output_format="old-format", reference_images=["missing"])
        original = deepcopy(values)
        self.validate(values)
        self.assertEqual(values, original)
        for name in ("poll_interval_seconds", "generation_timeout_seconds"):
            invalid = deepcopy(values)
            invalid[name] = 0
            node = fixture.Node(invalid)
            with self.assertRaises(ValueError):
                node._validate_parameters(invalid)
            self.assertEqual(node.bridge.posts, [])

    def test_final_sparse_request_ignores_new_prompt_media_tos_expiry_and_priority(self):
        values = self.values(draft_action=t.DRAFT_ACTION_FINAL, resolution="1080p", output_format="mov",
            prompt="must not be resent", reference_images=["unavailable-image"],
            video_references=["unavailable-picker"], execution_expires_after=-1, priority=99,
            local_video_upload_service="old-uploader", tos_url_validity_seconds=0)
        node = self.validate(values)
        body = node._build_broker_payload(values)
        self.assertEqual(set(body), {"provider", "model", "draft_job_id", "resolution", "output_format",
                                     "project_id", "project_name"})
        self.assertEqual((body["draft_job_id"], body["resolution"], body["output_format"]),
                         (fixture.JOB, "1080p", "mov"))
        self.assertEqual(node.bridge.posts, [])
        self.assertEqual(node.upload_calls, 0)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps({"status": "PASS" if result.wasSuccessful() else "FAIL", "tests": result.testsRun,
                      "failures": len(result.failures), "errors": len(result.errors),
                      "provider_calls": 0, "mode": "clean_ci_actual_validator_and_payload"}))
    raise SystemExit(0 if result.wasSuccessful() else 1)
