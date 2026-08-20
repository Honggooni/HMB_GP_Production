from __future__ import annotations

import importlib.util
from io import BytesIO
import json
from pathlib import Path
import sys
import tempfile
import time
from types import ModuleType, SimpleNamespace


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

    registered_state = asset_library._load_project_catalog(catalog_root, prepared)
    hero_asset = next(
        item for item in registered_state["assets"] if item["relative_path"] == "Hero.png"
    )
    assert hero_asset["registered"] is True
    assert asset_library.ASSET_METADATA_DIRECTORY_NAME not in registered_state["folders"]
    hero_asset["selected"] = True
    hero_asset["selection_order"] = 1
    registered_state = asset_library._normalize_state(registered_state)

    node = object.__new__(asset_library.HMBImageAssetLibrary)
    node._hmb_import_media_by_uid = {}
    node._hmb_last_manifest_poll_error = ""
    node.get_parameter_value = lambda _name: []
    node._publish_state = lambda state: asset_library._normalize_state(state)

    original_scan = asset_library._scan_project_assets
    scan_count = 0

    def counted_scan(project_root_value):
        global scan_count
        scan_count += 1
        return original_scan(project_root_value)

    asset_library._scan_project_assets = counted_scan
    try:
        unchanged = node._apply_manifest_poll(registered_state)
        assert scan_count == 0
        assert unchanged["manifest_signature"] == registered_signature

        sidekick_path = project_root / "Sidekick.png"
        sidekick_path.write_bytes(PNG_BYTES)
        asset_library._write_asset_manifest_record(
            project_root,
            {
                "path": "Sidekick.png",
                "asset_id": "Sidekick",
                "image_name": "Sidekick",
                "source_type": "Character Appearance",
                "custom_source_type": "",
                "scope": "Head / face only",
            },
        )
        refreshed = node._apply_manifest_poll(registered_state)
        assert scan_count == 1
        assert refreshed["status"]["registered_asset_count"] == 2
        selected = [item for item in refreshed["assets"] if item["selected"]]
        assert [item["asset_id"] for item in selected] == ["Hero"]
        assert selected[0]["selection_order"] == 1
    finally:
        asset_library._scan_project_assets = original_scan

    poll_node = object.__new__(asset_library.HMBImageAssetLibrary)
    poll_node._hmb_last_manifest_poll_nonce = ""
    poll_node._hmb_manifest_poll_pending = False
    widget_parameter = SimpleNamespace(name=asset_library.WIDGET_STATE_PARAMETER)
    poll_payload = dict(registered_state)
    poll_payload["__hmb_manifest_poll_nonce"] = "poll-one"
    canonical = poll_node.before_value_set(widget_parameter, json.dumps(poll_payload))
    assert poll_node._hmb_manifest_poll_pending is True
    assert "__hmb_manifest_poll_nonce" not in json.loads(canonical)

    no_op_node = object.__new__(asset_library.HMBImageAssetLibrary)
    no_op_node._hmb_manifest_poll_received = False
    no_op_node._hmb_manifest_poll_pending = False
    no_op_node._hmb_last_manifest_poll_nonce = ""
    no_op_node._hmb_last_manifest_poll_error = ""
    no_op_node._hmb_refresh_revision = refreshed["refresh_revision"]
    no_op_node._hmb_import_media_by_uid = {}
    no_op_node.get_parameter_value = lambda name: (
        refreshed["catalog_root"]
        if name == asset_library.PROJECT_ROOT_PARAMETER
        else []
    )
    no_op_node._sync_output = lambda _state: (_ for _ in ()).throw(
        AssertionError("An unchanged manifest probe must not rebuild outputs.")
    )
    published_states = []
    live_state = {"value": refreshed}

    def publish_without_output_rebuild(value):
        normalized = asset_library._normalize_state(value)
        live_state["value"] = normalized
        published_states.append(normalized)
        return normalized

    no_op_node._publish_state = publish_without_output_rebuild
    no_op_node._current_state = lambda: live_state["value"]
    no_op_node._replace_import_media = lambda _media: None
    no_op_node._scan_owner_is_current = lambda: True
    no_op_node._hmb_import_revision = 0
    no_op_payload = dict(refreshed)
    no_op_payload["__hmb_manifest_poll_nonce"] = "poll-no-change"
    no_op_canonical = no_op_node.before_value_set(
        widget_parameter,
        json.dumps(no_op_payload),
    )
    assert no_op_node._hmb_manifest_poll_received is True
    assert no_op_node._hmb_manifest_poll_pending is True

    # The value-set hook performs no filesystem I/O.  The retained-mode apply
    # schedules one worker probe, and an unchanged signature must avoid a full
    # project scan as well as the output rebuild guarded above.
    no_op_scan_count = [0]
    original_scan = asset_library._scan_project_assets

    def no_op_counted_scan(project_root_value):
        no_op_scan_count[0] += 1
        return original_scan(project_root_value)

    asset_library._scan_project_assets = no_op_counted_scan
    try:
        scheduled = no_op_node._apply_widget_state(no_op_canonical)
        assert scheduled["scan_busy"] is True
        worker = no_op_node._hmb_scan_thread
        assert worker is not None
        worker.join(timeout=10.0)
        assert worker.is_alive() is False
        deadline = time.monotonic() + 2.0
        while (
            no_op_node._hmb_scan_pending_result is None
            and time.monotonic() < deadline
        ):
            time.sleep(0.01)
        assert no_op_node._consume_pending_catalog_scan_result() is True
    finally:
        asset_library._scan_project_assets = original_scan
    assert no_op_scan_count[0] == 0
    no_op_result = live_state["value"]
    assert no_op_result["scan_busy"] is False
    assert no_op_result["manifest_signature"] == refreshed["manifest_signature"]
    assert len(published_states) == 2

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
    "HMB shared Asset path portability + HTTP thumbnail + manifest auto-sync "
    "+ no-folder-creation regression: PASS"
)
