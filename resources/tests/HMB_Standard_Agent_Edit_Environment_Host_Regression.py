"""Cold bundled Agent construction and five-shot restore with Standard unavailable."""
import os
from pathlib import Path
import runpy
import sys
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
LIBRARIES = Path.home() / "Documents/GriptapeNodes/libraries"
STANDARD_SITE = (LIBRARIES / "griptape-nodes-library-standard/.venv/Lib/site-packages").resolve()
assert str(STANDARD_SITE) not in sys.path, "This test requires a cold edit environment"
sys.path[:0] = [str(ROOT), str(LIBRARIES / "HMB_GP_Production/.venv/Lib/site-packages")]

from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

with mock.patch.dict(os.environ, {"HMB_GRIPTAPE_STANDARD_LIBRARY_PATH": str(ROOT / "missing-standard")}), \
     mock.patch.object(GriptapeNodes, "LibraryManager", side_effect=AssertionError("External Standard lookup")) as lookup:
    import HMBAgentLibrary as agents
    native = agents._BuiltinAgent
    assert native is not None and native in agents.HMBAgentLibrary.__mro__
    assert Path(sys.modules[native.__module__].__file__).resolve() == ROOT / "_hmb_native_agent/agents/agent.py"
    assert str(STANDARD_SITE) not in sys.path
    lookup.assert_not_called()

runpy.run_path(str(ROOT / "resources/tests/HMB_Agent_Shot_Store_Hydration_Host_Regression.py"), run_name="__main__")
print("HMB_STANDARD_AGENT_EDIT_ENVIRONMENT_HOST=PASS (bundled Agent, unavailable external Standard, five-shot restore)")
