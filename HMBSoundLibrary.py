from __future__ import annotations

"""Project sound browser, Shot assignments and authored audio timing.

Sound selection never runs an upstream node, model or renderer. Original audio
is read in place and only explicit finishing creates a new video in Color LUT.
"""
import copy
import contextvars
import hashlib
import json
import inspect
from pathlib import Path
import threading
from typing import Any
from urllib.parse import quote
from uuid import uuid4
import weakref

from HMBFinishLookLibrary import (
    DataNode, _add_parameter, _add_widget_parameter, _mode,
    _parameter_object, _set_parameter_silently, _normalize_shot_catalog, set_output,
    _normalize_shot_selection,
)
from _hmb_deletion_guard import hmb_binding_mutation
from _hmb_sound import (
    DEFAULT_PROJECTS_ROOT, SCHEMA, VERSION, SoundError, discover_sound_projects,
    scan_sound_project, make_sound_track, normalize_sound_snapshot, project_uid,
    MAX_TRACKS,
    relative_audio_path, absolute_path,
)

UI = "HMB_SOUND_UI_STATE"
COMMAND = "HMB_SOUND_COMMAND"
CATALOG_IN = "SHOT_ASSET_IN"
OUTPUTS = ("SOUND_OUT", "SHOT_SOUND_OUT")
SOUND_START_WIDTH = 1470
SOUND_START_HEIGHT = 710
SOUND_WIDGET_WIDTH = 1430
SOUND_WIDGET_HEIGHT = 620
_HIDDEN_OUTPUT_UI = {"hide": True, "hide_property": True, "hide_label": True, "hide_handles": True}
_SOUND_UI_REGISTRATION_LOCK = threading.RLock()


def _register_sound_ui_reader(node: HMBSoundLibrary) -> None:
    """Register a session-routed read for live Sound instances, once per engine."""
    try:
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
        engine = GriptapeNodes.get_instance()
    except (ImportError, RuntimeError):
        return

    from dataclasses import dataclass, field
    from griptape_nodes.retained_mode.events.base_events import (
        RequestPayload, ResultPayloadFailure, ResultPayloadSuccess, WorkflowNotAlteredMixin,
    )
    from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry
    from griptape_nodes.retained_mode.request_handlers import handles

    manager = engine.event_manager
    with _SOUND_UI_REGISTRATION_LOCK:
        handler = getattr(manager, "_hmb_sound_ui_read_handler", None)
        if handler is not None:
            handler.owners.add(node)
            return

        if PayloadRegistry.get_type("HMBGetSoundUISnapshotRequest") is None:
            @PayloadRegistry.register
            @dataclass
            class HMBGetSoundUISnapshotRequest(RequestPayload):
                node_name: str = ""
                expected_stream_id: str = ""
                workflow_name: str = ""
                flow_name: str = ""

            @PayloadRegistry.register
            @dataclass
            class HMBGetSoundUISnapshotResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
                node_name: str = ""
                snapshot: dict = field(default_factory=dict)

            @PayloadRegistry.register
            @dataclass
            class HMBGetSoundUISnapshotResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
                pass

        request_type = PayloadRegistry.get_type("HMBGetSoundUISnapshotRequest")
        success_type = PayloadRegistry.get_type("HMBGetSoundUISnapshotResultSuccess")
        failure_type = PayloadRegistry.get_type("HMBGetSoundUISnapshotResultFailure")

        class Handler:
            def __init__(self):
                self.engine_ref = weakref.ref(engine)
                self.owners = weakref.WeakSet()

            @handles(request_type)
            def read(self, request, workflow=None):
                current = self.engine_ref()
                name, expected = request.node_name, request.expected_stream_id
                workflow_name, flow_name = request.workflow_name, request.flow_name
                if (not isinstance(name, str) or not 1 <= len(name) <= 512
                        or not isinstance(expected, str) or len(expected) > 128
                        or not all(isinstance(part, str) and len(part) <= 512 for part in (workflow_name, flow_name))
                        or bool(workflow_name) != bool(flow_name)):
                    return failure_type(result_details="사운드 라이브러리 조회 요청 형식을 확인하세요.")
                # Mounting, switching shots and closing a workflow can retire a read.
                pending = success_type(node_name=name, result_details="Sound UI snapshot is not ready.")
                if current is None:
                    return pending
                try:
                    if workflow_name:
                        matches = [runtime for runtime in current.open_workflows.all_open()
                                   if current.workflow_registry.get(runtime.workflow_id).name == workflow_name]
                        if len(matches) != 1 or (workflow is not None and workflow is not matches[0]):
                            return pending
                        workflow = matches[0]
                    nodes = current.node_manager
                    if workflow is not None:
                        parent = workflow.nodes.parent_flow_name(name)
                        if flow_name and parent != flow_name:
                            return pending
                        flow = current.flow_manager.get_flow_by_name_in(workflow, parent)
                        lookup = lambda: nodes.get_node_by_name_in(workflow, name)
                    else:
                        context = current.context_manager
                        if not context.has_current_workflow() or not context.has_current_flow():
                            return pending
                        flow = context.get_current_flow()
                        lookup = lambda: nodes.get_node_by_name(name)
                    owner = lookup()
                    if owner not in self.owners or flow.nodes.get(name) is not owner:
                        return pending
                    snapshot = owner._hmb_sound_ui_read_snapshot(expected)
                    if flow.nodes.get(name) is not owner or lookup() is not owner:
                        return pending
                    if workflow_name and current.open_workflows.find(workflow.workflow_id) is not workflow:
                        return pending
                except (KeyError, ValueError):
                    return pending
                return success_type(node_name=name, snapshot=snapshot, result_details="Sound UI snapshot read.")

        handler = Handler()
        handler.owners.add(node)
        manager.register_request_handlers(handler)
        manager._hmb_sound_ui_read_handler = handler


def default_state() -> dict[str, Any]:
    return {"schema": "hmb-sound-library-ui", "version": 1, "revision": 0,
        "project_id": "", "project_root": "", "project_uid": "", "channel_uuid": "",
        "shot": {"channel_uuid": "", "shot_uuid": "", "number": 0, "name": "Only"},
        "shot_catalog": {}, "projects": [], "project_states": {}, "assets": [], "tracks": [], "status": "ImageAsset의 샷 연결을 기다리는 중",
        "busy": False, "error_code": "", "ack_command_id": "", "ui": {"search": "", "role": ""}}


class HMBSoundLibrary(DataNode):
    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.category = "HMB_GP_Production"
        self.metadata = {**dict(getattr(self, "metadata", {}) or {}), "library": "HMB_GP_Production", "node_type": "HMBSoundLibrary",
            "hmb_native_studio_ui": {"schema": "hmb-native-studio-ui", "version": 1, "node_type": "HMBSoundLibrary", "widget": "HMBSoundLibraryWidget"}}
        self.description = "Project audio, dialogue/lip-sync and exact Shot sound assignments."
        self._lock = threading.RLock()
        self._state_sound = default_state()
        self._syncing = False
        self._hmb_node_deleted = False
        self._worker = None
        self._pending_job = None
        self._desired_project_root = ""
        self._catalog_available = False
        self._sound_preparing = False
        self._sound_preparation_error = ""
        self._sound_pending_scope = ("", "")
        self._generation = 0
        self._seen_commands: list[str] = []
        self._source_nodes: dict[str, Any] = {}
        self._image_project_source = None
        self._context_epoch = 0
        self._scan_requested_root = ""
        self._scan_finished_root = ""
        self._standalone_discovery_started = False
        self._root_aliases: dict[str, str] = {}
        # UI transport is ephemeral. The retained property and both sound
        # outputs always contain complete authoring snapshots.
        self._ui_stream = str(uuid4())
        self._ui_sequence = 0
        self._ui_previous = None
        self._ui_catalog_cache = None
        self._ui_projection = contextvars.ContextVar("hmb_sound_ui_projection", default=None)
        initial = getattr(self, "set_initial_node_size", None)
        if "size" not in self.metadata:
            if callable(initial):
                initial(width=SOUND_START_WIDTH, height=SOUND_START_HEIGHT)
            else:
                self.metadata["size"] = {"width": SOUND_START_WIDTH, "height": SOUND_START_HEIGHT}
        _add_widget_parameter(self, widget_name="HMBSoundLibraryWidget", name=UI, default_value=self._state_sound,
            type="dict", input_types=["dict"], allow_input=False, allow_output=False, allow_property=True,
            allowed_modes=_mode("PROPERTY"), ui_options={"display_name": "HMB Sound Library", "is_full_width": True,
                "width": SOUND_WIDGET_WIDTH, "height": SOUND_WIDGET_HEIGHT,
                "min_width": 760, "min_height": 500, "expandable": True, "resizable": True})
        _add_parameter(self, name=COMMAND, type="str", input_types=["str"], default_value="",
            allow_input=False, allow_output=False, allow_property=True, allowed_modes=_mode("PROPERTY"),
            ui_options={"hide": True, "hide_property": True, "hide_handles": True})
        _add_parameter(self, name=CATALOG_IN, type="str", input_types=["str", "dict"], default_value="",
            allow_input=True, allow_output=False, allow_property=False, allowed_modes=_mode("INPUT"),
            ui_options={"hide": True, "hide_property": True, "hide_handles": True})
        for name in OUTPUTS:
            _add_parameter(self, name=name, type="dict", output_type="dict", default_value={},
                allow_input=False, allow_output=True, allow_property=False, allowed_modes=_mode("OUTPUT"),
                hide=True, hide_property=True,
                ui_options={"display_name": "Sound" if name == "SOUND_OUT" else "Shot Sound", **_HIDDEN_OUTPUT_UI})
        self._publish(notify=False)
        _register_sound_ui_reader(self)
        self._schedule_reconcile()

    def _snapshot(self) -> dict[str, Any]:
        state = self._state_sound
        if not state.get("project_root"):
            return {}
        return normalize_sound_snapshot({"schema": SCHEMA, "version": VERSION,
            **{k: copy.deepcopy(state[k]) for k in ("project_id", "project_root", "project_uid", "channel_uuid", "revision", "tracks")},
            **({"preparing": True} if self._sound_preparing else {}),
            **({"preparation_error": self._sound_preparation_error} if self._sound_preparation_error else {})})

    @staticmethod
    def _project_key(state: dict[str, Any]) -> str:
        return json.dumps([state.get("project_uid", ""), state.get("channel_uuid", "")], separators=(",", ":"))

    @classmethod
    def _track_total(cls, state: dict[str, Any]) -> int:
        active = cls._project_key(state)
        return len(state["tracks"]) + sum(len(row.get("tracks", [])) for key, row in state.get("project_states", {}).items() if key != active)

    @staticmethod
    def _project_document(state: dict[str, Any]) -> dict[str, Any]:
        snapshot = normalize_sound_snapshot({"schema": SCHEMA, "version": VERSION,
            **{k: copy.deepcopy(state[k]) for k in ("project_id", "project_root", "project_uid", "channel_uuid", "revision", "tracks")}})
        return {**snapshot, "shot": copy.deepcopy(state.get("shot", {})), "shot_catalog": copy.deepcopy(state.get("shot_catalog", {}))}

    @staticmethod
    def _normalize_saved_state(value: Any) -> dict[str, Any]:
        if not isinstance(value, dict) or value.get("schema") != "hmb-sound-library-ui" or type(value.get("version")) is not int or value["version"] != 1:
            raise SoundError("SOUND_SNAPSHOT_INVALID", "저장된 사운드 형식을 확인하세요.")
        saved = {**default_state(), **{k: copy.deepcopy(v) for k, v in value.items() if k in default_state()}}
        if not isinstance(saved["tracks"], list) or not isinstance(saved["assets"], list) or not isinstance(saved["projects"], list):
            raise SoundError("SOUND_SNAPSHOT_INVALID", "저장된 사운드 목록 형식을 확인하세요.")
        if saved.get("project_root"):
            snapshot = normalize_sound_snapshot({"schema": SCHEMA, "version": VERSION,
                **{k: saved[k] for k in ("project_id", "project_root", "project_uid", "channel_uuid", "revision", "tracks")}})
            saved.update(**{k: snapshot[k] for k in ("project_id", "project_root", "project_uid", "channel_uuid", "revision", "tracks")})
        elif saved["tracks"] or any(saved[k] for k in ("project_id", "project_uid")):
            raise SoundError("SOUND_PROJECT_INVALID", "저장된 사운드의 프로젝트 연결을 확인하세요.")
        if type(saved["revision"]) is not int or not 0 <= saved["revision"] < 2**53 or not isinstance(saved["channel_uuid"], str) or len(saved["channel_uuid"]) > 128:
            raise SoundError("SOUND_SNAPSHOT_INVALID", "저장된 사운드 갱신·샷 연결을 확인하세요.")
        saved["shot_catalog"] = _normalize_shot_catalog(saved["shot_catalog"], strict=True, allow_sparse=True)
        saved["shot"] = _normalize_shot_selection(saved["shot"], saved["shot_catalog"])
        if not saved["shot_catalog"]:
            saved["shot"] = default_state()["shot"]
        saved["projects"] = [p for p in saved["projects"][:1000] if isinstance(p, dict)
            and isinstance(p.get("project_id"), str) and isinstance(p.get("project_root"), str)]
        saved["assets"] = [p for p in saved["assets"][:20000] if isinstance(p, dict)
            and isinstance(p.get("relative_path"), str) and isinstance(p.get("name"), str)]
        histories = saved.get("project_states")
        if not isinstance(histories, dict) or len(histories) > 64:
            raise SoundError("SOUND_SNAPSHOT_INVALID", "저장된 프로젝트 사운드 기록을 확인하세요.")
        checked = {}
        for key, document in histories.items():
            if not isinstance(document, dict):
                raise SoundError("SOUND_SNAPSHOT_INVALID", "저장된 프로젝트 사운드 기록을 확인하세요.")
            normalized = normalize_sound_snapshot(document)
            if not normalized or key != HMBSoundLibrary._project_key(normalized):
                raise SoundError("SOUND_PROJECT_INVALID", "사운드 프로젝트 기록 식별자가 일치하지 않습니다.")
            catalog = _normalize_shot_catalog(document.get("shot_catalog"), strict=True, allow_sparse=True)
            checked[key] = {**normalized, "shot_catalog": catalog,
                "shot": _normalize_shot_selection(document.get("shot"), catalog)}
        saved["project_states"] = checked
        if HMBSoundLibrary._track_total(saved) > MAX_TRACKS:
            raise SoundError("SOUND_TRACK_LIMIT", "보존된 프로젝트를 포함해 사운드는 최대 64개 트랙까지 선택할 수 있습니다.")
        saved.update(busy=False, ack_command_id="", status="저장된 사운드 복원 완료", error_code="")
        return saved

    @hmb_binding_mutation
    def set_parameter_value(self, name: str, value: Any, *args: Any, **kwargs: Any) -> Any:
        lock = getattr(self, "_lock", None)
        if lock is None:
            return super().set_parameter_value(name, value, *args, **kwargs)
        restored_state = False
        with lock:
            if name == UI and isinstance(value, dict) and "__hmb_sound_command" in value:
                kwargs["emit_change"] = False
            restoring = name == UI and kwargs.get("initial_setup") is True and not self._syncing and not self._hmb_node_deleted
            if restoring:
                try:
                    restored = self._normalize_saved_state(value)
                except Exception:
                    # A malformed saved value never replaces already accepted
                    # originals/assignments or leaks a partial browser payload.
                    value = copy.deepcopy(self._state_sound)
                else:
                    self._generation += 1
                    self._pending_job = None
                    self._desired_project_root = ""
                    self._sound_preparing = False
                    self._sound_preparation_error = ""
                    self._state_sound = restored
                    self._context_epoch += 1
                    self._scan_requested_root = ""
                    self._scan_finished_root = ""
                    self._catalog_available = bool(restored["shot_catalog"])
                    self._ui_stream = str(uuid4())
                    self._ui_sequence = 0
                    self._ui_previous = None
                    self._ui_catalog_cache = None
                    value = copy.deepcopy(restored)
                    restored_state = True
            result = super().set_parameter_value(name, value, *args, **kwargs)
        if restored_state:
            from _hmb_shot_routing import schedule_post_hydration_reconcile

            schedule_post_hydration_reconcile(self)
        return result

    def _hmb_sound_snapshot_for(self, *, channel_uuid: str | None = None, shot_uuid: str | None = None) -> dict[str, Any]:
        context = self._registered_image_context()
        if context is not None:
            self._activate_sound_context(context)
        elif self._image_project_source is not None:
            raise SoundError("SOUND_CONNECTION_INVALID", "현재 이미지 라이브러리의 프로젝트·샷 연결을 확인하세요.")
        with self._lock:
            if self._hmb_node_deleted:
                raise SoundError("SOUND_OWNER_UNAVAILABLE", "사운드 라이브러리 연결을 확인하세요.")
            snapshot = self._snapshot()
            if channel_uuid and snapshot and snapshot["channel_uuid"] != channel_uuid:
                raise SoundError("SOUND_SHOT_MISMATCH", "사운드 라이브러리의 샷 연결을 확인하세요.")
            if shot_uuid and not any(row.get("shot_uuid") == shot_uuid for row in self._state_sound.get("shot_catalog", {}).get("shots", [])):
                raise SoundError("SOUND_SHOT_MISMATCH", "사운드 대상 샷이 현재 프로젝트에 없습니다.")
            if self._sound_pending_scope is not None and (channel_uuid is not None or shot_uuid is not None) and (channel_uuid or "", shot_uuid or "") != self._sound_pending_scope:
                snapshot.pop("preparing", None)
                snapshot.pop("preparation_error", None)
            return copy.deepcopy(snapshot)

    def _sound_ui_projection(self, state: dict[str, Any], *, full: bool = False) -> dict[str, Any]:
        """Prepare full/delta display data without changing persisted state."""
        previous = getattr(self, "_ui_previous", None)
        self._ui_sequence = getattr(self, "_ui_sequence", 0) + 1
        if not getattr(self, "_ui_stream", ""):
            self._ui_stream = str(uuid4())
        catalog_key = self._ui_catalog_cache[3]
        metadata = {"schema": "hmb-sound-ui-transport", "version": 1,
                    "stream_id": self._ui_stream, "sequence": self._ui_sequence,
                    "catalog_key": catalog_key}
        # Project changes and catalog replacements deliberately send a complete
        # snapshot; ordinary selection/edit/status updates omit the catalog.
        if full or previous is None or previous[0] != catalog_key:
            value = {**state, "__hmb_sound_transport": {**metadata, "mode": "full"}}
        else:
            prior = previous[1]
            value = {"schema": "hmb-sound-ui-patch", "version": 1,
                     "__hmb_sound_transport": {**metadata, "mode": "delta", "base_sequence": previous[2]},
                     "values": {key: value for key, value in state.items()
                                if key != "assets" and (key not in prior or value != prior[key])},
                     "removed": [key for key in prior if key not in state]}
        self._ui_previous = (catalog_key, state, self._ui_sequence)
        return value

    def get_display_value_for_output(self, parameter_name: str, output_value: Any) -> Any:
        local = getattr(self, "_ui_projection", None)
        projection = local.get() if local is not None else None
        if parameter_name == UI and projection is not None and output_value is projection[0]:
            return projection[1]
        parent = getattr(super(), "get_display_value_for_output", None)
        return parent(parameter_name, output_value) if callable(parent) else output_value

    def _sound_ui_state(self) -> tuple[dict[str, Any], tuple]:
        """Build the display snapshot and candidate catalog cache without writes."""
        state = copy.deepcopy({key: value for key, value in self._state_sound.items() if key != "assets"})
        try:
            from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
            base = str(GriptapeNodes.StaticFilesManager().static_server_base_url).rstrip("/")
        except Exception:
            base = ""
        source_assets = self._state_sound["assets"]
        scope = (state["project_root"], state["project_uid"], state["channel_uuid"], base)
        cached = self._ui_catalog_cache
        if cached is None or cached[0] != scope or cached[1] != source_assets:
            assets = copy.deepcopy(source_assets)
            for asset in assets:
                try:
                    path = relative_audio_path(Path(state["project_root"]), asset["relative_path"])
                    raw = str(path)
                    external = raw if raw.startswith("\\\\") else raw.replace("\\", "/").lstrip("/")
                    asset["preview_url"] = base + "/external/" + quote(external, safe="/:") + f"?v={asset.get('size', 0)}-{asset.get('mtime_ns', 0)}" if base else ""
                except Exception:
                    asset["preview_url"] = ""
            key = hashlib.sha256(json.dumps([scope, assets], ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            cached = (scope, copy.deepcopy(source_assets), assets, key)
        state["assets"] = cached[2]
        # Browser preview URLs are presentation only, never authority.
        for track in state["tracks"]:
            try:
                path = Path(track["path"])
                raw = str(path)
                external = raw if raw.startswith("\\\\") else raw.replace("\\", "/").lstrip("/")
                track["preview_url"] = base + "/external/" + quote(external, safe="/:") + "?v=" + track["media_signature"][:16] if base else ""
            except Exception:
                track["preview_url"] = ""
        return state, cached

    def _hmb_sound_ui_read_snapshot(self, expected_stream_id: str) -> dict[str, Any]:
        """Read a coherent UI baseline without publishing, scanning or advancing it."""
        with self._lock:
            if self._hmb_node_deleted or expected_stream_id and expected_stream_id != self._ui_stream:
                raise ValueError("Sound UI owner changed")
            if self._ui_previous is None:
                # Save hydration starts a new stream before the first publish.
                state, cached = self._sound_ui_state()
                catalog_key, sequence = cached[3], self._ui_sequence
            else:
                catalog_key, state, sequence = self._ui_previous
            value = copy.deepcopy(state)
            value["__hmb_sound_transport"] = {"schema": "hmb-sound-ui-transport", "version": 1,
                "mode": "full", "stream_id": self._ui_stream, "sequence": sequence, "catalog_key": catalog_key}
            return value

    def _publish(self, *, notify: bool = True, full: bool = False, outputs: bool = True) -> None:
        if self._hmb_node_deleted:
            return
        with self._lock:
            self._syncing = True
            try:
                state, self._ui_catalog_cache = self._sound_ui_state()
                _set_parameter_silently(self, UI, state)
                publisher = getattr(self, "publish_update_to_parameter", None)
                if callable(publisher):
                    # Native publish stores its argument in output_values.
                    # Only display events are projected, never that argument.
                    token = self._ui_projection.set((state, self._sound_ui_projection(state, full=full)))
                    try:
                        publisher(UI, state)
                    except Exception:
                        self._ui_previous = None
                        raise
                    finally:
                        self._ui_projection.reset(token)
                if outputs:
                    snapshot = self._snapshot()
                    for name in OUTPUTS:
                        set_output(self, name, copy.deepcopy(snapshot))
            finally:
                self._syncing = False
        if notify:
            self._notify_consumers()

    def _notify_consumers(self) -> None:
        try:
            from _hmb_shot_routing import _same_flow_nodes, _incoming_connections
            from _hmb_connection_management import is_detached
            _flow, nodes = _same_flow_nodes(self)
            if is_detached(self):
                return
            for node in nodes:
                if node is self or is_detached(node):
                    continue
                for edge in _incoming_connections(node):
                    if getattr(edge, "source_node_name", "") == self.name and getattr(edge, "source_parameter_name", "") in OUTPUTS:
                        callback = getattr(node, "_hmb_hydrate_sound_source", None)
                        if callable(callback):
                            callback(self)
                        else:
                            node.set_parameter_value(getattr(edge, "target_parameter_name"), copy.deepcopy(self._snapshot()))
                        break
        except Exception:
            # Exact execution readers resolve from the retained source again.
            # Presentation notification failure cannot alter stored selection.
            pass

    def _registered_image_context(self, expected_project: Any = None, expected_catalog: Any = None) -> dict[str, Any] | None:
        """Resolve current project metadata from one real retained Image publisher."""
        try:
            from _hmb_shot_routing import _same_flow_nodes
            from _hmb_connection_management import is_detached, relationship_suspended
            flow, nodes = _same_flow_nodes(self)
            if not flow or self not in nodes:
                return None
            contexts = []
            for source in nodes:
                metadata = getattr(source, "metadata", {}) or {}
                if (type(source).__name__ != "HMBImageAssetLibrary" or metadata.get("library") != "HMB_GP_Production"
                        or metadata.get("node_type") != "HMBImageAssetLibrary" or getattr(source, "_hmb_node_deleted", False)
                        or is_detached(source) or relationship_suspended(source, self)):
                    continue
                if Path(inspect.getfile(type(source))).resolve() != Path(__file__).with_name("HMBImageAssetLibrary.py").resolve():
                    continue
                raw = source.get_parameter_value("HMB_IMAGE_ASSET_STATE")
                if isinstance(raw, str):
                    raw = json.loads(raw)
                if not isinstance(raw, dict) or not raw.get("project_root"):
                    continue
                image_root = absolute_path(raw["project_root"])
                if image_root.name.casefold() != "ai_ct_image":
                    continue
                if isinstance(expected_project, dict) and expected_project.get("root") and absolute_path(expected_project["root"]) != image_root:
                    continue
                catalog = _normalize_shot_catalog(source._hmb_shot_routing_catalog(), strict=True, allow_sparse=True)
                if not catalog:
                    continue
                if expected_catalog and any(catalog.get(key) != expected_catalog.get(key) for key in ("channel_uuid", "publisher_instance_uuid", "generation", "metadata_sha256")):
                    continue
                contexts.append({"source": source, "project_id": image_root.parent.name,
                    "project_root": str(image_root.parent / "Ai_Ct_audio"), "catalog": catalog})
            return contexts[0] if len(contexts) == 1 else None
        except Exception:
            return None

    def _has_image_peer(self) -> bool:
        try:
            from _hmb_shot_routing import _same_flow_nodes
            _flow, nodes = _same_flow_nodes(self)
            return any(type(node).__name__ == "HMBImageAssetLibrary" and not getattr(node, "_hmb_node_deleted", False) for node in nodes)
        except Exception:
            return False

    def _activate_sound_context(self, context: dict[str, Any]) -> None:
        """Switch only Sound's own project state; old assignments remain archived."""
        root = absolute_path(context["project_root"])
        root = Path(self._root_aliases.get(str(root).casefold(), str(root)))
        catalog = _normalize_shot_catalog(context.get("catalog"), strict=True, allow_sparse=True)
        channel = catalog.get("channel_uuid", "")
        uid = project_uid(root)
        target_key = self._project_key({"project_uid": uid, "channel_uuid": channel})
        with self._lock:
            if self._hmb_node_deleted:
                return
            state = self._state_sound
            old_key, old_root = self._project_key(state), state.get("project_root", "")
            changed = old_key != target_key
            owner_changed = self._image_project_source is not context.get("source")
            if changed:
                histories = copy.deepcopy(state["project_states"])
                if old_root:
                    histories[old_key] = self._project_document(state)
                if len(histories) > 64:
                    raise SoundError("SOUND_TRACK_LIMIT", "보존된 사운드 프로젝트 기록을 확인하세요.")
                saved = histories.get(target_key, {})
                state["project_states"] = histories
                state.update(project_id=context["project_id"], project_root=str(root), project_uid=uid, channel_uuid=channel,
                    tracks=copy.deepcopy(saved.get("tracks", [])), shot=copy.deepcopy(saved.get("shot", default_state()["shot"])))
                if old_root != str(root):
                    state["assets"] = []
            self._image_project_source = context.get("source")
            self._catalog_available = bool(catalog)
            if state["shot_catalog"] != catalog or changed:
                state["shot_catalog"] = catalog
                selected = _normalize_shot_selection(state["shot"], catalog)
                if catalog and not selected.get("shot_uuid"):
                    selected = {"channel_uuid": channel, **{key: catalog["shots"][0][key] for key in ("shot_uuid", "number", "name")}}
                state["shot"] = selected if catalog else default_state()["shot"]
                state["revision"] += 1
            if changed or owner_changed:
                self._context_epoch += 1
                self._generation += 1
                self._pending_job = None
                self._sound_preparing = False
                self._sound_preparation_error = ""
                state["busy"] = False
            state["projects"] = [{"project_id": state["project_id"], "project_root": state["project_root"]}]
            self._scan_sound_context()

    def _scan_sound_context(self, *, force: bool = False) -> None:
        with self._lock:
            state = self._state_sound
            root, uid, epoch = state["project_root"], state["project_uid"], self._context_epoch
            if not root or (not force and self._scan_requested_root == uid):
                return
            self._scan_requested_root = uid
            restoring_tracks = bool(state["tracks"] and self._scan_finished_root != uid)
            def work():
                assets = scan_sound_project(root)
                canonical_root = Path(root).resolve()
                canonical_uid = project_uid(canonical_root)
                def commit():
                    if epoch != self._context_epoch or self._state_sound["project_uid"] != uid:
                        return False
                    if canonical_uid != uid:
                        current = self._state_sound
                        old_key = self._project_key(current)
                        if current["tracks"]:
                            current["project_states"][old_key] = self._project_document(current)
                        canonical_key = self._project_key({"project_uid": canonical_uid, "channel_uuid": current["channel_uuid"]})
                        saved = current["project_states"].get(canonical_key, {})
                        current.update(project_id=canonical_root.parent.name, project_root=str(canonical_root), project_uid=canonical_uid,
                            tracks=copy.deepcopy(saved.get("tracks", [])))
                        selected = _normalize_shot_selection(saved.get("shot", current["shot"]), current["shot_catalog"])
                        current["shot"] = selected
                        self._context_epoch += 1
                        self._root_aliases[str(absolute_path(root)).casefold()] = str(canonical_root)
                    self._state_sound["assets"] = assets
                    self._scan_requested_root = canonical_uid
                    self._scan_finished_root = canonical_uid
                return commit
            self._start_job(work, "사운드 목록 준비 중…", replace=True, preparing=restoring_tracks, scope=None)

    def _hmb_follow_image_asset_project(self, project: Any) -> None:
        # Internal context discovery only. Image files, asset selections and UI
        # project controls never become Sound records.
        context = self._registered_image_context(expected_project=project)
        if context is not None:
            self._activate_sound_context(context)

    def _discover_standalone_context(self, *, force: bool = False) -> None:
        with self._lock:
            if self._hmb_node_deleted or self._image_project_source is not None or (self._standalone_discovery_started and not force):
                return
            if self._has_image_peer():
                self._state_sound.update(status="ImageAsset의 샷 연결을 기다리는 중", error_code="")
                return
            self._standalone_discovery_started = True
            def work():
                projects = discover_sound_projects(DEFAULT_PROJECTS_ROOT)
                def commit():
                    current = self._registered_image_context()
                    if current is not None:
                        self._activate_sound_context(current)
                        return
                    self._state_sound["projects"] = projects
                    if len(projects) == 1 and not self._has_image_peer():
                        self._activate_sound_context({**projects[0], "source": None, "catalog": {}})
                    else:
                        self._state_sound.update(status="샷 컨텍스트가 필요합니다. 이미지 라이브러리의 프로젝트·샷을 선택하세요.", error_code="SOUND_CONTEXT_REQUIRED")
                        return False
                return commit
            self._start_job(work, "사운드 경로 확인 중…", replace=True)

    def _schedule_reconcile(self) -> None:
        try:
            from _hmb_shot_routing import schedule_post_registration_reconcile
            schedule_post_registration_reconcile(self)
        except Exception:
            pass

    def _start_job(self, operation, message: str, *, replace: bool = False, preparing: bool = False, scope: tuple[str, str] | None = ("", "")) -> None:
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                if not replace:
                    raise SoundError("SOUND_BUSY", "사운드 준비가 끝난 뒤 다시 선택하세요.")
                self._generation += 1
                self._sound_preparing = preparing
                self._sound_preparation_error = ""
                self._sound_pending_scope = scope
                self._pending_job = (operation, self._generation)
                self._state_sound.update(busy=True, status=message, error_code="")
                self._publish(notify=False)
                return
            self._generation += 1
            self._sound_preparing = preparing
            self._sound_preparation_error = ""
            self._sound_pending_scope = scope
            generation = self._generation
            self._state_sound.update(busy=True, status=message, error_code="")
            context = contextvars.copy_context()
            def run():
                active_operation, active_generation = operation, generation
                while True:
                    try:
                        result = active_operation()
                        with self._lock:
                            if not self._hmb_node_deleted and active_generation == self._generation:
                                outcome = result()
                                if active_generation == self._generation:
                                    self._sound_preparing = False
                                    self._state_sound["revision"] += 1
                                    self._state_sound["busy"] = False
                                    if outcome is not False:
                                        self._state_sound.update(status="사운드 준비 완료", error_code="")
                    except Exception as exc:
                        with self._lock:
                            if not self._hmb_node_deleted and active_generation == self._generation:
                                if self._sound_preparing:
                                    self._sound_preparation_error = "SOUND_PREPARATION_FAILED"
                                self._sound_preparing = False
                                self._state_sound["revision"] += 1
                                self._state_sound.update(busy=False, status=str(exc) if isinstance(exc, SoundError) else "사운드 준비에 실패했습니다. 연결과 음원 형식을 확인하세요.", error_code=getattr(exc, "code", "SOUND_PREPARATION_FAILED"))
                    with self._lock:
                        if self._hmb_node_deleted:
                            self._pending_job = None
                            return
                        pending, self._pending_job = self._pending_job, None
                        if pending is None:
                            self._worker = None
                    if active_generation == self._generation:
                        try:
                            self._publish()
                        except Exception:
                            pass  # A UI notification cannot undo accepted edits.
                    if pending is None:
                        return
                    active_operation, active_generation = pending
            self._worker = threading.Thread(target=lambda: context.run(run), daemon=True, name="HMB-Sound-Prepare")
            self._publish(notify=False)
            self._worker.start()

    @hmb_binding_mutation
    def _command(self, value: Any) -> None:
        command = json.loads(value) if isinstance(value, str) else value
        if not isinstance(command, dict) or not isinstance(command.get("id"), str) or not 1 <= len(command["id"]) <= 128:
            raise SoundError("SOUND_COMMAND_INVALID", "사운드 명령을 다시 선택하세요.")
        with self._lock:
            if command.get("action") == "ui_sync":
                if self._hmb_node_deleted:
                    raise SoundError("SOUND_OWNER_UNAVAILABLE", "삭제된 사운드 라이브러리에는 작업할 수 없습니다.")
                # Read-only display recovery: no revision, binding, scan,
                # cancellation, normal-command acknowledgement, or output edit.
                self._publish(notify=False, full=True, outputs=False)
                return
            if command["id"] in self._seen_commands:
                return
            self._seen_commands.append(command["id"])
            self._seen_commands = self._seen_commands[-256:]
            action = command.get("action")
            state = self._state_sound
            state["ack_command_id"] = command["id"]
            if action == "cancel":
                self._generation += 1
                self._pending_job = None
                self._desired_project_root = ""
                self._sound_preparing = False
                self._sound_preparation_error = ""
                state.update(busy=False, status="사운드 준비를 취소했습니다.", error_code="")
                state["revision"] += 1
                self._publish(notify=False)
                return
            if self._hmb_node_deleted:
                raise SoundError("SOUND_OWNER_UNAVAILABLE", "삭제된 사운드 라이브러리에는 작업할 수 없습니다.")
            supplied = command.get("context")
            expected = {"project_uid": state["project_uid"], "channel_uuid": state["shot"].get("channel_uuid", ""),
                        "shot_uuid": state["shot"].get("shot_uuid", ""), "revision": state["revision"]}
            valid_context = supplied == expected
            if action == "shot_add" and isinstance(supplied, dict):
                valid_context = (supplied.get("project_uid") == state["project_uid"]
                    and supplied.get("channel_uuid") == state["channel_uuid"] and supplied.get("revision") == state["revision"])
            if supplied is not None and not valid_context:
                raise SoundError("SOUND_CONTEXT_CHANGED", "프로젝트·샷 선택이 변경되었습니다. 현재 목록에서 다시 선택하세요.")
            if state["busy"] and action != "project":
                raise SoundError("SOUND_BUSY", "사운드 준비가 끝난 뒤 다시 선택하세요.")
            if action == "projects":
                def work():
                    projects = discover_sound_projects()
                    return lambda: state.update(projects=projects)
                self._start_job(work, "프로젝트 사운드 폴더 확인 중…")
                return
            if action in {"project", "refresh"}:
                if action == "refresh" and not state["project_root"]:
                    self._discover_standalone_context(force=True)
                    return
                selected = next((p for p in state["projects"] if p["project_id"] == command.get("project_id")), None) if action == "project" else {"project_id": state["project_id"], "project_root": state["project_root"]}
                if not selected or not selected["project_root"]:
                    raise SoundError("SOUND_PROJECT_UNAVAILABLE", "현재 샷의 사운드 폴더를 확인하세요.")
                selected = copy.deepcopy(selected)
                if state["project_root"] != selected["project_root"] and state["tracks"]:
                    raise SoundError("SOUND_PROJECT_IN_USE", "기존 사운드는 보존했습니다. 현재 샷의 사운드 폴더 연결을 확인하세요.")
                self._desired_project_root = selected["project_root"]
                def work():
                    assets = scan_sound_project(selected["project_root"])
                    def commit():
                        if state["project_root"] != selected["project_root"] and state["tracks"]:
                            raise SoundError("SOUND_PROJECT_IN_USE", "기존 사운드는 보존했습니다. 현재 샷의 사운드 폴더 연결을 확인하세요.")
                        state.update(**selected, project_uid=project_uid(Path(selected["project_root"])), assets=assets)
                        self._scan_requested_root = state["project_uid"]
                        self._scan_finished_root = state["project_uid"]
                        self._desired_project_root = ""
                    return commit
                self._start_job(work, "사운드 목록 준비 중…", replace=action == "project")
                return
            if action == "shot":
                identity = command.get("shot_uuid", "")
                selected = next((row for row in state["shot_catalog"].get("shots", []) if row["shot_uuid"] == identity), None)
                if identity and not selected:
                    raise SoundError("SOUND_SHOT_MISMATCH", "현재 프로젝트의 샷을 선택하세요.")
                state["shot"] = {"channel_uuid": state["channel_uuid"], **{k: selected[k] for k in ("shot_uuid", "number", "name")}} if selected else default_state()["shot"]
            elif action in {"add", "shot_add"}:
                if self._track_total(state) >= MAX_TRACKS:
                    raise SoundError("SOUND_TRACK_LIMIT", "사운드는 최대 64개 트랙까지 선택할 수 있습니다.")
                relative = command.get("relative_path")
                source_uid = command.get("source_uid")
                selected_asset = next((row for row in state["assets"] if (row.get("source_uid") == source_uid if source_uid else row["relative_path"] == relative)), None)
                if selected_asset is None or (source_uid and relative is not None and selected_asset["relative_path"] != relative):
                    raise SoundError("SOUND_SOURCE_UNAVAILABLE", "현재 목록에서 음원을 선택하세요.")
                relative = selected_asset["relative_path"]
                if action == "shot_add":
                    selected_shot = next((row for row in state["shot_catalog"].get("shots", []) if row["shot_uuid"] == command.get("shot_uuid")), None)
                    if selected_shot is None or state["shot_catalog"].get("channel_uuid") != state["channel_uuid"]:
                        raise SoundError("SOUND_SHOT_MISMATCH", "현재 이미지 라이브러리의 샷에만 사운드를 추가할 수 있습니다.")
                    scope = {"channel_uuid": state["channel_uuid"], **{key: selected_shot[key] for key in ("shot_uuid", "number", "name")}}
                else:
                    scope = copy.deepcopy(state["shot"])
                if any(t["relative_path"] == relative and t["shot_uuid"] == scope["shot_uuid"] and t["channel_uuid"] == scope["channel_uuid"] for t in state["tracks"]):
                    return
                root = state["project_root"]
                epoch = self._context_epoch
                def work():
                    track = make_sound_track(root, relative, channel_uuid=scope["channel_uuid"], shot_uuid=scope["shot_uuid"])
                    def commit():
                        if state["project_root"] != root or epoch != self._context_epoch:
                            raise SoundError("SOUND_CONTEXT_CHANGED", "음원 준비 중 프로젝트·샷이 변경되었습니다.")
                        if scope["shot_uuid"] and not any(row["shot_uuid"] == scope["shot_uuid"] for row in state["shot_catalog"].get("shots", [])):
                            raise SoundError("SOUND_SHOT_MISMATCH", "음원 준비 중 대상 샷이 제거되었습니다.")
                        if any(t["relative_path"] == relative and t["shot_uuid"] == scope["shot_uuid"] and t["channel_uuid"] == scope["channel_uuid"] for t in state["tracks"]):
                            return
                        candidate = copy.deepcopy(state)
                        candidate["tracks"] = [*candidate["tracks"], track]
                        checked = self._normalize_saved_state(candidate)
                        state["tracks"] = checked["tracks"]
                    return commit
                self._start_job(work, "음원 원본·재생 정보 준비 중…", preparing=True, scope=(scope["channel_uuid"], scope["shot_uuid"]))
                return
            elif action in {"edit", "remove", "duplicate"}:
                track = next((t for t in state["tracks"] if t["instance_id"] == command.get("instance_id")), None)
                if track is None:
                    raise SoundError("SOUND_TRACK_UNAVAILABLE", "최신 사운드 목록에서 다시 선택하세요.")
                if action == "remove":
                    state["tracks"] = [t for t in state["tracks"] if t is not track]
                elif action == "duplicate":
                    if self._track_total(state) >= MAX_TRACKS:
                        raise SoundError("SOUND_TRACK_LIMIT", "사운드는 최대 64개 트랙까지 선택할 수 있습니다.")
                    state["tracks"].append({**copy.deepcopy(track), "instance_id": str(uuid4())})
                else:
                    allowed = {"role", "purpose", "transcript", "target", "in_seconds", "out_seconds", "start_seconds", "gain_db", "enabled", "loop", "lipsync"}
                    changes = command.get("changes")
                    if not isinstance(changes, dict) or not set(changes) <= allowed:
                        raise SoundError("SOUND_EDIT_INVALID", "사운드 편집 항목이 올바르지 않습니다.")
                    previous = copy.deepcopy(track)
                    track.update(copy.deepcopy(changes))
                    try:
                        self._snapshot()
                    except Exception:
                        track.clear(); track.update(previous)
                        raise
            else:
                raise SoundError("SOUND_COMMAND_INVALID", "지원하지 않는 사운드 명령입니다.")
            state["revision"] += 1
            self._publish()

    def _hmb_reconcile_shot_routing(self, snapshot: Any) -> None:
        catalog = _normalize_shot_catalog(snapshot, strict=True, allow_sparse=True)
        context = self._registered_image_context(expected_catalog=catalog)
        if context is not None:
            self._activate_sound_context(context)
            self._publish(notify=False)
            return
        with self._lock:
            previous = self._state_sound["shot_catalog"]
            if previous.get("channel_uuid") == catalog["channel_uuid"]:
                if previous.get("generation", 0) > catalog["generation"]:
                    return
                if previous.get("generation") == catalog["generation"] and previous.get("metadata_sha256") != catalog["metadata_sha256"]:
                    raise SoundError("SOUND_SHOT_MISMATCH", "같은 샷 갱신 번호의 연결 데이터가 변경되었습니다.")
            if self._state_sound["channel_uuid"] and self._state_sound["channel_uuid"] != catalog["channel_uuid"] and self._state_sound["tracks"]:
                self._state_sound.update(status="기존 사운드 샷 연결을 보존했습니다. 원래 프로젝트를 확인하세요.", error_code="SOUND_SHOT_MISMATCH")
                return
            self._state_sound["channel_uuid"] = catalog["channel_uuid"]
            self._state_sound["shot_catalog"] = catalog
            self._state_sound["shot"] = _normalize_shot_selection(self._state_sound["shot"], catalog)
            self._catalog_available = True
            if previous != catalog:
                self._state_sound["revision"] += 1
            self._publish(notify=False)

    def _hmb_clear_shot_routing_catalog(self, reason: str = "publisher_unavailable") -> dict[str, Any]:
        with self._lock:
            self._catalog_available = False
            self._state_sound["shot_catalog"] = {}
            self._state_sound["shot"] = default_state()["shot"]
            self._state_sound["revision"] += 1
            self._publish(notify=False)
        return self._hmb_shot_channel_subscription()

    def _hmb_shot_channel_subscription(self) -> dict[str, Any]:
        return {"schema": "hmb-shot-channel-subscription", "version": 1, "participant_kind": "sound",
            "enabled": bool(self._state_sound["channel_uuid"] and self._catalog_available and not self._hmb_node_deleted),
            "channel_uuid": self._state_sound["channel_uuid"], "shot_uuid": "", "shot_number": 1, "shot_name": "Sound Library"}

    def _hmb_shot_routing_status(self, value: Any) -> None:
        self._route_status = copy.deepcopy(value)

    def after_value_set(self, parameter: Any, value: Any) -> Any:
        result = getattr(super(), "after_value_set", lambda *_: None)(parameter, value)
        if self._syncing:
            return result
        name = getattr(parameter, "name", parameter)
        if name == COMMAND and value:
            try:
                self._command(value)
            except Exception as exc:
                with self._lock:
                    self._state_sound.update(status=str(exc) if isinstance(exc, SoundError) else "사운드 작업을 완료하지 못했습니다.", error_code=getattr(exc, "code", "SOUND_COMMAND_FAILED"))
                self._publish(notify=False)
        elif name == UI and isinstance(value, dict):
            if "__hmb_sound_command" in value:
                try:
                    self._command(value["__hmb_sound_command"])
                except Exception as exc:
                    with self._lock:
                        self._state_sound.update(status=str(exc) if isinstance(exc, SoundError) else "사운드 작업을 완료하지 못했습니다.", error_code=getattr(exc, "code", "SOUND_COMMAND_FAILED"))
                    self._publish(notify=False)
                finally:
                    # The SDK stores the incoming property before this hook.
                    # Duplicate/no-op commands must not leave that envelope in
                    # a saved workflow or keep a widget awaiting its ack.
                    retained = self.get_parameter_value(UI)
                    if isinstance(retained, dict) and "__hmb_sound_command" in retained:
                        self._publish(notify=False, outputs=False)
                return result
            # Live UI owns bounded commands only. Native initial_setup restores
            # through set_parameter_value because the SDK suppresses this hook.
            self._publish(notify=False)
        return result

    def after_deserialize(self, *args: Any, **kwargs: Any) -> Any:
        result = getattr(super(), "after_deserialize", lambda *_a, **_k: None)(*args, **kwargs)
        for name in OUTPUTS:
            parameter = _parameter_object(self, name)
            if parameter is not None:
                parameter.hide = parameter.hide_property = True
                parameter.ui_options = {**(parameter.ui_options or {}), **_HIDDEN_OUTPUT_UI}
        self._schedule_reconcile()
        return result

    def _hmb_post_registration_shot_discovery(self) -> None:
        if not self._hmb_node_deleted:
            context = self._registered_image_context()
            if context is not None:
                self._activate_sound_context(context)
            elif not self._state_sound["project_root"]:
                self._discover_standalone_context()
            elif not self._scan_requested_root:
                self._scan_sound_context()
            self._publish(full=True)
            if context is not None:
                # Registration discovery can enable Sound after ImageAsset's
                # last routing pass. Reconcile this authoritative context on
                # the host's next turn, including Image-before-Sound creation.
                from _hmb_shot_routing import schedule_post_hydration_reconcile
                schedule_post_hydration_reconcile(self)

    def _hmb_post_hydration_state_restore(self) -> None:
        if not self._hmb_node_deleted:
            context = self._registered_image_context()
            if context is not None:
                self._activate_sound_context(context)
            elif self._state_sound["project_root"] and not self._scan_requested_root:
                self._scan_sound_context()
            self._publish(full=True)

    def after_node_deleted(self, *args: Any, **kwargs: Any) -> Any:
        self._hmb_node_deleted = True
        self._generation += 1
        self._pending_job = None
        self._sound_preparing = False
        from _hmb_shot_routing import release_node_lifecycle
        release_node_lifecycle(self)
        return getattr(super(), "after_node_deleted", lambda *_a, **_k: None)(*args, **kwargs)

    def process(self):
        self._publish()
