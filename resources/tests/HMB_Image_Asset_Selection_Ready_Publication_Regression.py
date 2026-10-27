"""Portable ordering regression for an actual extracted ImageAsset method.

No SDK engine, worker, filesystem media, provider or live graph is constructed.
The retained host is a small fake; cache identity and completion consumption are
compiled directly from the production AST rather than reimplemented here.
"""
from __future__ import annotations

import ast
from collections import OrderedDict
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import threading
from typing import Any, Dict
import unittest


SOURCE = Path(__file__).resolve().parents[2] / "HMBImageAssetLibrary.py"
TREE = ast.parse(SOURCE.read_text("utf-8-sig"), filename=str(SOURCE))


def extracted_consumer(*, legacy_unconditional=False):
    helpers = {"_clean", "_non_negative_int", "_resolution_cache_state_identity",
               "_resolution_cache_put"}
    definitions = [deepcopy(node) for node in TREE.body
                   if isinstance(node, ast.FunctionDef) and node.name in helpers]
    owner = next(node for node in TREE.body
                 if isinstance(node, ast.ClassDef) and node.name == "HMBImageAssetLibrary")
    consumer = deepcopy(next(node for node in owner.body
                             if isinstance(node, ast.FunctionDef)
                             and node.name == "_consume_selection_resolution"))
    if legacy_unconditional:
        # Restore precisely the old consume-before-read ordering to prove this
        # test rejects the observed race, without depending on a Git checkout.
        changed = 0
        for node in ast.walk(consumer):
            if isinstance(node, ast.With):
                for index, statement in enumerate(node.body):
                    if (isinstance(statement, ast.If)
                            and isinstance(statement.test, ast.Name)
                            and statement.test.id == "publish"):
                        node.body[index:index + 1] = statement.body
                        changed += 1
        assert changed == 1, "The legacy ordering proof must affect exactly one gate"
    namespace = {"Any": Any, "Dict": Dict, "OrderedDict": OrderedDict,
                 "json": json, "hashlib": hashlib,
                 "_ASSET_RESOLUTION_CACHE_LIMIT": 256,
                 "_shot_routing_catalog_identity": lambda state, **_: state["project_uid"]}
    module = ast.fix_missing_locations(ast.Module(body=definitions + [consumer], type_ignores=[]))
    exec(compile(module, str(SOURCE), "exec"), namespace)
    return namespace["_consume_selection_resolution"], namespace["_resolution_cache_state_identity"]


CONSUME, IDENTITY = extracted_consumer()
ASSET_OUT, MEDIA_OUT, SHOT_OUT = "IMAGE_ASSET_OUT", "IMAGE_OUT", "SHOT_ASSET_OUT"


def extracted_output_path(*, legacy_unchanged_token=False):
    stage = deepcopy(next(node for node in TREE.body if isinstance(node, ast.FunctionDef)
                          and node.name == "_stage_and_notify_image_output_pair"))
    owner = next(node for node in TREE.body
                 if isinstance(node, ast.ClassDef) and node.name == "HMBImageAssetLibrary")
    sync = deepcopy(next(node for node in owner.body if isinstance(node, ast.FunctionDef)
                         and node.name == "_sync_output"))
    if legacy_unchanged_token:
        class OldTokenGate(ast.NodeTransformer):
            changed = 0

            def visit_Name(self, node):
                if node.id == "notify_unchanged_shot" and isinstance(node.ctx, ast.Load):
                    self.changed += 1
                    return ast.copy_location(ast.Constant(False), node)
                return node
        old = OldTokenGate()
        stage = old.visit(stage)
        assert old.changed == 1, "Restore only the old unchanged-token notification gate"

    def set_output(node, name, value):
        node.parameter_output_values[name] = deepcopy(value)
        node.staged.append(name)

    def physical_delivery(node, name, value, **_kwargs):
        node.physical_deliveries.append((name, value))

    def no_media_work(*_args, **_kwargs):
        raise AssertionError("The cached readiness path must not resolve media or touch files")

    definitions = [deepcopy(node) for node in TREE.body if isinstance(node, ast.FunctionDef)
                   and node.name in {"_clean", "_non_negative_int"}]
    namespace = {"Any": Any, "Dict": Dict, "OUTPUT_PARAMETER": ASSET_OUT,
                 "MEDIA_OUTPUT_PARAMETER": MEDIA_OUT, "SHOT_ASSET_OUTPUT_PARAMETER": SHOT_OUT,
                 "set_output": set_output, "_is_image_output_side_effect_callback": lambda _: False,
                 "_propagate_image_output_to_connections": physical_delivery,
                 "_project_output_fingerprint": lambda *_args: "cached-pair",
                 "_normalize_state": no_media_work, "_build_synchronized_outputs": no_media_work}
    module = ast.fix_missing_locations(ast.Module(body=definitions + [stage, sync], type_ignores=[]))
    exec(compile(module, str(SOURCE), "exec"), namespace)
    return namespace["_stage_and_notify_image_output_pair"], namespace["_sync_output"]


STAGE, SYNC = extracted_output_path()


class RetainedHost:
    def __init__(self, consumer=CONSUME):
        self.consumer = consumer
        self.live = {"catalog_root": "C:/synthetic", "project_root": "C:/synthetic/A",
                     "project_id": "A", "project_uid": "uid-A", "project_cache_uid": "cache-A",
                     "manifest_signature": "manifest", "scan_revision": 4, "scan_busy": False}
        self.entries = OrderedDict([("asset-A", {"path": "C:/synthetic/A/asset.png"})])
        self.ready = (IDENTITY(self.live), 7, self.entries)
        self._hmb_selection_resolution_work = {
            "lock": threading.RLock(), "ready": self.ready, "epoch": 7}
        self.cache = OrderedDict()
        self.registered_owner = self
        self.deleted = False
        self.publications = []
        self.selection_ready_flags = []
        self.routes = []
        self.read_during_sync = False
        self.recursive_read_results = []

    def consume(self, *, publish=False):
        return self.consumer(self, publish=publish)

    def _scan_owner_is_current(self):
        return not self.deleted and self.registered_owner is self

    def _current_state(self):
        return deepcopy(self.live)

    def _resolution_cache_for_state(self, _state):
        return self.cache

    def _sync_output(self, state, *, normalized=False, selection_ready=False):
        assert normalized is True
        assert selection_ready is True, "Only validated completion marks the ready publication"
        self.selection_ready_flags.append(selection_ready)
        self.publications.append(deepcopy(state))
        if self.read_during_sync:
            self.recursive_read_results.append(self.consume(publish=False))

    def _reconcile_hmb_shot_routing(self, identity):
        self.routes.append(identity)


class OutputHost(RetainedHost):
    def _persist_shot_routing_facts(self, state, snapshot):
        # This fixture isolates output notification ordering. Full real-node
        # persistence is exercised by HMB_Image_Asset_Publication_Cursor_Regression.
        assert state == self.live

    def __init__(self):
        super().__init__()
        self._hmb_last_output_fingerprint = "cached-pair"
        self._hmb_last_output_pair = ('{"asset":"current"}', ["synthetic-media"])
        self.parameter_output_values = {
            ASSET_OUT: self._hmb_last_output_pair[0],
            MEDIA_OUT: list(self._hmb_last_output_pair[1]), SHOT_OUT: "same-shot-token"}
        self._hmb_import_media_by_uid = {}
        self._hmb_import_revision = 0
        self.staged = []
        self.physical_deliveries = []
        self.published_snapshots = []

    def _defer_project_selection_resolution(self, _state):
        # This is the synchronous read that _sync_output normally performs.
        self.recursive_read_results.append(self.consume(publish=False))
        return False

    def _cache_shot_routing_snapshot(self, state, **_kwargs):
        return {"synthetic": True}

    def _shot_asset_dependency_token(self, _snapshot):
        return "same-shot-token"

    def publish_update_to_parameter(self, name, value):
        self.published_snapshots.append((name, deepcopy(self.parameter_output_values)))

    def _sync_output(self, state, **kwargs):
        return SYNC(self, state, **kwargs)


class SelectionReadyPublicationTests(unittest.TestCase):
    def assert_published_once(self, host):
        self.assertTrue(host.consume(publish=True))
        self.assertEqual(host.cache, host.entries)
        self.assertEqual(len(host.publications), 1)
        self.assertEqual(host.routes, ["uid-A"])
        self.assertEqual(host.selection_ready_flags, [True])
        self.assertIsNone(host._hmb_selection_resolution_work["ready"])

    def test_direct_host_callback_publishes_once(self):
        self.assert_published_once(RetainedHost())

    def test_read_warms_cache_without_consuming_queued_publication(self):
        host = RetainedHost()
        self.assertTrue(host.consume(publish=False))
        self.assertEqual(host.cache, host.entries)
        self.assertIs(host._hmb_selection_resolution_work["ready"], host.ready)
        self.assertEqual(host.publications, [])
        self.assertEqual(host.routes, [])
        self.assert_published_once(host)

    def test_repeated_reads_then_duplicate_callbacks_publish_exactly_once(self):
        host = RetainedHost()
        for _ in range(25):
            self.assertTrue(host.consume(publish=False))
        self.assert_published_once(host)
        for _ in range(25):
            self.assertFalse(host.consume(publish=True))
            self.assertFalse(host.consume(publish=False))
        self.assertEqual(len(host.publications), 1)
        self.assertEqual(host.routes, ["uid-A"])

    def test_previous_unconditional_consumer_fails_read_then_publish_contract(self):
        old_consumer, _ = extracted_consumer(legacy_unconditional=True)
        host = RetainedHost(old_consumer)
        self.assertTrue(host.consume(publish=False))
        with self.assertRaises(AssertionError):
            self.assert_published_once(host)
        self.assertEqual(host.cache, host.entries)
        self.assertEqual(host.publications, [])
        self.assertEqual(host.routes, [])

    def test_stale_epoch_cannot_warm_or_publish(self):
        host = RetainedHost()
        host._hmb_selection_resolution_work["epoch"] += 1
        self.assertFalse(host.consume(publish=False))
        self.assertFalse(host.consume(publish=True))
        self.assertEqual((host.cache, host.publications, host.routes), ({}, [], []))

    def test_stale_project_cannot_warm_or_publish(self):
        host = RetainedHost()
        host.live.update(project_root="C:/synthetic/B", project_uid="uid-B",
                         project_cache_uid="cache-B", project_id="B")
        self.assertFalse(host.consume(publish=False))
        self.assertFalse(host.consume(publish=True))
        self.assertEqual((host.cache, host.publications, host.routes), ({}, [], []))

    def test_deleted_owner_cannot_warm_or_publish(self):
        host = RetainedHost()
        host.deleted = True
        self.assertFalse(host.consume(publish=False))
        self.assertFalse(host.consume(publish=True))
        self.assertEqual((host.cache, host.publications, host.routes), ({}, [], []))

    def test_foreign_registered_owner_cannot_warm_or_publish(self):
        host = RetainedHost()
        host.registered_owner = object()
        self.assertFalse(host.consume(publish=False))
        self.assertFalse(host.consume(publish=True))
        self.assertEqual((host.cache, host.publications, host.routes), ({}, [], []))

    def test_read_during_publication_does_not_recurse(self):
        host = RetainedHost()
        host.read_during_sync = True
        self.assertTrue(host.consume(publish=False))
        self.assert_published_once(host)
        self.assertEqual(host.recursive_read_results, [False])
        self.assertFalse(host.consume(publish=True))
        self.assertEqual(len(host.publications), 1)

    def test_empty_or_missing_work_does_nothing(self):
        host = RetainedHost()
        host._hmb_selection_resolution_work["ready"] = None
        self.assertFalse(host.consume(publish=True))
        host._hmb_selection_resolution_work = None
        self.assertFalse(host.consume(publish=False))
        self.assertEqual((host.cache, host.publications, host.routes), ({}, [], []))

    def test_cached_pair_normal_noop_does_not_notify(self):
        host = OutputHost()
        host._hmb_selection_resolution_work["ready"] = None
        host._sync_output(host.live, normalized=True)
        self.assertEqual(host.staged, [])
        self.assertEqual(host.published_snapshots, [])
        self.assertEqual(host.physical_deliveries, [])

    def test_ready_cached_pair_forces_same_shot_token_physical_wake_once(self):
        host = OutputHost()
        self.assertTrue(host.consume(publish=False))
        self.assertTrue(host.consume(publish=True))
        self.assertEqual(host.physical_deliveries, [(SHOT_OUT, "same-shot-token")])
        self.assertEqual([name for name, _ in host.published_snapshots], [ASSET_OUT, MEDIA_OUT, SHOT_OUT])
        self.assertEqual(host.recursive_read_results, [False])
        self.assertFalse(host.consume(publish=True))
        host._sync_output(host.live, normalized=True)
        self.assertEqual(host.physical_deliveries, [(SHOT_OUT, "same-shot-token")])
        self.assertEqual(host._hmb_pending_output_notifications, {})

    def test_stage_helper_normal_same_token_has_no_compact_wake(self):
        host = OutputHost()
        STAGE(host, "fresh-asset", ["fresh-media"], "same-shot-token")
        self.assertEqual([name for name, _ in host.published_snapshots], [ASSET_OUT, MEDIA_OUT])
        self.assertEqual(host.physical_deliveries, [])

    def test_readiness_stages_every_sibling_before_first_notification(self):
        host = OutputHost()
        expected = {ASSET_OUT: "fresh-asset", MEDIA_OUT: ["fresh-media"], SHOT_OUT: "same-shot-token"}
        STAGE(host, expected[ASSET_OUT], expected[MEDIA_OUT], expected[SHOT_OUT],
              notify_unchanged_shot=True)
        self.assertEqual(host.staged, [ASSET_OUT, MEDIA_OUT, SHOT_OUT])
        self.assertEqual([name for name, _ in host.published_snapshots], [ASSET_OUT, MEDIA_OUT, SHOT_OUT])
        self.assertTrue(all(snapshot == expected for _, snapshot in host.published_snapshots))
        self.assertEqual(host.physical_deliveries, [(SHOT_OUT, "same-shot-token")])

    def test_old_helper_drops_same_token_even_when_completion_requests_wake(self):
        old_stage, _ = extracted_output_path(legacy_unchanged_token=True)
        host = OutputHost()
        old_stage(host, "fresh-asset", ["fresh-media"], "same-shot-token",
                  notify_unchanged_shot=True)
        self.assertEqual([name for name, _ in host.published_snapshots], [ASSET_OUT, MEDIA_OUT])
        with self.assertRaises(AssertionError):
            self.assertEqual(host.physical_deliveries, [(SHOT_OUT, "same-shot-token")])

    def test_missing_shot_token_cannot_be_invented_by_ready_flag(self):
        host = OutputHost()
        STAGE(host, "fresh-asset", ["fresh-media"], None, notify_unchanged_shot=True)
        self.assertEqual([name for name, _ in host.published_snapshots], [ASSET_OUT, MEDIA_OUT])
        self.assertEqual(host.physical_deliveries, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
