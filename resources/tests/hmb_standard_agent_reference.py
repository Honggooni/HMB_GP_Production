"""Locate the external Standard Agent for SDK comparison fixtures."""
from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
import re
import sys
import sysconfig
from typing import Any, Optional, Type

ROOT = Path(__file__).resolve().parents[2]
PATH_LOG_PREFIX = "[HMB_REFERENCE][PATH]"
WARN_LOG_PREFIX = "[HMB_REFERENCE][WARN]"


_STANDARD_AGENT_IMPORT_WARNINGS: set[tuple[str, str, str]] = set()


def _standard_agent_import_warning(stage: str, error: Exception) -> None:
    """Bounded import diagnostics; exception text may contain private values."""
    error_type = type(error).__name__
    if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]{0,79}", error_type):
        error_type = "ImportFailure"
    missing = getattr(error, "name", None) if isinstance(error, ModuleNotFoundError) else None
    if not isinstance(missing, str) or len(missing) > 160 or not re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", missing):
        missing = ""
    identity = (stage, error_type, missing)
    if identity in _STANDARD_AGENT_IMPORT_WARNINGS or len(_STANDARD_AGENT_IMPORT_WARNINGS) >= 64:
        return
    _STANDARD_AGENT_IMPORT_WARNINGS.add(identity)
    try:
        print(f"{WARN_LOG_PREFIX} Standard Agent import unavailable: stage={stage} type={error_type} missing_module={missing or '-'}")
    except Exception:
        pass


def _append_standard_agent_edit_dependencies(root: Path) -> None:
    """Use only this validated package's edit environment, after host paths.

    Append a directory directly: site.addsitedir would execute arbitrary .pth
    files. Never infer a sibling, scan home, or change loaded SDK modules.
    An absent environment is optional when the native Agent is already usable.
    """
    try:
        root = root.resolve(strict=True)
        venv = (root / ".venv").resolve(strict=True)
        venv.relative_to(root)
        configuration = (venv / "pyvenv.cfg").resolve(strict=True)
        configuration.relative_to(venv)
        if not configuration.is_file() or configuration.stat().st_size > 16 * 1024:
            return
        site_packages = Path(sysconfig.get_path("purelib", vars={"base": str(venv), "platbase": str(venv)})).resolve(strict=True)
        site_packages.relative_to(venv)
        if site_packages.is_dir() and str(site_packages) not in sys.path:
            sys.path.append(str(site_packages))
            importlib.invalidate_caches()
    except (OSError, ValueError, TypeError):
        return


def _configured_standard_library_root() -> Optional[Path]:
    """Return only the explicitly configured Standard Library package root."""
    explicit = os.environ.get("HMB_GRIPTAPE_STANDARD_LIBRARY_PATH", "").strip()
    if not explicit:
        return None
    try:
        configured = Path(explicit).expanduser().resolve(strict=True)
        if configured.is_file():
            if configured.name.casefold() != "agent.py":
                raise ValueError("configured file is not the canonical Agent module")
            configured = configured.parents[2]
        elif configured.name.casefold() == "griptape_nodes_library":
            configured = configured.parent
        agent_file = (
            configured / "griptape_nodes_library" / "agents" / "agent.py"
        ).resolve(strict=True)
        if not agent_file.is_file():
            raise FileNotFoundError(agent_file)
        return configured
    except Exception as exc:
        try:
            _standard_agent_import_warning("explicit_root", exc)
        except Exception:
            pass
        return None


def _validated_registered_standard_library_root(candidate: Path) -> Optional[Path]:
    """Validate a host-reported Standard Library manifest/root and Agent file."""
    try:
        resolved = candidate.expanduser().resolve(strict=True)
        if resolved.is_file():
            manifest_path = resolved
            root = manifest_path.parent
        else:
            root = resolved
            manifest_path = (root / "griptape_nodes_library.json").resolve(strict=True)
        if not root.is_dir():
            raise ValueError("Standard Library root is not a directory")
        if not manifest_path.is_file() or manifest_path.stat().st_size > 4 * 1024 * 1024:
            raise ValueError("invalid Standard Library manifest")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("name") != "Griptape Nodes Library":
            raise ValueError("unexpected Standard Library manifest name")
        canonical_relative = "griptape_nodes_library/agents/agent.py"
        if not any(
            isinstance(record, dict)
            and record.get("class_name") == "Agent"
            and str(record.get("file_path") or "").replace("\\", "/")
            == canonical_relative
            for record in manifest.get("nodes", [])
        ):
            raise ValueError("canonical Agent registration is missing")
        agent_file = (root / Path(canonical_relative)).resolve(strict=True)
        agent_file.relative_to(root)
        if not agent_file.is_file():
            raise FileNotFoundError(agent_file)
        return root
    except Exception:
        return None


def _registered_standard_library_root_from_host(*, status: Optional[dict] = None) -> Optional[Path]:
    """Resolve the Standard Library through Griptape's discovery metadata."""
    try:
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes  # type: ignore
    except Exception:
        return None
    try:
        library_info = GriptapeNodes.LibraryManager().get_library_info_by_library_name(
            "Griptape Nodes Library"
        )
        if library_info is None or not getattr(library_info, "library_path", None):
            if status is not None:
                status["rejected"] = True
            return None
        if getattr(library_info, "enabled", True) is False:
            if status is not None:
                status["rejected"] = True
            raise ValueError("host Standard Library registration is disabled")
        lifecycle = getattr(library_info, "lifecycle_state", None)
        lifecycle_name = str(getattr(lifecycle, "name", lifecycle) or "").upper()
        if lifecycle_name == "FAILURE":
            if status is not None:
                status["rejected"] = True
            raise ValueError("host Standard Library registration failed")
        root = _validated_registered_standard_library_root(
            Path(str(library_info.library_path))
        )
        if root is None:
            if status is not None:
                status["rejected"] = True
            raise ValueError("host-reported Standard Library failed validation")
        return root
    except Exception as exc:
        try:
            _standard_agent_import_warning("registered_root", exc)
        except Exception:
            pass
        return None


def _is_canonical_agent_module(module: Any, explicit_root: Optional[Path]) -> bool:
    try:
        module_file = Path(str(getattr(module, "__file__", ""))).resolve(strict=True)
        canonical_tail = tuple(
            part.casefold()
            for part in ("griptape_nodes_library", "agents", "agent.py")
        )
        if tuple(part.casefold() for part in module_file.parts[-3:]) != canonical_tail:
            return False
        if explicit_root is not None:
            expected = (
                explicit_root / "griptape_nodes_library" / "agents" / "agent.py"
            ).resolve(strict=True)
            return module_file == expected
        # The HMB library must never satisfy its own Standard Agent dependency.
        try:
            module_file.relative_to(ROOT)
        except ValueError:
            return True
        return False
    except Exception:
        return False


def find_builtin_agent_class() -> Optional[Type[Any]]:
    """Load the canonical registered or explicitly configured Standard Agent."""
    explicit_requested = bool(
        os.environ.get("HMB_GRIPTAPE_STANDARD_LIBRARY_PATH", "").strip()
    )
    explicit_root = _configured_standard_library_root()
    if explicit_requested and explicit_root is None:
        return None
    failures: list[tuple[str, Exception]] = []
    def report_failures() -> None:
        for stage, error in failures:
            _standard_agent_import_warning(stage, error)
    def is_node_agent_class(candidate: Any) -> bool:
        try:
            if not isinstance(candidate, type) or candidate.__name__ != "Agent":
                return False
            if not (
                hasattr(candidate, "add_parameter")
                or any(
                    hasattr(base, "add_parameter")
                    for base in getattr(candidate, "__mro__", ())
                )
            ):
                return False
            return hasattr(candidate, "process")
        except Exception:
            return False

    def load_from(expected_root: Optional[Path]) -> Optional[Type[Any]]:
        try:
            module = importlib.import_module("griptape_nodes_library.agents.agent")
            candidate = getattr(module, "Agent", None)
            if _is_canonical_agent_module(module, expected_root) and is_node_agent_class(candidate):
                return candidate
        except Exception as error:
            failures.append(("canonical_source", error))
        return None

    def load_from_registry(expected_root: Optional[Path]) -> Optional[Type[Any]]:
        try:
            from griptape_nodes.node_library.library_registry import LibraryRegistry  # type: ignore

            library = LibraryRegistry.get_library("Griptape Nodes Library")
            candidate = library.get_node_class("Agent")
            module = importlib.import_module(str(candidate.__module__))
            if _is_canonical_agent_module(module, expected_root) and is_node_agent_class(candidate):
                return candidate
        except Exception as error:
            failures.append(("registered_class", error))
        return None

    if explicit_root is not None:
        text_path = str(explicit_root)
        if text_path not in sys.path:
            # Explicit configuration is an administrator/user decision. Append it
            # so it cannot shadow already configured host packages at sys.path[0].
            sys.path.append(text_path)
        _append_standard_agent_edit_dependencies(explicit_root)
        importlib.invalidate_caches()
        candidate = load_from(explicit_root)
        if candidate is not None:
            return candidate
        report_failures()
        try:
            print(
                f"{WARN_LOG_PREFIX} The explicitly configured Standard Agent "
                f"could not be loaded from {explicit_root}."
            )
        except Exception:
            pass
        return None

    discovery_status: dict[str, bool] = {}
    registered_root = _registered_standard_library_root_from_host(status=discovery_status)
    if discovery_status.get("rejected"):
        return None
    if registered_root is not None:
        # Registry entries may resolve a lazy Agent on the first call. Its
        # provider dependencies must be visible before that first import.
        _append_standard_agent_edit_dependencies(registered_root)

    # First honor the exact Agent class already registered by the host.
    candidate = load_from_registry(registered_root)
    if candidate is not None:
        return candidate

    # During startup the manager has metadata for all discovered libraries even
    # when the Standard Library loads after HMB.  Trust only that registered
    # root; never infer a sibling or scan the user's home directory.
    if registered_root is not None:
        text_path = str(registered_root)
        if text_path not in sys.path:
            sys.path.append(text_path)
        importlib.invalidate_caches()
        candidate = load_from(registered_root)
        if candidate is not None:
            try:
                print(
                    f"{PATH_LOG_PREFIX} Loaded the registered Standard Agent "
                    f"from {registered_root}"
                )
            except Exception:
                pass
            return candidate

    try:
        report_failures()
        print(
            f"{WARN_LOG_PREFIX} Built-in Griptape Agent node class was not found "
            "at the registered host path. Check the Standard Library or set "
            "HMB_GRIPTAPE_STANDARD_LIBRARY_PATH to its exact package root."
        )
    except Exception:
        pass
    return None
