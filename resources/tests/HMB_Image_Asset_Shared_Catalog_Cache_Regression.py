from __future__ import annotations

from copy import deepcopy
from io import BytesIO
import importlib.util
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time


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
    temporary_root = Path(temporary)
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

    # Raw files are admitted only after the background worker confirms one
    # stable second; the browser need not wait for a second 10-second poll.
    probe_node = object.__new__(asset_library.HMBImageAssetLibrary)
    probe_node._hmb_catalog_probe_last_manifest_at = 0.0
    probe_node._hmb_catalog_probe_last_folder_at = 0.0
    probe_node._hmb_catalog_probe_pending_folder_signature = ""
    probe_node._hmb_catalog_probe_pending_folder_since = 0.0
    sidekick = project_a / "Sidekick.png"
    sidekick.write_bytes(png_bytes((20, 80, 220)))
    request = {"probe_kind": "folder"}
    outcome, changed = probe_node._compute_catalog_probe(state, request)
    assert outcome == "changed" and changed is not None
    assert {item["relative_path"] for item in changed["assets"]} == {
        "Hero.png",
        "Sidekick.png",
    }

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
    # reopening never displays a stale catalog for another 10-20 seconds.
    asset_library._write_catalog_index(rescanned)
    raw_added = project_a / "RawAdded.png"
    raw_added.write_bytes(png_bytes((40, 50, 60)))
    previous_for_index = {**asset_library._default_state(), **rescanned}
    previous_for_index["catalog_root"] = str(catalog_a)
    assert asset_library._read_catalog_index(project_a, previous_for_index) is None


print("HMB shared catalog/cache/probe/portable media identity regression: PASS")
