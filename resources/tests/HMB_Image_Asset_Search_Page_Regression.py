"""Offline immutable search index/page protocol, epoch retirement and payload budget."""
from __future__ import annotations

import asyncio
from copy import deepcopy
import json
from pathlib import Path
import sys
import threading
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import HMBImageAssetLibrary as image


def assets(count):
    return [dict(asset_library_id=f"lib-{i}", asset_id=f"ID-{i:06d}", source_uid=f"source-{i}",
        source_kind="user" if i % 23 == 0 else "project", registered=True,
        image_name=("캐릭터 영웅 İΣ" if i % 97 == 0 else "Background") + f" {i}",
        relative_path=f"{'CH' if i % 2 else 'BG'}/Group{i % 11}/image-{i}.png",
        image_main_type="CHARACTER" if i % 2 else "Background", image_sub_type="Main Hero",
        path=f"C:/fixture/image-{i}.png", media_signature=f"media-{i}",
        selected=i in (1, 87), selection_order=1 if i == 1 else 2 if i == 87 else 0)
        for i in range(count)]


def expected(rows, query="", folder="", source="project"):
    keys = ("asset_id", "image_name", "relative_path", "image_main_type", "image_sub_type")
    needle, folder = query.strip().lower(), folder.strip("/").lower()
    return [row["asset_library_id"] for row in rows if row["source_kind"] == source
        and (source != "project" or not folder or row["relative_path"].lower().startswith(folder + "/"))
        and needle in "\n".join(str(row.get(key, "")).strip().lower() for key in keys)]


def state_for(count=5000):
    state = image._default_state()
    state.update(project_uid="fixture-project", project_cache_uid="fixture-cache", project_id="fixture",
        project_root="C:/fixture/project", manifest_signature="manifest-one", folder_signature="folders-one",
        scan_revision=7, assets=assets(count))
    return image._normalize_state(state)


def node_for(state):
    node = image.HMBImageAssetLibrary.__new__(image.HMBImageAssetLibrary)
    node.name = "ImageAssetSearchFixture"
    node._hmb_node_deleted = False
    node._hmb_import_revision = 0
    node._scan_owner_is_current = lambda: not node._hmb_node_deleted
    node._accept_normalized_widget_state_baseline(state)
    return node


def request_for(node, state, sequence, **extra):
    request = dict(schema=image.THUMBNAIL_BRIDGE_SCHEMA, version=1, operation="catalog_page", phase="request",
        runtime_instance_id=node._thumbnail_runtime_id(state), project_uid=state["project_uid"],
        project_cache_uid=state["project_cache_uid"], manifest_signature=state["manifest_signature"],
        folder_signature=state["folder_signature"], scan_revision=state["scan_revision"],
        session_id="fixture-session", sequence=sequence, request_id=f"fixture-{sequence}",
        query="", folder="", source_view="project", offset=0, limit=80)
    request.update(extra)
    return image._normalize_thumbnail_bridge(request)


async def wait_until(predicate, timeout=8):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        await asyncio.sleep(0.005)
    assert predicate(), "Search worker did not finish"


async def check_protocol():
    state = state_for()
    node = node_for(state)
    events = []
    main_thread = threading.get_ident()
    node._set_thumbnail_bridge_value = lambda value: events.append((deepcopy(value), threading.get_ident()))
    original = deepcopy(state)
    raw_before = node._hmb_last_accepted_widget_state
    node._request_catalog_search(request_for(node, state, 1, query="캐릭터"))
    await wait_until(lambda: len(events) == 1)
    first = events[-1][0]
    assert first["state"]["catalog_page"]["asset_library_ids"] == expected(state["assets"], "캐릭터")[:80]
    assert len(first["state"]["assets"]) <= 82
    assert first["state"]["shot_routing"] == original["shot_routing"]
    assert first["state"]["status"]["project_asset_count"] == original["status"]["project_asset_count"]
    assert events[-1][1] == main_thread, "SDK publication ran on search thread"
    for number in range(2, 8):
        node._request_catalog_search(request_for(node, state, number, query=f"ID-{number:06d}"))
        await wait_until(lambda: len(events) == number)
    assert node._hmb_catalog_search_builds == 1, "Repeated queries rebuilt unchanged catalog"
    assert node._hmb_last_accepted_widget_state == raw_before and state == original
    assert len(json.dumps(first, ensure_ascii=False)) < len(json.dumps(state, ensure_ascii=False)) / 15
    # Read pages cannot become canonical assets, even through full-state legacy fallback.
    assert node._expand_widget_edit(first["state"])["assets"] == original["assets"]

    # Selection and thumbnail publication keep index; same-count metadata changes rebuild.
    presentation = deepcopy(state)
    presentation["assets"][3]["thumbnail_url"] = "data:image/png;base64,fixture"
    presentation["thumbnail_revision"] += 1
    node._accept_normalized_widget_state_baseline(presentation)
    node._request_catalog_search(request_for(node, presentation, 8, query="Background"))
    await wait_until(lambda: len(events) == 8)
    assert node._hmb_catalog_search_builds == 1
    edited = deepcopy(presentation)
    edited["assets"][3]["image_name"] = "OnlyNewMetadata"
    edited["assets"][3]["image_main_type"] = "new-category"
    node._accept_normalized_widget_state_baseline(edited)
    node._request_catalog_search(request_for(node, edited, 9, query="OnlyNewMetadata"))
    await wait_until(lambda: len(events) == 9)
    assert node._hmb_catalog_search_builds == 2
    assert events[-1][0]["state"]["catalog_page"]["asset_library_ids"] == [edited["assets"][3]["asset_library_id"]]

    # An in-flight older query is retired by the next intent, project/scan/import epoch and delete.
    entered, release = threading.Event(), threading.Event()
    original_query = image._ImageCatalogSearchIndex.query
    def held(index, request, cancelled=lambda: False):
        if request["query"] == "hold":
            entered.set()
            assert release.wait(5)
        return original_query(index, request, cancelled)
    with patch.object(image._ImageCatalogSearchIndex, "query", held):
        node._request_catalog_search(request_for(node, edited, 10, query="hold"))
        await wait_until(entered.is_set)
        node._request_catalog_search(request_for(node, edited, 11, query="ID-000004"))
        release.set()
        await wait_until(lambda: len(events) == 10)
    assert events[-1][0]["sequence"] == 11 and all(event[0]["sequence"] != 10 for event in events)
    before = len(events)
    for number, mutation in enumerate(("scan", "import", "project", "deleted"), 12):
        entered.clear(); release.clear()
        with patch.object(image._ImageCatalogSearchIndex, "query", held):
            node._request_catalog_search(request_for(node, edited, number, query="hold"))
            await wait_until(entered.is_set)
            if mutation == "scan":
                edited = deepcopy(edited); edited["scan_revision"] += 1
                node._accept_normalized_widget_state_baseline(edited)
            elif mutation == "import":
                node._hmb_import_revision += 1
            elif mutation == "project":
                edited = deepcopy(edited); edited["project_uid"] = "other-project"
                node._accept_normalized_widget_state_baseline(edited)
            else:
                node._hmb_node_deleted = True
            release.set()
            await wait_until(lambda: node._hmb_catalog_search_thread is None)
        assert len(events) == before, f"Retired {mutation} query published"
    return {"full_catalog_bytes": len(json.dumps(original, ensure_ascii=False).encode()),
        "query_page_bytes": len(json.dumps(first, ensure_ascii=False).encode()),
        "canonical_records": len(original["assets"]), "first_index_builds": 1,
        "repeated_query_rebuilds": 0, "metadata_change_rebuilds": 1}


rows = assets(5000)
start = time.perf_counter(); index = image._ImageCatalogSearchIndex(rows); build_ms = (time.perf_counter() - start) * 1000
for needle in ("", "캐릭터", "İΣ", "id-000097", "main\nhero", "background", "CH/Group", "not-present"):
    for folder in ("", "CH", "BG/Group2"):
        for source in ("project", "user"):
            page = index.query(dict(query=needle, folder=folder, source_view=source, offset=80, limit=80))
            matching = expected(rows, needle, folder, source)
            offset = min(80, ((len(matching) - 1) // 80) * 80 if matching else 0)
            assert page["asset_library_ids"] == matching[offset:offset + 80], (needle, folder, source)
            assert page["total"] == len(matching)
rows[97]["image_name"] = "externally-mutated"
assert index.query({"query": "캐릭터", "source_view": "project"})["total"] == len(expected(assets(5000), "캐릭터"))
result = asyncio.run(check_protocol())

# Stress index only: production import/scan limit stays 5,000.
assert image.MAX_ASSETS == 5000
stress = assets(100000)
start = time.perf_counter(); large = image._ImageCatalogSearchIndex(stress); stress_build_ms = (time.perf_counter() - start) * 1000
start = time.perf_counter()
for number in range(100):
    result_page = large.query({"query": f"ID-{number * 997:06d}", "source_view": "project"})
    assert result_page["total"] <= 1
query_ms = (time.perf_counter() - start) * 1000
result.update(index_5000_build_ms=round(build_ms, 2), synthetic_100000_build_ms=round(stress_build_ms, 2),
    synthetic_100_queries_ms=round(query_ms, 2), synthetic_candidate_checks=large.stats["candidate_checks"])
out = ROOT / "reports/feature123-local804-20261016/search"
out.mkdir(parents=True, exist_ok=True)
(out / "search-index-benchmark.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print("PASS ImageAsset search pages: parity, detached index, full authority, latest-only, epochs, metadata rebuild, 5k/100k budgets.")
print(json.dumps(result, ensure_ascii=False))
