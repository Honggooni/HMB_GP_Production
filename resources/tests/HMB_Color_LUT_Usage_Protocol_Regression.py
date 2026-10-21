"""Offline usage protocol: strict metadata, gateway/auth reuse and no POST replay."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
import unittest
import uuid
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import _hmb_color_lut_usage as usage

OPERATION = "12345678-1234-4234-9234-123456789abc"
SETTINGS = {"enabled": False, "precision_version": 2, **dict.fromkeys(usage.STEP_KEYS, 0)}


def event(stage="local_export", **overrides):
    values = dict(export_operation_id=OPERATION, stage=stage, settings=copy.deepcopy(SETTINGS), codec="hevc10",
                  preset_classification="custom", export_sha256="a" * 64)
    if stage == "web_upload":
        values.update(source_task_id="job-" + "b" * 32, upload_idempotency_key="c" * 64)
    values.update(overrides)
    return usage.build_event(**values)


def capabilities(prefix=""):
    return {"schema": usage.CAPABILITIES_SCHEMA, "version": 1, "enabled": True, "ready": True,
        "persistence_scope": "metadata_only", "media_stored": False, "pixel_transform_verified": False,
        "max_body_bytes": 8192, "stages": list(usage.STAGES), "codecs": list(usage.CODECS),
        "preset_classifications": list(usage.PRESET_CLASSES), "settings_precision_version": 2,
        "settings_step": 0.25, "settings_min": -3, "settings_max": 3,
        "local_export_attestation": "client_attested", "web_upload_attestation": "server_upload_receipt",
        "web_upload_enabled": False, "event_path": prefix + usage.EVENTS_API,
        "lookup_path": prefix + usage.EVENTS_API + "/{export_operation_id}/{stage}",
        "count_basis": "distinct_user_export_operation", "_http_status": 200}


def receipt(request, *, created=True, stages=None):
    return {"schema": usage.RECEIPT_SCHEMA, "version": 1, "export_operation_id": request["export_operation_id"],
        "stage": request["stage"], "created": created,
        "attestation_kind": "client_attested" if request["stage"] == "local_export" else "server_upload_receipt",
        **{key: request[key] for key in ("settings_sha256", "export_sha256", "codec", "preset_classification")},
        "recorded_at": 1792551600, "recorded_stages": stages or [request["stage"]], "export_usage_count": 1,
        "count_basis": "distinct_user_export_operation", "pixel_transform_verified": False, "media_stored": False,
        "_http_status": 201 if created else 200}


class TransportError(RuntimeError):
    def __init__(self, status=None):
        # A malicious transport detail must never leak into usage errors.
        super().__init__("token=secret C:/private/source.mov prompt=private")
        self.status_code = status


class FakeBridge:
    def __init__(self, *, prefix="", post_error=None, store_before_error=True, lookup_error=None):
        self.server_url = "https://broker.example.test" + prefix
        self.cap = capabilities(prefix)
        self.calls = []
        self.events = {}
        self.post_error = post_error
        self.store_before_error = store_before_error
        self.lookup_error = lookup_error
        self.invalid_receipt = False

    def _request_json(self, method, path, *, payload, timeout, submission=False):
        self.calls.append((method, path, copy.deepcopy(payload), timeout, submission))
        assert submission is False, "Usage metadata must not enter the media-create submission path"
        assert method in ("GET", "POST")
        if path == usage.CAPABILITIES_API:
            assert method == "GET" and payload is None
            return copy.deepcopy(self.cap)
        if method == "POST":
            assert path == usage.EVENTS_API
            normalized = usage.validate_event(payload)
            key = (normalized["export_operation_id"], normalized["stage"])
            created = key not in self.events
            if self.post_error is None or self.store_before_error:
                self.events[key] = normalized
            if self.post_error is not None:
                raise self.post_error
            result = receipt(normalized, created=created)
            if self.invalid_receipt:
                result["export_sha256"] = "f" * 64
            return result
        assert payload is None
        if self.lookup_error is not None:
            raise self.lookup_error
        operation, stage = path.removeprefix(usage.EVENTS_API + "/").split("/")
        stored = self.events.get((operation, stage))
        if stored is None:
            raise TransportError(404)
        stages = [value for value in usage.STAGES if (operation, value) in self.events]
        return receipt(stored, created=False, stages=stages)


class UsageProtocolTests(unittest.TestCase):
    def reject(self, function, *args, **kwargs):
        with self.assertRaises(usage.ColorLUTUsageError) as result:
            function(*args, **kwargs)
        self.assertNotIn("secret", str(result.exception))
        self.assertNotIn("private", str(result.exception))
        return result.exception

    def test_import_is_offline_and_native_runtime_is_not_loaded(self):
        self.assertNotIn("HMBSeedanceGeneration", sys.modules)
        self.assertNotIn("griptape_nodes", sys.modules)
        with mock.patch("socket.create_connection", side_effect=AssertionError("Unexpected network")), \
                mock.patch.object(Path, "open", side_effect=AssertionError("Unexpected file read")):
            self.assertEqual(usage.validate_event(event())["settings"]["enabled"], False)

    def test_exact_eleven_field_metadata_no_paths_or_user(self):
        value = event()
        self.assertEqual(set(value), usage.EVENT_FIELDS)
        self.assertEqual(len(value), 11)
        self.assertIsNone(value["source_task_id"])
        self.assertIsNone(value["upload_idempotency_key"])
        self.assertLess(len(json.dumps(value).encode()), 8192)
        for forbidden in ("user_id", "prompt", "source_path", "output_path", "video", "token", "api_key", "preset_name"):
            self.reject(usage.validate_event, value | {forbidden: "private"})

    def test_required_fields_not_defaulted(self):
        for field in usage.EVENT_FIELDS:
            value = event()
            del value[field]
            with self.subTest(field=field):
                self.reject(usage.validate_event, value)

    def test_uuid_v4_only_canonical(self):
        for invalid in (uuid.uuid1().hex, str(uuid.uuid1()), OPERATION.upper(), OPERATION.replace("-", ""),
                        "urn:uuid:" + OPERATION, "{" + OPERATION + "}", 0, False, None, [], "../x"):
            with self.subTest(value=invalid):
                self.reject(event, export_operation_id=invalid)
        self.assertEqual(event()["export_operation_id"], OPERATION)

    def test_setting_types_and_quarter_grid_are_strict(self):
        for key in usage.STEP_KEYS:
            for invalid in (True, False, "0", None, [], {}, float("nan"), float("inf"), -3.25, 3.25, 0.1, -0.125):
                value = copy.deepcopy(SETTINGS)
                value[key] = invalid
                with self.subTest(key=key, value=invalid):
                    self.reject(usage.normalize_usage_settings, value)
        for key, invalid in (("enabled", 0), ("enabled", 1), ("enabled", "false"),
                             ("precision_version", True), ("precision_version", 2.0), ("precision_version", 1)):
            self.reject(usage.normalize_usage_settings, SETTINGS | {key: invalid})
        self.reject(usage.normalize_usage_settings, SETTINGS | {"path": "private"})

    def test_all_grid_values_match_gp_numeric_serialization(self):
        from _hmb_color_lut import normalize_settings
        for key in usage.STEP_KEYS:
            for tick in range(-12, 13):
                settings = SETTINGS | {key: tick / 4}
                with self.subTest(key=key, tick=tick):
                    strict = usage.normalize_usage_settings(settings)
                    native = normalize_settings(settings)
                    self.assertEqual(json.dumps(strict, sort_keys=True), json.dumps(native, sort_keys=True))
                    digest = hashlib.sha256(json.dumps(native, ensure_ascii=False, sort_keys=True,
                                                       separators=(",", ":")).encode()).hexdigest()
                    self.assertEqual(usage.settings_sha256(settings), digest)
        normalized = usage.normalize_usage_settings(SETTINGS)
        self.assertIs(normalized["enabled"], False)
        self.assertEqual(type(normalized["exposure"]), float)
        self.assertEqual(json.dumps(normalized["exposure"]), "0.0")
        self.assertEqual(usage.settings_sha256(SETTINGS | {"exposure": -0.0}), usage.settings_sha256(SETTINGS))

    def test_settings_snapshot_is_detached(self):
        settings = copy.deepcopy(SETTINGS)
        value = event(settings=settings)
        settings["exposure"] = 3
        self.assertEqual(value["settings"]["exposure"], 0)
        detached = usage.validate_event(value)
        detached["settings"]["exposure"] = -3
        self.assertEqual(value["settings"]["exposure"], 0)

    def test_hashes_are_required_lowercase_and_settings_bound(self):
        for invalid in (None, "", "A" * 64, "a" * 63, "a" * 65, False, 0, []):
            self.reject(event, export_sha256=invalid)
        value = event()
        value["settings_sha256"] = "b" * 64
        error = self.reject(usage.validate_event, value)
        self.assertEqual(error.code, "COLOR_LUT_USAGE_SETTINGS_HASH_MISMATCH")

    def test_stage_codec_and_classification_all_supported(self):
        for stage in usage.STAGES:
            for codec in usage.CODECS:
                for classification in usage.PRESET_CLASSES:
                    value = event(stage, codec=codec, preset_classification=classification)
                    self.assertEqual(value["codec"], codec)
                    self.assertEqual(value["preset_classification"], classification)
        for key in ("stage", "codec", "preset_classification"):
            for invalid in (None, [], {}, 0, True, "unknown"):
                self.reject(event, **{key: invalid})

    def test_local_export_source_fields_must_be_explicit_null(self):
        self.reject(event, source_task_id="job-" + "a" * 32)
        self.reject(event, upload_idempotency_key="b" * 64)
        self.reject(event, source_task_id="")

    def test_web_source_requires_existing_native_task_and_upload_hash(self):
        self.assertEqual(event("web_upload")["source_task_id"], "job-" + "b" * 32)
        for invalid in (None, "", "job-mybox-" + "b" * 32, "job-" + "B" * 32, "job-new", [], False):
            self.reject(event, "web_upload", source_task_id=invalid)
        for invalid in (None, "", "b" * 63, "B" * 64, [], False):
            self.reject(event, "web_upload", upload_idempotency_key=invalid)

    def test_capabilities_routes_and_http_false_are_not_reinterpreted(self):
        result = usage.validate_capabilities(capabilities())
        self.assertIs(result["web_upload_enabled"], False)
        self.assertNotIn("_http_status", result)
        self.reject(usage.validate_capabilities, capabilities("/GripTapeServer"))
        result = usage.validate_capabilities(capabilities("/GripTapeServer"), server_url="https://example.test/GripTapeServer/")
        self.assertEqual(result["event_path"], "/GripTapeServer" + usage.EVENTS_API)
        for invalid in ("/other", "//host", "/../x", "/%2e%2e", "/x?secret", "https://evil.test"):
            value = capabilities(invalid)
            self.reject(usage.validate_capabilities, value, server_url="https://example.test/GripTapeServer")
        for url in ("https://user:secret@broker.test", "https://broker.test?secret=1", "https://broker.test/#secret"):
            self.reject(usage.validate_capabilities, capabilities(), server_url=url)

    def test_capability_fields_are_strict(self):
        for key, invalid in (("schema", "other"), ("version", True), ("enabled", 1), ("ready", 0),
                             ("web_upload_enabled", 0), ("media_stored", 0), ("pixel_transform_verified", 0),
                             ("max_body_bytes", 8192.0), ("settings_min", True), ("settings_max", float("nan")),
                             ("stages", list(reversed(usage.STAGES))), ("lookup_path", "/wrong")):
            with self.subTest(key=key):
                self.reject(usage.validate_capabilities, capabilities() | {key: invalid})
        self.reject(usage.validate_capabilities, capabilities() | {"user_id": 99})
        for key in usage.CAPABILITIES_FIELDS:
            value = capabilities()
            del value[key]
            self.reject(usage.validate_capabilities, value)

    def test_receipts_bind_operation_stage_snapshot_and_attestation(self):
        for stage in usage.STAGES:
            request = event(stage)
            self.assertEqual(usage.validate_receipt(receipt(request), request)["stage"], stage)
            for key, invalid in (("export_operation_id", str(uuid.uuid4())), ("stage", "other"),
                                 ("settings_sha256", "f" * 64), ("export_sha256", "f" * 64),
                                 ("codec", "prores"), ("preset_classification", "personal"),
                                 ("attestation_kind", "server_verified_pixels")):
                self.reject(usage.validate_receipt, receipt(request) | {key: invalid}, request)

    def test_receipts_keep_created_false_and_ordered_stage_growth(self):
        request = event()
        first = usage.validate_receipt(receipt(request, created=False), request, lookup=True)
        later = usage.validate_receipt(receipt(request, created=False, stages=list(usage.STAGES)), request, lookup=True)
        self.assertIs(first["created"], False)
        self.assertEqual(later["recorded_stages"], list(usage.STAGES))
        for invalid in (["local_export", "local_export"], ["web_upload"], list(reversed(usage.STAGES)), [], "local_export"):
            self.reject(usage.validate_receipt, receipt(request) | {"recorded_stages": invalid}, request)

    def test_receipt_types_and_no_extra_data(self):
        request = event()
        for key, invalid in (("version", True), ("created", 0), ("recorded_at", True), ("recorded_at", -1),
                             ("export_usage_count", True), ("export_usage_count", 2), ("media_stored", 0),
                             ("pixel_transform_verified", 0), ("_http_status", True)):
            self.reject(usage.validate_receipt, receipt(request) | {key: invalid}, request)
        self.reject(usage.validate_receipt, receipt(request) | {"source_path": "private"}, request)
        self.reject(usage.validate_receipt, receipt(request), request, lookup=True)
        self.reject(usage.validate_receipt, receipt(request) | {"_http_status": 200}, request)

    def test_successful_post_uses_shared_bridge_fixed_gateway_relative_routes(self):
        bridge = FakeBridge(prefix="/GripTapeServer")
        result = usage.submit_event(bridge, event())
        self.assertTrue(result["created"])
        self.assertEqual([(call[0], call[1]) for call in bridge.calls], [("GET", usage.CAPABILITIES_API), ("POST", usage.EVENTS_API)])
        self.assertTrue(all(call[4] is False for call in bridge.calls))
        self.assertEqual(bridge.server_url, "https://broker.example.test/GripTapeServer")

    def test_prefetched_capabilities_are_revalidated(self):
        bridge = FakeBridge()
        usage.submit_event(bridge, event(), capabilities=capabilities())
        self.assertEqual([call[0] for call in bridge.calls], ["POST"])
        bridge = FakeBridge()
        self.reject(usage.submit_event, bridge, event(), capabilities=capabilities() | {"ready": False})
        self.assertEqual(bridge.calls, [])

    def test_unavailable_capabilities_never_send_event(self):
        for flag in ("enabled", "ready"):
            bridge = FakeBridge()
            bridge.cap[flag] = False
            self.reject(usage.submit_event, bridge, event())
            self.assertEqual([call[0] for call in bridge.calls], ["GET"])
        bridge = mock.Mock(server_url="https://broker.test")
        bridge._request_json.side_effect = TransportError(404)
        error = self.reject(usage.submit_event, bridge, event())
        self.assertEqual(error.code, "COLOR_LUT_USAGE_UNAVAILABLE")
        self.assertEqual(bridge._request_json.call_count, 1)

    def test_false_media_upload_flag_does_not_disable_usage_metadata(self):
        bridge = FakeBridge()
        self.assertIs(bridge.cap["web_upload_enabled"], False)
        result = usage.submit_event(bridge, event("web_upload"))
        self.assertEqual(result["attestation_kind"], "server_upload_receipt")
        self.assertTrue(all("generate" not in call[1] and "derivatives" not in call[1] for call in bridge.calls))

    def test_timeout_after_acceptance_only_gets_same_uuid_stage(self):
        bridge = FakeBridge(post_error=TransportError())
        request = event()
        result = usage.submit_event(bridge, request)
        self.assertFalse(result["created"])
        self.assertEqual([call[0] for call in bridge.calls], ["GET", "POST", "GET"])
        self.assertEqual(bridge.calls[-1][1], usage.EVENTS_API + "/" + OPERATION + "/local_export")
        self.assertEqual(bridge.calls[1][2], request)

    def test_conflict_only_retrieves_same_operation_never_creates_new_key(self):
        bridge = FakeBridge(post_error=TransportError(409))
        result = usage.submit_event(bridge, event())
        self.assertEqual(result["export_operation_id"], OPERATION)
        self.assertEqual(sum(call[0] == "POST" for call in bridge.calls), 1)

    def test_unknown_get404_is_pending_no_automatic_post_retry(self):
        bridge = FakeBridge(post_error=TransportError(), store_before_error=False)
        error = self.reject(usage.submit_event, bridge, event())
        self.assertEqual(error.code, "COLOR_LUT_USAGE_SUBMISSION_PENDING")
        self.assertTrue(error.submission_outcome_unknown)
        self.assertEqual(error.status_code, 404)
        self.assertEqual(sum(call[0] == "POST" for call in bridge.calls), 1)
        error = self.reject(usage.retrieve_event, bridge, event())
        self.assertEqual(error.code, "COLOR_LUT_USAGE_EVENT_NOT_FOUND")
        self.assertEqual(sum(call[0] == "POST" for call in bridge.calls), 1)

    def test_definitive_http_rejection_does_not_lookup_or_retry(self):
        for status in (400, 401, 403, 404, 405, 413, 415, 422, 429):
            bridge = FakeBridge(post_error=TransportError(status), store_before_error=False)
            error = self.reject(usage.submit_event, bridge, event())
            self.assertEqual(error.code, "COLOR_LUT_USAGE_SUBMISSION_REJECTED")
            self.assertEqual(error.status_code, status)
            self.assertFalse(error.submission_outcome_unknown)
            self.assertEqual([call[0] for call in bridge.calls], ["GET", "POST"])

    def test_server_error_and_invalid_post_receipt_recover_by_get(self):
        for status in (500, 502, 503):
            bridge = FakeBridge(post_error=TransportError(status))
            self.assertFalse(usage.submit_event(bridge, event())["created"])
            self.assertEqual([call[0] for call in bridge.calls], ["GET", "POST", "GET"])
        bridge = FakeBridge()
        bridge.invalid_receipt = True
        self.assertFalse(usage.submit_event(bridge, event())["created"])

    def test_recovered_receipt_mismatch_remains_pending(self):
        bridge = FakeBridge(post_error=TransportError(409), store_before_error=False)
        bridge.events[(OPERATION, "local_export")] = event(export_sha256="f" * 64)
        error = self.reject(usage.submit_event, bridge, event())
        self.assertTrue(error.submission_outcome_unknown)
        self.assertEqual(sum(call[0] == "POST" for call in bridge.calls), 1)

    def test_lookup_has_no_capability_or_post_side_effect(self):
        bridge = FakeBridge()
        request = event()
        bridge.events[(OPERATION, "local_export")] = request
        self.assertFalse(usage.retrieve_event(bridge, request)["created"])
        self.assertEqual([call[0] for call in bridge.calls], ["GET"])

    def test_two_success_stages_keep_one_export_operation(self):
        bridge = FakeBridge()
        usage.submit_event(bridge, event())
        second = usage.submit_event(bridge, event("web_upload"))
        self.assertEqual(second["recorded_stages"], ["web_upload"])
        result = usage.retrieve_event(bridge, event())
        self.assertEqual(result["recorded_stages"], list(usage.STAGES))
        self.assertEqual(result["export_usage_count"], 1)
        self.assertEqual(len({key[0] for key in bridge.events}), 1)

    def test_invalid_input_rejected_before_transport(self):
        bridge = FakeBridge()
        self.reject(usage.submit_event, bridge, event() | {"prompt": "private"})
        self.assertEqual(bridge.calls, [])
        for invalid in (0, -1, True, "15", float("nan"), float("inf"), 61, 10**1000):
            self.reject(usage.submit_event, bridge, event(), timeout=invalid)
        self.assertEqual(bridge.calls, [])

    def test_optional_readonly_server_contract_parity(self):
        path = os.environ.get("HMB_LUT_USAGE_SERVER_CONTRACT")
        if not path:
            self.skipTest("Set HMB_LUT_USAGE_SERVER_CONTRACT for read-only server source parity")
        spec = importlib.util.spec_from_file_location("_hmb_test_server_usage_contract", path)
        server = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(server)
        for stage in usage.STAGES:
            for tick in range(-12, 13):
                request = event(stage, settings=SETTINGS | {"exposure": tick / 4})
                canonical, _, _ = server._validate(request)
                self.assertEqual(json.dumps(canonical, sort_keys=True), json.dumps(usage.validate_event(request), sort_keys=True))
        for constant in ("EVENT_FIELDS", "SETTINGS_FIELDS", "STAGES", "CODECS", "PRESET_CLASSES", "MAX_BODY_BYTES"):
            self.assertEqual(getattr(usage, constant), getattr(server, constant))


if __name__ == "__main__":
    unittest.main(verbosity=2)
