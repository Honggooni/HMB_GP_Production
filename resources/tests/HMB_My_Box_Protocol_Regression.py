"""Offline private Only contract, frozen submission and original-media guards."""
from __future__ import annotations

import copy
from dataclasses import FrozenInstanceError
from email.message import Message
import hashlib
import io
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import _hmb_my_box as box

assert "HMBSeedanceGeneration" not in sys.modules, "Pure My Box helper imported the native/video runtime"
checks = 1


def check(value, message=""):
    global checks
    assert value, message
    checks += 1


def rejects(action, code=""):
    global checks
    try:
        action()
    except box.MyBoxError as exc:
        assert not code or exc.code == code, (exc.code, code)
        checks += 1
        return exc
    raise AssertionError("Invalid My Box operation was accepted")


BASE = "https://broker.example.test/Gateway"
WID = "mbx_" + "1" * 32
TID = "job-mybox-" + "2" * 32
CID = "mybox-client-request-1"
SELECTION = {"schema": box.SELECTION_SCHEMA, "version": 1, "selection_source": "only_my_box",
    "scope": box.SCOPE, "workspace_id": WID, "explicit_selection": True}
WORKSPACE = {"workspace_id": WID, "scope": box.SCOPE, "created_at": 100, "selection": SELECTION}
CAPS = {"schema": box.CAPABILITIES_SCHEMA, "version": 1, "implemented": True, "enabled": True,
    "generation_enabled": True, "workspace_management_enabled": True, "reason_code": None,
    "budget_limits_supported": False, "project_source_reuse_enabled": False,
    "selection_schema": box.SELECTION_SCHEMA, "selection_source": "only_my_box", "scope": box.SCOPE,
    "publish_to_reviews": False, "image_results_included": False, "generation_modes": ["only"],
    "output_media_types": ["video"], "generation_endpoint": "/api/v1/generate/video", "workspace": WORKSPACE,
    "automatic_deletion_enabled": False, "management_deadline_disables_media": False, "default_management_days": 30}
PAYLOAD = {"provider": "volcengine_ark", "model": "doubao-seedance-2-5-260628", "type": "video",
    "hmb_generation_task": "Reference to Video", "prompt": "기존 동작과 한글을 유지", "resolution": "480p",
    "draft": True, "ratio": "16:9", "generate_audio": False, "seed": 0, "output_format": "mov",
    "image_urls": ["data:image/png;base64,reference"]}
INVOCATION = box.prepare_invocation(PAYLOAD, selection=SELECTION, title="개인 테스트", client_request_id=CID)
JOB = {"schema": box.JOB_SCHEMA, "version": 1, "task_id": TID, "job_id": TID, "workspace_id": WID,
    "scope": box.SCOPE, "publish_to_reviews": False, "generation_mode": "only", "client_request_id": CID,
    "provider": PAYLOAD["provider"], "model": PAYLOAD["model"], "status": "pending", "resubmit_allowed": False,
    "download_url": None, "video_url": None, "created_at": 100}


class Bridge:
    def __init__(self):
        self.server_url = BASE
        self.calls = []
        self.work = copy.deepcopy(WORKSPACE)
        self.failure = None
        self.job = copy.deepcopy(JOB)
        self.capability = copy.deepcopy(CAPS)

    def _request_json(self, method, path, **kwargs):
        self.calls.append((method, path, copy.deepcopy(kwargs)))
        if self.failure is not None:
            raise self.failure
        if path.endswith("/capabilities"):
            return copy.deepcopy(self.capability)
        if path.endswith("/workspace"):
            created = method == "POST"
            if created:
                self.work = copy.deepcopy(WORKSPACE)
            return {"schema": box.WORKSPACE_SCHEMA, "version": 1, "workspace": copy.deepcopy(self.work), "created": created}
        if path.endswith("/source-reference"):
            return {"schema": "hmb-only-my-box-source-reference-v1", "version": 1, "scope": box.SCOPE,
                "target_client_request_id": kwargs["payload"]["target_client_request_id"], "expires_at": 9999999999,
                "url": BASE + box.API + "/provider-source/" + "A" * 43}
        return copy.deepcopy(self.job)

    def _load_access_token(self):
        return "OFFLINE_TEST_TOKEN"


def ready():
    bridge = Bridge()
    client = box.MyBoxBroker(bridge)
    client.capabilities()
    return bridge, client


# Explicit scope is exact and detached; malformed/production metadata cannot
# become a canonical production project through a legacy fallback.
check(box.normalize_selection(SELECTION) == SELECTION)
detached = box.normalize_selection(SELECTION)
detached["workspace_id"] = "changed"
check(SELECTION["workspace_id"] == WID)
for key, bad in (("schema", "hmb-only-project-selection-v1"), ("version", True), ("version", 2),
                 ("selection_source", "imageasset"), ("scope", "production"), ("explicit_selection", 1),
                 ("workspace_id", "mbx_" + "A" * 32), ("workspace_id", "../" + WID)):
    value = dict(SELECTION, **{key: bad})
    rejects(lambda: box.normalize_selection(value))
for key in SELECTION:
    value = dict(SELECTION)
    value.pop(key)
    rejects(lambda: box.normalize_selection(value))
rejects(lambda: box.normalize_selection(dict(SELECTION, project_id="superwings12")))

caps = box.parse_capabilities(CAPS)
check(caps.generation_enabled and caps.workspace["workspace_id"] == WID)
caps.workspace["selection"]["workspace_id"] = "changed"
check(caps.workspace["workspace_id"] == WID)
broken_workspace = copy.deepcopy(CAPS)
broken_workspace["workspace"]["selection"]["workspace_id"] = "mbx_" + "3" * 32
rejects(lambda: box.parse_capabilities(broken_workspace), "MY_BOX_IDENTITY_MISMATCH")
for key, bad in (("version", True), ("scope", "project"), ("publish_to_reviews", True),
                 ("image_results_included", True), ("generation_modes", ["only", "shot"]),
                 ("generation_endpoint", "/api/generate"), ("automatic_deletion_enabled", True),
                 ("management_deadline_disables_media", True), ("default_management_days", True),
                 ("budget_limits_supported", 0), ("enabled", "yes"), ("reason_code", "raw secret\n")):
    value = copy.deepcopy(CAPS)
    value[key] = bad
    rejects(lambda: box.parse_capabilities(value))
budget = copy.deepcopy(CAPS)
budget.update(enabled=False, generation_enabled=False, reason_code="my_box_configured_budget_not_supported")
reason = rejects(lambda: box.parse_capabilities(budget).require_generation(), "my_box_configured_budget_not_supported")
check("my_box_configured_budget_not_supported" in str(reason))
budget.update(enabled=True, generation_enabled=True)
rejects(lambda: box.parse_capabilities(budget).require_generation(), "my_box_configured_budget_not_supported")

# Frozen input preserves OFF/0/480p/MOV and does not mutate the caller.
check(INVOCATION.payload()["seed"] == 0 and INVOCATION.payload()["generate_audio"] is False)
check(INVOCATION.payload()["resolution"] == "480p" and INVOCATION.payload()["output_format"] == "mov")
copy_payload = INVOCATION.payload()
copy_payload["image_urls"].clear()
check(len(INVOCATION.payload()["image_urls"]) == 1)
check("my_box_selection" not in PAYLOAD)
try:
    INVOCATION.client_request_id = "changed"
except FrozenInstanceError:
    checks += 1
else:
    raise AssertionError("Invocation was mutable")
for key in ("project_id", "project_name", "project_selection_schema", "hmb_shot", "owner_id", "user_id", "api_key", "web_search", "content_filter"):
    rejects(lambda: box.prepare_invocation(dict(PAYLOAD, **{key: "untrusted"}), selection=SELECTION, title="개인", client_request_id=CID), "MY_BOX_MIXED_SCOPE")
for key, bad in (("hmb_generation_mode", "shot"), ("type", "image")):
    rejects(lambda: box.prepare_invocation(dict(PAYLOAD, **{key: bad}), selection=SELECTION, title="개인", client_request_id=CID), "MY_BOX_ONLY_REQUIRED")
rejects(lambda: box.prepare_invocation(PAYLOAD, selection=SELECTION, title="", client_request_id=CID))
rejects(lambda: box.prepare_invocation(PAYLOAD, selection=SELECTION, title="개인", client_request_id=TID))
rejects(lambda: box.prepare_invocation(dict(PAYLOAD, seed=float("nan")), selection=SELECTION, title="개인", client_request_id=CID))

# No construction I/O; GET never creates. Explicit creation uses one owner-bound
# POST only if the queried workspace does not already exist.
bridge = Bridge()
client = box.MyBoxBroker(bridge)
check(not bridge.calls)
check(client.workspace()["workspace_id"] == WID)
check([v[0] for v in bridge.calls] == ["GET"])
rejects(lambda: client.workspace(create=True), "MY_BOX_SELECTION_INVALID")
rejects(lambda: client.create(INVOCATION), "MY_BOX_UNSUPPORTED")
bridge, client = ready()
bridge.work = None
check(client.workspace() is None)
check(not any(method == "POST" for method, _, _ in bridge.calls))
check(client.workspace(create=True, explicit_selection=True)["selection"] == SELECTION)
posts = [(path, args["payload"]) for method, path, args in bridge.calls if method == "POST"]
check(posts == [(box.API + "/workspace", {"explicit_selection": True})])
client.workspace(create=True, explicit_selection=True)
check(sum(method == "POST" for method, _, _ in bridge.calls) == 1)

# Prepared checkpoint is stored before exactly one create. Unknown errors are
# preserved unchanged and recovery uses the same ID without another create.
bridge, client = ready()
prepared = []
job = client.create(INVOCATION, on_submission_prepared=lambda snapshot: prepared.append(snapshot))
check(prepared == [INVOCATION])
post = bridge.calls[-1]
check(post[0:2] == ("POST", "/api/v1/generate/video"))
check(post[2]["submission"] is True and post[2]["idempotency_key"] == CID)
check(post[2]["payload"]["my_box_title"] == "개인 테스트" and "title" not in post[2]["payload"])
check(job["job_id"] == TID)
check(client.refresh(CID, selection=SELECTION, client_request_id=CID)["task_id"] == TID)
check(client.detail(TID, selection=SELECTION)["task_id"] == TID)
check(sum(path == "/api/v1/generate/video" for _, path, _ in bridge.calls) == 1)
bridge.failure = SimpleNamespace()
unknown = TimeoutError("OFFLINE unknown")
unknown.submission_outcome_unknown = True
bridge.failure = unknown
try:
    client.create(INVOCATION, on_submission_prepared=lambda snapshot: prepared.append(snapshot))
except TimeoutError as exc:
    check(exc is unknown and exc.submission_outcome_unknown)
else:
    raise AssertionError("Unknown submission was retried or swallowed")
check(prepared[-1].client_request_id == CID)
check(sum(path == "/api/v1/generate/video" for _, path, _ in bridge.calls) == 2)
bridge.failure = None
client.refresh(CID, selection=SELECTION, client_request_id=CID)
check(sum(path == "/api/v1/generate/video" for _, path, _ in bridge.calls) == 2)

bridge, client = ready()
rejects(lambda: client.create(INVOCATION, is_alive=lambda: False), "MY_BOX_CANCELLED")
check(len(bridge.calls) == 1)
alive = [True]
rejects(lambda: client.create(INVOCATION, on_submission_prepared=lambda _: alive.__setitem__(0, False), is_alive=lambda: alive[0]), "MY_BOX_CANCELLED")
check(len(bridge.calls) == 1)
bridge.job["workspace_id"] = "mbx_" + "3" * 32
exc = rejects(lambda: client.create(INVOCATION), "MY_BOX_IDENTITY_MISMATCH")
check(exc.submission_outcome_unknown is True)
bridge.capability.update(enabled=False, generation_enabled=False, reason_code="my_box_configured_budget_not_supported")
client.capabilities()
before = len(bridge.calls)
rejects(lambda: client.create(INVOCATION), "my_box_configured_budget_not_supported")
check(len(bridge.calls) == before)

class HttpFailure(RuntimeError):
    def __init__(self, status):
        self.status_code = status


for status in (404, 405, 501):
    bridge.failure = HttpFailure(status)
    rejects(client.capabilities, "MY_BOX_UNSUPPORTED")
for status in (401, 403, 429, 503):
    failure = HttpFailure(status)
    bridge.failure = failure
    try:
        client.capabilities()
    except HttpFailure as exc:
        check(exc is failure, "Authentication or budget failure was hidden")
    else:
        raise AssertionError("Broker authentication/readiness failure was ignored")
bridge.failure = None

for key, bad in (("job_id", "job-" + "2" * 32), ("task_id", "job-" + "2" * 32), ("version", True),
                 ("scope", "production"), ("publish_to_reviews", True), ("generation_mode", "shot"),
                 ("resubmit_allowed", True), ("status", "succeeded"), ("status", []),
                 ("client_request_id", "other"), ("model", "other"), ("workspace_id", "mbx_" + "3" * 32)):
    value = copy.deepcopy(JOB)
    value[key] = bad
    rejects(lambda: box.validate_job(value, invocation=INVOCATION))
for status in box.JOB_ACTIVE_STATUSES | box.JOB_SUCCESS_STATUSES | box.JOB_FAILURE_STATUSES:
    check(box.validate_job(dict(JOB, status=status), invocation=INVOCATION)["status"] == status)

# Authenticated original is selected even for browser-incompatible MOV. The
# gateway, private Task, query, response MIME/length/strong ETag are all exact.
VIDEO = b"\x00\x00\x00\x18ftypqt  " + b"offline-original-video" * 7
COMPLETE = dict(JOB, status="completed", video_url=None,
    download_url=BASE + box.API + "/items/" + TID + "/media?download=1",
    preview_url=BASE + box.API + "/items/" + TID + "/preview")


class Response(io.BytesIO):
    def __init__(self, raw=VIDEO, *, url=COMPLETE["download_url"], headers=None, status=200):
        super().__init__(raw)
        self.url, self.status = url, status
        self.headers = Message()
        for key, value in (headers or {"Content-Type": "video/quicktime", "Content-Length": str(len(raw)),
                                      "ETag": '"' + hashlib.sha256(raw).hexdigest() + '"'}).items():
            self.headers[key] = value

    def geturl(self):
        return self.url


class Opener:
    def __init__(self, **kwargs):
        self.kwargs, self.calls = kwargs, []

    def open(self, request, timeout):
        self.calls.append((request, timeout))
        return Response(**self.kwargs)


bridge, client = ready()
bridge._opener = Opener()
check(client.download_info(COMPLETE).url == COMPLETE["download_url"])
check(client.download_result(COMPLETE) == VIDEO)
request = bridge._opener.calls[0][0]
check(request.get_method() == "GET" and request.get_header("Authorization") == "Bearer OFFLINE_TEST_TOKEN")
check(request.full_url.endswith("/media?download=1"))
for url in ("https://outside.test/media", COMPLETE["preview_url"], COMPLETE["download_url"].replace("Gateway", "Other"),
            COMPLETE["download_url"] + "&owner_id=1", COMPLETE["download_url"].replace(TID, "job-mybox-" + "4" * 32),
            COMPLETE["download_url"].replace("?download=1", ""), COMPLETE["download_url"].replace("/items/", "/items/%2e%2e/")):
    rejects(lambda: client.download_info(dict(COMPLETE, download_url=url)), "MY_BOX_RESULT_UNTRUSTED")
for kwargs in ({"url": "https://outside.test/media"}, {"status": 206}):
    bridge._opener = Opener(**kwargs)
    rejects(lambda: client.download_result(COMPLETE), "MY_BOX_RESULT_UNTRUSTED")
defaults = {"Content-Type": "video/quicktime", "Content-Length": str(len(VIDEO)), "ETag": '"' + hashlib.sha256(VIDEO).hexdigest() + '"'}
for key, bad in (("Content-Type", "text/html"), ("Content-Length", "0"), ("Content-Length", str(box.MAX_VIDEO_BYTES + 1)),
                 ("Content-Length", str(len(VIDEO) - 1)), ("Content-Length", str(len(VIDEO) + 1)),
                 ("ETag", 'W/"' + "a" * 64 + '"'), ("ETag", '"' + "a" * 64 + '"'),
                 ("Transfer-Encoding", "chunked"), ("Content-Encoding", "gzip")):
    bridge._opener = Opener(headers=dict(defaults, **{key: bad}))
    rejects(lambda: client.download_result(COMPLETE), "MY_BOX_DOWNLOAD_INVALID")
bridge._opener = Opener(raw=b"not-a-video")
rejects(lambda: client.download_result(COMPLETE), "MY_BOX_DOWNLOAD_INVALID")
bridge._opener = Opener()
rejects(lambda: client.download_result(COMPLETE, max_bytes=len(VIDEO) - 1), "MY_BOX_DOWNLOAD_INVALID")
rejects(lambda: client.download_result(COMPLETE, is_alive=lambda: False), "MY_BOX_CANCELLED")
bridge.server_url = "https://different.example.test"
rejects(lambda: client.refresh(TID, selection=SELECTION), "MY_BOX_IDENTITY_MISMATCH")
rejects(lambda: client.download_result(COMPLETE), "MY_BOX_IDENTITY_MISMATCH")

# Source grants are owner/workspace checked and bound to the eventual create
# key and exact private provider-source URL; no production review route exists.
bridge, client = ready()
bridge.job = copy.deepcopy(COMPLETE)
grant = client.source_reference(TID, CID, "Video Editing", selection=SELECTION)
check(grant["target_client_request_id"] == CID)
check(bridge.calls[-1][2]["payload"] == {"target_client_request_id": CID, "task": "Video Editing"})
check(not bridge.calls[-1][2]["submission"])
rejects(lambda: client.source_reference(TID, CID, "image", selection=SELECTION))
other = dict(SELECTION, workspace_id="mbx_" + "3" * 32)
before = len(bridge.calls)
rejects(lambda: client.source_reference(TID, CID, "Video Extension", selection=other), "MY_BOX_IDENTITY_MISMATCH")
check(len(bridge.calls) == before + 1, "Mismatched workspace proceeded to source grant POST")
check(not any("/api/v1/reviews" in path or "/api/assets" in path for _, path, _ in bridge.calls))
bridge.job["status"] = "running"
before = len(bridge.calls)
rejects(lambda: client.source_reference(TID, CID, "Video Extension", selection=SELECTION), "MY_BOX_RESULT_NOT_READY")
check(len(bridge.calls) == before + 1, "Incomplete source proceeded to source grant POST")

# Duplicate response headers, cancellation while streaming, and malformed
# accepted JSON cannot produce a published original or a second create.
class DuplicateOpener(Opener):
    def open(self, request, timeout):
        response = super().open(request, timeout)
        response.headers["Content-Length"] = str(len(VIDEO))
        return response


bridge, client = ready()
bridge._opener = DuplicateOpener()
rejects(lambda: client.download_result(COMPLETE), "MY_BOX_DOWNLOAD_INVALID")
bridge._opener = Opener()
alive_reads = [0]
def stop_midstream():
    alive_reads[0] += 1
    return alive_reads[0] < 3
rejects(lambda: client.download_result(COMPLETE, is_alive=stop_midstream), "MY_BOX_CANCELLED")
for malformed in (None, [], {"error": "not-a-task"}):
    bridge.job = malformed
    before = len(bridge.calls)
    error = rejects(lambda: client.create(INVOCATION))
    check(error.submission_outcome_unknown and len(bridge.calls) == before + 1)

# Owner-private source-only Final state is advertised separately. Missing older
# projections never imply eligibility; an existing failed/unknown child always
# wins over expiry or a tempting recommended request key.
FINAL_CONTRACT = {"schema": box.DRAFT_FINAL_SCHEMA, "version": 1, "detail_field": "draft_final",
    "projection_scope": "preview_source_detail_only", "final_child_detail_state": "not_draft",
    "states": ["available", "reserved", "running", "completed", "expired", "not_draft"],
    "expiry_basis": "source_creation_provider_limit", "source_ttl_seconds": 604800,
    "eligibility_scope": "source_only", "requires_generation_enabled": True,
    "existing_child_has_precedence": True, "resubmit_allowed": False,
    "final_client_request_id_rule": "mbx-final-v1-{source_task_hex32}", "final_client_request_id_required": False,
    "client_key_namespace_conflicts_rejected": True}
new_caps = dict(CAPS, draft_final_detail_supported=True, draft_final_contract=FINAL_CONTRACT)
parsed = box.parse_capabilities(new_caps)
check(parsed.draft_final_detail_supported and parsed.draft_final_contract == FINAL_CONTRACT)
check(not caps.draft_final_detail_supported and caps.draft_final_contract is None)
for key, bad in (("version", True), ("source_ttl_seconds", 30 * 86400), ("requires_generation_enabled", False),
                 ("existing_child_has_precedence", False), ("resubmit_allowed", True),
                 ("projection_scope", "public"), ("final_client_request_id_required", True)):
    contract = dict(FINAL_CONTRACT, **{key: bad})
    rejects(lambda: box.parse_capabilities(dict(new_caps, draft_final_contract=contract)))

STATE = {"schema": box.DRAFT_FINAL_SCHEMA, "version": 1, "state": "available", "eligible": True,
    "source_task_id": TID, "child_task_id": None, "child_status": None, "expires_at": 604900,
    "expiry_basis": "source_creation_provider_limit", "workspace_id": WID, "selection": SELECTION,
    "final_client_request_id": "mbx-final-v1-" + "2" * 32, "eligibility_scope": "source_only",
    "resubmit_allowed": False, "reason_code": None}
check(box.parse_draft_final_state(COMPLETE) is None)
check(box.parse_draft_final_state(dict(COMPLETE, draft_final=STATE)) == STATE)
check(len(STATE["final_client_request_id"]) == 45)
for key in STATE:
    state = copy.deepcopy(STATE)
    state.pop(key)
    rejects(lambda: box.parse_draft_final_state(dict(COMPLETE, draft_final=state)))
for key, bad in (("version", True), ("source_task_id", "job-mybox-" + "9" * 32),
                 ("workspace_id", "mbx_" + "9" * 32), ("selection", dict(SELECTION, workspace_id="mbx_" + "9" * 32)),
                 ("eligible", 1), ("eligible", False), ("resubmit_allowed", True), ("expires_at", True),
                 ("expiry_basis", "completed_at"), ("final_client_request_id", "new-key"),
                 ("reason_code", "blocked"), ("child_status", "failed"), ("eligibility_scope", "account_and_budget")):
    state = dict(STATE, **{key: bad})
    rejects(lambda: box.parse_draft_final_state(dict(COMPLETE, draft_final=state)))
CHILD = "job-mybox-" + "5" * 32
for child_status, name in (("completed", "completed"), ("pending", "running"), ("running", "running"),
                           ("downloading", "running"), ("submitting", "reserved"), ("failed", "reserved"),
                           ("submission_unknown", "reserved"), ("cancelled", "reserved")):
    state = dict(STATE, state=name, eligible=False, child_task_id=CHILD, child_status=child_status,
                 reason_code="my_box_draft_final_reserved_no_resubmit")
    result = box.parse_draft_final_state(dict(COMPLETE, draft_final=state))
    check(not result["eligible"] and result["child_task_id"] == CHILD and result["child_status"] == child_status)
for name in ("expired", "not_draft"):
    state = dict(STATE, state=name, eligible=False, reason_code="my_box_draft_source_expired")
    check(not box.parse_draft_final_state(dict(COMPLETE, draft_final=state))["eligible"])
foreign = dict(STATE, state="reserved", eligible=False, child_task_id=None, child_status=None,
               reason_code="my_box_draft_child_binding_unavailable")
check(box.parse_draft_final_state(dict(COMPLETE, draft_final=foreign))["child_task_id"] is None)
for name, child_status in (("running", "failed"), ("completed", "running"), ("reserved", "completed"), ("reserved", "pending")):
    state = dict(STATE, state=name, eligible=False, child_task_id=CHILD, child_status=child_status)
    rejects(lambda: box.parse_draft_final_state(dict(COMPLETE, draft_final=state)))
state = dict(STATE, state="reserved", eligible=True, child_task_id=CHILD, child_status="submission_unknown")
rejects(lambda: box.parse_draft_final_state(dict(COMPLETE, draft_final=state)))
# A previously saved nonrecommended key stays unchanged in its invocation.
old = box.prepare_invocation(dict(PAYLOAD, draft_job_id=TID), selection=SELECTION,
    title="기존 키 복구", client_request_id="preexisting-final-key")
check(old.client_request_id == "preexisting-final-key")

print("PASS HMB_My_Box_Protocol_Regression:", checks, "offline checks; paid/network/production writes = 0")
