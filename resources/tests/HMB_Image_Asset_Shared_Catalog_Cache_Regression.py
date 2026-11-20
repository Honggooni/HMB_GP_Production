from __future__ import annotations

from copy import deepcopy
from io import BytesIO
import importlib.util
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "HMBImageAssetLibrary.py"
spec = importlib.util.spec_from_file_location(
    "hmb_image_asset_shared_catalog_cache_regression",
    MODULE_PATH,
)
assert spec is not None and spec.loader is not None
asset_library = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = asset_library
spec.loader.exec_module(asset_library)

from PIL import Image


def png_bytes(color: tuple[int, int, int]) -> bytes:
    output = BytesIO()
    Image.new("RGB", (12, 9), color).save(output, format="PNG")
    return output.getvalue()


with tempfile.TemporaryDirectory(prefix="hmb_shared_catalog_") as temporary:
    # Windows CI TEMP may use an 8.3 alias. Match the canonical paths emitted
    # by project discovery, just as a native dropdown selection does.
    temporary_root = Path(temporary).resolve()
    asset_library._ASSET_CATALOG_INDEX_ROOT = temporary_root / "cache" / "image_catalogs"
    asset_library._ASSET_THUMBNAIL_CACHE_ROOT = temporary_root / "cache" / "image_thumbnails"
    catalog_a = temporary_root / "MountA"
    project_a = catalog_a / "ProjectA"
    project_a.mkdir(parents=True)
    hero_a = project_a / "Hero.png"
    hero_a.write_bytes(png_bytes((220, 20, 70)))
    pre_manifest_cache_uid = asset_library._project_cache_uid(project_a)
    asset_library._write_asset_manifest_record(
        project_a,
        {
            "path": "Hero.png",
            "asset_id": "Hero",
            "image_name": "Hero",
            "source_type": "Character Appearance",
            "custom_source_type": "",
            "scope": "Full body / full appearance",
        },
    )
    assert asset_library._project_cache_uid(project_a) == pre_manifest_cache_uid

    state = asset_library._load_project_catalog(
        catalog_a,
        {
            **asset_library._default_state(),
            "catalog_root": str(catalog_a),
            "project_root": str(project_a),
            "project_id": "ProjectA",
            "project_uid": asset_library._project_uid(project_a),
        },
        use_shared_cache=False,
    )
    assert state["folder_signature"]
    hero = state["assets"][0]
    live_url = "http://localhost:8124/static/hero.webp"
    asset_library._ASSET_THUMBNAIL_URLS[hero["media_signature"]] = live_url
    hero["thumbnail_url"] = live_url
    state = asset_library._normalize_state(state)
    asset_library._store_shared_catalog_snapshot(state, normalized=True)

    # A replacement node may retain its workflow routing, but catalog rows and
    # live thumbnail presentation are adopted without another image walk.
    replacement = asset_library._default_state()
    replacement.update(
        {
            "catalog_root": str(catalog_a),
            "project_root": str(project_a),
            "project_id": "ProjectA",
            "project_uid": state["project_uid"],
        }
    )
    replacement_routing = deepcopy(replacement["shot_routing"])
    original_scan = asset_library._scan_project_assets
    asset_library._scan_project_assets = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("replacement node walked an already-cached project")
    )
    try:
        adopted = asset_library._load_project_catalog(catalog_a, replacement)
    finally:
        asset_library._scan_project_assets = original_scan
    assert adopted["assets"][0]["thumbnail_url"] == live_url
    assert adopted["shot_routing"] == replacement_routing
    assert adopted["shot_routing"] != state["shot_routing"]

    # Portable project media signatures survive a drive/root alias rebind.
    catalog_b = temporary_root / "MountB"
    project_b = catalog_b / "ProjectA"
    shutil.copytree(project_a, project_b, copy_function=shutil.copy2)
    hero_b = project_b / "Hero.png"
    relative = "Hero.png"
    facts_a = asset_library._asset_file_facts(
        hero_a,
        project_uid=state["project_cache_uid"],
        relative_path=relative,
    )
    facts_b = asset_library._asset_file_facts(
        hero_b,
        project_uid=asset_library._project_cache_uid(project_b),
        relative_path=relative,
    )
    assert facts_a[3] == facts_b[3]
    resolved_b = asset_library._resolve_project_asset_file(
        project_b,
        "ProjectA",
        relative,
        hero["asset_library_id"],
    )
    assert resolved_b[2] == hero["media_signature"]

    # An older widget may still send probes. They cannot read or adopt files
    # changed by other users until an explicit Refresh or a new engine session.
    probe_node = object.__new__(asset_library.HMBImageAssetLibrary)
    sidekick = project_a / "Sidekick.png"
    sidekick.write_bytes(png_bytes((20, 80, 220)))
    with patch.object(asset_library, "_catalog_directory_entries", side_effect=AssertionError("implicit folder scan")):
        assert probe_node._compute_catalog_probe(state, {"probe_kind": "folder"}) == ("no_change", None)
        idle = asset_library._load_project_catalog(catalog_a, adopted)
        assert {item["relative_path"] for item in idle["assets"]} == {"Hero.png"}
    changed = asset_library._load_project_catalog(catalog_a, adopted, use_shared_cache=False)
    assert {item["relative_path"] for item in changed["assets"]} == {"Hero.png", "Sidekick.png"}

    bridge = asset_library._normalize_thumbnail_bridge(
        {
            "schema": asset_library.THUMBNAIL_BRIDGE_SCHEMA,
            "version": asset_library.THUMBNAIL_BRIDGE_VERSION,
            "operation": asset_library.CATALOG_PROBE_OPERATION,
            "phase": "request",
            "request_id": "probe-1",
            "runtime_instance_id": "runtime-1",
            "project_uid": state["project_uid"],
            "project_cache_uid": state["project_cache_uid"],
            "project_root": state["project_root"],
            "manifest_signature": state["manifest_signature"],
            "scan_revision": state["scan_revision"],
            "probe_kind": "folder",
        }
    )
    assert bridge["operation"] == asset_library.CATALOG_PROBE_OPERATION
    assert bridge["probe_kind"] == "folder"
    assert bridge["project_cache_uid"] == state["project_cache_uid"]

    # Independent same-named projects must never share selection, catalog
    # indices, media signatures, or persistent thumbnail payloads.
    twin_a = temporary_root / "IndependentA" / "ProjectX"
    twin_b = temporary_root / "IndependentB" / "ProjectX"
    twin_a.mkdir(parents=True)
    twin_b.mkdir(parents=True)
    twin_a_image = twin_a / "Hero.bmp"
    twin_b_image = twin_b / "Hero.bmp"
    Image.new("RGB", (16, 16), (255, 0, 0)).save(twin_a_image, format="BMP")
    Image.new("RGB", (16, 16), (0, 0, 255)).save(twin_b_image, format="BMP")
    forced_mtime = time.time() - 60
    for candidate in (twin_a_image, twin_b_image):
        os.utime(candidate, (forced_mtime, forced_mtime))
    assert twin_a_image.stat().st_size == twin_b_image.stat().st_size
    assert asset_library._project_cache_uid(twin_a) != asset_library._project_cache_uid(
        twin_b
    )
    twin_a_state = asset_library._scan_project_assets(twin_a)
    twin_b_state = asset_library._scan_project_assets(twin_b)
    assert (
        twin_a_state["assets"][0]["media_signature"]
        != twin_b_state["assets"][0]["media_signature"]
    )
    assert asset_library._catalog_index_path(twin_a) != asset_library._catalog_index_path(
        twin_b
    )
    twin_a_state["assets"][0]["selected"] = True
    twin_a_state["assets"][0]["selection_order"] = 1
    isolated = asset_library._merge_scan_with_state(twin_b_state, twin_a_state)
    assert not isolated["assets"][0]["selected"]

    # Hidden image files are excluded by both the full scan and metadata probe,
    # so they cannot cause a permanent change/rescan loop.
    hidden = project_a / ".copying.png"
    hidden.write_bytes(png_bytes((1, 2, 3)))
    rescanned = asset_library._scan_project_assets(project_a)
    assert not any(item["relative_path"] == hidden.name for item in rescanned["assets"])
    assert rescanned["folder_signature"] == asset_library._project_folder_metadata_signature(
        project_a
    )

    # A raw exact-root change invalidates the persistent index immediately;
    # a cold verification must detect it even when an index is already present.
    asset_library._write_catalog_index(rescanned)
    raw_added = project_a / "RawAdded.png"
    raw_added.write_bytes(png_bytes((40, 50, 60)))
    previous_for_index = {**asset_library._default_state(), **rescanned}
    previous_for_index["catalog_root"] = str(catalog_a)
    assert asset_library._read_catalog_index(project_a, previous_for_index) is None

    # Completion publication, including a cache hit/pending drain/probe result,
    # must never resolve a project or persist an index on the host loop.  Cache
    # preparation is worker-owned, and live edits cannot supply its identity.
    cache_state = asset_library._load_project_catalog(
        catalog_a, previous_for_index, use_shared_cache=False
    )
    # A real cached project selection owns new verified rows, even though the
    # cache-adoption helper deliberately preserves its caller's source clock.
    asset_library._store_shared_catalog_snapshot(cache_state)
    busy_ack = deepcopy(cache_state)
    busy_ack.update(project_id="", project_uid="", project_cache_uid="",
                    manifest_signature="", folder_signature="", assets=[],
                    scan_busy=True, scan_revision=7, ui_edit_revision=42)
    cached_selection = asset_library._select_catalog_project(busy_ack, str(project_a))
    assert cached_selection["scan_revision"] == 7
    assert cached_selection["assets"]
    cached_selection["scan_busy"] = False  # All scheduler completion callers do this.
    cached_before_publication = deepcopy(cached_selection)
    current_publication = [deepcopy(busy_ack)]

    def publish_selection(payload, **_kwargs):
        current_publication[0] = deepcopy(payload)
        return deepcopy(payload)

    selection_publisher = SimpleNamespace(
        _hmb_scan_lock=threading.RLock(), _hmb_fresh_registration_scan_key="",
        _hmb_node_deleted=False,
        _current_state=lambda: deepcopy(current_publication[0]),
        _publish_state=publish_selection,
    )
    completed_selection = asset_library.HMBImageAssetLibrary._publish_completed_catalog_scan(
        selection_publisher, cached_selection, "project:verified-cache-hit"
    )
    assert completed_selection["scan_revision"] == 8
    assert completed_selection["ui_edit_revision"] == 42
    assert completed_selection["assets"] == cached_selection["assets"]
    assert cached_selection == cached_before_publication, "Cache source was mutated"
    authority = SimpleNamespace(
        _widget_revision_pair=asset_library.HMBImageAssetLibrary._widget_revision_pair,
        _hmb_last_accepted_widget_state=asset_library._json_text(completed_selection),
        _hmb_last_accepted_widget_revisions=(8, 42),
        _hmb_last_accepted_thumbnail_revision=0,
    )
    assert asset_library.HMBImageAssetLibrary._widget_state_is_stale(authority, busy_ack), (
        "A late empty native ACK must not erase completed cached image rows"
    )
    repeated = asset_library.HMBImageAssetLibrary._publish_completed_catalog_scan(
        selection_publisher, completed_selection, "project:verified-cache-hit"
    )
    assert repeated == completed_selection, "Completed snapshots must not oscillate clocks"
    for key, live, result in (
        ("manifest:unchanged", busy_ack, cached_selection),
        ("probe:changed", busy_ack, cached_selection),
        ("project:other-root", {**busy_ack, "project_root": str(project_b)}, cached_selection),
    ):
        current_publication[0] = deepcopy(live)
        unchanged = asset_library.HMBImageAssetLibrary._publish_completed_catalog_scan(
            selection_publisher, result, key
        )
        assert unchanged["scan_revision"] == result["scan_revision"], key
    current_publication[0] = {**busy_ack, "scan_revision": 9}
    caught_up = asset_library.HMBImageAssetLibrary._publish_completed_catalog_scan(
        selection_publisher, cached_selection, "project:poll-progress"
    )
    assert caught_up["scan_revision"] == 10
    current_publication[0] = deepcopy(busy_ack)
    cold_result = {**cached_selection, "scan_revision": 8}
    cold_complete = asset_library.HMBImageAssetLibrary._publish_completed_catalog_scan(
        selection_publisher, cold_result, "project:cold-scan"
    )
    assert cold_complete["scan_revision"] == 8, "Cold scans must not gain an extra revision"
    for key, result in (
        ("project:empty", {**cached_selection, "assets": []}),
        ("project:failed", {**cached_selection, "assets": [], "error": "unavailable"}),
    ):
        current_publication[0] = deepcopy(busy_ack)
        terminal = asset_library.HMBImageAssetLibrary._publish_completed_catalog_scan(
            selection_publisher, result, key
        )
        assert terminal["scan_revision"] == 8 and terminal["scan_busy"] is False
        assert terminal["assets"] == [] and terminal["error"] == result["error"]
    # Loading/reloading from either local index or shared cache keeps the source
    # clock; the terminal publisher advances only the actual selected operation.
    # The synthetic empty completion above must not be accepted as a complete
    # catalog for three real files. Restore the actual verified snapshot.
    assert asset_library._adopt_shared_catalog_snapshot(
        {"catalog_root": str(catalog_a), "projects": cache_state["projects"]},
        cache_state["projects"][0], completed_selection,
    ) is None
    asset_library._store_shared_catalog_snapshot(cache_state)
    reopened = asset_library._select_catalog_project(completed_selection, str(project_a))
    assert reopened["scan_revision"] == completed_selection["scan_revision"]
    assert reopened["project_cache_uid"] == completed_selection["project_cache_uid"]
    asset_library._write_catalog_index(cache_state)
    indexed_reopen = asset_library._read_catalog_index(project_a, completed_selection)
    assert indexed_reopen is not None
    assert indexed_reopen["scan_revision"] == completed_selection["scan_revision"]
    unchanged_poll, media = asset_library.HMBImageAssetLibrary._compute_manifest_poll(
        SimpleNamespace(_hmb_last_manifest_poll_error=""), completed_selection
    )
    assert unchanged_poll == completed_selection and media is None
    verified_uid = cache_state["project_cache_uid"]
    expected_index = asset_library._catalog_index_path(project_a)
    assert expected_index == asset_library._catalog_index_path_for_verified_uid(
        verified_uid
    )
    original_uid_lookup = asset_library._project_cache_uid
    original_writer = asset_library._write_catalog_index
    original_index_lookup = asset_library._catalog_index_path
    host_thread = threading.get_ident()
    lookup_started = threading.Event()
    allow_lookup = threading.Event()
    worker_errors = []
    writer_threads = []
    lookup_calls = []

    def worker_uid_lookup(root):
        assert threading.get_ident() != host_thread, "project IO ran on host"
        lookup_calls.append(str(root))
        lookup_started.set()
        assert allow_lookup.wait(5), "worker lookup latch timed out"
        return original_uid_lookup(root)

    def worker_writer(payload, **kwargs):
        assert threading.get_ident() != host_thread, "durable IO ran on host"
        writer_threads.append(threading.get_ident())
        original_writer(payload, **kwargs)

    def forbidden_index_lookup(*_args, **_kwargs):
        raise AssertionError("writer revisited the project to calculate a local filename")

    publisher = SimpleNamespace(
        _hmb_scan_lock=threading.RLock(),
        _hmb_fresh_registration_scan_key="",
        _hmb_node_deleted=False,
        _publish_state=lambda payload, **_kwargs: deepcopy(payload),
    )

    def prepare_in_worker(payload):
        try:
            asset_library._prepare_catalog_scan_index(payload, normalized=True)
        except BaseException as exc:
            worker_errors.append(exc)

    asset_library._project_cache_uid = worker_uid_lookup
    asset_library._write_catalog_index = worker_writer
    asset_library._catalog_index_path = forbidden_index_lookup
    try:
        thread = threading.Thread(target=prepare_in_worker, args=(cache_state,))
        thread.start()
        assert lookup_started.wait(5)
        # A slow share is still waiting on the worker.  Each actual publisher
        # path remains available and retains the scan-owned cache UID.
        for key in ("ready-cache", "thread-completion", "pending-drain", "probe:changed"):
            published = asset_library.HMBImageAssetLibrary._publish_completed_catalog_scan(
                publisher, cache_state, key
            )
            assert published["project_cache_uid"] == verified_uid
            assert published["project_id"] == cache_state["project_id"]
        assert not writer_threads
        allow_lookup.set()
        thread.join(5)
        assert not thread.is_alive() and not worker_errors
        assert len(lookup_calls) == len(writer_threads) == 1
        assert expected_index.is_file()

        # A syntactically valid client UID still has no cache-write authority.
        forged_uid = "hmbpc1:" + ("a" * 32 if verified_uid[-32:] != "a" * 32 else "b" * 32)
        forged_state = {**cache_state, "project_cache_uid": forged_uid}
        forged_index = asset_library._catalog_index_path_for_verified_uid(forged_uid)
        thread = threading.Thread(target=prepare_in_worker, args=(forged_state,))
        thread.start(); thread.join(5)
        assert not thread.is_alive() and not worker_errors
        assert len(writer_threads) == 1 and not forged_index.exists()

        # Same-root replacement with a new verified identity uses a new file;
        # the old worker cannot overwrite that new identity's snapshot.
        asset_library._project_cache_uid = lambda _root: forged_uid
        prepare_in_worker(cache_state)
        assert len(writer_threads) == 1
        replacement_state = {**cache_state, "project_cache_uid": forged_uid}
        thread = threading.Thread(target=prepare_in_worker, args=(replacement_state,))
        thread.start(); thread.join(5)
        assert not thread.is_alive() and not worker_errors
        assert len(writer_threads) == 2 and forged_index.is_file()
        assert forged_index != expected_index
    finally:
        allow_lookup.set()
        if thread.is_alive():
            thread.join(5)
        asset_library._project_cache_uid = original_uid_lookup
        asset_library._write_catalog_index = original_writer
        asset_library._catalog_index_path = original_index_lookup

    # The write-side fast filename does not relax authoritative read-side
    # rejection of another identity or fresh raw filesystem changes.
    assert asset_library._read_catalog_index(project_a, cache_state) is not None
    wrong_raw = __import__("json").loads(expected_index.read_text(encoding="utf-8"))
    wrong_raw["project_cache_uid"] = forged_uid
    expected_index.write_text(__import__("json").dumps(wrong_raw), encoding="utf-8")
    assert asset_library._read_catalog_index(project_a, cache_state) is None


with tempfile.TemporaryDirectory(prefix="hmb_incremental_catalog_") as temporary:
    catalog = Path(temporary).resolve()
    project = catalog / "Show"
    project.mkdir()
    asset_library._ASSET_CATALOG_INDEX_ROOT = catalog / "cache"
    for number in range(5):
        (project / f"Hero{number}.png").write_bytes(png_bytes((number, 20, 40)))
    initial = {**asset_library._default_state(), "catalog_root": str(catalog),
               "project_root": str(project), "project_id": "Show",
               "project_uid": asset_library._project_uid(project)}
    current = asset_library._load_project_catalog(catalog, initial, use_shared_cache=False)
    routes = deepcopy(current["shot_routing"])
    original_dimensions = asset_library._asset_dimensions

    # A manual Refresh verifies metadata but reuses unchanged image facts.
    # A new engine must verify the on-disk index before adopting it.
    with patch.object(asset_library, "_asset_dimensions", side_effect=AssertionError("unchanged image decoded")), \
         patch.object(asset_library, "_asset_content_probe", side_effect=AssertionError("unchanged image sampled")):
        for _ in range(3):
            current = asset_library._load_project_catalog(catalog, current, use_shared_cache=False)
            assert len(current["assets"]) == 5 and current["shot_routing"] == routes
        asset_library._write_catalog_index(current)
        with patch.dict(asset_library._CATALOG_READS, clear=True), \
             patch.object(asset_library, "_read_catalog_index", wraps=asset_library._read_catalog_index) as reads:
            restored = asset_library._load_project_catalog(catalog, initial)
            assert reads.call_count == 1
        assert len(restored["assets"]) == 5

    # File-by-file cache survives normalization/serialization and a new file,
    # replacement, removal or registration change cannot trigger full decode.
    (project / "New.png").write_bytes(png_bytes((90, 40, 10)))
    with patch.object(asset_library, "_asset_dimensions", wraps=original_dimensions) as reads:
        current = asset_library._load_project_catalog(catalog, current, use_shared_cache=False)
        assert [call.args[0].name for call in reads.call_args_list] == ["New.png"]
    (project / "Hero1.png").write_bytes(png_bytes((210, 50, 10)))
    with patch.object(asset_library, "_asset_dimensions", wraps=original_dimensions) as reads:
        current = asset_library._load_project_catalog(catalog, current, use_shared_cache=False)
        assert [call.args[0].name for call in reads.call_args_list] == ["Hero1.png"]
    (project / "Hero2.png").unlink()
    with patch.object(asset_library, "_asset_dimensions", side_effect=AssertionError("removed file caused re-read")):
        current = asset_library._load_project_catalog(catalog, current, use_shared_cache=False)
        assert len(current["assets"]) == 5
        asset_library._write_asset_manifest_record(project, {
            "path": "Hero0.png", "asset_id": "Renamed", "image_name": "한글 이름",
            "image_main_type": "Character", "image_sub_type": "",
        })
        current = asset_library._load_project_catalog(catalog, current, use_shared_cache=False)
        assert next(item for item in current["assets"] if item["relative_path"] == "Hero0.png")["image_name"] == "한글 이름"
        assert current["shot_routing"] == routes
    with patch.object(asset_library.os, "scandir", side_effect=PermissionError("offline")):
        try:
            asset_library._project_folder_metadata_signature(project)
        except PermissionError:
            pass
        else:
            raise AssertionError("An unavailable share was accepted as an empty inventory")

# Older widget sessions are acknowledged synchronously with no shared-drive work.
node = object.__new__(asset_library.HMBImageAssetLibrary)
state = asset_library._default_state()
replies = []
node._set_thumbnail_bridge_value = replies.append
with patch.object(asset_library, "_catalog_directory_entries", side_effect=AssertionError("legacy folder request scanned")), \
     patch.object(asset_library, "_asset_manifest_signature", side_effect=AssertionError("legacy request read manifest")):
    for kind in ("folder", "manifest"):
        node._schedule_catalog_probe({"request_id": kind, "probe_kind": kind}, state)
assert [(reply["request_id"], reply["outcome"]) for reply in replies] == [("folder", "no_change"), ("manifest", "no_change")]

# Multiple nodes share filesystem facts without sharing the author's shots.
from concurrent.futures import ThreadPoolExecutor
import json
import uuid


def concurrent_open(catalog, states):
    barrier = threading.Barrier(len(states))
    def run(state):
        barrier.wait(timeout=5)
        return asset_library._load_project_catalog(catalog, state)
    with ThreadPoolExecutor(max_workers=len(states)) as pool:
        return list(pool.map(run, states))


with tempfile.TemporaryDirectory(prefix="hmb_session_catalog_") as temporary:
    catalog = Path(temporary).resolve()
    project = catalog / "Show"
    project.mkdir()
    asset_library._ASSET_CATALOG_INDEX_ROOT = catalog / "cache"
    for number in range(3):
        (project / f"Hero{number}.png").write_bytes(png_bytes((number, 30, 70)))
        asset_library._write_asset_manifest_record(project, {
            "path": f"Hero{number}.png", "asset_id": f"Hero{number}",
            "image_name": f"Hero {number}", "image_main_type": "Character",
        })
    initial = {**asset_library._default_state(), "catalog_root": str(catalog),
               "project_root": str(project), "project_id": "Show",
               "project_uid": asset_library._project_uid(project)}
    current = asset_library._load_project_catalog(catalog, initial, use_shared_cache=False)
    states = []
    for number in range(5):
        state = deepcopy(current)
        route = asset_library._default_state()["shot_routing"]
        uids = [a["source_uid"] for a in state["assets"]]
        order = uids[number % 3:] + uids[:number % 3]
        route["shots"] = [{**deepcopy(route["shots"][0]), "shot_uuid": str(uuid.uuid4()),
                           "number": i + 1, "name": f"Node {number} Shot {i + 1}",
                           "name_is_custom": True, "selected_source_uids": order[:2]}
                          for i in range(5)]
        route["active_shot_uuid"] = route["shots"][number]["shot_uuid"]
        state["shot_routing"] = route
        for asset in state["assets"]:
            asset["selected"] = asset["source_uid"] in order[:2]
            asset["selection_order"] = order.index(asset["source_uid"]) + 1 if asset["selected"] else 0
        states.append(asset_library._normalize_state(state))
    originals = deepcopy(states)
    # Five already-loaded views cannot schedule a manifest read, a directory
    # walk, or image decoding during this session, including after a foreign Add.
    manifest_path = asset_library._existing_asset_manifest_path(project)
    manifest = json.loads(manifest_path.read_text("utf-8"))
    new_name = "변경된 등록 이름"
    manifest["assets"][0]["image_name"] = new_name
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    with patch.object(asset_library, "_asset_manifest_signature", side_effect=AssertionError("implicit manifest read")), \
         patch.object(asset_library, "_catalog_directory_entries", side_effect=AssertionError("implicit inventory")), \
         patch.object(asset_library, "_asset_dimensions", side_effect=AssertionError("implicit decode")):
        old_views = concurrent_open(catalog, states)
    for original, view in zip(originals, old_views):
        assert view["shot_routing"] == original["shot_routing"]
        assert view["assets"] == original["assets"]

    # One explicit refresh updates the session list. Each later open gets
    # those records and retains its own selections, even if edited mid-read.
    updated = asset_library._load_project_catalog(catalog, states[0], use_shared_cache=False)
    assert updated["assets"][0]["image_name"] == new_name
    with patch.object(asset_library, "_asset_manifest_signature", side_effect=AssertionError("re-read after refresh")), \
         patch.object(asset_library, "_catalog_directory_entries", side_effect=AssertionError("re-scanned after refresh")):
        results = concurrent_open(catalog, states)
    for state, result in zip(states, results):
        assert result["assets"][0]["image_name"] == new_name
        assert result["shot_routing"] == state["shot_routing"]
        assert [(a["selected"], a["selection_order"]) for a in result["assets"]] == [
            (a["selected"], a["selection_order"]) for a in state["assets"]]
        live = deepcopy(state)
        live["shot_routing"]["shots"][0]["selected_source_uids"].reverse()
        live["assets"][0]["selected"] = False
        live["assets"][0]["selection_order"] = 0
        live = asset_library._normalize_state(live)
        merged = asset_library._merge_async_scan_result_with_live_state(result, state, live)
        assert merged["shot_routing"] == live["shot_routing"]
        assert not merged["assets"][0]["selected"]
        restored = asset_library._normalize_state(json.loads(json.dumps(merged)))
        assert restored["shot_routing"] == merged["shot_routing"]
        assert restored["assets"] == merged["assets"]
    # Neither returned data nor later edits can mutate the shared snapshot.
    results[0]["assets"][0]["image_name"] = "private edit"
    assert results[1]["assets"][0]["image_name"] != "private edit"
    assert states == originals

    # Key isolation, completion TTL, retries and cache bound are independent
    # of per-node request timeouts. Offline failures must never become cache.
    base = states[0]
    asset_library._SHARED_PROBE_RESULTS.clear()
    reader = lambda: {"rows": ["fresh"]}
    with patch.object(asset_library.time, "monotonic", return_value=100):
        result = asset_library._shared_project_probe_value(base, "test", reader, ttl=3)
    result["rows"].clear()
    with patch.object(asset_library.time, "monotonic", return_value=102):
        assert asset_library._shared_project_probe_value(base, "test", lambda: 0, ttl=3) == {"rows": ["fresh"]}
    with patch.object(asset_library.time, "monotonic", return_value=104):
        assert asset_library._shared_project_probe_value(base, "test", lambda: "expired", ttl=3) == "expired"
    for field in ("catalog_root", "project_root", "project_uid", "project_cache_uid", "manifest_signature", "folder_signature"):
        other = {**base, field: str(base[field]) + "different"}
        assert asset_library._shared_project_probe_value(other, "test", lambda: field, ttl=3) == field
    for _ in range(2):
        try:
            asset_library._shared_project_probe_value(base, "offline", lambda: (_ for _ in ()).throw(PermissionError("offline")), ttl=3)
        except PermissionError:
            pass
        else:
            raise AssertionError("offline probe was silently accepted")
        assert not asset_library._SHARED_PROBE_FLIGHTS
    barrier = threading.Barrier(5)
    failed_reads = []
    def shared_failure():
        barrier.wait(timeout=5)
        def read():
            failed_reads.append(1)
            time.sleep(.1)
            raise PermissionError("shared offline")
        try:
            asset_library._shared_project_probe_value(base, "concurrent_offline", read, ttl=3)
        except PermissionError:
            return True
        return False
    with ThreadPoolExecutor(max_workers=5) as pool:
        assert all(pool.map(lambda _: shared_failure(), range(5)))
    assert len(failed_reads) == 1 and not asset_library._SHARED_PROBE_FLIGHTS
    assert asset_library._shared_project_probe_value(base, "offline", lambda: "reconnected", ttl=3) == "reconnected"
    for number in range(120):
        asset_library._shared_project_probe_value(base, ("bound", number), reader, ttl=3)
    assert len(asset_library._SHARED_PROBE_RESULTS) == asset_library._SHARED_PROBE_LIMIT
print("Session catalog: five nodes with 25 shot UUIDs kept selections and read no manifests or folders on reopen; explicit refresh, legacy ACK and cache isolation: PASS")
print("HMB shared catalog/cache/probe/portable media identity and incremental reuse regression: PASS")
