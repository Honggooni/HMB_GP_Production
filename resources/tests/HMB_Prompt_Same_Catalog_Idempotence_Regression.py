"""Identical catalog ACKs cannot advance clocks through active document copies."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import threading
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import HMBPromptLibrary as prompt

channel="11111111-1111-4111-8111-111111111111"
shots=[dict(channel_uuid=channel,shot_uuid=f"22222222-2222-4222-8222-{number:012d}",
    number=number,name=f"authored_{number}",selected_source_uids=[]) for number in range(1,6)]
def catalog_for(rows,generation):
    contract=dict(channel_uuid=channel,generation=generation,shots=[dict(shot_uuid=row["shot_uuid"],
        number=row["number"],name=row["name"],revision=generation) for row in rows])
    return dict(schema=prompt.SHOT_ROUTING_CATALOG_SCHEMA,version=prompt.SHOT_ROUTING_CATALOG_VERSION,
        publisher_instance_uuid=channel,**contract,metadata_sha256=prompt._canonical_sha256(contract))
catalog=catalog_for(shots,10)
state=prompt._normalize_state(dict(prompt._default_widget_state(),multi_shot_enabled=True,shot=shots[0],
    image_asset=dict(shot_catalog=shots,shot_catalog_routing=prompt._catalog_routing_projection(catalog))))
text_key=next(iter(prompt.TEXT_FIELD_DEFAULTS))
for row in shots:
    state=prompt._select_prompt_shot_document(state,row)
    state["text"][text_key]=f"exact authored text {row['number']} {{literal}}"
    state["images"][0]["label"]=f"native image label {row['number']}"
    state["videos"][0]["keep_out"]=f"keep_out_{row['number']}"
    state["ui"]["textarea_heights"]={"video:1:keep_out":80+row["number"]}
    state[prompt.UI_EDIT_REVISION_KEY]+=1
    state=prompt._store_prompt_shot_document(state)
state=prompt._select_prompt_shot_document(state,shots[2])
# Source enrichment advanced the outer clock; dormant document clocks are
# intentionally opaque old snapshots, not a request to rewrite their contents.
state[prompt.SOURCE_SYNC_REVISION_KEY]=100
state[prompt.UI_EDIT_REVISION_KEY]=30
live={"state":deepcopy(state)}
owner=prompt.HMBPromptLibrary.__new__(prompt.HMBPromptLibrary)
owner._hmb_sync_lock=threading.RLock()
owner._hmb_node_deleted=False
owner._hmb_shot_routing_hydration_rebase_pending=False
owner._current_state=lambda:deepcopy(live["state"])
scheduled=[]
owner._schedule_prompt_sync=lambda **kwargs:scheduled.append(kwargs)
publications=[]
def store(candidate,name,value):
    assert candidate is owner and name==prompt.WIDGET_PARAMETER_NAME
    publications.append(json.loads(value))
    live["state"]=json.loads(value)
with patch.object(prompt,"_set_parameter_value",store):
    before=deepcopy(live["state"])
    for _ in range(40):owner._hmb_reconcile_shot_routing(routing_snapshot=deepcopy(catalog))
    assert publications==[] and scheduled==[]
    assert live["state"]==before,"Identical same-Shot catalog ACK rewrote stored documents"

    # A real rename still owns exactly one monotonic source update.
    renamed=deepcopy(shots);renamed[2]["name"]="renamed_by_asset_library"
    renamed_catalog=catalog_for(renamed,11)
    owner._hmb_reconcile_shot_routing(routing_snapshot=deepcopy(renamed_catalog))
    assert len(publications)==len(scheduled)==1
    assert live["state"]["shot"]["name"]=="renamed_by_asset_library"
    assert live["state"][prompt.SOURCE_SYNC_REVISION_KEY]==101
    assert live["state"][prompt.UI_EDIT_REVISION_KEY]==30
    for _ in range(40):owner._hmb_reconcile_shot_routing(routing_snapshot=deepcopy(renamed_catalog))
    assert len(publications)==len(scheduled)==1,"Rename ACK caused clock feedback"

    # Visible authored edits are durable before a document switch; same-Shot
    # reconciliation must neither overwrite them from old JSON nor lose them.
    live["state"]["text"][text_key]="new current third-shot edit {unchanged literal}"
    live["state"]["images"][0]["label"]="new current label"
    live["state"][prompt.UI_EDIT_REVISION_KEY]=31
    documents_before=deepcopy(live["state"]["shot_documents"])
    owner._hmb_reconcile_shot_routing(routing_snapshot=deepcopy(renamed_catalog))
    assert live["state"]["shot_documents"]==documents_before
    assert len(publications)==len(scheduled)==1
    for row in (renamed[4],renamed[2],renamed[0],renamed[3],renamed[1],renamed[2]):
        live["state"]=prompt._select_prompt_shot_document(live["state"],row)
        number=row["number"]
        assert live["state"]["text"][text_key]==("new current third-shot edit {unchanged literal}" if number==3
            else f"exact authored text {number} {{literal}}")
        assert live["state"]["images"][0]["label"]==("new current label" if number==3 else f"native image label {number}")
        assert live["state"]["videos"][0]["keep_out"]==f"keep_out_{number}"
        assert live["state"]["ui"]["textarea_heights"]["video:1:keep_out"]==80+number
        assert live["state"][prompt.SOURCE_SYNC_REVISION_KEY]==101
        assert live["state"][prompt.UI_EDIT_REVISION_KEY]==31

    # Crossed source/UI clocks preserve the latest active edit plus all other
    # UUID bodies. Neither same-Shot catalog ACK nor source clock alone stores it.
    newer_source=deepcopy(live["state"]);newer_source[prompt.SOURCE_SYNC_REVISION_KEY]=102
    newer_ui=deepcopy(live["state"]);newer_ui[prompt.UI_EDIT_REVISION_KEY]=32
    newer_ui["text"][text_key]="newest crossed-axis edit"
    merged=prompt._merge_prompt_revision_axes(newer_source,newer_ui)
    assert merged["text"][text_key]=="newest crossed-axis edit"
    assert (merged[prompt.SOURCE_SYNC_REVISION_KEY],merged[prompt.UI_EDIT_REVISION_KEY])==(102,32)
    live["state"]=merged
    documents_before=deepcopy(merged["shot_documents"])
    for _ in range(20):owner._hmb_reconcile_shot_routing(routing_snapshot=deepcopy(renamed_catalog))
    assert live["state"]["shot_documents"]==documents_before and len(publications)==1

    # Active UUID deletion switches once, while preserving the deleted body's
    # authored content in its opaque document. Repeated new catalog is stable.
    remaining=[dict(row,number=i+1) for i,row in enumerate(row for row in renamed if row["number"]!=3)]
    deleted_catalog=catalog_for(remaining,12)
    owner._hmb_reconcile_shot_routing(routing_snapshot=deepcopy(deleted_catalog))
    assert len(publications)==len(scheduled)==2
    assert live["state"]["shot"]["shot_uuid"]==remaining[0]["shot_uuid"]
    deleted_document=json.loads(live["state"]["shot_documents"][channel+"/"+shots[2]["shot_uuid"]])
    assert deleted_document["text"][text_key]=="newest crossed-axis edit"
    before=deepcopy(live["state"])
    for _ in range(20):owner._hmb_reconcile_shot_routing(routing_snapshot=deepcopy(deleted_catalog))
    assert live["state"]==before and len(publications)==2
    invalid=deepcopy(deleted_catalog);invalid["metadata_sha256"]="0"*64
    try:owner._hmb_reconcile_shot_routing(routing_snapshot=invalid)
    except prompt._ShotRoutingContractError:pass
    else:raise AssertionError("Invalid source authority was accepted")
    assert live["state"]==before and len(publications)==2
print("PASS Prompt same-catalog idempotence: 120 unchanged ACKs publish0, rename/delete once, five authored bodies/edits/clock merge retained, invalid source rejected.")
