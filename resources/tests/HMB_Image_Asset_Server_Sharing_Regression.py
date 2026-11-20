from __future__ import annotations

import importlib.util
from io import BytesIO
import json
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hmb_image_asset_detached_fixture import initialize_detached_image_asset

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "HMBImageAssetLibrary.py"
TEMP_ROOT = ROOT / ".tmp"
TEMP_ROOT.mkdir(parents=True, exist_ok=True)

spec = importlib.util.spec_from_file_location("hmb_asset_server_sharing_test", MODULE_PATH)
assert spec is not None and spec.loader is not None
asset_library = importlib.util.module_from_spec(spec)
spec.loader.exec_module(asset_library)


assert asset_library._project_uid(Path(r"C:\Local\ProjectA")) == asset_library._project_uid(
    Path(r"Z:\Shared\ProjectA")
)
assert asset_library._project_uid(Path(r"Z:\Shared\ProjectA")) == asset_library._project_uid(
    Path(r"\\SERVER\Assets\ProjectA")
)
assert asset_library._project_uid(Path(r"C:\Local\ProjectA")) != asset_library._project_uid(
    Path(r"C:\Local\ProjectB")
)


from PIL import Image

png_buffer = BytesIO()
Image.new("RGB", (8, 8), (210, 40, 110)).save(png_buffer, format="PNG")
PNG_BYTES = png_buffer.getvalue()


with tempfile.TemporaryDirectory(prefix="hmb_asset_share_", dir=TEMP_ROOT) as temporary:
    # Cache writes belong to this test's disposable tree, never the user's
    # LocalAppData cache (also when run outside the clean-CI environment).
    asset_library._ASSET_THUMBNAIL_CACHE_ROOT = Path(temporary) / "thumbnail-cache"
    asset_library._ASSET_CATALOG_INDEX_ROOT = Path(temporary) / "catalog-index"
    catalog_root = Path(temporary) / "catalog"
    project_root = catalog_root / "ProjectA"
    project_root.mkdir(parents=True)
    hero_path = project_root / "Hero.png"
    hero_path.write_bytes(PNG_BYTES)
    keep_folder = project_root / "Keep_User_Folder"
    keep_folder.mkdir()

    previous = asset_library._default_state()
    previous.update(
        {
            "catalog_root": "C:/OldMount",
            "project_root": "C:/OldMount/ProjectA",
            "project_id": "ProjectA",
            "project_uid": "ProjectA:legacy-absolute-path-hash",
        }
    )
    restored = asset_library._load_project_catalog(catalog_root, previous)
    assert Path(restored["project_root"]).resolve() == project_root.resolve()
    assert restored["project_uid"] == asset_library._project_uid(project_root)

    entries_before_reload = sorted(path.name for path in project_root.iterdir())
    prepared = asset_library._load_project_catalog(catalog_root, restored)
    assert sorted(path.name for path in project_root.iterdir()) == entries_before_reload
    assert keep_folder.is_dir(), "Catalog loading must not modify user-created folders."

    missing_signature = prepared["manifest_signature"]
    hero_record = {
        "path": "Hero.png",
        "asset_id": "Hero",
        "image_name": "Hero",
        "source_type": "Character Appearance",
        "custom_source_type": "",
        "scope": "Full body / full appearance",
    }
    asset_library._write_asset_manifest_record(project_root, hero_record)
    metadata_root = project_root / asset_library.ASSET_METADATA_DIRECTORY_NAME
    process_lock = metadata_root / asset_library.ASSET_MANIFEST_LOCK_NAME
    manifest_path = metadata_root / asset_library.MANIFEST_NAMES[0]
    assert process_lock.is_file()
    assert process_lock.stat().st_size >= 1
    assert manifest_path.is_file()
    assert not (project_root / asset_library.ASSET_MANIFEST_LOCK_NAME).exists()
    assert not (project_root / asset_library.MANIFEST_NAMES[0]).exists()
    registered_signature = asset_library._asset_manifest_signature(project_root)
    assert registered_signature != missing_signature

    # Another writer registered this image. Reopening the saved workflow
    # within this session keeps its previous view until the user refreshes.
    pinned = asset_library._load_project_catalog(catalog_root, prepared)
    assert pinned["manifest_signature"] == missing_signature
    assert not any(item["registered"] for item in pinned["assets"])
    registered_state = asset_library._load_project_catalog(catalog_root, pinned, use_shared_cache=False)
    hero_asset = next(
        item for item in registered_state["assets"] if item["relative_path"] == "Hero.png"
    )
    assert hero_asset["registered"] is True
    assert asset_library.ASSET_METADATA_DIRECTORY_NAME not in registered_state["folders"]
    hero_asset["selected"] = True
    hero_asset["selection_order"] = 1
    registered_state = asset_library._normalize_state(registered_state)

    sidekick_path = project_root / "Sidekick.png"
    sidekick_path.write_bytes(PNG_BYTES)
    asset_library._write_asset_manifest_record(project_root, {
        **hero_record, "path": "Sidekick.png", "asset_id": "Sidekick", "image_name": "Sidekick",
    })
    registration = asset_library._asset_manifest_signature(project_root)
    assert registration != registered_signature

    node = object.__new__(asset_library.HMBImageAssetLibrary)
    registered_state = initialize_detached_image_asset(node, asset_library, state=registered_state)
    widget_parameter = SimpleNamespace(name=asset_library.WIDGET_STATE_PARAMETER)
    payload = {**registered_state, "__hmb_manifest_poll_nonce": "old-widget"}
    with patch.object(asset_library, "_asset_manifest_signature", side_effect=AssertionError("implicit manifest read")), \
         patch.object(asset_library, "_catalog_directory_entries", side_effect=AssertionError("implicit folder scan")):
        canonical = node.before_value_set(widget_parameter, json.dumps(payload))
        assert "__hmb_manifest_poll_nonce" not in json.loads(canonical)
        assert not getattr(node, "_hmb_manifest_poll_pending", False)
        assert not getattr(node, "_hmb_manifest_poll_received", False)
        unchanged = asset_library._load_project_catalog(catalog_root, registered_state)
        assert unchanged["manifest_signature"] == registered_signature
        assert [row["asset_id"] for row in unchanged["assets"]] == ["Hero"]

    refreshed = asset_library._load_project_catalog(catalog_root, unchanged, use_shared_cache=False)
    assert refreshed["manifest_signature"] == registration
    assert refreshed["status"]["registered_asset_count"] == 2
    assert [row["asset_id"] for row in refreshed["assets"] if row["selected"]] == ["Hero"]
    assert next(row for row in refreshed["assets"] if row["selected"])["selection_order"] == 1
    assert refreshed["shot_routing"] == unchanged["shot_routing"]

    captured_thumbnail_bytes = []

    class FakeStaticFilesManager:
        def save_static_file(self, value, filename):
            captured_thumbnail_bytes.append(bytes(value))
            return f"http://localhost:8124/workspace/static_files/{filename}"

    class FakeGriptapeNodes:
        StaticFilesManager = FakeStaticFilesManager

    module_names = (
        "griptape_nodes",
        "griptape_nodes.retained_mode",
        "griptape_nodes.retained_mode.griptape_nodes",
    )
    saved_modules = {name: sys.modules.get(name) for name in module_names}
    package = ModuleType(module_names[0])
    package.__path__ = []
    retained = ModuleType(module_names[1])
    retained.__path__ = []
    leaf = ModuleType(module_names[2])
    leaf.GriptapeNodes = FakeGriptapeNodes
    sys.modules[module_names[0]] = package
    sys.modules[module_names[1]] = retained
    sys.modules[module_names[2]] = leaf
    try:
        asset_library._ASSET_THUMBNAIL_URLS.clear()
        thumbnail_url = asset_library._asset_thumbnail_url(hero_path, "hero-library-id")
        assert thumbnail_url.startswith("http://localhost:8124/workspace/static_files/")
        assert captured_thumbnail_bytes
    finally:
        for name, saved in saved_modules.items():
            if saved is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = saved


print(
    "HMB shared Asset path portability + HTTP thumbnail + manual session refresh "
    "+ no-folder-creation regression: PASS"
)
