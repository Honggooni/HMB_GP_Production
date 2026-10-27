"""Guarded Override coordinator contracts without touching an installed runtime."""
from __future__ import annotations
import ast
from copy import deepcopy
import hashlib
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
import weakref
from unittest import mock
from uuid import UUID

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / '_hmb_library_bootstrap.py'
TREE = ast.parse(SOURCE.read_text('utf-8'))
NAMES = {'_HMB_ENV_STATE_MODULE','_HMB_ENV_RESPONSE_LIMIT','_HMB_ENV_NODE_FILES','_HMB_TOS_ENVIRONMENT_REPAIR_SOURCE'}
NODES = [node for node in TREE.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and
         (node.name.startswith('_hmb_environment_') or node.name == '_hmb_coordinate_environment_repair') or
         isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id in NAMES for target in node.targets)]
PROGRAM = compile(ast.Module(body=NODES, type_ignores=[]), str(SOURCE), 'exec')

class Coordinator(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='hmb-coordinator-')
        self.addCleanup(self.tmp.cleanup)
        # The coordinator canonicalizes owned paths before its module guard.
        self.root = Path(self.tmp.name).resolve()
        self.file = self.root / '_hmb_library_bootstrap.py'
        self.file.write_text('# exact fixture owner\n', encoding='utf-8')
        self.manifest = self.root / 'griptape-nodes-library.json'
        self.manifest.write_text(json.dumps({'name':'HMB_GP_Production','advanced_library_path':self.file.name}), encoding='utf-8')
        self.site = self.root / '.venv' / ('Lib/site-packages' if os.name=='nt' else 'lib/python3.12/site-packages')
        self.site.mkdir(parents=True)
        self.member = self.site / 'wrapt/__init__.py'
        self.member.parent.mkdir()
        self.member.write_text('raise AssertionError("must not import")\n', encoding='utf-8')
        self.ns = dict(Path=Path, Any=object, sys=sys, os=os, hashlib=hashlib, json=json, threading=threading,
            logging=logging, types=types, subprocess=subprocess, __file__=str(self.file), __name__='offline_coordinator', _LIBRARY_NAME='HMB_GP_Production')
        exec(PROGRAM, self.ns)
        self.ns['_HMB_ENV_STATE_MODULE'] += '_' + self.root.name.replace('-', '_')
        self.addCleanup(lambda: sys.modules.pop(self.ns['_HMB_ENV_STATE_MODULE'], None))
        manager = types.SimpleNamespace(is_worker=False, get_library_info_by_library_name=lambda name: types.SimpleNamespace(library_path=str(self.manifest)))
        self.ns['current_engine'] = lambda: types.SimpleNamespace(library_manager=manager)
        self.calls = []
        self.audit = dict(version=1, ok=True,status='clean',inspected_fingerprint='a'*64,removal_paths=[],needs_tos_runtime=False)
        self.repair = dict(version=1,ok=True,status='repaired',removed_versions={'wrapt':'1.16.0'})
        def child(python, source, request, *, timeout):
            self.calls.append(dict(request, timeout=timeout, site_quarantined=str(self.site) not in sys.path))
            return deepcopy(self.repair if request['operation']=='repair' else self.audit)
        self.ns['_hmb_environment_child'] = child
        self.ns['_hmb_environment_loaded'] = lambda root, paths=None: ''
        self.ns['_hmb_environment_mapped_dlls'] = lambda paths: False
        self.paths = list(sys.path)
        self.addCleanup(lambda: sys.path.__setitem__(slice(None),self.paths))
        sys.path.insert(0,str(self.site))
        self.before = self.member.read_bytes()
    def run_coordinator(self):
        return self.ns['_hmb_coordinate_environment_repair']()
    def needed(self):
        self.audit.update(status='needed',removal_paths=[str(self.member)])
    def test_registered_owner_required(self):
        self.ns['current_engine'] = lambda: types.SimpleNamespace(library_manager=types.SimpleNamespace(is_worker=False,get_library_info_by_library_name=lambda name:None))
        self.assertEqual(self.run_coordinator()['status'],'unavailable')
        self.assertEqual(self.calls,[])
        self.assertEqual(self.member.read_bytes(),self.before)
    def test_clean_refresh_cache_and_unrelated_path_preserved(self):
        child = self.ns['_hmb_environment_child']
        def append(*args,**kwargs):
            result=child(*args,**kwargs)
            sys.path.append('concurrent-unrelated-library')
            return result
        self.ns['_hmb_environment_child']=append
        self.assertEqual(self.run_coordinator()['status'],'clean')
        self.ns['_hmb_environment_loaded']=lambda *args:'HMB loaded normally'
        self.assertTrue(self.run_coordinator()['cached'])
        self.assertEqual(len(self.calls),1)
        self.assertTrue(self.calls[0]['site_quarantined'])
        self.assertIn(str(self.site),sys.path)
        self.assertIn('concurrent-unrelated-library',sys.path)
    def test_changed_dependency_invalidates_cached_clean_without_mutating_loaded(self):
        self.run_coordinator()
        self.member.write_text('changed by explicit external update\n',encoding='utf-8')
        self.needed()
        self.ns['_hmb_environment_loaded']=lambda *args:'already loaded'
        self.assertEqual(self.run_coordinator()['reason'],'loaded_dependency')
        self.assertEqual([r['operation'] for r in self.calls],['audit','audit'])
    def test_changed_code_loaded_defers_without_audit(self):
        self.run_coordinator()
        self.file.write_text('# updated Override code\n',encoding='utf-8')
        self.ns['_hmb_environment_loaded']=lambda *args:'already loaded'
        result=self.run_coordinator()
        self.assertEqual(result['reason'],'loaded_hmb_code')
        self.assertEqual(len(self.calls),1)
    def test_repair_once_then_verified_clean_refresh(self):
        self.needed()
        original=self.ns['_hmb_environment_child']
        def child(*args,**kwargs):
            result=original(*args,**kwargs)
            if args[2]['operation']=='repair':
                self.audit.update(status='clean',removal_paths=[])
            return result
        self.ns['_hmb_environment_child']=child
        self.assertEqual(self.run_coordinator()['removed_distributions'],['wrapt'])
        self.ns['_hmb_environment_loaded']=lambda *args:'HMB loaded'
        self.assertTrue(self.run_coordinator()['cached'])
        self.assertEqual([r['operation'] for r in self.calls],['audit','repair','audit'])
        self.assertEqual(self.calls[1]['expected_fingerprint'],'a'*64)
    def test_exact_legacy_reexposure_cannot_reuse_success_or_repeat_cleanup(self):
        self.needed()
        original=self.ns['_hmb_environment_child']
        def child(*args,**kwargs):
            result=original(*args,**kwargs)
            if args[2]['operation']=='repair':self.audit.update(status='clean',removal_paths=[])
            return result
        self.ns['_hmb_environment_child']=child
        self.assertEqual(self.run_coordinator()['status'],'repaired')
        self.needed()
        self.member.write_text('legacy exact audit fingerprint reexposed\n',encoding='utf-8')
        self.ns['_hmb_environment_loaded']=lambda *args:'HMB loaded'
        for _ in range(2):
            self.assertEqual(self.run_coordinator()['reason'],'reexposed_environment')
        self.assertEqual([r['operation'] for r in self.calls].count('repair'),1)
    def test_loaded_dependency_file_and_spec_guard(self):
        real=self.ns['_hmb_environment_loaded']
        exec(compile(ast.Module([next(n for n in NODES if isinstance(n,ast.FunctionDef) and n.name=='_hmb_environment_loaded')],[]),str(SOURCE),'exec'),self.ns)
        module=types.ModuleType('hmb_affected_fixture')
        module.__spec__=types.SimpleNamespace(origin=str(self.member))
        with mock.patch.dict(sys.modules,{'hmb_affected_fixture':module}):
            self.assertIn('affected',self.ns['_hmb_environment_loaded'](self.root,[self.member]))
            module.__file__=str(self.member)
            self.assertIn('affected',self.ns['_hmb_environment_loaded'](self.root,[self.member]))
        self.ns['_hmb_environment_loaded']=real
    def test_mapped_dll_or_unverified_query_preserves_dependency(self):
        self.needed()
        for value in (True,RuntimeError('unverified')):
            def mapped(paths):
                if isinstance(value,Exception):raise value
                return value
            self.ns['_hmb_environment_mapped_dlls']=mapped
            self.ns['_hmb_environment_state']().attempts.clear()
            self.assertEqual(self.run_coordinator()['reason'],'loaded_dependency')
        self.assertTrue(all(r['operation']=='audit' for r in self.calls))
        self.assertEqual(self.member.read_bytes(),self.before)
    def test_verified_rollback_is_pending_and_never_retried(self):
        self.needed()
        self.repair=dict(version=1,ok=False,status='rolled_back',rollback_verified=True)
        for _ in range(2):self.assertEqual(self.run_coordinator()['reason'],'verified_rollback')
        self.assertEqual([r['operation'] for r in self.calls].count('repair'),1)
        self.assertEqual(self.member.read_bytes(),self.before)
    def test_unverified_integrity_fails_closed_and_restores_path(self):
        for stage in ('audit','repair'):
            self.calls.clear()
            self.audit.update(status='clean',ok=True)
            self.ns['_hmb_environment_state']().attempts.clear()
            if stage=='audit':self.audit.update(status='integrity_unknown',ok=False)
            else:
                self.needed()
                self.repair=dict(version=1,ok=False,status='rolled_back',rollback_verified=False)
            with self.assertRaisesRegex(RuntimeError,'recovery'):
                self.run_coordinator()
            self.assertIn(str(self.site),sys.path)
    def test_removal_path_cannot_escape_venv(self):
        self.needed()
        self.audit['removal_paths']=[str(self.file)]
        with self.assertRaisesRegex(RuntimeError,'escaped'):self.run_coordinator()
        self.assertEqual(len(self.calls),1)
        self.assertEqual(self.member.read_bytes(),self.before)
    def test_optional_prepare_failure_stays_local_and_single_attempt(self):
        self.audit['needs_tos_runtime']=True
        original=self.ns['_hmb_environment_child']
        done=threading.Event()
        def child(*args,**kwargs):
            if args[2]['operation']=='prepare':
                done.set()
                raise RuntimeError('offline optional setup')
            return original(*args,**kwargs)
        self.ns['_hmb_environment_child']=child
        self.assertEqual(self.run_coordinator()['status'],'clean')
        self.assertTrue(done.wait(2))
        state=self.ns['_hmb_environment_state']()
        for thread in threading.enumerate():
            if thread.name=='HMB isolated TOS preparation':thread.join(2)
        self.assertEqual([job['status'] for job in state.jobs.values()],['pending'])
        self.assertTrue(self.run_coordinator()['cached'])
        self.assertEqual(self.member.read_bytes(),self.before)
    def test_actual_private_child_protocol_and_job(self):
        # Source is fixed fixture code; no SDK, uv, network or filesystem writes.
        node=next(n for n in NODES if isinstance(n,ast.FunctionDef) and n.name=='_hmb_environment_child')
        exec(compile(ast.Module([node],[]),str(SOURCE),'exec'),self.ns)
        source='import json,sys,os; r=json.load(sys.stdin); print(json.dumps(dict(version=1,ok=True,status="clean",isolated=sys.flags.isolated,bytecode=sys.dont_write_bytecode,secret="HMB_FAKE_TOKEN" in os.environ)))'
        with mock.patch.dict(os.environ,{'HMB_FAKE_TOKEN':'fixture-only'}):
            result=self.ns['_hmb_environment_child'](Path(sys.executable),source,{'version':1},timeout=5)
        self.assertEqual(result['isolated'],1)
        self.assertTrue(result['bytecode'])
        self.assertFalse(result['secret'])
        with self.assertRaises(subprocess.TimeoutExpired):
            self.ns['_hmb_environment_child'](Path(sys.executable),'import time; time.sleep(30)',{},timeout=.1)
    def test_actual_mapped_dll_query_and_descendant_timeout_cleanup(self):
        if sys.platform!='win32':
            node=next(n for n in NODES if isinstance(n,ast.FunctionDef) and n.name=='_hmb_environment_mapped_dlls')
            exec(compile(ast.Module([node],[]),str(SOURCE),'exec'),self.ns)
            self.assertFalse(self.ns['_hmb_environment_mapped_dlls']([self.site/'fixture.dll']))
            return
        import ctypes
        from ctypes import wintypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        filename=kernel.GetModuleFileNameW
        filename.argtypes,filename.restype=[wintypes.HMODULE,wintypes.LPWSTR,wintypes.DWORD],wintypes.DWORD
        name=ctypes.create_unicode_buffer(32768)
        self.assertTrue(filename(kernel._handle,name,len(name)))
        node=next(n for n in NODES if isinstance(n,ast.FunctionDef) and n.name=='_hmb_environment_mapped_dlls')
        exec(compile(ast.Module([node],[]),str(SOURCE),'exec'),self.ns)
        self.assertTrue(self.ns['_hmb_environment_mapped_dlls']([Path(name.value)]))
        node=next(n for n in NODES if isinstance(n,ast.FunctionDef) and n.name=='_hmb_environment_child')
        exec(compile(ast.Module([node],[]),str(SOURCE),'exec'),self.ns)
        pidfile=self.root/'owned-child.pid'
        program='import subprocess,sys,time; p=subprocess.Popen([sys.executable,"-I","-B","-c","import time; time.sleep(30)"]); open('+repr(str(pidfile))+',"w").write(str(p.pid)); time.sleep(30)'
        with self.assertRaises(subprocess.TimeoutExpired):
            self.ns['_hmb_environment_child'](Path(sys.executable),program,{},timeout=.5)
        self.assertTrue(pidfile.is_file())
        pid=int(pidfile.read_text())
        open_process=kernel.OpenProcess
        open_process.argtypes,open_process.restype=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD],wintypes.HANDLE
        handle=open_process(0x100000,False,pid)
        if handle:
            wait=kernel.WaitForSingleObject
            wait.argtypes,wait.restype=[wintypes.HANDLE,wintypes.DWORD],wintypes.DWORD
            self.assertEqual(wait(handle,2000),0,'Only the helper-owned descendant must be stopped on timeout')
            close=kernel.CloseHandle;close.argtypes=[wintypes.HANDLE];close(handle)

class NativeEditorCoordinator(unittest.TestCase):
    """Only disposable Documents-like fixtures; no actual app bundle target."""
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='hmb-native-coordinator-')
        self.addCleanup(self.tmp.cleanup)
        self.documents=Path(self.tmp.name).resolve()/'Documents'
        self.root=self.documents/'GriptapeNodes/libraries/HMB_GP_Production'
        (self.root/'tools').mkdir(parents=True)
        (self.root/'resources/editor').mkdir(parents=True)
        self.file=self.root/'_hmb_library_bootstrap.py';self.file.write_text('# private source fixture\n','utf-8')
        self.manifest=self.root/'griptape-nodes-library.json'
        self.manifest.write_text(json.dumps(dict(name='HMB_GP_Production',advanced_library_path=self.file.name)),'utf-8')
        self.patcher=self.root/'tools/hmb_color_lut_native_header_patch.py';self.patcher.write_text('# fixed private CLI\n','utf-8')
        self.helper=self.root/'resources/editor/hmb-color-lut-native-header.js';self.helper.write_text('// private helper\n','utf-8')
        self.descriptor=self.root/'resources/editor/native-editor-patch.json'
        self.descriptor_value=dict(schema='hmb-native-editor-patch-release',version=1,editor_version='0.128.1',
            bundle_name='index-DEZU41rc.js',helper_path='resources/editor/hmb-color-lut-native-header.js',
            patcher_path='tools/hmb_color_lut_native_header_patch.py',candidate_sha256='a'*64)
        self.update_descriptor()
        constants={'_HMB_NATIVE_EDITOR_STATE_MODULE','_HMB_NATIVE_EDITOR_RESPONSE_LIMIT','_HMB_NATIVE_EDITOR_TIMEOUT_SECONDS'}
        nodes=[n for n in TREE.body if isinstance(n,ast.FunctionDef) and
            (n.name.startswith('_hmb_native_editor_') or n.name=='_hmb_coordinate_native_editor_update') or
            isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in constants for t in n.targets)]
        self.ns=dict(Path=Path,Any=object,sys=sys,os=os,hashlib=hashlib,json=json,threading=threading,
            logging=logging,types=types,subprocess=subprocess,weakref=weakref,UUID=UUID,
            __file__=str(self.file),__name__='offline_native_coordinator',_LIBRARY_NAME='HMB_GP_Production')
        exec(compile(ast.Module(body=nodes,type_ignores=[]),str(SOURCE),'exec'),self.ns)
        self.ns['_HMB_NATIVE_EDITOR_STATE_MODULE']+='_'+self.root.parents[3].name.replace('-','_')
        self.addCleanup(lambda:sys.modules.pop(self.ns['_HMB_NATIVE_EDITOR_STATE_MODULE'],None))
        self.ns['_hmb_native_editor_documents_path']=lambda:self.documents
        self.ns['_hmb_environment_job']=lambda process:lambda:None
        class Owner:pass
        self.owner=Owner();self.engine=Owner()
        self.engine.library_manager=types.SimpleNamespace(is_worker=False,
            get_library_info_by_library_name=lambda name:types.SimpleNamespace(library_path=str(self.manifest)))
        self.data=types.SimpleNamespace(name='HMB_GP_Production')
        self.calls=[]
        self.response=self.reply('applied')
        def child(*args):
            self.calls.append(args)
            return deepcopy(self.response)
        self.ns['_hmb_native_editor_child']=child
        logging.disable(logging.CRITICAL)
        self.addCleanup(lambda:logging.disable(logging.NOTSET))
    def update_descriptor(self):
        for key,path in (('patcher',self.patcher),('helper',self.helper)):
            self.descriptor_value[key+'_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
        self.descriptor.write_text(json.dumps(self.descriptor_value),'utf-8')
    def reply(self,status):
        success=status in {'current','applied'}
        return dict(schema='hmb-native-editor-git-override',version=1,status=status,reason='private_fixture',
            disk_ready=success,restart_required=True,renderer_verified=False,
            candidate_sha256='a'*64,editor_version='0.128.1')
    def run_coordinator(self,owner=None):
        return self.ns['_hmb_coordinate_native_editor_update'](owner or self.owner,self.engine,self.data)
    def settled(self,owner=None):
        owner=owner or self.owner
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            value=getattr(owner,'_hmb_native_editor_update_summary',{})
            if value.get('reason')!='native_update_check_running':return value
            time.sleep(.005)
        self.fail('Private native coordinator did not settle')
    def test_developer_checkout_never_spawns_or_opens_installed_support_sources(self):
        self.ns['__file__']=str(SOURCE)
        with mock.patch.object(Path,'read_bytes',side_effect=AssertionError('Support file must not be opened')):
            self.assertEqual(self.run_coordinator()['reason'],'not_installed_library')
        self.assertEqual(self.calls,[])
    def test_registered_owner_worker_and_library_identity_required(self):
        self.engine.library_manager.is_worker=True
        self.assertEqual(self.run_coordinator()['status'],'unsupported')
        self.engine.library_manager.is_worker=False
        self.engine.library_manager.get_library_info_by_library_name=lambda name:types.SimpleNamespace(library_path=str(self.root/'foreign.json'))
        self.assertEqual(self.run_coordinator()['reason'],'registered_library_path_changed')
        self.data.name='Foreign'
        self.assertEqual(self.run_coordinator()['reason'],'not_hmb_library')
        self.assertEqual(self.calls,[])
    def test_all_support_sources_required_and_integrity_checked(self):
        for path in (self.patcher,self.helper,self.descriptor):
            before=path.read_bytes();path.unlink()
            try:self.assertEqual(self.run_coordinator()['status'],'error')
            finally:path.write_bytes(before)
        for key,value in (('patcher_path','../foreign.py'),('helper_sha256','b'*64),('version',True),('candidate_sha256','invalid')):
            before=deepcopy(self.descriptor_value);self.descriptor_value[key]=value
            self.descriptor.write_text(json.dumps(self.descriptor_value),'utf-8')
            self.assertEqual(self.run_coordinator()['status'],'error')
            self.descriptor_value=before;self.update_descriptor()
        self.assertEqual(self.calls,[])
    def test_async_single_invocation_cached_result_and_engine_publication(self):
        entered=threading.Event();release=threading.Event()
        def child(*args):
            self.calls.append(args);entered.set();self.assertTrue(release.wait(2));return self.reply('applied')
        self.ns['_hmb_native_editor_child']=child
        initial=self.run_coordinator();self.assertEqual(initial['status'],'pending')
        self.assertTrue(entered.wait(1));self.assertTrue(self.run_coordinator()['cached'])
        self.assertEqual(len(self.calls),1);release.set()
        final=self.settled();self.assertEqual(final['status'],'applied')
        self.assertFalse(final['renderer_verified']);self.assertTrue(final['restart_required'])
        self.assertEqual(self.engine._hmb_native_editor_update_summary,final)
        self.assertTrue(self.run_coordinator()['cached']);self.assertEqual(len(self.calls),1)
    def test_each_typed_child_status_is_retained_without_claiming_renderer_ready(self):
        for status in ('current','applied','pending','unsupported','error'):
            self.ns['_hmb_native_editor_state']().jobs.clear();self.response=self.reply(status)
            self.run_coordinator();value=self.settled()
            self.assertEqual(value['status'],status);self.assertFalse(value['renderer_verified'])
    def test_current_at_cold_start_does_not_warn_or_require_a_restart_loop(self):
        self.response=self.reply('current');done=threading.Event()
        logger=types.SimpleNamespace(info=mock.Mock(side_effect=lambda *a:done.set()),warning=mock.Mock())
        with mock.patch.object(logging,'getLogger',return_value=logger):
            self.run_coordinator();self.assertTrue(done.wait(2))
        logger.warning.assert_not_called();self.assertEqual(logger.info.call_count,1)
        self.assertEqual(self.settled()['status'],'current')
    def test_timeout_or_start_failure_is_explicit_and_not_repeated(self):
        def timeout(*args):raise subprocess.TimeoutExpired('fixed updater',20)
        self.ns['_hmb_native_editor_child']=timeout
        self.run_coordinator();self.assertEqual(self.settled()['reason'],'native_update_timeout')
        self.assertTrue(self.run_coordinator()['cached'])
        self.ns['_hmb_native_editor_state']().jobs.clear()
        with mock.patch.object(threading.Thread,'start',side_effect=RuntimeError('private launch unavailable')):
            self.assertIn('native_update_start_failed',self.run_coordinator()['reason'])
    def test_invalidated_support_clears_previous_engine_disk_ready(self):
        self.run_coordinator();self.assertTrue(self.settled()['disk_ready'])
        self.helper.write_text('explicitly changed private source','utf-8')
        self.assertEqual(self.run_coordinator()['status'],'error')
        self.assertFalse(self.engine._hmb_native_editor_update_summary['disk_ready'])
        self.assertEqual(len(self.calls),1)
    def test_late_old_generation_cannot_replace_new_engine_status(self):
        entered=threading.Event();release=threading.Event();old_owner=self.owner
        def child(*args):
            self.calls.append(args)
            if len(self.calls)==1:entered.set();self.assertTrue(release.wait(2));return self.reply('pending')
            return self.reply('applied')
        self.ns['_hmb_native_editor_child']=child
        self.run_coordinator();self.assertTrue(entered.wait(1))
        self.file.write_text('# new exact private generation\n','utf-8')
        self.owner=type(old_owner)();self.run_coordinator();self.assertEqual(self.settled()['status'],'applied')
        release.set();self.assertEqual(self.settled(old_owner)['status'],'pending')
        self.assertEqual(self.engine._hmb_native_editor_update_summary['status'],'applied')
        self.assertEqual(len(self.calls),2)
    def child_function(self):
        node=next(n for n in TREE.body if isinstance(n,ast.FunctionDef) and n.name=='_hmb_native_editor_child')
        exec(compile(ast.Module([node],[]),str(SOURCE),'exec'),self.ns)
        return self.ns['_hmb_native_editor_child']
    def test_cli_command_isolated_environment_and_bounded_json_contract(self):
        calls=[];response=self.reply('applied');test=self
        class Process:
            returncode=0
            def communicate(self,*,timeout):test.assertEqual(timeout,20);return json.dumps(response).encode(),None
            def poll(self):return 0
        def popen(command,**kwargs):calls.append((command,kwargs));return Process()
        child=self.child_function()
        with mock.patch.object(subprocess,'Popen',side_effect=popen),mock.patch.dict(os.environ,{'API_KEY':'private-secret','HMB_FAKE_TOKEN':'fixture-secret'}):
            self.assertEqual(child(self.root,Path(sys.executable),self.descriptor_value),response)
        command,kwargs=calls[0]
        self.assertEqual(command,[str(Path(sys.executable)),'-I','-B',str(self.patcher),'--apply-git-override'])
        self.assertNotIn('API_KEY',kwargs['env']);self.assertNotIn('HMB_FAKE_TOKEN',kwargs['env'])
        self.assertIs(kwargs['close_fds'],True);self.assertEqual(kwargs['cwd'],str(self.root))
    def test_malformed_or_false_ready_child_replies_are_errors(self):
        child=self.child_function();payload=self.reply('applied');code=0
        class Process:
            @property
            def returncode(self):return code
            def communicate(self,*,timeout):return json.dumps(payload).encode(),None
            def poll(self):return code
        with mock.patch.object(subprocess,'Popen',return_value=Process()):
            for key,value in (('schema','foreign'),('version',True),('renderer_verified',True),('disk_ready','true'),
                    ('candidate_sha256','b'*64),('restart_required',False),('status','unknown')):
                payload=self.reply('applied');payload[key]=value
                with self.assertRaises(ValueError):child(self.root,Path(sys.executable),self.descriptor_value)
            payload=self.reply('current');code=1
            with self.assertRaises(ValueError):child(self.root,Path(sys.executable),self.descriptor_value)
            code=0;payload=self.reply('pending');payload['disk_ready']=True
            with self.assertRaises(ValueError):child(self.root,Path(sys.executable),self.descriptor_value)
    def test_real_isolated_child_cli_uses_private_fixture_only(self):
        self.patcher.write_text('import json,os,sys\nprint(json.dumps(dict(schema="hmb-native-editor-git-override",version=1,status="current",reason="private_fixture",disk_ready=True,restart_required=True,renderer_verified=False,editor_version="0.128.1",candidate_sha256="a"*64,isolated=sys.flags.isolated,bytecode=sys.dont_write_bytecode,secret="HMB_FAKE_TOKEN" in os.environ)))\n','utf-8')
        child=self.child_function()
        with mock.patch.dict(os.environ,{'HMB_FAKE_TOKEN':'fixture-only'}):
            result=child(self.root,Path(sys.executable),self.descriptor_value)
        self.assertEqual(result['isolated'],1);self.assertTrue(result['bytecode']);self.assertFalse(result['secret'])
        self.assertEqual(self.calls,[])
    def test_pending_same_pin_is_once_per_process_and_retries_after_cold_process_start(self):
        program=r'''
import ast,hashlib,json,logging,os,sys,threading,time,types,weakref
from pathlib import Path
from uuid import UUID
source,folder,documents=map(Path,sys.argv[1:])
tree=ast.parse(source.read_text('utf-8'))
names={'_HMB_NATIVE_EDITOR_STATE_MODULE','_HMB_NATIVE_EDITOR_RESPONSE_LIMIT','_HMB_NATIVE_EDITOR_TIMEOUT_SECONDS'}
nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and (n.name.startswith('_hmb_native_editor_') or n.name=='_hmb_coordinate_native_editor_update') or isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in names for t in n.targets)]
scope=dict(Path=Path,Any=object,sys=sys,os=os,hashlib=hashlib,json=json,threading=threading,logging=logging,types=types,weakref=weakref,UUID=UUID,__file__=str(folder/'_hmb_library_bootstrap.py'),__name__='private_process_fixture',_LIBRARY_NAME='HMB_GP_Production')
exec(compile(ast.Module(body=nodes,type_ignores=[]),str(source),'exec'),scope)
scope['_hmb_native_editor_documents_path']=lambda:documents
calls=[]
def child(*args):
    calls.append(True)
    return scope['_hmb_native_editor_summary']('pending','private_fixture_lock',restart_required=True)
scope['_hmb_native_editor_child']=child
class Owner:pass
owner,engine=Owner(),Owner()
engine.library_manager=types.SimpleNamespace(is_worker=False,get_library_info_by_library_name=lambda name:types.SimpleNamespace(library_path=str(folder/'griptape-nodes-library.json')))
logging.disable(logging.CRITICAL)
scope['_hmb_coordinate_native_editor_update'](owner,engine,types.SimpleNamespace(name='HMB_GP_Production'))
end=time.monotonic()+3
while time.monotonic()<end and owner._hmb_native_editor_update_summary['reason']=='native_update_check_running':time.sleep(.005)
again=scope['_hmb_coordinate_native_editor_update'](owner,engine,types.SimpleNamespace(name='HMB_GP_Production'))
assert again['cached'] and len(calls)==1 and again['reason']=='private_fixture_lock'
identity=next(iter(scope['_hmb_native_editor_state']().jobs))
print(json.dumps(dict(calls=len(calls),identity=repr(identity),status=again['status'])))
'''
        records=[]
        for _ in range(2):
            completed=subprocess.run([sys.executable,'-I','-B','-c',program,str(SOURCE),str(self.root),str(self.documents)],
                capture_output=True,text=True,timeout=10,check=True)
            records.append(json.loads(completed.stdout))
        self.assertEqual(records[0],records[1])
        self.assertEqual(records[0]['calls'],1)


if __name__=='__main__': unittest.main(verbosity=2)
