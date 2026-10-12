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
             "_broker_validated_server_url", "_broker_read_json", "_broker_require_exact_response_url"}
    definitions = [item for item in tree.body if isinstance(item, (ast.FunctionDef, ast.ClassDef)) and item.name in names]
    bridge = next(item for item in tree.body if isinstance(item, ast.ClassDef) and item.name == "_HMBAIBrokerBridge")
    methods = {"__init__", "server_url", "_review_task_path", "review_capabilities", "put_task_casecard",
               "post_task_feedback", "task_feedback", "_load_access_token", "_clear_access_token", "_request_json"}
    definitions.append(ast.ClassDef(name="Bridge", bases=[], keywords=[], decorator_list=[], body=[
        item for item in bridge.body if isinstance(item, ast.FunctionDef) and item.name in methods]))
    node = next(item for item in tree.body if isinstance(item, ast.ClassDef) and item.name == "HMBSeedanceGeneration")
    methods = {"_review_origin_for_task", "_review_sync_is_live", "_sync_review_task", "_schedule_review_sync",
               "_schedule_open_review_gallery", "_validate_task_id"}
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
            assert request.method == "PUT"
            assert body == review.public_evidence(body), "Wire evidence must be the exact public projection"
            assert set(body) == {"schema", "version", "case_id", "input_evidence_sha256", "client_prompt_sha256",
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
                "generation_origin": {"channel_uuid": "channel-a", "shot_uuid": "shot-a", "number": 2}},
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
            assert not any(v in json.dumps(wire) for v in ("SECRET", "private", "C:/", "SERVER PROMPT"))
            assert tokens and set(tokens) == {"https://old.example"}
            checks += 6
            put_count = sum(call["method"] == "PUT" for call in portal.calls)
            node._sync_review_task("task-a", "https://old.example", 0)
            assert sum(call["method"] == "PUT" for call in portal.calls) == put_count
            assert review.read_case("task-a")["server_sync"]["status"] == "synced", "Identical retry cannot leave pending"
            checks += 2
            bridge = ns["Bridge"](opener=portal, server_url="https://old.example")
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
