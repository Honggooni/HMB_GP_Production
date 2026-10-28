"""Offline start-state planning. No CGT client, provider calls or writes."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import _hmb_cgt as cgt


class WorkStartPlanRegression(unittest.TestCase):
    def setUp(self):
        self.account, self.project, self.pipeline = [str(uuid4()) for _ in range(3)]
        self.scope = {"origin": "https://fixture.invalid", "project_id": self.project,
            "project_db": "fixture_project", "module": "shot", "module_type": "task",
            "pipeline_id": self.pipeline, "account_id": self.account}
        self.binding = {"cgt_account_id": self.account, "cgt_scope": self.scope, "members": []}
        self.snapshot = {"status": "ready", "account_id": self.account, "origin": self.scope["origin"],
            "project": {"id": self.project, "database": "fixture_project", "entity": "Fixture"},
            "can_bind": True, "truncated": False, "tls_verified": True, "hostname_verified": True, "tasks": []}

    def add(self, status="Wait"):
        task_id, entity = str(uuid4()), str(uuid4())
        identity = {"task_id": task_id, "entity_id": entity, "pipeline_id": self.pipeline}
        row = {"task_id": task_id, "identity": identity, "source_name": "e201s001c001__",
               "pipeline_id": self.pipeline, "artist": "Fixture Artist", "status": status}
        self.snapshot["tasks"].append(row)
        self.binding["members"].append({"origin": "cgt", "cgt_task_id": task_id,
            "cgt_identity": identity, "source_name": row["source_name"], "artist": row["artist"], "status": status})
        return task_id

    def plan(self, previous=None):
        return cgt.plan_wait_to_work_transition(previous or {}, self.binding, "Fixture", self.snapshot,
            commit_request_id="fixture-explicit-shot-commit")

    def test_wait_is_planned_as_conditional_and_submission_stays_disabled(self):
        task = self.add()
        result = self.plan()
        self.assertEqual(result["status"], "requires_atomic_status_transition")
        self.assertEqual(result["transitions"][0]["task_id"], task)
        self.assertEqual(result["transitions"][0]["expected_status"], "Wait")
        self.assertEqual(result["transitions"][0]["status"], "Work")
        self.assertFalse(result["submission_enabled"])

    def test_work_is_noop(self):
        self.add("Work")
        result = self.plan()
        self.assertEqual(result["transitions"], [])
        self.assertEqual(result["skipped"][0]["reason"], "already_work")

    def test_other_states_including_different_case_are_noop(self):
        for status in ("Approve", "Submit", "Close", "Retake", "wait", "work", "", "Unknown"):
            with self.subTest(status=status):
                self.setUp(); self.add(status)
                result = self.plan()
                self.assertEqual(result["transitions"], [])
                self.assertEqual(result["skipped"][0]["reason"], "other_status")

    def test_existing_binding_reconfirm_or_reopen_never_plans_start(self):
        self.add()
        result = self.plan(deepcopy(self.binding))
        self.assertEqual(result["transitions"], [])
        self.assertEqual(result["skipped"][0]["reason"], "existing_binding")

    def test_mixed_list_only_new_wait_is_planned(self):
        self.add("Wait"); prior = deepcopy(self.binding)
        new_wait = self.add("Wait"); self.add("Work"); self.add("Approve")
        result = self.plan(prior)
        self.assertEqual([row["task_id"] for row in result["transitions"]], [new_wait])
        self.assertEqual(len(result["skipped"]), 3)

    def test_manual_shots_never_plan_a_cgt_update(self):
        self.binding["members"] = [{"origin": "manual"}]
        self.assertEqual(self.plan()["transitions"], [])

    def test_source_and_bindings_are_not_modified(self):
        self.add(); before = deepcopy((self.binding, self.snapshot))
        self.plan()
        self.assertEqual((self.binding, self.snapshot), before)

    def test_unverified_or_truncated_snapshot_rejected(self):
        for key, value in (("tls_verified", False), ("hostname_verified", False), ("can_bind", False), ("truncated", True)):
            with self.subTest(key=key):
                self.setUp(); self.add(); self.snapshot[key] = value
                with self.assertRaises(ValueError): self.plan()

    def test_changed_account_project_or_origin_rejected(self):
        for key in ("account_id", "origin", "project"):
            with self.subTest(key=key):
                self.setUp(); self.add()
                self.snapshot[key] = {"id": str(uuid4())} if key == "project" else str(uuid4())
                with self.assertRaises(ValueError): self.plan()

    def test_changed_task_status_or_identity_rejected(self):
        for key, value in (("status", "Work"), ("identity", {}), ("artist", "Other Artist"), ("source_name", "other")):
            with self.subTest(key=key):
                self.setUp(); self.add(); self.snapshot["tasks"][0][key] = value
                with self.assertRaises(ValueError): self.plan()

    def test_non_task_scope_rejected(self):
        self.add(); self.scope["module_type"] = "info"
        with self.assertRaises(ValueError): self.plan()

    def test_duplicate_tasks_rejected(self):
        self.add(); self.binding["members"].append(deepcopy(self.binding["members"][0]))
        with self.assertRaises(ValueError): self.plan()
        self.binding["members"].pop(); self.snapshot["tasks"].append(deepcopy(self.snapshot["tasks"][0]))
        with self.assertRaises(ValueError): self.plan()

    def test_malformed_commit_and_ids_rejected(self):
        self.add(); self.binding["members"][0]["cgt_task_id"] = "untrusted-task-name"
        with self.assertRaises(ValueError): self.plan()
        with self.assertRaises(ValueError):
            cgt.plan_wait_to_work_transition({}, {}, "Fixture", {}, commit_request_id="")


if __name__ == "__main__":
    unittest.main(verbosity=2)
