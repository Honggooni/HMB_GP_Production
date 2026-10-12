import assert from 'node:assert/strict';
import { hmbNormalizeImageAssetState, hmbPublishImageAssetState,
  hmbBuildImageAssetCompactEdit, hmbConsumeImageAssetStateEcho } from '../../widgets/HMBImageAssetLibraryWidget.js';

const state = hmbNormalizeImageAssetState({
  edit_transport_schema: 'hmb-image-asset-edit-v1', scan_revision: 7,
  project_uid: 'project-one', project_cache_uid: 'cache-one',
  manifest_signature: 'manifest-one', folder_signature: 'folder-one',
  assets: Array.from({ length: 1000 }, (_, i) => ({
    asset_library_id: `library-${i}`, asset_id: `asset-${i}`, source_uid: `source-${i}`,
    source_kind: 'project', registered: true, path: `C:/fixture/${i}.png`,
    image_name: `Asset ${i}`, selected: i < 2, selection_order: i + 1,
  })),
});
assert.equal(state.assets.length, 1000);
const identity = Object.fromEntries(['catalog_root', 'project_root', 'project_uid', 'project_cache_uid',
  'manifest_signature', 'folder_signature', 'scan_revision'].map((key) => [key, state[key]]));
const container = { __hmbImageAssetAcceptedEditCatalogIdentity: identity };
let wire;
const stringify = JSON.stringify;
JSON.stringify = function(value, ...args) {
  assert.ok(!Array.isArray(value?.assets), 'Edit publication serialized the full catalog');
  return stringify(value, ...args);
};
try {
  state.search = 'hero';
  hmbPublishImageAssetState(container, { onChange: (value) => { wire = value; } }, state,
    null, { suppressMatchingEcho: true });
} finally { JSON.stringify = stringify; }
const request = JSON.parse(wire);
assert.equal(request.schema, 'hmb-image-asset-edit-v1');
assert.equal(request.edits.search, 'hero');
assert.equal(request.catalog_identity.scan_revision, 7);
assert.equal(request.edits.shot_routing.shots[0].shot_uuid, state.shot_routing.shots[0].shot_uuid);
assert.equal(request.selected_source_uids.length, 2);
assert.ok(!('assets' in request) && !('projects' in request));
assert.ok(wire.length < stringify(state).length / 20);
assert.equal(hmbConsumeImageAssetStateEcho(container, { value: stringify(state) }), true);
assert.equal(hmbBuildImageAssetCompactEdit({ ...state, project_uid: 'different' }, identity), null);
assert.equal(hmbBuildImageAssetCompactEdit({ ...state, edit_transport_schema: '' }, identity), null);

// Registration/disconnect/cleanup intents remain compact; the referenced
// source and private server authority are still validated by Python.
state.asset_registration_request = { request_id: 'register-1', source_uid: state.assets[0].source_uid };
state.disconnect_import_uid = 'import:exact-input';
state.asset_cleanup_request = { request_id: 'cleanup-1' };
const intents = hmbBuildImageAssetCompactEdit(state, identity);
assert.equal(intents.edits.asset_registration_request.request_id, 'register-1');
assert.equal(intents.edits.disconnect_import_uid, 'import:exact-input');
assert.equal(intents.edits.asset_cleanup_request.request_id, 'cleanup-1');
let legacyWire;
hmbPublishImageAssetState({}, { onChange: (value) => { legacyWire = value; } },
  hmbNormalizeImageAssetState({ assets: state.assets }));
assert.equal(JSON.parse(legacyWire).assets.length, 1000);
console.log(JSON.stringify({ status: 'PASS', catalog_rows: 1000, compact_bytes: wire.length,
  full_bytes: stringify(state).length, checks: ['no full stringify', 'Shot/source ownership', 'echo', 'legacy', 'intents'] }));
