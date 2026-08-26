from __future__ import annotations

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

    def publish_node_state(value):
        normalized_value = asset_library._normalize_state(value)
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

    def publish_flight_state(value):
        normalized_value = asset_library._normalize_state(value)
        flight_live["state"] = normalized_value
        flight_publications.append(normalized_value)
        return normalized_value

    flight_node._publish_state = publish_flight_state
    original_hydrator = asset_library._hydrate_asset_thumbnails
    flight_started = threading.Event()
    flight_release = threading.Event()
    flight_counter_lock = threading.Lock()
    flight_counts = {"active": 0, "max_active": 0, "calls": 0}

    def slow_hydrator(state_value, request_value):
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
            return original_hydrator(state_value, request_value)
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
    deserialize_node.after_deserialize()
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
