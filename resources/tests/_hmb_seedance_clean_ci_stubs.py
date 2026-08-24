"""Minimal Griptape import surface for host-independent Seedance regressions."""

from __future__ import annotations

import importlib.util
import sys
import types
from typing import Any


def install_clean_ci_griptape_stubs() -> None:
    """Install test-only modules when public CI has no Griptape host packages."""

    def surface_missing(name: str) -> bool:
        try:
            return importlib.util.find_spec(name) is None
        except (AttributeError, ImportError, ModuleNotFoundError, ValueError):
            return True

    griptape_missing = surface_missing("griptape.artifacts.video_url_artifact")
    griptape_nodes_missing = any(
        surface_missing(name)
        for name in (
            "griptape_nodes.files.project_file",
            "griptape_nodes.exe_types.param_components.project_file_parameter",
            "griptape_nodes.retained_mode.griptape_nodes",
        )
    )
    if not griptape_missing and not griptape_nodes_missing:
        return

    def package(name: str) -> types.ModuleType:
        existing = sys.modules.get(name)
        if existing is not None:
            return existing
        module = types.ModuleType(name)
        module.__path__ = []  # type: ignore[attr-defined]
        sys.modules[name] = module
        if "." in name:
            parent_name, child_name = name.rsplit(".", 1)
            setattr(package(parent_name), child_name, module)
        return module

    def module(name: str, **attributes: Any) -> types.ModuleType:
        parent_name, child_name = name.rsplit(".", 1)
        parent = package(parent_name)
        installed = types.ModuleType(name)
        installed.__dict__.update(attributes)
        sys.modules[name] = installed
        setattr(parent, child_name, installed)
        return installed

    class StubValue:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.args = args
            self.__dict__.update(kwargs)
            self.name = kwargs.get("name", "")
            self.default_value = kwargs.get("default_value")
            self.type = kwargs.get("type")
            self.input_types = list(kwargs.get("input_types", []))
            self.output_type = kwargs.get("output_type")
            self.accept_any = bool(kwargs.get("accept_any", False))
            self.serializable = bool(kwargs.get("serializable", True))
            self.ui_options = dict(kwargs.get("ui_options", {}))
            self._children: list[Any] = []

        def __enter__(self) -> "StubValue":
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

        def add_child(self, child: Any) -> None:
            self._children.append(child)

        def add_trait(self, child: Any) -> None:
            self._children.append(child)

        def add_parameter(self, *args: Any, **kwargs: Any) -> None:
            del args, kwargs

        def update_ui_options_key(self, key: str, value: Any) -> None:
            self.ui_options[key] = value

        def set_badge(self, *args: Any, **kwargs: Any) -> None:
            del args, kwargs

    class StubParameterMode:
        INPUT = "INPUT"
        OUTPUT = "OUTPUT"
        PROPERTY = "PROPERTY"

    class StubDataNode:
        def __init__(self, **kwargs: Any) -> None:
            self.name = kwargs.get("name", type(self).__name__)
            self.parameters: dict[str, Any] = {}
            self.parameter_values: dict[str, Any] = {}
            self.parameter_output_values: dict[str, Any] = {}
            self.metadata: dict[str, Any] = {}

        def add_parameter(self, parameter: Any) -> None:
            self.parameters[parameter.name] = parameter

        def add_node_element(self, element: Any) -> None:
            name = getattr(element, "name", "")
            if name:
                self.parameters[name] = element

        def get_parameter_by_name(self, name: str) -> Any:
            return self.parameters.get(name)

        def get_parameter_value(self, name: str) -> Any:
            if name in self.parameter_values:
                return self.parameter_values[name]
            parameter = self.get_parameter_by_name(name)
            return getattr(parameter, "default_value", None)

        def hide_parameter_by_name(self, name: Any) -> None:
            if isinstance(name, (list, tuple, set)):
                for item in name:
                    self.hide_parameter_by_name(item)
                return
            parameter = self.get_parameter_by_name(name)
            if parameter is not None:
                parameter.hide = True

        def show_parameter_by_name(self, name: Any) -> None:
            if isinstance(name, (list, tuple, set)):
                for item in name:
                    self.show_parameter_by_name(item)
                return
            parameter = self.get_parameter_by_name(name)
            if parameter is not None:
                parameter.hide = False

        def set_parameter_value(
            self,
            name: str,
            value: Any,
            *,
            initial_setup: bool = False,
            emit_change: bool = True,
            skip_before_value_set: bool = False,
        ) -> None:
            del emit_change
            parameter = self.get_parameter_by_name(name)
            if parameter is None:
                # Parameters declared inside a real ParameterGroup context are
                # registered by the host. The lightweight stub materializes
                # them lazily when constructor synchronization first writes.
                parameter = StubValue(name=name, default_value=value)
                self.add_parameter(parameter)
            final_value = value
            if not initial_setup and not skip_before_value_set:
                callback = getattr(self, "before_value_set", None)
                if callable(callback):
                    final_value = callback(parameter, value)
            self.parameter_values[name] = final_value
            if not initial_setup:
                callback = getattr(self, "after_value_set", None)
                if callable(callback):
                    callback(parameter, final_value)

        def before_value_set(self, _parameter: Any, value: Any) -> Any:
            return value

        def after_value_set(self, _parameter: Any, _value: Any) -> None:
            return None

    class StubStatusComponent:
        def __init__(self) -> None:
            self._group = StubValue(name="status")

        def get_parameter_group(self) -> StubValue:
            return self._group

    class StubSuccessFailureNode(StubDataNode):
        def _create_status_parameters(self, **_kwargs: Any) -> None:
            self.status_component = StubStatusComponent()

    class StubFileLoadError(Exception):
        pass

    class StubFile(StubValue):
        def __init__(self, value: Any, *args: Any, **kwargs: Any) -> None:
            super().__init__(value, *args, **kwargs)
            self._value = value

        def resolve(self) -> Any:
            return self._value

    class StubProjectFileParameter(StubValue):
        DEFAULT_SITUATION = "save_node_output"

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self._default_filename = str(kwargs.get("default_filename") or "")

    class StubProjectFileDestination(StubValue):
        @classmethod
        def from_situation(
            cls,
            filename: str,
            situation: str,
            **extra_vars: str | int,
        ) -> "StubProjectFileDestination":
            return cls(
                filename,
                filename=filename,
                situation=situation,
                extra_vars=dict(extra_vars),
            )

        def resolve(self) -> str:
            return str(getattr(self, "filename", ""))

    class StubExistingFilePolicy:
        CREATE_NEW = object()
        FAIL = object()
        OVERWRITE = object()

    class StubCloudStorageDriver(StubValue):
        def create_signed_upload_url(self, _path: Any) -> Any:
            raise NotImplementedError

        def create_signed_download_url(self, _path: Any) -> Any:
            raise NotImplementedError

    class StubGriptapeNodes:
        pass

    class StubSaveWorkflowRequest(StubValue):
        def __init__(
            self,
            *,
            file_name: str | None = None,
            broadcast_result: bool = True,
            create_versioned: bool = False,
            overwrite_existing: bool = True,
            **kwargs: Any,
        ) -> None:
            super().__init__(
                file_name=file_name,
                broadcast_result=broadcast_result,
                create_versioned=create_versioned,
                overwrite_existing=overwrite_existing,
                **kwargs,
            )

    class StubSaveWorkflowResultSuccess(StubValue):
        pass

    if griptape_missing:
        artifacts = package("griptape.artifacts")
        artifacts.ImageUrlArtifact = StubValue
        artifacts.VideoUrlArtifact = StubValue
        module(
            "griptape.artifacts.video_url_artifact",
            VideoUrlArtifact=StubValue,
        )

    if not griptape_nodes_missing:
        return

    module(
        "griptape_nodes.drivers.storage.griptape_cloud_storage_driver",
        GriptapeCloudStorageDriver=StubCloudStorageDriver,
    )
    module(
        "griptape_nodes.exe_types.core_types",
        NodeMessagePayload=StubValue,
        NodeMessageResult=StubValue,
        Parameter=StubValue,
        ParameterGroup=StubValue,
        ParameterList=StubValue,
        ParameterMode=StubParameterMode,
    )
    module(
        "griptape_nodes.exe_types.node_types",
        DataNode=StubDataNode,
        SuccessFailureNode=StubSuccessFailureNode,
    )
    module(
        "griptape_nodes.exe_types.param_components.project_file_parameter",
        ProjectFileParameter=StubProjectFileParameter,
    )
    for parameter_module, parameter_name in (
        ("parameter_bool", "ParameterBool"),
        ("parameter_button", "ParameterButton"),
        ("parameter_dict", "ParameterDict"),
        ("parameter_image", "ParameterImage"),
        ("parameter_int", "ParameterInt"),
        ("parameter_string", "ParameterString"),
        ("parameter_video", "ParameterVideo"),
    ):
        module(
            f"griptape_nodes.exe_types.param_types.{parameter_module}",
            **{parameter_name: StubValue},
        )
    module(
        "griptape_nodes.files.file",
        File=StubFile,
        FileLoadError=StubFileLoadError,
    )
    module(
        "griptape_nodes.files.project_file",
        ProjectFileDestination=StubProjectFileDestination,
    )
    module(
        "griptape_nodes.retained_mode.events.os_events",
        ExistingFilePolicy=StubExistingFilePolicy,
    )
    module(
        "griptape_nodes.retained_mode.events.project_events",
        MacroPath=StubValue,
    )
    module(
        "griptape_nodes.retained_mode.events.workflow_events",
        SaveWorkflowRequest=StubSaveWorkflowRequest,
        SaveWorkflowResultSuccess=StubSaveWorkflowResultSuccess,
    )
    module(
        "griptape_nodes.retained_mode.file_metadata.sidecar_metadata",
        write_sidecar=lambda *_args, **_kwargs: None,
    )
    module(
        "griptape_nodes.retained_mode.griptape_nodes",
        GriptapeNodes=StubGriptapeNodes,
    )
    module("griptape_nodes.traits.options", Options=StubValue)
