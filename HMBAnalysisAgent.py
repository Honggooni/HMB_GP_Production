from __future__ import annotations

import asyncio
import copy
import hashlib
import logging
from pathlib import Path
import re
from stat import S_ISREG
from tempfile import TemporaryDirectory
import threading
from typing import Any
from urllib.parse import urlsplit

from HMBFinishLookLibrary import (
    DataNode, _add_parameter, _add_widget_parameter, _mode, _set_parameter_silently,
)
from _hmb_analysis_delivery import ANALYSIS_RESULT_TEXT_LIMIT
from _hmb_reference_analysis import ANALYSIS_CATEGORIES, AnalysisError, _source_path, analysis_model_choices
from _hmb_shot_routing import _same_flow_nodes, release_node_lifecycle, schedule_post_registration_reconcile


UI = "HMB_ANALYSIS_UI_STATE"
STATE = "HMB_ANALYSIS_STATE"
FILE = "HMB_ANALYSIS_FILE"
_COMMAND = "__hmb_analysis_command"
_SCHEMA = "hmb-reference-analysis-state"
_KINDS = ("image", "video", "audio")
_ROLES = ("after", "before")
_ROLE_LOCK = threading.RLock()
_FIELD_LIMITS = {"PROJECT_STYLE_LOOK": 6000, "SCENE_CONTEXT": 6000,
                 "EMOTION_INTENT": 6000, "PRESERVED_TEXT": 6000, "VIDEO_VFX": 20000}
_CATEGORY_FIELDS = {
    "composition": "VIDEO_VFX", "lighting_reference": "PROJECT_STYLE_LOOK",
    "color_look": "PROJECT_STYLE_LOOK", "character_pose": "EMOTION_INTENT",
    "appearance": "SCENE_CONTEXT", "camera": "VIDEO_VFX", "motion": "SCENE_CONTEXT",
    "cut_timing": "VIDEO_VFX", "effect_shape": "VIDEO_VFX", "effect_timing": "VIDEO_VFX",
    "audio_content": "SCENE_CONTEXT", "audio_delivery": "EMOTION_INTENT",
    "audio_rhythm": "VIDEO_VFX", "audio_effects": "VIDEO_VFX", "audio_timing": "VIDEO_VFX",
}
_CATEGORY_LABELS = {
    "camera": "카메라", "motion": "동작", "cut_timing": "컷 타이밍",
    "effect_shape": "이펙트 형태", "effect_timing": "이펙트 타이밍",
    "composition": "구도·프레이밍", "lighting_reference": "라이팅 참고", "color_look": "컬러 룩",
    "character_pose": "캐릭터 포즈", "appearance": "캐릭터·소품 외형",
    "audio_content": "대사·발음", "audio_delivery": "말투·감정", "audio_rhythm": "리듬·강약",
    "audio_effects": "효과음·환경음", "audio_timing": "시작·종료 타이밍",
}
_SUFFIXES = {
    "image": {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"},
    "video": {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"},
    "audio": {".wav", ".mp3", ".flac", ".m4a", ".aac", ".aif", ".aiff", ".ogg"},
}
_LOG = logging.getLogger(__name__)


class _AnalysisStateError(ValueError):
    pass


def _text(value: Any, limit: int) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


def _seconds(value: Any) -> float | None:
    if type(value) not in (int, float) or not 0 <= value <= 86400:
        return None
    return round(float(value), 3)


def _local_file(value: Any) -> tuple[Path, str]:
    raw = _text(value, 4096)
    candidate = Path(raw)
    if not raw or not candidate.is_absolute() or raw.startswith(("\\\\", "//")) or "://" in raw:
        raise _AnalysisStateError("이미지·영상·오디오의 로컬 파일을 선택하세요.")
    try:
        path = candidate.resolve(strict=True)
    except (OSError, ValueError, RuntimeError):
        raise _AnalysisStateError("선택한 파일을 읽을 수 없습니다.") from None
    for kind, suffixes in _SUFFIXES.items():
        if path.suffix.casefold() in suffixes and path.is_file():
            return path, kind
    raise _AnalysisStateError("지원하는 이미지·영상·오디오 형식을 선택하세요.")


def _source_stamp(source: dict) -> list[Any]:
    raw, kind = source.get("path"), source.get("kind")
    if kind == "image" and isinstance(raw, str) and raw.startswith("data:image/"):
        if len(raw) > 45_000_000 or not raw.isascii():
            return []
        return ["data:" + hashlib.sha256(raw.encode("ascii")).hexdigest(), 0, 0, len(raw), 0, 0]
    try:
        path = _source_path(raw, kind).resolve(strict=True)
        stat = path.stat()
    except (OSError, ValueError, RuntimeError, TypeError):
        return []
    if not S_ISREG(stat.st_mode) or not stat.st_size:
        return []
    return [str(path), stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns]


def _result(value: Any, kind: str) -> dict:
    if not isinstance(value, dict) or value.get("kind") != kind:
        return {}
    key, digest = value.get("cache_key"), value.get("source_digest")
    if not all(isinstance(x, str) and re.fullmatch("[0-9a-f]{64}", x) for x in (key, digest)):
        return {}
    supplied = value.get("observations")
    if not isinstance(supplied, dict):
        return {}
    observations = {}
    for category in ANALYSIS_CATEGORIES.get(kind, ()):
        rows = supplied.get(category)
        if not isinstance(rows, list):
            continue
        clean = []
        for row in rows[:12]:
            if not isinstance(row, dict):
                continue
            observation = _text(row.get("observation"), 480)
            interpretation = _text(row.get("interpretation"), 480)
            if not observation and not interpretation:
                continue
            item = {"observation": observation, "interpretation": interpretation}
            start, end = _seconds(row.get("start")), _seconds(row.get("end"))
            if start is not None:
                item["start"] = start
            if end is not None and start is not None and start <= end:
                item["end"] = end
            if kind == "video":
                start_frame, end_frame = row.get("start_frame"), row.get("end_frame")
                if type(start_frame) is int and start_frame >= 0:
                    item["start_frame"] = start_frame
                    if type(end_frame) is int and end_frame >= start_frame:
                        item["end_frame"] = end_frame
            clean.append(item)
        if clean:
            observations[category] = clean
    if not observations:
        return {}
    interval = value.get("range")
    interval = interval if isinstance(interval, dict) else {}
    result = {"cache_key": key, "source_digest": digest, "kind": kind, "range": {
        "start": _seconds(interval.get("start")), "end": _seconds(interval.get("end"))},
        "model": _text(value.get("model"), 128), "cache_hit": value.get("cache_hit") is True,
        "observations": observations}
    model_settings_digest = value.get("model_settings_sha256")
    if isinstance(model_settings_digest, str) and re.fullmatch("[0-9a-f]{64}", model_settings_digest):
        result["model_settings_sha256"] = model_settings_digest
    broker_request_id = value.get("broker_request_id")
    if isinstance(broker_request_id, str) and re.fullmatch("analysis-[0-9a-f]{32}", broker_request_id):
        result["broker_request_id"] = broker_request_id
    if kind in ("video", "audio"):
        field = "frame_ranges" if kind == "video" else "time_ranges"
        if ranges := _saved_ranges(value.get(field) or interval.get(field), kind):
            result[field] = ranges
    return result


def _scope(channel: str, shot: str) -> str:
    return f"{channel}\x1f{shot}" if channel and shot else ""


def _default_slot() -> dict:
    return {"origin": "", "kind": "", "source_id": "", "source_role": "after", "path": "", "model": "", "guidance": "",
            "start": None, "end": None, "frame_ranges": [], "time_ranges": [], "full_video": False,
            "result": {}, "stamp": [], "categories": [],
            "edited_result": "", "edited_categories": [], "field_overrides": {},
            "applied": False, "prompt_applied": False, "results_only": False,
            "send_agent": True, "send_original": False, "original_stamp": []}


def _selected_result_items(slot: dict) -> list[dict]:
    selected = slot["categories"]
    return [{**item, "category": key} for key, rows in slot["result"].get("observations", {}).items()
            if not selected or key in selected for item in rows]


def _selected_categories(slot: dict, command: dict) -> list[str]:
    categories = command.get("categories", slot["categories"])
    observations = slot["result"].get("observations", {})
    if (not isinstance(categories, list)
            or any(not isinstance(key, str) or key not in observations for key in categories)):
        raise _AnalysisStateError("현재 소스의 분석 항목을 선택하세요.")
    return [key for key in observations if key in categories]


def _edited_result(slot: dict) -> str:
    return slot["edited_result"] if slot["edited_categories"] == slot["categories"] else ""


def _result_editor_text(slot: dict) -> str:
    if edited := _edited_result(slot):
        return edited
    return "\n".join(_format_result_item(row) for row in _selected_result_items(slot))[:ANALYSIS_RESULT_TEXT_LIMIT]


def _format_result_item(row: dict, *, include_interpretation: bool = True) -> str:
    timing = ""
    if "start_frame" in row:
        end = f"–{row['end_frame']}" if "end_frame" in row and row["end_frame"] != row["start_frame"] else ""
        timing = f" ({row['start_frame']}{end}프레임)"
    elif "start" in row:
        end = f"–{row['end']:g}" if "end" in row else ""
        timing = f" ({row['start']:g}{end}초)"
    text = row["observation"]
    if include_interpretation and row["interpretation"]:
        text = " · ".join(filter(None, (text, row["interpretation"])))
    return f"{_CATEGORY_LABELS[row['category']]}{timing} · {text}" if text else ""


def _prompt_result_fields(slot: dict) -> dict[str, str]:
    grouped = {field: [] for field in _FIELD_LIMITS}
    for row in _selected_result_items(slot):
        field = _CATEGORY_FIELDS[row["category"]]
        # Scene facts must come from observed source content. The analysis
        # schema contains no exact-literal evidence, so only an explicit edit
        # can fill PRESERVED_TEXT.
        line = _format_result_item(row, include_interpretation=field != "SCENE_CONTEXT")
        if line:
            grouped[field].append(" ".join(line.splitlines()))
    overrides = slot.get("field_overrides", {})
    return {field: overrides.get(field, "\n".join(grouped[field])[:limit])
            for field, limit in _FIELD_LIMITS.items()}


def _valid_stamp(stamp: Any) -> bool:
    return (isinstance(stamp, list) and len(stamp) == 6 and isinstance(stamp[0], str)
            and all(type(part) is int for part in stamp[1:]))


def _saved_ranges(value: Any, kind: str) -> list[dict]:
    if not value:
        return []
    from _hmb_reference_analysis import normalize_analysis_ranges

    try:
        return normalize_analysis_ranges(value, kind=kind)
    except AnalysisError:
        return []


def _normalize_slot(value: Any) -> dict:
    slot = _default_slot()
    if not isinstance(value, dict):
        return slot
    slot["results_only"] = value.get("results_only") is True
    kind, origin = value.get("kind"), value.get("origin")
    if kind not in _KINDS or origin not in ("prompt", "direct"):
        return slot
    saved_model = _text(value.get("model"), 128)
    slot.update(origin=origin, kind=kind, source_id=_text(value.get("source_id"), 512),
        source_role=value["source_role"] if value.get("source_role") in _ROLES else "after",
        path=_text(value.get("path"), 4096) if origin == "direct" else "",
        model=saved_model if saved_model in analysis_model_choices(kind) else "",
        guidance=_text(value.get("guidance"), 500),
        start=_seconds(value.get("start")) if kind != "image" else None,
        end=_seconds(value.get("end")) if kind != "image" else None)
    if kind in ("video", "audio"):
        field = "frame_ranges" if kind == "video" else "time_ranges"
        slot[field] = _saved_ranges(value.get(field), kind)
    if kind == "video":
        full_video = value.get("full_video")
        slot["full_video"] = full_video if type(full_video) is bool else (
            not slot["frame_ranges"] and slot["start"] is None and slot["end"] is None)
    result = _result(value.get("result"), kind)
    stamp, categories = value.get("stamp"), value.get("categories")
    if result and _valid_stamp(stamp) and isinstance(categories, list):
        selected = [key for key in result["observations"] if key in categories]
        slot.update(result=result, stamp=list(stamp), categories=selected,
                    prompt_applied=value.get("prompt_applied") is True)
        edited_categories = value.get("edited_categories")
        if isinstance(edited_categories, list):
            slot.update(edited_result=_text(value.get("edited_result"), ANALYSIS_RESULT_TEXT_LIMIT),
                        edited_categories=[key for key in result["observations"] if key in edited_categories])
        overrides = value.get("field_overrides")
        if isinstance(overrides, dict):
            slot["field_overrides"] = {field: overrides[field][:limit] for field, limit in _FIELD_LIMITS.items()
                                       if isinstance(overrides.get(field), str)}
    original_stamp = value.get("original_stamp")
    original = (value.get("applied") is True
                and value.get("send_original", value.get("send_original_to_generator")) is True
                and _valid_stamp(original_stamp))
    send_agent = value.get("send_agent", True) is True
    slot.update(send_agent=send_agent, send_original=original,
        original_stamp=list(original_stamp) if original else [],
        applied=original or (bool(slot["result"]) and send_agent))
    return slot


def _normalize_catalog(value: Any) -> dict:
    if not isinstance(value, dict) or not isinstance(value.get("shots"), list):
        return {}
    channel = _text(value.get("channel_uuid"), 128)
    if not channel or "\x1f" in channel:
        return {}
    rows = []
    numbers, shots = set(), set()
    for item in value["shots"][:5]:
        if not isinstance(item, dict):
            continue
        number, shot = item.get("number"), _text(item.get("shot_uuid"), 128)
        if type(number) is not int or not 1 <= number <= 5 or not shot or "\x1f" in shot or number in numbers or shot in shots:
            continue
        numbers.add(number)
        shots.add(shot)
        rows.append({"number": number, "shot_uuid": shot, "name": _text(item.get("name"), 128) or f"샷 {number}"})
    return {"channel_uuid": channel, "shots": sorted(rows, key=lambda row: row["number"])} if rows else {}


def _registered_node_class(name: str) -> type | None:
    try:
        from griptape_nodes.node_library.library_registry import LibraryRegistry

        return LibraryRegistry.get_library("HMB_GP_Production").get_node_class(name)
    except (ImportError, AttributeError, RuntimeError, KeyError, ValueError):
        return None


def _live_analysis_nodes(nodes: list[Any]) -> list[Any]:
    expected = _registered_node_class("HMBAnalysisAgent")
    return [node for node in nodes if type(node) is expected
            and getattr(node, "_hmb_reference_analysis_node", False)
            and not getattr(node, "_hmb_node_deleted", False)]


def _analysis_role(node: Any) -> str | None:
    return getattr(node, "_role", "after")


def _find_analysis_node(nodes: list[Any], *, role: str) -> Any | None:
    live = _live_analysis_nodes(nodes)
    matches = [node for node in live if _analysis_role(node) == role]
    return matches[0] if len(live) <= len(_ROLES) and len(matches) == 1 else None


def get_analysis_context(prompt_owner: Any, *, channel_uuid: str, shot_uuid: str, destination: str) -> dict:
    """Read only an applied selection from the exact registered Prompt flow."""
    flow, nodes = _same_flow_nodes(prompt_owner)
    if not flow or prompt_owner not in nodes:
        return {}
    node = _find_analysis_node(nodes, role="after")
    if node is None:
        return {}
    return node._hmb_analysis_context_for(prompt_owner, channel_uuid=channel_uuid,
        shot_uuid=shot_uuid, destination=destination)


def get_analysis_original(prompt_owner: Any, *, channel_uuid: str, shot_uuid: str) -> dict:
    flow, nodes = _same_flow_nodes(prompt_owner)
    node = _find_analysis_node(nodes, role="after") if flow and prompt_owner in nodes else None
    return node._hmb_analysis_original_for(prompt_owner, channel_uuid=channel_uuid, shot_uuid=shot_uuid) if node else {}


def get_analysis_originals(prompt_owner: Any, *, channel_uuid: str, shot_uuid: str, preview: bool = False) -> list[dict]:
    flow, nodes = _same_flow_nodes(prompt_owner)
    if not flow or prompt_owner not in nodes or type(prompt_owner) is not _registered_node_class("HMBPromptLibrary"):
        return []
    node = _find_analysis_node(nodes, role="after")
    if node is not None:
        return node._hmb_analysis_originals_for(prompt_owner, channel_uuid=channel_uuid, shot_uuid=shot_uuid, preview=preview)
    live = _live_analysis_nodes(nodes)
    if len(live) > len(_ROLES) or any(_analysis_role(candidate) != "before" for candidate in live):
        return []
    # The default also applies before an Analysis Agent is added. Only a
    # registered analysis node can opt an exact Shot out of its originals.
    return _reference_tokens(_prompt_analysis_originals(prompt_owner, channel_uuid, shot_uuid, preview=preview))


def _prompt_analysis_originals(owner: Any, channel: str, shot: str, *, preview: bool) -> list[dict]:
    getter = getattr(owner, "_hmb_analysis_preview_sources_for" if preview else "_hmb_analysis_originals_for", None)
    try:
        return getter(channel_uuid=channel, shot_uuid=shot) if callable(getter) else []
    except (RuntimeError, ValueError):
        return []


def _reference_tokens(originals: list[dict]) -> list[dict]:
    from _hmb_analysis_delivery import reference_identity

    seen = set()
    rows = []
    for original in originals:
        kind, path = original["kind"], original["path"]
        identity = kind, reference_identity(path)
        if identity in seen:
            continue
        seen.add(identity)
        rows.append({**original, "start": original.get("start_seconds"), "end": original.get("end_seconds")})
    for index, row in enumerate(rows, 1):
        if not row.get("shot_reference"):
            row["shot_reference"] = "@analysis_original" if len(rows) == 1 else f"@analysis_original_{row['kind']}_{index}"
    return rows


def get_analysis_results_only(prompt_owner: Any, *, channel_uuid: str, shot_uuid: str, preview: bool = False) -> bool:
    from _hmb_connection_management import relationship_suspended

    flow, nodes = _same_flow_nodes(prompt_owner)
    node = _find_analysis_node(nodes, role="after") if flow and prompt_owner in nodes else None
    if (node is None or relationship_suspended(prompt_owner, node)
            or (not preview and node._exact_owner(node._registered_catalogs(), channel_uuid, shot_uuid) is not prompt_owner)):
        return False
    with node._lock:
        return (_analysis_role(node) == "after"
                and node._slots.get(_scope(channel_uuid, shot_uuid), {}).get("results_only") is True)


def _notify_prompt_media_changed(owner: Any, channel: str, shot: str) -> None:
    notify = getattr(owner, "_hmb_notify_analysis_delivery_changed", None)
    if callable(notify):
        notify(channel_uuid=channel, shot_uuid=shot)


def schedule_analysis_refresh(anchor: Any) -> None:
    """Refresh the analysis panel after same-flow Prompt or Agent changes."""
    flow, nodes = _same_flow_nodes(anchor)
    if flow and anchor in nodes:
        for node in _live_analysis_nodes(nodes):
            node._hmb_schedule_analysis_refresh()


def _local_preview_url(raw: Any) -> str:
    raw = _text(raw, 8192)
    if any(ord(char) < 32 or ord(char) == 127 for char in raw):
        return ""
    try:
        parsed = urlsplit(raw)
        if raw.startswith("/") and not raw.startswith(("//", "/\\")):
            return raw
        if (parsed.scheme in ("http", "https") and parsed.hostname in ("localhost", "127.0.0.1", "::1")
                and not parsed.username and not parsed.password):
            return raw
    except ValueError:
        pass
    return ""


def _preview(source: dict) -> str:
    raw, kind = source.get("path"), source.get("kind")
    try:
        if kind == "image":
            from HMBImageAssetLibrary import _asset_thumbnail_url, _generate_thumbnail_payload, _publish_thumbnail_payload

            if isinstance(raw, str) and raw.startswith("data:image/"):
                from _hmb_reference_analysis import _read_source, _source_suffix

                with TemporaryDirectory(prefix="hmb-analysis-preview-") as directory:
                    stage = Path(directory) / ("source" + _source_suffix(raw, kind))
                    digest = _read_source(raw, kind, stage=stage, is_live=lambda: True)
                    payload, extension, _, _ = _generate_thumbnail_payload(stage)
                return _local_preview_url(_publish_thumbnail_payload(payload, extension, "analysis", digest))
            path = _source_path(raw, kind)
            return _local_preview_url(_asset_thumbnail_url(path, "analysis")) or _local_preview_url(source.get("preview_url"))
        if kind in ("video", "audio"):
            from HMBVideoPickerLibrary import _external_media_url

            return _local_preview_url(source.get("preview_url")) or _local_preview_url(_external_media_url(_source_path(raw, kind)))
    except (AttributeError, ImportError, OSError, RuntimeError, TypeError, ValueError):
        pass
    return ""


def _analysis_timeline(source: dict, legacy_start: float | None, legacy_end: float | None) -> dict:
    kind = source.get("kind")
    try:
        if kind == "video":
            from _hmb_reference_analysis import analysis_video_frame_info

            return analysis_video_frame_info(source["path"], legacy_start=legacy_start, legacy_end=legacy_end)
        if kind == "audio" and not _seconds(source.get("duration_seconds")):
            from _hmb_reference_analysis import analysis_audio_duration

            return {"duration_seconds": analysis_audio_duration(source["path"])}
    except (AnalysisError, OSError, RuntimeError, ValueError):
        return {"timeline_error": True}
    return {}


class HMBAnalysisAgent(DataNode):
    _hmb_reference_analysis_node = True

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.category = "HMB_GP_Production"
        self.metadata = {**dict(getattr(self, "metadata", {}) or {}),
            "library": "HMB_GP_Production", "node_type": "HMBAnalysisAgent",
            "hmb_native_studio_ui": {"schema": "hmb-native-studio-ui", "version": 1,
                "node_type": "HMBAnalysisAgent", "widget": "HMBAnalysisAgentWidget"}}
        self.description = "Shot-scoped reference image, video, and audio analysis."
        self._lock = threading.RLock()
        self._role: str | None = None
        self._slots: dict[str, dict] = {}
        self._active = ("", "")
        self._revision = 0
        self._ack = ""
        self._recent: list[str] = []
        self._status = ""
        self._error = ""
        self._job: tuple[str, threading.Event] | None = None
        self._hmb_node_deleted = False
        self._syncing = False
        self._sources_key = ("", "")
        self._sources: list[dict] = []
        self._selected_source: dict = {}
        self._catalog: dict = {}
        self._default_model: str | None = None
        self._refresh_queued = False
        self._refresh_preserve_results = False
        self._preview_request = None
        self._preview_task = None
        size = getattr(self, "set_initial_node_size", None)
        if callable(size):
            size(width=780, height=1160)
        else:
            self.metadata.setdefault("size", {"width": 780, "height": 1160})
        _add_widget_parameter(self, widget_name="HMBAnalysisAgentWidget", name=UI, default_value={},
            type="dict", input_types=["dict"], allow_input=False, allow_output=False, allow_property=True,
            allowed_modes=_mode("PROPERTY"), ui_options={"display_name": "HMB Analysis Agent",
                "is_full_width": True, "width": 736, "height": 1055, "min_width": 606, "min_height": 625,
                "expandable": True, "resizable": True})
        _add_parameter(self, name=STATE, type="dict", default_value={}, allow_input=False,
            allow_output=False, allow_property=True, allowed_modes=_mode("PROPERTY"),
            ui_options={"hide": True, "hide_property": True, "hide_handles": True})
        _add_parameter(self, name=FILE, type="str", default_value="", allow_input=False,
            allow_output=False, allow_property=True, allowed_modes=_mode("PROPERTY"),
            ui_options={"display_name": "직접 분석할 파일", "clickable_file_browser": True})
        self._publish()
        schedule_post_registration_reconcile(self)

    def _ensure_registered_role(self) -> None:
        if _analysis_role(self) is not None:
            return
        flow, nodes = _same_flow_nodes(self)
        if not flow or self not in nodes:
            return
        with _ROLE_LOCK:
            occupied = {_analysis_role(node) for node in _live_analysis_nodes(nodes)}
            if self._role is None:
                self._role = next((role for role in _ROLES if role not in occupied), None)

    def _role_options(self) -> tuple[str, list[str], bool]:
        role = _analysis_role(self) or "after"
        flow, nodes = _same_flow_nodes(self)
        if not flow or self not in nodes:
            return role, list(_ROLES), False
        live = _live_analysis_nodes(nodes)
        if len(live) > len(_ROLES):
            return role, [role], True
        occupied = {_analysis_role(node) for node in live if node is not self}
        return role, [option for option in _ROLES if option == role or option not in occupied], role in occupied

    def _set_role(self, command: dict) -> None:
        role = command.get("role")
        if role not in _ROLES:
            raise _AnalysisStateError("선행 분석 또는 후속 분석을 선택하세요.")
        flow, nodes = _same_flow_nodes(self)
        if not flow or self not in nodes:
            raise _AnalysisStateError("분석 노드가 워크플로에 등록된 뒤 다시 시도하세요.")
        with _ROLE_LOCK, self._lock:
            if self._job is not None:
                raise _AnalysisStateError("실행 중인 분석이 완료된 뒤 사용 위치를 바꾸세요.")
            if type(command.get("revision")) is not int or command["revision"] != self._revision:
                raise _AnalysisStateError("분석 상태가 변경되었습니다. 사용 위치를 다시 선택하세요.")
            live = _live_analysis_nodes(nodes)
            if len(live) > len(_ROLES) or any(node is not self and _analysis_role(node) == role for node in live):
                raise _AnalysisStateError("이 워크플로에서 해당 사용 위치의 분석 노드가 이미 있습니다.")
            self._role = role
        self._refresh_sources(preserve_results=True)
        for owner, catalog in self._registered_catalogs():
            for shot in catalog["shots"]:
                _notify_prompt_media_changed(owner, catalog["channel_uuid"], shot["shot_uuid"])
        for node in live:
            if node is not self:
                node._hmb_schedule_analysis_refresh(preserve_results=True)
        self._status = "선행 분석으로 설정" if role == "before" else "후속 분석으로 설정"

    def _registered_catalogs(self, *, include_suspended: bool = False) -> list[tuple[Any, dict]]:
        from _hmb_connection_management import relationship_suspended

        flow, nodes = _same_flow_nodes(self)
        role = _analysis_role(self)
        if not flow or self not in nodes or role is None or _find_analysis_node(nodes, role=role) is not self:
            return []
        prompt_class = _registered_node_class("HMBPromptLibrary")
        catalogs = []
        for node in nodes:
            if (type(node) is not prompt_class or getattr(node, "_hmb_node_deleted", False)
                    or (not include_suspended and relationship_suspended(node, self))):
                continue
            getter = getattr(node, "_hmb_analysis_catalog", None)
            if not callable(getter):
                continue
            try:
                catalog = _normalize_catalog(getter())
            except (RuntimeError, ValueError):
                continue
            if catalog:
                catalogs.append((node, catalog))
        return catalogs

    def _hmb_connection_dependency_shots(self, source: Any, *, include_suspended: bool = False) -> list[dict]:
        catalogs = self._registered_catalogs(include_suspended=include_suspended)
        return [dict(channel_uuid=catalog["channel_uuid"], **row) for owner, catalog in catalogs if owner is source
                for row in catalog["shots"] if self._exact_owner(catalogs, catalog["channel_uuid"], row["shot_uuid"]) is source]

    def _hmb_deletion_dependencies(self) -> list[Any]:
        catalogs = self._registered_catalogs()
        return [owner for owner, catalog in catalogs if any(
            self._exact_owner(catalogs, catalog["channel_uuid"], row["shot_uuid"]) is owner for row in catalog["shots"])]

    def _hmb_refresh_retained_analysis_binding(self, source: Any) -> bool:
        # Reproject the link display without touching the stored Analysis slots.
        if _analysis_role(self) == "after":
            for row in self._hmb_connection_dependency_shots(source, include_suspended=True):
                _notify_prompt_media_changed(source, row["channel_uuid"], row["shot_uuid"])
        return self._hmb_schedule_analysis_refresh(preserve_results=True)

    @staticmethod
    def _exact_owner(catalogs: list[tuple[Any, dict]], channel: str, shot: str) -> Any | None:
        matched = [owner for owner, catalog in catalogs if catalog["channel_uuid"] == channel
                   and any(row["shot_uuid"] == shot for row in catalog["shots"])]
        return matched[0] if len(matched) == 1 else None

    def _resolve_source(self, owner: Any, channel: str, shot: str, slot: dict) -> dict:
        if slot["origin"] == "direct":
            try:
                path, kind = _local_file(slot["path"])
            except _AnalysisStateError:
                return {}
            if kind != slot["kind"]:
                return {}
            return {"kind": kind, "source_id": slot["source_id"], "name": path.name, "path": str(path)}
        if slot["origin"] != "prompt":
            return {}
        getter = getattr(owner, "_hmb_analysis_upstream_reference_for" if _analysis_role(self) == "before"
                         else "_hmb_analysis_reference_for", None)
        if not callable(getter):
            return {}
        try:
            row = getter(channel_uuid=channel, shot_uuid=shot, kind=slot["kind"], source_id=slot["source_id"])
        except (RuntimeError, ValueError):
            return {}
        if (not isinstance(row, dict) or row.get("kind") != slot["kind"] or row.get("source_id") != slot["source_id"]
                or not isinstance(row.get("path"), str) or not row["path"]):
            return {}
        return row

    def _refresh_sources(self, *, preserve_results: bool = False, page_only: bool = False) -> None:
        self._ensure_registered_role()
        with self._lock:
            if not page_only:
                # Source/configuration changes invalidate inactive media views.
                # Saved analysis text remains in its exact UUID-owned slot.
                self._display_pages = {}
            expected_active = self._active
        channel, shot = expected_active
        catalogs = self._registered_catalogs()
        if preserve_results and channel and shot and self._exact_owner(catalogs, channel, shot) is None:
            catalogs = []  # Keep the saved selection while its connection is absent.
        channels = {catalog["channel_uuid"] for _, catalog in catalogs}
        if channel not in channels and len(channels) == 1:
            channel = next(iter(channels))
        all_rows = [row for _, catalog in catalogs if catalog["channel_uuid"] == channel
                    for row in catalog["shots"]]
        rows = [row for row in all_rows if sum(
            other["number"] == row["number"] or other["shot_uuid"] == row["shot_uuid"]
            for other in all_rows
        ) == 1]
        rows.sort(key=lambda row: row["number"])
        owner = None
        if rows:
            if not any(row["shot_uuid"] == shot for row in rows):
                shot = rows[0]["shot_uuid"]
            owner = self._exact_owner(catalogs, channel, shot)
        with self._lock:
            if self._active != expected_active:
                return
            if owner is None:
                self._catalog, self._sources, self._selected_source = {}, [], {}
                self._default_model = None
                self._preview_request = None
                return
            self._catalog = {"channel_uuid": channel, "shots": rows}
            self._active = (channel, shot)
            if self._active != expected_active:
                self._default_model = None
            slot = copy.deepcopy(self._slots.get(_scope(channel, shot), _default_slot()))
        from HMBAgentLibrary import get_same_shot_analysis_model_label

        try:
            default_model = get_same_shot_analysis_model_label(owner, channel_uuid=channel, shot_uuid=shot)
        except AnalysisError:
            default_model = None
        sources = []
        preview_getter = getattr(owner, "_hmb_analysis_upstream_preview_sources_for" if _analysis_role(self) == "before"
                                 else "_hmb_analysis_preview_sources_for", None)
        prepared_page = page_only and callable(preview_getter)
        getter = preview_getter if prepared_page else getattr(
            owner, "_hmb_analysis_upstream_sources_for" if _analysis_role(self) == "before"
            else "_hmb_analysis_sources_for", None)
        if callable(getter):
            try:
                sources = getter(channel_uuid=channel, shot_uuid=shot)
            except (RuntimeError, ValueError):
                pass
        if prepared_page:
            # A page switch only reads the exact-Shot prepared display. Execution
            # and edits still resolve and stamp the current original independently.
            selected = next((row for row in sources if isinstance(row, dict)
                             and row.get("kind") == slot["kind"] and row.get("source_id") == slot["source_id"]), {}) \
                if slot["origin"] == "prompt" else {}
            if slot["origin"] == "direct":
                selected = {"kind": slot["kind"], "source_id": slot["source_id"],
                            "name": Path(slot["path"]).name, "path": slot["path"]}
        else:
            selected = self._resolve_source(owner, channel, shot, slot) if slot["origin"] else {}
        path = selected.get("path", "")
        stamp = ((slot["stamp"] or slot["original_stamp"]) if prepared_page else
                 (_source_stamp(selected) if selected and (slot["result"] or slot["send_original"]
                  or not path.startswith("data:image/")) else []))
        other_role_source = not selected and slot["origin"] == "prompt" and slot["source_role"] != _analysis_role(self)
        invalidated = not prepared_page and not other_role_source and bool(slot["result"] and stamp != slot["stamp"])
        original_changed = not prepared_page and not other_role_source and slot["send_original"] and stamp != slot["original_stamp"]
        with self._lock:
            current = self._slots.get(_scope(channel, shot), _default_slot())
            if self._active != (channel, shot) or current != slot:
                return
            self._default_model = default_model
            self._sources_key = self._active
            projected = [{key: row[key] for key in ("kind", "source_id", "name")
                              if key in row} for row in sources[:160]
                if isinstance(row, dict)] if isinstance(sources, list) else []
            if projected != self._sources:
                self._sources = projected
                self._revision += 1
            previous_source = self._selected_source
            self._selected_source = {key: selected[key] for key in (
                                     "kind", "source_id", "name", "duration_seconds", "start_seconds", "end_seconds")
                                     if key in selected}
            identity = (self._active, _analysis_role(self), selected.get("kind"), selected.get("source_id"), path,
                        () if path.startswith("data:image/") else tuple(stamp), slot["start"], slot["end"])
            cached_preview = getattr(self, "_preview_cache", {}).get(identity)
            if not selected:
                self._preview_request = None
            elif cached_preview is not None:
                self._preview_request = None
                self._selected_source.update(cached_preview)
            elif self._preview_request is not None and self._preview_request[0] == identity:
                for field in ("preview_url", "frame_count", "frame_rate", "duration_seconds",
                              "legacy_frame_ranges", "timeline_error"):
                    if field in previous_source:
                        self._selected_source[field] = previous_source[field]
                if self._preview_task is None and "preview_url" not in previous_source:
                    self._queue_preview(identity, selected, slot["start"], slot["end"])
            else:
                self._queue_preview(identity, selected, slot["start"], slot["end"])
            if invalidated and not preserve_results:
                current.update(result={}, stamp=[], categories=[], edited_result="", edited_categories=[],
                               field_overrides={}, prompt_applied=False, applied=slot["send_original"])
            if original_changed and not preserve_results:
                current.update(original_stamp=[], send_original=False,
                               applied=current["send_agent"] and bool(current["result"]))
            if invalidated or original_changed:
                self._revision += 1
                self._status = "참고 소스가 변경되어 다시 분석해야 합니다."

    def _queue_preview(self, identity: tuple, source: dict, legacy_start: float | None, legacy_end: float | None) -> None:
        if self._preview_request is None or self._preview_request[0] != identity:
            self._preview_request = (identity, source, legacy_start, legacy_end)
        if self._preview_task is not None:
            return
        try:
            from griptape_nodes.retained_mode.engine import has_current_engine
            from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

            if not has_current_engine():
                return
            loop = GriptapeNodes.EventManager().event_loop
            if loop is None or not loop.is_running():
                return
        except (AttributeError, ImportError, RuntimeError):
            return

        async def render_latest() -> None:
            while True:
                with self._lock:
                    request = self._preview_request
                    if self._hmb_node_deleted or request is None:
                        self._preview_task = None
                        return
                try:
                    url, timeline = await asyncio.gather(
                        asyncio.to_thread(_preview, request[1]),
                        asyncio.to_thread(_analysis_timeline, *request[1:]),
                    )
                except Exception:
                    url, timeline = "", {"timeline_error": True}
                with self._lock:
                    if url and not timeline.get("timeline_error") and not self._hmb_node_deleted:
                        cache = getattr(self, "_preview_cache", {})
                        cache.pop(request[0], None)
                        cache[request[0]] = {"preview_url": url, **timeline}
                        while len(cache) > 10:
                            cache.pop(next(iter(cache)))
                        self._preview_cache = cache
                    if self._preview_request is not request:
                        continue
                    self._preview_task = None
                    if self._hmb_node_deleted:
                        return
                    self._selected_source["preview_url"] = url
                    self._selected_source.update(timeline)
                self._publish()
                return

        coroutine = render_latest()
        try:
            self._preview_task = asyncio.run_coroutine_threadsafe(coroutine, loop)
        except RuntimeError:
            coroutine.close()

    def _publish(self) -> None:
        role, available_roles, role_conflict = self._role_options()
        with self._lock:
            if self._hmb_node_deleted:
                return
            channel, shot = self._active
            key = _scope(channel, shot)
            slot = self._slots.get(key, _default_slot())
            public = {k: copy.deepcopy(v) for k, v in slot.items()
                      if k not in ("path", "source_role", "stamp", "original_stamp", "edited_result",
                                   "edited_categories", "field_overrides", "prompt_applied")}
            if role == "before":
                public["fields"] = _prompt_result_fields(slot)
            source = copy.deepcopy(self._selected_source) if self._sources_key == self._active else {}
            legacy_frames = source.pop("legacy_frame_ranges", [])
            if slot["kind"] == "video" and not public["frame_ranges"]:
                public["frame_ranges"] = legacy_frames
            if slot["kind"] == "audio" and not public["time_ranges"] and (slot["start"] is not None or slot["end"] is not None):
                start = slot["start"] or 0
                end = slot["end"] if slot["end"] is not None else _seconds(source.get("duration_seconds"))
                if end is not None and 0 < end - start <= 30:
                    public["time_ranges"] = [{"start": start, "end": end}]
            jobs = self._job[0] if self._job is not None else ""
            applied_field = "prompt_applied" if role == "before" else "applied"
            rows = [{**row, "busy": _scope(channel, row["shot_uuid"]) == jobs,
                     "applied": bool(self._slots.get(_scope(channel, row["shot_uuid"]), {}).get(applied_field))}
                    for row in self._catalog.get("shots", [])]
            state = {"schema": _SCHEMA, "version": 1, "role": role, "active": list(self._active),
                     "slots": copy.deepcopy(self._slots)}
            widget = {"revision": self._revision, "ack": self._ack,
                "role": role, "available_roles": available_roles, "role_conflict": role_conflict,
                "channel_uuid": channel if rows else "", "shot_uuid": shot if rows else "",
                "shots": rows, "slot": public, "result_text": _result_editor_text(slot),
                "sources": copy.deepcopy(self._sources) if self._sources_key == self._active else [],
                "source": source,
                "default_model": self._default_model,
                "categories": ANALYSIS_CATEGORIES.get(slot["kind"], ()),
                "busy": jobs == key and bool(key), "running": bool(jobs),
                "status": self._status or ("사용 위치가 중복되었습니다. 사용 가능한 위치를 선택하세요." if role_conflict
                    else "Prompt의 샷을 연결하세요." if not rows else ""),
                "error": self._error}
            # Transient public pages, never saved/routed as analysis authority.
            # Inactive text is already in memory; do not probe files or compile
            # execution documents just to display another tab.
            cached = getattr(self, "_display_pages", {})
            cache_key = (channel, shot, role)
            cached[cache_key] = {name: copy.deepcopy(widget[name]) for name in
                ("slot", "result_text", "source", "sources", "default_model", "categories", "busy")}
            pages = {}
            live_keys = set()
            for row in rows:
                row_id = row["shot_uuid"]
                identity = (channel, row_id, role)
                live_keys.add(identity)
                saved = self._slots.get(_scope(channel, row_id), _default_slot())
                shown = {k: copy.deepcopy(v) for k, v in saved.items()
                    if k not in ("path", "source_role", "stamp", "original_stamp", "edited_result",
                                 "edited_categories", "field_overrides", "prompt_applied")}
                if role == "before":
                    shown["fields"] = _prompt_result_fields(saved)
                page = copy.deepcopy(cached.get(identity, {}))
                if page.get("slot", {}).get("source_id") != shown["source_id"]:
                    page = {}
                page.update(slot=shown, result_text=_result_editor_text(saved),
                            categories=ANALYSIS_CATEGORIES.get(saved["kind"], ()), busy=row["busy"])
                pages[row_id] = page
            self._display_pages = {identity: value for identity, value in cached.items() if identity in live_keys}
            widget["display_pages"] = pages
            self._syncing = True
            try:
                _set_parameter_silently(self, STATE, state)
                _set_parameter_silently(self, UI, widget)
                publish = getattr(self, "publish_update_to_parameter", None)
                if callable(publish):
                    publish(UI, widget)
            finally:
                self._syncing = False

    def set_parameter_value(self, name: str, value: Any, *args: Any, **kwargs: Any) -> Any:
        if name == UI and isinstance(value, dict) and isinstance(value.get(_COMMAND), dict):
            kwargs["emit_change"] = False
        if name == STATE and kwargs.get("initial_setup") is True and hasattr(self, "_lock") and not self._syncing:
            with _ROLE_LOCK, self._lock:
                if isinstance(value, dict) and value.get("schema") == _SCHEMA and type(value.get("version")) is int and value["version"] == 1:
                    self._role = value["role"] if value.get("role") in _ROLES else "after"
                    active, supplied = value.get("active"), value.get("slots")
                    if isinstance(active, list) and len(active) == 2:
                        self._active = tuple(_text(part, 128) for part in active)
                    if isinstance(supplied, dict):
                        self._slots = {key: _normalize_slot(slot) for key, slot in list(supplied.items())[:32]
                            if isinstance(key, str) and len(key) <= 257 and key.count("\x1f") == 1}
        return super().set_parameter_value(name, value, *args, **kwargs)

    def _hmb_post_registration_shot_discovery(self) -> None:
        self._refresh_sources()
        self._publish()
        if _analysis_role(self) == "after":
            for owner, catalog in self._registered_catalogs():
                for shot in catalog["shots"]:
                    _notify_prompt_media_changed(owner, catalog["channel_uuid"], shot["shot_uuid"])
        _, nodes = _same_flow_nodes(self)
        for node in _live_analysis_nodes(nodes):
            if node is not self:
                node._hmb_schedule_analysis_refresh(preserve_results=True)

    def _hmb_schedule_analysis_refresh(self, *, preserve_results: bool = False) -> bool:
        try:
            from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

            loop = GriptapeNodes.EventManager().event_loop
            if loop is None or loop.is_closed():
                return False
        except (ImportError, AttributeError, RuntimeError):
            return False
        with self._lock:
            if self._hmb_node_deleted:
                return False
            self._refresh_preserve_results = self._refresh_preserve_results or preserve_results
            if self._refresh_queued:
                return True
            self._refresh_queued = True

        def refresh() -> None:
            with self._lock:
                self._refresh_queued = False
                keep_results = self._refresh_preserve_results
                self._refresh_preserve_results = False
                if self._hmb_node_deleted:
                    return
            self._refresh_sources(preserve_results=keep_results)
            self._publish()

        try:
            loop.call_soon_threadsafe(refresh)
        except RuntimeError:
            with self._lock:
                self._refresh_queued = False
                self._refresh_preserve_results = False
            return False
        return True

    def after_deserialize(self, *args: Any, **kwargs: Any) -> Any:
        result = getattr(super(), "after_deserialize", lambda *_a, **_k: None)(*args, **kwargs)
        schedule_post_registration_reconcile(self)
        return result

    def after_node_deleted(self, *args: Any, **kwargs: Any) -> Any:
        _, nodes = _same_flow_nodes(self)
        catalogs = self._registered_catalogs() if _analysis_role(self) == "after" else []
        with self._lock:
            self._hmb_node_deleted = True
            if self._job is not None:
                self._job[1].set()
        for node in _live_analysis_nodes(nodes):
            node._hmb_schedule_analysis_refresh(preserve_results=True)
        for owner, catalog in catalogs:
            for shot in catalog["shots"]:
                _notify_prompt_media_changed(owner, catalog["channel_uuid"], shot["shot_uuid"])
        release_node_lifecycle(self)
        return getattr(super(), "after_node_deleted", lambda *_a, **_k: None)(*args, **kwargs)

    def _select_source(self, channel: str, shot: str, slot: dict, *, publish: bool = True) -> None:
        key = _scope(channel, shot)
        with self._lock:
            if self._job is not None and self._job[0] == key:
                raise _AnalysisStateError("이 샷의 분석이 완료된 뒤 소스를 바꾸세요.")
            if key not in self._slots and len(self._slots) >= 32:
                raise _AnalysisStateError("분석 작업의 샷 저장 공간이 가득 찼습니다.")
            current = self._slots.get(key, {})
            slot["results_only"] = current.get("results_only", False)
            slot["source_role"] = _analysis_role(self) or "after"
            for field in ("origin", "kind", "source_id", "source_role", "path", "start", "end", "frame_ranges",
                          "time_ranges", "full_video", "model", "guidance"):
                if current.get(field) != slot[field]:
                    self._slots[key] = slot
                    break
            self._active = (channel, shot)
            self._status, self._error = "참고 소스 선택 완료", ""
            self._revision += 1
        self._refresh_sources()
        if publish:
            self._publish()
        if _analysis_role(self) == "after" and (current.get("origin") == "direct" or slot["origin"] == "direct"):
            owner = self._exact_owner(self._registered_catalogs(), channel, shot)
            _notify_prompt_media_changed(owner, channel, shot)

    def _hmb_pick_prompt_reference(self, prompt_owner: Any, *, channel_uuid: str, shot_uuid: str,
            kind: str, source_id: str, guidance: str = "", publish: bool = True) -> bool:
        owner = self._exact_owner(self._registered_catalogs(), channel_uuid, shot_uuid)
        if owner is None or owner is not prompt_owner or kind not in _KINDS:
            return False
        slot = {**_default_slot(), "origin": "prompt", "kind": kind, "full_video": kind == "video",
                "source_id": _text(source_id, 512), "guidance": _text(guidance, 500)}
        source = self._resolve_source(owner, channel_uuid, shot_uuid, slot)
        if not source or not _source_stamp(source):
            return False
        with self._lock:
            current = copy.deepcopy(self._slots.get(_scope(channel_uuid, shot_uuid), {}))
        if current.get("origin") == "prompt" and current.get("source_id") == slot["source_id"] and current.get("kind") == kind:
            explicit_guidance = slot["guidance"]
            slot = current
            if explicit_guidance and explicit_guidance != current["guidance"]:
                slot.update(guidance=explicit_guidance, result={}, stamp=[], categories=[],
                            edited_result="", edited_categories=[], field_overrides={}, prompt_applied=False,
                            applied=slot["send_original"])
        elif kind != "image":
            slot.update(start=_seconds(source.get("start_seconds")), end=_seconds(source.get("end_seconds")))
        try:
            self._select_source(channel_uuid, shot_uuid, slot, publish=publish)
        except _AnalysisStateError:
            return False
        return True

    def _verified_delivery(self, prompt_owner: Any, channel_uuid: str, shot_uuid: str, route: str) -> tuple[dict, dict]:
        role = "before" if route == "prompt_fields" else "after"
        key = _scope(channel_uuid, shot_uuid)
        with self._lock:
            slot = copy.deepcopy(self._slots.get(key, {}))
        ready = bool(slot.get("result")) if role == "before" else slot.get("applied") and slot.get(route)
        if self._hmb_node_deleted or _analysis_role(self) != role or not ready:
            return {}, {}
        stamp_key = "original_stamp" if route == "send_original" else "stamp"
        if not slot.get(stamp_key):
            return {}, {}
        owner = self._exact_owner(self._registered_catalogs(), channel_uuid, shot_uuid)
        if owner is None or owner is not prompt_owner:
            return {}, {}
        source = self._resolve_source(owner, channel_uuid, shot_uuid, slot)
        stamp = _source_stamp(source)
        with self._lock:
            if (self._hmb_node_deleted or _analysis_role(self) != role
                    or self._slots.get(key) != slot or stamp != slot[stamp_key]):
                return {}, {}
        return slot, source

    def _apply_prompt_fields(self, owner: Any, channel: str, shot: str) -> bool:
        slot, _ = self._verified_delivery(owner, channel, shot, "prompt_fields")
        apply = getattr(owner, "_hmb_apply_analysis_fields", None)
        accepted = False
        try:
            accepted = bool(slot and callable(apply) and apply(channel, shot, _prompt_result_fields(slot)) is True)
        except (RuntimeError, ValueError):
            _LOG.exception("Unable to apply reference analysis to Prompt Shot")
        with self._lock:
            current = self._slots.get(_scope(channel, shot))
            if current == slot:
                current["prompt_applied"] = accepted
            self._status = ("선택한 샷의 Prompt 필드에 분석 결과 반영 완료" if accepted
                            else "분석 결과를 보존했습니다. Prompt 샷 연결과 잠금을 확인하세요.")
        return accepted

    def _hmb_analysis_original_for(self, prompt_owner: Any, *, channel_uuid: str, shot_uuid: str) -> dict:
        slot, source = self._verified_delivery(prompt_owner, channel_uuid, shot_uuid, "send_original")
        if not source:
            return {}
        kind = source["kind"]
        original = {"kind": kind, "path": source["path"], "source_id": source["source_id"],
                    "start": slot["start"], "end": slot["end"]}
        reference = _text(source.get("shot_reference"), 24)
        if kind in ("image", "video") and re.fullmatch(r"@" + kind + r"[1-9][0-9]{0,2}", reference):
            original["shot_reference"] = reference
        return original

    def _hmb_analysis_originals_for(self, prompt_owner: Any, *, channel_uuid: str, shot_uuid: str,
                                    preview: bool = False) -> list[dict]:
        from _hmb_connection_management import relationship_suspended

        if _analysis_role(self) != "after" or relationship_suspended(prompt_owner, self):
            return []
        key = _scope(channel_uuid, shot_uuid)
        with self._lock:
            slot = copy.deepcopy(self._slots.get(key, _default_slot()))
        if slot["results_only"] or self._hmb_node_deleted:
            return []
        owner = prompt_owner if preview else self._exact_owner(self._registered_catalogs(), channel_uuid, shot_uuid)
        if owner is not prompt_owner:
            return []
        originals = _prompt_analysis_originals(owner, channel_uuid, shot_uuid, preview=preview)
        if slot["origin"] == "direct":
            direct = ({"path": slot["path"], "kind": slot["kind"], "source_id": slot["source_id"]}
                      if preview else self._resolve_source(owner, channel_uuid, shot_uuid, slot))
            if direct:
                originals.append({**direct, "start_seconds": slot["start"], "end_seconds": slot["end"]})
        with self._lock:
            current = self._slots.get(key, _default_slot())
            if (self._hmb_node_deleted or _analysis_role(self) != "after" or current["results_only"]
                    or any(current[field] != slot[field] for field in ("origin", "path", "kind", "start", "end"))):
                return []
        return _reference_tokens(originals)

    def _hmb_analysis_context_for(self, prompt_owner: Any, *, channel_uuid: str, shot_uuid: str,
            destination: str) -> dict:
        if destination != "agent":
            return {}
        slot, source = self._verified_delivery(prompt_owner, channel_uuid, shot_uuid, "send_agent")
        if not slot:
            return {}
        result = slot["result"]
        items = _selected_result_items(slot)
        if not items:
            return {}
        context = {"schema": "hmb-reference-analysis-context", "version": 1, "channel_uuid": channel_uuid,
            "shot_uuid": shot_uuid, "source_kind": slot["kind"], "items": items,
            "source_id": source["source_id"], "source_origin": slot["origin"],
            "analysis_status": "completed", "original_requested": not slot["results_only"],
            "cache_key": result["cache_key"], "range": result["range"]}
        # Resolve the current token again, since Picker order can change after
        # analysis. The source ID and freshness check above retain its identity.
        if reference := source.get("shot_reference"):
            context["source_reference"] = reference
        for field in ("frame_ranges", "time_ranges"):
            if field in result:
                context[field] = result[field]
        if edited := _edited_result(slot):
            context.update(items=[], edited_result=edited)
        return context

    def _start_analysis(self, owner: Any, channel: str, shot: str, slot: dict, source: dict, command: dict) -> None:
        if command.get("confirmed_paid") is not True:
            raise _AnalysisStateError("유료 분석 실행을 확인하세요.")
        stamp = _source_stamp(source)
        if not stamp:
            raise _AnalysisStateError("참고 소스를 읽을 수 없습니다.")
        model = slot["model"]
        model_config = None
        model_digest = ""
        if not model:
            from HMBAgentLibrary import get_same_shot_analysis_model
            from _hmb_reference_analysis import analysis_model_settings_digest

            model_config = get_same_shot_analysis_model(owner, channel_uuid=channel, shot_uuid=shot, kind=slot["kind"])
            model = model_config.model
            model_digest = analysis_model_settings_digest(model_config)
        cached = slot["result"]
        if (cached and slot["stamp"] == stamp and cached["model"] == model
                and cached.get("model_settings_sha256", "") == model_digest):
            if _analysis_role(self) == "before":
                self._apply_prompt_fields(owner, channel, shot)
            else:
                with self._lock:
                    self._status = "저장된 분석 결과 재사용"
            return
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
        from _hmb_reference_analysis import analyze_reference

        loop = GriptapeNodes.EventManager().event_loop
        if loop is None or loop.is_closed() or not loop.is_running():
            raise _AnalysisStateError("엔진이 시작된 뒤 분석을 실행하세요.")
        key = _scope(channel, shot)
        token = threading.Event()
        with self._lock:
            if self._slots.get(key) != slot:
                raise _AnalysisStateError("샷이나 소스가 변경되었습니다. 분석 상태를 다시 확인하세요.")
            if self._job is not None:
                raise _AnalysisStateError("실행 중인 분석이 완료된 뒤 다시 시도하세요.")
            self._job = key, token
            self._status, self._error = "참고 소스 분석 중…", ""

        async def run() -> None:
            try:
                if slot["full_video"]:
                    range_arguments = {"start": _seconds(source.get("start_seconds")),
                                       "end": _seconds(source.get("end_seconds"))}
                elif slot["frame_ranges"]:
                    range_arguments = {"frame_ranges": slot["frame_ranges"]}
                elif slot["time_ranges"]:
                    range_arguments = {"time_ranges": slot["time_ranges"]}
                else:
                    range_arguments = {"start": slot["start"], "end": slot["end"]}
                result = await asyncio.to_thread(analyze_reference, self, source=source["path"],
                    kind=slot["kind"], **range_arguments,
                    model=model, model_config=model_config, guidance=slot["guidance"], is_live=lambda: not token.is_set(),
                    analysis_context={"channel_uuid": channel, "shot_uuid": shot})
                result = _result(result, slot["kind"])
                if not result:
                    raise _AnalysisStateError("검토할 수 있는 분석 결과를 받지 못했습니다.")
                owner = self._exact_owner(self._registered_catalogs(), channel, shot)
                fresh = self._resolve_source(owner, channel, shot, slot) if owner is not None else {}
                if not fresh or _source_stamp(fresh) != stamp:
                    raise _AnalysisStateError("분석 중 참고 소스가 바뀌었습니다.")
                committed = False
                with self._lock:
                    if not token.is_set() and self._slots.get(key) == slot:
                        previous_edit = ({name: slot[name] for name in ("categories", "edited_result", "edited_categories", "field_overrides")}
                                         if slot["result"].get("cache_key") == result["cache_key"]
                                         else {"categories": [], "edited_result": "", "edited_categories": [], "field_overrides": {}})
                        self._slots[key] = {**slot, "result": result, "stamp": stamp,
                            **previous_edit,
                            "prompt_applied": False, "applied": slot["send_original"] or slot["send_agent"]}
                        committed = True
                        self._status = "저장된 분석 결과 재사용" if result["cache_hit"] else "분석 완료"
                if committed and _analysis_role(self) == "before" and not token.is_set():
                    self._apply_prompt_fields(owner, channel, shot)
            except (AnalysisError, _AnalysisStateError) as exc:
                with self._lock:
                    if not token.is_set():
                        self._error, self._status = getattr(exc, "code", "ANALYSIS_SOURCE_CHANGED"), str(exc)
            except Exception:
                _LOG.exception("Reference analysis failed")
                with self._lock:
                    if not token.is_set():
                        self._error, self._status = "ANALYSIS_FAILED", "참고 소스 분석을 완료하지 못했습니다."
            finally:
                with self._lock:
                    if self._job == (key, token):
                        self._job = None
                        self._revision += 1
                        if token.is_set():
                            self._status = "분석 취소"
                self._publish()

        coroutine = run()
        try:
            asyncio.run_coroutine_threadsafe(coroutine, loop)
        except RuntimeError:
            coroutine.close()
            with self._lock:
                self._job = None
            raise _AnalysisStateError("엔진에 분석 요청을 전달할 수 없습니다.") from None

    def _run_command(self, command: dict) -> None:
        action = command.get("action")
        if action == "refresh":
            self._hmb_post_registration_shot_discovery()
            return
        if action == "set_role":
            self._set_role(command)
            return
        channel, shot = _text(command.get("channel_uuid"), 128), _text(command.get("shot_uuid"), 128)
        key = _scope(channel, shot)
        owner = self._exact_owner(self._registered_catalogs(), channel, shot)
        if owner is None:
            raise _AnalysisStateError("현재 샷의 Prompt 리모트 연결을 확인하세요.")
        with self._lock:
            if action == "select_shot":
                self._active = (channel, shot)
            elif self._active != (channel, shot):
                raise _AnalysisStateError("선택된 샷을 다시 확인하세요.")
            elif action == "cancel":
                if self._job is not None and self._job[0] == key:
                    self._job[1].set()
                return
            elif self._job is not None and self._job[0] == key:
                raise _AnalysisStateError("이 샷의 분석이 진행 중입니다.")
            elif type(command.get("revision")) is not int or command["revision"] != self._revision:
                raise _AnalysisStateError("샷이나 소스가 변경되었습니다. 분석 상태를 다시 확인하세요.")
            slot = copy.deepcopy(self._slots.get(key, _default_slot()))
        if action == "select_shot":
            self._refresh_sources(page_only=True)
            return
        if action == "select_source":
            if not self._hmb_pick_prompt_reference(owner, channel_uuid=channel, shot_uuid=shot,
                    kind=command.get("kind"), source_id=command.get("source_id"), publish=False):
                raise _AnalysisStateError("현재 샷의 참고 소스를 선택하세요.")
            return
        if action == "clear":
            with self._lock:
                if slot["results_only"]:
                    self._slots[key] = {**_default_slot(), "results_only": True}
                else:
                    self._slots.pop(key, None)
            self._refresh_sources()
            self._status = "참고 소스 선택 해제"
            if _analysis_role(self) == "after" and slot["origin"] == "direct":
                _notify_prompt_media_changed(owner, channel, shot)
            return
        route_only = (action == "delivery" and "results_only" in command and "result_text" not in command
                      and command.get("categories", slot["categories"]) == slot["categories"])
        source = self._resolve_source(owner, channel, shot, slot) if action != "unapply" and not route_only else {}
        if not source and action != "unapply" and not (action == "delivery" and "results_only" in command):
            raise _AnalysisStateError("현재 샷의 참고 소스를 선택하세요.")
        if _analysis_role(self) == "before" and action in ("delivery", "set_field"):
            if not slot["result"] or _source_stamp(source) != slot["stamp"]:
                raise _AnalysisStateError("현재 샷의 참고 소스를 분석한 뒤 결과를 수정하세요.")
            updated = {**slot, "prompt_applied": False}
            if action == "set_field":
                field, value = command.get("field"), command.get("text")
                limit = _FIELD_LIMITS.get(field) if isinstance(field, str) else None
                if limit is None or not isinstance(value, str) or len(value) > limit:
                    raise _AnalysisStateError("수정할 Prompt 항목과 입력 길이를 확인하세요.")
                updated["field_overrides"] = {**slot["field_overrides"], field: value}
            else:
                updated["categories"] = _selected_categories(slot, command)
            with self._lock:
                if self._slots.get(key) != slot or _analysis_role(self) != "before":
                    raise _AnalysisStateError("샷이나 소스가 변경되었습니다. 분석 상태를 다시 확인하세요.")
                self._slots[key] = updated
            self._apply_prompt_fields(owner, channel, shot)
            return
        if action in ("configure", "analyze"):
            if action == "analyze" and command.get("confirmed_paid") is not True:
                raise _AnalysisStateError("유료 분석 실행을 확인하세요.")
            source_start, source_end = _seconds(source.get("start_seconds")), _seconds(source.get("end_seconds"))
            range_fields = [field for field in ("frame_ranges", "time_ranges") if field in command]
            if "full_video" in command:
                from _hmb_reference_analysis import normalize_analysis_ranges

                full_video = command["full_video"]
                if (slot["kind"] != "video" or type(full_video) is not bool or "time_ranges" in command
                        or "start" in command or "end" in command):
                    raise _AnalysisStateError("영상에 맞는 분석 구간을 선택하세요.")
                selection = {"full_video": full_video}
                ranges = slot["frame_ranges"]
                if "frame_ranges" in command:
                    supplied = command["frame_ranges"]
                    ranges = [] if isinstance(supplied, list) and not supplied else normalize_analysis_ranges(supplied, kind="video")
                    selection["frame_ranges"] = ranges
                    if not ranges:
                        selection.update(start=None, end=None)
                if not full_video and not ranges:
                    raise _AnalysisStateError("분석할 영상 프레임 구간을 선택하세요.")
            elif range_fields:
                from _hmb_reference_analysis import normalize_analysis_ranges

                expected = {"video": "frame_ranges", "audio": "time_ranges"}.get(slot["kind"])
                if range_fields != [expected]:
                    raise _AnalysisStateError("미디어에 맞는 분석 구간을 선택하세요.")
                ranges = normalize_analysis_ranges(command[expected], kind=slot["kind"])
                if expected == "time_ranges" and any(
                    (source_start is not None and row["start"] < source_start)
                    or (source_end is not None and row["end"] > source_end) for row in ranges
                ):
                    raise _AnalysisStateError("Prompt에 지정된 소스 구간 안에서 분석 시간을 선택하세요.")
                selection = {expected: ranges}
                if slot["kind"] == "video":
                    selection["full_video"] = False
            else:
                start, end = _seconds(command.get("start")), _seconds(command.get("end"))
                if any(command.get(part) is not None and value is None for part, value in (("start", start), ("end", end))):
                    raise _AnalysisStateError("분석 구간을 초 단위로 입력하세요.")
                if end is not None and (start or 0) >= end:
                    raise _AnalysisStateError("끝 시간이 시작 시간보다 뒤에 있어야 합니다.")
                if slot["kind"] == "image" and (start is not None or end is not None):
                    raise _AnalysisStateError("이미지에는 분석 구간을 입력할 수 없습니다.")
                if slot["kind"] != "image" and (
                    (source_start is not None and (start or 0) < source_start)
                    or (source_end is not None and (end is None or end > source_end))
                ):
                    raise _AnalysisStateError("Prompt에 지정된 소스 구간 안에서 분석 시간을 선택하세요.")
                selection = {"start": start, "end": end, "frame_ranges": [], "time_ranges": []}
                if slot["kind"] == "video":
                    selection["full_video"] = start is None and end is None
            model = _text(command.get("model"), 128)
            if model and model not in analysis_model_choices(slot["kind"]):
                raise _AnalysisStateError("이 미디어에서 사용할 수 있는 모델을 선택하세요.")
            updated = {**slot, **selection, "model": model,
                       "guidance": _text(command.get("guidance"), 500)}
            if updated != slot:
                updated.update(result={}, stamp=[], categories=[], edited_result="", edited_categories=[],
                               field_overrides={}, prompt_applied=False, applied=slot["send_original"])
                self._select_source(channel, shot, updated, publish=False)
            if action == "analyze":
                self._start_analysis(owner, channel, shot, updated, source, command)
            return
        if action in ("delivery", "apply", "unapply"):
            new_delivery = action == "delivery" and "results_only" in command
            results_only = command.get("results_only", slot["results_only"])
            if type(results_only) is not bool:
                raise _AnalysisStateError("원본 전달 설정을 다시 확인하세요.")
            send_agent = new_delivery or (action != "unapply" and command.get("send_agent", slot["send_agent"]) is True)
            original = (not new_delivery and action != "unapply"
                        and command.get("send_original", slot["send_original"]) is True)
            observations = slot["result"].get("observations", {})
            selected = _selected_categories(slot, command)
            editing = "result_text" in command
            stamp = _source_stamp(source) if not route_only and (observations or original) else []
            if (original and not stamp) or (not route_only and observations and stamp != slot["stamp"] and (send_agent or editing)):
                raise _AnalysisStateError("현재 샷의 참고 소스를 확인하세요.")
            updated = {**slot, "categories": selected, "applied": original or (send_agent and bool(observations)),
                       "results_only": results_only, "send_agent": send_agent, "send_original": original,
                       "original_stamp": stamp if original else []}
            if editing:
                edited = command["result_text"]
                if not observations or not isinstance(edited, str) or len(edited) > ANALYSIS_RESULT_TEXT_LIMIT:
                    raise _AnalysisStateError("현재 분석 결과를 26,000자 이내로 입력하세요.")
                edit_scope = command.get("result_text_categories", selected)
                if (not isinstance(edit_scope, list)
                        or any(not isinstance(key, str) or key not in observations for key in edit_scope)):
                    raise _AnalysisStateError("수정할 결과의 분석 항목을 다시 확인하세요.")
                updated.update(edited_result=edited.strip(),
                               edited_categories=[key for key in observations if key in edit_scope])
            with self._lock:
                if self._slots.get(key, _default_slot()) != slot:
                    raise _AnalysisStateError("샷이나 소스가 변경되었습니다. 분석 상태를 다시 확인하세요.")
                if key not in self._slots and len(self._slots) >= 32:
                    raise _AnalysisStateError("분석 작업의 샷 저장 공간이 가득 찼습니다.")
                self._slots[key] = updated
                self._status = "분석 결과 수정 저장" if editing else "이 샷의 전달 설정 저장"
            if results_only != slot["results_only"]:
                _notify_prompt_media_changed(owner, channel, shot)
            return
        raise _AnalysisStateError("분석 명령을 확인하세요.")

    def after_value_set(self, parameter: Any, value: Any) -> Any:
        result = getattr(super(), "after_value_set", lambda *_: None)(parameter, value)
        if self._syncing or self._hmb_node_deleted:
            return result
        name = getattr(parameter, "name", parameter)
        if name == FILE and isinstance(value, str) and value:
            try:
                path, kind = _local_file(value)
                self._refresh_sources()
                with self._lock:
                    channel, shot = self._active
                    if not self._catalog or not _scope(channel, shot):
                        raise _AnalysisStateError("Prompt 샷을 먼저 선택한 다음 직접 분석할 파일을 고르세요.")
                slot = {**_default_slot(), "origin": "direct", "kind": kind, "source_id": "direct",
                        "full_video": kind == "video",
                        "path": str(path)}
                self._select_source(channel, shot, slot)
            except _AnalysisStateError as exc:
                with self._lock:
                    self._error, self._status = "ANALYSIS_FILE_INVALID", str(exc)
            finally:
                _set_parameter_silently(self, FILE, "")
                publish = getattr(self, "publish_update_to_parameter", None)
                if callable(publish):
                    publish(FILE, "")
                self._publish()
            return result
        if name != UI or not isinstance(value, dict):
            return result
        command = value.get(_COMMAND)
        if isinstance(command, dict) and (request := _text(command.get("id"), 128)):
            with self._lock:
                if request in self._recent:
                    return result
                self._recent = [*self._recent[-31:], request]
                self._ack = request
                self._error = ""
                self._status = ""
            try:
                self._run_command(command)
            except AnalysisError as exc:
                with self._lock:
                    self._error, self._status = exc.code, str(exc)
            except _AnalysisStateError as exc:
                with self._lock:
                    self._error, self._status = "ANALYSIS_REQUEST_INVALID", str(exc)
            except Exception:
                _LOG.exception("Reference analysis control failed")
                with self._lock:
                    self._error, self._status = "ANALYSIS_REQUEST_FAILED", "분석 요청을 처리하지 못했습니다."
            with self._lock:
                self._revision += 1
        self._publish()
        return result

    def process(self) -> None:
        self._refresh_sources()
        self._publish()
