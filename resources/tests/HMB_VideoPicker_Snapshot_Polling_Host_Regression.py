"""Real retained SDK: pending reads must not cancel media preparation.

Controlled 50 ms local-file I/O, current-state replacement and real DeleteNode
exercise the publication token without a renderer, provider or user workflow.
"""
from __future__ import annotations

import asyncio
import copy
import json
import logging
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
from unittest import mock

ROOT = Path(os.environ.get('HMB_PICKER_TEST_ROOT', str(Path(__file__).resolve().parents[2])))
sys.path.insert(0, str(ROOT))


async def scenario(engine, folder):
    import HMBVideoPickerLibrary as picker
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    from griptape_nodes.retained_mode.events.node_events import DeleteNodeRequest

    engine.event_manager.initialize_queue()
    flow = None
    owner_thread = threading.get_ident()
    files = [folder / f'controlled-{number}.mp4' for number in (1, 2)]
    for path in files:
        path.write_bytes(b'isolated readable media fixture')
    created = []

    async def node():
        nonlocal flow
        result = engine.handle_request(EnsureWorkflowAndFlowRequest(flow_name=f'PickerSnapshotPolling{len(created) + 1}'))
        assert result.succeeded(), str(result.result_details)
        flow = engine.flow_manager.get_flow_by_name(result.flow_name)
        instance = picker.HMBVideoPickerLibrary(name=f'PollingPicker{len(created) + 1}')
        flow.add_node(instance)
        engine.object_manager.add_object_by_name(instance.name, instance)
        engine.node_manager._name_to_parent_flow_name[instance.name] = flow.name
        created.append(instance)
        await asyncio.sleep(.08)
        state = picker._append_video_asset(instance._picker_state(), {
            'video_uid': f'fixture-{len(created)}', 'video_path': str(files[0]),
        }, defer_thumbnail=True)
        instance._write_state(state)
        return instance

    async def wait_until(predicate, message, seconds=3):
        end = asyncio.get_running_loop().time() + seconds
        while not predicate() and asyncio.get_running_loop().time() < end:
            await asyncio.sleep(.005)
        assert predicate(), message

    async def delete(instance):
        result = await engine.ahandle_request(DeleteNodeRequest(node_name=instance.name, broadcast_result=False))
        assert result.succeeded(), str(result.result_details)
        assert instance._hmb_node_deleted and instance.name not in flow.nodes

    def fresh_revision(instance, label):
        # Registration callbacks can finish a fast local-file preparation before
        # this test installs its controlled I/O. A genuine authored row change
        # provides a new media identity without touching the readiness cache.
        state = instance._picker_state()
        state['videos'][0]['label'] = label
        instance._write_state(state)

    async def poll(instance, seconds=1.5):
        tokens = []
        end = asyncio.get_running_loop().time() + seconds
        while asyncio.get_running_loop().time() < end:
            try:
                snapshot = instance._hmb_shot_routing_snapshot()
            except ValueError as error:
                assert getattr(error, 'hmb_picker_media_preparing', False) is True, error
                tokens.append(instance._hmb_video_removal_sync_token)
                await asyncio.sleep(.01)
            else:
                return snapshot, tokens
        return None, tokens

    original_prepare = picker.HMBVideoPickerLibrary._prepare_execution_media
    records = []
    try:
        current = await node()
        probes = []

        def slow_prepare(state):
            probes.append(threading.get_ident())
            time.sleep(.05)
            return original_prepare(state)

        with mock.patch.object(picker.HMBVideoPickerLibrary, '_prepare_execution_media', side_effect=slow_prepare):
            try:
                fresh_revision(current, 'Steady pending read fixture')
                snapshot, tokens = await poll(current)
            finally:
                await wait_until(lambda: not getattr(current, '_hmb_video_removal_sync_running', False), 'Polling worker did not terminate after reads stopped')
        assert snapshot is not None, ('Repeated read invalidated its own preparation', len(tokens), tokens[:3], tokens[-3:])
        assert tokens and len(set(tokens)) == 1, tokens
        assert probes and owner_thread not in probes, probes
        assert current.parameter_output_values['VIDEO_OUT'] == [str(files[0])]
        assert current._hmb_verified_media[0] == current._execution_media_identity(current._picker_state())
        records.append(dict(case='steady_10ms_reads_50ms_io_eventually_ready', pending_reads=len(tokens), token_changes=len(set(tokens)) - 1, probes=len(probes)))
        await delete(current)

        current = await node()
        entered, release = threading.Event(), threading.Event()
        prepared = []
        publications = []
        original_publish = current._sync_outputs_from_state

        def blocking_prepare(state):
            prepared.append(state['videos'][0]['video_path'])
            if len(prepared) == 1:
                entered.set()
                assert release.wait(5), 'Controlled old-state probe not released'
            time.sleep(.05)
            return original_prepare(state)

        def publish(state, *args, **kwargs):
            if kwargs.get('_prepared_publication') is not None:
                publications.append((state['videos'][0]['video_path'], threading.get_ident()))
            return original_publish(state, *args, **kwargs)

        with mock.patch.object(picker.HMBVideoPickerLibrary, '_prepare_execution_media', side_effect=blocking_prepare), mock.patch.object(current, '_sync_outputs_from_state', side_effect=publish):
            try:
                fresh_revision(current, 'Old state before live replacement')
                try:
                    current._hmb_shot_routing_snapshot()
                except ValueError as error:
                    assert getattr(error, 'hmb_picker_media_preparing', False) is True
                await wait_until(entered.is_set, 'Old source probe never started')
                old_token = current._hmb_video_removal_sync_token
                changed = current._picker_state()
                changed['videos'][0]['video_path'] = str(files[1])
                current._write_state(changed)
                current._schedule_video_removal_output_sync()
                assert current._hmb_video_removal_sync_token == old_token + 1, 'Real UI change must retain invalidation'
                release.set()
                snapshot, tokens = await poll(current)
            finally:
                release.set()
                await wait_until(lambda: not getattr(current, '_hmb_video_removal_sync_running', False), 'Changed source worker did not terminate')
        assert snapshot is not None and prepared[:2] == [str(files[0]), str(files[1])], prepared
        assert publications and all(path == str(files[1]) and thread == owner_thread for path, thread in publications), publications
        assert current.parameter_output_values['VIDEO_OUT'] == [str(files[1])]
        assert current._hmb_verified_media[0] == current._execution_media_identity(current._picker_state())
        records.append(dict(case='real_change_invalidates_old_worker_then_latest_ready', prepared=prepared, published=[path for path, _ in publications], pending_reads=len(tokens)))
        await delete(current)

        current = await node()
        entered, release = threading.Event(), threading.Event()

        def deleted_prepare(state):
            entered.set()
            assert release.wait(5), 'Controlled deletion probe not released'
            return original_prepare(state)

        with mock.patch.object(picker.HMBVideoPickerLibrary, '_prepare_execution_media', side_effect=deleted_prepare):
            try:
                fresh_revision(current, 'Pending state before real deletion')
                try:
                    current._hmb_shot_routing_snapshot()
                except ValueError as error:
                    assert getattr(error, 'hmb_picker_media_preparing', False) is True
                await wait_until(entered.is_set, 'Deleted source probe never started')
                await delete(current)
                after_delete = copy.deepcopy(dict(current.parameter_output_values))
            finally:
                release.set()
                await wait_until(lambda: not getattr(current, '_hmb_video_removal_sync_running', False), 'Deleted worker did not exit')
        assert dict(current.parameter_output_values) == after_delete, 'Late completion published after deletion'
        assert not getattr(current, '_hmb_verified_media', None)
        records.append(dict(case='actual_delete_blocks_late_publication_and_exits', late_output_changes=0))
    finally:
        for instance in created:
            if not instance._hmb_node_deleted:
                instance.after_node_deleted()
    return records


def main():
    from griptape_nodes.retained_mode.engine import engine_scope
    with tempfile.TemporaryDirectory(prefix='hmb-picker-snapshot-polling-') as directory:
        folder = Path(directory)
        variables = {name: str(folder / name) for name in ('XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'XDG_CACHE_HOME', 'LOCALAPPDATA', 'APPDATA', 'GTN_CONFIG_WORKSPACE_DIRECTORY')}
        with mock.patch.dict(os.environ, variables), mock.patch.object(socket, 'create_connection', side_effect=AssertionError('Network forbidden')):
            try:
                logging.disable(logging.CRITICAL)
                with engine_scope() as engine:
                    records = asyncio.run(scenario(engine, folder))
            finally:
                logging.shutdown()
    print('HMB_VIDEOPICKER_SNAPSHOT_POLLING_HOST=PASS ' + json.dumps(dict(cases=records, paid_calls=0, user_graph_requests=0), sort_keys=True))


if __name__ == '__main__':
    main()
