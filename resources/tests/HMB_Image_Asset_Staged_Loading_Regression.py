from __future__ import annotations

import asyncio
from copy import deepcopy
from io import BytesIO
import importlib.util
import inspect
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import types
from types import SimpleNamespace
import uuid


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "HMBImageAssetLibrary.py"
spec = importlib.util.spec_from_file_location(
    "hmb_image_asset_staged_loading_regression",
    MODULE_PATH,
)
assert spec is not None and spec.loader is not None
asset_library = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = asset_library
spec.loader.exec_module(asset_library)

from PIL import Image


assert "_scan_project_assets(" not in inspect.getsource(
    asset_library._apply_asset_registration
)


def png_bytes(size: tuple[int, int], color: tuple[int, int, int]) -> bytes:
    output = BytesIO()
    Image.new("RGB", size, color).save(output, format="PNG")
    return output.getvalue()


temporary = Path(tempfile.mkdtemp(prefix="hmb_image_staged_loading_"))
default_cache_root = asset_library._ASSET_THUMBNAIL_CACHE_ROOT
if os.environ.get("LOCALAPPDATA") and not os.environ.get(
    "HMB_IMAGE_THUMBNAIL_CACHE"
):
    assert default_cache_root == (
        Path(os.environ["LOCALAPPDATA"])
        / "HMB_GP_Production"
        / "cache"
        / "image_thumbnails"
    )
asset_library._ASSET_THUMBNAIL_CACHE_ROOT = temporary / "runtime-cache"
try:
    catalog_root = temporary / "Projects"
    project_root = catalog_root / "ProjectA"
    asset_folder = project_root / "Assets"
    asset_folder.mkdir(parents=True)
    hero_path = asset_folder / "Hero.png"
    sidekick_path = asset_folder / "Sidekick.png"
    hero_path.write_bytes(png_bytes((12, 8), (210, 20, 70)))
    sidekick_path.write_bytes(png_bytes((9, 11), (20, 90, 210)))

    # A cold project scan is metadata-first: header dimensions remain part of
    # the existing output contract, but no thumbnail decoder/publisher runs.
    original_thumbnail_url = asset_library._asset_thumbnail_url

    def forbidden_thumbnail(*_args, **_kwargs):
        raise AssertionError("cold metadata scan decoded/published a thumbnail")

    asset_library._asset_thumbnail_url = forbidden_thumbnail
    try:
        cold_scan = asset_library._scan_project_assets(project_root)
    finally:
        asset_library._asset_thumbnail_url = original_thumbnail_url
    assert len(cold_scan["assets"]) == 2
    assert all(not item["thumbnail_url"] for item in cold_scan["assets"])
    assert {(item["width"], item["height"]) for item in cold_scan["assets"]} == {
        (12, 8),
        (9, 11),
    }
    assert all(len(item["media_signature"]) == 64 for item in cold_scan["assets"])

    # Refresh merges unchanged hydrated presentation data by path+size+mtime,
    # and invalidates only the file whose identity changed.
    previous = asset_library._merge_scan_with_state(
        cold_scan,
        asset_library._default_state(),
    )
    previous["assets"][0]["thumbnail_url"] = "memory://keep-unchanged"
    asset_library._ASSET_THUMBNAIL_URLS[
        previous["assets"][0]["media_signature"]
    ] = "memory://keep-unchanged"
    previous = asset_library._normalize_state(previous)
    unchanged = asset_library._merge_scan_with_state(
        asset_library._scan_project_assets(project_root),
        previous,
    )
    assert unchanged["assets"][0]["thumbnail_url"] == "memory://keep-unchanged"
    asset_library._ASSET_THUMBNAIL_URLS.clear()
    restarted = asset_library._merge_scan_with_state(
        asset_library._scan_project_assets(project_root),
        unchanged,
    )
    assert restarted["assets"][0]["thumbnail_url"] == ""
    changed_path = Path(unchanged["assets"][0]["path"])
    changed_path.write_bytes(png_bytes((21, 7), (15, 150, 80)))
    changed = asset_library._merge_scan_with_state(
        asset_library._scan_project_assets(project_root),
        unchanged,
    )
    changed_asset = next(
        item
        for item in changed["assets"]
        if Path(item["path"]).resolve() == changed_path.resolve()
    )
    assert changed_asset["thumbnail_url"] == ""
    assert (changed_asset["width"], changed_asset["height"]) == (21, 7)

    # A completed scan may be projected into a local, non-authoritative index.
    # Reopening the same project must consume that index without walking the
    # project again, while every identity/corruption boundary fails closed.
    original_index_root = asset_library._ASSET_CATALOG_INDEX_ROOT
    index_root = temporary / "catalog-index"
    asset_library._ASSET_CATALOG_INDEX_ROOT = index_root
    indexed_state = asset_library._merge_scan_with_state(
        asset_library._scan_project_assets(project_root),
        asset_library._default_state(),
    )
    indexed_state["catalog_root"] = str(catalog_root).replace("\\", "/")
    indexed_state["projects"] = [
        {
            "project_id": indexed_state["project_id"],
            "project_uid": indexed_state["project_uid"],
            "path": indexed_state["project_root"],
            "name": "ProjectA",
        }
    ]
    indexed_state = asset_library._normalize_state(indexed_state)
    try:
        asset_library._write_catalog_index(indexed_state)
        index_path = asset_library._catalog_index_path(project_root)
        assert index_path.is_file()
        assert index_path.resolve().is_relative_to(index_root.resolve())
        assert not any(project_root.glob("*.hmb-image-asset-catalog-index*"))

        original_scan_for_index = asset_library._scan_project_assets
        asset_library._scan_project_assets = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("A valid restart index performed a full project scan.")
        )
        try:
            reopened = asset_library._read_catalog_index(
                project_root,
                indexed_state,
            )
        finally:
            asset_library._scan_project_assets = original_scan_for_index
        assert reopened is not None
        assert reopened["project_uid"] == indexed_state["project_uid"]
        assert [item["relative_path"] for item in reopened["assets"]] == [
            item["relative_path"]
            for item in indexed_state["assets"]
            if item["source_kind"] == "project"
        ]
        assert all(not item["thumbnail_url"] for item in reopened["assets"])

        valid_index_text = index_path.read_text(encoding="utf-8")

        def rejected_index(mutator):
            raw = __import__("json").loads(valid_index_text)
            mutator(raw)
            index_path.write_text(
                __import__("json").dumps(raw),
                encoding="utf-8",
            )
            assert asset_library._read_catalog_index(
                project_root,
                indexed_state,
            ) is None

        rejected_index(lambda raw: raw.__setitem__("project_uid", "wrong-project"))
        rejected_index(lambda raw: raw.__setitem__("manifest_signature", "0" * 64))
        rejected_index(lambda raw: raw.__setitem__("project_root", str(temporary / "other")))

        def inject_traversal(raw):
            raw["assets"][0]["relative_path"] = "../escape.png"

        rejected_index(inject_traversal)
        index_path.write_text("{not-json", encoding="utf-8")
        assert asset_library._read_catalog_index(
            project_root,
            indexed_state,
        ) is None

        # Refresh remains the explicit full-rescan authority; the index is
        # only a restart/process accelerator and cannot replace this branch.
        apply_source = inspect.getsource(
            asset_library.HMBImageAssetLibrary._apply_widget_state
        )
        refresh_branch = apply_source[apply_source.index("if refresh_requested:") :]
        refresh_branch = refresh_branch[: refresh_branch.index("requested_path =")]
        assert "_load_project_catalog(" in refresh_branch
        assert "use_shared_cache=False" in refresh_branch
        assert "_read_catalog_index" not in refresh_branch
        process_source = inspect.getsource(asset_library.HMBImageAssetLibrary.process)
        assert process_source.index("_read_catalog_index(") < process_source.index(
            "self._load_catalog("
        )

        # PROJECT_ROOT remains authoritative even when a host changes it
        # programmatically without delivering the retained widget callback.
        # Neither an otherwise-current state nor its local index may keep the
        # node attached to the previous catalog.
        requested_process_root = str(temporary / "ReplacementProjects")
        process_current = deepcopy(indexed_state)
        # Reproduce the async root-change busy snapshot: catalog_root already
        # reflects the new picker value while project_root/assets still belong
        # to the previous project.
        process_current["catalog_root"] = requested_process_root.replace("\\", "/")
        process_loads = []

        class ProcessRootProbe:
            def _consume_pending_catalog_scan_result(self):
                return False

            def _consume_pending_thumbnail_result(self):
                return False

            def _ensure_parameters(self):
                return None

            def _current_state(self):
                return process_current

            def _load_catalog(self, root_value):
                process_loads.append(root_value)
                loaded = deepcopy(process_current)
                loaded["catalog_root"] = str(root_value).replace("\\", "/")
                return loaded

            def _sync_output(self, state, *, force=False):
                assert force is True
                return state

            def _reconcile_hmb_shot_routing(self, _catalog_identity=""):
                return None

        original_parameter_reader = asset_library._get_parameter_raw
        original_current_check = asset_library._state_catalog_is_current
        original_index_reader = asset_library._read_catalog_index
        asset_library._get_parameter_raw = lambda _node, name: (
            requested_process_root
            if name == asset_library.PROJECT_ROOT_PARAMETER
            else None
        )
        asset_library._state_catalog_is_current = lambda _state: True
        asset_library._read_catalog_index = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("A stale-root catalog index was consulted by process().")
        )
        try:
            asset_library.HMBImageAssetLibrary.process(ProcessRootProbe())
        finally:
            asset_library._get_parameter_raw = original_parameter_reader
            asset_library._state_catalog_is_current = original_current_check
            asset_library._read_catalog_index = original_index_reader
        assert process_loads == [requested_process_root]
    finally:
        asset_library._ASSET_CATALOG_INDEX_ROOT = original_index_root

    # The local cache survives the process-memory URL map and remains bounded.
    cache_root = temporary / "thumbnail-cache"
    original_cache_root = asset_library._ASSET_THUMBNAIL_CACHE_ROOT
    original_cache_limit = asset_library._ASSET_THUMBNAIL_CACHE_MAX_ENTRIES
    original_publisher = asset_library._publish_thumbnail_payload
    original_generator = asset_library._generate_thumbnail_payload
    asset_library._ASSET_THUMBNAIL_CACHE_ROOT = cache_root
    asset_library._ASSET_THUMBNAIL_CACHE_MAX_ENTRIES = 2
    asset_library._ASSET_THUMBNAIL_URLS.clear()
    generated = []

    def counted_generator(path):
        generated.append(Path(path))
        return original_generator(path)

    asset_library._generate_thumbnail_payload = counted_generator
    asset_library._publish_thumbnail_payload = (
        lambda _payload, _extension, _asset_id, signature: f"memory://{signature}"
    )
    try:
        first_url = asset_library._asset_thumbnail_url(hero_path, "hero")
        assert first_url.startswith("memory://")
        assert len(generated) == 1
        asset_library._ASSET_THUMBNAIL_URLS.clear()

        def cache_miss_is_failure(_path):
            raise AssertionError("persistent thumbnail cache was not reused")

        asset_library._generate_thumbnail_payload = cache_miss_is_failure
        second_url = asset_library._asset_thumbnail_url(hero_path, "hero")
        assert second_url == first_url

        asset_library._generate_thumbnail_payload = counted_generator
        hero_path.write_bytes(png_bytes((22, 7), (16, 151, 81)))
        changed_url = asset_library._asset_thumbnail_url(hero_path, "hero")
        assert changed_url != first_url
        assert len(generated) == 2
        for index in range(3):
            path = asset_folder / f"Cache{index}.png"
            path.write_bytes(png_bytes((7 + index, 6), (20 * index, 30, 40)))
            assert asset_library._asset_thumbnail_url(path, f"cache-{index}")
        assert len(list(cache_root.glob("*.json"))) <= 2
        assert len(asset_library._ASSET_THUMBNAIL_URLS) <= 2
    finally:
        asset_library._ASSET_THUMBNAIL_CACHE_ROOT = original_cache_root
        asset_library._ASSET_THUMBNAIL_CACHE_MAX_ENTRIES = original_cache_limit
        asset_library._publish_thumbnail_payload = original_publisher
        asset_library._generate_thumbnail_payload = original_generator
        asset_library._ASSET_THUMBNAIL_URLS.clear()

    # Register one project asset, then prove bounded hydration patches only its
    # thumbnail_url. Width/height, outputs, selection, Shot order, and scan/UI
    # revisions remain byte-for-byte stable.
    hero_relative = hero_path.relative_to(project_root).as_posix()
    asset_library._write_asset_manifest_record(
        project_root,
        {
            "path": hero_relative,
            "asset_id": "Hero",
            "image_name": "Hero",
            "image_main_type": "Character",
            "image_sub_type": "Full Appearance",
            "source_type": "Character Appearance",
            "custom_source_type": "",
            "scope": "Full body / full appearance",
        },
    )
    hydrated_base = asset_library._merge_scan_with_state(
        asset_library._scan_project_assets(project_root),
        asset_library._default_state(),
    )
    hero = next(item for item in hydrated_base["assets"] if item["asset_id"] == "Hero")
    hero["selected"] = True
    hero["selection_order"] = 1
    hydrated_base[asset_library.UI_EDIT_REVISION_KEY] = 11
    hydrated_base = asset_library._normalize_state(hydrated_base)
    hero = next(item for item in hydrated_base["assets"] if item["asset_id"] == "Hero")
    request_ids = [hero["asset_library_id"]] * 3 + [
        f"missing-{index}" for index in range(100)
    ]
    capped = asset_library._normalize_thumbnail_request(
        {
            "request_id": "cap",
            "project_uid": hydrated_base["project_uid"],
            "manifest_signature": hydrated_base["manifest_signature"],
            "scan_revision": hydrated_base["scan_revision"],
            "asset_library_ids": request_ids,
        }
    )
    assert len(capped["asset_library_ids"]) == 64
    assert capped["asset_library_ids"].count(hero["asset_library_id"]) == 1

    hydration_request = {
        "request_id": "visible-selected-one",
        "project_uid": hydrated_base["project_uid"],
        "manifest_signature": hydrated_base["manifest_signature"],
        "scan_revision": hydrated_base["scan_revision"],
        "asset_library_ids": [hero["asset_library_id"]],
    }
    before_fingerprint = asset_library._project_output_fingerprint(hydrated_base)
    before_dimensions = (hero["width"], hero["height"])
    before_shot_routing = deepcopy(hydrated_base["shot_routing"])
    before_selection = (hero["selected"], hero["selection_order"])
    asset_library._asset_thumbnail_url = lambda _path, asset_id: f"memory://{asset_id}"
    try:
        hydration_result = asset_library._hydrate_asset_thumbnails(
            hydrated_base,
            hydration_request,
        )
    finally:
        asset_library._asset_thumbnail_url = original_thumbnail_url
    hydrated_hero = next(
        item for item in hydration_result["assets"] if item["asset_id"] == "Hero"
    )
    assert hydrated_hero["thumbnail_url"].startswith("memory://")
    assert (hydrated_hero["width"], hydrated_hero["height"]) == before_dimensions
    assert (hydrated_hero["selected"], hydrated_hero["selection_order"]) == before_selection
    assert hydration_result["scan_revision"] == hydrated_base["scan_revision"]
    assert hydration_result[asset_library.UI_EDIT_REVISION_KEY] == 11
    assert hydration_result["shot_routing"] == before_shot_routing
    assert asset_library._project_output_fingerprint(hydration_result) == before_fingerprint

    # A worker result merges into current UI edits without owning any editable
    # field. A newer scan context rejects the same stale thumbnail result.
    live = deepcopy(hydrated_base)
    live["search"] = "newer live edit"
    live[asset_library.UI_EDIT_REVISION_KEY] = 12
    live = asset_library._normalize_state(live)
    merged = asset_library._merge_async_thumbnail_result_with_live_state(
        hydration_result,
        hydrated_base,
        live,
        hydration_request,
    )
    merged_hero = next(item for item in merged["assets"] if item["asset_id"] == "Hero")
    assert merged["search"] == "newer live edit"
    assert merged[asset_library.UI_EDIT_REVISION_KEY] == 12
    assert merged["shot_routing"] == live["shot_routing"]
    assert merged_hero["thumbnail_url"].startswith("memory://")

    # The compact worker pipeline receives canonical state/request objects.
    # Its bounded thumbnail mutation and live merge must not re-normalize the
    # complete O(N) catalog at every internal stage.
    original_state_normalizer = asset_library._normalize_state
    normalized_pipeline_calls = []

    def counted_state_normalizer(value):
        normalized_pipeline_calls.append(value)
        return original_state_normalizer(value)

    asset_library._normalize_state = counted_state_normalizer
    asset_library._asset_thumbnail_url = (
        lambda _path, asset_id: f"memory://normalized/{asset_id}"
    )
    try:
        normalized_hydration = asset_library._hydrate_asset_thumbnails(
            hydrated_base,
            hydration_request,
            normalized=True,
            request_normalized=True,
        )
        normalized_merge = asset_library._merge_async_thumbnail_result_with_live_state(
            normalized_hydration,
            hydrated_base,
            live,
            hydration_request,
            inputs_normalized=True,
            request_normalized=True,
        )
    finally:
        asset_library._normalize_state = original_state_normalizer
        asset_library._asset_thumbnail_url = original_thumbnail_url
    assert normalized_pipeline_calls == []
    assert next(
        item for item in normalized_merge["assets"] if item["asset_id"] == "Hero"
    )["thumbnail_url"].startswith("memory://normalized/")

    mismatched_result = deepcopy(hydration_result)
    mismatched_result["thumbnail_result"]["request_id"] = "another-worker"
    rejected_mismatch = asset_library._merge_async_thumbnail_result_with_live_state(
        mismatched_result,
        hydrated_base,
        live,
        hydration_request,
    )
    rejected_hero = next(
        item for item in rejected_mismatch["assets"] if item["asset_id"] == "Hero"
    )
    assert rejected_hero["thumbnail_url"] == ""
    assert rejected_mismatch["thumbnail_result"] == live["thumbnail_result"]

    newer_scan = deepcopy(live)
    newer_scan["scan_revision"] += 1
    newer_scan = asset_library._normalize_state(newer_scan)
    stale = asset_library._merge_async_thumbnail_result_with_live_state(
        hydration_result,
        hydrated_base,
        newer_scan,
        hydration_request,
    )
    stale_hero = next(item for item in stale["assets"] if item["asset_id"] == "Hero")
    assert stale_hero["thumbnail_url"] == ""
    assert stale["shot_routing"] == newer_scan["shot_routing"]
    assert hero["asset_library_id"] in stale["thumbnail_result"][
        "failed_asset_library_ids"
    ]

    # Persistent-cache maintenance is amortized over one hydration batch.
    # Three misses prune once, warm hits do not prune, and nested/exception
    # paths always return the global defer counter to a safe value.
    batch_cache_root = temporary / "batch-thumbnail-cache"
    original_batch_cache_root = asset_library._ASSET_THUMBNAIL_CACHE_ROOT
    original_batch_publisher = asset_library._publish_thumbnail_payload
    original_batch_prune = asset_library._prune_persistent_thumbnail_cache
    original_batch_generator = asset_library._generate_thumbnail_payload
    original_defer_count = asset_library._ASSET_THUMBNAIL_CACHE_DEFER_COUNT
    original_prune_pending = asset_library._ASSET_THUMBNAIL_CACHE_PRUNE_PENDING
    batch_paths = []
    for index in range(3):
        batch_path = asset_folder / f"BatchPrune{index}.png"
        batch_path.write_bytes(png_bytes((14 + index, 10), (40, 60 + index, 90)))
        batch_paths.append(batch_path)
    batch_state = asset_library._merge_scan_with_state(
        asset_library._scan_project_assets(project_root),
        asset_library._default_state(),
    )
    batch_by_path = {
        Path(item["path"]).resolve(): item
        for item in batch_state["assets"]
    }
    batch_ids = [batch_by_path[path.resolve()]["asset_library_id"] for path in batch_paths]
    batch_request = {
        "request_id": "three-cache-misses",
        "project_uid": batch_state["project_uid"],
        "manifest_signature": batch_state["manifest_signature"],
        "scan_revision": batch_state["scan_revision"],
        "asset_library_ids": batch_ids,
    }
    prune_calls = []
    generate_calls = []

    def counted_batch_prune(root):
        prune_calls.append(Path(root))
        return original_batch_prune(root)

    def counted_batch_generator(path):
        generate_calls.append(Path(path).resolve())
        return original_batch_generator(path)

    asset_library._ASSET_THUMBNAIL_CACHE_ROOT = batch_cache_root
    asset_library._ASSET_THUMBNAIL_CACHE_DEFER_COUNT = 0
    asset_library._ASSET_THUMBNAIL_CACHE_PRUNE_PENDING = False
    asset_library._ASSET_THUMBNAIL_URLS.clear()
    asset_library._prune_persistent_thumbnail_cache = counted_batch_prune
    asset_library._generate_thumbnail_payload = counted_batch_generator
    asset_library._publish_thumbnail_payload = (
        lambda _payload, _extension, _asset_id, signature: f"memory://{signature}"
    )
    try:
        batch_result = asset_library._hydrate_asset_thumbnails(
            batch_state,
            batch_request,
        )
        assert sorted(batch_result["thumbnail_result"]["completed_asset_library_ids"]) == sorted(batch_ids)
        assert sorted(generate_calls) == sorted(path.resolve() for path in batch_paths)
        assert len(prune_calls) == 1
        assert asset_library._ASSET_THUMBNAIL_CACHE_DEFER_COUNT == 0
        assert asset_library._ASSET_THUMBNAIL_CACHE_PRUNE_PENDING is False

        asset_library._ASSET_THUMBNAIL_URLS.clear()
        generate_calls.clear()
        prune_calls.clear()
        warm_request = {**batch_request, "request_id": "three-warm-hits"}
        warm_result = asset_library._hydrate_asset_thumbnails(
            batch_state,
            warm_request,
        )
        assert sorted(warm_result["thumbnail_result"]["completed_asset_library_ids"]) == sorted(batch_ids)
        assert generate_calls == []
        assert prune_calls == []
        assert asset_library._ASSET_THUMBNAIL_CACHE_DEFER_COUNT == 0

        nested_path = asset_folder / "NestedBatch.png"
        nested_path.write_bytes(png_bytes((19, 13), (81, 42, 23)))
        nested_state = asset_library._merge_scan_with_state(
            asset_library._scan_project_assets(project_root),
            asset_library._default_state(),
        )
        nested_asset = next(
            item
            for item in nested_state["assets"]
            if Path(item["path"]).resolve() == nested_path.resolve()
        )
        nested_request = {
            "request_id": "nested-batch",
            "project_uid": nested_state["project_uid"],
            "manifest_signature": nested_state["manifest_signature"],
            "scan_revision": nested_state["scan_revision"],
            "asset_library_ids": [nested_asset["asset_library_id"]],
        }
        prune_calls.clear()
        asset_library._ASSET_THUMBNAIL_CACHE_DEFER_COUNT = 1
        nested_result = asset_library._hydrate_asset_thumbnails(
            nested_state,
            nested_request,
        )
        assert nested_result["thumbnail_result"]["completed_asset_library_ids"] == [
            nested_asset["asset_library_id"]
        ]
        assert asset_library._ASSET_THUMBNAIL_CACHE_DEFER_COUNT == 1
        assert asset_library._ASSET_THUMBNAIL_CACHE_PRUNE_PENDING is True
        assert prune_calls == []
        asset_library._ASSET_THUMBNAIL_CACHE_DEFER_COUNT = 0
        asset_library._flush_persistent_thumbnail_cache_prune()
        assert len(prune_calls) == 1
        assert asset_library._ASSET_THUMBNAIL_CACHE_PRUNE_PENDING is False

        failing_thumbnail = asset_library._asset_thumbnail_url

        def raised_thumbnail(*_args, **_kwargs):
            raise RuntimeError("simulated thumbnail failure")

        asset_library._asset_thumbnail_url = raised_thumbnail
        try:
            failed_batch = asset_library._hydrate_asset_thumbnails(
                nested_state,
                {**nested_request, "request_id": "exception-batch"},
            )
        finally:
            asset_library._asset_thumbnail_url = failing_thumbnail
        assert failed_batch["thumbnail_result"]["completed_asset_library_ids"] == []
        assert failed_batch["thumbnail_result"]["failed_asset_library_ids"] == [
            nested_asset["asset_library_id"]
        ]
        assert asset_library._ASSET_THUMBNAIL_CACHE_DEFER_COUNT == 0
    finally:
        asset_library._ASSET_THUMBNAIL_CACHE_ROOT = original_batch_cache_root
        asset_library._publish_thumbnail_payload = original_batch_publisher
        asset_library._prune_persistent_thumbnail_cache = original_batch_prune
        asset_library._generate_thumbnail_payload = original_batch_generator
        asset_library._ASSET_THUMBNAIL_CACHE_DEFER_COUNT = original_defer_count
        asset_library._ASSET_THUMBNAIL_CACHE_PRUNE_PENDING = original_prune_pending
        asset_library._ASSET_THUMBNAIL_URLS.clear()

    # The node-level contract acknowledges immediately, completes off-thread,
    # and publishes through the retained-mode consumer without a catalog scan.
    node = object.__new__(asset_library.HMBImageAssetLibrary)
    node_live = {"state": deepcopy(hydrated_base)}
    node._hmb_manifest_poll_received = False
    node._hmb_manifest_poll_pending = False
    node._hmb_refresh_revision = hydrated_base["refresh_revision"]
    node._hmb_import_media_by_uid = {}
    node._scan_owner_is_current = lambda: True
    node._current_state = lambda: node_live["state"]
    node.get_parameter_value = lambda name: (
        hydrated_base["catalog_root"]
        if name == asset_library.PROJECT_ROOT_PARAMETER
        else []
    )

    node_publications = []

    def publish_node_state(value, *, normalized=False):
        normalized_value = (
            value if normalized else asset_library._normalize_state(value)
        )
        node_live["state"] = normalized_value
        node_publications.append(normalized_value)
        return normalized_value

    node._publish_state = publish_node_state
    requested_state = deepcopy(hydrated_base)
    requested_state["thumbnail_request"] = hydration_request
    asset_library._asset_thumbnail_url = lambda _path, asset_id: f"memory://{asset_id}"
    try:
        pending = node._apply_widget_state(requested_state)
        assert pending["thumbnail_busy"] is True
        assert pending["thumbnail_request"] == {}
        assert node_publications == []
        worker = node._hmb_thumbnail_thread
        assert worker is not None
        worker.join(timeout=5.0)
        assert worker.is_alive() is False
        assert node._consume_pending_thumbnail_result() is True
    finally:
        asset_library._asset_thumbnail_url = original_thumbnail_url
    node_hero = next(
        item for item in node_live["state"]["assets"] if item["asset_id"] == "Hero"
    )
    assert node_live["state"]["thumbnail_busy"] is False
    assert node_hero["thumbnail_url"].startswith("memory://")
    assert len(node_publications) == 1

    # The hidden bridge owns compact thumbnail request/result traffic. Its
    # worker completion updates the canonical backend state silently and emits
    # only the bounded result envelope; the full widget publisher is not used.
    bridge_node = object.__new__(asset_library.HMBImageAssetLibrary)
    bridge_live = {"state": deepcopy(hydrated_base)}
    bridge_results = []
    bridge_silent_stores = []
    bridge_node._current_state = lambda: bridge_live["state"]
    bridge_node._scan_owner_is_current = lambda: True
    bridge_node._hmb_import_media_by_uid = {}
    bridge_node._hmb_manifest_poll_received = False
    bridge_node._hmb_manifest_poll_pending = False
    bridge_node._hmb_refresh_revision = hydrated_base["refresh_revision"]
    bridge_node._publish_state = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("Compact thumbnail completion used the full widget publisher.")
    )
    bridge_node._accept_normalized_widget_state_baseline = lambda *_args, **_kwargs: None

    def bridge_set_parameter(name, value, *args, **kwargs):
        assert name == asset_library.WIDGET_STATE_PARAMETER
        assert kwargs.get("emit_change") is False
        assert kwargs.get("skip_before_value_set") is True
        normalized_value = asset_library._normalize_state(value)
        bridge_live["state"] = normalized_value
        bridge_silent_stores.append(normalized_value)

    bridge_node.set_parameter_value = bridge_set_parameter
    bridge_node._set_thumbnail_bridge_value = lambda value: bridge_results.append(
        asset_library._normalize_thumbnail_bridge(value)
    )
    runtime_id = bridge_node._thumbnail_runtime_id(bridge_live["state"])
    bridge_request = {
        "schema": asset_library.THUMBNAIL_BRIDGE_SCHEMA,
        "version": asset_library.THUMBNAIL_BRIDGE_VERSION,
        "runtime_instance_id": runtime_id,
        "operation": "hydrate",
        "phase": "request",
        "request_id": "compact-bridge-request",
        "project_uid": hydrated_base["project_uid"],
        "manifest_signature": hydrated_base["manifest_signature"],
        "scan_revision": hydrated_base["scan_revision"],
        "asset_library_ids": [hero["asset_library_id"]],
    }
    # Path-derived identities are allowed to exceed 128 characters throughout
    # the canonical contract. The compact bridge must preserve them verbatim
    # in both directions or the generated thumbnail can never match its card.
    long_bridge_id = "asset/" + ("long-segment-" * 24) + "image.png"
    assert len(long_bridge_id) > 128
    normalized_long_request = asset_library._normalize_thumbnail_bridge(
        {**bridge_request, "asset_library_ids": [long_bridge_id]}
    )
    assert normalized_long_request["asset_library_ids"] == [long_bridge_id]
    normalized_long_result = asset_library._normalize_thumbnail_bridge(
        {
            **bridge_request,
            "phase": "result",
            "completed_assets": [
                {
                    "asset_library_id": long_bridge_id,
                    "source_uid": "project:" + long_bridge_id,
                    "media_signature": "a" * 64,
                    "thumbnail_url": "https://static.invalid/long.webp",
                }
            ],
            "failed_asset_library_ids": [long_bridge_id],
        }
    )
    assert normalized_long_result["completed_assets"][0]["asset_library_id"] == (
        long_bridge_id
    )
    assert normalized_long_result["failed_asset_library_ids"] == [long_bridge_id]
    asset_library._asset_thumbnail_url = lambda _path, asset_id: f"memory://bridge/{asset_id}"
    try:
        bridge_node._apply_thumbnail_bridge_request(bridge_request)
        bridge_thread = bridge_node._hmb_thumbnail_thread
        assert bridge_thread is not None
        bridge_thread.join(timeout=5.0)
        assert bridge_thread.is_alive() is False
        assert bridge_node._consume_pending_thumbnail_result() is True
    finally:
        asset_library._asset_thumbnail_url = original_thumbnail_url
    assert len(bridge_silent_stores) == 1
    bridge_hero = next(
        item
        for item in bridge_live["state"]["assets"]
        if item["asset_library_id"] == hero["asset_library_id"]
    )
    assert bridge_hero["thumbnail_url"].startswith("memory://bridge/")
    assert len(bridge_results) == 1
    bridge_result = bridge_results[0]
    assert bridge_result["operation"] == "hydrate"
    assert bridge_result["phase"] == "result"
    assert bridge_result["request_id"] == bridge_request["request_id"]
    assert bridge_result["completed_assets"] == [
        {
            "asset_library_id": hero["asset_library_id"],
            "source_uid": bridge_hero["source_uid"],
            "media_signature": bridge_hero["media_signature"],
            "thumbnail_url": bridge_hero["thumbnail_url"],
        }
    ]
    assert len(asset_library._json_text(bridge_result)) < 8192

    # The browser watchdog may repeat the exact request after a lost response.
    # Re-publish the accepted result without starting a second decoder worker.
    idempotent_generation = bridge_node._hmb_thumbnail_generation
    idempotent_thread = bridge_node._hmb_thumbnail_thread
    idempotent_results = len(bridge_results)
    bridge_node._apply_thumbnail_bridge_request(bridge_request)
    assert bridge_node._hmb_thumbnail_generation == idempotent_generation
    assert bridge_node._hmb_thumbnail_thread is idempotent_thread
    assert len(bridge_results) == idempotent_results + 1
    assert bridge_results[-1]["request_id"] == bridge_request["request_id"]

    stale_generation = bridge_node._hmb_thumbnail_generation
    stale_store_count = len(bridge_silent_stores)
    stale_result_count = len(bridge_results)
    for stale_request in (
        {**bridge_request, "request_id": "wrong-runtime", "runtime_instance_id": "stale"},
        {**bridge_request, "request_id": "wrong-project", "project_uid": "stale"},
        {**bridge_request, "request_id": "wrong-manifest", "manifest_signature": "stale"},
        {**bridge_request, "request_id": "wrong-scan", "scan_revision": hydrated_base["scan_revision"] + 1},
    ):
        bridge_node._apply_thumbnail_bridge_request(stale_request)
    assert bridge_node._hmb_thumbnail_generation == stale_generation
    assert len(bridge_silent_stores) == stale_store_count
    assert len(bridge_results) == stale_result_count

    # A compact remount can replace request A with request B while A is still
    # decoding. The backend must coalesce and run B after A; otherwise the
    # browser rejects A by request ID and waits forever for a B result.
    queued_started = threading.Event()
    queued_release = threading.Event()
    queued_hydrator = asset_library._hydrate_asset_thumbnails
    queued_calls = []

    def blocking_bridge_hydrator(state_value, request_value, **kwargs):
        queued_calls.append(request_value["request_id"])
        queued_started.set()
        assert queued_release.wait(timeout=5.0)
        return queued_hydrator(state_value, request_value, **kwargs)

    bridge_request_a = {**bridge_request, "request_id": "compact-flight-a"}
    bridge_request_b = {**bridge_request, "request_id": "compact-flight-b"}
    asset_library._hydrate_asset_thumbnails = blocking_bridge_hydrator
    asset_library._asset_thumbnail_url = (
        lambda _path, asset_id: f"memory://queued/{asset_id}"
    )
    try:
        bridge_node._apply_thumbnail_bridge_request(bridge_request_a)
        assert queued_started.wait(timeout=2.0)
        bridge_thread_a = bridge_node._hmb_thumbnail_thread
        bridge_node._apply_thumbnail_bridge_request(bridge_request_b)
        assert bridge_node._hmb_thumbnail_queued_bridge_request["request_id"] == (
            bridge_request_b["request_id"]
        )
        queued_release.set()
        bridge_thread_a.join(timeout=5.0)
        assert bridge_node._consume_pending_thumbnail_result() is True
        bridge_thread_b = bridge_node._hmb_thumbnail_thread
        assert bridge_thread_b is not None and bridge_thread_b is not bridge_thread_a
        bridge_thread_b.join(timeout=5.0)
        assert bridge_node._consume_pending_thumbnail_result() is True
    finally:
        queued_release.set()
        asset_library._hydrate_asset_thumbnails = queued_hydrator
        asset_library._asset_thumbnail_url = original_thumbnail_url
    assert queued_calls == ["compact-flight-a", "compact-flight-b"]
    assert [item["request_id"] for item in bridge_results[-2:]] == [
        "compact-flight-a",
        "compact-flight-b",
    ]
    assert bridge_node._hmb_thumbnail_queued_bridge_request is None

    # Worker completion belongs on the retained-mode/event-manager loop. Cover
    # the four host lifecycle paths that a synchronous pending-only test cannot:
    # a live loop, late loop bootstrap, one failed publish recovered by the
    # browser's exact-request probe, and deleted/replaced node ownership.
    def make_host_loop_bridge_node(request_id, *, owner_state=None):
        live = {"state": deepcopy(hydrated_base)}
        stores = []
        results = []
        owner = owner_state if isinstance(owner_state, dict) else {"current": True}
        host_node = object.__new__(asset_library.HMBImageAssetLibrary)
        host_node._current_state = lambda: live["state"]
        host_node._scan_owner_is_current = lambda: bool(owner["current"])
        host_node._hmb_import_media_by_uid = {}
        host_node._hmb_manifest_poll_received = False
        host_node._hmb_manifest_poll_pending = False
        host_node._hmb_refresh_revision = hydrated_base["refresh_revision"]
        host_node._publish_state = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("Compact host-loop completion used the full publisher.")
        )
        host_node._accept_normalized_widget_state_baseline = (
            lambda *_args, **_kwargs: None
        )

        def store_state(name, value, *args, **kwargs):
            assert name == asset_library.WIDGET_STATE_PARAMETER
            assert kwargs.get("emit_change") is False
            assert kwargs.get("skip_before_value_set") is True
            normalized_value = asset_library._normalize_state(value)
            live["state"] = normalized_value
            stores.append(normalized_value)

        host_node.set_parameter_value = store_state
        host_node._set_thumbnail_bridge_value = lambda value: results.append(
            asset_library._normalize_thumbnail_bridge(value)
        )
        request = {
            **bridge_request,
            "request_id": request_id,
        }
        return host_node, live, stores, results, owner, request

    async def wait_for_thread(worker, *, timeout=5.0):
        assert worker is not None
        await asyncio.to_thread(worker.join, timeout)
        assert worker.is_alive() is False
        # The worker schedules completion before exiting. Yield to the owning
        # loop so its thread-safe callback can run before assertions.
        await asyncio.sleep(0)

    async def running_host_loop_completion():
        host_node, _live, stores, results, _owner, request = (
            make_host_loop_bridge_node("host-loop-once")
        )
        loop_thread_id = threading.get_ident()
        callback_threads = []
        original_result_publisher = host_node._set_thumbnail_bridge_value

        def record_result(value):
            callback_threads.append(threading.get_ident())
            original_result_publisher(value)

        host_node._set_thumbnail_bridge_value = record_result
        host_node._apply_thumbnail_bridge_request(request)
        worker = host_node._hmb_thumbnail_thread
        await wait_for_thread(worker)
        assert len(stores) == 1
        assert len(results) == 1
        assert callback_threads == [loop_thread_id]
        assert host_node._hmb_thumbnail_pending_key == ""
        assert host_node._hmb_thumbnail_pending_result is None

    def late_event_manager_loop_completion():
        injected_modules = {}
        try:
            from griptape_nodes.retained_mode import engine as engine_module
            from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
        except ModuleNotFoundError:
            module_names = (
                "griptape_nodes",
                "griptape_nodes.retained_mode",
                "griptape_nodes.retained_mode.engine",
                "griptape_nodes.retained_mode.griptape_nodes",
            )
            injected_modules = {
                name: sys.modules.get(name)
                for name in module_names
            }
            package = types.ModuleType("griptape_nodes")
            package.__path__ = []
            retained = types.ModuleType("griptape_nodes.retained_mode")
            retained.__path__ = []
            engine_module = types.ModuleType("griptape_nodes.retained_mode.engine")
            engine_module.has_current_engine = lambda: True

            class GriptapeNodes:
                @classmethod
                def EventManager(cls):
                    return None

            griptape_module = types.ModuleType(
                "griptape_nodes.retained_mode.griptape_nodes"
            )
            griptape_module.GriptapeNodes = GriptapeNodes
            retained.engine = engine_module
            package.retained_mode = retained
            sys.modules["griptape_nodes"] = package
            sys.modules["griptape_nodes.retained_mode"] = retained
            sys.modules["griptape_nodes.retained_mode.engine"] = engine_module
            sys.modules[
                "griptape_nodes.retained_mode.griptape_nodes"
            ] = griptape_module

        host_node, _live, stores, results, _owner, request = (
            make_host_loop_bridge_node("host-loop-bootstrap")
        )
        started = threading.Event()
        release = threading.Event()
        published = threading.Event()
        callback_threads = []
        loop_ready = threading.Event()
        loop_thread_id = []
        loop = asyncio.new_event_loop()

        def run_loop():
            asyncio.set_event_loop(loop)
            loop_thread_id.append(threading.get_ident())
            loop_ready.set()
            loop.run_forever()
            loop.close()

        loop_thread = threading.Thread(target=run_loop, daemon=True)
        loop_thread.start()
        assert loop_ready.wait(timeout=2.0)

        class FakeEventManager:
            event_loop = None

        fake_event_manager = FakeEventManager()
        original_engine_probe = engine_module.has_current_engine
        original_event_manager_descriptor = GriptapeNodes.__dict__["EventManager"]
        original_bootstrap_hydrator = asset_library._hydrate_asset_thumbnails

        def blocked_hydrator(state_value, request_value, **kwargs):
            started.set()
            assert release.wait(timeout=5.0)
            return original_bootstrap_hydrator(state_value, request_value, **kwargs)

        def record_result(value):
            callback_threads.append(threading.get_ident())
            results.append(asset_library._normalize_thumbnail_bridge(value))
            published.set()

        host_node._set_thumbnail_bridge_value = record_result
        engine_module.has_current_engine = lambda: True
        GriptapeNodes.EventManager = classmethod(lambda _cls: fake_event_manager)
        asset_library._hydrate_asset_thumbnails = blocked_hydrator
        try:
            # There is deliberately no running loop on this caller thread and
            # EventManager has not been initialized yet.
            host_node._apply_thumbnail_bridge_request(request)
            worker = host_node._hmb_thumbnail_thread
            assert worker is not None
            assert started.wait(timeout=2.0)
            fake_event_manager.event_loop = loop
            release.set()
            worker.join(timeout=5.0)
            assert worker.is_alive() is False
            assert published.wait(timeout=2.0)
            assert len(stores) == 1
            assert len(results) == 1
            assert callback_threads == loop_thread_id
            assert host_node._hmb_thumbnail_pending_key == ""

            class DroppingLoop:
                def __init__(self):
                    self.accepted = 0

                @staticmethod
                def is_running():
                    return True

                @staticmethod
                def is_closed():
                    return False

                def call_soon_threadsafe(self, *_args, **_kwargs):
                    self.accepted += 1
                    return None

            dropping_loop = DroppingLoop()
            fake_event_manager.event_loop = dropping_loop
            drop_node, _drop_live, drop_stores, drop_results, _drop_owner, drop_request = (
                make_host_loop_bridge_node("host-loop-accepted-but-dropped")
            )
            drop_node._apply_thumbnail_bridge_request(drop_request)
            drop_worker = drop_node._hmb_thumbnail_thread
            drop_worker.join(timeout=5.0)
            assert drop_worker.is_alive() is False
            assert dropping_loop.accepted == 1
            assert drop_node._hmb_thumbnail_pending_result is not None
            assert drop_node._consume_pending_thumbnail_result() is True
            assert len(drop_stores) == 1
            assert len(drop_results) == 1
            assert drop_node._hmb_thumbnail_pending_key == ""
            assert drop_node._hmb_thumbnail_pending_result is None
        finally:
            release.set()
            asset_library._hydrate_asset_thumbnails = original_bootstrap_hydrator
            engine_module.has_current_engine = original_engine_probe
            GriptapeNodes.EventManager = original_event_manager_descriptor
            if loop.is_running():
                loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=2.0)
            for module_name, original_module in injected_modules.items():
                if original_module is None:
                    sys.modules.pop(module_name, None)
                else:
                    sys.modules[module_name] = original_module

    async def failed_publish_probe_recovery():
        host_node, _live, stores, results, _owner, request = (
            make_host_loop_bridge_node("host-loop-publish-retry")
        )
        attempts = []
        first_failure_seen = threading.Event()
        hydrate_calls = 0
        original_retry_hydrator = asset_library._hydrate_asset_thumbnails

        def count_hydration(state_value, request_value, **kwargs):
            nonlocal hydrate_calls
            hydrate_calls += 1
            return original_retry_hydrator(state_value, request_value, **kwargs)

        def fail_once(value):
            attempts.append(threading.get_ident())
            if len(attempts) == 1:
                first_failure_seen.set()
                raise RuntimeError("simulated compact bridge publication failure")
            results.append(asset_library._normalize_thumbnail_bridge(value))

        host_node._set_thumbnail_bridge_value = fail_once
        asset_library._hydrate_asset_thumbnails = count_hydration
        try:
            host_node._apply_thumbnail_bridge_request(request)
            worker = host_node._hmb_thumbnail_thread
            await wait_for_thread(worker)
            for _ in range(50):
                if first_failure_seen.is_set():
                    break
                await asyncio.sleep(0.01)
            assert first_failure_seen.is_set()
            assert host_node._hmb_thumbnail_pending_result is not None
            assert len(stores) == 1
            assert results == []

            # An exact-request watchdog probe enters through before_value_set;
            # that official retained-mode callback drains the immutable result
            # without starting a replacement decoder.
            normalized_probe = host_node.before_value_set(
                SimpleNamespace(name=asset_library.THUMBNAIL_PATCH_PARAMETER),
                request,
            )
            assert normalized_probe["request_id"] == request["request_id"]
            assert host_node._hmb_thumbnail_pending_result is None
            assert host_node._hmb_thumbnail_pending_key == ""
            assert len(stores) == 2
            assert len(results) == 1
            assert len(attempts) == 2
            assert hydrate_calls == 1
        finally:
            asset_library._hydrate_asset_thumbnails = original_retry_hydrator

    async def stale_owner_and_delete_completion():
        original_lifecycle_hydrator = asset_library._hydrate_asset_thumbnails

        async def run_stale_owner_case(*, delete=False):
            owner_state = {"current": True}
            request_id = "host-loop-delete" if delete else "host-loop-remount"
            host_node, _live, _stores, results, owner, request = (
                make_host_loop_bridge_node(request_id, owner_state=owner_state)
            )
            started = threading.Event()
            release = threading.Event()

            def blocked_hydrator(state_value, request_value, **kwargs):
                started.set()
                assert release.wait(timeout=5.0)
                return original_lifecycle_hydrator(
                    state_value,
                    request_value,
                    **kwargs,
                )

            asset_library._hydrate_asset_thumbnails = blocked_hydrator
            host_node._apply_thumbnail_bridge_request(request)
            worker = host_node._hmb_thumbnail_thread
            assert worker is not None
            assert await asyncio.to_thread(started.wait, 2.0)
            if delete:
                prepare = getattr(asset_library._hmb_shot_routing, "prepare_node_deletion", None)
                release_lifecycle = getattr(
                    asset_library._hmb_shot_routing,
                    "release_node_lifecycle",
                    None,
                )
                asset_library._hmb_shot_routing.prepare_node_deletion = lambda _node: None
                asset_library._hmb_shot_routing.release_node_lifecycle = lambda _node: None
                host_node._hmb_delete_parent_called = True
                host_node._hmb_deletion_reconcile_called = True
                try:
                    host_node.after_node_deleted()
                finally:
                    if prepare is None:
                        delattr(asset_library._hmb_shot_routing, "prepare_node_deletion")
                    else:
                        asset_library._hmb_shot_routing.prepare_node_deletion = prepare
                    if release_lifecycle is None:
                        delattr(asset_library._hmb_shot_routing, "release_node_lifecycle")
                    else:
                        asset_library._hmb_shot_routing.release_node_lifecycle = release_lifecycle
            else:
                # NodeManager now resolves the replacement with the same name.
                owner["current"] = False
            release.set()
            await wait_for_thread(worker)
            await asyncio.sleep(0)
            assert results == []
            assert host_node._hmb_thumbnail_pending_key == ""
            assert host_node._hmb_thumbnail_pending_result is None
            assert host_node._hmb_thumbnail_queued_bridge_request is None

        try:
            await run_stale_owner_case(delete=False)
            await run_stale_owner_case(delete=True)
        finally:
            asset_library._hydrate_asset_thumbnails = original_lifecycle_hydrator

    asset_library._asset_thumbnail_url = (
        lambda _path, asset_id: f"memory://host-loop/{asset_id}"
    )
    try:
        asyncio.run(running_host_loop_completion())
        late_event_manager_loop_completion()
        asyncio.run(failed_publish_probe_recovery())
        asyncio.run(stale_owner_and_delete_completion())
    finally:
        asset_library._asset_thumbnail_url = original_thumbnail_url

    flight_node = object.__new__(asset_library.HMBImageAssetLibrary)
    flight_live = {"state": deepcopy(hydrated_base)}
    flight_publications = []
    flight_node._current_state = lambda: flight_live["state"]
    flight_node._scan_owner_is_current = lambda: True
    flight_node._hmb_manifest_poll_received = False
    flight_node._hmb_manifest_poll_pending = False
    flight_node._hmb_refresh_revision = hydrated_base["refresh_revision"]
    flight_node._hmb_import_media_by_uid = {}
    flight_node.get_parameter_value = lambda name: (
        hydrated_base["catalog_root"]
        if name == asset_library.PROJECT_ROOT_PARAMETER
        else []
    )
    flight_sync_calls = []
    flight_node._sync_output = lambda state: (
        flight_sync_calls.append(asset_library._normalize_state(state))
        or asset_library._normalize_state(state)
    )
    flight_node._hmb_last_reconciled_shot_catalog_identity = ""
    flight_node._reconcile_hmb_shot_routing = lambda *_args: None

    def publish_flight_state(value, *, normalized=False):
        normalized_value = (
            value if normalized else asset_library._normalize_state(value)
        )
        flight_live["state"] = normalized_value
        flight_publications.append(normalized_value)
        return normalized_value

    flight_node._publish_state = publish_flight_state
    original_hydrator = asset_library._hydrate_asset_thumbnails
    flight_started = threading.Event()
    flight_release = threading.Event()
    flight_counter_lock = threading.Lock()
    flight_counts = {"active": 0, "max_active": 0, "calls": 0}

    def slow_hydrator(state_value, request_value, **kwargs):
        with flight_counter_lock:
            flight_counts["active"] += 1
            flight_counts["calls"] += 1
            flight_counts["max_active"] = max(
                flight_counts["max_active"],
                flight_counts["active"],
            )
        flight_started.set()
        try:
            assert flight_release.wait(timeout=5.0)
            return original_hydrator(state_value, request_value, **kwargs)
        finally:
            with flight_counter_lock:
                flight_counts["active"] -= 1

    asset_library._hydrate_asset_thumbnails = slow_hydrator
    asset_library._asset_thumbnail_url = lambda _path, asset_id: f"memory://{asset_id}"
    try:
        first_flight = flight_node._schedule_thumbnail_hydration(
            hydrated_base,
            hydration_request,
        )
        assert first_flight["thumbnail_busy"] is True
        assert flight_started.wait(timeout=2.0)
        first_thread = flight_node._hmb_thumbnail_thread
        assert first_thread is not None
        live_edit = deepcopy(hydrated_base)
        live_edit["search"] = "semantic edit during thumbnail decode"
        live_edit[asset_library.UI_EDIT_REVISION_KEY] += 1
        live_edit["thumbnail_request"] = {
            **hydration_request,
            "request_id": "repeat-riding-with-ui-edit",
        }
        applied_edit = flight_node._apply_widget_state(live_edit)
        assert applied_edit["search"] == "semantic edit during thumbnail decode"
        assert len(flight_sync_calls) == 1
        assert flight_node._hmb_thumbnail_thread is first_thread
        for index in range(20):
            rapid_request = {
                **hydration_request,
                "request_id": f"rapid-{index}",
            }
            rapid = flight_node._schedule_thumbnail_hydration(
                hydrated_base,
                rapid_request,
            )
            assert rapid["thumbnail_busy"] is True
            assert flight_node._hmb_thumbnail_thread is first_thread
        assert flight_counts == {"active": 1, "max_active": 1, "calls": 1}
        assert flight_node._hmb_thumbnail_generation == 1
        assert flight_publications == []
        flight_release.set()
        first_thread.join(timeout=5.0)
        assert first_thread.is_alive() is False
        assert flight_node._consume_pending_thumbnail_result() is True
    finally:
        flight_release.set()
        asset_library._hydrate_asset_thumbnails = original_hydrator
        asset_library._asset_thumbnail_url = original_thumbnail_url
    assert flight_counts["max_active"] == 1
    assert flight_counts["calls"] == 1
    assert len(flight_publications) == 1

    # A newer UI transaction carrying a delayed pre-hydration echo keeps its
    # edits while the accepted thumbnail revision/media field remains durable.
    echo_node = object.__new__(asset_library.HMBImageAssetLibrary)
    echo_node._hmb_last_accepted_widget_state = None
    echo_node._hmb_last_accepted_widget_revisions = (0, 0)
    echo_node._hmb_last_accepted_thumbnail_revision = 0
    echo_node._accept_widget_state_baseline(hydration_result)
    assert echo_node._widget_state_is_stale(hydrated_base) is True
    delayed_ui = deepcopy(hydrated_base)
    delayed_ui["search"] = "keep this newer UI edit"
    delayed_ui[asset_library.UI_EDIT_REVISION_KEY] = 12
    assert echo_node._widget_state_is_stale(delayed_ui) is False
    preserved = echo_node._preserve_newer_thumbnail_baseline(delayed_ui)
    preserved_hero = next(
        item for item in preserved["assets"] if item["asset_id"] == "Hero"
    )
    assert preserved["search"] == "keep this newer UI edit"
    assert preserved_hero["thumbnail_url"].startswith("memory://")
    assert preserved["thumbnail_revision"] == hydration_result["thumbnail_revision"]

    # Restart/deserialization retires session URLs and every transient worker
    # flag before scheduling the replacement catalog generation.
    crash_state = deepcopy(hydration_result)
    crash_state["thumbnail_busy"] = True
    crash_state["thumbnail_request"] = hydration_request
    crash_state["thumbnail_result"] = hydration_result["thumbnail_result"]
    asset_library._ASSET_THUMBNAIL_URLS.clear()
    deserialize_node = object.__new__(asset_library.HMBImageAssetLibrary)
    deserialize_node._current_state = lambda: crash_state
    deserialize_node._ensure_parameters = lambda: None
    deserialize_node.get_parameter_value = lambda name: (
        crash_state["catalog_root"]
        if name == asset_library.PROJECT_ROOT_PARAMETER
        else []
    )
    deserialize_node.set_parameter_value = lambda *_args, **_kwargs: None
    deserialize_node._schedule_post_hydration_shot_reconcile = lambda: None
    deserialize_capture = []
    deserialize_node._schedule_catalog_scan = (
        lambda key, candidate, scan, **kwargs: deserialize_capture.append(
            (key, asset_library._normalize_state(candidate), scan, kwargs)
        )
    )
    deserialize_node._hmb_thumbnail_queued_bridge_request = {
        "request_id": "stale-before-deserialize"
    }
    deserialize_node._hmb_scan_generation = 7
    deserialize_node._hmb_scan_pending_key = "constructor-scan"
    deserialize_node._hmb_scan_pending_result = (7, "constructor-scan", "old", {})
    deserialize_node._hmb_scan_thread = object()
    deserialize_node.after_deserialize()
    assert deserialize_node._hmb_thumbnail_queued_bridge_request is None
    assert deserialize_node._hmb_scan_generation == 8
    assert deserialize_node._hmb_scan_pending_key == ""
    assert deserialize_node._hmb_scan_pending_result is None
    assert deserialize_node._hmb_scan_thread is None
    assert len(deserialize_capture) == 1
    deserialize_candidate = deserialize_capture[0][1]
    assert deserialize_candidate["thumbnail_busy"] is False
    assert deserialize_candidate["thumbnail_request"] == {}
    assert deserialize_candidate["thumbnail_result"] == {}
    assert all(
        not item["thumbnail_url"] for item in deserialize_candidate["assets"]
    )

    # External Add performs no project scan, replaces only the source row, and
    # remaps that source UID at the exact position in every Shot.
    catalog_state = asset_library._load_project_catalog(
        catalog_root,
        asset_library._default_state(),
    )
    catalog_project_path = next(
        item["path"]
        for item in catalog_state["projects"]
        if item["name"] == project_root.name
    )
    catalog_state = asset_library._select_catalog_project(
        catalog_state,
        catalog_project_path,
    )
    external_path = temporary / "External.png"
    external_path.write_bytes(png_bytes((13, 13), (120, 30, 180)))
    catalog_state, media_by_uid = asset_library._merge_import_input(
        catalog_state,
        [str(external_path)],
    )
    anchor = next(item for item in catalog_state["assets"] if item["asset_id"] == "Hero")
    imported = next(
        item
        for item in catalog_state["assets"]
        if item["source_kind"] == "user" and item["import_index"] > 0
    )
    anchor["selected"] = True
    anchor["selection_order"] = 1
    imported["selected"] = True
    imported["selection_order"] = 2
    routing = deepcopy(catalog_state["shot_routing"])
    first_shot = routing["shots"][0]
    first_shot["selected_source_uids"] = [anchor["source_uid"], imported["source_uid"]]
    second_shot = deepcopy(first_shot)
    second_shot["shot_uuid"] = str(uuid.uuid4())
    second_shot["number"] = 2
    second_shot["name"] = "Shot 2"
    second_shot["selected_source_uids"] = [imported["source_uid"], anchor["source_uid"]]
    routing["shots"] = [first_shot, second_shot]
    catalog_state["shot_routing"] = routing
    catalog_state = asset_library._normalize_state(catalog_state)
    imported = next(
        item
        for item in catalog_state["assets"]
        if item["source_kind"] == "user" and item["import_index"] > 0
    )
    request = {
        "request_id": "single-row-add",
        "project_uid": catalog_state["project_uid"],
        "asset_library_id": imported["asset_library_id"],
        "source_kind": "user",
        "source_uid": imported["source_uid"],
        "relative_path": "",
        "target_folder": "Assets",
        "image_name": "External Registered",
        "asset_id": "ExternalRegistered",
        "image_main_type": "Character",
        "image_sub_type": "Full Appearance",
        "custom_source_type": "",
    }
    original_scan = asset_library._scan_project_assets
    asset_library._scan_project_assets = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("Add performed a full project scan")
    )
    asset_library._asset_thumbnail_url = lambda _path, asset_id: f"memory://{asset_id}"
    try:
        added = asset_library._apply_asset_registration(
            catalog_state,
            request,
            media_by_uid,
        )
    finally:
        asset_library._scan_project_assets = original_scan
        asset_library._asset_thumbnail_url = original_thumbnail_url
    assert all(item["source_uid"] != imported["source_uid"] for item in added["assets"])
    registered = next(item for item in added["assets"] if item["asset_id"] == "ExternalRegistered")
    assert registered["thumbnail_url"].startswith("memory://")
    assert (registered["selected"], registered["selection_order"]) == (True, 2)
    added_shots = added["shot_routing"]["shots"]
    assert added_shots[0]["selected_source_uids"] == [
        anchor["source_uid"],
        registered["source_uid"],
    ]
    assert added_shots[1]["selected_source_uids"] == [
        registered["source_uid"],
        anchor["source_uid"],
    ]

    live_during_add = deepcopy(catalog_state)
    live_during_add["search"] = "edit committed while Add worker ran"
    live_during_add[asset_library.UI_EDIT_REVISION_KEY] += 1
    live_during_add = asset_library._normalize_state(live_during_add)
    async_added = asset_library._merge_async_registration_result_with_live_state(
        added,
        catalog_state,
        live_during_add,
        request,
    )
    async_registered = next(
        item for item in async_added["assets"] if item["asset_id"] == "ExternalRegistered"
    )
    assert async_added["search"] == "edit committed while Add worker ran"
    assert all(
        imported["source_uid"] not in shot["selected_source_uids"]
        for shot in async_added["shot_routing"]["shots"]
    )
    assert async_added["shot_routing"]["shots"][0]["selected_source_uids"] == [
        anchor["source_uid"],
        async_registered["source_uid"],
    ]
    assert async_added["shot_routing"]["shots"][1]["selected_source_uids"] == [
        async_registered["source_uid"],
        anchor["source_uid"],
    ]

    disconnected_live = deepcopy(catalog_state)
    disconnected_live["assets"] = [
        item
        for item in disconnected_live["assets"]
        if item["source_uid"] != imported["source_uid"]
    ]
    disconnected_live = asset_library._normalize_state(disconnected_live)
    disconnected_add = asset_library._merge_async_registration_result_with_live_state(
        added,
        catalog_state,
        disconnected_live,
        request,
    )
    disconnected_target = next(
        item
        for item in disconnected_add["assets"]
        if item["asset_id"] == "ExternalRegistered"
    )
    assert disconnected_target["selected"] is False
    assert disconnected_target["selection_order"] == 0
    assert all(
        disconnected_target["source_uid"] not in shot["selected_source_uids"]
        for shot in disconnected_add["shot_routing"]["shots"]
    )

    duplicate_probe = {"shot_routing": deepcopy(added["shot_routing"])}
    duplicate_probe["shot_routing"]["shots"][0]["selected_source_uids"] = [
        imported["source_uid"],
        anchor["source_uid"],
        registered["source_uid"],
    ]
    asset_library._remap_shot_routing_source_uid(
        duplicate_probe,
        imported["source_uid"],
        registered["source_uid"],
    )
    assert duplicate_probe["shot_routing"]["shots"][0]["selected_source_uids"] == [
        registered["source_uid"],
        anchor["source_uid"],
    ]
finally:
    asset_library._ASSET_THUMBNAIL_CACHE_ROOT = default_cache_root
    shutil.rmtree(temporary, ignore_errors=True)


print("HMB image asset staged loading/cache/Add single-row regression: PASS")
