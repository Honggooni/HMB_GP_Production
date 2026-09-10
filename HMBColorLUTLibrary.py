from __future__ import annotations

"""Local, post-generation color finishing. Commands never execute upstream nodes."""

import copy
import contextvars
import json
import logging
import os
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
                _set_parameter_silently(self, UI, state)
                publisher = getattr(self, "publish_update_to_parameter", None)
                if callable(publisher):
                    publisher(UI, state)
            finally:
                self._syncing = False

    def _status(self, phase: str, message: str = "", progress: float = 0) -> None:
        with self._lock:
            if self._hmb_color_lut_state["language"] == "ko":
                message = {"Loading video…": "영상을 불러오는 중…", "Processing original source…": "원본 영상 처리 중…",
                    "Encoding original source…": "원본 영상 인코딩 중…", "Preset saved.": "프리셋을 저장했습니다.",
                    "A local operation is already running.": "로컬 작업이 이미 진행 중입니다."}.get(message, message)
            self._hmb_color_lut_state["status"] = {"phase": phase, "message": message, "progress": progress}
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
        self._pending_source_key = None
        if not shot.get("shot_uuid") and saved.get("source", {}).get("path"):
            self._queue_source(saved["source"])

    def _apply_ui(self, value: Any) -> None:
        if not isinstance(value, Mapping):
            return
        command = value.get("__hmb_color_lut_command__")
        with self._lock:
            # A serialized backend state contains shot_states; a live widget
            # edit deliberately does not. Never hydrate read-only source data
            # back from that first compact edit after automatic routing.
            initial = not self._hydrated and isinstance(value.get("shot_states"), Mapping)
            self._hydrated = True
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
            self._hmb_color_lut_state["preset_name"] = str(value.get("preset_name") or "")[:80]
            self._hmb_color_lut_state["revision"] = max(revision, self._hmb_color_lut_state["revision"]) + 1
            self._remember_selection()
            if initial and not shot.get("shot_uuid") and self._hmb_color_lut_state["source"].get("path"):
                self._queue_source(self._hmb_color_lut_state["source"])
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
            if action in {"export", "browse_video"} and self._worker is not None and self._worker.is_alive():
                self._status("busy", "A local operation is already running.")
                return
            captured = copy.deepcopy(self._hmb_color_lut_state)
            # Commands may arrive before the debounced property update. Capture the
            # current UI settings, but never trust a UI-supplied source/provenance.
            authored = value.get("state")
            if isinstance(authored, Mapping) and _selection_key(authored) == _selection_key(captured):
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
        self._queue_source(_raw_parameter(self, SOURCE))
        self._publish()

    def after_node_deleted(self, *args: Any, **kwargs: Any) -> Any:
        if self._hmb_node_deleted:
            return None
        self._hmb_node_deleted = True
        self._source_token += 1
        self._cancel.set()
        try:
            from _hmb_shot_routing import prepare_node_deletion, release_node_lifecycle, schedule_post_deletion_reconcile
            prepare_node_deletion(self)
            release_node_lifecycle(self)
            schedule_post_deletion_reconcile(self)
        except Exception:
            LOGGER.debug("Color LUT deletion reconciliation deferred", exc_info=True)
        parent = getattr(super(), "after_node_deleted", None)
        return parent(*args, **kwargs) if callable(parent) else None
