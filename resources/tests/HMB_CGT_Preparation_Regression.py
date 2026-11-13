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
    def test_assignment_does_not_wait_for_unrelated_media_scan(self):
        import _hmb_shot_basket as basket
        state = dict(project_id="superwings12", scan_busy=True, error="")
        node = SimpleNamespace(metadata={basket._MARKER: dict(project_id="superwings12", cgt_required=True)})
        with patch.object(basket, "_shot_state", return_value=(state, None)), patch.object(basket, "_basket_shots", return_value=[]):
            node.name = "Fixture Image"
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
            self.assertIsNone(preparation.reader("superwings12"))
            self.assertIsNone(preparation.reader("Katuri8"))
            release.set()
            value = getter(threading.Event())
            self.assertEqual(value, result)
            value["tasks"].clear()
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


if __name__ == "__main__":
    unittest.main()
