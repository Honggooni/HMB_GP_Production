"""Detached native capture sharing, bounded queue and owner-local cancellation.

All external processes are simulated. No Maya, render, workflow or network is
started; real job/path copying and source/dependency invalidation are exercised.
"""
from __future__ import annotations
import copy
import gc
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import weakref
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import HMBVideoPickerLibrary as picker


class Controller:
    _run_shared_maya_capture = picker.HMBVideoPickerLibrary._run_shared_maya_capture
    def __init__(self, state):
        self.state = copy.deepcopy(state)
        self._hmb_cancel_requested = threading.Event()
        self.active = None
        self.stale = False
    def _picker_state(self): return copy.deepcopy(self.state)
    def _write_state(self, state): self.state = copy.deepcopy(state); return self.state
    def _assert_operation_current(self, _context, _stage):
        if self.stale: raise picker._StaleOperationError('This Shot changed')
    def _register_active_process(self, process, _kind): self.active = process
    def _clear_active_process(self, process):
        assert self.active is process
        self.active = None
    def _wait_for_process_with_progress(self, process, _progress, _overall, _stall, _label, *, activity_paths):
        while not process.release.wait(0.01):
            if self._hmb_cancel_requested.is_set():
                picker._terminate_process(process)
                raise RuntimeError('All capture subscribers cancelled')
        if self._hmb_cancel_requested.is_set():
            picker._terminate_process(process)
            raise RuntimeError('All capture subscribers cancelled')
        process.complete()
        return process.return_code


def wait_until(predicate, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate(): return
        time.sleep(0.01)
    raise AssertionError('Fixture did not reach requested state')


with tempfile.TemporaryDirectory(prefix='hmb_maya_single_flight_') as temporary:
    root = Path(temporary)
    scene, texture = root / 'source.ma', root / 'eye.png'
    scene.write_text('// fixture scene', encoding='utf-8')
    texture.write_bytes(b'original eye texture')
    manifest = root / 'dependencies.json'
    manifest.write_text(json.dumps(dict(schema=picker.ORIGINAL_DEPENDENCY_MANIFEST_SCHEMA,
        version=1, scene_path=str(scene), scene_fingerprint=picker._scene_fingerprint(scene),
        paths=[str(scene), str(texture)])), encoding='utf-8')
    state = {'native_metadata': {'dependency_manifest_path': str(manifest)}, 'selected_camera': '|camera'}
    processes, release = [], threading.Event()
    fail_next = [False]

    class Process:
        def __init__(self, _command, *, env, **_kwargs):
            self.job = picker._read_json(Path(env['HMB_VIDEO_PICKER_JOB']))
            self.pid = 4000000 + len(processes)
            self.release, self.killed = release, False
            self.return_code = None
            self.fail = fail_next[0]; fail_next[0] = False
            processes.append(self)
        def poll(self): return self.return_code
        def kill(self): self.killed = True; self.return_code = -1
        def wait(self, **_kwargs): return self.return_code
        def complete(self):
            frames = Path(self.job['frames_folder']); frames.mkdir(parents=True, exist_ok=True)
            (frames / 'mask.000000.png').write_bytes(b'completed private frame')
            sidecar = {'camera': self.job['camera'], 'frames_folder': str(frames)}
            picker._write_json(Path(self.job['sidecar_path']), sidecar)
            picker._write_json(Path(self.job['result_path']), dict(ok=not self.fail,
                error='fixture native error' if self.fail else '', capture_pass=self.job['capture_pass'],
                frames_folder=str(frames), sidecar_path=self.job['sidecar_path']))
            self.return_code = 0

    def request(name):
        folder = root / '.hmb_video_picker' / name; folder.mkdir(parents=True, exist_ok=True)
        job = dict(operation='render', scene_path=str(scene), capture_pass='color',
            camera='|camera', start_frame=101, end_frame=101, width=320, height=180, fps=24,
            output_name='mask', frames_folder=str(folder/'frames'), sidecar_path=str(folder/'mask.hmb.json'),
            result_path=str(folder/'capture.result.json'), progress_path=str(folder/'capture.progress.json'),
            bindings=[{'root':'|Hero', 'marker_name':'Yellow'}], depth_range_bindings=[{'root':'|Hero'}],
            hidden_paths=['|Hidden'], depth_range_mode='close', depth_profile=picker.DEPTH_PLAYBLAST_PROFILE)
        return job, folder

    errors, values = {}, {}
    def launch(name, node, job, folder):
        def work():
            try:
                values[name] = node._run_shared_maya_capture(job=job, command=['fixture-mayabatch'],
                    job_path=folder/'capture.job.json', result_path=folder/'capture.result.json',
                    progress_path=folder/'capture.progress.json', log_path=root/(name+'.log'),
                    activity_paths=(folder/'frames',), context=None, operation_label='Fixture Mask')
            except Exception as exc: errors[name] = exc
        worker = threading.Thread(target=work); worker.start(); return worker

    with patch.object(picker.subprocess, 'Popen', Process), \
            patch.object(picker.subprocess, 'run', return_value=SimpleNamespace(returncode=0)):
        coordinator = picker._MayaCaptureCoordinator(workers=1, max_queued=2, max_wait=2)
        picker._MAYA_CAPTURE_COORDINATOR = coordinator
        job_a, folder_a = request('Shot-A'); job_b, folder_b = request('Shot-B')
        key_a, proof = picker._maya_capture_identity(job_a, ['fixture-mayabatch'], folder_a, state)
        key_b, _ = picker._maya_capture_identity(job_b, ['fixture-mayabatch'], folder_b, state)
        assert proof['complete'] and key_a == key_b
        # Every capture-affecting pass/binding/depth/visibility setting changes
        # identity; different owner output folders do not.
        for field, value in [('capture_pass','depth'),('camera','|other'),('start_frame',102),
                ('width',640),('bindings',[]),('depth_range_bindings',[]),('depth_range_mode','far'),
                ('depth_profile','old'),('hidden_paths',[]),('maya_evaluation_mode','off')]:
            modified = dict(job_a); modified[field] = value
            assert picker._maya_capture_identity(modified,['fixture-mayabatch'],folder_a,state)[0] != key_a, field
        node_a, node_b = Controller(state), Controller(state)
        first = launch('A', node_a, job_a, folder_a)
        wait_until(lambda: len(processes) == 1)
        second = launch('B', node_b, job_b, folder_b)
        wait_until(lambda: coordinator.shared_requests == 1 and node_b.active is not None)
        first_flight = node_a.active.flight
        picker._terminate_process(node_a.active)  # no taskkill, releases only A
        first.join(3)
        assert 'A' in errors and not processes[0].killed
        assert coordinator.flights[key_a].subscribers == 1
        release.set(); second.join(3); coordinator.pending.join()
        assert values['B'] == 0 and len(processes) == 1
        result_b = picker._read_json(folder_b/'capture.result.json')
        assert result_b['frames_folder'] == str(folder_b/'frames').replace('\\','/')
        assert (folder_b/'frames'/'mask.000000.png').is_file()
        assert not (folder_a/'frames').exists() and node_a.active is node_b.active is None
        assert not coordinator.flights and coordinator.peak_active == 1
        assert first_flight.producer is None
        owner_reference = weakref.ref(node_a)
        errors['A'] = str(errors['A'])  # Drop the expected exception traceback.
        del node_a
        gc.collect()
        assert owner_reference() is None, 'Idle worker retained the first node through its producer closure'

        # All subscriber cancellation terminates the producer and leaves no
        # shared staging or public/owner files; another request can start fresh.
        release = threading.Event()
        job_c, folder_c = request('Shot-C'); job_d, folder_d = request('Shot-D')
        node_c, node_d = Controller(state), Controller(state)
        third = launch('C', node_c, job_c, folder_c)
        wait_until(lambda: len(processes) == 2)
        fourth = launch('D', node_d, job_d, folder_d)
        wait_until(lambda: node_d.active is not None and coordinator.shared_requests == 2)
        flight = node_c.active.flight
        picker._terminate_process(node_c.active); picker._terminate_process(node_d.active)
        third.join(3); fourth.join(3); coordinator.pending.join()
        assert processes[1].killed and flight.abort.is_set()
        assert flight.root is not None and not flight.root.exists()
        assert not (folder_c/'frames').exists() and not (folder_d/'frames').exists()

        # A failed result is never retained as a completed cache.
        release = threading.Event(); release.set(); fail_next[0] = True
        job_e, folder_e = request('Shot-E'); node_e = Controller(state)
        failed = launch('E', node_e, job_e, folder_e); failed.join(3); coordinator.pending.join()
        assert 'E' in errors and 'fixture native error' in str(errors['E'])
        failed_owner_reference = weakref.ref(node_e)
        errors['E'] = str(errors['E'])  # Caller traceback is not flight retention.
        del node_e
        gc.collect()
        assert failed_owner_reference() is None, 'Idle worker retained failed node through producer/error traceback'
        job_f, folder_f = request('Shot-F'); node_f = Controller(state)
        retry = launch('F', node_f, job_f, folder_f); retry.join(3); coordinator.pending.join()
        assert values['F'] == 0 and len(processes) == 4

        # A referenced file changing during rendering invalidates the flight.
        release = threading.Event()
        job_g, folder_g = request('Shot-G'); node_g = Controller(state)
        stale = launch('G', node_g, job_g, folder_g)
        wait_until(lambda: len(processes) == 5)
        before = picker._maya_capture_identity(job_g,['fixture-mayabatch'],folder_g,state)[0]
        texture.write_bytes(b'changed eye texture with new size')
        after = picker._maya_capture_identity(job_g,['fixture-mayabatch'],folder_g,state)[0]
        assert before != after
        release.set(); stale.join(3); coordinator.pending.join()
        assert isinstance(errors['G'], picker._StaleOperationError)
        assert not (folder_g/'frames').exists()
        unknown = {'native_metadata': {}}
        assert picker._maya_capture_identity(job_g,['fixture-mayabatch'],folder_g,unknown)[0] != picker._maya_capture_identity(job_g,['fixture-mayabatch'],folder_g,unknown)[0]

        # Queue tickets are bounded, same-key joins work at capacity, cancelled
        # queued requests release tickets, and waiting has a finite timeout.
        queue_coordinator = picker._MayaCaptureCoordinator(workers=1, max_queued=1, max_wait=.15)
        picker._MAYA_CAPTURE_COORDINATOR = queue_coordinator
        blocking, entered = threading.Event(), threading.Event()
        def blocked(flight):
            entered.set()
            while not blocking.wait(.01):
                if flight.abort.is_set(): return -1
            return 0
        running = queue_coordinator.subscribe('running', blocked); assert entered.wait(2)
        queued = queue_coordinator.subscribe('queued', blocked)
        try:
            queue_coordinator.subscribe('overflow', blocked)
            raise AssertionError('Bounded queue accepted overflow')
        except RuntimeError as exc: assert 'queue is full' in str(exc)
        joined = queue_coordinator.subscribe('running', blocked)
        queue_coordinator.release(queued)
        assert queue_coordinator.pending.qsize() == 0
        job_h, folder_h = request('Shot-H'); node_h = Controller(state)
        timed_out = launch('H', node_h, job_h, folder_h); timed_out.join(3)
        assert 'queue wait timed out' in str(errors['H'])
        assert queue_coordinator.pending.qsize() == 0 and len(processes) == 5
        queue_coordinator.release(running); queue_coordinator.release(joined)
        queue_coordinator.pending.join()
        assert queue_coordinator.peak_active == 1 and queue_coordinator.peak_queued <= 1
        assert not queue_coordinator.flights
        idle_worker = queue_coordinator.threads[0]
        assert idle_worker.is_alive()
        idle_request = queue_coordinator.subscribe('after-idle', lambda _flight: 0)
        assert idle_request.flight.done.wait(2)
        queue_coordinator.release(idle_request); queue_coordinator.pending.join()
        assert queue_coordinator.threads == [idle_worker], 'Idle queue stranded a new request or grew workers'

print('PASS: one Maya capture for two Shots; isolated cancel/copies; all-cancel abort; failure retry; dependency stale rejection; bounded queue and wait')
