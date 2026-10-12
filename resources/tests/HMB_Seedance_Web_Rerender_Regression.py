"""Offline web execution isolation and billing-boundary regression.

The real Generator pipeline runs against a fake Broker. No provider requests,
cloud uploads, native workflow writes or paid renders are performed.
"""
from __future__ import annotations

import asyncio
import ast
import copy
from collections import OrderedDict
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
from typing import Any, Dict, List, Optional
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hmb_seedance_clean_ci_stubs import install_clean_ci_griptape_stubs

install_clean_ci_griptape_stubs()
spec = importlib.util.spec_from_file_location("seedance_web_rerender", ROOT / "HMBSeedanceGeneration.py")
assert spec and spec.loader
target = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = target
spec.loader.exec_module(target)
target.AI_BROKER_SUBMISSION_MIN_INTERVAL_SECONDS = 0
Base, Execution = target.HMBSeedanceGeneration, target._HMBWebRerenderExecution
agent = SimpleNamespace(name="Connected HMB Agent", _hmb_run_web_rerender=lambda *a: None)
worker_spec = importlib.util.spec_from_file_location("web_rerender_worker_contract", ROOT / "_hmb_web_rerender.py")
assert worker_spec and worker_spec.loader
worker = importlib.util.module_from_spec(worker_spec)
sys.modules[worker_spec.name] = worker
worker_spec.loader.exec_module(worker)


def new_node():
    node = Base(name="Web Rerender Test")
    node.parameter_values.update({
        "model_id": target.SEEDANCE_2_0_MODEL_ID,
        "resolution": target.MODEL_DEFAULT_RESOLUTIONS[target.SEEDANCE_2_0_MODEL_ID],
        "duration": 5, "ratio": "adaptive", "prompt": "ORIGINAL PROMPT MUST STAY",
        "reference_images": ["https://example.com/first.png", "https://example.com/second.png"],
        "reference_audio": [], target.VIDEO_REFERENCES_PARAMETER: [],
        "generate_audio": False, "watermark": False, "priority": 0,
        "poll_interval_seconds": 1, "generation_timeout_seconds": 30,
        "execution_expires_after": 86400, "output_format": "mp4", "return_last_frame": False,
        "first_frame": None, "last_frame": None,
    })
    node.parameter_output_values.update(generation_id="original-task", generation_status="succeeded",
                                       video_url=target.VideoUrlArtifact(value="C:/original.mp4"))
    node._web_original_parameters = copy.deepcopy(node.parameter_values)
    node._web_original_outputs = target._web_rerender_plain(dict(node.parameter_output_values))
    return node


def unchanged(node):
    assert node.parameter_values == node._web_original_parameters, "Web execution mutated native authoring values"
    assert target._web_rerender_plain(dict(node.parameter_output_values)) == node._web_original_outputs, "Web execution overwrote original Task outputs"
    assert not node._generation_run_active.is_set(), "Web execution leaked its shared Run reservation"


def result(text="WEB AGENT RESULT {{LITERAL}}"):
    return {"text": text, "run_id": "agent-web-1", "output_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "policy_identity": {"version": "signed-policy"}, "observation": {"status": "observed"}}


async def fake_save(self, final_task, generation_id, destination, *args, **kwargs):
    self.parameter_output_values.update(generation_id=generation_id, generation_status="succeeded",
                                       video_url=target.VideoUrlArtifact(value=str(self._output_file.path)))
    self._set_generation_recovery_checkpoint(stage="local_succeeded", task_id=generation_id,
        task_identity="broker_task", status="succeeded", params=self._web_params)
    await self._force_save_generation_recovery_checkpoint(required=False, reason="local_succeeded")


class Broker:
    def __init__(self, checkpoints):
        self.calls, self.checkpoints = [], checkpoints
    def account_snapshot(self, **kwargs):
        return SimpleNamespace(connected=True)
    def generate_seedance(self, payload, **kwargs):
        assert self.checkpoints and self.checkpoints[-1][1] == "pre_submit", "Create preceded durable identity"
        assert self.checkpoints[-1][0]["client_request_id"] == payload["client_request_id"]
        self.calls.append(copy.deepcopy(payload))
        return {"job_id": "web-new-task", "status": "succeeded", "video_url": "https://example.com/new.mp4"}


async def checks(root):
    count = source_readiness_contracts()
    node = new_node()
    original_get = Base.get_parameter_value
    def no_prompt_read(self, name):
        assert name != "prompt", "Snapshot consulted the original authored Prompt"
        return original_get(self, name)
    with mock.patch.object(Base, "get_parameter_value", no_prompt_read):
        snapshot = node._hmb_web_rerender_capture_inputs()
    assert "prompt" not in snapshot["params"]
    assert snapshot["params"]["reference_images"] == node.parameter_values["reference_images"]
    assert snapshot["generation_settings"]["priority"] == 0
    assert snapshot["generation_settings"]["generate_audio"] is False
    assert "_hmb_broker_server_url" not in snapshot["generation_settings"]
    unchanged(node)
    count += 1

    checkpoints = []
    def sink(checkpoint, *, reason, required):
        checkpoints.append((copy.deepcopy(checkpoint), reason, required))
    bridge = Broker(checkpoints)
    async with node._hmb_web_rerender_claim(snapshot) as claim:
        assert node._generation_run_active.is_set()
        assert not node._hmb_web_rerender_readiness()["ready"]
        native = mock.AsyncMock()
        with mock.patch.object(Base, "_aprocess_impl", native):
            await node.aprocess()
            native.assert_not_called()
        try:
            async with node._hmb_web_rerender_claim(snapshot):
                raise AssertionError("Duplicate claim was admitted")
        except RuntimeError as exc:
            assert "busy" in str(exc)
        await node._hmb_web_rerender_prepare_media(claim)
        response = await node._hmb_web_rerender_execute(claim, result(), client_request_id="hmb-fixed-web-1",
            output_directory=root / "outputs", checkpoint_sink=sink, submission_bridge=bridge,
            parent_task_id="original-task", command_id="command-one")
        assert response["task_id"] == "web-new-task" and response["parent_task_id"] == "original-task"
        assert len(bridge.calls) == 1 and bridge.calls[0]["client_request_id"] == "hmb-fixed-web-1"
        assert bridge.calls[0]["prompt"] == result()["text"]
        assert bridge.calls[0]["image_urls"] == snapshot["params"]["reference_images"]
        try:
            await node._hmb_web_rerender_execute(claim, result(), client_request_id="hmb-fixed-web-1",
                output_directory=root, checkpoint_sink=sink, submission_bridge=bridge)
            raise AssertionError("Same claim rendered twice")
        except RuntimeError as exc:
            assert "already been executed" in str(exc)
    unchanged(node)
    count += 1

    # Keep the production bridge's field filtering, JSON encoding, headers and
    # response validation active through the final POST boundary.
    node = new_node()
    snapshot = node._hmb_web_rerender_capture_inputs()
    checkpoints = []
    wire_calls = []
    class Response(io.BytesIO):
        status = 200
        def geturl(self):
            return target.AI_BROKER_INTERNAL_ORIGIN + "/api/v1/generate/video"
    class Opener:
        def open(self, request, *, timeout):
            body = json.loads(request.data)
            assert request.full_url.endswith("/api/v1/generate/video") and request.get_method() == "POST"
            assert request.get_header("Idempotency-key") == body["client_request_id"] == "hmb-wire-intent"
            assert body["prompt"] == "  WEB {{LITERAL}} \n"
            assert body["priority"] == 0 and body["generate_audio"] is False and body["watermark"] is False
            assert checkpoints[-1][1] == "pre_submit"
            wire_calls.append(body)
            return Response(json.dumps({"job_id": "web-new-task", "status": "succeeded", "video_url": "https://example.com/new.mp4"}).encode())
    wire_bridge = target._HMBAIBrokerBridge(opener=Opener(), server_url=target.AI_BROKER_INTERNAL_ORIGIN)
    wire_bridge._load_access_token = lambda: "offline-test"
    wire_bridge.account_snapshot = lambda **kwargs: SimpleNamespace(connected=True)
    async with node._hmb_web_rerender_claim(snapshot) as claim:
        await node._hmb_web_rerender_prepare_media(claim)
        response = await node._hmb_web_rerender_execute(claim, result("  WEB {{LITERAL}} \n"), client_request_id="hmb-wire-intent",
            output_directory=root, checkpoint_sink=sink, submission_bridge=wire_bridge)
    assert len(wire_calls) == 1 and response["task_id"] == "web-new-task"
    unchanged(node)
    count += 1

    count += await command_submission_contracts(root)

    for field, value in (("duration", 4), ("reference_images", ["https://example.com/changed.png"]),
                         (target.SHOT_UUID_PARAMETER, "abfda38b-2308-42c7-9db9-679207a2d70b")):
        node = new_node()
        snapshot = node._hmb_web_rerender_capture_inputs()
        async with node._hmb_web_rerender_claim(snapshot) as claim:
            node.parameter_values[field] = value
            try:
                node._hmb_web_rerender_validate_claim(claim)
                raise AssertionError("Changed input was accepted")
            except (RuntimeError, ValueError):
                pass
        count += 1

    node = new_node()
    local = root / "reference.png"
    local.write_bytes(b"original bytes")
    node.parameter_values["reference_images"] = [str(local)]
    snapshot = node._hmb_web_rerender_capture_inputs()
    async with node._hmb_web_rerender_claim(snapshot) as claim:
        await node._hmb_web_rerender_prepare_media(claim)
        local.write_bytes(b"different bytes")
        try:
            await node._hmb_web_rerender_prepare_media(claim)
            raise AssertionError("Mutated media was accepted")
        except RuntimeError as exc:
            assert "reference changed" in str(exc)
    count += 1

    node = new_node()
    snapshot = node._hmb_web_rerender_capture_inputs()
    def failed_sink(*args, **kwargs):
        raise OSError("simulated journal disk failure")
    failed_bridge = Broker([])
    async with node._hmb_web_rerender_claim(snapshot) as claim:
        await node._hmb_web_rerender_prepare_media(claim)
        try:
            await node._hmb_web_rerender_execute(claim, result(), client_request_id="hmb-fixed-web-2",
                output_directory=root, checkpoint_sink=failed_sink, submission_bridge=failed_bridge)
            raise AssertionError("Unpersisted render was allowed")
        except OSError:
            pass
    assert not failed_bridge.calls
    unchanged(node)
    count += 1

    node = new_node()
    snapshot = node._hmb_web_rerender_capture_inputs()
    tampered = copy.deepcopy(snapshot)
    tampered["params"]["duration"] = 4
    try:
        async with node._hmb_web_rerender_claim(tampered):
            raise AssertionError("A tampered snapshot retained its authority")
    except RuntimeError:
        pass
    unchanged(node)
    count += 1

    node = new_node()
    snapshot = node._hmb_web_rerender_capture_inputs()
    checkpoints = []
    uncertain = Broker(checkpoints)
    def unknown_create(payload, **kwargs):
        uncertain.calls.append(copy.deepcopy(payload))
        raise target._BrokerUnavailableError("synthetic timeout", submission_outcome_unknown=True)
    uncertain.generate_seedance = unknown_create
    async with node._hmb_web_rerender_claim(snapshot) as claim:
        await node._hmb_web_rerender_prepare_media(claim)
        try:
            await node._hmb_web_rerender_execute(claim, result(), client_request_id="hmb-fixed-unknown",
                output_directory=root, checkpoint_sink=sink, submission_bridge=uncertain)
            raise AssertionError("An unknown submission was reported as success")
        except target._BrokerUnavailableError:
            pass
    assert len(uncertain.calls) == 1
    assert checkpoints[-1][0]["task_id"] == "hmb-fixed-unknown"
    assert checkpoints[-1][0]["status"] == "submission_unknown"
    unchanged(node)
    count += 1

    node = new_node()
    snapshot = node._hmb_web_rerender_capture_inputs()
    checkpoints = []
    gated = Broker(checkpoints)
    loop = asyncio.get_running_loop()
    def change_during_cadence():
        # This callback runs on the HTTP worker; the authoritative recheck
        # must return to the engine loop after the queued user edit.
        loop.call_soon_threadsafe(node.parameter_values.__setitem__, "duration", 4)
    async with node._hmb_web_rerender_claim(snapshot) as claim:
        await node._hmb_web_rerender_prepare_media(claim)
        with mock.patch.object(target, "_broker_wait_for_submission_slot", change_during_cadence):
            try:
                await node._hmb_web_rerender_execute(claim, result(), client_request_id="hmb-fixed-stale",
                    output_directory=root, checkpoint_sink=sink, submission_bridge=gated)
                raise AssertionError("Stale inputs crossed the create boundary")
            except target._AgentResultUnavailable:
                pass
    assert not gated.calls
    count += 1

    node = new_node()
    snapshot = node._hmb_web_rerender_capture_inputs()
    node.parameter_values["reference_images"] = [str(root / "not-yet-available.png")]
    with mock.patch.object(Path, "is_file", side_effect=AssertionError("Readiness touched filesystem")):
        fast = node._hmb_web_rerender_capture_inputs()
    async with node._hmb_web_rerender_claim(fast) as claim:
        try:
            await node._hmb_web_rerender_prepare_media(claim)
            raise AssertionError("Missing media was accepted for execution")
        except ValueError as exc:
            assert "no longer available" in str(exc)
    count += 1

    node = new_node()
    snapshot = node._hmb_web_rerender_capture_inputs()
    async with node._hmb_web_rerender_claim(snapshot) as claim:
        await node._hmb_web_rerender_prepare_media(claim)
        node._hmb_node_deleted = True
        try:
            node._hmb_web_rerender_validate_claim(claim)
            raise AssertionError("Deleted target retained authority")
        except RuntimeError:
            pass
    count += 1
    assert Base._new_generation_client_request_id(node) != Base._new_generation_client_request_id(node)
    print(f"PASS web rerender Generator isolation: {count} cases; provider calls=0")


async def command_submission_contracts(root):
    """Real pipeline, bridge filter and web fence through the final fake POST."""
    raw = result("  WEB {{LITERAL}} \n")
    finish = "Character Beauty: brightness 0, glow OFF. {{FINISH_LITERAL}}"
    composed = Base._compose_finish_look_prompt(raw["text"], finish)
    source_resolver = Execution._resolve_exact_shot_generation_inputs
    def resolve_snapshot(self, params):
        resolved = source_resolver(self, params)
        # Model a verified connected Finish Look publication; all subsequent
        # snapshot checks, payload composition and HTTP code are production.
        if not self._web_request:
            resolved["_hmb_finish_look_out"] = finish
        return resolved
    checkpoints, prepared, transitions, wire_calls = [], [], [], []
    def sink(checkpoint, *, reason, required):
        checkpoints.append((copy.deepcopy(checkpoint), reason, required))
    command = {"render_key": "hmb-wire-finish-intent", "operation_id": "web-operation",
               "lease_id": "web-lease", "fence": 7}
    lease = threading.Event()
    lease.set()
    class Response(io.BytesIO):
        status = 200
        def geturl(self):
            return target.AI_BROKER_INTERNAL_ORIGIN + "/api/v1/generate/video"
    class Opener:
        def open(self, request, *, timeout):
            body = json.loads(request.data)
            assert request.full_url.endswith("/api/v1/generate/video") and request.get_method() == "POST"
            assert request.get_header("Idempotency-key") == body["client_request_id"] == command["render_key"]
            assert request.get_header("X-hmb-rerender-operation") == command["operation_id"]
            assert request.get_header("X-hmb-rerender-lease") == command["lease_id"]
            assert request.get_header("X-hmb-rerender-fence") == str(command["fence"])
            assert body["prompt"] == composed and raw["text"] in body["prompt"] and finish in body["prompt"]
            assert body["priority"] == 0 and body["generate_audio"] is False and body["watermark"] is False
            assert not any(key.startswith("_hmb_") for key in body), "Private snapshot fields leaked into provider request"
            assert checkpoints[-1][1] == "pre_submit"
            assert prepared == [{"agent_output": raw["text"], "agent_output_sha256": raw["output_sha256"],
                                 "render_payload_sha256": worker.request_fingerprint(body)}]
            assert transitions == [("local-operation", {"render_preparing"}, "submitting")]
            wire_calls.append(body)
            return Response(json.dumps({"job_id": "web-finish-task", "status": "succeeded",
                                        "video_url": "https://example.com/new.mp4"}).encode())
    bare = target._HMBAIBrokerBridge(opener=Opener(), server_url=target.AI_BROKER_INTERNAL_ORIGIN)
    bare._load_access_token = lambda: "offline-test"
    bare.account_snapshot = lambda **kwargs: SimpleNamespace(connected=True)
    def record_prepared(received_command, event, **fields):
        assert received_command == command and event == "prepared"
        prepared.append(fields)
    protocol = SimpleNamespace(bridge=bare, result=record_prepared)
    journal = SimpleNamespace(transition=lambda *args: transitions.append(args))
    bridge = worker.command_bridge(protocol, command, journal, "local-operation", raw, lease,
                                   submitted_prompt=composed)
    with mock.patch.object(Execution, "_resolve_exact_shot_generation_inputs", resolve_snapshot):
        node = new_node()
        snapshot = node._hmb_web_rerender_capture_inputs()
        assert snapshot["params"]["_hmb_finish_look_out"] == finish
        async with node._hmb_web_rerender_claim(snapshot) as claim:
            await node._hmb_web_rerender_prepare_media(claim)
            response = await node._hmb_web_rerender_execute(claim, raw,
                client_request_id=command["render_key"], output_directory=root,
                checkpoint_sink=sink, submission_bridge=bridge, parent_task_id="original-task")
    assert len(wire_calls) == 1 and response["task_id"] == "web-finish-task"
    assert raw == result("  WEB {{LITERAL}} \n"), "Finish Look modified raw Agent evidence"
    unchanged(node)

    # Exercise the exact final HTTP guard with tampered raw evidence and with
    # altered submitted text. Neither may prepare, journal or POST anything.
    from urllib.request import Request
    for tampered_result, expected_prompt, reason in (
        ({**raw, "text": "forged Agent text"}, composed, "agent_result_integrity_failed"),
        (raw, composed + "forged suffix", "submitted_prompt_mismatch"),
    ):
        guarded = worker.CommandSubmissionOpener(bare._opener, protocol, command, journal,
            "local-operation", tampered_result, lease, submitted_prompt=expected_prompt)
        request = Request(bare.server_url + "/api/v1/generate/video", method="POST",
            data=json.dumps(wire_calls[0]).encode(), headers={"Idempotency-key": command["render_key"]})
        try:
            guarded.open(request, timeout=1)
            raise AssertionError("Tampered Agent evidence crossed the final HTTP guard")
        except ValueError as exc:
            assert reason in str(exc)
    assert len(wire_calls) == len(prepared) == len(transitions) == 1
    return 3


def source_readiness_contracts():
    """Exercise the actual source method bodies with filesystem traps."""
    tree = ast.parse((ROOT / "HMBVideoPickerLibrary.py").read_text(encoding="utf-8-sig"))
    picker_cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "HMBVideoPickerLibrary")
    methods = [node for node in picker_cls.body if isinstance(node, ast.FunctionDef) and node.name in {
        "_hmb_shot_routing_snapshot", "_hmb_shot_routing_snapshot_locked"}]
    selector = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_select_synchronized_video_media")
    probes = []
    def probe(*args, **kwargs):
        probes.append(True)
        return None
    def outputs(state, *, enforce_media_availability, probe_cache):
        assert enforce_media_availability is False, "Fast view's nested output builder re-enabled filesystem checks"
        return {}, [row["video_path"] for row in state["videos"] if row["selected"]]
    scope = {"Any": Any, "Dict": Dict, "List": List, "Optional": Optional, "Path": Path,
             "threading": threading, "hashlib": hashlib, "_clean": lambda value: str(value or ""),
             "_uuid_text": lambda value: str(value or ""), "_parse_state": copy.deepcopy,
             "_state_sync_local": lambda node: SimpleNamespace(), "_sha256_canonical": target._web_rerender_digest,
             "_is_remote_video_reference": lambda value: value.startswith("https://"),
             "_resolve_readable_video_reference": probe,
             "_picker_representative_video_uids": lambda selected, preview: list(selected),
             "SHOT_ROUTING_SNAPSHOT_SCHEMA": "hmb-picker-shot-routing-snapshot", "SHOT_ROUTING_SNAPSHOT_VERSION": 1,
             "_build_synchronized_video_outputs": outputs}
    executable = ast.Module(body=[selector, ast.ClassDef(name="PickerRead", bases=[], keywords=[], body=methods, decorator_list=[])], type_ignores=[])
    exec(compile(ast.fix_missing_locations(executable), "<production-picker-readiness>", "exec"), scope)
    picker = scope["PickerRead"]()
    state = {"channel_uuid": "channel", "shot_publisher_instance_uuid": "publisher",
             "videos": [{"video_uid": "video-one", "video_path": "C:/not-present/video.mp4"}],
             "picker_shots": [{"bound_shot_uuid": "shot", "selected_video_uids": ["video-one"]}]}
    picker._picker_state = lambda: copy.deepcopy(state)
    picker._hmb_shot_catalog_snapshot = {"channel_uuid": "channel", "publisher_instance_uuid": "publisher",
                                         "shots": [{"shot_uuid": "shot", "number": 1, "name": "Shot 1"}]}
    picker._hmb_picker_publisher_uuid = "picker"
    picker._shot_video_metadata = lambda row: {}
    picker._hmb_allocate_shot_snapshot_generation = lambda identity: (_ for _ in ()).throw(AssertionError("Fast read advanced generation"))
    snapshot = picker._hmb_shot_routing_snapshot("channel", validate_media=False)
    assert snapshot["media_by_source_uid"]["video-one"] == "C:/not-present/video.mp4" and not probes
    try:
        picker._hmb_shot_routing_snapshot("channel")
        raise AssertionError("Ordinary Picker availability checks were bypassed")
    except ValueError as exc:
        assert "unavailable" in str(exc) and probes

    tree = ast.parse((ROOT / "HMBImageAssetLibrary.py").read_text(encoding="utf-8-sig"))
    image_cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "HMBImageAssetLibrary")
    method = next(node for node in image_cls.body if isinstance(node, ast.FunctionDef) and node.name == "_cache_shot_routing_snapshot")
    image_scope = {"Any": Any, "Dict": Dict, "OrderedDict": OrderedDict, "_normalize_state": copy.deepcopy,
                   "_non_negative_int": lambda value: int(value or 0), "_sha256_canonical": lambda value: "same-memory-identity",
                   "_project_output_fingerprint": lambda *args: "memory-only",
                   "_apply_shot_routing_state_facts": lambda *args: None,
                   "_build_shot_routing_snapshot": lambda *a, **kw: (_ for _ in ()).throw(AssertionError("Readiness resolved project files"))}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])), "<production-image-readiness>", "exec"), image_scope)
    image = SimpleNamespace(_hmb_resolution_cache=OrderedDict())
    state = {"shot_routing": {"publisher_instance_uuid": "publisher", "channel_uuid": "channel", "shots": []}}
    try:
        image_scope["_cache_shot_routing_snapshot"](image, state, cached_only=True)
        raise AssertionError("Unpublished ImageAsset state was declared ready")
    except ValueError as exc:
        assert "preparing" in str(exc)
    image._hmb_shot_routing_input_identity = "same-memory-identity"
    image._hmb_shot_routing_cache = {"safe": "cached snapshot"}
    assert image_scope["_cache_shot_routing_snapshot"](image, state, cached_only=True) == image._hmb_shot_routing_cache
    return 2


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="hmb-web-generator-") as temp, \
         mock.patch.dict(os.environ, {"LOCALAPPDATA": temp}), \
         mock.patch.object(Base, "_runtime_node_is_live", lambda self, **kw: not self._hmb_node_deleted), \
         mock.patch.object(Base, "_manual_agent_prompt_source", lambda self: agent), \
         mock.patch.object(Base, "_exact_incoming_source", lambda self, *a, **kw: None), \
         mock.patch.object(Base, "_has_incoming_parameter_connection", lambda self, name: False), \
         mock.patch.object(Base, "_generation_recovery_blocks_new_submission", lambda self: False), \
         mock.patch.object(target.GriptapeNodes, "NodeManager", lambda: SimpleNamespace(get_node_parent_flow_by_name=lambda name: "flow-web"), create=True), \
         mock.patch.object(Execution, "_preflight_output_destination", lambda *a, **kw: None), \
         mock.patch.object(Execution, "_prepare_video_references_for_run", lambda self, params: params), \
         mock.patch.object(Execution, "_save_completed_task", fake_save), \
         mock.patch.object(target._HMBWebRerenderOutput, "build_file", lambda self: object()), \
         mock.patch.object(target, "_resolve_mp4_decode_verifier", lambda: SimpleNamespace(executable="offline", backend="offline")), \
         mock.patch.object(target, "_get_build_diagnostics", lambda: {}):
        asyncio.run(checks(Path(temp)))
