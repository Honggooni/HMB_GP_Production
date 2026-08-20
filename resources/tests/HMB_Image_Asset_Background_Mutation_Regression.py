from __future__ import annotations

from copy import deepcopy
import importlib.util
import inspect
from pathlib import Path
import sys
import threading
import time


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "HMBImageAssetLibrary.py"
spec = importlib.util.spec_from_file_location(
    "hmb_image_asset_background_mutation_regression",
    MODULE_PATH,
)
assert spec is not None and spec.loader is not None
asset_library = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = asset_library
spec.loader.exec_module(asset_library)


def asset_row(*, registered: bool = False) -> dict:
    return {
        "asset_library_id": "library:slow-registration",
        "source_uid": "project:library:slow-registration",
        "source_kind": "project",
        "relative_path": "Character/Hero.png",
        "path": "C:/catalog/ProjectA/Character/Hero.png",
        "extension": ".png",
        "asset_id": "Hero",
        "image_name": "Hero",
        "registered": registered,
        "selected": False,
        "selection_order": 0,
        "source_type": "Character Appearance" if registered else "",
        "custom_source_type": "",
        "scope_candidate": "Full body / full appearance" if registered else "",
        "color_pick_candidates": [],
        "width": 1,
        "height": 1,
    }


def registration_state() -> tuple[dict, dict]:
    state = asset_library._default_state()
    state.update(
        {
            "catalog_root": "C:/catalog",
            "projects": [
                {
                    "project_id": "ProjectA",
                    "project_uid": "project-a-uid",
                    "name": "ProjectA",
                    "label": "ProjectA",
                    "path": "C:/catalog/ProjectA",
                }
            ],
            "project_root": "C:/catalog/ProjectA",
            "project_id": "ProjectA",
            "project_uid": "project-a-uid",
            "assets": [asset_row()],
        }
    )
    request = {
        "request_id": "slow-registration-request",
        "project_uid": "project-a-uid",
        "asset_library_id": "library:slow-registration",
        "source_kind": "project",
        "source_uid": "project:library:slow-registration",
        "relative_path": "Character/Hero.png",
        "target_folder": "",
        "image_name": "Hero",
        "asset_id": "Hero",
        "source_type": "Character Appearance",
        "custom_source_type": "",
        "scope_candidate": "Full body / full appearance",
    }
    state["asset_registration_request"] = request
    return asset_library._normalize_state(state), request


def fake_node(initial_state: dict):
    node = object.__new__(asset_library.HMBImageAssetLibrary)
    live = {"state": asset_library._normalize_state(initial_state)}
    published = []
    node._hmb_manifest_poll_received = False
    node._hmb_manifest_poll_pending = False
    node._hmb_refresh_revision = live["state"]["refresh_revision"]
    node._hmb_import_media_by_uid = {}
    node._hmb_import_revision = 0
    node._scan_owner_is_current = lambda: True
    node._replace_import_media = lambda _media: None
    node.get_parameter_value = lambda _name: []
    node._current_state = lambda: live["state"]

    def publish(value):
        normalized = asset_library._normalize_state(value)
        live["state"] = normalized
        published.append(normalized)
        return normalized

    node._publish_state = publish
    return node, live, published


def finish_worker(node, live) -> dict:
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        thread = getattr(node, "_hmb_scan_thread", None)
        if thread is not None:
            thread.join(timeout=0.1)
        if node._consume_pending_catalog_scan_result():
            return live["state"]
        if not getattr(node, "_hmb_scan_pending_key", ""):
            return live["state"]
        time.sleep(0.01)
    raise AssertionError("Background mutation did not finish in five seconds.")


# A pending acknowledgement is a UI-only publication.  It must not resolve
# media, read manifests through output synchronization, or reconcile the graph.
pending_publish_node = object.__new__(asset_library.HMBImageAssetLibrary)
pending_publish_node._hmb_root_syncing = False
pending_publish_node._hmb_state_syncing = False
pending_publish_node._hmb_refresh_revision = 0
pending_publish_node.get_parameter_value = lambda _name: ""
pending_publish_node._accept_widget_state_baseline = lambda _state: None
pending_publish_node._cache_shot_routing_snapshot = lambda _state: (_ for _ in ()).throw(
    AssertionError("busy publish resolved Shot media")
)
pending_publish_node._sync_output = lambda _state: (_ for _ in ()).throw(
    AssertionError("busy publish rebuilt outputs")
)
pending_publish_node._reconcile_hmb_shot_routing = lambda *_args: (_ for _ in ()).throw(
    AssertionError("busy publish scanned the graph")
)
original_parameter_setter = asset_library._set_parameter_value
asset_library._set_parameter_value = lambda *_args, **_kwargs: None
try:
    pending_publication = pending_publish_node._publish_state(
        {**asset_library._default_state(), "scan_busy": True}
    )
finally:
    asset_library._set_parameter_value = original_parameter_setter
assert pending_publication["scan_busy"] is True


base, request = registration_state()
node, live, published = fake_node(base)
started = threading.Event()
release = threading.Event()
original_registration = asset_library._apply_asset_registration


def slow_durable_registration(state, request_value, _media):
    assert request_value["request_id"] == request["request_id"]
    started.set()
    if not release.wait(timeout=2.0):
        raise RuntimeError("test worker was executed synchronously")
    result = asset_library._normalize_state(state)
    result["assets"] = [asset_row(registered=True)]
    result["asset_registration_result"] = {
        "request_id": request["request_id"],
        "ok": True,
        "asset_library_id": "library:slow-registration",
        "message": "durable manifest committed",
    }
    return asset_library._normalize_state(result)


asset_library._apply_asset_registration = slow_durable_registration
try:
    before = time.monotonic()
    pending = node._apply_widget_state(base)
    elapsed = time.monotonic() - before
    assert elapsed < 0.5, "Registration callback waited for filesystem work."
    assert started.wait(timeout=1.0)
    assert pending["scan_busy"] is True
    assert pending["asset_registration_request"] == {}
    assert pending["assets"][0]["registered"] is False
    assert pending["asset_registration_result"] == {}
    assert published and published[0]["scan_busy"] is True

    release.set()
    completed = finish_worker(node, live)
    assert completed["scan_busy"] is False
    assert completed["assets"][0]["registered"] is True
    assert completed["asset_registration_result"]["ok"] is True
finally:
    release.set()
    asset_library._apply_asset_registration = original_registration


# Failure acknowledges only the failed intent.  The usable catalog, selection,
# and verification state must remain byte-for-byte equivalent after normalize.
failed_base, _ = registration_state()
failed_base["search"] = "keep this filter"
failed_base = asset_library._normalize_state(failed_base)
failure_snapshot = deepcopy(failed_base)
failure_snapshot["asset_registration_request"] = {}
failure_snapshot = asset_library._normalize_state(failure_snapshot)
failed_node, failed_live, _ = fake_node(failed_base)


def failed_registration(*_args, **_kwargs):
    raise RuntimeError("simulated durable-write rejection")


asset_library._apply_asset_registration = failed_registration
try:
    failed_pending = failed_node._apply_widget_state(failed_base)
    assert failed_pending["scan_busy"] is True
    failed = finish_worker(failed_node, failed_live)
finally:
    asset_library._apply_asset_registration = original_registration

assert failed["assets"] == failure_snapshot["assets"]
assert failed["project_root"] == failure_snapshot["project_root"]
assert failed["search"] == "keep this filter"
assert failed["asset_registration_result"] == {
    "request_id": request["request_id"],
    "ok": False,
    "asset_library_id": request["asset_library_id"],
    "message": "simulated durable-write rejection",
}
assert failed["error"].endswith("simulated durable-write rejection")


# The visible PROJECT_ROOT callback must schedule the generation-owned path,
# never call the synchronous catalog loader directly.
after_set_source = inspect.getsource(asset_library.HMBImageAssetLibrary.after_value_set)
assert "self._schedule_catalog_root_change(value)" in after_set_source
assert "self._load_catalog(value)" not in after_set_source

root_node, root_live, _ = fake_node(failure_snapshot)
root_started = threading.Event()
root_release = threading.Event()
original_catalog_loader = asset_library._load_project_catalog


def slow_root_load(root_value, previous):
    root_started.set()
    if not root_release.wait(timeout=2.0):
        raise RuntimeError("root discovery ran synchronously")
    result = asset_library._normalize_state(previous)
    result["catalog_root"] = str(root_value).replace("\\", "/")
    result["projects"] = []
    result["project_root"] = ""
    result["project_id"] = ""
    result["project_uid"] = ""
    result["assets"] = []
    return asset_library._normalize_state(result)


asset_library._load_project_catalog = slow_root_load
try:
    before = time.monotonic()
    root_pending = root_node._schedule_catalog_root_change("C:/new-catalog")
    elapsed = time.monotonic() - before
    assert elapsed < 0.5, "PROJECT_ROOT callback waited for discovery."
    assert root_started.wait(timeout=1.0)
    assert root_pending["scan_busy"] is True
    assert root_pending["catalog_root"] == "C:/new-catalog"
    # Old verified rows remain visible but outputs are not restaged while busy.
    assert root_pending["assets"] == failure_snapshot["assets"]
    root_release.set()
    root_completed = finish_worker(root_node, root_live)
    assert root_completed["scan_busy"] is False
    assert root_completed["catalog_root"] == "C:/new-catalog"
    assert root_completed["assets"] == []
finally:
    root_release.set()
    asset_library._load_project_catalog = original_catalog_loader


print(
    "HMB image asset background registration/root mutation + pending/rollback "
    "regression: PASS"
)
