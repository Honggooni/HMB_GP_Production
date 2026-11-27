"""Shared native controls and Shot selector contracts used by independent HMB nodes."""
from __future__ import annotations

import copy
import hashlib
import hmac
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping

_THIS_DIR = Path(__file__).resolve().parent


def _load_hmb_common() -> Any:
    module_path = _THIS_DIR / "_hmb_common.py"
    module_name = "_hmb_gp_production_common"
    existing = sys.modules.get(module_name)
    if existing is not None and Path(getattr(existing, "__file__", "")).resolve() == module_path.resolve():
        return existing
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load HMB common module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_hmb = _load_hmb_common()
DataNode = _hmb.DataNode
Parameter = _hmb.Parameter
ParameterMode = _hmb.ParameterMode
add_group = _hmb.add_group
set_output = _hmb.set_output
parameter_exists = _hmb.parameter_exists

try:
    from griptape_nodes.traits.widget import Widget  # type: ignore
except Exception:
    Widget = None  # type: ignore


try:
    from griptape_nodes.traits.file_system_picker import FileSystemPicker  # type: ignore
except Exception:
    FileSystemPicker = None  # type: ignore

try:
    from griptape_nodes.exe_types.param_types.parameter_string import (  # type: ignore
        ParameterString,
    )
except Exception:
    ParameterString = None  # type: ignore


WIDGET_LIBRARY_NAME = "HMB_GP_Production"
SHOT_ROUTING_CATALOG_SCHEMA = "hmb-shot-routing-catalog"
SHOT_ROUTING_CATALOG_VERSION = 1
MAX_SHOTS = 5


class FinishLookValidationError(ValueError):
    """A state or remote request violates the public Finish Look contract."""


def _shot_only() -> dict[str, Any]:
    return {
        "channel_uuid": "",
        "shot_uuid": "",
        "number": 1,
        "name": "Only",
    }


def _normalize_shot_catalog(
    value: Any,
    *,
    strict: bool = False,
    allow_sparse: bool = False,
) -> dict[str, Any]:
    """Normalize the compact ImageAsset-owned Shot catalog.

    Selector state contains no media. The catalog is
    only a bounded UUID/name option list supplied by the same-flow router.
    """

    if not value:
        return {}
    if not isinstance(value, Mapping):
        if strict:
            raise FinishLookValidationError("Shot catalog must be an object.")
        return {}
    required = {
        "schema",
        "version",
        "publisher_instance_uuid",
        "channel_uuid",
        "generation",
        "metadata_sha256",
        "shots",
    }
    if set(value) != required:
        if strict:
            raise FinishLookValidationError("Shot catalog shape is invalid.")
        return {}
    publisher = str(value.get("publisher_instance_uuid") or "")
    channel = str(value.get("channel_uuid") or "")
    metadata_sha256 = str(value.get("metadata_sha256") or "").casefold()
    generation = value.get("generation")
    shots_value = value.get("shots")
    if (
        value.get("schema") != SHOT_ROUTING_CATALOG_SCHEMA
        or value.get("version") != SHOT_ROUTING_CATALOG_VERSION
        or not publisher
        or publisher != publisher.strip()
        or len(publisher) > 128
        or not channel
        or channel != channel.strip()
        or len(channel) > 128
        or isinstance(generation, bool)
        or not isinstance(generation, int)
        or not 1 <= generation <= (1 << 53) - 1
        or re.fullmatch(r"[0-9a-f]{64}", metadata_sha256) is None
        or not isinstance(shots_value, list)
        or not 1 <= len(shots_value) <= MAX_SHOTS
    ):
        if strict:
            raise FinishLookValidationError("Shot catalog metadata is invalid.")
        return {}
    shots: list[dict[str, Any]] = []
    shot_ids: set[str] = set()
    shot_numbers: set[int] = set()
    for raw in shots_value:
        if not isinstance(raw, Mapping) or set(raw) != {
            "shot_uuid",
            "number",
            "name",
            "revision",
        }:
            if strict:
                raise FinishLookValidationError("Shot catalog row is invalid.")
            return {}
        shot_uuid = str(raw.get("shot_uuid") or "")
        name = " ".join(str(raw.get("name") or "").split())
        number = raw.get("number")
        revision = raw.get("revision")
        if (
            not shot_uuid
            or shot_uuid != shot_uuid.strip()
            or len(shot_uuid) > 128
            or shot_uuid in shot_ids
            or isinstance(number, bool)
            or not isinstance(number, int)
            or not 1 <= number <= MAX_SHOTS
            or number in shot_numbers
            or not name
            or len(name) > 128
            or isinstance(revision, bool)
            or not isinstance(revision, int)
            or not 0 <= revision <= (1 << 53) - 1
        ):
            if strict:
                raise FinishLookValidationError("Shot catalog row value is invalid.")
            return {}
        shot_ids.add(shot_uuid)
        shot_numbers.add(number)
        shots.append(
            {
                "shot_uuid": shot_uuid,
                "number": number,
                "name": name,
                "revision": revision,
            }
        )
    shots.sort(key=lambda item: (item["number"], item["shot_uuid"]))
    if (
        not allow_sparse
        and [item["number"] for item in shots] != list(range(1, len(shots) + 1))
    ):
        if strict:
            raise FinishLookValidationError("Shot catalog numbering is invalid.")
        return {}
    document = {
        "channel_uuid": channel,
        "generation": generation,
        "shots": shots,
    }
    expected_sha256 = hashlib.sha256(
        json.dumps(
            document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    if not hmac.compare_digest(metadata_sha256, expected_sha256):
        if strict:
            raise FinishLookValidationError("Shot catalog hash does not match.")
        return {}
    return {
        "schema": SHOT_ROUTING_CATALOG_SCHEMA,
        "version": SHOT_ROUTING_CATALOG_VERSION,
        "publisher_instance_uuid": publisher,
        "channel_uuid": channel,
        "generation": generation,
        "metadata_sha256": metadata_sha256,
        "shots": shots,
    }


def _normalize_shot_selection(value: Any, catalog: Any = None) -> dict[str, Any]:
    source = value if isinstance(value, Mapping) else {}
    channel = str(source.get("channel_uuid") or "").strip()[:128]
    shot_uuid = str(source.get("shot_uuid") or "").strip()[:128]
    if not channel or not shot_uuid:
        return _shot_only()
    normalized_catalog = _normalize_shot_catalog(catalog, allow_sparse=True)
    if normalized_catalog and normalized_catalog.get("channel_uuid") != channel:
        return _shot_only()
    selected = next(
        (
            item
            for item in normalized_catalog.get("shots", [])
            if item.get("shot_uuid") == shot_uuid
        ),
        None,
    )
    if normalized_catalog and selected is None:
        return _shot_only()
    try:
        number = max(1, min(MAX_SHOTS, int(source.get("number") or 1)))
    except (TypeError, ValueError, OverflowError):
        number = 1
    if selected is not None:
        number = int(selected["number"])
        name = str(selected["name"])
    else:
        name = " ".join(str(source.get("name") or f"Shot {number}").split())[:128]
    return {
        "channel_uuid": channel,
        "shot_uuid": shot_uuid,
        "number": number,
        "name": name or f"Shot {number}",
    }


def _mode(name: str) -> Any:
    if ParameterMode is None:
        return None
    return {getattr(ParameterMode, name)}


def _parameter_attempts(kwargs: dict[str, Any]) -> list[dict[str, Any]]:
    modern = dict(kwargs)
    if modern.get("allowed_modes") is not None:
        for key in ("allow_input", "allow_output", "allow_property"):
            modern.pop(key, None)
    legacy = dict(kwargs)
    legacy.pop("allowed_modes", None)
    attempts: list[dict[str, Any]] = []
    for candidate in (modern, legacy):
        attempts.append(candidate)
        without_type = dict(candidate)
        without_type.pop("type", None)
        if without_type != candidate:
            attempts.append(without_type)
    return attempts


def _add_parameter(node: Any, **kwargs: Any) -> Any:
    if parameter_exists(node, str(kwargs.get("name") or "")):
        return _parameter_object(node, kwargs["name"])
    last_error: Exception | None = None
    for attempt in _parameter_attempts(kwargs):
        try:
            parameter = Parameter(**attempt)
            node.add_parameter(parameter)
            return parameter
        except Exception as exc:
            last_error = exc
    raise last_error or RuntimeError(f"Unable to add parameter {kwargs.get('name')}.")


def _parameter_object(node: Any, name: str) -> Any:
    for getter_name in ("get_parameter_by_name", "get_parameter"):
        getter = getattr(node, getter_name, None)
        if callable(getter):
            try:
                parameter = getter(name)
                if parameter is not None:
                    return parameter
            except Exception:
                pass
    parameters = getattr(node, "parameters", None)
    if isinstance(parameters, dict):
        return parameters.get(name)
    if isinstance(parameters, (list, tuple)):
        return next(
            (
                parameter
                for parameter in parameters
                if getattr(parameter, "name", None) == name
            ),
            None,
        )
    return None


def _add_widget_parameter(node: Any, *, widget_name: str, **kwargs: Any) -> Any:
    """Attach the Widget trait before Griptape performs its first row layout."""

    name = str(kwargs.get("name") or "")
    if parameter_exists(node, name):
        parameter = _parameter_object(node, name)
    else:
        parameter = None
        last_error: Exception | None = None
        for attempt in _parameter_attempts(kwargs):
            if Widget is not None:
                try:
                    parameter = Parameter(
                        **{
                            **attempt,
                            "traits": {
                                Widget(name=widget_name, library=WIDGET_LIBRARY_NAME)
                            },
                        }
                    )
                    break
                except Exception as exc:
                    last_error = exc
            try:
                parameter = Parameter(**attempt)
                if Widget is not None:
                    parameter.add_trait(
                        Widget(name=widget_name, library=WIDGET_LIBRARY_NAME)
                    )
                break
            except Exception as exc:
                parameter = None
                last_error = exc
        if parameter is None:
            raise last_error or RuntimeError(f"Unable to add widget parameter {name}.")
        # Adding the trait after add_parameter() leaves the host's first layout
        # cached as a compact native dict row (about 40-48 px).
        node.add_parameter(parameter)

    if Widget is not None and parameter is not None:
        has_widget = False
        try:
            finder = getattr(parameter, "find_elements_by_type", None)
            if callable(finder):
                has_widget = bool(finder(Widget, find_recursively=True))
        except Exception:
            has_widget = False
        if not has_widget:
            try:
                parameter.add_trait(
                    Widget(name=widget_name, library=WIDGET_LIBRARY_NAME)
                )
            except Exception:
                pass
    return parameter


def _apply_parameter_ui_options(parameter: Any, options: Mapping[str, Any]) -> None:
    if parameter is None:
        return
    try:
        current = dict(getattr(parameter, "ui_options", {}) or {})
        current.update(dict(options))
        parameter.ui_options = current
    except Exception:
        return
    updater = getattr(parameter, "update_ui_options_key", None)
    if callable(updater):
        for key, value in options.items():
            try:
                updater(key, value)
            except Exception:
                pass


def _hidden_transport_ui_options() -> dict[str, Any]:
    return {
        "display_name": "",
        "hide": True,
        "hide_property": True,
        "hide_label": True,
        "hide_handles": True,
        "height": 1,
        "min_height": 0,
        "max_height": 1,
        "is_full_width": True,
        "expandable": False,
        "compact": True,
    }


def _hide_transport_parameter(parameter: Any) -> None:
    if parameter is None:
        return
    for attribute in ("hide", "hide_property", "hide_label"):
        try:
            setattr(parameter, attribute, True)
        except Exception:
            pass
    _apply_parameter_ui_options(parameter, _hidden_transport_ui_options())


def _raw_parameter(node: Any, name: str) -> Any:
    try:
        return node.get_parameter_value(name)
    except Exception:
        parameter = _parameter_object(node, name)
        return getattr(parameter, "default_value", None)


def _set_parameter_silently(node: Any, name: str, value: Any) -> None:
    parent_setter = getattr(super(type(node), node), "set_parameter_value", None)
    if callable(parent_setter):
        try:
            if ParameterMode is None:
                parent_setter(name, copy.deepcopy(value))
            else:
                parent_setter(
                    name,
                    copy.deepcopy(value),
                    initial_setup=False,
                    emit_change=False,
                    skip_before_value_set=True,
                )
            return
        except (AttributeError, TypeError):
            try:
                parent_setter(name, copy.deepcopy(value))
                return
            except Exception:
                pass
        except Exception:
            pass
    parameter = _parameter_object(node, name)
    if parameter is not None:
        try:
            parameter.default_value = copy.deepcopy(value)
        except Exception:
            pass


def add_project_folder_parameter(node: Any, name: str, default: str, tooltip: str) -> None:
    if parameter_exists(node, name):
        return
    trait = None
    if FileSystemPicker is not None:
        for trait_kwargs in (
            {
                "allow_files": False,
                "allow_directories": True,
                "multiple": False,
            },
            {"allow_directories": True},
        ):
            try:
                trait = FileSystemPicker(**trait_kwargs)
                break
            except Exception:
                continue
    if ParameterString is not None:
        parameter = ParameterString(
            name=name,
            default_value=default,
            tooltip=tooltip,
            placeholder_text=default,
        )
        if trait is not None:
            try:
                parameter.add_trait(trait)
            except Exception:
                pass
        try:
            parameter.allowed_modes = _mode("PROPERTY")
        except Exception:
            pass
        try:
            options = dict(getattr(parameter, "ui_options", {}) or {})
            options.update(
                {
                    "display_name": name,
                    "placeholder_text": default,
                    "is_full_width": True,
                }
            )
            parameter.ui_options = options
        except Exception:
            pass
        node.add_parameter(parameter)
        return
    kwargs: dict[str, Any] = {
        "name": name,
        "default_value": default,
        "type": "str",
        "tooltip": tooltip,
        "allow_input": False,
        "allow_output": False,
        "allow_property": True,
        "ui_options": {
            "display_name": name,
            "placeholder_text": default,
            "is_full_width": True,
        },
    }
    modes = _mode("PROPERTY")
    if modes is not None:
        kwargs["allowed_modes"] = modes
        kwargs["allow_input"] = False
    if trait is not None:
        kwargs["traits"] = {trait}
    _add_parameter(node, **kwargs)


def add_site_folder_parameter(node: Any) -> None:
    add_project_folder_parameter(node, "HMB_SITE_FOLDER_DRAFT", "",
                                 "Choose a shared vendor asset folder. Save in ImageAsset project settings to apply.")
