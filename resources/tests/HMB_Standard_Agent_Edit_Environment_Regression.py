"""Validated Standard edit dependencies precede lazy import, without shadowing."""
import contextlib
import importlib
import io
import json
import os
from pathlib import Path
import sys
import sysconfig
import tempfile
import types
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import _hmb_common as common

prefixes = ("griptape_nodes", "griptape_nodes_library", "hmb_native_provider_fixture")
saved_modules = {name: value for name, value in sys.modules.items() if any(name == p or name.startswith(p + ".") for p in prefixes)}
saved_path = list(sys.path)
saved_explicit = os.environ.pop("HMB_GRIPTAPE_STANDARD_LIBRARY_PATH", None)
checks = []
try:
    for name in list(saved_modules):
        sys.modules.pop(name, None)
    with tempfile.TemporaryDirectory(prefix="hmb-standard-edit-env-") as directory:
        root = Path(directory) / "registered-custom-name"
        package = root / "griptape_nodes_library/agents"
        package.mkdir(parents=True)
        (root / "griptape_nodes_library/__init__.py").write_text("")
        (package / "__init__.py").write_text("")
        agent_file = package / "agent.py"
        agent_file.write_text("from hmb_native_provider_fixture import MARKER\nclass Agent:\n def add_parameter(self,*args): pass\n def process(self): pass\n")
        manifest = root / "griptape_nodes_library.json"
        manifest.write_text(json.dumps({"name": "Griptape Nodes Library", "nodes": [{"class_name": "Agent", "file_path": "griptape_nodes_library/agents/agent.py"}]}))
        venv = root / ".venv"
        venv.mkdir()
        config = venv / "pyvenv.cfg"
        config.write_text("version = 3.12.13\n")
        site = Path(sysconfig.get_path("purelib", vars={"base": str(venv), "platbase": str(venv)}))
        site.mkdir(parents=True)
        (site / "hmb_native_provider_fixture.py").write_text("MARKER = 'native dependency'\n")
        sentinel = Path(directory) / "PTH_WAS_EXECUTED"
        (site / "never-execute.pth").write_text("import pathlib; pathlib.Path(" + repr(str(sentinel)) + ").touch()\n")
        info = types.SimpleNamespace(library_path=str(manifest), enabled=True, lifecycle_state=types.SimpleNamespace(name="METADATA_LOADED"))
        manager = types.SimpleNamespace(get_library_info_by_library_name=lambda name: info)
        host = types.SimpleNamespace(LibraryManager=lambda: manager)
        called = []
        def lazy_class(name):
            assert str(site.resolve()) in sys.path, "Provider path must precede the first lazy import"
            called.append(name)
            return importlib.import_module("griptape_nodes_library.agents.agent").Agent
        registry = types.SimpleNamespace(get_library=lambda name: types.SimpleNamespace(get_node_class=lazy_class))
        for name in ("griptape_nodes", "griptape_nodes.retained_mode", "griptape_nodes.node_library"):
            module = types.ModuleType(name); module.__path__ = []; sys.modules[name] = module
        module = types.ModuleType("griptape_nodes.retained_mode.griptape_nodes"); module.GriptapeNodes = host; sys.modules[module.__name__] = module
        module = types.ModuleType("griptape_nodes.node_library.library_registry"); module.LibraryRegistry = registry; sys.modules[module.__name__] = module
        sys.path.append(str(root))  # Official loader has added the library source root.
        old_path = list(sys.path)
        candidate = common.find_builtin_agent_class()
        assert candidate.__name__ == "Agent" and called == ["Agent"]
        assert sys.path[:len(old_path)] == old_path and sys.path[-1] == str(site.resolve())
        assert not sentinel.exists()
        checks.append("first lazy import sees only validated append-only dependencies; no .pth execution")
        for rejected in (None, types.SimpleNamespace(library_path=str(manifest), enabled=False),
                         types.SimpleNamespace(library_path=str(manifest), enabled=True, lifecycle_state=types.SimpleNamespace(name="FAILURE"))):
            info, previous = rejected, info
            assert common.find_builtin_agent_class() is None
            info = previous
        checks.append("missing disabled failed host registration rejects cached canonical class")
        previous = info
        info = types.SimpleNamespace(library_path=str(Path(directory) / "missing.json"), enabled=True)
        before = list(sys.path)
        assert common.find_builtin_agent_class() is None and sys.path == before
        info = previous
        checks.append("invalid manifest cannot add dependency paths")
        config.unlink()
        registry.get_library = lambda name: types.SimpleNamespace(get_node_class=lambda name: candidate)
        assert common.find_builtin_agent_class() is candidate
        checks.append("missing edit environment remains optional for an available native Agent")
        config.write_text("version = 3.12.13\n")
        os.environ["HMB_GRIPTAPE_STANDARD_LIBRARY_PATH"] = str(root)
        registry.get_library = lambda name: (_ for _ in ()).throw(AssertionError("Explicit override must not use registry"))
        assert common.find_builtin_agent_class() is candidate
        checks.append("explicit override semantics preserved")
        # Display only a validated missing-module identifier, never exception text.
        common._STANDARD_AGENT_IMPORT_WARNINGS.clear()
        stream = io.StringIO()
        error = ModuleNotFoundError("secret-token https://private.invalid/?key=SECRET", name="missing.provider")
        with contextlib.redirect_stdout(stream):
            common._standard_agent_import_warning("canonical_source", error)
            common._standard_agent_import_warning("canonical_source", error)
        output = stream.getvalue()
        assert output.count("missing_module=missing.provider") == 1
        assert "SECRET" not in output and "private.invalid" not in output and "secret-token" not in output
        checks.append("sanitized missing-module diagnostic bounded to one identical failure")
finally:
    sys.path[:] = saved_path
    for name in list(sys.modules):
        if any(name == p or name.startswith(p + ".") for p in prefixes):
            sys.modules.pop(name, None)
    sys.modules.update(saved_modules)
    if saved_explicit is None:
        os.environ.pop("HMB_GRIPTAPE_STANDARD_LIBRARY_PATH", None)
    else:
        os.environ["HMB_GRIPTAPE_STANDARD_LIBRARY_PATH"] = saved_explicit
print("HMB_STANDARD_AGENT_EDIT_ENVIRONMENT=PASS", len(checks), checks)
