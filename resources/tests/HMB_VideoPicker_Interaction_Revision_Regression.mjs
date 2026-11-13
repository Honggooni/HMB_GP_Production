import assert from 'node:assert/strict';
import fs from 'node:fs';
const source=fs.readFileSync(new URL('../../widgets/HMBVideoPickerLibraryWidget_v032.js',import.meta.url),'utf8');
const picker=await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
const a='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',b='bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
const initial={runtime_instance_id:'r1',scene_request_path:'C:/scene.ma',active_picker_shot_uuid:b,
  picker_shots:[{workspace_uuid:a,number:1},{workspace_uuid:b,number:2}],
  mask_enabled:true,original_enabled:false,slot_visibility:[],depth_settings:{range:'close'},language:'ko'};
const local={...initial,active_picker_shot_uuid:a,mask_enabled:false,original_enabled:true,
  slot_visibility:[{video_slot:1,hidden_paths:['|Glass']}],depth_settings:{range:'far'}};
const host={};
picker.hmbRememberPickerInteractionDraft(host,local,initial);
const beforePaint=picker.hmbProtectPickerInteractionDraft(host,{...initial,status:'READING',last_action_id:'backend-ack',message:'progress'});
assert.equal(beforePaint.protected,true);
assert.equal(beforePaint.state.active_picker_shot_uuid,a);
assert.equal(beforePaint.state.mask_enabled,false);
assert.equal(beforePaint.state.status,'READING');
assert.equal(beforePaint.state.last_action_id,'backend-ack');
picker.hmbStampPickerInteractionDraft(host,{state_revision:12,state_published_at_ms:100});
const ack={...local,state_writer:'python',state_revision:12,frontend_seen_revision:12,state_published_at_ms:100};
assert.equal(picker.hmbProtectPickerInteractionDraft(host,ack).protected,false);
const crossed=picker.hmbProtectPickerInteractionDraft(host,{...initial,state_writer:'python',state_revision:11,state_published_at_ms:90});
assert.equal(crossed.protected,true);
assert.equal(crossed.state.state_revision,12,'old echoes cannot lower the next authoring revision');
assert.equal(crossed.state.original_enabled,true);
assert.deepEqual(crossed.state.slot_visibility,local.slot_visibility);
// Python may confirm rejection or a newer edit. Do not conceal that authority.
const rejected=picker.hmbProtectPickerInteractionDraft(host,{...ack,mask_enabled:true});
assert.equal(rejected.protected,false);
assert.equal(host.__hmbPickerInteractionDraft.fields.has('mask_enabled'),false);
// New runtime/scene and authoritative Shot deletion must not inherit UI choices.
const sceneChanged=picker.hmbProtectPickerInteractionDraft(host,{...initial,scene_request_path:'C:/new.ma'});
assert.ok(sceneChanged.state.slot_visibility.every(entry=>!entry.hidden_paths.length));
const removed=picker.hmbProtectPickerInteractionDraft(host,{...initial,picker_shots:[{workspace_uuid:b,number:2}]});
assert.equal(removed.state.active_picker_shot_uuid,b);
assert.equal(host.__hmbPickerInteractionDraft.fields.has('active_picker_shot_uuid'),false);
picker.hmbProtectPickerInteractionDraft(host,{...initial,runtime_instance_id:'r2'});
assert.equal(host.__hmbPickerInteractionDraft,undefined);
// Unchanged controls are not claimed by another local edit or kept in a global registry.
picker.hmbRememberPickerInteractionDraft(host,{...initial,language:'en'},initial);
assert.deepEqual([...host.__hmbPickerInteractionDraft.fields.keys()],['language']);
assert.doesNotMatch(source.split('const HMB_PICKER_INTERACTION_FIELDS = [')[1].split('];')[0],/"(?:status|videos|video_tools_status|backend_ack_action_id)"/);

// Same file name does not let one shot's pending edits override its peer.
const scenes={
  [a]:{scene_path:'C:/shared.mb',scene_request_path:'C:/shared.mb',mask_enabled:true},
  [b]:{scene_path:'C:/shared.mb',scene_request_path:'C:/shared.mb',mask_enabled:true},
};
const scoped={...initial,...scenes[b],picker_scene_states:scenes,picker_scene_owner_uuid:b,
  shot_publisher_instance_uuid:'11111111-1111-4111-8111-111111111111',
  channel_uuid:'22222222-2222-4222-8222-222222222222',
  shot_selections:[{shot_uuid:a,number:1,name:'Shot 1'},{shot_uuid:b,number:2,name:'Shot 2'}],
  picker_shots:[{workspace_uuid:a,bound_shot_uuid:a,number:1},{workspace_uuid:b,bound_shot_uuid:b,number:2}]};
const scopedHost={};
const scopedEdit={...picker.hmbSwitchLocalPickerShot(scoped,a),mask_enabled:false};
picker.hmbRememberPickerInteractionDraft(scopedHost,scopedEdit,scoped);
const scopedEcho=picker.hmbProtectPickerInteractionDraft(scopedHost,scoped);
assert.equal(scopedEcho.state.active_picker_shot_uuid,a);
assert.equal(scopedEcho.state.mask_enabled,false);
assert.equal(picker.hmbSwitchLocalPickerShot(scopedEcho.state,b).mask_enabled,true);
console.log('Picker interaction revision guards: PASS (pre-paint, crossed ACK, backend rejection, scene/runtime reset, Shot removal, scoped fields)');
