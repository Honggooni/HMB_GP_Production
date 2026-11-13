"""Installed SDK, isolated engine: physical Sound edge and current Prompt pair."""
from __future__ import annotations
from contextlib import ExitStack
from copy import deepcopy
import logging
import os
from pathlib import Path
import socket
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main():
    previous = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="hmb-prompt-sound-sdk-") as temporary:
        base = Path(temporary)
        environment = {key: str(base / key) for key in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME",
            "XDG_STATE_HOME", "LOCALAPPDATA", "APPDATA", "GTN_ENGINE_CONFIG_DIR", "GTN_ENGINE_DATA_DIR",
            "GTN_ENGINE_STATE_DIR", "GTN_CONFIG_WORKSPACE_DIRECTORY")}
        for value in environment.values():
            Path(value).mkdir(parents=True, exist_ok=True)
        with patch.dict(os.environ, environment), ExitStack() as guard:
            os.chdir(base)
            try:
                guard.enter_context(patch.object(socket, "create_connection", side_effect=AssertionError("network forbidden")))
                logging.disable(logging.CRITICAL)
                import HMBPromptLibrary as prompt
                import HMBSoundLibrary as sound_node
                import _hmb_sound as sound
                import _hmb_shot_routing as routing
                from griptape_nodes.node_library.library_registry import LibraryRegistry, LibrarySchema
                from griptape_nodes.retained_mode.engine import engine_scope
                from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
                from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
                from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest, DeleteConnectionRequest
                for name in ("schedule_post_registration_reconcile", "schedule_post_hydration_reconcile"):
                    guard.enter_context(patch.object(routing, name, return_value=False))
                guard.enter_context(patch.object(prompt.HMBPromptLibrary, "_schedule_prompt_sync", return_value=None))
                # This fixture controls its physical edge explicitly. Automatic
                # whole-flow routing has separate coverage and would recreate
                # the managed Sound edge during the disconnect assertion.
                guard.enter_context(patch.object(prompt.HMBPromptLibrary, "_reconcile_shared_shot_edges", return_value=None))
                guard.enter_context(patch.object(sound_node.HMBSoundLibrary, "_schedule_reconcile", return_value=None))
                with engine_scope() as engine:
                    schema = LibrarySchema.model_validate_json((ROOT / "griptape-nodes-library.json").read_text("utf-8-sig"))
                    library = LibraryRegistry.generate_new_library(schema)
                    classes = {cls.__name__: cls for cls in (prompt.HMBPromptLibrary, sound_node.HMBSoundLibrary)}
                    for definition in schema.nodes:
                        cls = classes.get(definition.class_name)
                        if cls is not None:
                            library.register_lazy_node_type(definition.class_name, definition.metadata, lambda cls=cls: cls)
                    def send(request):
                        request.broadcast_result = False
                        result = engine.handle_request(request)
                        assert result.succeeded(), str(result.result_details)
                        return result
                    try:
                        send(EnsureWorkflowAndFlowRequest(flow_name="Isolated Sound Prompt"))
                        for kind, name in (("HMBSoundLibrary", "Sounds"), ("HMBPromptLibrary", "Prompt")):
                            send(CreateNodeRequest(node_type=kind, node_name=name, specific_library_name=schema.name,
                                initial_setup=True, create_error_proxy_on_failure=False))
                        source = engine.node_manager.get_node_by_name("Sounds")
                        target = engine.node_manager.get_node_by_name("Prompt")
                        empty = target._compile_current_prompt_pair(refresh_sources=False)[2]
                        assert '"audios"' not in empty
                        edge = dict(source_node_name=source.name, source_parameter_name="SHOT_SOUND_OUT",
                            target_node_name=target.name, target_parameter_name="SOUND_IN")
                        send(CreateConnectionRequest(**edge, initial_setup=True))
                        assert target._reconcile_connected_source_inputs_from_graph()
                        assert target._registered_sound_source() is source
                        assert target._hmb_sound_snapshot_for() == {}
                        assert target._compile_current_prompt_pair(refresh_sources=False)[2] == empty
                        root = base / "superwings12" / "Ai_Ct_audio"
                        (root / "Dialogue").mkdir(parents=True)
                        audio = root / "Dialogue" / "Hero.wav"
                        audio.write_bytes(b"isolated identity fixture; no listening or generation")
                        track = {"instance_id": "host-track", "source_uid": sound.source_uid(root, "Dialogue/Hero.wav"),
                            "relative_path": "Dialogue/Hero.wav", "media_signature": sound.media_signature(audio),
                            "name": "Hero", "role": "Dialogue", "purpose": "both", "transcript": "  안녕 {0} OFF  ",
                            "target": "Hero", "in_seconds": 0, "out_seconds": None, "start_seconds": 0, "gain_db": 0,
                            "enabled": True, "loop": False, "lipsync": True, "duration_seconds": 1,
                            "channel_uuid": "", "shot_uuid": ""}
                        source._state_sound.update(project_id="superwings12", project_root=str(root), project_uid=sound.project_uid(root), tracks=[track])
                        source._publish(notify=False)
                        assert target._reconcile_connected_source_inputs_from_graph()
                        assert target._registered_sound_source() is source
                        snapshot = target._hmb_sound_snapshot_for()
                        assert snapshot["tracks"][0]["transcript"] == track["transcript"]
                        state, _visible, machine, _fingerprint = target._compile_current_prompt_pair(refresh_sources=False)
                        assert len(state["sound_sources"]) == 1 and str(audio) not in machine and "media_signature" not in machine
                        paired = target._hmb_agent_sound_snapshot(machine)
                        assert len(sound.resolve_sound_tracks(paired, project_id="superwings12")) == 1
                        try:
                            target._hmb_agent_sound_snapshot(machine + "stale")
                        except sound.SoundError as exc:
                            assert exc.code == "SOUND_PROMPT_PAIR_CHANGED"
                        else:
                            raise AssertionError("stale Prompt pair admitted")
                        send(DeleteConnectionRequest(**edge))
                        target._reconcile_connected_source_inputs_from_graph()
                        assert target._hmb_sound_snapshot_for() == {}
                        assert target._compile_current_prompt_pair(refresh_sources=False)[2] == empty
                        print("HMB_PROMPT_SOUND_HOST=PASS (actual registered physical edge, unconfigured Sound-first drag optional, project selection/current machine pair, original hash, disconnect optional; no application/provider/network calls)")
                    finally:
                        LibraryRegistry.unregister_library(schema.name, event_manager=engine.event_manager)
            finally:
                logging.shutdown()
                os.chdir(previous)


if __name__ == "__main__":
    main()
