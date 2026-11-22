"""Offline coverage for completed regular, Draft and My Box media publishing. Never creates a task."""
from concurrent.futures import CancelledError, Future, ThreadPoolExecutor
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import _hmb_client_review_media as worker


class Reply(BytesIO):
    def __init__(self, url, data, status=200, headers=None):
        super().__init__(data if isinstance(data, bytes) else json.dumps(data).encode())
        self.status, self.headers, self.url = status, headers or {}, url

    def geturl(self):
        return self.url


class Broker:
    def __init__(self, task, source, private=False):
        self.server_url = "https://broker.example.test/GripTapeServer"
        self._opener = self
        self.task, self.source = task, source
        self.sha = hashlib.sha256(source).hexdigest()
        self.key = hashlib.sha256(task.encode()).hexdigest()
        self.route = "/api/v1/reviews/tasks/" + task + "/workstation-media"
        self.original = ("/api/v1/only/my-box/items/" + task + "/media?download=1" if private
                         else "/api/v1/reviews/tasks/" + task + "/download")
        self.token = "example-token"
        self.owner = 18
        self.ready = False
        self.descriptor_state = None
        self.heartbeat_state = None
        self.supported = True
        self.lost_response = False
        self.truncated = False
        self.transient = False
        self.requests = []
        self.entered, self.release = threading.Event(), threading.Event()
        self.release.set()
        self.upload_url = self.route

    def _load_access_token(self):
        return self.token

    def open(self, request, timeout):
        url = request.full_url
        if not url.startswith(self.server_url + "/api/"):
            raise AssertionError("Unexpected host")
        route, method = url[len(self.server_url):], request.get_method()
        hdr = {k.lower():v for k, v in request.header_items()}
        assert hdr["authorization"] == "Bearer " + self.token
        self.requests.append((method, route))
        if route == "/api/v1/reviews/capabilities" and method == "GET":
            return Reply(url, {"workstation_review_media": "pc-v1", "workstation_fallback_seconds": 30} if self.supported else {})
        if route == "/api/me" and method == "GET":
            return Reply(url, {"id": self.owner})
        if route == self.route and method == "GET":
            return Reply(url, {"task_id": self.task, "state": self.descriptor_state or ("ready" if self.ready else "waiting"),
                               "source_sha256": self.sha, "source_bytes": len(self.source), "idempotency_key": self.key,
                               "original_url": self.original, "upload_url": self.upload_url,
                               "heartbeat_url": self.route + "/heartbeat"})
        if route == self.original and method == "GET":
            self.entered.set()
            assert self.release.wait(10)
            if self.transient:
                self.transient = False
                raise HTTPError(url, 503, "Transient", {}, BytesIO())
            return Reply(url, self.source[:-1] if self.truncated else self.source, headers={"Content-Length": str(len(self.source))})
        if method == "POST":
            assert hdr["x-hmb-source-sha256"] == self.sha and hdr["idempotency-key"] == self.key
            if route == self.route + "/heartbeat":
                assert request.data == b""
                if self.heartbeat_state:
                    return Reply(url, {"task_id": self.task, "state": self.heartbeat_state, "workstation_fallback_seconds": 30})
                return Reply(url, b"", 204)
            if route == self.route:
                blob = b"".join(request.data)
                n = int(hdr["x-hmb-poster-bytes"])
                assert len(blob) == int(hdr["content-length"])
                assert blob.startswith(b"\xff\xd8") and blob[n + 4:n + 8] == b"ftyp"
                self.ready = True
                if self.lost_response:
                    raise ConnectionResetError("Response lost after commit")
                return Reply(url, {"state": "ready", "derived_task_id": self.task, "source_sha256": self.sha}, 201)
        raise AssertionError(f"Disallowed call {method} {route}")

    def count(self, method, route):
        return self.requests.count((method, route))


class WorkstationMediaTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.enter = self.enterContext
        self.enter(patch.dict(os.environ, LOCALAPPDATA=temp.name))
        self.enter(patch.object(worker, "_HEARTBEAT", .03))
        self.source = b"\0\0\0\x18ftypqt  test original"
        self.broker = Broker("job-normal", self.source)
        self.encoded = 0

    def encoder(self, source, directory, cancel, *, expected_sha256):
        self.encoded += 1
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), expected_sha256)
        poster, preview = directory / "poster.jpg", directory / "preview.mp4"
        poster.write_bytes(b"\xff\xd8poster")
        preview.write_bytes(b"\0\0\0\x18ftypmp42preview")
        return poster, preview

    def schedule(self, broker=None, **opts):
        broker = broker or self.broker
        return worker.schedule_completed_review_media(broker, broker.task, **opts)

    def observe_handoff(self):
        observed = threading.Event()
        confirm = worker._WorkstationLease.confirm
        def watch(lease):
            state = confirm(lease)
            if state != "waiting":
                observed.set()
            return state
        self.enter(patch.object(worker._WorkstationLease, "confirm", watch))
        return observed

    def test_join_and_restart_under_five_simultaneous_completions(self):
        broker = self.broker
        self.enter(patch.object(worker, "make_review_media", self.encoder))
        broker.release.clear()
        first = self.schedule()
        try:
            self.assertTrue(broker.entered.wait(5))
            with ThreadPoolExecutor(max_workers=5) as pool:
                calls = list(pool.map(lambda _: self.schedule(), range(5)))
            self.assertTrue(all(call is first for call in calls))
            for _ in range(100):
                if broker.count("POST", broker.route + "/heartbeat") >= 2:
                    break
                time.sleep(.01)
            self.assertGreaterEqual(broker.count("POST", broker.route + "/heartbeat"), 2)
        finally:
            broker.release.set()
        self.assertEqual(first.result(5)["state"], "ready")
        beats = broker.count("POST", broker.route + "/heartbeat")
        time.sleep(.08)
        self.assertEqual(beats, broker.count("POST", broker.route + "/heartbeat"))
        self.assertEqual(self.schedule().result(5)["state"], "ready")
        self.assertEqual(broker.count("GET", broker.original), 1)
        self.assertEqual(broker.count("POST", broker.route), 1)
        self.assertEqual(self.encoded, 1)
        cached, = self.root.rglob("source.mov")
        self.assertEqual(cached.read_bytes(), self.source)
        self.assertEqual(json.loads(cached.with_name("receipt.json").read_bytes())["source_sha256"], broker.sha)
        broker.ready = False
        self.assertEqual(self.schedule().result(5)["state"], "ready")
        self.assertEqual(broker.count("GET", broker.original), 1)

    def test_local_sources_and_ambiguous_receipts(self):
        self.enter(patch.object(worker, "make_review_media", self.encoder))
        path = self.root / "existing.mov"
        path.write_bytes(self.source)
        for task, media, private in (("job-normal", path, False), ("job-draft", self.source, False),
                                     ("job-mybox-" + "2" * 32, path, True)):
            broker = Broker(task, self.source, private)
            broker.lost_response = True
            existing_pointers = set(self.root.rglob("local-source.json"))
            self.assertEqual(self.schedule(broker, local_source=media, private=private).result(5)["state"], "ready")
            self.assertEqual(broker.count("GET", broker.original), 0)
            self.assertEqual(broker.count("GET", broker.route), 2)
            self.assertEqual(broker.count("POST", broker.route), 1)
            if isinstance(media, Path):
                pointer, = set(self.root.rglob("local-source.json")) - existing_pointers
                self.assertTrue(Path(json.loads(pointer.read_bytes())["path"]).samefile(path))
                broker.ready = False
                self.schedule(broker, private=private).result(5)
                self.assertEqual(broker.count("GET", broker.original), 0)

    def test_stale_local_paths_recover_one_verified_original_then_reuse_cache(self):
        self.enter(patch.object(worker, "make_review_media", self.encoder))
        for kind in ("moved", "deleted", "changed"):
            with self.subTest(kind=kind):
                path = self.root / f"{kind}.mov"
                path.write_bytes(self.source)
                if kind == "moved":
                    path.rename(self.root / "user-moved.mov")
                elif kind == "deleted":
                    path.unlink()
                else:
                    path.write_bytes(b"x" * len(self.source))
                broker = Broker("job-" + kind, self.source)
                promise = Future()
                promise.set_result(path)
                self.assertEqual(self.schedule(broker, local_source=promise).result(5)["source_sha256"], broker.sha)
                self.assertEqual(broker.count("GET", broker.original), 1)
                self.assertEqual(broker.count("POST", broker.route), 1)
                broker.ready = False
                self.assertEqual(self.schedule(broker, local_source=path).result(5)["state"], "ready")
                self.assertEqual(broker.count("GET", broker.original), 1)
                if kind == "changed":
                    self.assertEqual(path.read_bytes(), b"x" * len(self.source))

    def test_unverified_recovery_bytes_are_never_published(self):
        self.enter(patch.object(worker, "make_review_media", self.encoder))
        broker = self.broker
        broker.source = b"x" * len(self.source)
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            self.schedule(local_source=self.root / "deleted.mov").result(5)
        self.assertEqual(broker.count("GET", broker.original), 1)
        self.assertEqual(broker.count("POST", broker.route), 0)
        self.assertEqual(self.encoded, 0)
        self.assertFalse(list(self.root.rglob("source.*")))
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            self.schedule(local_source=broker.source).result(5)
        self.assertEqual(broker.count("GET", broker.original), 1)

    def test_external_original_changes_during_encoding(self):
        path = self.root / "changing.mov"
        path.write_bytes(self.source)
        def invalidate(source, directory, cancel, *, expected_sha256):
            if source.samefile(path):
                path.write_bytes(b"x" * len(self.source))
                raise worker.ColorLUTError("The video changed while preparing its review media.")
            return self.encoder(source, directory, cancel, expected_sha256=expected_sha256)
        with patch.object(worker, "make_review_media", invalidate):
            self.assertEqual(self.schedule(local_source=path).result(5)["state"], "ready")
        self.assertEqual(path.read_bytes(), b"x" * len(self.source))
        self.assertEqual(self.encoded, 1)
        self.assertEqual(self.broker.count("GET", self.broker.original), 1)
        self.assertEqual(self.broker.count("POST", self.broker.route), 1)
        broker = Broker("job-healthy-source-encoder-error", self.source)
        path.write_bytes(self.source)
        with patch.object(worker, "make_review_media", side_effect=worker.ColorLUTError("codec unavailable")):
            with self.assertRaisesRegex(worker.ColorLUTError, "codec unavailable"):
                self.schedule(broker, local_source=path).result(5)
        self.assertEqual(broker.count("GET", broker.original), 0)
        self.assertEqual(broker.count("POST", broker.route), 0)

    def test_all_pending_origins_heartbeat_while_heavy_slot_is_full(self):
        self.enter(patch.object(worker, "make_review_media", self.encoder))
        gate = threading.BoundedSemaphore(1)
        self.enter(patch.object(worker, "_WORK_SLOTS", gate))
        producers = [Future() for _ in range(5)]
        brokers = [Broker("job-queued-" + str(i), self.source) for i in range(5)]
        with gate:
            jobs = [self.schedule(broker, local_source=producer) for broker, producer in zip(brokers, producers)]
            deadline = time.monotonic() + 5
            while (time.monotonic() < deadline and
                   any(b.count("POST", b.route + "/heartbeat") < 2 for b in brokers)):
                time.sleep(.01)
            for broker, producer in zip(brokers, producers):
                self.assertGreaterEqual(broker.count("POST", broker.route + "/heartbeat"), 2)
                self.assertEqual(broker.count("GET", broker.original), 0)
                producer.set_result(self.source)
        for broker, job in zip(brokers, jobs):
            self.assertEqual(job.result(5)["state"], "ready")
            self.assertEqual(broker.count("GET", broker.original), 0)
            self.assertEqual(broker.count("POST", broker.route), 1)

    def test_failed_and_abandoned_foreground_downloads(self):
        self.enter(patch.object(worker, "make_review_media", self.encoder))
        self.enter(patch.object(worker, "_SOURCE_WAIT_SECONDS", .1))
        producer = Future()
        producer.cancel()
        with self.assertRaises(CancelledError):
            self.schedule(local_source=producer).result(5)
        with self.assertRaises(TimeoutError):
            self.schedule(local_source=Future()).result(5)
        self.assertEqual(self.broker.count("GET", self.broker.original), 0)
        beats = self.broker.count("POST", self.broker.route + "/heartbeat")
        time.sleep(.08)
        self.assertEqual(beats, self.broker.count("POST", self.broker.route + "/heartbeat"))
        failed = Future()
        failed.set_result(None)
        self.schedule(local_source=failed).result(5)
        self.assertEqual(self.broker.count("GET", self.broker.original), 1)

    def test_fallback_descriptor_and_first_heartbeat_end_work(self):
        self.enter(patch.object(worker, "make_review_media", self.encoder))
        broker = self.broker
        broker.descriptor_state = "fallback"
        self.assertEqual(worker.get_workstation_media_state(broker, broker.task)["state"], "fallback")
        self.assertEqual(self.schedule().result(2)["state"], "fallback")
        self.assertEqual(broker.count("POST", broker.route + "/heartbeat"), 0)
        broker.descriptor_state = "waiting"
        for state in ("fallback", "ready"):
            broker.heartbeat_state = state
            self.assertEqual(self.schedule().result(2)["state"], state)
            cancel = threading.Event()
            with worker.workstation_media_heartbeat(broker, heartbeat_url=broker.route + "/heartbeat",
                    task_id=broker.task, source_sha256=broker.sha, idempotency_key=broker.key, cancel_event=cancel) as lease:
                self.assertEqual(lease.state, state)
                self.assertTrue(cancel.is_set())
                self.assertIs(cancel, lease.cancel_event)
                self.assertEqual(lease.confirm(), state)
        self.assertEqual(broker.count("GET", "/api/me"), 0)
        self.assertEqual(broker.count("GET", broker.original), 0)
        self.assertEqual(broker.count("POST", broker.route), 0)
        self.assertEqual(self.encoded, 0)

    def test_ongoing_foreground_future_and_queue_handoff(self):
        self.enter(patch.object(worker, "make_review_media", self.encoder))
        slot = threading.BoundedSemaphore(1)
        self.enter(patch.object(worker, "_WORK_SLOTS", slot))
        for stage in ("future", "queue"):
            with slot:
                broker = Broker("job-handoff-" + stage, self.source)
                broker.heartbeat_state = "waiting"
                promise = Future()
                future = self.schedule(broker, local_source=promise if stage == "future" else None)
                deadline = time.monotonic() + 2
                while broker.count("POST", broker.route + "/heartbeat") < 2 and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertGreaterEqual(broker.count("POST", broker.route + "/heartbeat"), 2)
                broker.heartbeat_state = "fallback"
                self.assertEqual(future.result(2)["state"], "fallback")
                self.assertFalse(promise.done())
                self.assertEqual(broker.count("GET", broker.original), 0)
                self.assertEqual(broker.count("POST", broker.route), 0)

    def test_handoff_mid_original_stream_discards_incomplete_file(self):
        self.enter(patch.object(worker, "make_review_media", self.encoder))
        broker = self.broker
        broker.heartbeat_state = "waiting"
        original_open = broker.open
        first_chunk = threading.Event()
        handoff = self.observe_handoff()
        class HeldStream(Reply):
            def read(self, n):
                first_chunk.set()
                if not handoff.wait(2):
                    raise TimeoutError("Fixture did not signal handoff")
                return super().read(min(n, 4))
        def open_with_slow_original(request, timeout):
            response = original_open(request, timeout)
            if request.full_url.endswith(broker.original):
                return HeldStream(response.geturl(), response.getvalue(), headers=response.headers)
            return response
        broker.open = open_with_slow_original
        future = self.schedule()
        self.assertTrue(first_chunk.wait(2))
        broker.heartbeat_state = "fallback"
        self.assertEqual(future.result(3)["state"], "fallback")
        self.assertEqual(broker.count("GET", broker.original), 1)
        self.assertEqual(broker.count("POST", broker.route), 0)
        self.assertEqual(self.encoded, 0)
        self.assertFalse(list(self.root.rglob("source.*")))

    def test_handoff_stops_encoder_and_checks_before_post(self):
        for state, stage in (("fallback", "encoding"), ("ready", "attachment")):
            broker = Broker("job-lease-" + stage, self.source)
            broker.heartbeat_state = "waiting"
            def encode(source, directory, cancel, *, expected_sha256):
                if stage == "encoding":
                    broker.heartbeat_state = state
                    self.assertTrue(cancel.wait(2))
                    raise worker.ColorLUTError("Encoding cancelled")
                pair = self.encoder(source, directory, cancel, expected_sha256=expected_sha256)
                broker.heartbeat_state = state
                return pair
            with patch.object(worker, "make_review_media", encode), \
                    patch.object(worker, "_HEARTBEAT", .03 if stage == "encoding" else 60):
                self.assertEqual(self.schedule(broker, local_source=self.source).result(3)["state"], state)
            self.assertEqual(broker.count("GET", broker.original), 0)
            self.assertEqual(broker.count("POST", broker.route), 0)
            self.assertFalse(list(self.root.rglob("receipt.json")))

    def test_handoff_stops_inflight_attachment_between_chunks(self):
        broker = self.broker
        broker.heartbeat_state = "waiting"
        self.enter(patch.object(worker, "make_review_media", self.encoder))
        initial_open = broker.open
        handoff = self.observe_handoff()
        sent = []
        def start_then_handoff(request, timeout):
            if request.get_method() == "POST" and request.full_url.endswith(broker.route):
                body = iter(request.data)
                sent.append(next(body))
                broker.heartbeat_state = "fallback"
                self.assertTrue(handoff.wait(2))
                sent.extend(body)
                self.fail("The broker took over an in-flight transfer")
            return initial_open(request, timeout)
        broker.open = start_then_handoff
        self.assertEqual(self.schedule(local_source=self.source).result(3)["state"], "fallback")
        self.assertEqual(sent, [b"\xff\xd8poster"])
        self.assertFalse(broker.ready)
        self.assertFalse(list(self.root.rglob("receipt.json")))

    def test_incomplete_original_and_transient_retry(self):
        self.enter(patch.object(worker, "make_review_media", self.encoder))
        broker = self.broker
        broker.truncated = True
        with self.assertRaisesRegex(EOFError, "authorized length"):
            self.schedule().result(5)
        self.assertFalse(list(self.root.rglob("*.part")))
        self.assertFalse(list(self.root.rglob("source.mov")))
        self.assertEqual(broker.count("POST", broker.route), 0)
        broker.truncated = False
        broker.transient = True
        self.schedule().result(5)
        self.assertEqual(broker.count("GET", broker.original), 4)
        self.assertEqual(broker.count("POST", broker.route), 1)

    def test_private_cache_isolation_and_broker_compatibility(self):
        self.enter(patch.object(worker, "make_review_media", self.encoder))
        broker = self.broker
        broker.supported = False
        self.assertEqual(self.schedule().result(5), {"state": "unsupported"})
        self.assertEqual(broker.requests, [("GET", "/api/v1/reviews/capabilities")])
        broker.supported = True
        broker.upload_url = "https://other.example.test/media"
        with self.assertRaises(ValueError):
            self.schedule().result(5)
        broker.upload_url = broker.route
        for owner in (18, 25):
            broker.owner = owner
            broker.ready = False
            self.schedule().result(5)
        self.assertEqual(len(list(self.root.rglob("source.mov"))), 2)
        self.assertEqual(broker.count("GET", broker.original), 2)
        with self.assertRaisesRegex(ValueError, "scope mismatch"):
            self.schedule(private=True).result(5)

    def test_credential_lookup_is_async_and_prior_account_remains_bound(self):
        entered, release = threading.Event(), threading.Event()
        def delayed_token():
            entered.set()
            self.assertTrue(release.wait(3))
            return "different-user-token"
        self.broker._load_access_token = delayed_token
        self.broker._reference_auth_digest = hashlib.sha256(b"original-user-token").hexdigest()
        future = self.schedule()
        try:
            self.assertTrue(entered.wait(2))
            self.assertFalse(future.done())
        finally:
            release.set()
        with self.assertRaisesRegex(ValueError,"account changed"):
            future.result(3)
        self.assertEqual(self.broker.requests, [])

    def test_broker_mounts_do_not_absorb_the_api_prefix(self):
        task = "job-mybox-" + "2"*32
        routes = ("/api/v1/reviews/tasks/" + task + "/workstation-media",
                  "/api/v1/reviews/tasks/" + task + "/workstation-media/heartbeat",
                  "/api/v1/only/my-box/items/" + task + "/media?download=1")
        for mount in ("", "/api", "/api/v1", "/GripTapeServer", "/studio/review"):
            origin = "https://broker.example.test" + mount
            for route in routes:
                with self.subTest(mount=mount, route=route):
                    self.assertEqual(worker._url(origin, route, task), origin + route)
                    self.assertEqual(worker._url(origin, mount + route, task), origin + route)
                    with self.assertRaises(ValueError):
                        worker._url(origin, "/other" + route, task)

    def test_16_gib_contract_and_original_container_extensions(self):
        session = worker._Session(self.broker)
        state = worker._state(session,self.broker.task)
        state["source_bytes"] = 16 * 1024**3
        with patch.object(session,"get_json",return_value=state):
            self.assertEqual(worker._state(session,self.broker.task)["source_bytes"],16 * 1024**3)
            state["source_bytes"] += 1
            with self.assertRaisesRegex(ValueError,"original identity"):
                worker._state(session,self.broker.task)
        for suffix, raw in ((".webm",b"\x1a\x45\xdf\xa3webm-video"),(".m4v",b"\0\0\0\x18ftypM4V demo"),
                            (".mp4",b"\0\0\0\x18ftypisomdemo"),(".mov",self.source)):
            broker = Broker("job-format",raw)
            session = worker._Session(broker)
            state = worker._state(session,broker.task)
            path = self.root / ("original"+suffix)
            path.write_bytes(raw)
            directory = self.root / suffix[1:]
            directory.mkdir()
            self.assertTrue(worker._original(session, broker.task, state, directory, path).samefile(path))
            self.assertFalse(any(directory.glob("source.*")))
            self.assertTrue(worker._original(session, broker.task, state, directory, None).samefile(path))
            path.unlink()
            cached = worker._original(session,broker.task,state,directory,None)
            self.assertEqual(cached.suffix,suffix)
            self.assertEqual(cached.read_bytes(),raw)
            self.assertTrue(worker._original(session, broker.task, state, directory, None).samefile(cached))
            self.assertEqual(broker.count("GET",broker.original),1)

    def test_cache_lock_coalesces_independent_worker_sessions(self):
        self.enter(patch.object(worker, "make_review_media", self.encoder))
        broker = self.broker
        broker.release.clear()
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(worker._work, worker._Session(broker), broker.task, None)
            self.assertTrue(broker.entered.wait(5))
            second = pool.submit(worker._work, worker._Session(broker), broker.task, None)
            try:
                deadline = time.monotonic() + 3
                while broker.count("GET", "/api/me") < 2 and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertEqual(broker.count("GET", "/api/me"), 2)
            finally:
                broker.release.set()
            self.assertEqual(first.result(5), second.result(5))
        self.assertEqual(broker.count("GET", broker.original), 1)
        self.assertEqual(broker.count("POST", broker.route), 1)
        self.assertEqual(self.encoded, 1)

    def test_interrupted_process_releases_lock_and_discards_partial_source(self):
        self.enter(patch.object(worker, "make_review_media", self.encoder))
        broker = self.broker
        session = worker._Session(broker)
        directory = worker._cache_directory(session, broker.task, worker._state(session, broker.task))
        # Exercise the actual OS lock lifetime across an abnormal interpreter exit.
        child = (
            "import os, sys\n"
            "from pathlib import Path\n"
            "from _hmb_client_review_media import _file_lock\n"
            "cache = Path(sys.argv[1])\n"
            "with _file_lock(cache):\n"
            "    (cache / 'source.part').write_bytes(b'partial')\n"
            "    os._exit(19)\n"
        )
        interrupted = subprocess.run([sys.executable, "-B", "-c", child, str(directory)],
                                     cwd=Path(worker.__file__).parent, timeout=10)
        self.assertEqual(interrupted.returncode, 19)
        self.assertFalse((directory / "source.mov").exists())
        self.assertEqual(self.schedule().result(5)["state"], "ready")
        self.assertEqual((directory / "source.mov").read_bytes(), self.source)
        self.assertFalse((directory / "source.part").exists())

    def test_real_ffmpeg_generated_pair(self):
        from _hmb_video_tools import _find_ffmpeg
        source = self.root / "fixture.mp4"
        subprocess.run([_find_ffmpeg(), "-hide_banner", "-loglevel", "error", "-nostdin", "-f", "lavfi", "-i",
                        "color=c=blue:s=64x48:r=24:d=0.5", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source)],
                       check=True, timeout=30)
        broker = Broker("job-draft-real-codec", source.read_bytes())
        result = self.schedule(broker, local_source=source).result(30)
        self.assertEqual(result["state"], "ready")
        self.assertEqual(broker.count("GET", broker.original), 0)
        self.assertEqual(broker.count("POST", broker.route), 1)

        # Long review cache paths are common with redirected Windows profiles.
        # Exercise real input, JPEG and MP4 paths beyond MAX_PATH.
        from PIL import Image
        from _hmb_color_lut import _review_media_tools, make_review_media
        directory = self.root
        while len(str(directory)) < 275:
            directory = directory / ("review-cache-" + "a" * 35)
        directory.mkdir(parents=True)
        long_source = directory / "source.mp4"
        long_source.write_bytes(source.read_bytes())
        poster, preview = make_review_media(long_source, directory, threading.Event(), expected_sha256=broker.sha)
        with Image.open(poster) as image:
            self.assertEqual((image.format, image.size), ("JPEG", (640, 360)))
            image.load()
        _, ffprobe = _review_media_tools()
        streams = subprocess.check_output(
            [ffprobe, "-v", "error", "-show_streams", "-of", "json", str(preview)], timeout=30)
        video = json.loads(streams)["streams"][0]
        self.assertEqual((video["codec_name"], video["width"], video["height"], video["nb_frames"]),
                         ("h264", 64, 48, "12"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
