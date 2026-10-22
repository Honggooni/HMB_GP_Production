"""Only-mode private video controller. No production project/review side effects."""
from __future__ import annotations

import asyncio
from contextlib import suppress
from copy import deepcopy
import hashlib
import json
import ntpath
import os
from pathlib import Path
import re
import sys
import threading
import time
from typing import Any
from uuid import uuid4

import _hmb_broker_config as broker_config
import _hmb_my_box as protocol
import _hmb_reference_leases as reference_leases
import _hmb_queue_admission as queue

TITLE_PARAMETER = "my_box_title"
SOURCE_PARAMETER = "my_box_source_task_id"
CHECKPOINT_PARAMETER = "HMB_MY_BOX_CHECKPOINT"
CHECKPOINT_SCHEMA = "hmb-only-my-box-local-checkpoint-v1"
_JOURNAL_ID = re.compile(r"[a-f0-9]{32}\Z")
_SHA = re.compile(r"[a-f0-9]{64}\Z")
_STAGES = frozenset(("prepared", "submitting", "polling", "remote_completed", "local_succeeded", "failed", "not_submitted", "interrupted"))
_STATUSES = protocol.JOB_ACTIVE_STATUSES | protocol.JOB_SUCCESS_STATUSES | protocol.JOB_FAILURE_STATUSES | {"not_submitted", "cancelled_locally", "timed_out"}
_FIELDS = frozenset(("schema", "version", "journal_id", "revision", "selection", "broker_server_url", "client_request_id", "job_id", "stage", "status", "model_id", "task", "output_format", "output_file", "saved_file_sha256", "request_fingerprint", "updated_at_ms", "draft_preview", "draft_source_task_id", "draft_source", "draft_final", "reference_lease_id", "queue_only_headers"))


def _host(node: Any) -> Any:
    # Imported lazily after the node module finishes defining its native class.
    for cls in type(node).__mro__:
        module = sys.modules.get(cls.__module__)
        if module is not None and hasattr(module, "_SeedanceDraftOutputDestination"):
            return module
    import HMBSeedanceGeneration
    return HMBSeedanceGeneration


def is_selected(node: Any) -> bool:
    """Pure selection predicate: an unavailable Shot is never an Only fallback."""
    try:
        return bool(node.get_parameter_value("only_project") == protocol.MY_BOX_LABEL
                    and node._hmb_seedance_execution_mode() == "only")
    except (AttributeError, KeyError, TypeError, ValueError):
        return False  # Partial native construction is never private authority.


def install_parameters(node: Any) -> None:
    m = _host(node)
    for name, label, default, tooltip in (
        (TITLE_PARAMETER, "My Box Title", "Only video", "Private video title. This does not create a production Shot."),
        (SOURCE_PARAMETER, "My Box Source Task ID", "", "Legacy saved value; new renders use Reference Videos."),
    ):
        node.add_parameter(m.ParameterString(name=name, default_value=default, allowed_modes={m.ParameterMode.PROPERTY},
            tooltip=tooltip, hide=True, hide_property=(name == SOURCE_PARAMETER),
            ui_options={"display_name": label, "hide_handles": True, "hide": True,
                        "hide_property": name == SOURCE_PARAMETER}))
    node.add_parameter(m.ParameterDict(name=CHECKPOINT_PARAMETER, default_value={}, allowed_modes={m.ParameterMode.PROPERTY},
        settable=False, serializable=True, hide=True, hide_property=True, hide_label=True,
        ui_options={"hide": True, "hide_property": True, "hide_label": True, "hide_handles": True}))


def normalize_checkpoint(raw: Any) -> dict[str, Any]:
    if not raw:
        return {}
    if not isinstance(raw, dict) or set(raw) - _FIELDS or raw.get("schema") != CHECKPOINT_SCHEMA or type(raw.get("version")) is not int or raw["version"] != 1:
        raise ValueError("The private My Box recovery record is invalid. No request was submitted.")
    if (not isinstance(raw.get("journal_id"), str) or not _JOURNAL_ID.fullmatch(raw["journal_id"])
            or raw.get("stage") not in _STAGES or raw.get("status") not in _STATUSES
            or type(raw.get("revision")) is not int or not 0 <= raw["revision"] <= 2_147_483_647
            or type(raw.get("updated_at_ms")) is not int or raw["updated_at_ms"] < 0):
        raise ValueError("The private My Box recovery identity is invalid.")
    protocol.normalize_selection(raw.get("selection"))
    if "queue_only_headers" in raw:
        queue.identity(raw["queue_only_headers"])
    broker_config.normalize_broker_base_url(raw.get("broker_server_url"))
    for field, limit in (("client_request_id", 256), ("model_id", 256), ("task", 128), ("output_file", 4096)):
        value = raw.get(field)
        if not isinstance(value, str) or not value or len(value) > limit or re.search(r"[\x00-\x1f\x7f]", value):
            raise ValueError("The private My Box recovery field is invalid.")
    if protocol.IDENTIFIER.fullmatch(raw["client_request_id"]) is None or raw["client_request_id"].startswith("job-mybox-"):
        raise ValueError("The private My Box client request ID is invalid.")
    for field in ("job_id", "draft_source_task_id"):
        if raw.get(field) and (not isinstance(raw[field], str) or protocol.TASK_ID.fullmatch(raw[field]) is None):
            raise ValueError("The private My Box Task identity is invalid.")
    if raw.get("output_format") not in {"mp4", "mov"} or raw["output_file"].startswith(("http:", "https:", "data:")):
        raise ValueError("The private My Box local destination is invalid.")
    for field in ("saved_file_sha256", "request_fingerprint"):
        if raw.get(field) and (not isinstance(raw[field], str) or _SHA.fullmatch(raw[field]) is None):
            raise ValueError("The private My Box recovery checksum is invalid.")
    # Final metadata is a bounded, validated protocol projection, never raw detail.
    for field in ("draft_final", "draft_source"):
        if field in raw and not isinstance(raw[field], dict):
            raise ValueError("The private My Box Draft recovery record is invalid.")
        value = raw.get(field, {})
        allowed = {"schema", "version", "state", "eligible", "source_task_id", "child_task_id", "child_status", "expires_at", "expiry_basis", "workspace_id", "selection", "final_client_request_id", "eligibility_scope", "resubmit_allowed", "reason_code"}
        if set(value) - allowed or any(isinstance(v, (dict, list)) for k, v in value.items() if k != "selection"):
            raise ValueError("The private My Box recovery record contains unsupported Draft data.")
        if value:
            if value.get("workspace_id") != raw["selection"]["workspace_id"] or protocol.normalize_selection(value.get("selection")) != raw["selection"]:
                raise ValueError("The private Draft workspace changed.")
    if type(raw.get("draft_preview")) is not bool:
        raise ValueError("The private Draft flag is invalid.")
    if raw.get("reference_lease_id") and reference_leases.lease_id(raw["reference_lease_id"]) != raw["reference_lease_id"]:
        raise ValueError("The private reference lease identity is invalid.")
    encoded = json.dumps(raw, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > 32768:
        raise ValueError("The private My Box recovery record is too large.")
    return json.loads(encoded)


def _write_journal(root: Path, value: dict[str, Any]) -> None:
    value = normalize_checkpoint(value)
    root.mkdir(parents=True, exist_ok=True)
    target = root / (value["journal_id"] + ".json")
    temporary = root / ("." + value["journal_id"] + "." + uuid4().hex + ".partial")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        with suppress(OSError):
            temporary.unlink()


class MyBoxController:
    def __init__(self, node: Any, *, broker_factory: Any = None, journal_root: Path | str | None = None) -> None:
        self.node = node
        self.broker_factory = broker_factory or protocol.MyBoxBroker
        self.journal_root = Path(journal_root) if journal_root is not None else Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local/share") / "HMB_GP_Production" / "my-box-recovery"
        self._epoch = 0
        self._deleted = False
        self._lock = threading.Lock()
        self._busy = False
        self._post_started = False
        self._capabilities = None
        self._pending: set[asyncio.Task[Any]] = set()
        self._active_final_source = ""
        self._owner_journal_id = ""
        self._projection_checked_at = 0.0
        self._restore_future = None
        self._run_epoch = 0
        self._run_origin = ""

    def invalidate(self, *, deleted: bool = False) -> None:
        self._epoch += 1
        self._deleted = self._deleted or deleted
        self._capabilities = None
        self._projection_checked_at = 0.0

    def checkpoint(self) -> dict[str, Any]:
        return normalize_checkpoint(self.node.get_parameter_value(CHECKPOINT_PARAMETER))

    def handles_existing(self) -> bool:
        identifier = str(self.node.parameter_output_values.get("generation_id") or "")
        if protocol.TASK_ID.fullmatch(identifier):
            return True
        with suppress(ValueError):
            cp = self.checkpoint()
            return bool(cp and identifier == cp["client_request_id"])
        return False

    def current_output_is_private(self) -> bool:
        if str(self.node.parameter_output_values.get("generation_id") or "").startswith("job-mybox-"):
            return True
        with suppress(ValueError):
            cp = self.checkpoint()
            def normalized(path: str) -> str:
                return ntpath.normcase(ntpath.normpath(path)) if re.match(r"^[A-Za-z]:[\\/]", path) or "\\" in path else os.path.normcase(os.path.normpath(path))
            for name in ("VIDEO_OUT", "video_url"):
                artifact = self.node.parameter_output_values.get(name)
                path = str(getattr(artifact, "value", artifact) or "")
                if cp and path and normalized(path) == normalized(cp.get("output_file", "")):
                    return True
                cached = getattr(self.node, "_hmb_native_local_video_preview", None)
                if (cp and isinstance(cached, tuple) and len(cached) == 2 and isinstance(cached[0], tuple)
                        and len(cached[0]) == 3 and path == cached[0][2] and normalized(cached[0][1]) == normalized(cp["output_file"])):
                    return True
            # During native replay an alias read URL can arrive before its raw
            # output and Task ID. Do not borrow old production provenance for
            # that temporarily ambiguous artifact. A subsequently restored
            # public Task/raw original removes this conservative guard.
            alias = self.node.parameter_output_values.get("video_url")
            alias_value = str(getattr(alias, "value", alias) or "")
            if (cp and cp.get("stage") == "local_succeeded" and not self.node.parameter_output_values.get("VIDEO_OUT")
                    and not self.node.parameter_output_values.get("generation_id") and alias_value.startswith(("http://", "https://"))):
                return True
        return False

    def _alive(self, epoch: int, origin: str, *, selection: bool = True, allow_cancelled: bool = False) -> bool:
        node = self.node
        return bool(not self._deleted and not getattr(node, "_hmb_node_deleted", False)
            and node._runtime_node_is_live(require_registered=True)
            and epoch == self._epoch and (allow_cancelled or not bool(getattr(node, "is_cancellation_requested", False)))
            and (not selection or (is_selected(node) and node._selected_broker_server_url() == origin)))

    def _guard(self, epoch: int, origin: str) -> None:
        if not self._alive(epoch, origin):
            raise protocol.MyBoxError("My Box selection changed or this action was stopped. No replacement was submitted.", code="MY_BOX_CANCELLED")

    def _snapshot(self) -> dict[str, Any]:
        node, m = self.node, _host(self.node)
        get = node.get_parameter_value
        raw_model = str(get("model_id") or m.MODEL_NAME_SEEDANCE_2_5)
        model = m.MODEL_ID_ALIASES.get(raw_model, raw_model)
        videos = list(node._get_list_input(m.VIDEO_REFERENCES_PARAMETER))
        if not videos and not node._list_input_is_authoritative(m.VIDEO_REFERENCES_PARAMETER):
            videos = [get(f"reference_video_{i}") for i in range(1, m.LEGACY_VIDEO_REFERENCE_SLOTS + 1) if node._has_reference_value(get(f"reference_video_{i}"))]
        params = {"model_id": model, "prompt": str(get("prompt") or ""), "task": str(get("task") or m.TASK_REFERENCE_TO_VIDEO),
            "input_mode": get("input_mode") or m.INPUT_MODE_MULTIMODAL_REFERENCES,
            "reference_images": list(node._get_list_input("reference_images")), "video_references": videos,
            "video_reference_slots": [], "reference_audio": list(node._get_list_input("reference_audio")),
            "first_frame": get("first_frame"), "last_frame": get("last_frame"),
            "resolution": str(get("resolution") or m.MODEL_DEFAULT_RESOLUTIONS.get(model, "720p")), "ratio": str(get("ratio") or "adaptive"),
            "duration": get("duration"), "generate_audio": bool(get("generate_audio")), "watermark": bool(get("watermark")),
            "output_format": str(get("output_format") or ("mov" if model == m.SEEDANCE_2_5_MODEL_ID else "mp4")).lower(),
            "return_last_frame": bool(get("return_last_frame")), "execution_expires_after": get("execution_expires_after"),
            "priority": get("priority") if model == m.SEEDANCE_2_0_MODEL_ID else 0,
            "poll_interval_seconds": get("poll_interval_seconds"), "generation_timeout_seconds": get("generation_timeout_seconds"),
            "auto_publish_local_videos": bool(get("auto_publish_local_videos")),
            "local_video_upload_service": get("local_video_upload_service") or m.LOCAL_VIDEO_UPLOAD_GRIPTAPE,
            "tos_region": get("tos_region") or m.DEFAULT_TOS_REGION, "tos_endpoint": get("tos_endpoint") or m.DEFAULT_TOS_ENDPOINT,
            "tos_url_validity_seconds": get("tos_url_validity_seconds"), "resume_generation_id": "", "draft_action": m.DRAFT_ACTION_OFF}
        return params

    def preflight(self) -> dict[str, Any]:
        if not is_selected(self.node):
            raise ValueError("Select Only and My Box explicitly before private generation.")
        self.node._assert_only_mode_inputs()
        params = self._snapshot()
        self._validate_snapshot(params, self.node.get_parameter_value(TITLE_PARAMETER), "")
        return params

    def _validate_snapshot(self, params: dict[str, Any], title: Any, source: Any) -> None:
        if not isinstance(title, str) or not title.strip() or len(title) > 128 or re.search(r"[\x00-\x1f\x7f]", title):
            raise ValueError("Enter a valid My Box Title (1–128 characters).")
        if not isinstance(source, str) or (source and protocol.TASK_ID.fullmatch(source) is None):
            raise ValueError("My Box Source must be an owned job-mybox-... Task ID.")
        if params["model_id"] == _host(self.node).SEEDANCE_2_5_MODEL_ID and params["return_last_frame"]:
            raise ValueError("My Box does not yet return a separate last-frame image. Turn return_last_frame OFF; no video was submitted.")
        # The owned-source grant is resolved only at execution, not UI selection.
        validation = deepcopy(params)
        if source:
            validation["video_references"] = ["https://owned-source.invalid/private-video", *validation["video_references"]]
        self.node._validate_parameters(validation)
        self.node._validate_broker_model(params["model_id"])
        params["output_format"] = validation["output_format"]
        params["return_last_frame"] = validation["return_last_frame"]

    def validate_start(self) -> None:
        cp = self.checkpoint()
        if cp and (str(self.node.get_parameter_value("resume_generation_id") or "").strip()
                or cp["stage"] not in {"local_succeeded", "failed", "not_submitted"}
                or self.node.get_parameter_value("draft_action") == _host(self.node).DRAFT_ACTION_FINAL):
            return
        self.preflight()

    def _journal_owner(self) -> str:
        value = str(self.node._draft_owner_id() or "").replace("-", "")
        if _JOURNAL_ID.fullmatch(value) is None:
            raise ValueError("Save this Generator's stable owner identity before using My Box.")
        self._owner_journal_id = value
        return value

    async def _recover_checkpoint(self, cp: dict[str, Any]) -> dict[str, Any]:
        owner = self._journal_owner()
        def read() -> dict[str, Any]:
            path = self.journal_root / (owner + ".json")
            if not path.exists():
                return {}
            if path.stat().st_size > 32768:
                raise ValueError("Private recovery JSON is too large; no new request was submitted.")
            record = normalize_checkpoint(json.loads(path.read_text(encoding="utf-8")))
            if record.get("journal_id") != owner:
                raise ValueError("Private recovery owner does not match this Generator.")
            return record
        durable = await asyncio.to_thread(read)
        if durable and (not cp or durable["revision"] > cp["revision"]):
            if self._deleted or getattr(self.node, "_hmb_node_deleted", False):
                raise ValueError("The private Generator was deleted.")
            self.node.set_parameter_value(CHECKPOINT_PARAMETER, deepcopy(durable), emit_change=False)
            return durable
        return cp

    async def _broker(self, origin: str) -> Any:
        bridge = await self.node._ensure_broker_connected(server_url=origin)
        return self.broker_factory(bridge)

    async def _persist(self, value: dict[str, Any], *, required: bool = True) -> dict[str, Any]:
        current = self.checkpoint()
        value = normalize_checkpoint({**value, "journal_id": self._owner_journal_id or self._journal_owner(),
            "revision": min(2_147_483_647, max(int(value.get("revision", 0)), int(current.get("revision", 0))) + 1), "updated_at_ms": int(time.time() * 1000)})
        if self._deleted or getattr(self.node, "_hmb_node_deleted", False):
            raise protocol.MyBoxError("The private Generator was deleted.", code="MY_BOX_CANCELLED")
        try:
            await asyncio.to_thread(_write_journal, self.journal_root, value)
        except Exception:
            if required:
                raise RuntimeError("My Box recovery JSON could not be saved. No new render was submitted.") from None
        if self._deleted or getattr(self.node, "_hmb_node_deleted", False):
            # The paid intent remains on disk, but a retired node owns no UI.
            return value
        self.node.set_parameter_value(CHECKPOINT_PARAMETER, deepcopy(value), emit_change=False)
        return value

    def _status(self, status: str, identifier: str = "", *, details: str = "", successful: bool | None = None) -> None:
        if self._deleted or getattr(self.node, "_hmb_node_deleted", False):
            return
        node = self.node
        if successful is not None:
            # Commit the result before optional host status/UI callbacks.
            node._execution_succeeded = successful
            for name, value in (("was_successful", successful), ("result_details", details)):
                self._output(name, value)
        if identifier:
            self._output("generation_id", identifier)
        self._output("generation_status", status)
        self._output("provider_response", {"transport": "fn_ai_broker", "scope": protocol.SCOPE,
            "id": identifier, "status": status, "resubmit_allowed": False})
        with suppress(Exception):
            # The public status mapper treats remote "succeeded" as the start
            # of download. A verified, locally committed private result has
            # already passed that boundary; keep its final preview terminal.
            phase = ("succeeded" if status == "succeeded" and successful is True else
                status if status in {"downloading", "verifying"} else
                node._generation_preview_phase_for_status(status))
            node._publish_generation_preview(phase, generation_id=identifier,
                action="refresh_existing" if identifier and status not in {"succeeded", "failed"} else "none")
        if successful is not None:
            try:
                node._set_status_results(was_successful=successful, result_details=details)
            except Exception:
                if node.parameter_output_values.get("was_successful") is not successful:
                    raise

    def _output(self, name: str, value: Any) -> None:
        try:
            self.node.parameter_output_values[name] = value
        except Exception:
            current = self.node.parameter_output_values.get(name)
            if current is not value and current != value:
                raise

    async def _payload(self, params: dict[str, Any], broker: Any, selection: dict[str, Any], client_id: str,
                       *, epoch: int, origin: str, final_source: dict[str, Any] | None = None) -> dict[str, Any]:
        node, m = self.node, _host(self.node)
        if final_source:
            return {"provider": "volcengine_ark", "model": params["model_id"], "hmb_generation_task": final_source["task"],
                "draft_job_id": final_source["job_id"], "quality": "1080p", "resolution": "1080p", "output_format": params["output_format"]}
        source_id = params.get("_private_source_id", "")
        deferred_source = ""
        if source_id:
            grant = await asyncio.to_thread(broker.source_reference, source_id, client_id, params["task"], selection=selection)
            self._guard(epoch, origin)
            if grant.get("queue_only") is True:
                admission = getattr(getattr(broker, "_capabilities", None), "_queue_admission", None)
                queue.require_bound(broker._bridge, admission, "only")
                deferred_source = queue.source_marker(source_id)
                if grant["url"] != deferred_source:
                    raise ValueError("Private queue source identity changed.")
            else:
                params = dict(params, video_references=[grant["url"], *params["video_references"]])
        params = await node._run_blocking_generation_stage(node._prepare_video_references_for_run, params)
        self._guard(epoch, origin)
        input_mode = m.TASK_INPUT_MODES[params["task"]]
        payload = {"provider": "volcengine_ark", "model": params["model_id"], "hmb_generation_task": params["task"],
            "task": params["task"], "input_mode": input_mode, "prompt": params["prompt"], "duration_seconds": params["duration"],
            "quality": params["resolution"], "resolution": params["resolution"] if params["model_id"] == m.SEEDANCE_2_5_MODEL_ID else ("720x1280" if params["ratio"] in {"9:16", "3:4"} else "1280x720"),
            "aspect_ratio": params["ratio"], "generate_audio": params["generate_audio"], "watermark": params["watermark"],
            "execution_expires_after": params["execution_expires_after"], "output_format": params["output_format"], "return_last_frame": False}
        if params["model_id"] == m.SEEDANCE_2_5_MODEL_ID:
            # Private Only posts directly through MyBoxBroker, so it must carry
            # the same provider subtask as the ordinary Generator bridge.
            omni_task = m.TASK_OMNI_REFERENCE_TYPES.get(params["task"])
            if omni_task:
                payload["omni_reference_task_type"] = omni_task
        if params["model_id"] == m.SEEDANCE_2_0_MODEL_ID:
            payload["priority"] = params["priority"]
        if params.get("_private_draft_preview"):
            payload["draft"] = True
        fields = []
        if input_mode == m.INPUT_MODE_FIRST_LAST_FRAME:
            fields = [("first_frame", "image", [params["first_frame"]] if params["first_frame"] else []),
                      ("last_frame", "image", [params["last_frame"]] if params["last_frame"] else [])]
        elif input_mode == m.INPUT_MODE_MULTIMODAL_REFERENCES:
            fields = [("image_urls", "image", params["reference_images"]), ("video_urls", "video", params["video_references"]), ("audio_urls", "audio", params["reference_audio"])]
        await asyncio.to_thread(node._preflight_broker_media_size, payload, tuple(fields))
        for field, kind, values in fields:
            if values:
                payload[field] = await asyncio.to_thread(lambda: [node._prepare_media_reference(kind, value) for value in values])
        if deferred_source:
            if input_mode != m.INPUT_MODE_MULTIMODAL_REFERENCES:
                raise ValueError("Private queue sources are permitted only in video_urls.")
            payload["video_urls"] = [deferred_source, *payload.get("video_urls", [])]
            if len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > protocol.MAX_REQUEST_BYTES:
                raise ValueError("Private queue request exceeds the Broker size limit.")
        return payload

    async def _create(self, broker: Any, invocation: Any, *, epoch: int, origin: str) -> dict[str, Any]:
        cancelled = threading.Event()
        def permitted() -> bool:
            return not cancelled.is_set() and self._alive(epoch, origin)
        def guard() -> None:
            if not permitted():
                raise protocol.MyBoxError("The queued private submission was stopped before HTTP.", code="MY_BOX_CANCELLED")
        def invoke() -> dict[str, Any]:
            guard()
            context = _host(self.node)._BROKER_NATIVE_SUBMISSION_CONTEXT
            previous = getattr(context, "callbacks", None)
            def started() -> None:
                guard()
                self._post_started = True
            def rejected() -> None:
                self._post_started = False
            context.callbacks = (guard, rejected, started)
            try:
                # Mark conservatively for injected transports which do not expose
                # native before-HTTP callbacks; known rejection flags undo it.
                self._post_started = True
                job = broker.create(invocation, is_alive=permitted, timeout=300)
                self.node._observe_reference_lease(job, bridge=broker._bridge, origin=origin,
                    requested_id=invocation.client_request_id, identifier=reference_lease, private_scope=True)
                return job
            finally:
                context.callbacks = previous
        reference_lease = self.checkpoint().get("reference_lease_id", "")
        pending = asyncio.create_task(asyncio.to_thread(invoke))
        self._pending.add(pending)
        def consume(task: asyncio.Task[Any]) -> None:
            self._pending.discard(task)
            if not task.cancelled():
                with suppress(Exception):
                    task.exception()
        pending.add_done_callback(consume)
        try:
            return await asyncio.shield(pending)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    async def _adopt(self, cp: dict[str, Any], job: dict[str, Any]) -> dict[str, Any]:
        if job["model"] != cp["model_id"] or job.get("task") != cp["task"]:
            raise protocol.MyBoxError("My Box result changed the submitted model or task.", code="MY_BOX_IDENTITY_MISMATCH")
        await self.node._run_blocking_generation_stage(self._observe_reference_job, cp, job)
        cp = {**cp, "job_id": job["job_id"], "status": job["status"],
              "stage": "remote_completed" if job["status"] == "completed" else "failed" if job["status"] == "failed" else "polling"}
        cp = await self._persist(cp, required=False)
        self._status("succeeded" if job["status"] == "completed" else job["status"], job["job_id"])
        return cp

    def _observe_reference_job(self, cp: dict[str, Any], job: dict[str, Any]) -> None:
        bridge = getattr(self.node, "_broker_bridge_instance", None)
        self.node._observe_reference_lease(job, bridge=bridge, origin=cp["broker_server_url"],
            requested_id=cp.get("job_id") or cp["client_request_id"],
            identifier=cp.get("reference_lease_id", ""), private_scope=True)

    async def _complete(self, cp: dict[str, Any], broker: Any, job: dict[str, Any], *, epoch: int, origin: str) -> dict[str, Any]:
        node, m = self.node, _host(self.node)
        self._guard(epoch, origin)
        self._status("downloading", job["job_id"])
        data = await asyncio.to_thread(broker.download_result, job, is_alive=lambda: self._alive(epoch, origin), timeout=300)
        self._guard(epoch, origin)
        self._status("verifying", job["job_id"])
        destination = m._SeedanceDraftOutputDestination(cp["output_file"])
        digest = hashlib.sha256(data).hexdigest()
        def same_file() -> bool:
            path = Path(cp["output_file"])
            return path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == digest
        cancelled = False
        if await asyncio.to_thread(same_file):
            saved = m.File(cp["output_file"])
        else:
            publication = asyncio.create_task(node._atomic_publish_completed_video(destination, data, cp["output_format"]))
            while True:
                try:
                    saved = await asyncio.shield(publication)
                    break
                except asyncio.CancelledError:
                    # A filesystem commit can have won the cancellation race.
                    # Observe its outcome before deciding whether this paid Task
                    # still requires publication; never report saved bytes lost.
                    cancelled = True
                    if publication.done() and publication.cancelled():
                        raise
        path = str(saved.location)
        cp = {**cp, "stage": "local_succeeded", "status": "completed", "output_file": path, "saved_file_sha256": digest}
        # Persist local success before optional UI hooks. A UI notification cannot
        # erase a completed paid render or cause another create on a fresh Run.
        cp = await self._persist(cp, required=False)
        if not self._alive(epoch, origin):
            return cp
        with suppress(Exception):
            self._publish_local(cp)
        if cp.get("draft_preview"):
            with suppress(Exception):
                detail = await asyncio.to_thread(broker.detail, cp["job_id"], selection=cp["selection"])
                parser = getattr(protocol, "parse_draft_final_state", None)
                projection = parser(detail) if callable(parser) else None
                if projection is not None:
                    self._guard(epoch, origin)
                    cp = await self._persist({**cp, "draft_final": projection}, required=False)
                    self._projection_checked_at = time.monotonic()
        self._guard(epoch, origin)
        with suppress(Exception):
            self._status("succeeded", cp["job_id"], successful=True,
                details=f"SUCCESS: My Box task {cp['job_id']} completed.\nSaved {cp['output_format'].upper()}: {path}")
        return cp

    def _publish_local(self, cp: dict[str, Any]) -> None:
        node, m = self.node, _host(self.node)
        artifact = m.VideoUrlArtifact(value=cp["output_file"], name=Path(cp["output_file"]).name)
        # Clear production provenance BEFORE any new artifact event can travel
        # to a downstream LUT; a private result must never borrow an old Shot.
        node._hmb_generated_video_source = {}
        node.parameter_values[m.GENERATED_VIDEO_SOURCE_PARAMETER] = {}
        self._output(m.GENERATED_VIDEO_SOURCE_PARAMETER, {})
        self._output("VIDEO_OUT", artifact)
        node._hmb_last_success_video = artifact
        self._output("video_url", node._native_local_video_preview_artifact(artifact))
        self._output("last_frame_url", None)
        node._hmb_generation_media_revision += 1

    async def _reuse_local(self, cp: dict[str, Any], *, epoch: int, origin: str) -> bool:
        if cp.get("stage") != "local_succeeded" or not cp.get("saved_file_sha256"):
            return False
        def verify() -> bool:
            path = Path(cp["output_file"])
            return path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == cp["saved_file_sha256"]
        if not await asyncio.to_thread(verify):
            return False
        self._guard(epoch, origin)
        with suppress(Exception):
            self._publish_local(cp)
        with suppress(Exception):
            self._status("succeeded", cp["job_id"], successful=True, details="SUCCESS: Existing private My Box original restored locally. " + cp["job_id"])
        return True

    async def _final_source(self, broker: Any, cp: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        if not cp or not cp.get("draft_preview") or not cp.get("job_id"):
            raise ValueError("Complete this My Box 480p Draft before finalizing.")
        detail = await asyncio.to_thread(broker.detail, cp["job_id"], selection=cp["selection"])
        self._guard(self._run_epoch, self._run_origin)
        parser = getattr(protocol, "parse_draft_final_state", None)
        projection = parser(detail) if callable(parser) else None
        if not getattr(self._capabilities, "draft_final_detail_supported", False) or projection is None:
            raise ValueError("This Broker has not advertised private Draft Final state. No Final was submitted.")
        cp = await self._persist({**cp, "draft_final": projection}, required=False)
        self._projection_checked_at = time.monotonic()
        return cp, projection

    def schedule_local_restore(self) -> None:
        """Hydration schedules only local file work; selection never contacts HTTP."""
        if self._busy or self._deleted or self._restore_future is not None and not self._restore_future.done():
            return
        with suppress(Exception):
            cp = self.checkpoint()
            if cp.get("stage") != "local_succeeded":
                return
            origin, epoch = cp["broker_server_url"], self._epoch
            loop = getattr(_host(self.node).GriptapeNodes.EventManager(), "event_loop", None)
            if loop is not None and loop.is_running():
                self._restore_future = asyncio.run_coroutine_threadsafe(self._reuse_local(cp, epoch=epoch, origin=origin), loop)
                self._restore_future.add_done_callback(lambda f: f.exception() if not f.cancelled() else None)

    def schedule_final(self, details: Any, expected_task_id: str) -> Any:
        m, node = _host(self.node), self.node
        try:
            if not node._runtime_node_is_live(require_registered=True):
                raise ValueError("The private Generator is inactive.")
            node._assert_draft_final_flow_idle()
            cp = self.checkpoint()
            if not is_selected(node) or cp.get("job_id") != expected_task_id or not self.draft_ui_state()["final_available"]:
                raise ValueError("Refresh this private Draft before finalizing; its identity or availability changed.")
            loop = getattr(m.GriptapeNodes.EventManager(), "event_loop", None)
            if loop is None or not loop.is_running():
                raise ValueError("The engine event loop is unavailable; no private Final was submitted.")
            with node._generation_refresh_lock:
                if self._busy or node._generation_run_active.is_set() or node._generation_refresh_running or node._hmb_draft_finalize_pending:
                    return m.NodeMessageResult(success=True, details="Generator is busy; no duplicate private Final scheduled.", response=details, altered_workflow_state=False)
                node._hmb_draft_finalize_pending = True
            clear = getattr(node, "clear_cancellation", None)
            if callable(clear):
                clear()
            expected_epoch, expected_origin = self._epoch, node._selected_broker_server_url()
            async def execute() -> None:
                try:
                    self._guard(expected_epoch, expected_origin)
                    if self.checkpoint().get("job_id") != expected_task_id:
                        raise ValueError("The private Draft changed before Final began; no video was submitted.")
                    await self.run(final=True, expected_source_task_id=expected_task_id)
                finally:
                    node._hmb_draft_finalize_pending = False
                    with suppress(Exception):
                        node._sync_seedance_shot_widget(emit_change=True)
            future = asyncio.run_coroutine_threadsafe(execute(), loop)
            node._hmb_draft_finalize_future = future
            def finished(f: Any) -> None:
                if f.cancelled():
                    node._hmb_draft_finalize_pending = False
                else:
                    with suppress(Exception):
                        f.exception()
            future.add_done_callback(finished)
            return m.NodeMessageResult(success=True, details="Private Draft final scheduled. Saved 480p settings are unchanged.", response=details, altered_workflow_state=False)
        except Exception as exc:
            return m.NodeMessageResult(success=False, details=str(exc), response=details, altered_workflow_state=False)

    def draft_ui_state(self) -> dict[str, Any]:
        node, m = self.node, _host(self.node)
        with suppress(ValueError):
            cp = self.checkpoint()
            projection = cp.get("draft_final", {}) if cp else {}
            caps = self._capabilities
            supported = str(node.get_parameter_value("model_id")) in {m.SEEDANCE_2_5_MODEL_ID, m.MODEL_NAME_SEEDANCE_2_5}
            available = bool(supported and projection.get("eligible") is True and projection.get("state") == "available"
                and not projection.get("child_task_id") and type(projection.get("expires_at")) is int
                and time.time() < projection["expires_at"] and self._projection_checked_at > 0
                and time.monotonic() - self._projection_checked_at <= 30
                and getattr(caps, "implemented", False) and (
                    (getattr(caps, "enabled", False) and getattr(caps, "generation_enabled", False) and not getattr(caps, "reason_code", ""))
                    or "draft_final" in getattr(getattr(caps, "_queue_admission", None), "operations", ()))
                and getattr(caps, "draft_final_detail_supported", False) and not self._busy)
            return m._seedance_draft_ui_value({"visible": supported
                and (node.get_parameter_value("resolution") == "480p" or bool(cp and cp.get("draft_preview"))),
                "action": node.get_parameter_value("draft_action"), "preview_available": not self._busy and node.get_parameter_value("resolution") == "480p",
                "final_available": available, "job_id": cp.get("job_id", "") if cp.get("draft_preview") else "",
                "effective_resolution": "1080p" if self._active_final_source else node.get_parameter_value("resolution"),
                "busy": self._busy, "final_busy": bool(self._busy and self._active_final_source), "cancel_available": False,
                "final_state": projection.get("state", "unavailable"), "final_visible": bool(supported and cp.get("draft_preview") and projection.get("state") not in {"completed", "expired", "not_draft"}),
                "final_task_id": projection.get("child_task_id", ""), "reason": "" if available else "Refresh this My Box Task to check private Draft Final availability."})
        return m._seedance_draft_ui_value()

    async def run(self, *, refresh: bool = False, final: bool = False, expected_source_task_id: str = "") -> None:
        if not self._lock.acquire(blocking=False):
            return
        self._busy, self._post_started = True, False
        self._capabilities = None
        self._projection_checked_at = 0.0
        epoch = self._epoch
        cp: dict[str, Any] = {}
        origin = ""
        refreshing = False
        historical_unresolved = False
        submitted_this_run = False
        completion_attempted = False
        try:
            if not is_selected(self.node):
                raise ValueError("Select Only and My Box to retrieve this private Task; no production request was sent.")
            cp = self.checkpoint()
            historical_unresolved = bool(cp and cp["stage"] not in {"local_succeeded", "failed", "not_submitted"})
            # Capture every authored input before the first network/disk await.
            # Capability/queue waits must not turn a click into a later edit.
            frozen_params = deepcopy(self._snapshot())
            frozen_title = self.node.get_parameter_value(TITLE_PARAMETER)
            # Preserve old serialized fields for a lossless reopen, but a
            # removed editor control must never be a hidden render input.
            # Recovery uses the durable checkpoint/Task, not this legacy value.
            frozen_source = ""
            frozen_action = self.node.get_parameter_value("draft_action")
            if frozen_params["model_id"] != _host(self.node).SEEDANCE_2_5_MODEL_ID:
                frozen_action = _host(self.node).DRAFT_ACTION_OFF
                if final:
                    raise ValueError("Private Draft final requires Seedance 2.5.")
            resume = str(self.node.get_parameter_value("resume_generation_id") or "").strip()
            frozen_destination = None
            destination_error = None
            if not refresh and not resume:
                try:
                    frozen_destination = self.node._build_generation_output_destination(draft=True).resolve()
                except Exception as exc:
                    destination_error = exc
            cp = await self._recover_checkpoint(cp)
            historical_unresolved = bool(cp and cp["stage"] not in {"local_succeeded", "failed", "not_submitted"})
            if expected_source_task_id and (not final or cp.get("job_id") != expected_source_task_id):
                raise ValueError("The private Draft source changed; no Final was submitted.")
            if resume and (not cp or resume not in {cp.get("job_id"), cp.get("client_request_id")}):
                raise ValueError("Resume Task ID does not match this Generator's private My Box checkpoint. No render was submitted.")
            if refresh and not cp:
                raise ValueError("There is no saved My Box Task to retrieve.")
            unresolved = bool(cp and cp["stage"] not in {"local_succeeded", "failed", "not_submitted"})
            historical_unresolved = unresolved
            # Unknown or not-yet-published intents always recover, even on Run.
            refreshing = bool(refresh or resume or unresolved)
            origin = cp["broker_server_url"] if refreshing or final else self.node._selected_broker_server_url()
            self._run_epoch, self._run_origin = epoch, origin
            if origin != self.node._selected_broker_server_url():
                raise ValueError("Restore the original Broker address to retrieve this My Box Task.")
            broker = await self._broker(origin)
            self._guard(epoch, origin)
            self._capabilities = None
            self._projection_checked_at = 0.0
            self._capabilities = await asyncio.to_thread(broker.capabilities)
            self._guard(epoch, origin)
            current_workspace = self._capabilities.workspace
            if cp and (refreshing or final) and current_workspace is not None and current_workspace["workspace_id"] != cp["selection"]["workspace_id"]:
                raise ValueError("Restore the original account workspace to retrieve this private My Box Task.")
            if refreshing:
                # Existing task lookup is the authorization authority, including
                # when the current account no longer has a workspace projection.
                job = await asyncio.to_thread(broker.refresh, cp.get("job_id") or cp["client_request_id"], selection=cp["selection"], client_request_id=cp["client_request_id"], timeout=300)
                self._guard(epoch, origin)
                await self.node._run_blocking_generation_stage(self._observe_reference_job, cp, job)
                if job["status"] == "completed" and await self._reuse_local(cp, epoch=epoch, origin=origin):
                    if cp.get("draft_preview"):
                        with suppress(Exception):
                            await self._final_source(broker, cp)
                    return
                cp = await self._adopt(cp, job)
                params = {"generation_timeout_seconds": int(self.node.get_parameter_value("generation_timeout_seconds") or 3600),
                          "poll_interval_seconds": int(self.node.get_parameter_value("poll_interval_seconds") or 30)}
            else:
                projection = None
                if final:
                    cp, projection = await self._final_source(broker, cp)
                    self._guard(epoch, origin)
                    child = projection.get("child_task_id")
                    if child:
                        job = await asyncio.to_thread(broker.detail, child, selection=cp["selection"])
                        self._guard(epoch, origin)
                        if job.get("draft_parent_task_id") != cp["job_id"]:
                            raise ValueError("The private Final child does not match this source Draft. No new render was submitted.")
                        cp = {**cp, "job_id": child, "client_request_id": job["client_request_id"], "draft_preview": False,
                            "draft_source_task_id": projection["source_task_id"], "draft_source": deepcopy(projection), "draft_final": {},
                            "output_file": str(Path(cp["output_file"]).with_name(Path(cp["output_file"]).stem + "-final-" + child + "." + cp["output_format"]))}
                        cp = await self._adopt(cp, job)
                        params = {"generation_timeout_seconds": int(self.node.get_parameter_value("generation_timeout_seconds") or 3600), "poll_interval_seconds": int(self.node.get_parameter_value("poll_interval_seconds") or 30)}
                    elif (not projection.get("eligible") or projection.get("state") != "available"
                          or type(projection.get("expires_at")) is not int or time.time() >= projection["expires_at"]):
                        raise ValueError("This private Draft Final is unavailable, expired or already reserved.")
                if not final or not projection.get("child_task_id"):
                    self._capabilities.require_submission("draft_final" if final else "only")
                    params = frozen_params
                    if destination_error is not None:
                        raise destination_error
                    params["_private_source_id"] = frozen_source
                    if not final:
                        # Validate the frozen snapshot, not controls edited while
                        # authentication/capabilities were in flight.
                        self._validate_snapshot(params, frozen_title, frozen_source)
                        if destination_error is not None:
                            raise destination_error
                    source_cp = deepcopy(cp) if final else None
                    if final:
                        self._active_final_source = source_cp["job_id"]
                        params.update(model_id=source_cp["model_id"], resolution="1080p", output_format=source_cp["output_format"], task=source_cp["task"], return_last_frame=False)
                        client_id = projection.get("final_client_request_id") or "mbx-final-v1-" + source_cp["job_id"].removeprefix("job-mybox-")
                        selection = source_cp["selection"]
                    else:
                        client_id = "hmb-mybox-" + uuid4().hex
                        workspace = await asyncio.to_thread(broker.workspace, create=True, explicit_selection=True)
                        self._guard(epoch, origin)
                        selection = workspace["selection"]
                        raw_draft = frozen_action
                        if raw_draft == _host(self.node).DRAFT_ACTION_FINAL:
                            raise ValueError("Use Draft final for the completed private Draft; a new Run does not reuse a Final action.")
                        if raw_draft == _host(self.node).DRAFT_ACTION_PREVIEW:
                            params.update(resolution="480p", return_last_frame=False, _private_draft_preview=True)
                    # Capability checks are read-only; never call production create.
                    bridge = broker._bridge
                    if params.get("_private_draft_preview") or final:
                        params["output_format"] = await asyncio.to_thread(bridge.require_seedance_draft_features, output_format=params["output_format"], allow_output_fallback=True)
                    else:
                        params["output_format"] = await asyncio.to_thread(bridge.require_seedance_features,
                            model_id=params["model_id"], task=params["task"], output_format=params["output_format"], return_last_frame=False, allow_output_fallback=True)
                    self._guard(epoch, origin)
                    base = await self._payload(params, broker, selection, client_id, epoch=epoch, origin=origin, final_source=source_cp)
                    invocation = protocol.prepare_invocation(base, selection=selection, title=frozen_title, client_request_id=client_id,
                        queue_admission=self._capabilities._queue_admission)
                    if frozen_destination is None:
                        frozen_destination = self.node._build_generation_output_destination(draft=True).resolve()
                    base_path = self.node._normalized_video_output_path(frozen_destination, params["output_format"])
                    path = str(base_path.with_name(base_path.stem + "-mybox-" + client_id + "." + params["output_format"]))
                    self.node._preflight_output_destination(_host(self.node)._SeedanceDraftOutputDestination(path), params["output_format"])
                    cp = {"schema": CHECKPOINT_SCHEMA, "version": 1, "journal_id": self._owner_journal_id, "revision": cp.get("revision", 0), "selection": selection,
                        "broker_server_url": origin, "client_request_id": client_id, "job_id": "", "stage": "prepared", "status": "submitting",
                        "model_id": params["model_id"], "task": params["task"], "output_format": params["output_format"], "output_file": path,
                        "saved_file_sha256": "", "request_fingerprint": hashlib.sha256(invocation._payload_json.encode()).hexdigest(), "updated_at_ms": int(time.time() * 1000),
                        "draft_preview": bool(params.get("_private_draft_preview")), "draft_source_task_id": source_cp["job_id"] if source_cp else "", "draft_source": deepcopy(projection or {}), "draft_final": {}}
                    if self._capabilities._queue_admission is not None:
                        cp["queue_only_headers"] = json.loads(invocation._queue_headers_json)
                    cp["reference_lease_id"] = await self.node._run_blocking_generation_stage(
                        lambda: self.node._bind_temporary_reference_lease(broker._bridge, origin, client_id, scope="my_box"))
                    cp = await self._persist(cp)
                    self._guard(epoch, origin)
                    self._status("submitting", client_id)
                    submitted_this_run = True
                    job = await self._create(broker, invocation, epoch=epoch, origin=origin)
                    self._guard(epoch, origin)
                    cp = await self._adopt(cp, job)
            deadline = time.monotonic() + params["generation_timeout_seconds"]
            while job["status"] in protocol.JOB_ACTIVE_STATUSES:
                self._guard(epoch, origin)
                if job["status"] == "submission_unknown":
                    raise protocol.MyBoxError("My Box acceptance is unconfirmed. Retrieve this same Task; no automatic resubmission was performed.", code="MY_BOX_SUBMISSION_UNKNOWN", submission_outcome_unknown=True)
                if time.monotonic() >= deadline:
                    raise TimeoutError("My Box polling time limit reached. Retrieve this same Task; it can continue remotely.")
                await self.node._sleep(params["poll_interval_seconds"])
                self._guard(epoch, origin)
                job = await asyncio.to_thread(broker.refresh, cp["job_id"], selection=cp["selection"], client_request_id=cp["client_request_id"], timeout=300)
                self._guard(epoch, origin)
                cp = await self._adopt(cp, job)
            if job["status"] == "completed":
                completion_attempted = True
                cp = await self._complete(cp, broker, job, epoch=epoch, origin=origin)
            else:
                self._status("failed", cp.get("job_id", ""), successful=False, details="FAILURE: My Box Task failed. The saved Task and previous local video are retained.")
        except (Exception, asyncio.CancelledError) as exc:
            if not self._deleted and not getattr(self.node, "_hmb_node_deleted", False):
                with suppress(Exception):
                    current = self.checkpoint()
                    if current and current.get("client_request_id") == cp.get("client_request_id") and current.get("stage") == "local_succeeded":
                        cp = current
                rejection = bool(submitted_this_run and (getattr(exc, "definitive_submission_rejection", False) or
                    (getattr(exc, "status_code", None) in {400, 401, 403, 404, 409, 413, 422, 429}
                     and not getattr(exc, "submission_outcome_unknown", False))
                    or getattr(exc, "code", "") == "MY_BOX_CANCELLED" and not self._post_started))
                if rejection and getattr(exc, "status_code", None) not in {404, 500, 502, 503, 504}:
                    await self.node._run_blocking_generation_stage(self.node._reject_unsubmitted_reference_lease)
                ambiguous = bool(not cp.get("job_id") and ((self._post_started and not rejection)
                    or (historical_unresolved and not submitted_this_run)))
                if cp.get("stage") == "local_succeeded" and completion_attempted:
                    if self._alive(epoch, origin, allow_cancelled=True):
                        with suppress(Exception):
                            self._status("succeeded", cp["job_id"], successful=True, details="SUCCESS: My Box original was saved. Refresh can restore its player.")
                    return
                if cp and cp.get("stage") != "local_succeeded":
                    status = "submission_unknown" if ambiguous else cp["status"] if cp.get("job_id") or historical_unresolved and not rejection else "not_submitted"
                    cp = await self._persist({**cp, "status": status, "stage": "interrupted" if ambiguous or cp.get("job_id") else "not_submitted"}, required=False)
                identifier = cp.get("job_id") or cp.get("client_request_id", "")
                message = "Local My Box wait stopped; an accepted Task can continue remotely. Retrieve the same Task." if isinstance(exc, asyncio.CancelledError) else self.node._safe_exception_message(exc)
                if not origin or self._alive(epoch, origin, allow_cancelled=True):
                    self._status("submission_unknown" if ambiguous else "cancelled_locally" if isinstance(exc, asyncio.CancelledError) else "failed", identifier,
                        successful=False, details="FAILURE: " + message + ("\nExisting My Box request: " + identifier if identifier else ""))
            if isinstance(exc, asyncio.CancelledError):
                raise
        finally:
            self._active_final_source = ""
            self._busy = False
            self._lock.release()
            with suppress(Exception):
                self.node._update_parameter_visibility()
                self.node._sync_seedance_shot_widget(emit_change=True)
            # Submitted references have left these lists for their exact
            # process-owned lease. A failed/blocked My Box status alone has no
            # native terminal proof and never releases that lease.
            with suppress(Exception):
                if cp and cp.get("status") not in {"completed", "failed", "not_submitted"}:
                    self.node._defer_temporary_video_upload_cleanup()
                else:
                    await self.node._run_blocking_generation_stage(self.node._cleanup_temporary_video_uploads)
