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
import types
import unittest
from unittest import mock

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
        self.root = Path(self.tmp.name)
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

if __name__=='__main__': unittest.main(verbosity=2)
