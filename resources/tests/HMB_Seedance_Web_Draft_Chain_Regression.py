"""Offline web Draft480 chains through actual Worker/Generator/HTTP guards.

Only SDK topology, Agent model output, media transport and verified-file
publication are synthetic. The production SQLite journal, parent binding,
Generator pipeline, Broker bridge and final command opener remain active.
No live API, retained user graph, provider or paid render is used.
"""
from __future__ import annotations

import asyncio
from contextlib import ExitStack, closing
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
from urllib.error import URLError
from urllib.parse import urlparse
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import HMB_Seedance_Web_Rerender_Regression as fixture
from _hmb_web_rerender_settings_fixtures import freeze_command
import _hmb_web_rerender as web

g = fixture.target
Base, Execution = fixture.Base, fixture.Execution
PROJECT = {'project_id': 'superwings12', 'project_name': '슈퍼윙즈12'}
PARENT = 'job-' + '0' * 32


def draft_settings(**changes):
    return {'model': g.SEEDANCE_2_5_MODEL_ID,
        'input_mode': g.INPUT_MODE_MULTIMODAL_REFERENCES,
        'quality': '480p', 'resolution': '480p', 'aspect_ratio': '16:9',
        'duration_seconds': 4, 'generate_audio': False, 'watermark': False,
        'return_last_frame': False, 'output_format': 'mov', 'priority': 0,
        'omni_reference_task_type': 'reference', 'draft': True, **changes}


def saved_link(name, parent, child, *, origin=g.AI_BROKER_INTERNAL_ORIGIN,
               owner='17', project=None, state='completed', checkpoint=None,
               result=True, render_key=None, updated=1.0):
    """One synthetic legacy row, including exact saved command provenance."""
    project = PROJECT if project is None else project
    render_key = render_key or 'hmb-legacy-' + name
    command = {'command_id': 'legacy-' + name, 'render_key': render_key,
        'parent_task_id': parent, 'review_id': 'review-' + name,
        'target_id': 'legacy-target', 'binding_fingerprint': 'a' * 64,
        'prompt': 'Synthetic saved review', **project}
    document = {'command': command, 'agent_result': None, 'checkpoint': checkpoint,
        'result': {'task_id': child} if result else None, 'error_code': ''}
    return (web.OperationJournal.key(origin, owner, command['command_id']), origin,
        owner, command['command_id'], render_key, web._digest(command), state,
        web._json(document), updated, updated)


def write_legacy_operations(directory, rows):
    """A pre-index installation's existing operations table, one transaction."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / 'operations.sqlite3'
    with closing(sqlite3.connect(path)) as connection:
        connection.execute('''CREATE TABLE operations (
            operation_key TEXT PRIMARY KEY, origin TEXT NOT NULL,
            owner_key TEXT NOT NULL, command_id TEXT NOT NULL,
            render_key TEXT NOT NULL, command_hash TEXT NOT NULL,
            state TEXT NOT NULL, document TEXT NOT NULL,
            created_at REAL NOT NULL, updated_at REAL NOT NULL)''')
        connection.executemany('INSERT INTO operations VALUES(?,?,?,?,?,?,?,?,?,?)', rows)
        connection.commit()
    return path


def operations_digest(path):
    with closing(sqlite3.connect(path)) as connection:
        rows = connection.execute('SELECT * FROM operations ORDER BY operation_key').fetchall()
    return hashlib.sha256(web._json(rows).encode()).hexdigest()


class SyntheticAgent:
    name = 'Connected offline HMB Agent'

    def __init__(self):
        self.calls = []

    def _hmb_issue_web_rerender_authority(self, **values):
        assert values['owner_key'] == '17'
        return object()

    def _hmb_web_rerender_policy_status(self, **kwargs):
        return {'ready': True, 'policy_verified': True, 'version': 'synthetic'}

    def _hmb_web_rerender_busy(self):
        return False

    async def _hmb_run_web_rerender(self, prompt, media, settings, authority):
        self.calls.append({'prompt': prompt, 'media': deepcopy(media),
                           'settings': deepcopy(settings)})
        text = f'WEB REVIEW {len(self.calls)}: {prompt} {{SIGN}}'
        return {'text': text, 'run_id': 'synthetic-agent-' + str(len(self.calls)),
            'output_sha256': hashlib.sha256(text.encode()).hexdigest(),
            'policy_identity': {'mode': 'preserved_parent', 'reinjected': False},
            'observation': {'status': 'synthetic'}}


class Response(io.BytesIO):
    status = 200

    def __init__(self, value, url):
        super().__init__(json.dumps(value).encode())
        self.url = url

    def geturl(self):
        return self.url


class SyntheticOpener:
    def __init__(self):
        self.posts, self.capability_reads = [], []
        self.response_lost = False

    def open(self, request, *, timeout):
        path = urlparse(request.full_url).path
        if request.get_method() == 'GET' and path == g.BROKER_SEEDANCE_CAPABILITIES_PATH:
            self.capability_reads.append(request.full_url)
            return Response({'schema': g.BROKER_SEEDANCE_CAPABILITIES_SCHEMA,
                'version': 3, 'models': {g.SEEDANCE_2_5_MODEL_ID: {
                    'tasks': ['text_to_video', 'first_last_frame', 'reference_to_video'],
                    'output_formats': ['mp4', 'mov'], 'return_last_frame': True,
                    'draft_generation': True, 'draft_preview_resolution': '480p',
                    'draft_final_resolution': '1080p', 'draft_source_reference': 'broker_job_id',
                    'draft_source_ttl_seconds': 604800, 'draft_output_formats': ['mp4', 'mov']}}},
                request.full_url)
        if request.get_method() != 'POST' or path != '/api/v1/generate/video':
            raise AssertionError('Unexpected synthetic transport route')
        body = json.loads(request.data)
        assert request.get_header('Idempotency-key') == body['client_request_id']
        operation = request.get_header('X-hmb-rerender-operation')
        assert operation and request.get_header('X-hmb-rerender-lease')
        assert request.get_header('X-hmb-rerender-fence') == '1'
        assert not any(key.startswith('_hmb_') for key in body)
        job = 'job-' + 'abcdef'[len(self.posts)] * 32
        self.posts.append({'body': deepcopy(body), 'operation_id': operation,
                           'task_id': job})
        if self.response_lost:
            raise URLError('Synthetic response lost after accepted create')
        return Response({'job_id': job, 'status': 'succeeded',
                         'video_url': 'https://synthetic.invalid/completed.mov'}, request.full_url)


class SyntheticProtocol:
    owner_key = '17'
    parent_draft_preserved = True
    optional_policy_status_supported = True

    def __init__(self, opener):
        self.events = []
        self.fail_prepared = False
        self.bridge = g._HMBAIBrokerBridge(opener=opener,
                                         server_url=g.AI_BROKER_INTERNAL_ORIGIN)
        self.bridge._load_access_token = lambda: 'offline-boundary-token'
        self.bridge.account_snapshot = lambda **kwargs: SimpleNamespace(connected=True)

    def result(self, command, event, **fields):
        self.events.append((command['operation_id'], event, deepcopy(fields)))
        if event == 'prepared' and self.fail_prepared:
            raise g._BrokerError('Synthetic prepared rejection', status_code=429)
        return {'operation_id': command['operation_id'],
                'state': 'completed' if event == 'ack' else 'prepared'}

    def renew(self, command):
        pass


class WebDraftChainTests(unittest.TestCase):
    def setUp(self):
        self.context = ExitStack()
        self.addCleanup(self.context.close)
        self.directory = Path(self.context.enter_context(tempfile.TemporaryDirectory(
            prefix='hmb-web-draft-chain-')))
        self.context.enter_context(mock.patch.dict(os.environ,
            {'LOCALAPPDATA': str(self.directory / 'local')}))
        original_connect = socket.socket.connect

        def offline_only(sock, address):
            # Windows asyncio's wake-up socketpair requires local loopback.
            if isinstance(address, tuple) and address[0] in ('127.0.0.1', '::1'):
                return original_connect(sock, address)
            raise AssertionError('Offline test attempted external socket access')

        self.context.enter_context(mock.patch.object(socket.socket, 'connect', new=offline_only))
        self.context.enter_context(mock.patch.object(socket, 'create_connection',
            side_effect=AssertionError('Offline test attempted a network connection')))
        self.agent = SyntheticAgent()
        for name, replacement in (
            ('_runtime_node_is_live', lambda self, **kwargs: not self._hmb_node_deleted),
            ('_manual_agent_prompt_source', lambda node: self.agent),
            ('_exact_incoming_source', lambda self, *args, **kwargs: None),
            ('_has_incoming_parameter_connection', lambda self, name: False),
        ):
            self.context.enter_context(mock.patch.object(Base, name, replacement))
        self.context.enter_context(mock.patch.object(g.GriptapeNodes, 'NodeManager',
            return_value=SimpleNamespace(get_node_parent_flow_by_name=lambda name: 'offline-flow'),
            create=True))
        def synthetic_preflight(run, destination, output_format):
            path = Path(destination.resolve())
            self.assertTrue(path.is_absolute())
            self.assertTrue(path.resolve().is_relative_to(self.directory.resolve()))
            return path

        self.context.enter_context(mock.patch.object(Execution, '_preflight_output_destination',
                                                    new=synthetic_preflight))
        self.context.enter_context(mock.patch.object(Execution, '_prepare_video_references_for_run',
            new=lambda self, params: params))
        self.context.enter_context(mock.patch.object(g._HMBWebRerenderOutput, 'build_file',
            new=lambda self: SimpleNamespace(resolve=lambda: str(self.path))))
        self.context.enter_context(mock.patch.object(g, '_resolve_mp4_decode_verifier',
            return_value=SimpleNamespace(executable='synthetic', backend='synthetic')))
        self.context.enter_context(mock.patch.object(g, '_get_build_diagnostics', return_value={}))
        for name in ('bind_task_origin', 'bind_task_project', 'update_case'):
            self.context.enter_context(mock.patch.object(g._review, name))
        self.context.enter_context(mock.patch.object(g._review, 'capture_inputs',
            return_value={'status': 'synthetic'}))
        self.context.enter_context(mock.patch.object(g._review, 'start_case', return_value='synthetic-case'))
        self.publications = []
        test = self

        async def synthetic_verified_publication(run, task, job_id, destination, *args, **kwargs):
            checkpoint = run._generation_recovery_state()
            test.assertEqual(checkpoint['task_id'], job_id)
            path = Path(destination.resolve())
            test.assertTrue(path.is_absolute(), 'Publication path escaped the test directory')
            test.assertTrue(path.resolve().is_relative_to(test.directory.resolve()),
                            'Publication path escaped the test directory')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'SYNTHETIC-VERIFIED-VIDEO-PUBLICATION')
            run.parameter_output_values.update(generation_id=job_id, generation_status='succeeded',
                video_url=g.VideoUrlArtifact(value=str(path)))
            run._set_generation_recovery_checkpoint(stage='local_succeeded', task_id=job_id,
                task_identity='broker_task', status='succeeded', params=run._web_params)
            await run._force_save_generation_recovery_checkpoint(required=False, reason='local_succeeded')
            test.publications.append({'task_id': job_id,
                'draft_action': checkpoint.get('draft_action'),
                'effective_draft_action': run._web_params['draft_action'],
                'path': str(path), 'kwargs': deepcopy(kwargs)})

        self.context.enter_context(mock.patch.object(Execution, '_save_completed_task',
                                                   new=synthetic_verified_publication))
        self.node = fixture.new_node()
        self.node.parameter_values.update(model_id=g.SEEDANCE_2_5_MODEL_ID,
            resolution='480p', draft_action=g.DRAFT_ACTION_PREVIEW, output_format='mov',
            duration=4, ratio='16:9', return_last_frame=False, draft_job_id='job-' + 'f' * 32)
        self.node.parameter_output_values['generation_id'] = PARENT
        self.node._web_original_parameters = deepcopy(self.node.parameter_values)
        self.node._web_original_outputs = g._web_rerender_plain(dict(self.node.parameter_output_values))
        # EngineWorker stores only a weak reference to the engine.
        self.engine = type('OfflineEngine', (), {})()
        self.journal = web.OperationJournal(self.directory / 'journal')
        self.worker = web.EngineWorker(self.engine, self.journal)
        self.opener = SyntheticOpener()
        self.protocol = SyntheticProtocol(self.opener)
        self.target_id = str(uuid4())

    def command(self, snapshot, parent=PARENT, settings=None):
        operation = str(uuid4())
        return freeze_command({'operation_id': operation,
            'render_key': 'hmb-web-rerender-' + operation, 'target_id': self.target_id,
            'session_id': self.worker.session_id, 'snapshot_sha256': snapshot['binding_fingerprint'],
            'web_prompt': 'Web review ' + operation[-8:], 'parent_task_id': parent,
            'review_id': str(uuid4()), 'state': 'claimed', 'lease_id': str(uuid4()), 'fence': 1,
            'policy_application': 'preserved_parent', 'policy_reinjected': False,
            'policy_required': False, 'input_mode': 'web_only',
            'exclude_authored_prompt': True, 'preserve_connected_sources': True, **PROJECT},
            draft_settings() if settings is None else settings)

    def record(self, command):
        row = self.journal.read(self.journal.key(self.protocol.bridge.server_url,
                                self.protocol.owner_key, command['operation_id']))
        return {**row, **row['document']}

    def unchanged(self):
        fixture.unchanged(self.node)
        self.assertEqual(self.node.get_parameter_value('resolution'), '480p')
        self.assertEqual(self.node.get_parameter_value('draft_action'), g.DRAFT_ACTION_PREVIEW)
        self.assertFalse(self.node._hmb_draft_finalize_pending)

    def test_three_web_drafts_no_final_and_replays_do_not_repeat_either_paid_boundary(self):
        async def scenario():
            parent, commands, ids = PARENT, [], []
            frozen = draft_settings()
            for cycle in range(3):
                snapshot = self.node._hmb_web_rerender_capture_inputs()
                request = self.command(snapshot, parent, frozen)
                await self.worker.execute(self.node, self.agent, snapshot, self.protocol, request)
                row = self.record(request)
                self.assertEqual(row['state'], 'completed', row)
                self.assertEqual(len(self.opener.posts), cycle + 1)
                self.assertEqual(len(self.agent.calls), cycle + 1)
                post = self.opener.posts[-1]
                body, child = post['body'], post['task_id']
                self.assertEqual({k: v for k, v in body.items() if k in web.PARENT_SETTINGS_FIELDS}, frozen)
                self.assertIs(body['draft'], True)
                self.assertEqual((body['quality'], body['resolution'], body['output_format']),
                                 ('480p', '480p', 'mov'))
                self.assertNotIn('draft_job_id', body)
                self.assertNotIn('draft_action', body)
                self.assertEqual(body['image_urls'], snapshot['params']['reference_images'])
                self.assertEqual(body['prompt'], row['agent_result']['text'])
                self.assertIs(body['generate_audio'], False)
                self.assertEqual(body['priority'], 0)
                self.assertEqual(row['result']['parent_task_id'], parent)
                self.assertEqual(row['result']['task_id'], child)
                self.assertEqual(row['checkpoint']['draft_action'], g.DRAFT_ACTION_PREVIEW)
                self.assertEqual(row['checkpoint']['stage'], 'local_succeeded')
                self.assertEqual(self.agent.calls[-1]['settings']['draft_action'], g.DRAFT_ACTION_PREVIEW)
                self.assertEqual(self.publications[-1]['draft_action'], g.DRAFT_ACTION_PREVIEW)
                prepared = [fields for operation, event, fields in self.protocol.events
                            if operation == request['operation_id'] and event == 'prepared']
                self.assertEqual(len(prepared), 1)
                self.assertEqual(prepared[0]['render_payload_sha256'], web.request_fingerprint(body))
                self.unchanged()
                await asyncio.gather(*(self.worker.execute(self.node, self.agent, snapshot,
                                      self.protocol, request) for _ in range(3)))
                restarted = web.EngineWorker(self.engine, web.OperationJournal(self.journal.root))
                await restarted.execute(self.node, self.agent, snapshot, self.protocol, request)
                self.assertEqual(len(self.opener.posts), cycle + 1)
                self.assertEqual(len(self.agent.calls), cycle + 1)
                self.assertFalse(self.worker.leases)
                commands.append(request)
                ids.append(child)
                parent = child
                # Model the next immutable parent request using the observed
                # final POST, as the Broker projects it for the next command.
                frozen = {key: deepcopy(value) for key, value in body.items()
                          if key in web.PARENT_SETTINGS_FIELDS}
            self.assertEqual(len(set(ids)), 3)
            self.assertEqual(len({item['render_key'] for item in commands}), 3)
            self.assertEqual([item['parent_task_id'] for item in commands], [PARENT, ids[0], ids[1]])
            self.assertEqual(self.worker.children[self.target_id], ids)
            self.assertEqual(len(self.publications), 3)
            self.assertEqual(len(set(item['path'] for item in self.publications)), 3)
            self.assertTrue(all('draft480p' in item['path'] for item in self.publications))
            self.assertTrue(all('final1080p' not in item['path'] for item in self.publications))
            descendants = self.journal.descendants(self.protocol.bridge.server_url,
                self.protocol.owner_key, PARENT, PROJECT['project_id'])
            self.assertTrue(set(ids).issubset(descendants))
            self.unchanged()
        asyncio.run(scenario())

    def test_accepted_response_loss_keeps_same_render_key_and_never_resubmits_on_replay(self):
        async def scenario():
            snapshot = self.node._hmb_web_rerender_capture_inputs()
            request = self.command(snapshot)
            self.opener.response_lost = True
            await self.worker.execute(self.node, self.agent, snapshot, self.protocol, request)
            row = self.record(request)
            self.assertEqual(row['state'], 'uncertain', row)
            self.assertEqual(row['render_key'], request['render_key'])
            self.assertEqual(row['checkpoint']['task_id'], request['render_key'])
            self.assertEqual(row['checkpoint']['task_identity'], 'client_request')
            self.assertEqual(row['checkpoint']['draft_action'], g.DRAFT_ACTION_PREVIEW)
            self.assertEqual(len(self.agent.calls), 1)
            self.assertEqual(len(self.opener.posts), 1)
            self.assertIs(self.opener.posts[0]['body']['draft'], True)
            self.opener.response_lost = False
            await self.worker.execute(self.node, self.agent, snapshot, self.protocol, request)
            restarted = web.EngineWorker(self.engine, web.OperationJournal(self.journal.root))
            await restarted.execute(self.node, self.agent, snapshot, self.protocol, request)
            self.assertEqual(len(self.agent.calls), 1)
            self.assertEqual(len(self.opener.posts), 1)
            self.assertEqual(self.record(request)['render_key'], request['render_key'])
            self.assertEqual(self.publications, [])
            self.unchanged()
        asyncio.run(scenario())

    def test_prepared_rejection_is_not_sent_and_cannot_replay_agent_or_create(self):
        async def scenario():
            snapshot = self.node._hmb_web_rerender_capture_inputs()
            request = self.command(snapshot)
            self.protocol.fail_prepared = True
            await self.worker.execute(self.node, self.agent, snapshot, self.protocol, request)
            row = self.record(request)
            self.assertEqual(row['state'], 'failed', row)
            self.assertEqual(row['error_code'], 'prepared_http_429')
            self.assertEqual(row['render_key'], request['render_key'])
            self.assertEqual(len(self.agent.calls), 1)
            self.assertEqual(self.opener.posts, [])
            self.protocol.fail_prepared = False
            await self.worker.execute(self.node, self.agent, snapshot, self.protocol, request)
            restarted = web.EngineWorker(self.engine, web.OperationJournal(self.journal.root))
            await restarted.execute(self.node, self.agent, snapshot, self.protocol, request)
            self.assertEqual(len(self.agent.calls), 1)
            self.assertEqual(self.opener.posts, [])
            self.unchanged()
        asyncio.run(scenario())

    def test_absent_or_false_draft_never_promotes_normal_480p_to_draft(self):
        async def scenario(settings):
            snapshot = self.node._hmb_web_rerender_capture_inputs()
            request = self.command(snapshot, settings=settings)
            await self.worker.execute(self.node, self.agent, snapshot, self.protocol, request)
            self.assertEqual(self.record(request)['state'], 'completed')
            posted = self.opener.posts[-1]['body']
            self.assertEqual({key: value for key, value in posted.items()
                              if key in web.PARENT_SETTINGS_FIELDS}, settings)
            self.assertIsNot(posted.get('draft'), True)
            self.assertNotIn('draft_job_id', posted)
            self.assertEqual(self.publications[-1]['effective_draft_action'], g.DRAFT_ACTION_OFF)
            self.assertIsNone(self.publications[-1]['draft_action'])
            self.unchanged()
        for value in (None, False):
            with self.subTest(draft=value):
                settings = draft_settings(draft=False)
                if value is None:
                    settings.pop('draft')
                asyncio.run(scenario(settings))

    def test_invalid_draft_types_model_and_resolution_fail_before_agent_or_post(self):
        async def scenario():
            snapshot = self.node._hmb_web_rerender_capture_inputs()
            invalid = [draft_settings(draft=value) for value in ('true', 'False', 0, 1, None)]
            invalid.extend((draft_settings(model=g.SEEDANCE_2_0_MODEL_ID),
                draft_settings(quality='720p', resolution='720p'),
                draft_settings(quality='480p', resolution='1080p'),
                draft_settings(draft_job_id='job-' + 'f' * 32)))
            for settings in invalid:
                with self.subTest(settings=settings):
                    request = self.command(snapshot, settings=settings)
                    await self.worker.execute(self.node, self.agent, snapshot, self.protocol, request)
                    self.assertEqual(self.record(request)['state'], 'failed')
            self.assertEqual(self.agent.calls, [])
            self.assertEqual(self.opener.posts, [])
            self.assertEqual(self.publications, [])
            self.unchanged()
        asyncio.run(scenario())

    def test_draft_projection_closes_for_arbitrary_iterations_until_explicit_mode_change(self):
        snapshot = self.node._hmb_web_rerender_capture_inputs()
        frozen = draft_settings()
        for iteration in range(192):
            settings, context = g._web_rerender_parent_execution_settings(frozen)
            params = g._web_rerender_apply_parent_settings(snapshot['params'], settings)
            params['prompt'] = f'Projection-only review {iteration}'
            body = self.node._build_broker_payload(params)
            self.assertIs(body['draft'], True)
            self.assertEqual((body['resolution'], body['quality']), ('480p', '480p'))
            self.assertEqual(context['draft_action'], g.DRAFT_ACTION_PREVIEW)
            self.assertNotIn('draft_job_id', body)
            frozen = {key: deepcopy(value) for key, value in body.items()
                      if key in web.PARENT_SETTINGS_FIELDS}
        # Only this explicit new parent setting changes the mode. There is no
        # third-render threshold, Final promotion, or iteration counter.
        changed = {**frozen, 'draft': False, 'quality': '1080p', 'resolution': '1080p'}
        settings, context = g._web_rerender_parent_execution_settings(changed)
        params = g._web_rerender_apply_parent_settings(snapshot['params'], settings)
        params['prompt'] = 'Explicit normal1080 user selection'
        body = self.node._build_broker_payload(params)
        self.assertIsNot(body.get('draft'), True)
        self.assertEqual((body['resolution'], body['quality']), ('1080p', '1080p'))
        self.assertEqual(context['draft_action'], g.DRAFT_ACTION_OFF)
        self.assertEqual(self.agent.calls, [])
        self.assertEqual(self.opener.posts, [])
        self.unchanged()

    def test_old_server_draft_capability_is_rejected_before_agent_or_create(self):
        async def scenario():
            snapshot = self.node._hmb_web_rerender_capture_inputs()
            for advertised in (False, None):
                with self.subTest(parent_draft_preserved=advertised):
                    if advertised is None:
                        protocol = SimpleNamespace(owner_key=self.protocol.owner_key,
                            bridge=self.protocol.bridge, result=self.protocol.result,
                            renew=self.protocol.renew)
                    else:
                        protocol = self.protocol
                        protocol.parent_draft_preserved = advertised
                    request = self.command(snapshot)
                    await self.worker.execute(self.node, self.agent, snapshot, protocol, request)
                    self.assertEqual(self.record(request)['state'], 'failed')
            self.assertEqual(self.agent.calls, [])
            self.assertEqual(self.opener.posts, [])
            self.unchanged()
        asyncio.run(scenario())

    def test_old_server_draft_capability_does_not_block_ordinary_720p(self):
        async def scenario():
            snapshot = self.node._hmb_web_rerender_capture_inputs()
            self.protocol.parent_draft_preserved = False
            settings = draft_settings(quality='720p', resolution='720p')
            settings.pop('draft')
            request = self.command(snapshot, settings=settings)
            await self.worker.execute(self.node, self.agent, snapshot, self.protocol, request)
            self.assertEqual(self.record(request)['state'], 'completed')
            self.assertEqual(len(self.agent.calls), 1)
            self.assertEqual(len(self.opener.posts), 1)
            self.assertIsNot(self.opener.posts[0]['body'].get('draft'), True)
            self.assertEqual(self.opener.posts[0]['body']['quality'], '720p')
            self.unchanged()
        asyncio.run(scenario())

    def test_deep_legacy_chains_restore_latest_leaf_and_continue_draft_after_restart(self):
        async def scenario(depth):
            rows, parent = [], PARENT
            for index in range(1, depth + 1):
                child = 'job-' + f'{index:032x}'
                rows.append(saved_link(f'depth-{depth}-{index}', parent, child,
                                       updated=float(index)))
                parent = child
            directory = self.directory / ('legacy-depth-' + str(depth))
            path = write_legacy_operations(directory, rows)
            before = operations_digest(path)
            migrated = web.OperationJournal(directory)
            expected = ['job-' + f'{index:032x}'
                        for index in range(depth - 30, depth + 1)]
            self.assertEqual(migrated.descendants(self.protocol.bridge.server_url,
                self.protocol.owner_key, PARENT, PROJECT['project_id']), expected)
            restarted = web.EngineWorker(self.engine, web.OperationJournal(directory))
            self.engine.node_manager = SimpleNamespace(get_node_by_name=lambda name: self.agent)
            self.engine.context_manager = SimpleNamespace(get_current_workflow_name=lambda: 'offline-flow')
            restarted.protocols[self.protocol.bridge.server_url] = self.protocol
            with mock.patch.object(web._review, 'task_origin',
                    return_value=self.protocol.bridge.server_url), \
                 mock.patch.object(web._review, 'task_project', return_value=deepcopy(PROJECT)):
                found = await restarted._target(self.node)
            self.assertIsNotNone(found)
            _, descriptor, snapshot, _ = found
            self.assertTrue(descriptor['ready'])
            self.assertEqual(descriptor['parent_task_ids'], [PARENT, *expected])
            self.assertEqual(len(descriptor['parent_task_ids']), 32)
            self.assertIn(parent, descriptor['parent_task_ids'])
            self.assertEqual(operations_digest(path), before,
                             'Derived-index migration altered original saved operations')
            creates = len(self.opener.posts)
            self.worker, self.journal = restarted, restarted.journal
            self.target_id = descriptor['target_id']
            request = self.command(snapshot, parent=parent)
            await restarted.execute(self.node, self.agent, snapshot, self.protocol, request)
            self.assertEqual(self.record(request)['state'], 'completed')
            self.assertEqual(len(self.opener.posts), creates + 1)
            self.assertIs(self.opener.posts[-1]['body']['draft'], True)
            self.assertEqual(self.opener.posts[-1]['body']['quality'], '480p')
            self.assertNotIn('draft_job_id', self.opener.posts[-1]['body'])
            self.unchanged()
        for depth in (64, 1153):
            with self.subTest(saved_chain_depth=depth):
                asyncio.run(scenario(depth))

    def test_lineage_cycle_scope_and_unconfirmed_keys_do_not_pollute_restored_window(self):
        good_a, good_b, confirmed = ('job-' + digit * 32 for digit in ('6', '7', '8'))
        rejected = ['job-' + f'{index:032x}' for index in range(8000, 8007)]
        checkpoint = lambda task_id, **changes: {
            'task_id': task_id, 'task_identity': 'broker_task', 'stage': 'accepted',
            'status': 'queued', 'broker_server_url': self.protocol.bridge.server_url, **changes}
        rows = [saved_link('good-a', PARENT, good_a, updated=1),
            saved_link('good-b', good_a, good_b, updated=2),
            saved_link('cycle-root', good_b, PARENT, updated=3),
            saved_link('cycle-self', good_a, good_a, updated=4),
            saved_link('confirmed-checkpoint', good_b, confirmed, state='submitting',
                       checkpoint=checkpoint(confirmed), result=False, updated=5),
            saved_link('other-origin', PARENT, rejected[0],
                       origin='https://other.synthetic.invalid', updated=10),
            saved_link('other-owner', PARENT, rejected[1], owner='99', updated=11),
            saved_link('other-project', PARENT, rejected[2],
                       project={'project_id': 'katuri8', 'project_name': '까투리8'}, updated=12),
            saved_link('uncertain-result', PARENT, rejected[3], state='uncertain', updated=13),
            saved_link('provisional-client', PARENT, rejected[4], state='submitting',
                       checkpoint=checkpoint(rejected[4], task_identity='client_request'),
                       result=False, updated=14),
            saved_link('unknown-checkpoint', PARENT, rejected[5], state='uncertain',
                       checkpoint=checkpoint(rejected[5], status='submission_unknown'),
                       result=False, updated=15),
            saved_link('wrong-checkpoint-origin', PARENT, rejected[6], state='submitting',
                       checkpoint=checkpoint(rejected[6], broker_server_url='https://other.synthetic.invalid'),
                       result=False, updated=16),
            saved_link('same-as-render-key', PARENT, 'hmb-provisional-identity',
                       render_key='hmb-provisional-identity', updated=17)]
        directory = self.directory / 'legacy-isolation'
        path = write_legacy_operations(directory, rows)
        before = operations_digest(path)
        for _ in range(2):
            journal = web.OperationJournal(directory)
            found = journal.descendants(self.protocol.bridge.server_url,
                self.protocol.owner_key, PARENT, PROJECT['project_id'])
            self.assertEqual(set(found), {good_a, good_b, confirmed})
            self.assertEqual(len(found), len(set(found)))
            self.assertNotIn(PARENT, found)
            self.assertTrue(set(found).isdisjoint(rejected))
            self.assertNotIn('hmb-provisional-identity', found)
            self.assertEqual(operations_digest(path), before)

    def test_live_and_legacy_writer_updates_refresh_only_confirmed_derived_links(self):
        directory = self.directory / 'derived-live-writes'
        journal = web.OperationJournal(directory)
        child = 'job-' + '9' * 32
        command = {'command_id': 'derived-live', 'render_key': 'hmb-derived-live',
            'parent_task_id': PARENT, 'review_id': 'synthetic-review',
            'target_id': 'synthetic-target', 'binding_fingerprint': 'a' * 64,
            'prompt': 'Synthetic review', **PROJECT}
        accepted = journal.accept(origin=self.protocol.bridge.server_url,
                                  owner_key='17', command=command)
        key = accepted['operation_key']
        read = lambda: journal.descendants(self.protocol.bridge.server_url, '17', PARENT,
                                           PROJECT['project_id'])
        self.assertEqual(read(), [])
        journal.transition(key, {'accepted'}, 'submitting')
        journal.checkpoint(key, {'task_id': command['render_key'],
            'task_identity': 'client_request', 'stage': 'submission_unknown',
            'status': 'submission_unknown', 'broker_server_url': self.protocol.bridge.server_url},
            'synthetic-unknown', True)
        self.assertEqual(read(), [])
        journal.checkpoint(key, {'task_id': child, 'task_identity': 'broker_task',
            'stage': 'accepted', 'status': 'queued',
            'broker_server_url': self.protocol.bridge.server_url}, 'synthetic-accepted', True)
        self.assertEqual(read(), [child])
        journal.transition(key, {'submitting'}, 'completed', result={'task_id': child})
        self.assertEqual(read(), [child])
        # An old process writes only the original table. The derived index must
        # observe this update on the next read without modifying that row.
        row = journal.read(key)
        changed = deepcopy(row['document'])
        changed['result'] = None
        changed['checkpoint'] = None
        with closing(sqlite3.connect(journal.path)) as connection:
            connection.execute('UPDATE operations SET state=?,document=? WHERE operation_key=?',
                               ('uncertain', web._json(changed), key))
            connection.commit()
        before = operations_digest(journal.path)
        restarted = web.OperationJournal(directory)
        self.assertEqual(restarted.descendants(self.protocol.bridge.server_url,
            '17', PARENT, PROJECT['project_id']), [])
        self.assertEqual(operations_digest(journal.path), before)


if __name__ == '__main__':
    unittest.main()
