"""Saved Generator snapshots win over discarded, newer render journals.

No network, provider calls, automatic native saves, real renders or user files.
The temporary journals deliberately contain newer same-UUID tasks. Hydration
must use only the explicit saved checkpoint, outputs and completed-video route.
"""
from __future__ import annotations

import asyncio
from contextlib import ExitStack
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
from uuid import uuid4

from _hmb_seedance_clean_ci_stubs import install_clean_ci_griptape_stubs

install_clean_ci_griptape_stubs()
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "seedance_discarded_workflow_recovery", ROOT / "HMBSeedanceGeneration.py"
)
target = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = target
spec.loader.exec_module(target)

UNSAVED_STATUSES = (
    "submitting", "queued", "running", "submission_unknown", "timed_out",
    "failed", "succeeded",
)
HYDRATION_HOOKS = (
    "after_deserialize", "after_load", "on_loaded",
    "_hmb_post_registration_shot_discovery", "_hmb_post_hydration_state_restore",
)


class DiscardedWorkflowRecoveryTests(unittest.TestCase):
    cases_checked = 0

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.folder = Path(self.stack.enter_context(tempfile.TemporaryDirectory(
            prefix="hmb-discarded-workflow-"
        )))
        self.stack.enter_context(mock.patch.object(
            target, "_seedance_recovery_journal_path",
            side_effect=lambda identity: self.folder / f"{identity}.json",
        ))
        self.broker = self.stack.enter_context(mock.patch.object(
            target.HMBSeedanceGeneration, "_create_broker_bridge",
            side_effect=AssertionError("Hydration must not contact the Broker"),
        ))
        self.host = self.stack.enter_context(mock.patch.object(
            target.GriptapeNodes, "ahandle_request", create=True,
            new_callable=mock.AsyncMock,
        ))
        self.stack.enter_context(mock.patch.object(
            target._shot_routing, "schedule_post_deletion_reconcile"
        ))
        self.nodes = []

    def tearDown(self):
        self.broker.assert_not_called()
        self.host.assert_not_called()
        for node in self.nodes:
            node.after_node_deleted()

    def node(self, name="HMB Seedance Generation", shot=1):
        node = target.HMBSeedanceGeneration(name=name)
        node._discard_dangling_owned_list_connections_before_delete = lambda: None
        node._reconcile_shared_shot_routing = lambda: None
        node._restore_seedance_shot_route = lambda: None
        node._schedule_existing_generation_refresh = mock.Mock(
            side_effect=AssertionError("Hydration must not schedule a refresh")
        )
        origin = {
            "channel_uuid": str(uuid4()), "shot_uuid": str(uuid4()),
            "source_node_instance_id": str(uuid4()),
            "number": shot, "name": f"Shot {shot}",
        }
        node._capture_generated_video_origin = lambda: deepcopy(origin)
        self.nodes.append(node)
        return node

    def render_metadata(self, node, task_id, status, media=None):
        """Persist render metadata only; native workflow snapshot is untouched."""
        stage = (
            "local_succeeded" if status == "succeeded" else
            "pre_submit" if status == "submitting" else
            "terminal" if status == "failed" else "accepted"
        )
        checkpoint = node._set_generation_recovery_checkpoint(
            stage=stage, task_id=task_id,
            task_identity="client_request" if status == "submitting" else "broker_task",
            status=status, terminal=status == "failed",
            params={"_hmb_generation_origin": node._capture_generated_video_origin()},
        )
        node.parameter_output_values.update({
            "generation_id": task_id, "generation_status": status,
            "provider_response": {"id": task_id, "status": status},
        })
        if media is not None:
            video = target.VideoUrlArtifact(value=str(media), name=media.name)
            node.parameter_output_values.update(video_url=video, VIDEO_OUT=video)
            source = target._generated_video_source_value({
                "schema": target.GENERATED_VIDEO_SOURCE_SCHEMA, "version": 1,
                **node._capture_generated_video_origin(),
                "generation_id": task_id, "task_id": task_id,
                "result_revision": 1, "path": str(media), "url": str(media),
                "completed": True,
            })
            self.assertTrue(source)
            node.parameter_values[target.GENERATED_VIDEO_SOURCE_PARAMETER] = deepcopy(source)
            node.parameter_output_values[target.GENERATED_VIDEO_SOURCE_PARAMETER] = deepcopy(source)
            node._hmb_generated_video_source = deepcopy(source)
        node._write_live_generation_recovery_journal(checkpoint)
        return checkpoint

    @staticmethod
    def snapshot(node):
        return deepcopy({
            "checkpoint": node.get_parameter_value(target.SEEDANCE_RECOVERY_PARAMETER),
            "outputs": node.parameter_output_values,
            "source": node.get_parameter_value(target.GENERATED_VIDEO_SOURCE_PARAMETER),
        })

    def reopen(self, snapshot, name="HMB Seedance Generation", shot=1):
        node = self.node(name, shot)
        node.parameter_output_values.update(deepcopy(snapshot["outputs"]))
        node.set_parameter_value(target.GENERATED_VIDEO_SOURCE_PARAMETER,
                                 deepcopy(snapshot["source"]), initial_setup=True)
        # The recovery property is the host's final hydration sentinel.
        node.set_parameter_value(target.SEEDANCE_RECOVERY_PARAMETER,
                                 deepcopy(snapshot["checkpoint"]), initial_setup=True)
        for hook in HYDRATION_HOOKS:
            getattr(node, hook)()
        node._schedule_existing_generation_refresh.assert_not_called()
        return node

    def assert_authoritative(self, node, snapshot):
        saved_checkpoint = target._seedance_recovery_value(snapshot["checkpoint"])
        self.assertEqual(node._generation_recovery_state(), saved_checkpoint)
        expected_id = saved_checkpoint["task_id"]
        self.assertEqual(node._authoritative_existing_generation_id(), expected_id)
        self.assertEqual(node.parameter_output_values.get("generation_id") or "", expected_id)
        for field in ("VIDEO_OUT", "video_url", "last_frame_url"):
            expected = snapshot["outputs"].get(field)
            actual = node.parameter_output_values.get(field)
            self.assertEqual(getattr(actual, "value", actual), getattr(expected, "value", expected))
        self.assertEqual(node._hmb_generated_video_source_snapshot(),
                         target._generated_video_source_value(snapshot["source"]))
        type(self).cases_checked += 1

    def media(self, directory, content):
        folder = self.folder / directory
        folder.mkdir()
        path = folder / "same-video-name.mp4"
        path.write_bytes(content)
        return path

    def test_01_idle_saved_snapshot_discards_unsaved_render_for_every_status(self):
        for status in UNSAVED_STATUSES:
            with self.subTest(status=status):
                old = self.node()
                saved = self.snapshot(old)
                self.render_metadata(old, f"job-unsaved-{status}", status)
                journal = target._seedance_recovery_journal_path(saved["checkpoint"]["journal_id"])
                before = journal.read_bytes()
                old.after_node_deleted()  # native close also invokes this hook
                opened = self.reopen(saved)
                self.assert_authoritative(opened, saved)
                self.assertFalse(opened._generation_recovery_blocks_new_submission())
                self.assertEqual(opened._hmb_generation_preview_state["action"], "none")
                self.assertEqual(journal.read_bytes(), before)

    def test_02_saved_video_a_remains_a_after_unsaved_render_b(self):
        for status in UNSAVED_STATUSES:
            with self.subTest(status=status):
                old = self.node()
                a = self.media(f"saved-{status}", b"saved video A")
                b = self.media(f"discarded-{status}", b"discarded video B")
                self.render_metadata(old, f"job-saved-a-{status}", "succeeded", a)
                saved = self.snapshot(old)
                self.render_metadata(old, f"job-discarded-b-{status}", status, b)
                old.after_node_deleted()
                opened = self.reopen(saved)
                self.assert_authoritative(opened, saved)
                self.assertFalse(opened._generation_recovery_blocks_new_submission())
                self.assertEqual(a.read_bytes(), b"saved video A")
                self.assertEqual(b.read_bytes(), b"discarded video B")

    def test_03_saved_running_task_retains_its_exact_refresh_identity(self):
        for status in UNSAVED_STATUSES:
            with self.subTest(discarded_status=status):
                old = self.node()
                self.render_metadata(old, f"job-saved-running-{status}", "running")
                saved = self.snapshot(old)
                self.render_metadata(old, f"job-discarded-new-{status}", status)
                old.after_node_deleted()
                opened = self.reopen(saved)
                self.assert_authoritative(opened, saved)
                self.assertTrue(opened._generation_recovery_blocks_new_submission())
                self.assertEqual(opened._hmb_generation_preview_state["action"], "refresh_existing")
                self.assertEqual(opened._hmb_generation_preview_state["job_id"],
                                 f"job-saved-running-{status}")

    def test_04_five_same_named_nodes_and_reverse_hydration_stay_isolated(self):
        saved = []
        for shot in range(1, 6):
            old = self.node(shot=shot)
            video = self.media(f"shot-{shot}", f"shot {shot} saved".encode())
            self.render_metadata(old, f"job-shot-{shot}-saved", "succeeded", video)
            saved.append(self.snapshot(old))
            self.render_metadata(old, f"job-shot-{shot}-discarded", "running")
            old.after_node_deleted()
        self.assertEqual(len({item["checkpoint"]["journal_id"] for item in saved}), 5)
        for shot in range(5, 0, -1):
            opened = self.reopen(saved[shot - 1], shot=shot)
            self.assert_authoritative(opened, saved[shot - 1])
            self.assertEqual(opened._hmb_generated_video_source_snapshot()["number"], shot)

    def test_05_new_instance_never_adopts_task_by_node_name_or_shot(self):
        for shot in range(1, 6):
            old = self.node(shot=shot)
            previous = self.render_metadata(old, f"job-retired-shot-{shot}", "running")
            old.after_node_deleted()
            fresh = self.node(shot=shot)
            saved = self.snapshot(fresh)
            for hook in HYDRATION_HOOKS:
                getattr(fresh, hook)()
            self.assert_authoritative(fresh, saved)
            self.assertNotEqual(fresh._generation_recovery_state()["journal_id"], previous["journal_id"])

    def test_06_explicitly_saved_empty_reset_checkpoint_is_authoritative(self):
        old = self.node()
        self.render_metadata(old, "job-before-clear", "running")
        old.parameter_output_values.update(generation_id="", generation_status="", provider_response=None)
        old._clear_generation_recovery_checkpoint()
        saved = self.snapshot(old)
        self.assertGreater(saved["checkpoint"]["updated_at_ms"], 0)
        self.render_metadata(old, "job-discarded-after-clear", "running")
        old.after_node_deleted()
        self.assert_authoritative(self.reopen(saved), saved)

    def test_07_all_hydration_hooks_repeat_without_adopting_disk_updates(self):
        old = self.node()
        saved = self.snapshot(old)
        self.render_metadata(old, "job-unsaved-at-close", "running")
        old.after_node_deleted()
        opened = self.reopen(saved)
        for index, hook in enumerate(HYDRATION_HOOKS):
            newer = target._seedance_recovery_value({
                **saved["checkpoint"], "task_id": f"job-late-disk-{index}",
                "status": "running", "stage": "accepted", "task_identity": "broker_task",
                "revision": 50 + index, "updated_at_ms": 9_000_000_000_000 + index,
            })
            target._write_seedance_recovery_journal(newer)
            getattr(opened, hook)()
            self.assert_authoritative(opened, saved)

    def test_08_invalid_external_journal_cannot_change_saved_media(self):
        for raw in ("{invalid json", "x" * 70_000):
            with self.subTest(length=len(raw)):
                old = self.node()
                saved = self.snapshot(old)
                journal = target._seedance_recovery_journal_path(saved["checkpoint"]["journal_id"])
                journal.write_text(raw, encoding="utf-8")
                old.after_node_deleted()
                self.assert_authoritative(self.reopen(saved), saved)
                self.assertEqual(journal.read_text(encoding="utf-8"), raw)

    def test_09_diagnostic_checkpoint_write_never_saves_or_rekeys_workflow(self):
        old = self.node()
        saved = self.snapshot(old)
        native_file = self.folder / "manual-workflow.py"
        native_file.write_bytes(b"# explicitly saved workflow snapshot\n")
        before = (native_file.read_bytes(), native_file.stat().st_mtime_ns)
        self.render_metadata(old, "job-unsaved-diagnostic", "running")
        result = asyncio.run(old._force_save_generation_recovery_checkpoint(
            required=True, reason="test diagnostic checkpoint"
        ))
        self.assertTrue(result)
        self.host.assert_not_called()
        self.assertEqual((native_file.read_bytes(), native_file.stat().st_mtime_ns), before)
        old.after_node_deleted()
        self.assert_authoritative(self.reopen(saved), saved)

    def test_10_saved_checkpoint_loads_without_a_local_journal(self):
        old = self.node()
        self.render_metadata(old, "job-manually-saved-running", "running")
        saved = self.snapshot(old)
        journal = target._seedance_recovery_journal_path(saved["checkpoint"]["journal_id"])
        old.after_node_deleted()
        journal.unlink()
        opened = self.reopen(saved)
        self.assert_authoritative(opened, saved)
        self.assertEqual(opened._hmb_generation_preview_state["action"], "refresh_existing")


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(DiscardedWorkflowRecoveryTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(f"Discarded workflow recovery: {result.testsRun} test groups, "
          f"{DiscardedWorkflowRecoveryTests.cases_checked} authoritative snapshot checks passed; "
          "zero network requests / zero native saves")
    raise SystemExit(0 if result.wasSuccessful() else 1)
