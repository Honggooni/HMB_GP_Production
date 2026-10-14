"""Offline real-code transport and lifecycle checks; no SDK/server/model required."""
from __future__ import annotations

import ast
import hashlib
import ipaddress
import json
import re
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from contextlib import suppress
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch
from urllib.parse import quote, urlencode, urlparse
from uuid import UUID

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import _hmb_review as review

CAPABILITIES = {"schema": "hmb-review-portal", "version": 1, "review_portal": True,
                "page_url": "/reviews", "page_size": 20, "retention_days": 30,
                "can_view_all": False, "access_scope": "own"}


def production_namespace(queued: list, opened: list, tokens: list) -> dict:
    """Compile unchanged production methods, replacing only host/HTTP boundaries."""
    tree = ast.parse((ROOT / "HMBSeedanceGeneration.py").read_text(encoding="utf-8"))
    names = {"_BrokerError", "_BrokerUnavailableError", "_BrokerAuthenticationError", "_BrokerProtocolError",
             "_broker_validated_server_url", "_broker_read_json", "_broker_require_exact_response_url",
             "_captured_display_title_operation_id", "_captured_display_title_request",
             "_validate_captured_display_title_request", "_validate_captured_display_title_response"}
    definitions = [item for item in tree.body if isinstance(item, (ast.FunctionDef, ast.ClassDef)) and item.name in names]
    bridge = next(item for item in tree.body if isinstance(item, ast.ClassDef) and item.name == "_HMBAIBrokerBridge")
    methods = {"__init__", "server_url", "_review_task_path", "review_capabilities", "put_task_casecard", "get_task_casecard",
               "get_task_captured_title", "post_task_captured_title", "post_task_feedback", "task_feedback",
               "_load_access_token", "_clear_access_token", "_request_json"}
    definitions.append(ast.ClassDef(name="Bridge", bases=[], keywords=[], decorator_list=[], body=[
        item for item in bridge.body if isinstance(item, ast.FunctionDef) and item.name in methods]))
    node = next(item for item in tree.body if isinstance(item, ast.ClassDef) and item.name == "HMBSeedanceGeneration")
    methods = {"_review_origin_for_task", "_review_sync_is_live", "_sync_review_task", "_schedule_review_sync",
               "_schedule_open_review_gallery", "_validate_task_id", "_set_captured_title_sync_state",
               "_sync_captured_display_title"}
    definitions.append(ast.ClassDef(name="PortalNode", bases=[], keywords=[], decorator_list=[], body=[
        item for item in node.body if isinstance(item, ast.FunctionDef) and item.name in methods]))
    class DeferredThread:
        def __init__(self, *, target, **_kwargs):
            self.target = target
        def start(self):
            queued.append(self.target)
    def token(**kwargs):
        tokens.append(kwargs.get("server_url", "default"))
        return "credential-canary"
    namespace = dict(globals(), _review=review, _TASK_ID_PATTERN=review._TASK_ID,
        AI_BROKER_SERVER_URL="https://default.example", AI_BROKER_INTERNAL_ORIGIN="http://internal.example",
        MAX_REQUEST_BYTES=64 * 1024 * 1024, AI_BROKER_MAX_JSON_BYTES=2 * 1024 * 1024,
        _broker_load_token=token, _broker_clear_token=lambda **_kwargs: None,
        _broker_log_transport_error=lambda **_kwargs: None,
        _broker_build_opener=lambda: (_ for _ in ()).throw(AssertionError("Real network opener requested")),
        logger=SimpleNamespace(warning=lambda *_args: None),
        webbrowser=SimpleNamespace(open=lambda url, **_kwargs: opened.append(url)),
        threading=SimpleNamespace(Lock=threading.Lock, Thread=DeferredThread),
        GriptapeNodes=SimpleNamespace(EventManager=lambda: SimpleNamespace(event_loop=None)))
    for item in tree.body:
        if (isinstance(item, ast.Assign) and len(item.targets) == 1 and isinstance(item.targets[0], ast.Name)
                and item.targets[0].id in {"SEEDANCE_2_0_MODEL_ID", "SEEDANCE_2_0_FAST_MODEL_ID", "SEEDANCE_2_5_MODEL_ID"}):
            namespace[item.targets[0].id] = ast.literal_eval(item.value)
    module = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0),
                             *definitions], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), "<actual-review-portal-methods>", "exec"), namespace)
    return namespace


class Response:
    def __init__(self, url, payload, status=200):
        self.url, self.status = url, status
        self.data = json.dumps(payload).encode()
    def geturl(self):
        return self.url
    def read(self, limit):
        return self.data[:limit]
    def __enter__(self):
        return self
    def __exit__(self, *_args):
        pass


class FakePortal:
    """The explicit v1 wire contract, not a generation/provider substitute."""
    def __init__(self, ns):
        self.ns, self.calls, self.casecards, self.reviews = ns, [], {}, {}
        self.capabilities = deepcopy(CAPABILITIES)
        self.feedback_pages = [{"items": [], "has_more": False}]
        self.hook = None
        self.failure = None
        self.ack_task = None
        self.ack_modifier = None
        self.titles = {}
        self.title_failure = None
        self.title_ack_modifier = None
        self.casecard_get_failure = None
    def open(self, request, *, timeout):
        assert 0 < timeout <= 5
        parsed = urlparse(request.full_url)
        assert parsed.path.startswith("/api/v1/reviews/")
        assert "/generate/" not in parsed.path and "/refresh" not in parsed.path
        assert "credential-canary" not in request.full_url
        assert request.get_header("Authorization") == "Bearer credential-canary"
        body = json.loads(request.data) if request.data else None
        call = {"method": request.method, "origin": parsed.scheme + "://" + parsed.netloc,
                "path": parsed.path, "query": parsed.query, "body": body,
                "idempotency_key": request.get_header("Idempotency-key")}
        self.calls.append(call)
        if self.hook:
            self.hook(call)
        if self.failure:
            raise self.failure
        if parsed.path.endswith("/capabilities"):
            return Response(request.full_url, self.capabilities)
        task = parsed.path.split("/")[-2]
        if parsed.path.endswith("/casecard"):
            if request.method == "GET":
                if self.casecard_get_failure:
                    raise self.casecard_get_failure
                return Response(request.full_url, {"task_id": self.ack_task or task,
                    "casecard": deepcopy(self.casecards.get(task))})
            assert request.method == "PUT"
            assert body == review.public_evidence(body), "Wire evidence must be the exact public projection"
            assert set(body) == {"schema", "version", "case_id", "input_evidence_sha256", "client_prompt_sha256",
                                 "project_id", "project_name",
                                 "build", "shot", "settings", "references", "agent_observation"}
            assert call["idempotency_key"] == review._digest(body)
            previous = self.casecards.get(task)
            if previous is not None and previous != body:
                raise self.ns["_BrokerError"]("Conflicting immutable casecard", status_code=409)
            self.casecards[task] = deepcopy(body)
            result = {"task_id": self.ack_task or task, "casecard": body, "created": previous is None}
            if self.ack_modifier:
                result = self.ack_modifier(result)
            return Response(request.full_url, result, 200 if previous else 201)
        if parsed.path.endswith("/captured-title"):
            if self.title_failure:
                raise self.title_failure
            if request.method == "GET":
                result = {"schema": "hmb-captured-display-title", "version": 1, "task_id": task,
                          "captured_title": deepcopy(self.titles.get(task))}
                if self.title_ack_modifier:
                    result = self.title_ack_modifier(result)
                return Response(request.full_url, result)
            assert request.method == "POST"
            assert set(body) == {"schema", "version", "operation_id", "name", "expected_casecard_sha256",
                                 "case_id", "input_evidence_sha256", "project_id", "project_name", "provider", "model", "shot"}
            assert str(UUID(body["operation_id"])) == body["operation_id"] == call["idempotency_key"]
            assert review._digest(self.casecards[task]) == body["expected_casecard_sha256"]
            previous = self.titles.get(task)
            if previous and (previous["name"] != body["name"] or previous["operation_id"] != body["operation_id"]):
                raise self.ns["_BrokerError"]("Conflicting captured title", status_code=409)
            title = {"operation_id": body["operation_id"], "name": body["name"],
                     "provenance": "owner_attested_creation_snapshot", "verified_generation_input": False,
                     "created_at": 1791949727}
            self.titles[task] = deepcopy(title)
            result = {"schema": "hmb-captured-display-title", "version": 1, "task_id": task,
                      "created": previous is None, "captured_title": title}
            if self.title_ack_modifier:
                result = self.title_ack_modifier(result)
            return Response(request.full_url, result, 200 if previous else 201)
        assert parsed.path.endswith("/feedback")
        if request.method == "POST":
            identity = body["client_review_id"]
            assert str(UUID(identity)) == identity == call["idempotency_key"]
            assert set(body) == {"client_review_id", "score", "category", "note", "input_evidence_sha256", "library_version"}
            if identity in self.reviews and self.reviews[identity] != body:
                raise self.ns["_BrokerError"]("Conflicting review identity", status_code=409)
            status = 200 if identity in self.reviews else 201
            self.reviews[identity] = deepcopy(body)
            return Response(request.full_url, {"task_id": task, "client_review_id": identity}, status)
        return Response(request.full_url, self.feedback_pages.pop(0) if len(self.feedback_pages) > 1 else self.feedback_pages[0])


def main() -> None:
    queued, opened, tokens = [], [], []
    ns = production_namespace(queued, opened, tokens)
    portal = FakePortal(ns)
    class Node(ns["PortalNode"]):
        def __init__(self):
            self.name, self.alive, self.selected = "OfflinePortal", True, "https://new.example"
            self._hmb_review_sync_epoch, self.checkpoint = 0, {}
            self._hmb_review_sync_lock, self._hmb_review_sync_jobs = threading.Lock(), set()
            self.values, self.published = {"status_details": "render succeeded"}, []
            self._generation_run_active = threading.Event()
        def _runtime_node_is_live(self, **_kwargs):
            return self.alive
        def _selected_broker_server_url(self):
            return self.selected
        def _generation_recovery_state(self):
            return self.checkpoint
        def _create_broker_bridge(self, *, server_url):
            return ns["Bridge"](opener=portal, server_url=server_url)
        def _authoritative_existing_generation_id(self):
            return self.checkpoint.get("task_id", "")
        def get_parameter_value(self, name):
            return self.values.get(name)
        def set_parameter_value(self, name, value):
            self.values[name] = value
        def publish_update_to_parameter(self, name, value):
            self.published.append((name, value))
    checks = 0
    with tempfile.TemporaryDirectory(prefix="hmb-portal-client-") as directory:
        base = Path(directory)
        original_root = review.review_root
        with patch.object(review, "review_root", side_effect=lambda root=None: original_root(root or base)), \
             patch("socket.create_connection", side_effect=AssertionError("External network forbidden")), \
             patch("socket.socket.connect", side_effect=AssertionError("External network forbidden")):
            case = review.start_case("client-a", {"settings": {"model_id": "seedance-2.5", "duration": 5},
                "references": [{"role": "video", "kind": "local", "path": "C:/private/source.mp4",
                                "source_identity_sha256": "1" * 64, "content_sha256": "2" * 64}],
                "generation_origin": {"channel_uuid": "channel-a", "shot_uuid": "shot-a", "number": 2,
                                      "name": "컷 02 · 원본 이름 🎬"}},
                "SERVER PROMPT MUST NOT BE OVERWRITTEN", {"library_version": "0.7.82", "runtime": {"fingerprint_sha256": "3" * 64}},
                {"run_id": "agent-a", "coverage": [{"media_token": "@video1", "observation_role": "original",
                  "bundle_run_id": "bundle-a", "sample_group_id": "pair-a", "decoded_pts_seconds": 2.125,
                  "requested_seek_seconds": 2., "pts_status": "observed", "url": "https://private/?token=SECRET"}],
                 "skips": [{"reason": "remote_fetch_disabled", "source_uid": "depth-a"}]})
            review.update_case("task-a", case_id=case, status="succeeded")
            review.bind_task_origin("task-a", "https://old.example")
            node = Node()
            node.checkpoint = {"task_id": "current-new-task", "broker_server_url": node.selected}
            assert node._review_origin_for_task("task-a") == "https://old.example"
            assert not node._schedule_review_sync("unknown-historical-task") and not portal.calls
            checks += 2
            assert node._schedule_review_sync("task-a") and not node._schedule_review_sync("task-a")
            assert not portal.calls, "Scheduling must acknowledge before HTTP work"
            queued.pop(0)()
            assert review.read_case("task-a")["server_sync"]["status"] == "synced"
            assert all(call["origin"] == "https://old.example" for call in portal.calls)
            wire = portal.casecards["task-a"]
            assert wire["agent_observation"]["coverage"][0]["decoded_pts_seconds"] == 2.125
            assert wire["shot"]["shot_uuid"] == "shot-a"
            assert wire["shot"]["name"] == "컷 02 · 원본 이름 🎬"
            assert not any(v in json.dumps(wire) for v in ("SECRET", "private", "C:/", "SERVER PROMPT"))
            assert tokens and set(tokens) == {"https://old.example"}
            checks += 6
            put_count = sum(call["method"] == "PUT" for call in portal.calls)
            node._sync_review_task("task-a", "https://old.example", 0)
            assert sum(call["method"] == "PUT" for call in portal.calls) == put_count
            assert review.read_case("task-a")["server_sync"]["status"] == "synced", "Identical retry cannot leave pending"
            checks += 2
            # Pre-name bindings keep their immutable payload, including when a
            # prior login failure erased the old client's local sync digest.
            for known_digest, sparse in ((True, False), (False, False), (True, True), (False, True)):
                suffix = ("known" if known_digest else "lost") + ("-sparse" if sparse else "")
                task = "legacy-task-" + suffix
                frozen = review.capture_inputs({"_hmb_generation_origin": {
                    "channel_uuid": "legacy-channel", "shot_uuid": "legacy-shot", "number": 1,
                    "name": "생성 당시 슬롯 이름"}})
                original_case = review.start_case("legacy-client-" + suffix, frozen, "original", {}, None if sparse else {})
                review.update_case(task, case_id=original_case, status="succeeded")
                review.bind_task_origin(task, "https://old.example")
                old = review.public_evidence(review.read_case(task))
                old["shot"].pop("name")
                old_wire = review.public_evidence(old)
                portal.casecards[task] = deepcopy(old_wire)
                if known_digest:
                    review.mark_server_sync(task, status="synced", evidence_sha256=review._digest(old))
                else:
                    review.mark_server_sync(task, status="login_required")
                before_record = review.read_case(task)
                local_feedback = review.save_review(task, score=4, category="identity", note="retained review")
                before_calls = len(portal.calls)
                node._sync_review_task(task, "https://old.example", 0)
                calls = portal.calls[before_calls:]
                assert not any(call["method"] == "PUT" for call in calls)
                assert sum(call["method"] == "GET" and call["path"].endswith("/casecard") for call in calls) == (not known_digest)
                after_record = review.read_case(task)
                assert after_record["server_sync"]["status"] == "synced"
                assert after_record["server_sync"]["evidence_sha256"] == review._digest(old)
                assert after_record["inputs"] == before_record["inputs"]
                assert after_record["input_evidence_sha256"] == before_record["input_evidence_sha256"]
                assert after_record["reviews"][0]["server_sync"]["status"] == "synced"
                assert portal.casecards[task] == old_wire
                checks += 8
                if not known_digest:
                    # Only the absent name can differ; another source/hash
                    # difference remains a failure and cannot write metadata.
                    portal.casecards[task]["client_prompt_sha256"] = "f" * 64
                    review.mark_server_sync(task, status="failed", evidence_sha256="a" * 64)
                    before_calls = len(portal.calls)
                    node._sync_review_task(task, "https://old.example", 0)
                    assert review.read_case(task)["server_sync"]["status"] == "failed"
                    assert not any(call["method"] != "GET" for call in portal.calls[before_calls:])
                    assert review.read_case(task)["inputs"] == before_record["inputs"]
                    checks += 3
            portal.reviews.clear()
            bridge = ns["Bridge"](opener=portal, server_url="https://old.example")
            assert bridge.get_task_casecard("task-a") == wire
            portal.ack_task = "foreign-task"
            try:
                bridge.get_task_casecard("task-a")
            except ns["_BrokerProtocolError"]:
                checks += 1
            else:
                raise AssertionError("Foreign Task casecard GET accepted")
            portal.ack_task = None
            assert bridge.put_task_casecard("task-a", wire)["_http_status"] == 200
            for modifier in (lambda result: {**result, "task_id": "foreign-task"},
                             lambda result: {**result, "casecard": {**result["casecard"], "client_prompt_sha256": "f" * 64}},
                             lambda result: {**result, "casecard": None},
                             lambda result: {**result, "created": "true"}):
                portal.ack_modifier = modifier
                try:
                    bridge.put_task_casecard("task-a", wire)
                except ns["_BrokerProtocolError"]:
                    checks += 1
                else:
                    raise AssertionError("Foreign, partial or forged casecard ACK accepted")
            portal.ack_modifier = None
            local = review.save_review("task-a", score=2, category="motion", note="Feedback from older native client")
            assert bridge.post_task_feedback("task-a", local, library_version="0.7.82")["_http_status"] == 201
            assert bridge.post_task_feedback("task-a", local, library_version="0.7.82")["_http_status"] == 200 and len(portal.reviews) == 1
            try:
                bridge.post_task_feedback("task-a", {**local, "note": "changed content"}, library_version="0.7.82")
            except ns["_BrokerError"] as exc:
                assert exc.status_code == 409
            else:
                raise AssertionError("Conflicting review ID accepted")
            checks += 4
            node._sync_review_task("task-a", "https://old.example", 0)
            assert review.read_case("task-a")["reviews"][0]["server_sync"]["status"] == "synced"
            web_review = {"client_review_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "task_id": "task-a",
                          "score": 4, "category": "camera", "note": "Web feedback"}
            portal.feedback_pages = [{"items": [web_review], "has_more": True, "next_cursor": "opaque /?cursor"},
                                     {"items": [], "has_more": False}]
            node._sync_review_task("task-a", "https://old.example", 0)
            assert review.read_server_feedback("task-a")["items"][0]["note"] == "Web feedback"
            assert review.read_case("task-a")["reviews"][0]["note"] == local["note"]
            assert portal.calls[-1]["query"] == "cursor=opaque+%2F%3Fcursor"
            checks += 4
            node.checkpoint = {"task_id": "task-a", "broker_server_url": "https://new.example"}
            assert not node._schedule_review_sync("task-a"), "Conflicting Task namespace must fail closed"
            checks += 1
            node.checkpoint = {}
            for exception, status in ((ns["_BrokerError"]("unsupported", status_code=404), "unsupported"),
                                      (ns["_BrokerAuthenticationError"]("expired", status_code=401), "login_required"),
                                      (ns["_BrokerUnavailableError"]("offline"), "failed")):
                portal.failure = exception
                node._sync_review_task("task-a", "https://old.example", 0)
                assert review.read_case("task-a")["server_sync"]["status"] == status
                assert review.read_case("task-a")["status"] == "succeeded"
                checks += 1
            portal.failure = None
            portal.capabilities["page_url"] = "https://evil.example/reviews"
            before_put = len(portal.casecards)
            node._sync_review_task("task-a", "https://old.example", 0)
            assert review.read_case("task-a")["server_sync"]["status"] == "failed" and len(portal.casecards) == before_put
            portal.capabilities = deepcopy(CAPABILITIES)
            checks += 1
            # No persistence or further request after a deleted/replaced node's in-flight result.
            portal.hook = lambda _call: setattr(node, "alive", False)
            before = len(portal.calls)
            node._sync_review_task("task-a", "https://old.example", 0)
            assert len(portal.calls) == before + 1 and review.read_case("task-a")["server_sync"]["status"] == "pending"
            portal.hook = None
            node.alive = True
            unsynced = review.save_review("task-a", score=3, category="other", note="Cancel while posting")
            def cancel_post(call):
                if call["method"] == "POST":
                    node.alive = False
                    raise ns["_BrokerUnavailableError"]("cancelled request")
            portal.hook = cancel_post
            node._sync_review_task("task-a", "https://old.example", 0)
            assert "server_sync" not in review.read_case("task-a")["reviews"][-1]
            portal.hook = None
            node.alive = True
            checks += 2
            # Queued browser launch uses this node only, never a credential/query or stale setting.
            node._schedule_open_review_gallery(node.selected)
            assert not opened
            queued.pop(0)()
            assert opened == ["https://new.example/reviews"]
            node._schedule_open_review_gallery(node.selected)
            node.selected = "https://another.example"
            queued.pop(0)()
            assert len(opened) == 1
            node._schedule_open_review_gallery(node.selected)
            node._hmb_review_sync_epoch += 1
            queued.pop(0)()
            assert len(opened) == 1
            checks += 3
            portal.feedback_pages = [{"items": [web_review], "has_more": True, "next_cursor": "repeat"}]
            try:
                bridge.task_feedback("task-a")
            except ns["_BrokerProtocolError"]:
                pass
            else:
                raise AssertionError("Repeated cursor accepted")
            assert bridge.task_feedback("task-a", is_live=lambda: False)["cancelled"]
            portal.feedback_pages = [{"items": [], "task_id": "other-task", "has_more": False}]
            try:
                bridge.task_feedback("task-a")
            except ns["_BrokerProtocolError"]:
                pass
            else:
                raise AssertionError("Foreign Task feedback accepted")
            checks += 3
            # An old task can retrieve server-owned feedback without inventing
            # evidence from today's selected media or settings.
            review.bind_task_origin("historic-only", "https://old.example")
            portal.feedback_pages = [{"items": [{**web_review, "task_id": "historic-only"}], "has_more": False}]
            before = len(portal.calls)
            node._sync_review_task("historic-only", "https://old.example", node._hmb_review_sync_epoch)
            assert review.read_case("historic-only") is None
            assert review.read_server_feedback("historic-only")["items"][0]["note"] == "Web feedback"
            assert all(call["method"] == "GET" for call in portal.calls[before:])
            checks += 3
            portal.feedback_pages = [{"items": [web_review] * 20, "has_more": True, "next_cursor": f"page-{index}"}
                                     for index in range(5)]
            before = len(portal.calls)
            bounded = bridge.task_feedback("task-a")
            assert len(bounded["items"]) == 100 and bounded["has_more"] and len(portal.calls) == before + 5
            checks += 1
            # Optional captured titles enrich display only. Legacy input records
            # remain byte-for-byte authoritative and no generation route is used.
            captured_checks = 0
            supported = {**CAPABILITIES, "captured_title_supported": True,
                         "captured_title_schema": "hmb-captured-display-title", "captured_title_version": 1}
            portal.capabilities, portal.feedback_pages = deepcopy(supported), [{"items": [], "has_more": False}]
            node = Node()
            def captured_case(task, *, name="생성 때 수정한 이름 🎬", sparse=False, known=True, embedded=False):
                frozen = review.capture_inputs({"project_id": "katuri8", "project_name": "까투리8",
                    "model_id": ns["SEEDANCE_2_5_MODEL_ID"], "resolution": "480p", "duration": 4,
                    "_hmb_generation_origin": {"channel_uuid": "11111111-1111-4111-8111-111111111111",
                        "shot_uuid": "22222222-2222-4222-8222-222222222222", "number": 4,
                        "source_node_instance_id": "33333333-3333-4333-8333-333333333333", "name": name}})
                cid = review.start_case("client-" + task, frozen, "IMMUTABLE PROMPT", {}, None if sparse else {})
                review.update_case(task, case_id=cid, status="succeeded")
                review.bind_task_origin(task, "https://old.example")
                original = review.read_case(task)
                public = review.public_evidence(original)
                legacy = deepcopy(public)
                legacy["shot"].pop("name", None)
                portal.casecards[task] = review.public_evidence(public if embedded else legacy)
                if known:
                    review.mark_server_sync(task, status="synced", evidence_sha256=review._digest(public if embedded else legacy))
                return review.read_case(task), legacy
            for known, sparse in ((True, False), (False, False), (True, True), (False, True)):
                task = f"captured-{int(known)}-{int(sparse)}"
                original, legacy = captured_case(task, known=known, sparse=sparse)
                node.checkpoint = {"task_id": task}
                before = len(portal.calls)
                node._sync_review_task(task, "https://old.example", 0)
                calls = portal.calls[before:]
                posts = [c for c in calls if c["path"].endswith("/captured-title") and c["method"] == "POST"]
                assert len(posts) == 1
                post = posts[0]
                assert any(c["path"].endswith("/casecard") and c["method"] == "GET" for c in calls), "Known digest cannot replace authenticated whole-casecard GET"
                assert not any(c["method"] == "PUT" for c in calls)
                assert all(c["origin"] == "https://old.example" for c in calls)
                assert post["body"]["name"] == "생성 때 수정한 이름 🎬"
                assert post["body"]["expected_casecard_sha256"] == review._digest(portal.casecards[task])
                assert post["body"]["model"] == ns["SEEDANCE_2_5_MODEL_ID"] and post["body"]["provider"] == "volcengine_ark"
                assert "name" not in post["body"]["shot"]
                assert not any(text in json.dumps(post["body"]) for text in ("IMMUTABLE PROMPT", "private", "http", "credential-canary"))
                after = review.read_case(task)
                assert after["inputs"] == original["inputs"] and after["input_evidence_sha256"] == original["input_evidence_sha256"]
                assert after["server_sync"]["evidence_sha256"] == review._digest(legacy)
                assert portal.casecards[task] == review.public_evidence(legacy)
                assert node._hmb_captured_title_sync_state["status"] == "synced"
                assert portal.titles[task]["verified_generation_input"] is False
                payload = ns["_captured_display_title_request"](task, original, portal.casecards[task])
                assert str(UUID(payload["operation_id"])) == payload["operation_id"] == post["idempotency_key"]
                assert UUID(payload["operation_id"]).version == 5
                assert payload == ns["_captured_display_title_request"](task, original, portal.casecards[task])
                # Direct replay acknowledges the same exact operation with HTTP 200.
                assert bridge.post_task_captured_title(task, payload)["_http_status"] == 200
                before_posts = sum(c["method"] == "POST" and c["path"].endswith("/captured-title") for c in portal.calls)
                node._sync_review_task(task, "https://old.example", 0)
                assert sum(c["method"] == "POST" and c["path"].endswith("/captured-title") for c in portal.calls) == before_posts
                assert bridge.get_task_captured_title(task)["name"] == payload["name"]
                captured_checks += 18
            # Embedded names need no title endpoint. Capability negotiation is
            # independent of normal review/casecard/feedback compatibility.
            original, legacy = captured_case("captured-embedded", embedded=True)
            before = len(portal.calls)
            node._sync_review_task("captured-embedded", "https://old.example", 0)
            assert not any(c["path"].endswith("/captured-title") for c in portal.calls[before:])
            assert node._hmb_captured_title_sync_state["status"] == "embedded"
            captured_checks += 2
            for capability in (CAPABILITIES, {**supported, "captured_title_supported": False},
                               {**supported, "captured_title_schema": "foreign"},
                               {**supported, "captured_title_version": True}):
                portal.capabilities = deepcopy(capability)
                task = "captured-unsupported"
                original, legacy = captured_case(task)
                before = len(portal.calls)
                node._sync_review_task(task, "https://old.example", 0)
                assert not any(c["path"].endswith(("/captured-title", "/casecard")) for c in portal.calls[before:])
                assert review.read_case(task)["server_sync"]["status"] == "synced"
                assert node._hmb_captured_title_sync_state["status"] == "unsupported"
                captured_checks += 3
            portal.capabilities = deepcopy(supported)
            # Whole-record mismatch, foreign Task and permission rejection never
            # permit a PUT, alternate origin or metadata ownership workaround.
            task = "captured-conflict"
            original, legacy = captured_case(task)
            portal.casecards[task]["client_prompt_sha256"] = "f" * 64
            before = len(portal.calls)
            node._sync_review_task(task, "https://old.example", 0)
            assert node._hmb_captured_title_sync_state["status"] == "failed"
            assert not any(c["method"] != "GET" for c in portal.calls[before:])
            assert review.read_case(task)["inputs"] == original["inputs"]
            assert review.read_case(task)["server_sync"]["status"] == "synced"
            captured_checks += 4
            for code in (403, 409):
                task = "captured-rejected-" + str(code)
                original, legacy = captured_case(task)
                node.checkpoint = {"task_id": task}
                portal.title_failure = ns["_BrokerError"]("denied", status_code=code)
                before = len(portal.calls)
                node._sync_review_task(task, "https://old.example", 0)
                calls = portal.calls[before:]
                assert not any(c["method"] == "PUT" for c in calls)
                assert node._hmb_captured_title_sync_state["status"] == "failed"
                assert "[CAPTURED_TITLE_SYNC]" in node.values["status_details"]
                assert review.read_case(task)["status"] == "succeeded"
                assert review.read_case(task)["server_sync"]["status"] == "synced"
                assert review.read_case(task)["inputs"] == original["inputs"]
                captured_checks += 6
            portal.title_failure = None
            for failure in (ns["_BrokerError"]("forbidden", status_code=403), ns["_BrokerAuthenticationError"]("expired", status_code=401)):
                task = "captured-casecard-denied"
                original, legacy = captured_case(task)
                portal.casecard_get_failure = failure
                before = len(portal.calls)
                node._sync_review_task(task, "https://old.example", 0)
                assert not any(c["method"] != "GET" for c in portal.calls[before:])
                assert review.read_case(task)["status"] == "succeeded"
                assert review.read_case(task)["inputs"] == original["inputs"]
                captured_checks += 3
            portal.casecard_get_failure = None
            # Optional failure must not publish into another or currently active render.
            node.checkpoint = {"task_id": "another-task"}
            before = len(node.published)
            node._set_captured_title_sync_state("captured-casecard-denied", "failed")
            assert len(node.published) == before
            node.checkpoint = {"task_id": "captured-casecard-denied"}
            node._generation_run_active.set()
            node._set_captured_title_sync_state("captured-casecard-denied", "failed")
            assert len(node.published) == before
            node._generation_run_active.clear()
            captured_checks += 2
            # Cancellation after the authenticated read cannot start metadata POST.
            original, legacy = captured_case("captured-cancelled")
            def cancel_casecard(call):
                if call["path"].endswith("/casecard"):
                    node.alive = False
            portal.hook = cancel_casecard
            before = len(portal.calls)
            node._sync_review_task("captured-cancelled", "https://old.example", 0)
            assert not any(c["method"] != "GET" for c in portal.calls[before:])
            assert "captured-cancelled" not in portal.titles
            portal.hook, node.alive = None, True
            captured_checks += 2
            # Validate strict owner-attested DTOs; a title is never represented as
            # verified generation input, and malformed/foreign ACKs are rejected.
            task = "captured-response-check"
            original, legacy = captured_case(task)
            payload = ns["_captured_display_title_request"](task, original, portal.casecards[task])
            assert bridge.get_task_captured_title(task) is None
            assert bridge.post_task_captured_title(task, payload)["_http_status"] == 201
            modifiers = (
                lambda r: {**r, "task_id": "foreign-task"},
                lambda r: {**r, "version": True},
                lambda r: {**r, "created": "true"},
                lambda r: {**r, "created": True},
                lambda r: {**r, "captured_title": None},
                lambda r: {**r, "extra": "untrusted"},
                lambda r: {**r, "captured_title": {**r["captured_title"], "name": "Another name"}},
                lambda r: {**r, "captured_title": {**r["captured_title"], "operation_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"}},
                lambda r: {**r, "captured_title": {**r["captured_title"], "provenance": "verified_input"}},
                lambda r: {**r, "captured_title": {**r["captured_title"], "verified_generation_input": True}},
                lambda r: {**r, "captured_title": {**r["captured_title"], "verified_generation_input": 0}},
                lambda r: {**r, "captured_title": {**r["captured_title"], "created_at": True}},
                lambda r: {**r, "captured_title": {**r["captured_title"], "created_at": -1}},
                lambda r: {**r, "captured_title": {**r["captured_title"], "extra": "untrusted"}},
            )
            for modifier in modifiers:
                portal.title_ack_modifier = modifier
                try:
                    bridge.post_task_captured_title(task, payload)
                except ns["_BrokerProtocolError"]:
                    captured_checks += 1
                else:
                    raise AssertionError("Malformed captured-title ACK was accepted")
            portal.title_ack_modifier = None
            for modifier in (lambda r: {**r, "task_id": "foreign-task"},
                             lambda r: {**r, "captured_title": {**r["captured_title"], "operation_id": "not-a-UUID"}},
                             lambda r: {**r, "created": False}):
                portal.title_ack_modifier = modifier
                try:
                    bridge.get_task_captured_title(task)
                except ns["_BrokerProtocolError"]:
                    captured_checks += 1
                else:
                    raise AssertionError("Malformed captured-title GET was accepted")
            portal.title_ack_modifier = None
            for mutation in ({"prompt": "must not be sent"}, {"model": "live-selector-alias"},
                             {"name": "https://private/token"}, {"operation_id": "AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA"}):
                changed = {**payload, **mutation}
                before = len(portal.calls)
                try:
                    bridge.post_task_captured_title(task, changed)
                except ns["_BrokerProtocolError"]:
                    assert len(portal.calls) == before
                    captured_checks += 1
                else:
                    raise AssertionError("Unsafe captured-title payload reached HTTP")
            # Existing different display metadata is preserved, never overwritten.
            portal.titles[task]["name"] = "Previously attested different name"
            before = len(portal.calls)
            node._sync_review_task(task, "https://old.example", 0)
            assert node._hmb_captured_title_sync_state["status"] == "failed"
            assert not any(c["method"] != "GET" for c in portal.calls[before:])
            assert portal.titles[task]["name"] == "Previously attested different name"
            captured_checks += 3
            assert checks == 78, "Preserve the existing 78 compatibility checks"
            checks += captured_checks
            assert all(call["path"].startswith("/api/v1/reviews/") for call in portal.calls)
            evidence_dir = __import__("os").environ.get("HMB_REVIEW_PORTAL_EVIDENCE_DIR")
            if evidence_dir:
                destination = Path(evidence_dir)
                destination.mkdir(parents=True, exist_ok=True)
                (destination / "casecard-wire-fixture.json").write_text(json.dumps(wire, ensure_ascii=False, indent=2), encoding="utf-8")
                (destination / "client-transport-receipt.json").write_text(json.dumps({"checks": checks,
                    "mode": "offline actual-code fake authenticated HTTP transport; no SDK/server/model call",
                    "capabilities": CAPABILITIES, "wire_sha256": review._digest(wire),
                    "requests": [{k: v for k, v in call.items() if k not in {"body", "origin"}} for call in portal.calls],
                    "source_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                                      for name in ("_hmb_review.py", "HMBSeedanceGeneration.py")}}, indent=2), encoding="utf-8")
    print(f"PASS: Review portal client ({checks} checks; actual-code authenticated fake transport, pinned origin, cancellation; no paid requests).")


if __name__ == "__main__":
    main()
