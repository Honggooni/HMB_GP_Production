"""Original-file local preview transport; exact code, no SDK/server/model calls."""
from __future__ import annotations
import ast
from copy import deepcopy
import hashlib
import ipaddress
from pathlib import Path
import re
import socket
import sys
import tempfile
from types import ModuleType, SimpleNamespace
from typing import Any
import unittest
from unittest import mock
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
TREE = ast.parse((ROOT / 'HMBSeedanceGeneration.py').read_text(encoding='utf-8-sig'))
HOST = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == 'HMBSeedanceGeneration')
NAMESPACE = dict(Any=Any, Parameter=Any, re=re, ipaddress=ipaddress, urlparse=urlparse, Path=Path, deepcopy=deepcopy,
    _TASK_ID_PATTERN=re.compile(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,255}'),
    SEEDANCE_SHOT_WIDGET_PARAMETER='shot_widget')
for name in ('SEEDANCE_PREFLIGHT_PARAMETER', 'SEEDANCE_RECOVERY_PARAMETER',
             'BROKER_SERVER_URL_PARAMETER', 'SEEDANCE_REFRESH_COMMAND_PARAMETER'):
    NAMESPACE[name] = name
NAMESPACE['GENERATED_VIDEO_SOURCE_PARAMETER'] = 'saved_source'
NAMESPACE['_generated_video_source_value'] = lambda value: value if isinstance(value, dict) else {}
for node in TREE.body:
    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in {
        'GENERATION_PREVIEW_PHASES', 'GENERATION_PREVIEW_REFRESH_PHASES', 'GENERATION_PREVIEW_GUIDANCE',
        'GENERATION_PREVIEW_SCHEMA', 'GENERATION_PREVIEW_VERSION'} for t in node.targets):
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<exact-preview-constant>', 'exec'), NAMESPACE)
definitions = [node for node in TREE.body if isinstance(node, ast.FunctionDef)
    and node.name in {'_seedance_local_preview_value', '_seedance_generation_preview_value'}]
methods = [node for node in HOST.body if isinstance(node, ast.FunctionDef)
    and node.name in {'_local_original_generation_preview', '_generation_preview_for_widget',
                     '_sync_seedance_shot_widget', 'before_value_set',
                     '_restore_saved_generation_media_revision'}]
definitions.append(ast.ClassDef(name='PreviewHost', bases=[], keywords=[], decorator_list=[], body=methods))
exec(compile(ast.fix_missing_locations(ast.Module(body=definitions, type_ignores=[])), '<exact-original-preview-code>', 'exec'), NAMESPACE)
normalize_pair = NAMESPACE['_seedance_local_preview_value']
normalize_generation = NAMESPACE['_seedance_generation_preview_value']


class LocalDriver:
    def __init__(self, workspace, *, base_url='http://127.0.0.1:8124/workspace'):
        # The real LocalStorageDriver compares a resolved workspace when
        # minting read URLs. Canonicalize this fake as well: a CI TEMP short
        # path or another alias must not incorrectly mint an external URL.
        self.workspace_directory, self.base_url = Path(workspace).resolve(), base_url
        self.calls, self.override = [], None

    def create_signed_download_url(self, path):
        self.calls.append(path)
        if isinstance(self.override, BaseException):
            raise self.override
        if self.override is not None:
            return self.override
        try:
            suffix = path.relative_to(self.workspace_directory).as_posix()
            return self.base_url + '/' + suffix + '?v=unchanged-file'
        except ValueError:
            suffix = str(path).replace('\\', '/').removeprefix('/')
            return self.base_url.rsplit('/workspace', 1)[0] + '/external/' + suffix + '?v=unchanged-file'


class FileDouble:
    calls = []
    path = None
    failure = None

    def __init__(self, source):
        self.calls.append(source)

    def resolve(self):
        if self.failure:
            raise self.failure
        return SimpleNamespace(location=str(self.path))


class Node(NAMESPACE['PreviewHost']):
    def __init__(self, driver, source, *, output=True):
        artifact = SimpleNamespace(value=source, name='original.mov', id='retained-original-id', meta={})
        self.parameter_output_values = dict(video_url=artifact, VIDEO_OUT=artifact,
            generation_id='job-retained', generation_status='succeeded') if output else {}
        self._hmb_last_success_video = artifact
        self.engine = SimpleNamespace(static_files_manager=SimpleNamespace(storage_driver=driver))
        self._hmb_generation_preview_state = normalize_generation({'phase': 'succeeded', 'job_id': 'job-retained', 'media_revision': 7})
        self._hmb_shot_catalog_snapshot = None
        self.parameter = SimpleNamespace(default_value={})
        self.values = {'resolution': '480p', 'draft_action': 'Draft 480p', 'prompt': 'retained literal'}
        self.published = []
        self._hmb_shot_syncing = False

    def get_parameter_by_name(self, name):
        return self.parameter if name == 'shot_widget' else None

    def get_parameter_value(self, name):
        return self.values.get(name)

    def _shot_identity(self):
        return {'channel_uuid': 'same-channel', 'shot_uuid': 'same-shot'}

    def _hmb_available_seedance_shot_catalog(self, value):
        return value

    def _draft_ui_state(self):
        return {}

    def _set_shot_value(self, name, value, **kwargs):
        self.values[name] = deepcopy(value)

    def publish_update_to_parameter(self, name, value):
        self.published.append((name, deepcopy(value)))


class LocalOriginalPreviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='hmb-original-preview-contract-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.workspace = self.root / 'workspace'
        self.workspace.mkdir()
        self.path = self.workspace / '원본 space.mov'
        self.path.write_bytes(b'synthetic-original-movie-bytes')
        self.driver = LocalDriver(self.workspace)
        FileDouble.calls, FileDouble.path, FileDouble.failure = [], self.path, None
        NAMESPACE['File'] = FileDouble
        NAMESPACE['_seedance_widget_value'] = lambda shot, catalog, generation, route, draft=None: {'generation': normalize_generation(generation)}
        driver_module = ModuleType('griptape_nodes.drivers.storage.local_storage_driver')
        driver_module.LocalStorageDriver = LocalDriver
        path_module = ModuleType('griptape_nodes.files.path_utils')
        path_module.strip_windows_long_path_prefix = lambda value: str(value)
        path_module.canonicalize_to_posix = lambda value: str(value).replace('\\', '/')
        self.modules = mock.patch.dict(sys.modules, {
            driver_module.__name__: driver_module, path_module.__name__: path_module})
        self.modules.start()
        self.addCleanup(self.modules.stop)
        self.net = mock.patch.object(socket, 'create_connection', side_effect=AssertionError('No network permitted'))
        self.net.start()
        self.addCleanup(self.net.stop)

    def identity(self):
        stat = self.path.stat()
        return (hashlib.sha256(self.path.read_bytes()).hexdigest(), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)

    def test_optional_key_is_absent_on_legacy_or_invalid_generation(self):
        original = normalize_generation()
        self.assertNotIn('local_preview', original)
        self.assertEqual(normalize_generation({'local_preview': {'source': 'x', 'url': 'https://remote.invalid/x'}}), original)

    def test_literal_local_source_and_loopback_url_survive_normalization(self):
        pair = {'source': 'C:/원본 space.mov', 'url': 'http://localhost:8124/workspace/원본 space.mov?v=exact'}
        self.assertEqual(normalize_pair(pair), pair)
        self.assertEqual(normalize_generation({'local_preview': pair})['local_preview'], pair)
        self.assertEqual(normalize_pair({**pair, 'url': 'http://[::1]:8124/external/C:/원본.mov'}).get('source'), pair['source'])

    def test_unsafe_url_and_remote_source_inputs_are_rejected(self):
        bad_urls = ['https://example.invalid/workspace/x.mov', 'http://127.0.0.1.evil.invalid/workspace/x.mov',
            'http://user:password@127.0.0.1:8124/workspace/x.mov', 'http://127.0.0.1:8124/workspace/x.mov#fragment',
            'javascript:alert(1)', '/workspace/x.mov', 'http://127.0.0.1:bad/workspace/x.mov',
            'http://127.0.0.1:8124/admin/shutdown', 'http://0.0.0.0:8124/workspace/x.mov',
            'http://127.0.0.1:8124/workspace\\x.mov', 'http://127.0.0.1:8124/workspace/x\n.mov']
        for url in bad_urls:
            with self.subTest(url=url):
                self.assertEqual(normalize_pair({'source': 'C:/x.mov', 'url': url}), {})
        for source in ('https://example.invalid/x.mov', 'file:///C:/x.mov', 'asset://x', 'data:video/mp4;base64,AA', 'x\x00.mov'):
            with self.subTest(source=source):
                self.assertEqual(normalize_pair({'source': source, 'url': 'http://127.0.0.1:8124/workspace/x.mov'}), {})
                self.assertEqual(Node(self.driver, source)._local_original_generation_preview(), {})
        self.assertEqual(FileDouble.calls, [])
        self.assertEqual(self.driver.calls, [])

    def test_pair_requires_exact_keys_bounded_strings(self):
        valid = {'source': 'C:/x.mov', 'url': 'http://127.0.0.1:8124/workspace/x.mov'}
        for pair in (None, [], {}, {**valid, 'task_id': 'browser-task'}, {**valid, 'source': 'x' * 4097},
                     {**valid, 'url': 'x' * 8193}, {**valid, 'source': 123}, {**valid, 'source': ' '}):
            with self.subTest(pair_type=type(pair).__name__):
                self.assertEqual(normalize_pair(pair), {})

    def test_original_internal_movie_only_mints_read_url_and_preserves_artifact_task_settings(self):
        source = str(self.path)
        node = Node(self.driver, source)
        artifact = node.parameter_output_values['video_url']
        before, outputs, settings = self.identity(), dict(node.parameter_output_values), deepcopy(node.values)
        result = node._local_original_generation_preview()
        self.assertEqual(result['source'], source)
        self.assertTrue(result['url'].startswith('http://127.0.0.1:8124/workspace/'))
        self.assertEqual(FileDouble.calls, [source])
        self.assertEqual(self.driver.calls, [self.path.resolve()])
        self.assertEqual(node.parameter_output_values, outputs)
        self.assertIs(node.parameter_output_values['video_url'], artifact)
        self.assertIs(node.parameter_output_values['VIDEO_OUT'], artifact)
        self.assertEqual(node.values, settings)
        self.assertEqual(self.identity(), before)

    def test_external_original_uses_same_driver_read_only_external_route(self):
        external = self.root / 'external.mov'
        external.write_bytes(b'external-original')
        FileDouble.path = external
        result = Node(self.driver, str(external))._local_original_generation_preview()
        self.assertEqual(result['source'], str(external))
        self.assertIn('/external/', result['url'])
        self.assertEqual(external.read_bytes(), b'external-original')

    def test_workspace_alias_mints_the_same_internal_read_route(self):
        alias = self.workspace / '..' / 'workspace'
        self.assertNotEqual(str(alias), str(self.workspace.resolve()))
        driver = LocalDriver(alias)
        source = str(self.path)
        before = self.identity()
        result = Node(driver, source)._local_original_generation_preview()
        self.assertEqual(driver.workspace_directory, self.workspace.resolve())
        self.assertEqual(result['source'], source)
        self.assertEqual(result['url'], self.driver.create_signed_download_url(self.path.resolve()))
        self.assertTrue(result['url'].startswith('http://127.0.0.1:8124/workspace/'))
        self.assertEqual(driver.calls, [self.path.resolve()])
        self.assertEqual(self.identity(), before)

    def test_driver_mismatch_origin_resource_or_fragment_fails_closed(self):
        node = Node(self.driver, str(self.path))
        for url in ('http://127.0.0.1:8124/workspace/other.mov?v=1',
                    'http://localhost:9999/workspace/other.mov',
                    'http://127.0.0.1:8124/workspace/원본 space.mov#fragment',
                    'https://remote.invalid/workspace/원본 space.mov'):
            self.driver.override = url
            with self.subTest(url=url):
                self.assertEqual(node._local_original_generation_preview(), {})

    def test_nonlocal_or_unavailable_driver_does_not_resolve_or_contact_media(self):
        node = Node(SimpleNamespace(create_signed_download_url=mock.Mock()), str(self.path))
        self.assertEqual(node._local_original_generation_preview(), {})
        self.assertEqual(FileDouble.calls, [])
        node.engine.static_files_manager.storage_driver.create_signed_download_url.assert_not_called()
        node.engine = None
        self.assertEqual(node._local_original_generation_preview(), {})

    def test_deleted_missing_or_resolution_failure_is_optional(self):
        node = Node(self.driver, str(self.path))
        node._hmb_node_deleted = True
        self.assertEqual(node._local_original_generation_preview(), {})
        self.assertEqual(FileDouble.calls, [])
        node._hmb_node_deleted = False
        FileDouble.path = self.root / 'missing.mov'
        self.assertEqual(node._local_original_generation_preview(), {})
        self.assertEqual(self.driver.calls, [])
        FileDouble.failure = OSError('fixture inaccessible')
        self.assertEqual(node._local_original_generation_preview(), {})

    def test_mint_failure_does_not_change_success_or_original_outputs(self):
        node = Node(self.driver, str(self.path))
        before = dict(node.parameter_output_values)
        self.driver.override = RuntimeError('fixture local storage unavailable')
        self.assertEqual(node._local_original_generation_preview(), {})
        self.assertEqual(node.parameter_output_values, before)

    def test_delete_or_artifact_replacement_during_mint_rejects_stale_pair(self):
        for kind in ('deleted', 'replaced'):
            with self.subTest(kind=kind):
                node = Node(self.driver, str(self.path))
                mint = self.driver.create_signed_download_url
                def changed(path):
                    result = mint(path)
                    if kind == 'deleted':
                        node._hmb_node_deleted = True
                    else:
                        node.parameter_output_values['video_url'] = SimpleNamespace(value=str(self.path))
                    return result
                with mock.patch.object(self.driver, 'create_signed_download_url', side_effect=changed):
                    self.assertEqual(node._local_original_generation_preview(), {})

    def test_sync_restored_workflow_and_repeated_sync_recompute_without_artifact_mutation(self):
        node = Node(self.driver, str(self.path))
        node._hmb_generation_preview_state = normalize_generation()  # reopened runtime can start idle
        original = node.parameter_output_values['video_url']
        node._sync_seedance_shot_widget(emit_change=True)
        self.assertEqual(node.values['shot_widget']['generation']['local_preview']['source'], original.value)
        count = len(node.published)
        node._sync_seedance_shot_widget(emit_change=True)
        self.assertEqual(len(self.driver.calls), 2)
        self.assertEqual(len(node.published), count)
        self.assertIs(node.parameter_output_values['video_url'], original)
        self.assertIs(node.parameter_output_values['VIDEO_OUT'], original)
        self.assertNotIn('local_preview', node._hmb_generation_preview_state)

    def test_running_preview_keeps_last_success_and_stale_pair_is_removed_on_clear(self):
        node = Node(self.driver, str(self.path), output=False)
        node._hmb_generation_preview_state = normalize_generation({'phase': 'running', 'job_id': 'job-new'})
        node._sync_seedance_shot_widget(emit_change=True)
        self.assertIn('local_preview', node.values['shot_widget']['generation'])
        self.assertEqual(node.parameter_output_values, {})
        node._hmb_generation_preview_state['local_preview'] = node.values['shot_widget']['generation']['local_preview']
        node._hmb_last_success_video = None
        node._sync_seedance_shot_widget(emit_change=True)
        self.assertNotIn('local_preview', node.values['shot_widget']['generation'])

    def test_sdk_setter_normalization_retains_trusted_preview_and_rejects_browser_pair(self):
        node = Node(self.driver, str(self.path))
        original = node.parameter_output_values['video_url']
        parameter = SimpleNamespace(name='shot_widget')
        browser = {'shot': None, 'generation': {'phase': 'failed', 'job_id': 'job-browser',
            'local_preview': {'source': 'C:/forged.mov', 'url': 'http://127.0.0.1:8124/workspace/forged.mov'}}}
        normalized = node.before_value_set(parameter, browser)
        self.assertEqual(normalized['generation']['local_preview']['source'], original.value)
        self.assertEqual(normalized['generation']['phase'], 'succeeded')
        self.assertEqual(normalized['generation']['job_id'], 'job-retained')
        node._set_shot_value = lambda name, value, **kwargs: node.values.__setitem__(
            name, node.before_value_set(parameter, value))
        node._sync_seedance_shot_widget(emit_change=True)
        self.assertEqual(node.values['shot_widget'], node.published[-1][1])
        self.assertIs(node.parameter_output_values['video_url'], original)
        self.assertNotIn('local_preview', node._hmb_generation_preview_state)

    def test_restore_counter_uses_matching_saved_source_and_never_widget_revision(self):
        node = Node(self.driver, str(self.path))
        node.values['saved_source'] = {'task_id': 'job-retained', 'path': str(self.path), 'result_revision': 3}
        node.values['shot_widget'] = {'generation': {'media_revision': 99999}}
        node._hmb_generation_media_revision = 0
        node._restore_saved_generation_media_revision('job-retained', node.parameter_output_values['video_url'])
        self.assertEqual(node._hmb_generation_media_revision, 3)
        self.assertIsNone(node._hmb_generation_recovery_restore_fingerprint)
        node._hmb_generation_media_revision = 8
        node._hmb_generation_recovery_restore_fingerprint = 'same-ready-state'
        node._restore_saved_generation_media_revision('job-retained', node.parameter_output_values['video_url'])
        self.assertEqual(node._hmb_generation_media_revision, 8)
        self.assertEqual(node._hmb_generation_recovery_restore_fingerprint, 'same-ready-state')

    def test_restore_counter_rejects_foreign_task_source_missing_file_or_deleted_node(self):
        for kind in ('source_task', 'output_task', 'foreign_path', 'missing_path', 'deleted', 'no_source', 'remote', 'resolve_failure'):
            with self.subTest(kind=kind):
                node = Node(self.driver, str(self.path))
                node.values['saved_source'] = {'task_id': 'job-retained', 'path': str(self.path), 'result_revision': 3}
                node._hmb_generation_media_revision = 0
                if kind == 'source_task': node.values['saved_source']['task_id'] = 'job-foreign'
                if kind == 'output_task': node.parameter_output_values['generation_id'] = 'job-foreign'
                if kind == 'foreign_path': node.values['saved_source']['path'] = str(self.root / 'foreign.mov')
                if kind == 'missing_path': FileDouble.path = self.root / 'missing.mov'
                if kind == 'deleted': node._hmb_node_deleted = True
                if kind == 'no_source': node.values['saved_source'] = {}
                if kind == 'remote': node.parameter_output_values['video_url'].value = 'https://invalid.example/movie.mov'
                if kind == 'resolve_failure': FileDouble.failure = RuntimeError('fixture unavailable macro')
                node._restore_saved_generation_media_revision('job-retained', node.parameter_output_values['video_url'])
                self.assertEqual(node._hmb_generation_media_revision, 0)
                FileDouble.path = self.path
                FileDouble.failure = None


if __name__ == '__main__':
    unittest.main(verbosity=2)
