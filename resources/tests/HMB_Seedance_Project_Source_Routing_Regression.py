"""Selected ImageAsset project provenance; synthetic graph and transport only."""
from __future__ import annotations

import asyncio
from contextlib import ExitStack
from copy import deepcopy
import importlib.util
import itertools
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))
spec = importlib.util.spec_from_file_location('project_source_draft_fixture', Path(__file__).with_name('HMB_Seedance_Draft_Regression.py'))
base = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = base
spec.loader.exec_module(base)
t = base.t
from _hmb_project import resolve_project
from griptape_nodes.node_library.library_registry import LibraryRegistry
from griptape_nodes.retained_mode.events.connection_events import (
    IncomingConnection, ListConnectionsForNodeResultSuccess,
)


class HMBImageAssetLibrary:
    metadata = {'library': 'HMB_GP_Production', 'node_type': 'HMBImageAssetLibrary'}

    def __init__(self, name, project='katuri8'):
        self.name, self.project = name, project
        self._hmb_shot_routing_snapshot = mock.Mock(side_effect=AssertionError('media snapshot'))
        self.process = mock.Mock(side_effect=AssertionError('upstream process'))

    def _hmb_project_identity(self):
        return resolve_project(self.project, default_legacy=False)


class HMBPromptLibrary:
    metadata = {'library': 'HMB_GP_Production', 'node_type': 'HMBPromptLibrary'}

    def __init__(self, name):
        self.name = name
        self._hmb_connected_source_nodes = {}  # Deliberately cold.
        self.process = mock.Mock(side_effect=AssertionError('Prompt process'))


class HMBAgentLibrary:
    metadata = {'library': 'HMB_GP_Production', 'node_type': 'HMBAgentLibrary'}

    def __init__(self, name):
        self.name = name
        self._hmb_selected_project = mock.Mock(side_effect=AssertionError('Agent cached project'))
        self.process = mock.Mock(side_effect=AssertionError('Agent process'))


class Node(base.Node):
    _resolve_exact_shot_generation_inputs = t.HMBSeedanceGeneration._resolve_exact_shot_generation_inputs

    def _reconcile_shared_shot_routing(self, **kwargs):
        return {'ok': True}

    def _hmb_shot_channel_subscription(self):
        return {'enabled': False}


class Graph:
    def __init__(self, node):
        self.node = node
        self.nodes = {node.name: node}
        self.flows = {node.name: 'fixture-flow'}
        self.edges = {}
        self.reads = []
        self.classes = {c.__name__: c for c in (HMBImageAssetLibrary, HMBPromptLibrary, HMBAgentLibrary)}

    def add(self, node):
        self.nodes[node.name] = node
        self.flows[node.name] = 'fixture-flow'
        return node

    def edge(self, source, source_port, target, target_port):
        self.edges.setdefault(target.name, []).append(IncomingConnection(
            source_node_name=source.name, source_parameter_name=source_port, target_parameter_name=target_port))

    def direct(self, *, child=False, hidden=False, project='katuri8'):
        image = self.add(HMBImageAssetLibrary('Image', project))
        target = 'SHOT_ASSET_IN' if hidden else 'reference_images'
        if child:
            target += '_ParameterListUniqueParamID_fixture'
            original = self.node.get_parameter_by_name
            self.node.get_parameter_by_name = lambda name: SimpleNamespace(parent_container_name='reference_images') if name == target else original(name)
        self.edge(image, 'SHOT_ASSET_OUT' if hidden else 'IMAGE_OUT', self.node, target)
        return image

    def mediated(self, *, legacy=False, hidden=False, project='katuri8'):
        image = self.add(HMBImageAssetLibrary('Mediated Image', project))
        prompt = self.add(HMBPromptLibrary('Prompt'))
        agent = self.add(HMBAgentLibrary('Agent'))
        self.edge(image, 'IMAGE_ASSET_OUT' if legacy else 'SHOT_ASSET_OUT', prompt,
                  'IMAGE_ASSET_IN' if legacy else 'SHOT_ASSET_IN')
        self.edge(prompt, 'PROMPT_OUT', agent, 'SHOT_PROMPT_IN')
        self.edge(agent, 'output', self.node, 'SHOT_PROMPT_IN' if hidden else 'prompt')
        return image

    def read(self, request):
        self.reads.append(request)
        assert request.include_internal is True
        assert request.broadcast_result is False
        return ListConnectionsForNodeResultSuccess(result_details="fixture", incoming_connections=list(self.edges.get(request.node_name, [])), outgoing_connections=[])

    def context(self):
        stack = ExitStack()
        manager = SimpleNamespace(get_node_by_name=lambda name: self.nodes.get(name),
            get_node_parent_flow_by_name=lambda name: self.flows.get(name))
        stack.enter_context(mock.patch.object(t.GriptapeNodes, 'NodeManager', return_value=manager))
        stack.enter_context(mock.patch.object(t.GriptapeNodes, 'handle_request', side_effect=self.read))
        stack.enter_context(mock.patch.object(LibraryRegistry, 'get_library',
            return_value=SimpleNamespace(get_node_class=lambda name: self.classes[name])))
        return stack


class ProjectSourceTests(unittest.TestCase):
    def tearDown(self):
        while base.TEMPORARIES:
            base.TEMPORARIES.pop().cleanup()

    def test_three_projects_direct_hidden_parent_child_and_cold_mediated(self):
        for project, mode in itertools.product(('superwings12', 'katuri8', 'dinoster5'),
                                               ('hidden', 'parent', 'child', 'mediated', 'legacy', 'hidden_agent')):
            with self.subTest(project=project, mode=mode):
                node = Node(); graph = Graph(node)
                if mode in ('hidden', 'parent', 'child'):
                    image = graph.direct(hidden=mode == 'hidden', child=mode == 'child', project=project)
                else:
                    image = graph.mediated(legacy=mode == 'legacy', hidden=mode == 'hidden_agent', project=project)
                before = deepcopy(node.parameter_values)
                with graph.context():
                    selection = node._capture_imageasset_project_selection()
                    self.assertEqual(selection['project']['project_id'], project)
                    self.assertEqual(node._hmb_generation_project(), selection['project'])
                self.assertEqual(node.parameter_values, before)
                image._hmb_shot_routing_snapshot.assert_not_called()
                for source in graph.nodes.values():
                    if isinstance(source, (HMBPromptLibrary, HMBAgentLibrary)):
                        source.process.assert_not_called()
                    if isinstance(source, HMBAgentLibrary):
                        source._hmb_selected_project.assert_not_called()

    def test_all_paths_same_project_agree_conflict_fails(self):
        node = Node(); graph = Graph(node)
        direct = graph.direct(project='katuri8'); graph.mediated(project='katuri8')
        with graph.context():
            self.assertEqual(node._hmb_generation_project()['project_id'], 'katuri8')
            direct.project = 'superwings12'
            with self.assertRaisesRegex(ValueError, 'different projects'):
                node._hmb_generation_project()

    def test_no_source_and_selected_blank_unknown_mismatch_fail(self):
        for value in (None, '', {}, 'unknown', {'project_id': 'katuri8', 'project_name': '다이노스터'}):
            node = Node(); graph = Graph(node)
            if value is not None:
                graph.direct(project=value)
            with graph.context(), self.assertRaises(ValueError):
                node._capture_imageasset_project_selection()

    def test_crossflow_deleted_replaced_wrongport_and_impostor_fail(self):
        for mode in ('crossflow', 'deleted', 'replaced', 'wrongport', 'impostor', 'missing'):
            node = Node(); graph = Graph(node); image = graph.direct(hidden=True)
            if mode == 'crossflow': graph.flows[image.name] = 'other-flow'
            if mode == 'deleted': image._hmb_node_deleted = True
            if mode == 'replaced': graph.nodes[image.name] = SimpleNamespace(name=image.name, metadata=image.metadata)
            if mode == 'wrongport': graph.edges[node.name][0].source_parameter_name = 'arbitrary'
            if mode == 'impostor': graph.classes['HMBImageAssetLibrary'] = type('Other', (), {})
            if mode == 'missing': del graph.nodes[image.name]
            with self.subTest(mode=mode), graph.context(), self.assertRaises(ValueError):
                node._capture_imageasset_project_selection()

    def test_generic_media_and_prompt_text_cannot_claim_project(self):
        node = Node(); graph = Graph(node)
        foreign = graph.add(SimpleNamespace(name='Generic', metadata={},
            _hmb_project_identity=lambda: resolve_project('katuri8')))
        graph.edge(foreign, 'IMAGE_OUT', node, 'reference_images')
        node.values['prompt'] = 'project katuri8 //server/Katuri8/some.png'
        with graph.context(), self.assertRaisesRegex(ValueError, r'Select Project \(Only\), or connect'):
            node._capture_imageasset_project_selection()

    def test_lookup_failure_is_not_default_project(self):
        node = Node(); graph = Graph(node); graph.direct()
        with graph.context(), mock.patch.object(t.GriptapeNodes, 'handle_request', return_value=None), self.assertRaises(ValueError):
            node._capture_imageasset_project_selection()

    def test_frozen_scope_detects_project_and_edge_changes(self):
        node = Node(); graph = Graph(node); image = graph.mediated()
        with graph.context():
            selected = node._capture_imageasset_project_selection()
            image.project = 'dinoster5'
            with self.assertRaises(t._ProjectSelectionChanged): node._assert_imageasset_project_selection(selected)
            image.project = 'katuri8'; graph.edges['Agent'] = []
            with self.assertRaises(t._ProjectSelectionChanged): node._assert_imageasset_project_selection(selected)
        self.assertEqual(selected['project']['project_id'], 'katuri8')

    def test_owner_loop_preupload_and_paced_post_validate_without_worker_graph_access(self):
        async def scenario():
            node = Node(); graph = Graph(node); image = graph.direct()
            thread = threading.get_ident()
            original_read = graph.read
            def read(request):
                self.assertEqual(threading.get_ident(), thread)
                return original_read(request)
            graph.read = read
            with graph.context():
                node._hmb_project_selection_guard = {'selection': node._capture_imageasset_project_selection(),
                    'loop': asyncio.get_running_loop(), 'thread': thread}
                await asyncio.to_thread(node._assert_operation_project_selection)
                image.project = 'dinoster5'
                post = mock.Mock()
                with mock.patch.object(t, '_broker_wait_for_submission_slot'), self.assertRaises(t._ProjectSelectionChanged):
                    await node._await_submission_result(post, {})
                post.assert_not_called()
        asyncio.run(scenario())

    def test_no_source_process_blocks_before_broker_upload_or_post(self):
        node = Node(); graph = Graph(node)
        node._ensure_broker_connected = mock.AsyncMock(side_effect=AssertionError('Broker accessed'))
        with graph.context(), self.assertRaisesRegex(ValueError, r'Select Project \(Only\), or connect'):
            asyncio.run(node._process_generation_impl())
        self.assertEqual(node.upload_calls, 0)
        self.assertEqual(node.bridge.posts, [])
        node._ensure_broker_connected.assert_not_awaited()

    def test_normal_preview_marker_and_literal_values_only_after_source_resolution(self):
        for action in (t.DRAFT_ACTION_OFF, t.DRAFT_ACTION_PREVIEW):
            node = Node(); graph = Graph(node); graph.mediated()
            values = base.params(action)
            values.update(prompt='한국어 {{SIGN}} {% raw %} 🙂', resolution='480p', seed=0, generate_audio=False)
            original = deepcopy(values)
            with graph.context():
                resolved = node._resolve_exact_shot_generation_inputs(values)
                wire = node._build_broker_payload(resolved)
            self.assertEqual(wire['project_id'], 'katuri8')
            self.assertEqual(wire['project_selection_schema'], t.PROJECT_SELECTION_SCHEMA)
            self.assertEqual(wire['prompt'], original['prompt'])
            self.assertIs(wire['generate_audio'], False)
            self.assertEqual(resolved['seed'], 0)
            self.assertEqual(values, original)
            self.assertNotIn('_hmb_imageasset_project_selection', wire)
            self.assertNotIn('project_selection_schema', node._build_broker_payload(original))

    def test_bridge_keeps_marker_and_rejects_bad_or_final_marker(self):
        node = Node(); graph = Graph(node); graph.direct()
        with graph.context():
            payload = node._build_broker_payload(node._resolve_exact_shot_generation_inputs(base.params()))
        payload['client_request_id'] = 'hmb-project-fixture'
        bridge = t._HMBAIBrokerBridge(server_url=base.ORIGIN)
        bridge.queue_admission = mock.Mock(return_value=None)  # Native body-only seam; no HTTP fixture.
        with mock.patch.object(bridge, '_request_json', return_value={'job_id': base.JOB}) as request:
            bridge.generate_seedance(payload, timeout=1)
            self.assertEqual(request.call_args.kwargs['payload']['project_selection_schema'], t.PROJECT_SELECTION_SCHEMA)
        for bad in ('', True, {}, 'old-v0'):
            with self.subTest(bad=bad), self.assertRaises(t._BrokerProtocolError):
                bridge.generate_seedance({**payload, 'project_selection_schema': bad}, timeout=1)
        final = node._build_broker_payload({**base.params(t.DRAFT_ACTION_FINAL), 'resolution': '1080p'})
        self.assertNotIn('project_selection_schema', final)
        with self.assertRaises(t._BrokerProtocolError):
            bridge.generate_seedance({**final, 'client_request_id': 'hmb-final-fixture', 'project_selection_schema': t.PROJECT_SELECTION_SCHEMA}, timeout=1)

    def test_claimed_web_body_omits_new_marker_and_keeps_parent_project(self):
        owner = Node(); view = t._HMBWebRerenderExecution.read_view(owner)
        values = base.params()
        values['_hmb_imageasset_project_selection'] = {'schema': t.PROJECT_SELECTION_SCHEMA, 'project': {'project_id': 'katuri8'}}
        wire = view._build_broker_payload(values)
        self.assertEqual(wire['project_id'], base.PROJECT['project_id'])
        self.assertNotIn('project_selection_schema', wire)

    def test_draft_output_builder_seeds_index_and_preserves_explicit_provider(self):
        node = Node()
        destination = object()
        build = mock.Mock(return_value=destination)
        node._output_file = SimpleNamespace(build_file=build)
        self.assertIs(node._build_generation_output_destination(draft=True), destination)
        build.assert_called_once_with(_index=1)
        build.reset_mock()
        self.assertIs(node._build_generation_output_destination(), destination)
        build.assert_called_once_with()
        node._output_file = SimpleNamespace(build_file=lambda: destination)
        self.assertIs(node._build_generation_output_destination(draft=True), destination)

    @unittest.skipIf(t.ProjectFileParameter.__name__ == 'StubProjectFileParameter', 'Actual SDK macro test runs on the installed host.')
    def test_actual_sdk_default_draft_macro_and_explicit_destination(self):
        native = t.HMBSeedanceGeneration(name='Draft Macro SDK Fixture')
        # Actual ProjectFileParameter/ProjectFileDestination/MacroPath; no file
        # is written and no template/global project setting is edited.
        with mock.patch.object(native._output_file, '_get_upstream_destination', return_value=None):
            unbound = native._output_file.build_file()
            with self.assertRaisesRegex(Exception, '_index'):
                unbound.resolve()
            destination = native._build_generation_output_destination(draft=True)
            self.assertEqual(destination._file._file_path.variables['_index'], 1)
            first = Path(destination.resolve())
            candidates = list(itertools.islice(native._output_destination_candidate_records(destination), 2))
            self.assertEqual(candidates[0], (first.with_suffix('.mp4'), 1))
            self.assertEqual(candidates[1][1], 2)
            self.assertNotEqual(candidates[0][0], candidates[1][0])
            temporary = tempfile.TemporaryDirectory()
            self.addCleanup(temporary.cleanup)
            explicit = Path(temporary.name) / 'authored.mov'
            native.parameter_values['output_file'] = str(explicit)
            self.assertEqual(Path(native._build_generation_output_destination(draft=True).resolve()), explicit)
        # Connected FileOutputSettings owns its destination/policy, regardless
        # of the optional index offered to the parameter component.
        with mock.patch.object(native._output_file, '_get_upstream_destination', return_value=destination):
            self.assertIs(native._build_generation_output_destination(draft=True), destination)

    def test_resolved_normal_and_preview_process_submit_once_with_selected_project(self):
        for action in (t.DRAFT_ACTION_OFF, t.DRAFT_ACTION_PREVIEW):
            node = Node(base.params(action)); graph = Graph(node); graph.mediated(project='katuri8')
            if action == t.DRAFT_ACTION_PREVIEW:
                node.values['resolution'] = '480p'
            with graph.context(), \
                 mock.patch.object(t, '_resolve_mp4_decode_verifier', return_value=SimpleNamespace(executable='fixture', backend='test')), \
                 mock.patch.object(t._review, 'capture_inputs', return_value={}):
                asyncio.run(node._process_generation_impl())
            self.assertEqual(len(node.bridge.posts), 1)
            self.assertEqual(node.bridge.posts[0]['project_id'], 'katuri8')
            self.assertEqual(node.bridge.posts[0]['project_selection_schema'], t.PROJECT_SELECTION_SCHEMA)


if __name__ == '__main__':
    unittest.main()
