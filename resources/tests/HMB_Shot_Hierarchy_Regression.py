"""Independent execution slots, atomic hierarchy edits and immutable receipts.

All names/media/account IDs are synthetic. No CGT/Broker/provider calls.
"""
from __future__ import annotations
import copy
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest import mock
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import _hmb_shot_routing as routing
import HMBImageAssetLibrary as image

checks = 0
def rejects(action):
    global checks
    try:
        action()
    except ValueError:
        checks += 1
        return
    raise AssertionError('Invalid hierarchy was accepted')

base = image._default_state()
base.update(project_root='C:/fixture/project/Ai_Ct_image/project', project_id='fixture', project_uid='fixture-project')
slot = base['shot_routing']['shots'][0]['shot_uuid']
base['shot_routing']['shots'][0]['selected_source_uids'] = ['fixture-source']
base['historical_unknown_task'] = {'task_id': 'fixture-retained-task', 'result': 'unchanged'}

def member(i, target=None, name=None):
    identity = str(uuid4())
    parsed = routing.hierarchy_parse_name(name or f'e201s{i:03d}c001__')
    return dict(member_id='manual:' + identity, origin='manual', manual_uuid=identity,
                source_name=parsed['source_name'], canonical_name=parsed['canonical_name'],
                gp_shot_uuid=target or str(uuid4()), parent_id=None, selection_order=i,
                cgt_task_id=None, artist=None, status=None)

def request(state, members, prior=None):
    prior = prior if prior is not None else state.get('shot_hierarchy', {})
    return dict(schema=routing.SHOT_HIERARCHY_REQUEST_SCHEMA, version=1,
                expected_generation=state['shot_routing']['generation'], expected_binding_revision=prior.get('revision', 0),
                removed_member_ids=[row['member_id'] for row in prior.get('members', []) if not any(item['member_id'] == row['member_id'] for item in members)],
                binding=dict(schema=routing.SHOT_HIERARCHY_SCHEMA, version=1,
                    binding_id=prior.get('binding_id', str(uuid4())), revision=prior.get('revision', 0) + 1,
                    project_identity=routing.hierarchy_project_key(state), channel_uuid=state['shot_routing']['channel_uuid'],
                    cgt_account_id=None, members=copy.deepcopy(members)))

members = [member(i, slot if i == 1 else None) for i in range(1, 6)]
members[1]['parent_id'] = members[0]['member_id']
members[3]['parent_id'] = members[2]['member_id']
original = copy.deepcopy(base)
command = request(base, members)
updated = routing.apply_shot_hierarchy_edit(base, command)
assert base == original, 'Pure preparation mutated the live graph'
assert len(updated['shot_routing']['shots']) == 5
assert len({row['shot_uuid'] for row in updated['shot_routing']['shots']}) == 5
assert updated['shot_routing']['shots'][0]['selected_source_uids'] == ['fixture-source']
assert updated['historical_unknown_task'] == base['historical_unknown_task']
expected = ['e201_s001c001-s002c001__', 'e201s002c001__', 'e201_s003c001-s004c001__', 'e201s004c001__', 'e201s005c001__']
assert [row['name'] for row in updated['shot_routing']['shots']] == expected
checks += 6

# Every root count and executable count; an empty default is not silently reused.
for count in range(6):
    rows = [member(i, slot if i == 1 else None) for i in range(1, count + 1)]
    result = routing.apply_shot_hierarchy_edit(base, request(base, rows))
    assert len(result['shot_routing']['shots']) == max(1, count)
    checks += 1
rejects(lambda: routing.apply_shot_hierarchy_edit(base, request(base, [member(i) for i in range(1, 6)])))
rejects(lambda: routing.apply_shot_hierarchy_edit(base, request(base, [member(i) for i in range(1, 7)])))
again = routing.apply_shot_hierarchy_edit(updated, request(updated, members))
assert again == updated
checks += 1

for mutate in [
    lambda rows: rows[0].update(parent_id=rows[0]['member_id']),
    lambda rows: rows[0].update(parent_id=rows[1]['member_id']),
    lambda rows: rows[4].update(parent_id='missing'),
    lambda rows: rows[4].update(gp_shot_uuid=rows[0]['gp_shot_uuid']),
    lambda rows: rows[4].update(member_id=rows[0]['member_id']),
    lambda rows: rows[4].update(canonical_name=rows[0]['canonical_name'], source_name=rows[0]['source_name']),
    lambda rows: rows[4].update(origin='cgt', cgt_task_id='unverified-task'),
    lambda rows: rows[4].update(source_name='e202s005c001__', canonical_name='e202s005c001__'),
]:
    invalid = copy.deepcopy(members); mutate(invalid)
    before = copy.deepcopy(updated)
    rejects(lambda: routing.apply_shot_hierarchy_edit(updated, request(updated, invalid)))
    assert updated == before

# A child may also own a group without losing its parent or execution slot.
nested_members = copy.deepcopy(members)
nested_members[2]['parent_id'] = nested_members[1]['member_id']
nested = routing.apply_shot_hierarchy_edit(updated, request(updated, nested_members))
assert [row['name'] for row in nested['shot_routing']['shots']] == [
    'e201_s001c001-s002c001__', 'e201_s002c001-s003c001__',
    'e201_s003c001-s004c001__', 'e201s004c001__', 'e201s005c001__']
assert nested['shot_hierarchy']['members'][1]['parent_id'] == members[0]['member_id']
assert [row['shot_uuid'] for row in nested['shot_routing']['shots']] == [row['shot_uuid'] for row in updated['shot_routing']['shots']]
assert nested['shot_routing']['shots'][0]['selected_source_uids'] == ['fixture-source']
assert nested['historical_unknown_task'] == updated['historical_unknown_task']
assert image._normalize_state(json.dumps(nested))['shot_hierarchy'] == nested['shot_hierarchy']
for child_index, parent_index in [(0, 3), (1, 2), (2, 3), (3, 3)]:
    invalid = copy.deepcopy(nested_members)
    invalid[child_index]['parent_id'] = invalid[parent_index]['member_id']
    rejects(lambda: routing.apply_shot_hierarchy_edit(nested, request(nested, invalid)))
assert routing.apply_shot_hierarchy_edit(nested, request(nested, members))['shot_hierarchy']['members'] == members
checks += 7

invalid = request(updated, members); invalid['expected_generation'] -= 1
rejects(lambda: routing.apply_shot_hierarchy_edit(updated, invalid))
invalid = request(updated, members); invalid['binding']['project_identity'] = 'different-project'
rejects(lambda: routing.apply_shot_hierarchy_edit(updated, invalid))
rejects(lambda: routing.apply_shot_hierarchy_edit(updated, request(updated, members[1:])))
unacknowledged = request(updated, [])
unacknowledged['removed_member_ids'] = []
rejects(lambda: routing.apply_shot_hierarchy_edit(updated, unacknowledged))
all_released = routing.apply_shot_hierarchy_edit(updated, request(updated, []))
assert len(all_released['shot_routing']['shots']) == 5
other_project = dict(updated, project_root='C:/fixture/other-project')
rejects(lambda: routing.apply_shot_hierarchy_edit(other_project, request(other_project, members)))
other_cleared = routing.apply_shot_hierarchy_edit(other_project, request(other_project, []))
assert other_cleared['shot_hierarchy']['members'] == []
checks += 2

# Detach/move and root removal preserve the five native media/execution slots.
moved = copy.deepcopy(members); moved[1]['parent_id'] = members[2]['member_id']
detached = routing.apply_shot_hierarchy_edit(updated, request(updated, moved))
assert detached['shot_routing']['shots'][0]['name'] == members[0]['canonical_name']
assert detached['shot_routing']['shots'][2]['name'] == 'e201_s003c001-s002c001-s004c001__'
remaining = copy.deepcopy(moved); remaining[1]['parent_id'] = None; remaining[3]['parent_id'] = None
unparented = routing.apply_shot_hierarchy_edit(detached, request(detached, remaining))
released = routing.apply_shot_hierarchy_edit(unparented, request(unparented, []))
assert len(released['shot_routing']['shots']) == 5
assert released['shot_hierarchy']['members'] == []
assert [row['name'] for row in released['shot_routing']['shots']] == [row['canonical_name'] for row in members]
checks += 5

# Exact source context is distinct from the execution name; s identifies a
# shot, c identifies its split. Parsing a name never manufactures a CGT Task.
for text in ['e201/e201s001c001__', 'e201s001c002__', '수동_이름__']:
    parsed = routing.hierarchy_parse_name(text)
    assert parsed['source_name'] == text
    assert '/' not in parsed['canonical_name']
    checks += 1
assert routing.hierarchy_parse_name('e201s001c002__')['shot'] == 's001'
assert routing.hierarchy_parse_name('e201s001c002__')['split_cut'] == 'c002'
for text in ['', ' x', 'x ', 'x\nname', 'a/b', '../a', 'x' * 129, '😀' * 65, 'a  b', 'e202/e201s001c001__']:
    rejects(lambda: routing.hierarchy_parse_name(text))
long = [member(1, slot, 'x' * 70), member(2, name='y' * 70)]
long[1]['parent_id'] = long[0]['member_id']
rejects(lambda: routing.apply_shot_hierarchy_edit(base, request(base, long)))

# Real ImageAsset serializer, reset, compact host command and legacy restore.
wire_state = copy.deepcopy(updated)
wire_state['assets'] = []
wire_state['shot_routing']['shots'][0]['selected_source_uids'] = []
wire_state = image._normalize_state(wire_state)
saved = json.dumps(wire_state, ensure_ascii=False)
restored = image._normalize_state(saved)
assert restored['shot_hierarchy'] == wire_state['shot_hierarchy']
assert [row['name'] for row in restored['shot_routing']['shots']] == expected
reset = image._reset_image_asset_state_preserving_shot_media(restored)
assert reset['shot_hierarchy'] == restored['shot_hierarchy']
assert not image._normalize_state({})['shot_hierarchy']
host = image.HMBImageAssetLibrary.__new__(image.HMBImageAssetLibrary)
host._hmb_last_accepted_widget_state = json.dumps(image._normalize_state(base))
host._hmb_last_accepted_widget_revisions = (0, 0)
host._hmb_last_accepted_thumbnail_revision = 0
edit = dict(schema=image.IMAGE_ASSET_EDIT_SCHEMA, version=1, ui_edit_revision=1, scan_revision=0,
            catalog_identity={field: image._normalize_state(base)[field] for field in ('catalog_root', 'project_root', 'project_uid', 'project_cache_uid', 'manifest_signature', 'folder_signature', 'scan_revision')},
            selected_source_uids=[], edits={'shot_hierarchy_request': command})
prepared = image._normalize_state(host._expand_widget_edit(edit))
assert prepared['shot_hierarchy']['members'] == members
assert [row['name'] for row in prepared['shot_routing']['shots']] == expected
assert 'shot_hierarchy_request' not in prepared
checks += 7

# Manual Shot management is available before project discovery or CGT login.
# Its existing native slot owns the edit, and first project selection adopts
# only the previously empty manual scope without replacing that slot.
unselected = image._normalize_state({})
manual_slot = unselected['shot_routing']['shots'][0]['shot_uuid']
manual_rows = [member(1, manual_slot, 'local_shot')]
local = routing.apply_shot_hierarchy_edit(unselected, request(unselected, manual_rows))
assert local['shot_hierarchy']['project_identity'] == ''
assert local['shot_routing']['shots'][0]['shot_uuid'] == manual_slot
assert image._normalize_state(json.dumps(local))['shot_hierarchy'] == local['shot_hierarchy']
renamed_rows = copy.deepcopy(manual_rows)
renamed_rows[0].update(source_name='renamed_local_shot', canonical_name='renamed_local_shot')
renamed = routing.apply_shot_hierarchy_edit(local, request(local, renamed_rows))
assert renamed['shot_routing']['shots'][0]['name'] == 'renamed_local_shot'
assert renamed['shot_routing']['shots'][0]['shot_uuid'] == manual_slot
assert renamed['shot_routing']['shots'][0]['selected_source_uids'] == local['shot_routing']['shots'][0]['selected_source_uids']
unselected_catalog = dict(renamed, projects=[dict(project_id='fixture', project_uid='fixture-project',
    name='fixture', path='C:/fixture/project/Ai_Ct_image/project')])
synthetic_scan = dict(project_root='C:/fixture/project/Ai_Ct_image/project', project_id='fixture',
    project_uid='fixture-project', project_cache_uid='', manifest_signature='', folder_signature='',
    folders=[], assets=[], warnings=[])
with mock.patch.object(image, '_adopt_shared_catalog_snapshot', return_value=None), mock.patch.object(image, '_scan_project_assets', return_value=synthetic_scan):
    selected_project = image._select_catalog_project(unselected_catalog, synthetic_scan['project_root'])
assert selected_project['shot_hierarchy']['project_identity'] == routing.hierarchy_project_key(selected_project)
assert selected_project['shot_hierarchy']['members'] == renamed['shot_hierarchy']['members']
assert selected_project['shot_routing']['shots'] == renamed['shot_routing']['shots']
assert image._normalize_state(json.dumps(selected_project))['shot_hierarchy'] == selected_project['shot_hierarchy']
changed_again = copy.deepcopy(renamed_rows)
changed_again[0].update(source_name='second_local_name', canonical_name='second_local_name')
after_selection = routing.apply_shot_hierarchy_edit(selected_project, request(selected_project, changed_again))
assert after_selection['shot_routing']['shots'][0]['name'] == 'second_local_name'
assert renamed['shot_hierarchy']['project_identity'] == '', 'Project adoption mutated the prior saved state'
checks += 13
print(json.dumps({'status':'PASS', 'checks': checks, 'independent_slots':5, 'paid_requests':0, 'cgt_writes':0}))
