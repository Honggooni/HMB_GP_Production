"""Recognized CPython teardown guard, fake transports and official hook bodies.

The exact product helper/lifecycle AST executes without an SDK engine. The
stdlib method is copied into a private fake module/class; no real asyncio
method, socket, workflow or installed file is mutated by this regression.
"""
from __future__ import annotations
import ast
import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import inspect
import logging
from pathlib import Path
import socket
import sys
from types import ModuleType
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
source=ast.parse((ROOT/'_hmb_library_bootstrap.py').read_text(encoding='utf-8'))
def sdk_import(node):
    return any(isinstance(child,ast.ImportFrom) and (child.module or '').startswith('griptape_nodes')
               for child in ast.walk(node))
body=[node for node in source.body if not (isinstance(node,(ast.ImportFrom,ast.Try)) and sdk_import(node))]
class Dummy:pass
namespace={'__name__':'_hmb_windows_close_guard_test','__file__':str(ROOT/'_hmb_library_bootstrap.py'),
    'AdvancedNodeLibrary':object,'current_engine':None,'_LOAD_TYPES':(),
    '_SERIALIZE_TYPES':(),'_SAVE_TYPES':(),
    'is_loading_workflow':lambda:False,'LibraryRegistry':Dummy,'WorkflowRegistry':Dummy,
    **{name:type(name,(),{}) for name in ('CreateNodeRequest','CreateNodeResultFailure',
        'DeserializeSelectedNodesFromCommandsRequest','DeserializeSelectedNodesFromCommandsResultFailure',
        'SetParameterValueRequest','EnsureWorkflowAndFlowRequest','EnsureWorkflowAndFlowResultSuccess')}}
exec(compile(ast.Module(body=body,type_ignores=[]),str(ROOT/'_hmb_library_bootstrap.py'),'exec'),namespace)

stdlib=Path(asyncio.__file__).with_name('proactor_events.py')
module_ast=ast.parse(stdlib.read_text(encoding='utf-8'))
transport_ast=next(node for node in module_ast.body if isinstance(node,ast.ClassDef)
    and node.name=='_ProactorBasePipeTransport')
method_ast=next(node for node in transport_ast.body if isinstance(node,ast.FunctionDef)
    and node.name=='_call_connection_lost')
known_hash=hashlib.sha256(ast.dump(method_ast,annotate_fields=True,include_attributes=False).encode()).hexdigest()
if known_hash!=namespace['_WINDOWS_CLOSE_GUARD_AST_SHA256']:
    print('Windows close guard regression: unsupported stdlib shape; compatibility stays inactive')
    raise SystemExit(0)
private=ModuleType('asyncio.proactor_events');private.__file__=str(stdlib);private.socket=socket
private_class=deepcopy(transport_ast);private_class.bases=[];private_class.keywords=[];private_class.body=[deepcopy(method_ast)]
exec(compile(ast.Module(body=[private_class],type_ignores=[]),str(stdlib),'exec'),vars(private))
transport_class=private._ProactorBasePipeTransport
original=transport_class._call_connection_lost
acquire=namespace['_acquire_windows_transport_close_guard']
release=namespace['_release_windows_transport_close_guard']
diagnostics=namespace['_windows_transport_close_guard_diagnostics']
def reset_error(code=10054):
    error=ConnectionResetError(code,'fixture socket shutdown');error.winerror=code
    return error
class Protocol:
    def __init__(self,error=None):self.error=error;self.calls=[]
    def connection_lost(self,error):
        self.calls.append(error)
        if self.error is not None:raise self.error
class Sock:
    def __init__(self,error=None,fd=17):self.error=error;self.fd=fd;self.shutdowns=[];self.closes=0
    def fileno(self):return self.fd
    def shutdown(self,how):
        self.shutdowns.append(how)
        if self.error is not None:raise self.error
    def close(self):self.closes+=1
    def getsockname(self):return ('127.0.0.1',9001)
    def getpeername(self):return ('127.0.0.1',9002)
class Server:
    def __init__(self,error=None):self.detaches=0;self.error=error
    def _detach(self):
        self.detaches+=1
        if self.error:raise self.error
def transport(shutdown_error=None,protocol_error=None,fd=17,server_error=None):
    value=transport_class();value._called_connection_lost=False
    value._protocol=Protocol(protocol_error);value._sock=Sock(shutdown_error,fd)
    value._server=Server(server_error);value._extra={}
    return value,value._sock,value._protocol,value._server
def raises_expected(fn,error):
    try:fn()
    except BaseException as caught:assert caught is error,(caught,error)
    else:raise AssertionError('Expected original failure was masked')
class Capture(logging.Handler):
    def __init__(self):super().__init__();self.rows=[]
    def emit(self,record):self.rows.append(record.getMessage())

with patch.dict(sys.modules,{'asyncio.proactor_events':private}),patch.object(sys,'platform','win32'):
    first,second=Dummy(),Dummy()
    logger=logging.getLogger(namespace['__name__']);handler=Capture();logger.addHandler(handler);old_level=logger.level;logger.setLevel(logging.INFO)
    try:
        assert namespace['_known_windows_close_function'](original,transport_class)
        assert acquire(first) and acquire(first) and acquire(second)
        wrapper=transport_class._call_connection_lost
        assert wrapper is not original and diagnostics()['owner_count']==2
        value,sock,protocol,server=transport(reset_error())
        wrapper(value,None)
        assert protocol.calls==[None] and sock.shutdowns==[socket.SHUT_RDWR] and sock.closes==server.detaches==1
        assert value._sock is value._server is None and value._called_connection_lost
        wrapper(value,None)
        assert len(protocol.calls)==sock.closes==server.detaches==1
        assert diagnostics()['handled_count']==1
        # Repaired shutdown may not replace a protocol exception; finally still
        # closes/detaches before the exact original exception propagates.
        failure=RuntimeError('protocol fixture')
        value,sock,protocol,server=transport(reset_error(),failure)
        raises_expected(lambda:wrapper(value,None),failure)
        assert protocol.calls==[None] and sock.closes==server.detaches==1 and value._called_connection_lost
        other=reset_error(10053)
        value,sock,protocol,server=transport(other)
        raises_expected(lambda:wrapper(value,None),other)
        assert sock.closes==server.detaches==0 and not value._called_connection_lost
        # The same shutdown error during genuine read/write failure is unchanged.
        shutdown=reset_error();read_failure=ConnectionError('read failed')
        value,sock,protocol,server=transport(shutdown)
        raises_expected(lambda:wrapper(value,read_failure),shutdown)
        assert protocol.calls==[read_failure] and sock.closes==server.detaches==0
        for protocol_failure in (RuntimeError('protocol only'),reset_error()):
            value,sock,protocol,server=transport(None,protocol_failure)
            raises_expected(lambda:wrapper(value,None),protocol_failure)
            assert sock.closes==server.detaches==1 and value._called_connection_lost
        # Other finalization failures remain visible rather than being logged away.
        detach_failure=RuntimeError('server detach failed')
        value,sock,protocol,server=transport(reset_error(),server_error=detach_failure)
        raises_expected(lambda:wrapper(value,None),detach_failure)
        assert sock.closes==server.detaches==1 and not value._called_connection_lost
        value,sock,protocol,server=transport(reset_error(),fd=-1)
        wrapper(value,None);assert sock.shutdowns==[] and sock.closes==server.detaches==1
        for _ in range(3):
            value,*_=transport(reset_error());wrapper(value,None)
        assert sum('guard enabled' in row for row in handler.rows)==1
        assert sum('cleanup completed' in row for row in handler.rows)==1,'Repeated compatibility events flooded INFO logs'
        assert all('127.0.0.1' not in row and 'http' not in row for row in handler.rows)
        assert diagnostics()['first_diagnostic']==dict(protocol_class=__name__+'.Protocol',local_port=9001,peer_loopback=True,remote_port=9002)
        release(first);assert transport_class._call_connection_lost is wrapper
        release(second);assert transport_class._call_connection_lost is original
        release(second);assert transport_class._call_connection_lost is original
        assert diagnostics()['owner_count']==0
        # Another async package's wrapper must never be overwritten or removed.
        def foreign(*args):return original(*args)
        transport_class._call_connection_lost=foreign
        assert not acquire(first) and transport_class._call_connection_lost is foreign
        release(first);assert transport_class._call_connection_lost is foreign
        transport_class._call_connection_lost=original
        assert acquire(first)
        transport_class._call_connection_lost=foreign
        release(first);assert transport_class._call_connection_lost is foreign
        # A cached HMB wrapper becomes inert after its last owner has unloaded.
        value,sock,*_=transport(reset_error())
        raises_expected(lambda:wrapper(value,None),sock.error);assert sock.closes==0
        transport_class._call_connection_lost=original
        with patch.object(sys,'platform','linux'):
            assert not acquire(first) and transport_class._call_connection_lost is original
        with patch.object(sys,'implementation',Dummy()):
            assert not acquire(first) and transport_class._call_connection_lost is original
        marker=namespace['_WINDOWS_CLOSE_GUARD_MARKER'];state=getattr(transport_class,marker)
        delattr(transport_class,marker)
        try:
            with patch.dict(namespace,{'_WINDOWS_CLOSE_GUARD_AST_SHA256':'0'*64}):
                assert not acquire(first) and transport_class._call_connection_lost is original
        finally:setattr(transport_class,marker,state)

        # Two aliases of the same Advanced library must share one process-wide
        # lock, not race between a module-local CAS check and method assignment.
        alias=dict(namespace,__name__='_hmb_windows_close_guard_alias')
        exec(compile(ast.Module(body=deepcopy(body),type_ignores=[]),str(ROOT/'_hmb_library_bootstrap.py'),'exec'),alias)
        assert alias['_windows_transport_close_lock']() is namespace['_windows_transport_close_lock']()
        owners=[Dummy() for _ in range(16)]
        with ThreadPoolExecutor(max_workers=8) as pool:
            admitted=list(pool.map(lambda index:(namespace if index%2 else alias)['_acquire_windows_transport_close_guard'](owners[index]),range(16)))
        assert all(admitted) and diagnostics()['owner_count']==16
        assert transport_class._call_connection_lost is wrapper
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda index:(namespace if index%2 else alias)['_release_windows_transport_close_guard'](owners[index]),range(16)))
        assert diagnostics()['owner_count']==0 and transport_class._call_connection_lost is original
        assert sum('guard enabled' in row for row in handler.rows)==1,'Reload repeated activation INFO'
        shared_key=namespace['_WINDOWS_CLOSE_GUARD_LOCK_KEY'];shared=vars(private)[shared_key]
        vars(private)[shared_key]=object()
        assert not acquire(first) and transport_class._call_connection_lost is original
        vars(private)[shared_key]=shared

        # Run the actual Advanced-library hook bodies with isolated weak owners.
        class Manager:
            def __init__(self):
                self.pre=[];self.post=[];self.event_loop=None
                self._pre_dispatch_hooks=self.pre;self._lock=namespace['threading'].RLock()
            def add_pre_dispatch_hook(self,hook):self.pre.append(hook)
            def remove_pre_dispatch_hook(self,hook):self.pre.remove(hook)
            def add_post_dispatch_hook(self,kind,hook):self.post.append((kind,hook))
            def remove_post_dispatch_hook(self,kind,hook):self.post.remove((kind,hook))
            def register_request_handlers(self,handler):pass
        engine=Dummy();engine.event_manager=Manager();engine.library_manager=Dummy();engine.library_manager.is_worker=False
        namespace['current_engine']=lambda:engine
        data=Dummy();data.name='HMB_GP_Production';library=Dummy()
        # This stdlib-only fixture does not construct an SDK payload registry.
        # Typed registration is tested by real SDK regressions. The stdlib
        # fixture supplies the mandatory critical seam explicitly.
        installed=[];optional={}
        for module_name in ('_hmb_deletion_guard','_hmb_connection_management'):
            stub=ModuleType(module_name)
            def install(_engine,registration,_name=module_name):
                assert _engine is engine
                installed.append((_name,registration))
                handler=Dummy()
                if _name=='_hmb_connection_management':
                    handler.owner_ref=lambda:registration
                    handler.protect_detached_ports=lambda *_args:None
                    engine.event_manager.add_pre_dispatch_hook(handler.protect_detached_ports)
                return handler
            stub.install_request_handlers=install;optional[module_name]=stub
            if module_name=='_hmb_deletion_guard':
                stub.__file__=str(ROOT/'_hmb_deletion_guard.py')
                stub.PROTECTION_VERSION=2;stub.protection_readiness=lambda _engine:(True,'')
                stub.guard_request=lambda _engine,_request:None
                barrier=Dummy();barrier.is_installed=lambda:True;barrier.engine_ref=lambda:engine
                def install_barrier(_engine):
                    assert _engine is engine
                    return barrier
                stub.install_reentrant_barrier=install_barrier
                stub.install_handler_barrier=install_barrier
        with patch.dict(sys.modules,optional):
            a,b=namespace['HMBProductionLibrary'](),namespace['HMBProductionLibrary']()
            a.before_library_nodes_loaded(data,library);a.before_library_nodes_loaded(data,library)
            b.before_library_nodes_loaded(data,library)
            assert len(installed)==2 and len({id(item[1]) for item in installed})==1
            gate=getattr(engine.event_manager,'_hmb_connected_deletion_lifetime_v2')
            assert len(engine.event_manager.pre)==3 and diagnostics()['owner_count']==1
            assert transport_class._call_connection_lost is wrapper
            a.before_library_unregistered(data,library)
            assert diagnostics()['owner_count']==1 and transport_class._call_connection_lost is wrapper
            b.before_library_unregistered(data,library)
            assert diagnostics()['owner_count']==0 and transport_class._call_connection_lost is original
            assert engine.event_manager.pre==[gate.hook] and engine.event_manager.post==[]
            assert gate.is_registered() and gate.engine_ref() is engine
    finally:
        logger.removeHandler(handler);logger.setLevel(old_level)
        transport_class._call_connection_lost=original
print('PASS Windows teardown guard: exact AST/CPython/platform, normal shutdown10054 only, protocol errors preserved, close/detach/flag once, sanitized INFO once, concurrent module aliases, multiple owner/lifecycle/foreign-wrapper safety.')
