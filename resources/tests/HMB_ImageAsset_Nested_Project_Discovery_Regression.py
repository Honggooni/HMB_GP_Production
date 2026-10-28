"""Official show/Ai_Ct_image only; retired addresses are one-way saved-data replacements."""
from __future__ import annotations
import base64
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from contextlib import ExitStack
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("hmb_direct_project_regression", ROOT / "HMBImageAssetLibrary.py")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
refresh_spec = importlib.util.spec_from_file_location("hmb_direct_refresh_fixture", ROOT / "resources/tests/HMB_Image_Asset_Refresh_Cleanup_Regression.py")
refresh_fixture = importlib.util.module_from_spec(refresh_spec)
refresh_spec.loader.exec_module(refresh_fixture)
refresh_fixture.library = module
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4////fwAJ+wP9KobjigAAAABJRU5ErkJggg==")


def make_project(root: Path, key: str, absolute_record: str = "") -> Path:
    (root / "CH").mkdir(parents=True)
    (root / "CH" / "Hero.png").write_bytes(PNG)
    (root / ".json").mkdir()
    manifest = root / ".json" / "hmb_image_assets.json"
    manifest.write_text(json.dumps({"schema": "hmb-image-assets", "version": 1,
        "project_cache_uid": "hmbpc1:" + key * 32,
        "assets": [{"path": absolute_record or "CH/Hero.png", "asset_id": "Approved_Hero",
        "image_name": "Registered Hero", "image_main_type": "Character",
        "image_sub_type": "Full Appearance", "selected": True, "selection_order": 1}]}), encoding="utf-8")
    return manifest


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def guard_old_io(stack, retired):
    """Any attempt to inspect/open retired storage is a test failure, even if it exists."""
    prefixes = [str(item).replace("\\", "/").rstrip("/").casefold() for item in retired]
    def check(value):
        text = str(value).replace("\\", "/").rstrip("/").casefold()
        assert not any(text == prefix or text.startswith(prefix + "/") for prefix in prefixes), "Retired storage IO: " + text
    for name in ("stat", "lstat", "resolve", "iterdir", "open"):
        original = getattr(Path, name)
        def checked(path, *args, _original=original, **kwargs):
            check(path)
            return _original(path, *args, **kwargs)
        stack.enter_context(patch.object(Path, name, checked))
    original_scandir = os.scandir
    def checked_scandir(path):
        check(path)
        return original_scandir(path)
    stack.enter_context(patch.object(os, "scandir", checked_scandir))


with tempfile.TemporaryDirectory(prefix="hmb-direct-image-projects-") as temporary:
    base = Path(temporary).resolve()
    projects = base / "projects"
    old_catalog = projects / "Ai_Ct_image"
    old = old_catalog / "superwings12"
    sw = projects / "superwings12" / "Ai_Ct_image"
    ka = projects / "Katuri8" / "Ai_Ct_image"
    sw_manifest = make_project(sw, "1", (old / "CH" / "Hero.png").as_posix())
    ka_manifest = make_project(ka, "2")
    # Deliberately present but forbidden old locations must never win or be read.
    retired_nested = sw / "superwings12"
    retired_nested.mkdir()
    old_catalog.mkdir()
    (projects / "Unrelated_Show" / "pipelines").mkdir(parents=True)
    registration_before = {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in (sw_manifest, ka_manifest)}
    with ExitStack() as stack:
        guard_old_io(stack, [old_catalog, retired_nested])
        stack.enter_context(patch.object(module, "_ASSET_CATALOG_INDEX_ROOT", base / "catalog-cache"))
        catalog = module._load_project_catalog(projects, module._default_state(), use_shared_cache=False)
        assert [row["name"] for row in catalog["projects"]] == ["Katuri8", "superwings12"]
        selected = module._select_catalog_project(catalog, sw)
        selected["shot_routing"]["shots"] = [
            {"shot_uuid": str(uuid.uuid4()), "number": number, "name": f"e201s00{number}c001__",
             "name_is_custom": True, "selected_source_uids": [selected["assets"][0]["source_uid"]],
             "revision": number, "metadata_sha256": str(number) * 64, "media_sha256": str(number) * 64}
            for number in range(1, 6)]
        selected["shot_routing"]["active_shot_uuid"] = selected["shot_routing"]["shots"][3]["shot_uuid"]
        selected = module._normalize_state(selected)
        before = copy.deepcopy(selected)
        downstream = [{"binding": {"channel_uuid": before["shot_routing"]["channel_uuid"],
                        "shot_uuid": shot["shot_uuid"], "publisher_instance_uuid": before["shot_routing"]["publisher_instance_uuid"]},
                       "inputs": {"prompt": f"authored prompt {index}", "model": "retained model", "seed": index},
                       "outputs": {"text": f"authored result {index}", "task_id": f"existing-job-{index}",
                                   "video_url": f"C:/existing/result-{index}.mov"}}
                      for index, shot in enumerate(before["shot_routing"]["shots"], 1)]
        authored_hash = digest(downstream)
        old_saved = json.loads(json.dumps(before).replace(sw.as_posix(), old.as_posix()).replace(projects.as_posix() + '",', old_catalog.as_posix() + '",'))
        old_saved["catalog_root"] = old_catalog.as_posix()
        workflow = {"image": old_saved, "bound_nodes": copy.deepcopy(downstream)}
        moved = module._load_project_catalog(old_catalog, workflow["image"], use_shared_cache=False)
        for key in ("project_id", "project_uid", "project_cache_uid", "shot_routing"):
            assert moved[key] == before[key], key
        for key in ("asset_library_id", "asset_project_uid", "source_uid", "asset_id", "image_name", "selected", "selection_order"):
            assert moved["assets"][0][key] == before["assets"][0][key], key
        assert moved["catalog_root"] == projects.as_posix()
        assert moved["project_root"] == sw.as_posix()
        assert moved["assets"][0]["path"] == (sw / "CH" / "Hero.png").as_posix()
        assert moved["project_cache_uid"] == "hmbpc1:" + "1" * 32
        assert module._project_folder_metadata_signature(old)
        audit = module._audit_project_manifest_refresh(old)
        assert not audit["error"], audit
        assert audit["registered_count"] == audit["file_count"] == 1
        assert audit["missing_count"] == audit["unregistered_count"] == 0
        # Exercise the actual asynchronous Refresh path that previously audited
        # the retired root and returned WinError3 before catalog discovery.
        owner, live, published = refresh_fixture.fake_node(old_saved)
        pending = owner._schedule_project_manifest_refresh(old_saved, old_catalog.as_posix(), [])
        assert pending["scan_busy"]
        refreshed = refresh_fixture.finish_worker(owner, live)
        assert refreshed["asset_refresh_review"]["status"] == "review", refreshed.get("error")
        assert not refreshed["error"]
        assert refreshed["project_root"] == sw.as_posix()
        assert refreshed["shot_routing"] == before["shot_routing"]
        assert refreshed["assets"][0]["source_uid"] == before["assets"][0]["source_uid"]
        for address in (projects, old_catalog, sw.parent, sw, retired_nested):
            assert module._state_project_belongs_to_catalog(moved, address)
            assert any(row["path"] == sw.as_posix() for row in module._discover_project_catalog(address)["projects"])
        # Five saved consumers retain their individual inputs, Task IDs and results.
        workflow["image"] = moved
        reopened_workflow = json.loads(json.dumps(workflow))
        reopened = module._load_project_catalog(reopened_workflow["image"]["catalog_root"], reopened_workflow["image"], use_shared_cache=False)
        assert reopened["shot_routing"] == before["shot_routing"]
        assert digest(reopened_workflow["bound_nodes"]) == authored_hash
        for consumer in reopened_workflow["bound_nodes"]:
            assert consumer["binding"]["channel_uuid"] == reopened["shot_routing"]["channel_uuid"]
            assert consumer["binding"]["shot_uuid"] in {shot["shot_uuid"] for shot in reopened["shot_routing"]["shots"]}
        # Missing new storage must fail; it must not fall back to the old share.
        try:
            module._scan_project_assets(old_catalog / "MissingShow")
        except ValueError:
            pass
        else:
            raise AssertionError("Missing official project silently accepted")
        # A later show is discovered by the same direct rule; name case is preserved.
        future = projects / "FutureShow" / "AI_CT_IMAGE"
        future.mkdir(parents=True)
        assert any(row["path"] == future.as_posix() for row in module._discover_project_catalog(projects)["projects"])
    # A show vanishing from the same catalog is not a user request to clear
    # its project, assets, or five saved Shot identities.
    displaced = base / "temporarily-unavailable-show"
    sw.rename(displaced)
    try:
        try:
            module._load_project_catalog(projects, moved, use_shared_cache=False)
        except ValueError as exc:
            assert "no longer available" in str(exc)
        else:
            raise AssertionError("Disappeared selected project was silently cleared")
        assert moved["shot_routing"] == before["shot_routing"]
        assert moved["assets"] == before["assets"]
        assert digest(workflow["bound_nodes"]) == authored_hash
    finally:
        displaced.rename(sw)
    for path in (sw_manifest, ka_manifest):
        assert (path.read_bytes(), path.stat().st_mtime_ns) == registration_before[str(path)]
    # A specifically configured independent catalog remains supported.
    custom = base / "artist-projects"
    make_project(custom / "CustomA", "3")
    assert module._discover_project_catalog(custom)["projects"][0]["path"] == (custom / "CustomA").as_posix()

new_root = Path("//192.168.200.19/v/projects/superwings12/Ai_Ct_image")
for prefix in ("P:/projects/Ai_Ct_image/superwings12", "//192.168.200.19/v/projects/Ai_Ct_image/superwings12",
               "//fin-rcomp1/Composite_Team/projects_AI/superwings12", "P:/projects/superwings12/Ai_Ct_image/superwings12"):
    assert module._manifest_asset_relative_path(new_root, {"path": prefix + "/CH/Hero.png"}) == "CH/Hero.png"
for address in ("P:/projects/Ai_Ct_image/Katuri8/CH/Hero.png", "P:/projects/Ai_Ct_image/superwings12_old/CH/Hero.png",
                "P:/other/superwings12/CH/Hero.png", "../Other/Hero.png", "CH/../Hero.png"):
    assert module._manifest_asset_relative_path(new_root, {"path": address}) == "", address
print("Direct project discovery; retired IO=0; new JSON immutable; five Shot UUID/channel/input/result save-reopen preservation: PASS")
