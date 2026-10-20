"""Real installed SDK: Finish Look consolidation preserves per-Shot Beauty.

Only structure and deterministic local context preparation run. No user graph,
provider, model, Broker, DCC or video generation is used.
"""
from __future__ import annotations

import asyncio
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import json
import logging
import os
from pathlib import Path
import socket
import sys
import tempfile
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
CHANNEL = "11111111-1111-4111-8111-111111111111"
PUBLISHER = "22222222-2222-4222-8222-222222222222"
SHOTS = [dict(shot_uuid=f"33333333-3333-4333-8333-{number:012d}", number=number,
    name=f"Renamed Beauty asset {number}", revision=number, selected_source_uids=[]) for number in range(1, 6)]
PROJECT = {"project_id": "katuri8", "project_name": "까투리8"}
EXECUTED, NETWORK = [], []


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":")).encode("utf-8")).hexdigest()


def deny_network(*args, **kwargs):
    NETWORK.append(True)
    raise AssertionError("Finish consolidation attempted external transport")


def deny_execution(*args, **kwargs):
    EXECUTED.append(True)
    raise AssertionError("Finish consolidation executed a model or render")


def send(engine, request, *, success=True):
    request.broadcast_result = False
    result = engine.handle_request(request)
    assert result.succeeded() is success, str(result.result_details)
    return result


def register_library(engine):
    import HMBImageAssetLibrary as images
    import HMBFinishLookLibrary as finishes
    import HMBSeedanceGeneration as generators
    from _hmb_library_bootstrap import HMBProductionLibrary
    from griptape_nodes.node_library.library_registry import LibraryRegistry, LibrarySchema
    schema = LibrarySchema.model_validate_json((ROOT / "griptape-nodes-library.json").read_text(encoding="utf-8-sig"))
    advanced = HMBProductionLibrary()
    library = LibraryRegistry.generate_new_library(schema, advanced_library=advanced)
    classes = {cls.__name__: cls for cls in (images.HMBImageAssetLibrary,
        finishes.HMBFinishLookLibrary, generators.HMBSeedanceGeneration)}
    for definition in schema.nodes:
        cls = classes.get(definition.class_name)
        if cls is not None:
            library.register_lazy_node_type(definition.class_name, definition.metadata, lambda cls=cls: cls)
    advanced.before_library_nodes_loaded(schema, library)
    return library, advanced, images, finishes, generators


def media_fixture(source):
    catalog_document = dict(channel_uuid=CHANNEL, generation=1,
        shots=[{key: row[key] for key in ("shot_uuid", "number", "name", "revision")} for row in SHOTS])
    catalog = dict(schema="hmb-shot-routing-catalog", version=1, publisher_instance_uuid=PUBLISHER,
        **catalog_document, metadata_sha256=digest(catalog_document))
    snapshot = dict(schema="hmb-shot-routing-snapshot", version=1, publisher_instance_uuid=PUBLISHER,
        channel_uuid=CHANNEL, generation=1, project_id=PROJECT["project_id"], shots=deepcopy(SHOTS),
        ordered_assets=[], media_by_source_uid={})
    snapshot["metadata_sha256"] = digest({key: snapshot[key] for key in
        ("channel_uuid", "generation", "project_id", "shots", "ordered_assets")})
    snapshot["media_sha256"] = digest({"media_descriptors": []})
    source._hmb_initial_catalog_scan_pending = False
    source._hmb_hydration_adopted = True
    source._hmb_shot_routing_catalog = lambda: deepcopy(catalog)
    source._hmb_shot_routing_snapshot = lambda *a, **k: deepcopy(snapshot)
    source._hmb_shot_routing_snapshot_for = lambda **kwargs: deepcopy(snapshot)
    source._hmb_project_identity = lambda: dict(PROJECT)
    source._hmb_shot_channel_subscription = lambda: dict(schema="hmb-shot-channel-subscription", version=1,
        participant_kind="image_asset", enabled=True, channel_uuid=CHANNEL,
        shot_uuid=SHOTS[0]["shot_uuid"], shot_number=1, shot_name=SHOTS[0]["name"])
    return catalog


async def exercise(engine, directory):
    import _hmb_workflow_migration as migration
    import _hmb_shot_routing as routing
    from griptape_nodes.node_library.library_registry import LibraryRegistry
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    from griptape_nodes.retained_mode.events.flow_events import (
        SerializeFlowToCommandsRequest, DeserializeFlowFromCommandsRequest, DeleteFlowRequest, CreateFlowRequest)
    from griptape_nodes.retained_mode.events.node_events import (
        CreateNodeRequest, SerializeSelectedNodesToCommandsRequest, DeserializeSelectedNodesFromCommandsRequest)
    from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest
    from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
    from griptape_nodes.serialization.values import decode_value
    engine.event_manager.initialize_queue()
    library, advanced, images, finishes, generators = register_library(engine)
    try:
        result = send(engine, EnsureWorkflowAndFlowRequest(flow_name="LegacyFiveFinishLook"))
        flow = engine.flow_manager.get_flow_by_name(result.flow_name)
        migration.mark_flow_migration_pending(engine, flow.name)
        def create(kind, name, **kwargs):
            result = send(engine, CreateNodeRequest(node_type=kind, node_name=name,
                specific_library_name="HMB_GP_Production", initial_setup=True, **kwargs))
            return engine.node_manager.get_node_by_name(result.node_name)
        source = create("HMBImageAssetLibrary", "Renamed Finish Image Library")
        catalog = media_fixture(source)
        finish_nodes, generator_nodes, authored = [], [], {}
        for number, shot in enumerate(SHOTS, 1):
            node = create("HMBFinishLookLibrary", f"Renamed Finish {number}")
            raw = finishes.default_widget_state()
            raw.pop("shot_manager", None)
            raw["shot_catalog"], raw["shot"] = deepcopy(catalog), {"channel_uuid": CHANNEL, **shot}
            beauty = raw["finish_look"]["beauty"]
            beauty.update(enabled=number % 2 == 1, soften_shadows=-0.2 + number / 10,
                shadow_threshold=number / 10, saturation=number / 2,
                brightness=1 + number / 10, glow_brightness=number / 20,
                glow_threshold=number / 5, glow_width=number * 7,
                soft_focus=number / 30, blur_amount=number / 40,
                pore_size=number / 50, reduce_shine=number / 10)
            node._hmb_capture_saved_parameter_value(finishes.WIDGET_PARAMETER_NAME, raw)
            send(engine, SetParameterValueRequest(node_name=node.name,
                parameter_name=finishes.WIDGET_PARAMETER_NAME, value=raw, initial_setup=True))
            node.after_deserialize()
            # The current legacy node owns a native remote revision/history.
            # Migration must retain those values without re-applying requests.
            node._remote_revision = number * 10
            node._seen_remote_requests = [f"authored-remote-{number}"]
            node._remote_status = {"schema_version": 1, "status": "accepted", "code": "ok",
                "message": f"Authored remote state {number}", "request_id": f"authored-remote-{number}", "revision": number * 10}
            node._publish_all(live=False)
            finish_nodes.append(node)
            authored[shot["shot_uuid"]] = deepcopy(raw["finish_look"])
            generator = create("HMBSeedanceGeneration", f"Renamed Finish Generator {number}")
            for name, value in (("shot_channel_uuid", CHANNEL), ("shot_uuid", shot["shot_uuid"]),
                ("shot_number", number), ("shot_name", shot["name"]), ("resolution", "480p"),
                ("resume_generation_id", "job-" + str(number) * 32), ("draft_job_id", "job-" + str(number + 1) * 32)):
                generator.set_parameter_value(name, value, initial_setup=True)
            generator_nodes.append(generator)
            for src, output, dst, inp in ((source, "SHOT_ASSET_OUT", generator, "SHOT_ASSET_IN"),
                (node, "SHOT_FINISH_LOOK_OUT", generator, "SHOT_FINISH_LOOK_IN")):
                send(engine, CreateConnectionRequest(source_node_name=src.name, source_parameter_name=output,
                    target_node_name=dst.name, target_parameter_name=inp, initial_setup=True))
        original = {node.name: migration._raw_node_state(node) for node in flow.nodes.values()}
        before_exports = {node.name: node._hmb_finish_merge_snapshot() for node in finish_nodes}
        edges = migration._edge_records(engine, set(flow.nodes))
        result = await migration.migrate_flow(engine, flow.name, backup_root=directory / "backups")
        assert result["ok"] and result["code"] == "consolidated", result
        assert set(result["survivors"]) == {"finish_look"} and len(flow.nodes) == 7
        manager = flow.nodes[result["survivors"]["finish_look"]]
        assert manager is finish_nodes[0] and len(result["removed_nodes"]) == 4
        merged = manager._hmb_finish_merge_snapshot()
        for number, shot in enumerate(SHOTS, 1):
            key = CHANNEL + "\x1f" + shot["shot_uuid"]
            old = before_exports[finish_nodes[number - 1].name]["documents"][key]
            assert merged["documents"][key] == old
            assert old["finish_look"] == authored[shot["shot_uuid"]], (number, old["finish_look"], authored[shot["shot_uuid"]])
            assert old["remote_revision"] == number * 10 and old["seen_remote_requests"] == [f"authored-remote-{number}"]
        for node in generator_nodes:
            assert migration._raw_node_state(node) == original[node.name], node.name
        backup = decode_value(json.loads(Path(result["backup_path"]).read_text(encoding="utf-8")))
        assert len(backup["nodes"]) == 11 and backup["edges"] == edges
        print("PASS real Finish5 + Generator5 contracts to Finish1 + Generator5; all Beauty values/ON-OFF, remote revision/history/snapshots and Generator authored controls retained")

        # The editor stays on Shot1 while each Generator reads its own Shot.
        routed = routing.reconcile_shot_routing(source, _allow_unready_cleanup=True)
        assert routed["ok"], routed
        for shot, generator in zip(SHOTS, generator_nodes):
            snapshot = manager._hmb_finish_look_shot_snapshot_for(channel_uuid=CHANNEL, shot_uuid=shot["shot_uuid"])
            assert snapshot["finish_look_state"] == authored[shot["shot_uuid"]]
            assert snapshot["shot_uuid"] == shot["shot_uuid"] and snapshot["shot_name"] == shot["name"]
            declared = generator._finish_look_source_subscription(manager, generator._hmb_shot_channel_subscription())
            assert declared["shot_uuid"] == shot["shot_uuid"]
            prepared = generator._resolve_exact_shot_generation_inputs({"model_id": generators.SEEDANCE_2_5_MODEL_ID,
                "prompt": "Literal authored {{SIGN}} prompt", "duration": 4, "resolution": "480p"})
            assert prepared["_hmb_finish_look_out"] == finishes.compile_finish_look_prompt(authored[shot["shot_uuid"]])
            assert prepared["prompt"] == "Literal authored {{SIGN}} prompt"
        assert manager._hmb_finish_merge_snapshot()["active_subscription"]["shot_uuid"] == SHOTS[0]["shot_uuid"]
        print("PASS every bound Generator reads its exact per-Shot Finish context while the visible editor stays on another Shot; literal prompt unchanged")

        # Replay a fully saved single manager; hidden per-Shot settings survive
        # SDK serialization and the load coordinator takes its safe no-op path.
        raw_store = deepcopy(manager.get_parameter_value(finishes.SHOT_STORE_PARAMETER_NAME))
        assert len(raw_store.get("documents", {})) == 5, {"raw_store_keys": list(raw_store), "document_count": len(raw_store.get("documents", {}))}
        serialized = send(engine, SerializeFlowToCommandsRequest(flow_name=flow.name)).serialized_flow_commands
        saved_stores = [value for value in serialized.unique_parameter_uuid_to_values.values()
            if isinstance(value, dict) and value.get("schema") == finishes.SHOT_STORE_SCHEMA]
        assert any(value.get("documents") == raw_store["documents"] for value in saved_stores), [list(value.get("documents", {})) for value in saved_stores]
        merged_documents = manager._hmb_finish_merge_snapshot()["documents"]
        old_name = flow.name
        # SDK CreateFlow(None) means the ambient flow when one exists. A real
        # reopen clears that context; discard this fixture's deleted canvas
        # before replay so it cannot become its own parent by name.
        while engine.context_manager.has_current_flow():
            engine.context_manager.pop_flow()
        send(engine, DeleteFlowRequest(flow_name=old_name))
        with migration._LOCK:
            migration._RESULTS.get(engine, {}).pop(old_name, None)
        loaded = await engine.ahandle_request(DeserializeFlowFromCommandsRequest(
            serialized_flow_commands=serialized, broadcast_result=False))
        assert loaded.succeeded(), str(loaded.result_details)
        flow = engine.flow_manager.get_flow_by_name(loaded.flow_name)
        engine.context_manager.push_flow(flow)
        source = next(node for node in flow.nodes.values() if node.metadata.get("node_type") == "HMBImageAssetLibrary")
        media_fixture(source)
        for _ in range(100):
            resumed = migration.last_migration_result(engine, flow.name)
            if resumed is not None:
                break
            await asyncio.sleep(0.02)
        assert resumed and resumed["ok"] and resumed["code"] == "already_single", resumed
        manager = flow.nodes[result["survivors"]["finish_look"]]
        reloaded_documents = manager._hmb_finish_merge_snapshot()["documents"]
        assert reloaded_documents == merged_documents, {
            "before_keys": list(merged_documents), "after_keys": list(reloaded_documents),
            "loaded_store": manager._hmb_finish_loaded_store,
            "saved_store_count": len(raw_store["documents"]),
            "restored_raw_store_keys": list((manager.get_parameter_value(finishes.SHOT_STORE_PARAMETER_NAME) or {}).get("documents", {}))}
        print("PASS real saved manager SDK reload retains all five Shot documents and completes the singleton no-op load path")

        # Restore the original five native nodes, then inject a structural
        # failure and cancellation after some deletes. Both must restore raw
        # inputs/outputs, exact names, edges and private caches before releasing.
        affected = set(result["aliases"])
        await migration._restore(engine, flow, backup, affected)
        baseline = migration._stamp(engine, flow)
        probe = engine.handle_request(SerializeFlowToCommandsRequest(flow_name=flow.name, broadcast_result=False))
        assert probe.succeeded(), str(probe.result_details)
        original_send = migration._send
        for cancelled in (False, True):
            count = {"value": 0}
            async def fail_delete(host, request, expected):
                if type(request).__name__ == "DeleteNodeRequest":
                    count["value"] += 1
                    if count["value"] == 3:
                        if cancelled:
                            raise asyncio.CancelledError()
                        raise RuntimeError("Offline forced Finish structural failure")
                return await original_send(host, request, expected)
            with mock.patch.object(migration, "_send", fail_delete):
                if cancelled:
                    try:
                        await migration.migrate_flow(engine, flow.name, backup_root=directory / "backups")
                    except asyncio.CancelledError:
                        outcome = migration.last_migration_result(engine, flow.name)
                    else:
                        raise AssertionError("Cancellation did not propagate after restoration")
                else:
                    outcome = await migration.migrate_flow(engine, flow.name, backup_root=directory / "backups")
            assert not outcome["ok"] and outcome["rollback"] == "verified", outcome
            assert migration._stamp(engine, flow) == baseline
            await asyncio.sleep(0.03)
            assert migration._stamp(engine, flow) == baseline
            for name, exported in before_exports.items():
                assert flow.nodes[name]._hmb_finish_merge_snapshot()["private_cache"] == exported["private_cache"]
            blocked = routing.reconcile_shot_routing(source)
            assert not blocked["ok"] and blocked["code"] == "workflow_migration_failed"
            assert migration._stamp(engine, flow) == baseline
        print("PASS partial deletion failure and cancellation restore exact Finish names/input/output/edges/private caches; subsequent router drain changes nothing")

        # New duplicate palette/paste loads are rejected before construction.
        inventory = set(flow.nodes)
        rejected = send(engine, CreateNodeRequest(node_type="HMBFinishLookLibrary", node_name="Forbidden Finish",
            specific_library_name="HMB_GP_Production", create_error_proxy_on_failure=False), success=False)
        assert "already loaded" in str(rejected.result_details) and set(flow.nodes) == inventory
        serialized_node = send(engine, SerializeSelectedNodesToCommandsRequest(
            nodes_to_serialize=[[next(iter(before_exports)), "fixture"]]))
        send(engine, DeserializeSelectedNodesFromCommandsRequest(
            deserialize_commands=serialized_node.serialized_selected_node_commands,
            pickled_values=serialized_node.pickled_values), success=False)
        assert set(flow.nodes) == inventory
        print("PASS second Finish palette load and official paste are refused atomically; saved legacy originals were allowed for migration")

        # A single standalone public Finish output stays wired exactly as it
        # was. Several differently authored standalone outputs are ambiguous:
        # retain every original rather than guessing a Shot from node names.
        other = send(engine, CreateFlowRequest(flow_name="StandaloneFinish", parent_flow_name=None, set_as_new_context=True))
        standalone = create("HMBFinishLookLibrary", "Standalone Finish")
        target = create("HMBSeedanceGeneration", "Standalone manual consumer")
        raw = finishes.default_widget_state()
        raw.pop("shot_manager", None)
        raw["finish_look"]["beauty"]["enabled"] = True
        raw["finish_look"]["beauty"]["brightness"] = 1.7
        standalone._hmb_capture_saved_parameter_value(finishes.WIDGET_PARAMETER_NAME, raw)
        send(engine, SetParameterValueRequest(node_name=standalone.name,
            parameter_name=finishes.WIDGET_PARAMETER_NAME, value=raw, initial_setup=True))
        standalone.after_deserialize()
        send(engine, CreateConnectionRequest(source_node_name=standalone.name, source_parameter_name="FINISH_LOOK_OUT",
            target_node_name=target.name, target_parameter_name="prompt", initial_setup=True))
        standalone_flow = engine.flow_manager.get_flow_by_name(other.flow_name)
        old_edges = migration._edge_records(engine, set(standalone_flow.nodes))
        old_output = standalone.parameter_output_values.get("FINISH_LOOK_OUT")
        outcome = await migration.migrate_flow(engine, other.flow_name, backup_root=directory / "backups")
        assert outcome["ok"] and migration._edge_records(engine, set(standalone_flow.nodes)) == old_edges
        assert standalone.parameter_output_values.get("FINISH_LOOK_OUT") == old_output
        extra = create("HMBFinishLookLibrary", "Different standalone Finish")
        second = create("HMBSeedanceGeneration", "Another standalone manual consumer")
        different = deepcopy(raw)
        different["finish_look"]["beauty"]["brightness"] = 0.8
        extra._hmb_capture_saved_parameter_value(finishes.WIDGET_PARAMETER_NAME, different)
        send(engine, SetParameterValueRequest(node_name=extra.name,
            parameter_name=finishes.WIDGET_PARAMETER_NAME, value=different, initial_setup=True))
        extra.after_deserialize()
        send(engine, CreateConnectionRequest(source_node_name=extra.name, source_parameter_name="FINISH_LOOK_OUT",
            target_node_name=second.name, target_parameter_name="prompt", initial_setup=True))
        before = migration._stamp(engine, standalone_flow)
        outcome = await migration.migrate_flow(engine, other.flow_name, backup_root=directory / "backups")
        assert not outcome["ok"] and outcome["rollback"] == "not_needed", outcome
        await asyncio.sleep(0.03)
        assert migration._stamp(engine, standalone_flow) == before and len(standalone_flow.nodes) == 4
        print("PASS single standalone FINISH_LOOK_OUT and authored state stay exact; ambiguous differently authored standalone outputs retain every original and report conflict")

        # The real SDK must carry the optional command through before/set/after,
        # not merely a direct Python helper. Creative and public outputs stay
        # on the existing nine-key/Beauty schema contracts.
        clock_flow = send(engine, CreateFlowRequest(flow_name="FinishUITransport", parent_flow_name=None, set_as_new_context=True))
        clock_node = create("HMBFinishLookLibrary", "Native UI Clock Finish")
        def ui_wire(node):
            node._restore_widget_parameter(live=False)
            return deepcopy(node.get_parameter_value(finishes.WIDGET_PARAMETER_NAME))
        def ui_command(node, operation, sequence, *, brightness=None, supplied_clock=None, epoch=""):
            value = deepcopy(node._widget_state)
            if brightness is not None:value["finish_look"]["beauty"].update(enabled=True, brightness=brightness)
            clock = supplied_clock or ui_wire(node)[finishes.UI_TRANSPORT_KEY]
            value[finishes.UI_TRANSPORT_KEY] = dict(schema=finishes.UI_TRANSPORT_SCHEMA,version=1,
                operation=operation,session_id=clock["session_id"],base_revision=clock["revision"],
                base_target_revision=clock["target_revisions"]["__standalone__"],client_id="native-ui-editor",
                client_epoch=epoch,request_id=f"native-ui-{sequence}",sequence=sequence)
            return value
        def apply_ui(node, value):
            send(engine, SetParameterValueRequest(node_name=node.name,parameter_name=finishes.WIDGET_PARAMETER_NAME,
                value=value,initial_setup=False))
            return ui_wire(node)[finishes.UI_TRANSPORT_KEY]
        before_outputs=deepcopy(dict(clock_node.parameter_output_values))
        with mock.patch.object(finishes,"compile_finish_look_prompt",side_effect=AssertionError("Native UI refresh compiled")):
            acknowledgement=apply_ui(clock_node,ui_command(clock_node,"refresh",1))
        assert acknowledgement["status"]=="refreshed" and acknowledgement["request_id"]=="native-ui-1"
        # SDK live property publication also mirrors the UI parameter in its
        # output map. Only this transport property may change on refresh.
        assert {key:value for key,value in dict(clock_node.parameter_output_values).items() if key!=finishes.WIDGET_PARAMETER_NAME}==before_outputs
        epoch=acknowledgement["client_epoch"];assert epoch
        editing=ui_command(clock_node,"edit",2,brightness=1.2,epoch=epoch)
        acknowledgement=apply_ui(clock_node,editing)
        assert acknowledgement["status"]=="accepted" and acknowledgement["request_id"]=="native-ui-2",acknowledgement
        assert clock_node._last_valid_state["beauty"]["brightness"]==1.2 and clock_node._last_valid_state["beauty"]["enabled"]
        assert len(clock_node._widget_state)==9 and finishes.UI_TRANSPORT_KEY not in clock_node._last_valid_state
        assert clock_node.parameter_output_values[finishes.FINISH_LOOK_OUTPUT_PARAMETER_NAME]==finishes.compile_finish_look_prompt(clock_node._last_valid_state)
        remote_revision=clock_node._remote_revision
        assert apply_ui(clock_node,editing)["status"]=="duplicate" and clock_node._remote_revision==remote_revision
        old_session=ui_wire(clock_node)[finishes.UI_TRANSPORT_KEY]["session_id"]
        saved=send(engine,SerializeFlowToCommandsRequest(flow_name=clock_flow.flow_name)).serialized_flow_commands
        saved_ui_values=[value for value in saved.unique_parameter_uuid_to_values.values() if isinstance(value,dict) and finishes.UI_TRANSPORT_KEY in value]
        assert saved_ui_values and all(len(finishes.validate_widget_state(value))==9 for value in saved_ui_values)
        while engine.context_manager.has_current_flow():engine.context_manager.pop_flow()
        send(engine,DeleteFlowRequest(flow_name=clock_flow.flow_name))
        reopened=await engine.ahandle_request(DeserializeFlowFromCommandsRequest(serialized_flow_commands=saved,broadcast_result=False))
        assert reopened.succeeded(),str(reopened.result_details)
        reopened_flow=engine.flow_manager.get_flow_by_name(reopened.flow_name);engine.context_manager.push_flow(reopened_flow)
        clock_node=reopened_flow.nodes["Native UI Clock Finish"]
        assert clock_node._last_valid_state["beauty"]["brightness"]==1.2
        assert ui_wire(clock_node)[finishes.UI_TRANSPORT_KEY]["session_id"]!=old_session
        assert apply_ui(clock_node,editing)["status"]=="stale_session"
        refreshed=apply_ui(clock_node,ui_command(clock_node,"refresh",3,epoch=epoch))
        assert refreshed["status"]=="refreshed" and clock_node._last_valid_state["beauty"]["brightness"]==1.2
        assert len(clock_node._widget_state)==9 and clock_node._hmb_finish_ui_clients["native-ui-editor"]["client_epoch"]!=epoch
        assert finishes.UI_TRANSPORT_KEY not in clock_node.get_parameter_value(finishes.SHOT_STORE_PARAMETER_NAME)
        print("PASS actual SetParameterValueRequest refresh/edit/duplicate carries UI request ID and lease; official save/reload preserves Beauty with a fresh instance session and rejects old commands; refresh compiles nothing")
    finally:
        LibraryRegistry.unregister_library("HMB_GP_Production", event_manager=engine.event_manager)


def main():
    with tempfile.TemporaryDirectory(prefix="hmb-finish-consolidation-") as directory:
        root = Path(directory)
        overrides = {key: str(root / leaf) for key, leaf in (("XDG_CONFIG_HOME", "config"),
            ("XDG_DATA_HOME", "data"), ("XDG_CACHE_HOME", "cache"), ("APPDATA", "app"),
            ("LOCALAPPDATA", "local"), ("GTN_CONFIG_WORKSPACE_DIRECTORY", "workspace"), ("HMB_IMAGE_PROJECTS_ROOT", "images"))}
        for value in overrides.values():
            Path(value).mkdir(parents=True, exist_ok=True)
        with mock.patch.dict(os.environ, overrides), ExitStack() as stack:
            stack.enter_context(mock.patch.object(socket, "create_connection", deny_network))
            try:
                from griptape_nodes.retained_mode.engine import engine_scope
            except ImportError:
                print("HMB_FINISH_MULTISHOT_CONSOLIDATION_HOST=SKIP (installed SDK required)")
                return
            import _hmb_shot_routing as routing
            import _hmb_library_bootstrap as bootstrap
            import HMBImageAssetLibrary as images
            import HMBSeedanceGeneration as generators
            stack.enter_context(mock.patch.object(bootstrap._Registration, "start_web_worker", lambda *a, **k: None))
            for name in ("schedule_post_registration_reconcile", "schedule_post_hydration_reconcile"):
                stack.enter_context(mock.patch.object(routing, name, lambda *a, **k: False))
            stack.enter_context(mock.patch.object(images.HMBImageAssetLibrary, "_schedule_catalog_scan", lambda *a, **k: None))
            stack.enter_context(mock.patch.object(generators.HMBSeedanceGeneration, "_process_generation", deny_execution))
            logging.disable(logging.CRITICAL)
            with engine_scope() as engine:
                asyncio.run(exercise(engine, root))
            assert NETWORK == [] and EXECUTED == []
    print("HMB_FINISH_MULTISHOT_CONSOLIDATION_HOST=PASS (actual SDK; no network, render or user graph changes)")


if __name__ == "__main__":
    main()
