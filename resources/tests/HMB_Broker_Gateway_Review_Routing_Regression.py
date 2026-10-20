"""Offline gateway routing, immutable Task pins and web lease boundaries."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import _hmb_review as review
import _hmb_web_rerender as web
import HMB_Web_Rerender_Worker_Regression as fixtures


def deny_network(*_args, **_kwargs):
    raise AssertionError("Gateway regressions must not contact a real server")


class GatewayReviewRouting(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="hmb-gateway-review-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.journal = web.OperationJournal(self.root / "journal")
        for target in ("socket.create_connection", "socket.socket.connect"):
            guard = patch(target, deny_network)
            guard.start()
            self.addCleanup(guard.stop)

    def test_gateway_task_pin_is_persistent_and_immutable(self):
        canonical = "https://broker.example/Gateway/tenant-a"
        for value in (canonical, canonical + "/", "https://BROKER.example:443/Gateway/tenant-a/"):
            review.bind_task_origin("job-existing", value, root=self.root)
        self.assertEqual(review.task_origin("job-existing", root=str(self.root)), canonical)
        before = {path.name: path.read_bytes() for path in self.root.rglob("*.json")}
        for value in ("https://broker.example", "https://broker.example/Gateway/tenant-b",
                      "https://other.example/Gateway/tenant-a"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "immutable"):
                review.bind_task_origin("job-existing", value, root=self.root)
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.root.rglob("*.json")})
        # No address, credential or path is added to public production evidence.
        self.assertNotIn("broker.example", json.dumps(review.public_evidence({})))

    def test_equivalent_legacy_pin_is_not_rewritten(self):
        # Pre-gateway evidence stored the supplied origin verbatim. Retain it
        # while accepting equivalent DNS casing and the default HTTPS port.
        legacy = "https://BROKER.example:443"
        filename = hashlib.sha256(b"job-legacy-pin").hexdigest() + ".json"
        path = self.root / "task-origins" / filename
        review._write(path, {"schema": "hmb-private-task-origin", "version": 1,
                             "task_id": "job-legacy-pin", "origin": legacy})
        before = path.read_bytes()
        review.bind_task_origin("job-legacy-pin", "https://broker.example/", root=self.root)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(review.task_origin("job-legacy-pin", root=self.root), legacy)

    def test_malformed_task_pin_never_becomes_routing_authority(self):
        invalid = ("", "https://user:secret@broker.example/Gateway", "https://broker.example/Gateway?token=x",
                   "https://broker.example/Gateway#fragment", "https://broker.example/Gateway/../other",
                   "https://broker.example/Gateway/%2e%2e/other", "https://broker.example/Gateway\\other",
                   "http://broker.example/Gateway")
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                review.bind_task_origin("job-invalid", value, root=self.root)
        self.assertFalse((self.root / "task-origins").exists())
        approved_internal = "http://192.168.203.245:8080"
        review.bind_task_origin("job-legacy-internal", approved_internal, root=self.root)
        self.assertEqual(review.task_origin("job-legacy-internal", root=self.root), approved_internal)

    async def test_parent_readiness_keeps_gateway_path_identity(self):
        engine = fixtures.Engine()
        worker = web.EngineWorker(engine, self.journal)
        base = "https://broker.example/Gateway/tenant-a"
        cases = (
            (base, base, base, "job-parent"),
            (base + "/", "https://BROKER.example:443/Gateway/tenant-a/", base, "job-parent"),
            (base, "", base, "job-parent"),
            ("", base, base, "job-parent"),
            (base, base, "https://broker.example/Gateway/tenant-b", ""),
            (base, base, "https://broker.example", ""),
            (base, "https://broker.example/Gateway/tenant-b", base, ""),
            (base, "https://broker.example/Gateway/%2e%2e", base, ""),
        )
        for pinned, saved, selected, expected in cases:
            node = SimpleNamespace(parameter_output_values={"generation_id": "job-parent"})
            checkpoint = {"task_id": "job-parent", "broker_server_url": saved}
            node.get_parameter_value = lambda _key: checkpoint
            before = deepcopy((node.parameter_output_values, checkpoint))
            with self.subTest(pinned=pinned, saved=saved, selected=selected), \
                    patch.object(web._review, "task_origin", return_value=pinned):
                self.assertEqual(await worker._parent_task_id(node, selected), expected)
            self.assertEqual(before, (node.parameter_output_values, checkpoint))

    async def test_gateway_submission_replay_and_ambiguous_result_do_not_repeat(self):
        for fail_after_submit in (False, True):
            with self.subTest(fail_after_submit=fail_after_submit):
                engine = fixtures.Engine()
                node, agent, protocol = fixtures.Generator(), fixtures.Agent(), fixtures.Protocol()
                protocol.bridge.server_url = "https://broker.example/Gateway/tenant-a"
                wire_headers = []
                underlying_open = protocol.open
                def capture_request(request, *, timeout):
                    wire_headers.append(dict(request.header_items()))
                    return underlying_open(request, timeout=timeout)
                protocol.bridge._opener = SimpleNamespace(open=capture_request)
                node.fail_after_post = fail_after_submit
                command = fixtures.command()
                snapshot = {"params": {}, "generation_settings": {"seed": 0, "generate_audio": False}}
                worker = web.EngineWorker(engine, self.journal)
                original = deepcopy((node.original, agent.original))
                await worker.execute(node, agent, snapshot, protocol, command)
                self.assertEqual(len(protocol.posts), 1)
                self.assertEqual(protocol.posts[0][0], protocol.bridge.server_url + "/api/v1/generate/video")
                self.assertEqual(wire_headers[0]["X-hmb-rerender-operation"], command["operation_id"])
                self.assertEqual(wire_headers[0]["X-hmb-rerender-lease"], command["lease_id"])
                self.assertEqual(wire_headers[0]["X-hmb-rerender-fence"], str(command["fence"]))
                self.assertEqual([event[0] for event in protocol.events][:2], ["agent_started", "prepared"])
                key = self.journal.key(protocol.bridge.server_url, protocol.owner_key, command["operation_id"])
                state = self.journal.read(key)["state"]
                self.assertEqual(state, "uncertain" if fail_after_submit else "completed")
                # A process restart can inspect the same record, but cannot create another job.
                restarted = web.EngineWorker(engine, web.OperationJournal(self.journal.root))
                await restarted.execute(node, agent, snapshot, protocol, command)
                self.assertEqual((agent.calls, node.executions, len(protocol.posts)), (1, 1, 1))
                self.assertEqual(original, (node.original, agent.original))

    async def test_same_host_gateway_switch_fences_old_lease_and_lineage(self):
        await fixtures.broker_origin_rotation(
            "https://broker.example/Gateway/tenant-a", "https://broker.example/Gateway/tenant-b")


if __name__ == "__main__":
    unittest.main(verbosity=2)
