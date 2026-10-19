"""Cold installed SDK + HMB edit path; loader must discover Standard deps itself."""
import importlib
import json
import os
from pathlib import Path
import runpy
import sys
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
STANDARD = Path.home() / "Documents/GriptapeNodes/libraries/griptape-nodes-library-standard"
SITE = STANDARD / ".venv/Lib/site-packages"
assert str(SITE) not in sys.path, "Cold regression must not externally append Standard dependencies"
os.environ.pop("HMB_GRIPTAPE_STANDARD_LIBRARY_PATH", None)
sys.path.insert(0, str(ROOT))
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
sys.path.insert(0, str(Path.home() / "Documents/GriptapeNodes/libraries/HMB_GP_Production/.venv/Lib/site-packages"))
before = list(sys.path)
info = SimpleNamespace(library_path=str(STANDARD / "griptape_nodes_library.json"), enabled=True,
    lifecycle_state=SimpleNamespace(name="METADATA_LOADED"))
manager = SimpleNamespace(get_library_info_by_library_name=lambda name: info if name == "Griptape Nodes Library" else None)
with mock.patch.object(GriptapeNodes, "LibraryManager", return_value=manager):
    import HMBAgentLibrary as agents
    assert agents._BuiltinAgent is not None
    native = agents._BuiltinAgent
    assert Path(sys.modules[native.__module__].__file__).resolve() == (STANDARD / "griptape_nodes_library/agents/agent.py").resolve()
    assert native in agents.HMBAgentLibrary.__mro__
    assert sys.path.index(str(SITE.resolve())) >= len(before)
# Reuse the actual SDK native constructor + official five-slot property restore,
# first callback, intentional selected-Shot edit, and normal recovery assertions.
# No wrapper has supplied Standard's site-packages: the product did that above.
runpy.run_path(str(ROOT / "resources/tests/HMB_Agent_Shot_Store_Hydration_Host_Regression.py"), run_name="__main__")
print("HMB_STANDARD_AGENT_EDIT_ENVIRONMENT_HOST=PASS (cold native discovery, actual constructor and five-slot first-callback preservation)")
