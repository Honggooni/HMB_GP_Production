"""Off-loop Picker media verification, retained snapshots and stale-result guards.

Runs with the lightweight core or installed SDK, in a private flow/configuration.
All slow/UNC probes are controlled fixtures; no real shared drive or DCC calls.
"""
from __future__ import annotations
import asyncio
import copy
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main():
    with tempfile.TemporaryDirectory(prefix="hmb-picker-async-") as temporary:
        root = Path(temporary)
        env = {key: str(root / key) for key in (
            "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "LOCALAPPDATA", "APPDATA",
        )}
        with patch.dict(os.environ, env), patch.object(socket, "create_connection", side_effect=AssertionError("Network forbidden")):
            import HMBVideoPickerLibrary as picker
            try:
                from griptape_nodes.retained_mode.engine import current_engine
                from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes as G
                from griptape_nodes.exe_types.flow import ControlFlow
            except ImportError:
                G = None
            counts = []
            metrics = {}

            async def scenario():
                owner = threading.get_ident()
                if G is not None:
                    G.EventManager().initialize_queue()
                sequence = 0

                def node(path="//isolated.invalid/share/slow.mp4"):
                    nonlocal sequence
                    sequence += 1
                    if G is not None:
                        flow = ControlFlow(name=f"PickerAsyncRegressionFlow{sequence}", engine=current_engine())
                        G.ObjectManager().add_object_by_name(flow.name, flow)
                    result = picker.HMBVideoPickerLibrary(name=f"PickerAsync{sequence}")
                    if G is not None:
                        flow.add_node(result)
                        G.ObjectManager().add_object_by_name(result.name, result)
                        G.NodeManager()._name_to_parent_flow_name[result.name] = flow.name
                    state = picker._append_video_asset(result._picker_state(), {
                        "video_uid": f"asset-{sequence}", "video_path": path,
                        "video_url": "http://127.0.0.1:8123/external/stale-preview.mp4",
                    }, defer_thumbnail=True)
                    result._write_state(state)
                    return result

                async def wait_event(event):
                    limit = asyncio.get_running_loop().time() + 5
                    while not event.is_set() and asyncio.get_running_loop().time() < limit:
                        await asyncio.sleep(.005)
                    assert event.is_set(), "Detached preparation never started"

                async def wait_worker(n):
                    limit = asyncio.get_running_loop().time() + 5
                    while getattr(n, "_hmb_video_removal_sync_running", False) and asyncio.get_running_loop().time() < limit:
                        await asyncio.sleep(.005)
                    assert not getattr(n, "_hmb_video_removal_sync_running", False), "Deferred media did not settle"

                n = node()
                publications = []
                probes = []
                old_notify = picker._notify_parameter_update
                def notify(target, name, value):
                    publications.append((threading.get_ident(), name, copy.deepcopy(dict(target.parameter_output_values))))
                    return old_notify(target, name, value)
                def slow_probe(value):
                    probes.append((str(value), threading.get_ident()))
                    time.sleep(.25)
                    return root / "controlled.mp4"
                beats = []
                stop = False
                async def beat():
                    while not stop:
                        beats.append(time.perf_counter())
                        await asyncio.sleep(.005)
                heartbeat = asyncio.create_task(beat())
                await asyncio.sleep(.02)
                with patch.object(picker, "_probe_readable_video_reference", side_effect=slow_probe), patch.object(picker, "_notify_parameter_update", side_effect=notify):
                    await n.aprocess()
                    snapshot = n._hmb_shot_routing_snapshot()
                    assert snapshot["generation"] > 0
                await asyncio.sleep(.02)
                stop = True
                await heartbeat
                gap = max(b-a for a,b in zip(beats, beats[1:]))
                assert gap < .15, f"Media preparation blocked owner loop for {gap:.3f}s"
                assert probes and all(t != owner for _, t in probes), probes
                assert len(probes) == 1, "Snapshot re-probed the same prepared revision"
                assert publications and all(t == owner for t, _, _ in publications), publications
                expected = ["//isolated.invalid/share/slow.mp4"]
                assert n.parameter_output_values["VIDEO_OUT"] == expected
                for _, _, outputs in publications:
                    assert outputs["VIDEO_OUT"] == expected
                    assert json.loads(outputs["PICKER_OUT"])["videos"][0]["video_path"] == expected[0]
                counts.extend(["nonblocking_sdk_aprocess", "owner_loop_coherent_publication", "cached_snapshot_no_probe"])
                metrics.update(max_heartbeat_gap_seconds=gap, probe_count=len(probes), sdk=G is not None)

                # Fresh Run must notice external deletion even with a prepared snapshot cache.
                local = root / "real.mp4"
                local.write_bytes(b"fixture-local-video")
                n = node(str(local))
                await n.aprocess()
                assert n.parameter_output_values["VIDEO_OUT"] == [str(local)]
                local.unlink()
                try:
                    await n.aprocess()
                except RuntimeError:
                    pass
                else:
                    raise AssertionError("Missing selection must block Run")
                assert n.parameter_output_values["VIDEO_OUT"] == []
                payload = json.loads(n.parameter_output_values["PICKER_OUT"])
                assert payload["media_blocked"] and payload["videos"] == []
                assert n._picker_state()["videos"][0]["video_path"] == str(local), "Probe mutated authored source"
                counts.append("fresh_run_missing_local_clears_without_preview_fallback")

                local.write_bytes(b"fixture-local-video")
                await asyncio.to_thread(n.process)
                assert n._hmb_verified_media is not None
                local.unlink()
                try:
                    await asyncio.to_thread(n.process)
                except RuntimeError:
                    pass
                else:
                    raise AssertionError("Missing selection must block synchronous Run too")
                assert n.parameter_output_values["VIDEO_OUT"] == []
                assert n._hmb_verified_media is None, "Failed sync recheck retained an older ready cache"
                counts.append("sync_recheck_missing_file_invalidates_prior_readiness")

                # The existing deletion/output worker must use the same strict builder.
                n = node(str(root / "absent.mp4"))
                with patch.object(picker, "_notify_parameter_update", side_effect=notify):
                    n._schedule_video_removal_output_sync()
                    await wait_worker(n)
                assert n.parameter_output_values["VIDEO_OUT"] == []
                assert json.loads(n.parameter_output_values["PICKER_OUT"])["media_blocked"]
                assert n._picker_state()["videos"][0]["video_path"].endswith("absent.mp4")
                counts.append("deferred_delete_missing_local_preserves_authority")

                # Public retained snapshots may schedule verification, but never probe on-loop.
                n = node()
                calls = []
                def pending_probe(value):
                    calls.append(threading.get_ident())
                    time.sleep(.1)
                    return root / "controlled.mp4"
                with patch.object(picker, "_probe_readable_video_reference", side_effect=pending_probe):
                    start = time.perf_counter()
                    try:
                        n._hmb_shot_routing_snapshot()
                    except ValueError as error:
                        assert getattr(error, "hmb_picker_media_preparing", False) is True
                    else:
                        raise AssertionError("Unverified snapshot escaped as ready")
                    assert time.perf_counter() - start < .075
                    await wait_worker(n)
                    n._hmb_shot_routing_snapshot()
                assert calls and owner not in calls and len(calls) == 1, calls
                counts.append("snapshot_pending_defers_and_reuses_verified_cache")

                # Saved-workflow callers can publish on a synchronous retained
                # request/worker before Generator starts its asyncio execution.
                # That verified publication must be readable without a second
                # preparation cycle or another shared-drive probe.
                n = node()
                calls = []
                with patch.object(picker, "_probe_readable_video_reference", side_effect=pending_probe):
                    await asyncio.to_thread(n.process)
                    verified = n._hmb_verified_media
                    assert verified is not None
                    n._hmb_shot_routing_snapshot()
                    assert len(calls) == 1 and owner not in calls
                    changed = n._picker_state()
                    changed["videos"][0]["video_path"] = "//isolated.invalid/share/rebound.mp4"
                    n._write_state(changed)
                    with patch.object(n, "_schedule_video_removal_output_sync") as schedule:
                        try:
                            n._hmb_shot_routing_snapshot()
                        except ValueError as error:
                            assert getattr(error, "hmb_picker_media_preparing", False) is True
                        else:
                            raise AssertionError("Sync verification escaped its source identity")
                        assert schedule.call_count == 1
                    assert len(calls) == 1, "Rebound source probed on the owner loop"
                counts.append("legacy_sync_publication_shared_with_async_consumer")

                # Verification includes inactive Shots; a later exact-Shot
                # consumer must not discover a new drive read on the loop.
                n = node()
                state = n._picker_state()
                first = state["active_picker_shot_uuid"]
                second = picker._new_picker_workspace_row(2, bound_shot_uuid="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
                state["picker_shots"].append(second)
                state = picker._append_video_asset(state, {
                    "video_uid": "inactive-shot", "video_path": "//isolated.invalid/share/second.mp4",
                }, picker_shot_uuid=second["workspace_uuid"], defer_thumbnail=True)
                state = picker._activate_picker_workspace_projection(state, first)
                n._write_state(state)
                calls = []
                with patch.object(picker, "_probe_readable_video_reference", side_effect=pending_probe):
                    await n.aprocess()
                    snapshot = n._hmb_shot_routing_snapshot()
                assert len(calls) == 2 and owner not in calls
                assert len(snapshot["shots"]) == 2
                assert n.parameter_output_values["VIDEO_OUT"] == expected
                counts.append("inactive_shot_verification_cached_without_loop_io")

                # A newer Run can finish first. The late older worker cannot
                # replace its verified result or invalidate its ready cache.
                n = node()
                entered, release = threading.Event(), threading.Event()
                call_lock = threading.Lock()
                call_number = 0
                def overlapping_probe(value):
                    nonlocal call_number
                    with call_lock:
                        call_number += 1
                        number = call_number
                    if number == 1:
                        entered.set()
                        assert release.wait(5)
                    return root / "controlled.mp4"
                with patch.object(picker, "_probe_readable_video_reference", side_effect=overlapping_probe):
                    old = asyncio.create_task(n.aprocess())
                    try:
                        await wait_event(entered)
                        await n.aprocess()
                        ready = n._hmb_verified_media
                        before = copy.deepcopy(dict(n.parameter_output_values))
                    finally:
                        release.set()
                    try:
                        await old
                    except ValueError:
                        pass
                    else:
                        raise AssertionError("Older Run replaced a newer execution")
                assert n._hmb_verified_media == ready and dict(n.parameter_output_values) == before
                counts.append("newer_execution_wins_over_late_preparation")

                # Inputs changed during slow I/O must never publish an old selection.
                for mutation in ("source", "selection", "shot", "project", "lifecycle", "task_cancel", "sdk_cancel"):
                    n = node()
                    entered, release = threading.Event(), threading.Event()
                    def blocked_probe(value):
                        entered.set()
                        assert release.wait(5)
                        return root / "controlled.mp4"
                    before = copy.deepcopy(dict(n.parameter_output_values))
                    with patch.object(picker, "_probe_readable_video_reference", side_effect=blocked_probe):
                        task = asyncio.create_task(n.aprocess())
                        try:
                            await wait_event(entered)
                            if mutation == "task_cancel":
                                task.cancel()
                            elif mutation == "sdk_cancel":
                                if G is not None:
                                    n.request_cancellation()
                                else:
                                    n.is_cancellation_requested = True
                            elif mutation == "project":
                                n._hmb_shot_catalog_snapshot = {"project_id": "katuri8"}
                            elif mutation == "lifecycle":
                                n._hmb_lifecycle_generation += 1
                                n._hmb_node_deleted = True
                            else:
                                state = n._picker_state()
                                if mutation == "source":
                                    state["videos"][0]["video_path"] = "//isolated.invalid/share/new.mp4"
                                elif mutation == "selection":
                                    state["picker_shots"][0]["selected_video_uids"] = []
                                    state["videos"][0]["selected"] = False
                                    state["videos"][0]["selection_order"] = 0
                                else:
                                    second = picker._new_picker_workspace_row(2, bound_shot_uuid="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
                                    state["picker_shots"].append(second)
                                    state = picker._activate_picker_workspace_projection(state, second["workspace_uuid"])
                                n._write_state(state)
                        finally:
                            release.set()
                        try:
                            await task
                        except (ValueError, asyncio.CancelledError):
                            pass
                        else:
                            raise AssertionError(f"Stale {mutation} was published")
                        await asyncio.sleep(.03)
                    assert dict(n.parameter_output_values) == before, mutation
                    assert n._hmb_verified_media is None, mutation
                    counts.append(f"stale_guard_{mutation}")

                # Prepared I/O does not mutate supplied rows, including missing local fallback.
                state = picker._parse_state({"videos": [{"video_uid": "missing", "selected": True,
                    "selection_order": 1, "video_path": str(root / "absent.mp4"),
                    "video_url": "http://127.0.0.1:8123/external/preview.mp4"}]})
                original = copy.deepcopy(state)
                payload, media, cache = await asyncio.to_thread(picker.HMBVideoPickerLibrary._prepare_execution_media, state)
                assert state == original and payload["media_blocked"] and media == []
                counts.append("detached_prepare_nonmutating_strict_media")

            asyncio.run(scenario())
            print("Picker async execution: PASS " + json.dumps({"count": len(counts), "cases": counts, **metrics}, sort_keys=True))


if __name__ == "__main__":
    main()
