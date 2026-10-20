"""Native player uses local read URLs; generated outputs remain original files.

Exact Python helpers with synthetic media only; no SDK conversion, render,
server request, user workflow save or original media mutation is permitted.
"""
from __future__ import annotations
import ast
from copy import deepcopy
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

TESTS = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('native_preview_original_fixture',
    TESTS / 'HMB_Seedance_Local_Original_Preview_Regression.py')
assert SPEC and SPEC.loader
fixture = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fixture)
NAMESPACE = fixture.NAMESPACE
NAMES = {'_native_local_video_preview_artifact', '_refresh_native_local_video_preview',
         '_capture_last_success_video', '_set_safe_defaults', '_generation_artifact_is_present'}
METHODS = [node for node in fixture.HOST.body if isinstance(node, ast.FunctionDef) and node.name in NAMES]
TREE = ast.fix_missing_locations(ast.Module(body=[ast.ClassDef(name='NativeProjection',
    bases=[], keywords=[], decorator_list=[], body=METHODS)], type_ignores=[]))

class Artifact:
    next_id = 0
    def __init__(self, value, *, name, meta=None):
        type(self).next_id += 1
        self.value, self.name, self.meta = value, name, deepcopy(meta or {})
        self.id = f'native-artifact-{type(self).next_id}'
NAMESPACE.update(VideoUrlArtifact=Artifact, ImageUrlArtifact=Artifact)
exec(compile(TREE, '<exact-native-original-preview>', 'exec'), NAMESPACE)

class Node(fixture.Node, NAMESPACE['NativeProjection']):
    def __init__(self, driver, source):
        super().__init__(driver, source)
        self._hmb_last_success_last_frame_url = None

class NativeProjectionTests(fixture.LocalOriginalPreviewTests):
    def make_node(self):
        return Node(self.driver, str(self.path))

    def test_native_property_only_is_projected_original_task_and_settings_unchanged(self):
        node = self.make_node()
        original, settings, file_identity = node.parameter_output_values['VIDEO_OUT'], deepcopy(node.values), self.identity()
        original.meta = {'source': 'retained-source'}
        node._refresh_native_local_video_preview()
        native = node.parameter_output_values['video_url']
        self.assertIsNot(native, original)
        self.assertTrue(native.value.startswith('http://127.0.0.1:8124/workspace/'))
        self.assertEqual(native.name, original.name)
        self.assertEqual(native.meta, original.meta)
        self.assertIs(node.parameter_output_values['VIDEO_OUT'], original)
        self.assertIs(node._hmb_last_success_video, original)
        self.assertEqual(node.parameter_output_values['generation_id'], 'job-retained')
        self.assertEqual(node.values, settings)
        self.assertEqual(self.identity(), file_identity)

    def test_five_nodes_remain_independent_and_progress_does_not_recreate_artifact(self):
        nodes = [self.make_node() for _ in range(5)]
        for index, node in enumerate(nodes):
            node.parameter_output_values['generation_id'] = f'job-slot-{index + 1}'
            node._refresh_native_local_video_preview()
        natives = [node.parameter_output_values['video_url'] for node in nodes]
        self.assertEqual(len({item.id for item in natives}), 5)
        for _ in range(20):
            for index, node in enumerate(nodes):
                node._refresh_native_local_video_preview()
                self.assertIs(node.parameter_output_values['video_url'], natives[index])
                self.assertEqual(node.parameter_output_values['generation_id'], f'job-slot-{index + 1}')

    def test_rerender_safe_defaults_preserves_original_and_native_id_at_480p(self):
        node = self.make_node()
        original = node.parameter_output_values['VIDEO_OUT']
        node._refresh_native_local_video_preview()
        native = node.parameter_output_values['video_url']
        for _ in range(5):
            node._set_safe_defaults()
            self.assertIs(node.parameter_output_values['video_url'], native)
            self.assertIs(node.parameter_output_values['VIDEO_OUT'], original)
            self.assertIs(node._hmb_last_success_video, original)
            self.assertEqual(node.values['resolution'], '480p')
            self.assertEqual(node.values['draft_action'], 'Draft 480p')

    def test_saved_native_url_and_original_hydration_retains_artifact_id(self):
        node = self.make_node()
        node._refresh_native_local_video_preview()
        original, native = node.parameter_output_values['VIDEO_OUT'], node.parameter_output_values['video_url']
        reopened = self.make_node()
        reopened.parameter_output_values.update(VIDEO_OUT=deepcopy(original), video_url=deepcopy(native))
        expected = reopened.parameter_output_values['video_url']
        reopened._refresh_native_local_video_preview()
        self.assertIs(reopened.parameter_output_values['video_url'], expected)
        self.assertEqual(expected.id, native.id)
        self.assertEqual(reopened.parameter_output_values['VIDEO_OUT'].value, str(self.path))

    def test_changed_local_server_remints_native_url_without_touching_original(self):
        node = self.make_node()
        node._refresh_native_local_video_preview()
        original, native = node.parameter_output_values['VIDEO_OUT'], node.parameter_output_values['video_url']
        self.driver.base_url = 'http://127.0.0.1:9912/workspace'
        node._refresh_native_local_video_preview()
        self.assertIsNot(node.parameter_output_values['video_url'], native)
        self.assertTrue(node.parameter_output_values['video_url'].value.startswith(self.driver.base_url))
        self.assertIs(node.parameter_output_values['VIDEO_OUT'], original)

    def test_untrusted_driver_or_missing_file_keeps_original_success(self):
        for bad in ('driver', 'missing', 'remote_route', 'delete'):
            node = self.make_node()
            original = node.parameter_output_values['VIDEO_OUT']
            if bad == 'driver': node.engine.static_files_manager.storage_driver = object()
            if bad == 'missing': fixture.FileDouble.path = self.root / 'does-not-exist.mov'
            if bad == 'remote_route': self.driver.override = 'https://server.invalid/media.mov'
            if bad == 'delete': node._hmb_node_deleted = True
            node._refresh_native_local_video_preview()
            self.assertIs(node.parameter_output_values['video_url'], original, bad)
            self.assertIs(node.parameter_output_values['VIDEO_OUT'], original, bad)
            self.assertEqual(node.parameter_output_values['generation_status'], 'succeeded')
            fixture.FileDouble.path, self.driver.override = self.path, None

    def test_canonical_alias_wins_over_a_saved_http_preview(self):
        node = self.make_node()
        original = node.parameter_output_values['VIDEO_OUT']
        node.parameter_output_values['video_url'] = Artifact(value='https://server.invalid/unrelated.mov', name=original.name)
        self.assertEqual(node._local_original_generation_preview()['source'], str(self.path))
        node._refresh_native_local_video_preview()
        self.assertTrue(node.parameter_output_values['video_url'].value.startswith('http://127.0.0.1:'))
        self.assertIs(node._capture_last_success_video(), original)

    def test_current_source_replacement_during_projection_cannot_bind_old_url(self):
        node = self.make_node()
        original = node.parameter_output_values['VIDEO_OUT']
        replacement = SimpleNamespace(value=str(self.path), name='replacement.mov')
        mint = self.driver.create_signed_download_url
        def changed(path):
            result = mint(path)
            node.parameter_output_values['VIDEO_OUT'] = replacement
            return result
        with mock.patch.object(self.driver, 'create_signed_download_url', side_effect=changed):
            self.assertIs(node._native_local_video_preview_artifact(original), original)
        self.assertIs(node.parameter_output_values['VIDEO_OUT'], replacement)

    def test_original_file_replaced_during_mint_rejects_projection(self):
        node = self.make_node()
        original = node.parameter_output_values['VIDEO_OUT']
        mint = self.driver.create_signed_download_url
        def changed(path):
            result = mint(path)
            path.write_bytes(b'fixture replacement different length')
            return result
        with mock.patch.object(self.driver, 'create_signed_download_url', side_effect=changed):
            self.assertIs(node._native_local_video_preview_artifact(original), original)
        self.assertIs(node.parameter_output_values['video_url'], original)
        self.assertIs(node.parameter_output_values['VIDEO_OUT'], original)

    def test_hydration_and_publication_use_projection_and_output_connector_remains_original(self):
        methods = {node.name: node for node in fixture.HOST.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for name in ('_set_safe_defaults', '_save_completed_task', '_reuse_saved_generation_result'):
            code = ast.unparse(methods[name])
            self.assertIn('self._native_local_video_preview_artifact(', code, name)
        self.assertIn('_refresh_native_local_video_preview', ast.unparse(methods['_restore_generation_recovery_preview']))
        web = ast.unparse(methods['_hmb_execute_web_rerender']) if '_hmb_execute_web_rerender' in methods else ''
        if web: self.assertIn("get('VIDEO_OUT')", web)
        constructor = ast.unparse(methods['__init__'])
        native = next(call for call in ast.walk(methods['__init__']) if isinstance(call, ast.Call)
            and getattr(call.func, 'id', None) == 'ParameterVideo'
            and any(kw.arg == 'name' and isinstance(kw.value, ast.Constant) and kw.value.value == 'video_url' for kw in call.keywords))
        self.assertIs(next(kw.value.value for kw in native.keywords if kw.arg == 'pulse_on_run'), False)

if __name__ == '__main__':
    unittest.main(verbosity=2)
