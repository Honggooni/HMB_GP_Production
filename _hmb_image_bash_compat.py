"""Read-only compatibility gate for HMB's adapter of the installed Image Bash.

An upstream version string is diagnostic only. A changed Image Bash source or
built-in editor feature region requires review. This module never rewrites an
upstream file or updates its own approved baseline.
"""
from __future__ import annotations

import ast
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

STANDARD_NAME = "Griptape Nodes Library"
MANIFEST_NAME = "griptape_nodes_library.json"
SOURCE_RELATIVE = "griptape_nodes_library/image/image_bash.py"
MODULE_NAME = "griptape_nodes_library.image.image_bash"
BASELINE_PATH = Path(__file__).resolve().parent / "resources" / "image_bash" / "compatibility.json"
ADAPTER_CONTRACT = "hmb-image-bash-compatibility-v1"
REQUIRED_PARAMETERS = (
    "canvas_size", "width", "height", "background_color", "input_images",
    "output_image", "bash_image", "comp_on_run", "output_file",
)
REQUIRED_METHODS = (
    "__init__", "_get_image_dimensions", "_get_canvas_dimensions",
    "_create_viewport_metadata", "_update_bash_image_metadata",
    "_process_input_image", "_is_brush_layer", "_create_konva_layer",
    "_build_konva_images", "_sync_metadata_with_input_images",
    "_handle_input_images_removed", "_create_new_bash_image",
    "_handle_bash_image_change", "after_value_set",
    "after_incoming_connection_removed", "_process_output_image",
    "_update_output_image", "process",
)
# Deliberately pinned to the reviewed editor build. Each anchor is unique and
# lands at a complete component/function declaration boundary. An upstream
# rebuild that renames these symbols needs review, rather than a guessed slice.
# The brush region contains the actual modal's load/restore/PNG-export callbacks.
EDITOR_SCOPES = {
    "modal_store": ("var iGn={brushType:", ",cGn={isOpen:"),
    "parameter_launch": ("function rSr(e){let t=(0,C.c)(33),{label:", "function iSr(e){"),
    "brush_layers_load_export_modal": ("function x5(e){if(e.startsWith(`rgba(`))", "function WZr(e,t){"),
    "modal_settings": ("function Z4r(e,t,r,i,a={min:0,max:1,step:.01})", ",$4r=.15;"),
}


class ImageBashCompatibilityError(RuntimeError):
    """The installed node/editor is not the reviewed adapter contract."""

    def __init__(self, message: str, diagnostics: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.diagnostics = diagnostics or {}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _inside(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve(strict=True)
    candidate.relative_to(root)
    if not candidate.is_file():
        raise ValueError(f"Expected a file: {relative}")
    return candidate


def _standard_root(candidate: str | Path) -> Path:
    path = Path(candidate).expanduser().resolve(strict=True)
    root = path.parent if path.is_file() else path
    manifest_path = _inside(root, MANIFEST_NAME)
    if manifest_path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError("Standard Library manifest is too large")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    if manifest.get("name") != STANDARD_NAME:
        raise ValueError("Expected the registered Griptape Nodes Library")
    records = manifest.get("nodes", [])
    if not isinstance(records, list):
        raise ValueError("Invalid Standard Library node registrations")
    registrations = [record for record in records
                     if isinstance(record, dict) and record.get("class_name") == "ImageBash"]
    if (len(registrations) != 1
            or str(registrations[0].get("file_path", "")).replace("\\", "/") != SOURCE_RELATIVE):
        raise ValueError("Canonical ImageBash registration is missing")
    _inside(root, SOURCE_RELATIVE)
    return root


def resolve_standard_root(standard_root: str | Path | None = None) -> Path:
    """Prefer explicit configuration and the engine's actual discovery record.

    The two conventional locations are only for a standalone diagnostic process
    where the retained-mode host is unavailable. A rejected host registration
    never falls through to a different installed copy.
    """
    explicit = standard_root or os.environ.get("HMB_IMAGE_BASH_STANDARD_LIBRARY_PATH") or os.environ.get(
        "HMB_GRIPTAPE_STANDARD_LIBRARY_PATH"
    )
    if explicit:
        try:
            return _standard_root(explicit)
        except Exception as exc:
            raise ImageBashCompatibilityError(f"Configured Standard Image Bash is invalid: {exc}") from exc
    try:
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
        manager = GriptapeNodes.LibraryManager()
    except Exception:
        manager = None
    if manager is not None:
        try:
            info = manager.get_library_info_by_library_name(STANDARD_NAME)
        except Exception as exc:
            raise ImageBashCompatibilityError(f"Cannot read the host Standard Library registration: {exc}") from exc
        if info is not None:
            lifecycle = str(getattr(getattr(info, "lifecycle_state", None), "name", "")).upper()
            if getattr(info, "enabled", True) is False or lifecycle == "FAILURE":
                raise ImageBashCompatibilityError("The host Standard Library is disabled or failed to load")
            try:
                return _standard_root(str(info.library_path))
            except Exception as exc:
                raise ImageBashCompatibilityError(f"The host Standard Image Bash registration is invalid: {exc}") from exc
        raise ImageBashCompatibilityError("The running host has no Standard Library discovery record")
    module = sys.modules.get(MODULE_NAME)
    candidates: list[Path] = []
    if module is not None and getattr(module, "__file__", None):
        candidates.append(Path(module.__file__).resolve().parents[2])
    try:
        spec = importlib.util.find_spec("griptape_nodes_library")
        if spec and spec.submodule_search_locations:
            candidates.extend(Path(location).parent for location in spec.submodule_search_locations)
    except (ImportError, ValueError, AttributeError):
        pass
    candidates.extend((
        Path(__file__).resolve().parent.parent / "griptape-nodes-library-standard",
        Path.home() / "Documents" / "GriptapeNodes" / "libraries" / "griptape-nodes-library-standard",
    ))
    for candidate in candidates:
        try:
            return _standard_root(candidate)
        except (OSError, ValueError, KeyError, TypeError):
            continue
    raise ImageBashCompatibilityError(
        "Standard Image Bash was not found. Register the Standard Library or set "
        "HMB_IMAGE_BASH_STANDARD_LIBRARY_PATH to its exact library directory."
    )


def resolve_editor_root(editor_root: str | Path | None = None) -> Path | None:
    """Locate the bundled editor without assuming a user account or drive."""
    explicit = editor_root or os.environ.get("HMB_IMAGE_BASH_EDITOR_BUNDLE_PATH")
    if explicit:
        root = Path(explicit).expanduser().resolve(strict=True)
        if not root.is_dir():
            raise ValueError("Configured editor bundle is not a directory")
        return root
    candidates = [parent / "editor-bundle" for parent in Path(sys.executable).resolve().parents]
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.append(Path(local_app_data) / "ai.griptape.nodes.desktop" / "current" / "resources" / "editor-bundle")
    for candidate in candidates:
        if candidate.is_dir() and (candidate / "assets").is_dir():
            return candidate.resolve()
    return None


def source_contract(source: str) -> dict[str, Any]:
    """Inspect the modal/scene seam without executing any candidate source."""
    tree = ast.parse(source)
    node = next((item for item in tree.body if isinstance(item, ast.ClassDef) and item.name == "ImageBash"), None)
    if node is None:
        raise ValueError("ImageBash class is missing")
    methods = sorted(item.name for item in node.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)))
    parameters: set[str] = set()
    modal = None
    scene_keys: list[str] = []
    scene_collection_keys: list[str] = []
    for call in ast.walk(node):
        if not isinstance(call, ast.Call):
            continue
        kwargs = {keyword.arg: keyword.value for keyword in call.keywords if keyword.arg}
        name_node = kwargs.get("name")
        if not isinstance(name_node, ast.Constant) or not isinstance(name_node.value, str):
            continue
        call_name = call.func.id if isinstance(call.func, ast.Name) else ""
        if call_name not in {"Parameter", "ParameterList", "ProjectFileParameter"}:
            continue
        parameters.add(name_node.value)
        if name_node.value != "bash_image":
            continue
        ui = kwargs.get("ui_options")
        if isinstance(ui, ast.Dict):
            for key, value in zip(ui.keys, ui.values):
                if isinstance(key, ast.Constant) and key.value == "modal" and isinstance(value, ast.Constant):
                    modal = value.value
        default = kwargs.get("default_value")
        if isinstance(default, ast.Dict):
            meta = next((value for key, value in zip(default.keys, default.values)
                         if isinstance(key, ast.Constant) and key.value == "meta"), None)
            if isinstance(meta, ast.Dict):
                scene_keys = sorted(key.value for key in meta.keys if isinstance(key, ast.Constant) and isinstance(key.value, str))
                konva = next((value for key, value in zip(meta.keys, meta.values)
                              if isinstance(key, ast.Constant) and key.value == "konva_json"), None)
                if isinstance(konva, ast.Dict):
                    scene_collection_keys = sorted(key.value for key in konva.keys
                                                   if isinstance(key, ast.Constant) and isinstance(key.value, str))
    return {
        "class_name": "ImageBash", "parameters": sorted(parameters), "methods": methods,
        "modal": modal, "scene_metadata_keys": scene_keys, "scene_collection_keys": scene_collection_keys,
    }


def editor_contract(source: str, anchors: dict[str, tuple[str, str]] | None = None) -> dict[str, dict[str, Any]]:
    """Hash exact reviewed feature regions while retaining unrelated bundle drift.

    No candidate JavaScript executes. Both boundary anchors must occur exactly
    once; missing, ambiguous or reordered sections fail closed.
    """
    result: dict[str, dict[str, Any]] = {}
    for scope, (start_anchor, end_anchor) in (anchors or EDITOR_SCOPES).items():
        if source.count(start_anchor) != 1 or source.count(end_anchor) != 1:
            raise ValueError(f"Image Bash editor anchors changed or are ambiguous: {scope}")
        start, end = source.index(start_anchor), source.index(end_anchor)
        if end <= start:
            raise ValueError(f"Image Bash editor boundaries are reordered: {scope}")
        raw = source[start:end].encode("utf-8")
        result[scope] = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    return result


def _active_editor_bundle(root: Path) -> tuple[str, bytes]:
    """Inspect only the bundle named by the current editor entry, without writes."""
    entry = _inside(root, "index-editor.html")
    if entry.stat().st_size > 1024 * 1024:
        raise ValueError("Editor entry is too large")
    html = entry.read_bytes()
    matches = re.findall(rb'''\bsrc\s*=\s*["']\./assets/(index-[A-Za-z0-9_-]+\.js)["']''', html)
    if len(matches) != 1:
        raise ValueError("Active editor entry is missing or ambiguous")
    relative = "assets/" + matches[0].decode("ascii")
    path = _inside(root, relative)
    before = path.stat()
    if before.st_size > 64 * 1024 * 1024:
        raise ValueError("Editor bundle is too large")
    source = path.read_bytes()
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns) or len(source) != before.st_size:
        raise ValueError("Editor bundle changed during inspection")
    if entry.read_bytes() != html:
        raise ValueError("Active editor entry changed during inspection")
    return relative, source


def _editor_profiles(baseline: dict[str, Any]) -> list[dict[str, Any]]:
    """Build only explicitly approved scope profiles; never approve observed code."""
    editor = baseline.get("editor", {})
    profiles = []
    # The historical reviewed four-region baseline remains valid independent
    # of the original filename or editor version label.
    bundles = editor.get("bundles", {})
    if not isinstance(bundles, dict):
        raise ValueError("Invalid Image Bash legacy profiles")
    for relative, bundle in bundles.items():
        if not isinstance(bundle, dict) or set(bundle.get("scopes", {})) != set(EDITOR_SCOPES):
            raise ValueError("Incomplete Image Bash legacy profile")
        profiles.append({"id": "legacy:" + relative, "anchors": EDITOR_SCOPES,
                         "scopes": bundle["scopes"], "sha256": bundle.get("sha256")})
    additional = editor.get("profiles", [])
    if not isinstance(additional, list) or len(additional) > 16:
        raise ValueError("Invalid Image Bash profile list")
    for row in additional:
        if not isinstance(row, dict) or row.get("review_status") != "approved":
            continue
        scope_rows = row.get("regions")
        if not isinstance(scope_rows, dict) or set(scope_rows) != set(EDITOR_SCOPES):
            raise ValueError("Incomplete Image Bash approved profile")
        anchors, hashes = {}, {}
        for name, region in scope_rows.items():
            if not isinstance(region, dict) or set(region) != {"start", "end", "sha256", "bytes"}:
                raise ValueError("Invalid Image Bash approved region")
            start, end, digest, size = (region[k] for k in ("start", "end", "sha256", "bytes"))
            if (not all(isinstance(v, str) and 0 < len(v) <= 512 for v in (start, end))
                    or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
                    or type(size) is not int or not 0 < size <= 64 * 1024 * 1024):
                raise ValueError("Invalid Image Bash approved region values")
            anchors[name] = (start, end)
            hashes[name] = {"sha256": digest, "bytes": size}
        profile_id = row.get("id")
        if not isinstance(profile_id, str) or not profile_id or len(profile_id) > 128:
            raise ValueError("Invalid Image Bash profile identity")
        profiles.append({"id": profile_id, "anchors": anchors, "scopes": hashes, "sha256": row.get("sha256")})
    if not profiles:
        raise ValueError("The approved Image Bash editor section baseline is missing")
    return profiles


def inspect_standard_compatibility(
    standard_root: str | Path | None = None, *,
    baseline_path: str | Path | None = None,
    editor_root: str | Path | None = None,
    require_editor: bool = True,
) -> dict[str, Any]:
    """Return JSON-safe diagnostics; never import or modify upstream source."""
    result: dict[str, Any] = {
        "schema": ADAPTER_CONTRACT, "compatible": False, "status": "review_required",
        "errors": [], "standard": {}, "editor": {"status": "not_checked"},
    }
    errors: list[str] = result["errors"]
    try:
        baseline = json.loads(Path(baseline_path or BASELINE_PATH).read_text(encoding="utf-8-sig"))
        if baseline.get("schema") != ADAPTER_CONTRACT:
            raise ValueError("Unknown compatibility baseline schema")
        root = resolve_standard_root(standard_root)
        manifest_path, source_path = _inside(root, MANIFEST_NAME), _inside(root, SOURCE_RELATIVE)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        contract = source_contract(source_path.read_text(encoding="utf-8-sig"))
        current = {
            "root": str(root),
            "manifest_sha256": _sha256(manifest_path), "source_sha256": _sha256(source_path),
            "source_relative": SOURCE_RELATIVE, "contract": contract,
        }
        result["standard"] = current
        approved = baseline["standard"]
        # Griptape's release label is neither stored nor consulted. Admit only
        # canonical registration, reviewed source and source/editor contracts.
        # Unrelated manifest changes cannot approve a changed implementation.
        current["observations"] = [
            f"Standard {key} changed; exact ImageBash source and contract were checked"
            for key in ("manifest_sha256",)
            if current[key] != approved.get(key)
        ]
        if current["source_sha256"] != approved.get("source_sha256"):
            errors.append("Standard source_sha256 changed; review and adapter regression are required")
        for parameter in REQUIRED_PARAMETERS:
            if parameter not in contract["parameters"]:
                errors.append(f"ImageBash parameter is missing: {parameter}")
        for method in REQUIRED_METHODS:
            if method not in contract["methods"]:
                errors.append(f"ImageBash method is missing: {method}")
        if contract["modal"] != "ImageBashModal":
            errors.append("The built-in ImageBashModal contract changed")
        if not {"input_images", "konva_json", "viewport"}.issubset(contract["scene_metadata_keys"]):
            errors.append("ImageBash scene metadata contract changed")
        if not {"images", "lines"}.issubset(contract["scene_collection_keys"]):
            errors.append("ImageBash image/brush scene collections changed")
        if contract != approved.get("contract"):
            errors.append("ImageBash source structure changed; preserve/migrate saved metadata before approval")
        editor = resolve_editor_root(editor_root)
        if editor is None:
            result["editor"] = {"status": "unavailable"}
            if require_editor:
                errors.append("The actual editor bundle is unavailable; editor compatibility is unverified")
        else:
            relative, raw = _active_editor_bundle(editor)
            source = raw.decode("utf-8")
            full_hash = hashlib.sha256(raw).hexdigest()
            observations, reasons, accepted = [], [], None
            for profile in _editor_profiles(baseline):
                try:
                    scopes = editor_contract(source, profile["anchors"])
                    changed = [scope for scope, observed in scopes.items() if observed != profile["scopes"].get(scope)]
                    if changed:
                        reasons.extend(f"Image Bash editor section changed: {scope}" for scope in changed)
                        continue
                    accepted = (profile, scopes)
                    break
                except ValueError as exc:
                    reasons.append(str(exc))
            observed = {"sha256": full_hash}
            if accepted is None:
                result["editor"] = {"status": "changed", "root": str(editor), "active_bundle": relative,
                                    "bundles": {relative: observed}, "observations": []}
                errors.extend(reasons or ["Active Image Bash editor has no reviewed feature profile"])
            else:
                profile, scopes = accepted
                observed.update(scopes=scopes, whole_bundle_changed=full_hash != profile.get("sha256"))
                if observed["whole_bundle_changed"]:
                    observations.append(f"Editor bundle SHA changed: {relative}; exact Image Bash sections checked separately")
                result["editor"] = {"status": "matches_contract" if observations else "matches_baseline",
                                    "root": str(editor), "active_bundle": relative, "profile": profile["id"],
                                    "bundles": {relative: observed}, "observations": observations}
    except Exception as exc:
        errors.append(f"Compatibility inspection failed: {exc}")
    result["compatible"] = not errors
    result["status"] = "matches_baseline" if not errors else "review_required"
    return result


def require_standard_compatibility(*args: Any, **kwargs: Any) -> dict[str, Any]:
    diagnostics = inspect_standard_compatibility(*args, **kwargs)
    if not diagnostics["compatible"]:
        raise ImageBashCompatibilityError(
            "HMB Image Bash compatibility review required: " + "; ".join(diagnostics["errors"]), diagnostics
        )
    return diagnostics


def load_builtin_image_bash(
    standard_root: str | Path | None = None, *,
    baseline_path: str | Path | None = None,
    editor_root: str | Path | None = None,
    require_editor: bool = True,
) -> type:
    """Return the exact registered built-in class, after read-only approval checks.

    A stale package already imported from another installation is an explicit
    failure. Replacing sys.modules or globally monkeypatching the stock node
    would affect unrelated Standard nodes and is deliberately avoided.
    """
    diagnostics = require_standard_compatibility(
        standard_root, baseline_path=baseline_path, editor_root=editor_root, require_editor=require_editor,
    )
    root = Path(diagnostics["standard"]["root"])
    expected = _inside(root, SOURCE_RELATIVE)

    def validated(candidate: Any) -> type:
        if not isinstance(candidate, type) or candidate.__name__ != "ImageBash":
            raise ValueError("The registered ImageBash object is not the built-in class")
        module = importlib.import_module(candidate.__module__)
        actual = Path(module.__file__).resolve(strict=True)
        if actual != expected:
            raise ValueError("A different Standard Image Bash is already loaded; restart after reviewing the installation")
        if not callable(getattr(candidate, "process", None)) or not callable(getattr(candidate, "add_parameter", None)):
            raise ValueError("ImageBash is not a native Griptape node class")
        return candidate

    try:
        from griptape_nodes.node_library.library_registry import LibraryRegistry
        registered = LibraryRegistry.get_library(STANDARD_NAME)
    except (ImportError, KeyError):
        registered = None
    if registered is not None:
        try:
            return validated(registered.get_node_class("ImageBash"))
        except Exception as exc:
            raise ImageBashCompatibilityError(f"Registered Standard Image Bash cannot be loaded: {exc}", diagnostics) from exc
    root_string = str(root)
    if root_string not in sys.path:
        sys.path.append(root_string)
    importlib.invalidate_caches()
    try:
        module = importlib.import_module(MODULE_NAME)
        return validated(module.ImageBash)
    except Exception as exc:
        raise ImageBashCompatibilityError(f"Approved Standard Image Bash import failed: {exc}", diagnostics) from exc
