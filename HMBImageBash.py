"""HMB Image Bash node and the retained document contract for its editor.

The editor's PNG is the authoritative render. A saved Apply transaction embeds
that PNG and its scene/source receipt, so a later Run never substitutes a PIL
approximation for an approved browser render.
"""
from __future__ import annotations

import base64
import asyncio
import contextvars
from copy import deepcopy
from collections import OrderedDict
import hashlib
import inspect
from io import BytesIO
from pathlib import Path
import sys
import threading
from typing import Any
from types import SimpleNamespace
from urllib.parse import unquote, urlparse
import weakref
from uuid import uuid4

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from _hmb_deletion_guard import hmb_binding_mutation

from griptape.artifacts import ImageUrlArtifact
from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterList, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.exe_types.param_components.project_file_parameter import ProjectFileParameter
from griptape_nodes.files.file import File
from griptape_nodes.traits.color_picker import ColorPicker
from griptape_nodes.traits.options import Options
from griptape_nodes.traits.widget import Widget
from PIL import Image

from _hmb_image_bash_render import render_scene
from _hmb_image_bash_state import sync_scene, scene_fingerprint, validate_png_bytes

CONTEXT_SCHEMA = "hmb-image-bash-inputs-v1"
RECEIPT_SCHEMA = "hmb-image-bash-apply-v1"
HEADER_PARAMETER = "HMB_IMAGE_BASH_UI"
PREPARATION_SCHEMA = "hmb-image-bash-preparation-v1"
_HIDDEN_UI = {"hide": True, "hide_property": True, "hide_label": True,
              "hide_handles": True, "height": 1, "min_height": 0, "max_height": 1}
_PREPARE_WORKSPACE = "hmb-new-workspace-v1"
EDITOR_SCHEMA = "hmb-image-bash-editor-v1"
CANVAS_PRESETS = {
    "2K Full": (2048, 1080), "2K Flat": (1998, 1080), "2K Scope": (2048, 858),
    "4K Full": (4096, 2160), "4K Flat": (3996, 2160), "4K Scope": (4096, 1716),
    "HD (16:9)": (1920, 1080), "UHD (4K, 16:9)": (3840, 2160),
    "Square 2K": (2048, 2048), "Square 4K": (4096, 4096),
    "YouTube Shorts / TikTok / Reels": (1080, 1920), "Instagram Square": (1080, 1080),
    "Instagram Portrait": (1080, 1350), "Twitter Landscape": (1600, 900),
    "Twitter Portrait": (1080, 1350), "Facebook Cover": (820, 312),
}
_DIMENSION_MODES = {ParameterMode.INPUT, ParameterMode.PROPERTY, ParameterMode.OUTPUT}
_EMPTY_CANVAS = "data:image/svg+xml;base64," + base64.b64encode(
    b'<svg width="1920" height="1080" xmlns="http://www.w3.org/2000/svg"><rect width="1920" height="1080" fill="#fffffa"/></svg>'
).decode("ascii")


class _ImageBashSourceError(ValueError):
    """An input raster could not be freshly read or decoded."""


def _snapshot_driver(file: File) -> Any:
    """Use SDK driver classification only when the acceleration seam is available."""
    try:
        from griptape_nodes.files.file import _resolve_file_path
        from griptape_nodes.files.file_driver import FileDriverRegistry
        signature = inspect.signature(_resolve_file_path)
        arguments = (file._file_path,)
        keywords = {"workflow": file.workflow} if "workflow" in signature.parameters else {}
        signature.bind(*arguments, **keywords)
    except (AttributeError, ImportError, TypeError, ValueError):
        return None  # Unknown private API: keep the normal SDK file reader.
    location = _resolve_file_path(*arguments, **keywords)
    return FileDriverRegistry.get_driver(location)


def _hmb_is_registered_node(node: Any, kind: str) -> bool:
    """Accept only the actual class registered by the HMB production library."""
    try:
        from griptape_nodes.node_library.library_registry import LibraryRegistry
        metadata = getattr(node, "metadata", None)
        if not isinstance(metadata, dict) or metadata.get("library") != "HMB_GP_Production" or metadata.get("node_type") != kind:
            return False
        library = LibraryRegistry.get_library_for_node_type(kind, "HMB_GP_Production")
        return type(node) is library.get_node_class(kind)
    except (AttributeError, KeyError, TypeError, ValueError):
        return False


def _hmb_is_palette_creation_metadata(metadata: Any) -> bool:
    """Capture layout-only creation before the node adds its own metadata.

    The SDK injects the registered library identity into the request's same
    dictionary before calling this constructor. Later the native node adds
    size and other runtime fields, so the post-create request is no longer an
    immutable description of the user's creation intent.
    """
    if metadata is None:
        return True
    if (not isinstance(metadata, dict)
            or set(metadata) - {"position", "tempId", "library_node_metadata", "library", "node_type"}):
        return False
    if not any(key in metadata for key in ("library_node_metadata", "library", "node_type")):
        return True
    try:
        from griptape_nodes.node_library.library_registry import LibraryRegistry
        library = LibraryRegistry.get_library_for_node_type("HMBImageBash", "HMB_GP_Production")
        registered = library.get_node_metadata("HMBImageBash").model_dump(mode="json")
        return (metadata.get("library") == "HMB_GP_Production"
                and metadata.get("node_type") == "HMBImageBash"
                and metadata.get("library_node_metadata") == registered)
    except (AttributeError, KeyError, TypeError, ValueError):
        return False


def _install_bash_creation_observer(engine: Any) -> None:
    """Observe fresh create results; perform graph work only on a later tick."""
    manager = engine.event_manager
    _install_bash_initial_value_admission(engine)
    if getattr(manager, "_hmb_bash_creation_observer", None) is not None:
        return
    from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
    from griptape_nodes.retained_mode.engine import engine_scope

    def after_create(request: Any, result: Any) -> None:
        if (not result.succeeded() or request.initial_setup
                or request.node_type not in {"HMBImageBash", "HMBImageAssetLibrary"}):
            return
        name, flow_name, kind = result.node_name, result.parent_flow_name, request.node_type
        try:
            created_node = engine.node_manager.get_node_by_name(name)
        except Exception:
            return
        if not _hmb_is_registered_node(created_node, kind):
            return
        if kind == "HMBImageBash" and not getattr(created_node, "_hmb_palette_creation_layout_only", False):
            return
        loop = manager.event_loop
        if loop is None or loop.is_closed() or not loop.is_running():
            # Leave explicit Refresh available in synchronous hosts. Graph
            # mutation is never performed from a notification-only hook.
            if kind == "HMBImageBash" and not getattr(created_node, "_hmb_user_binding_interacted", False):
                created_node._hmb_auto_workspace_pending = True
            return
        def reconcile() -> None:
            with engine_scope(engine):
                try:
                    if engine.node_manager.get_node_by_name(name) is not created_node:
                        return
                    if kind == "HMBImageBash":
                        node = created_node
                        if not _hmb_is_registered_node(node, "HMBImageBash") or getattr(node, "_hmb_user_binding_interacted", False):
                            return
                        node._hmb_auto_workspace_pending = True
                        node._hmb_try_auto_workspace()
                    else:
                        flow = engine.flow_manager.get_flow_by_name(flow_name)
                        for node in tuple(flow.nodes.values()):
                            if _hmb_is_registered_node(node, "HMBImageBash") and getattr(node, "_hmb_auto_workspace_pending", False):
                                node._hmb_try_auto_workspace()
                except Exception:
                    # The node may be deleted or the flow closed before the tick.
                    return
        loop.call_soon_threadsafe(lambda: loop.call_later(.01, reconcile, context=contextvars.Context()))

    manager.add_post_dispatch_hook(CreateNodeRequest, after_create)
    from griptape_nodes.retained_mode.events.parameter_events import GetParameterValueRequest
    def after_header_read(request: Any, result: Any) -> None:
        # SDK initial_setup can omit both value callbacks and a final header
        # projection. The native launcher's first header read is a safe lazy
        # entry point; only queue validation after resolving the current node.
        if request.parameter_name != HEADER_PARAMETER or not result.succeeded():
            return
        try:
            node = engine.node_manager.get_node_by_name(request.node_name)
            if (_hmb_is_registered_node(node, "HMBImageBash")
                    and getattr(node, "_hmb_prepare_phase", None) == "idle"
                    and not getattr(node, "_hmb_node_deleted", False)):
                node._publish_header()
        except (AttributeError, KeyError, RuntimeError, ValueError):
            return
    manager.add_post_dispatch_hook(GetParameterValueRequest, after_header_read)
    manager._hmb_bash_readiness_observer = after_header_read
    manager._hmb_bash_creation_observer = after_create


def _install_bash_initial_value_admission(engine: Any) -> None:
    """Carry actual SDK initial_setup into hooks without trusting document flags.

    The SDK invokes before_value_set even for a saved assignment, before its
    inputs/connections exist, but does not pass initial_setup to that hook.
    Keep this request-scoped context on the manager so a library reload cannot
    leave a wrapper referring to a different module's ContextVar.
    """
    from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
    manager = engine.event_manager
    mapping = getattr(manager, "_request_type_to_manager", None)
    if not isinstance(mapping, dict):
        raise RuntimeError("SDK 파라미터 복원 요청 경계를 확인할 수 없습니다.")
    original = mapping.get(SetParameterValueRequest)
    installed = getattr(manager, "_hmb_bash_initial_value_admission", None)
    if installed is not None and original is installed:
        return
    if not callable(original):
        raise RuntimeError("SDK 파라미터 복원 핸들러를 확인할 수 없습니다.")
    # Callable handler objects (notably SDK RemoteHandler) have identity-based
    # dispatch semantics. Preserve them exactly instead of hiding that type in
    # a plain async function. Transparent foreign function chains remain valid.
    try:
        dispatch = inspect.unwrap(original)
    except ValueError:
        return
    if not (inspect.isfunction(dispatch) or inspect.ismethod(dispatch)):
        return
    if inspect.ismethod(dispatch) and (dispatch.__self__ is not engine.node_manager
            or getattr(dispatch.__self__, dispatch.__name__, None) != dispatch):
        return
    context = getattr(manager, "_hmb_bash_initial_assignment_context", None)
    if not isinstance(context, contextvars.ContextVar):
        context = contextvars.ContextVar("hmb_bash_initial_assignment", default=None)
        manager._hmb_bash_initial_assignment_context = context
    def target(request):
        if request.initial_setup is not True or request.parameter_name != "bash_image":
            return None
        try:
            node = engine.node_manager.get_node_by_name(request.node_name)
        except (KeyError, ValueError):
            return None
        return node if _hmb_is_registered_node(node, "HMBImageBash") else None
    asynchronous = inspect.iscoroutinefunction(original) or inspect.iscoroutinefunction(getattr(original, "__call__", None))
    if asynchronous:
        async def wrapped(request, *args, **kwargs):
            lease = {"node": target(request), "active": True}
            token = context.set(lease)
            try:
                return await original(request, *args, **kwargs)
            finally:
                lease["active"] = False
                context.reset(token)
    else:
        def wrapped(request, *args, **kwargs):
            lease = {"node": target(request), "active": True}
            token = context.set(lease)
            try:
                return original(request, *args, **kwargs)
            finally:
                lease["active"] = False
                context.reset(token)
    # Replace only this exact observed handler; do not remove any other SDK
    # registration or alter the previous handler's signature/result/behavior.
    if mapping.get(SetParameterValueRequest) is not original:
        raise RuntimeError("SDK 파라미터 복원 핸들러가 설치 중 변경되었습니다.")
    mapping[SetParameterValueRequest] = wrapped
    manager._hmb_bash_initial_value_admission = wrapped


def _install_bash_snapshot_header_read(engine: Any) -> None:
    """Refresh only the small header before its SDK reply is constructed."""
    from griptape_nodes.retained_mode.events.parameter_events import GetParameterValueRequest, GetParameterValueResultFailure
    manager = engine.event_manager
    mapping = getattr(manager, "_request_type_to_manager", None)
    if not isinstance(mapping, dict):
        raise RuntimeError("SDK 편집기 상태 읽기 경계를 확인할 수 없습니다.")
    original = mapping.get(GetParameterValueRequest)
    if original is getattr(manager, "_hmb_bash_snapshot_header_read", None) and original is not None:
        return
    if not callable(original):
        raise RuntimeError("SDK 편집기 상태 읽기 핸들러를 확인할 수 없습니다.")
    try:
        dispatch = inspect.unwrap(original)
    except ValueError:
        return
    if not (inspect.isfunction(dispatch) or inspect.ismethod(dispatch)):
        return  # Keep RemoteHandler and every special callable-object identity.
    if inspect.ismethod(dispatch) and (dispatch.__self__ is not engine.node_manager
            or getattr(dispatch.__self__, dispatch.__name__, None) != dispatch):
        return
    def target(request):
        if request.parameter_name != HEADER_PARAMETER:
            return None
        try:
            node = (engine.node_manager.get_node_by_name(request.node_name) if request.node_name is not None
                    else engine.context_manager.get_current_node())
        except (AttributeError, KeyError, ValueError):
            return None
        return node if _hmb_is_registered_node(node, "HMBImageBash") else None
    def before(request):
        node = target(request)
        if node is not None and not node._publish_header():
            return node, GetParameterValueResultFailure(result_details="현재 Bash 편집기 상태를 확인하지 못했습니다. 잠시 후 다시 시도하세요.")
        return node, None
    def after(node, result):
        if (node is not None and result.succeeded()
                and result.value != node.get_parameter_value(HEADER_PARAMETER)):
            return GetParameterValueResultFailure(result_details="Bash 편집기 상태가 변경되었습니다. 최신 상태로 다시 시도하세요.")
        return result
    asynchronous = inspect.iscoroutinefunction(original) or inspect.iscoroutinefunction(getattr(original, "__call__", None))
    if asynchronous:
        async def wrapped(request, *args, **kwargs):
            node, failure = before(request)
            return failure if failure is not None else after(node, await original(request, *args, **kwargs))
    else:
        def wrapped(request, *args, **kwargs):
            node, failure = before(request)
            return failure if failure is not None else after(node, original(request, *args, **kwargs))
    if mapping.get(GetParameterValueRequest) is not original:
        raise RuntimeError("SDK 편집기 상태 핸들러가 설치 중 변경되었습니다.")
    mapping[GetParameterValueRequest] = wrapped
    manager._hmb_bash_snapshot_header_read = wrapped


def _document(value: Any) -> dict:
    if isinstance(value, dict):
        return deepcopy(value)
    if isinstance(getattr(value, "value", None), dict):
        return deepcopy(value.value)
    if hasattr(value, "to_dict"):
        result = value.to_dict()
        if isinstance(result, dict):
            return deepcopy(result)
    if hasattr(value, "value"):
        result = {"value": value.value, "meta": deepcopy(getattr(value, "meta", {}))}
        return result
    raise ValueError("Image Bash project must be a JSON object.")


def _url(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return str(value.get("value", value.get("url", "")))
    return str(getattr(value, "value", ""))


def _flatten(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [item for row in value for item in _flatten(row)]
    return [value]


def _read_bytes(url: str) -> bytes:
    if url.startswith("data:"):
        header, encoded = url.split(",", 1)
        if ";base64" not in header:
            raise ValueError("Only base64 image data URLs are supported.")
        return base64.b64decode(encoded, validate=True)
    return File(url).read_bytes()


def _busy(node: Any) -> bool:
    state = getattr(node, "state", "")
    return str(getattr(state, "name", state)).casefold() == "resolving"


def _editor_layer(record: dict, index: int, canvas: dict, dimensions) -> dict:
    width, height = dimensions(record["url"])
    scale = min(1, canvas["width"] / width, canvas["height"] / height)
    name = record.get("name") or Path(unquote(urlparse(record["url"]).path)).stem or f"Image Layer {index + 1}"
    return {"id": f"canvas-img-{index + 1}", "source_id": record["id"], "src": record["url"],
            "x": canvas["width"] / 2, "y": canvas["height"] / 2, "width": width, "height": height,
            "rotation": 0, "scaleX": scale, "scaleY": scale, "type": "image", "name": name,
            "opacity": 1, "visible": True, "order": index + 1}


class HMBImageBash(DataNode):
    """HMB-owned editor with stable ImageAsset identities and verified Apply."""

    def allow_incoming_connection(self, source_node: Any, source_parameter: Parameter, target_parameter: Parameter) -> bool:
        # A list output belongs on the ParameterList parent. Native SDKs may
        # otherwise accept it on a single-image row and corrupt its value.
        parent = getattr(target_parameter, "parent_container_name", None)
        output_type = str(getattr(source_parameter, "output_type", "") or getattr(source_parameter, "type", ""))
        if parent == "input_images" and output_type.replace(" ", "").casefold().startswith("list["):
            return False
        return super().allow_incoming_connection(source_node, source_parameter, target_parameter)

    def __init__(self, **kwargs) -> None:
        incoming_metadata = kwargs.get("metadata")
        self._hmb_palette_creation_layout_only = _hmb_is_palette_creation_metadata(incoming_metadata)
        saved_size = deepcopy(incoming_metadata.get("size")) if isinstance(incoming_metadata, dict) and "size" in incoming_metadata else None
        self._hmb_syncing = True
        super().__init__(**kwargs)
        self._add_editor_parameters()
        # Serialized user geometry is authoritative. The SDK's library
        # metadata width/height alone does not set the new node's geometry.
        if saved_size is not None:
            self.metadata = {**self.metadata, "size": saved_size}
        elif "size" not in self.metadata:
            setter = getattr(self, "set_initial_node_size", None)
            if callable(setter):
                setter(width=800, height=680)
            else:
                self.metadata = {**self.metadata, "size": {"width": 800, "height": 680}}
        self.add_parameter(Parameter(name="image_bash_context", type="dict", default_value={},
            input_types=["dict"], allowed_modes={ParameterMode.INPUT},
            ui_options=dict(_HIDDEN_UI),
            tooltip="ImageAsset Library Image Bash workspace identity and ordered sources."))
        self.add_parameter(Parameter(name="HMB_BASH_STATUS", type="str", default_value="Apply 필요",
            allowed_modes={ParameterMode.OUTPUT},
            tooltip="Apply receipt, source freshness and compatibility status."))
        self.add_parameter(Parameter(name="HMB_BASH_VERIFICATION", type="dict", default_value={},
            allowed_modes={ParameterMode.OUTPUT}, ui_options={"hide": True}))
        self.get_parameter_by_name("comp_on_run").tooltip = (
            "기본 OFF: Apply PNG를 그대로 저장합니다. ON: 수정한 합성기로 픽셀을 추가 비교하며 "
            "Apply와 다르면 출력을 중단합니다."
        )
        self.get_parameter_by_name("output_image").tooltip = "검증된 Image Bash Apply 이미지입니다."
        # Media arrives only through REMOTE. Retain the native typed list for
        # validation/serialization, without exposing a second input workflow.
        images = self.get_parameter_by_name("input_images")
        images.ui_options = {**images.ui_options, **_HIDDEN_UI}
        for name in ("canvas_size", "width", "height", "background_color", "comp_on_run", "output_file", "HMB_BASH_STATUS"):
            parameter = self.get_parameter_by_name(name)
            parameter.ui_options = {**parameter.ui_options, "hide_handles": True}
        self.add_parameter(Parameter(name=HEADER_PARAMETER, type="dict", default_value={},
            serializable=False, allowed_modes={ParameterMode.PROPERTY},
            traits={Widget(name="HMBImageBashWidget", library="HMB_GP_Production")},
            ui_options={"display_name": "", "hide_label": True, "hide_handles": True,
                "is_full_width": True, "height": 64, "min_height": 64, "max_height": 64,
                "widget_height": 64, "expandable": False, "resizable": False, "compact": True}))
        self.move_element_to_position(HEADER_PARAMETER, "first")
        self._hmb_header_publishing = False
        self._hmb_last_output = None
        self._hmb_node_deleted = False
        self._hmb_output_generation = 0
        self._hmb_output_propagating = False
        self._hmb_output_pending = False
        self._hmb_output_delivered = {}
        self._hmb_restore_pending = False
        self._hmb_restore_scheduled = False
        self._hmb_cold_readiness_scheduled = False
        self._hmb_cold_input_gap = False
        self._hmb_cold_gap_admitted = False
        self._hmb_cold_gap_recovery = None
        self._hmb_inputs_unready = False
        self._hmb_prepare_phase = "idle"
        self._hmb_prepare_error = ""
        self._hmb_editor_snapshot_id = ""
        self._hmb_snapshot_republish_pending = None
        self._hmb_value_callback_depth = 0
        self._hmb_apply_epoch = 0
        self._hmb_apply_pending = None
        self._hmb_prepare_pending = None
        self._hmb_cold_restore_pending = None
        self._hmb_apply_rollback_document = None
        self._hmb_apply_prior_receipt = None
        self._hmb_apply_rgba_cache = None
        self._hmb_apply_work = {"lock": threading.RLock(), "active": False, "queued": None,
                                "completed": None, "publish_scheduled": False}
        self._hmb_auto_workspace_pending = False
        self._hmb_user_binding_interacted = False
        self.set_parameter_value("comp_on_run", False)
        self._hmb_syncing = False
        self._hmb_auto_pristine_project = _document(self.get_parameter_value("bash_image"))
        self._hmb_auto_pristine_settings = {
            name: deepcopy(self.get_parameter_value(name))
            for name in ("canvas_size", "width", "height", "background_color", "comp_on_run", "output_file")
        }
        # Required for lossless pending-draft restoration. An unsupported SDK
        # must fail node creation visibly, allowing its saved-value proxy,
        # rather than silently discarding a document during later hydration.
        _install_bash_initial_value_admission(self.engine)
        _install_bash_snapshot_header_read(self.engine)
        try:
            _install_bash_creation_observer(self.engine)
        except (AttributeError, RuntimeError):
            # Older hosts can still prepare a source through the explicit selector.
            pass
        self._publish_header()

    def _add_editor_parameters(self) -> None:
        with ParameterGroup(name="canvas_details", ui_options={"collapsed": True}) as details:
            Parameter(name="canvas_size", type="string", default_value="Custom",
                      allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                      traits={Options(choices=[*CANVAS_PRESETS, "Custom"])})
            for name, value in (("width", 1920), ("height", 1080)):
                Parameter(name=name, type="int", input_types=["int"], default_value=value,
                          allowed_modes=set(_DIMENSION_MODES))
            Parameter(name="background_color", type="str", default_value="#ffffff",
                      allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY}, traits={ColorPicker(format="hex")})
        self.add_node_element(details)
        self.add_parameter(ParameterList(name="input_images", default_value=None, type="ImageArtifact",
            input_types=["ImageArtifact", "ImageUrlArtifact"], allowed_modes={ParameterMode.INPUT},
            tooltip="연결된 ImageAsset 작업 공간의 이미지 목록입니다."))
        self.add_parameter(Parameter(name="output_image", type="ImageUrlArtifact",
            input_types=["ImageArtifact", "ImageUrlArtifact"], allowed_modes={ParameterMode.OUTPUT},
            ui_options={"expander": True}))
        self.add_parameter(Parameter(name="bash_image", type="JsonArtifact", allowed_modes={ParameterMode.PROPERTY},
            default_value={"value": _EMPTY_CANVAS, "name": "Canvas Project", "meta": {"input_images": [],
                "konva_json": {"images": [], "lines": []}, "viewport": {"x": 0, "y": 0, "scale": 1,
                    "center_x": 960, "center_y": 540}}},
            traits={Widget(name="HMBImageBashWidget", library="HMB_GP_Production", synced_parameters=[HEADER_PARAMETER])},
            ui_options={"display_name": "", "hide_label": True, "hide_handles": True, "is_full_width": True,
                        "height": 40, "min_height": 40, "max_height": 40, "expandable": False}))
        self.add_parameter(Parameter(name="comp_on_run", type="bool", default_value=False,
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY}))
        self._output_file = ProjectFileParameter(node=self, name="output_file", default_filename="image_bash.png")
        self._output_file.add_parameter()

    def _remote_sources(self) -> list[tuple[Any, dict]]:
        from _hmb_shot_routing import _same_flow_nodes
        _, nodes = _same_flow_nodes(self)
        result = []
        for node in nodes:
            if bool(getattr(node, "_hmb_node_deleted", False)):
                continue
            if not _hmb_is_registered_node(node, "HMBImageAssetLibrary"):
                continue
            getter = getattr(node, "_hmb_image_bash_catalog", None)
            if not callable(getter):
                continue
            catalog = getter()
            if catalog.get("schema") == "hmb-image-bash-workspace-catalog-v1":
                result.append((node, catalog))
        return result

    def _hmb_try_auto_workspace(self) -> None:
        """One fresh palette node may prepare one unambiguous same-flow source."""
        if (not getattr(self, "_hmb_auto_workspace_pending", False)
                or getattr(self, "_hmb_user_binding_interacted", False) or self._hmb_node_deleted
                or bool(getattr(self, "lock", False)) or _busy(self)):
            return
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
        from griptape_nodes.retained_mode.events.connection_events import ListConnectionsForNodeRequest
        from _hmb_shot_routing import _same_flow_nodes
        if GriptapeNodes.NodeManager().get_node_by_name(self.name) is not self:
            return
        _, nodes = _same_flow_nodes(self)
        assets = [node for node in nodes if _hmb_is_registered_node(node, "HMBImageAssetLibrary")
                  and not getattr(node, "_hmb_node_deleted", False)]
        if len(assets) > 1:
            self._hmb_auto_workspace_pending = False
            self._status("이미지 라이브러리가 여러 개입니다 · 연결할 라이브러리를 선택하세요")
            return
        if not assets:
            self._status("이미지 라이브러리를 추가하면 연결을 준비합니다")
            return
        edges = GriptapeNodes.handle_request(ListConnectionsForNodeRequest(node_name=self.name, broadcast_result=False))
        if not edges.succeeded() or edges.incoming_connections or self.get_parameter_value("image_bash_context"):
            self._hmb_auto_workspace_pending = False
            return
        project = _document(self.get_parameter_value("bash_image"))
        if (project != self._hmb_auto_pristine_project
                or any(self.get_parameter_value(name) != value
                       for name, value in self._hmb_auto_pristine_settings.items())
                or self.parameter_output_values.get("output_image") is not None):
            self._hmb_auto_workspace_pending = False
            return
        source = assets[0]
        if bool(getattr(source, "lock", False)) or _busy(source):
            # Retry after the source is available; do not even create a
            # temporary workspace in a locked or resolving library.
            return
        if not source._hmb_image_bash_catalog():
            # A just-created ImageAsset may not have adopted its initial state.
            return
        try:
            source._hmb_prepare_image_bash_workspace(self)
        except Exception as exc:
            self._hmb_auto_workspace_pending = False
            self._status("이미지 작업 공간 연결 확인: " + str(exc))
        else:
            self._hmb_auto_workspace_pending = False

    @staticmethod
    def _remote_source_instance(node: Any) -> str:
        """Transient object lease; a same-name replacement is a new source."""
        token = getattr(node, "_hmb_image_bash_live_source_uuid", "")
        if not token:
            token = str(uuid4())
            node._hmb_image_bash_live_source_uuid = token
        return token

    def _remote_bound_source(self, candidates: list[tuple[Any, dict]]) -> Any:
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
        from griptape_nodes.retained_mode.events.connection_events import ListConnectionsForNodeRequest
        result = GriptapeNodes.handle_request(ListConnectionsForNodeRequest(node_name=self.name,
                                                                           broadcast_result=False))
        if not result.succeeded():
            return None
        relevant = [edge for edge in result.incoming_connections
                    if edge.target_parameter_name in {"input_images", "image_bash_context"}
                    or edge.target_parameter_name.startswith("input_images_")]
        context = self.get_parameter_value("image_bash_context") or {}
        for node, catalog in candidates:
            expected = {("IMAGE_BASH_IMAGES_OUT", "input_images"),
                        ("IMAGE_BASH_CONTEXT_OUT", "image_bash_context")}
            actual = {(edge.source_parameter_name, edge.target_parameter_name) for edge in relevant
                      if edge.source_node_name == node.name}
            if (len(relevant) == 2 and actual == expected and any(
                row["workspace_id"] == context.get("workspace_id")
                for row in catalog.get("workspaces", []))):
                return node
        return None

    def _editor_preparation(self, context: Any, sources: list[tuple[Any, dict]], bound: Any) -> dict:
        """Small readiness projection; never read pixels or mutate the scene here.

        ImageAsset may retain the previous records while checking a new
        revision. Requested counts come from its current catalog/context, not
        those retained records. Browser decoding is a separate modal stage.
        """
        context = context if isinstance(context, dict) else {}
        metadata = self.metadata if isinstance(self.metadata, dict) else {}
        workspace = str(metadata.get("hmb_image_bash_workspace_id") or context.get("workspace_id") or "")
        catalog = next((value for node, value in sources if node is bound), {})
        requested = next((row for row in catalog.get("workspaces", []) if row.get("workspace_id") == workspace), {})
        def integer(value: Any) -> int | None:
            return value if type(value) is int and value >= 0 else None
        context_revision = integer(context.get("revision"))
        revision = integer(requested.get("revision"))
        if revision is None:
            revision = context_revision if context_revision is not None else 0
        count = integer(requested.get("count"))
        if count is None:
            count = integer(context.get("requested_count"))
        records = context.get("records")
        records = records if isinstance(records, list) else []
        phase, error = "idle", ""
        meta, hmb = {}, {}
        prepared = 0
        if workspace:
            phase = "preparing"
            if context.get("ready") is False:
                if context.get("preparation_phase") == "error":
                    phase, error = "error", str(context.get("error") or "이미지 원본을 확인할 수 없습니다.")
            elif context.get("schema") == CONTEXT_SCHEMA and context_revision == revision:
                if self._hmb_prepare_phase == "error":
                    phase, error = "error", self._hmb_prepare_error
                elif self._hmb_prepare_phase == "ready":
                    try:
                        project = _document(self.get_parameter_value("bash_image"))
                        meta = project.get("meta", {})
                        hmb = meta.get("hmb_image_bash", {}) if isinstance(meta, dict) else None
                        if not isinstance(hmb, dict):
                            raise ValueError("Invalid editor metadata")
                    except (TypeError, ValueError, AttributeError):
                        phase, error, hmb = "error", "편집기 장면 정보를 확인할 수 없습니다. 입력을 다시 확인하세요.", {}
                    actual = [_url(item) for item in _flatten(self.get_parameter_value("input_images"))]
                    expected = [str(row.get("url", "")) for row in records if isinstance(row, dict)]
                    if (phase != "error" and context.get("workspace_id") == workspace and len(expected) == len(records) and actual == expected
                            and (count is None or count == len(records))
                            and hmb.get("workspace_id") == workspace and hmb.get("workspace_revision") == revision
                            and hmb.get("channel_uuid") == metadata.get("hmb_image_bash_channel_uuid")
                            and hmb.get("node_instance_uuid") == self._remote_source_instance(self)
                            and isinstance(hmb.get("prepared_source_hashes"), dict)):
                        phase, prepared = "ready", len(records)
                        if count is None:
                            count = prepared
        snapshot = hmb.get("editor_snapshot_id", "")
        if (not isinstance(snapshot, str) or snapshot != getattr(self, "_hmb_editor_snapshot_id", "")):
            snapshot = ""
        commit = meta.get("created_at") if isinstance(meta, dict) else None
        return {"schema": PREPARATION_SCHEMA, "phase": phase, "ready": phase in {"idle", "ready"},
            "workspace_id": workspace, "workspace_revision": revision,
            "channel_uuid": str(metadata.get("hmb_image_bash_channel_uuid") or ""),
            "node_instance_uuid": self._remote_source_instance(self), "requested_count": count,
            "prepared_count": prepared, "error": error[:1024],
            "editor_snapshot_id": snapshot, "editor_commit": commit if isinstance(commit, str) else None}

    def _publish_header(self) -> bool:
        if getattr(self, "_hmb_header_publishing", True):
            return False
        self._hmb_header_publishing = True
        try:
            sources = self._remote_sources()
            bound = self._remote_bound_source(sources)
            context = self.get_parameter_value("image_bash_context") or {}
            self._queue_saved_editor_readiness(context, sources, bound)
            preparation = self._editor_preparation(context, sources, bound)
            projection = {"schema": "hmb-image-bash-header-v1", "sources": [
                {"id": node.name, "label": f"{node.name} · {workspace.get('name', 'HMBImageBash')}",
                 "workspace_id": workspace["workspace_id"]}
                for node, catalog in sources for workspace in (catalog.get("workspaces") or
                    [{"workspace_id": _PREPARE_WORKSPACE, "name": "새 이미지 작업 공간"}])],
                "source_instances": {node.name: self._remote_source_instance(node)
                    for node, catalog in sources},
                "bound_source": bound.name if bound else "",
                "image_count": (preparation["requested_count"] if preparation["requested_count"] is not None
                                else len(context.get("records", []))), "preparation": preparation,
                "status": self.get_parameter_value("HMB_BASH_STATUS") or "이미지 라이브러리를 선택하세요",
                # Execution state is transient; the native widget disabled prop
                # owns it. Persisting RESOLVING here can strand the selector.
                "locked": bool(getattr(self, "lock", False)),
                "route": {"connected": bound is not None, "source_node_name": bound.name if bound else "",
                    "target_node_name": self.name, "source_parameter": "IMAGE_BASH_IMAGES_OUT",
                    "context_source_parameter": "IMAGE_BASH_CONTEXT_OUT"}}
            if self.get_parameter_value(HEADER_PARAMETER) != projection:
                self.set_parameter_value(HEADER_PARAMETER, projection)
                self.publish_update_to_parameter(HEADER_PARAMETER, projection)
            # Native Get gives a serialized output cache precedence over the
            # property map. Do not let a saved UI-only cache hide this header.
            if HEADER_PARAMETER in self.parameter_output_values:
                self.parameter_output_values[HEADER_PARAMETER] = projection
            return True
        except Exception:
            # Native construction/restoration precedes registration in a flow.
            # Refresh and the next input update retry once registration exists.
            return False
        finally:
            self._hmb_header_publishing = False

    def _queue_saved_editor_readiness(self, context: Any, sources: list[tuple[Any, dict]], bound: Any) -> None:
        """Initial SDK hydration skips callbacks; verify a saved Apply on a tick.

        Header projection remains metadata-only. The existing restore verifier
        performs source/receipt/PNG checks after registration and real input
        connections are available, without Run or new rendering/writing.
        """
        recovery = getattr(self, "_hmb_cold_gap_recovery", None)
        recover_gap = self._hmb_prepare_phase == "error" and isinstance(recovery, dict)
        if ((self._hmb_prepare_phase != "idle" and not recover_gap) or bound is None or not isinstance(context, dict)
                or context.get("schema") != CONTEXT_SCHEMA or context.get("ready") is not True
                or getattr(self, "_hmb_cold_readiness_scheduled", False)
                or self._hmb_node_deleted or not _hmb_is_registered_node(self, "HMBImageBash")):
            return
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
        if GriptapeNodes.NodeManager().get_node_by_name(self.name) is not self:
            return
        try:
            project = _document(self.get_parameter_value("bash_image"))
        except (TypeError, ValueError, AttributeError):
            self._hmb_prepare_phase = "error"
            self._hmb_prepare_error = "편집기 장면 정보를 확인할 수 없습니다. 저장본을 확인하세요."
            return
        meta = project.get("meta", {})
        hmb = meta.get("hmb_image_bash", {}) if isinstance(meta, dict) else {}
        if not isinstance(hmb, dict):
            self._hmb_prepare_phase = "error"
            self._hmb_prepare_error = "편집기 장면 정보 형식이 올바르지 않습니다. 저장본을 확인하세요."
            return
        receipt = hmb.get("apply") if isinstance(hmb, dict) else None
        retained = isinstance(receipt, dict) and bool(receipt)
        pending = hmb.get("pending_apply")
        saved_draft = (isinstance(pending, dict) and pending.get("schema") == "hmb-image-bash-pending-apply-v1"
                       and isinstance(pending.get("editor_commit"), str) and bool(pending["editor_commit"])
                       and pending.get("editor_commit") == meta.get("created_at"))
        preparing = hmb.get("pending_prepare")
        scope = self._apply_scope()
        saved_preparing = (isinstance(preparing, dict)
            and preparing.get("schema") == "hmb-image-bash-pending-prepare-v1"
            and preparing.get("scope") == {key: scope[key] for key in ("workspace_id", "channel_uuid", "workspace_revision")}
            and isinstance(preparing.get("source_uids"), list)
            and all(isinstance(uid, str) and uid for uid in preparing["source_uids"]))
        if preparing is not None and not saved_preparing:
            self._hmb_prepare_phase, self._hmb_prepare_error = "error", "저장된 입력 준비 정보가 현재 연결과 다릅니다."
            return
        if pending is not None and not saved_draft:
            self._hmb_prepare_phase, self._hmb_prepare_error = "error", "저장된 Apply 대기 정보가 올바르지 않습니다."
            return
        valid_digest = lambda value: (isinstance(value, str) and len(value) == 64
                                      and all(char in "0123456789abcdef" for char in value))
        if retained and (receipt.get("schema") != RECEIPT_SCHEMA
                         or not isinstance(receipt.get("editor_commit"), str) or not receipt["editor_commit"]
                         or (receipt.get("editor_commit") != meta.get("created_at") and not (saved_draft or saved_preparing))
                         or not all(valid_digest(receipt.get(key)) for key in ("scene_sha256", "png_sha256", "rgba_sha256"))
                         or any(type(receipt.get(key)) is not int or receipt[key] <= 0 for key in ("width", "height"))
                         or not isinstance(receipt.get("source_hashes"), dict)
                         or not isinstance(receipt.get("png_base64"), str) or not receipt["png_base64"]):
            self._hmb_prepare_phase = "error"
            self._hmb_prepare_error = "저장된 Apply 검증 정보가 올바르지 않습니다. 저장본을 확인하세요."
            return
        if saved_draft or saved_preparing:
            # The editor closed while validation was pending. Preserve the new
            # scene and the old embedded receipt/PNG as a draft, never approval.
            retained = False
        if (not scope["workspace_id"] or not scope["channel_uuid"]
                or self.metadata.get("hmb_image_bash_workspace_id") != scope["workspace_id"]
                or (not saved_preparing and any(key in hmb and hmb[key] != scope[key]
                       for key in ("workspace_id", "channel_uuid", "workspace_revision")))):
            self._hmb_prepare_phase = "error"
            self._hmb_prepare_error = "저장된 작업 공간·연결·입력 버전이 현재 상태와 다릅니다. 연결을 확인하세요."
            return
        catalog = next((value for node, value in sources if node is bound), {})
        current = next((row for row in catalog.get("workspaces", [])
                        if row.get("workspace_id") == scope["workspace_id"]), {})
        if current.get("revision") != scope["workspace_revision"]:
            return
        try:
            records = self._records()
        except (TypeError, ValueError):
            return
        if current.get("count") != len(records):
            return
        if saved_preparing and preparing["source_uids"] != [row["source_uid"] for row in records]:
            self._hmb_prepare_phase, self._hmb_prepare_error = "error", "저장된 입력 준비의 이미지 ID가 현재 목록과 다릅니다."
            return
        try:
            prior_scope = {**scope, "node_instance_uuid": hmb.get("node_instance_uuid")}
            if not saved_preparing:
                self._validate_apply_source_bindings(project, records, expected_scope=prior_scope)
            if retained and receipt["scene_sha256"] != scene_fingerprint(project, records, self._canvas()):
                # A changed authored scene/source list is a saved draft. Keep
                # its old receipt untouched and never publish its old pixels.
                retained = False
        except (TypeError, ValueError) as exc:
            self._hmb_prepare_phase, self._hmb_prepare_error = "error", str(exc)
            self._hmb_cold_gap_recovery = None
            return
        if recover_gap:
            # Connection reconstruction can pass empty source values before
            # initial saved assignments. Only that pristine gap, followed by
            # a real initial saved Apply, can enter the existing verifier once.
            self._hmb_cold_gap_recovery = None
            self._hmb_cold_input_gap = False
            if (not retained or saved_draft or saved_preparing
                    or recovery.get("epoch") != self._hmb_apply_epoch
                    or recovery.get("identity") != self._cold_gap_saved_identity(project)
                    or self._hmb_last_output is not None):
                return
        self._hmb_prepare_phase, self._hmb_prepare_error = "preparing", ""
        self._hmb_restore_pending = retained
        self._hmb_cold_readiness_scheduled = True
        epoch, source_instance = self._hmb_apply_epoch, self._remote_source_instance(bound)
        def complete() -> None:
            try:
                self._complete_cold_editor_readiness(scope, bound, source_instance, epoch, retained)
            finally:
                self._hmb_cold_readiness_scheduled = False
        if not self._schedule_host_callback(complete):
            self._hmb_cold_readiness_scheduled = False
            self._hmb_prepare_phase = "error"
            self._hmb_prepare_error = "저장본 준비에 필요한 호스트 이벤트 루프를 확인하세요."

    @hmb_binding_mutation
    def _complete_cold_editor_readiness(self, scope: dict, source: Any, source_instance: str,
                                      epoch: int, retained: bool) -> None:
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
        if (self._hmb_node_deleted or epoch != self._hmb_apply_epoch
                or not _hmb_is_registered_node(self, "HMBImageBash")
                or GriptapeNodes.NodeManager().get_node_by_name(self.name) is not self):
            return
        try:
            if self._apply_scope() != scope or self.metadata.get("hmb_image_bash_workspace_id") != scope["workspace_id"]:
                raise ValueError("작업 공간이 변경되어 저장본 준비를 중단했습니다. 연결을 확인하세요.")
            sources = self._remote_sources()
            if self._remote_bound_source(sources) is not source or self._remote_source_instance(source) != source_instance:
                raise ValueError("이미지 연결이 변경되어 저장본 준비를 중단했습니다. 연결을 확인하세요.")
            catalog = next((value for node, value in sources if node is source), {})
            current = next((row for row in catalog.get("workspaces", [])
                            if row.get("workspace_id") == scope["workspace_id"]), {})
            records = self._records()
            if current.get("revision") != scope["workspace_revision"] or current.get("count") != len(records):
                raise ValueError("이미지 입력 버전이 변경되었습니다. 입력 준비를 다시 확인하세요.")
            project = _document(self.get_parameter_value("bash_image"))
            if retained:
                self._restore_saved_output(project, records)
                if self._hmb_cold_restore_pending is not None:
                    return
                if self._hmb_prepare_phase != "ready":
                    raise ValueError(str(self.get_parameter_value("HMB_BASH_STATUS") or "저장된 Apply를 확인하지 못했습니다."))
            else:
                self._sync_metadata_with_input_images(force_draft=True)
        except Exception as exc:
            self._hmb_prepare_phase, self._hmb_prepare_error = "error", str(exc)
            self._status("저장본 준비 실패: " + str(exc))

    def _header_command(self, value: Any) -> None:
        request = value.get("hmb_image_bash_command", {}) if isinstance(value, dict) else {}
        try:
            operation = request.get("operation")
            if operation == "refresh":
                # Source discovery is presentation-only. Re-reading rasters or
                # syncing the scene here would turn every topology/focus event
                # into an edit, invalidating a retained Apply unnecessarily.
                # Input changes, Apply and Run retain their full validation.
                self._hmb_try_auto_workspace()
                return
            if operation == "retry_inputs":
                if bool(getattr(self, "lock", False)) or _busy(self):
                    raise ValueError("노드 실행을 마치고 편집 잠금을 해제하세요.")
                sources = self._remote_sources()
                source = self._remote_bound_source(sources)
                context = self.get_parameter_value("image_bash_context") or {}
                if (source is None or request.get("source_node_name") != source.name
                        or request.get("workspace_id") != context.get("workspace_id")
                        or request.get("source_instance_id") != self._remote_source_instance(source)):
                    raise ValueError("리모트 작업 공간이 변경되었습니다. 현재 연결을 다시 확인하세요.")
                retry = getattr(source, "_hmb_retry_image_bash_inputs", None)
                if not callable(retry):
                    raise ValueError("이미지 라이브러리에서 원본을 다시 확인하세요.")
                self._hmb_prepare_phase, self._hmb_prepare_error = "preparing", ""
                self._status("작업 준비 중 · 이미지 원본을 다시 확인합니다")
                intent = {"source": source, "workspace_id": context["workspace_id"],
                          "channel_uuid": self.metadata.get("hmb_image_bash_channel_uuid")}
                self._hmb_snapshot_republish_pending = intent
                try:
                    retry(self, context["workspace_id"])
                    self._sync_metadata_with_input_images()
                except Exception:
                    if self._hmb_snapshot_republish_pending is intent:
                        self._hmb_snapshot_republish_pending = None
                    raise
                return
            if operation not in {"bind", "unbind"}:
                raise ValueError("지원하지 않는 리모트 연결 요청입니다.")
            self._hmb_user_binding_interacted = True
            self._hmb_auto_workspace_pending = False
            if bool(getattr(self, "lock", False)) or _busy(self):
                raise ValueError("노드 실행을 마치고 편집 잠금을 해제하세요.")
            sources = self._remote_sources()
            old = self._remote_bound_source(sources)
            old_context = deepcopy(self.get_parameter_value("image_bash_context") or {})
            if operation == "unbind":
                if old is None:
                    raise ValueError("검증된 리모트 연결이 없습니다. 기존 연결을 확인하세요.")
                if ("source_instance_id" in request
                        and request["source_instance_id"] != self._remote_source_instance(old)):
                    raise ValueError("이미지 라이브러리가 교체되었습니다. 목록에서 다시 선택하세요.")
                if ("workspace_id" in request and request["workspace_id"] != old_context.get("workspace_id")):
                    raise ValueError("Image Bash 작업 공간이 변경되었습니다. 연결을 다시 확인하세요.")
                old._hmb_bind_image_bash_workspace(self, old_context["workspace_id"], enabled=False)
                return
            selected = next((node for node, catalog in sources if node.name == request.get("source_node_name")
                and (any(row["workspace_id"] == request.get("workspace_id") for row in catalog.get("workspaces", []))
                     or (not catalog.get("workspaces") and request.get("workspace_id") == _PREPARE_WORKSPACE))), None)
            if selected is None:
                raise ValueError("선택한 이미지 라이브러리 작업 공간을 다시 확인하세요.")
            # Legacy direct commands have no lease. The current widget always
            # carries this transient projection token, so a delayed selection
            # cannot silently bind a new object with the old name/workspace.
            if ("source_instance_id" in request
                    and request["source_instance_id"] != self._remote_source_instance(selected)):
                raise ValueError("이미지 라이브러리가 교체되었습니다. 목록에서 다시 선택하세요.")
            if request.get("workspace_id") == _PREPARE_WORKSPACE:
                if old:
                    raise ValueError("현재 리모트 연결을 먼저 해제하세요.")
                selected._hmb_prepare_image_bash_workspace(self)
                return
            if old is selected and old_context.get("workspace_id") == request.get("workspace_id"):
                return
            if old:
                old._hmb_bind_image_bash_workspace(self, old_context["workspace_id"], enabled=False)
            try:
                selected._hmb_bind_image_bash_workspace(self, request["workspace_id"], enabled=True)
            except Exception:
                if old:
                    old._hmb_bind_image_bash_workspace(self, old_context["workspace_id"], enabled=True)
                raise
            if self.get_parameter_value("HMB_BASH_STATUS") == "REMOTE 연결 해제 · 편집 내용은 유지됩니다":
                self._status("REMOTE 연결됨 · Run에서 저장된 Apply를 확인합니다")
        except Exception as exc:
            self._status("REMOTE 연결 확인: " + str(exc))
        finally:
            self._publish_header()

    def _status(self, text: str) -> None:
        self.set_parameter_value("HMB_BASH_STATUS", text)
        self.parameter_output_values["HMB_BASH_STATUS"] = text
        self.publish_update_to_parameter("HMB_BASH_STATUS", text)
        self._publish_header()

    def _clear_output(self, *, preserve_initial_gap: bool = False) -> None:
        if not preserve_initial_gap:
            self._hmb_cold_input_gap = False
            self._hmb_cold_gap_recovery = None
        self._hmb_apply_epoch += 1
        if preserve_initial_gap and isinstance(getattr(self, "_hmb_cold_gap_recovery", None), dict):
            self._hmb_cold_gap_recovery["epoch"] = self._hmb_apply_epoch
        self._hmb_apply_pending = None
        self._hmb_prepare_pending = None
        self._hmb_cold_restore_pending = None
        self._hmb_apply_rollback_document = None
        work = getattr(self, "_hmb_apply_work", None)
        if isinstance(work, dict):
            with work["lock"]:
                work["queued"] = None
                work["completed"] = None
        epoch = self._hmb_apply_epoch
        if self._hmb_value_callback_depth:
            if not self._schedule_host_callback(lambda: self._clear_output_now() if epoch == self._hmb_apply_epoch and not self._hmb_node_deleted else None):
                self._status("입력 변경 대기 · 호스트 이벤트 루프를 확인하세요")
            return
        self._clear_output_now()

    @hmb_binding_mutation
    def _clear_output_now(self, *, preserve_verification: bool = False) -> None:
        self._hmb_output_generation += 1
        self._hmb_output_delivered = {}
        # Invalidate the source locally without retracting a previously
        # imported completed asset from downstream libraries.
        self.set_parameter_value("output_image", None, emit_change=False)
        self.parameter_output_values["output_image"] = None
        self.publish_update_to_parameter("output_image", None)
        if not preserve_verification:
            self.set_parameter_value("HMB_BASH_VERIFICATION", {})
            self.parameter_output_values["HMB_BASH_VERIFICATION"] = {}

    @staticmethod
    def _schedule_host_callback(callback: Any) -> bool:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            try:
                from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
                loop = GriptapeNodes.EventManager().event_loop
            except Exception:
                loop = None
        if loop is None or not loop.is_running():
            return False
        loop.call_soon_threadsafe(callback)
        return True

    def _propagate_output(self, value: Any, generation: int) -> bool:
        """Deliver an Apply result through real edges without executing targets."""
        if self._hmb_output_propagating or self._hmb_node_deleted:
            return False
        from griptape_nodes.retained_mode.events.connection_events import ListConnectionsForNodeRequest, ListConnectionsForNodeResultSuccess
        from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest, SetParameterValueResultSuccess
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
        try:
            if GriptapeNodes.NodeManager().get_node_by_name(self.name) is not self:
                return True
        except Exception:
            return True
        self._hmb_output_propagating = True
        try:
            found = GriptapeNodes.handle_request(ListConnectionsForNodeRequest(node_name=self.name, broadcast_result=False))
            if not isinstance(found, ListConnectionsForNodeResultSuccess):
                raise RuntimeError("Image Bash 출력 연결을 확인하지 못했습니다.")
            parameter = self.get_parameter_by_name("output_image")
            data_type = getattr(parameter, "output_type", None) or getattr(parameter, "type", None)
            targets = {}
            for edge in found.outgoing_connections:
                if edge.source_parameter_name == "output_image":
                    target = (edge.target_node_name, edge.target_parameter_name)
                    try:
                        targets[target] = GriptapeNodes.NodeManager().get_node_by_name(target[0])
                    except Exception:
                        targets[target] = None
            seen = set()
            complete = True
            for edge in found.outgoing_connections:
                if self._hmb_node_deleted or generation != self._hmb_output_generation:
                    return False
                if edge.source_parameter_name != "output_image":
                    continue
                target = (edge.target_node_name, edge.target_parameter_name)
                if target in seen:
                    continue
                seen.add(target)
                target_node = targets.get(target)
                try:
                    current_source = GriptapeNodes.NodeManager().get_node_by_name(self.name)
                    current_target = GriptapeNodes.NodeManager().get_node_by_name(target[0])
                except Exception:
                    complete = False
                    continue
                current_edges = GriptapeNodes.handle_request(ListConnectionsForNodeRequest(node_name=self.name, broadcast_result=False))
                if not isinstance(current_edges, ListConnectionsForNodeResultSuccess):
                    raise RuntimeError("Image Bash 출력 연결을 확인하지 못했습니다.")
                still_connected = any(item.source_parameter_name == "output_image"
                    and item.target_node_name == target[0] and item.target_parameter_name == target[1]
                    for item in current_edges.outgoing_connections)
                if current_source is not self or current_target is not target_node or not still_connected:
                    complete = False
                    continue
                if (target_node is None or bool(getattr(target_node, "_hmb_node_deleted", False))
                        or bool(getattr(target_node, "lock", False)) or _busy(target_node)):
                    complete = False
                    continue
                if self._hmb_output_delivered.get(target) is target_node:
                    continue
                result = GriptapeNodes.handle_request(SetParameterValueRequest(
                    node_name=target[0], parameter_name=target[1], value=value, data_type=data_type,
                    incoming_connection_source_node_name=self.name,
                    incoming_connection_source_parameter_name="output_image"))
                if not isinstance(result, SetParameterValueResultSuccess):
                    raise RuntimeError("Image Bash 이미지를 연결된 입력에 전달하지 못했습니다: " + str(getattr(result, "result_details", "")))
                if generation == self._hmb_output_generation:
                    self._hmb_output_delivered[target] = target_node
            return complete and generation == self._hmb_output_generation and not self._hmb_node_deleted
        finally:
            self._hmb_output_propagating = False

    def _records(self) -> list[dict]:
        context = self.get_parameter_value("image_bash_context") or {}
        if not isinstance(context, dict) or context.get("schema") != CONTEXT_SCHEMA:
            raise ValueError("ImageAsset Library의 Image Bash 탭을 연결하세요.")
        if not context.get("workspace_id"):
            raise ValueError("Image Bash workspace_id is missing.")
        if context.get("ready", True) is not True:
            raise ValueError("ImageAsset 이미지를 준비하지 못했습니다. 누락된 원본을 확인하세요.")
        records = deepcopy(context.get("records", []))
        if not isinstance(records, list) or any(not isinstance(row, dict) for row in records):
            raise ValueError("Invalid ImageAsset source records.")
        actual = [_url(item) for item in _flatten(self.get_parameter_value("input_images"))]
        if actual != [str(row.get("url", "")) for row in records]:
            raise ValueError("이미지 목록과 ImageAsset 작업 공간 동기화를 기다리는 중입니다.")
        return records

    def _canvas(self) -> dict:
        context = self.get_parameter_value("image_bash_context") or {}
        return {"width": int(self.get_parameter_value("width")),
                "height": int(self.get_parameter_value("height")),
                "background_color": self.get_parameter_value("background_color"),
                "workspace_id": context.get("workspace_id") if isinstance(context, dict) else None}

    def _set_project(self, project: dict) -> None:
        # A small host-owned coherence token lets the native launcher use its
        # already-delivered document, avoiding another multi-MB RPC read.
        # HMB metadata is excluded from the rendered scene/receipt fingerprint.
        project = deepcopy(project)
        snapshot = str(uuid4())
        project.setdefault("meta", {}).setdefault("hmb_image_bash", {})["editor_snapshot_id"] = snapshot
        previous = self._hmb_syncing
        self._hmb_syncing = True
        try:
            # One explicit UI publication below is sufficient. Lifecycle
            # emission here would serialize the same multi-MB saved Apply
            # document again; hooks/storage still run with emit_change=False.
            self.set_parameter_value("bash_image", project, emit_change=False)
            self._hmb_editor_snapshot_id = snapshot
            self._publish_header()
            self.publish_update_to_parameter("bash_image", project)
        finally:
            self._hmb_syncing = previous

    def _sync_project(self, project: dict, records: list[dict], *, add_missing: bool = True) -> dict:
        canvas = self._canvas()
        # file:// launches the native editor's lossy preview conversion. Mint
        # the original-file URL through the SDK's existing local storage driver
        # so the canvas receives full-quality source bytes, on Windows/UNC too.
        editor_records = self._editor_records(records)
        def dimensions(url):
            with Image.open(BytesIO(_read_bytes(url))) as image:
                return image.size

        def create(record, index):
            return _editor_layer(record, index, canvas, dimensions)
        updated = sync_scene(project, editor_records, create, add_missing=add_missing)
        meta = updated.setdefault("meta", {})
        meta["hmb_canvas"] = {key: canvas[key] for key in ("width", "height", "background_color")}
        hmb = meta.setdefault("hmb_image_bash", {})
        hmb.update(self._apply_scope())
        return updated

    @staticmethod
    def _editor_records(records: list[dict]) -> list[dict]:
        editor_records = deepcopy(records)
        for record in editor_records:
            url = record.get("url", "")
            if url.startswith("file:") or Path(url).is_absolute():
                from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
                from griptape_nodes.drivers.storage.local_storage_driver import LocalStorageDriver
                driver = GriptapeNodes.StaticFilesManager().storage_driver
                if not isinstance(driver, LocalStorageDriver):
                    raise ValueError("ImageAsset 원본을 제공할 로컬 파일 서비스를 확인하세요.")
                record["url"] = driver.create_signed_download_url(Path(File(url).resolve()))
        return editor_records

    def _sync_metadata_with_input_images(self, *, force_draft: bool = False) -> None:
        if self._hmb_syncing or getattr(self, "_initializing", False):
            return
        context = self.get_parameter_value("image_bash_context") or {}
        self._hmb_cold_gap_recovery = None
        self._hmb_cold_input_gap = False
        cached = self._hmb_last_output
        if isinstance(context, dict) and context.get("ready") is False:
            # Keep the previously completed result while this workspace is
            # revalidated. _records still rejects Run and new Apply until the
            # producer publishes ready=True; no old result is re-emitted.
            self._hmb_inputs_unready = True
            self._hmb_prepare_phase = "error" if context.get("preparation_phase") == "error" else "preparing"
            self._hmb_prepare_error = str(context.get("error") or "") if self._hmb_prepare_phase == "error" else ""
            if isinstance(cached, dict) and context.get("workspace_id") != cached.get("workspace_id"):
                self._clear_output()
            self._status(self._hmb_prepare_error or "작업 준비 중 · 이미지 원본 확인 대기")
            return
        self._hmb_inputs_unready = False
        self._hmb_prepare_phase, self._hmb_prepare_error = "preparing", ""
        try:
            records = self._records()
            project = _document(self.get_parameter_value("bash_image"))
            if self._queue_prepare(project, records, force_draft=force_draft):
                return
            updated = self._sync_project(project, records)
            hmb = updated.setdefault("meta", {}).setdefault("hmb_image_bash", {})
            if updated != project or "prepared_source_hashes" not in hmb:
                hmb["prepared_source_hashes"] = self._source_hashes(updated)
            if updated != project:
                self._set_project(updated)
            self._hmb_prepare_phase = "ready"
            receipt = updated.get("meta", {}).get("hmb_image_bash", {}).get("apply")
            if force_draft or not receipt or receipt.get("scene_sha256") != scene_fingerprint(updated, records, self._canvas()):
                self._clear_output()
                self._status("입력이 변경되었습니다 · 편집기에서 Apply 필요")
            elif self._hmb_restore_pending:
                self._schedule_restore()
            elif receipt and self._hmb_last_output and not self._hmb_output_pending:
                self._status("Apply 저장 및 이미지 출력 완료")
        except Exception as exc:
            pristine_gap = (not isinstance(context, dict) or context.get("schema") != CONTEXT_SCHEMA)
            if pristine_gap:
                try:
                    pristine_gap = (self._hmb_last_output is None and self._hmb_apply_pending is None
                        and self._hmb_prepare_pending is None and self._hmb_cold_restore_pending is None
                        and _document(self.get_parameter_value("bash_image")) == self._hmb_auto_pristine_project
                        and not getattr(self, "_hmb_cold_gap_admitted", False))
                except (AttributeError, TypeError, ValueError):
                    pristine_gap = False
            actual = [_url(item) for item in _flatten(self.get_parameter_value("input_images"))]
            records = context.get("records") if isinstance(context, dict) else None
            staging = (isinstance(records, list) and all(isinstance(row, dict) for row in records)
                       and actual != [str(row.get("url", "")) for row in records])
            self._hmb_prepare_phase = "preparing" if staging else "error"
            self._hmb_prepare_error = "" if staging else str(exc)
            self._clear_output()
            self._hmb_cold_input_gap = pristine_gap
            self._status(str(exc))
        finally:
            self._publish_header()

    def _handle_input_images_change(self, value: Any) -> None:
        self._sync_metadata_with_input_images()

    def _handle_input_images_removed(self) -> None:
        self._sync_metadata_with_input_images()

    def _queue_prepare(self, project: dict, records: list[dict], *, force_draft: bool = False) -> bool:
        """Snapshot graph state; defer dimensions and all-raster checks off host."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return False
        from griptape_nodes.retained_mode.engine import has_current_engine
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
        if (not has_current_engine() or not loop.is_running()
                or GriptapeNodes.NodeManager().get_node_by_name(self.name) is not self):
            return False
        canvas, scope = self._canvas(), self._apply_scope()
        connections = self._apply_connection_lease()
        republish = getattr(self, "_hmb_snapshot_republish_pending", None)
        if republish is not None and (republish["workspace_id"] != scope["workspace_id"]
                or republish["channel_uuid"] != scope["channel_uuid"]
                or not any(edge[0] is republish["source"] for edge in connections)):
            self._hmb_snapshot_republish_pending = republish = None
        apply = self._hmb_apply_pending
        if apply is not None and not force_draft and republish is None and self._apply_task_current(apply):
            # Resolving the upstream node may re-publish the identical input
            # while Apply is pending. It must not cancel that accepted edit.
            self._hmb_prepare_phase, self._hmb_prepare_error = "ready", ""
            return True
        preparing = self._hmb_prepare_pending
        if (preparing is not None and self._apply_task_current(preparing)
                and (not force_draft or preparing.get("force_draft"))
                and preparing.get("republish_snapshot") is republish):
            return True
        editor_records = self._editor_records(records)
        read_paths = self._snapshot_read_paths(project, records=editor_records)
        if read_paths is None:
            return False
        # Keep old geometry/brushes and completed PNG while the newest source
        # list is checked. This marker authorizes no output; cold restoration
        # revalidates the actual source list and reconciles it as a draft.
        hmb = project.setdefault("meta", {}).setdefault("hmb_image_bash", {})
        if (any(hmb.get(key) != scope[key] for key in ("workspace_id", "channel_uuid", "workspace_revision"))
                or [row.get("source_uid") for row in hmb.get("source_bindings", [])]
                    != [row["source_uid"] for row in records]):
            hmb["pending_prepare"] = {"schema": "hmb-image-bash-pending-prepare-v1",
                "scope": {key: scope[key] for key in ("workspace_id", "channel_uuid", "workspace_revision")},
                "source_uids": [row["source_uid"] for row in records]}
            self._set_project(project)
        self._hmb_apply_epoch += 1
        self._hmb_apply_pending = None
        self._hmb_cold_restore_pending = None
        self._hmb_apply_rollback_document = None
        task = {"kind": "prepare", "epoch": self._hmb_apply_epoch, "project": deepcopy(project),
            "force_draft": force_draft,
            "republish_snapshot": republish,
            "records": deepcopy(records), "editor_records": editor_records,
            "canvas": canvas, "scope": scope, "read_paths": read_paths,
            "read_drivers": self._snapshot_driver_lease(read_paths),
            "scene": scene_fingerprint(project, records, canvas), "png_url": _url(project),
            "context": deepcopy(self.get_parameter_value("image_bash_context") or {}),
            "connections": connections}
        self._hmb_prepare_pending = task
        self._hmb_prepare_phase, self._hmb_prepare_error = "preparing", ""
        self._status("작업 준비 중 · 이미지 원본과 편집 장면 확인")
        return self._start_snapshot_task(task, loop)

    @staticmethod
    def _calculate_prepare(task: dict, is_live) -> dict:
        rgba_cache, source_cache = OrderedDict(), {}
        read = lambda url: HMBImageBash._snapshot_read(task, url)
        # Hash/decode each URL once in this stage. A new layer obtains its
        # dimensions from the same verified raster, never a fallback 400x300.
        def dimensions(url):
            probe = {"meta": {"input_images": [{"id": "dimensions", "url": url}]}}
            info = HMBImageBash._source_hashes(None, probe, cache=source_cache,
                rgba_cache=rgba_cache, is_live=is_live, read_bytes=read)["input:dimensions"]
            return info["width"], info["height"]
        def create(record, index):
            return _editor_layer(record, index, task["canvas"], dimensions)
        updated = sync_scene(task["project"], task["editor_records"], create)
        meta = updated.setdefault("meta", {})
        meta["hmb_canvas"] = {key: task["canvas"][key] for key in ("width", "height", "background_color")}
        hmb = meta.setdefault("hmb_image_bash", {})
        hmb.update(task["scope"])
        hmb.pop("pending_prepare", None)
        hashes = HMBImageBash._source_hashes(None, updated, cache=source_cache,
            rgba_cache=rgba_cache, is_live=is_live, read_bytes=read)
        hmb["prepared_source_hashes"] = hashes
        if not is_live():
            raise ValueError("새 입력으로 이전 이미지 준비가 취소되었습니다.")
        return {"project": updated, "rgba_cache": rgba_cache, "hashes": hashes}

    @hmb_binding_mutation
    def _finish_prepare(self, task: dict, result: dict) -> bool:
        if not self._apply_task_current(task):
            self._discard_apply_task(task)
            return False
        if not result.get("error"):
            try:
                current_hashes = self._source_hashes(result["project"], rgba_cache=result["rgba_cache"])
                if current_hashes != result["hashes"]:
                    raise _ImageBashSourceError("준비 중 이미지 원본이 변경되었습니다. 다시 준비하세요.")
            except Exception as exc:
                result = {"error": str(exc)}
        if not self._apply_task_current(task):
            self._discard_apply_task(task)
            return False
        self._hmb_prepare_pending = None
        if result.get("error"):
            self._hmb_prepare_phase, self._hmb_prepare_error = "error", result["error"]
            self._status("입력 준비 실패: " + result["error"] + " · 기존 편집과 완료 결과는 유지됩니다. 다시 준비하세요.")
            return False
        current = _document(self.get_parameter_value("bash_image"))
        updated = result["project"]
        if "viewport" in current.get("meta", {}):
            updated["meta"]["viewport"] = deepcopy(current["meta"]["viewport"])
        else:
            updated["meta"].pop("viewport", None)
        for key in ("id", "reference"):
            if key in current:
                updated[key] = deepcopy(current[key])
            else:
                updated.pop(key, None)
        snapshot = getattr(self, "_hmb_editor_snapshot_id", "")
        republish = task.get("republish_snapshot")
        force_snapshot = republish is not None and republish is getattr(self, "_hmb_snapshot_republish_pending", None)
        if (force_snapshot or updated != current or not snapshot
                or updated.get("meta", {}).get("hmb_image_bash", {}).get("editor_snapshot_id") != snapshot):
            self._set_project(updated)
        if force_snapshot:
            self._hmb_snapshot_republish_pending = None
        self._hmb_prepare_phase, self._hmb_prepare_error = "ready", ""
        receipt = updated.get("meta", {}).get("hmb_image_bash", {}).get("apply")
        if (task.get("force_draft") or not receipt or receipt.get("scene_sha256") != scene_fingerprint(updated, self._records(), self._canvas())
                or receipt.get("source_hashes") != result["hashes"]):
            self._clear_output()
            self._status("입력이 변경되었습니다 · 편집기에서 Apply 필요")
        elif self._hmb_restore_pending:
            self._schedule_restore()
        elif self._hmb_last_output and not self._hmb_output_pending:
            self._status("Apply 저장 및 이미지 출력 완료")
        return True

    def _flush_pending_prepare(self) -> None:
        task = getattr(self, "_hmb_prepare_pending", None)
        if task is None:
            return
        if not self._apply_task_current(task):
            self._discard_apply_task(task)
            raise ValueError("이미지 준비 중 입력이 변경되었습니다. 준비 완료 후 다시 실행하세요.")
        self._hmb_apply_epoch += 1
        task = {**task, "epoch": self._hmb_apply_epoch}
        self._hmb_prepare_pending = task
        try:
            result = self._calculate_prepare(task, lambda: not self._hmb_node_deleted and task["epoch"] == self._hmb_apply_epoch)
        except Exception as exc:
            self._finish_prepare(task, {"error": str(exc)})
            raise
        if not self._finish_prepare(task, result):
            raise ValueError("현재 이미지 원본을 준비하지 못했습니다. 상태를 확인하세요.")

    def _source_hashes(self, project: dict, *, cache: dict | None = None,
                       rgba_cache: OrderedDict | None = None, is_live=None, read_bytes=None) -> dict:
        """Read every source before committing; a missing hidden layer also fails."""
        sources = project.get("meta", {}).get("input_images", [])
        hashes = {}
        loaded = {} if cache is None else cache
        def check(url):
            if is_live is not None and not is_live():
                raise ValueError("새 입력 또는 Apply로 이전 이미지 검증이 취소되었습니다.")
            if not url:
                raise ValueError("Image Bash source URL is missing.")
            if url not in loaded:
                try:
                    raw = (read_bytes or _read_bytes)(url)
                    raw_sha = hashlib.sha256(raw).hexdigest()
                    raster = rgba_cache.get(raw_sha) if rgba_cache is not None else None
                    if raster is None:
                        with Image.open(BytesIO(raw)) as image:
                            image.load()
                            rgba = image.convert("RGBA")
                            raster = {"rgba_sha256": hashlib.sha256(rgba.tobytes()).hexdigest(),
                                "width": rgba.width, "height": rgba.height}
                except Exception as exc:
                    raise _ImageBashSourceError("이미지 원본 확인 실패: " + str(exc)) from exc
                if rgba_cache is not None and raw_sha not in rgba_cache:
                    if rgba_cache is not None:
                        # Apply-owned hashes/dimensions only; no pixels or raw
                        # bytes survive the read. Current raw SHA is mandatory.
                        rgba_cache[raw_sha] = raster
                        rgba_cache.move_to_end(raw_sha)
                        while len(rgba_cache) > 128:
                            rgba_cache.popitem(last=False)
                elif rgba_cache is not None:
                    rgba_cache.move_to_end(raw_sha)
                loaded[url] = {"sha256": raw_sha, **raster}
            return {"url_sha256": hashlib.sha256(url.encode()).hexdigest(), **loaded[url]}
        for source in sources:
            url = source.get("url", "")
            hashes["input:" + str(source["id"])] = check(url)
        # Some editor versions keep brush rasters on layers alone.
        for layer in project.get("meta", {}).get("konva_json", {}).get("images", []):
            url = layer.get("src")
            hashes["layer:" + str(layer.get("id"))] = check(url)
        return hashes

    @staticmethod
    def _render_layers(project: dict) -> list:
        # Identity annotations may be repaired without changing a rendered scene.
        return [{key: val for key, val in layer.items()
                 if key not in {"id", "source_id", "source_uid", "name", "src"}}
                for layer in project.get("meta", {}).get("konva_json", {}).get("images", [])]

    def _apply_scope(self) -> dict:
        context = self.get_parameter_value("image_bash_context") or {}
        metadata = self.metadata if isinstance(self.metadata, dict) else {}
        return {"workspace_id": context.get("workspace_id"),
            "channel_uuid": metadata.get("hmb_image_bash_channel_uuid"),
            "workspace_revision": int(context.get("revision", 0)),
            "node_instance_uuid": self._remote_source_instance(self)}

    @staticmethod
    def _validate_apply_source_bindings(project: dict, records: list[dict], *, expected_scope: dict | None = None) -> None:
        """Refuse an old modal's Apply before repairing its source metadata."""
        meta = project.get("meta", {})
        hmb = meta.get("hmb_image_bash", {}) if isinstance(meta, dict) else None
        bindings = hmb.get("source_bindings", []) if isinstance(hmb, dict) else None
        if not isinstance(bindings, list):
            raise ValueError("Apply 원본 목록 형식이 올바르지 않습니다. 입력 동기화 후 편집기를 다시 열어 Apply하세요.")
        def source_uids(rows):
            result = set()
            for row in rows:
                uid = row.get("source_uid") if isinstance(row, dict) else None
                if not isinstance(uid, str) or not uid.strip() or uid in result:
                    raise ValueError("Apply 원본 식별자가 누락되었거나 중복되었습니다. 입력 동기화 후 편집기를 다시 열어 Apply하세요.")
                result.add(uid)
            return result
        if source_uids(bindings) != source_uids(records):
            raise ValueError("편집 중 ImageAsset 입력이 추가되거나 제거되었습니다. 입력 동기화 후 편집기를 다시 열어 확인하고 Apply하세요. 이전 완료 결과는 유지됩니다.")
        if expected_scope is not None:
            keys = {"workspace_id", "channel_uuid", "workspace_revision", "node_instance_uuid"}
            present = keys.intersection(hmb)
            # Old saved documents without scope metadata keep their UID fence.
            # A partially annotated document must never silently act as legacy.
            if present and (present != keys or type(hmb.get("workspace_revision")) is not int
                    or hmb["workspace_revision"] < 0 or any(hmb[key] != expected_scope[key] for key in keys)):
                raise ValueError("Image Bash 작업 공간 또는 입력 버전이 변경되었습니다. 편집기를 다시 열어 확인하고 Apply하세요. 이전 완료 결과는 유지됩니다.")

    def _admit_pending_cold_assignment(self, project: dict) -> bool:
        """Preserve a saved pending draft before its real inputs are hydrated.

        This only admits a document; the later cold readiness path still
        verifies actual source/receipt/scope and never promotes pending pixels.
        A marker sent by a live editor is insufficient to enter this path.
        """
        from griptape_nodes.retained_mode.engine import has_current_engine
        if not has_current_engine():
            return False
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
        manager = GriptapeNodes.EventManager()
        context = getattr(manager, "_hmb_bash_initial_assignment_context", None)
        lease = context.get() if isinstance(context, contextvars.ContextVar) else None
        if (not isinstance(lease, dict) or lease.get("active") is not True or lease.get("node") is not self
                or GriptapeNodes.NodeManager().get_node_by_name(self.name) is not self):
            return False
        meta = project.get("meta")
        hmb = meta.get("hmb_image_bash") if isinstance(meta, dict) else None
        scene = meta.get("konva_json") if isinstance(meta, dict) else None
        if (not isinstance(hmb, dict) or not isinstance(scene, dict)
                or not isinstance(scene.get("images"), list) or not isinstance(scene.get("lines"), list)
                or any(not isinstance(row, dict) for row in scene["images"])
                or not isinstance(meta.get("input_images"), list)
                or any(not isinstance(row, dict) for row in meta["input_images"])):
            return False
        pending, preparing = hmb.get("pending_apply"), hmb.get("pending_prepare")
        if pending is None and preparing is None:
            return False
        if pending is not None and (not isinstance(pending, dict)
                or pending.get("schema") != "hmb-image-bash-pending-apply-v1"
                or not isinstance(pending.get("editor_commit"), str) or not pending["editor_commit"]
                or pending["editor_commit"] != meta.get("created_at")):
            return False
        if preparing is not None:
            if not isinstance(preparing, dict) or preparing.get("schema") != "hmb-image-bash-pending-prepare-v1":
                return False
            scope, uids = preparing.get("scope"), preparing.get("source_uids")
            if (not isinstance(scope, dict) or set(scope) != {"workspace_id", "channel_uuid", "workspace_revision"}
                    or any(not isinstance(scope.get(key), str) or not scope[key] for key in ("workspace_id", "channel_uuid"))
                    or type(scope.get("workspace_revision")) is not int or scope["workspace_revision"] < 0
                    or not isinstance(uids, list) or any(not isinstance(uid, str) or not uid for uid in uids)
                    or len(uids) != len(set(uids))):
                return False
        current = _document(self.get_parameter_value("bash_image"))
        # Native saved Python restores the same field both as its value and as
        # output. Repeating this exact assignment cannot authorize a new edit.
        def envelope_free(value):
            value = dict(value)
            value.pop("id", None)
            value.pop("reference", None)
            return value
        if (getattr(self, "_hmb_cold_pending_assignment_admitted", False)
                and envelope_free(current) == envelope_free(project)):
            return True
        if (self._hmb_prepare_phase != "idle" or self._hmb_apply_epoch != 0
                or self._hmb_last_output is not None or self._hmb_apply_pending is not None
                or self._hmb_prepare_pending is not None
                or current != self._hmb_auto_pristine_project):
            return False
        self._hmb_cold_pending_assignment_admitted = True
        return True

    @staticmethod
    def _cold_gap_saved_identity(project: dict) -> tuple | None:
        meta = project.get("meta", {})
        hmb = meta.get("hmb_image_bash", {}) if isinstance(meta, dict) else {}
        receipt = hmb.get("apply") if isinstance(hmb, dict) else None
        if (not isinstance(receipt, dict) or receipt.get("schema") != RECEIPT_SCHEMA
                or not isinstance(meta.get("created_at"), str) or not meta["created_at"]
                or receipt.get("editor_commit") != meta["created_at"]
                or any(type(receipt.get(key)) is not int or receipt[key] <= 0 for key in ("width", "height"))
                or not isinstance(receipt.get("source_hashes"), dict)
                or not isinstance(receipt.get("png_base64"), str) or not receipt["png_base64"]
                or hmb.get("pending_apply") is not None or hmb.get("pending_prepare") is not None
                or any(not isinstance(hmb.get(key), str) or not hmb[key]
                    for key in ("workspace_id", "channel_uuid", "node_instance_uuid"))
                or type(hmb.get("workspace_revision")) is not int or hmb["workspace_revision"] < 0
                or any(not isinstance(receipt.get(key), str) or len(receipt[key]) != 64
                    or any(char not in "0123456789abcdef" for char in receipt[key])
                    for key in ("scene_sha256", "png_sha256", "rgba_sha256"))):
            return None
        return (meta["created_at"], *(hmb[key] for key in ("workspace_id", "channel_uuid", "workspace_revision", "node_instance_uuid")),
            *(receipt[key] for key in ("scene_sha256", "png_sha256", "rgba_sha256")))

    def _initial_bash_assignment_active(self) -> bool:
        try:
            context = getattr(self.engine.event_manager, "_hmb_bash_initial_assignment_context", None)
            lease = context.get() if isinstance(context, contextvars.ContextVar) else None
            return (isinstance(lease, dict) and lease.get("active") is True and lease.get("node") is self
                and _hmb_is_registered_node(self, "HMBImageBash")
                and self.engine.node_manager.get_node_by_name(self.name) is self)
        except (AttributeError, KeyError, RuntimeError, TypeError, ValueError):
            return False

    def before_value_set(self, parameter: Parameter, value: Any) -> Any:
        value = super().before_value_set(parameter, value)
        if (parameter.name != "bash_image" or getattr(self, "_hmb_syncing", False)
                or getattr(self, "_initializing", False)):
            return value
        project = _document(value)
        initial = self._initial_bash_assignment_active()
        identity = self._cold_gap_saved_identity(project)
        if not initial:
            self._hmb_cold_input_gap = False
            self._hmb_cold_gap_recovery = None
        elif (getattr(self, "_hmb_cold_input_gap", False) and identity is not None
                and not getattr(self, "_hmb_cold_gap_admitted", False)
                and self._hmb_last_output is None and self._hmb_apply_pending is None
                and self._hmb_prepare_pending is None and self._hmb_cold_restore_pending is None
                and _document(self.get_parameter_value("bash_image")) == self._hmb_auto_pristine_project):
            self._hmb_cold_gap_recovery = {"identity": identity, "epoch": self._hmb_apply_epoch}
            self._hmb_cold_gap_admitted = True
        if not _url(project) or _url(project).startswith("data:image/svg"):
            return value
        meta = project.get("meta", {})
        hmb = meta.get("hmb_image_bash", {}) if isinstance(meta, dict) else {}
        retained = hmb.get("apply") if isinstance(hmb, dict) else None
        if isinstance(retained, dict) and retained and retained.get("editor_commit") == meta.get("created_at"):
            return value
        if HMBImageBash._admit_pending_cold_assignment(self, project):
            return value
        try:
            if meta.get("hmb_editor") == EDITOR_SCHEMA and (
                    self._hmb_prepare_phase != "ready" or not self._hmb_editor_snapshot_id
                    or hmb.get("editor_snapshot_id") != self._hmb_editor_snapshot_id):
                raise ValueError("편집 중 입력 또는 장면이 바뀌었습니다. 현재 장면을 다시 열어 주세요.")
            self._validate_apply_source_bindings(project, self._records(), expected_scope=self._apply_scope())
        except Exception as exc:
            self._status("Apply 검증 실패: " + str(exc))
            raise
        if getattr(self, "_hmb_apply_pending", None) is None:
            previous = _document(self.get_parameter_value("bash_image"))
            self._hmb_apply_prior_receipt = deepcopy(previous.get("meta", {}).get("hmb_image_bash", {}).get("apply"))
        return value

    def _handle_bash_image_change(self, value: Any) -> None:
        if not (self._hmb_syncing or getattr(self, "_initializing", False) or self._hmb_node_deleted):
            project = _document(value)
            retained = project.get("meta", {}).get("hmb_image_bash", {}).get("apply")
            if retained and retained.get("editor_commit") == project.get("meta", {}).get("created_at"):
                if getattr(self, "_hmb_apply_pending", None) is not None:
                    self._hmb_apply_epoch += 1
                    self._hmb_apply_pending = None
                    self._hmb_apply_rollback_document = None
                    with self._hmb_apply_work["lock"]:
                        self._hmb_apply_work["queued"] = None
            if (_url(project) and not _url(project).startswith("data:image/svg")
                    and not (retained and retained.get("editor_commit") == project.get("meta", {}).get("created_at"))):
                try:
                    if HMBImageBash._queue_apply(self, project):
                        return
                except Exception as exc:
                    self._hmb_apply_pending = None
                    self._hmb_apply_rollback_document = None
                    with self._hmb_apply_work["lock"]:
                        self._hmb_apply_work["queued"] = None
                    failed = _document(self.get_parameter_value("bash_image"))
                    self._preserve_failed_apply(failed, str(exc))
                    raise
        return HMBImageBash._handle_bash_image_change_sync(self, value)

    def _queue_apply(self, project: dict) -> bool:
        """One worker + newest intent; host acceptance means queued, not verified."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return False
        from griptape_nodes.retained_mode.engine import has_current_engine
        if not has_current_engine() or not loop.is_running():
            return False
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
        if GriptapeNodes.NodeManager().get_node_by_name(self.name) is not self:
            return False
        records, canvas, scope = self._records(), self._canvas(), self._apply_scope()
        self._validate_apply_source_bindings(project, records, expected_scope=scope)
        updated = self._sync_project(project, records, add_missing=False)
        read_paths = self._snapshot_read_paths(updated, project)
        if read_paths is None:
            return False  # Preserve the SDK's original remote-file read policy.
        hmb = updated.setdefault("meta", {}).setdefault("hmb_image_bash", {})
        if not hmb.get("apply") and isinstance(self._hmb_apply_prior_receipt, dict):
            hmb["apply"] = deepcopy(self._hmb_apply_prior_receipt)
        hmb["pending_apply"] = {
            "schema": "hmb-image-bash-pending-apply-v1", "editor_commit": project.get("meta", {}).get("created_at")}
        # Lossless scene-only reconciliation remains immediate (undo/deletion
        # metadata); a new receipt/output is never published before the worker.
        if updated != project:
            self._set_project(updated)
        self._hmb_apply_epoch += 1
        task = {"epoch": self._hmb_apply_epoch, "project": deepcopy(project), "updated": updated,
            "records": deepcopy(records), "canvas": deepcopy(canvas), "scope": deepcopy(scope),
            "scene": scene_fingerprint(updated, records, canvas), "png_url": _url(updated),
            "context": deepcopy(self.get_parameter_value("image_bash_context") or {}),
            "connections": self._apply_connection_lease()}
        task["kind"] = "apply"
        task["read_paths"] = read_paths
        task["read_drivers"] = self._snapshot_driver_lease(read_paths)
        self._hmb_prepare_pending = None
        self._hmb_cold_restore_pending = None
        self._hmb_apply_pending = task
        self._status("Apply 검증 중 · 이전 완료 결과 유지")
        return self._start_snapshot_task(task, loop)

    def _start_snapshot_task(self, task: dict, loop) -> bool:
        """Share one daemon between Apply and preparation; keep one latest intent."""
        work = self._hmb_apply_work
        with work["lock"]:
            work["queued"] = task
            if work["active"]:
                return True
            work["active"] = True
            token = work["worker_token"] = object()
        owner_ref, host_context = weakref.ref(self), contextvars.copy_context()
        def worker():
            try:
                while True:
                    with work["lock"]:
                        current, work["queued"] = work["queued"], None
                        if current is None:
                            work["active"] = False
                            return
                    owner = owner_ref()
                    if owner is None:
                        return
                    live = lambda: (owner_ref() is not None and not owner._hmb_node_deleted
                                    and current["epoch"] == owner._hmb_apply_epoch
                                    and getattr(owner, "_hmb_" + current["kind"] + "_pending", None) is current)
                    try:
                        calculator = {"prepare": HMBImageBash._calculate_prepare,
                                      "cold_restore": HMBImageBash._calculate_cold_restore}.get(current["kind"], HMBImageBash._calculate_apply)
                        result = calculator(current, live)
                    except Exception as exc:
                        result = {"error": str(exc), "source_error": isinstance(exc, _ImageBashSourceError)}
                    if owner_ref() is not None:
                        # A congested host retains only the newest completed
                        # payload, not one large scene/PNG closure per result.
                        with work["lock"]:
                            work["completed"] = (current, result)
                            schedule = not work["publish_scheduled"]
                            work["publish_scheduled"] = True
                        if schedule:
                            def publish():
                                with work["lock"]:
                                    completed, work["completed"] = work["completed"], None
                                    work["publish_scheduled"] = False
                                node = owner_ref()
                                if node is not None and completed is not None:
                                    completed_task, completed_result = completed
                                    finish = {"prepare": node._finish_prepare,
                                              "cold_restore": node._finish_cold_restore}.get(completed_task["kind"], node._finish_apply)
                                    finish(completed_task, completed_result)
                            try:
                                loop.call_soon_threadsafe(publish, context=host_context.copy())
                            except RuntimeError:
                                with work["lock"]:
                                    work["completed"] = None
                                    work["publish_scheduled"] = False
            finally:
                with work["lock"]:
                    if work.get("worker_token") is token:
                        work["active"] = False
        try:
            threading.Thread(target=lambda: host_context.run(worker), name="HMBImageBashWorker", daemon=True).start()
        except Exception:
            with work["lock"]:
                work["active"] = False
            raise
        return True

    @staticmethod
    def _snapshot_read_paths(*projects: dict, records: list[dict] | None = None) -> dict | None:
        """Resolve SDK path policy on the host; raster I/O belongs to the worker."""
        try:
            from griptape_nodes.files.drivers.local_file_driver import LocalFileDriver
            from griptape_nodes.files.drivers.static_server_file_driver import StaticServerFileDriver
        except ImportError:
            return None
        urls = {row.get("url", "") for row in records or []}
        for project in projects:
            if _url(project):
                urls.add(_url(project))
            urls.update(row.get("url", "") for row in project.get("meta", {}).get("input_images", []))
            urls.update(row.get("src", "") for row in project.get("meta", {}).get("konva_json", {}).get("images", []))
        paths = {}
        for url in urls:
            if not url or url.startswith("data:"):
                continue
            # Custom/subclass drivers may enforce additional policy. Only the
            # reviewed stock local transports admit direct snapshot reads.
            file = File(url)
            if type(_snapshot_driver(file)) not in {LocalFileDriver, StaticServerFileDriver}:
                return None
            resolved = file.resolve()
            if urlparse(resolved).scheme in {"http", "https"}:
                return None
            paths[url] = resolved
        return paths

    @staticmethod
    def _snapshot_driver_lease(paths: dict) -> tuple:
        return tuple((url, _snapshot_driver(File(url))) for url in sorted(paths))

    @staticmethod
    def _snapshot_read(task: dict, url: str) -> bytes:
        if url.startswith("data:"):
            return _read_bytes(url)
        return Path(task["read_paths"][url]).read_bytes()

    @staticmethod
    def _calculate_apply(task: dict, is_live) -> dict:
        """Pure snapshot validation; no host writes, parameters or graph APIs."""
        rgba_cache = OrderedDict()
        view = SimpleNamespace(_hmb_syncing=False, _initializing=False, _hmb_node_deleted=False,
            _hmb_last_output=None, _hmb_apply_epoch=0, project=deepcopy(task["project"]))
        view._records = lambda: deepcopy(task["records"])
        view._canvas = lambda: deepcopy(task["canvas"])
        view._apply_scope = lambda: deepcopy(task["scope"])
        view._hmb_read_apply_bytes = lambda url: HMBImageBash._snapshot_read(task, url)
        view._validate_apply_source_bindings = HMBImageBash._validate_apply_source_bindings
        view._render_layers = HMBImageBash._render_layers
        view._sync_project = lambda *args, **kwargs: deepcopy(task["updated"])
        view._source_hashes = lambda project, **kwargs: HMBImageBash._source_hashes(
            view, project, **{**kwargs, "rgba_cache": rgba_cache, "is_live": is_live,
                             "read_bytes": lambda url: HMBImageBash._snapshot_read(task, url)})
        def set_project(value): view.project = deepcopy(value)
        view._set_project = set_project
        view._schedule_host_callback = lambda callback: True
        view._status = lambda text: None
        view._clear_output = lambda: None
        HMBImageBash._handle_bash_image_change_sync(view, task["project"])
        if not is_live():
            raise ValueError("새 입력 또는 Apply로 이전 이미지 검증이 취소되었습니다.")
        # The second fresh raw read belongs immediately before host commit,
        # not here: otherwise queued delivery would create a third I/O pass.
        return {"project": view.project, "rgba_cache": rgba_cache}

    def _apply_task_current(self, task: dict) -> bool:
        pending = "_hmb_" + task.get("kind", "apply") + "_pending"
        if self._hmb_node_deleted or task["epoch"] != self._hmb_apply_epoch or getattr(self, pending, None) is not task:
            return False
        try:
            from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
            if GriptapeNodes.NodeManager().get_node_by_name(self.name) is not self:
                return False
            records, canvas = self._records(), self._canvas()
            current = _document(self.get_parameter_value("bash_image"))
            connections = self._apply_connection_lease()
            same_connections = (len(connections) == len(task["connections"]) and all(
                live[0] is prior[0] and live[1:] == prior[1:]
                for live, prior in zip(connections, task["connections"])))
            drivers = self._snapshot_driver_lease(task["read_paths"])
            same_drivers = len(drivers) == len(task["read_drivers"]) and all(
                live[0] == prior[0] and live[1] is prior[1] for live, prior in zip(drivers, task["read_drivers"]))
            return (same_connections and same_drivers and self._apply_scope() == task["scope"] and canvas == task["canvas"]
                    and (self.get_parameter_value("image_bash_context") or {}) == task["context"]
                    and records == task["records"] and _url(current) == task["png_url"]
                    and scene_fingerprint(current, records, canvas) == task["scene"])
        except (ValueError, TypeError, KeyError, RuntimeError):
            return False

    def _apply_connection_lease(self) -> tuple:
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
        from griptape_nodes.retained_mode.events.connection_events import ListConnectionsForNodeRequest
        found = GriptapeNodes.handle_request(ListConnectionsForNodeRequest(node_name=self.name, broadcast_result=False))
        if not found.succeeded():
            raise ValueError("Apply 입력 연결을 확인하지 못했습니다.")
        return tuple((GriptapeNodes.NodeManager().get_node_by_name(edge.source_node_name),
                      edge.source_parameter_name, edge.target_parameter_name)
                     for edge in sorted(found.incoming_connections,
                         key=lambda row: (row.source_node_name, row.source_parameter_name, row.target_parameter_name)))

    def _mark_verified_apply_ready(self, records: list[dict], canvas: dict, scope: dict, epoch: int) -> bool:
        """A verified current Apply also completes its superseded input preparation.

        Do this before publishing/writing: a later input notification must be
        able to replace ready with preparing, rather than being overwritten by
        an older output completion. Worker views only update their own fields.
        """
        try:
            if (self._hmb_node_deleted or self._hmb_apply_epoch != epoch
                    or self._records() != records or self._canvas() != canvas or self._apply_scope() != scope):
                return False
            if isinstance(self, HMBImageBash):
                sources = self._remote_sources()
                bound = self._remote_bound_source(sources)
                if bound is not None:
                    catalog = next(value for node, value in sources if node is bound)
                    workspace = next((row for row in catalog.get("workspaces", [])
                                      if row.get("workspace_id") == scope["workspace_id"]), {})
                    if (type(workspace.get("revision")) is not int
                            or workspace["revision"] != scope["workspace_revision"]
                            or workspace.get("count") != len(records)):
                        return False
        except (TypeError, ValueError, KeyError):
            return False
        previous_prepare = getattr(self, "_hmb_prepare_pending", None)
        previous_apply = getattr(self, "_hmb_apply_pending", None)
        self._hmb_prepare_pending = self._hmb_apply_pending = None
        self._hmb_cold_restore_pending = None
        self._hmb_prepare_phase, self._hmb_prepare_error = "ready", ""
        self._hmb_inputs_unready = False
        work = getattr(self, "_hmb_apply_work", None)
        if isinstance(work, dict):
            with work["lock"]:
                if work.get("queued") is previous_prepare or work.get("queued") is previous_apply:
                    work["queued"] = None
                completed = work.get("completed")
                if completed is not None and (completed[0] is previous_prepare or completed[0] is previous_apply):
                    work["completed"] = None
        return True

    @hmb_binding_mutation
    def _finish_apply(self, task: dict, result: dict, *, write_output: bool = True) -> bool:
        if not self._apply_task_current(task):
            self._discard_apply_task(task)
            return False
        if not result.get("error"):
            try:
                raw, png = self._verify_apply(result["project"], self._records(), rgba_cache=result["rgba_cache"])
            except Exception as exc:
                result = {"error": str(exc), "source_error": isinstance(exc, _ImageBashSourceError)}
        # A File resolver may re-enter the host. No verified result outranks a
        # new owner, input, channel, scene or newer Apply accepted meanwhile.
        if not self._apply_task_current(task):
            self._discard_apply_task(task)
            return False
        if result.get("error"):
            self._hmb_apply_pending = None
            self._hmb_apply_rollback_document = None
            if result.get("source_error"):
                self._hmb_prepare_phase, self._hmb_prepare_error = "error", result["error"]
            elif self._hmb_prepare_phase == "preparing" and self._hmb_prepare_pending is None:
                self._hmb_prepare_phase = "error"
                self._hmb_prepare_error = "Apply 검증 실패: " + result["error"] + " · 입력 준비를 다시 확인하세요. 편집 초안은 보존됩니다."
            self._preserve_failed_apply(_document(self.get_parameter_value("bash_image")), result["error"])
            return False
        # Pan/zoom and SDK envelope materialization are deliberately excluded
        # from the scene hash. Never rewind those newer, non-render edits.
        current = _document(self.get_parameter_value("bash_image"))
        completed = deepcopy(result["project"])
        if "viewport" in current.get("meta", {}):
            completed["meta"]["viewport"] = deepcopy(current["meta"]["viewport"])
        else:
            completed["meta"].pop("viewport", None)
        for name in ("id", "reference"):
            if name in current:
                completed[name] = deepcopy(current[name])
            else:
                completed.pop(name, None)
        if not HMBImageBash._mark_verified_apply_ready(self, task["records"], task["canvas"], task["scope"], task["epoch"]):
            self._discard_apply_task(task)
            return False
        self._set_project(completed)
        self._hmb_apply_rollback_document = None
        if write_output:
            self._complete_apply(task["epoch"], verified=(raw, png))
        return True

    def _preserve_failed_apply(self, project: dict, error: str) -> None:
        """Retain edits after the modal closes, without approving their PNG."""
        hmb = project.setdefault("meta", {}).setdefault("hmb_image_bash", {})
        if not hmb.get("apply") and isinstance(self._hmb_apply_prior_receipt, dict):
            hmb["apply"] = deepcopy(self._hmb_apply_prior_receipt)
        hmb["pending_apply"] = {"schema": "hmb-image-bash-pending-apply-v1",
            "editor_commit": project["meta"].get("created_at"), "phase": "error", "error": error[:1024]}
        self._set_project(project)
        self._status("Apply 검증 실패: " + error + " · 편집 초안 보존, 다시 열어 수정 후 Apply하세요. 이전 완료 결과는 유지됩니다.")

    def _discard_apply_task(self, task: dict) -> None:
        pending = "_hmb_" + task.get("kind", "apply") + "_pending"
        if getattr(self, pending, None) is task:
            setattr(self, pending, None)
            self._hmb_apply_rollback_document = None
            with self._hmb_apply_work["lock"]:
                if self._hmb_apply_work["queued"] is task:
                    self._hmb_apply_work["queued"] = None
            if task.get("kind") in {"prepare", "cold_restore"} and not self._hmb_node_deleted:
                context = self.get_parameter_value("image_bash_context") or {}
                if isinstance(context, dict) and context.get("ready") is False:
                    self._hmb_prepare_phase = "error" if context.get("preparation_phase") == "error" else "preparing"
                    self._hmb_prepare_error = str(context.get("error") or "")
                else:
                    self._hmb_prepare_phase = "error"
                    self._hmb_prepare_error = "입력·연결·편집 장면이 변경되어 이전 준비를 중단했습니다. 다시 준비하세요."
                    self._status(self._hmb_prepare_error)

    def _flush_pending_apply(self) -> None:
        """An explicit Run may synchronously validate its newest queued Apply."""
        task = self._hmb_apply_pending
        if task is None or not self._apply_task_current(task):
            return
        self._hmb_apply_epoch += 1
        task = {**task, "epoch": self._hmb_apply_epoch}
        self._hmb_apply_pending = task
        try:
            result = self._calculate_apply(task, lambda: not self._hmb_node_deleted and task["epoch"] == self._hmb_apply_epoch)
        except Exception as exc:
            self._finish_apply(task, {"error": str(exc)}, write_output=False)
            raise
        if not self._finish_apply(task, result, write_output=False):
            raise ValueError("대기 중 Apply를 현재 입력으로 확정하지 못했습니다. 상태를 확인하세요.")

    def _handle_bash_image_change_sync(self, value: Any) -> None:
        if self._hmb_syncing or getattr(self, "_initializing", False) or self._hmb_node_deleted:
            return
        try:
            project = _document(value)
            if not _url(project) or _url(project).startswith("data:image/svg"):
                self._clear_output()
                self._status("편집기에서 Apply 필요")
                return
            # A receipt arriving from workflow deserialization must be verified,
            # never silently renewed against changed sources.
            retained = project.get("meta", {}).get("hmb_image_bash", {}).get("apply")
            editor_commit = project.get("meta", {}).get("created_at")
            if retained and retained.get("editor_commit") == editor_commit:
                cached = self._hmb_last_output
                if isinstance(cached, dict):
                    try:
                        _raw, expected = self._verify_apply(project, self._records())
                        if (cached.get("key") == self._output_key(project, expected)
                                and validate_png_bytes(File(cached["path"]).read_bytes()) == expected):
                            self._adopt_verified_saved_editor_scope(project, self._records())
                            if self._hmb_output_pending:
                                output = self.parameter_output_values.get("output_image")
                                self._hmb_output_pending = not self._propagate_output(output, self._hmb_output_generation)
                                if not self._hmb_output_pending:
                                    self._status("Apply 저장 및 이미지 출력 완료")
                            return
                    except Exception:
                        pass
                # Native deserialization restores stock parameters before our
                # appended context/input connections. Defer validation to Run.
                gap = getattr(self, "_hmb_cold_gap_recovery", None)
                if (self._initial_bash_assignment_active() and isinstance(gap, dict)
                        and gap.get("identity") == self._cold_gap_saved_identity(project)):
                    self._clear_output(preserve_initial_gap=True)
                else:
                    self._clear_output()
                self._hmb_restore_pending = True
                self._status("저장된 Apply 복원 중 · 입력과 파일을 확인합니다")
                return
            records = self._records()
            scope, admission_epoch, admission_canvas = self._apply_scope(), self._hmb_apply_epoch, self._canvas()
            self._validate_apply_source_bindings(project, records, expected_scope=scope)
            updated = self._sync_project(project, records, add_missing=False)
            source_cache = {}
            rgba_cache = OrderedDict()
            source_hashes = self._source_hashes(updated, cache=source_cache, rgba_cache=rgba_cache)
            same_render = self._render_layers(updated) == self._render_layers(project)
            if same_render:
                try:
                    # The native editor resolves C:/ paths to browser URLs.
                    # Equal decoded rasters are the same source despite an alias.
                    self._source_hashes(project, cache=source_cache, rgba_cache=rgba_cache)
                    old_layers = project.get("meta", {}).get("konva_json", {}).get("images", [])
                    new_layers = updated.get("meta", {}).get("konva_json", {}).get("images", [])
                    same_render = all(
                        all(source_cache[old["src"]][key] == source_cache[new["src"]][key]
                            for key in ("width", "height", "rgba_sha256"))
                        for old, new in zip(old_layers, new_layers)
                    )
                except Exception as exc:
                    raise ValueError("편집기 이미지 경로 검증 실패: " + str(exc)) from exc
            if not same_render:
                updated.setdefault("meta", {}).setdefault("hmb_image_bash", {})["prepared_source_hashes"] = source_hashes
                self._set_project(updated)
                raise ValueError("편집 중 ImageAsset 입력이 변경되었습니다. 동기화된 레이어를 확인하고 다시 Apply하세요.")
            project = updated
            raw = getattr(self, "_hmb_read_apply_bytes", _read_bytes)(_url(project))
            png = validate_png_bytes(raw)
            canvas = self._canvas()
            if (png["width"], png["height"]) != (canvas["width"], canvas["height"]):
                raise ValueError("Apply PNG와 캔버스 해상도가 다릅니다. 다시 Apply하세요.")
            prepared = project.get("meta", {}).get("hmb_image_bash", {}).get("prepared_source_hashes", {})
            external_keys = {"input:" + binding["source_id"] for binding in
                project.get("meta", {}).get("hmb_image_bash", {}).get("source_bindings", [])}
            if prepared and any(source_hashes.get(key) != item for key, item in prepared.items()
                                if key in external_keys and key in source_hashes):
                project["meta"]["hmb_image_bash"]["prepared_source_hashes"] = source_hashes
                self._set_project(project)
                raise _ImageBashSourceError("편집기를 연 뒤 원본 이미지가 변경되었습니다. 다시 열어 확인하고 Apply하세요.")
            canonical_url = "data:image/png;base64," + base64.b64encode(raw).decode("ascii")
            project["value"] = canonical_url
            project["meta"]["preview_url"] = canonical_url
            project["meta"]["content_hash"] = png["png_sha256"]
            receipt = {"schema": RECEIPT_SCHEMA, **png,
                "editor_commit": editor_commit,
                "scene_sha256": scene_fingerprint(project, records, canvas),
                "source_hashes": source_hashes,
                "png_base64": base64.b64encode(raw).decode("ascii")}
            # The saved workflow remains usable after transient editor URLs expire.
            project.setdefault("meta", {}).setdefault("hmb_image_bash", {})["apply"] = receipt
            project["meta"]["hmb_image_bash"].pop("pending_apply", None)
            project["meta"]["hmb_image_bash"].pop("pending_prepare", None)
            project["meta"]["hmb_image_bash"]["prepared_source_hashes"] = source_hashes
            if not HMBImageBash._mark_verified_apply_ready(self, records, admission_canvas, scope, admission_epoch):
                raise ValueError("Apply 검증 중 입력·작업 공간이 변경되었습니다. 현재 입력을 확인하고 다시 Apply하세요.")
            self._set_project(project)
            self._hmb_apply_epoch += 1
            epoch = self._hmb_apply_epoch
            self._hmb_apply_rgba_cache = (epoch, rgba_cache)
            def complete() -> None:
                try:
                    self._complete_apply(epoch)
                except Exception as exc:
                    if not self._hmb_node_deleted and epoch == self._hmb_apply_epoch:
                        self._status("Apply 저장 또는 전달 실패: " + str(exc))
            if not self._schedule_host_callback(complete):
                raise ValueError("Apply 출력에 필요한 호스트 이벤트 루프를 확인하세요.")
            self._status("Apply 검증 완료 · 이미지 저장 중")
        except Exception as exc:
            self._status("Apply 검증 실패: " + str(exc))
            raise

    @hmb_binding_mutation
    def _complete_apply(self, epoch: int, *, verified: tuple | None = None) -> None:
        if self._hmb_node_deleted or epoch != self._hmb_apply_epoch:
            return
        try:
            from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
            if GriptapeNodes.NodeManager().get_node_by_name(self.name) is not self:
                return
            project = _document(self.get_parameter_value("bash_image"))
            cache = getattr(self, "_hmb_apply_rgba_cache", None)
            raw, expected = (verified if verified is not None else self._verify_apply(project, self._records(),
                rgba_cache=cache[1] if cache and cache[0] == epoch else None))
            if self._hmb_node_deleted or epoch != self._hmb_apply_epoch:
                return
            self._write_output(raw, expected, exact_apply=True)
            self._hmb_apply_rgba_cache = None
            if self._hmb_node_deleted or epoch != self._hmb_apply_epoch:
                return
            self._hmb_restore_pending = False
            self._status("이미지 원본 확인 대기 · 이전 완료 결과 유지" if self._hmb_inputs_unready else
                         "Apply 저장 완료 · 연결된 입력이 사용 가능해지면 Run으로 다시 전달하세요" if self._hmb_output_pending else "Apply 저장 및 이미지 출력 완료")
        except Exception as exc:
            if not self._hmb_node_deleted and epoch == self._hmb_apply_epoch:
                self._status("Apply 저장 또는 전달 실패: " + str(exc))

    def _schedule_restore(self) -> None:
        if self._hmb_restore_scheduled:
            return
        self._hmb_restore_scheduled = True
        epoch = self._hmb_apply_epoch
        def restore() -> None:
            self._hmb_restore_scheduled = False
            if self._hmb_node_deleted or epoch != self._hmb_apply_epoch or not self._hmb_restore_pending:
                return
            try:
                project = _document(self.get_parameter_value("bash_image"))
                self._restore_saved_output(project, self._records())
            except Exception as exc:
                self._status("저장된 Apply 복원 대기: " + str(exc))
        if not self._schedule_host_callback(restore):
            self._hmb_restore_scheduled = False
            self._status("Apply 복원 대기 · 호스트 이벤트 루프를 확인하세요")

    def _output_key(self, project: dict, expected: dict) -> tuple:
        receipt = project.get("meta", {}).get("hmb_image_bash", {}).get("apply", {})
        return (receipt.get("editor_commit"), receipt.get("scene_sha256"), expected.get("png_sha256"),
                repr(self.get_parameter_value("output_file")))

    def _adopt_verified_saved_editor_scope(self, project: dict, records: list[dict]) -> bool:
        """Renew a saved editor's lease and view data after PNG verification.

        Callers have already checked the retained receipt, source rasters and
        exact saved output PNG. A workflow reload creates a fresh Python node;
        it must not keep the old modal lease, or the editor remains preparing.
        No workspace, channel, revision, binding, scene or receipt is repaired.
        """
        if self._hmb_node_deleted or not _hmb_is_registered_node(self, "HMBImageBash"):
            return False
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
        if GriptapeNodes.NodeManager().get_node_by_name(self.name) is not self:
            return False
        context = self.get_parameter_value("image_bash_context") or {}
        if (not isinstance(context, dict) or context.get("schema") != CONTEXT_SCHEMA
                or context.get("ready") is not True):
            return False
        scope = self._apply_scope()
        metadata = self.metadata if isinstance(self.metadata, dict) else {}
        if (not scope["workspace_id"] or not scope["channel_uuid"]
                or metadata.get("hmb_image_bash_workspace_id") != scope["workspace_id"]):
            return False
        sources = self._remote_sources()
        bound = self._remote_bound_source(sources)
        if bound is None:
            return False
        catalog = next((value for node, value in sources if node is bound), {})
        current = next((row for row in catalog.get("workspaces", [])
                        if row.get("workspace_id") == scope["workspace_id"]), {})
        if (current.get("revision") != scope["workspace_revision"]
                or current.get("count") != len(records)):
            return False
        meta = project.get("meta", {})
        hmb = meta.get("hmb_image_bash", {}) if isinstance(meta, dict) else {}
        retained = hmb.get("apply") if isinstance(hmb, dict) else None
        if (not isinstance(retained, dict) or retained.get("schema") != RECEIPT_SCHEMA
                or retained.get("editor_commit") != meta.get("created_at")
                or not isinstance(hmb.get("node_instance_uuid"), str)
                or not hmb["node_instance_uuid"]):
            return False
        prior_scope = {**scope, "node_instance_uuid": hmb["node_instance_uuid"]}
        try:
            self._validate_apply_source_bindings(project, records, expected_scope=prior_scope)
        except ValueError:
            return False
        snapshot = getattr(self, "_hmb_editor_snapshot_id", "")
        canvas = self._canvas()
        view = {key: canvas[key] for key in ("width", "height", "background_color")}
        if (hmb["node_instance_uuid"] != scope["node_instance_uuid"]
                or not snapshot or hmb.get("editor_snapshot_id") != snapshot or meta.get("hmb_canvas") != view):
            updated = deepcopy(project)
            updated["meta"]["hmb_canvas"] = view
            updated["meta"]["hmb_image_bash"]["node_instance_uuid"] = scope["node_instance_uuid"]
            self._set_project(updated)
        self._hmb_prepare_phase, self._hmb_prepare_error = "ready", ""
        self._hmb_inputs_unready = False
        self._publish_header()
        return True

    @hmb_binding_mutation
    def _restore_saved_output(self, project: dict, records: list[dict]) -> None:
        """Revalidate an existing saved Apply file; never recreate it on load."""
        receipt = project.get("meta", {}).get("hmb_image_bash", {}).get("apply", {})
        proof = self.get_parameter_value("HMB_BASH_VERIFICATION") or {}
        path = receipt.get("output_path") or (proof.get("output") if isinstance(proof, dict) else "")
        if not isinstance(path, str) or not path:
            self._status("저장된 Apply의 출력 경로가 없습니다 · 다시 Apply하세요")
            return
        if self._queue_cold_restore(project, records, path):
            return
        # Unsupported/custom transports and hosts without a running loop keep
        # the original driver policy. Never call a custom SDK driver in a worker.
        _raw, expected = self._verify_apply(project, records)
        try:
            actual = validate_png_bytes(File(path).read_bytes())
        except Exception:
            self._status("저장된 Apply 파일을 찾을 수 없습니다 · 다시 Apply하세요")
            return
        if actual != expected:
            self._status("저장된 Apply 파일이 변경되었습니다 · 다시 Apply하세요")
            return
        # Preserve the original synchronous legacy/custom-driver behavior:
        # adopting a REMOTE scope is optional there. The async path below has
        # stricter eligibility and must adopt its exact captured owner lease.
        self._adopt_verified_saved_editor_scope(project, records)
        self._publish_verified_saved_output(project, path, expected)

    def _queue_cold_restore(self, project: dict, records: list[dict], path: str) -> bool:
        """Verify saved source rasters/PNG in the existing bounded daemon."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return False
        from griptape_nodes.retained_mode.engine import has_current_engine
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
        if (not has_current_engine() or not loop.is_running()
                or GriptapeNodes.NodeManager().get_node_by_name(self.name) is not self):
            return False
        context = self.get_parameter_value("image_bash_context") or {}
        scope = self._apply_scope()
        metadata = self.metadata if isinstance(self.metadata, dict) else {}
        if (not isinstance(context, dict) or context.get("ready") is not True
                or not scope["workspace_id"] or not scope["channel_uuid"]
                or metadata.get("hmb_image_bash_workspace_id") != scope["workspace_id"]
                or metadata.get("hmb_image_bash_channel_uuid") != scope["channel_uuid"]):
            return False
        sources = self._remote_sources()
        bound = self._remote_bound_source(sources)
        if bound is None:
            return False
        catalog = next((value for node, value in sources if node is bound), {})
        workspace = next((row for row in catalog.get("workspaces", [])
                          if row.get("workspace_id") == scope["workspace_id"]), {})
        if workspace.get("revision") != scope["workspace_revision"] or workspace.get("count") != len(records):
            return False
        pending = self._hmb_cold_restore_pending
        if pending is not None and self._cold_restore_task_current(pending):
            return True
        read_paths = self._snapshot_read_paths(project, {"value": path}, records=records)
        if read_paths is None:
            return False
        canvas = self._canvas()
        self._hmb_apply_epoch += 1
        self._hmb_apply_pending = self._hmb_prepare_pending = None
        self._hmb_apply_rollback_document = None
        task = {"kind": "cold_restore", "epoch": self._hmb_apply_epoch,
            "project": deepcopy(project), "records": deepcopy(records), "canvas": canvas, "scope": scope,
            "read_paths": read_paths, "read_drivers": self._snapshot_driver_lease(read_paths),
            "scene": scene_fingerprint(project, records, canvas), "png_url": _url(project),
            "context": deepcopy(self.get_parameter_value("image_bash_context") or {}),
            "connections": self._apply_connection_lease(), "output_path": path,
            "output_setting": repr(self.get_parameter_value("output_file")),
            "host_snapshot": self._hmb_editor_snapshot_id}
        self._hmb_cold_restore_pending = task
        self._hmb_prepare_phase, self._hmb_prepare_error = "preparing", ""
        # A serialized output is not a newly verified live result. Keep a
        # genuinely verified existing result while a later restore is pending.
        if self._hmb_last_output is None:
            # Legacy saved receipts can keep their only output path in this
            # historical proof. Pending save/reopen must not lose that path.
            self._clear_output_now(preserve_verification=True)
        self._status("저장된 Apply 복원 중 · 이미지 원본과 완료 파일 확인")
        return self._start_snapshot_task(task, loop)

    @staticmethod
    def _calculate_cold_restore(task: dict, is_live) -> dict:
        """Pure file snapshot checks; no SDK, graph, publication or file write."""
        rgba_cache = OrderedDict()
        read = lambda url: HMBImageBash._snapshot_read(task, url)
        view = SimpleNamespace()
        view._canvas = lambda: task["canvas"]
        view._source_hashes = lambda project, **kwargs: HMBImageBash._source_hashes(
            None, project, **{**kwargs, "rgba_cache": rgba_cache, "is_live": is_live, "read_bytes": read})
        _raw, expected = HMBImageBash._verify_apply(view, task["project"], task["records"])
        actual = validate_png_bytes(read(task["output_path"]))
        if actual != expected:
            raise ValueError("저장된 Apply 파일이 변경되었습니다. 다시 Apply하세요.")
        if not is_live():
            raise ValueError("입력·연결·편집 변경으로 이전 저장본 확인을 중단했습니다.")
        # Fresh byte SHA checks after PNG decoding narrow the verification
        # window without moving UNC reads back to the host loop. External
        # files are still sequential snapshots, not atomic filesystem locks.
        receipt = task["project"].get("meta", {}).get("hmb_image_bash", {}).get("apply", {})
        fresh = HMBImageBash._source_hashes(None, task["project"], rgba_cache=rgba_cache,
            is_live=is_live, read_bytes=read)
        if fresh != receipt.get("source_hashes"):
            raise _ImageBashSourceError("복원 중 이미지 원본이 변경되었습니다. 입력을 다시 확인하세요.")
        if hashlib.sha256(read(task["output_path"])).hexdigest() != expected["png_sha256"]:
            raise ValueError("복원 중 완료 이미지 파일이 변경되었습니다. 다시 Apply하세요.")
        if not is_live():
            raise ValueError("새 작업으로 이전 저장본 확인을 중단했습니다.")
        return {"expected": expected}

    def _cold_restore_task_current(self, task: dict, *, adopted: bool = False) -> bool:
        if not self._apply_task_current(task):
            return False
        current = _document(self.get_parameter_value("bash_image"))
        old_meta, meta = task["project"].get("meta", {}), current.get("meta", {})
        old_hmb, hmb = old_meta.get("hmb_image_bash", {}), meta.get("hmb_image_bash", {})
        nonce = self._hmb_editor_snapshot_id if adopted else task["host_snapshot"]
        return (meta.get("created_at") == old_meta.get("created_at") and hmb.get("apply") == old_hmb.get("apply")
                and (adopted or hmb.get("editor_snapshot_id") == old_hmb.get("editor_snapshot_id"))
                and (not adopted or hmb.get("editor_snapshot_id") == self._hmb_editor_snapshot_id)
                and self._hmb_editor_snapshot_id == nonce
                and repr(self.get_parameter_value("output_file")) == task["output_setting"])

    @hmb_binding_mutation
    def _finish_cold_restore(self, task: dict, result: dict) -> bool:
        if not self._cold_restore_task_current(task):
            self._discard_apply_task(task)
            return False
        if result.get("error"):
            self._hmb_cold_restore_pending = None
            self._hmb_prepare_phase, self._hmb_prepare_error = "error", result["error"]
            self._status("저장본 준비 실패: " + result["error"] + " · 기존 장면과 완료 파일은 유지됩니다.")
            return False
        try:
            if not self._cold_restore_task_current(task):
                self._discard_apply_task(task)
                return False
            # Viewport and SDK envelope changes are non-rendering and excluded
            # from the scene fence. Adopt the current document, never rewind
            # them to the worker's older snapshot.
            current = _document(self.get_parameter_value("bash_image"))
            if not self._adopt_verified_saved_editor_scope(current, task["records"]):
                raise ValueError("저장된 Apply의 현재 작업 공간·연결을 확인하지 못했습니다.")
            if not self._cold_restore_task_current(task, adopted=True):
                self._discard_apply_task(task)
                return False
            if not self._publish_verified_saved_output(current, task["output_path"], result["expected"],
                    guard=lambda: self._cold_restore_task_current(task, adopted=True)):
                if not self._cold_restore_task_current(task, adopted=True):
                    self._discard_apply_task(task)
                    return False
                raise ValueError("검증된 저장 이미지를 현재 파일 서비스로 전달하지 못했습니다.")
            self._hmb_cold_restore_pending = None
            return True
        except Exception as exc:
            if self._hmb_cold_restore_pending is task:
                if not self._apply_task_current(task):
                    self._discard_apply_task(task)
                    return False
                self._hmb_cold_restore_pending = None
                self._hmb_prepare_phase, self._hmb_prepare_error = "error", str(exc)
                self._status("저장본 준비 실패: " + str(exc))
            return False

    def _publish_verified_saved_output(self, project: dict, path: str, expected: dict, *, guard=None) -> bool:
        """Host-only publication of an already verified existing file."""
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
        from griptape_nodes.drivers.storage.local_storage_driver import LocalStorageDriver
        driver = GriptapeNodes.StaticFilesManager().storage_driver
        if not isinstance(driver, LocalStorageDriver):
            self._status("출력 이미지를 제공할 로컬 파일 서비스를 확인하세요")
            return False
        if self._hmb_node_deleted:
            return False
        value = ImageUrlArtifact(value=driver.create_signed_download_url(Path(File(path).resolve())))
        # Resolving/signing stays on the host and can re-enter its request
        # hooks. The async result must still own the exact current lease.
        if self._hmb_node_deleted or (guard is not None and not guard()):
            return False
        verification = {"schema": "hmb-image-bash-run-v1", **expected, "apply_pixel_equal": True, "output": path}
        self.set_parameter_value("HMB_BASH_VERIFICATION", verification)
        self.parameter_output_values["HMB_BASH_VERIFICATION"] = verification
        self.publish_update_to_parameter("HMB_BASH_VERIFICATION", verification)
        self.set_parameter_value("output_image", value, emit_change=False)
        self.parameter_output_values["output_image"] = value
        self.publish_update_to_parameter("output_image", value)
        self._hmb_last_output = {"key": self._output_key(project, expected), "path": path,
                                 "workspace_id": self._canvas().get("workspace_id")}
        self._hmb_restore_pending = False
        self._hmb_output_generation += 1
        self._hmb_output_delivered = {}
        self._hmb_output_pending = not self._propagate_output(value, self._hmb_output_generation)
        self._status("저장된 Apply 복원 · 연결된 입력이 사용 가능해지면 Run으로 다시 전달하세요" if self._hmb_output_pending else "저장된 Apply 이미지 복원 완료")
        return True

    def after_node_deleted(self) -> None:
        self._hmb_node_deleted = True
        self._hmb_apply_pending = None
        self._hmb_prepare_pending = None
        self._hmb_cold_restore_pending = None
        self._hmb_apply_rollback_document = None
        with self._hmb_apply_work["lock"]:
            self._hmb_apply_work["queued"] = None
            self._hmb_apply_work["completed"] = None
        self._hmb_apply_epoch += 1
        self._hmb_output_generation += 1
        self._hmb_output_delivered = {}
        self._hmb_last_output = None
        return super().after_node_deleted()

    def _verify_apply(self, project: dict, records: list[dict], *, rgba_cache: OrderedDict | None = None) -> tuple[bytes, dict]:
        receipt = project.get("meta", {}).get("hmb_image_bash", {}).get("apply", {})
        if receipt.get("schema") != RECEIPT_SCHEMA:
            raise ValueError("편집기에서 Apply한 저장본이 없습니다.")
        if receipt.get("scene_sha256") != scene_fingerprint(project, records, self._canvas()):
            raise ValueError("레이어/입력/캔버스 변경 후 다시 Apply해야 합니다.")
        if receipt.get("source_hashes") != self._source_hashes(project, rgba_cache=rgba_cache):
            raise _ImageBashSourceError("원본 이미지가 변경되었습니다. 다시 Apply하세요.")
        raw = base64.b64decode(receipt["png_base64"], validate=True)
        if _url(project) != "data:image/png;base64," + receipt["png_base64"]:
            raise ValueError("편집기 이미지와 저장된 Apply 이미지가 다릅니다. 다시 Apply하세요.")
        if project.get("meta", {}).get("preview_url") != _url(project):
            raise ValueError("편집기 미리보기와 저장된 Apply 이미지가 다릅니다.")
        png = validate_png_bytes(raw)
        if any(png[key] != receipt.get(key) for key in png):
            raise ValueError("저장된 Apply PNG 무결성 검사에 실패했습니다.")
        return raw, png

    @hmb_binding_mutation
    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if self._hmb_syncing:
            return
        if parameter.name == HEADER_PARAMETER:
            if not self._hmb_header_publishing:
                self._header_command(value)
            return
        self._hmb_value_callback_depth += 1
        try:
            result = super().after_value_set(parameter, value)
            if parameter.name == "canvas_size":
                dimensions = CANVAS_PRESETS.get(value) if isinstance(value, str) else None
                for index, name in enumerate(("width", "height")):
                    dimension = self.get_parameter_by_name(name)
                    dimension.allowed_modes = {ParameterMode.OUTPUT} if dimensions else set(_DIMENSION_MODES)
                    if dimensions:
                        self.publish_update_to_parameter(name, dimensions[index])
            elif "input_images" in parameter.name:
                self._handle_input_images_change(value)
            elif parameter.name == "bash_image" and value is not None:
                self._handle_bash_image_change(value)
            if parameter.name == "image_bash_context":
                self._sync_metadata_with_input_images()
            elif parameter.name in {"width", "height", "background_color", "canvas_size"}:
                self._sync_metadata_with_input_images()
            return result
        finally:
            self._hmb_value_callback_depth -= 1

    def after_incoming_connection_removed(self, source_node, source_parameter, target_parameter) -> None:
        if "input_images" in target_parameter.name:
            self._sync_metadata_with_input_images()
        super().after_incoming_connection_removed(source_node, source_parameter, target_parameter)

    def _process_output_image(self) -> None:
        """Check the corrected compositor without publishing a mismatched render."""
        project = _document(self.get_parameter_value("bash_image"))
        try:
            applied, expected = self._verify_apply(project, self._records())
        except Exception:
            self._clear_output()
            raise
        canvas = self._canvas()
        def load(url):
            with Image.open(BytesIO(_read_bytes(url))) as image:
                return image.convert("RGBA")
        image = render_scene(project, canvas["width"], canvas["height"], canvas["background_color"], load)
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        raw = buffer.getvalue()
        recomposed = validate_png_bytes(raw)
        if any(recomposed[key] != expected[key] for key in ("width", "height", "rgba_sha256")):
            raise ValueError("원본 재합성과 Apply 픽셀이 다릅니다. comp_on_run을 끄고 검증된 Apply PNG를 출력하세요.")
        self._write_output(applied, expected, exact_apply=True)

    def _write_output(self, raw: bytes, expected: dict, *, exact_apply: bool) -> None:
        # FileDestination.write_bytes would inject workflow metadata a second
        # time into the editor's already-authored PNG. Use the SDK's atomic
        # writer with its explicit opt-out, retaining destination/macros/policy.
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
        from griptape_nodes.retained_mode.events.os_events import WriteFileRequest
        if self._hmb_node_deleted:
            raise ValueError("삭제된 Image Bash 노드에는 이미지를 출력할 수 없습니다.")
        key = self._output_key(_document(self.get_parameter_value("bash_image")), expected)
        destination = self._output_file.build_file()
        configured = destination._file
        cached = self._hmb_last_output
        saved = None
        if isinstance(cached, dict) and cached.get("key") == key:
            try:
                candidate = File(cached["path"])
                if validate_png_bytes(candidate.read_bytes()) == expected:
                    saved = candidate
            except Exception:
                pass
        if saved is None:
            result = GriptapeNodes.handle_request(WriteFileRequest(
                file_path=configured._file_path, content=raw,
                existing_file_policy=destination._existing_file_policy,
                append=destination._append, create_parents=destination._create_parents,
                coerce_extension_to_match_bytes=destination._coerce_extension_to_match_bytes,
                file_metadata=configured._build_file_metadata(), skip_metadata_injection=True))
            if not result.succeeded():
                raise ValueError("Apply PNG 저장 실패: " + str(result.result_details))
            saved = File(str(result.final_file_path))
        actual = validate_png_bytes(saved.read_bytes())
        if actual != expected:
            raise ValueError("Run 저장 이미지와 검증한 PNG가 다릅니다.")
        project = _document(self.get_parameter_value("bash_image"))
        receipt = project.get("meta", {}).get("hmb_image_bash", {}).get("apply", {})
        if receipt.get("output_path") != saved.location:
            receipt["output_path"] = saved.location
            self._set_project(project)
        # The native image preview runs in the editor browser. A Windows path
        # is a valid File value for Python but cannot be loaded by that browser.
        # Publish the SDK's original-file HTTP URL, not a lossy preview URL;
        # keep the permanent local destination in the verification receipt.
        from griptape_nodes.drivers.storage.local_storage_driver import LocalStorageDriver
        driver = GriptapeNodes.StaticFilesManager().storage_driver
        if not isinstance(driver, LocalStorageDriver):
            raise ValueError("출력 이미지를 제공할 로컬 파일 서비스를 확인하세요.")
        if self._hmb_node_deleted:
            raise ValueError("삭제된 Image Bash 노드에는 이미지를 출력할 수 없습니다.")
        previous_output = self.parameter_output_values.get("output_image")
        if (isinstance(cached, dict) and cached.get("key") == key and previous_output is not None):
            try:
                if Path(File(_url(previous_output)).resolve()) == Path(saved.resolve()):
                    if self._hmb_output_pending:
                        self._hmb_output_pending = not self._propagate_output(previous_output, self._hmb_output_generation)
                        self._status("Apply 저장 완료 · 연결된 입력이 사용 가능해지면 Run으로 다시 전달하세요" if self._hmb_output_pending else "Apply 저장 및 이미지 출력 완료")
                    return
            except Exception:
                pass
        result = ImageUrlArtifact(value=driver.create_signed_download_url(Path(saved.resolve())))
        proof = {"schema": "hmb-image-bash-run-v1", **actual,
                 "apply_pixel_equal": exact_apply, "output": saved.location}
        self.set_parameter_value("HMB_BASH_VERIFICATION", proof)
        self.parameter_output_values["HMB_BASH_VERIFICATION"] = proof
        self.publish_update_to_parameter("HMB_BASH_VERIFICATION", proof)
        self.set_parameter_value("output_image", result, emit_change=False)
        self.parameter_output_values["output_image"] = result
        self.publish_update_to_parameter("output_image", result)
        self._hmb_last_output = {"key": key, "path": saved.location,
                                 "workspace_id": self._canvas().get("workspace_id")}
        self._hmb_output_generation += 1
        self._hmb_output_delivered = {}
        self._hmb_output_pending = not self._propagate_output(result, self._hmb_output_generation)
        self._status("Apply 저장 완료 · 연결된 입력이 사용 가능해지면 Run으로 다시 전달하세요" if self._hmb_output_pending else
                     ("Apply = Run · RGBA 픽셀 일치" if exact_apply else "재합성 완료 · Apply 픽셀 일치 보증 대상 아님"))

    def process(self) -> None:
        # A deliberate Run supersedes any queued Apply/restore/invalidation;
        # it performs the same current-input verification synchronously.
        try:
            self._flush_pending_prepare()
            self._flush_pending_apply()
            cold_restore = self._hmb_cold_restore_pending
            self._hmb_cold_restore_pending = None
            self._hmb_apply_epoch += 1
            if self.get_parameter_value("comp_on_run") is True:
                if cold_restore is not None:
                    project = _document(self.get_parameter_value("bash_image"))
                    records = self._records()
                    self._verify_apply(project, records)
                    if not self._adopt_verified_saved_editor_scope(project, records):
                        raise ValueError("현재 입력으로 저장된 Apply를 확인하지 못했습니다.")
                self._process_output_image()
            else:
                project = _document(self.get_parameter_value("bash_image"))
                try:
                    raw, png = self._verify_apply(project, self._records())
                except Exception:
                    self._clear_output()
                    raise
                if cold_restore is not None and not self._adopt_verified_saved_editor_scope(project, self._records()):
                    raise ValueError("현재 입력으로 저장된 Apply를 확인하지 못했습니다.")
                self._write_output(raw, png, exact_apply=True)
        except Exception as exc:
            self._status("실행 중단: " + str(exc))
            raise
