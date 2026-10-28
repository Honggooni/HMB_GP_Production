"""Offline only: native task start, durable claims, no CGT or provider transport."""
from copy import deepcopy
import importlib.util
import json
import os
import stat
import subprocess
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import _hmb_cgt as cgt

spec = importlib.util.spec_from_file_location("cgt_start_fixture", Path(__file__).with_name("HMB_CGT_Own_Task_Regression.py"))
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


class NativeStartTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="hmb-cgt-start-offline-")
        self.root = Path(self.tmp.name)
        self.sdk = self.root / "sdk"
        self.sdk.mkdir()
        (self.sdk / "cgtw2.py").write_text("# fixture", encoding="utf-8")
        self.original = deepcopy(fixture.tasks)
        self.binding = deepcopy(fixture.binding)
        self.member = self.binding["members"][0]
        self.task = next(row for row in fixture.tasks if row["task_id"] == self.member["cgt_task_id"])
        self.task["status"] = "Wait"
        self.previous = {"members": deepcopy(self.binding["members"][1:])}
        fixture.session = fixture.Session()
        fixture.calls.clear()
        self.writes = []
        self.write_effect = "success"
        sdk = types.SimpleNamespace(tw=fixture.Tw, G_tw_http_ip='192.168.200.18:8383', G_cgtw_session=fixture.session)
        self.sdk_stub = sdk
        modules = {'cgtw2': sdk, 'websocket': types.SimpleNamespace(setdefaulttimeout=lambda value: None),
                   'requests.adapters': types.SimpleNamespace(HTTPAdapter=fixture.Adapter)}
        self.context = mock.patch.dict(sys.modules, modules)
        self.context.start()
        self.environment = mock.patch.dict(os.environ, {"HMB_CGT_SDK_PATH": str(self.sdk), "LOCALAPPDATA": str(self.root)})
        self.environment.start()

        def update(db, module, ids, status, note="", image_list=None, retake_pipeline_id_list=None):
            self.writes.append((db, module, deepcopy(ids), status, note, image_list, retake_pipeline_id_list))
            fixture.session.post('https://192.168.200.18:8383/api.php', data={'data': json.dumps({
                'controller': 'task', 'method': 'update_task_status', 'db': db, 'module': module,
                'task_id_array': ids, 'status': status, 'dom_array': [], 'retake_pipeline_id_array': []})})
            if self.write_effect == "timeout-before":
                raise TimeoutError("private provider body")
            self.task['status'] = status
            if self.write_effect == "timeout-after":
                raise TimeoutError("private provider body")
            return True
        self.update = mock.patch.object(fixture.Tw.task, 'update_task_status', side_effect=update, create=True)
        self.update.start()

    def tearDown(self):
        self.update.stop()
        self.environment.stop()
        self.context.stop()
        fixture.tasks[:] = self.original
        self.tmp.cleanup()

    def run_start(self, commit="commit-one", *, include_bound_wait=False):
        # The real wrapper uses a new child and a fresh vendor session per call.
        fixture.session = fixture.Session()
        self.sdk_stub.G_cgtw_session = fixture.session
        return cgt._native_start_own_wait(dict(project_id='superwings12', previous_binding=self.previous,
            committed_binding=self.binding, commit_request_id=commit, cgt_project_id=fixture.project_id,
            include_bound_wait=include_bound_wait))

    def test_wait_once_then_work_and_existing_bindings_skip(self):
        result = self.run_start()
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['updated_count'], 1)
        self.assertEqual(result['skipped_count'], 4)
        self.assertFalse(result['atomic_compare_and_set'])
        self.assertEqual(len(self.writes), 1)
        self.assertEqual(self.writes[0][1:], ('shot', [self.task['task_id']], 'Work', '', [], []))
        self.assertEqual(result['observed_tasks'][0]['status'], 'Work')
        files = list((self.root / 'HMB_GP_Production/cgt-work-start-receipts').glob('*.json'))
        self.assertEqual(len(files), 1)
        text = files[0].read_text('ascii')
        self.assertNotIn(self.task['task_id'], text)
        self.assertNotIn(fixture.account, text)
        self.task['status'] = 'Wait'  # another client reverted the status
        retry = self.run_start('new-commit')
        self.assertEqual(retry['status'], 'unknown')
        self.assertEqual(retry['tasks'][0]['outcome'], 'prior_write_unconfirmed')
        self.assertEqual(len(self.writes), 1)

    def test_timeout_claim_blocks_new_commit_even_when_task_still_wait(self):
        self.write_effect = 'timeout-before'
        first = self.run_start()
        self.assertEqual(first['status'], 'unknown')
        self.assertEqual(first['tasks'][0]['outcome'], 'write_unconfirmed')
        self.assertEqual(self.run_start('another-commit')['tasks'][0]['outcome'], 'prior_write_unconfirmed')
        self.assertEqual(len(self.writes), 1)

    def test_claim_save_failure_prevents_cgt_write(self):
        with mock.patch.object(cgt.os, 'fsync', side_effect=OSError('private disk error')):
            result = self.run_start()
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['tasks'][0]['outcome'], 'receipt_unavailable')
        self.assertEqual(self.writes, [])
        self.assertEqual(self.run_start('after-fsync-failure')['tasks'][0]['outcome'], 'prior_write_unconfirmed')

    def test_changed_identity_or_owner_blocks_any_write(self):
        self.member['artist'] = 'Different artist'
        with self.assertRaises(ValueError):
            self.run_start()
        self.assertEqual(self.writes, [])

    def test_timeout_after_accept_is_unknown_but_next_read_sees_work(self):
        self.write_effect = 'timeout-after'
        self.assertEqual(self.run_start()['tasks'][0]['outcome'], 'write_unconfirmed')
        self.assertEqual(self.run_start('later')['tasks'][0]['outcome'], 'already_work')
        self.assertEqual(len(self.writes), 1)

    def test_receipt_directory_reparse_point_prevents_write(self):
        target = self.root / 'HMB_GP_Production' / 'cgt-work-start-receipts'
        target.mkdir(parents=True)
        original_lstat = Path.lstat
        def reparse(path, *args, **kwargs):
            if path == target:
                return types.SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
            return original_lstat(path, *args, **kwargs)
        with mock.patch.object(Path, 'lstat', reparse):
            result = self.run_start()
        self.assertEqual(result['tasks'][0]['outcome'], 'receipt_unavailable')
        self.assertEqual(self.writes, [])

    def test_wait_work_other_and_existing_are_distinct(self):
        self.previous = {'members': []}
        second = next(row for row in fixture.tasks if row['task_id'] == self.binding['members'][1]['cgt_task_id'])
        third = next(row for row in fixture.tasks if row['task_id'] == self.binding['members'][2]['cgt_task_id'])
        second['status'], third['status'] = 'Work', 'Approve'
        result = self.run_start()
        self.assertEqual(result['updated_count'], 1)
        self.assertEqual(result['already_work_count'], 3)
        self.assertEqual(result['skipped_count'], 1)
        self.assertEqual(len(self.writes), 1)

    def test_explicit_reconfirm_includes_existing_wait_without_changing_binding(self):
        self.previous = deepcopy(self.binding)
        before = deepcopy(self.binding)
        default = self.run_start()
        self.assertEqual(default['updated_count'], 0)
        self.assertEqual(default['skipped_count'], 5)
        self.assertEqual(self.writes, [])
        result = self.run_start('explicit-reconfirm', include_bound_wait=True)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['updated_count'], 1)
        self.assertEqual(result['already_work_count'], 4)
        self.assertEqual(self.binding, before)
        self.assertEqual(len(self.writes), 1)
        self.task['status'] = 'Wait'
        retry = self.run_start('second-reconfirm', include_bound_wait=True)
        self.assertEqual(retry['tasks'][0]['outcome'], 'prior_write_unconfirmed')
        self.assertEqual(len(self.writes), 1)
        with self.assertRaises(ValueError):
            self.run_start('bad-flag', include_bound_wait='true')
        self.assertEqual(len(self.writes), 1)

    def test_scope_guard_blocks_wrong_task_before_transport(self):
        def wrong_update(db, module, ids, status, **_kwargs):
            return fixture.session.post('https://192.168.200.18:8383/api.php', data={'data': json.dumps({
                'controller':'task', 'method':'update_task_status', 'db':db, 'module':module,
                'task_id_array':[fixture.tasks[1]['task_id']], 'status':status, 'dom_array':[],
                'retake_pipeline_id_array':[]})})
        with mock.patch.object(fixture.Tw.task, 'update_task_status', side_effect=wrong_update):
            result = self.run_start()
        self.assertEqual(result['tasks'][0]['outcome'], 'write_unconfirmed')
        self.assertFalse(any(row.get('method') == 'update_task_status' for row in fixture.calls))

    def test_vendor_retry_cannot_post_same_task_twice(self):
        def retrying_update(db, module, ids, status, **_kwargs):
            data = {'data':json.dumps({'controller':'task', 'method':'update_task_status',
                'db':db, 'module':module, 'task_id_array':ids, 'status':status,
                'dom_array':[], 'retake_pipeline_id_array':[]})}
            fixture.session.post('https://192.168.200.18:8383/api.php', data=data)
            return fixture.session.post('https://192.168.200.18:8383/api.php', data=data)
        with mock.patch.object(fixture.Tw.task, 'update_task_status', side_effect=retrying_update):
            result = self.run_start()
        self.assertEqual(result['tasks'][0]['outcome'], 'write_unconfirmed')
        self.assertEqual(sum(row.get('method') == 'update_task_status' for row in fixture.calls), 1)
        self.assertEqual(self.run_start('later')['tasks'][0]['outcome'], 'prior_write_unconfirmed')

    def test_claim_survives_independent_child_processes(self):
        snapshot = {'origin':'https://fixture.invalid', 'account_id':fixture.account,
                    'project':{'id':fixture.project_id}}
        payload = json.dumps({'snapshot':snapshot, 'member':self.member}).encode('utf-8')
        command = [sys.executable, '-B', '-c',
            'import json,sys,_hmb_cgt as c; d=json.load(sys.stdin); '
            'print(c._claim_native_work_start(d["snapshot"],d["member"],"commit"))']
        first = subprocess.run(command, input=payload, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               cwd=str(ROOT), env=os.environ.copy(), check=True)
        second = subprocess.run(command, input=payload, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                cwd=str(ROOT), env=os.environ.copy(), check=True)
        self.assertEqual(first.stdout.strip(), b'True')
        self.assertEqual(second.stdout.strip(), b'False')
        self.assertEqual(self.writes, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
