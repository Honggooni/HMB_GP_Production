"""Isolated real-SDK HMB creation, source-selection and replacement lifecycle.

No user workflow, engine transport, provider or model is used.  Native node
requests, retained connections, source manifests, publisher snapshots and
deferred HMB routing remain real; only discovery/polling/execution boundaries
are replaced by offline fixtures.
"""
from __future__ import annotations

import asyncio
import base64
from contextlib import ExitStack
from copy import copy, deepcopy
import hashlib
import importlib.util
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
KINDS = ("HMBImageAssetLibrary", "HMBVideoPickerLibrary", "HMBPromptLibrary",
         "HMBAgentLibrary", "HMBFinishLookLibrary", "HMBSeedanceGeneration")
CHANNEL = "11111111-1111-4111-8111-111111111111"
PUBLISHER = "22222222-2222-4222-8222-222222222222"
SHOTS = [dict(shot_uuid=f"33333333-3333-4333-8333-{i:012d}", number=i,
              name=f"Named asset {letter}", name_is_custom=True, revision=1,
              selected_source_uids=[]) for i, letter in enumerate("QAZWX", 1)]
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4////fwAJ+wP9KobjigAAAABJRU5ErkJggg==")
ATTEMPTS = []
RESULTS = []


def deny(*args, **kwargs):
    ATTEMPTS.append("execution_or_transport")
    raise AssertionError("The lifecycle fixture must not execute transport, model or rendering")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


def send(engine, request):
    request.broadcast_result = False
    result = engine.handle_request(request)
    assert result.succeeded(), str(result.result_details)
    return result


async def asend(engine, request):
    request.broadcast_result = False
    result = await engine.ahandle_request(request)
    assert result.succeeded(), str(result.result_details)
    return result


def create_project(images, folder):
    catalog = folder / "Projects"
    root = catalog / "Katuri8" / "Ai_Ct_image"
    entries = []
    for number in range(1, 11):
        path = root / "Character" / f"asset-{number}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(PNG)
        entries.append(dict(path=path.relative_to(root).as_posix(), asset_id=f"NativeAsset{number}",
            image_name=f"Native asset {number}", image_main_type="Character", image_sub_type="Full Appearance"))
    metadata = root / ".json"
    metadata.mkdir()
    (metadata / "hmb_image_assets.json").write_text(json.dumps(dict(assets=entries)), encoding="utf-8")
    state = images._select_catalog_project(images._load_project_catalog(catalog, images._default_state()), root)
    assert len(state["assets"]) == 10 and all(row["registered"] for row in state["assets"])
    ordered = sorted(state["assets"], key=lambda row: int(row["asset_id"].removeprefix("NativeAsset")))
    for number, row in enumerate(ordered, 1):
        row["selected"], row["selection_order"] = True, number
    state["assets"] = ordered
    shots = deepcopy(SHOTS)
    for number, shot in enumerate(shots):
        shot["selected_source_uids"] = [ordered[number * 2 + 1]["source_uid"], ordered[number * 2]["source_uid"]]
    state["shot_routing"].update(channel_uuid=CHANNEL, publisher_instance_uuid=PUBLISHER,
        generation=10, shots=shots, active_shot_uuid=shots[0]["shot_uuid"])
    return images._normalize_state(state)


def register(engine, modules):
    from griptape_nodes.node_library.library_registry import LibraryRegistry, LibrarySchema
    schema = LibrarySchema.model_validate_json((ROOT / "griptape-nodes-library.json").read_text("utf-8-sig"))
    library = LibraryRegistry.generate_new_library(schema)
    for definition in schema.nodes:
        module = modules.get(definition.class_name)
        if module:
            cls = getattr(module, definition.class_name)
            library.register_lazy_node_type(definition.class_name, definition.metadata, lambda cls=cls: cls)
    return library, schema


def edges(engine, flow):
    from griptape_nodes.retained_mode.events.connection_events import ListConnectionsForNodeRequest
    records = set()
    for node in flow.nodes.values():
        result = send(engine, ListConnectionsForNodeRequest(node_name=node.name))
        for edge in result.outgoing_connections:
            records.add((node.name, edge.source_parameter_name,
                         edge.target_node_name, edge.target_parameter_name))
    return records


async def settle(predicate, *, seconds=2.0):
    end = asyncio.get_running_loop().time() + seconds
    while asyncio.get_running_loop().time() < end:
        if predicate():
            # Permit already queued callbacks to run before accepting a stable graph.
            await asyncio.sleep(.03)
            if predicate():
                return
        await asyncio.sleep(.01)
    assert predicate(), "Deferred native lifecycle did not settle"


def prompt_rows(prompt, prompts, shot):
    state = prompts._select_prompt_shot_document(deepcopy(prompt._current_state()), shot)
    return prompt_rows_from_state(prompt,state)


def prompt_rows_from_state(prompt,state):
    view = copy(prompt)
    # Match the production _hmb_prompt_shot_document copy-view ownership. A
    # shallow copy itself is deliberately not a registered graph publisher.
    view._hmb_execution_registered_owner=prompt
    projected, images, videos, exact, _ = view._apply_exact_shot_routes(state)
    assert exact
    return projected, images, videos


def assert_graph(engine, flow, nodes, shots):
    source, picker, prompt, agent, finish = (nodes[k] for k in KINDS[:5])
    e = edges(engine, flow)
    required = {(source.name, "SHOT_ASSET_OUT", prompt.name, "SHOT_ASSET_IN"),
                (picker.name, "SHOT_PICKER_OUT", prompt.name, "SHOT_PICKER_IN"),
                (prompt.name, "PROMPT_OUT", agent.name, "SHOT_PROMPT_IN")}
    bindings = {}
    for generator in nodes[KINDS[5]]:
        sub = generator._hmb_shot_channel_subscription()
        assert sub["channel_uuid"] == CHANNEL and sub["shot_uuid"] not in bindings, sub
        bindings[sub["shot_uuid"]] = generator
        required.update({(source.name, "SHOT_ASSET_OUT", generator.name, "SHOT_ASSET_IN"),
            (picker.name, "SHOT_PICKER_OUT", generator.name, "SHOT_PICKER_IN"),
            (agent.name, "output", generator.name, "prompt"),
            (finish.name, "SHOT_FINISH_LOOK_OUT", generator.name, "SHOT_FINISH_LOOK_IN")})
    assert set(bindings) == {row["shot_uuid"] for row in shots}
    assert required <= e, sorted(required-e)
    return bindings


async def scenario(engine, modules, state, order, label, replacement=None):
    from griptape_nodes.node_library.library_registry import LibraryRegistry
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    from griptape_nodes.retained_mode.events.node_events import (CreateNodeRequest, DeleteNodeRequest,
        SerializeNodeToCommandsRequest, DeserializeNodeFromCommandsRequest)
    from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
    images, pickers, prompts, agents, finishes, generators = (modules[k] for k in KINDS)
    library, schema = register(engine, modules)
    engine.event_manager.initialize_queue()
    flow = engine.flow_manager.get_flow_by_name(send(engine, EnsureWorkflowAndFlowRequest(flow_name=label)).flow_name)
    nodes = {}
    def create(kind, name, seed_source=True):
        result = send(engine, CreateNodeRequest(node_type=kind, specific_library_name=schema.name,
            node_name=name, create_error_proxy_on_failure=False))
        node = engine.node_manager.get_node_by_name(result.node_name)
        if kind == KINDS[0] and seed_source:
            node._hmb_initial_catalog_scan_pending = False
            # This tiny local manifest is resolved synchronously as the media
            # boundary. Keep the production cache's own state identity, so the
            # first retained-mode publication need not start a share worker.
            node._resolution_cache_for_state(deepcopy(state))
            node._cache_shot_routing_snapshot(deepcopy(state), force=True)
            node._publish_state(deepcopy(state))
        return node
    try:
        for kind in order:
            if kind == KINDS[5]:
                nodes[kind] = [create(kind, f"Render-{letter}") for letter in "VNZBE"]
            else:
                nodes[kind] = create(kind, f"Native-{kind}")
            await asyncio.sleep(.02)
        source = nodes[KINDS[0]]
        shots = source._hmb_shot_routing_snapshot()["shots"]
        def ready():
            try:
                assert_graph(engine, flow, nodes, shots)
                return True
            except (AssertionError, KeyError, ValueError) as exc:
                ready.failure = str(exc)
                return False
        try:
            await settle(ready)
        except AssertionError:
            print("LIFECYCLE_NOT_READY "+json.dumps(dict(label=label, reason=getattr(ready,"failure",""),
                subscriptions={kind:[node._hmb_shot_channel_subscription() for node in value]
                    if isinstance(value,list) else value._hmb_shot_channel_subscription()
                    for kind,value in nodes.items()},edges=sorted(edges(engine,flow))),ensure_ascii=False))
            raise
        bindings = assert_graph(engine, flow, nodes, shots)
        prompt, agent, finish = nodes[KINDS[2]], nodes[KINDS[3]], nodes[KINDS[4]]
        # Remote metadata-only fixture videos make authored Color Picks refer
        # to a stable video UID. Empty Picker selection intentionally clears
        # former video bindings and is a different, already covered contract.
        picker=nodes[KINDS[1]]
        picker_state=picker._picker_state()
        picker_state["videos"]=[dict(video_uid=f"fixture-video-{i}",source_uid=f"fixture-video-{i}",
            video_url=f"https://media.invalid/fixture-video-{i}.mp4",label=f"Synthetic video {i}",
            selected=True,selection_order=i,video_slot=i) for i in range(1,6)]
        picker_state["picker_shots"]=[pickers._new_picker_workspace_row(i,
            bound_shot_uuid=shot["shot_uuid"],video_asset_uids=[f"fixture-video-{i}"],
            selected_video_uids=[f"fixture-video-{i}"],preview_video_uid=f"fixture-video-{i}")
            for i,shot in enumerate(shots,1)]
        picker_state["active_picker_shot_uuid"]=picker_state["picker_shots"][0]["workspace_uuid"]
        picker._write_state(picker_state)
        picker_state=picker._picker_state()
        # Availability is known for fixture-only opaque remote strings; this
        # is the media boundary, not a substituted snapshot or route getter.
        picker._hmb_verified_media=(picker._execution_media_identity(picker_state),{})
        picker._sync_outputs_from_state(picker_state,enforce_media_availability=False)
        prompt_state = prompt._current_state()
        text_key = next(iter(prompts.TEXT_FIELD_DEFAULTS))
        for shot in shots:
            prompt_state = prompts._select_prompt_shot_document(prompt_state, dict(shot, channel_uuid=CHANNEL))
            prompt_state = prompt_rows_from_state(prompt, prompt_state)[0]
            prompt_state["text"][text_key] = f"Authored {shot['shot_uuid']} {{literal}} RGB(12, 34, 56) OFF 0"
            for row in prompt_state["images"]:
                if row.get("asset_source_uid"):
                    row["color_picks"] = ["Red"]
            prompt_state = prompts._store_prompt_shot_document(prompt_state)
        send(engine, SetParameterValueRequest(node_name=prompt.name, parameter_name=prompts.WIDGET_PARAMETER_NAME,
            value=prompts._json_dumps(prompt_state), initial_setup=True))
        prompt._sync_prompt_output_now()
        finish_expected={}
        for shot in shots:
            authored=deepcopy(finish._widget_state)
            authored["shot"]=dict(shot,channel_uuid=CHANNEL)
            send(engine,SetParameterValueRequest(node_name=finish.name,parameter_name=finishes.WIDGET_PARAMETER_NAME,value=authored))
            authored=deepcopy(finish._widget_state)
            authored["finish_look"]["beauty"].update(enabled=shot["number"]%2==1,brightness=1+shot["number"]/10)
            send(engine,SetParameterValueRequest(node_name=finish.name,parameter_name=finishes.WIDGET_PARAMETER_NAME,value=authored))
            finish_expected[shot["shot_uuid"]]=deepcopy(authored["finish_look"])
        # Use real native property setters and the real slot switch/capture.
        # No Agent process, policy bootstrap, model or provider is invoked.
        catalog = source._hmb_shot_routing_catalog()
        for shot in shots:
            send(engine, SetParameterValueRequest(node_name=agent.name, parameter_name=agents._AGENT_WIDGET_PARAMETER,
                value=agent._hmb_widget_value(dict(shot,channel_uuid=CHANNEL),catalog,shot_manager=True)))
            send(engine, SetParameterValueRequest(node_name=agent.name, parameter_name="additional_context",
                value=f"Independent native authoring {shot['shot_uuid']}"))
            send(engine, SetParameterValueRequest(node_name=agent.name, parameter_name="output_schema",
                value={"type":"object","properties":{f"slot{shot['number']}":{"type":"string"}}}))
        send(engine, SetParameterValueRequest(node_name=agent.name, parameter_name=agents._AGENT_WIDGET_PARAMETER,
            value=agent._hmb_widget_value(dict(shots[0],channel_uuid=CHANNEL),catalog,shot_manager=True)))
        agent._hmb_capture_active_slot()
        await asyncio.sleep(.05)
        authored_prompt=authored_agent=authored_picker=authored_finish=True
        async def verify_documents():
            for shot in shots:
                for attempt in range(200):
                    try:
                        document = prompt._hmb_prompt_shot_document(channel_uuid=CHANNEL, shot_uuid=shot["shot_uuid"])
                        projected, media, _ = prompt_rows(prompt, prompts, dict(shot, channel_uuid=CHANNEL))
                        break
                    except ValueError as exc:
                        if not (getattr(exc,"hmb_image_asset_selection_preparing",False) is True
                                or getattr(exc,"hmb_picker_media_preparing",False) is True):
                            raise
                        if attempt==199:raise
                        await asyncio.sleep(.01)
                selected = [row for row in projected["images"] if row.get("asset_source_uid")]
                assert [row["asset_source_uid"] for row in selected] == shot["selected_source_uids"]
                assert all(row["image_main_type"] == "Character" and row["image_sub_type"] == "Full Appearance" for row in selected)
                if authored_prompt and authored_picker:
                    assert all(row["color_picks"] == ["Red"] for row in selected), (label,shot["number"],[(row["asset_source_uid"],row["color_picks"]) for row in selected])
                assert document["image_media"] == media and len(media) == 2
                if authored_prompt:
                    assert f"Authored {shot['shot_uuid']}" in document["machine_prompt"], (label,shot["number"],
                        prompt._current_state()["shot"],
                        {key:json.loads(value)["text"].get(text_key) for key,value in prompt._hmb_prompt_merge_snapshot()["materialized_documents"].items()})
                key = agent._hmb_slot_key(CHANNEL,shot["shot_uuid"])
                if authored_agent:
                    assert agent._hmb_shot_slots[key]["values"]["additional_context"] == f"Independent native authoring {shot['shot_uuid']}"
                if authored_finish:
                    assert finish._hmb_finish_look_shot_snapshot_for(channel_uuid=CHANNEL,shot_uuid=shot["shot_uuid"])["finish_look_state"]==finish_expected[shot["shot_uuid"]]
        await verify_documents()
        if replacement:
            kind, hydrated = replacement
            old = nodes[kind][2] if kind == KINDS[5] else nodes[kind]
            pool = {}
            serialized = send(engine, SerializeNodeToCommandsRequest(node_name=old.name,
                unique_parameter_uuid_to_values=pool, serialize_all_parameter_values=True))
            from griptape_nodes.serialization.values import decode_value
            before_uuids = {g.name:g._hmb_shot_channel_subscription()["shot_uuid"] for g in nodes[KINDS[5]]}
            if kind==KINDS[0]:
                print("SOURCE_REPLACEMENT_BEFORE "+json.dumps({key:json.loads(value)["text"].get(text_key) for key,value in prompt._hmb_prompt_merge_snapshot()["materialized_documents"].items()}),flush=True)
            if kind==KINDS[1]:
                original_mark=prompt._mark_deleted_document_source
                def mark_probe(retiring,target_name):
                    live=prompt._current_state()
                    print("PICKER_DELETE_MARK_ENTRY "+json.dumps(dict(target=target_name,shot=live["shot"],
                        colors=[(row.get("asset_source_uid"),row.get("color_picks")) for row in live["images"] if row.get("asset_source_uid")]),ensure_ascii=False),flush=True)
                    return original_mark(retiring,target_name)
                with mock.patch.object(prompt,"_mark_deleted_document_source",mark_probe):
                    await asend(engine, DeleteNodeRequest(node_name=old.name))
            else:
                await asend(engine, DeleteNodeRequest(node_name=old.name))
            assert old.name not in flow.nodes and old._hmb_node_deleted is True
            if kind==KINDS[0]:
                print("SOURCE_REPLACEMENT_DELETED "+json.dumps({key:json.loads(value)["text"].get(text_key) for key,value in prompt._hmb_prompt_merge_snapshot()["materialized_documents"].items()}),flush=True)
            if hydrated:
                commands = deepcopy(serialized.serialized_node_commands)
                commands.create_node_command.node_name = old.name
                commands.create_node_command.override_parent_flow_name = flow.name
                result = await asend(engine, DeserializeNodeFromCommandsRequest(serialized_node_commands=commands))
                replacement_node = engine.node_manager.get_node_by_name(result.node_name)
                for indirect in serialized.set_parameter_value_commands:
                    request = deepcopy(indirect.set_parameter_value_command)
                    request.node_name = replacement_node.name
                    request.value = decode_value(deepcopy(pool[indirect.unique_value_uuid]))
                    request.initial_setup = True
                    send(engine,request)
            else:
                replacement_node = create(kind,old.name,seed_source=kind!=KINDS[0])
            assert replacement_node is not old
            if kind == KINDS[5]:nodes[kind][2]=replacement_node
            else:nodes[kind]=replacement_node
            source,prompt,agent,finish=nodes[KINDS[0]],nodes[KINDS[2]],nodes[KINDS[3]],nodes[KINDS[4]]
            if kind==KINDS[0] and not hydrated:
                await asyncio.sleep(.15)
                new_catalog=source._hmb_shot_routing_catalog()
                assert new_catalog["channel_uuid"]!=CHANNEL
                assert not {row["shot_uuid"] for row in new_catalog["shots"]}&{row["shot_uuid"] for row in shots}
                preserved=prompt._hmb_prompt_merge_snapshot()["materialized_documents"]
                for shot in shots:
                    key=CHANNEL+"/"+shot["shot_uuid"]
                    assert json.loads(preserved[key])["text"][text_key]==f"Authored {shot['shot_uuid']} {{literal}} RGB(12, 34, 56) OFF 0"
                    try:prompt._hmb_prompt_shot_document(channel_uuid=CHANNEL,shot_uuid=shot["shot_uuid"])
                    except (RuntimeError,ValueError):pass
                    else:raise AssertionError("A blank new source implicitly acquired an archived old-channel document")
                RESULTS.append(dict(case=label,order=list(order),replacement=replacement,passed=True,
                    archived_UUID_documents=5,new_channel_not_inferred=True,old_document_execution_rejected=True))
                print("LIFECYCLE_CASE_PASS "+label,flush=True)
                return
            try:
                await settle(ready)
            except AssertionError:
                print("REPLACEMENT_NOT_READY "+json.dumps(dict(label=label,reason=getattr(ready,"failure",""),
                    agent=agent._hmb_shot_channel_subscription(),
                    generators=[g._hmb_shot_channel_subscription() for g in nodes[KINDS[5]]],
                    edges=sorted(edges(engine,flow))),ensure_ascii=False),flush=True)
                raise
            assert_graph(engine,flow,nodes,shots)
            if kind==KINDS[1] and hydrated:
                def visible_colors_restored():
                    current=prompt._current_state()
                    selected=[row for row in current["images"] if row.get("asset_source_uid")]
                    return current["shot"]["shot_uuid"]==shots[-1]["shot_uuid"] and len(selected)==2 and all(row["color_picks"]==["Red"] for row in selected)
                await settle(visible_colors_restored)
            for generator in nodes[KINDS[5]]:
                assert generator._hmb_shot_channel_subscription()["shot_uuid"] == before_uuids[generator.name]
            if not hydrated:
                # A deliberately blank replacement may adopt only source
                # identity. It must not infer deleted authoring from its name.
                if kind == KINDS[2]:
                    assert not any("Authored " in value for value in nodes[kind]._hmb_prompt_merge_snapshot()["materialized_documents"].values())
                if kind == KINDS[3]:
                    assert not any("Independent native authoring" in str(slot) for slot in nodes[kind]._hmb_shot_slots.values())
                authored_prompt=kind!=KINDS[2]
                authored_agent=kind!=KINDS[3]
                authored_picker=kind!=KINDS[1]
                authored_finish=kind!=KINDS[4]
            await verify_documents()
        if label == "LifecycleOrder0":
            # A same-UUID source selection updates only its image ordering.
            # It does not switch Prompt to the ImageAsset's active Shot.
            source_state=source._current_state();route=deepcopy(source_state["shot_routing"])
            route["shots"][4]["selected_source_uids"].reverse();route["shots"][4]["revision"]+=1;route["generation"]+=1
            edit=dict(schema=images.IMAGE_ASSET_EDIT_SCHEMA,version=1,scan_revision=source_state["scan_revision"],
                ui_edit_revision=source_state[images.UI_EDIT_REVISION_KEY]+1,
                catalog_identity={key:source_state[key] for key in ("catalog_root","project_root","project_uid","project_cache_uid","manifest_signature","folder_signature","scan_revision")},
                selected_source_uids=[row["source_uid"] for row in sorted(source_state["assets"],key=lambda row:row["selection_order"]) if row["selected"]],
                edits={"shot_routing":route})
            selected_prompt_uuid=prompt._current_state()["shot"]["shot_uuid"]
            send(engine,SetParameterValueRequest(node_name=source.name,parameter_name=images.WIDGET_STATE_PARAMETER,value=json.dumps(edit)))
            shots=source._hmb_shot_routing_snapshot(cached_only=True)["shots"]
            await settle(lambda:prompt._current_state()["image_asset"]["shot_catalog_routing"]["generation"]>=route["generation"])
            assert prompt._current_state()["shot"]["shot_uuid"]==selected_prompt_uuid
            await verify_documents()
            # Other Shots may rename or exchange their display number. This
            # updates tiny row metadata only, never the selected native form.
            active_before=agent._hmb_active_slot_key
            body_before={key:deepcopy(agent._native_parameter_value(key,None)) for key in
                ("provider","model","prompt","additional_context","tools","rulesets","output_schema")}
            elements_before=[(id(element),str(getattr(element,"element_id",""))) for element in agent._hmb_native_editor_elements]
            source_state=source._current_state();route=deepcopy(source_state["shot_routing"])
            route["shots"][1]["number"],route["shots"][2]["number"]=route["shots"][2]["number"],route["shots"][1]["number"]
            for shot in route["shots"][1:3]:shot["name"]+=" renamed";shot["revision"]+=1
            route["shots"].sort(key=lambda row:row["number"]);route["generation"]+=1
            body_writes=[];native=agents.HMBAgentLibrary.__mro__[1];native_setter=native.set_parameter_value
            def record_native(owner,name,*args,**kwargs):
                if owner is agent and name in body_before:body_writes.append(name)
                return native_setter(owner,name,*args,**kwargs)
            with mock.patch.object(native,"set_parameter_value",record_native),mock.patch.object(agent,"reorder_elements",wraps=agent.reorder_elements) as reordered,mock.patch.object(agent,"_hmb_switch_native_slot",wraps=agent._hmb_switch_native_slot) as switched:
                edit.update(scan_revision=source_state["scan_revision"],ui_edit_revision=source_state[images.UI_EDIT_REVISION_KEY]+1,
                    catalog_identity={key:source_state[key] for key in edit["catalog_identity"]},edits={"shot_routing":route})
                send(engine,SetParameterValueRequest(node_name=source.name,parameter_name=images.WIDGET_STATE_PARAMETER,value=json.dumps(edit)))
                await settle(lambda:agent._hmb_shot_catalog_snapshot["generation"]>=route["generation"])
                await asyncio.sleep(.15)
                assert body_writes==[],body_writes
                assert reordered.call_count==0,reordered.call_count
                # The retained callback may call the idempotent slot guard;
                # every such call must target the already active UUID, so no
                # native slot transition/capture/restore can occur.
                assert all(agent._hmb_slot_key(*call.args,**call.kwargs)==active_before
                           for call in switched.call_args_list),switched.call_args_list
            assert agent._hmb_active_slot_key==active_before
            assert {key:agent._native_parameter_value(key,None) for key in body_before}==body_before
            assert [(id(element),str(getattr(element,"element_id",""))) for element in agent._hmb_native_editor_elements]==elements_before
            shots=source._hmb_shot_routing_snapshot(cached_only=True)["shots"]
            await verify_documents()
        RESULTS.append(dict(case=label, order=list(order), replacement=replacement, passed=True,
            exact_shot_UUIDs=5, exact_prompt_documents=5, generators=5, actual_image_selection=True,
            Main_Sub_metadata=True, Color_Pick_preserved=authored_prompt and authored_picker,
            preserved_survivor_authoring=True,retained_edges=len(edges(engine, flow))))
        print("LIFECYCLE_CASE_PASS "+label,flush=True)
    finally:
        LibraryRegistry.unregister_library(schema.name, event_manager=engine.event_manager)


def main():
    try:
        from griptape_nodes.retained_mode.engine import engine_scope
    except ImportError:
        print("HMB_LIBRARY_LIFECYCLE_ORDER_HOST=SKIP (installed SDK required)")
        return
    previous = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="hmb-lifecycle-sdk-") as temp:
        folder = Path(temp)
        env = {key: str(folder/leaf) for key, leaf in (("XDG_CONFIG_HOME","config"),("XDG_DATA_HOME","data"),
            ("XDG_CACHE_HOME","cache"),("XDG_STATE_HOME","state"),("LOCALAPPDATA","local"),("APPDATA","app"),
            ("GTN_ENGINE_CONFIG_DIR","engine"),("GTN_ENGINE_DATA_DIR","engine-data"),("GTN_ENGINE_STATE_DIR","engine-state"),
            ("GTN_CONFIG_WORKSPACE_DIRECTORY","workspace"),("HMB_IMAGE_PROJECTS_ROOT","Projects"))}
        for value in env.values():Path(value).mkdir(parents=True,exist_ok=True)
        with mock.patch.dict(os.environ,env), ExitStack() as guard:
            os.chdir(folder)
            try:
                modules = {name: __import__(name) for name in KINDS}
                import _hmb_library_bootstrap as bootstrap
                for module in modules.values():
                    cls = getattr(module,module.__name__)
                    guard.enter_context(mock.patch.object(cls,"process",deny))
                guard.enter_context(mock.patch.object(modules[KINDS[0]].HMBImageAssetLibrary,"_schedule_catalog_scan",lambda *a,**k:False))
                guard.enter_context(mock.patch.object(bootstrap._Registration,"start_web_worker",lambda *a,**k:None))
                guard.enter_context(mock.patch.object(socket,"create_connection",deny))
                logging.disable(logging.CRITICAL)
                source_state = create_project(modules[KINDS[0]],folder)
                orders = [KINDS[i:]+KINDS[:i] for i in range(len(KINDS))]
                orders += [tuple(reversed(KINDS)),(KINDS[2],KINDS[3],KINDS[4],KINDS[5],KINDS[1],KINDS[0])]
                cases=[(order,f"LifecycleOrder{index}",None) for index,order in enumerate(orders)]
                cases += [(KINDS,f"HydratedReplacement{index}",(kind,True)) for index,kind in enumerate(KINDS)]
                cases += [(KINDS,f"BlankReplacement{index}",(kind,False)) for index,kind in enumerate(KINDS)]
                selected_case=os.environ.get("HMB_LIFECYCLE_CASE")
                if selected_case:
                    selected=set(selected_case.split(","))
                    cases=[item for item in cases if item[1] in selected]
                    assert cases,"Unknown isolated lifecycle case"
                for order,label,replacement in cases:
                    with engine_scope() as engine:
                        # Runner must capture this exact engine_scope; a Runner
                        # created outside it would make GriptapeNodes' static
                        # lifecycle calls consult the unrelated default engine.
                        with asyncio.Runner() as runner:
                            runner.run(scenario(engine,modules,source_state,order,label,replacement))
                assert not ATTEMPTS,ATTEMPTS
                print("HMB_LIBRARY_LIFECYCLE_ORDER_HOST=PASS "+json.dumps(dict(cases=RESULTS,execution_calls=0,paid_calls=0),ensure_ascii=False))
            finally:
                logging.shutdown()
                os.chdir(previous)


if __name__ == "__main__":
    main()
