"""Shared migration: exact audit/CAS, targeted rollback, isolated preparation."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('hmb_tos_install_fixture', HERE/'HMB_TOS_Installer_Isolation_Regression.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)


class AutomaticMigration(base.InstallerRepair):
    def namespace(self):
        namespace = {'__name__':'_exact_shared_auto_migration'}
        exec(base.REPAIR, namespace)
        return namespace

    def run_core(self, callback, *, runner=None):
        with mock.patch.object(sys,'version_info',(3,12,13)), mock.patch.object(base.metadata,'version',side_effect=lambda name:base.ENGINE[name]), mock.patch.object(subprocess,'run',side_effect=runner or self.fake_uv):
            return callback(self.namespace())

    def request(self, operation='audit', **values):
        return {'version':1,'operation':operation,'library_root':str(self.root),**values}

    def test_audit_is_read_only_and_returns_exact_owned_paths_and_fingerprint(self):
        self.legacy()
        before = {str(path):path.read_bytes() for path in self.root.rglob('*') if path.is_file()}
        result = self.run_core(lambda api:api['_repair_request'](self.request()))
        self.assertEqual(result['status'],'needed')
        self.assertTrue(result['needs_tos_runtime'])
        self.assertEqual(len(result['inspected_fingerprint']),64)
        self.assertEqual(len(result['removal_paths']),9)
        self.assertEqual(self.calls,[])
        self.assertEqual(before,{str(path):path.read_bytes() for path in self.root.rglob('*') if path.is_file()})

    def test_auto_commit_verifies_full_backup_and_preserves_unrelated_files(self):
        self.legacy();self.package('custom','1.0')
        def run(api):
            before=api['_inventory'](self.root,self.root/'.venv')
            audit=api['_repair_request'](self.request())
            report=api['_repair_request'](self.request('repair',expected_fingerprint=audit['inspected_fingerprint']))
            self.assertEqual(api['_inventory'](self.root,Path(report['backup_path'])),before)
            return report
        report=self.run_core(run)
        self.assertEqual(report['status'],'repaired')
        self.assertTrue((self.root/'.hmb-tos-runtime-needed.json').is_file())
        self.assertEqual([item.metadata['Name'] for item in base.metadata.distributions(path=[str(self.site)])],['custom'])
        self.assertFalse((self.root/'.hmb-tos-migration.lock').exists())

    def test_stale_audit_cannot_enter_uninstall(self):
        self.legacy()
        def run(api):
            audit=api['_repair_request'](self.request())
            self.package('new-custom','1.0')
            with self.assertRaisesRegex(RuntimeError,'changed after inspection'):
                api['_repair_request'](self.request('repair',expected_fingerprint=audit['inspected_fingerprint']))
        self.run_core(run)
        self.assertEqual(self.calls,[])

    def test_auto_partial_uninstall_failure_restores_original_files_and_times(self):
        self.legacy();self.package('custom','1.0')
        def fail(args,**kwargs):
            self.fake_uv(args,**kwargs)
            return SimpleNamespace(returncode=1,stdout='',stderr='fixture failure')
        def run(api):
            before=api['_inventory'](self.root,self.root/'.venv')
            audit=api['_repair_request'](self.request())
            report=api['_repair_request'](self.request('repair',expected_fingerprint=audit['inspected_fingerprint']))
            self.assertEqual(api['_inventory'](self.root,self.root/'.venv'),before)
            return report
        report=self.run_core(run,runner=fail)
        self.assertFalse(report['ok'])
        self.assertEqual(report['status'],'rolled_back')
        self.assertTrue(report['rollback_verified'])

    def test_rollback_never_overwrites_concurrent_changed_original_file(self):
        self.legacy();self.package('custom','1.0')
        target=self.site/'custom_fixture.py'
        def fail(args,**kwargs):
            self.fake_uv(args,**kwargs)
            target.write_bytes(b'concurrent writer: preserve me')
            return SimpleNamespace(returncode=1,stdout='',stderr='fixture failure')
        def run(api):
            audit=api['_repair_request'](self.request())
            return api['_repair_request'](self.request('repair',expected_fingerprint=audit['inspected_fingerprint']))
        report=self.run_core(run,runner=fail)
        self.assertEqual(report['status'],'integrity_unknown')
        self.assertFalse(report['rollback_verified'])
        self.assertEqual(target.read_bytes(),b'concurrent writer: preserve me')

    def test_concurrent_repair_lock_is_busy_and_never_uninstalls(self):
        self.legacy();lock=self.root/'.hmb-tos-migration.lock';lock.write_text('another owner')
        result=self.run_core(lambda api:api['_repair_request'](self.request('repair',expected_fingerprint='ignored')))
        self.assertEqual(result['status'],'busy')
        self.assertEqual(self.calls,[])
        self.assertEqual(lock.read_text(),'another owner')

    def test_manifest_compare_and_swap_precedes_package_operations(self):
        self.legacy()
        with self.assertRaisesRegex(RuntimeError,'manifest changed'):
            self.run_core(lambda api:api['_repair_request'](self.request(expected_manifest_sha256='0'*64)))
        self.assertEqual(self.calls,[])

    def test_unknown_legacy_versions_are_preserved_by_automatic_path(self):
        self.package('wrapt','2.5.0')
        result=self.run_core(lambda api:api['_repair_request'](self.request()))
        self.assertFalse(result['ok'])
        self.assertEqual(result['status'],'refused')
        self.assertEqual(result['reason'],'unrecognized_legacy_version')
        self.assertTrue((self.site/'wrapt_fixture.py').exists())
        self.assertEqual(self.calls,[])

    def test_clean_automatic_path_does_not_inventory_or_copy_whole_environment(self):
        for name,version in base.ENGINE.items():self.package(name,version)
        def run(api):
            api['_inventory']=mock.Mock(side_effect=AssertionError('No whole environment walk on a clean state'))
            audit=api['_repair_request'](self.request())
            result=api['_repair_request'](self.request('repair',expected_fingerprint=audit['inspected_fingerprint']))
            self.assertEqual(result['status'],'clean')
        self.run_core(run)
        self.assertEqual(self.calls,[])

    def test_only_record_source_corresponding_normal_bytecode_is_owned(self):
        self.package('tos','2.9.2')
        cache=self.site/'__pycache__';cache.mkdir()
        owned=cache/('tos_fixture.'+sys.implementation.cache_tag+'.opt-1.pyc');owned.write_bytes(b'owned cache')
        foreign=cache/('not_recorded.'+sys.implementation.cache_tag+'.pyc');foreign.write_bytes(b'preserve me')
        result=self.run_core(lambda api:api['_repair_request'](self.request()))
        self.assertIn(str(owned),result['removal_paths'])
        self.assertNotIn(str(foreign),result['removal_paths'])
        self.assertEqual(self.calls,[])

    def test_unlock_failure_cannot_replace_verified_rollback_status(self):
        self.legacy()
        def fail(args,**kwargs):
            self.fake_uv(args,**kwargs)
            return SimpleNamespace(returncode=1,stdout='',stderr='fixture failure')
        original_unlink=Path.unlink
        def unlink(path,*args,**kwargs):
            if path.name=='.hmb-tos-migration.lock':raise PermissionError('fixture lock cleanup failure')
            return original_unlink(path,*args,**kwargs)
        def run(api):
            audit=api['_repair_request'](self.request())
            with mock.patch.object(Path,'unlink',new=unlink):
                return api['_repair_request'](self.request('repair',expected_fingerprint=audit['inspected_fingerprint']))
        result=self.run_core(run,runner=fail)
        self.assertEqual(result['status'],'rolled_back')
        self.assertTrue(result['rollback_verified'])

    def test_successful_uninstaller_cannot_leave_orphan_recorded_code(self):
        self.legacy()
        target=self.site/'wrapt_fixture.py'
        original_unlink=Path.unlink
        def leave_code(path,*args,**kwargs):
            if path==target:return None
            return original_unlink(path,*args,**kwargs)
        def orphan(args,**kwargs):
            with mock.patch.object(Path,'unlink',new=leave_code):
                return self.fake_uv(args,**kwargs)
        def run(api):
            audit=api['_repair_request'](self.request())
            return api['_repair_request'](self.request('repair',expected_fingerprint=audit['inspected_fingerprint']))
        result=self.run_core(run,runner=orphan)
        self.assertFalse(result['ok'])
        self.assertEqual(result['status'],'rolled_back')
        self.assertTrue(result['rollback_verified'])
        self.assertTrue((self.site/'wrapt-1.16.0.dist-info/METADATA').is_file())

    def _new_uv_lock_case(self,failed):
        self.legacy()
        def uninstall(args,**kwargs):
            self.fake_uv(args,**kwargs)
            (self.root/'.venv/.lock').write_bytes(b'')
            return SimpleNamespace(returncode=1 if failed else 0,stdout='',stderr='')
        def run(api):
            before=api['_inventory'](self.root,self.root/'.venv')
            audit=api['_repair_request'](self.request())
            result=api['_repair_request'](self.request('repair',expected_fingerprint=audit['inspected_fingerprint']))
            if failed:self.assertEqual(api['_inventory'](self.root,self.root/'.venv'),before)
            return result
        result=self.run_core(run,runner=uninstall)
        self.assertEqual(result['status'],'rolled_back' if failed else 'repaired')
        if failed:self.assertTrue(result['rollback_verified'])
        else:self.assertEqual(result['generated_housekeeping_paths'],[str(self.root/'.venv/.lock')])

    def test_new_uv_empty_lock_is_reported_as_exact_housekeeping(self):
        self._new_uv_lock_case(False)

    def test_rollback_removes_only_unchanged_unused_new_uv_lock(self):
        self._new_uv_lock_case(True)

    def test_uv_lock_CAS_preserves_changed_file_and_an_active_windows_owner(self):
        def run(api):
            path=self.root/'.venv/.lock';path.write_bytes(b'')
            identity=api['_empty_uv_lock_identity'](self.root,path)
            path.write_bytes(b'changed: preserve')
            self.assertFalse(api['_remove_owned_empty_uv_lock'](self.root,path,identity))
            self.assertEqual(path.read_bytes(),b'changed: preserve')
            path.unlink();path.write_bytes(b'')
            identity=api['_empty_uv_lock_identity'](self.root,path)
            import os
            if os.name=='nt':
                with path.open('rb'):
                    self.assertFalse(api['_remove_owned_empty_uv_lock'](self.root,path,identity))
                self.assertTrue(path.exists())
            self.assertTrue(api['_remove_owned_empty_uv_lock'](self.root,path,identity))
            self.assertFalse(path.exists())
        self.run_core(run)

    def test_interrupted_or_unverified_transaction_cannot_be_reported_clean(self):
        for phase in ('backed-up','integrity_unknown','unrecognized'):
            with self.subTest(phase=phase):
                directory=self.root/'.hmb-environment-backups'/phase
                directory.mkdir(parents=True)
                (directory/'transaction.json').write_text(json.dumps({'version':1,'phase':phase}))
                result=self.run_core(lambda api:api['_repair_request'](self.request()))
                self.assertFalse(result['ok'])
                self.assertEqual(result['status'],'integrity_unknown')
                self.assertFalse(result['rollback_verified'])
                self.assertEqual(self.calls,[])
                (directory/'transaction.json').unlink();directory.rmdir()

    def test_verified_completed_or_rolled_back_journals_allow_normal_noop(self):
        for phase in ('committed','rolled_back','aborted'):
            directory=self.root/'.hmb-environment-backups'/phase
            directory.mkdir(parents=True)
            (directory/'transaction.json').write_text(json.dumps({'version':1,'phase':phase}))
        result=self.run_core(lambda api:api['_repair_request'](self.request()))
        self.assertTrue(result['ok'])
        self.assertEqual(result['status'],'clean')
        self.assertEqual(self.calls,[])

    def test_retained_shared_RECORD_member_is_rejected(self):
        self.package('tos','2.9.2');custom=self.package('custom','1.0')
        with (custom/'RECORD').open('a') as stream:stream.write('tos_fixture.py,,\n')
        with self.assertRaisesRegex(RuntimeError,'also owned'):
            self.run_core(lambda api:api['_repair_request'](self.request()))
        self.assertEqual(self.calls,[])

    def test_preparation_uses_staging_probe_then_atomic_publish_and_ready_no_pip(self):
        # Exercise the real preparation coordinator. Only uv and the child SDK
        # probe are offline fixtures; no subprocess/network can be contacted.
        source="_TOS_HELPER_SOURCE = 'fixed dummy child'\n"
        (self.root/'HMBSeedanceGeneration.py').write_text(source)
        calls=[]
        def run(args,**kwargs):
            calls.append(args)
            if 'venv' in args:
                directory=Path(args[-1]);(directory/'Scripts').mkdir(parents=True)
                (directory/'Scripts/python.exe').write_bytes(b'fixture only')
                (directory/'pyvenv.cfg').write_text('include-system-site-packages = false\n')
                return SimpleNamespace(returncode=0,stdout='',stderr='')
            if 'pip' in args:
                return SimpleNamespace(returncode=0,stdout='',stderr='')
            request=json.loads(kwargs['input'])
            return SimpleNamespace(returncode=0,stdout=json.dumps({'version':1,'ok':True,'runtime_root':request['runtime_root'],'tos_version':'2.9.2','wrapt_version':'1.16.0','isolated':True}),stderr='')
        first=self.run_core(lambda api:api['_repair_request'](self.request('prepare')),runner=run)
        self.assertEqual(first['status'],'prepared')
        self.assertTrue((self.root/'.venv-tos/Scripts/python.exe').is_file())
        self.assertTrue((self.root/'.hmb-tos-runtime-ready.json').is_file())
        self.assertEqual(len([call for call in calls if 'pip' in call]),1)
        calls.clear()
        second=self.run_core(lambda api:api['_repair_request'](self.request('prepare')),runner=run)
        self.assertTrue(second['prepared'])
        self.assertEqual(len(calls),1)
        self.assertNotIn('pip',calls[0])

    def test_incomplete_existing_TOS_runtime_is_preserved_without_pip(self):
        (self.root/'.venv-tos').mkdir()
        (self.root/'HMBSeedanceGeneration.py').write_text("_TOS_HELPER_SOURCE = 'fixed dummy child'\n")
        with self.assertRaisesRegex(RuntimeError,'incomplete'):
            self.run_core(lambda api:api['_repair_request'](self.request('prepare')))
        self.assertEqual(self.calls,[])
        self.assertTrue((self.root/'.venv-tos').is_dir())

    def test_background_prepare_never_publishes_after_manifest_or_source_changes(self):
        for changed in ('griptape-nodes-library.json','HMBSeedanceGeneration.py'):
            with self.subTest(changed=changed):
                (self.root/'griptape-nodes-library.json').write_text('{"name":"HMB_GP_Production","revision":1}')
                (self.root/'HMBSeedanceGeneration.py').write_text("_TOS_HELPER_SOURCE = 'fixed dummy child'\n")
                def run(args,**kwargs):
                    if 'venv' in args:
                        directory=Path(args[-1]);(directory/'Scripts').mkdir(parents=True)
                        (directory/'Scripts/python.exe').write_bytes(b'fixture only')
                        (directory/'pyvenv.cfg').write_text('include-system-site-packages = false\n')
                    elif 'pip' in args:
                        path=self.root/changed
                        path.write_text(path.read_text()+'\n' if changed.endswith('.py') else '{"name":"HMB_GP_Production","revision":2}')
                    else:
                        request=json.loads(kwargs['input'])
                        return SimpleNamespace(returncode=0,stdout=json.dumps({'version':1,'ok':True,'runtime_root':request['runtime_root'],'tos_version':'2.9.2','wrapt_version':'1.16.0','isolated':True}),stderr='')
                    return SimpleNamespace(returncode=0,stdout='',stderr='')
                with self.assertRaisesRegex(RuntimeError,'owner changed'):
                    self.run_core(lambda api:api['_repair_request'](self.request('prepare')),runner=run)
                self.assertFalse((self.root/'.venv-tos').exists())
                self.assertFalse((self.root/'.hmb-tos-runtime-ready.json').exists())
                self.assertTrue(list(self.root.glob('.venv-tos-stage-*')))


if __name__=='__main__':
    unittest.main(verbosity=2)
