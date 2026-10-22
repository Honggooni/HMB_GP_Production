"""Personal, provider-neutral image generation through the shared HMB Broker.

No provider key, project binding, web review publication, model invocation or
network discovery happens while constructing, opening or editing this node.
"""
from __future__ import annotations

import asyncio
from contextlib import suppress
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import logging
import math
from pathlib import Path
import re
import threading
from typing import Any
from urllib.parse import urlsplit

from griptape.artifacts import ImageUrlArtifact
from griptape_nodes.exe_types.core_types import ParameterGroup, ParameterList, ParameterMode
try:
    from griptape_nodes.exe_types.core_types import NodeMessageResult
except ImportError:  # Older supported hosts predate the native button result.
    @dataclass
    class NodeMessageResult:
        success: bool
        details: str
        response: Any = None
        altered_workflow_state: bool = True
from griptape_nodes.exe_types.node_types import SuccessFailureNode
from griptape_nodes.exe_types.param_components.project_file_parameter import ProjectFileParameter
from griptape_nodes.exe_types.param_components.execution_status_component import ExecutionStatusComponent
from griptape_nodes.exe_types.param_types.parameter_button import ParameterButton
from griptape_nodes.exe_types.param_types.parameter_dict import ParameterDict
from griptape_nodes.exe_types.param_types.parameter_bool import ParameterBool
from griptape_nodes.exe_types.param_types.parameter_float import ParameterFloat
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.exe_types.param_types.parameter_image import ParameterImage
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.files.file import File
from griptape_nodes.traits.options import Options
try:
    from griptape_nodes.traits.widget import Widget
except ImportError:
    Widget = None

import _hmb_broker_config as broker_config
from _hmb_image_generation import (
    ImageGenerationBroker, ImageGenerationError, JOB_FAILURE_STATUSES,
    JOB_PENDING_STATUSES, MAX_IMAGE_BYTES, prepare_invocation, validate_image_bytes,
    BUILTIN_IMAGE_MODEL_PROFILES, CAPABILITIES_SCHEMA, model_defaults, parse_capabilities,
    serialize_option_schema, serialize_option_spec,
)

logger = logging.getLogger(__name__)
_CHECKPOINT_SCHEMA = "hmb-personal-image-checkpoint-v1"
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}\Z")
_UNFINISHED = JOB_PENDING_STATUSES | {"submitting", "submission_unknown", "interrupted"}
_PARAM_MODES = {ParameterMode.INPUT, ParameterMode.PROPERTY}
_MODEL_SETTINGS_SCHEMA = "hmb-image-model-settings-v1"
_CORE_SETTINGS = ("task", "ratio", "image_size", "output_format")
_BUILTIN_PROFILES = {item.provider + "/" + item.model_id: item for item in BUILTIN_IMAGE_MODEL_PROFILES}


class HMBImageGeneration(SuccessFailureNode):
    """One independent personal image workspace; models come from the Broker."""

    POLL_INTERVAL_SECONDS = 30
    POLL_TIMEOUT_SECONDS = 3600

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._deleted = False
        self._operation_lock = threading.Lock()
        self._busy = False
        self._scheduled = False
        self._operation_token: threading.Event | None = None
        self._button_futures: set[Any] = set()
        self._capabilities = None
        self._capability_origin = ""
        self._broker_factory = ImageGenerationBroker
        self._choices: dict[str, Options] = {}
        self._model_settings_ready = False
        self._restoring_model_settings = False
        self._selected_model = ""
        self._model_views: dict[str, dict[str, Any]] = {}
        self._cached_profiles: dict[str, Any] = {}
        self._active_option_parameters: dict[str, str] = {}
        self._option_bindings: dict[str, tuple[str, str]] = {}
        self._model_settings_error = ""
        self._model_label_keys: dict[str, str] = {}
        self._syncing_model_label = False

        header_traits = {Widget(name="HMBImageGenerationWidget", library="HMB_GP_Production")} if Widget is not None else set()
        self.add_parameter(ParameterString(name="HMB_IMAGE_GENERATION_UI", default_value="HMBImageGeneration",
            settable=False, serializable=False, allowed_modes={ParameterMode.PROPERTY},
            traits=header_traits, ui_options={"display_name": "", "hide_label": True,
                "hide_handles": True, "is_full_width": True,
                "height": 64, "min_height": 64, "max_height": 64, "widget_height": 64,
                "expandable": False, "resizable": False, "compact": True}))
        # Native Options has no separate value/label mapping. Keep the original
        # serializable model_id for saved workflows, input edges and transport;
        # this property-only view displays names without changing that identity.
        self._add_choice("image_model", "Nano Banana Pro",
            [item.display_name for item in BUILTIN_IMAGE_MODEL_PROFILES], "Image Model",
            allowed_modes={ParameterMode.PROPERTY}, serializable=False)
        self._add_choice("model_id", "google/gemini-3-pro-image", list(_BUILTIN_PROFILES), "Model ID",
            hide=True, hide_property=True)
        self._add_choice("task", "text-to-image", ["text-to-image", "image-to-image"], "Task")
        self.add_parameter(ParameterString(name="prompt", default_value="", multiline=True,
            placeholder_text="Describe the image, or the changes to your reference images...",
            allowed_modes=_PARAM_MODES, ui_options={"display_name": "Prompt"}))
        self.add_parameter(ParameterList(name="reference_images", type="ImageUrlArtifact",
            input_types=["ImageUrlArtifact", "ImageArtifact", "str"], output_type="str",
            default_value="", allowed_modes={ParameterMode.INPUT},
            tooltip="Ordered image references. Local image files and connected image artifacts are supported.",
            ui_options={"display_name": "Reference Images"}))
        self._add_choice("ratio", "1:1", list(BUILTIN_IMAGE_MODEL_PROFILES[0].aspect_ratios), "Aspect Ratio")
        self._add_choice("image_size", "1K", ["1K", "2K", "4K"], "Resolution / 해상도")
        self._add_choice("output_format", "png", ["png"], "Output Format")
        self.get_parameter_by_name("image_size").tooltip = (
            "Generated image resolution, using the selected model's supported sizes. "
            "Nano Banana Pro: 1K / 2K / 4K; Nano Banana 2 also supports 512.")
        self._generation_settings = ParameterGroup(name="Generation Settings", ui_options={"collapsed": True})
        self._generation_settings.add_child(ParameterBool(name="auto_image_resize", default_value=True,
            allowed_modes={ParameterMode.PROPERTY},
            tooltip="Reduce input references only when they exceed the model or request byte budget. "
                    "The original files and generated output resolution are unchanged.",
            ui_options={"display_name": "Auto Resize References", "hide_handles": True}))
        self.add_node_element(self._generation_settings)
        # Keep the first installed preview alias for existing saved edges, but
        # expose one canonical image preview/output in the current surface.
        self.add_parameter(ParameterImage(name="image_url", default_value=None, settable=False,
            allowed_modes={ParameterMode.PROPERTY, ParameterMode.OUTPUT},
            hide=True, hide_property=True, hide_label=True,
            ui_options={"hide": True, "hide_property": True, "hide_handles": True}))
        self.add_parameter(ParameterImage(name="IMAGE_OUT", default_value=None, settable=False,
            allowed_modes={ParameterMode.PROPERTY, ParameterMode.OUTPUT},
            ui_options={"display_name": "Image", "hide_property": False},
            tooltip="Original saved image, connectable to an Image loader or HMBImageAssetLibrary.IMAGE_IMPORT_IN."))
        self._output_file = ProjectFileParameter(node=self, name="output_file", default_filename="hmb_image.png",
            ui_options={"hide_handles": True})
        self._output_file.add_parameter()

        self.status_component = ExecutionStatusComponent(self,
            was_successful_modes={ParameterMode.PROPERTY}, result_details_modes={ParameterMode.PROPERTY},
            parameter_group_initially_collapsed=True, result_details_tooltip="Personal image task and local-save status.")
        status = self.status_component.get_parameter_group()
        status.add_child(ParameterString(name="resume_task_id", default_value="", allowed_modes={ParameterMode.PROPERTY},
            tooltip="Retrieve this existing personal image Task instead of creating another image.",
            ui_options={"display_name": "Resume Task ID", "hide_handles": True}))
        for name, label, value in (
            ("generation_id", "Task ID", ""), ("generation_status", "Image Status", "not_checked"),
            ("broker_status", "Broker", "Server image adapter / API key registration pending"),
        ):
            status.add_child(ParameterString(name=name, default_value=value, settable=False,
                allowed_modes={ParameterMode.PROPERTY}, ui_options={"display_name": label, "hide_handles": True}))
        status.add_child(ParameterButton(name="broker_connect_refresh", label="Connect / Refresh Models",
            icon="refresh-cw", serializable=False, on_click=self._on_connect))
        status.add_child(ParameterButton(name="generation_refresh", label="Retrieve Existing Image",
            icon="refresh-cw", serializable=False, on_click=self._on_retrieve))
        status.add_child(ParameterString(name="image_notice", default_value=(
            "Personal image generation · local save and image output. "
            "No project/Shot binding or web work-management publication. "
            "Connect / Refresh checks server support; provider keys stay on the server."),
            multiline=True, settable=False, serializable=False,
            allowed_modes={ParameterMode.PROPERTY},
            ui_options={"display_name": "Information", "hide_handles": True}))
        # Only stable recovery identity and the local path are kept here, never
        # a provider key, signed remote URL, image bytes or another user's record.
        self.add_parameter(ParameterDict(name="image_recovery", default_value={}, settable=False,
            allowed_modes={ParameterMode.PROPERTY}, hide=True, hide_property=True,
            ui_options={"hide": True, "hide_handles": True}))
        # Only UI profiles and authored scalar settings live here. Cached
        # profiles never authorize a model call; every new Run checks the Broker.
        self.add_parameter(ParameterDict(name="image_model_settings", default_value={}, settable=False,
            allowed_modes={ParameterMode.PROPERTY}, hide=True, hide_property=True,
            ui_options={"hide": True, "hide_property": True, "hide_handles": True}))
        self._model_settings_ready = True
        initial_model = str(self.get_parameter_value("model_id"))
        self._model_views[initial_model] = {"core": {name: self.get_parameter_value(name) for name in _CORE_SETTINGS},
            "options": {}, "auto_image_resize": True}
        self._select_model_ui(initial_model, remember_current=False)

    def _add_choice(self, name: str, value: str, choices: list[str], label: str, **kwargs: Any) -> None:
        # Saved future model/options must survive an offline cold open. The
        # Broker capability validator, rather than a dropdown converter, is
        # the authority at submission time.
        trait = Options(choices=choices, allow_custom=True)
        self._choices[name] = trait
        modes = kwargs.pop("allowed_modes", _PARAM_MODES)
        self.add_parameter(ParameterString(name=name, default_value=value, allowed_modes=modes,
            traits={trait}, ui_options={"display_name": label, "hide_handles": True}, **kwargs))

    def _is_live(self, token: threading.Event | None = None) -> bool:
        # This predicate also runs in transport workers: no retained-engine
        # lookup or UI mutation is allowed here.
        return bool(not self._deleted and not self.lock and not self.is_cancellation_requested and
            (token is None or (self._operation_token is token and not token.is_set())))

    def _publish(self, name: str, value: Any) -> None:
        try:
            self.parameter_output_values[name] = value
        except Exception:
            # Native tracked output dicts commit the value before emitting the
            # editor event. A disconnected editor must not undo that result.
            if self.parameter_output_values.get(name) is not value:
                raise
            logger.warning("%s image output retained; editor notification failed", self.name)
        with suppress(Exception):
            self.publish_update_to_parameter(name, value)

    def _complete_success(self, details: str) -> None:
        # The validated file and immutable task have already been committed.
        # Status display is supplementary and cannot reverse that success.
        self._execution_succeeded = True
        self._publish("was_successful", True)
        self._publish("result_details", details)
        try:
            self._set_status_results(was_successful=True, result_details=details)
        except Exception:
            logger.warning("%s saved image succeeded; optional status notification failed", self.name)

    def _checkpoint(self) -> dict[str, Any]:
        raw = self.get_parameter_value("image_recovery")
        if not raw:
            return {}
        if (not isinstance(raw, dict) or raw.get("schema") != _CHECKPOINT_SCHEMA
                or len(raw) > 20 or not all(isinstance(key, str) for key in raw)):
            raise ImageGenerationError("The saved image recovery record is invalid.")
        for name in ("client_request_id", "task_id", "provider", "model_id"):
            if not isinstance(raw.get(name), str) or _IDENTIFIER.fullmatch(raw[name]) is None:
                raise ImageGenerationError("The saved image task identity is invalid.")
        if raw.get("status") not in _UNFINISHED | JOB_FAILURE_STATUSES | {"succeeded", "rejected"}:
            raise ImageGenerationError("The saved image task status is invalid.")
        broker_config.normalize_broker_base_url(raw.get("broker_url"))
        path = raw.get("output_path")
        if not isinstance(path, str) or not path or len(path) > 4096 or "\x00" in path:
            raise ImageGenerationError("The saved image output path is invalid.")
        return deepcopy(raw)

    def _store_checkpoint(self, value: dict[str, Any]) -> None:
        self.parameter_values["image_recovery"] = deepcopy(value)
        self._publish("generation_id", value["task_id"])
        self._publish("generation_status", value["status"])

    def _apply_capabilities(self, capabilities: Any, origin: str) -> None:
        self._capabilities, self._capability_origin = capabilities, origin
        for model in capabilities.models:
            self._cached_profiles[model.provider + "/" + model.model_id] = model
        self._update_model_choices()
        ready = [model for model in capabilities.models if model.enabled and model.credential_ready]
        names = ", ".join(model.display_name for model in ready)
        self._publish("broker_status", f"Ready: {names}" if capabilities.enabled and ready else
            "Maintenance queue: acceptance only; generation will be revalidated after reopening"
            if getattr(capabilities, "_queue_admission", None) is not None else
            "Image generation not ready: server adapter or provider key registration pending")
        self._select_model_ui(str(self.get_parameter_value("model_id")))

    def _update_model_choices(self) -> None:
        models = self._capabilities.models if self._capabilities is not None else BUILTIN_IMAGE_MODEL_PROFILES
        self._set_choices("model_id", [item.provider + "/" + item.model_id for item in models])
        self._sync_model_label()

    def _sync_model_label(self) -> None:
        """A memory-only display view; labels never become model identities."""
        canonical = self.get_parameter_by_name("model_id")
        if not canonical.hide or not canonical.hide_property:
            # Legacy saved node-element metadata may restore its former visible
            # ID dropdown. Keep those input edges and values, show one selector.
            canonical.update_ui_options({"hide": True, "hide_property": True})
        models = self._capabilities.models if self._capabilities is not None else BUILTIN_IMAGE_MODEL_PROFILES
        selected = str(self.get_parameter_value("model_id"))
        keys = [item.provider + "/" + item.model_id for item in models]
        if selected not in keys:
            keys.append(selected)  # Preserve offline/future saved selections.
        names = {}
        for key in keys:
            profile = _BUILTIN_PROFILES.get(key) or self._model_profile(key)
            names[key] = profile.display_name if profile is not None else key
        # Provider-supplied duplicate names must not select the wrong model.
        # Reserve the two built-in names for their exact provider/model IDs.
        reserved = {item.display_name: key for key, item in _BUILTIN_PROFILES.items()}
        labels = {}
        for key, name in names.items():
            label = name
            if (name in reserved and reserved[name] != key) or (
                    name not in reserved and sum(value == name for value in names.values()) > 1):
                label = f"{name} ({key})"
            while label in labels:
                label += f" ({key})"
            labels[label] = key
        self._model_label_keys = labels
        self._set_choices("image_model", labels)
        label = next(name for name, key in labels.items() if key == selected)
        self._syncing_model_label = True
        try:
            self._write_ui_value("image_model", label)
        finally:
            self._syncing_model_label = False
        parameter = self.get_parameter_by_name("image_model")
        parameter.tooltip = f"Actual model: {selected}"

    def _set_choices(self, name: str, values: Any) -> None:
        values = list(values)
        if self._choices[name].choices != values:
            self._choices[name].choices = values
            # Updating a trait's Python list alone does not notify the editor.
            # Keep authored values, including saved future options, untouched.
            self.get_parameter_by_name(name).update_ui_options({"simple_dropdown": values, "allow_custom": True})

    def _model_profile(self, key: str) -> Any:
        if self._capabilities is not None:
            actual = next((item for item in self._capabilities.models
                if item.provider + "/" + item.model_id == key), None)
            if actual is not None:
                return actual
        return self._cached_profiles.get(key) or _BUILTIN_PROFILES.get(key)

    @staticmethod
    def _profile_state(model: Any) -> dict[str, Any]:
        result = {"provider": model.provider, "model_id": model.model_id, "display_name": model.display_name,
            "enabled": False, "credential_ready": False, "tasks": list(model.tasks),
            "aspect_ratios": list(model.aspect_ratios), "image_sizes": list(model.image_sizes),
            "output_formats": list(model.output_formats), "max_reference_images": model.max_reference_images,
            "max_reference_bytes": model.max_reference_bytes, "defaults": model_defaults(model)}
        if model.option_schema_revision:
            result["option_schema"] = serialize_option_schema(model.option_schema_revision, model.options)
        return result

    def _ui_option_specs(self, key: str, profile: Any) -> tuple[Any, ...]:
        if profile is not None and profile.option_schema_revision:
            return profile.options
        builtin = _BUILTIN_PROFILES.get(key)
        return builtin.options if builtin is not None else ()

    def _remember_model(self) -> None:
        if not self._selected_model or self._restoring_model_settings:
            return
        view = self._model_views.setdefault(self._selected_model, {"options": {}})
        view["core"] = {name: deepcopy(self.get_parameter_value(name)) for name in _CORE_SETTINGS}
        view["auto_image_resize"] = self.get_parameter_value("auto_image_resize")
        for key, name in self._active_option_parameters.items():
            view["options"][key] = deepcopy(self.get_parameter_value(name))

    def _store_model_settings(self) -> None:
        if not self._model_settings_ready or self._restoring_model_settings:
            return
        state = deepcopy(self._model_views)
        for key, view in state.items():
            profile = self._model_profile(key)
            if profile is not None:
                view["profile"] = self._profile_state(profile)
        snapshot = {"schema": _MODEL_SETTINGS_SCHEMA, "models": state}
        if self.get_parameter_value("image_model_settings") != snapshot:
            self.parameter_values["image_model_settings"] = snapshot

    def _write_ui_value(self, name: str, value: Any, *, preserve_scalar: bool = False) -> None:
        current = self.get_parameter_value(name)
        if type(current) is not type(value) or current != value:
            if preserve_scalar:
                # A server schema can change while an authored value is saved.
                # Do not let a numeric/boolean converter truncate that value.
                # Fresh authoritative model validation runs before submission.
                self.parameter_values[name] = deepcopy(value)
                self.publish_update_to_parameter(name, deepcopy(value))
            else:
                super().set_parameter_value(name, deepcopy(value), initial_setup=True,
                    emit_change=not getattr(self, "_hydrating_model_settings", False))

    @staticmethod
    def _option_parameter_name(model_key: str, spec: Any) -> str:
        descriptor = serialize_option_spec(spec)
        identity = json.dumps([model_key, spec.name, descriptor], sort_keys=True, separators=(",", ":"))
        return "model_option__" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]

    def _ensure_option_parameter(self, model_key: str, spec: Any) -> str:
        name = self._option_parameter_name(model_key, spec)
        cls = {"boolean": ParameterBool, "number": ParameterFloat, "integer": ParameterInt,
            "string": ParameterString}[spec.type]
        existing = self.get_parameter_by_name(name)
        # Native saved dynamic structure reopens as a generic Parameter. Rebuild
        # this unconnected property through public SDK APIs to restore typed
        # validation/traits; authored values are restored from the stable cache.
        if existing is not None and not isinstance(existing, cls):
            self.hide_parameter_by_name(name)
            self.remove_parameter_element(existing)
            existing = None
        if existing is None:
            # Persist these scalars normally. The SDK shares an identity-based
            # value pool: opting out True/False can otherwise also omit another
            # field containing that same interned scalar (including success).
            kwargs = {"name": name, "default_value": deepcopy(spec.default),
                "allowed_modes": {ParameterMode.PROPERTY},
                "ui_options": {"display_name": spec.label, "hide_handles": True},
                "tooltip": "Model option: " + spec.name}
            if spec.choices:
                kwargs["traits"] = {Options(choices=list(spec.choices), allow_custom=True)}
            if spec.type in {"number", "integer"}:
                slider = spec.minimum is not None and spec.maximum is not None
                # The SDK's step validator is anchored at zero. A model schema
                # may instead start at 0.05 with step 0.1. Show its step in the
                # native UI, and validate against its actual minimum at submit.
                if spec.step is not None:
                    kwargs["ui_options"]["step"] = spec.step
                kwargs.update(min_val=spec.minimum, max_val=spec.maximum, slider=slider, soft_limits=slider)
            existing = cls(**kwargs)
            existing.parent_element_name = self._generation_settings.name
            self.add_parameter(existing)
        self._option_bindings[name] = (model_key, spec.name)
        return name

    def _select_model_ui(self, key: str, *, remember_current: bool = True) -> None:
        if not self._model_settings_ready or self._restoring_model_settings:
            return
        if remember_current:
            self._remember_model()
        self._restoring_model_settings = True
        try:
            profile = self._model_profile(key)
            fresh = key not in self._model_views
            view = self._model_views.setdefault(key, {"core": {}, "options": {}, "auto_image_resize": True})
            if fresh:
                defaults = model_defaults(profile) if profile is not None else {}
                available = {"task": profile.tasks, "ratio": profile.aspect_ratios,
                    "image_size": profile.image_sizes, "output_format": profile.output_formats} if profile else {}
                view["core"] = {name: defaults.get(name, self.get_parameter_value(name)
                    if not available or self.get_parameter_value(name) in available[name] else available[name][0])
                    for name in _CORE_SETTINGS}
            if profile is not None:
                for name, values in (("task", profile.tasks), ("ratio", profile.aspect_ratios),
                                     ("image_size", profile.image_sizes), ("output_format", profile.output_formats)):
                    self._set_choices(name, values)
            for name, value in view.get("core", {}).items():
                self._write_ui_value(name, value)
            self._write_ui_value("auto_image_resize", view.get("auto_image_resize", True))
            active = {}
            for spec in self._ui_option_specs(key, profile):
                name = self._ensure_option_parameter(key, spec)
                active[spec.name] = name
                if spec.name not in view["options"]:
                    view["options"][spec.name] = deepcopy(spec.default)
                self._write_ui_value(name, view["options"][spec.name], preserve_scalar=True)
                self.show_parameter_by_name(name)
            for name in set(self._active_option_parameters.values()) - set(active.values()):
                self.hide_parameter_by_name(name)
            self._active_option_parameters = active
            self._selected_model = key
            self._sync_model_label()
            # Reuse other models' controls, but discard superseded descriptors
            # of this model after hiding them. Schema refreshes stay bounded.
            for name, binding in tuple(self._option_bindings.items()):
                if binding[0] == key and name not in active.values():
                    self.hide_parameter_by_name(name)
                    self.remove_parameter_element_by_name(name)
                    self._option_bindings.pop(name, None)
        finally:
            self._restoring_model_settings = False
        self._store_model_settings()

    def _restore_model_settings(self, raw: Any) -> None:
        try:
            if (not isinstance(raw, dict) or raw.get("schema") != _MODEL_SETTINGS_SCHEMA
                    or not isinstance(raw.get("models"), dict) or len(raw["models"]) > 128
                    or len(json.dumps(raw, ensure_ascii=False, allow_nan=False)) > 1024 * 1024):
                raise ValueError("Invalid saved model settings")
            views, profiles = {}, {}
            for key, value in raw["models"].items():
                if (not isinstance(key, str) or key.count("/") != 1
                        or not all(_IDENTIFIER.fullmatch(part) for part in key.split("/"))
                        or not isinstance(value, dict) or not isinstance(value.get("core"), dict)
                        or set(value["core"]) - set(_CORE_SETTINGS)
                        or any(not isinstance(item, str) or len(item) > 128 for item in value["core"].values())
                        or not isinstance(value.get("options"), dict) or len(value["options"]) > 32
                        or type(value.get("auto_image_resize")) is not bool):
                    raise ValueError("Invalid per-model saved settings")
                for name, item in value["options"].items():
                    if (not isinstance(name, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", name)
                            or type(item) not in {str, bool, int, float}
                            or (type(item) is float and not math.isfinite(item))
                            or (isinstance(item, str) and (len(item) > 4096 or "\x00" in item))):
                        raise ValueError("Invalid saved option value")
                if "profile" in value:
                    profile = parse_capabilities({"schema": CAPABILITIES_SCHEMA, "version": 1,
                        "enabled": False, "persistence_scope": "personal_local", "models": [value["profile"]]}).models[0]
                    if profile.provider + "/" + profile.model_id != key:
                        raise ValueError("Saved model profile identity mismatch")
                    profiles[key] = profile
                views[key] = {name: deepcopy(value[name]) for name in ("core", "options", "auto_image_resize")}
            self._model_views, self._cached_profiles = views, profiles
            self._selected_model = ""
            for parameter in self.parameters:
                if parameter.name.startswith("model_option__"):
                    self.hide_parameter_by_name(parameter.name)
            self._active_option_parameters = {}
            self._model_settings_error = ""
            self._select_model_ui(str(self.get_parameter_value("model_id")), remember_current=False)
            # The constructor supplies the offline Pro controls. A saved Broker
            # profile may use different descriptors while another model is
            # selected. Remove those now-obsolete constructor controls as well.
            retained = {self._option_parameter_name(key, spec) for key in self._model_views
                for spec in self._ui_option_specs(key, self._model_profile(key))}
            for parameter in tuple(self.parameters):
                if parameter.name.startswith("model_option__") and parameter.name not in retained:
                    self.hide_parameter_by_name(parameter.name)
                    self.remove_parameter_element(parameter)
                    self._option_bindings.pop(parameter.name, None)
        except (ValueError, TypeError, ImageGenerationError) as exc:
            # Optional UI cache corruption must not turn an existing workflow
            # into an unloadable placeholder or start work with guessed inputs.
            self._model_settings_error = str(exc)
            logger.warning("%s has invalid saved image model settings", self.name)

    def set_parameter_value(self, param_name: str, value: Any, *, initial_setup: bool = False,
                            emit_change: bool = True, skip_before_value_set: bool = False) -> None:
        if initial_setup and param_name.startswith("model_option__") and self.get_parameter_by_name(param_name) is not None:
            # Replayed scalar values must keep their original type even when a
            # provider has since changed number -> integer (or boolean). They
            # are revalidated before a new create, never silently truncated.
            self.parameter_values[param_name] = deepcopy(value)
            if emit_change:
                self.publish_update_to_parameter(param_name, deepcopy(value))
            return
        super().set_parameter_value(param_name, value, initial_setup=initial_setup,
            emit_change=emit_change, skip_before_value_set=skip_before_value_set)
        # SDK hydration suppresses value hooks. Element Add/Alter commands have
        # finished before values replay, so reuse them now without duplicate IDs.
        if initial_setup and getattr(self, "_model_settings_ready", False):
            self._hydrating_model_settings = True
            try:
                if param_name == "image_model_settings" and value:
                    self._restore_model_settings(value)
                elif param_name == "model_id" or param_name in _CORE_SETTINGS:
                    # Old workflows have no model-settings cache. Adopt their
                    # restored inputs instead of replacing them with defaults.
                    key = str(self.get_parameter_value("model_id"))
                    view = self._model_views.setdefault(key, {"options": {}, "auto_image_resize": True})
                    view["core"] = {name: deepcopy(self.get_parameter_value(name)) for name in _CORE_SETTINGS}
                    self._select_model_ui(key, remember_current=False)
            finally:
                self._hydrating_model_settings = False

    def after_value_set(self, parameter: Any, value: Any) -> None:
        super().after_value_set(parameter, value)
        if not getattr(self, "_model_settings_ready", False) or self._restoring_model_settings:
            return
        if parameter.name == "image_model":
            if not self._syncing_model_label:
                key = self._model_label_keys.get(str(value))
                if key is not None:
                    self.set_parameter_value("model_id", key)
                else:
                    self._sync_model_label()
        elif parameter.name == "model_id":
            self._model_settings_error = ""
            self._select_model_ui(str(value))  # Memory-only; no fetch or inference.
        elif parameter.name == "image_model_settings" and value:
            self._restore_model_settings(value)
        elif parameter.name in self._option_bindings:
            model, key = self._option_bindings[parameter.name]
            self._model_views.setdefault(model, {"options": {}})["options"][key] = deepcopy(value)
            self._store_model_settings()
        elif parameter.name in _CORE_SETTINGS or parameter.name == "auto_image_resize":
            self._remember_model()
            self._store_model_settings()

    def _schedule(self, action: str, details: Any) -> NodeMessageResult:
        with self._operation_lock:
            if not self._is_live() or self._busy or self._scheduled:
                return NodeMessageResult(success=True, details="Image action already running or node locked; no duplicate request.",
                    response=details, altered_workflow_state=False)
            try:
                loop = self.engine.event_manager.event_loop
                if loop is None or not loop.is_running():
                    raise RuntimeError("Engine loop unavailable")
                self._scheduled = True
                future = asyncio.run_coroutine_threadsafe(self._execute(action), loop)
                self._button_futures.add(future)
                future.add_done_callback(self._button_futures.discard)
            except Exception:
                self._scheduled = False
                return NodeMessageResult(success=False, details="Engine is not ready. Retry after the workflow opens.",
                    response=details, altered_workflow_state=False)
        return NodeMessageResult(success=True, details="Image action scheduled in the background.",
            response=details, altered_workflow_state=False)

    def _on_connect(self, _button: Any, details: Any) -> NodeMessageResult:
        return self._schedule("connect", details)

    def _on_retrieve(self, _button: Any, details: Any) -> NodeMessageResult:
        return self._schedule("retrieve", details)

    def _resolve_reference(self, item: Any) -> Any:
        if isinstance(item, dict) and "value" in item:
            item = item["value"]
        value = getattr(item, "value", item)
        if isinstance(value, str) and not value.startswith("data:"):
            # SDK File resolves its own local static URLs and project macros.
            # An external HTTP reference stays a URL and is refused before any
            # fetch; a Broker bearer token is never sent to a reference host.
            resolved = File(value).resolve()
            if urlsplit(resolved).scheme in {"http", "https", "file"}:
                raise ImageGenerationError("Import the reference image locally before generating.")
            return Path(resolved)
        return item

    def _capture_inputs(self) -> tuple[dict[str, Any], tuple[Any, ...], str]:
        if self._model_settings_error:
            raise ImageGenerationError("Saved image model settings are invalid. Select the model again before generating.")
        self._remember_model()
        self._store_model_settings()
        inputs = {key: deepcopy(self.get_parameter_value(key)) for key in (
            "model_id", "task", "prompt", "ratio", "image_size", "output_format")}
        selected = inputs["model_id"]
        if not isinstance(selected, str) or selected.count("/") != 1:
            raise ImageGenerationError("Select an image model from the Broker catalogue.")
        inputs["model_options"] = deepcopy(self._model_views.get(selected, {}).get("options", {}))
        inputs["auto_image_resize"] = self.get_parameter_value("auto_image_resize")
        inputs["provider"], inputs["model_id"] = selected.split("/", 1)
        refs = deepcopy(self.get_parameter_value("reference_images") or [])
        if not isinstance(refs, (list, tuple)):
            refs = [refs]
        refs = tuple(self._resolve_reference(item) for item in refs if item not in (None, ""))
        output = str(self._output_file.build_file(_index=1).resolve())
        if urlsplit(output).scheme in {"http", "https", "file"}:
            raise ImageGenerationError("Select a local image output path.")
        return inputs, refs, output

    @staticmethod
    def _options_for_capabilities(capabilities: Any, inputs: dict[str, Any]) -> dict[str, Any]:
        """Preserve the old request shape for unchanged native Google defaults.

        An old Broker cannot implement new controls. Explicit non-defaults and
        removed/unknown keys remain present so the validator rejects them before
        any upload/create, rather than quietly ignoring the user's selection.
        """
        inputs = deepcopy(inputs)
        models = [item for item in capabilities.models
            if item.provider == inputs["provider"] and item.model_id == inputs["model_id"]]
        if len(models) == 1 and not models[0].option_schema_revision:
            profile = _BUILTIN_PROFILES.get(inputs["provider"] + "/" + inputs["model_id"])
            defaults = {spec.name: spec.default for spec in profile.options} if profile else {}
            options = inputs.get("model_options", {})
            if all(key in defaults and type(value) is type(defaults[key]) and value == defaults[key]
                   for key, value in options.items()):
                inputs["model_options"] = {}
        return inputs

    @staticmethod
    def _cached_image(checkpoint: dict[str, Any], job: dict[str, Any]) -> Path | None:
        path = checkpoint.get("saved_path")
        if not isinstance(path, str) or not path or len(path) > 4096:
            return None
        try:
            with Path(path).open("rb") as stream:
                raw = stream.read(MAX_IMAGE_BYTES + 1)
            validate_image_bytes(raw, advertised_mime=job["result"]["mime_type"],
                advertised_sha256=job["result"].get("sha256") or checkpoint.get("saved_sha256", ""))
            return Path(path)
        except (OSError, ValueError, ImageGenerationError):
            return None

    @staticmethod
    def _verify_recovered_job(job: dict[str, Any], checkpoint: dict[str, Any]) -> None:
        for key, expected in (("provider", checkpoint["provider"]), ("model", checkpoint["model_id"]),
                              ("client_request_id", checkpoint["client_request_id"])):
            if job.get(key) != expected:
                raise ImageGenerationError("The retrieved image belongs to a different request.")
        if checkpoint["task_id"] != checkpoint["client_request_id"] and job.get("job_id") != checkpoint["task_id"]:
            raise ImageGenerationError("The retrieved image Task ID does not match.")

    async def aprocess(self) -> None:
        await self._execute("run")

    async def _execute(self, action: str) -> None:
        with self._operation_lock:
            self._scheduled = False
            if self._busy or not self._is_live():
                return
            self._busy = True
            token = self._operation_token = threading.Event()
        checkpoint: dict[str, Any] = {}
        try:
            if action != "connect":
                self._clear_execution_status()
            origin = broker_config.load_broker_base_url()
            if not origin:
                raise ImageGenerationError("Set the shared Broker address before connecting.")
            if action == "connect":
                broker = await asyncio.to_thread(self._broker_factory, server_url=origin)
                if not self._is_live(token):
                    return
                account = await asyncio.to_thread(broker.account_snapshot, connect=True)
                if not self._is_live(token):
                    return
                if not account.connected:
                    self._publish("broker_status", "Broker login / approval required")
                    return
                caps = await asyncio.to_thread(broker.capabilities)
                if self._is_live(token):
                    self._apply_capabilities(caps, origin)
                return

            checkpoint = self._checkpoint()
            resume = str(self.get_parameter_value("resume_task_id") or "").strip()
            retrieving = (action == "retrieve" or bool(resume) or checkpoint.get("status") in _UNFINISHED
                or (checkpoint.get("status") == "succeeded" and not checkpoint.get("saved_path")))
            captured = None if retrieving else self._capture_inputs()
            # The first authenticated transport lazily loads the existing
            # video module's login bridge. Keep that import off the UI loop.
            broker = await asyncio.to_thread(self._broker_factory, server_url=origin)
            if not self._is_live(token):
                return
            if retrieving:
                if not checkpoint or (resume and resume not in {checkpoint["task_id"], checkpoint["client_request_id"]}):
                    raise ImageGenerationError("Use the saved Task ID of this image node to retrieve its result.")
                if origin != checkpoint["broker_url"]:
                    raise ImageGenerationError("Restore this task's original shared Broker address before retrieval.")
                if checkpoint["task_id"] == checkpoint["client_request_id"]:
                    caps = await asyncio.to_thread(broker.capabilities)
                    if not self._is_live(token):
                        return
                    self._apply_capabilities(caps, origin)
                job = await asyncio.to_thread(broker.refresh, checkpoint["task_id"],
                    client_request_id=checkpoint["client_request_id"])
                self._verify_recovered_job(job, checkpoint)
            else:
                # Freeze authored inputs and destination before the first
                # asynchronous capability lookup; edits affect the next Run.
                assert captured is not None
                inputs, refs, output = captured
                caps = await asyncio.to_thread(broker.capabilities)
                if not self._is_live(token):
                    return
                self._apply_capabilities(caps, origin)
                frozen_inputs = self._options_for_capabilities(caps, inputs)
                invocation = await asyncio.to_thread(prepare_invocation, caps, references=refs, **frozen_inputs)
                if not self._is_live(token):
                    return
                checkpoint = {"schema": _CHECKPOINT_SCHEMA, "broker_url": origin,
                    "provider": invocation.provider, "model_id": invocation.model_id,
                    "client_request_id": invocation.client_request_id, "task_id": invocation.client_request_id,
                    "status": "submitting", "output_path": output}
                if getattr(caps, "_queue_admission", None) is not None:
                    checkpoint["queue_only_headers"] = json.loads(invocation._queue_headers_json)
                self._store_checkpoint(checkpoint)
                try:
                    job = await asyncio.to_thread(broker.create, invocation, is_alive=lambda: self._is_live(token))
                except Exception as exc:
                    checkpoint["status"] = "submission_unknown" if getattr(exc, "submission_outcome_unknown", False) else "rejected"
                    if self._is_live(token):
                        self._store_checkpoint(checkpoint)
                    raise

            deadline = asyncio.get_running_loop().time() + self.POLL_TIMEOUT_SECONDS
            while self._is_live(token):
                self._verify_recovered_job(job, checkpoint)
                checkpoint.update(task_id=job["job_id"], status=job["status"])
                # A durable running Task can carry an explicit unknown provider
                # submission outcome. Polling cannot resolve that uncertainty
                # automatically and must never turn it into a replacement Run.
                error = job.get("error")
                if job["status"] in JOB_PENDING_STATUSES and (job.get("submission_outcome_unknown") is True
                        or isinstance(error, dict) and error.get("code") == "image_submission_unknown"):
                    checkpoint["status"] = "submission_unknown"
                    self._store_checkpoint(checkpoint)
                    raise ImageGenerationError(
                        f"Image submission outcome is unknown. Task {checkpoint['task_id']} retained. "
                        "Automatic polling stopped. Use Retrieve Existing Image to check this same Task; "
                        "no replacement image was submitted.", code="IMAGE_SUBMISSION_UNKNOWN",
                        submission_outcome_unknown=True)
                self._store_checkpoint(checkpoint)
                if job["status"] == "succeeded":
                    # A repeated Retrieve must not create another local copy.
                    existing = await asyncio.to_thread(self._cached_image, checkpoint, job)
                    if existing is not None:
                        saved_path = existing
                    else:
                        saved = await asyncio.to_thread(broker.save_result, job, Path(checkpoint["output_path"]),
                            is_alive=lambda: self._is_live(token))
                        saved_path = saved.path
                        checkpoint["saved_sha256"] = saved.sha256
                    if not self._is_live(token):
                        return
                    checkpoint["saved_path"] = str(saved_path)
                    self._store_checkpoint(checkpoint)
                    artifact = ImageUrlArtifact(value=str(saved_path), name=saved_path.name)
                    self._publish("IMAGE_OUT", artifact)
                    self._publish("image_url", artifact)
                    self._complete_success(f"SUCCESS: {job['job_id']}\nSaved image: {saved_path}")
                    return
                if job["status"] in JOB_FAILURE_STATUSES:
                    raise ImageGenerationError(f"Image generation ended: {job['status']}. Task {job['job_id']} retained.")
                if asyncio.get_running_loop().time() >= deadline:
                    raise ImageGenerationError("Image polling timed out. Retrieve the same Task; no replacement was submitted.")
                pause_until = asyncio.get_running_loop().time() + self.POLL_INTERVAL_SECONDS
                while self._is_live(token) and asyncio.get_running_loop().time() < pause_until:
                    await asyncio.sleep(min(0.25, max(0, pause_until - asyncio.get_running_loop().time())))
                if self._is_live(token):
                    job = await asyncio.to_thread(broker.refresh, checkpoint["task_id"],
                        client_request_id=checkpoint["client_request_id"])
        except asyncio.CancelledError:
            if checkpoint and self._is_live(token):
                if checkpoint["status"] == "submitting":
                    checkpoint["status"] = "submission_unknown"
                self._store_checkpoint(checkpoint)
                self._set_status_results(was_successful=False,
                    result_details="Local wait stopped. Retrieve this same image Task; the server may still finish it.")
            raise
        except Exception as exc:
            if self._is_live(token):
                # Never render raw provider bodies or tokens in workflow data.
                message = str(exc) if isinstance(exc, ImageGenerationError) else f"Image action failed ({type(exc).__name__})."
                if action == "connect":
                    self._publish("broker_status", message)
                else:
                    self._set_status_results(was_successful=False, result_details=message)
                logger.warning("%s personal image action failed: %s", self.name, type(exc).__name__)
        finally:
            token.set()
            with self._operation_lock:
                if self._operation_token is token:
                    self._operation_token = None
                    self._busy = False

    def after_node_deleted(self, *args: Any, **kwargs: Any) -> Any:
        self._deleted = True
        if self._operation_token is not None:
            self._operation_token.set()
        for future in tuple(self._button_futures):
            future.cancel()
        parent = getattr(super(), "after_node_deleted", None)
        return parent(*args, **kwargs) if callable(parent) else None
