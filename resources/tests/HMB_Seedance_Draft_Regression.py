"""Offline Draft billing/identity contract; never contacts Broker or provider."""
from __future__ import annotations

import asyncio
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hmb_seedance_clean_ci_stubs import install_clean_ci_griptape_stubs
install_clean_ci_griptape_stubs()
spec = importlib.util.spec_from_file_location("hmb_seedance_draft_tests", ROOT / "HMBSeedanceGeneration.py")
assert spec and spec.loader
t = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = t
spec.loader.exec_module(t)

JOB = "job-" + "a" * 32
ORIGIN = "http://192.168.203.245:8080"
PROJECT = {"project_id": "dinoster5", "project_name": "다이노스터"}
SOURCE = {"draft_job_id": JOB, **PROJECT, "broker_server_url": ORIGIN}
TEMPORARIES = []


def capability():
    return {"schema": t.BROKER_SEEDANCE_CAPABILITIES_SCHEMA, "version": 3,
            "models": {t.SEEDANCE_2_5_MODEL_ID: {
                "tasks": ["text_to_video", "first_last_frame", "reference_to_video"],
                "output_formats": ["mp4", "mov"], "return_last_frame": True,
                "draft_generation": True, "draft_preview_resolution": "480p",
                "draft_final_resolution": "1080p", "draft_source_reference": "broker_job_id",
                "draft_output_formats": ["mp4", "mov"],
                "draft_source_ttl_seconds": 604800}}}


def params(action=t.DRAFT_ACTION_OFF):
    return {"resume_generation_id": "", "model_id": t.SEEDANCE_2_5_MODEL_ID,
            "task": t.TASK_TEXT_ONLY, "input_mode": t.INPUT_MODE_TEXT_ONLY,
            "prompt": "Exact prompt {{SIGN}}", "first_frame": None, "last_frame": None,
            "reference_images": [], "video_reference_slots": [], "video_references": [],
            "reference_audio": [], "resolution": "720p", "ratio": "16:9", "duration": 4,
            "generate_audio": False, "watermark": False, "output_format": "mp4",
            "return_last_frame": False, "execution_expires_after": 3600, "priority": 0,
            "poll_interval_seconds": 1, "generation_timeout_seconds": 60,
            "auto_publish_local_videos": False, "local_video_upload_service": t.LOCAL_VIDEO_UPLOAD_GRIPTAPE,
            "draft_action": action, "draft_job_id": JOB, "_hmb_draft_only": True,
            "_hmb_draft_source": deepcopy(SOURCE), **PROJECT}


class FakeBridge:
    server_url = ORIGIN

    def __init__(self):
        self.posts = []
        self.cap_calls = 0
        self.draft_formats = []
        self.feature_calls = []
        self.refresh_ids = []
        self.capability_response = capability()
        self.capability_error = None
        self.format_resolution_calls = []

    def _authenticated_capability_bridge(self):
        bridge = t._HMBAIBrokerBridge(server_url=self.server_url)

        def capability_request(method, path, **kwargs):
            if method != "GET":
                raise AssertionError("Capability boundary attempted a generation request")
            if self.capability_error is not None:
                raise self.capability_error
            return deepcopy(self.capability_response)

        bridge._request_json = capability_request
        return bridge

    def require_seedance_draft_features(self, *, timeout, output_format="mp4",
                                       allow_output_fallback=False):
        self.cap_calls += 1
        self.draft_formats.append(output_format)
        result = self._authenticated_capability_bridge().require_seedance_draft_features(
            timeout=timeout, output_format=output_format,
            allow_output_fallback=allow_output_fallback)
        self.format_resolution_calls.append(("draft", output_format, result))
        return result

    def require_seedance_features(self, **features):
        self.feature_calls.append(deepcopy(features))
        result = self._authenticated_capability_bridge().require_seedance_features(**features)
        self.format_resolution_calls.append(("ordinary", features["output_format"], result))
        return result

    def generate_seedance(self, payload, *, timeout):
        self.posts.append(deepcopy(payload))
        return {"id": "job-" + str(len(self.posts)) * 32, "status": "succeeded", "video_url": "fixture"}

    def refresh_job(self, job_id, *, timeout):
        self.refresh_ids.append(job_id)
        return {"id": job_id, "status": "succeeded", "video_url": "fixture"}


class Node(t.HMBSeedanceGeneration):
    @property
    def is_cancellation_requested(self):
        return False

    def __init__(self, values=None):
        self.values = values or params()
        super().__init__(name="Draft Offline")
        # Clean CI does not emulate ParameterGroup child registration. Match
        # the native constructor's generated private owner for this fixture.
        if not self.get_parameter_value(t.DRAFT_OWNER_PARAMETER):
            self.parameter_values[t.DRAFT_OWNER_PARAMETER] = str(uuid4())
        self.saved = []
        self.upload_calls = 0
        self.bridge = FakeBridge()
        self.base = tempfile.TemporaryDirectory()
        TEMPORARIES.append(self.base)
        self.destination = SimpleNamespace(resolve=lambda: str(Path(self.base.name) / "original.mp4"))
        self._output_file = SimpleNamespace(build_file=lambda: self.destination, _default_filename="original.mp4")

    def _runtime_node_is_live(self, *, require_registered=False):
        return True

    @staticmethod
    def _output_destination_policy(destination):
        # Lightweight SDK stub constants are not Enum instances.
        return getattr(destination, "_existing_file_policy", t.ExistingFilePolicy.OVERWRITE)

    def _get_parameters(self):
        return deepcopy(self.values)

    def _draft_only_mode(self):
        return self.values.get("_hmb_draft_only") is True

    def _assert_new_submission_is_safe(self, **kwargs):
        pass

    def _capture_generated_video_origin(self):
        return {}

    def _resolve_exact_shot_generation_inputs(self, values):
        return values

    def _begin_generation_preview(self):
        pass

    def _set_safe_defaults(self):
        pass

    def _set_generation_status(self, *args, **kwargs):
        pass

    def _set_broker_task_outputs(self, task, *, generation_id, status, **kwargs):
        self.parameter_output_values.update(generation_id=generation_id, generation_status=status)

    async def _ensure_broker_connected(self, **kwargs):
        return self.bridge

    def _prepare_video_references_for_run(self, values):
        self.upload_calls += 1
        return values

    def _assert_agent_result_available(self, *args, **kwargs):
        if self.values["draft_action"] != t.DRAFT_ACTION_FINAL:
            return
        # Final path must not depend on any connected Agent result.

    def _normalize_broker_task(self, response, **kwargs):
        return response

    def _start_review_case(self, *args):
        pass

    async def _force_save_generation_recovery_checkpoint(self, **kwargs):
        return True

    async def _save_completed_task(self, task, job_id, destination, *args, **kwargs):
        self.saved.append((job_id, destination.resolve(), kwargs))

    def set_parameter_value(self, name, value, **kwargs):
        self.parameter_values[name] = value

    def publish_update_to_parameter(self, *args, **kwargs):
        pass


class DraftTests(unittest.TestCase):
    def tearDown(self):
        while TEMPORARIES:
            TEMPORARIES.pop().cleanup()

    def test_normal_480p_without_draft_flag(self):
        node = Node()
        value = params()
        value["resolution"] = "480p"
        payload = node._build_broker_payload(value)
        self.assertEqual((payload["quality"], payload["resolution"]), ("480p", "480p"))
        self.assertNotIn("draft", payload)
        self.assertNotIn("draft_job_id", payload)

    def test_preview_payload_480p(self):
        node = Node()
        value = params(t.DRAFT_ACTION_PREVIEW)
        value.update(resolution="480p", output_format="mov")
        payload = node._build_broker_payload(value)
        self.assertIs(payload["draft"], True)
        self.assertEqual(payload["quality"], "480p")
        self.assertEqual(payload["prompt"], value["prompt"])
        self.assertEqual(payload["output_format"], "mov")
        self.assertNotIn("draft_job_id", payload)

    def test_final_payload_sparse_original_project(self):
        node = Node()
        value = params(t.DRAFT_ACTION_FINAL)
        value.update(resolution="1080p", prompt="must never be re-used", duration=999,
                     ratio="changed", generate_audio=True, reference_images=["bad://media"],
                     project_id="katuri8", project_name="까투리8", output_format="mov")
        self.assertEqual(node._build_broker_payload(value), {
            "provider": "volcengine_ark", "model": t.SEEDANCE_2_5_MODEL_ID,
            "draft_job_id": JOB, "resolution": "1080p", "output_format": "mov", **PROJECT})

    def test_only_25_gate(self):
        for change in ({"_hmb_draft_only": False}, {"model_id": t.SEEDANCE_2_0_MODEL_ID}):
            value = params(t.DRAFT_ACTION_PREVIEW)
            value.update(resolution="480p", **change)
            with self.assertRaises(ValueError):
                Node()._build_broker_payload(value)

    def test_final_requires_local_broker_id(self):
        for job in ("cgt-20261013-test", "hmb-client", "", "../job-123"):
            value = params(t.DRAFT_ACTION_FINAL)
            value.update(resolution="1080p", draft_job_id=job)
            with self.assertRaises(ValueError):
                Node()._build_broker_payload(value)

    def test_capability_strict(self):
        bridge = t._HMBAIBrokerBridge(server_url=ORIGIN)
        for bad in ("version", "draft_generation", "draft_source_reference", "draft_source_ttl_seconds"):
            response = capability()
            if bad == "version":
                response[bad] = 2
            else:
                response["models"][t.SEEDANCE_2_5_MODEL_ID][bad] = "wrong"
            with mock.patch.object(bridge, "_request_json", return_value=response):
                with self.assertRaises(t._BrokerProtocolError):
                    bridge.require_seedance_draft_features()
        with mock.patch.object(bridge, "_request_json", return_value=capability()):
            bridge.require_seedance_draft_features()

    def test_bridge_final_does_not_add_inherited_fields(self):
        bridge = t._HMBAIBrokerBridge(server_url=ORIGIN)
        payload = {"provider": "volcengine_ark", "model": t.SEEDANCE_2_5_MODEL_ID,
                   "draft_job_id": JOB, "resolution": "1080p", "output_format": "mov",
                   "client_request_id": "hmb-final-unique", **PROJECT}
        calls = []
        def request(method, path, **kwargs):
            calls.append((method, path, kwargs))
            return capability() if method == "GET" else {"job_id": JOB}
        with mock.patch.object(bridge, "_request_json", side_effect=request):
            bridge.generate_seedance(payload, timeout=30)
        self.assertEqual([c[0] for c in calls], ["GET", "POST"])
        self.assertEqual(calls[0][1], t.BROKER_SEEDANCE_CAPABILITIES_PATH + "?draft=1")
        self.assertEqual(calls[-1][2]["payload"], payload)
        self.assertEqual(calls[-1][2]["idempotency_key"], payload["client_request_id"])
        for field in ("prompt", "duration_seconds", "input_mode", "quality", "draft"):
            with mock.patch.object(bridge, "_request_json", side_effect=AssertionError("network")):
                with self.assertRaises(t._BrokerProtocolError):
                    bridge.generate_seedance({**payload, field: "forbidden"}, timeout=30)

        for changes in ({"resolution": "480p"}, {"resolution": "720p"},
                        {"output_format": "avi"}, {"output_format": "MOV"}):
            with self.subTest(changes=changes), \
                 mock.patch.object(bridge, "_request_json", side_effect=AssertionError("network")), \
                 self.assertRaises(t._BrokerProtocolError):
                bridge.generate_seedance({**payload, **changes}, timeout=30)

    def test_mov_draft_requires_explicit_broker_output_format_capability(self):
        bridge = t._HMBAIBrokerBridge(server_url=ORIGIN)
        for advertised in (None, ["mp4"], "mov", []):
            response = capability()
            profile = response["models"][t.SEEDANCE_2_5_MODEL_ID]
            if advertised is None:
                profile.pop("draft_output_formats")
            else:
                profile["draft_output_formats"] = advertised
            with self.subTest(advertised=advertised), \
                 mock.patch.object(bridge, "_request_json", return_value=response), \
                 self.assertRaises(t._BrokerProtocolError):
                bridge.require_seedance_draft_features(output_format="mov", timeout=1)
        with mock.patch.object(bridge, "_request_json", return_value=capability()):
            bridge.require_seedance_draft_features(output_format="mov", timeout=1)

    def test_authenticated_capability_selects_mov_or_explicit_mp4_fallback(self):
        for draft in (False, True):
            for formats, expected in ((["mp4", "mov"], "mov"), (["mp4"], "mp4")):
                with self.subTest(draft=draft, formats=formats):
                    bridge = t._HMBAIBrokerBridge(server_url=ORIGIN)
                    response = capability()
                    profile = response["models"][t.SEEDANCE_2_5_MODEL_ID]
                    profile["output_formats"] = deepcopy(formats)
                    profile["draft_output_formats"] = deepcopy(formats)
                    with mock.patch.object(bridge, "_request_json", return_value=response) as request:
                        if draft:
                            effective = bridge.require_seedance_draft_features(
                                output_format="mov", allow_output_fallback=True, timeout=1)
                        else:
                            effective = bridge.require_seedance_features(model_id=t.SEEDANCE_2_5_MODEL_ID,
                                task=t.TASK_TEXT_ONLY, output_format="mov", return_last_frame=False,
                                allow_output_fallback=True, timeout=1)
                    self.assertEqual(effective, expected)
                    self.assertTrue(request.call_args_list)
                    self.assertTrue(all(call.args[0] == "GET" for call in request.call_args_list))

    def test_missing_malformed_or_failed_capability_never_selects_fallback_or_posts(self):
        invalid_documents = [None, {}, {**capability(), "version": True}]
        for advertised in (None, "mp4", [], ["mp4", False]):
            response = capability()
            profile = response["models"][t.SEEDANCE_2_5_MODEL_ID]
            for field in ("output_formats", "draft_output_formats"):
                if advertised is None:
                    profile.pop(field)
                else:
                    profile[field] = deepcopy(advertised)
            invalid_documents.append(response)
        errors = [t._BrokerError("Synthetic unauthenticated capability", status_code=401),
                  t._BrokerError("Synthetic unsupported capability", status_code=404),
                  t._BrokerError("Synthetic unavailable capability", status_code=503),
                  TimeoutError("Synthetic capability timeout")]
        for draft in (False, True):
            for index, fixture in enumerate([*invalid_documents, *errors]):
                bridge = t._HMBAIBrokerBridge(server_url=ORIGIN)
                transport = mock.Mock(side_effect=fixture) if isinstance(fixture, BaseException) else mock.Mock(return_value=fixture)
                with self.subTest(draft=draft, fixture=index), \
                     mock.patch.object(bridge, "_request_json", transport), \
                     self.assertRaises((t._BrokerProtocolError, t._BrokerError, TimeoutError)):
                    if draft:
                        bridge.require_seedance_draft_features(
                            output_format="mov", allow_output_fallback=True, timeout=1)
                    else:
                        bridge.require_seedance_features(model_id=t.SEEDANCE_2_5_MODEL_ID,
                            task=t.TASK_TEXT_ONLY, output_format="mov", return_last_frame=False,
                            allow_output_fallback=True, timeout=1)
                self.assertTrue(transport.call_args_list)
                self.assertTrue(all(call.args[0] == "GET" for call in transport.call_args_list))

    def test_direct_mov_generation_stays_strict_and_never_rewrites_frozen_body(self):
        response = capability()
        profile = response["models"][t.SEEDANCE_2_5_MODEL_ID]
        profile["output_formats"] = ["mp4"]
        profile["draft_output_formats"] = ["mp4"]
        for final in (False, True):
            values = params(t.DRAFT_ACTION_FINAL if final else t.DRAFT_ACTION_OFF)
            values.update(resolution="1080p", output_format="mov")
            body = Node()._build_broker_payload(values)
            body["client_request_id"] = t._seedance_draft_final_request_id(JOB)
            original = deepcopy(body)
            bridge = t._HMBAIBrokerBridge(server_url=ORIGIN)
            with self.subTest(final=final), \
                 mock.patch.object(bridge, "_request_json", return_value=response) as request, \
                 self.assertRaises(t._BrokerProtocolError):
                bridge.generate_seedance(body, timeout=1)
            self.assertEqual(body, original)
            self.assertEqual(body["output_format"], "mov")
            self.assertTrue(all(call.args[0] == "GET" for call in request.call_args_list))

    def test_draft_output_support_is_independent_of_ordinary_output_formats(self):
        for ordinary, draft, expected in ((["mp4"], ["mp4", "mov"], "mov"),
                                          (["mp4", "mov"], ["mp4"], "mp4")):
            with self.subTest(ordinary=ordinary, draft=draft):
                response = capability()
                profile = response["models"][t.SEEDANCE_2_5_MODEL_ID]
                profile["output_formats"] = deepcopy(ordinary)
                profile["draft_output_formats"] = deepcopy(draft)
                bridge = t._HMBAIBrokerBridge(server_url=ORIGIN)
                calls = []

                def request(method, path, **kwargs):
                    calls.append((method, path, deepcopy(kwargs)))
                    return deepcopy(response) if method == "GET" else {"job_id": JOB}

                with mock.patch.object(bridge, "_request_json", side_effect=request):
                    effective = bridge.require_seedance_draft_features(
                        output_format="mov", allow_output_fallback=True, timeout=1)
                    self.assertEqual(effective, expected)
                    values = params(t.DRAFT_ACTION_PREVIEW)
                    values.update(resolution="480p", output_format=effective)
                    body = Node()._build_broker_payload(values)
                    body["client_request_id"] = "hmb-distinct-draft-format-scope"
                    frozen = deepcopy(body)
                    bridge.generate_seedance(body, timeout=1)
                self.assertEqual(body, frozen)
                self.assertEqual([method for method, _, _ in calls].count("POST"), 1)
                published = next(kwargs["payload"] for method, _, kwargs in calls if method == "POST")
                self.assertIs(published["draft"], True)
                self.assertEqual(published.get("output_format", "mp4"), expected)

    def test_late_format_capability_loss_never_rewrites_or_posts_frozen_request(self):
        for draft in (False, True):
            with self.subTest(draft=draft):
                before = capability()
                after = capability()
                after_profile = after["models"][t.SEEDANCE_2_5_MODEL_ID]
                after_profile["output_formats"] = ["mp4"]
                if draft:
                    before["models"][t.SEEDANCE_2_5_MODEL_ID]["draft_output_formats"] = ["mp4"]
                    after_profile.pop("draft_output_formats")
                bridge = t._HMBAIBrokerBridge(server_url=ORIGIN)
                with mock.patch.object(bridge, "_request_json", side_effect=[before, after]) as request:
                    if draft:
                        effective = bridge.require_seedance_draft_features(
                            output_format="mov", allow_output_fallback=True, timeout=1)
                    else:
                        effective = bridge.require_seedance_features(model_id=t.SEEDANCE_2_5_MODEL_ID,
                            task=t.TASK_TEXT_ONLY, output_format="mov", return_last_frame=False,
                            allow_output_fallback=True, timeout=1)
                    values = params(t.DRAFT_ACTION_FINAL if draft else t.DRAFT_ACTION_OFF)
                    values.update(resolution="1080p", output_format=effective)
                    body = Node()._build_broker_payload(values)
                    body["client_request_id"] = t._seedance_draft_final_request_id(JOB)
                    frozen = deepcopy(body)
                    with self.assertRaises(t._BrokerProtocolError):
                        bridge.generate_seedance(body, timeout=1)
                self.assertEqual(body, frozen)
                self.assertEqual(body["output_format"], effective)
                self.assertEqual([call.args[0] for call in request.call_args_list], ["GET", "GET"])

    def test_legacy_mp4_final_bridge_preserves_frozen_sparse_body(self):
        bridge = t._HMBAIBrokerBridge(server_url=ORIGIN)
        legacy_capability = capability()
        legacy_capability["models"][t.SEEDANCE_2_5_MODEL_ID].pop("draft_output_formats")
        legacy = {"provider": "volcengine_ark", "model": t.SEEDANCE_2_5_MODEL_ID,
                  "draft_job_id": JOB, "quality": "1080p",
                  "client_request_id": "hmb-accepted-legacy-final", **PROJECT}
        for explicit_format in (False, True):
            body = {**legacy, **({"output_format": "mp4"} if explicit_format else {})}
            calls = []

            def request(method, path, **kwargs):
                calls.append((method, path, kwargs))
                return deepcopy(legacy_capability) if method == "GET" else {"job_id": JOB}

            with self.subTest(explicit_format=explicit_format), \
                 mock.patch.object(bridge, "_request_json", side_effect=request):
                bridge.generate_seedance(body, timeout=1)
            self.assertEqual([call[0] for call in calls], ["GET", "POST"])
            self.assertEqual(calls[-1][2]["payload"], body)
            self.assertEqual(calls[-1][2]["idempotency_key"], legacy["client_request_id"])

    def test_explicitly_malformed_draft_format_list_cannot_use_legacy_mp4_exception(self):
        for advertised in (None, "mp4", [], ["mp4", False]):
            response = capability()
            response["models"][t.SEEDANCE_2_5_MODEL_ID]["draft_output_formats"] = advertised
            bridge = t._HMBAIBrokerBridge(server_url=ORIGIN)
            with self.subTest(advertised=advertised), \
                 mock.patch.object(bridge, "_request_json", return_value=response) as request, \
                 self.assertRaises(t._BrokerProtocolError):
                bridge.require_seedance_draft_features(output_format="mp4", timeout=1)
            self.assertEqual([call.args[0] for call in request.call_args_list], ["GET"])

    def test_bridge_draft_20_and_wrong_resolution_rejected(self):
        bridge = t._HMBAIBrokerBridge(server_url=ORIGIN)
        for model, quality in ((t.SEEDANCE_2_0_MODEL_ID, "480p"), (t.SEEDANCE_2_5_MODEL_ID, "720p")):
            with mock.patch.object(bridge, "_request_json", side_effect=AssertionError("network")):
                with self.assertRaises(t._BrokerProtocolError):
                    bridge.generate_seedance({"model": model, "draft": True, "quality": quality, "resolution": quality}, timeout=30)

    def test_draft_source_bounded_and_no_secrets(self):
        record = t._seedance_draft_source_value({**SOURCE, "prompt": "PRIVATE", "image_urls": ["signed"], "token": "KEY"})
        self.assertEqual(record, SOURCE)
        self.assertEqual(t._seedance_draft_source_value({**SOURCE, "broker_server_url": ""}), {})

    def test_checkpoint_preserves_preview_action_and_project(self):
        node = Node()
        values = params(t.DRAFT_ACTION_PREVIEW)
        values.update(resolution="480p", _hmb_broker_server_url=ORIGIN, _hmb_draft_project=PROJECT)
        node._set_generation_recovery_checkpoint(stage="pre_submit", task_id="hmb-client", task_identity="client_request",
                                                status="submitting", params=values)
        changed = params(t.DRAFT_ACTION_FINAL)
        changed.update(_hmb_broker_server_url=ORIGIN)
        result = node._set_generation_recovery_checkpoint(stage="accepted", task_id=JOB, task_identity="broker_task",
                                                         status="succeeded", params=changed)
        self.assertEqual(result["draft_action"], t.DRAFT_ACTION_PREVIEW)
        self.assertEqual(result["draft_project"]["project_id"], PROJECT["project_id"])

    def test_normal_off_keeps_checkpoint_surface(self):
        result = t._seedance_recovery_value({"draft_action": t.DRAFT_ACTION_OFF})
        self.assertNotIn("draft_action", result)
        self.assertNotIn("draft_source", result)

    def test_real_parameter_snapshot_phase_overrides_are_explicit(self):
        node = Node()
        # The explicit Final selection now resolves its completed source before
        # exposing a runnable parameter snapshot. Keep the legacy Only source.
        node.parameter_values[t.DRAFT_SOURCE_PARAMETER] = deepcopy(SOURCE)
        for action, expected in ((t.DRAFT_ACTION_PREVIEW, "480p"), (t.DRAFT_ACTION_FINAL, "1080p")):
            node.parameter_values.update(draft_action=action, resolution="720p", output_format="mov", return_last_frame=True)
            value = t.HMBSeedanceGeneration._get_parameters(node)
            self.assertEqual((value["resolution"], value["output_format"], value["return_last_frame"]), (expected, "mov", False))
        node.parameter_values["draft_action"] = t.DRAFT_ACTION_OFF
        value = t.HMBSeedanceGeneration._get_parameters(node)
        self.assertEqual((value["resolution"], value["output_format"], value["return_last_frame"]), ("720p", "mov", True))

    def test_non25_normal_run_preserves_mp4_settings(self):
        node = Node()
        node.parameter_values.update(params())
        node.parameter_values.update(model_id=t.MODEL_NAME_SEEDANCE_2_0, resolution="720p",
                                     draft_action=t.DRAFT_ACTION_OFF, output_format="mp4")
        value = t.HMBSeedanceGeneration._get_parameters(node)
        self.assertEqual((value["draft_action"], value["resolution"], value["output_format"]),
                         (t.DRAFT_ACTION_OFF, "720p", "mp4"))
        payload = node._build_broker_payload(value)
        # Seedance 2.0 retains its v1 body and implicit MP4 contract.
        self.assertNotIn("output_format", payload)
        self.assertEqual(t.DEFAULT_OUTPUT_FORMAT, "mp4")
        self.assertNotIn("draft", payload)
        self.assertNotIn("draft_job_id", payload)

    def test_model_specific_default_format_without_authored_choice(self):
        for model, expected in ((t.MODEL_NAME_SEEDANCE_2_0, "mp4"),
                                (t.MODEL_NAME_SEEDANCE_2_5, "mov")):
            with self.subTest(model=model):
                node = Node()
                node.parameter_values.update(params())
                node.parameter_values.update(model_id=model, output_format=None,
                                             draft_action=t.DRAFT_ACTION_OFF)
                values = t.HMBSeedanceGeneration._get_parameters(node)
                self.assertEqual(values["output_format"], expected)

    def test_completed_preview_stores_job_project_and_origin_no_auto_post(self):
        values = params(t.DRAFT_ACTION_PREVIEW)
        values.update(resolution="480p", _hmb_broker_server_url=ORIGIN, _hmb_draft_project=PROJECT)
        node = Node(values)
        node._set_generation_recovery_checkpoint(stage="pre_submit", task_id="hmb-client", task_identity="client_request",
                                                status="submitting", params=values)
        node._set_generation_recovery_checkpoint(stage="remote_succeeded", task_id=JOB, task_identity="broker_task",
                                                status="succeeded", params=values)
        with mock.patch.object(node, "_extract_video_url", return_value="https://example.org/fixture.mp4"), \
             mock.patch.object(node, "_download_broker_video", new=mock.AsyncMock(return_value=b"fixture")), \
             mock.patch.object(node, "_atomic_publish_completed_video", new=mock.AsyncMock(return_value=SimpleNamespace(location="fixture.mp4", name="fixture.mp4"))), \
             mock.patch.object(node, "_publish_generation_preview"), \
             mock.patch.object(node, "_record_completed_video_source"), \
             mock.patch.object(node, "_schedule_review_sync"), \
             mock.patch.object(node, "_set_status_results", create=True), \
             mock.patch.object(t._review, "update_case"):
            asyncio.run(t.HMBSeedanceGeneration._save_completed_task(node, {}, JOB, node.destination,
                         model_id=t.SEEDANCE_2_5_MODEL_ID, output_format="mp4", return_last_frame=False))
        self.assertEqual(node.get_parameter_value("draft_job_id"), JOB)
        completed_source = node.get_parameter_value(t.DRAFT_SOURCE_PARAMETER)
        self.assertEqual({key: completed_source[key] for key in SOURCE}, SOURCE)
        self.assertEqual(completed_source["generation_origin"], {})
        self.assertIs(completed_source["completed"], True)
        self.assertGreater(completed_source["created_at_ms"], 0)
        self.assertEqual(node._generation_recovery_state()["draft_source"], completed_source)
        self.assertEqual(node.bridge.posts, [])

    def test_preview_one_post_no_auto_final(self):
        values = params(t.DRAFT_ACTION_PREVIEW)
        values.update(resolution="480p", output_format="mov")
        node = Node(values)
        # This billing fixture has no registered SDK graph. Source topology and
        # fail-closed preflight are exercised by Project_Source_Routing tests.
        selection = {"schema": t.PROJECT_SELECTION_SCHEMA, "project": deepcopy(PROJECT)}
        node._resolve_exact_shot_generation_inputs = lambda values: {
            **values, "_hmb_imageasset_project_selection": deepcopy(selection)
        }
        with mock.patch.object(t, "_resolve_mp4_decode_verifier", return_value=SimpleNamespace(executable="fixture", backend="test")), \
             mock.patch.object(node, "_capture_imageasset_project_selection", return_value=selection), \
             mock.patch.object(t._review, "capture_inputs", return_value={}):
            asyncio.run(node._process_generation_impl())
        self.assertEqual(len(node.bridge.posts), 1)
        self.assertIs(node.bridge.posts[0]["draft"], True)
        self.assertEqual(node.bridge.posts[0]["output_format"], "mov")
        self.assertEqual(node.saved[0][2]["output_format"], "mov")
        self.assertTrue(node.saved[0][1].endswith(".mov"))
        self.assertEqual(node.upload_calls, 1)
        self.assertIn("draft480p", node.saved[0][1])
        self.assertFalse(Path(node.base.name, "original.mp4").exists())

    def test_ordinary_25_fallback_freezes_supported_format_before_output_and_post(self):
        for formats, expected in ((["mp4", "mov"], "mov"), (["mp4"], "mp4")):
            with self.subTest(formats=formats):
                values = params()
                values.update(resolution="1080p", output_format="mov")
                node = Node(values)
                profile = node.bridge.capability_response["models"][t.SEEDANCE_2_5_MODEL_ID]
                profile["output_formats"] = deepcopy(formats)
                node.parameter_values["output_file"] = str(Path(node.base.name, "volcengine_seedance_video.mov"))
                destination = SimpleNamespace(resolve=lambda: str(
                    Path(node.base.name) / str(node.get_parameter_value("output_file"))))
                build = mock.Mock(return_value=destination)
                node._output_file = SimpleNamespace(build_file=build,
                    _default_filename="volcengine_seedance_video.mov")
                selection = {"schema": t.PROJECT_SELECTION_SCHEMA, "project": deepcopy(PROJECT)}
                node._resolve_exact_shot_generation_inputs = lambda current: {
                    **current, "_hmb_imageasset_project_selection": deepcopy(selection)}
                with mock.patch.object(t, "_resolve_mp4_decode_verifier",
                        return_value=SimpleNamespace(executable="fixture", backend="test")), \
                     mock.patch.object(node, "_capture_imageasset_project_selection", return_value=selection), \
                     mock.patch.object(t._review, "capture_inputs", return_value={}):
                    asyncio.run(node._process_generation_impl())
                self.assertEqual(len(node.bridge.posts), 1)
                self.assertEqual(node.bridge.posts[0].get("output_format", "mp4"), expected)
                self.assertEqual(node.saved[0][2]["output_format"], expected)
                self.assertTrue(node.saved[0][1].endswith("."+expected))
                self.assertEqual(node._generation_recovery_state()["output_format"], expected)
                self.assertEqual(node._generation_recovery_state()["output_file"], node.saved[0][1])
                self.assertTrue(build.called)

    def test_invalid_ordinary_and_preview_capability_block_before_upload_destination_or_post(self):
        for action in (t.DRAFT_ACTION_OFF, t.DRAFT_ACTION_PREVIEW):
            for failure in (None, t._BrokerError("Synthetic capability 401", status_code=401),
                            t._BrokerError("Synthetic capability 503", status_code=503)):
                with self.subTest(action=action, failure=repr(failure)):
                    values = params(action)
                    values.update(resolution="480p" if action == t.DRAFT_ACTION_PREVIEW else "1080p",
                                  output_format="mov")
                    self._assert_invalid_capability_stops_before_publication(values, failure)

    def _assert_invalid_capability_stops_before_publication(self, values, failure):
        node = Node(values)
        if failure is None:
            node.bridge.capability_response = {}
        else:
            node.bridge.capability_error = failure
        build = mock.Mock(side_effect=AssertionError("Unproven format froze an output destination"))
        node._output_file.build_file = build
        selection = {"schema": t.PROJECT_SELECTION_SCHEMA, "project": deepcopy(PROJECT)}
        node._resolve_exact_shot_generation_inputs = lambda current: {
            **current, "_hmb_imageasset_project_selection": deepcopy(selection)}
        with mock.patch.object(t, "_resolve_mp4_decode_verifier",
                return_value=SimpleNamespace(executable="fixture", backend="test")), \
             mock.patch.object(node, "_capture_imageasset_project_selection", return_value=selection), \
             mock.patch.object(t._review, "capture_inputs", return_value={}), \
             self.assertRaises((t._BrokerProtocolError, t._BrokerError)):
            asyncio.run(node._process_generation_impl())
        self.assertEqual(node.bridge.posts, [])
        self.assertEqual(node.upload_calls, 0)
        self.assertEqual(node.saved, [])
        build.assert_not_called()

    def test_final_one_post_no_media_no_agent_old_origin(self):
        values = params(t.DRAFT_ACTION_FINAL)
        values.update(resolution="1080p", output_format="mov")
        node = Node(values)
        node._prepare_video_references_for_run = mock.Mock(side_effect=AssertionError("media upload"))
        node._resolve_exact_shot_generation_inputs = mock.Mock(side_effect=AssertionError("new inputs"))
        with mock.patch.object(t, "_resolve_mp4_decode_verifier", return_value=SimpleNamespace(executable="fixture", backend="test")), \
             mock.patch.object(t._review, "capture_inputs", side_effect=AssertionError("media capture")):
            asyncio.run(node._process_generation_impl())
        self.assertEqual(len(node.bridge.posts), 1)
        self.assertEqual(set(node.bridge.posts[0]), {"provider", "model", "draft_job_id", "resolution", "output_format", "project_id", "project_name", "client_request_id"})
        self.assertEqual((node.bridge.posts[0]["resolution"], node.bridge.posts[0]["output_format"]),
                         ("1080p", "mov"))
        self.assertIn("final1080p", node.saved[0][1])

    def test_final_production_agent_gate_bypassed_only_when_explicit(self):
        node = Node()
        node.parameter_values.update(draft_action=t.DRAFT_ACTION_FINAL, model_id=t.MODEL_NAME_SEEDANCE_2_5)
        with mock.patch.object(node, "_manual_agent_prompt_source", side_effect=AssertionError("Agent must not be used")):
            t.HMBSeedanceGeneration._assert_agent_result_available(node)
        node.parameter_values["draft_action"] = t.DRAFT_ACTION_OFF
        with mock.patch.object(node, "_manual_agent_prompt_source", side_effect=RuntimeError("Agent missing")):
            with self.assertRaises(t._AgentResultUnavailable):
                t.HMBSeedanceGeneration._assert_agent_result_available(node)

    def test_hidden_draft_actions_are_dormant_outside_only_25(self):
        for action in (t.DRAFT_ACTION_PREVIEW, t.DRAFT_ACTION_FINAL):
            for model, only in ((t.MODEL_NAME_SEEDANCE_2_5, False), (t.MODEL_NAME_SEEDANCE_2_0, True)):
                node = Node()
                node.values["_hmb_draft_only"] = only
                node.parameter_values.update(draft_action=action, model_id=model, resolution="720p",
                                             output_format="mp4", return_last_frame=False)
                values = t.HMBSeedanceGeneration._get_parameters(node)
                self.assertEqual(values["draft_action"], t.DRAFT_ACTION_OFF)
                self.assertEqual(values["resolution"], "720p")
                self.assertEqual(node.get_parameter_value("draft_action"), action)
                self.assertEqual(t.HMBSeedanceGeneration._validate_draft_parameters(values), t.DRAFT_ACTION_OFF)

    def test_explicit_resume_uses_frozen_draft_path_no_new_post(self):
        for action in (t.DRAFT_ACTION_PREVIEW, t.DRAFT_ACTION_FINAL):
            for frozen_format in ("mp4", "mov"):
                with self.subTest(action=action, frozen_format=frozen_format):
                    original = params(action)
                    original.update(resolution="480p" if action == t.DRAFT_ACTION_PREVIEW else "1080p",
                                    output_format=frozen_format,
                                    _hmb_broker_server_url=ORIGIN, _hmb_draft_project=PROJECT)
                    node = Node()
                    saved_path = str(Path(node.base.name, "saved-draft-stage."+frozen_format))
                    original["_hmb_output_file"] = saved_path
                    node._set_generation_recovery_checkpoint(stage="pre_submit", task_id="hmb-previous", task_identity="client_request",
                                                            status="submitting", params=original)
                    node._set_generation_recovery_checkpoint(stage="accepted", task_id=JOB, task_identity="broker_task",
                                                            status="pending", params=original)
                    node.values.update(resume_generation_id=JOB, draft_action=t.DRAFT_ACTION_OFF,
                                       output_format="mp4" if frozen_format == "mov" else "mov", return_last_frame=True)
                    node.parameter_values["resume_generation_id"] = JOB
                    node.bridge.capability_response = {}  # Retrieval needs no fresh format proof.
                    asyncio.run(node._process_generation_impl())
                    self.assertEqual(node.saved[0][1], saved_path)
                    self.assertEqual(node.saved[0][2]["output_format"], frozen_format)
                    self.assertFalse(node.saved[0][2]["return_last_frame"])
                    self.assertEqual(node._generation_recovery_state()["output_file"], saved_path)
                    self.assertEqual(node.bridge.refresh_ids, [JOB])
                    self.assertEqual(node.bridge.posts, [])
                    self.assertEqual(node.bridge.format_resolution_calls, [])

    def test_resume_missing_frozen_draft_path_fails_before_requests(self):
        node = Node()
        node.parameter_values[t.SEEDANCE_RECOVERY_PARAMETER] = t._seedance_recovery_value({
            "task_id": JOB, "task_identity": "broker_task", "stage": "accepted", "status": "pending",
            "draft_action": t.DRAFT_ACTION_PREVIEW, "draft_project": PROJECT,
            "model_id": t.SEEDANCE_2_5_MODEL_ID, "output_format": "mp4", "broker_server_url": ORIGIN})
        node.values["resume_generation_id"] = JOB
        node.parameter_values["resume_generation_id"] = JOB
        with self.assertRaises(t._BrokerProtocolError):
            asyncio.run(node._process_generation_impl())
        self.assertEqual(node.bridge.posts, [])
        self.assertEqual(node.bridge.refresh_ids, [])

    def test_draft_journal_destination_exact_fail_policy_for_refresh_and_run(self):
        for action in (t.DRAFT_ACTION_PREVIEW, t.DRAFT_ACTION_FINAL):
            node = Node()
            path = Path(node.base.name, "frozen-stage.mp4")
            values = params(action)
            values.update(_hmb_output_file=str(path), _hmb_broker_server_url=ORIGIN,
                          _hmb_draft_project=PROJECT, resolution="480p" if action == t.DRAFT_ACTION_PREVIEW else "1080p")
            node._set_generation_recovery_checkpoint(stage="pre_submit", task_id="hmb-stage", task_identity="client_request",
                                                    status="submitting", params=values)
            checkpoint = node._set_generation_recovery_checkpoint(stage="accepted", task_id=JOB, task_identity="broker_task",
                                                                 status="queued", params=values)
            destination = node._build_recovery_output_destination(checkpoint)
            self.assertIsInstance(destination, t._SeedanceDraftOutputDestination)
            self.assertEqual(destination.resolve(), str(path))
            self.assertIs(node._output_destination_policy(destination), t.ExistingFilePolicy.FAIL)
            path.write_bytes(b"EXISTING-DRAFT")
            with self.assertRaises(FileExistsError):
                node._preflight_output_destination(destination, "mp4")
            self.assertEqual(path.read_bytes(), b"EXISTING-DRAFT")

    def test_distinct_paths_fail_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "original.mp4")
            path.write_bytes(b"ORIGINAL")
            destination = t._SeedanceDraftOutputDestination(str(path))
            with self.assertRaises(FileExistsError):
                Node._preflight_output_destination(destination, "mp4")
            self.assertEqual(path.read_bytes(), b"ORIGINAL")


if __name__ == "__main__":
    t.AI_BROKER_SUBMISSION_MIN_INTERVAL_SECONDS = 0.0
    unittest.main()
