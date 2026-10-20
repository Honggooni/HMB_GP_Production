from __future__ import annotations

"""Local, post-generation color finishing. Commands never execute upstream nodes."""

import copy
import contextvars
import json
import hashlib
import logging
import os
import re
import subprocess
import threading
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote

from HMBFinishLookLibrary import (
    DataNode, _add_parameter, _add_widget_parameter, _hidden_transport_ui_options,
    _hide_transport_parameter, _mode, _normalize_shot_catalog,
    _normalize_shot_selection, _raw_parameter, _set_parameter_silently,
    _shot_only, set_output,
)
from _hmb_color_lut import CODEC_EXTENSIONS, default_settings, normalize_settings, probe_source, export_video, write_cube

UI = "HMB_COLOR_LUT_UI_STATE"
COMMAND = "HMB_COLOR_LUT_COMMAND"
SOURCE = "COLOR_LUT_SOURCE_IN"
# Leave room for Griptape's title, flow row and video_url output around the widget.
COLOR_LUT_NODE_WIDTH = 1220
COLOR_LUT_NODE_HEIGHT = 1080
COLOR_LUT_WIDGET_WIDTH = 1180
COLOR_LUT_WIDGET_HEIGHT = 920
LOGGER = logging.getLogger("griptape_nodes")
_PROFILE_LOCK = threading.RLock()
_UPLOAD_LOCK = threading.RLock()
_UPLOAD_ACTIVE: set[str] = set()
COLOR_LUT_UPLOAD_SCHEMA = "hmb-color-lut-upload"


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _file_digest(path: Path, cancel: threading.Event | None = None) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            if cancel is not None and cancel.is_set():
                raise ValueError("Upload cancelled.")
            digest.update(block)
    return digest.hexdigest()


def _upload_receipt_path(identity: str) -> Path:
    if not isinstance(identity, str) or re.fullmatch(r"[a-f0-9]{64}", identity) is None:
        raise ValueError("Invalid Color LUT receipt identity.")
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local"))) / "HMB_GP_Production" / "color-lut" / "web-uploads" / (identity + ".json")


def _write_upload_receipt(identity: str, value: dict[str, Any]) -> None:
    destination = _upload_receipt_path(identity)
    with _UPLOAD_LOCK:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp = destination.with_name(uuid.uuid4().hex + ".tmp")
        try:
            temp.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True), encoding="utf-8")
            os.replace(temp, destination)
        finally:
            temp.unlink(missing_ok=True)


def _read_upload_receipt(identity: str) -> dict[str, Any]:
    try:
        path = _upload_receipt_path(identity)
        if path.stat().st_size > 65536:
            return {}
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _upload_bridge(origin: str) -> Any:
    # Reuse the Generator's origin-scoped credentials and redirect protections.
    # Opening a Color LUT never starts device login or upstream generation.
    from HMBSeedanceGeneration import _HMBAIBrokerBridge
    return _HMBAIBrokerBridge(server_url=origin)


def _profiles_path() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local"))) / "HMB_GP_Production" / "color-lut" / "personal-presets.json"


def _profiles(value: Any = None) -> list[dict[str, Any]]:
    return [{"id": str(p.get("id") or uuid.uuid4().hex), "name": str(p["name"])[:80],
             "project_id": str(p.get("project_id") or ""), "settings": normalize_settings(p.get("settings"))}
            for p in (value if isinstance(value, list) else []) if isinstance(p, Mapping) and p.get("name")]


def _read_profiles() -> list[dict[str, Any]]:
    try:
        with _PROFILE_LOCK:
            return _profiles(json.loads(_profiles_path().read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return _profiles()


def default_state() -> dict[str, Any]:
    return {"schema_version": 1, "revision": 0, "language": "ko", "shot": _shot_only(),
            "shot_catalog": {}, "project_id": "", "project": {}, "preset_name": "", "profiles": _read_profiles(),
            "settings": default_settings(), "source": {}, "output": {
                "codec": "hevc10", "manual_output_enabled": False, "path": ""},
            "status": {"phase": "idle", "message": "", "progress": 0}, "result": {}, "shot_states": {}}


def _selection_key(state: Mapping[str, Any]) -> str:
    shot = state.get("shot") if isinstance(state.get("shot"), Mapping) else {}
    return json.dumps([state.get("project_id", ""), shot.get("channel_uuid", ""), shot.get("shot_uuid", "")], ensure_ascii=False)


def _source_identity(source: Any) -> tuple[str, str, str]:
    source = source if isinstance(source, Mapping) else {}
    # Probing resolves short Windows paths and aliases. Retain the received
    # reference for identity instead of treating that resolution as a new video.
    return (str(source.get("_reference_path") or source.get("path") or ""), str(source.get("generation_id") or source.get("task_id") or ""),
            str(source.get("result_revision") or source.get("revision") or ""))


def _output(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, Mapping) else {}
    return {"codec": raw.get("codec") if isinstance(raw.get("codec"), str) and raw.get("codec") in CODEC_EXTENSIONS else "hevc10",
            "manual_output_enabled": raw.get("manual_output_enabled") is True, "path": str(raw.get("path") or "")}


def _media_url(path: Path) -> str:
    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
    base = str(GriptapeNodes.StaticFilesManager().static_server_base_url).rstrip("/")
    raw = str(path.resolve())
    external = raw if raw.startswith("\\\\") else raw.replace("\\", "/").lstrip("/")
    return f"{base}/external/{quote(external, safe='/:')}?v={path.stat().st_mtime_ns}"


def _browse() -> str:
    # A dedicated native dialog process avoids Tk cross-thread ownership in the host.
    if os.name == "nt":
        script = "Add-Type -AssemblyName System.Windows.Forms; $d=New-Object System.Windows.Forms.OpenFileDialog; $d.Filter='Video|*.mp4;*.mov;*.mkv;*.avi;*.webm'; if($d.ShowDialog() -eq 'OK'){[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; [Console]::Write($d.FileName)}"
        result = subprocess.run(["powershell.exe", "-NoProfile", "-STA", "-Command", script], capture_output=True,
                                encoding="utf-8-sig", timeout=600, creationflags=0x08000000)
        if result.returncode:
            raise RuntimeError("Could not open the video file browser.")
        return result.stdout.strip()
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    try:
        return str(filedialog.askopenfilename(parent=root, filetypes=[("Video", "*.mp4 *.mov *.mkv *.avi *.webm")]) or "")
    finally:
        root.destroy()


def _workflow_data_directory() -> Path:
    """Use the current workflow's actual save folder, never the media folder."""
    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
    from griptape_nodes.node_library.workflow_registry import WorkflowRegistry
    workspace = Path(GriptapeNodes.ConfigManager().workspace_path)
    context = GriptapeNodes.ContextManager()
    if context.has_current_workflow():
        workflow = WorkflowRegistry.get_workflow_by_name(context.get_current_workflow_name())
        if workflow.file_path:
            path = Path(workflow.file_path)
            return (path if path.is_absolute() else workspace / path).resolve().parent / "data"
    # A new unsaved canvas has no file yet; use Griptape's configured save root.
    return workspace.resolve() / "data"


class HMBColorLUTLibrary(DataNode):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        # Use the native initial-size contract once. Saved/manual sizes remain
        # authoritative and updates, shot binding and reset must not resize them.
        initial_size_setter = getattr(self, "set_initial_node_size", None)
        if callable(initial_size_setter):
            initial_size_setter(width=COLOR_LUT_NODE_WIDTH, height=COLOR_LUT_NODE_HEIGHT)
        else:
            self.metadata = dict(getattr(self, "metadata", None) or kwargs.get("metadata") or {})
            self.metadata.setdefault("size", {"width": COLOR_LUT_NODE_WIDTH, "height": COLOR_LUT_NODE_HEIGHT})
        self.category = "HMB_GP_Production"
        self.description = "Shot-bound local SDR color preview, project LUT and final video export."
        self._lock = threading.RLock()
        # BaseNode._state is Griptape's NodeResolutionState, not dashboard data.
        # Keep our state namespaced across registration, invalidation and reset.
        self._hmb_color_lut_state = default_state()
        self._syncing = False
        self._hydrated = False
        self._project_authoritative = False
        self._hmb_node_deleted = False
        self._hmb_initial_shot_autoclaim_pending = True
        self._hmb_initial_shot_preferred_uuid = ""
        self._seen_commands: list[str] = []
        self._source_token = 0
        self._pending_source_key: tuple[Any, ...] | None = None
        self._source_pending: tuple[Any, ...] | None = None
        self._restoring_source: dict[str, Any] = {}
        self._source_worker: threading.Thread | None = None
        self._worker: threading.Thread | None = None
        self._cancel = threading.Event()
        self._job_id = ""
        self._web_upload: dict[str, Any] = {"enabled": False, "phase": "unavailable", "reason": "Only / 영상 불러오기는 웹 업로드를 지원하지 않습니다."}
        self._web_upload_context: dict[str, Any] = {}
        self._web_upload_worker: threading.Thread | None = None
        self._web_upload_probe: threading.Thread | None = None
        self._web_upload_probe_key = ""
        self._web_node_id = uuid.uuid4().hex
        self._web_upload_epoch = 0
        self._web_upload_pending: dict[str, Any] | None = None
        self._web_upload_wake = threading.Event()
        self._setup_parameters()
        self._publish()
        try:
            from _hmb_shot_routing import schedule_post_registration_reconcile
            schedule_post_registration_reconcile(self)
        except Exception:
            LOGGER.debug("Color LUT registration deferred", exc_info=True)

    def _setup_parameters(self) -> None:
        _add_widget_parameter(self, widget_name="HMBColorLUTLibraryWidget", name=UI, default_value=self._hmb_color_lut_state,
            type="dict", input_types=["dict"], allow_input=False, allow_output=False, allow_property=True,
            allowed_modes=_mode("PROPERTY"), ui_options={"display_name": "HMB Color LUT", "is_full_width": True,
                "width": COLOR_LUT_WIDGET_WIDTH, "height": COLOR_LUT_WIDGET_HEIGHT, "min_width": 760, "min_height": 640,
                "expandable": True, "resizable": True, "compact": False, "hide": False, "hide_property": False})
        for name, kind, default, modes in ((COMMAND, "str", "", ("PROPERTY",)), (SOURCE, "dict", {}, ("INPUT",))):
            parameter = _add_parameter(self, name=name, type=kind, default_value=default, input_types=[kind],
                allow_input="INPUT" in modes, allow_output=False, allow_property="PROPERTY" in modes,
                allowed_modes=_mode(*modes), ui_options=_hidden_transport_ui_options())
            _hide_transport_parameter(parameter)
        _add_parameter(self, name="video_url", type="str", default_value="", output_type="str",
            allow_input=False, allow_output=True, allow_property=False, allowed_modes=_mode("OUTPUT"),
            ui_options={"display_name": "video_url"})

    def _publish(self) -> None:
        if self._hmb_node_deleted:
            return
        with self._lock:
            self._syncing = True
            try:
                state = copy.deepcopy(self._hmb_color_lut_state)
                state["web_upload"] = self._upload_projection()
                state["_web_node_id"] = self._web_node_id
                _set_parameter_silently(self, UI, state)
                publisher = getattr(self, "publish_update_to_parameter", None)
                if callable(publisher):
                    publisher(UI, state)
            finally:
                self._syncing = False

    def _upload_state_stamp(self, state: Mapping[str, Any]) -> str:
        """Small local invalidation key; no graph/network/hash work on a UI edit."""
        result = state.get("result") if isinstance(state.get("result"), Mapping) else {}
        return _digest([_selection_key(state), _source_identity(state.get("source")),
                        normalize_settings(state.get("settings")), result.get("path"), result.get("job_id")])

    def _upload_projection(self) -> dict[str, Any]:
        view = copy.deepcopy(self._web_upload)
        context = self._web_upload_context
        current = self._hmb_color_lut_state
        if not current["shot"].get("shot_uuid"):
            return {"enabled": False, "phase": "unavailable", "reason": "Only / 영상 불러오기는 웹 업로드를 지원하지 않습니다."}
        if context.get("state_stamp") != self._upload_state_stamp(current):
            return {"enabled": False, "phase": "unavailable", "reason": "현재 샷의 보정 영상을 먼저 최종 출력하세요."}
        if (context.get("source_token") != self._source_token or context.get("route_epoch") != self._web_upload_epoch
                or getattr(context.get("generator"), "_hmb_node_deleted", False)
                or getattr(context.get("asset"), "_hmb_node_deleted", False)):
            return {"enabled": False, "phase": "unavailable", "reason": "원본 샷 연결이 변경되었습니다."}
        if self._hmb_node_deleted:
            view["enabled"] = False
        return view

    def _upload_graph_context(self, state: Mapping[str, Any]) -> dict[str, Any]:
        """Resolve provenance from registered objects and physical data edges."""
        from _hmb_shot_routing import _same_flow_nodes, _incoming_connections, _subscription_for
        import _hmb_review as review
        source_token, route_epoch = self._source_token, self._web_upload_epoch
        flow, nodes = _same_flow_nodes(self)
        shot, src = state["shot"], state["source"]
        if not flow or self not in nodes or self._hmb_node_deleted or not shot.get("shot_uuid"):
            raise ValueError("Only / 영상 불러오기는 웹 업로드를 지원하지 않습니다.")
        assets = []
        for node in nodes:
            sub = _subscription_for(node)
            if sub is not None and sub.kind == "image_asset" and not getattr(node, "_hmb_node_deleted", False):
                catalog = node._hmb_shot_routing_catalog()
                match = next((item for item in catalog.get("shots", []) if item.get("shot_uuid") == shot["shot_uuid"]), None)
                if catalog.get("channel_uuid") == shot.get("channel_uuid") and match:
                    assets.append((node, match, node._hmb_project_identity()))
        if len(assets) != 1:
            raise ValueError("같은 플로우의 이미지 라이브러리 샷·프로젝트 연결을 확인하세요.")
        _asset, selected, project = assets[0]
        if not project.get("project_id") or not project.get("project_name"):
            raise ValueError("프로젝트를 선택하세요.")
        edges = [edge for edge in _incoming_connections(self)
                 if edge.target_parameter_name == SOURCE and edge.source_parameter_name == "HMB_GENERATED_VIDEO_SOURCE"]
        if len(edges) != 1:
            raise ValueError("샷에 바인딩된 Generator의 완료 영상 연결이 필요합니다.")
        generators = [node for node in nodes if str(getattr(node, "name", "")) == edges[0].source_node_name]
        if len(generators) != 1 or getattr(generators[0], "_hmb_node_deleted", False):
            raise ValueError("원본 Generator 연결이 해제되었습니다.")
        generator = generators[0]
        sub = _subscription_for(generator)
        if (sub is None or sub.kind != "seedance" or not sub.enabled
                or (sub.channel_uuid, sub.shot_uuid) != (shot.get("channel_uuid"), shot.get("shot_uuid"))):
            raise ValueError("Only Generator에서는 웹 업로드할 수 없습니다.")
        actual = generator._hmb_generated_video_source_snapshot()
        required = ("channel_uuid", "shot_uuid", "task_id", "generation_id", "source_node_instance_id", "result_revision")
        if (not isinstance(actual, dict) or actual.get("completed") is not True or not actual.get("task_id")
                or actual.get("task_id") != actual.get("generation_id")
                or any(actual.get(key) != src.get(key) for key in required)
                or _source_identity(actual) != _source_identity(src)):
            raise ValueError("현재 보정 영상의 Generator·Task·샷 정보가 일치하지 않습니다.")
        task = actual["task_id"]
        origin = review.task_origin(task)
        if not origin or review.task_project(task) != project:
            raise ValueError("원본 Task의 서버·프로젝트 기록을 확인할 수 없습니다.")
        name = review._public_shot_name(selected.get("name"))
        if not name:
            raise ValueError("유효한 라이브러리 샷 이름이 필요합니다.")
        return {"flow": flow, "generator": generator, "asset": _asset, "source_task_id": task, "server_url": origin,
                "project_id": project["project_id"], "project_name": project["project_name"],
                "channel_uuid": shot["channel_uuid"], "shot_uuid": shot["shot_uuid"], "shot_name": name,
                "source_node_instance_id": actual["source_node_instance_id"], "source_identity": list(_source_identity(actual)),
                "source_token": source_token, "route_epoch": route_epoch}

    def _record_export_proof(self, state: dict[str, Any], result: dict[str, Any], cancel: threading.Event) -> None:
        """Private durable receipt, never accepted from browser state."""
        self._upload_graph_context(state)
        path = Path(result["path"]).resolve()
        info = path.stat()
        proof = {"schema": "hmb-color-lut-local-export-v1", "source_identity": list(_source_identity(state["source"])),
                 "selection": _selection_key(state), "settings": normalize_settings(state["settings"]),
                 "path": str(path), "size": info.st_size, "mtime_ns": info.st_mtime_ns,
                 "sha256": _file_digest(path, cancel), "job_id": result["job_id"]}
        identity = _digest(proof)
        _write_upload_receipt(identity, proof)
        result["web_export_proof"] = identity

    def _prepare_upload_context(self, state: dict[str, Any], *, recheck_file: bool = True) -> dict[str, Any]:
        context = self._upload_graph_context(state)
        result = state["result"]
        proof = _read_upload_receipt(str(result.get("web_export_proof") or "")) if result.get("web_export_proof") else {}
        if proof.get("schema") != "hmb-color-lut-local-export-v1" or _digest(proof) != result.get("web_export_proof"):
            raise ValueError("현재 설정으로 최종 출력한 보정 영상이 필요합니다.")
        if proof.get("path") != result.get("path"):
            raise ValueError("보정 영상 경로가 변경되었습니다.")
        path = Path(proof["path"]).resolve()
        info = path.stat()
        if (proof.get("schema") != "hmb-color-lut-local-export-v1" or _digest(proof) != result.get("web_export_proof")
                or proof.get("settings") != normalize_settings(state["settings"])
                or proof.get("source_identity") != list(_source_identity(state["source"]))
                or proof.get("selection") != _selection_key(state) or proof.get("path") != str(path)
                or proof.get("size") != info.st_size or proof.get("mtime_ns") != info.st_mtime_ns
                or (recheck_file and proof.get("sha256") != _file_digest(path))):
            raise ValueError("현재 설정으로 최종 출력한 보정 영상이 필요합니다.")
        bridge = _upload_bridge(context["server_url"])
        capabilities = bridge.review_capabilities()
        cap = capabilities.get("color_lut_upload", {})
        if (not isinstance(cap, dict) or cap.get("schema") != COLOR_LUT_UPLOAD_SCHEMA or type(cap.get("version")) is not int or cap.get("version") != 1
                or cap.get("enabled") is not True or cap.get("display_name") != "HMB Color LUT"
                or cap.get("upload_path") != "/api/v1/reviews/tasks/{source_task_id}/color-lut"):
            raise ValueError("브로커가 Color LUT 웹 업로드를 아직 지원하지 않습니다. 서버 업데이트가 필요합니다.")
        maximum = cap.get("max_bytes")
        if type(maximum) is not int or not 1 <= maximum <= 536870912 or info.st_size > maximum:
            raise ValueError("보정 영상이 서버의 업로드 용량 제한을 초과했습니다.")
        if path.suffix.lower() not in {".mov", ".mp4"}:
            raise ValueError("이 출력 형식은 웹 업로드를 지원하지 않습니다.")
        eligibility = bridge._request_json("GET", "/api/v1/reviews/tasks/" + quote(context["source_task_id"], safe="") + "/color-lut", payload=None, timeout=5)
        bound = eligibility.get("shot") if isinstance(eligibility.get("shot"), dict) else {}
        if (eligibility.get("schema") != COLOR_LUT_UPLOAD_SCHEMA or type(eligibility.get("version")) is not int or eligibility.get("version") != 1
                or eligibility.get("enabled") is not True or eligibility.get("eligible") is not True
                or eligibility.get("display_name") != "HMB Color LUT"
                or any(eligibility.get(key) != context[key] for key in ("source_task_id", "project_id", "project_name"))
                or any(bound.get(key) != context[key] for key in ("channel_uuid", "shot_uuid", "source_node_instance_id"))
                or bound.get("name") != context["shot_name"]
                or eligibility.get("upload_path") != "/api/v1/reviews/tasks/" + quote(context["source_task_id"], safe="") + "/color-lut"
                or type(eligibility.get("max_bytes")) is not int or not info.st_size <= eligibility["max_bytes"] <= maximum
                or re.fullmatch(r"[a-f0-9]{64}", str(eligibility.get("source_sha256") or "")) is None
                or re.fullmatch(r"[a-f0-9]{64}", str(eligibility.get("source_revision") or "")) is None):
            raise ValueError("서버에서 본인 소유의 동일 프로젝트·샷 원본을 확인하지 못했습니다.")
        me = bridge._request_json("GET", "/api/me", payload=None, timeout=5)
        owner = str(me.get("id") or me.get("user_id") or (me.get("user") or {}).get("id") or "")
        if not owner:
            raise ValueError("브로커 로그인 계정을 확인하세요.")
        context.update(path=str(path), size=info.st_size, mtime_ns=info.st_mtime_ns, sha256=proof["sha256"],
                       settings=proof["settings"], owner_id=owner, bridge=bridge, state_stamp=self._upload_state_stamp(state),
                       source_revision=eligibility["source_revision"], settings_sha256=_digest(proof["settings"]))
        context["upload_id"] = hashlib.sha256("\n".join(("hmb-color-lut-upload-v1", context["source_task_id"], context["sha256"], context["settings_sha256"], context["shot_uuid"])).encode("utf-8")).hexdigest()
        context["receipt_id"] = _digest([context["server_url"], context["owner_id"], context["upload_id"]])
        return context

    def _schedule_upload_probe(self) -> None:
        with self._lock:
            if self._hmb_node_deleted:
                return
            state = copy.deepcopy(self._hmb_color_lut_state)
            stamp = self._upload_state_stamp(state)
            if not state["shot"].get("shot_uuid") or not state["result"].get("web_export_proof"):
                return
            if self._web_upload_probe_key == stamp and (self._web_upload_context.get("bridge") is not None
                    or self._web_upload_probe is not None and self._web_upload_probe.is_alive()):
                return
            self._web_upload_probe_key = stamp
            self._web_upload_pending = state
            self._web_upload_wake.set()
            if self._web_upload_probe is not None and self._web_upload_probe.is_alive():
                return
        def prepare() -> None:
            retry = 0
            selected = None
            while True:
                with self._lock:
                    if self._hmb_node_deleted:
                        self._web_upload_probe = None
                        return
                    if self._web_upload_pending is not None:
                        selected, self._web_upload_pending = self._web_upload_pending, None
                        retry = 0
                    if selected is None:
                        self._web_upload_probe = None
                        return
                    selected_stamp = self._upload_state_stamp(selected)
                    token, epoch = self._source_token, self._web_upload_epoch
                    self._web_upload_wake.clear()
                context, error = {}, ""
                try:
                    context = self._prepare_upload_context(selected, recheck_file=retry == 0)
                except Exception as exc:
                    error = str(exc)
                with self._lock:
                    if (self._hmb_node_deleted or selected_stamp != self._upload_state_stamp(self._hmb_color_lut_state)
                            or token != self._source_token or epoch != self._web_upload_epoch):
                        selected = None
                        continue
                    self._web_upload_context = context or {"state_stamp": selected_stamp, "source_token": token, "route_epoch": epoch}
                    receipt = _read_upload_receipt(context["receipt_id"]) if context else {}
                    complete = receipt.get("phase") == "complete"
                    pending = receipt.get("phase") in {"pending", "unknown"}
                    self._web_upload = {"enabled": bool(context) and not complete, "phase": "complete" if complete else "unknown" if pending else "ready" if context else "unavailable",
                                        "reason": "웹 업로드 완료" if complete else error or "현재 보정 영상을 웹에 업로드합니다."}
                self._publish()
                if context:
                    selected = None
                    continue
                # A held/offline Broker can become available later. One
                # background worker retries advisory reads with backoff only;
                # unchanged large files are not rehashed on those retries.
                if self._upload_retry_wait(min(60, 5 * 2**min(retry, 4))):
                    with self._lock:
                        self._web_upload_probe = None
                    return
                retry += 1
        self._web_upload_probe = threading.Thread(target=contextvars.copy_context().run, args=(prepare,), name="HMB LUT upload readiness", daemon=True)
        self._web_upload_probe.start()

    def _upload_retry_wait(self, seconds: float) -> bool:
        self._web_upload_wake.wait(seconds)
        return self._hmb_node_deleted

    def _upload_metadata(self, context: dict[str, Any]) -> dict[str, Any]:
        return {"schema": COLOR_LUT_UPLOAD_SCHEMA, "version": 1,
                **{key: context[key] for key in ("source_task_id", "source_revision", "channel_uuid", "shot_uuid", "settings_sha256")},
                "workflow_id": context["flow"], "generator_node_id": context["source_node_instance_id"],
                "color_lut_node_id": self._web_node_id, "export_sha256": context["sha256"],
                "export_bytes": context["size"], "output_format": Path(context["path"]).suffix.lower().lstrip(".")}

    def _upload_request(self, context: dict[str, Any], *, retrieve: bool, cancel: threading.Event) -> dict[str, Any]:
        from HMBSeedanceGeneration import _broker_require_exact_response_url, _broker_read_json
        from _hmb_broker_config import join_broker_url
        from urllib.request import Request
        from urllib.parse import quote as urlquote
        bridge, identity = context["bridge"], context["upload_id"]
        path = "/api/v1/reviews/tasks/" + urlquote(context["source_task_id"], safe="") + "/color-lut"
        metadata = context.get("frozen_metadata") or self._upload_metadata(context)
        if retrieve:
            return bridge._request_json("GET", path + "/" + identity, payload=None, timeout=30)
        boundary = "hmb-color-lut-" + uuid.uuid4().hex
        extension = Path(context["path"]).suffix.lower()
        prefix = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"metadata\"\r\nContent-Type: application/json\r\n\r\n"
                  + json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))
                  + f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"color-lut{extension}\"\r\nContent-Type: {'video/quicktime' if extension == '.mov' else 'video/mp4'}\r\n\r\n").encode("utf-8")
        suffix = f"\r\n--{boundary}--\r\n".encode()
        node = self
        class Body:
            def __iter__(self):
                yield prefix
                with Path(context["path"]).open("rb") as stream:
                    stat = os.fstat(stream.fileno())
                    if stat.st_size != context["size"] or stat.st_mtime_ns != context["mtime_ns"]:
                        raise ValueError("보정 영상 파일이 변경되었습니다.")
                    digest = hashlib.sha256()
                    while block := stream.read(1024 * 1024):
                        with node._lock:
                            if (cancel.is_set() or node._hmb_node_deleted
                                    or context["state_stamp"] != node._upload_state_stamp(node._hmb_color_lut_state)
                                    or context["source_token"] != node._source_token or context["route_epoch"] != node._web_upload_epoch):
                                raise ValueError("보정 영상 또는 샷이 변경되어 업로드를 중단했습니다.")
                        digest.update(block)
                        yield block
                    if digest.hexdigest() != context["sha256"]:
                        raise ValueError("보정 영상 파일이 변경되었습니다.")
                yield suffix
        request = Request(join_broker_url(bridge.server_url, path), data=Body(), method="POST", headers={
            "Authorization": "Bearer " + bridge._load_access_token(), "Accept": "application/json",
            "Content-Type": "multipart/form-data; boundary=" + boundary,
            "Content-Length": str(len(prefix) + context["size"] + len(suffix)), "Idempotency-Key": identity})
        with bridge._opener.open(request, timeout=300) as response:
            _broker_require_exact_response_url(response, request.full_url)
            return _broker_read_json(response, max_bytes=65536)

    def _start_web_upload(self, state: dict[str, Any]) -> None:
        # This is an explicit user command, never a side effect of export or Run.
        if not self._upload_projection().get("enabled"):
            self._status("error", self._upload_projection().get("reason", "웹 업로드 준비가 필요합니다."))
            return
        self._web_upload = {"enabled": False, "phase": "uploading", "reason": "웹 업로드 중…"}
        cancel = self._cancel = threading.Event()
        def upload() -> None:
            identity, sent, claimed, retrieve, context, durable = "", False, False, False, {}, {}
            try:
                context = self._prepare_upload_context(state)
                identity = context["upload_id"]
                current = self._upload_graph_context(state)
                if any(current.get(key) != context.get(key) for key in current):
                    raise ValueError("원본 Generator 또는 샷 연결이 변경되었습니다.")
                with self._lock:
                    if self._hmb_node_deleted or context["state_stamp"] != self._upload_state_stamp(self._hmb_color_lut_state):
                        raise ValueError("현재 샷 또는 보정 설정이 변경되었습니다.")
                with _UPLOAD_LOCK:
                    if identity in _UPLOAD_ACTIVE:
                        raise ValueError("동일한 보정 영상의 웹 업로드가 진행 중입니다.")
                    previous = _read_upload_receipt(context["receipt_id"])
                    if previous.get("phase") == "complete":
                        response = previous.get("response", {})
                    else:
                        metadata = self._upload_metadata(context)
                        if previous.get("metadata"):
                            frozen = previous["metadata"]
                            # A retry retains its original workflow/node IDs,
                            # while media/shot/source/settings preconditions
                            # must still be identical to the frozen operation.
                            if (not isinstance(frozen, dict) or set(frozen) != set(metadata)
                                    or any(frozen.get(key) != metadata[key] for key in metadata
                                           if key not in {"workflow_id", "color_lut_node_id"})):
                                raise ValueError("미확인 업로드의 원본 정보가 변경되었습니다. 기존 업로드 상태를 먼저 확인하세요.")
                            metadata = frozen
                        context["frozen_metadata"] = copy.deepcopy(metadata)
                        durable = {"schema": COLOR_LUT_UPLOAD_SCHEMA, "phase": "pending", "upload_id": identity, "metadata": metadata}
                        _UPLOAD_ACTIVE.add(identity)
                        claimed = True
                        retrieve = previous.get("phase") in {"pending", "unknown"}
                        _write_upload_receipt(context["receipt_id"], durable)
                        response = None
                if response is None:
                    # Persist pending before crossing the network boundary. An
                    # uncertain response is retrieved with the same ID only.
                    sent = True
                    response = self._upload_request(context, retrieve=retrieve, cancel=cancel)
                if (not isinstance(response, dict) or response.get("schema") != "hmb-color-lut-upload-result" or type(response.get("version")) is not int or response.get("version") != 1
                        or any(response.get(key) != context[key] for key in
                               ("source_task_id", "project_id", "project_name", "channel_uuid", "shot_uuid", "sha256", "shot_name"))
                        or type(response.get("bytes")) is not int or response.get("bytes") != context["size"] or type(response.get("created")) is not bool
                        or response.get("display_name") != "HMB Color LUT" or response.get("source_kind") != "HMB Color LUT"
                        or not isinstance(response.get("asset_id"), str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}", response["asset_id"]) is None
                        or not isinstance(response.get("derived_task_id"), str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}", response["derived_task_id"]) is None):
                    raise ValueError("서버가 동일 보정 영상의 업로드 완료를 확인하지 못했습니다.")
                try:
                    _write_upload_receipt(context["receipt_id"], {**durable, "schema": COLOR_LUT_UPLOAD_SCHEMA, "phase": "complete", "upload_id": identity, "response": response})
                except OSError:
                    # A local receipt failure cannot undo a verified successful
                    # server upload. The server retains this idempotency key.
                    LOGGER.debug("Color LUT completed upload receipt could not be saved", exc_info=True)
                with self._lock:
                    if not self._hmb_node_deleted and context["state_stamp"] == self._upload_state_stamp(self._hmb_color_lut_state):
                        self._web_upload_context = context
                        self._web_upload = {"enabled": False, "phase": "complete", "reason": "웹 업로드 완료 · HMB Color LUT"}
            except Exception as exc:
                absent = bool(sent and retrieve and (getattr(exc, "status_code", None) == 404 or getattr(exc, "code", None) == 404))
                if sent and identity:
                    try:
                        _write_upload_receipt(context["receipt_id"], {**durable, "schema": COLOR_LUT_UPLOAD_SCHEMA, "phase": "absent" if absent else "unknown", "upload_id": identity})
                    except OSError:
                        LOGGER.debug("Color LUT pending upload receipt could not be saved", exc_info=True)
                with self._lock:
                    if not self._hmb_node_deleted and self._upload_state_stamp(state) == self._upload_state_stamp(self._hmb_color_lut_state):
                        self._web_upload = {"enabled": bool(sent), "phase": "ready" if absent else "unknown" if sent else "unavailable",
                                            "reason": "서버에 업로드가 없습니다. 다시 누르면 동일 ID로 업로드합니다." if absent else "동일 업로드 상태 확인이 필요합니다. 다시 누르면 새 업로드 없이 조회합니다." if sent else str(exc)}
            finally:
                with _UPLOAD_LOCK:
                    if claimed:
                        _UPLOAD_ACTIVE.discard(identity)
                self._publish()
        self._web_upload_worker = threading.Thread(target=contextvars.copy_context().run, args=(upload,), name="HMB LUT web upload", daemon=True)
        self._web_upload_worker.start()
        self._publish()

    def _status(self, phase: str, message: str = "", progress: float = 0) -> None:
        with self._lock:
            if self._hmb_color_lut_state["language"] == "ko":
                message = {"Loading video…": "영상을 불러오는 중…", "Processing original source…": "원본 영상 처리 중…",
                    "Encoding original source…": "원본 영상 인코딩 중…", "Preset saved.": "프리셋을 저장했습니다.",
                    "A local operation is already running.": "로컬 작업이 이미 진행 중입니다."}.get(message, message)
            status = {"phase": phase, "message": message, "progress": progress}
            if status == self._hmb_color_lut_state["status"]:
                return
            self._hmb_color_lut_state["status"] = status
        self._publish()

    def _remember_selection(self) -> None:
        self._hmb_color_lut_state["shot_states"][_selection_key(self._hmb_color_lut_state)] = copy.deepcopy({
            key: self._hmb_color_lut_state[key] for key in ("settings", "output", "source", "result", "preset_name")})
        while len(self._hmb_color_lut_state["shot_states"]) > 128:
            del self._hmb_color_lut_state["shot_states"][next(iter(self._hmb_color_lut_state["shot_states"]))]

    def _publish_result_url(self, value: str = "") -> None:
        set_output(self, "video_url", value)
        publish = getattr(self, "publish_update_to_parameter", None)
        if callable(publish):
            publish("video_url", value)

    def _switch(self, shot: Any, project: str | None = None) -> None:
        self._remember_selection()
        self._hmb_color_lut_state["shot"] = copy.deepcopy(shot)
        if project is not None:
            self._hmb_color_lut_state["project_id"] = project
        saved = self._hmb_color_lut_state["shot_states"].get(_selection_key(self._hmb_color_lut_state), {})
        saved = saved if isinstance(saved, Mapping) else {}
        self._hmb_color_lut_state["settings"] = normalize_settings(saved.get("settings"))
        self._hmb_color_lut_state["preset_name"] = str(saved.get("preset_name") or "")
        self._hmb_color_lut_state["output"] = _output(saved.get("output"))
        self._hmb_color_lut_state["result"] = copy.deepcopy(saved.get("result", {}))
        self._restoring_source = copy.deepcopy(saved.get("source", {}))
        self._hmb_color_lut_state["source"] = {}
        _set_parameter_silently(self, SOURCE, {})
        self._publish_result_url()
        self._hmb_color_lut_state["status"] = {"phase": "idle", "message": "", "progress": 0}
        self._source_token += 1
        self._web_upload_wake.set()
        self._pending_source_key = None
        if not shot.get("shot_uuid") and saved.get("source", {}).get("path"):
            self._queue_source(saved["source"])

    def _apply_ui(self, value: Any, *, initial_setup: bool = False) -> None:
        if not isinstance(value, Mapping):
            return
        command = None if initial_setup else value.get("__hmb_color_lut_command__")
        with self._lock:
            if self._hmb_node_deleted:
                return
            # A serialized backend state contains shot_states; a live widget
            # edit deliberately does not. Never hydrate read-only source data
            # back from that first compact edit after automatic routing.
            initial = initial_setup or (not self._hydrated and isinstance(value.get("shot_states"), Mapping))
            self._hydrated = True
            supplied_project = str(value.get("project_id") or "")
            current_project = self._hmb_color_lut_state["project_id"]
            if ("project_id" in value and supplied_project != current_project
                    and (not initial or (self._project_authoritative and supplied_project))):
                # A debounced edit/command can arrive after ImageAsset has
                # changed the project. Never reinterpret its settings as an
                # edit of the newly selected project, even at a higher UI rev.
                if not initial_setup:
                    self._publish()
                return
            if initial_setup:
                if re.fullmatch(r"[a-f0-9]{32}", str(value.get("_web_node_id") or "")):
                    self._web_node_id = value["_web_node_id"]
                # Registration may already have queued an older Shot probe.
                # Its late result must not replace the restored Shot's source.
                self._source_token += 1
                self._source_pending = None
                self._pending_source_key = None
                self._restoring_source = {}
            if initial:
                self._hydrated = True
                histories = value.get("shot_states")
                if isinstance(histories, dict):
                    self._hmb_color_lut_state["shot_states"] = copy.deepcopy(histories)
                if not self._project_authoritative:
                    self._hmb_color_lut_state["project_id"] = str(value.get("project_id") or "")
                    self._hmb_color_lut_state["project"] = dict(value.get("project") or {}) if isinstance(value.get("project"), Mapping) else {}
                if isinstance(value.get("shot_catalog"), Mapping):
                    self._hmb_color_lut_state["shot_catalog"] = _normalize_shot_catalog(value["shot_catalog"], allow_sparse=True)
            try:
                revision = max(0, int(value.get("revision") or 0))
            except (TypeError, ValueError, OverflowError):
                revision = self._hmb_color_lut_state["revision"]
            if revision < self._hmb_color_lut_state["revision"] and not initial:
                if command:
                    self._command(command)
                return
            shot = _normalize_shot_selection(value.get("shot"), self._hmb_color_lut_state["shot_catalog"])
            project = self._hmb_color_lut_state["project_id"]  # ImageAsset owns this field.
            changed = shot != self._hmb_color_lut_state["shot"] or project != self._hmb_color_lut_state["project_id"]
            if changed and not initial:
                self._switch(shot, project)
            else:
                self._hmb_color_lut_state["shot"], self._hmb_color_lut_state["project_id"] = shot, project
                self._hmb_color_lut_state["settings"] = normalize_settings(value.get("settings", self._hmb_color_lut_state["settings"]))
                self._hmb_color_lut_state["output"] = _output(value.get("output"))
                if initial:
                    self._hmb_color_lut_state["result"] = copy.deepcopy(value.get("result")) if isinstance(value.get("result"), Mapping) else {}
                    self._hmb_color_lut_state["source"] = copy.deepcopy(value.get("source")) if isinstance(value.get("source"), Mapping) else {}
                    src = self._hmb_color_lut_state["source"]
                    if shot.get("shot_uuid") and (src.get("shot_uuid") != shot["shot_uuid"] or src.get("channel_uuid") != shot["channel_uuid"] or src.get("completed") is not True):
                        self._hmb_color_lut_state["source"], self._hmb_color_lut_state["result"] = {}, {}
            self._hmb_initial_shot_autoclaim_pending = False
            self._hmb_color_lut_state["language"] = "en" if value.get("language") == "en" else "ko"
            if initial or not changed:
                self._hmb_color_lut_state["preset_name"] = str(value.get("preset_name") or "")[:80]
            self._hmb_color_lut_state["revision"] = revision if initial_setup else max(revision, self._hmb_color_lut_state["revision"]) + 1
            self._remember_selection()
            if initial and not initial_setup and not shot.get("shot_uuid") and self._hmb_color_lut_state["source"].get("path"):
                self._queue_source(self._hmb_color_lut_state["source"])
        if initial_setup:
            # Native DeserializeFlow suppresses after_value_set. Restore only
            # private authoring here, before deferred routing can publish a
            # default state over the saved value. Never replay saved commands,
            # probe media, publish or reconcile during partial hydration.
            return
        self._publish()
        if changed:
            self._reconcile()
        if command:
            self._command(command)

    def _queue_source(self, snapshot: Any) -> None:
        if not isinstance(snapshot, Mapping) or not snapshot:
            return
        snap = copy.deepcopy(snapshot)
        with self._lock:
            shot = self._hmb_color_lut_state["shot"]
            if not shot.get("shot_uuid") and snap.get("shot_uuid"):
                return
            if shot.get("shot_uuid") and (snap.get("shot_uuid") != shot["shot_uuid"] or snap.get("channel_uuid") != shot["channel_uuid"] or snap.get("completed") is not True):
                return
            path = str(snap.get("path") or "")
            if not path:
                return
            key = (_selection_key(self._hmb_color_lut_state), *_source_identity(snap))
            if key == self._pending_source_key:
                return
            self._pending_source_key = key
            self._source_token += 1
            self._web_upload_wake.set()
            token = self._source_token
            if _source_identity(self._hmb_color_lut_state["source"] or self._restoring_source) != _source_identity(snap):
                self._hmb_color_lut_state["result"] = {}
                self._publish_result_url()
            self._restoring_source = {}
            self._hmb_color_lut_state["source"] = {}
            self._source_pending = (token, snap, path)
            self._publish()
            if self._source_worker is not None and self._source_worker.is_alive():
                return
        def load() -> None:
            while True:
                with self._lock:
                    pending = self._source_pending
                    self._source_pending = None
                    if pending is None or self._hmb_node_deleted:
                        self._source_worker = None
                        return
                token, snap, path = pending
                try:
                    info = probe_source(path)
                    media = Path(str(info.get("path") or path)).resolve()
                    source = {**snap, **info, "_reference_path": str(snap.get("_reference_path") or path),
                              "path": str(media), "url": _media_url(media), "name": media.name,
                              "fps": float(info.get("frame_rate") or info.get("fps") or 0),
                              "revision": str(snap.get("result_revision") or media.stat().st_mtime_ns)}
                    with self._lock:
                        if token != self._source_token or self._hmb_node_deleted:
                            continue
                        self._hmb_color_lut_state["source"] = source
                        result = self._hmb_color_lut_state["result"]
                        if result.get("path") and Path(result["path"]).is_file() and result.get("source_path") == source["path"]:
                            if Path(result["path"]).suffix.lower() != ".cube":
                                result["url"] = _media_url(Path(result["path"]))
                                self._publish_result_url(result["url"])
                        self._remember_selection()
                    self._publish()
                    self._schedule_upload_probe()
                except Exception as exc:
                    with self._lock:
                        if token != self._source_token or self._hmb_node_deleted:
                            continue
                        self._pending_source_key = None
                    self._status("error", str(exc))
        with self._lock:
            self._source_worker = threading.Thread(target=contextvars.copy_context().run, args=(load,), name="HMB LUT source", daemon=True)
            self._source_worker.start()

    def _command(self, value: Any) -> None:
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError:
                return
        if not isinstance(value, Mapping) or self._hmb_node_deleted:
            return
        request_id = str(value.get("id") or "")
        with self._lock:
            if not request_id or request_id in self._seen_commands:
                return
            self._hydrated = True
            self._seen_commands = (self._seen_commands + [request_id])[-128:]
            action = str(value.get("action") or "")
            if action == "cancel":
                self._cancel.set()
                return
            if action in {"export", "browse_video", "upload_web"} and self._worker is not None and self._worker.is_alive():
                self._status("busy", "A local operation is already running.")
                return
            if action == "upload_web" and self._web_upload_worker is not None and self._web_upload_worker.is_alive():
                return
            captured = copy.deepcopy(self._hmb_color_lut_state)
            # Commands may arrive before the debounced property update. Capture the
            # current UI settings, but never trust a UI-supplied source/provenance.
            authored = value.get("state")
            if isinstance(authored, Mapping) and _selection_key(authored) != _selection_key(captured):
                # Delayed buttons belong to their original Project/Shot.
                # Cancellation was handled above and may still stop that job.
                return
            if isinstance(authored, Mapping) and _selection_key(authored) == _selection_key(captured):
                # A native onCommand need not echo the property edit first.
                # Advance beyond that captured browser revision so worker
                # readiness/completion publications are accepted immediately.
                try:
                    authored_revision = max(0, min(2**53 - 2, int(authored.get("revision") or 0)))
                except (TypeError, ValueError, OverflowError):
                    authored_revision = self._hmb_color_lut_state["revision"]
                self._hmb_color_lut_state["revision"] = max(self._hmb_color_lut_state["revision"], authored_revision) + 1
                captured["settings"] = normalize_settings(authored.get("settings", captured["settings"]))
                captured["preset_name"] = str(authored.get("preset_name") or "")[:80]
                raw = authored.get("output")
                if isinstance(raw, Mapping):
                    captured["output"] = _output(raw)
                self._hmb_color_lut_state["settings"] = copy.deepcopy(captured["settings"])
                self._hmb_color_lut_state["output"] = copy.deepcopy(captured["output"])
                self._remember_selection()
            if action == "save_profile":
                self._save_profile(captured, authored)
                return
            if action == "upload_web":
                self._start_web_upload(captured)
                return
            if action not in {"export", "browse_video"}:
                return
            self._cancel = threading.Event()
            self._job_id = request_id
            if action == "export":
                # Capture before dispatch: changing the active workflow mid-export
                # must not redirect this export's collection to another project.
                try:
                    captured["data_directory"] = str(_workflow_data_directory())
                except Exception as exc:
                    self._status("error", f"Unable to resolve the workflow data folder: {exc}")
                    return
            key, cancel = _selection_key(captured), self._cancel
            self._status("working", "Loading video…" if action == "browse_video" else "Processing original source…")
            self._worker = threading.Thread(target=contextvars.copy_context().run, args=(self._run_command, action, captured, request_id, key, cancel), name="HMB LUT export", daemon=True)
            self._worker.start()

    def _save_profile(self, state: dict[str, Any], authored: Any) -> None:
        try:
            with _PROFILE_LOCK:
                profiles = _read_profiles()
                name = str((authored if isinstance(authored, Mapping) else state).get("preset_name") or "").strip()[:80]
                if not name:
                    raise ValueError("프리셋 이름을 입력하세요. / Enter a preset name.")
                item = next((p for p in profiles if p["project_id"] == state["project_id"] and p["name"] == name), None)
                if item is None:
                    item = {"id": uuid.uuid4().hex, "project_id": state["project_id"], "name": name}
                    profiles.append(item)
                item["settings"] = normalize_settings(state["settings"])
                destination = _profiles_path()
                destination.parent.mkdir(parents=True, exist_ok=True)
                temp = destination.with_name(f".{uuid.uuid4().hex}.tmp")
                try:
                    temp.write_text(json.dumps(profiles, ensure_ascii=False, indent=2), encoding="utf-8")
                    os.replace(temp, destination)
                finally:
                    temp.unlink(missing_ok=True)
                self._hmb_color_lut_state["profiles"] = profiles
                self._hmb_color_lut_state["preset_name"] = name
                self._remember_selection()
            self._status("complete", "Preset saved.")
        except Exception as exc:
            self._status("error", str(exc))

    def _archive_grade(self, state: dict[str, Any], result: dict[str, Any], job_id: str) -> dict[str, str]:
        directory = Path(state["data_directory"])
        directory.mkdir(parents=True, exist_ok=True)
        stem = f"color_lut_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:12]}"
        cube = directory / f"{stem}.cube"
        metadata = directory / f"{stem}.json"
        write_cube(cube, state["settings"])
        record = {"schema": "hmb-color-lut-export", "version": 1, "created_at": time.strftime('%Y-%m-%dT%H:%M:%S%z'),
            "project": state.get("project", {}), "project_id": state["project_id"], "preset_name": state.get("preset_name", ""),
            "shot": state["shot"], "source_path": state["source"].get("path", ""), "output_path": result["path"],
            "generation_id": state["source"].get("generation_id", ""), "settings": state["settings"],
            "codec": state["output"]["codec"], "lut_path": str(cube), "job_id": job_id}
        record["source_media"] = {key: state["source"].get(key) for key in ("width", "height", "fps", "duration", "pixel_format")}
        record["output_media"] = {key: result.get(key) for key in ("width", "height", "frame_rate", "duration", "video_codec", "pixel_format", "working_space", "cube_size", "interpolation", "color_assumptions")}
        with metadata.open("x", encoding="utf-8") as stream:
            json.dump(record, stream, ensure_ascii=False, indent=2)
        return {"lut_path": str(cube), "metadata_path": str(metadata)}

    def _hmb_follow_image_asset_project(self, project: Any) -> None:
        project = dict(project) if isinstance(project, Mapping) else {}
        with self._lock:
            self._project_authoritative = True
            state = self._hmb_color_lut_state
            if state["project"] == project:
                return
            project_id = str(project.get("id") or "")
            if project_id != state["project_id"]:
                # On first discovery retain the already-authored grade and source;
                # later project changes are isolated like Shot changes.
                if not state["project_id"]:
                    state["project_id"] = project_id
                else:
                    self._switch(state["shot"], project_id)
            state["project"] = project
            state["revision"] += 1
            self._remember_selection()
        self._publish()

    def _run_command(self, action: str, state: dict[str, Any], job_id: str, key: str, cancel: threading.Event) -> None:
        try:
            if action == "browse_video":
                path = _browse()
                with self._lock:
                    if path and key == _selection_key(self._hmb_color_lut_state) and not self._hmb_node_deleted and not cancel.is_set():
                        if self._hmb_color_lut_state["shot"].get("shot_uuid"):
                            raise ValueError("Use Only for a manual file, or use the matching Shot's Generator result.")
                        self._queue_source({"path": path})
                self._status("idle")
                return
            source = str(state["source"].get("path") or "")
            shot, src = state["shot"], state["source"]
            if shot.get("shot_uuid") and (src.get("shot_uuid") != shot["shot_uuid"] or src.get("channel_uuid") != shot["channel_uuid"] or src.get("completed") is not True):
                raise ValueError("The completed video does not belong to this Shot.")
            output = state["output"]
            codec = str(output.get("codec") or "hevc10")
            if codec not in CODEC_EXTENSIONS:
                raise ValueError("Unknown output codec.")
            if output.get("manual_output_enabled"):
                if not str(output.get("path") or "").strip():
                    raise ValueError("Enter the destination file path.")
                destination = Path(output["path"]).expanduser()
                if not destination.is_absolute():
                    raise ValueError("Output must be an absolute file path.")
            else:
                if not source:
                    raise ValueError("Load a video or explicitly choose an output path.")
                suffix = CODEC_EXTENSIONS[codec]
                original = Path(source)
                destination = original.with_name(f"{original.stem}_LUT_{time.strftime('%Y%m%d_%H%M%S')}_{job_id[-6:]}{suffix}")
            if cancel.is_set():
                if key == _selection_key(self._hmb_color_lut_state):
                    self._status("cancelled", "취소되었습니다." if self._hmb_color_lut_state["language"] == "ko" else "Cancelled.")
                return
            if action == "export":
                if not source:
                    raise ValueError("No matching completed video is loaded.")
                directory = Path(state["data_directory"])
                directory.mkdir(parents=True, exist_ok=True)
                with tempfile.TemporaryFile(dir=directory):
                    pass
                last_update = [0.0]
                def progress(value: Any) -> None:
                    now = time.monotonic()
                    if now - last_update[0] < .2:
                        return
                    last_update[0] = now
                    if key == _selection_key(self._hmb_color_lut_state) and _source_identity(self._hmb_color_lut_state["source"]) == _source_identity(state["source"]) and not self._hmb_node_deleted:
                        self._status("working", "Encoding original source…", float(value))
                result = export_video(source, destination, state["settings"], codec=codec, cancel_event=cancel, progress=progress)
            result = {**result, "shot": state["shot"], "project_id": state["project_id"], "settings": state["settings"], "job_id": job_id}
            if action == "export":
                try:
                    result.update(self._archive_grade(state, result, job_id))
                except Exception as exc:
                    raise RuntimeError(f"Video saved: {result['path']}. Automatic LUT data save failed: {exc}") from exc
                result["url"] = _media_url(Path(result["path"]))
                try:
                    self._record_export_proof(state, result, cancel)
                except Exception:
                    # A finished local export remains successful when the
                    # optional private web receipt cannot be written.
                    LOGGER.debug("Color LUT upload receipt could not be prepared", exc_info=True)
            with self._lock:
                if self._hmb_node_deleted:
                    return
                history = self._hmb_color_lut_state["shot_states"].setdefault(key, {})
                if _source_identity(history.get("source")) == _source_identity(state["source"]):
                    history["result"] = copy.deepcopy(result)
                if key == _selection_key(self._hmb_color_lut_state) and _source_identity(self._hmb_color_lut_state["source"]) == _source_identity(state["source"]):
                    self._hmb_color_lut_state["result"] = result
                    if action == "export":
                        self._publish_result_url(result["url"])
                    self._status("complete", str(result["path"]), 1)
                else:
                    self._publish()
            self._schedule_upload_probe()
        except Exception as exc:
            if key == _selection_key(self._hmb_color_lut_state) and _source_identity(self._hmb_color_lut_state["source"]) == _source_identity(state["source"]) and not self._hmb_node_deleted:
                self._status("cancelled" if cancel.is_set() else "error", str(exc))

    def _hmb_shot_channel_subscription(self) -> dict[str, Any]:
        shot = self._hmb_color_lut_state["shot"]
        enabled = bool(shot.get("channel_uuid") and shot.get("shot_uuid") and not self._hmb_node_deleted)
        return {"schema": "hmb-shot-channel-subscription", "version": 1, "participant_kind": "color_lut",
            "enabled": enabled, "channel_uuid": shot.get("channel_uuid", "") if enabled else "",
            "shot_uuid": shot.get("shot_uuid", "") if enabled else "", "shot_number": shot.get("number", 1), "shot_name": shot.get("name", "Only")}

    def _hmb_prepare_initial_shot_selection(self, shot_uuid: Any = "") -> None:
        if self._hmb_initial_shot_autoclaim_pending:
            self._hmb_initial_shot_preferred_uuid = str(shot_uuid or "")

    def _hmb_reconcile_shot_routing(self, snapshot: Any) -> None:
        catalog = _normalize_shot_catalog(snapshot, strict=True)
        with self._lock:
            previous = self._hmb_color_lut_state["shot_catalog"]
            if previous.get("channel_uuid") == catalog.get("channel_uuid") and int(previous.get("generation", 0)) > catalog["generation"]:
                return
            self._hmb_color_lut_state["shot_catalog"] = catalog
            shot = _normalize_shot_selection(self._hmb_color_lut_state["shot"], catalog)
            if self._hmb_initial_shot_autoclaim_pending and self._hmb_initial_shot_preferred_uuid:
                match = next((s for s in catalog["shots"] if s["shot_uuid"] == self._hmb_initial_shot_preferred_uuid), None)
                if match:
                    shot = {"channel_uuid": catalog["channel_uuid"], **{k: match[k] for k in ("shot_uuid", "number", "name")}}
                    self._hmb_initial_shot_autoclaim_pending = False
            if shot != self._hmb_color_lut_state["shot"]:
                self._switch(shot)
                self._hmb_color_lut_state["revision"] += 1
        self._publish()

    def _hmb_clear_shot_routing_catalog(self, reason: str = "publisher_unavailable") -> dict[str, Any]:
        with self._lock:
            self._hmb_color_lut_state["shot_catalog"] = {}
            self._switch(_shot_only())
            self._hmb_initial_shot_autoclaim_pending = False
            self._hmb_color_lut_state["revision"] += 1
        self._publish()
        return self._hmb_shot_channel_subscription()

    def _hmb_shot_routing_status(self, value: Any) -> None:
        self._route_status = copy.deepcopy(value)
        if isinstance(value, Mapping) and value.get("code") != "ready":
            with self._lock:
                self._web_upload_context = {}
                self._web_upload_probe_key = ""
                self._web_upload_epoch += 1
                self._web_upload_wake.set()
                self._web_upload["enabled"] = False
            self._publish()
        else:
            self._schedule_upload_probe()

    def _hmb_hydrate_color_lut_from_source(self, source: Any, source_parameter: str = "HMB_GENERATED_VIDEO_SOURCE") -> bool:
        reader = getattr(source, "_hmb_generated_video_source_snapshot", None)
        snapshot = reader() if callable(reader) else None
        if not isinstance(snapshot, Mapping) or not snapshot:
            return False
        shot = self._hmb_color_lut_state["shot"]
        if snapshot.get("shot_uuid") != shot.get("shot_uuid") or snapshot.get("channel_uuid") != shot.get("channel_uuid"):
            return False
        _set_parameter_silently(self, SOURCE, snapshot)
        self._queue_source(snapshot)
        return True

    def _reconcile(self) -> None:
        try:
            from _hmb_shot_routing import reconcile_shot_routing
            reconcile_shot_routing(self)
        except Exception:
            LOGGER.debug("Color LUT routing deferred", exc_info=True)

    def _hmb_post_registration_shot_discovery(self) -> None:
        if not self._hmb_node_deleted:
            self._reconcile()
            self._hmb_post_hydration_state_restore()

    def _hmb_post_hydration_state_restore(self) -> None:
        with self._lock:
            state = self._hmb_color_lut_state
            if not self._hmb_node_deleted and self._hydrated and not state["shot"].get("shot_uuid") and state["source"].get("path"):
                self._queue_source(state["source"])

    def set_parameter_value(self, name: str, value: Any, *args: Any, **kwargs: Any) -> Any:
        lock = getattr(self, "_lock", None)
        if lock is None:
            return super().set_parameter_value(name, value, *args, **kwargs)
        # Publication owns this same lock. A concurrent saved value must wait
        # until _syncing clears; only same-thread publication echoes may skip it.
        with lock:
            saved = (kwargs.get("initial_setup") is True and name == UI
                     and not self._syncing and not self._hmb_node_deleted and isinstance(value, Mapping))
            if saved:
                value = copy.deepcopy(value)
                value.pop("__hmb_color_lut_command__", None)
                supplied_project = str(value.get("project_id") or "")
                current_project = str(self._hmb_color_lut_state.get("project_id") or "")
                if self._project_authoritative and supplied_project != current_project:
                    value = copy.deepcopy(self._hmb_color_lut_state)
            result = super().set_parameter_value(name, value, *args, **kwargs)
            if saved:
                self._apply_ui(value, initial_setup=True)
                # Mirror only the normalized private state. Foreign source or
                # stale project fields must not remain visible in native UI.
                super().set_parameter_value(name, copy.deepcopy(self._hmb_color_lut_state), *args, **kwargs)
        if saved and not self._hmb_node_deleted:
            try:
                from _hmb_shot_routing import schedule_post_hydration_reconcile
                schedule_post_hydration_reconcile(self)
            except Exception:
                LOGGER.debug("Color LUT hydration discovery deferred", exc_info=True)
        return result

    def after_value_set(self, parameter: Any, value: Any) -> Any:
        # Wait for another thread\'s publication; only same-thread echoes may be skipped.
        with self._lock:
            parent = getattr(super(), "after_value_set", None)
            result = parent(parameter, value) if callable(parent) else None
            if self._syncing or self._hmb_node_deleted:
                return result
            name = str(getattr(parameter, "name", ""))
            if name == UI:
                self._apply_ui(value)
            elif name == COMMAND:
                self._command(value)
            elif name == SOURCE:
                self._queue_source(value)
            return result

    def process(self) -> None:
        # Workflow traversal only refreshes the source; paid upstream generation
        # is never invoked by the widget's local preview/export commands.
        # _queue_source publishes when the source actually changes. A second
        # unconditional full-state publication here duplicates that large
        # payload and can stall the editor without changing any output.
        self._queue_source(_raw_parameter(self, SOURCE))

    def after_node_deleted(self, *args: Any, **kwargs: Any) -> Any:
        with self._lock:
            if self._hmb_node_deleted:
                return None
            self._hmb_node_deleted = True
            self._source_token += 1
            self._cancel.set()
            self._web_upload_wake.set()
        try:
            from _hmb_shot_routing import prepare_node_deletion, release_node_lifecycle, schedule_post_deletion_reconcile
            prepare_node_deletion(self)
            release_node_lifecycle(self)
            schedule_post_deletion_reconcile(self)
        except Exception:
            LOGGER.debug("Color LUT deletion reconciliation deferred", exc_info=True)
        parent = getattr(super(), "after_node_deleted", None)
        return parent(*args, **kwargs) if callable(parent) else None
