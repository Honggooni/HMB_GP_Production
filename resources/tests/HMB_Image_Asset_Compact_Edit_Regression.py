"""Compact edits cannot replace catalog authority or roll back Shot ownership."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import sys
import threading
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import HMBImageAssetLibrary as image

state = image._default_state()
state.update(project_uid='project-uid', project_cache_uid='cache-uid',
             manifest_signature='manifest-one', folder_signature='folder-one', scan_revision=7)
state['assets'] = [dict(asset_library_id=f'library-{i}', asset_id=f'asset-{i}', source_uid=f'source-{i}',
                        source_kind='project', registered=True, path=f'C:/fixture/{i}.png',
                        image_name=f'Asset {i}', selected=i == 0, selection_order=1 if i == 0 else 0)
                   for i in range(1000)]
state = image._normalize_state(state)
node = image.HMBImageAssetLibrary.__new__(image.HMBImageAssetLibrary)
node._hmb_last_accepted_widget_state = None
node._hmb_last_accepted_widget_revisions = (0, 0)
node._hmb_last_accepted_thumbnail_revision = 0
node._accept_widget_state_baseline(state)
state = json.loads(node._hmb_last_accepted_widget_state)
source0, source1 = [asset['source_uid'] for asset in state['assets'][:2]]
routing = copy.deepcopy(state['shot_routing'])
routing['shots'][0]['selected_source_uids'] = [source1, source0]
routing['shots'][0]['revision'] += 1
routing['generation'] += 1
edit = dict(schema=image.IMAGE_ASSET_EDIT_SCHEMA, version=1, scan_revision=7, ui_edit_revision=1,
            catalog_identity={field:state[field] for field in ('catalog_root', 'project_root', 'project_uid',
                'project_cache_uid', 'manifest_signature', 'folder_signature', 'scan_revision')},
            selected_source_uids=[source1, source0], edits=dict(search='hero', shot_routing=routing))
merged = node._expand_widget_edit(edit)
assert len(merged['assets']) == 1000
assert merged['assets'][0]['path'] == state['assets'][0]['path']
assert merged['assets'][1]['selection_order'] == 1 and merged['assets'][0]['selection_order'] == 2
assert merged['shot_routing']['shots'][0]['shot_uuid'] == state['shot_routing']['shots'][0]['shot_uuid']
assert merged['search'] == 'hero'
assert len(json.dumps(edit)) < len(json.dumps(state)) / 20

def rejected(payload):
    prior = node._hmb_last_accepted_widget_state
    try:
        node._expand_widget_edit(payload)
    except ValueError:
        assert node._hmb_last_accepted_widget_state == prior
        return
    raise AssertionError('Invalid compact edit accepted')

for field in ('project_uid', 'project_cache_uid', 'manifest_signature', 'folder_signature', 'scan_revision'):
    stale = copy.deepcopy(edit)
    stale['catalog_identity'][field] = 6 if field == 'scan_revision' else 'other-owner'
    rejected(stale)
unknown = copy.deepcopy(edit); unknown['selected_source_uids'].append('missing-source'); rejected(unknown)
for field in ('assets', 'projects', 'project_root'):
    forged = copy.deepcopy(edit); forged['edits'][field] = []; rejected(forged)
wrong = copy.deepcopy(edit); wrong['edits']['shot_routing']['channel_uuid'] = 'different-channel'; rejected(wrong)
same_row = copy.deepcopy(edit)
same_row['edits']['shot_routing']['shots'][0]['revision'] = state['shot_routing']['shots'][0]['revision']
rejected(same_row)
node._accept_widget_state_baseline(merged)
older = copy.deepcopy(edit); older['ui_edit_revision'] = 0; rejected(older)
old_row = copy.deepcopy(edit); old_row['ui_edit_revision'] = 2
old_row['edits']['shot_routing']['shots'][0]['revision'] -= 1; rejected(old_row)

# The normal pre-set path emits a full canonical retained state, never an
# envelope in saved workflows. Legacy full payload hydration stays compatible.
node._hmb_state_syncing = False; node._hmb_restoring_widget_state = False
node._consume_pending_catalog_scan_result = lambda: None
node._consume_pending_thumbnail_result = lambda: None
node._consume_pending_catalog_probe_result = lambda: None
next_edit = copy.deepcopy(edit); next_edit['ui_edit_revision'] = 2
canonical = node.before_value_set(SimpleNamespace(name=image.WIDGET_STATE_PARAMETER), json.dumps(next_edit))
assert json.loads(canonical)['schema'] == image.STATE_SCHEMA
assert len(json.loads(canonical)['assets']) == 1000
assert node._expand_widget_edit(state)['assets'] == state['assets']

# An older ready scan may advance the scan clock during the exact value-set
# that selects a project. Rebase only that fresh path, never the client's old
# catalog, Shot routing, identities or commands.
prior = image._normalize_state(state)
root = '//192.168.200.19/v/projects/Ai_Ct_image'
target = root + '/Dinoster5'
prior.update(catalog_root=root, project_root='', project_id='', project_uid='', project_cache_uid='',
             projects=[dict(path=target, project_id='Dinoster5', project_uid='server-project', name='Dinoster5')],
             scan_revision=7, ui_edit_revision=12)
latest = copy.deepcopy(prior); latest['scan_revision'] = 8
intent = copy.deepcopy(prior); intent.update(project_root=target, ui_edit_revision=13, assets=[])
intent['shot_routing'] = {'channel_uuid': 'forged-client-channel'}
intent['asset_cleanup_request'] = {'request_id': 'forged-client-command'}
rebase = image.HMBImageAssetLibrary._rebase_fresh_project_selection
rebased = rebase(intent, prior, latest)
assert rebased and rebased['project_root'] == target and rebased['scan_revision'] == 8
assert rebased['assets'] == latest['assets'] and rebased['shot_routing'] == latest['shot_routing']
assert rebased['asset_cleanup_request'] == latest['asset_cleanup_request']
assert all(rebased[field] == '' for field in ('project_id', 'project_uid', 'project_cache_uid'))
for field, value in [('ui_edit_revision', 12), ('scan_revision', 6), ('project_id', 'client-id'),
                     ('project_uid', 'client-uid'), ('project_cache_uid', 'client-cache'),
                     ('catalog_root', root + '/Other'), ('project_root', root + '/Missing')]:
    invalid = copy.deepcopy(intent); invalid[field] = value
    assert rebase(invalid, prior, latest) is None, field
for changed in [dict(latest, projects=[]), dict(latest, catalog_root=root + '/Other'),
                dict(latest, ui_edit_revision=13), dict(latest, scan_revision=7)]:
    assert rebase(intent, prior, changed) is None

race = image.HMBImageAssetLibrary.__new__(image.HMBImageAssetLibrary)
race._hmb_state_syncing = race._hmb_restoring_widget_state = False
race._hmb_last_accepted_widget_state = image._json_text(prior)
race._hmb_last_accepted_widget_revisions = (7, 12)
race._hmb_last_accepted_thumbnail_revision = 0
race._hmb_scan_lock = threading.RLock(); race._hmb_scan_generation = 1
race._hmb_scan_pending_key = 'initial:ready'; race._hmb_fresh_registration_scan_key = 'initial:ready'
race._hmb_import_media_by_uid = {}; race._hmb_scan_thread = object()
payload = dict(state=latest, scan_base=prior, media_by_uid=None, result_merger=None, on_published=None)
race._hmb_scan_pending_result = (1, 'initial:ready', 'ready-id', payload)
race._scan_owner_is_current = lambda: True
race._current_state = lambda: copy.deepcopy(prior)
race._consume_pending_catalog_scan_result = lambda: None
race._consume_pending_thumbnail_result = race._consume_pending_catalog_probe_result = lambda: None
race._publish_state = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError('old-root publication escaped'))
canonical = json.loads(race.before_value_set(SimpleNamespace(name=image.WIDGET_STATE_PARAMETER), intent))
assert canonical['project_root'] == target and canonical['scan_revision'] == 8
assert canonical['ui_edit_revision'] == 13 and canonical['assets'] == latest['assets']
assert canonical['shot_routing'] == latest['shot_routing']
assert race._hmb_scan_generation == 2 and race._hmb_scan_pending_result is None
assert race._hmb_fresh_registration_scan_key == '' and race._hmb_hydration_adopted is True

# A second completion can publish after the ready scan was taken. Its facts,
# target list and UI clock must be rechecked before committing the new root.
for variant in ('probe', 'thumbnail', 'removed-target', 'new-ui', 'new-catalog'):
    race._hmb_last_accepted_widget_state = image._json_text(prior)
    race._hmb_last_accepted_widget_revisions = (7, 12)
    race._hmb_scan_generation = 1; race._hmb_scan_pending_key = 'initial:ready'
    race._hmb_scan_pending_result = (1, 'initial:ready', 'id', dict(payload))
    newer = copy.deepcopy(latest if variant != 'thumbnail' else prior)
    newer['manifest_signature'] = 'latest-post-drain-facts'
    newer['assets'][0]['image_name'] = 'Latest server fact'
    if variant == 'removed-target': newer['projects'] = []
    if variant == 'new-ui': newer['ui_edit_revision'] = 13
    if variant == 'new-catalog': newer['catalog_root'] = root + '/Other'
    race._consume_pending_catalog_probe_result = lambda: race._accept_widget_state_baseline(newer)
    after = json.loads(race.before_value_set(SimpleNamespace(name=image.WIDGET_STATE_PARAMETER), intent))
    if variant in ('removed-target', 'new-ui', 'new-catalog'):
        assert after['project_root'] == newer['project_root'], variant
    else:
        assert after['project_root'] == target and after['scan_revision'] == 8, variant
        assert after['manifest_signature'] == newer['manifest_signature'], variant
        assert after['assets'][0]['image_name'] == 'Latest server fact', variant
        assert after['shot_routing'] == newer['shot_routing'], variant
race._consume_pending_catalog_probe_result = lambda: None

# Callback/import handoffs, reentrancy, retired owners and outdated generations
# are not pure catalog publication and must keep normal consumption behavior.
for variant in ('callback', 'merger', 'imports', 'reentrant', 'owner', 'generation'):
    candidate_payload = dict(payload)
    race._hmb_scan_generation = 1; race._hmb_scan_pending_key = 'initial:ready'
    race._hmb_catalog_completion_active = variant == 'reentrant'
    race._scan_owner_is_current = lambda: variant != 'owner'
    if variant == 'callback': candidate_payload['on_published'] = lambda _state: None
    if variant == 'merger': candidate_payload['result_merger'] = lambda *_args: latest
    if variant == 'imports': candidate_payload['media_by_uid'] = {'source': 'image'}
    pending = (0 if variant == 'generation' else 1, 'initial:ready', 'id', candidate_payload)
    race._hmb_scan_pending_result = pending
    assert race._take_pending_project_selection(intent, prior) is None, variant
    assert race._hmb_scan_pending_result is pending
print('PASS: compact edits and fresh project intent survive pure pending scan; authority/stale/owner guards retained')
