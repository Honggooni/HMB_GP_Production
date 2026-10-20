"""Actual SDK output replay and browser snapshots project a local original.

No manual restore callback is allowed: is_output=True must work immediately
through the supported display hook, including native serialize/delete/reopen.
Only temporary fixture nodes/media/config are used. No render/network/usersave.
"""
from __future__ import annotations
import asyncio
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import logging
import os
from pathlib import Path
import socket
import sys
import tempfile
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
ATTEMPTS = []

def deny(*args, **kwargs):
    ATTEMPTS.append('unexpected_network_or_generation')
    raise AssertionError('Read-only native preview replay attempted a prohibited operation')

def send(engine, request):
    request.broadcast_result = False
    result = engine.handle_request(request)
    assert result.succeeded(), str(result.result_details)
    return result

def identity(path):
    stat = path.stat()
    return hashlib.sha256(path.read_bytes()).hexdigest(), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns

async def exercise(engine, temporary):
    import HMBSeedanceGeneration as target
    from griptape_nodes.node_library.library_registry import LibraryRegistry, LibrarySchema
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest, GetAllNodeInfoRequest
    from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest, GetNodeElementDetailsRequest, GetParameterValueRequest
    from griptape_nodes.retained_mode.events.flow_events import SerializeFlowToCommandsRequest, DeserializeFlowFromCommandsRequest, DeleteFlowRequest
    schema = LibrarySchema.model_validate_json((ROOT / 'griptape-nodes-library.json').read_text(encoding='utf-8-sig'))
    library = LibraryRegistry.generate_new_library(schema)
    definition = next(row for row in schema.nodes if row.class_name == 'HMBSeedanceGeneration')
    library.register_lazy_node_type(definition.class_name, definition.metadata, lambda: target.HMBSeedanceGeneration)
    engine.event_manager.initialize_queue()
    try:
        ensured = send(engine, EnsureWorkflowAndFlowRequest(flow_name='SyntheticNativePreviewHydration'))
        flow_name = ensured.flow_name
        saved = {}
        paths = []
        for slot in range(1, 6):
            created = send(engine, CreateNodeRequest(node_type='HMBSeedanceGeneration',
                node_name=f'Synthetic Native Preview {slot}', specific_library_name=schema.name, initial_setup=True))
            node = engine.node_manager.get_node_by_name(created.node_name)
            path = temporary / f'slot-{slot}-original.mov'
            path.write_bytes(b'synthetic immutable original movie fixture ' + bytes([slot]))
            paths.append(path)
            original = target.VideoUrlArtifact(value=str(path), name=path.name, meta={'slot': slot})
            originals = identity(path)
            # Native saved outputs bypass the node setter and after-value hook.
            # Exercise both recorded output orders. Never call a restore method.
            keys = ('video_url', 'VIDEO_OUT') if slot % 2 else ('VIDEO_OUT', 'video_url')
            for name in keys:
                send(engine, SetParameterValueRequest(node_name=node.name, parameter_name=name,
                    value=original, initial_setup=True, is_output=True))
            send(engine, SetParameterValueRequest(node_name=node.name, parameter_name='generation_id',
                value=f'job-saved-slot-{slot}', initial_setup=True, is_output=True))
            node.set_parameter_value('resolution', '480p', initial_setup=True)
            native = assert_snapshot(engine, node, original)
            for _ in range(10):
                assert_snapshot(engine, node, original, expected_id=native.id)
            assert identity(path) == originals
            assert node.get_parameter_value('resolution') == '480p'
            saved[node.name] = original.value, native.id, originals, f'job-saved-slot-{slot}'
        serialized = send(engine, SerializeFlowToCommandsRequest(flow_name=flow_name))
        send(engine, DeleteFlowRequest(flow_name=None))
        restored = send(engine, DeserializeFlowFromCommandsRequest(serialized_flow_commands=serialized.serialized_flow_commands))
        flow = engine.flow_manager.get_flow_by_name(restored.flow_name)
        for name, (path, _prior_display_id, originals, task_id) in saved.items():
            node = flow.nodes[name]
            canonical = node.parameter_output_values['VIDEO_OUT']
            assert canonical.value == path
            assert node.parameter_output_values['video_url'].value == path
            assert node.parameter_output_values['generation_id'] == task_id
            native = assert_snapshot(engine, node, canonical)
            for _ in range(10):
                assert_snapshot(engine, node, canonical, expected_id=native.id)
            assert node.get_parameter_value('resolution') == '480p'
            assert identity(Path(path)) == originals
        assert not ATTEMPTS
        print('HMB_NATIVE_PREVIEW_REPLAY_HOST=PASS (5 nodes; both native output replay orders; GetNodeElementDetails/GetAllNodeInfo; native serialize/delete/reopen; 100 repeated snapshots; canonical MOV+Task+480p unchanged; render/network/user-save0)')
    finally:
        LibraryRegistry.unregister_library(schema.name, event_manager=engine.event_manager)

def assert_snapshot(engine, node, canonical, *, expected_id=None):
    from griptape_nodes.retained_mode.events.node_events import GetAllNodeInfoRequest
    from griptape_nodes.retained_mode.events.parameter_events import GetNodeElementDetailsRequest, GetParameterValueRequest
    key = node.get_parameter_by_name('video_url').element_id
    details = send(engine, GetNodeElementDetailsRequest(node_name=node.name))
    native = details.element_details['element_id_to_value'][key]
    assert native is not canonical and native.value.startswith(('http://127.0.0.1:', 'http://localhost:'))
    assert native.value == node._local_original_generation_preview()['url']
    assert native.name == canonical.name and native.meta == canonical.meta
    if expected_id is not None: assert native.id == expected_id
    snapshot = send(engine, GetAllNodeInfoRequest(node_name=node.name))
    assert snapshot.element_id_to_value[key].value == native.value
    assert snapshot.element_id_to_value[key].id == native.id
    raw = send(engine, GetParameterValueRequest(node_name=node.name, parameter_name='video_url'))
    assert raw.value.value == canonical.value
    assert node.parameter_output_values['VIDEO_OUT'] is canonical
    # All unrelated output parameters retain the parent SDK's display rules.
    task = node.parameter_output_values.get('generation_id')
    assert node.get_display_value_for_output('generation_id', task) == task
    return native

def main():
    previous = Path.cwd()
    with tempfile.TemporaryDirectory(prefix='hmb-native-output-replay-sdk-') as temporary:
        base = Path(temporary)
        env = {key: str(base / leaf) for key, leaf in (('XDG_CONFIG_HOME', 'config'),
            ('XDG_DATA_HOME', 'data'), ('XDG_CACHE_HOME', 'cache'), ('XDG_STATE_HOME', 'state'),
            ('LOCALAPPDATA', 'local'), ('APPDATA', 'app'), ('GTN_ENGINE_CONFIG_DIR', 'engine-config'),
            ('GTN_ENGINE_DATA_DIR', 'engine-data'), ('GTN_ENGINE_STATE_DIR', 'engine-state'),
            ('GTN_CONFIG_WORKSPACE_DIRECTORY', 'workspace'))}
        for directory in env.values(): Path(directory).mkdir(parents=True, exist_ok=True)
        with mock.patch.dict(os.environ, env), ExitStack() as guard:
            os.chdir(base)
            try:
                import HMBSeedanceGeneration as target
                import _hmb_shot_routing as routing
                for name in ('schedule_post_registration_reconcile', 'schedule_post_hydration_reconcile'):
                    guard.enter_context(mock.patch.object(routing, name, lambda *a, **k: False))
                guard.enter_context(mock.patch.object(target.HMBSeedanceGeneration, '_restore_generation_recovery_preview', deny))
                guard.enter_context(mock.patch.object(target.HMBSeedanceGeneration, '_process_generation', deny))
                guard.enter_context(mock.patch.object(target._HMBAIBrokerBridge, '_request_json', deny))
                guard.enter_context(mock.patch.object(socket, 'create_connection', deny))
                native_connect = socket.socket.connect
                def guarded_connect(sock, address):
                    caller = sys._getframe(1)
                    if caller.f_code.co_name == '_fallback_socketpair' and Path(caller.f_code.co_filename).name == 'socket.py':
                        assert address[0] in {'127.0.0.1', '::1'}
                        return native_connect(sock, address)
                    return deny(sock, address)
                logging.disable(logging.CRITICAL)
                from griptape_nodes.retained_mode.engine import engine_scope
                with asyncio.Runner() as runner:
                    runner.get_loop()
                    with mock.patch.object(socket.socket, 'connect', guarded_connect), mock.patch.object(socket.socket, 'connect_ex', deny):
                        with engine_scope() as engine:
                            runner.run(exercise(engine, base))
            finally:
                logging.shutdown()
                os.chdir(previous)

if __name__ == '__main__': main()
