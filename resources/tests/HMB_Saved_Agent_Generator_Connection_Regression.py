"""Private installed-SDK attached/save/replay connection capability regression.

All saved Python files are produced by this disposable fixture. No user save,
running application, provider, model, render or live service is accessed.
"""
from __future__ import annotations

import argparse
import ast
import asyncio
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import importlib
import json
import logging
import os
from pathlib import Path
import socket
import sys
import tempfile
import time
from unittest import mock
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "resources/tests")]
sys.dont_write_bytecode = True
import HMB_Common_Connection_Management_Host_Regression as common

base = common.base
CASES = []
FORBIDDEN = []
PRODUCTS = ("_hmb_connection_management.py", "_hmb_deletion_guard.py", "_hmb_shot_routing.py",
            "_hmb_library_bootstrap.py", "HMBAgentLibrary.py", "HMBSeedanceGeneration.py")


def deny(*args, **kwargs):
    FORBIDDEN.append("transport_or_execution")
    raise AssertionError("Saved connection regression cannot use external transport or execution")


def record(name, **facts):
    CASES.append(dict(name=name, passed=True, **facts))


def capabilities(engine, nodes):
    import _hmb_connection_management as api
    result = {}
    for key, node in (("prompt", nodes[base.KINDS[2]]), ("agent", nodes[base.KINDS[3]]),
                      ("generator", nodes[base.KINDS[5]][0])):
        view = base.send(engine, api.HMBGetNodeConnectionsRequest(node_name=node.name))
        result[key] = {name: getattr(view, name) for name in (
            "detached", "can_disconnect", "can_reconnect", "details")}
        result[key].update(name=node.name, locked=bool(node.lock),
            resolution=str(getattr(node.state, "name", node.state)), rows=len(view.connections))
    return result


def assert_idle(view):
    assert all(row["can_disconnect"] and not row["detached"] for row in view.values()), view


async def save(engine, path, label):
    from griptape_nodes.retained_mode.events.workflow_events import SaveWorkflowRequest
    result = await base.asend(engine, SaveWorkflowRequest(file_name=str(path), display_name=label))
    actual = Path(result.file_path)
    await asyncio.sleep(.08)
    original = actual.read_bytes()
    text = original.decode("utf-8")
    tree = ast.parse(text)
    function = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef))
    omitted = {line for node in function.body if "RegisterLibraryFromFileRequest" in ast.unparse(node)
               for line in range(node.lineno, node.end_lineno + 1)}
    replay = actual.with_name(actual.stem + "-registered-fixture.py")
    replay.write_text("".join(line for number, line in enumerate(text.splitlines(keepends=True), 1)
                              if number not in omitted), encoding="utf-8")
    assert actual.read_bytes() == original
    return dict(path=replay, original_path=actual, original_sha256=hashlib.sha256(original).hexdigest(),
                removed_already_registered_library_lines=len(omitted))


async def construct(engine, modules, folder, schema):
    import _hmb_connection_management as api
    from griptape_nodes.retained_mode.events.node_events import SetLockNodeStateRequest, SetNodeMetadataRequest
    nodes = await common.setup(engine, modules, folder, schema)
    expected = common.authoring(nodes)
    before_edges = common.edges(engine)
    view = capabilities(engine, nodes)
    assert_idle(view)
    record("new_attached_Agent_Generator_and_Prompt_controls_enabled", capability=view)
    artifacts = {"idle": await save(engine, folder / "attached-idle.py", "Private attached idle")}

    generator = nodes[base.KINDS[5]][0]
    base.send(engine, SetLockNodeStateRequest(node_name=generator.name, lock=True))
    view = capabilities(engine, nodes)
    assert view["prompt"]["can_disconnect"]
    assert not view["agent"]["can_disconnect"] and not view["generator"]["can_disconnect"]
    record("native_Generator_lock_blocks_Agent_and_Generator_but_Prompt_stays_enabled", capability=view)
    artifacts["locked"] = await save(engine, folder / "attached-locked.py", "Private locked generator")
    assert "SetLockNodeStateRequest" in artifacts["locked"]["path"].read_text("utf-8")
    base.send(engine, SetLockNodeStateRequest(node_name=generator.name, lock=False))
    assert_idle(capabilities(engine, nodes))
    assert common.authoring(nodes) == expected and common.edges(engine) == before_edges
    record("unlock_restores_controls_without_authoring_or_edge_change")

    other = nodes[base.KINDS[5]][1]
    collision = str(uuid4())
    for node in (generator, other):
        base.send(engine, SetNodeMetadataRequest(node_name=node.name, metadata={api.IDENTITY: collision}))
    view = capabilities(engine, nodes)
    assert view["prompt"]["can_disconnect"]
    assert not view["agent"]["can_disconnect"] and not view["generator"]["can_disconnect"]
    record("duplicate_Generator_identity_blocks_exact_Agent_Generator_controls_only", capability=view)
    artifacts["duplicate"] = await save(engine, folder / "attached-duplicate.py", "Private duplicate identity")
    base.send(engine, SetNodeMetadataRequest(node_name=other.name, metadata={api.IDENTITY: str(uuid4())}))
    assert_idle(capabilities(engine, nodes))

    agent = nodes[base.KINDS[3]]
    current = base.send(engine, api.HMBGetNodeConnectionsRequest(node_name=agent.name))
    detached = await base.asend(engine, api.HMBManageNodeConnectionsRequest(node_name=agent.name,
        operation="disconnect", expected_state_token=current.state_token))
    assert detached.detached and detached.can_reconnect and not detached.can_disconnect
    assert common.authoring(nodes) == expected
    artifacts["detached"] = await save(engine, folder / "detached-agent.py", "Private detached Agent")
    record("detach_preserves_five_Shot_inputs_outputs_and_original_TaskIDs_before_save")
    return artifacts, expected, before_edges


def retained_nodes(engine):
    found = {}
    for kind in base.KINDS[:5]:
        found[kind] = engine.node_manager.get_node_by_name("Connection " + kind)
    found[base.KINDS[5]] = [engine.node_manager.get_node_by_name(f"Retained Generator {number}") for number in range(1, 6)]
    return found


def digest(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf8")
    return hashlib.sha256(encoded).hexdigest()


def published_shot(publications, node, receipt, shot_id):
    return next((snapshot for owner, snapshot in publications if owner is node
        and all(snapshot[name] == receipt[name] for name in (
            "publisher_instance_uuid", "channel_uuid", "generation", "metadata_sha256"))
        and any(shot["shot_uuid"] == shot_id for shot in snapshot["shots"])), None)


async def wait_for_reconnected_publications(nodes, publications):
    prompt = nodes[base.KINDS[2]]
    started = time.monotonic()
    while True:
        state = prompt._hmb_prompt_merge_snapshot()["state"]
        pending = prompt._hmb_sync_queued_token is not None
        matching = {
            kind: published_shot(publications[kind], nodes[base.KINDS[index]],
                state[kind]["shot_routing"], state["shot"]["shot_uuid"]) is not None
            for index, kind in enumerate(("image_asset", "picker"))
        }
        if not pending and all(matching.values()):
            return round(time.monotonic() - started, 3)
        if time.monotonic() - started >= 10:
            raise AssertionError(f"Timed out awaiting native Prompt receipts: queued={pending}, matched={matching}")
        await asyncio.sleep(.05)


def assert_reconnected_authoring(nodes, expected, publications):
    actual = common.authoring(nodes)
    expected = deepcopy(expected)
    prompt_state = nodes[base.KINDS[2]]._current_state()
    channel = prompt_state["shot"]["channel_uuid"]
    shot_id = prompt_state["shot"]["shot_uuid"]
    key = channel + "/" + shot_id
    before = json.loads(expected["prompt_documents"][key])
    after = json.loads(actual["prompt_documents"][key])

    # A cold physical reconnection republishes only the active document. Verify the
    # new receipts against each actual upstream node before comparing authoring.
    for kind, node, media_field in (
        ("image_asset", nodes[base.KINDS[0]], "ordered_assets"),
        ("picker", nodes[base.KINDS[1]], "ordered_videos"),
    ):
        # Reading the same publisher again can advance its sequence if another
        # consumer asked for a different Shot. Use the actual delivered snapshot.
        receipt = after[kind]["shot_routing"]
        snapshot = published_shot(publications[kind], node, receipt, shot_id)
        assert snapshot is not None, "Missing native " + kind + " publication"
        selected = next(shot for shot in snapshot["shots"] if shot["shot_uuid"] == shot_id)["selected_source_uids"]
        metadata_keys = ["channel_uuid", "generation", "shots", media_field]
        if kind == "image_asset":
            metadata_keys.append("project_id")
        metadata_digest = digest({name: snapshot[name] for name in metadata_keys})
        media_digest = digest({"media_descriptors": [
            {"source_uid": row["source_uid"], "media_value_sha256":
                hashlib.sha256(snapshot["media_by_source_uid"][row["source_uid"]].encode("utf8")).hexdigest()}
            for row in snapshot[media_field]
        ]})
        assert snapshot["metadata_sha256"] == metadata_digest and snapshot["media_sha256"] == media_digest, kind
        assert snapshot["channel_uuid"] == channel
        route = {
            "publisher_instance_uuid": snapshot["publisher_instance_uuid"], "channel_uuid": channel,
            "generation": snapshot["generation"], "metadata_sha256": metadata_digest, "media_sha256": media_digest,
            "media_count": len(selected), "media_order_sha256": digest({"selected_source_uids": selected}),
        }
        assert after[kind]["shot_routing"] == route, kind
        old = before[kind]["shot_routing"]
        assert all(old[name] == route[name] for name in ("channel_uuid", "media_count", "media_sha256", "media_order_sha256")), kind
        if kind == "image_asset":
            for document, generation in ((before, old["generation"]), (after, route["generation"])):
                selection = {"channel_uuid": channel, "generation": generation, "shot_uuid": shot_id, "selected_source_uids": selected}
                assert document[kind]["selection_id"] == digest(selection)
            before[kind]["selection_id"] = after[kind]["selection_id"]
        before[kind]["shot_routing"] = route
    assert after["source_sync_revision"] == prompt_state["source_sync_revision"]
    assert after["source_sync_revision"] >= before["source_sync_revision"]
    before["source_sync_revision"] = after["source_sync_revision"]
    assert before == after, "Active Shot authored data changed"
    expected["prompt_documents"][key] = actual["prompt_documents"][key]
    assert actual == expected, "Other Shot documents, memberships, saved settings or results changed"


async def replay(engine, modules, folder, artifact, expected, original_edges, scenario):
    publications = {"image_asset": [], "picker": []}
    with ExitStack() as observed:
        if scenario == "detached":
            for kind, cls_name in zip(publications, base.KINDS[:2]):
                cls = getattr(modules[cls_name], cls_name)
                for method in ("_hmb_shot_routing_snapshot", "_hmb_shot_routing_snapshot_for"):
                    original = getattr(cls, method)
                    def capture(self, *args, _read=original, _kind=kind, **kwargs):
                        result = _read(self, *args, **kwargs)
                        publications[_kind].append((self, deepcopy(result)))
                        return result
                    observed.enter_context(mock.patch.object(cls, method, capture))
        await replay_observed(engine, modules, folder, artifact, expected, original_edges, scenario, publications)


async def replay_observed(engine, modules, folder, artifact, expected, original_edges, scenario, publications):
    import _hmb_connection_management as api
    from griptape_nodes.retained_mode.events.node_events import SetLockNodeStateRequest
    from griptape_nodes.retained_mode.events.workflow_events import RunWorkflowFromScratchRequest
    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
    native_request = GriptapeNodes.ahandle_request
    failures = []
    async def inspect_request(request):
        result = await native_request(request)
        if not result.succeeded():
            failures.append(dict(request=type(request).__name__,
                node=getattr(request, "node_name", None),
                parameter=getattr(request, "parameter_name", None),
                details=str(result.result_details)))
        return result
    with mock.patch.object(GriptapeNodes, "ahandle_request", side_effect=inspect_request):
        loaded = await base.asend(engine, RunWorkflowFromScratchRequest(file_path=str(artifact["path"])))
    (Path(os.environ.get("HMB_LIFECYCLE_REPORT_DIR", str(folder))) / f"{scenario}-load-requests.json").write_text(
        json.dumps(dict(status=str(getattr(loaded, "status", "")), failures=failures), indent=2), encoding="utf-8")
    assert not failures, failures[:5]
    await asyncio.sleep(.25)
    nodes = retained_nodes(engine)
    view = capabilities(engine, nodes)
    actual = common.authoring(nodes)
    if actual != expected:
        (Path(os.environ.get("HMB_LIFECYCLE_REPORT_DIR", str(folder))) / f"{scenario}-authoring-mismatch.json").write_text(
            json.dumps({"expected": expected, "actual": actual}, ensure_ascii=False,
                       indent=2, default=str), encoding="utf-8")
    assert actual == expected, scenario
    agent = nodes[base.KINDS[3]]
    assert not agent._hmb_shot_workers
    assert not any(lock.locked() for lock in agent._hmb_shot_execution_locks.values())
    assert hashlib.sha256(artifact["original_path"].read_bytes()).hexdigest() == artifact["original_sha256"]
    if scenario == "idle":
        assert_idle(view)
        assert common.edges(engine) == original_edges
        record("cold_attached_save_replay_keeps_all_controls_and_five_Shot_results", capability=view)
        # Saved result status is presentation, not an active execution receipt.
        agent._hmb_shot_run_status = {"synthetic-retained-status": "running"}
        assert not api._busy(agent)
        record("retained_running_status_does_not_recreate_execution_worker_or_lock")
    elif scenario == "locked":
        assert view["generator"]["locked"]
        assert view["prompt"]["can_disconnect"]
        assert not view["agent"]["can_disconnect"] and not view["generator"]["can_disconnect"]
        generator = nodes[base.KINDS[5]][0]
        base.send(engine, SetLockNodeStateRequest(node_name=generator.name, lock=False))
        after = capabilities(engine, nodes)
        assert_idle(after)
        assert common.authoring(nodes) == expected and common.edges(engine) == original_edges
        record("cold_saved_native_lock_is_retained_and_explicit_unlock_restores_controls", initial=view, after=after)
    elif scenario == "duplicate":
        assert view["prompt"]["can_disconnect"]
        assert not view["agent"]["can_disconnect"] and not view["generator"]["can_disconnect"]
        current = base.send(engine, api.HMBGetNodeConnectionsRequest(node_name=agent.name))
        refused = await engine.ahandle_request(api.HMBManageNodeConnectionsRequest(node_name=agent.name,
            operation="disconnect", expected_state_token=current.state_token, broadcast_result=False))
        assert not refused.succeeded()
        assert common.authoring(nodes) == expected and common.edges(engine) == original_edges
        record("cold_saved_duplicate_identity_is_refused_without_mutation", capability=view)
    elif scenario == "detached":
        assert view["agent"]["detached"] and view["agent"]["can_reconnect"]
        current = base.send(engine, api.HMBGetNodeConnectionsRequest(node_name=agent.name))
        restored = await base.asend(engine, api.HMBManageNodeConnectionsRequest(node_name=agent.name,
            operation="reconnect", expected_state_token=current.state_token))
        assert not restored.detached and restored.can_disconnect
        assert common.edges(engine) == original_edges
        settled_seconds = await wait_for_reconnected_publications(nodes, publications)
        assert_reconnected_authoring(nodes, expected, publications)
        assert common.edges(engine) == original_edges
        record("cold_detached_Agent_reconnect_restores_exact_edges_and_TaskIDs", initial=view,
               after=capabilities(engine, nodes), settled_seconds=settled_seconds)


async def registered_stage(engine, modules, callback):
    # Match native registration under the engine's active asyncio context.
    with ExitStack() as patches:
        library, schema, owner = common.hooks(engine, modules, patches)
        try:
            return await callback(schema)
        finally:
            owner.before_library_unregistered(schema, library)
            from griptape_nodes.node_library.library_registry import LibraryRegistry
            LibraryRegistry.unregister_library(schema.name, event_manager=engine.event_manager)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "reports/saved-agent-generator-disconnect-audit-20261102/agent-review")
    args = parser.parse_args()
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=True)
    before = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in PRODUCTS}
    started = time.perf_counter(); passed = False; replay_count = 0; save_proofs = {}
    try:
        with tempfile.TemporaryDirectory(prefix="hmb-saved-agent-connections-") as temp:
            folder = Path(temp)
            env = {key: str(folder / key) for key in ("APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME", "XDG_DATA_HOME",
                "XDG_STATE_HOME", "XDG_CACHE_HOME", "GTN_ENGINE_CONFIG_DIR", "GTN_ENGINE_DATA_DIR", "GTN_ENGINE_STATE_DIR",
                "GTN_CONFIG_WORKSPACE_DIRECTORY", "HMB_IMAGE_PROJECTS_ROOT")}
            for path in env.values(): Path(path).mkdir(parents=True, exist_ok=True)
            previous = Path.cwd()
            with mock.patch.dict(os.environ, env), mock.patch.object(socket, "create_connection", deny):
                from griptape_nodes.retained_mode.engine import engine_scope
                os.chdir(folder)
                try:
                    modules = {kind: importlib.import_module(kind) for kind in base.KINDS}
                    logging.disable(logging.CRITICAL)
                    with engine_scope() as engine:
                        with asyncio.Runner() as runner:
                            artifacts, expected, original_edges = runner.run(registered_stage(engine, modules,
                                lambda schema: construct(engine, modules, folder, schema)))
                    proof_folder = out / "fixture-saves"
                    proof_folder.mkdir(exist_ok=True)
                    for scenario, artifact in artifacts.items():
                        proof = {}
                        for key in ("original_path", "path"):
                            payload = artifact[key].read_bytes()
                            destination = proof_folder / artifact[key].name
                            destination.write_bytes(payload)
                            proof[key] = dict(file=str(destination), bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest())
                        save_proofs[scenario] = proof
                    for scenario, artifact in artifacts.items():
                        with engine_scope() as engine:
                            with asyncio.Runner() as runner:
                                runner.run(registered_stage(engine, modules, lambda schema:
                                    replay(engine, modules, folder, artifact, expected, original_edges, scenario)))
                        replay_count += 1
                    passed = True
                finally:
                    logging.shutdown()
                    os.chdir(previous)
    finally:
        after = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in PRODUCTS}
        attempts = FORBIDDEN + common.ATTEMPTS + base.ATTEMPTS
        result = dict(status="PASS" if passed and not attempts and before == after else "FAIL", cases=CASES,
            cases_passed=len(CASES), source_stable=before == after, source_before=before, source_after=after,
            execution_transport_attempts=len(attempts), paid_calls=0, actual_Desktop_verified=False,
            user_workflows_read_or_executed=0, fresh_private_engine_replays=replay_count,
            synthetic_save_proofs=save_proofs,
            interpreter=sys.executable,
            sdk_module_file=str(getattr(sys.modules.get("griptape_nodes.retained_mode.engine"), "__file__", "")),
            product_module_files={name: str(getattr(sys.modules.get(name), "__file__", "")) for name in base.KINDS},
            scope="Installed SDK native retained requests and four disposable self-generated saves; no user save or live API",
            elapsed_seconds=time.perf_counter() - started)
        (out / "RESULT.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(dict(status=result["status"], cases_passed=len(CASES), source_stable=before == after)))
    assert result["status"] == "PASS", result


if __name__ == "__main__":
    main()
