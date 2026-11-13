import assert from 'node:assert/strict';
import fs from 'node:fs';

const source=fs.readFileSync(new URL('../../widgets/HMBVideoPickerLibraryWidget_v032.js',import.meta.url),'utf8');
const picker=await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
const ids=Array.from({length:5},(_,index)=>`11111111-1111-4111-8111-00000000000${index+1}`);
const state={runtime_instance_id:'isolated-runtime',active_picker_shot_uuid:ids[0]};
const host={};
const requests=ids.map((id,index)=>picker.hmbClaimPickerReadRequest(host,{...state,active_picker_shot_uuid:id},`read-${index+1}`,'C:/same/shared.mb'));
assert.equal(host.__hmbPickerReadRequests.size,5,'The same .mb may have five independent request receipts');
assert.equal(picker.hmbClaimPickerReadRequest(host,state,'duplicate','C:/another.mb'),null,'The same Shot cannot double-submit before acknowledgement');
picker.hmbProjectPickerReadRequest(host,{...state,active_picker_shot_uuid:ids[4]});
assert.equal(host.__hmbReadActionId,'read-5');
for(const raw of [
  {...state,state_writer:'python',backend_ack_action_id:'old-read'},
  {...state,runtime_instance_id:'foreign',state_writer:'python',backend_ack_action_id:'read-5'},
  {...state,state_writer:'widget',backend_ack_action_id:'read-5'},
]){
  assert.equal(picker.hmbReconcilePickerCommandAcknowledgements(host,raw).readReleased,false);
  assert.equal(host.__hmbPickerReadRequests.size,5);
}
for(let index=0;index<4;index++){
  const result=picker.hmbReconcilePickerCommandAcknowledgements(host,{...state,state_writer:'python',
    backend_ack_action_id:'unrelated-command',read_requests_by_shot:{[ids[index]]:{action_id:`read-${index+1}`,status:'queued'}}});
  assert.equal(result.readReleased,true);
  assert.equal(host.__hmbReadActionId,'read-5','Another Shot ACK does not release the displayed Shot');
  assert.equal(host.__hmbReadCommandPending,true);
}
assert.equal(picker.hmbReconcilePickerCommandAcknowledgements(host,{...state,state_writer:'python',read_requests_by_shot:{[ids[4]]:{action_id:'read-5',status:'running'}}}).readReleased,true);
assert.equal(host.__hmbPickerReadRequests.size,0);
assert.equal(host.__hmbReadCommandPending,false);
assert.equal(picker.hmbReleasePickerReadRequest(host,requests[4]),false,'Late timer cannot release a completed/replaced request');
const errorKey=`${state.runtime_instance_id}:${ids[0]}`;
host.__hmbPickerReadErrors=new Map([[errorKey,{runtime:state.runtime_instance_id,shot:ids[0],actionId:'read-retry',message:'timeout'}]]);
for(const raw of [
  {...state,state_writer:'python',backend_ack_action_id:'read-1'},
  {...state,state_writer:'python',runtime_instance_id:'foreign',backend_ack_action_id:'read-retry'},
  {...state,state_writer:'widget',backend_ack_action_id:'read-retry'},
]){
  picker.hmbReconcilePickerCommandAcknowledgements(host,raw);
  assert.equal(host.__hmbPickerReadErrors.size,1,'A stale or foreign receipt cannot clear the retry error');
}
assert.equal(picker.hmbReconcilePickerCommandAcknowledgements(host,{...state,state_writer:'python',
  read_requests_by_shot:{[ids[0]]:{action_id:'read-retry',status:'queued'}}}).readReleased,true);
assert.equal(host.__hmbPickerReadErrors.size,0,'Late receipt clears only its matching timeout');

const busy={...state,maya_available:true,maya_executable:'C:/Maya/bin/mayabatch.exe',scene_path:'C:/same/shared.mb',scene_request_path:'C:/same/shared.mb',
  status:'READING_SCENE',scene_stage:'MAYA_READING',operation_kind:'read_scene',operation_picker_shot_uuid:ids[0],active_process_pid:123,
  read_requests_by_shot:{[ids[0]]:{action_id:'read-1',status:'running'}}};
assert.equal(picker.pickerButtonAvailability(busy).readEnabled,false);
const other={...busy,active_picker_shot_uuid:ids[1]};
assert.equal(picker.pickerButtonAvailability(other).readEnabled,true,'Another Shot can queue READ while one Maya worker is active');
assert.equal(picker.pickerButtonAvailability(other).stopEnabled,false,'Another Shot cannot stop an unrelated READ');
const queued={...other,read_requests_by_shot:{...busy.read_requests_by_shot,[ids[1]]:{action_id:'read-2',status:'queued'}}};
assert.equal(picker.pickerButtonAvailability(queued).readEnabled,false);
assert.equal(picker.pickerButtonAvailability(queued).stopEnabled,true,'A queued Shot can cancel its own request');
assert.equal(picker.pickerButtonAvailability({...other,operation_kind:'run_video',status:'RUNNING'}).readEnabled,false,'Existing render lock remains in force');
picker.hmbClearPickerReadRequests(host);
assert.equal(host.__hmbPickerReadRequests,undefined);
console.log('PASS: five Shot READ receipt ownership, stale/foreign ACK rejection, queue admission and existing render lock.');
