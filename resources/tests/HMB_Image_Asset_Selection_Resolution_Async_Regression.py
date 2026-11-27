from __future__ import annotations

import asyncio
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4


ROOT = Path(os.environ.get("HMB_IMAGE_ASSET_TEST_ROOT", Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(ROOT))
SPEC = importlib.util.spec_from_file_location(
    "hmb_image_selection_resolution_async",
    os.environ.get("HMB_IMAGE_ASSET_TEST_MODULE", str(ROOT / "HMBImageAssetLibrary.py")),
)
assert SPEC is not None and SPEC.loader is not None
asset = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = asset
SPEC.loader.exec_module(asset)


def fixture_manifest(root):
    registered = {"ProjectA": ("A", "B", "C", "old", "new"), "ProjectB": ("B", "latest")}
    return {f"{name.casefold()}.png": {"asset_id": name} for name in registered[Path(root).name]}


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
    # Detached output-worker fixture: supply the fresh owner lease normally
    # established by the real constructor before accepting any state baseline.
    # Keep the real baseline/persistence implementation and all readiness checks.
    node._hmb_widget_runtime_lease = str(uuid4())
    state[asset.WIDGET_RUNTIME_LEASE_KEY] = node._hmb_widget_runtime_lease
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
        self.loop = asyncio.get_running_loop()
        self.previous_exception_handler = self.loop.get_exception_handler()
        self.callback_errors = []
        self.loop.set_exception_handler(lambda _loop, context: self.callback_errors.append(context))
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
            return fixture_manifest(path)

        self.patchers = [
            patch.object(asset, "_read_asset_manifest", read_manifest),
            patch.object(asset, "_verified_project_relative_path",
                         lambda row, state, records: row["relative_path"] if row["relative_path"].casefold() in records else ""),
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
        self.loop.set_exception_handler(self.previous_exception_handler)
        self.assertEqual(self.callback_errors, [], "Background callback raised unexpectedly")

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

    async def test_folder_refresh_verifies_only_new_shot_image_and_publishes_before_completion(self):
        node, live = fake_node(selected_state("A"))
        self.release.set()
        node._sync_output(live["state"])
        await self.wait_until(lambda: bool(self.published))
        second = selected_state("B")["assets"][0]
        second["selection_order"] = 2
        state = live["state"]
        state["assets"].append(second)
        for index in range(500):
            state["assets"].append(dict(second, asset_library_id=f"other-{index}",
                                        source_uid=f"project:other-{index}", selected=False, selection_order=0))
        shot = state["shot_routing"]["shots"][0]
        shot.update(selected_source_uids=["project:A", "project:B"], revision=shot["revision"] + 1)
        state["shot_routing"]["generation"] += 1
        state.update(scan_busy=True, scan_delayed=True)
        live["state"] = state = asset._normalize_state(state)
        node._hmb_scan_pending_key = "refresh:ProjectA:1"
        worked = []
        resolve = asset._resolve_selected_assets
        def trace_rows(view, *args, **kwargs):
            if kwargs.get("wait_for_catalog"):
                worked.append([row["source_uid"] for row in view["assets"]])
            return resolve(view, *args, **kwargs)
        with patch.object(asset, "_resolve_selected_assets", side_effect=trace_rows):
            node._sync_output(state)
            await self.wait_until(lambda: len(self.published[-1][1]) == 2)
        self.assertEqual(worked, [["project:B"]])
        self.assertEqual(self.published[-1][1], [state["assets"][0]["path"], second["path"]])
        self.assertTrue(live["state"]["scan_busy"])

    async def test_explicit_import_retry_uses_bounded_worker_without_host_unc_reads(self):
        state = selected_state("UNC")
        state["assets"][0].update(source_kind="user", source_uid="user:retry-unc",
            path="//synthetic.invalid/share/UNC.png", registered=False)
        state = asset._normalize_state(state)
        node, live = fake_node(state)
        key = asset._asset_resolution_cache_key(state["assets"][0], state, 0)
        node._hmb_image_bash_retry_cache_keys = {key}
        threads = []
        def slow_unc(value):
            threads.append(threading.get_ident())
            self.entered.set()
            assert threading.get_ident() != self.main_thread, "UNC retry blocked the host"
            assert self.release.wait(2), "Fixture UNC worker was not released"
            return str(value)
        before = deepcopy(live["state"])
        sentinel = {"old": "last-good"}
        node.parameter_output_values.update(sentinel)
        with patch.object(asset, "_resolved_media_value", side_effect=slow_unc):
            started = time.monotonic()
            node._sync_output(state)
            self.assertLess(time.monotonic() - started, .08)
            await self.wait_until(self.entered.is_set)
            for _ in range(5):
                node._sync_output(state)
            self.assertEqual(node.parameter_output_values, sentinel)
            self.assertEqual(len(threads), 1, "Duplicate Retry must reuse its active worker")
            self.release.set()
            await self.wait_until(lambda: bool(self.published))
        self.assertEqual(live["state"], before)
        self.assertEqual(self.published[-1][1], [state["assets"][0]["path"]])
        self.assertEqual(len(threads), 1)

    async def test_reselect_rechecks_previously_unavailable_same_uid(self):
        state = selected_state("A")
        node, live = fake_node(state)
        self.release.set()
        available = False
        checks = []
        def verify(row, _state, _records):
            checks.append(row["source_uid"])
            return row["relative_path"] if available else ""
        with patch.object(asset, "_verified_project_relative_path", side_effect=verify):
            node._sync_output(live["state"])
            await self.wait_until(lambda: bool(self.published))
            self.assertEqual(self.published[-1][1], [])
            first_checks = len(checks)
            node._sync_output(live["state"])
            self.assertEqual(len(checks), first_checks)
            available = True
            for selected in (False, True):
                latest = deepcopy(live["state"])
                latest[asset.UI_EDIT_REVISION_KEY] += 1
                latest["assets"][0].update(selected=selected, selection_order=int(selected))
                shot = latest["shot_routing"]["shots"][0]
                shot.update(selected_source_uids=["project:A"] if selected else [], revision=shot["revision"] + 1)
                latest["shot_routing"]["generation"] += 1
                live["state"] = asset._normalize_state(latest)
                node._sync_output(live["state"])
            await self.wait_until(lambda: self.published[-1][1] == [state["assets"][0]["path"]])
            self.assertEqual(len(checks), first_checks + 1)

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


class ReconnectedSiteExecutionTests(unittest.TestCase):
    def test_restored_selection_is_verified_on_first_run_and_explicit_edits_survive(self):
        from PIL import Image
        from _hmb_image_asset_sites import _EXECUTION_WORKSPACE

        with TemporaryDirectory(prefix="hmb-site-execution-") as temp:
            root = Path(temp)
            head = root / "projects" / "Example" / "Ai_Ct_image"
            shared = root / "shared"
            for folder, name in [(head, "Anchor"), (shared, "Reed")]:
                (folder / ".json").mkdir(parents=True)
                Image.new("RGB", (3, 3), "green").save(folder / f"{name}.png")
                record = {"path": f"{name}.png", "asset_id": name, "image_name": name,
                          "image_main_type": "Custom / Context", "image_sub_type": "Context"}
                (folder / ".json/hmb_image_assets.json").write_text(json.dumps({"assets": [record]}), encoding="utf-8")
            token = _EXECUTION_WORKSPACE.set(root)
            self.addCleanup(_EXECUTION_WORKSPACE.reset, token)
            with patch.object(asset, "_ASSET_CATALOG_INDEX_ROOT", root / "index"), \
                    patch.object(asset, "_LEGACY_CATALOG_INDEX_ROOT", root / "legacy"):
                profile = asset.save_site_settings(head, [{"id": "shared", "label": "Shared", "root": str(shared)}], "hq", "0")
                linked = asset._load_project_catalog(head, {})
                peer = next(row for row in linked["assets"] if row["asset_id"] == "Reed")
                anchor = next(row for row in linked["assets"] if row["asset_id"] == "Anchor")
                peer_uid, anchor_uid = peer["source_uid"], anchor["source_uid"]
                peer.update(selected=True, selection_order=1)
                linked["shot_routing"]["shots"][0]["selected_source_uids"] = [peer_uid]
                removed = asset.save_site_settings(head, [], "hq", profile["revision"])
                offline = asset._load_project_catalog(head, linked)
                self.assertIn(peer_uid, offline["site_selection_memory"])
                self.assertFalse(any(row["source_uid"] == peer_uid for row in offline["assets"]))
                # The catalog is already warm when the saved Shot's membership is restored.
                asset.save_site_settings(head, profile["links"], "hq", removed["revision"])
                reopened = asset._load_project_catalog(head, {})
                reopened["shot_routing"] = deepcopy(offline["shot_routing"])
                reopened["site_selection_memory"] = deepcopy(offline["site_selection_memory"])
                self.assertTrue(asset._state_catalog_is_current(reopened, head))

                def execute(state, expected_uids, expected_paths):
                    worker, media, revision, cache = asset.HMBImageAssetLibrary._prepare_execution_files(
                        state, str(head), None, {}, 0)
                    merged = asset._merge_async_scan_result_with_live_state(worker, state, state)
                    selected = [row for row in merged["assets"] if row["selected"]]
                    self.assertEqual([row["source_uid"] for row in selected], expected_uids)
                    self.assertEqual(merged["shot_routing"]["shots"][0]["selected_source_uids"], expected_uids)
                    for row in selected:
                        self.assertIn(asset._asset_resolution_cache_key(row, merged, revision), cache,
                                      "The detached worker must verify the restored row before publication")
                    result = asset._resolve_selected_assets(merged, media, resolution_cache=cache, import_revision=revision)
                    self.assertEqual(result["unresolved"], [])
                    self.assertEqual([Path(row["media"]).resolve() for row in result["resolved"]],
                                     [path.resolve() for path in expected_paths])
                    return merged

                current = execute(reopened, [peer_uid], [shared / "Reed.png"])
                self.assertFalse(current["site_selection_memory"])
                # Press X on the recovered image and select a different one in the same Shot.
                toggles = """
                    import { readFileSync } from 'node:fs';
                    const { hmbToggleImageAssetShotAsset } = await import(process.argv[1]);
                    const state = JSON.parse(readFileSync(0, 'utf8'));
                    for (const uid of process.argv.slice(2)) {
                        if (!hmbToggleImageAssetShotAsset(state, state.shot_routing.active_shot_uuid, uid))
                            throw new Error('Shot selection toggle failed');
                    }
                    process.stdout.write(JSON.stringify(state));
                """
                widget_uri = (ROOT / "widgets/HMBImageAssetLibraryWidget.js").as_uri()
                changed = subprocess.run(["node", "--input-type=module", "-e", toggles, widget_uri, peer_uid, anchor_uid],
                                         input=json.dumps(current), text=True, encoding="utf-8", capture_output=True,
                                         check=True, timeout=20)
                execute(asset._normalize_state(json.loads(changed.stdout)), [anchor_uid], [head / "Anchor.png"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
