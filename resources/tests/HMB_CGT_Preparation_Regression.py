"""Read-only look-ahead, one-use display cache and cancellation. No CGT IO."""
import sys
import threading
import time
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import _hmb_cgt as cgt


class PreparationTests(unittest.TestCase):
    def test_generator_uses_active_local_shot_without_assignment_state(self):
        import _hmb_shot_basket as basket
        from uuid import uuid4

        workspace, first, second = (str(uuid4()) for _ in range(3))
        marker = dict(project_id="superwings12", workspace_id=workspace, cgt_required=True)
        state = dict(project_id=marker["project_id"], error="CGT offline",
                     shot_routing=dict(active_shot_uuid=second, shots=[{"shot_uuid": first}, {"shot_uuid": second}]))
        image = SimpleNamespace(metadata={basket._MARKER: dict(marker, kind="image")}, _current_state=lambda: state)
        generator = SimpleNamespace(metadata={basket._MARKER: dict(marker, kind="generator")})
        with patch.object(basket, "_basket_shots", side_effect=AssertionError("unexpected CGT lookup")):
            self.assertEqual(basket.initial_seedance_shot(generator, image), second)
            state["project_id"] = "Katuri8"
            self.assertEqual(basket.initial_seedance_shot(generator, image), "")

    def test_assignment_does_not_wait_for_unrelated_media_scan(self):
        import _hmb_shot_basket as basket
        state = dict(project_id="superwings12", scan_busy=True, error="",
                     shot_routing={"active_shot_uuid": "", "shots": []})
        node = SimpleNamespace(name="Fixture Image", _current_state=lambda: state,
                               metadata={basket._MARKER: dict(project_id="superwings12", cgt_required=True)})
        kinds = dict(image=node)
        result = basket._status(SimpleNamespace(name="Fixture"), kinds, [], False)
        self.assertEqual(result["status"], "ready")
        self.assertTrue(result["media_preparing"])
        state["project_id"] = "Katuri8"
        self.assertEqual(basket._status(None, kinds, [], False)["status"], "preparing")
        state.update(project_id="superwings12", scan_busy=False, error="offline")
        self.assertEqual(basket._status(None, kinds, [], False)["status"], "unavailable")

    def test_pending_read_is_shared_and_used_once_without_blocking_entry(self):
        entered, release = threading.Event(), threading.Event()
        result = dict(schema=cgt.SCHEMA, status="ready", tasks=[dict(name="fixture")])
        def catalog(*args, **kwargs):
            entered.set()
            assert release.wait(2)
            return result
        with patch.object(cgt, "catalog", side_effect=catalog) as read:
            preparation = cgt.CatalogPreparation()
            started = time.perf_counter()
            preparation.prepare("superwings12")
            self.assertLess(time.perf_counter() - started, .1)
            self.assertTrue(entered.wait(2))
            preparation.prepare("superwings12")
            getter = preparation.reader("superwings12")
            second = preparation.reader("superwings12")
            self.assertTrue(callable(second))
            self.assertIsNone(preparation.reader("Katuri8"))
            release.set()
            value = getter(threading.Event())
            self.assertEqual(value, result)
            value["tasks"].clear()
            self.assertEqual(second(threading.Event()), result)
            self.assertIsNone(preparation.reader("superwings12"))
            self.assertEqual(len(result["tasks"]), 1)
            self.assertEqual(read.call_count, 1)

    def test_project_switch_cancels_previous_and_never_delivers_wrong_scope(self):
        entered = threading.Event()
        def catalog(project, *, cancel):
            if project == "superwings12":
                entered.set()
                self.assertTrue(cancel.wait(2))
            return dict(status="ready", project=project, tasks=[])
        with patch.object(cgt, "catalog", side_effect=catalog):
            preparation = cgt.CatalogPreparation()
            preparation.prepare("superwings12")
            self.assertTrue(entered.wait(2))
            old = preparation.reader("superwings12")
            preparation.prepare("Katuri8")
            getter = preparation.reader("Katuri8")
            self.assertEqual(getter(threading.Event())["project"], "Katuri8")
            self.assertEqual(old(threading.Event())["status"], "TIMEOUT")

    def test_expiry_and_failure_and_cancel_do_not_write_or_stall(self):
        with patch.object(cgt, "catalog", side_effect=RuntimeError("fixture")):
            preparation = cgt.CatalogPreparation()
            preparation.prepare("Katuri8")
            result = preparation.reader("Katuri8")(threading.Event())
            self.assertEqual(result["status"], "SDK_UNAVAILABLE")
            preparation.job["started"] -= 16
            self.assertIsNone(preparation.reader("Katuri8"))
            preparation.prepare("invalid/project")
            self.assertEqual(preparation.job["project"], "Katuri8")

    def test_slow_inflight_is_reused_without_extending_original_deadline(self):
        preparation = cgt.CatalogPreparation()
        job = dict(project="show", started=0, deadline=24, completed=None,
                   cancel=threading.Event(), done=threading.Event(), result=None)
        preparation.job = job
        with patch.object(cgt, "monotonic", return_value=16), patch.object(cgt, "Thread") as spawn:
            preparation.prepare("show")
            first = preparation.reader("show")
            second = preparation.reader("show")
            self.assertTrue(callable(first) and callable(second))
            spawn.assert_not_called()
            self.assertEqual(job["deadline"], 24)
        with patch.object(cgt, "monotonic", return_value=24.1):
            self.assertEqual(first(threading.Event())["status"], "TIMEOUT")
            self.assertIsNone(preparation.reader("show"))

    def test_completed_ttl_starts_at_completion_and_reader_cancel_is_independent(self):
        preparation = cgt.CatalogPreparation()
        job = dict(project="show", started=0, deadline=24, completed=None,
                   cancel=threading.Event(), done=threading.Event(), result=None)
        preparation.job = job
        with patch.object(cgt, "monotonic", return_value=16):
            abandoned, live = preparation.reader("show"), preparation.reader("show")
        job.update(completed=23, result={"status":"ready", "tasks":[{"task_id":"a"}]})
        job["done"].set()
        cancel = threading.Event(); cancel.set()
        self.assertEqual(abandoned(cancel)["status"], "TIMEOUT")
        self.assertFalse(job["cancel"].is_set())
        self.assertEqual(live(threading.Event())["status"], "ready")
        job.pop("taken")
        with patch.object(cgt, "monotonic", return_value=30):
            self.assertTrue(callable(preparation.reader("show")))
        job.pop("taken")
        with patch.object(cgt, "monotonic", return_value=38):
            self.assertIsNone(preparation.reader("show"))


if __name__ == "__main__":
    unittest.main()
