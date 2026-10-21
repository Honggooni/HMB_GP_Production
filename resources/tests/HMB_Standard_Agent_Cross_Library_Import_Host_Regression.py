"""Manual, fresh SDK process: cross-library edit environments and native Agent.

Run each case in a separate SDK-offline-guard process.  The normal expectation
is a usable native Agent.  ``--expect unavailable`` is an explicit diagnostic
counterexample mode for the known older Advanced Media Anthropic environment;
it verifies the precise missing-symbol cause rather than accepting any failure.
No Engine, node, workflow, provider, or socket is constructed by this fixture.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
from types import SimpleNamespace
from unittest import mock


parser = argparse.ArgumentParser()
parser.add_argument("--case", choices=("canonical-control", "advanced-front", "cached-advanced"), default="advanced-front")
parser.add_argument("--expect", choices=("native", "unavailable"), default="native")
parser.add_argument("--advanced-site", type=Path,
                    help="Explicit read-only clone site-packages for pre-install compatibility proof")
parser.add_argument("--product-root", type=Path,
                    help="Explicit source/package root; defaults to the installed HMB library")
parser.add_argument("--report", type=Path)
args = parser.parse_args()
assert os.environ.get("HMB_SDK_GUARD_RECEIPT"), "Run through the SDK offline guard"
assert os.environ.get("HMB_SDK_ISOLATED_ROOT"), "An isolated SDK config root is required"
os.environ.pop("HMB_GRIPTAPE_STANDARD_LIBRARY_PATH", None)

libraries = Path.home() / "Documents/GriptapeNodes/libraries"
installed = libraries / "HMB_GP_Production"
target = (args.product_root or installed).resolve(strict=True)
assert (target / "HMBAgentLibrary.py").is_file() and (target / "_hmb_common.py").is_file()
standard = libraries / "griptape-nodes-library-standard"
advanced = libraries / "griptape-nodes-library-advanced-media"
standard_site = (standard / ".venv/Lib/site-packages").resolve(strict=True)
advanced_site = (args.advanced_site or advanced / ".venv/Lib/site-packages").resolve(strict=True)
assert advanced_site.is_dir() and (advanced_site / "anthropic/__init__.py").is_file(), \
    "Advanced dependency fixture requires an existing Anthropic package directory"
assert any(advanced_site.glob("anthropic-*.dist-info/METADATA")), "Anthropic distribution metadata is required"
# A pre-install source/package proof changes the code origin only. The edit
# environment remains the real installed HMB environment, as in the default
# installed case; a source checkout's developer venv is not an editor venv.
hmb_site = (installed / ".venv/Lib/site-packages").resolve(strict=True)
assert str(standard_site) not in sys.path, "Fixture must not externally inject Standard's dependencies"
assert "anthropic" not in sys.modules, "Fixture requires a fresh dependency cache"

from griptape_nodes.retained_mode.engine import Engine
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.retained_mode.managers.library.module_loading import LibraryModuleLoading
from griptape_nodes.node_library.library_registry import LibraryRegistry

assert "anthropic" not in sys.modules, "SDK preparation unexpectedly loaded Anthropic"
engine_attempts = []


def no_engine(*_args, **_kwargs):
    engine_attempts.append(True)
    raise AssertionError("Import-order regression must not construct an Engine")


def chain(error):
    result = []
    seen = set()
    while error is not None and id(error) not in seen and len(result) < 12:
        seen.add(id(error))
        symbol = re.search(r"cannot import name ['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]", str(error))
        result.append({"type": type(error).__name__,
                       "module_name": getattr(error, "name", None),
                       "module_path": getattr(error, "path", None),
                       "missing_symbol": symbol.group(1) if symbol else None})
        error = error.__cause__ or (None if error.__suppress_context__ else error.__context__)
    return result


if args.case != "canonical-control":
    # This is the SDK environment.py edit-time prepend contract, deliberately
    # placed before the bundled site-packages and Standard's later append.
    sys.path.insert(0, str(advanced_site))
    if args.case == "cached-advanced":
        importlib.import_module("anthropic")
sys.path.insert(0, str(hmb_site))
# SDK environment.py also publishes the library package root independently of
# its edit-time dependency environment; the dynamic Agent imports its siblings.
sys.path.append(str(standard))
path_before = list(sys.path)

info = SimpleNamespace(library_path=str(standard / "griptape_nodes_library.json"), enabled=True,
                       lifecycle_state=SimpleNamespace(name="METADATA_LOADED"))
host_manager = SimpleNamespace(get_library_info_by_library_name=lambda name:
                               info if name == "Griptape Nodes Library" else None)
# Actual SDK dynamic loader, with its private alias maps isolated in this child.
# EngineScoped permits a supplied manager owner; the loader never needs an
# actual engine while importing a node class or creating its stable namespace.
loader = LibraryModuleLoading(SimpleNamespace())
registry_errors = []
native_classes = []


def get_native_class(name):
    assert name == "Agent"
    try:
        module = loader.load_module_from_file(standard / "griptape_nodes_library/agents/agent.py", "Griptape Nodes Library")
        native_classes.append(module.Agent)
        return module.Agent
    except ImportError as error:
        registry_errors.append(chain(error))
        raise


standard_library = SimpleNamespace(get_node_class=get_native_class)


def get_library(name):
    assert name == "Griptape Nodes Library"
    return standard_library


spec = importlib.util.spec_from_file_location("_hmb_installed_cross_library_order_fixture", target / "HMBAgentLibrary.py")
assert spec and spec.loader
agents = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = agents
with mock.patch.object(Engine, "__init__", no_engine), \
     mock.patch.object(GriptapeNodes, "LibraryManager", return_value=host_manager), \
     mock.patch.object(LibraryRegistry, "get_library", side_effect=get_library):
    spec.loader.exec_module(agents)

assert not engine_attempts
assert sys.path.index(str(standard_site)) >= len(path_before), "Product must append Standard dependencies"
assert Path(agents._hmb.__file__).resolve() == (target / "_hmb_common.py").resolve()
native = agents._BuiltinAgent
if args.expect == "native":
    assert native is not None, json.dumps({"case": args.case, "registry_error_chain": registry_errors}, ensure_ascii=True)
    assert native_classes and native is native_classes[-1]
    assert agents._BaseAgent is native and native in agents.HMBAgentLibrary.__mro__
    assert Path(sys.modules[native.__module__].__file__).resolve() == (standard / "griptape_nodes_library/agents/agent.py").resolve()
else:
    assert args.case != "canonical-control", "The control must remain native"
    assert native is None and agents._BaseAgent is agents.DataNode
    assert registry_errors, "Unavailable result must include the actual SDK-loader exception"
    assert any(row["missing_symbol"] in {
        "BetaCitationsConfigParamParam", "BetaInputTransformation", "BetaThinkingBlockBindingParam"
    } for failure in registry_errors for row in failure), json.dumps(registry_errors, ensure_ascii=True)

anthropic = sys.modules.get("anthropic")
record = {"schema": "hmb-standard-agent-cross-library-import-v1", "passed": True,
          "case": args.case, "expected": args.expect, "native_agent_available": native is not None,
          "product_root": str(target), "product_root_explicit": args.product_root is not None,
          "edit_environment_site": str(hmb_site),
          "actual_sdk_module_loader_used": True, "standard_dependencies_externally_injected": False,
          "product_appended_standard_site": True,
          "advanced_site": str(advanced_site), "advanced_site_explicit_clone": args.advanced_site is not None,
          "anthropic_module_path": str(getattr(anthropic, "__file__", "")),
          "anthropic_module_version": getattr(anthropic, "__version__", None),
          "registry_error_chain": registry_errors,
          "installed_common_sha256": hashlib.sha256((target / "_hmb_common.py").read_bytes()).hexdigest(),
          "installed_agent_sha256": hashlib.sha256((target / "HMBAgentLibrary.py").read_bytes()).hexdigest(),
          "engine_construction_attempts": len(engine_attempts), "node_construction": 0,
          "provider_calls": 0, "paid_calls": 0, "live_graph_changes": 0,
          "installed_file_writes": 0}
if args.report:
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(record, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
print("HMB_STANDARD_AGENT_CROSS_LIBRARY_IMPORT_HOST=PASS "
      f"case={args.case} expected={args.expect} native={native is not None} "
      f"anthropic={record['anthropic_module_version']} engine=0 node=0 paid=0")
