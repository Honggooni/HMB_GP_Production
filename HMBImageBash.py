"""HMB adapter for the stock ImageBashModal; the Standard library is read only.

The editor's PNG is the authoritative render. A saved Apply transaction embeds
that PNG and its scene/source receipt, so a later Run never substitutes a PIL
approximation for an approved browser render.
"""
from __future__ import annotations

import base64
from copy import deepcopy
import hashlib
from io import BytesIO
from pathlib import Path
import sys
from typing import Any
from uuid import uuid4

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from griptape.artifacts import ImageUrlArtifact
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.files.file import File
from griptape_nodes.traits.widget import Widget
from PIL import Image

from _hmb_image_bash_compat import load_builtin_image_bash, require_standard_compatibility
from _hmb_image_bash_render import render_scene
from _hmb_image_bash_state import sync_scene, scene_fingerprint, validate_png_bytes

_StockImageBash = load_builtin_image_bash()
CONTEXT_SCHEMA = "hmb-image-bash-inputs-v1"
RECEIPT_SCHEMA = "hmb-image-bash-apply-v1"
HEADER_PARAMETER = "HMB_IMAGE_BASH_UI"
_HIDDEN_UI = {"hide": True, "hide_property": True, "hide_label": True,
              "hide_handles": True, "height": 1, "min_height": 0, "max_height": 1}


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


class HMBImageBash(_StockImageBash):
    """Stock editing UI with stable ImageAsset identities and verified Apply."""

    def __init__(self, **kwargs) -> None:
        self._hmb_syncing = True
        super().__init__(**kwargs)
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
        editor = self.get_parameter_by_name("bash_image")
        editor.ui_options = {**editor.ui_options, "button_label": "Open HMBImageBash Editor"}
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
        self.set_parameter_value("comp_on_run", False)
        self._hmb_syncing = False
        self._publish_header()

    def _remote_sources(self) -> list[tuple[Any, dict]]:
        from _hmb_shot_routing import _same_flow_nodes
        _, nodes = _same_flow_nodes(self)
        result = []
        for node in nodes:
            if bool(getattr(node, "_hmb_node_deleted", False)):
                continue
            getter = getattr(node, "_hmb_image_bash_catalog", None)
            if not callable(getter):
                continue
            catalog = getter()
            if catalog.get("schema") == "hmb-image-bash-workspace-catalog-v1":
                result.append((node, catalog))
        return result

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

    def _publish_header(self) -> None:
        if getattr(self, "_hmb_header_publishing", True):
            return
        self._hmb_header_publishing = True
        try:
            sources = self._remote_sources()
            bound = self._remote_bound_source(sources)
            context = self.get_parameter_value("image_bash_context") or {}
            projection = {"schema": "hmb-image-bash-header-v1", "sources": [
                {"id": node.name, "label": f"{node.name} · {workspace.get('name', 'HMBImageBash')}",
                 "workspace_id": workspace["workspace_id"]}
                for node, catalog in sources for workspace in catalog.get("workspaces", [])],
                "source_instances": {node.name: self._remote_source_instance(node)
                    for node, catalog in sources if catalog.get("workspaces")},
                "bound_source": bound.name if bound else "", "image_count": len(context.get("records", [])),
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
        except Exception:
            # Native construction/restoration precedes registration in a flow.
            # Refresh and the next input update retry once registration exists.
            pass
        finally:
            self._hmb_header_publishing = False

    def _header_command(self, value: Any) -> None:
        request = value.get("hmb_image_bash_command", {}) if isinstance(value, dict) else {}
        try:
            operation = request.get("operation")
            if operation == "refresh":
                # Source discovery is presentation-only. Re-reading rasters or
                # syncing the scene here would turn every topology/focus event
                # into an edit, invalidating a retained Apply unnecessarily.
                # Input changes, Apply and Run retain their full validation.
                return
            if operation not in {"bind", "unbind"}:
                raise ValueError("지원하지 않는 리모트 연결 요청입니다.")
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
                and any(row["workspace_id"] == request.get("workspace_id") for row in catalog.get("workspaces", []))), None)
            if selected is None:
                raise ValueError("선택한 이미지 라이브러리 작업 공간을 다시 확인하세요.")
            # Legacy direct commands have no lease. The current widget always
            # carries this transient projection token, so a delayed selection
            # cannot silently bind a new object with the old name/workspace.
            if ("source_instance_id" in request
                    and request["source_instance_id"] != self._remote_source_instance(selected)):
                raise ValueError("이미지 라이브러리가 교체되었습니다. 목록에서 다시 선택하세요.")
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

    def _clear_output(self) -> None:
        self.set_parameter_value("output_image", None)
        self.parameter_output_values["output_image"] = None
        self.publish_update_to_parameter("output_image", None)
        self.set_parameter_value("HMB_BASH_VERIFICATION", {})
        self.parameter_output_values["HMB_BASH_VERIFICATION"] = {}

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
        previous = self._hmb_syncing
        self._hmb_syncing = True
        try:
            self.set_parameter_value("bash_image", project)
            self.publish_update_to_parameter("bash_image", project)
        finally:
            self._hmb_syncing = previous

    def _sync_project(self, project: dict, records: list[dict], *, add_missing: bool = True) -> dict:
        canvas = self._canvas()
        # file:// launches the native editor's lossy preview conversion. Mint
        # the original-file URL through the SDK's existing local storage driver
        # so the canvas receives full-quality source bytes, on Windows/UNC too.
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
        def create(record, index):
            return self._create_konva_layer(record, index, canvas["width"], canvas["height"])
        return sync_scene(project, editor_records, create, add_missing=add_missing)

    def _sync_metadata_with_input_images(self) -> None:
        if self._hmb_syncing or getattr(self, "_initializing", False):
            return
        try:
            records = self._records()
            project = _document(self.get_parameter_value("bash_image"))
            updated = self._sync_project(project, records)
            hmb = updated.setdefault("meta", {}).setdefault("hmb_image_bash", {})
            if updated != project or "prepared_source_hashes" not in hmb:
                hmb["prepared_source_hashes"] = self._source_hashes(updated)
            if updated != project:
                self._set_project(updated)
            receipt = updated.get("meta", {}).get("hmb_image_bash", {}).get("apply")
            if not receipt or receipt.get("scene_sha256") != scene_fingerprint(updated, records, self._canvas()):
                self._clear_output()
                self._status("입력이 변경되었습니다 · 편집기에서 Apply 필요")
        except Exception as exc:
            self._clear_output()
            self._status(str(exc))
        finally:
            self._publish_header()

    def _handle_input_images_change(self, value: Any) -> None:
        self._sync_metadata_with_input_images()

    def _handle_input_images_removed(self) -> None:
        self._sync_metadata_with_input_images()

    def _source_hashes(self, project: dict, *, cache: dict | None = None) -> dict:
        """Read every source before committing; a missing hidden layer also fails."""
        sources = project.get("meta", {}).get("input_images", [])
        hashes = {}
        loaded = {} if cache is None else cache
        def check(url):
            if not url:
                raise ValueError("Image Bash source URL is missing.")
            if url not in loaded:
                raw = _read_bytes(url)
                with Image.open(BytesIO(raw)) as image:
                    image.load()
                    rgba = image.convert("RGBA")
                    loaded[url] = {"sha256": hashlib.sha256(raw).hexdigest(),
                        "rgba_sha256": hashlib.sha256(rgba.tobytes()).hexdigest(),
                        "width": rgba.width, "height": rgba.height}
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

    def _handle_bash_image_change(self, value: Any) -> None:
        if self._hmb_syncing or getattr(self, "_initializing", False):
            return
        self._clear_output()
        try:
            project = _document(value)
            if not _url(project) or _url(project).startswith("data:image/svg"):
                self._status("편집기에서 Apply 필요")
                return
            # A receipt arriving from workflow deserialization must be verified,
            # never silently renewed against changed sources.
            retained = project.get("meta", {}).get("hmb_image_bash", {}).get("apply")
            editor_commit = project.get("meta", {}).get("created_at")
            if retained and retained.get("editor_commit") == editor_commit:
                # Native deserialization restores stock parameters before our
                # appended context/input connections. Defer validation to Run.
                self._status("저장된 Apply 복원됨 · Run에서 입력과 무결성 검사")
                return
            records = self._records()
            require_standard_compatibility()
            updated = self._sync_project(project, records, add_missing=False)
            source_cache = {}
            source_hashes = self._source_hashes(updated, cache=source_cache)
            same_render = self._render_layers(updated) == self._render_layers(project)
            if same_render:
                try:
                    # The native editor resolves C:/ paths to browser URLs.
                    # Equal decoded rasters are the same source despite an alias.
                    self._source_hashes(project, cache=source_cache)
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
            raw = _read_bytes(_url(project))
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
                raise ValueError("편집기를 연 뒤 원본 이미지가 변경되었습니다. 다시 열어 확인하고 Apply하세요.")
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
            project["meta"]["hmb_image_bash"]["prepared_source_hashes"] = source_hashes
            self._set_project(project)
            self._status("Apply 저장 완료 · Run은 동일 PNG를 저장합니다")
        except Exception as exc:
            self._status("Apply 검증 실패: " + str(exc))
            raise

    def _verify_apply(self, project: dict, records: list[dict]) -> tuple[bytes, dict]:
        require_standard_compatibility()
        receipt = project.get("meta", {}).get("hmb_image_bash", {}).get("apply", {})
        if receipt.get("schema") != RECEIPT_SCHEMA:
            raise ValueError("편집기에서 Apply한 저장본이 없습니다.")
        if receipt.get("scene_sha256") != scene_fingerprint(project, records, self._canvas()):
            raise ValueError("레이어/입력/캔버스 변경 후 다시 Apply해야 합니다.")
        if receipt.get("source_hashes") != self._source_hashes(project):
            raise ValueError("원본 이미지가 변경되었습니다. 다시 Apply하세요.")
        raw = base64.b64decode(receipt["png_base64"], validate=True)
        if _url(project) != "data:image/png;base64," + receipt["png_base64"]:
            raise ValueError("편집기 이미지와 저장된 Apply 이미지가 다릅니다. 다시 Apply하세요.")
        if project.get("meta", {}).get("preview_url") != _url(project):
            raise ValueError("편집기 미리보기와 저장된 Apply 이미지가 다릅니다.")
        png = validate_png_bytes(raw)
        if any(png[key] != receipt.get(key) for key in png):
            raise ValueError("저장된 Apply PNG 무결성 검사에 실패했습니다.")
        return raw, png

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if self._hmb_syncing:
            return
        if parameter.name == HEADER_PARAMETER:
            if not self._hmb_header_publishing:
                self._header_command(value)
            return
        result = super().after_value_set(parameter, value)
        if parameter.name == "image_bash_context":
            self._sync_metadata_with_input_images()
        elif parameter.name in {"width", "height", "background_color", "canvas_size"}:
            self._sync_metadata_with_input_images()
        return result

    def _process_output_image(self) -> None:
        """Check the corrected compositor without publishing a mismatched render."""
        project = _document(self.get_parameter_value("bash_image"))
        records = self._records()
        applied, expected = self._verify_apply(project, records)
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
        destination = self._output_file.build_file()
        configured = destination._file
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
        # The native image preview runs in the editor browser. A Windows path
        # is a valid File value for Python but cannot be loaded by that browser.
        # Publish the SDK's original-file HTTP URL, not a lossy preview URL;
        # keep the permanent local destination in the verification receipt.
        from griptape_nodes.drivers.storage.local_storage_driver import LocalStorageDriver
        driver = GriptapeNodes.StaticFilesManager().storage_driver
        if not isinstance(driver, LocalStorageDriver):
            raise ValueError("출력 이미지를 제공할 로컬 파일 서비스를 확인하세요.")
        result = ImageUrlArtifact(value=driver.create_signed_download_url(Path(saved.resolve())))
        proof = {"schema": "hmb-image-bash-run-v1", **actual,
                 "apply_pixel_equal": exact_apply, "output": saved.location}
        self.set_parameter_value("HMB_BASH_VERIFICATION", proof)
        self.parameter_output_values["HMB_BASH_VERIFICATION"] = proof
        self.publish_update_to_parameter("HMB_BASH_VERIFICATION", proof)
        self.set_parameter_value("output_image", result)
        self.parameter_output_values["output_image"] = result
        self.publish_update_to_parameter("output_image", result)
        self._status("Apply = Run · RGBA 픽셀 일치" if exact_apply else "재합성 완료 · Apply 픽셀 일치 보증 대상 아님")

    def process(self) -> None:
        self._clear_output()
        try:
            require_standard_compatibility()
            if self.get_parameter_value("comp_on_run") is True:
                self._process_output_image()
            else:
                project = _document(self.get_parameter_value("bash_image"))
                raw, png = self._verify_apply(project, self._records())
                self._write_output(raw, png, exact_apply=True)
        except Exception as exc:
            self._clear_output()
            self._status("실행 중단: " + str(exc))
            raise
