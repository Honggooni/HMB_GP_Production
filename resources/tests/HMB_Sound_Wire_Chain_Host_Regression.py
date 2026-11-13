"""Isolated installed SDK: physical Sound -> Prompt -> Agent -> Generator.

Creates disposable flows, saves them, then opens them in a second cold process.
Original sources are synthetic local files. Models, Broker and live transports
are forbidden. Run with the installed Desktop Python and Standard dependencies.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "resources/tests")]
import HMB_Seedance_Execution_Mode_Host_Regression as harness
import HMB_Finish_Multishot_Consolidation_Host_Regression as media_fixture


async def exercise(engine, phase, out):
    import _hmb_sound as helper
    import _hmb_shot_routing as routing
    import HMBSoundLibrary as sounds
    import HMBPromptLibrary as prompts
    import HMBAgentLibrary as agents
    import HMBSeedanceGeneration as generators
    import HMBAnalysisAgent as analysis
    import HMBImageAssetLibrary as images
    import HMBVideoPickerLibrary as pickers
    from griptape_nodes.node_library.library_registry import LibraryRegistry, LibrarySchema
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
    from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest, DeleteConnectionRequest
    from griptape_nodes.retained_mode.events.parameter_events import AlterElementEvent, GetNodeElementDetailsRequest, SetParameterValueRequest
    from griptape_nodes.retained_mode.events.flow_events import SerializeFlowToCommandsRequest, CreateFlowRequest
    from griptape_nodes.retained_mode.events.workflow_events import SaveWorkflowFileFromSerializedFlowRequest, RunWorkflowWithCurrentStateRequest
    from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry
    schema = LibrarySchema.model_validate_json((ROOT / "griptape-nodes-library.json").read_text("utf-8-sig"))
    library = LibraryRegistry.generate_new_library(schema)
    classes = {cls.__name__: cls for cls in (sounds.HMBSoundLibrary, prompts.HMBPromptLibrary,
        agents.HMBAgentLibrary, generators.HMBSeedanceGeneration, images.HMBImageAssetLibrary,
        pickers.HMBVideoPickerLibrary, analysis.HMBAnalysisAgent)}
    metadata = {}
    for definition in schema.nodes:
        if definition.class_name in classes:
            metadata[definition.class_name] = definition.metadata
    fallback_metadata = metadata["HMBImageAssetLibrary"]
    for name, cls in classes.items():
        library.register_lazy_node_type(name, metadata.get(name, fallback_metadata), lambda cls=cls: cls)
    engine.event_manager.initialize_queue()
    saved = out / "sound-wire-chain.py"
    expected_file = out / "sound-expected.json"
    audio_root = out / "fixtures" / "katuri8" / "Ai_Ct_audio"
    audio_root.mkdir(parents=True, exist_ok=True)
    path = audio_root / "literal-dialogue.wav"
    if not path.exists():
        path.write_bytes(b"immutable synthetic original sound; no model or audio decode")
    source_uid = helper.source_uid(audio_root, path.name)
    with ExitStack() as guards:
        guards.enter_context(mock.patch.object(routing, "schedule_post_registration_reconcile", lambda *a, **k: False))
        guards.enter_context(mock.patch.object(routing, "schedule_post_hydration_reconcile", lambda *a, **k: False))
        guards.enter_context(mock.patch.object(generators._HMBAIBrokerBridge, "_request_json", harness.deny))
        guards.enter_context(mock.patch.object(generators.HMBSeedanceGeneration, "_process_generation", harness.deny))
        guards.enter_context(mock.patch.object(agents._BaseAgent, "_process", harness.deny))
        if phase == "reopen":
            result = await harness.asend(engine, RunWorkflowWithCurrentStateRequest(file_path=str(saved)))
            assert str(getattr(result.status, "name", result.status)) == "GOOD", str(result.status)
            nodes = {key: engine.node_manager.get_node_by_name(name) for key, name in json.loads(expected_file.read_text("utf-8"))["names"].items()}
        else:
            harness.send(engine, EnsureWorkflowAndFlowRequest(flow_name="SoundWireChain"))
            def create(kind, name, metadata=None):
                result = harness.send(engine, CreateNodeRequest(node_type=kind, node_name=name,
                    specific_library_name=schema.name, initial_setup=True, metadata=metadata or {}, create_error_proxy_on_failure=False))
                return engine.node_manager.get_node_by_name(result.node_name)
            nodes = {"images": create("HMBImageAssetLibrary", "Synthetic Sound Image Publisher"),
                "sound": create("HMBSoundLibrary", "Synthetic Project Sound"),
                "prompt": create("HMBPromptLibrary", "Synthetic Sound Prompt"),
                "agent": create("HMBAgentLibrary", "Synthetic Sound Agent"),
                "generator": create("HMBSeedanceGeneration", "Synthetic Sound Generator", {
                    generators.SEEDANCE_EXECUTION_MODE_METADATA: harness.intent(generators, "shot", harness.SHOTS[0])})}
        source, sound, prompt, agent, generator = (nodes[key] for key in ("images", "sound", "prompt", "agent", "generator"))
        sound_workflow = engine.current_workflow()
        sound_scope = {"workflow_name": engine.workflow_registry.get(sound_workflow.workflow_id).name,
                       "flow_name": sound_workflow.nodes.parent_flow_name(sound.name)}
        read_sound_ui = PayloadRegistry.get_type("HMBGetSoundUISnapshotRequest")
        assert read_sound_ui is not None

        def assert_sound_ui_read():
            before = deepcopy(sound._state_sound)
            outputs = {name: deepcopy(sound.parameter_output_values.get(name)) for name in (sounds.UI, *sounds.OUTPUTS)}
            sequence = sound._ui_sequence
            # Desktop background reads carry the exact workflow/flow scope;
            # an SDK async callback is not guaranteed to retain global context.
            result = harness.send(engine, read_sound_ui(node_name=sound.name, expected_stream_id=sound._ui_stream, **sound_scope))
            assert result.altered_workflow_state is False
            assert sound._state_sound == before and sound._ui_sequence == sequence
            assert outputs == {name: sound.parameter_output_values.get(name) for name in outputs}
            assert result.snapshot["__hmb_sound_transport"]["sequence"] == sequence
            track = result.snapshot["tracks"][0]
            assert track["transcript"] == "안녕 {{SIGN}} 0 OFF" and track["gain_db"] == 0 and track["loop"] is False
            assert track["shot_uuid"] == harness.SHOTS[0]["shot_uuid"] and track["out_seconds"] is None
            return result.snapshot["__hmb_sound_transport"]["stream_id"]

        for name in sounds.OUTPUTS:
            port = sound.get_parameter_by_name(name)
            assert port.allow_output and port.hide and port.hide_property, name
            assert port.ui_options["hide_handles"] and port.ui_options["hide_property"], name
        display_name = generators.PROMPT_SOUND_AUDIO_DISPLAY_PARAMETER
        display = generator.get_parameter_by_name(display_name)
        audio_events = []
        original_put = engine.event_manager.put_event

        def capture_event(event):
            payload = event.get_request()
            if isinstance(payload, AlterElementEvent) and payload.element_details.get("element_id") == display.element_id:
                audio_events.append(deepcopy(payload.element_details))
            return original_put(event)

        guards.enter_context(mock.patch.object(engine.event_manager, "put_event", capture_event))

        def assert_native_audio(*, shown, authored, readonly=False):
            manual = generator.get_parameter_by_name("generate_audio")
            def read(parameter):
                return harness.send(engine, GetNodeElementDetailsRequest(node_name=generator.name,
                    specific_element_id=parameter.element_id)).element_details

            manual_details, display_details = read(manual), read(display)
            assert bool(manual_details["ui_options"].get("hide_property")) is readonly, manual_details
            assert bool(display_details["ui_options"].get("hide")) is not readonly, display_details
            selected = display_details if readonly else manual_details
            selected_id = display.element_id if readonly else manual.element_id
            root = harness.send(engine, GetNodeElementDetailsRequest(node_name=generator.name)).element_details
            assert root["element_id_to_value"][selected_id] is shown, selected
            assert selected["settable"] is not readonly, selected
            assert generator.get_parameter_value("generate_audio") is authored

        def set_manual_audio(value, *, accepted=True):
            request = SetParameterValueRequest(node_name=generator.name, parameter_name="generate_audio",
                value=value, data_type="bool", broadcast_result=False)
            assert engine.handle_request(request).succeeded() is accepted
        # Only publisher source/media internals are synthetic. Every physical
        # connection, consumer provenance reader and immutable document is real.
        catalog = media_fixture.media_fixture(source)
        for node in (prompt, agent, generator):
            node._hmb_reconcile_shot_routing(deepcopy(catalog))
        if phase != "reopen":
            raw = sounds.default_state()
            raw.update(project_id="katuri8", project_root=str(audio_root.resolve()), project_uid=helper.project_uid(audio_root),
                channel_uuid=harness.CHANNEL, revision=1, shot_catalog=deepcopy(catalog))
            raw["tracks"] = [{"instance_id": "dialogue-1", "source_uid": source_uid,
                "relative_path": path.name, "path": str(path.resolve()), "media_signature": helper.media_signature(path),
                "name": "Literal dialogue", "role": "Dialogue", "purpose": "both", "transcript": "안녕 {{SIGN}} 0 OFF",
                "target": "hero", "in_seconds": 0, "out_seconds": None, "start_seconds": 0,
                "gain_db": 0, "enabled": True, "loop": False, "lipsync": True, "duration_seconds": 2,
                "channel_uuid": harness.CHANNEL, "shot_uuid": harness.SHOTS[0]["shot_uuid"]}]
            sound.set_parameter_value(sounds.UI, deepcopy(raw), initial_setup=True)
            # Explicit physical edges prove the source even before automatic
            # reconciliation; no raw Sound JSON parameter is an authority.
            for src, output, dst, inp in ((source, "SHOT_ASSET_OUT", sound, sounds.CATALOG_IN),
                (source, "SHOT_ASSET_OUT", prompt, "SHOT_ASSET_IN"),
                (sound, "SOUND_OUT", prompt, "SOUND_IN"),
                (prompt, "PROMPT_OUT", agent, "SHOT_PROMPT_IN"),
                (agent, "output", generator, "prompt"),
                (source, "SHOT_ASSET_OUT", generator, "SHOT_ASSET_IN"),
                (sound, "SHOT_SOUND_OUT", generator, "SHOT_SOUND_IN")):
                harness.send(engine, CreateConnectionRequest(source_node_name=src.name, source_parameter_name=output,
                    target_node_name=dst.name, target_parameter_name=inp, initial_setup=True))
        prompt._hmb_hydrate_sound_source(sound)
        prompt._sync_prompt_output_now()
        assert_native_audio(shown=True, authored=False, readonly=True)
        document = prompt._hmb_prompt_shot_document(channel_uuid=harness.CHANNEL, shot_uuid=harness.SHOTS[0]["shot_uuid"])
        snapshot = document["audio_sources"]
        selected = helper.resolve_sound_tracks(snapshot, channel_uuid=harness.CHANNEL,
            shot_uuid=harness.SHOTS[0]["shot_uuid"], project_id="katuri8")
        assert len(selected) == 1 and selected[0]["transcript"] == "안녕 {{SIGN}} 0 OFF"
        original_sound = sound._snapshot()["tracks"][0]
        assert original_sound["out_seconds"] is None and original_sound["start_seconds"] == 0
        assert "안녕 {{SIGN}} 0 OFF" in document["machine_prompt"]
        assert str(audio_root) not in document["machine_prompt"], "local sound path leaked into model prose"
        source_view = agents._HMBAgentShotSource(prompt, document, {**document["subscription"], "participant_kind": "agent"})
        assert source_view._hmb_agent_sound_snapshot(document["machine_prompt"]) == snapshot
        assert agent._hmb_sound_snapshot_for(channel_uuid=harness.CHANNEL, shot_uuid=harness.SHOTS[0]["shot_uuid"]) == snapshot
        params = generator._get_parameters()
        params.update(model_id=generators.SEEDANCE_2_5_MODEL_ID, duration=5, resolution="480p", prompt="Exact authored visual prompt")
        resolved = generator._resolve_exact_shot_generation_inputs(params)
        assert resolved["generate_audio"] is True and params["generate_audio"] is False
        assert resolved["reference_audio"] == [row["path"] for row in selected if row["purpose"] in {"reference", "both"}]
        assert resolved["_hmb_sound_tracks"] == selected
        assert resolved["prompt"] == params["prompt"]
        # Sparse source fixture intentionally has no visual media. The ordinary
        # native model constraints still reject audio-only submission.
        try:
            generator._validate_parameters(resolved)
        except ValueError as exc:
            assert "image or video" in str(exc) or "at least one reference image, video" in str(exc)
        else:
            raise AssertionError("Sound bypassed ordinary model visual-reference requirement")
        foreign = prompt._hmb_prompt_shot_document(channel_uuid=harness.CHANNEL, shot_uuid=harness.SHOTS[1]["shot_uuid"])
        assert helper.resolve_sound_tracks(foreign["audio_sources"], channel_uuid=harness.CHANNEL,
            shot_uuid=harness.SHOTS[1]["shot_uuid"], project_id="katuri8") == []
        harness.record("native_physical_sound_prompt_agent_generator_exact_uuid", phase=phase,
            tracks=1, audio_observation="not_performed", sibling_audio=0, provider_calls=0)
        if phase != "reopen":
            def apply_prompt_overlays(controls):
                authored = prompts._normalize_state(prompt._current_state())
                authored = prompts._select_prompt_shot_document(authored, {"channel_uuid": harness.CHANNEL, **media_fixture.SHOTS[0]})
                authored["sound_overlays"] = {"dialogue-1": deepcopy(controls)}
                authored[prompts.UI_EDIT_REVISION_KEY] = int(authored.get(prompts.UI_EDIT_REVISION_KEY) or 0) + 1
                authored = prompts._store_prompt_shot_document(authored)
                prompt.set_parameter_value(prompts.WIDGET_PARAMETER_NAME, json.dumps(authored, ensure_ascii=False), initial_setup=True)
                prompt._hmb_hydrate_sound_source(sound)
                prompt._sync_prompt_output_now()
                return prompt._hmb_prompt_shot_document(channel_uuid=harness.CHANNEL, shot_uuid=harness.SHOTS[0]["shot_uuid"])
            set_manual_audio(True, accepted=False)
            assert_native_audio(shown=True, authored=False, readonly=True)
            disabled = apply_prompt_overlays({"enabled": False})
            assert_native_audio(shown=False, authored=False)
            assert audio_events[-1]["value"] is True and audio_events[-1]["ui_options"]["hide"] is True
            disabled_inputs = generator._resolve_exact_shot_generation_inputs(params)
            assert disabled_inputs["reference_audio"] == [] and disabled_inputs["_hmb_sound_tracks"] == []
            assert disabled["audio_sources"]["tracks"][0]["enabled"] is False
            assert sound._snapshot()["tracks"][0]["enabled"] is True
            scope = {"channel_uuid": harness.CHANNEL, "shot_uuid": harness.SHOTS[0]["shot_uuid"]}
            assert not prompt._hmb_analysis_sources_for(**scope)
            analyze_only = apply_prompt_overlays({"audio_sub_type": "Analysis"})
            assert "안녕 {{SIGN}} 0 OFF" not in analyze_only["machine_prompt"]
            assert analyze_only["audio_sources"]["tracks"][0]["enabled"] is False
            sources = prompt._hmb_analysis_sources_for(**scope)
            assert len(sources) == 1 and sources[0]["kind"] == "audio"
            analyzer = create("HMBAnalysisAgent", "Synthetic Audio Analysis")
            analyzer._hmb_post_registration_shot_discovery()
            assert "@analysis_original = Literal dialogue / Analysis source" in agent._native_parameter_value("prompt", "")
            assert generator._resolve_exact_shot_generation_inputs(params)["reference_audio"] == [str(path.resolve())]
            assert analyzer._hmb_pick_prompt_reference(prompt, **scope, kind="audio", source_id=sources[0]["source_id"])
            routed = generator._resolve_exact_shot_generation_inputs(params)
            assert routed["reference_audio"] == [str(path.resolve())]
            assert {"shot_reference": "@analysis_original", "provider_reference": "@audio1"} in routed["_hmb_analysis_media_bindings"]
            assert routed["_hmb_sound_tracks"] == []
            assert not helper.resolve_sound_tracks(routed["_hmb_sound_snapshot"], **scope, project_id="katuri8")
            analyzer._run_command({"action": "delivery", **scope, "revision": analyzer._revision,
                "categories": [], "results_only": True})
            assert generator._resolve_exact_shot_generation_inputs(params)["reference_audio"] == []
            assert "@analysis_original" not in agent._native_parameter_value("prompt", "")
            analyzer._run_command({"action": "delivery", **scope, "revision": analyzer._revision,
                "categories": [], "results_only": False})
            assert generator._resolve_exact_shot_generation_inputs(params)["reference_audio"] == [str(path.resolve())]
            apply_prompt_overlays({"audio_sub_type": "Ignore"})
            assert not prompt._hmb_analysis_sources_for(**scope)
            assert generator._resolve_exact_shot_generation_inputs(params)["reference_audio"] == []
            harness.record("prompt_audio_subtypes_control_reference_mix_and_analysis_original", provider_calls=0)
            effective_controls = {"enabled": True, "purpose": "mix", "start_seconds": .75,
                "in_seconds": .25, "out_seconds": 1.5, "gain_db": -3, "lipsync": False}
            effective_document = apply_prompt_overlays(effective_controls)
            assert_native_audio(shown=False, authored=False)
            effective_inputs = generator._resolve_exact_shot_generation_inputs(params)
            assert effective_inputs["reference_audio"] == []
            for key, expected_value in effective_controls.items():
                assert effective_inputs["_hmb_sound_snapshot"]["tracks"][0][key] == expected_value
                assert effective_inputs["_hmb_sound_tracks"][0][key] == expected_value
            assert effective_inputs["_hmb_sound_provenance"]["kind"] == "exact_prompt_document"
            assert sound._snapshot()["tracks"][0]["purpose"] == "both"
            readiness = generator._hmb_preflight_row(generator._hmb_shot_channel_subscription(),
                nodes={node.name: node for node in nodes.values()}, source=source,
                source_snapshot=source._hmb_shot_routing_snapshot())
            assert readiness["media"]["audio"] == 0
            assert "Prompt" in readiness["connections"].get("Sound", ""), json.dumps(readiness, ensure_ascii=False)
            harness.record("real_prompt_disable_mix_start_trim_controls_override_direct_sound_without_mutating_original", provider_calls=0)
            completed_origin = generator._capture_generated_video_origin()
            completed_file = out / "fixtures" / "synthetic-completed-video.mp4"
            completed_file.write_bytes(b"synthetic completed-boundary identity fixture; no rendered pixels claimed")
            generator._hmb_pending_sound = {"snapshot": deepcopy(effective_inputs["_hmb_sound_snapshot"]),
                "tracks": deepcopy(effective_inputs["_hmb_sound_tracks"]),
                "provenance": deepcopy(effective_inputs["_hmb_sound_provenance"]), "origin": completed_origin}
            with mock.patch.object(routing, "reconcile_completed_video_routes", lambda *_a, **_k: None):
                generator._record_completed_video_source(completed_origin, "job-" + "a" * 32,
                    __import__("types").SimpleNamespace(resolve=lambda: str(completed_file.resolve())))
            completed_sound = generator._hmb_sound_finishing_snapshot()
            assert completed_sound["snapshot"] == effective_inputs["_hmb_sound_snapshot"]
            assert completed_sound["tracks"][0]["start_seconds"] == .75
            assert generator.parameter_values[generators.GENERATION_SOUND_STORE_PARAMETER]["entries"]
            set_manual_audio(True)
            apply_prompt_overlays({})
            assert_native_audio(shown=True, authored=True, readonly=True)
            assert audio_events[-1]["value"] is True and audio_events[-1]["ui_options"]["hide"] is False
            set_manual_audio(False, accepted=False)
            apply_prompt_overlays({"enabled": False})
            assert_native_audio(shown=True, authored=True)
            set_manual_audio(False)
            active_document = apply_prompt_overlays({"audio_sub_type": "Apply"})
            assert_native_audio(shown=True, authored=False, readonly=True)
            harness.record("native_audio_auto_on_for_exact_prompt_with_immediate_manual_restore", provider_calls=0)
            stream_before_save = assert_sound_ui_read()
            harness.record("readonly_sound_snapshot_before_save_preserves_authored_audio", altered_workflow_state=False)
            serialized = harness.send(engine, SerializeFlowToCommandsRequest(flow_name="SoundWireChain")).serialized_flow_commands
            await harness.asend(engine, SaveWorkflowFileFromSerializedFlowRequest(file_name=saved.stem,
                file_path=str(saved), display_name="Offline Sound physical chain fixture", serialized_flow_commands=serialized))
            expected_file.write_text(json.dumps({"names": {key: node.name for key, node in nodes.items()},
                "sound": sound._hmb_sound_snapshot_for(channel_uuid=harness.CHANNEL, shot_uuid=harness.SHOTS[0]["shot_uuid"]),
                "effective_sound": active_document["audio_sources"], "completed_sound": completed_sound,
                "sound_ui_stream": stream_before_save}, ensure_ascii=False), "utf-8")
            # A second real five-node flow deliberately reuses the same UUIDs.
            # Its lack of Sound must remain optional and cannot discover the
            # first flow's Sound through browser/global/source caches.
            harness.send(engine, CreateFlowRequest(flow_name="NoSoundFiveNodeSameUUID", parent_flow_name=None, set_as_new_context=True))
            foreign_read = engine.handle_request(read_sound_ui(node_name=sound.name, broadcast_result=False))
            assert foreign_read.succeeded() and not foreign_read.snapshot and foreign_read.altered_workflow_state is False
            image2 = create("HMBImageAssetLibrary", "NoSound Image Publisher")
            picker2 = create("HMBVideoPickerLibrary", "NoSound Video Picker")
            prompt2 = create("HMBPromptLibrary", "NoSound Prompt")
            agent2 = create("HMBAgentLibrary", "NoSound Agent")
            generator2 = create("HMBSeedanceGeneration", "NoSound Generator", {
                generators.SEEDANCE_EXECUTION_MODE_METADATA: harness.intent(generators, "shot", harness.SHOTS[0])})
            catalog2 = media_fixture.media_fixture(image2)
            picker_snapshot = {"schema": "hmb-picker-shot-routing-snapshot", "version": 1,
                "publisher_instance_uuid": "88888888-8888-4888-8888-888888888888", "channel_uuid": harness.CHANNEL,
                "generation": 1, "shots": [dict(row, picker_payload={"media_ready": False}) for row in media_fixture.SHOTS],
                "ordered_videos": [], "media_by_source_uid": {}}
            picker_snapshot["metadata_sha256"] = media_fixture.digest({key: picker_snapshot[key] for key in ("channel_uuid", "generation", "shots", "ordered_videos")})
            picker_snapshot["media_sha256"] = media_fixture.digest({"media_descriptors": []})
            picker2._hmb_shot_routing_snapshot = lambda *a, **k: deepcopy(picker_snapshot)
            picker2._hmb_shot_routing_snapshot_for = lambda **k: deepcopy(picker_snapshot)
            for node in (picker2, prompt2, agent2, generator2):
                node._hmb_reconcile_shot_routing(deepcopy(catalog2))
            for src, output, dst, inp in ((image2, "SHOT_ASSET_OUT", prompt2, "SHOT_ASSET_IN"), (picker2, "SHOT_PICKER_OUT", prompt2, "SHOT_PICKER_IN"),
                (prompt2, "PROMPT_OUT", agent2, "SHOT_PROMPT_IN"), (agent2, "output", generator2, "prompt"),
                (image2, "SHOT_ASSET_OUT", generator2, "SHOT_ASSET_IN"), (picker2, "SHOT_PICKER_OUT", generator2, "SHOT_PICKER_IN")):
                harness.send(engine, CreateConnectionRequest(source_node_name=src.name, source_parameter_name=output,
                    target_node_name=dst.name, target_parameter_name=inp, initial_setup=True))
            noaudio_before = prompt2._hmb_prompt_shot_document(channel_uuid=harness.CHANNEL, shot_uuid=harness.SHOTS[0]["shot_uuid"])
            routing.reconcile_shot_routing(image2)
            noaudio_after = prompt2._hmb_prompt_shot_document(channel_uuid=harness.CHANNEL, shot_uuid=harness.SHOTS[0]["shot_uuid"])
            assert noaudio_before["machine_prompt"] == noaudio_after["machine_prompt"]
            assert noaudio_after["audio_sources"] == {}
            assert "@audio" not in noaudio_after["machine_prompt"]
            resolved2 = generator2._resolve_exact_shot_generation_inputs(dict(params, prompt="NoSound original visual text"))
            assert resolved2["reference_audio"] == [] and "_hmb_sound_snapshot" not in resolved2
            assert resolved2["prompt"] == "NoSound original visual text"
            harness.record("second_flow_original_five_nodes_same_uuids_no_audio_unchanged", nodes=5, foreign_audio=0, provider_calls=0)
        else:
            expected = json.loads(expected_file.read_text("utf-8"))
            stale_read = engine.handle_request(read_sound_ui(node_name=sound.name,
                expected_stream_id=expected["sound_ui_stream"], broadcast_result=False))
            assert stale_read.succeeded() and not stale_read.snapshot and stale_read.altered_workflow_state is False
            assert assert_sound_ui_read() != expected["sound_ui_stream"]
            harness.record("cold_sdk_reopen_readonly_sound_snapshot_uses_fresh_stream", altered_workflow_state=False)
            assert sound._hmb_sound_snapshot_for(channel_uuid=harness.CHANNEL, shot_uuid=harness.SHOTS[0]["shot_uuid"]) == expected["sound"]
            assert snapshot == expected["effective_sound"]
            assert prompts._normalize_state(prompt._current_state())["sound_overlays"]["dialogue-1"]["audio_sub_type"] == "Apply"
            assert resolved["reference_audio"] and resolved["_hmb_sound_tracks"][0]["purpose"] == "both"
            assert generator._hmb_sound_finishing_snapshot() == expected["completed_sound"]
            harness.send(engine, DeleteConnectionRequest(source_node_name=agent.name, source_parameter_name="output",
                target_node_name=generator.name, target_parameter_name="prompt"))
            assert_native_audio(shown=False, authored=False)
            harness.send(engine, CreateConnectionRequest(source_node_name=agent.name, source_parameter_name="output",
                target_node_name=generator.name, target_parameter_name="prompt"))
            assert_native_audio(shown=True, authored=False, readonly=True)
            harness.record("cold_sdk_reopen_keeps_manual_audio_off_and_reprojects_live_prompt_binding", provider_calls=0)
            harness.record("cold_sdk_reopen_retains_sound_original_eof_identity_and_physical_wires", provider_calls=0)
            harness.record("cold_sdk_reopen_retains_completed_generation_effective_prompt_sound", generation_id="job-" + "a" * 32, provider_calls=0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("create", "reopen"))
    parser.add_argument("--out", type=Path, default=ROOT / "reports/sound-wire-chain-20261103")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if args.phase:
        harness.exercise = exercise
        harness.PRODUCTS = ("HMBSoundLibrary.py", "HMBPromptLibrary.py", "HMBAgentLibrary.py", "HMBSeedanceGeneration.py",
            "HMBAnalysisAgent.py", "_hmb_sound.py")
        harness.run_phase(args.phase, args.out.resolve())
    else:
        for phase in ("create", "reopen"):
            subprocess.run([sys.executable, "-B", str(Path(__file__).resolve()), "--phase", phase, "--out", str(args.out.resolve())], check=True)
        print("HMB Sound wire chain installed SDK: PASS (cold save/reopen; model/provider calls 0)")


if __name__ == "__main__":
    main()
