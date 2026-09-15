"""Explicit Reset/Delete detaches locally; normal crash recovery stays intact.

No provider requests or billable renders. Exercise native Reset ordering
(create _temp, delete old, rename fresh), journal races and Shot isolation.
"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
import tempfile
import threading
from unittest import mock

from _hmb_seedance_clean_ci_stubs import install_clean_ci_griptape_stubs

install_clean_ci_griptape_stubs()
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("seedance_reset_fresh", ROOT / "HMBSeedanceGeneration.py")
target = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = target
spec.loader.exec_module(target)


def new(name):
    node = target.HMBSeedanceGeneration(name=name)
    node._discard_dangling_owned_list_connections_before_delete = lambda: None
    return node


def pending(node, status):
    node._set_generation_recovery_checkpoint(
        stage="submission_unknown" if status == "submission_unknown" else "accepted",
        task_id=f"job-{status}", task_identity="broker_task", status=status,
        terminal=status in ("failed", "succeeded"),
    )
    node.parameter_output_values.update(generation_id=f"job-{status}", generation_status=status)
    node.parameter_output_values["provider_response"] = {"id": f"job-{status}", "status": status}
    cp = deepcopy(node._generation_recovery_state())
    node._write_live_generation_recovery_journal(cp)
    return cp


def fresh(node, old_identity):
    cp = node._generation_recovery_state()
    assert cp["journal_id"] != old_identity
    assert cp["task_id"] == ""
    assert not node.parameter_output_values.get("generation_id")
    assert not node.parameter_output_values.get("generation_status")
    assert not node.get_parameter_value("resume_generation_id")
    assert not node._generation_recovery_blocks_new_submission()
    node._assert_new_submission_is_safe()


async def verify(folder):
    media = folder / "saved-shot-video.mp4"
    media.write_bytes(b"saved media must remain untouched")
    other = new("Shot 5")
    other_cp = pending(other, "running")
    other_path = target._seedance_recovery_journal_path(other_cp["journal_id"])
    other_bytes = other_path.read_bytes()
    count = 0
    for status in ("submitting", "queued", "running", "submission_unknown", "timed_out", "failed", "succeeded"):
        for reset in (False, True):
            old = new("Shot 1")
            cp = pending(old, status)
            path = target._seedance_recovery_journal_path(cp["journal_id"])
            old.parameter_output_values["VIDEO_OUT"] = str(media)
            # Reset creates its replacement before the old node is deleted.
            replacement = new("Shot 1_temp") if reset else None
            before = path.read_bytes()
            old.after_node_deleted()
            assert path.read_bytes() == before
            assert not old._runtime_node_is_live()
            assert cp["journal_id"] not in target._RECOVERY_JOURNAL_OWNERS
            replacement = replacement or new("Shot 1")
            replacement.name = "Shot 1"
            fresh(replacement, cp["journal_id"])
            # Delayed state reads/checkpoint jobs must never reclaim an owner
            # or update its retired journal after replacement.
            old._generation_recovery_state()
            assert cp["journal_id"] not in target._RECOVERY_JOURNAL_OWNERS
            assert not await old._force_save_generation_recovery_checkpoint(required=False, reason="late")
            try:
                await old._force_save_generation_recovery_checkpoint(required=True, reason="late pre-submit")
            except RuntimeError as exc:
                assert "deleted or reset" in str(exc)
            else:
                raise AssertionError("Deleted node must not cross the submission boundary")
            try:
                old._write_live_generation_recovery_journal(cp)
            except RuntimeError:
                pass
            else:
                raise AssertionError("Retired writer recreated an old journal")
            old.after_node_deleted()  # deletion is idempotent
            assert path.read_bytes() == before
            fresh(replacement, cp["journal_id"])
            assert media.read_bytes() == b"saved media must remain untouched"
            assert other_path.read_bytes() == other_bytes
            assert other._generation_recovery_blocks_new_submission()
            count += 1

    # Existing nodes retain their normal duplicate-submission protection.
    unknown = new("Unreset ambiguous job")
    pending(unknown, "submission_unknown")
    assert unknown._generation_recovery_blocks_new_submission()
    failed = new("Unreset terminal job")
    pending(failed, "failed")
    assert not failed._generation_recovery_blocks_new_submission()

    # A write that was already inside os.replace's critical section finishes
    # before retirement. It belongs only to the old identity and cannot affect
    # the replacement. No sleeps/timing guesses.
    race = new("Reset during disk write")
    cp = pending(race, "running")
    entered, release = threading.Event(), threading.Event()
    real_write = target._write_seedance_recovery_journal
    def paused_write(checkpoint):
        entered.set()
        assert release.wait(5)
        real_write(checkpoint)
    with ThreadPoolExecutor(max_workers=2) as pool:
        with mock.patch.object(target, "_write_seedance_recovery_journal", side_effect=paused_write):
            writer = pool.submit(race._write_live_generation_recovery_journal, cp)
            assert entered.wait(5)
            deleter = pool.submit(race.after_node_deleted)
            release.set()
            writer.result(5)
            deleter.result(5)
    fresh(new(race.name), cp["journal_id"])

    # Native workflow close uses the same hook; keep its disk checkpoint so a
    # normal reopen restores its saved checkpoint. No disk deletion required.
    denied = new("Read-only retired journal")
    cp = pending(denied, "running")
    with mock.patch.object(Path, "unlink", side_effect=PermissionError("read-only")):
        denied.after_node_deleted()
    fresh(new(denied.name), cp["journal_id"])
    assert cp["journal_id"] not in target._RECOVERY_JOURNAL_OWNERS
    restored = new("Reopen same saved workflow")
    restored.set_parameter_value(target.SEEDANCE_RECOVERY_PARAMETER, cp, initial_setup=True)
    assert restored._generation_recovery_state()["task_id"] == cp["task_id"]
    assert restored._generation_recovery_blocks_new_submission()
    assert other_path.read_bytes() == other_bytes
    print(f"PASS: {count} Reset/Delete lifecycle cases; late writes, disk race, isolation and normal Run guards")


with tempfile.TemporaryDirectory(prefix="hmb-reset-delete-") as directory:
    folder = Path(directory)
    with mock.patch.object(target, "_seedance_recovery_journal_path", side_effect=lambda key: folder / f"{key}.json"), \
         mock.patch.object(target._shot_routing, "schedule_post_deletion_reconcile"), \
         mock.patch.object(target.HMBSeedanceGeneration, "_create_broker_bridge", side_effect=AssertionError("Reset must not contact Broker")):
        asyncio.run(verify(folder))
