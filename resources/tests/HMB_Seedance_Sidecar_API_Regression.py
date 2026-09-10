"""No-network adapter coverage for old and current Griptape sidecar APIs."""

import importlib.util
from pathlib import Path
import sys
from types import ModuleType
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hmb_seedance_clean_ci_stubs import install_clean_ci_griptape_stubs

install_clean_ci_griptape_stubs()
spec = importlib.util.spec_from_file_location("seedance_sidecar_api", ROOT / "HMBSeedanceGeneration.py")
target = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = target
spec.loader.exec_module(target)

path = Path("generated-video.mp4")
metadata = object()
engine = object()
engine_module = ModuleType("griptape_nodes.retained_mode.engine")
engine_module.current_engine = Mock(return_value=engine)
calls = []


def legacy(file_path, value):
    calls.append((file_path, value))


def current(file_path, value, engine):
    calls.append((file_path, value, engine))


def keyword_only(file_path, value, *, engine):
    calls.append((file_path, value, engine))


def positional_only(file_path, value, engine, /):
    calls.append((file_path, value, engine))


with patch.dict(sys.modules, {engine_module.__name__: engine_module}):
    for writer in (legacy, current, keyword_only, positional_only):
        calls.clear()
        engine_module.current_engine.reset_mock()
        with patch.object(target, "write_sidecar", writer):
            target._write_generation_sidecar(path, metadata)
        assert calls == [(path, metadata)] if writer is legacy else calls == [(path, metadata, engine)]
        assert engine_module.current_engine.call_count == (0 if writer is legacy else 1)

    # An exception from inside a writer is not a reason to call it a second time.
    calls.clear()

    def partial_failure(file_path, value, engine):
        calls.append((file_path, value, engine))
        raise TypeError("simulated failure after a write")

    with patch.object(target, "write_sidecar", partial_failure):
        try:
            target._write_generation_sidecar(path, metadata)
        except TypeError:
            pass
        else:
            raise AssertionError("The sidecar failure was swallowed")
    assert calls == [(path, metadata, engine)]

print("HMB Seedance sidecar API: PASS (legacy/current/keyword/positional engine, correct context, exactly one write, no network)")
