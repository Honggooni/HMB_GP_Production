"""Actual SDK five-shot DAG with hierarchy names; all model/render calls mocked.

Synthetic private graph only. Reuses the existing native lifecycle fixture so
the Prompt, Standard Agent adapter and Generator boundaries stay identical.
"""
from __future__ import annotations
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
from unittest import mock
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(Path(__file__).parent)]
import HMB_Multishot_Manager_Host_Regression as native
import _hmb_shot_routing as routing

members = []
is_cgt_fixture = os.environ.get('HMB_HIERARCHY_TEST_CGT') == '1'
cgt_account, cgt_project, cgt_pipeline = (str(uuid4()).upper() for _ in range(3))
for i, shot in enumerate(native.SHOTS, 1):
    identity = str(uuid4())
    # Two splits of the same s001 remain two independently owned execution rows.
    name = ('e201s001c002__' if i == 2 else f'e201s{i:03d}c001__')
    members.append(dict(member_id='manual:' + identity, origin='manual', manual_uuid=identity,
        source_name=('e201/' + name if i == 1 else name), canonical_name=name,
        gp_shot_uuid=shot['shot_uuid'], parent_id=None, selection_order=i,
        cgt_task_id=None, artist=None, status=None))
    if is_cgt_fixture:
        task_id = str(uuid4()).upper()
        members[-1].update(member_id='cgt:' + task_id.lower(), origin='cgt', cgt_task_id=task_id,
            artist='Synthetic Artist', status='Work',
            cgt_identity=dict(entity_id=str(uuid4()).upper(), task_id=task_id, pipeline_id=cgt_pipeline))
members[1]['parent_id'] = members[0]['member_id']
members[2]['parent_id'] = members[1]['member_id']
members[3]['parent_id'] = members[2]['member_id']
names = routing.hierarchy_derived_names({'members':members})
assert names[members[1]['gp_shot_uuid']] == 'e201_s001c002-s003c001__'
assert names[members[2]['gp_shot_uuid']] == 'e201_s003c001-s004c001__'
for row in native.SHOTS:
    row['name'] = names[row['shot_uuid']]

exercise_native = native.exercise
binding_id = str(uuid4())

async def exercise(engine):
    import HMBImageAssetLibrary as image
    import HMBSeedanceGeneration as seedance
    import _hmb_review as review
    publish = image.HMBImageAssetLibrary._publish_state
    observations = []
    def fixture_publish(self, state, *args, **kwargs):
        state = deepcopy(state)
        if (state.get('shot_routing', {}).get('channel_uuid') == native.CHANNEL
                and len(state['shot_routing']['shots']) == 5):
            state['shot_hierarchy'] = dict(schema=routing.SHOT_HIERARCHY_SCHEMA, version=1,
                binding_id=binding_id, revision=1, project_identity=routing.hierarchy_project_key(state),
                channel_uuid=native.CHANNEL, cgt_account_id=None, members=deepcopy(members))
            if is_cgt_fixture:
                state['shot_hierarchy'].update(version=2, cgt_account_id=cgt_account,
                    cgt_scope=dict(origin='https://cgt.synthetic.invalid', project_id=cgt_project,
                        project_db='proj_fixture_sw12', module='shot', module_type='task',
                        pipeline_id=cgt_pipeline, account_id=cgt_account))
            normalized = image._normalize_state(json.dumps(state))
            assert normalized['shot_hierarchy'] == state['shot_hierarchy']
            assert normalized['shot_routing']['shots'][0]['name'] == 'e201_s001c001-s001c002__'
            observations.append(True)
        return publish(self, state, *args, **kwargs)
    with mock.patch.object(image.HMBImageAssetLibrary, '_publish_state', fixture_publish):
        await exercise_native(engine)
    assert observations
    source = engine.node_manager.get_node_by_name('offline_manager_image')
    from griptape_nodes.retained_mode.events.node_events import SerializeNodeToCommandsRequest
    from griptape_nodes.serialization.values import decode_value
    pool = {}
    save_request = SerializeNodeToCommandsRequest(node_name=source.name,
        unique_parameter_uuid_to_values=pool, serialize_all_parameter_values=True)
    save_request.broadcast_result = False
    serialized = engine.handle_request(save_request)
    assert serialized.succeeded(), serialized.result_details
    retained = {item.set_parameter_value_command.parameter_name: decode_value(deepcopy(pool[item.unique_value_uuid]))
                for item in serialized.set_parameter_value_commands}
    saved = retained[image.WIDGET_STATE_PARAMETER]
    reopened = image._normalize_state(saved)
    assert reopened['shot_hierarchy']['members'] == members
    receipts = []
    for i, shot in enumerate(native.SHOTS, 1):
        node = engine.node_manager.get_node_by_name(f'offline_managed_generator_{i}')
        origin = node._capture_generated_video_origin()
        assert origin['name'] == names[shot['shot_uuid']]
        snapshot = routing.capture_shot_hierarchy(node, native.CHANNEL, shot['shot_uuid'])
        assert snapshot['members'] == members
        checkpoint = seedance._seedance_recovery_value(dict(task_id='job-' + f'{i:032x}',
            task_identity='broker_task', stage='local_succeeded', status='succeeded',
            broker_server_url='https://broker.example', generation_origin=origin, shot_hierarchy=snapshot))
        assert checkpoint['shot_hierarchy']['members'] == members
        assert checkpoint['generation_origin'] == origin
        public = review.public_evidence({'inputs': {'project_id':'superwings12', 'generation_origin':origin}})
        assert public['shot']['name'] == names[shot['shot_uuid']]
        assert 'shot_hierarchy' not in public and 'members' not in public['shot']
        receipts.append(checkpoint)
    before = json.dumps(receipts, sort_keys=True)
    changed = deepcopy(members)
    changed[0].update(source_name='e201s101c001__', canonical_name='e201s101c001__')
    prior = reopened['shot_hierarchy']
    edit_command = dict(schema=routing.SHOT_HIERARCHY_REQUEST_SCHEMA, version=1,
        expected_generation=reopened['shot_routing']['generation'], expected_binding_revision=prior['revision'],
        removed_member_ids=[],
        binding=dict(prior, revision=prior['revision']+1, members=changed))
    if is_cgt_fixture:
        try:
            routing.apply_shot_hierarchy_edit(reopened, edit_command)
        except ValueError:
            pass
        else:
            raise AssertionError('Authenticated CGT name was directly renamed')
        edited = deepcopy(reopened)
        assert edited['shot_routing']['shots'][0]['name'] == 'e201_s001c001-s001c002__'
    else:
        edited = routing.apply_shot_hierarchy_edit(reopened, edit_command)
        assert edited['shot_routing']['shots'][0]['name'] == 'e201_s101c001-s001c002__'
    assert json.dumps(receipts, sort_keys=True) == before
    assert image._normalize_state(json.dumps(edited))['shot_hierarchy']['members'] == (members if is_cgt_fixture else changed)
    # Recreate a fresh native node from the actual serialized creation/element
    # commands in an isolated second flow, then restore its saved parameter.
    from griptape_nodes.retained_mode.events.flow_events import CreateFlowRequest
    from griptape_nodes.retained_mode.events.node_events import DeserializeNodeFromCommandsRequest
    from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
    restored_flow = engine.handle_request(CreateFlowRequest(parent_flow_name=None,
        flow_name='HierarchyColdReopen', set_as_new_context=False))
    assert restored_flow.succeeded(), restored_flow.result_details
    with engine.context_manager.flow(restored_flow.flow_name):
        recreated = engine.handle_request(DeserializeNodeFromCommandsRequest(
            serialized_node_commands=deepcopy(serialized.serialized_node_commands)))
        assert recreated.succeeded(), recreated.result_details
        restored_node = engine.node_manager.get_node_by_name(recreated.node_name)
        restored = engine.handle_request(SetParameterValueRequest(node_name=restored_node.name,
            parameter_name=image.WIDGET_STATE_PARAMETER, value=saved, initial_setup=True))
        assert restored.succeeded(), restored.result_details
        loaded = image._normalize_state(restored_node.get_parameter_value(image.WIDGET_STATE_PARAMETER))
        assert loaded['shot_hierarchy'] == reopened['shot_hierarchy']
        assert [row['shot_uuid'] for row in loaded['shot_routing']['shots']] == [row['shot_uuid'] for row in native.SHOTS]
        assert loaded['shot_routing']['channel_uuid'] == native.CHANNEL
    assert json.dumps(receipts, sort_keys=True) == before
    print('HMB_SHOT_HIERARCHY_HOST=PASS (five independent native Prompt/Agent/Generator executions; split identity; exact naming; save/reopen; immutable recovery and public title; no paid calls)')

native.exercise = exercise
if __name__ == '__main__':
    native.main()
