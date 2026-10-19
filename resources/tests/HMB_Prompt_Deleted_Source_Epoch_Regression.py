"""A deleted publisher can retire proof once; a live edge swap cannot."""
from __future__ import annotations
from copy import deepcopy
import importlib
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from unittest import mock
from _hmb_seedance_clean_ci_stubs import install_clean_ci_griptape_stubs
install_clean_ci_griptape_stubs()
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import HMBPromptLibrary as prompt
import _hmb_shot_routing as routing

channel="11111111-1111-4111-8111-111111111111"
shots=[dict(channel_uuid=channel,shot_uuid=f"22222222-2222-4222-8222-{n:012d}",number=n,name=f"authored_{n}",selected_source_uids=[]) for n in range(1,6)]
old_publisher="33333333-3333-4333-8333-333333333333"
new_publisher="44444444-4444-4444-8444-444444444444"
def snapshot(publisher,generation=1):
    payload=dict(channel_uuid=channel,generation=generation,shots=deepcopy(shots),ordered_videos=[])
    return dict(payload,publisher_instance_uuid=publisher,metadata_sha256=prompt._canonical_sha256(payload),media_sha256=prompt._canonical_sha256({"media_descriptors":[]}))
def state_for():
    state=prompt._normalize_state(dict(prompt._default_widget_state(),multi_shot_enabled=True,shot=shots[0]))
    for row in shots:
        state=prompt._select_prompt_shot_document(state,row)
        state["text"][next(iter(prompt.TEXT_FIELD_DEFAULTS))]=f"authored text {row['number']} {{literal}}"
        state["picker"]["shot_routing"]=prompt._routing_projection(snapshot(old_publisher),[])
        state=prompt._store_prompt_shot_document(state)
    return prompt._select_prompt_shot_document(state,shots[0])

nodes={};objects={};edges=[]
class Request(SimpleNamespace):pass
class Success(SimpleNamespace):pass
connection_module=ModuleType('griptape_nodes.retained_mode.events.connection_events')
connection_module.ListConnectionsForNodeRequest=Request
connection_module.ListConnectionsForNodeResultSuccess=Success
class API:
    @staticmethod
    def NodeManager():return SimpleNamespace(get_node_by_name=lookup)
    @staticmethod
    def ObjectManager():return SimpleNamespace(attempt_get_object_by_name=lambda name:objects.get(name))
    @staticmethod
    def handle_request(request):return Success(incoming_connections=edges)
def lookup(name):
    if name not in nodes:raise ValueError("missing fixture node")
    return nodes[name]
api_module=sys.modules['griptape_nodes.retained_mode.griptape_nodes']

def reject(call):
    try:call()
    except prompt._ShotRoutingContractError:return
    raise AssertionError("An unproven source replacement was admitted")

with mock.patch.object(api_module,'GriptapeNodes',API),mock.patch.dict(sys.modules,{'griptape_nodes.retained_mode.events.connection_events':connection_module}),mock.patch.object(routing,'_same_flow_nodes',side_effect=lambda owner:('Flow',list(nodes.values()))):
    owner=prompt.HMBPromptLibrary(name='Prompt lifecycle owner')
    live={'state':state_for()};owner._current_state=lambda:deepcopy(live['state'])
    old=SimpleNamespace(name='Picker',metadata={'library':'HMB_GP_Production','node_type':'HMBVideoPickerLibrary'},_hmb_node_deleted=False)
    fresh=SimpleNamespace(name='Replacement',metadata={'library':'HMB_GP_Production','node_type':'HMBVideoPickerLibrary'},_hmb_node_deleted=False)
    nodes.update({owner.name:owner,old.name:old,fresh.name:fresh});objects.update(nodes)
    owner._hmb_hydrated_document_routes={(prompt._prompt_document_key(row),'video_picker'):None for row in shots}
    owner._hmb_hydrated_document_sources={}
    def connect(source):
        edges[:]=[SimpleNamespace(source_node_name=source.name,source_parameter_name='SHOT_PICKER_OUT',target_parameter_name='SHOT_PICKER_IN')]
        owner._hmb_connected_source_nodes={prompt.SHOT_PICKER_INPUT_PARAMETER_NAME:source}
    def validate(source,data= None,row=shots[0]):
        owner._validate_document_route_watermark({**live['state'],'shot':row},kind='video_picker',source=source,snapshot=data or snapshot(new_publisher),previous=live['state']['picker']['shot_routing'],label='VideoPicker shot routing')
    connect(old);validate(old,snapshot(old_publisher))
    before=deepcopy(live['state']);ledger_before=deepcopy(owner._hmb_hydrated_document_routes)
    # A manual disconnect or valid second publisher never retires a live owner.
    owner._mark_deleted_document_source(old,prompt.SHOT_PICKER_INPUT_PARAMETER_NAME)
    connect(fresh);reject(lambda:validate(fresh));assert owner._hmb_hydrated_document_routes==ledger_before
    # SDK marks deleted before removing its registry entry. That boundary alone
    # cannot authorize a replacement while the original object remains registered.
    old._hmb_node_deleted=True;owner._mark_deleted_document_source(old,prompt.SHOT_PICKER_INPUT_PARAMETER_NAME)
    reject(lambda:validate(fresh));assert owner._hmb_hydrated_document_sources['video_picker'] is old
    # After actual deregistration, only the exact connected registered owner can
    # consume each UUID allowance. Another object without its edge still fails.
    nodes.pop(old.name);objects.pop(old.name)
    identity_before=owner._prompt_sync_retry_identity();owner._retire_deleted_document_sources()
    assert owner._prompt_sync_retry_identity()!=identity_before
    assert 'video_picker' not in owner._hmb_hydrated_document_sources
    foreign=SimpleNamespace(name=fresh.name,metadata=fresh.metadata,_hmb_node_deleted=False)
    reject(lambda:validate(foreign))
    for row in shots:validate(fresh,row=row)
    assert owner._hmb_hydrated_document_sources['video_picker'] is fresh
    assert live['state']==before,'Epoch retirement must not rewrite authored documents or active state'
    epoch=owner._hmb_document_source_epoch
    owner._retire_deleted_document_sources();assert owner._hmb_document_source_epoch==epoch
    changed=snapshot(new_publisher);changed['metadata_sha256']='0'*64
    reject(lambda:validate(fresh,changed))
    assert all(value is not None for key,value in owner._hmb_hydrated_document_routes.items() if key[1]=='video_picker')
    # A delayed callback for old edge removal cannot clear a newly connected
    # source or its raw parameter. No setter or output refresh is invoked.
    with mock.patch.object(prompt,'_set_parameter_value') as setter,mock.patch.object(owner,'_sync_prompt_output_now') as sync:
        owner.after_incoming_connection_removed(old,SimpleNamespace(name='SHOT_PICKER_OUT'),SimpleNamespace(name=prompt.SHOT_PICKER_INPUT_PARAMETER_NAME))
        setter.assert_not_called();sync.assert_not_called()
    assert owner._hmb_connected_source_nodes[prompt.SHOT_PICKER_INPUT_PARAMETER_NAME] is fresh
    # Clear before publisher turnover archives the newest visible body, while
    # retaining the exact bytes of all other UUID documents.
    key=next(iter(prompt.TEXT_FIELD_DEFAULTS));live['state']['text'][key]='newest active text {preserve}'
    stored_before=deepcopy(live['state']['shot_documents'])
    def store(node,name,value):
        assert node is owner and name==prompt.WIDGET_PARAMETER_NAME;live['state']=json.loads(value)
    with mock.patch.object(prompt,'_set_parameter_value',side_effect=store),mock.patch.object(owner,'_sync_prompt_output_from_state',return_value={}):
        owner._hmb_clear_shot_routing_catalog()
    active_key=prompt._prompt_document_key(shots[0])
    assert json.loads(live['state']['shot_documents'][active_key])['text'][key]=='newest active text {preserve}'
    assert all(live['state']['shot_documents'][k]==v for k,v in stored_before.items() if k!=active_key)
    assert live['state']['shot']['shot_uuid']==''
    cleared=deepcopy(live['state'])
    with mock.patch.object(prompt,'_set_parameter_value',side_effect=store),mock.patch.object(owner,'_sync_prompt_output_from_state',return_value={}):
        for _ in range(40):owner._hmb_clear_shot_routing_catalog()
    assert live['state']==cleared,'Repeated unavailable callbacks cannot resave clocks into an unbound document'
    # A recreated source may restore a different exact UUID first. Its document
    # is selected before the source-only clock is merged with the old unbound
    # UI projection. That projection must not author the newly selected body.
    restored=prompt._select_prompt_shot_document(deepcopy(cleared),shots[1])
    restored['image_asset']['shot_catalog']=deepcopy(shots)
    restored['image_asset']['shot_catalog_routing']={"publisher_instance_uuid":new_publisher,"channel_uuid":channel,"generation":2,"metadata_sha256":"b"*64}
    restored[prompt.SOURCE_SYNC_REVISION_KEY]+=1
    merged=prompt._merge_prompt_revision_axes(restored,cleared)
    assert merged['shot']['shot_uuid']==shots[1]['shot_uuid']
    assert merged['text'][key]=='authored text 2 {literal}', 'Unbound body must not overwrite restored UUID document'
    assert all(merged['shot_documents'][k]==v for k,v in cleared['shot_documents'].items())
    crossed_ui=prompt._select_prompt_shot_document(deepcopy(restored),shots[2])
    crossed_ui['text'][key]='new valid third-UUID UI edit'
    crossed_ui[prompt.UI_EDIT_REVISION_KEY]+=1
    crossed_source=deepcopy(restored);crossed_source[prompt.SOURCE_SYNC_REVISION_KEY]+=1
    crossed=prompt._merge_prompt_revision_axes(crossed_source,crossed_ui)
    assert crossed['shot']['shot_uuid']==shots[2]['shot_uuid'] and crossed['text'][key]=='new valid third-UUID UI edit'
    foreign_ui=deepcopy(crossed_ui);foreign_ui['shot']['channel_uuid']='99999999-9999-4999-8999-999999999999'
    foreign_ui['text'][key]='foreign channel edit must not leak'
    foreign=prompt._merge_prompt_revision_axes(crossed_source,foreign_ui)
    assert foreign['shot']==crossed_source['shot'] and foreign['text']==crossed_source['text']
# Source deletion and explicit live selection removal are distinct.  Preserve
# only the exact unavailable projection of this UUID, not another slot/name.
def uid_payload(uid):
    rows=[] if not uid else [dict(video_uid=uid,source_uid=uid,selected=True,
        video_slot=1,selection_order=1,video_path=f"https://media.invalid/{uid}.mp4")]
    return dict(schema="hmb-prompt-library-picker-binding",schema_version=5,mode="maya",
        media_ready=bool(rows),selected_video_count=len(rows),active_slot_count=len(rows),
        ordered_video_uids=[uid] if uid else [],selection_id=f"selection-{uid}",videos=rows,markers=[])
owner=prompt.HMBPromptLibrary(name="Prompt authored deletion")
base=prompt._normalize_state(dict(prompt._default_widget_state(),multi_shot_enabled=True,shot=shots[4]))
base["images"][0].update(asset_source_uid="exact-image-uid",source_uid="exact-image-uid",
    asset_managed=True,present=True,label="hero.png",image_main_type="Character",
    image_sub_type="Full Appearance",owner="original Target")
original=prompt._apply_picker_payload(base,uid_payload("exact-video-uid"),connected=True)
original["images"][0]["color_picks"]=["Red"]
old=SimpleNamespace(name="Deleted picker",metadata={"library":"HMB_GP_Production","node_type":"HMBVideoPickerLibrary"},_hmb_node_deleted=True)
live={"state":deepcopy(original)};owner._current_state=lambda:deepcopy(live["state"])
owner._hmb_connected_source_nodes={prompt.SHOT_PICKER_INPUT_PARAMETER_NAME:old}
owner._mark_deleted_document_source(old,prompt.SHOT_PICKER_INPUT_PARAMETER_NAME)
assert len(owner._hmb_deleted_picker_authoring)==1
# A final unavailable UID publication may clear the active binding before its
# physical edge disappears. That projection is safe while the owner is absent.
unavailable=prompt._apply_picker_payload(deepcopy(original),uid_payload(""),connected=True)
unavailable=prompt._apply_picker_payload(unavailable,{},connected=False)
assert unavailable["images"][0]["color_picks"]==[""]
assert unavailable["picker"]["enabled"] is False and not unavailable["picker"]["ordered_video_uids"]
owner._hmb_connected_source_nodes={}
owner._remember_deleted_picker_projection(unavailable)
record=deepcopy(owner._hmb_deleted_picker_authoring)
# The archive is private: no source, ledger, or replacement authority leaks into
# serialized document/schema. Existing unavailable output remains empty.
assert "_hmb_deleted_picker_authoring" not in prompt._json_dumps(unavailable)
restored=prompt._apply_picker_payload(deepcopy(unavailable),uid_payload("exact-video-uid"),connected=True)
owner._restore_deleted_picker_authoring(restored,["exact-video-uid"])
assert restored["images"][0]["color_picks"]==["Red"]
assert restored["images"][0]["owner"]=="original Target"
assert restored[prompt.UI_EDIT_REVISION_KEY]==unavailable[prompt.UI_EDIT_REVISION_KEY]+1
restored[prompt.SOURCE_SYNC_REVISION_KEY]=unavailable[prompt.SOURCE_SYNC_REVISION_KEY]+1
owner._hmb_last_accepted_widget_state=prompt._json_dumps(unavailable)
assert prompt._parse_state(owner._merge_widget_revision_axes(prompt._json_dumps(restored)))["images"][0]["color_picks"]==["Red"]
assert not owner._hmb_deleted_picker_authoring
stable=deepcopy(restored)
owner._restore_deleted_picker_authoring(restored,["exact-video-uid"])
assert restored==stable, "A consumed restoration cannot advance clocks again"
# Editing while disconnected wins over the saved automatic projection.
owner._hmb_deleted_picker_authoring=deepcopy(record)
edited=deepcopy(unavailable);edited["images"][0]["color_picks"]=["Green"];edited["images"][0]["owner"]="new Target"
owner._remember_deleted_picker_projection(edited)
restored=prompt._apply_picker_payload(edited,uid_payload("exact-video-uid"),connected=True)
owner._restore_deleted_picker_authoring(restored,["exact-video-uid"],authored_snapshot=owner._deleted_picker_authoring_snapshot(edited))
assert restored["images"][0]["color_picks"]==["Green"] and restored["images"][0]["owner"]=="new Target"
# Execution views can read the restoration without consuming the live editor's
# private archive, so a preview cannot make the subsequent commit lose it.
owner._hmb_deleted_picker_authoring=deepcopy(record)
view=__import__("copy").copy(owner);view._hmb_execution_registered_owner=owner
restored=prompt._apply_picker_payload(deepcopy(unavailable),uid_payload("exact-video-uid"),connected=True)
view._restore_deleted_picker_authoring(restored,["exact-video-uid"])
assert restored["images"][0]["color_picks"]==["Red"] and owner._hmb_deleted_picker_authoring
for changed in ([],["foreign-video-uid"]):
    owner._hmb_deleted_picker_authoring=deepcopy(record)
    foreign=prompt._apply_picker_payload(deepcopy(unavailable),uid_payload(changed[0] if changed else ""),connected=True)
    owner._restore_deleted_picker_authoring(foreign,changed)
    assert foreign["images"][0]["color_picks"]==[""] and not owner._hmb_deleted_picker_authoring
owner._hmb_deleted_picker_authoring=deepcopy(record)
foreign=deepcopy(unavailable);foreign["shot"]=shots[0]
owner._restore_deleted_picker_authoring(foreign,["exact-video-uid"])
assert foreign["images"][0]["color_picks"]==[""]
# Ordinary live deselection/disconnection still uses the original clear contract
# and never creates a lifecycle restoration record.
regular=prompt.HMBPromptLibrary(name="Prompt live deselection")
regular._current_state=lambda:deepcopy(original)
old._hmb_node_deleted=False
regular._hmb_connected_source_nodes={prompt.SHOT_PICKER_INPUT_PARAMETER_NAME:old}
regular._mark_deleted_document_source(old,prompt.SHOT_PICKER_INPUT_PARAMETER_NAME)
assert not getattr(regular,"_hmb_deleted_picker_authoring",{})
assert prompt._apply_picker_payload(deepcopy(original),uid_payload(""),connected=True)["images"][0]["color_picks"]==[""]
# The active body may be newer than its dormant JSON copy until a switch.
# Deletion archives that current body before dropping source authority; merging
# an older accepted UI must not replace it with its stale dormant document.
active=state_for();active=prompt._select_prompt_shot_document(active,shots[4])
active["images"][0]["color_picks"]=["Red"]
active=prompt._store_prompt_shot_document(active)
active[prompt.UI_EDIT_REVISION_KEY]=5
active["images"][0]["color_picks"]=["Blue"]
active["text"][key]="latest active fifth body"
archived=prompt._store_prompt_shot_document(deepcopy(active))
archived["shot"]=prompt._normalize_shot_selection({})
archived["image_asset"]["shot_catalog"]=[]
archived["image_asset"]["shot_catalog_routing"]={}
archived[prompt.SOURCE_SYNC_REVISION_KEY]=active[prompt.SOURCE_SYNC_REVISION_KEY]+1
fifth_key=prompt._prompt_document_key(shots[4])
merged=prompt._merge_prompt_revision_axes(archived,active)
assert json.loads(merged["shot_documents"][fifth_key])["images"][0]["color_picks"]==["Blue"], "A stale UI archive cannot overwrite the newly archived active edit"
assert json.loads(merged["shot_documents"][fifth_key])["text"][key]=="latest active fifth body"
# Fresh UI edits to another dormant UUID still win; equal UI revisions use
# source revision, and an exact clock tie preserves the fresh source archive.
ui_new=deepcopy(active);ui_doc=json.loads(ui_new["shot_documents"][fifth_key]);ui_doc[prompt.UI_EDIT_REVISION_KEY]=6;ui_doc["images"][0]["color_picks"]=["Green"];ui_new["shot_documents"][fifth_key]=prompt._json_dumps(ui_doc)
assert json.loads(prompt._merge_prompt_revision_axes(archived,ui_new)["shot_documents"][fifth_key])["images"][0]["color_picks"]==["Green"]
source_doc=json.loads(archived["shot_documents"][fifth_key]);tie_ui=deepcopy(active);tie_doc=deepcopy(source_doc);tie_doc["images"][0]["color_picks"]=["Red"];tie_ui["shot_documents"][fifth_key]=prompt._json_dumps(tie_doc)
assert json.loads(prompt._merge_prompt_revision_axes(archived,tie_ui)["shot_documents"][fifth_key])["images"][0]["color_picks"]==["Blue"]
# A default empty video row after a true disconnect is a placeholder, not
# the removed UID itself. Selecting the exact dormant UID again must not map
# that placeholder's address to zero and delete a later manual Color Pick.
blue=prompt._apply_picker_payload(deepcopy(base),uid_payload("same-dormant-uid"),connected=True)
blue["images"][0]["color_picks"]=["Blue"]
released=prompt._apply_picker_payload(blue,{},connected=False)
assert released["images"][0]["color_picks"]==["Blue"]
returned=prompt._apply_picker_payload(deepcopy(released),uid_payload("same-dormant-uid"),connected=True)
assert returned["images"][0]["color_picks"]==["Blue"], "A generated placeholder cannot clear an exact restored UID binding"
foreign=prompt._apply_picker_payload(deepcopy(released),uid_payload("foreign-new-uid"),connected=True)
assert foreign["images"][0]["color_picks"]==[""], "A different UID cannot borrow the old slot's binding"
deselected=prompt._apply_picker_payload(deepcopy(blue),uid_payload(""),connected=True)
returned=prompt._apply_picker_payload(deselected,uid_payload("same-dormant-uid"),connected=True)
assert returned["images"][0]["color_picks"]==[""], "Explicit deselection remains clear even when the old UID returns"
print('HMB Prompt deleted-source epoch: PASS (live swap rejected; marked-but-registered rejected; exact deleted owner retires once; 5 documents retained; unique physical owner pinned; stale callback cannot clear newer source; active clear archive exact)')
