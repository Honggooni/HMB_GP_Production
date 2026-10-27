"""Real SDK Save-generated property replay, with no deserialize repair hook.

All work is synthetic and confined to a temporary engine/workspace. Neither
the desktop engine nor model/provider/render/upload boundaries are used.
"""
from __future__ import annotations
import ast
import asyncio
from contextlib import ExitStack
from copy import deepcopy
import importlib
import json
import logging
import os
from pathlib import Path
import socket
import sys
import tempfile
from unittest import mock
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'resources/tests')]
sys.dont_write_bytecode = True
os.environ.setdefault('HMB_GRIPTAPE_STANDARD_LIBRARY_PATH', str(Path.home() / 'Documents/GriptapeNodes/libraries/griptape-nodes-library-standard'))
import HMB_Library_Lifecycle_Order_Host_Regression as base

ATTEMPTS = []
def deny(*a, **k):
    ATTEMPTS.append(True)
    raise AssertionError('Generated restore fixture cannot execute or use external transport')


def hooks(engine, modules, guard):
    import _hmb_library_bootstrap as bootstrap
    guard.enter_context(mock.patch.object(bootstrap._Registration, 'start_web_worker', lambda *a, **k:None))
    guard.enter_context(mock.patch.object(modules[base.KINDS[0]].HMBImageAssetLibrary, '_schedule_catalog_scan', lambda *a, **k:False))
    for kind, module in modules.items():
        guard.enter_context(mock.patch.object(getattr(module, kind), 'process', deny))
    library, schema = base.register(engine, modules)
    owner = bootstrap.HMBProductionLibrary.__new__(bootstrap.HMBProductionLibrary)
    owner._registrations = set()
    owner.before_library_nodes_loaded(schema, library)
    engine.event_manager.initialize_queue()
    return library, schema, owner


async def save_healthy(engine, modules, folder):
    from griptape_nodes.node_library.library_registry import LibraryRegistry
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
    from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
    from griptape_nodes.retained_mode.events.workflow_events import SaveWorkflowRequest
    with ExitStack() as guard:
        library, schema, owner = hooks(engine, modules, guard)
        base.send(engine, EnsureWorkflowAndFlowRequest(flow_name='OfflineGeneratedRestore'))
        source_state = base.create_project(modules[base.KINDS[0]], folder / 'media')
        nodes = {}
        for kind in base.KINDS:
            result = base.send(engine, CreateNodeRequest(node_type=kind, specific_library_name=schema.name,
                node_name='Offline ' + kind, create_error_proxy_on_failure=False))
            node = engine.node_manager.get_node_by_name(result.node_name)
            nodes[kind] = node
            if kind == base.KINDS[0]:
                node._hmb_initial_catalog_scan_pending = False
                node._resolution_cache_for_state(deepcopy(source_state))
                node._cache_shot_routing_snapshot(deepcopy(source_state), force=True)
                node._publish_state(deepcopy(source_state))
            await asyncio.sleep(.03)
        source, picker, _, agent, finish = (nodes[k] for k in base.KINDS[:5])
        await base.settle(lambda: len(getattr(agent, '_hmb_shot_catalog_snapshot', {}).get('shots', [])) == 5
            and len(getattr(picker, '_hmb_shot_catalog_snapshot', {}).get('shots', [])) == 5)
        for number in (1, 2, 3, 4, 5, 2):
            row_name = 'HMB_AGENT_SHOT_ROW_' + str(number)
            row = deepcopy(agent.get_parameter_value(row_name))
            row['action'] = dict(kind='select', request_id=uuid4().hex, expanded=True)
            base.send(engine, SetParameterValueRequest(node_name=agent.name, parameter_name=row_name, value=row))
            base.send(engine, SetParameterValueRequest(node_name=agent.name, parameter_name='additional_context',
                value=f'Saved exact Shot {number}: OFF 0 {{literal}}'))
            key = agent._hmb_active_slot_key
            agent._hmb_shot_results[key] = dict(status='succeeded', text=f'Synthetic retained output {number}', run_id=f'saved-{number}')
        agent._hmb_persist_shot_store()
        expected = dict(agent_store=deepcopy(agent.get_parameter_value('HMB_AGENT_SHOT_STATES')),
            finish_documents=deepcopy(finish._hmb_finish_documents),
            picker_memberships=deepcopy(picker._picker_state()['shot_selections']),
            catalog=source._hmb_shot_routing_catalog())
        result = base.send(engine, SaveWorkflowRequest(file_name=str(folder / 'healthy-generated.py'), display_name='Offline healthy generated restore'))
        saved = Path(result.file_path)
        assert saved.is_file()
        owner.before_library_unregistered(schema, library)
        LibraryRegistry.unregister_library(schema.name, event_manager=engine.event_manager)
        return saved, expected


async def restore_generated(engine, modules, saved, expected, *, legacy_cursor=False):
    import _hmb_shot_routing as routing
    import _hmb_workflow_migration as migration
    from griptape_nodes.node_library.library_registry import LibraryRegistry
    from griptape_nodes.retained_mode.managers.workflow.loading import LoadProblemFrame
    with ExitStack() as guard:
        library, schema, owner = hooks(engine, modules, guard)
        # The generated property replay itself must restore Finish readiness.
        guard.enter_context(mock.patch.object(modules['HMBFinishLookLibrary'].HMBFinishLookLibrary, 'after_deserialize', deny))
        tree = ast.parse(saved.read_text(encoding='utf-8'))
        fn = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef))
        fn.body = [n for n in fn.body if 'RegisterLibraryFromFileRequest' not in ast.unparse(n)]
        if legacy_cursor:
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'SetParameterValueRequest':
                    kwargs = {k.arg:k for k in node.keywords}
                    if isinstance(kwargs.get('parameter_name').value, ast.Constant) and kwargs['parameter_name'].value.value == 'HMB_IMAGE_ASSET_STATE':
                        kwargs['value'].value = ast.Call(func=ast.Name(id='legacy_source_value', ctx=ast.Load()), args=[kwargs['value'].value], keywords=[])
        def legacy_source_value(value):
            state = json.loads(value) if isinstance(value, str) else deepcopy(value)
            state['shot_routing']['generation'] = max(1, expected['catalog']['generation'] - 1)
            return json.dumps(state, ensure_ascii=False)
        namespace = dict(__name__='offline_generated_restore', __file__=str(saved), legacy_source_value=legacy_source_value)
        exec(compile(ast.fix_missing_locations(tree), str(saved), 'exec'), namespace)
        with LoadProblemFrame(): await namespace['build_workflow']()
        migration.schedule_loaded_flow_migrations(engine)
        flow = engine.flow_manager.get_flow_by_name('OfflineGeneratedRestore')
        source = engine.node_manager.get_node_by_name('Offline HMBImageAssetLibrary')
        picker = engine.node_manager.get_node_by_name('Offline HMBVideoPickerLibrary')
        agent = engine.node_manager.get_node_by_name('Offline HMBAgentLibrary')
        finish = engine.node_manager.get_node_by_name('Offline HMBFinishLookLibrary')
        await base.settle(lambda: bool(getattr(agent, '_hmb_shot_catalog_snapshot', {}).get('shots'))
            and bool(getattr(picker, '_hmb_shot_catalog_snapshot', None)), seconds=3)
        outcome = routing.reconcile_shot_routing(source)
        assert outcome['code'] == 'ready', outcome
        assert not migration.flow_migration_pending(engine, flow.name)
        catalog = source._hmb_shot_routing_catalog()
        if legacy_cursor:
            assert catalog['generation'] > expected['catalog']['generation']
        else:
            assert catalog['generation'] == expected['catalog']['generation']
        assert catalog['shots'] == expected['catalog']['shots']
        assert picker._hmb_shot_catalog_snapshot == catalog
        output = picker.parameter_output_values['SHOT_PICKER_OUT']
        assert output['generation'] > 0 and output['metadata_sha256']
        assert picker._picker_state()['shot_selections'] == expected['picker_memberships']
        row2 = agent.get_parameter_value('HMB_AGENT_SHOT_ROW_2')
        assert row2['shot']['number'] == 2 and row2['selected'] and not row2.get('routing_pending'), row2
        assert agent.get_parameter_value('HMB_AGENT_SHOT_STATES') == expected['agent_store']
        assert finish._hmb_finish_documents == expected['finish_documents']
        # Repeated unchanged routing does not change the repaired generation.
        for _ in range(4): assert routing.reconcile_shot_routing(source)['code'] == 'ready'
        assert source._hmb_shot_routing_catalog()['generation'] == catalog['generation']
        for number in (1, 2, 3, 4, 5, 2):
            value = deepcopy(agent.get_parameter_value('HMB_AGENT_SHOT_ROW_' + str(number)))
            value['action'] = dict(kind='select', request_id=uuid4().hex, expanded=True)
            agent.set_parameter_value('HMB_AGENT_SHOT_ROW_' + str(number), value)
            assert agent.get_parameter_value('additional_context') == f'Saved exact Shot {number}: OFF 0 {{literal}}'
        owner.before_library_unregistered(schema, library)
        LibraryRegistry.unregister_library(schema.name, event_manager=engine.event_manager)
        print('GENERATED_RESTORE_CASE=PASS ' + ('legacy-cursor' if legacy_cursor else 'healthy'), flush=True)


def main():
    from griptape_nodes.retained_mode.engine import engine_scope
    previous = Path.cwd()
    with tempfile.TemporaryDirectory(prefix='hmb-generated-restore-') as temp:
        folder = Path(temp)
        env = {key:str(folder/key) for key in ('XDG_CONFIG_HOME','XDG_DATA_HOME','XDG_STATE_HOME','XDG_CACHE_HOME','LOCALAPPDATA','APPDATA','GTN_ENGINE_CONFIG_DIR','GTN_ENGINE_DATA_DIR','GTN_ENGINE_STATE_DIR','GTN_CONFIG_WORKSPACE_DIRECTORY','HMB_IMAGE_PROJECTS_ROOT')}
        for value in env.values(): Path(value).mkdir(parents=True, exist_ok=True)
        with mock.patch.dict(os.environ, env), mock.patch.object(socket, 'create_connection', deny):
            os.chdir(folder)
            logging.disable(logging.CRITICAL)
            try:
                modules = {kind:importlib.import_module(kind) for kind in base.KINDS}
                with engine_scope() as engine:
                    with asyncio.Runner() as runner: saved, expected = runner.run(save_healthy(engine, modules, folder))
                for legacy in (False, True):
                    with engine_scope() as engine:
                        with asyncio.Runner() as runner: runner.run(restore_generated(engine, modules, saved, expected, legacy_cursor=legacy))
                assert not ATTEMPTS
                print('HMB_SHOT_ROUTING_GENERATED_RESTORE_HOST=PASS (SDK Save/property replay; healthy and old cursor; five slots/results; Only-safe authority; external/model/render calls 0)')
            finally:
                os.chdir(previous)
                logging.shutdown()


if __name__ == '__main__': main()
