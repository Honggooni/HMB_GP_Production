"""Offline project routing, immutable history, and web billing-boundary checks."""
from __future__ import annotations

import asyncio
from copy import deepcopy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.request import Request
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))
import _hmb_review as review
import _hmb_web_rerender as web
from _hmb_web_rerender_settings_fixtures import freeze_command
from _hmb_project import PROJECTS, resolve_project
from _hmb_seedance_clean_ci_stubs import install_clean_ci_griptape_stubs

install_clean_ci_griptape_stubs()
spec = importlib.util.spec_from_file_location("project_generator_fixture", ROOT / "resources/tests/HMB_Seedance_Web_Rerender_Regression.py")
fixture = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fixture
spec.loader.exec_module(fixture)
generator = fixture.target
source_spec = importlib.util.spec_from_file_location(
    "project_registered_source_fixture", Path(__file__).with_name("HMB_Seedance_Project_Source_Routing_Regression.py"))
source_fixture = importlib.util.module_from_spec(source_spec)
sys.modules[source_spec.name] = source_fixture
source_spec.loader.exec_module(source_fixture)


def public(project="superwings12"):
    return {key: PROJECTS[project][key] for key in ("project_id", "project_name")}


def command(project="superwings12"):
    operation, target, session, lease = [str(uuid4()) for _ in range(4)]
    prompt = "Original final prompt + review 수정 {{literal}}"
    return freeze_command({"operation_id": operation, "target_id": target, "session_id": session,
            "lease_id": lease, "fence": 1, "render_key": "hmb-web-rerender-" + operation,
            "parent_task_id": "job-parent", "review_id": str(uuid4()), "state": "claimed",
            "snapshot_sha256": "a" * 64, "web_prompt": prompt,
            "web_prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "exclude_authored_prompt": True, "preserve_connected_sources": True,
            "policy_required": False, "input_mode": "web_only",
            "policy_application": "preserved_parent", "policy_reinjected": False,
            **public(project)})


class ProjectRegression(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="hmb-project-routing-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_casecard_project_is_path_free_and_roundtrips(self):
        for project in PROJECTS:
            with self.subTest(project=project):
                params = {**public(project), "seed": 0, "generate_audio": False,
                          "prompt": "UNMODIFIED", "reference_images": ["https://private.example/source?secret=yes"]}
                original = deepcopy(params)
                inputs = review.capture_inputs(params)
                case = review.start_case("request-" + project, inputs, params["prompt"], {}, {}, root=self.root)
                review.update_case("job-" + project, case_id=case, status="succeeded", root=self.root)
                evidence = review.public_evidence(review.read_case("job-" + project, root=self.root))
                self.assertEqual({key: evidence[key] for key in public(project)}, public(project))
                self.assertEqual(review.public_evidence(evidence), evidence)
                self.assertNotIn("private.example", json.dumps(evidence))
                self.assertEqual(params, original)
                self.assertEqual(evidence["settings"]["seed"], 0)
                self.assertIs(evidence["settings"]["generate_audio"], False)

    def test_task_project_is_immutable_and_legacy_is_sw12(self):
        self.assertEqual(review.task_project("job-historical", root=self.root), resolve_project())
        self.assertFalse((self.root / "task-projects").exists())
        for project in PROJECTS:
            task = "job-" + project
            review.bind_task_project(task, public(project), root=self.root)
            review.bind_task_project(task, public(project), root=self.root)
            self.assertEqual(review.task_project(task, root=self.root), resolve_project(project))
            other = "dinoster5" if project != "dinoster5" else "katuri8"
            with self.assertRaisesRegex(ValueError, "immutable"):
                review.bind_task_project(task, public(other), root=self.root)
            self.assertEqual(review.task_project(task, root=self.root), resolve_project(project))
        path = self.root / "task-projects" / (hashlib.sha256(b"job-bad").hexdigest() + ".json")
        path.write_text('{"schema":"hmb-private-task-project","task_id":"job-bad","project_id":"unknown"}')
        with self.assertRaises(ValueError):
            review.task_project("job-bad", root=self.root)

    def test_connected_source_never_falls_back_to_another_project(self):
        node = fixture.new_node()
        del node._capture_imageasset_project_selection
        graph = source_fixture.Graph(node)
        source = graph.direct(hidden=True)
        for project in PROJECTS:
            source.project = project
            with graph.context():
                self.assertEqual(node._hmb_generation_project(), public(project))
        for value in ({}, {"project_id": "unknown"}, {"project_id": "Katuri8", "project_name": "다이노스터"}):
            source.project = value
            with graph.context(), self.assertRaises(ValueError):
                node._hmb_generation_project()
        graph.edges[node.name] = []
        with graph.context(), self.assertRaises(ValueError):
            node._hmb_generation_project()
        fixture.unchanged(node)

    def test_source_snapshot_project_participates_in_integrity_hash(self):
        channel, shot_id, publisher = [str(uuid4()) for _ in range(3)]
        metadata = {"channel_uuid": channel, "generation": 1, "shots": [{
            "shot_uuid": shot_id, "number": 1, "name": "Shot 1", "revision": 1,
            "selected_source_uids": []}], "ordered_assets": []}
        snapshot = {"schema": "hmb-shot-routing-snapshot", "version": 1,
                    "publisher_instance_uuid": publisher, **metadata,
                    "metadata_sha256": generator.HMBSeedanceGeneration._canonical_sha256(metadata),
                    "media_sha256": generator.HMBSeedanceGeneration._canonical_sha256({"media_descriptors": []}),
                    "media_by_source_uid": {}}
        validate = lambda value: generator.HMBSeedanceGeneration._validate_direct_media_snapshot(
            value, source_kind="image_asset", expected_channel_uuid=channel)
        self.assertNotIn("project_id", validate(snapshot))  # v79 publication remains accepted.
        for project in PROJECTS.values():
            current = {**snapshot, "project_id": project["project_folder"]}
            with self.assertRaisesRegex(RuntimeError, "metadata hash"):
                validate(current)
            current["metadata_sha256"] = generator.HMBSeedanceGeneration._canonical_sha256(
                {**metadata, "project_id": project["project_folder"]})
            self.assertEqual(validate(current)["project_id"], project["project_folder"])

    def test_only_public_imageasset_wire_routes_project_without_hidden_shot_wire(self):
        node = fixture.new_node()
        del node._capture_imageasset_project_selection
        original = deepcopy(node.parameter_values)
        graph = source_fixture.Graph(node)
        source = graph.direct()
        connection = graph.edges[node.name][0]
        with graph.context():
            for project in PROJECTS:
                source.project = project
                self.assertEqual(node._hmb_generation_project(), public(project))
            source.project = {}
            with self.assertRaises(ValueError):
                node._hmb_generation_project()
            source.project = "unrecognized"
            with self.assertRaises(ValueError):
                node._hmb_generation_project()
            source.project = "katuri8"
            connection.source_parameter_name = "not_image_output"
            with self.assertRaises(ValueError):
                node._hmb_generation_project()
            connection.source_parameter_name = "IMAGE_OUT"
            hidden = graph.add(source_fixture.HMBImageAssetLibrary('Hidden', 'superwings12'))
            graph.edge(hidden, 'SHOT_ASSET_OUT', node, 'SHOT_ASSET_IN')
            with self.assertRaisesRegex(ValueError, "different projects"):
                node._hmb_generation_project()
        self.assertEqual(node.parameter_values, original)

    def test_generator_build_and_actual_bridge_keep_project_metadata(self):
        node = fixture.new_node()
        for project in PROJECTS:
            for model in generator.BROKER_SUPPORTED_MODEL_IDS:
                with self.subTest(project=project, model=model):
                    params = {**node._get_parameters(), **public(project), "model_id": model,
                              "resolution": generator.MODEL_DEFAULT_RESOLUTIONS[model], "duration": 5,
                              "task": generator.TASK_TEXT_ONLY, "input_mode": generator.INPUT_MODE_TEXT_ONLY,
                              "reference_images": [], "video_references": [], "reference_audio": []}
                    original = deepcopy(params)
                    payload = node._build_broker_payload(params)
                    self.assertEqual({key: payload[key] for key in public(project)}, public(project))
                    wire = []
                    bridge = generator._HMBAIBrokerBridge(server_url="https://broker.invalid")
                    bridge._request_json = lambda method, route, **kw: wire.append(deepcopy(kw["payload"])) or {"job_id": "job-new"}
                    bridge.generate_seedance(payload, timeout=1)
                    self.assertEqual({key: wire[0][key] for key in public(project)}, public(project))
                    self.assertEqual(wire[0]["prompt"], params["prompt"])
                    self.assertEqual(params, original)
                    with self.assertRaises(ValueError):
                        node._build_broker_payload({**params, "project_name": public("katuri8" if project != "katuri8" else "dinoster5")["project_name"]})

    def test_capability_discovery_is_read_only_before_registration(self):
        current = command()
        calls = []
        capability = {"parent_settings_contract": web.PARENT_SETTINGS_SCHEMA, "project_routing": {"schema": web.PROJECT_ROUTING_SCHEMA, "project_ids": sorted(web.PROJECT_IDS)}}
        response = {"schema": web.PROTOCOL, "worker_id": str(uuid4()), "session_id": current["session_id"],
                    "registered": True, "user_id": 17, **capability}
        supported = False
        def request(method, route, **kwargs):
            calls.append((method, route, deepcopy(kwargs)))
            return deepcopy(capability if supported else {}) if method == "GET" else deepcopy(response)
        bridge = SimpleNamespace(_request_json=request)
        protocol = web.BrokerProtocol(bridge, response["worker_id"], response["session_id"])
        with self.assertRaisesRegex(ValueError, "project_server_upgrade_required"):
            protocol.heartbeat([public()], register=True)
        self.assertEqual([(row[0], row[1]) for row in calls], [("GET", "/api/v1/reviews/capabilities")])
        self.assertEqual(protocol.owner_key, "")
        calls.clear(); supported = True
        protocol.heartbeat([public()], register=True)
        self.assertEqual([row[0] for row in calls], ["GET", "POST"])
        self.assertEqual(calls[-1][2]["payload"]["targets"], [public()])
        self.assertTrue(protocol.project_routing_ready)
        response.pop("project_routing")
        with self.assertRaises(ValueError):
            protocol.heartbeat([public()])
        self.assertFalse(protocol.project_routing_ready)

    def test_claim_requires_exact_canonical_project_pair(self):
        current = command()
        bridge = SimpleNamespace(_request_json=lambda *a, **kw: {"command": current})
        protocol = web.BrokerProtocol(bridge, str(uuid4()), current["session_id"])
        self.assertEqual(protocol.claim(current["target_id"]), current)
        for field, value in (("project_id", None), ("project_name", None), ("project_id", "Dinoster5"),
                             ("project_id", "unknown"), ("project_name", "다이노스터"), ("project_id", 3)):
            original = deepcopy(current)
            current[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                protocol.claim(current["target_id"])
            current.clear(); current.update(original)

    def test_final_project_mismatch_cannot_prepare_or_submit(self):
        current = command()
        journal = web.OperationJournal(self.root)
        record = journal.accept(origin="https://broker.invalid", owner_key="17", command={
            **current, "command_id": current["operation_id"]})
        journal.transition(record["operation_key"], {"accepted"}, "render_preparing")
        calls = []
        protocol = SimpleNamespace(bridge=SimpleNamespace(server_url="https://broker.invalid"),
                                   result=lambda *a, **kw: calls.append((a, kw)))
        wire = SimpleNamespace(open=lambda *a, **kw: calls.append("POST"))
        live = threading.Event(); live.set()
        text = current["web_prompt"]
        agent = {"text": text, "output_sha256": hashlib.sha256(text.encode()).hexdigest(),
                 "policy_identity": {"mode": "preserved_parent", "reinjected": False}}
        for project in ("dinoster5", "katuri8"):
            opener = web.CommandSubmissionOpener(wire, protocol, current, journal, record["operation_key"], agent, live)
            payload = {"client_request_id": current["render_key"], "prompt": text, **public(project)}
            request = Request("https://broker.invalid/api/v1/generate/video", data=json.dumps(payload).encode(),
                              headers={"Idempotency-Key": current["render_key"]}, method="POST")
            with self.assertRaisesRegex(ValueError, "submitted_project_mismatch"):
                opener.open(request, timeout=1)
        self.assertEqual(calls, [])
        self.assertEqual(journal.read(record["operation_key"])["state"], "render_preparing")

    def test_descendants_cannot_cross_project_and_history_is_unchanged(self):
        journal = web.OperationJournal(self.root)
        for project in PROJECTS:
            current = command(project)
            row = journal.accept(origin="https://broker.invalid", owner_key="17", command={
                **current, "command_id": current["operation_id"]})
            journal.transition(row["operation_key"], {"accepted"}, "completed", result={"task_id": "job-" + project})
        before = journal.path.read_bytes()
        for project in PROJECTS:
            self.assertEqual(journal.descendants("https://broker.invalid", "17", "job-parent", project), ["job-" + project])
        self.assertEqual(before, journal.path.read_bytes())

    def test_project_switch_fences_old_target_and_checks_parent_and_policy(self):
        async def run():
            class Engine: pass
            class Agent: pass
            class Node: pass
            engine, agent, node = Engine(), Agent(), Node()
            policy_reads = []
            agent.name = "agent"
            agent._hmb_web_rerender_busy = lambda: False
            def policy(project_id=None):
                policy_reads.append(project_id)
                return {"ready": project_id == "superwings12", "version": "test"}
            agent._hmb_web_rerender_policy_status = policy
            engine.node_manager = SimpleNamespace(get_node_by_name=lambda name: agent)
            engine.context_manager = SimpleNamespace(get_current_workflow_name=lambda: "flow")
            node.name = "generator"; node.project = "superwings12"
            node._selected_broker_server_url = lambda: "https://broker.invalid"
            node._create_broker_bridge = lambda **kw: SimpleNamespace(server_url="https://broker.invalid", _load_access_token=lambda: "test")
            node._hmb_web_rerender_capture_inputs = lambda: {"agent_name": "agent", "target": {"flow_name": "flow"},
                "source_bindings": [], "binding_fingerprint": hashlib.sha256(node.project.encode()).hexdigest(),
                "project": public(node.project)}
            node._hmb_web_rerender_readiness = lambda: {"ready": True}
            node.parameter_output_values = {"generation_id": "job-parent"}
            node.get_parameter_value = lambda key: None
            worker = web.EngineWorker(engine, web.OperationJournal(self.root))
            with patch.object(review, "task_origin", return_value="https://broker.invalid"), \
                 patch.object(review, "task_project", return_value=resolve_project()):
                protocol, first, *_ = await worker._target(node)
                self.assertTrue(first["ready"])
                protocol.owner_key = "17"
                live = threading.Event(); live.set()
                worker.leases[first["target_id"]] = live
                worker.children[first["target_id"]] = ["job-child-sw"]
                node.project = "dinoster5"
                _, changed, *_ = await worker._target(node)
                self.assertNotEqual(changed["target_id"], first["target_id"])
                self.assertFalse(live.is_set())
                self.assertEqual(changed["parent_task_ids"], [])
                self.assertFalse(changed["ready"])
                self.assertNotIn(first["target_id"], worker.children)
                node.project = "superwings12"
                _, back, *_ = await worker._target(node)
                self.assertTrue(back["ready"])
                self.assertEqual(back["parent_task_ids"], ["job-parent"])
            self.assertEqual(policy_reads, ["superwings12", "dinoster5"])
        asyncio.run(run())


if __name__ == "__main__":
    unittest.main(verbosity=2)
