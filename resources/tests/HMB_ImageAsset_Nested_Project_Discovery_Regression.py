"""Show-local image roots retain registered assets and five saved Shot addresses."""
from __future__ import annotations

import base64
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import uuid
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from _hmb_project import project_from_asset_payload

spec = importlib.util.spec_from_file_location("hmb_nested_image_projects", ROOT / "HMBImageAssetLibrary.py")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4////fwAJ+wP9KobjigAAAABJRU5ErkJggg==")


def make_project(path: Path, identity: str, *, absolute: bool = False) -> Path:
    (path / "CH").mkdir(parents=True)
    (path / "CH" / "Hero.png").write_bytes(PNG)
    metadata = path / ".json"
    metadata.mkdir()
    manifest = metadata / "hmb_image_assets.json"
    manifest.write_text(json.dumps({
        "schema": "hmb-image-assets", "version": 1,
        "project_cache_uid": "hmbpc1:" + identity * 32,
        "assets": [{"path": (path / "CH" / "Hero.png").as_posix() if absolute else "CH/Hero.png",
                    "asset_id": "Approved_Hero", "image_name": "Registered Hero",
                    "image_main_type": "Character", "image_sub_type": "Full Appearance",
                    "selected": True, "selection_order": 1}],
    }, ensure_ascii=False), encoding="utf-8")
    return manifest


def protected(path: Path) -> tuple[bytes, int, int]:
    facts = path.stat()
    return path.read_bytes(), facts.st_mtime_ns, facts.st_ctime_ns


with tempfile.TemporaryDirectory(prefix="hmb-nested-project-") as temporary:
    projects = Path(temporary) / "projects"
    legacy = projects / "Ai_Ct_image"
    old_sw = legacy / "superwings12"
    old_ka = legacy / "Katuri8"
    sw_manifest = make_project(old_sw, "1")
    make_project(old_ka, "2")
    (projects / "Unrelated_Show" / "pipelines").mkdir(parents=True)
    initial_catalog = module._load_project_catalog(legacy, module._default_state())
    selected = module._select_catalog_project(initial_catalog, old_sw)
    assert [row["name"] for row in initial_catalog["projects"]] == ["Katuri8", "superwings12"]
    assert selected["assets"][0]["selected"] is True
    selected["shot_routing"]["shots"] = [
        {"shot_uuid": str(uuid.uuid4()), "number": number, "name": f"custom_{number}",
         "name_is_custom": True, "selected_source_uids": [selected["assets"][0]["source_uid"]]}
        for number in range(1, 6)
    ]
    selected["shot_routing"]["active_shot_uuid"] = selected["shot_routing"]["shots"][3]["shot_uuid"]
    selected = module._normalize_state(selected)
    before = copy.deepcopy(selected)
    selected["projects"].append({"project_id": "Dinoster5", "name": "Dinoster5", "path": str(legacy / "Dinoster5")})
    new_sw = projects / "superwings12" / "Ai_Ct_image"
    new_sw.parent.mkdir()
    shutil.move(str(old_sw), str(new_sw))
    new_ka = projects / "Katuri8" / "Ai_Ct_image" / "Katuri8"
    new_ka.parent.mkdir(parents=True)
    shutil.move(str(old_ka), str(new_ka))
    legacy.rmdir()  # Saved catalog no longer exists: discovery must still work.
    moved_manifest = new_sw / ".json" / "hmb_image_assets.json"
    original_registration = protected(moved_manifest)
    moved = module._load_project_catalog(legacy, json.loads(json.dumps(selected)), use_shared_cache=False)
    assert moved["catalog_root"] == legacy.as_posix()
    assert [row["name"] for row in moved["projects"]] == ["Katuri8", "superwings12"]
    assert moved["project_root"] == new_sw.as_posix()
    for field in ("project_id", "project_uid", "project_cache_uid", "shot_routing"):
        assert moved[field] == before[field], field
    for field in ("asset_library_id", "source_uid", "asset_id", "image_name", "selected", "selection_order"):
        assert moved["assets"][0][field] == before["assets"][0][field], field
    assert moved["assets"][0]["path"] == (new_sw / "CH" / "Hero.png").as_posix()
    assert moved["tree"]["label"] == "superwings12"
    assert protected(moved_manifest) == original_registration
    assert selected["shot_routing"] == before["shot_routing"]
    assert module._normalize_state(json.dumps(moved)) == moved
    reopened = module._load_project_catalog(legacy, module._normalize_state(json.dumps(moved)), use_shared_cache=False)
    assert reopened["shot_routing"] == moved["shot_routing"]
    assert reopened["assets"][0]["source_uid"] == moved["assets"][0]["source_uid"]
    # The selected project must retain its identity through the actual Image
    # API and serialized Image -> Prompt -> Agent -> Generator transport.
    for routed, expected in ((moved, "superwings12"), (module._select_catalog_project(moved, new_ka), "katuri8")):
        owner = SimpleNamespace(_current_state=lambda state=routed: state)
        assert module.HMBImageAssetLibrary._hmb_project_identity(owner)["project_id"] == expected
        payload = module._build_output_payload(routed)
        assert project_from_asset_payload(json.dumps(payload), default_legacy=False)["project_id"] == expected
    for catalog_root in (legacy, projects, new_sw.parent, new_sw):
        assert module._state_project_belongs_to_catalog(moved, catalog_root), str(catalog_root)
        catalog = module._discover_project_catalog(catalog_root)
        assert any(row["path"] == new_sw.as_posix() for row in catalog["projects"])
    wrong = {**moved, "project_root": (projects / "Katuri8" / "Ai_Ct_image" / "superwings12").as_posix()}
    assert not module._state_project_belongs_to_catalog(wrong, projects)
    assert not module._state_project_belongs_to_catalog({**moved, "project_root": (projects / "superwings12" / "pipelines").as_posix()}, legacy)
    assert not module._state_project_belongs_to_catalog(moved, projects / "Unrelated_Show")
    # The migrated show wins if its stale flat directory remains alongside it.
    make_project(old_sw, "3")
    catalog = module._discover_project_catalog(legacy)
    sw_rows = [row for row in catalog["projects"] if row["project_id"] == "superwings12"]
    assert len(sw_rows) == 1 and sw_rows[0]["path"] == new_sw.as_posix()
    # Case-insensitive Ai_Ct_image and matching nested show names are accepted.
    mixed = projects / "Dinoster5" / "AI_CT_IMAGE" / "dinoster5"
    mixed.mkdir(parents=True)
    assert any(row["path"] == mixed.as_posix() for row in module._discover_project_catalog(legacy)["projects"])
    # An unavailable catalog is an explicit failure, not a valid empty update.
    try:
        module._discover_project_catalog(projects / "unavailable" / "Ai_Ct_image")
    except ValueError:
        pass
    else:
        raise AssertionError("Unavailable project catalog was silently accepted")
    with patch.object(module, "_scan_project_assets", side_effect=AssertionError("Discovery must not scan media")):
        assert module._discover_project_catalog(legacy)["projects"]
    # A denied/unavailable show is not a successful catalog with that project
    # removed. The background owner keeps its prior completed snapshot on error.
    original_is_dir = Path.is_dir
    retained = copy.deepcopy(moved)
    for error in (PermissionError("simulated SMB permission loss"), OSError(10054, "simulated SMB disconnect")):
        def deny_current_project(path):
            if path == new_sw:
                raise error
            return original_is_dir(path)
        with patch.object(Path, "is_dir", deny_current_project):
            try:
                module._load_project_catalog(legacy, moved)
            except OSError:
                pass
            else:
                raise AssertionError("SMB failure was published as a missing project")
    assert moved == retained


with tempfile.TemporaryDirectory(prefix="hmb-nested-manifest-") as temporary:
    projects = Path(temporary) / "projects"
    old = projects / "Ai_Ct_image" / "superwings12"
    manifest = make_project(old, "4", absolute=True)
    original = protected(manifest)
    new = projects / "superwings12" / "Ai_Ct_image"
    (new / "CH").mkdir(parents=True)
    shutil.copy2(old / "CH" / "Hero.png", new / "CH" / "Hero.png")
    scan = module._scan_project_assets(new)
    assert scan["project_id"] == "superwings12"
    assert scan["project_cache_uid"] == "hmbpc1:" + "4" * 32
    assert scan["assets"][0]["registered"] is True
    assert scan["assets"][0]["asset_id"] == "Approved_Hero"
    assert scan["assets"][0]["path"] == (new / "CH" / "Hero.png").as_posix()
    assert protected(manifest) == original
    original_read_text = Path.read_text
    def deny_legacy_metadata(path, *args, **kwargs):
        if path == manifest:
            raise PermissionError("simulated registration lock")
        return original_read_text(path, *args, **kwargs)
    module._invalidate_asset_manifest_cache(new)
    with patch.object(Path, "read_text", deny_legacy_metadata):
        try:
            module._scan_project_assets(new)
        except ValueError:
            pass
        else:
            raise AssertionError("Locked legacy metadata was treated as unregistered images")
    assert protected(manifest) == original
    review = module._audit_project_manifest_refresh(new)
    assert review["registered_count"] == review["file_count"] == 1
    assert review["unregistered_count"] == review["missing_count"] == 0
    assert review["safe_to_clean"] is False  # Never clean a legacy fallback file.
    try:
        module._clean_project_manifest_refresh(review, lambda: True)
    except ValueError:
        pass
    else:
        raise AssertionError("Legacy metadata cleanup was allowed")
    # An explicit Add writes to the new project, retains prior registrations,
    # and never edits or moves the original shared registration document.
    (new / "CH" / "New.png").write_bytes(PNG)
    saved = module._write_asset_manifest_record(new, {"path": "CH/New.png", "asset_id": "New", "image_name": "New"})
    assert saved == new / ".json" / "hmb_image_assets.json"
    assert protected(manifest) == original
    local = json.loads(saved.read_text(encoding="utf-8"))
    assert local["assets"][0]["path"] == "CH/Hero.png"
    assert local["project_cache_uid"] == "hmbpc1:" + "4" * 32
    # A project-local manifest takes precedence over the former registration.
    local["assets"][0]["asset_id"] = "NEW_PROJECT_WINS"
    saved.write_text(json.dumps(local), encoding="utf-8")
    with patch.object(Path, "read_text", deny_legacy_metadata):
        assert module._scan_project_assets(new)["assets"][0]["asset_id"] == "NEW_PROJECT_WINS"
    assert protected(manifest) == original
    other = projects / "Katuri8" / "Ai_Ct_image"
    other.mkdir(parents=True)
    assert module._existing_asset_manifest_path(other) is None


new_production = Path("//192.168.200.19/v/projects/superwings12/Ai_Ct_image")
for prefix in ("P:/projects/Ai_Ct_image/superwings12", "//192.168.200.19/v/projects/Ai_Ct_image/superwings12",
               "//fin-rcomp1/Composite_Team/projects_AI/superwings12"):
    assert module._manifest_asset_relative_path(new_production, {"path": prefix + "/CH/Hero.png"}) == "CH/Hero.png"
for path in ("P:/projects/Ai_Ct_image/Katuri8/CH/Hero.png", "P:/projects/Ai_Ct_image/superwings12_old/CH/Hero.png",
             "P:/other/superwings12/CH/Hero.png", "../Other/Hero.png", "CH/../Hero.png"):
    assert module._manifest_asset_relative_path(new_production, {"path": path}) == "", path
assert module._manifest_asset_relative_path(new_production, {"path": "P:/other/Hero.png", "relative_path": "CH/Hero.png"}) == "CH/Hero.png"
print("Nested ImageAsset discovery, legacy metadata reads, path fencing, five Shot save/reopen and immutable registrations: PASS")
