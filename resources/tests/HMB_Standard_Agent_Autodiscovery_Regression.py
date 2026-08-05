from __future__ import annotations

import json
import os
import sys
import tempfile
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import _hmb_common as common


MANAGED_PREFIX = "griptape_nodes"
STANDARD_PREFIX = "griptape_nodes_library"
saved_modules = {
    name: module
    for name, module in tuple(sys.modules.items())
    if name == MANAGED_PREFIX
    or name.startswith(f"{MANAGED_PREFIX}.")
    or name == STANDARD_PREFIX
    or name.startswith(f"{STANDARD_PREFIX}.")
}
saved_sys_path = list(sys.path)
saved_root = common.ROOT
saved_explicit = os.environ.pop("HMB_GRIPTAPE_STANDARD_LIBRARY_PATH", None)


def clear_test_modules() -> None:
    for name in tuple(sys.modules):
        if (
            name == MANAGED_PREFIX
            or name.startswith(f"{MANAGED_PREFIX}.")
            or name == STANDARD_PREFIX
            or name.startswith(f"{STANDARD_PREFIX}.")
        ):
            sys.modules.pop(name, None)


try:
    with tempfile.TemporaryDirectory(prefix="hmb_standard_agent_manager_") as temporary:
        temp_root = Path(temporary)
        hmb_root = temp_root / "project-a" / "custom-libraries" / "HMB_GP_Production"
        standard_root = temp_root / "download-cache" / "renamed-standard-clone"
        unregistered_sibling = hmb_root.parent / "griptape-nodes-library-standard"
        agent_file = standard_root / "griptape_nodes_library" / "agents" / "agent.py"
        hmb_root.mkdir(parents=True)
        agent_file.parent.mkdir(parents=True)
        unregistered_sibling.mkdir(parents=True)
        (standard_root / "griptape_nodes_library" / "__init__.py").write_text(
            "", encoding="utf-8"
        )
        (agent_file.parent / "__init__.py").write_text("", encoding="utf-8")
        agent_file.write_text(
            "class Agent:\n"
            "    def add_parameter(self, parameter):\n"
            "        return parameter\n"
            "    def process(self):\n"
            "        if False:\n"
            "            yield None\n",
            encoding="utf-8",
        )
        manifest_path = standard_root / "griptape_nodes_library.json"
        manifest = {
            "name": "Griptape Nodes Library",
            "nodes": [
                {
                    "class_name": "Agent",
                    "file_path": "griptape_nodes_library/agents/agent.py",
                }
            ],
        }
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        current_info = types.SimpleNamespace(
            library_path=str(manifest_path),
            enabled=True,
            lifecycle_state=types.SimpleNamespace(name="METADATA_LOADED"),
        )

        class FakeLibraryManager:
            def get_library_info_by_library_name(self, name: str):
                assert name == "Griptape Nodes Library"
                return current_info

        class FakeGriptapeNodes:
            @staticmethod
            def LibraryManager():
                return FakeLibraryManager()

        class FakeLibraryRegistry:
            @staticmethod
            def get_library(_name: str):
                raise KeyError("Standard is discovered but intentionally not loaded yet")

        clear_test_modules()
        for package_name in (
            "griptape_nodes",
            "griptape_nodes.retained_mode",
            "griptape_nodes.node_library",
        ):
            package = types.ModuleType(package_name)
            package.__path__ = []
            sys.modules[package_name] = package
        manager_module = types.ModuleType("griptape_nodes.retained_mode.griptape_nodes")
        manager_module.GriptapeNodes = FakeGriptapeNodes
        sys.modules[manager_module.__name__] = manager_module
        registry_module = types.ModuleType("griptape_nodes.node_library.library_registry")
        registry_module.LibraryRegistry = FakeLibraryRegistry
        sys.modules[registry_module.__name__] = registry_module

        common.ROOT = hmb_root
        resolved = common.find_builtin_agent_class()
        assert resolved is not None and resolved.__name__ == "Agent"
        resolved_file = Path(sys.modules[resolved.__module__].__file__).resolve()
        assert resolved_file == agent_file.resolve()
        assert str(standard_root.resolve()) in sys.path
        assert str(unregistered_sibling.resolve()) not in sys.path
        assert sys.path[0] != str(standard_root.resolve())

        # A valid-looking but unregistered sibling must never be inferred.
        clear_standard = [
            name
            for name in tuple(sys.modules)
            if name == STANDARD_PREFIX or name.startswith(f"{STANDARD_PREFIX}.")
        ]
        for name in clear_standard:
            sys.modules.pop(name, None)
        sys.path[:] = [item for item in sys.path if item != str(standard_root.resolve())]
        current_info = None
        assert common.find_builtin_agent_class() is None

        # Disabled and failed registrations are not eligible even with valid files.
        for enabled, lifecycle_name in ((False, "METADATA_LOADED"), (True, "FAILURE")):
            current_info = types.SimpleNamespace(
                library_path=str(manifest_path),
                enabled=enabled,
                lifecycle_state=types.SimpleNamespace(name=lifecycle_name),
            )
            assert common.find_builtin_agent_class() is None
finally:
    common.ROOT = saved_root
    sys.path[:] = saved_sys_path
    clear_test_modules()
    sys.modules.update(saved_modules)
    if saved_explicit is not None:
        os.environ["HMB_GRIPTAPE_STANDARD_LIBRARY_PATH"] = saved_explicit


print("HMB manager-backed Standard Agent pre-load auto-discovery regression: PASS")
