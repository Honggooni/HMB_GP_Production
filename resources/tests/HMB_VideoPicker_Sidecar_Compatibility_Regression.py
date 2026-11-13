"""Metadata adapters preserve workflow ownership without retrying failed writes."""
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import HMBVideoPickerLibrary as picker

owner_engine = object()
ambient_engine = object()
workflow = SimpleNamespace(engine=owner_engine)
fake_engine = ModuleType('griptape_nodes.retained_mode.engine')
fake_engine.current_engine = lambda: ambient_engine

with patch.dict(sys.modules, {'griptape_nodes.retained_mode.engine': fake_engine}):
    def legacy(path):
        return path

    def engine_only(path, engine, /):
        return path, engine

    def current(path, metadata, engine, workflow):
        return path, metadata, engine, workflow

    assert picker._call_picker_sidecar_api(legacy, 'file', workflow=workflow) == 'file'
    assert picker._call_picker_sidecar_api(engine_only, 'file', workflow=workflow) == ('file', owner_engine)
    assert picker._call_picker_sidecar_api(engine_only, 'file') == ('file', ambient_engine)
    assert picker._call_picker_sidecar_api(current, 'file', {'key': 'value'}, workflow=workflow) == (
        'file', {'key': 'value'}, owner_engine, workflow)

    calls = []
    def failed_write(path, engine, workflow):
        calls.append(path)
        raise TypeError('write failure after a partial side effect')

    try:
        picker._call_picker_sidecar_api(failed_write, 'file', workflow=workflow)
    except TypeError as error:
        assert 'partial side effect' in str(error)
    else:
        raise AssertionError('A failed metadata write must propagate to rollback')
    assert calls == ['file'], 'Never retry a possibly completed metadata write'

print('Sidecar compatibility: PASS (legacy/current signatures, owner engine, one failed invocation)')
