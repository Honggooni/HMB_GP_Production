"""Offline completed-video provenance and optional downstream LUT routing.

Only graph, download, decode and persistence boundaries are fixtures. Production
capture/checkpoint/completion/publication and routing methods remain real. No
Broker, DAT, workflow, application configuration or external media is accessed.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import socket
import sys
import threading
import tempfile
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hmb_seedance_clean_ci_stubs import install_clean_ci_griptape_stubs

install_clean_ci_griptape_stubs()


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


target = load("hmb_color_lut_seedance_regression", "HMBSeedanceGeneration.py")
routing = load("hmb_color_lut_routing_regression", "_hmb_shot_routing.py")
CHANNEL = "11111111-1111-4111-8111-111111111111"
OTHER_CHANNEL = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
SHOT_A = "33333333-3333-4333-8333-333333333333"
SHOT_B = "44444444-4444-4444-8444-444444444444"
INSTANCE = "55555555-5555-4555-8555-555555555555"
VIDEO = str(ROOT / "offline-provenance-result.mp4")
SOURCE = target.GENERATED_VIDEO_SOURCE_PARAMETER


def origin(shot=SHOT_A):
    return dict(channel_uuid=CHANNEL, shot_uuid=shot, number=1 if shot == SHOT_A else 2,
                name="Opening" if shot == SHOT_A else "Ending", source_node_instance_id=INSTANCE)


def completed(shot=SHOT_A, task="offline-task-a", revision=1):
    return dict(schema="hmb-generated-video-source", version=1, **origin(shot),
                generation_id=task, task_id=task, result_revision=revision,
                path=VIDEO, url=VIDEO, completed=True)


def saved_file():
    return SimpleNamespace(location=VIDEO, name=Path(VIDEO).name, resolve=lambda: VIDEO)


def make_generator():
    node = object.__new__(target.HMBSeedanceGeneration)
    node.name = "Offline Generator"
    node.parameter_values = {"resume_generation_id": ""}
    node.parameter_output_values = {}
    node._hmb_node_deleted = False
    node._hmb_generation_media_revision = 0
    node._hmb_generated_source_instance_id = INSTANCE
    node._hmb_generated_video_source = {}
    node._hmb_generated_video_source_published = {}
    node.current = origin()
    node.publications = []
    node.persisted = []
    node._runtime_node_is_live = lambda **_kwargs: True
    node.get_parameter_value = lambda key: node.parameter_values.get(key)
    node.set_parameter_value = lambda key, value, **_kwargs: node.parameter_values.__setitem__(key, deepcopy(value))
    node._hmb_shot_channel_subscription = lambda: dict(
        enabled=True, channel_uuid=node.current["channel_uuid"], shot_uuid=node.current["shot_uuid"],
        shot_number=node.current["number"], shot_name=node.current["name"])
    node._generation_recovery_state = lambda: target._seedance_recovery_value(
        node.parameter_values.get(target.SEEDANCE_RECOVERY_PARAMETER))
    node._current_recovery_output_file = lambda: VIDEO
    node._output_file = SimpleNamespace(_default_filename=VIDEO)
    node._publish_generation_preview = mock.Mock()
    node._set_status_results = mock.Mock()
    node._reconcile_shared_shot_routing = mock.Mock(side_effect=AssertionError("Completion must not revisit generation routes"))
    node.publish_update_to_parameter = lambda key, value: node.publications.append((key, deepcopy(value)))

    async def persist(**_kwargs):
        node.persisted.append(deepcopy(node.parameter_values))
        return True

    node._force_save_generation_recovery_checkpoint = persist
    node._atomic_publish_completed_video = mock.AsyncMock(return_value=saved_file())
    node._download_broker_video = mock.AsyncMock(return_value=b"offline-decoded-video-fixture")
    node._extract_video_url = lambda _task: "https://not-contacted.invalid/signed?secret=fixture"
    return node


def checkpoint(node, task, stage="accepted", captured=None):
    return node._set_generation_recovery_checkpoint(
        stage=stage, task_id=task,
        task_identity="client_request" if stage == "pre_submit" else "broker_task",
        status="running", params={"_hmb_generation_origin": captured or {}})


async def provenance_tests():
    node = make_generator()
    captured = node._capture_generated_video_origin()
    params = {"_hmb_generation_origin": captured}
    pending = node._set_generation_recovery_checkpoint(
        stage="pre_submit", task_id="offline-client-a", task_identity="client_request",
        status="submitting", params=params)
    # Pending origin is JSON-only durable metadata, not a reference to live UI.
    restored = target._seedance_recovery_value(json.loads(json.dumps(pending)))
    assert restored["generation_origin"] == origin()
    node.current = origin(SHOT_B)
    captured["name"] = "Mutated caller copy"
    assert pending["generation_origin"]["name"] == "Opening"
    params["_hmb_generation_origin"] = restored["generation_origin"]
    node._set_generation_recovery_checkpoint(
        stage="accepted", task_id="offline-task-a", task_identity="broker_task",
        status="running", params=params)
    assert node._generation_recovery_state()["generation_origin"] == origin()

    started, release = asyncio.Event(), asyncio.Event()

    async def gated_download(_url):
        started.set()
        await release.wait()
        return b"offline-decoded-video-fixture"

    node.current = origin()
    node._download_broker_video = gated_download
    save = asyncio.create_task(node._save_completed_task({}, "offline-task-a", object()))
    await started.wait()
    node.current = origin(SHOT_B)
    release.set()
    await save
    assert node._hmb_generated_video_source_snapshot() == completed()
    assert node.parameter_output_values["VIDEO_OUT"] is node.parameter_output_values["video_url"]
    assert node.parameter_output_values["VIDEO_OUT"].value == VIDEO
    assert node.persisted[-1][SOURCE] == completed()
    assert "secret" not in json.dumps(node._generation_recovery_state())
    assert "https:" not in json.dumps(node._hmb_generated_video_source_snapshot())
    assert node._generation_recovery_state()["generation_origin"] == origin()
    assert node.publications[-1] == (SOURCE, completed())

    # Snapshots are copies; repeat refresh does not invent a new result revision.
    mutated = node._hmb_generated_video_source_snapshot()
    mutated["shot_uuid"] = SHOT_B
    assert node._hmb_generated_video_source_snapshot() == completed()
    assert node._record_completed_video_source(origin(), "offline-task-a", saved_file())
    assert node._hmb_generated_video_source_snapshot()["result_revision"] == 1

    # Beginning/failing B preserves the prior successful A source and VIDEO_OUT.
    checkpoint(node, "offline-task-b", stage="pre_submit", captured=origin(SHOT_B))
    before = node._hmb_generated_video_source_snapshot()
    node._download_broker_video = mock.AsyncMock(side_effect=RuntimeError("offline failure"))
    try:
        await node._save_completed_task({}, "offline-task-b", object())
        raise AssertionError("Failure fixture did not fail")
    except RuntimeError as exc:
        assert str(exc) == "offline failure"
    assert node._hmb_generated_video_source_snapshot() == before
    assert node.parameter_output_values["VIDEO_OUT"].value == VIDEO

    # Legacy recovery, unknown IDs and malformed origins never infer current B.
    for unknown_origin in ({}, dict(origin(), channel_uuid="not-a-uuid")):
        checkpoint(node, "offline-old-task", captured=unknown_origin)
        node._download_broker_video = mock.AsyncMock(return_value=b"offline-video")
        await node._save_completed_task({}, "offline-old-task", object())
        assert node._hmb_generated_video_source_snapshot() == before
        assert node._generation_recovery_state()["generation_origin"] == {}
    checkpoint(node, "different-task", captured=origin(SHOT_B))
    await node._save_completed_task({}, "offline-unrecorded-task", object())
    assert node._hmb_generated_video_source_snapshot() == before

    # Normal saved-workflow hydration can restore a source without running.
    reopened = make_generator()
    reopened.parameter_values[SOURCE] = json.loads(json.dumps(before))
    assert reopened._hmb_generated_video_source_snapshot() == before
    assert reopened._hmb_publish_generated_video_source(force=True)
    assert reopened.parameter_output_values[SOURCE] == before
    reopened._download_broker_video.assert_not_called()

    # A subsequent genuine success B increments the immutable result revision.
    assert node._record_completed_video_source(origin(SHOT_B), "offline-task-b", saved_file())
    assert node._hmb_generated_video_source_snapshot() == completed(SHOT_B, "offline-task-b", 2)
    node._hmb_node_deleted = True
    assert not node._record_completed_video_source(origin(), "offline-task-c", saved_file())

    # Capture occurs before the cleanup await; a changed selection aborts safely.
    early = make_generator()
    early._assert_new_submission_is_safe = mock.Mock()
    early._set_safe_defaults = mock.Mock()
    early._begin_generation_preview = mock.Mock()
    early._set_generation_status = mock.Mock()
    early._get_parameters = lambda: {"resume_generation_id": ""}
    early._resolve_exact_shot_generation_inputs = lambda params: params
    early._validate_parameters = mock.Mock(side_effect=AssertionError("must fail before validation"))
    early._cleanup_temporary_video_uploads = mock.Mock()

    async def mutate_during_cleanup(_function):
        early.current = origin(SHOT_B)

    early._run_blocking_generation_stage = mutate_during_cleanup
    try:
        await early._process_generation()
        raise AssertionError("Changed Shot was not rejected")
    except ValueError as exc:
        assert "Shot changed" in str(exc)
    early._validate_parameters.assert_not_called()
    assert early._generation_recovery_state()["task_id"] == ""


class Participant:
    def __init__(self, name, kind, shot=SHOT_A, *, channel=CHANNEL, enabled=True):
        self.name, self.kind = name, kind
        self.channel_uuid, self.shot_uuid = channel, shot
        self.enabled = enabled
        self.incoming = []
        self.statuses = []
        self.source = {}
        self.input = {}
        self.publications = []
        self._hmb_node_deleted = False

    def _hmb_shot_channel_subscription(self):
        return dict(schema="hmb-shot-channel-subscription", version=1,
                    participant_kind=self.kind, enabled=self.enabled,
                    channel_uuid=self.channel_uuid, shot_uuid=self.shot_uuid,
                    shot_number=1 if self.shot_uuid == SHOT_A else 2,
                    shot_name="Opening" if self.shot_uuid == SHOT_A else "Ending")

    def _hmb_reconcile_shot_routing(self, snapshot):
        assert snapshot["channel_uuid"] == CHANNEL

    def _hmb_shot_routing_status(self, value):
        self.statuses.append(deepcopy(value))

    def _hmb_generated_video_source_snapshot(self):
        return deepcopy(self.source)

    def _hmb_hydrate_color_lut_from_source(self, source, parameter):
        assert parameter == SOURCE
        snapshot = source._hmb_generated_video_source_snapshot()
        assert (snapshot["channel_uuid"], snapshot["shot_uuid"]) == (self.channel_uuid, self.shot_uuid)
        self.input = snapshot
        return True

    def _hmb_publish_generated_video_source(self, *, force=False):
        self.publications.append(force)
        return True


def graph_fixture():
    kinds = (routing.KIND_IMAGE_ASSET, routing.KIND_VIDEO_PICKER, routing.KIND_FINISH_LOOK,
             routing.KIND_PROMPT, routing.KIND_AGENT, routing.KIND_SEEDANCE)
    nodes = [Participant(name, kind) for name, kind in zip(
        ("Image", "Picker", "Finish", "Prompt", "Agent", "Generator"), kinds)]
    nodes[1].shot_uuid = ""
    document = dict(channel_uuid=CHANNEL, generation=1, shots=[
        dict(shot_uuid=SHOT_A, number=1, name="Opening", revision=1),
        dict(shot_uuid=SHOT_B, number=2, name="Ending", revision=1)])
    catalog = dict(schema="hmb-shot-routing-catalog", version=1,
                   publisher_instance_uuid=INSTANCE, **document,
                   metadata_sha256=hashlib.sha256(json.dumps(document, ensure_ascii=False,
                       sort_keys=True, separators=(",", ":")).encode()).hexdigest())
    nodes[0]._hmb_shot_routing_catalog = lambda: catalog
    return nodes


def link(source, source_parameter, target_node, target_parameter):
    edge = SimpleNamespace(source_node_name=source.name, source_parameter_name=source_parameter,
                           target_node_name=target_node.name, target_parameter_name=target_parameter)
    target_node.incoming.append(edge)
    return edge


def identities(nodes):
    return {(e.source_node_name, e.source_parameter_name, e.target_node_name, e.target_parameter_name)
            for node in nodes for e in node.incoming}


def routing_tests():
    nodes = graph_fixture()
    source = nodes[-1]

    def create(edge):
        link(edge.source, edge.source_parameter, edge.target, edge.target_parameter)
        return True

    def delete(edge, node):
        node.incoming.remove(edge)
        return True

    with mock.patch.object(routing, "_same_flow_nodes", side_effect=lambda _node: ("Offline LUT Flow", nodes)), \
         mock.patch.object(routing, "_incoming_connections", side_effect=lambda node: list(node.incoming)), \
         mock.patch.object(routing, "_has_parameter", return_value=True), \
         mock.patch.object(routing, "_create_connection", side_effect=create), \
         mock.patch.object(routing, "_delete_connection", side_effect=delete):
        for node in nodes:
            routing._mark_authoritative(node)
        baseline = routing.reconcile_shot_routing(source)
        assert baseline["ok"], baseline
        original = identities(nodes)
        expected = {
            ("Image", "SHOT_ASSET_OUT", "Prompt", "SHOT_ASSET_IN"),
            ("Picker", "SHOT_PICKER_OUT", "Prompt", "SHOT_PICKER_IN"),
            ("Prompt", "PROMPT_OUT", "Agent", "SHOT_PROMPT_IN"),
            ("Agent", "output", "Generator", "prompt"),
            ("Image", "SHOT_ASSET_OUT", "Generator", "SHOT_ASSET_IN"),
            ("Picker", "SHOT_PICKER_OUT", "Generator", "SHOT_PICKER_IN"),
            ("Finish", "SHOT_FINISH_LOOK_OUT", "Generator", "SHOT_FINISH_LOOK_IN"),
        }
        assert original == expected, original
        lut_a = Participant("LUT A", routing.KIND_COLOR_LUT)
        lut_b = Participant("LUT B", routing.KIND_COLOR_LUT, SHOT_B)
        nodes.extend((lut_a, lut_b))
        routing._mark_authoritative(lut_a)
        routing._mark_authoritative(lut_b)
        source.source = completed()
        result = routing.reconcile_shot_routing(source)
        lut_edge = ("Generator", SOURCE, "LUT A", "COLOR_LUT_SOURCE_IN")
        assert result["ok"] and identities(nodes) == original | {lut_edge}, result
        assert lut_a.input == completed() and lut_b.input == {}
        assert source.publications[-1] is True

        # The new route uses completed origin A, not Generator's live B selector.
        source.shot_uuid = SHOT_B
        values = [routing._subscription_for(node) for node in nodes]
        subscriptions = {item.node_name: item for item in values if item}
        narrow = routing.reconcile_completed_video_routes(source)
        assert narrow["ok"] and identities(nodes) == original | {lut_edge}
        assert lut_edge in identities(nodes)
        assert lut_a.input["shot_uuid"] == SHOT_A and not lut_b.incoming

        # Current-source Only mode also cannot relabel the already completed A.
        source.enabled = False
        values = [routing._subscription_for(node) for node in nodes]
        subscriptions = {item.node_name: item for item in values if item}
        routing._reconcile_color_lut_routes(values, subscriptions, nodes)
        assert lut_edge in identities(nodes)
        source.enabled = True
        source.shot_uuid = SHOT_A

        # Different channels and a same-number/name different UUID never match.
        lut_b.shot_uuid = SHOT_A
        lut_b.channel_uuid = OTHER_CHANNEL
        values = [routing._subscription_for(node) for node in nodes]
        subscriptions = {item.node_name: item for item in values if item}
        routing._reconcile_color_lut_routes(values, subscriptions, nodes)
        assert not lut_b.incoming

        # A duplicate completed publisher is ambiguous; never pick by node age.
        duplicate = Participant("Other Generator", routing.KIND_SEEDANCE, SHOT_B)
        duplicate.source = completed()
        nodes.append(duplicate)
        values = [routing._subscription_for(node) for node in nodes]
        subscriptions = {item.node_name: item for item in values if item}
        routing._reconcile_color_lut_routes(values, subscriptions, nodes)
        assert not lut_a.incoming
        assert lut_a.statuses[-1]["code"] == "duplicate_generated_source"
        nodes.remove(duplicate)

        # Foreign input edges and alternate Generator output edges are manual.
        foreign = Participant("Manual Utility", "foreign")
        nodes.append(foreign)
        for manual_source, manual_parameter in ((foreign, SOURCE), (source, "VIDEO_OUT")):
            manual_edge = link(manual_source, manual_parameter, lut_a, "COLOR_LUT_SOURCE_IN")
            values = [item for node in nodes if (item := routing._subscription_for(node))]
            subscriptions = {item.node_name: item for item in values}
            routing._reconcile_color_lut_routes(values, subscriptions, nodes)
            assert lut_a.incoming == [manual_edge]
            assert lut_a.statuses[-1]["code"] == "route_incomplete"
            lut_a.incoming.clear()

        # Cycles through both direct and foreign intermediate paths are blocked.
        for indirect in (False, True):
            backward = link(lut_a, "COLOR_LUT_VIDEO_OUT", foreign if indirect else source, "manual")
            bridge = link(foreign, "output", source, "manual") if indirect else None
            routing._reconcile_color_lut_routes(values, subscriptions, nodes)
            assert not lut_a.incoming and lut_a.statuses[-1]["code"] == "cycle_prevented"
            (foreign if indirect else source).incoming.remove(backward)
            if bridge:
                source.incoming.remove(bridge)

        # A missing/failed LUT never changes the existing six-library routes.
        lut_b.channel_uuid = CHANNEL
        lut_b.shot_uuid = SHOT_B
        lut_a._hmb_reconcile_shot_routing = mock.Mock(side_effect=RuntimeError("offline LUT error"))
        for node in nodes:
            routing._mark_authoritative(node)
        result = routing.reconcile_shot_routing(source)
        assert result["ok"], result
        assert identities(nodes) == original
        assert lut_a.input == completed(), "Unavailable new source must not erase previous success"


def no_network(*_args, **_kwargs):
    raise AssertionError("Offline LUT regression attempted network IO")


def deletion_order_tests():
    """Real LUT catalog/switch/hydration methods, five original UUIDs, all orders."""
    lut_module = load("hmb_color_lut_node_routing_regression", "HMBColorLUTLibrary.py")
    shot_ids = [SHOT_A, SHOT_B, "66666666-6666-4666-8666-666666666666",
                "77777777-7777-4777-8777-777777777777", "88888888-8888-4888-8888-888888888888"]
    transitions = 0

    def make_catalog(alive, generation):
        document = dict(channel_uuid=CHANNEL, generation=generation, shots=[
            dict(shot_uuid=shot, number=index + 1, name=f"Original {shot_ids.index(shot) + 1}", revision=generation)
            for index, shot in enumerate(alive)])
        return dict(schema="hmb-shot-routing-catalog", version=1,
                    publisher_instance_uuid=INSTANCE, **document,
                    metadata_sha256=hashlib.sha256(json.dumps(document, ensure_ascii=False,
                        sort_keys=True, separators=(",", ":")).encode()).hexdigest())

    for order in itertools.permutations(shot_ids):
        lut = object.__new__(lut_module.HMBColorLUTLibrary)
        lut.name = "Offline Real LUT"
        lut.parameter_values = {}
        lut.parameter_output_values = {}
        lut.parameters = {}
        lut.incoming = []
        lut._lock = threading.RLock()
        with mock.patch.object(lut_module, "_read_profiles", return_value=lut_module._profiles()):
            lut._hmb_color_lut_state = lut_module.default_state()
        lut._hmb_node_deleted = False
        lut._hmb_initial_shot_autoclaim_pending = False
        lut._hmb_initial_shot_preferred_uuid = ""
        lut._source_token = 0
        lut._pending_source_key = None
        lut._restoring_source = {}
        lut._publish = mock.Mock()
        lut._publish_result_url = mock.Mock()
        # The local media probe is the only replacement for production source
        # hydration; all Shot validation and input publication remain real.
        def stage_source(value):
            assert value["shot_uuid"] == lut._hmb_color_lut_state["shot"]["shot_uuid"]
            assert value["channel_uuid"] == lut._hmb_color_lut_state["shot"]["channel_uuid"]
            lut._hmb_color_lut_state["source"] = deepcopy(value)
        lut._queue_source = stage_source
        sources = []
        for number, shot in enumerate(shot_ids, 1):
            source = Participant(f"Generator {number}", routing.KIND_SEEDANCE, shot)
            source.source = dict(completed(shot, f"offline-task-{number}"),
                                 number=number, name=f"Original {number}")
            sources.append(source)
        nodes = [*sources, lut]

        def create(edge):
            link(edge.source, edge.source_parameter, edge.target, edge.target_parameter)
            return True

        def delete(edge, node):
            node.incoming.remove(edge)
            return True

        def reconcile():
            values = [routing._subscription_for(node) for node in nodes]
            subscriptions = {item.node_name: item for item in values if item}
            routing._reconcile_color_lut_routes(values, subscriptions, nodes)

        def select(shot):
            entry = next(item for item in lut._hmb_color_lut_state["shot_catalog"]["shots"] if item["shot_uuid"] == shot)
            lut._switch(dict(channel_uuid=CHANNEL, **{key: entry[key] for key in ("shot_uuid", "number", "name")}))
            reconcile()
            assert lut._hmb_color_lut_state["source"]["shot_uuid"] == shot
            assert lut.parameter_values[lut_module.SOURCE]["shot_uuid"] == shot
            assert len(lut.incoming) == 1
            expected = sources[shot_ids.index(shot)]
            assert lut.incoming[0].source_node_name == expected.name

        with mock.patch.object(routing, "_incoming_connections", side_effect=lambda node: list(node.incoming)), \
             mock.patch.object(routing, "_has_parameter", return_value=True), \
             mock.patch.object(routing, "_create_connection", side_effect=create), \
             mock.patch.object(routing, "_delete_connection", side_effect=delete):
            alive = list(shot_ids)
            lut._hmb_reconcile_shot_routing(make_catalog(alive, 1))
            select(order[0])
            for step, removed in enumerate(order[:-1], 1):
                assert lut._hmb_color_lut_state["shot"]["shot_uuid"] == removed
                alive.remove(removed)
                lut._hmb_reconcile_shot_routing(make_catalog(alive, step + 1))
                reconcile()
                assert not lut._hmb_color_lut_state["shot"].get("shot_uuid")
                assert lut._hmb_color_lut_state["source"] == {} and not lut.incoming
                assert lut.parameter_values.get(lut_module.SOURCE) == {}, "Deleted Shot retained its hidden source"
                select(order[step])
                transitions += 1
    assert transitions == 480


async def main():
    # Windows creates a local socketpair while creating the event loop. Start
    # the external-IO guard only once that internal loop setup has completed.
    with mock.patch.object(socket, "create_connection", side_effect=no_network), \
         mock.patch.object(socket.socket, "connect", side_effect=no_network), \
         mock.patch.object(target._HMBAIBrokerBridge, "generate_seedance", side_effect=no_network):
        await provenance_tests()
        legacy_completed_source_tests()
        project_follow_tests()
        routing_tests()
        deletion_order_tests()


def legacy_completed_source_tests():
    with tempfile.TemporaryDirectory() as directory:
        clip = Path(directory) / "volcengine_seedance_video_shot_01_v001.mp4"
        clip.write_bytes(b"existing completed video; probing is exercised by host regression")
        node = make_generator()
        node.parameter_output_values["VIDEO_OUT"] = SimpleNamespace(value=str(clip))
        node.parameter_output_values["generation_id"] = "completed-old-task"
        node.parameter_values[target.SEEDANCE_SHOT_WIDGET_PARAMETER] = {"generation": {"phase": "succeeded", "job_id": "completed-old-task"}}
        with mock.patch.object(target, "File", side_effect=lambda p: SimpleNamespace(resolve=lambda: Path(p))):
            source = node._hmb_generated_video_source_snapshot()
            assert source["shot_uuid"] == SHOT_A and source["path"] == str(clip)
            node.current = origin(SHOT_B)
            assert node._hmb_generated_video_source_snapshot()["shot_uuid"] == SHOT_A
            node._hmb_generated_video_source = {}
            node.parameter_values[SOURCE] = {}
            assert node._hmb_generated_video_source_snapshot() == {}, "Legacy Shot 1 must not be adopted as Shot 2"
            node.current = origin()
            node.parameter_values[target.SEEDANCE_SHOT_WIDGET_PARAMETER]["generation"]["phase"] = "running"
            assert node._hmb_generated_video_source_snapshot() == {}, "Unconfirmed result cannot be adopted"


def project_follow_tests():
    nodes = graph_fixture()
    seen = []
    recipient = SimpleNamespace(_hmb_follow_image_asset_project=lambda project: seen.append(deepcopy(project)))
    nodes.append(recipient)
    state = {"project_id": "superwings12", "project_root": "//server/projects/superwings12"}
    nodes[0].get_parameter_value = lambda _key: json.dumps(state)
    routing._reconcile_color_lut_projects(nodes)
    assert seen[-1]["name"] == "superwings12" and seen[-1]["root"] == state["project_root"]
    with mock.patch.object(routing, "_same_flow_nodes", return_value=("Flow", nodes)):
        routing.notify_color_lut_project_change(nodes[0], state)
        count = len(seen)
        routing.notify_color_lut_project_change(nodes[0], state)
        assert len(seen) == count, "Unchanged image edits must not republish the LUT project"
        state = {"project_id": "show-b", "project_root": "D:/other/show-b"}
        routing.notify_color_lut_project_change(nodes[0], state)
        assert seen[-1]["name"] == "show-b"
    routing._reconcile_color_lut_projects([recipient])
    assert seen[-1] == {}, "Removed ImageAsset cannot leave a stale project"


if __name__ == "__main__":
    asyncio.run(main())
    print("PASS: Color LUT origin capture/completion races, durable recovery, last-success retention, exact UUID routing, existing six-library routes, manual edges/cycles, and real LUT 120 deletion orders/480 clear-rebind transitions (offline).")
