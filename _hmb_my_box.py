"""Private Only video contract over the existing authenticated Broker session.

No native nodes, accounts, credentials, project records or provider APIs are
created here. A prepared invocation is immutable; an uncertain POST is never
retried. File publication remains the Generator's responsibility.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
import hashlib
import hmac
import json
import re
import time
from typing import Any, Callable
from urllib.parse import quote
import urllib.request

import _hmb_broker_config as broker_config
import _hmb_queue_admission as queue

MY_BOX_LABEL = "My Box"
API = "/api/v1/only/my-box"
SELECTION_SCHEMA = "hmb-only-my-box-selection-v1"
CAPABILITIES_SCHEMA = "hmb-only-my-box-capabilities-v1"
WORKSPACE_SCHEMA = "hmb-only-my-box-workspace-v1"
JOB_SCHEMA = "hmb-only-my-box-job-v1"
DRAFT_FINAL_SCHEMA = "hmb-only-my-box-draft-final-v1"
SCOPE = "personal_my_box"
MAX_REQUEST_BYTES = 64 * 1024 * 1024
MAX_VIDEO_BYTES = 2 * 1024 * 1024 * 1024
WORKSPACE_ID = re.compile(r"mbx_[a-f0-9]{32}\Z")
TASK_ID = re.compile(r"job-mybox-[a-f0-9]{32}\Z")
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}\Z")
SELECTION_FIELDS = frozenset(("schema", "version", "selection_source", "scope", "workspace_id", "explicit_selection"))
JOB_ACTIVE_STATUSES = frozenset(("submitting", "pending", "running", "downloading", "submission_unknown"))
JOB_SUCCESS_STATUSES = frozenset(("completed",))
JOB_FAILURE_STATUSES = frozenset(("failed",))
PAYLOAD_FIELDS = frozenset(("provider", "model", "type", "task", "hmb_generation_mode", "hmb_generation_task",
    "my_box_selection", "my_box_title", "client_request_id", "prompt", "quality", "resolution", "duration",
    "duration_seconds", "aspect_ratio", "ratio", "generate_audio", "watermark", "return_last_frame", "input_mode",
    "omni_reference_task_type", "output_format", "draft", "draft_job_id", "priority", "execution_expires_after",
    "seed", "camera_fixed", "first_frame", "last_frame", "image_urls", "video_urls", "audio_urls"))


class MyBoxError(ValueError):
    def __init__(self, message: str, *, code: str = "MY_BOX_PROTOCOL_INVALID", status_code: int | None = None,
                 submission_outcome_unknown: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.submission_outcome_unknown = submission_outcome_unknown


def _fail(message: str, code: str = "MY_BOX_PROTOCOL_INVALID") -> None:
    raise MyBoxError(message, code=code)


def _json(value: Any, *, limit: int = MAX_REQUEST_BYTES) -> str:
    try:
        result = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        if len(result.encode("utf-8")) > limit:
            _fail("My Box request exceeds the allowed size.", "MY_BOX_REQUEST_TOO_LARGE")
        return result
    except (TypeError, ValueError, RecursionError, UnicodeError) as exc:
        if isinstance(exc, MyBoxError):
            raise
        raise MyBoxError("My Box data is not a valid JSON snapshot.") from None


def _text(value: Any, *, limit: int = 256) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit or any(ord(c) < 32 or ord(c) == 127 for c in value):
        _fail("My Box response contains an invalid identifier or text.")
    return value


def _identifier(value: Any) -> str:
    if not isinstance(value, str) or IDENTIFIER.fullmatch(value) is None:
        _fail("My Box request or Task ID is invalid.")
    return value


def _task_id(value: Any) -> str:
    if not isinstance(value, str) or TASK_ID.fullmatch(value) is None:
        _fail("A private My Box Task ID is required.")
    return value


def _alive(is_alive: Callable[[], bool] | None) -> None:
    if is_alive is not None and not is_alive():
        _fail("My Box action was cancelled before publication.", "MY_BOX_CANCELLED")


def normalize_selection(value: Any) -> dict[str, Any]:
    """Accept only the server-issued six-field explicit Only selection."""
    if (not isinstance(value, dict) or set(value) != SELECTION_FIELDS or value.get("schema") != SELECTION_SCHEMA
            or type(value.get("version")) is not int or value["version"] != 1
            or value.get("selection_source") != "only_my_box" or value.get("scope") != SCOPE
            or value.get("explicit_selection") is not True or not isinstance(value.get("workspace_id"), str)
            or WORKSPACE_ID.fullmatch(value["workspace_id"]) is None):
        _fail("Select My Box explicitly using this account's server workspace.", "MY_BOX_SELECTION_INVALID")
    return dict(value)


def _workspace(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict) or value.get("scope") != SCOPE:
        _fail("My Box workspace response is invalid.")
    selection = normalize_selection(value.get("selection"))
    if value.get("workspace_id") != selection["workspace_id"]:
        _fail("My Box workspace identities do not match.", "MY_BOX_IDENTITY_MISMATCH")
    return json.loads(_json(value, limit=8192))


@dataclass(frozen=True)
class MyBoxCapabilities:
    implemented: bool
    enabled: bool
    generation_enabled: bool
    workspace_management_enabled: bool
    reason_code: str
    budget_limits_supported: bool
    project_source_reuse_enabled: bool
    _workspace_json: str
    draft_final_detail_supported: bool = False
    _draft_final_contract_json: str = "null"
    _queue_admission: Any = field(default=None, repr=False, compare=False)

    @property
    def workspace(self) -> dict[str, Any] | None:
        return json.loads(self._workspace_json)

    @property
    def draft_final_contract(self) -> dict[str, Any] | None:
        return json.loads(self._draft_final_contract_json)

    def require_generation(self) -> None:
        if not self.implemented or not self.enabled or not self.generation_enabled or self.reason_code:
            reason = self.reason_code or "my_box_generation_not_ready"
            raise MyBoxError("My Box generation is unavailable (" + reason + "). No video was submitted.", code=reason)

    def require_submission(self, operation: str = "only") -> None:
        if self._queue_admission is None:
            self.require_generation()
        else:
            self._queue_admission.require(operation)


def parse_capabilities(raw: Any) -> MyBoxCapabilities:
    if (not isinstance(raw, dict) or raw.get("schema") != CAPABILITIES_SCHEMA
            or type(raw.get("version")) is not int or raw["version"] != 1
            or raw.get("selection_schema") != SELECTION_SCHEMA or raw.get("selection_source") != "only_my_box"
            or raw.get("scope") != SCOPE or raw.get("publish_to_reviews") is not False
            or raw.get("image_results_included") is not False or raw.get("generation_modes") != ["only"]
            or raw.get("output_media_types") != ["video"] or raw.get("generation_endpoint") != "/api/v1/generate/video"):
        _fail("This Broker has not provided the private My Box video contract.", "MY_BOX_UNSUPPORTED")
    for key in ("implemented", "enabled", "generation_enabled", "workspace_management_enabled", "budget_limits_supported",
                "project_source_reuse_enabled", "automatic_deletion_enabled", "management_deadline_disables_media"):
        if type(raw.get(key)) is not bool:
            _fail("My Box capabilities contain an invalid flag.")
    if raw["automatic_deletion_enabled"] or raw["management_deadline_disables_media"]:
        _fail("My Box management policy does not match the supported private contract.")
    if type(raw.get("default_management_days")) is not int or raw["default_management_days"] != 30:
        _fail("My Box management period is invalid.")
    reason = raw.get("reason_code")
    if reason is not None and (not isinstance(reason, str) or re.fullmatch(r"[a-z][a-z0-9_]{0,127}", reason) is None):
        _fail("My Box readiness reason is invalid.")
    workspace = _workspace(raw.get("workspace"))
    final_supported = raw.get("draft_final_detail_supported", False)
    if type(final_supported) is not bool:
        _fail("My Box Draft-final support flag is invalid.")
    final_contract = None
    if final_supported:
        final_contract = raw.get("draft_final_contract")
        if (not isinstance(final_contract, dict) or final_contract.get("schema") != DRAFT_FINAL_SCHEMA
                or type(final_contract.get("version")) is not int or final_contract["version"] != 1
                or final_contract.get("detail_field") != "draft_final"
                or final_contract.get("projection_scope") != "preview_source_detail_only"
                or final_contract.get("final_child_detail_state") != "not_draft"
                or final_contract.get("eligibility_scope") != "source_only"
                or final_contract.get("requires_generation_enabled") is not True
                or final_contract.get("existing_child_has_precedence") is not True
                or final_contract.get("resubmit_allowed") is not False
                or final_contract.get("expiry_basis") != "source_creation_provider_limit"
                or type(final_contract.get("source_ttl_seconds")) is not int or final_contract["source_ttl_seconds"] != 7 * 86400
                or final_contract.get("final_client_request_id_required") is not False
                or final_contract.get("client_key_namespace_conflicts_rejected") is not True
                or final_contract.get("states") != ["available", "reserved", "running", "completed", "expired", "not_draft"]
                or final_contract.get("final_client_request_id_rule") != "mbx-final-v1-{source_task_hex32}"):
            _fail("Broker My Box Draft-final contract is invalid.")
    return MyBoxCapabilities(*(raw[k] for k in ("implemented", "enabled", "generation_enabled", "workspace_management_enabled")),
        reason or "", raw["budget_limits_supported"], raw["project_source_reuse_enabled"], _json(workspace),
        final_supported, _json(final_contract, limit=8192))


@dataclass(frozen=True)
class MyBoxInvocation:
    client_request_id: str
    workspace_id: str
    provider: str
    model: str
    _payload_json: str
    _queue_admission: Any = field(default=None, repr=False)
    _queue_headers_json: str = "{}"

    def payload(self) -> dict[str, Any]:
        return json.loads(self._payload_json)

    @property
    def selection(self) -> dict[str, Any]:
        return self.payload()["my_box_selection"]


def prepare_invocation(base_payload: Any, *, selection: dict[str, Any], title: str,
                       client_request_id: str, queue_admission: Any = None) -> MyBoxInvocation:
    selected = normalize_selection(selection)
    client = _identifier(client_request_id)
    if client.startswith("job-mybox-"):
        _fail("A Task ID cannot be reused as a new My Box request ID.")
    if not isinstance(base_payload, dict) or set(base_payload) - PAYLOAD_FIELDS:
        _fail("Private My Box input contains unsupported or production-project fields.", "MY_BOX_MIXED_SCOPE")
    payload = json.loads(_json(base_payload))
    if payload.get("hmb_generation_mode", "only") != "only" or payload.get("type", "video") != "video":
        _fail("My Box accepts only explicit Only video generation.", "MY_BOX_ONLY_REQUIRED")
    for key, expected in (("my_box_selection", selected), ("client_request_id", client), ("my_box_title", title)):
        if key == "my_box_selection" and key in payload:
            normalize_selection(payload[key])
        if key in payload and payload[key] != expected:
            _fail("My Box input does not match its frozen invocation.", "MY_BOX_IDENTITY_MISMATCH")
    provider, model = _text(payload.get("provider")), _text(payload.get("model"))
    _text(title, limit=128)
    if not isinstance(payload.get("prompt", ""), str):
        _fail("My Box prompt must be text.")
    payload.update(hmb_generation_mode="only", my_box_selection=selected, my_box_title=title, client_request_id=client)
    if queue_admission is not None:
        queue_admission.require("draft_final" if payload.get("draft_job_id") else "only")
    return MyBoxInvocation(client, selected["workspace_id"], provider, model, _json(payload), queue_admission,
        json.dumps(queue_admission.headers, sort_keys=True) if queue_admission is not None else "{}")


def validate_job(raw: Any, *, selection: dict[str, Any] | None = None, expected_job_id: str = "",
                 client_request_id: str = "", invocation: MyBoxInvocation | None = None) -> dict[str, Any]:
    if (not isinstance(raw, dict) or raw.get("schema") != JOB_SCHEMA or type(raw.get("version")) is not int
            or raw["version"] != 1 or raw.get("scope") != SCOPE or raw.get("publish_to_reviews") is not False
            or raw.get("generation_mode") != "only" or raw.get("resubmit_allowed") is not False):
        _fail("Broker returned an invalid private My Box Task.")
    task_id = _task_id(raw.get("task_id"))
    if raw.get("job_id") != task_id or not isinstance(raw.get("workspace_id"), str) or WORKSPACE_ID.fullmatch(raw["workspace_id"]) is None:
        _fail("My Box Task identities do not match.", "MY_BOX_IDENTITY_MISMATCH")
    client = _identifier(raw.get("client_request_id"))
    if not isinstance(raw.get("status"), str) or raw["status"] not in JOB_ACTIVE_STATUSES | JOB_SUCCESS_STATUSES | JOB_FAILURE_STATUSES:
        _fail("My Box Task status is invalid.")
    _text(raw.get("provider"))
    _text(raw.get("model"))
    if invocation is not None:
        selection, client_request_id = invocation.selection, invocation.client_request_id
        if raw.get("provider") != invocation.provider or raw.get("model") != invocation.model:
            _fail("My Box Task model identity changed.", "MY_BOX_IDENTITY_MISMATCH")
    if selection is not None and raw["workspace_id"] != normalize_selection(selection)["workspace_id"]:
        _fail("My Box Task belongs to a different workspace.", "MY_BOX_IDENTITY_MISMATCH")
    if client_request_id and client != _identifier(client_request_id):
        _fail("My Box Task belongs to a different request.", "MY_BOX_IDENTITY_MISMATCH")
    if expected_job_id and expected_job_id not in (task_id, client):
        _fail("My Box lookup returned a different Task.", "MY_BOX_IDENTITY_MISMATCH")
    return json.loads(_json(raw, limit=2 * 1024 * 1024))


def parse_draft_final_state(job: dict[str, Any]) -> dict[str, Any] | None:
    """Validate the owner's detail projection; never infer a missing state.

    ``eligible`` describes this source only. The caller must also require fresh
    generation readiness. The recommended client key never replaces a saved
    key or an already reserved child's identity, including failed/unknown jobs.
    """
    checked = validate_job(job)
    if "draft_final" not in checked:
        return None
    state = checked["draft_final"]
    required = {"schema", "version", "state", "eligible", "source_task_id", "child_task_id", "child_status", "expires_at",
        "expiry_basis", "workspace_id", "selection", "final_client_request_id", "eligibility_scope", "resubmit_allowed", "reason_code"}
    if (not isinstance(state, dict) or not required.issubset(state) or state.get("schema") != DRAFT_FINAL_SCHEMA
            or type(state.get("version")) is not int or state["version"] != 1
            or state.get("state") not in ("available", "reserved", "running", "completed", "expired", "not_draft")
            or type(state.get("eligible")) is not bool or state.get("resubmit_allowed") is not False
            or state.get("eligibility_scope") != "source_only" or state.get("expiry_basis") != "source_creation_provider_limit"):
        _fail("Broker returned an invalid private Draft-final state.")
    if (state.get("source_task_id") != checked["task_id"] or state.get("workspace_id") != checked["workspace_id"]
            or normalize_selection(state.get("selection"))["workspace_id"] != checked["workspace_id"]):
        _fail("Private Draft-final source identity changed.", "MY_BOX_IDENTITY_MISMATCH")
    child, child_status = state.get("child_task_id"), state.get("child_status")
    if child is not None:
        _task_id(child)
        if child == checked["task_id"] or not isinstance(child_status, str) or re.fullmatch(r"[a-z][a-z0-9_]{0,63}", child_status) is None:
            _fail("Private Draft-final child identity or status is invalid.")
    elif child_status is not None:
        _fail("Private Draft-final child status has no Task identity.")
    expires = state.get("expires_at")
    if expires is not None and (type(expires) is not int or expires <= 0):
        _fail("Private Draft-final source deadline is invalid.")
    name = state["state"]
    if ((name == "available") != state["eligible"] or (name in ("available", "expired") and expires is None)
            or (name in ("available", "expired", "not_draft") and child is not None)
            or (name in ("running", "completed") and child is None)
            or (name == "running" and child_status not in ("pending", "running", "downloading"))
            or (name == "completed" and child_status != "completed")
            or (name == "reserved" and child_status in ("pending", "running", "downloading", "completed"))):
        _fail("Private Draft-final state conflicts with its eligibility or child.")
    expected_key = "mbx-final-v1-" + checked["task_id"][len("job-mybox-"):]
    if state.get("final_client_request_id") != expected_key:
        _fail("Private Draft-final recommended request identity changed.", "MY_BOX_IDENTITY_MISMATCH")
    reason = state.get("reason_code")
    if reason is not None and (not isinstance(reason, str) or re.fullmatch(r"[a-z][a-z0-9_]{0,127}", reason) is None):
        _fail("Private Draft-final reason is invalid.")
    if name == "available" and reason is not None:
        _fail("Private Draft-final eligible state has a blocking reason.")
    return json.loads(_json(state, limit=8192))


@dataclass(frozen=True)
class MyBoxDownload:
    url: str
    task_id: str
    workspace_id: str


class MyBoxBroker:
    """Inject the already authenticated Bridge; never open a new login store."""
    def __init__(self, bridge: Any) -> None:
        self._bridge = bridge
        self.server_url = broker_config.normalize_broker_base_url(bridge.server_url)
        self._capabilities: MyBoxCapabilities | None = None

    def _bound_bridge(self) -> None:
        if broker_config.normalize_broker_base_url(self._bridge.server_url) != self.server_url:
            _fail("Broker address changed during the private action.", "MY_BOX_IDENTITY_MISMATCH")

    def _request(self, method: str, path: str, *, payload: Any = None, timeout: float = 15,
                 submission: bool = False, idempotency_key: str = "", **queue_kwargs: Any) -> Any:
        self._bound_bridge()
        return self._bridge._request_json(method, path, payload=payload, timeout=timeout,
            submission=submission, idempotency_key=idempotency_key, **queue_kwargs)

    def _checked_response(self, raw: Any, **expected: Any) -> dict[str, Any]:
        checked = validate_job(raw, **expected)
        transfer = getattr(self._bridge, "_reference_transfer_response", None)
        if callable(transfer):
            transfer(raw, checked)
        return checked

    def capabilities(self, *, timeout: float = 15) -> MyBoxCapabilities:
        # A failed refresh must not leave a previously ready catalogue usable.
        self._capabilities = None
        try:
            self._bound_bridge()
            admission = queue.discover(self._bridge, timeout=timeout)
            if admission is not None:
                queue.require_bound(self._bridge, admission, "only")
            raw = admission.profile("only_syntax") if admission is not None else self._request("GET", API + "/capabilities", timeout=timeout)
        except Exception as exc:
            if getattr(exc, "status_code", None) in (404, 405, 501):
                raise MyBoxError("This Broker My Box adapter is not installed. No video was submitted.", code="MY_BOX_UNSUPPORTED") from exc
            raise
        self._capabilities = replace(parse_capabilities(raw), _queue_admission=admission)
        return self._capabilities

    def workspace(self, *, create: bool = False, explicit_selection: bool = False, timeout: float = 15) -> dict[str, Any] | None:
        if type(create) is not bool or type(explicit_selection) is not bool or (create and not explicit_selection):
            _fail("My Box workspace creation requires explicit selection.", "MY_BOX_SELECTION_INVALID")
        if create and (self._capabilities is None or not self._capabilities.implemented or not self._capabilities.workspace_management_enabled):
            _fail("Check My Box capabilities before creating a workspace.", "MY_BOX_UNSUPPORTED")
        admission = self._capabilities._queue_admission if self._capabilities else None
        if admission is not None:
            self._bound_bridge()
            queue.require_bound(self._bridge, admission, "only")
            current = self._capabilities.workspace
            # A target is returned only for explicit create intent. No native
            # workspace write, and read-only callers still see null if absent.
            return current if current is not None or not create else admission.workspace_intent
        raw = self._request("GET", API + "/workspace", timeout=timeout)
        current = self._parse_workspace(raw)
        if create and current is None:
            raw = self._request("POST", API + "/workspace", payload={"explicit_selection": True}, timeout=timeout)
            current = self._parse_workspace(raw)
            if current is None:
                _fail("Broker did not create the explicitly selected My Box workspace.")
        return current

    @staticmethod
    def _parse_workspace(raw: Any) -> dict[str, Any] | None:
        if (not isinstance(raw, dict) or raw.get("schema") != WORKSPACE_SCHEMA or type(raw.get("version")) is not int
                or raw["version"] != 1 or type(raw.get("created")) is not bool):
            _fail("Broker returned an invalid My Box workspace.")
        return _workspace(raw.get("workspace"))

    def create(self, invocation: MyBoxInvocation, *, on_submission_prepared: Callable[[MyBoxInvocation], None] | None = None,
               is_alive: Callable[[], bool] | None = None, timeout: float = 300) -> dict[str, Any]:
        _alive(is_alive)
        if self._capabilities is None:
            _fail("Check My Box readiness before rendering.", "MY_BOX_UNSUPPORTED")
        payload = invocation.payload()
        operation = "draft_final" if payload.get("draft_job_id") else "only"
        self._capabilities.require_submission(operation)
        admission = self._capabilities._queue_admission
        if invocation._queue_admission is not admission:
            _fail("Private queue admission changed after preparation.", "MY_BOX_IDENTITY_MISMATCH")
        queue_kwargs = {}
        if admission is not None:
            self._bound_bridge()
            queue.require_bound(self._bridge, admission, operation)
            queue_kwargs = {"queue_admission": admission, "queue_operation": operation}
        current_workspace = self._capabilities.workspace
        if current_workspace is not None and current_workspace["workspace_id"] != invocation.workspace_id:
            _fail("My Box invocation belongs to a different account workspace.", "MY_BOX_IDENTITY_MISMATCH")
        if admission is not None and current_workspace is None:
            intent = admission.workspace_intent
            if intent is None or intent["selection"] != invocation.selection:
                _fail("Private queue workspace intent does not match the invocation.", "MY_BOX_IDENTITY_MISMATCH")
        if admission is not None and payload.get("draft_job_id"):
            detail = self.detail(payload["draft_job_id"], selection=invocation.selection, timeout=min(timeout, 15))
            final = parse_draft_final_state(detail)
            if (final is None or not final["eligible"] or final["state"] != "available" or final.get("child_task_id")
                    or type(final.get("expires_at")) is not int or time.time() >= final["expires_at"]):
                _fail("Private Draft Final is no longer eligible. Retrieve the same source.", "MY_BOX_RESULT_NOT_READY")
        checked = prepare_invocation(payload, selection=invocation.selection, title=payload.get("my_box_title"),
            client_request_id=invocation.client_request_id, queue_admission=admission)
        if checked != invocation:
            _fail("My Box invocation no longer matches its snapshot.", "MY_BOX_IDENTITY_MISMATCH")
        if on_submission_prepared is not None:
            on_submission_prepared(invocation)
        _alive(is_alive)
        raw = self._request("POST", "/api/v1/generate/video", payload=payload, timeout=timeout,
            submission=True, idempotency_key=invocation.client_request_id, **queue_kwargs)
        try:
            return self._checked_response(raw, invocation=invocation)
        except MyBoxError as exc:
            # The server may have accepted even an invalid response. Preserve
            # the caller's prepared checkpoint and prohibit an automatic POST.
            exc.submission_outcome_unknown = True
            raise

    def refresh(self, identifier: str, *, selection: dict[str, Any], client_request_id: str = "",
                invocation: MyBoxInvocation | None = None, timeout: float = 300) -> dict[str, Any]:
        selected = normalize_selection(selection)
        identifier = _identifier(identifier)
        raw = self._request("POST", "/api/v1/jobs/" + quote(identifier, safe="") + "/refresh", timeout=timeout)
        return self._checked_response(raw, selection=selected, expected_job_id=identifier, client_request_id=client_request_id, invocation=invocation)

    def detail(self, task_id: str, *, selection: dict[str, Any], client_request_id: str = "",
               timeout: float = 15) -> dict[str, Any]:
        task_id, selected = _task_id(task_id), normalize_selection(selection)
        raw = self._request("GET", API + "/items/" + task_id, timeout=timeout)
        return self._checked_response(raw, selection=selected, expected_job_id=task_id, client_request_id=client_request_id)

    def download_info(self, job: dict[str, Any]) -> MyBoxDownload:
        checked = validate_job(job)
        if checked["status"] not in JOB_SUCCESS_STATUSES:
            _fail("My Box original video is not completed.", "MY_BOX_RESULT_NOT_READY")
        expected = self.server_url + API + "/items/" + checked["task_id"] + "/media?download=1"
        if checked.get("download_url") != expected:
            _fail("Broker authorization was refused for a different private media URL.", "MY_BOX_RESULT_UNTRUSTED")
        return MyBoxDownload(expected, checked["task_id"], checked["workspace_id"])

    def download_result(self, job: dict[str, Any], *, max_bytes: int = MAX_VIDEO_BYTES,
                        is_alive: Callable[[], bool] | None = None, timeout: float = 300) -> bytes:
        _alive(is_alive)
        self._bound_bridge()
        info = self.download_info(job)
        if type(max_bytes) is not int or not 0 < max_bytes <= MAX_VIDEO_BYTES:
            _fail("My Box video download size limit is invalid.")
        request = urllib.request.Request(info.url, headers={"Accept": "video/mp4,video/quicktime,video/webm",
            "Authorization": "Bearer " + self._bridge._load_access_token()}, method="GET")
        with self._bridge._opener.open(request, timeout=timeout) as response:
            if response.geturl() != info.url or getattr(response, "status", 200) != 200:
                _fail("My Box original download changed its origin, path or range.", "MY_BOX_RESULT_UNTRUSTED")
            headers = response.headers
            def header(name: str) -> str:
                values = headers.get_all(name) if hasattr(headers, "get_all") else [headers.get(name)]
                if not values or len(values) != 1 or values[0] is None:
                    _fail("My Box download metadata is missing or duplicated.", "MY_BOX_DOWNLOAD_INVALID")
                return str(values[0])
            mime = header("Content-Type").split(";", 1)[0].strip().lower()
            length, etag = header("Content-Length"), header("ETag")
            if (mime not in ("video/mp4", "video/quicktime", "video/webm") or re.fullmatch(r"[1-9][0-9]{0,12}", length) is None
                    or not 0 < int(length) <= max_bytes or re.fullmatch(r'"[a-fA-F0-9]{64}"', etag) is None
                    or headers.get("Transfer-Encoding") or headers.get("Content-Encoding", "identity").lower() != "identity"):
                _fail("My Box original download metadata is invalid.", "MY_BOX_DOWNLOAD_INVALID")
            expected_length, expected_sha = int(length), etag[1:-1].lower()
            chunks, size, checksum = [], 0, hashlib.sha256()
            while True:
                _alive(is_alive)
                chunk = response.read(min(1024 * 1024, expected_length - size + 1))
                if not chunk:
                    break
                size += len(chunk)
                if size > expected_length:
                    _fail("My Box original download exceeds its advertised length.", "MY_BOX_DOWNLOAD_INVALID")
                chunks.append(chunk)
                checksum.update(chunk)
            if size != expected_length or not hmac.compare_digest(checksum.hexdigest(), expected_sha):
                _fail("My Box original download failed its length or checksum check.", "MY_BOX_DOWNLOAD_INVALID")
        raw = b"".join(chunks)
        if (mime in ("video/mp4", "video/quicktime") and (len(raw) < 12 or raw[4:8] != b"ftyp")) or (mime == "video/webm" and not raw.startswith(b"\x1aE\xdf\xa3")):
            _fail("My Box original video container does not match its type.", "MY_BOX_DOWNLOAD_INVALID")
        _alive(is_alive)
        return raw

    def source_reference(self, source_task_id: str, target_client_request_id: str, task: str, *,
                         selection: dict[str, Any], timeout: float = 15) -> dict[str, Any]:
        selected = normalize_selection(selection)
        source_task_id, target_client_request_id = _task_id(source_task_id), _identifier(target_client_request_id)
        if task not in ("Video Editing", "Video Extension", "Reference to Video"):
            _fail("My Box source-reference task is invalid.")
        source = self.detail(source_task_id, selection=selected, timeout=timeout)
        if source["status"] not in JOB_SUCCESS_STATUSES:
            _fail("My Box source video is not completed.", "MY_BOX_RESULT_NOT_READY")
        admission = self._capabilities._queue_admission if self._capabilities else None
        if admission is not None:
            queue.require_bound(self._bridge, admission, "only")
            return {"url": queue.source_marker(source_task_id), "queue_only": True}
        raw = self._request("POST", API + "/items/" + source_task_id + "/source-reference",
            payload={"target_client_request_id": target_client_request_id, "task": task}, timeout=timeout)
        expected_prefix = self.server_url + API + "/provider-source/"
        if (not isinstance(raw, dict) or raw.get("schema") != "hmb-only-my-box-source-reference-v1"
                or type(raw.get("version")) is not int or raw["version"] != 1 or raw.get("scope") != SCOPE
                or raw.get("target_client_request_id") != target_client_request_id or not isinstance(raw.get("url"), str)
                or not raw["url"].startswith(expected_prefix) or re.fullmatch(r"[A-Za-z0-9_-]{43}", raw["url"][len(expected_prefix):]) is None
                or type(raw.get("expires_at")) is not int or raw["expires_at"] <= 0):
            _fail("Broker returned an invalid private source-reference grant.", "MY_BOX_RESULT_UNTRUSTED")
        return json.loads(_json(raw, limit=8192))
