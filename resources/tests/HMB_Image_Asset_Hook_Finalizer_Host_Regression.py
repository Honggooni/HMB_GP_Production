"""Actual SDK hook locks must not deadlock a collected import observer.

Each lock case runs in a bounded child process, so the old synchronous
weakref-finalizer bug produces a failure rather than hanging the test runner.
No live engine, workflow transport, project or provider request is used.
"""
from __future__ import annotations
import argparse
import asyncio
import gc
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import weakref
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True


def child(case):
    with tempfile.TemporaryDirectory(prefix='hmb-hook-finalizer-') as temp:
        env = {key:str(Path(temp)/key) for key in ('APPDATA','LOCALAPPDATA','XDG_CONFIG_HOME','XDG_DATA_HOME','XDG_STATE_HOME','XDG_CACHE_HOME','GTN_CONFIG_WORKSPACE_DIRECTORY')}
        for path in env.values(): Path(path).mkdir(parents=True, exist_ok=True)
        with mock.patch.dict(os.environ, env), mock.patch.object(socket, 'create_connection', side_effect=AssertionError('No network')):
            import HMBImageAssetLibrary as library
            from griptape_nodes.retained_mode.managers.event_manager import EventManager
            from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
            from griptape_nodes.retained_mode.events.parameter_events import RemoveParameterFromNodeRequest
            manager = EventManager()
            sentinel_pre = lambda request, context:None
            sentinel_post = lambda request, result:None
            manager.add_pre_dispatch_hook(sentinel_pre)
            manager.add_post_dispatch_hook(RemoveParameterFromNodeRequest, sentinel_post)
            class Owner:
                name='Synthetic collected ImageAsset'
                lock=False
                def _scan_owner_is_current(self): return True
            with mock.patch.object(GriptapeNodes, 'EventManager', return_value=manager):
                owner = Owner()
                reference = weakref.ref(owner)
                state = library._ensure_import_child_removal_observers(owner)
                assert len(manager._pre_dispatch_hooks) == 2
                assert len(manager._post_dispatch_hooks[RemoveParameterFromNodeRequest]) == 2
                previous_pre = manager._pre_dispatch_hooks[-1]
                previous_post = manager._post_dispatch_hooks[RemoveParameterFromNodeRequest][-1]
                if case == 'explicit':
                    with mock.patch.object(library.threading, 'Thread', side_effect=AssertionError('Explicit cleanup must remain synchronous')):
                        library._release_import_child_removal_observers(owner)
                    assert not state['finalizer'].alive
                    assert state['manager'] is None
                    # Re-register in the same manager; old detached callbacks
                    # must not act on the replacement registration's state.
                    current = library._ensure_import_child_removal_observers(owner)
                    request = RemoveParameterFromNodeRequest(node_name=owner.name, parameter_name='unused')
                    assert previous_pre(request, None) is None
                    assert previous_post(request, None) is None
                    library._release_import_child_removal_observers(owner)
                    del owner
                elif case == 'shutdown-refuses-thread':
                    with mock.patch.object(library.threading.Thread, 'start', side_effect=RuntimeError('Interpreter shutdown')):
                        del owner
                        gc.collect()
                    assert reference() is None
                    request = RemoveParameterFromNodeRequest(node_name='gone', parameter_name='unused')
                    assert previous_pre(request, None) is None
                    assert previous_post(request, None) is None
                    # The simulated interpreter continues only for assertions;
                    # perform deterministic teardown of its private manager.
                    state['unregister']()
                else:
                    if case == 'closed-loop':
                        loop = asyncio.new_event_loop(); loop.close()
                        manager._event_loop = loop
                    lock = manager._pre_dispatch_hooks_lock if case == 'pre-lock' else manager._post_dispatch_hooks_lock
                    # Actual CPython weakref finalization while the actual SDK
                    # owns its non-reentrant lock. The old implementation hangs.
                    with lock:
                        del owner
                        gc.collect()
                        assert reference() is None
                    deadline = time.monotonic() + 2
                    while True:
                        with manager._pre_dispatch_hooks_lock:
                            pre = list(manager._pre_dispatch_hooks)
                        with manager._post_dispatch_hooks_lock:
                            post = list(manager._post_dispatch_hooks.get(RemoveParameterFromNodeRequest, []))
                        if pre == [sentinel_pre] and post == [sentinel_post]: break
                        assert time.monotonic() < deadline, 'Finalizer cleanup did not complete'
                        time.sleep(.001)
                    request = RemoveParameterFromNodeRequest(node_name='gone', parameter_name='unused')
                    assert previous_pre(request, None) is None
                    assert previous_post(request, None) is None
                gc.collect()
                assert reference() is None
                assert manager._pre_dispatch_hooks == [sentinel_pre]
                assert manager._post_dispatch_hooks[RemoveParameterFromNodeRequest] == [sentinel_post]
                deadline = time.monotonic() + 2
                while [t for t in __import__('threading').enumerate() if t.name == 'HMBImageImportHookCleanup' and t.is_alive()]:
                    assert time.monotonic() < deadline, 'Cleanup worker retained resources'
                    time.sleep(.001)
    print('FINALIZER_CASE=PASS ' + case)


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--case'); args=parser.parse_args()
    if args.case:
        child(args.case); return
    for case in ('post-lock','pre-lock','closed-loop','explicit','shutdown-refuses-thread'):
        result=subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),'--case',case],
            capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=12)
        assert result.returncode==0, (case,result.stdout,result.stderr)
        print(result.stdout.strip(),flush=True)
    print('HMB_IMAGE_ASSET_HOOK_FINALIZER_HOST=PASS (actual SDK locks; bounded GC; closed loop; explicit synchronous cleanup; weak owner; unrelated hooks preserved; external calls 0)')


if __name__=='__main__': main()
