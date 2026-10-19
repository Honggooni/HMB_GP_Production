"""Official SDK bridge dispatch/background completion; no scans, files or render calls."""
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
try:
    from griptape_nodes.exe_types.flow import ControlFlow
    from griptape_nodes.retained_mode.engine import current_engine
    from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
except ImportError:
    print("ImageAsset search page native SDK: SKIP (SDK unavailable)")
    raise SystemExit(0)
import HMBImageAssetLibrary as image


async def wait_until(predicate):
    end = time.monotonic() + 8
    while not predicate() and time.monotonic() < end:
        await asyncio.sleep(0.005)
    assert predicate(), "Native search page completion timed out"


async def main():
    GriptapeNodes.EventManager().initialize_queue()
    flow = ControlFlow(name="ImageSearchPageOfflineFlow", engine=current_engine())
    GriptapeNodes.ObjectManager().add_object_by_name(flow.name, flow)
    source = image.HMBImageAssetLibrary(name="ImageSearchPageOfflineSource")
    flow.add_node(source)
    GriptapeNodes.ObjectManager().add_object_by_name(source.name, source)
    GriptapeNodes.NodeManager()._name_to_parent_flow_name[source.name] = flow.name
    source._hmb_initial_catalog_scan_pending = False
    source._hmb_hydration_adopted = True
    state = source._current_state()
    state.update(project_root="C:/fixture/search-project", project_uid="search-project", project_id="search",
        project_cache_uid="search-cache", manifest_signature="manifest", folder_signature="folders", scan_revision=9,
        assets=[dict(asset_library_id=f"library-{i}", asset_id=f"asset-{i}", source_uid=f"source-{i}",
            source_kind="project", registered=True, path=f"C:/fixture/search-project/{i}.png",
            relative_path=f"CH/{i}.png", image_name=f"Character {i}", image_main_type="CH", image_sub_type="Full body",
            selected=i in (1,87), selection_order=1 if i==1 else 2 if i==87 else 0) for i in range(5000)])
    state = image._normalize_state(state)
    source._store_thumbnail_state_silently(state, normalized=True)
    # Model an existing last-good native output pair. Search must neither clear
    # nor resolve it; a fresh process/scan belongs to the separate owner path.
    source.parameter_output_values[image.OUTPUT_PARAMETER] = json.dumps({"assets":state["assets"][:2]})
    source.parameter_output_values[image.MEDIA_OUTPUT_PARAMETER] = [state["assets"][1]["path"],state["assets"][87]["path"]]
    output_before = deepcopy(dict(source.parameter_output_values))
    raw_before = image._get_parameter_raw(source, image.WIDGET_STATE_PARAMETER)
    saved_before = source._hmb_last_accepted_widget_state
    publisher = source.publish_update_to_parameter
    events, threads = [], []
    def publish(name, value):
        if name == image.THUMBNAIL_PATCH_PARAMETER:
            events.append(deepcopy(value)); threads.append(threading.get_ident())
        return publisher(name, value)
    source.publish_update_to_parameter = publish
    def request(number, query="Character"):
        return dict(schema=image.THUMBNAIL_BRIDGE_SCHEMA,version=1,operation="catalog_page",phase="request",
            runtime_instance_id=source._thumbnail_runtime_id(state),request_id=f"native-{number}",session_id="native-page-client",
            sequence=number,project_uid=state["project_uid"],project_cache_uid=state["project_cache_uid"],
            manifest_signature=state["manifest_signature"],folder_signature=state["folder_signature"],
            scan_revision=state["scan_revision"],query=query,folder="",source_view="project",offset=0,limit=80)
    async def dispatch(number, query="Character"):
        result = await GriptapeNodes.ahandle_request(SetParameterValueRequest(
            node_name=source.name,parameter_name=image.THUMBNAIL_PATCH_PARAMETER,value=request(number,query),data_type="dict"))
        assert not result.failed(), result
    entered, release = threading.Event(), threading.Event()
    original = image._ImageCatalogSearchIndex.__init__
    worker_threads = []
    def build(index, rows, cancelled=lambda:False):
        worker_threads.append(threading.get_ident());entered.set()
        assert release.wait(5)
        return original(index, rows, cancelled)
    owner_thread = threading.get_ident()
    with patch.object(source,"_sync_output",side_effect=AssertionError("Search must not resolve media outputs")), \
         patch.object(source,"_current_state",side_effect=AssertionError("Queries must reuse accepted catalog; no full parse")), \
         patch.object(image._ImageCatalogSearchIndex,"__init__",build):
        started = time.perf_counter()
        await dispatch(1)
        dispatch_ms = (time.perf_counter() - started) * 1000
        await wait_until(entered.is_set)
        heartbeat = asyncio.Event()
        asyncio.get_running_loop().call_later(0.01, heartbeat.set)
        await asyncio.wait_for(heartbeat.wait(), timeout=0.3)
        assert not release.is_set() and not events
        await dispatch(2,"asset-4999")
        release.set()
        await wait_until(lambda: any(event.get("sequence")==2 for event in events))
        assert all(event.get("sequence")!=1 for event in events), "Stale query was published"
        assert events[-1]["state"]["catalog_page"]["asset_library_ids"] == ["library-4999"]
        await dispatch(3,"asset-4000")
        await wait_until(lambda: any(event.get("sequence")==3 for event in events))
        assert source._hmb_catalog_search_builds == 1
        assert all(thread != owner_thread for thread in worker_threads)
        assert all(thread == owner_thread for thread in threads)
    assert image._get_parameter_raw(source,image.WIDGET_STATE_PARAMETER) == raw_before
    assert source._hmb_last_accepted_widget_state == saved_before
    assert len(json.loads(raw_before)["assets"]) == 5000
    actual_outputs = dict(source.parameter_output_values)
    # SDK mirrors every hidden property into output-values too. Only its compact
    # bridge envelope may change; ASSET_OUT/media/shot and all other values stay.
    actual_outputs.pop(image.THUMBNAIL_PATCH_PARAMETER, None)
    output_before.pop(image.THUMBNAIL_PATCH_PARAMETER, None)
    assert actual_outputs == output_before, [key for key in set(actual_outputs)|set(output_before)
        if actual_outputs.get(key) != output_before.get(key)]
    assert events[-1]["state"]["shot_routing"] == state["shot_routing"]
    assert "tree" not in events[-1]["state"]
    # Previous clients still receive the same complete canonical parameter.
    assert json.loads(image._get_parameter_raw(source,image.WIDGET_STATE_PARAMETER))["assets"] == state["assets"]
    result = {"sdk":"official installed SDK","records":5000,"sdk_dispatch_ms":round(dispatch_ms,3),
        "index_builds":source._hmb_catalog_search_builds,"heartbeat_during_blocked_index":True,
        "publication_on_owner_loop":True,"stale_query_publications":0,"full_retained_catalog_unchanged":True,
        "native_output_pair_unchanged":True,"legacy_client_full_property_preserved":True,"paid_calls":0}
    out=ROOT/"reports/feature123-local804-20261016/search"
    out.mkdir(parents=True,exist_ok=True)
    (out/"native-sdk-result.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result))


asyncio.run(main())
print("PASS ImageAsset search page native SDK dispatch/heartbeat/latest-only/full authority/output preservation")
