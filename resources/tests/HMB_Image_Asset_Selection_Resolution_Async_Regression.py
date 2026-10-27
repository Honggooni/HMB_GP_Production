from __future__ import annotations

import asyncio
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
SPEC = importlib.util.spec_from_file_location(
    "hmb_image_selection_resolution_async",
    os.environ.get("HMB_IMAGE_ASSET_TEST_MODULE", str(ROOT / "HMBImageAssetLibrary.py")),
)
assert SPEC is not None and SPEC.loader is not None
asset = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = asset
SPEC.loader.exec_module(asset)


def selected_state(name="A", project="ProjectA"):
    state = asset._default_state()
    state.update({
        "catalog_root": "C:/isolated-projects", "project_id": project,
        "project_root": f"C:/isolated-projects/{project}", "project_uid": project,
        "project_cache_uid": project, "manifest_signature": "fixture-manifest",
        "scan_revision": 1,
        "assets": [{
            "asset_library_id": name, "source_uid": f"project:{name}",
            "source_kind": "project", "asset_project_uid": project,
            "registered": True, "selected": True, "selection_order": 1,
            "path": f"C:/isolated-projects/{project}/{name}.png",
            "relative_path": f"{name}.png", "extension": ".png",
            "image_name": name, "asset_id": name,
            "image_main_type": "CH", "image_sub_type": "Full body",
        }],
    })
    return asset._normalize_state(state)


def fake_node(state):
    node = object.__new__(asset.HMBImageAssetLibrary)
    live = {"state": state}
    node.name = "synthetic_async_selection"
    node.get_parameter_value = lambda name: asset._json_text(live["state"]) if name == asset.WIDGET_STATE_PARAMETER else ""
    def set_value(name, value):
        assert name == asset.WIDGET_STATE_PARAMETER
        live["state"] = asset._normalize_state(value)
    node.set_parameter_value = set_value
    node._current_state = lambda: deepcopy(live["state"])
    node._scan_owner_is_current = lambda: not getattr(node, "_hmb_node_deleted", False)
    node._hmb_import_media_by_uid = {}
    node._hmb_import_revision = 0
    node._hmb_last_resolution_warning = ""
    node.parameter_output_values = {}
    node._reconcile_hmb_shot_routing = lambda *args: None
    return node, live


class SelectionResolutionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.main_thread = threading.get_ident()
        self.release = threading.Event()
        self.entered = threading.Event()
        self.reads = []
        self.published = []

        def read_manifest(path):
            self.reads.append((str(path), threading.get_ident()))
            self.entered.set()
            if threading.get_ident() != self.main_thread:
                assert self.release.wait(2), "Fixture worker was not released"
            else:
                # Old implementation stalls the host callback before returning.
                time.sleep(0.12)
            return {}

        self.patchers = [
            patch.object(asset, "_read_asset_manifest", read_manifest),
            patch.object(asset, "_verified_project_relative_path",
                         lambda row, state, records: row["relative_path"]),
            patch.object(asset, "_stage_and_notify_image_output_pair",
                         lambda node, payload, media, token, **kwargs:
                         self.published.append((json.loads(payload), list(media)))),
        ]
        for patcher in self.patchers:
            patcher.start()

    async def asyncTearDown(self):
        self.release.set()
        await asyncio.sleep(0.04)
        for patcher in reversed(self.patchers):
            patcher.stop()

    async def wait_until(self, predicate):
        deadline = time.monotonic() + 2
        while not predicate() and time.monotonic() < deadline:
            await asyncio.sleep(0.005)
        self.assertTrue(predicate())

    async def test_first_selection_does_not_block_or_clear_last_outputs(self):
        state = selected_state()
        node, _ = fake_node(state)
        sentinel = {"old": "last-good"}
        node.parameter_output_values.update(sentinel)
        started = time.monotonic()
        node._sync_output(state)
        self.assertLess(time.monotonic() - started, 0.08)
        await self.wait_until(self.entered.is_set)
        self.assertEqual(node.parameter_output_values, sentinel)
        self.assertEqual(self.published, [])
        self.assertTrue(all(tid != self.main_thread for _, tid in self.reads))
        self.release.set()
        await self.wait_until(lambda: bool(self.published))
        self.assertEqual(self.published[-1][1], [state["assets"][0]["path"]])
        count = len(self.reads)
        node._sync_output(state)
        self.assertEqual(len(self.reads), count)

    async def test_rapid_selection_keeps_only_latest_queued_click(self):
        node, live = fake_node(selected_state("A"))
        node._sync_output(live["state"])
        await self.wait_until(self.entered.is_set)
        for name in ("B", "C"):
            live["state"] = selected_state(name)
            node._sync_output(live["state"])
        self.assertEqual(len(self.reads), 1)
        self.release.set()
        await self.wait_until(lambda: bool(self.published))
        self.assertTrue(all(media == [live["state"]["assets"][0]["path"]]
                            for _, media in self.published))
        self.assertEqual(len(self.reads), 2)

    async def test_project_switch_rejects_old_result(self):
        node, live = fake_node(selected_state("A", "ProjectA"))
        node._sync_output(live["state"])
        await self.wait_until(self.entered.is_set)
        live["state"] = selected_state("B", "ProjectB")
        node._sync_output(live["state"])
        self.release.set()
        await self.wait_until(lambda: bool(self.published))
        self.assertTrue(all(media == [live["state"]["assets"][0]["path"]]
                            for _, media in self.published))

    async def test_project_a_b_a_retires_obsolete_queue(self):
        node, live = fake_node(selected_state("A", "ProjectA"))
        node._sync_output(live["state"])
        await self.wait_until(self.entered.is_set)
        live["state"] = selected_state("B", "ProjectB")
        node._sync_output(live["state"])
        live["state"] = selected_state("A", "ProjectA")
        node._sync_output(live["state"])
        self.release.set()
        await self.wait_until(lambda: bool(self.published))
        self.assertTrue(all(media == [live["state"]["assets"][0]["path"]]
                            for _, media in self.published))
        self.assertEqual(len(self.reads), 1)

    async def test_failed_resolver_drains_newest_queued_selection(self):
        node, live = fake_node(selected_state("A"))
        original = asset._resolve_selected_assets

        def fail_first(state, *args, **kwargs):
            if state["assets"][0]["image_name"] == "A":
                self.entered.set()
                assert self.release.wait(2)
                raise RuntimeError("isolated resolver failure")
            return original(state, *args, **kwargs)

        with patch.object(asset, "_resolve_selected_assets", fail_first):
            node._sync_output(live["state"])
            await self.wait_until(self.entered.is_set)
            live["state"] = selected_state("B")
            node._sync_output(live["state"])
            self.release.set()
            await self.wait_until(lambda: bool(self.published))
        self.assertEqual(self.published[-1][1], [live["state"]["assets"][0]["path"]])

    async def test_failed_resolver_same_selection_can_retry(self):
        node, live = fake_node(selected_state())
        with patch.object(asset, "_resolve_selected_assets",
                          side_effect=RuntimeError("isolated resolver failure")):
            node._sync_output(live["state"])
            await self.wait_until(lambda: not node._hmb_selection_resolution_work["active"])
        self.release.set()
        node._sync_output(live["state"])
        await self.wait_until(lambda: bool(self.published))
        self.assertEqual(self.published[-1][1], [live["state"]["assets"][0]["path"]])

    async def test_pending_shot_readiness_rejects_previous_snapshot(self):
        old = selected_state("old")
        node, live = fake_node(old)
        self.release.set()
        node._sync_output(old, force=True)
        old_snapshot = node._hmb_shot_routing_snapshot(cached_only=True)
        self.release.clear()
        live["state"] = selected_state("new")
        node._sync_output(live["state"])
        with self.assertRaisesRegex(ValueError, "still preparing"):
            node._hmb_shot_routing_snapshot(cached_only=True)
        reads_before = len(self.reads)
        with self.assertRaisesRegex(ValueError, "still preparing") as caught:
            node._hmb_shot_routing_snapshot()
        self.assertTrue(caught.exception.hmb_image_asset_selection_preparing)
        catalog = node._hmb_shot_routing_catalog()
        self.assertEqual(catalog["shots"][0]["name"], live["state"]["shot_routing"]["shots"][0]["name"])
        self.assertEqual(len(self.reads), reads_before)
        self.release.set()
        await self.wait_until(lambda: len(self.published) > 1)
        new_snapshot = node._hmb_shot_routing_snapshot(cached_only=True)
        self.assertNotEqual(old_snapshot["metadata_sha256"], new_snapshot["metadata_sha256"])
        self.assertEqual(self.published[-1][1], [live["state"]["assets"][0]["path"]])

    async def test_deselect_while_verifying_never_republishes_old_image(self):
        node, live = fake_node(selected_state())
        node._sync_output(live["state"])
        await self.wait_until(self.entered.is_set)
        live["state"] = asset._normalize_state(asset._default_state())
        node._sync_output(live["state"])
        self.assertEqual(self.published[-1][1], [])
        self.release.set()
        await asyncio.sleep(0.04)
        self.assertTrue(all(media == [] for _, media in self.published))

    async def test_deleted_owner_never_publishes(self):
        node, live = fake_node(selected_state())
        node._sync_output(live["state"])
        await self.wait_until(self.entered.is_set)
        node._hmb_node_deleted = True
        self.release.set()
        await asyncio.sleep(0.04)
        self.assertEqual(self.published, [])

    async def test_force_execution_invalidates_older_background_verification(self):
        node, live = fake_node(selected_state())
        node._sync_output(live["state"])
        await self.wait_until(self.entered.is_set)
        node._sync_output(live["state"], force=True)
        count = len(self.published)
        self.assertEqual(count, 1)
        self.release.set()
        await asyncio.sleep(0.04)
        self.assertEqual(len(self.published), count)


if __name__ == "__main__":
    unittest.main(verbosity=2)
