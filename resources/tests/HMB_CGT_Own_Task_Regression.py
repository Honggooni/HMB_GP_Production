"""Synthetic CGT read/confirm failure boundaries. No network or record writes."""
from __future__ import annotations
import contextlib
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
from unittest import mock
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import _hmb_cgt as cgt
import _hmb_shot_routing as routing
import HMBImageAssetLibrary as image

guid = lambda: str(uuid4()).upper()
account, project_id, pipeline = guid(), guid(), guid()
other_project_id = guid()
tasks = [dict(task_id=guid(), entity_id=guid(), name=f'e201s{i:03d}c001__', status='Work') for i in range(1, 6)]
calls = []
source_changes = {}
project_entity = 'superwings12'
needed = ['task.id', 'shot.id', 'eps.entity', 'shot.entity', 'pipeline.id', 'pipeline.entity', 'task.account_id', 'task.artist', 'task.status']

def visible_projects():
    return [{'project.id': project_id, 'project.entity': project_entity, 'project.full_name': 'Fixture SW12',
             'project.database': 'proj_fixture_sw12', 'project.status': 'Active'},
            {'project.id': other_project_id, 'project.entity': 'Other_Show', 'project.full_name': 'Other CGT Name',
             'project.database': 'proj_fixture_other', 'project.status': 'Archive'}]

class Response:
    is_redirect = False
    def raise_for_status(self): pass

class Session:
    trust_env = True
    def mount(self, origin, adapter):
        assert origin == 'https://192.168.200.18:8383/'
    def post(self, url, *args, **kwargs):
        assert kwargs['verify'] is True and kwargs['allow_redirects'] is False
        assert kwargs['timeout'] == (5, 10)
        calls.append(json.loads(kwargs['data']['data']))
        return Response()

session = Session()
def read(controller, method, data, value):
    session.post('https://192.168.200.18:8383/api.php', data={'data': json.dumps(dict(controller=controller, method=method, **data))})
    return value

class Tw:
    login = types.SimpleNamespace(account_id=lambda: account, is_login=lambda: True)
    account = types.SimpleNamespace(get=lambda ids, fields: read('account', 'get', {}, [{'account.id': account, 'account.entity': 'fixture-login', 'account.name': 'Synthetic Artist'}]))
    project = types.SimpleNamespace(
        get_id=lambda filters: read('project', 'get_id', {'sign_filter_array': filters}, [row['project.id'] for row in visible_projects()]),
        get=lambda ids, fields: read('project', 'get', {}, [row for row in visible_projects() if row['project.id'] in ids]))
    class task:
        @staticmethod
        def fields_and_str(db, module):
            assert db in {'proj_fixture_sw12', 'proj_fixture_other'} and module == 'shot'
            return read('task', 'fields_and_str', {}, [{'sign': field} for field in needed])
        @staticmethod
        def get_id(db, module, query, limit='200', start_num='0'):
            assert query[:3] == [['task.account_id', 'has', account], 'and', ['pipeline.entity', '=', 'AI_Shot']]
            selected = query[-1][2] if len(query) > 3 else [row['task_id'] for row in tasks]
            return read('task', 'get_id', {'sign_filter_array': query}, [row['task_id'] for row in tasks if row['task_id'] in selected] if db == 'proj_fixture_sw12' else [])
        @staticmethod
        def get(db, module, ids, fields, limit='200'):
            assert fields == needed
            rows = []
            for task in tasks:
                if task['task_id'] not in ids: continue
                rows.append({'task.id': task['task_id'], 'shot.id': task['entity_id'], 'eps.entity': 'e201',
                    'shot.entity': task['name'], 'pipeline.id': pipeline, 'pipeline.entity': 'AI_Shot',
                    'task.account_id': account, 'task.artist': 'Synthetic Artist', 'task.status': task['status'], **source_changes})
            return read('task', 'get', {}, rows)

class Adapter:
    def __init__(self, *args, **kwargs): pass
    def init_poolmanager(self, *args, **kwargs): pass

def query(binding=None, project_key='superwings12', cgt_project_id=None):
    global session
    session = Session()
    sdk = types.SimpleNamespace(tw=Tw, G_tw_http_ip='192.168.200.18:8383', G_cgtw_session=session)
    modules = {'cgtw2': sdk, 'websocket': types.SimpleNamespace(setdefaulttimeout=lambda value: None),
               'requests.adapters': types.SimpleNamespace(HTTPAdapter=Adapter)}
    with tempfile.TemporaryDirectory(prefix='hmb-cgt-synthetic-') as directory:
        (Path(directory)/'cgtw2.py').write_text('# synthetic SDK marker', 'utf-8')
        with mock.patch.dict(os.environ, {'HMB_CGT_SDK_PATH': directory}), mock.patch.dict(sys.modules, modules):
            return cgt._read_own({'project_id': project_key, 'binding': binding, 'cgt_project_id': cgt_project_id,
                                  'project_db': 'untrusted-ui-database'})

snapshot = query()
assert snapshot['status'] == 'ready' and len(snapshot['tasks']) == 5
assert snapshot['tls_verified'] and snapshot['hostname_verified']
assert all(item['controller'] in {'account', 'project', 'task'} and item['method'] in {'get', 'get_id', 'fields_and_str'} for item in calls)
assert all('password' not in item.get('sign_array', []) for item in calls)

state = image._default_state()
state.update(project_root='C:/fixture/superwings12', project_id='superwings12', project_uid='fixture-project')
scope = dict(origin=snapshot['origin'], project_id=project_id, project_db=snapshot['project']['database'],
             module='shot', module_type='task', pipeline_id=pipeline, account_id=account)
members = []
for i, task in enumerate(snapshot['tasks'], 1):
    identity = str(uuid4())
    parsed = routing.hierarchy_parse_name(task['source_name'])
    members.append(dict(member_id='cgt:'+task['task_id'].lower(), origin='cgt', manual_uuid=identity,
        source_name=parsed['source_name'], canonical_name=parsed['canonical_name'],
        gp_shot_uuid=state['shot_routing']['shots'][0]['shot_uuid'] if i == 1 else str(uuid4()),
        parent_id=None, selection_order=i, cgt_task_id=task['task_id'], artist=task['artist'], status=task['status'], cgt_identity=task['identity']))
members[1]['parent_id'] = members[0]['member_id']
members[3]['parent_id'] = members[2]['member_id']
binding = dict(schema=routing.SHOT_HIERARCHY_SCHEMA, version=2, binding_id=str(uuid4()), revision=1,
    project_identity=routing.hierarchy_project_key(state), channel_uuid=state['shot_routing']['channel_uuid'],
    cgt_account_id=account, cgt_scope=scope, members=members)
command = dict(schema=routing.SHOT_HIERARCHY_REQUEST_SCHEMA, version=1, expected_generation=state['shot_routing']['generation'],
    expected_binding_revision=0, removed_member_ids=[], binding=binding)
before = deepcopy(state)
cgt.verify_binding(binding, 'superwings12', query(binding))
committed = routing.apply_shot_hierarchy_edit(state, command)
assert state == before and len(committed['shot_routing']['shots']) == 5
assert committed['shot_routing']['shots'][0]['name'] == 'e201_s001c001-s002c001__'
assert image._normalize_state(json.dumps(committed))['shot_hierarchy'] == binding
checks = 10
assert next(item for item in calls if item['controller'] == 'project' and item['method'] == 'get_id')['sign_filter_array'] == []
project_entity = 'Katuri8'
assert query(project_key='katuri8')['status'] == 'ready'
assert query(project_key='katuri8')['project']['entity'] == 'Katuri8'
assert query(project_key='unknown')['status'] == 'ready' and query(project_key='unknown')['project'] is None
project_entity = 'superwings12'
listed = query(project_key='')
assert listed['status'] == 'ready' and listed['project'] is None and listed['tasks'] == [] and listed['can_bind'] is False
assert [(row['id'], row['entity'], row['name'], row['status']) for row in listed['projects']] == [
    (project_id, 'superwings12', 'Fixture SW12', 'Active'),
    (other_project_id, 'Other_Show', 'Other CGT Name', 'Archive')]
assert snapshot['can_bind'] and snapshot['project']['id'] == project_id
assert query(cgt_project_id=project_id.lower())['project']['id'] == project_id
other_browse = query(cgt_project_id=other_project_id)
assert other_browse['status'] == 'ready' and other_browse['project']['id'] == other_project_id
assert other_browse['project']['database'] == 'proj_fixture_other' and other_browse['can_bind'] is False
assert query(cgt_project_id=guid())['status'] == 'PROJECT_UNAVAILABLE'
assert query(binding=binding, cgt_project_id=other_project_id)['status'] == 'SOURCE_CHANGED'
assert query(binding=binding, project_key='')['status'] == 'SELECT_GP_PROJECT'
assert cgt.catalog(cgt_project_id='ui-database-or-name')['status'] == 'PROJECT_UNAVAILABLE'
checks += 11
with mock.patch.object(Tw.task, 'fields_and_str', return_value=[]):
    unsupported = query(cgt_project_id=other_project_id)
assert unsupported['status'] == 'SOURCE_SCHEMA' and unsupported['projects'] == listed['projects']
assert unsupported['tasks'] == [] and unsupported['can_bind'] is False
checks += 2
retained_tasks = deepcopy(tasks); tasks.clear()
assert query()['status'] == 'ready' and query()['tasks'] == []
tasks.extend(retained_tasks)
checks += 4

def rejected(fn):
    global checks
    try: fn()
    except ValueError: checks += 1
    else: raise AssertionError('Invalid source was accepted')

# Authenticated CGT names remain read-only even if an edit preserves every
# account/task ID and supplies matching source/canonical names.
locked_command = deepcopy(command)
locked_command.update(expected_generation=committed['shot_routing']['generation'], expected_binding_revision=1)
locked_command['binding']['revision'] = 2
locked_command['binding']['members'][0].update(source_name='e201s999c001__', canonical_name='e201s999c001__')
rejected(lambda: routing.apply_shot_hierarchy_edit(committed, locked_command))
empty_project_command = deepcopy(command)
empty_project_command['binding']['project_identity'] = ''
rejected(lambda: routing.normalize_shot_hierarchy(empty_project_command['binding']))
assert committed['shot_hierarchy'] == binding and state == before
checks += 1

# Inline manual rename remains local even beside authenticated CGT members.
# Every other member/scope/group field must remain exactly accepted authority.
mixed = deepcopy(committed)
local_identity = str(uuid4())
mixed['shot_hierarchy']['members'][-1].update(member_id='manual:' + local_identity,
    origin='manual', manual_uuid=local_identity, source_name='local_reference', canonical_name='local_reference',
    cgt_task_id=None, artist=None, status=None, cgt_identity=None)
mixed['shot_routing']['shots'][-1]['name'] = 'local_reference'
mixed = image._normalize_state(mixed)
mixed_before = deepcopy(mixed)
manual_rename = dict(schema=routing.SHOT_HIERARCHY_REQUEST_SCHEMA, version=1,
    expected_generation=mixed['shot_routing']['generation'],
    expected_binding_revision=mixed['shot_hierarchy']['revision'], removed_member_ids=[],
    binding=deepcopy(mixed['shot_hierarchy']))
manual_rename['binding']['revision'] += 1
manual_rename['binding']['members'][-1].update(source_name='renamed_reference', canonical_name='renamed_reference')
local_host = object.__new__(image.HMBImageAssetLibrary)
local_host._hmb_last_accepted_widget_state = json.dumps(mixed)
local_host._widget_state_is_stale = lambda value: False
with mock.patch.object(cgt, 'catalog', side_effect=AssertionError('Manual-only rename must not contact CGT')):
    renamed_mixed = local_host._prepare_shot_hierarchy_edit({image.UI_EDIT_REVISION_KEY: 1}, manual_rename)
assert renamed_mixed['shot_hierarchy']['members'][:-1] == mixed['shot_hierarchy']['members'][:-1]
assert renamed_mixed['shot_hierarchy']['cgt_scope'] == mixed['shot_hierarchy']['cgt_scope']
assert renamed_mixed['shot_routing']['shots'][-1]['name'] == 'renamed_reference'
assert [row['shot_uuid'] for row in renamed_mixed['shot_routing']['shots']] == [row['shot_uuid'] for row in mixed['shot_routing']['shots']]
assert [row['selected_source_uids'] for row in renamed_mixed['shot_routing']['shots']] == [row['selected_source_uids'] for row in mixed['shot_routing']['shots']]
assert image._normalize_state(json.dumps(renamed_mixed))['shot_hierarchy'] == renamed_mixed['shot_hierarchy']
assert mixed == mixed_before
checks += 7

def reorder_mixed(value):
    value['members'][2], value['members'][3] = value['members'][3], value['members'][2]
    for order, row in enumerate(value['members'], 1): row['selection_order'] = order

for mutate in [lambda b: b['cgt_scope'].update(origin='https://other.example'),
               lambda b: b['members'][0].update(source_name='e201s999c001__', canonical_name='e201s999c001__'),
               lambda b: b['members'][0]['cgt_identity'].update(entity_id=guid()),
               lambda b: b['members'][0].update(status='Approve'),
               lambda b: b['members'][0].update(artist='Other Artist'),
               lambda b: b['members'][-1].update(parent_id=b['members'][0]['member_id']),
               lambda b: b['members'][1].update(parent_id=b['members'][2]['member_id']),
               lambda b: b['members'][-1].update(gp_shot_uuid=str(uuid4())),
               reorder_mixed]:
    invalid = deepcopy(manual_rename); mutate(invalid['binding'])
    rejected(lambda: local_host._prepare_shot_hierarchy_edit({image.UI_EDIT_REVISION_KEY: 1}, invalid))
    assert mixed == mixed_before

for mutate in [lambda b: b.update(cgt_account_id=guid()),
               lambda b: b['cgt_scope'].update(project_id=guid()),
               lambda b: b['cgt_scope'].update(origin='https://other.example'),
               lambda b: b['members'][0].update(source_name='e201s999c001__'),
               lambda b: b['members'][0]['cgt_identity'].update(entity_id=guid()),
               lambda b: b['members'][0].update(status='Approve'),
               lambda b: b['members'][0].update(artist='Other Artist')]:
    invalid = deepcopy(binding); mutate(invalid)
    rejected(lambda: cgt.verify_binding(invalid, 'superwings12', snapshot))
for status in ['LOGIN_REQUIRED', 'TLS_REJECTED', 'TIMEOUT', 'SOURCE_CHANGED']:
    rejected(lambda: cgt.verify_binding(binding, 'superwings12', {'status': status}))
source_changes['task.account_id'] = guid()
assert query()['status'] == 'OWNERSHIP_CHANGED'
source_changes.clear()
source_changes['pipeline.entity'] = 'Animation'
assert query()['status'] == 'OWNERSHIP_CHANGED'
source_changes.clear()
checks += 2

# Child request never forwards provider/Broker secrets or reuses a login token.
with mock.patch.dict(os.environ, {'GT_CLOUD_API_KEY': 'fixture-secret', 'NO_PROXY': 'unsafe.example'}):
    with mock.patch.object(cgt.subprocess, 'run', return_value=types.SimpleNamespace(returncode=0, stdout=json.dumps(snapshot).encode())) as run:
        assert cgt.catalog('superwings12')['status'] == 'ready'
        args = run.call_args.kwargs
        assert 'GT_CLOUD_API_KEY' not in args['env'] and args['env']['NO_PROXY'] == '127.0.0.1,localhost,::1'
        assert '-I' in run.call_args.args[0] and args['stderr'] == subprocess.DEVNULL
        assert 'token' not in json.loads(args['input'])
    with mock.patch.object(cgt.subprocess, 'run', side_effect=subprocess.TimeoutExpired('fixture', 40)) as run:
        assert cgt.catalog('superwings12')['status'] == 'TIMEOUT' and run.call_count == 1
checks += 5

def make_node():
    node = object.__new__(image.HMBImageAssetLibrary)
    holder = {'state': deepcopy(state), 'published': [], 'responses': []}
    node._hmb_node_deleted = False
    node.lock = False
    node._current_state = lambda: deepcopy(holder['state'])
    def publish(value):
        holder['state'] = image._normalize_state(value)
        holder['published'].append(deepcopy(holder['state']))
        return holder['state']
    node._publish_state = publish
    node._set_thumbnail_bridge_value = lambda value: holder['responses'].append(deepcopy(value))
    intent = dict(schema=image.THUMBNAIL_BRIDGE_SCHEMA, version=1, operation='cgt_confirm', phase='request',
        request_id=str(uuid4()), session_id=str(uuid4()), runtime_instance_id=node._thumbnail_runtime_id(state),
        project_identity=routing.hierarchy_project_key(state), hierarchy_request=deepcopy(command))
    return node, holder, intent

for case in ['success', 'cancel', 'deleted', 'locked', 'resolving', 'stale', 'account_changed', 'timeout', 'publish_failure']:
    node, holder, intent = make_node()
    result = deepcopy(snapshot)
    if case == 'account_changed': result['account_id'] = guid()
    if case == 'timeout': result = {'status': 'TIMEOUT'}
    if case == 'publish_failure':
        original_publish = node._publish_state
        def failed_publish(value):
            result = original_publish(value)
            if value.get('shot_hierarchy', {}).get('members'): raise RuntimeError('Synthetic local publication failure')
            return result
        node._publish_state = failed_publish
    with mock.patch.object(cgt, 'catalog', return_value=result) as read_catalog:
        node._request_cgt_read(intent)
        worker = node._hmb_cgt_thread
        if worker: worker.join(3)
        assert read_catalog.call_args.kwargs['cgt_project_id'] == project_id
        assert not holder['published'], 'Worker mutated the native graph'
        if case == 'cancel': node._apply_thumbnail_bridge_request(dict(intent, operation='cgt_cancel'))
        if case == 'deleted': node._hmb_node_deleted = True
        if case == 'locked': node.lock = True
        if case == 'resolving': node.state = 'resolving'
        if case == 'stale': holder['state']['shot_routing']['generation'] += 1
        node._consume_cgt_result()
    if case == 'success':
        assert len(holder['published']) == 1 and holder['state']['shot_hierarchy'] == binding
        assert holder['responses'][-1]['outcome'] == 'committed'
    elif case == 'publish_failure':
        assert len(holder['published']) == 2 and holder['state'].get('shot_hierarchy', {}) == {}
        assert holder['responses'][-1]['outcome'] == 'rejected'
    else:
        assert not holder['published'] and holder['state'].get('shot_hierarchy', {}) == {}
    checks += 3

# Browsing an authenticated CGT project never changes the current GP project,
# native Shot rows or bindings, including when GP has not been selected yet.
node, holder, intent = make_node()
holder['state'] = image._normalize_state({})
intent = dict(intent, operation='cgt_catalog', cgt_project_id=other_project_id,
    runtime_instance_id=node._thumbnail_runtime_id(holder['state']), project_identity='')
intent.pop('hierarchy_request')
intent['project_db'] = 'untrusted-ui-database'
normalized_intent = image._normalize_thumbnail_bridge(intent)
assert normalized_intent['cgt_project_id'] == other_project_id and 'project_db' not in normalized_intent
projectless_before = deepcopy(holder['state'])
with mock.patch.object(cgt, 'catalog', return_value=other_browse) as read_catalog:
    node._request_cgt_read(normalized_intent)
    worker = node._hmb_cgt_thread
    if worker: worker.join(3)
    node._consume_cgt_result()
    assert read_catalog.call_args.args == ('',)
    assert read_catalog.call_args.kwargs == {'binding': None, 'cgt_project_id': other_project_id}
assert holder['state'] == projectless_before and not holder['published']
assert holder['responses'][-1]['state']['projects'] == other_browse['projects']
assert holder['responses'][-1]['cgt_project_id'] == other_project_id
checks += 6
node, holder, intent = make_node()
intent['cgt_project_id'] = other_project_id
with mock.patch.object(cgt, 'catalog') as read_catalog:
    rejected(lambda: node._request_cgt_read(intent))
    assert not read_catalog.called and not holder['published']
checks += 1

print(json.dumps({'status': 'PASS', 'checks': checks, 'synthetic_cgt_tasks': 5,
    'independent_native_slots': 5, 'live_cgt_calls': 0, 'cgt_writes': 0, 'paid_requests': 0}))
