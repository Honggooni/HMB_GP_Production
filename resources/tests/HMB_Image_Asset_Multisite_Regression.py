"""Physical-store routing and saved Shot restoration across independent image-library engines."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import json
import multiprocessing
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch
from HMB_ImageAsset_Concurrent_Add_Regression import deselect_connected_import

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def station(workspace):
    workspace.mkdir(exist_ok=True)
    os.environ["GTN_CONFIG_WORKSPACE_DIRECTORY"] = str(workspace)
    os.environ["HMB_IMAGE_THUMBNAIL_CACHE"] = str(workspace / "thumbs")
    import HMBImageAssetLibrary as lib
    # The CLI engine has no StaticFiles HTTP publisher.
    lib._asset_thumbnail_url = lambda _path, key, *_args, **_kw: f"memory://{key}"
    return lib


def load(lib, catalog, previous=None):
    state = lib._load_project_catalog(catalog, previous or {})
    if not state["project_root"]:
        state = lib._select_catalog_project(state, state["projects"][0]["path"])
    assert not state["error"], state["error"]
    return state


def paths(root):
    return [root / name / "projects" / "superwings12" / "Ai_Ct_image" for name in ("hq", "gwangju", "busan")]


def register(station_name, directory, barrier):
    root = Path(directory)
    lib = station(root / ("pc-" + station_name))
    hq, gwangju, busan = paths(root)
    catalog = hq.parents[1]
    settings = lib.save_site_settings(hq, [
        {"id": "gwangju", "label": "광주", "root": str(gwangju)},
        {"id": "busan", "label": "부산", "root": str(busan)}], station_name, "0")
    site = settings["write_site_id"]
    counts = Counter()
    scan = lib._scan_project_assets

    def counted(path, **kwargs):
        counts[Path(path).name + "-" + Path(path).parents[2].name] += 1
        return scan(path, **kwargs)

    with patch.object(lib, "_scan_project_assets", side_effect=counted):
        state = load(lib, catalog)
        assert sorted(counts.values()) == [1, 1, 1], counts
        assert all((path / ".json").is_dir() for path in (hq, gwangju, busan))
        assert not (gwangju / ".json" / "hmb_image_assets.json").exists()
        anchor = next(row for row in state["assets"] if row["asset_id"] == "Existing")
        anchor.update(selected=True, selection_order=1)
        shot = state["shot_routing"]["shots"][0]
        shot["selected_source_uids"] = [anchor["source_uid"]]
        for _ in range(4):
            state = load(lib, catalog, state)
            assert state["shot_routing"]["shots"][0]["selected_source_uids"] == [anchor["source_uid"]]
        assert sorted(counts.values()) == [1, 1, 1], counts
        source = root / ("pc-" + station_name) / "repeated.png"
        from PIL import Image
        Image.new("RGB", (9, 6), "red" if site == "hq" else "blue").save(source)
        state, media = lib._merge_import_input(state, [str(source)])
        incoming = next(a for a in state["assets"] if a["source_kind"] == "user")
        assert state["shot_routing"]["shots"][0]["selected_source_uids"] == [anchor["source_uid"], incoming["source_uid"]]
        if site != "hq":
            state = deselect_connected_import(state, incoming["source_uid"])
            assert state["shot_routing"]["shots"][0]["selected_source_uids"] == [anchor["source_uid"]]
        request = {"request_id": "add-" + station_name, "project_uid": state["project_uid"],
                   "asset_library_id": incoming["asset_library_id"], "source_uid": incoming["source_uid"],
                   "source_kind": "user", "target_folder": "CH" if site == "hq" else f"site:{site}/CH",
                   "asset_id": "DuplicateLabel", "image_name": "Common", "image_main_type": "Custom / Context",
                   "image_sub_type": "Context", "site_settings_revision": settings["revision"]}
        wrong = {**request, "target_folder": f"site:{settings['links'][1]['id']}/CH"}
        try:
            lib._apply_asset_registration(state, wrong, media)
        except ValueError:
            pass
        else:
            raise AssertionError("peer received a write")
        barrier.wait(25)
        result = lib._apply_asset_registration(state, request, media)
        assert result["asset_registration_result"]["ok"]
        assert sorted(counts.values()) == [1, 1, 1], counts
        registered = next(a for a in result["assets"] if a["registered"] and a["import_source_uid"] == incoming["source_uid"])
        assert registered["source_uid"] != incoming["source_uid"]
        assert (registered["selected"], registered["selection_order"]) == ((True, 2) if site == "hq" else (False, 0))
        expected_after = [anchor["source_uid"], registered["source_uid"]] if site == "hq" else [anchor["source_uid"]]
        assert result["shot_routing"]["shots"][0]["selected_source_uids"] == expected_after
        barrier.wait(25)
        frozen = load(lib, catalog, result)
        assert frozen["shot_routing"]["shots"][0]["selected_source_uids"] == expected_after
        assert sum(a["registered"] and a["asset_id"] == "DuplicateLabel" for a in frozen["assets"]) == 1
        refreshed = lib._load_project_catalog(catalog, frozen, use_shared_cache=False)
        assert sorted(counts.values()) == [2, 2, 2], counts
        assert sum(a["registered"] and a["asset_id"] == "DuplicateLabel" for a in refreshed["assets"]) == 2
        assert refreshed["shot_routing"]["shots"][0]["selected_source_uids"] == expected_after
        additions = sorted((a for a in refreshed["assets"] if a["registered"] and a["asset_id"] == "DuplicateLabel"),
                           key=lambda a: a["relative_path"])
        order = [anchor["source_uid"]]
        for added in additions:
            order.append(added["source_uid"])
            added.update(selected=True, selection_order=len(order))
        refreshed["shot_routing"]["shots"][0]["selected_source_uids"] = order
        saved = root / ("workflow-" + station_name + ".json")
        saved.write_text(json.dumps(refreshed), encoding="utf-8")


def reopened(station_name, directory):
    root = Path(directory)
    lib = station(root / ("pc-" + station_name))
    hq, gwangju, busan = paths(root)
    catalog = hq.parents[1]
    settings = lib.get_site_settings(hq)
    assert len(settings["links"]) == 2
    saved = json.loads((root / ("workflow-" + station_name + ".json")).read_text("utf-8"))
    # A workstation can open a saved shot before Windows reconnects its mapped drive.
    # Read the persisted index first, then reconnect without changing either registration.
    with patch.object(lib, "_discover_shared_image_projects", side_effect=OSError("share not mounted")), \
            patch.object(lib, "_read_asset_manifest", side_effect=AssertionError("offline registry read")):
        offline = load(lib, catalog, saved)
    def registered_sources(state):
        return {a["source_uid"] for a in state["assets"] if a["registered"]}
    assert registered_sources(offline) == registered_sources(saved)
    assert offline["shot_routing"]["shots"] == saved["shot_routing"]["shots"]
    assert lib.get_site_settings(hq, fresh=True) == settings
    state = load(lib, catalog, offline)
    assert registered_sources(state) == registered_sources(saved)
    assert len([a for a in state["assets"] if a["asset_id"] == "DuplicateLabel"]) == 2
    assert state["shot_routing"]["shots"][0]["selected_source_uids"] == saved["shot_routing"]["shots"][0]["selected_source_uids"]
    assert len(state["shot_routing"]["shots"][0]["selected_source_uids"]) == 3
    assets = [a for a in state["assets"] if a.get("registered")]
    assert len(assets) == 4, [(r["relative_path"], r["registered"]) for r in state["assets"]]
    for i, asset in enumerate(assets, 1):
        asset.update(selected=True, selection_order=i)
    shot = state["shot_routing"]["shots"][0]
    shot["selected_source_uids"] = [a["source_uid"] for a in reversed(assets)]
    expected = list(shot["selected_source_uids"])
    state = lib._normalize_state(state)
    assert len(set(expected)) == 4 and state["shot_routing"]["shots"][0]["selected_source_uids"] == expected
    media = lib._resolve_selected_assets(state)
    assert not media["unresolved"], media["unresolved"]
    request = {"request_id": "visible", "project_uid": state["project_uid"], "scan_revision": state["scan_revision"],
               "manifest_signature": state["manifest_signature"], "asset_library_ids": [a["asset_library_id"] for a in assets]}
    hydrated = lib._hydrate_asset_thumbnails(state, request)
    assert all(a["thumbnail_url"] for a in hydrated["assets"] if a["registered"]), hydrated["thumbnail_result"]
    # Retain the saved Shot through unlink, reopen without the link, and relink.
    if station_name != "hq":
        return
    missing_id = settings["links"][0]["id"]
    missing = {a["source_uid"] for a in assets if a["relative_path"].startswith(f"site:{missing_id}/")}
    assert len(missing) == 1
    retained = lib.save_site_settings(hq, settings["links"][1:], "hq", settings["revision"])
    unlinked = load(lib, catalog, state)
    assert set(unlinked["site_selection_memory"]) == missing, unlinked["site_selection_memory"]
    assert unlinked["shot_routing"]["shots"][0]["selected_source_uids"] == [uid for uid in expected if uid not in missing]
    assert all(not a["relative_path"].startswith(f"site:{missing_id}/") for a in unlinked["assets"])
    reloaded = load(lib, catalog, json.loads(json.dumps(unlinked)))
    assert reloaded["site_selection_memory"] == unlinked["site_selection_memory"]
    linked = lib.save_site_settings(hq, settings["links"], "hq", retained["revision"])
    assert linked["links"][0]["id"] == missing_id
    recovered = load(lib, catalog, reloaded)
    assert recovered["shot_routing"]["shots"][0]["selected_source_uids"] == expected
    assert not recovered["site_selection_memory"]
    async_merge = lib._merge_async_scan_result_with_live_state(recovered, reloaded, deepcopy(reloaded))
    assert async_merge["shot_routing"]["shots"][0]["selected_source_uids"] == expected
    # Two read-only or unreachable partners must not block a usable HQ selection.
    # Inject the network error at the per-folder boundary, never modify any real ACL.
    resolve = lib._site_root
    def offline(root, config, site):
        if site == missing_id:
            raise OSError("isolated test disconnected share")
        return resolve(root, config, site)

    with patch.object(lib, "_site_root", side_effect=offline):
        disconnected = lib._load_project_catalog(catalog, recovered, use_shared_cache=False)
        assert disconnected["warnings"] and not disconnected["error"]
        assert disconnected["shot_routing"]["shots"][0]["selected_source_uids"] == expected
        media = lib._resolve_selected_assets(disconnected)
        assert {row["source_uid"] for row in media["unresolved"]} == missing
    restored = lib._load_project_catalog(catalog, disconnected, use_shared_cache=False)
    assert not lib._resolve_selected_assets(restored)["unresolved"]


def live_profile_changes(root):
    from _hmb_image_asset_sites import add_site_folder, confirm_site_folder
    from PIL import Image
    lib = station(root / "pc-confirm-active")
    hq, first, second = paths(root)
    Image.new("RGB", (4, 4)).save(first/"CH"/"unregistered.png")
    catalog = hq.parents[1]
    state = load(lib, catalog)
    anchor = next(a for a in state["assets"] if a["registered"])
    anchor.update(selected=True, selection_order=1)
    state["shot_routing"]["shots"][0]["selected_source_uids"] = [anchor["source_uid"]]
    with patch.object(lib, "_scan_project_assets", wraps=lib._scan_project_assets) as scans:
        profile, site = add_site_folder(hq, str(first), "image")
        assert profile["write_site_id"] == "hq"
        profile = lib.save_site_settings(hq, profile["links"], site, profile["revision"], existing_only=True)
        confirm_site_folder(hq, "image", profile["revision"], site)
        state = load(lib,catalog,state)
        assert f"site:{site}/add" in state["folders"]
        assert any(a["relative_path"] == f"site:{site}/CH/unregistered.png" for a in state["assets"])
        for _ in range(2):
            confirm_site_folder(hq, "image", profile["revision"], site)
            state = load(lib,catalog,state)
        profile2, site2 = add_site_folder(hq, str(second), "image")
        assert profile2["write_site_id"] == site
        profile2 = lib.save_site_settings(hq, profile2["links"], site2, profile2["revision"], existing_only=True)
        confirm_site_folder(hq, "image", profile2["revision"], site2)
        state = load(lib,catalog,state)
        assert not any(a["relative_path"] == f"site:{site}/CH/unregistered.png" for a in state["assets"])
        assert any(a["relative_path"].startswith(f"site:{site2}/") for a in state["assets"])
        clipped = lib.save_site_settings(hq, profile2["links"][1:], site2, profile2["revision"], existing_only=True)
        confirm_site_folder(hq, "image", clipped["revision"], site2)
        state = load(lib,catalog,state)
        assert not any(f.startswith(f"site:{site}/") for f in state["folders"])
        assert state["shot_routing"]["shots"][0]["selected_source_uids"] == [anchor["source_uid"]]
        # A Windows temporary root may be supplied as an 8.3 path while the scanner returns its long form.
        observed = [Path(call.args[0]) for call in scans.call_args_list]
        assert len(observed) == 2, observed
        assert observed[0].samefile(first) and observed[1].samefile(second), observed


def explicit_import_destinations(root):
    from PIL import Image

    root.mkdir()
    lib = station(root / "workstation")
    hq, first, second = paths(root)
    for store in (hq, first, second):
        (store / "CH").mkdir(parents=True)
    catalog = hq.parents[1]
    profile = lib.save_site_settings(hq, [
        {"id": "first", "label": "First", "root": str(first)},
        {"id": "second", "label": "Second", "root": str(second)},
    ], "first", "0")
    first_id, second_id = (link["id"] for link in profile["links"])
    assert profile["write_site_id"] == first_id
    manual = first / "CH" / "manual.png"
    Image.new("RGB", (9, 6), "green").save(manual)
    manual_bytes = manual.read_bytes()
    state = load(lib, catalog)

    for site, storage, destination in (
        ("hq", hq, "CH"),
        (first_id, first, f"site:{first_id}/CH"),
        (second_id, second, f"site:{second_id}/add"),
    ):
        source = root / f"external-{storage.parents[2].name}.png"
        Image.new("RGB", (9, 6), "blue").save(source)
        state, media = lib._merge_import_input(state, [str(source)])
        incoming = next(a for a in state["assets"] if a["source_kind"] == "user")
        request = {"request_id": f"choose-{site}", "project_uid": state["project_uid"],
                   "asset_library_id": incoming["asset_library_id"], "source_uid": incoming["source_uid"],
                   "source_kind": "user", "target_folder": destination, "target_site_id": site,
                   "asset_id": "External", "image_name": "External", "image_main_type": "Custom / Context",
                   "image_sub_type": "Context", "site_settings_revision": profile["revision"]}
        for bad_request in (
            {**request, "target_site_id": "missing"},
            {**request, "target_site_id": "missing", "target_folder": "site:missing/add"},
            {**request, "site_settings_revision": "stale"},
        ):
            try:
                lib._apply_asset_registration(state, bad_request, media)
            except ValueError:
                pass
            else:
                raise AssertionError("An invalid or stale destination received an Add")
        state = lib._apply_asset_registration(state, request, media)
        assert state["asset_registration_result"]["ok"]
        child = "add" if site == second_id else "CH"
        saved = storage / child / source.name
        assert source.read_bytes() == saved.read_bytes()
        for other in (hq, first, second):
            records = lib._read_asset_manifest(other)
            assert (f"{child}/{source.name}".casefold() in records) == (other == storage)
        assert lib.get_site_settings(hq, fresh=True) == profile

    row = next(a for a in state["assets"] if a["relative_path"] == f"site:{first_id}/CH/manual.png")
    state = lib._apply_asset_registration(state, {
        "request_id": "manual", "project_uid": state["project_uid"],
        "asset_library_id": row["asset_library_id"], "relative_path": row["relative_path"],
        "asset_id": "Manual", "image_name": "Manual", "image_main_type": "Custom / Context",
        "image_sub_type": "Context", "site_settings_revision": profile["revision"],
    })
    assert state["asset_registration_result"]["ok"]
    assert manual.read_bytes() == manual_bytes
    assert "ch/manual.png" in lib._read_asset_manifest(first)
    assert len(list(root.rglob("manual.png"))) == 1
    owned = next(a for a in state["assets"] if a["asset_library_id"] == row["asset_library_id"])
    revision = owned["registration_revision"]
    edit = {
        "request_id": "edit", "action": "edit", "project_uid": state["project_uid"],
        "asset_library_id": row["asset_library_id"], "relative_path": row["relative_path"],
        "asset_id": "Manual", "image_name": "Manual updated", "image_main_type": "Custom / Context",
        "image_sub_type": "Context", "site_settings_revision": profile["revision"],
        "registration_revision": revision,
    }
    with patch.object(lib, "_asset_registration_owner", return_value="another Windows account"):
        for action in ("edit", "delete"):
            try:
                lib._apply_asset_registration(state, {**edit, "action": action})
            except ValueError:
                pass
            else:
                raise AssertionError("A different account changed a registration")
    state = lib._apply_asset_registration(state, edit)
    edited = next(a for a in state["assets"] if a["asset_library_id"] == row["asset_library_id"])
    assert edited["image_name"] == "Manual updated" and edited["registration_revision"] != revision
    try:
        lib._apply_asset_registration(state, {**edit, "action": "delete"})
    except ValueError:
        pass
    else:
        raise AssertionError("A stale version deleted the edited registration")
    state = lib._apply_asset_registration(state, {
        **edit, "request_id": "delete", "action": "delete", "registration_revision": edited["registration_revision"],
    })
    assert not next(a for a in state["assets"] if a["asset_library_id"] == row["asset_library_id"])["registered"]
    assert "ch/manual.png" not in lib._read_asset_manifest(first)
    assert manual.read_bytes() == manual_bytes
    assert (hq / "add").is_dir()


def run():
    from PIL import Image
    with TemporaryDirectory(prefix="hmb-site-") as home:
        root = Path(home)
        for path in paths(root):
            (path / "CH").mkdir(parents=True)
        hq, gwangju, busan = paths(root)
        for k, location in enumerate((hq, busan)):
            (location / ".json").mkdir()
            Image.new("RGB", (8, 8), "green").save(location / "CH" / "anchor.png")
            record = {"path": "CH/anchor.png", "asset_id": ("Existing", "PeerExisting")[k],
                      "image_name": "Anchor", "image_main_type": "Custom / Context", "image_sub_type": "Context"}
            (location / ".json" / "hmb_image_assets.json").write_text(json.dumps({"assets": [record]}), encoding="utf-8")
        busan_manifest = busan / ".json" / "hmb_image_assets.json"
        untouched = busan_manifest.read_bytes()
        # Initialize from the clean station env before importing the library.
        station(root / "pc-confirm-active")
        explicit_import_destinations(root / "destination-choice")
        station(root / "pc-confirm-active")
        live_profile_changes(root)
        context = multiprocessing.get_context("spawn")
        barrier = context.Barrier(2)
        for entry, arguments in [(register, (barrier,)), (reopened, ())]:
            workers = [context.Process(target=entry, args=(who, home, *arguments)) for who in ("hq", "gwangju")]
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join(90)
                assert worker.exitcode == 0, (entry.__name__, worker.exitcode)
        for path, expected in [(hq, 2), (gwangju, 1), (busan, 1)]:
            manifest = json.loads((path / ".json" / "hmb_image_assets.json").read_text("utf-8"))
            assert len(manifest["assets"]) == expected
        assert busan_manifest.read_bytes() == untouched
    print("PASS: 3 sources, 2 concurrent workstations, per-root read once per startup/refresh, independent Add, "
          "4 hot reopens, 2 cold restores, Shot identity, equal asset IDs, media, thumbnails, unlink/relink, "
          "per-import destination choice with independent registries and in-place manual Add.")


if __name__ == "__main__":
    run()
