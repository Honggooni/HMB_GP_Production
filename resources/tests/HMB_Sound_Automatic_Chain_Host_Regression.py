"""Real advanced-library aliases and automatic Sound routing, without Save.

Every node, source snapshot, post-registration callback and routing operation
is real. Only unrelated editor installation/background web work is disabled.
Projects and WAV files are synthetic, local and confined to the test profile.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import ExitStack
from copy import deepcopy
import json
from pathlib import Path
import sys
from unittest import mock
import wave

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "resources/tests")]
import HMB_Seedance_Execution_Mode_Host_Regression as harness

CHANNEL = "11111111-1111-4111-8111-111111111111"
PUBLISHER = "22222222-2222-4222-8222-222222222222"
SHOTS = [{"shot_uuid": f"33333333-3333-4333-8333-{number:012d}", "number": number,
    "name": f"Auto Shot {number}", "revision": 1, "selected_source_uids": []} for number in range(1, 4)]


async def exercise(engine, phase, out):
    import _hmb_library_bootstrap as bootstrap
    import _hmb_shot_routing as routing
    import _hmb_sound as sound_helper
    from griptape_nodes.node_library.library_registry import LibraryRegistry, LibrarySchema
    from griptape_nodes.retained_mode.managers.library.module_loading import LibraryModuleLoading
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest, DeleteNodeRequest
    from griptape_nodes.retained_mode.events.flow_events import CreateFlowRequest
    from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
    schema = LibrarySchema.model_validate_json((ROOT / "griptape-nodes-library.json").read_text("utf-8-sig"))
    modules = {}
    names = {"HMBImageAssetLibrary", "HMBSoundLibrary", "HMBPromptLibrary", "HMBAgentLibrary", "HMBSeedanceGeneration", "HMBColorLUTLibrary"}
    engine.event_manager.initialize_queue()
    with ExitStack() as guards:
        guards.enter_context(mock.patch.object(bootstrap, "_hmb_coordinate_environment_repair", return_value={"status": "test_guard"}))
        guards.enter_context(mock.patch.object(bootstrap, "_hmb_coordinate_native_editor_update", return_value={"status": "test_guard"}))
        guards.enter_context(mock.patch.object(bootstrap._Registration, "start_web_worker", lambda _self: None))
        advanced = bootstrap.HMBProductionLibrary()
        library = LibraryRegistry.generate_new_library(schema, advanced_library=advanced)
        loader = LibraryModuleLoading(engine)
        for definition in schema.nodes:
            if definition.class_name not in names:
                continue
            def load(definition=definition):
                if definition.class_name not in modules:
                    modules[definition.class_name] = loader.load_module_from_file(ROOT / definition.file_path, schema.name)
                return getattr(modules[definition.class_name], definition.class_name)
            library.register_lazy_node_type(definition.class_name, definition.metadata, load)
        advanced.before_library_nodes_loaded(schema, library)

        def create(kind, label, *, shot=False):
            metadata = {}
            if shot:
                # This is the saved/user-selected mode, not a routing shortcut.
                import HMBSeedanceGeneration as canonical
                metadata[canonical.SEEDANCE_EXECUTION_MODE_METADATA] = harness.intent(canonical, "shot", SHOTS[0])
            result = harness.send(engine, CreateNodeRequest(node_type=kind, node_name=label,
                specific_library_name=schema.name, metadata=metadata, initial_setup=True, create_error_proxy_on_failure=False))
            return engine.node_manager.get_node_by_name(result.node_name)

        async def settled(predicate, description, seconds=12):
            deadline = asyncio.get_running_loop().time() + seconds
            while not predicate():
                if asyncio.get_running_loop().time() >= deadline:
                    raise AssertionError(description)
                await asyncio.sleep(.025)

        projects = out / "local-projects"
        expected_audio_roots = []
        flows = []
        for index, sound_first in enumerate((True, False), 1):
            project_id = "katuri8" if index == 1 else "superwings12"
            image_root = projects / project_id / "Ai_Ct_image"
            audio_root = projects / project_id / "Ai_Ct_audio"
            image_root.mkdir(parents=True, exist_ok=True)
            wav = audio_root / "Dialogue" / "voice.wav"
            wav.parent.mkdir(parents=True, exist_ok=True)
            with wave.open(str(wav), "wb") as stream:
                stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(8000)
                stream.writeframes(b"\x00\x08" * 2000)
            expected_audio_roots.append(str(audio_root.resolve()))
            while engine.context_manager.has_current_flow():
                engine.context_manager.pop_flow()
            flow_name = f"Automatic Sound order {index}"
            if index == 1:
                harness.send(engine, EnsureWorkflowAndFlowRequest(flow_name=flow_name))
            else:
                harness.send(engine, CreateFlowRequest(flow_name=flow_name, parent_flow_name="Automatic Sound order 1", set_as_new_context=True))
            nodes = {}
            order = ("HMBSoundLibrary", "HMBColorLUTLibrary", "HMBSeedanceGeneration", "HMBAgentLibrary", "HMBPromptLibrary", "HMBImageAssetLibrary") if sound_first else (
                "HMBImageAssetLibrary", "HMBPromptLibrary", "HMBAgentLibrary", "HMBSeedanceGeneration", "HMBColorLUTLibrary", "HMBSoundLibrary")
            for kind in order:
                nodes[kind] = create(kind, f"Auto {index} {kind}", shot=kind == "HMBSeedanceGeneration")
                if kind == "HMBImageAssetLibrary":
                    image = nodes[kind]
                    module = modules[kind]
                    catalog_state = module._load_project_catalog(projects, module._default_state(), use_shared_cache=False)
                    state = module._select_catalog_project(catalog_state, str(image_root.resolve()))
                    state["shot_routing"].update(channel_uuid=CHANNEL, publisher_instance_uuid=PUBLISHER,
                        generation=1, shots=deepcopy(SHOTS[:2]), active_shot_uuid=SHOTS[0]["shot_uuid"])
                    harness.send(engine, SetParameterValueRequest(node_name=image.name, parameter_name=module.WIDGET_STATE_PARAMETER,
                        value=json.dumps(state, ensure_ascii=False), initial_setup=True))
                await asyncio.sleep(.025)
            image, sound = nodes["HMBImageAssetLibrary"], nodes["HMBSoundLibrary"]
            prompt, agent = nodes["HMBPromptLibrary"], nodes["HMBAgentLibrary"]
            generator, lut = nodes["HMBSeedanceGeneration"], nodes["HMBColorLUTLibrary"]
            await settled(lambda: sound._state_sound.get("project_root") == str(audio_root.resolve())
                and len(sound._state_sound.get("shot_catalog", {}).get("shots", [])) == 2
                and sound._state_sound.get("assets") and not sound._state_sound.get("busy"),
                "Sound did not adopt the real Image project, independent audio catalog and dynamic two-Shot metadata")
            def wired(target, port, owner, output):
                return any(edge.source_node_name == owner.name and edge.source_parameter_name == output
                    and edge.target_parameter_name == port for edge in routing._incoming_connections(target))
            await settled(lambda: all((wired(prompt, "SHOT_ASSET_IN", image, "SHOT_ASSET_OUT"),
                wired(prompt, "SOUND_IN", sound, "SHOT_SOUND_OUT"), wired(agent, "SHOT_PROMPT_IN", prompt, "PROMPT_OUT"),
                wired(generator, "SHOT_ASSET_IN", image, "SHOT_ASSET_OUT"), wired(generator, "SHOT_SOUND_IN", sound, "SHOT_SOUND_OUT"),
                wired(generator, "prompt", agent, "output"), wired(lut, "SOUND_IN", sound, "SHOT_SOUND_OUT"))),
                "Automatic physical routes did not become ready without Save or manual reconciliation")
            routing.schedule_post_registration_reconcile(sound)
            routing.schedule_post_registration_reconcile(sound)
            await settled(lambda: sound not in routing._POST_REGISTRATION_PENDING,
                "Duplicate registration signals did not settle behind the exact owner boundary")
            for target, port in ((prompt, "SOUND_IN"), (generator, "SHOT_SOUND_IN"), (lut, "SOUND_IN")):
                assert len([edge for edge in routing._incoming_connections(target)
                    if edge.source_node_name == sound.name and edge.target_parameter_name == port]) == 1
            assert sound._state_sound["channel_uuid"] == CHANNEL
            assert [row["shot_uuid"] for row in sound._state_sound["shot_catalog"]["shots"]] == [row["shot_uuid"] for row in SHOTS[:2]]
            assert sound._state_sound["project_root"] != image._current_state()["project_root"]
            assert sound._state_sound["assets"][0]["source_uid"].startswith("sound:")
            assert not image._current_state()["assets"], "Sound catalog must not reuse the ImageAsset catalog"
            assert generator._hmb_preflight_kind(sound) == "HMBSoundLibrary", "Real loader alias was rejected as a Sound publisher"
            # The target card is Shot 2 while the visible Sound tab may be Shot 1.
            current = sound._state_sound
            sound._command({"id": f"{index:032x}", "action": "shot_add", "source_uid": current["assets"][0]["source_uid"],
                "shot_uuid": SHOTS[1]["shot_uuid"], "context": {"project_uid": current["project_uid"],
                    "channel_uuid": current["shot"].get("channel_uuid", ""), "shot_uuid": current["shot"].get("shot_uuid", ""), "revision": current["revision"]}})
            await settled(lambda: len(sound._state_sound["tracks"]) == 1 and not sound._state_sound["busy"], "Bound Shot card add did not finish")
            snapshot = sound._hmb_sound_snapshot_for(channel_uuid=CHANNEL, shot_uuid=SHOTS[1]["shot_uuid"])
            tracks = sound_helper.resolve_sound_tracks(snapshot, channel_uuid=CHANNEL, shot_uuid=SHOTS[1]["shot_uuid"], project_id=project_id)
            assert len(tracks) == 1 and tracks[0]["path"] == str(wav.resolve())
            document2 = prompt._hmb_prompt_shot_document(channel_uuid=CHANNEL, shot_uuid=SHOTS[1]["shot_uuid"])
            assert len(sound_helper.resolve_sound_tracks(document2["audio_sources"], channel_uuid=CHANNEL,
                shot_uuid=SHOTS[1]["shot_uuid"], project_id=project_id)) == 1
            document1 = prompt._hmb_prompt_shot_document(channel_uuid=CHANNEL, shot_uuid=SHOTS[0]["shot_uuid"])
            assert sound_helper.resolve_sound_tracks(document1["audio_sources"], channel_uuid=CHANNEL,
                shot_uuid=SHOTS[0]["shot_uuid"], project_id=project_id) == []
            source_state = deepcopy(image._current_state())
            old_binding = source_state.get("shot_hierarchy") or {}
            members = []
            for number, row in enumerate(SHOTS, 1):
                manual_uuid = f"55555555-5555-4555-8555-{index * 10 + number:012d}"
                members.append({"member_id": "manual:" + manual_uuid, "origin": "manual", "manual_uuid": manual_uuid,
                    "source_name": row["name"], "canonical_name": row["name"], "gp_shot_uuid": row["shot_uuid"],
                    "parent_id": None, "selection_order": number, "cgt_task_id": None, "artist": None, "status": None})
            source_state["shot_hierarchy_request"] = {"schema": routing.SHOT_HIERARCHY_REQUEST_SCHEMA, "version": 1,
                "expected_generation": source_state["shot_routing"]["generation"],
                "expected_binding_revision": old_binding.get("revision", 0), "removed_member_ids": [],
                "binding": {"schema": routing.SHOT_HIERARCHY_SCHEMA, "version": 1,
                    "binding_id": old_binding.get("binding_id") or f"44444444-4444-4444-8444-{index:012d}",
                    "revision": old_binding.get("revision", 0) + 1, "project_identity": routing.hierarchy_project_key(source_state),
                    "channel_uuid": CHANNEL, "cgt_account_id": None, "members": members}}
            source_state[modules["HMBImageAssetLibrary"].UI_EDIT_REVISION_KEY] += 1
            harness.send(engine, SetParameterValueRequest(node_name=image.name, parameter_name=modules["HMBImageAssetLibrary"].WIDGET_STATE_PARAMETER,
                value=json.dumps(source_state, ensure_ascii=False), initial_setup=False))
            await settled(lambda: len(sound._state_sound.get("shot_catalog", {}).get("shots", [])) == 3,
                "Sound rows did not follow the ImageAsset Shot count from two to three")
            assert sound._state_sound["tracks"][0]["shot_uuid"] == SHOTS[1]["shot_uuid"]
            flows.append(nodes)
            harness.record("advanced_alias_automatic_sound_chain_without_save", sound_first=sound_first,
                nodes=6, initial_shots=2, updated_shots=3, manual_route_calls=0, patched_source_apis=0, provider_calls=0)
        assert flows[0]["HMBSoundLibrary"]._state_sound["project_root"] == expected_audio_roots[0]
        assert flows[1]["HMBSoundLibrary"]._state_sound["project_root"] == expected_audio_roots[1]
        assert expected_audio_roots[0] != expected_audio_roots[1]
        harness.record("same_uuids_other_flow_keeps_independent_sound_project_catalog_and_tracks", provider_calls=0)
        while engine.context_manager.has_current_flow():
            engine.context_manager.pop_flow()
        harness.send(engine, CreateFlowRequest(flow_name="Cancelled Sound registration", parent_flow_name="Automatic Sound order 1", set_as_new_context=True))
        temp_image = create("HMBImageAssetLibrary", "Registration lifetime Image")
        image_module = modules["HMBImageAssetLibrary"]
        saved_image = image_module._load_project_catalog(projects, image_module._default_state(), use_shared_cache=False)
        saved_image = image_module._select_catalog_project(saved_image, str((projects / "katuri8" / "Ai_Ct_image").resolve()))
        saved_image["shot_routing"].update(channel_uuid=CHANNEL, publisher_instance_uuid=PUBLISHER,
            generation=1, shots=deepcopy(SHOTS[:2]), active_shot_uuid=SHOTS[0]["shot_uuid"])
        harness.send(engine, SetParameterValueRequest(node_name=temp_image.name, parameter_name=image_module.WIDGET_STATE_PARAMETER,
            value=json.dumps(saved_image, ensure_ascii=False), initial_setup=True))
        retired = create("HMBSoundLibrary", "Registration lifetime Sound")
        routing.schedule_post_registration_reconcile(retired)
        routing.schedule_post_registration_reconcile(retired)
        # No event-loop yield occurs between construction and deletion.
        harness.send(engine, DeleteNodeRequest(node_name=retired.name))
        replacement = create("HMBSoundLibrary", "Registration lifetime Sound")
        await settled(lambda: replacement._state_sound.get("project_root") == expected_audio_roots[0]
            and not replacement._state_sound.get("busy") and bool(replacement._state_sound.get("assets")),
            "The replacement Sound did not retain its own registered context")
        assert engine.node_manager.get_node_by_name(replacement.name) is replacement
        assert retired is not replacement and retired._hmb_node_deleted
        assert retired not in routing._POST_REGISTRATION_PENDING and retired._worker is None
        assert retired._state_sound["tracks"] == [] and replacement._state_sound["tracks"] == []
        assert flows[0]["HMBSoundLibrary"]._state_sound["tracks"]
        harness.record("duplicate_registration_and_deleted_same_name_sound_keep_exact_lifetime", provider_calls=0)
        advanced.before_library_unregistered(schema, library)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "reports/sound-automatic-chain-20261104")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    harness.exercise = exercise
    harness.PRODUCTS = ("HMBSoundLibrary.py", "HMBImageAssetLibrary.py", "HMBPromptLibrary.py", "HMBAgentLibrary.py",
        "HMBSeedanceGeneration.py", "HMBColorLUTLibrary.py", "_hmb_sound.py", "_hmb_shot_routing.py")
    harness.run_phase("automatic", args.out.resolve())
    result = json.loads((args.out / "automatic-result.json").read_text("utf-8"))
    assert result["passed"]
    print("HMB Sound automatic advanced-library chain: PASS (both source orders; no Save, models, provider, or live graph)")


if __name__ == "__main__":
    main()
