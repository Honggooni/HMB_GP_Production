import assert from 'node:assert/strict';
import fs from 'node:fs';
import {createHash} from 'node:crypto';

const files = [
  ['HMBImageAssetLibraryWidget.js', '.hmb-image-assets'],
  ['HMBVideoPickerLibraryWidget_v032.js', '.hmbvp'],
  ['HMBPromptLibraryScopedBindingWidget.js', '.hmb-dashboard'],
  ['HMBAgentLibraryWidget.js', '.hmb-agent-dashboard'],
  ['HMBSeedanceGenerationWidget.js', '.hmb-seedance-shot'],
  ['HMBFinishLookLibraryWidget.js', '.hmb-finish-look'],
];
const modules = await Promise.all(files.map(async ([file, root]) => {
  const url = new URL(`../../widgets/${file}`, import.meta.url);
  const source = fs.readFileSync(url, 'utf8');
  assert.ok(source.includes(`${root} :is(button,input,select,textarea){font-family:inherit}`), `${file}: native controls inherit the common font, without overriding size/weight.`);
  assert.ok(source.includes('"Pretendard Variable",Pretendard,Inter,"Noto Sans KR",system-ui,-apple-system,"Segoe UI",sans-serif'));
  return import(url);
}));
const [image, picker, prompt, agent, seedance, finish] = modules;
const publisher = '10000000-0000-4000-8000-000000000001';
const channel = '20000000-0000-4000-8000-000000000002';
const ids = Array.from({length: 5}, (_, i) => `30000000-0000-4000-8000-${String(i + 1).padStart(12, '0')}`);
const makeState = () => ({
  assets: ids.flatMap((id, shot) => Array.from({length: 3}, (_, i) => ({
    source_uid: `${id}-${i}`, asset_library_id: `${id}-${i}`, source_kind: 'user',
    selected: true, selection_order: shot * 3 + i + 1,
  }))),
  shot_routing: {publisher_instance_uuid: publisher, channel_uuid: channel,
    generation: 1, active_shot_uuid: ids[0], shots: ids.map((shot_uuid, i) => ({
      shot_uuid, number: i + 1, name: `Shot ${i + 1}`, revision: 1,
      selected_source_uids: Array.from({length: 3}, (_, n) => `${shot_uuid}-${n}`),
    }))},
});
function* permutations(items) {
  if (!items.length) { yield []; return; }
  for (const item of items) for (const rest of permutations(items.filter(other => other !== item))) yield [item, ...rest];
}
let checks = 0;
function inspect(state, requestedUuid, previousPicker = {}) {
  const ui = image.hmbImageAssetShotRoutingCatalog(state);
  const {publisher_kind, ...raw} = ui;
  const catalog = {...raw, schema: 'hmb-shot-routing-catalog',
    metadata_sha256: createHash('sha256').update(JSON.stringify(ui)).digest('hex')};
  const expected = ui.shots.map(shot => shot.shot_uuid);
  assert.deepEqual(image.hmbImageAssetCompactShotRows(state).map(row => row.shot_uuid), expected);
  assert.deepEqual(ui.shots.map(shot => shot.number), ui.shots.map((_, i) => i + 1));
  const requested = {channel_uuid: channel, shot_uuid: requestedUuid, number: 1, name: 'Old label'};
  const promptState = {shot: requested, image_asset: {shot_catalog_routing: catalog,
    shot_catalog: ui.shots.map(shot => ({...shot, channel_uuid: channel}))}};
  const values = [
    [agent.hmbAgentState({value: {shot_catalog: catalog, shot: requested}}), agent.hmbAgentShotOptions],
    [seedance.hmbSeedanceShotState({value: {shot_catalog: catalog, shot: requested}}), seedance.hmbSeedanceShotOptions],
    [finish.hmbNormalizeFinishLookWidgetValue({shot_catalog: catalog, shot: requested}), finish.hmbFinishLookShotOptions],
  ];
  for (const [value, options] of values) {
    assert.deepEqual(options(value).filter(row => !row.only).map(row => row.shot_uuid), expected);
    assert.equal(value.shot.shot_uuid, expected.includes(requestedUuid) ? requestedUuid : '', 'Deleted UUID must not bind to the new occupant of its old number.');
    if (value.shot.shot_uuid) assert.equal(value.shot.number, ui.shots.find(shot => shot.shot_uuid === requestedUuid).number);
  }
  const promptOptions = prompt.hmbPromptShotOptions(promptState);
  assert.deepEqual(promptOptions.filter(row => !row.only).map(row => row.shot_uuid), expected);
  assert.equal(promptOptions.find(row => row.selected).shot_uuid, expected.includes(requestedUuid) ? requestedUuid : '');
  let pickerState = picker.hmbApplyPickerShotCatalog(previousPicker, ui);
  assert.deepEqual(pickerState.shot_selections.map(row => row.shot_uuid), expected);
  assert.deepEqual(pickerState.picker_shots.map(row => row.bound_shot_uuid), expected);
  if (expected.includes(requestedUuid)) {
    const workspace = pickerState.picker_shots.find(row => row.bound_shot_uuid === requestedUuid);
    pickerState = picker.hmbSwitchLocalPickerShot(pickerState, workspace.workspace_uuid);
    assert.equal(pickerState.shot_uuid, requestedUuid);
  }
  else {
    // Picker retains the established adjacent-workspace fallback on deletion;
    // consumers remain Only until explicitly/backend bound to a valid UUID.
    assert.ok(!pickerState.shot_uuid || expected.includes(pickerState.shot_uuid));
    assert.notEqual(pickerState.shot_uuid, requestedUuid);
  }
  checks++;
  return pickerState;
}
let deletions = 0, additions = 0;
for (const order of permutations(ids)) {
  const state = makeState();
  let pickerState = inspect(state, order[0]);
  for (const id of order.slice(0, 4)) {
    assert.equal(image.hmbDeleteImageAssetShot(state, id), true);
    pickerState = inspect(state, id, pickerState);
    deletions++;
  }
  const removed = new Set(order.slice(0, 4));
  for (let i = 0; i < 4; i++) {
    assert.equal(image.hmbAddImageAssetShot(state), true);
    const added = state.shot_routing.active_shot_uuid;
    assert.equal(removed.has(added), false, 'Re-created Shot has a fresh UUID.');
    pickerState = inspect(state, added, pickerState);
    additions++;
  }
}
assert.equal(deletions, 480);
assert.equal(additions, 480);

// No persistent cache: in-place changes must be visible on the next render.
const large = makeState();
large.assets.push(...Array.from({length: 10000}, (_, i) => ({source_uid: `unused-${i}`, selected: false})));
let reads = 0;
large.assets.forEach(asset => {
  const selected = asset.selected;
  Object.defineProperty(asset, 'selected', {get() { reads++; return selected; }, configurable: true});
});
image.hmbImageAssetCompactShotRows(large);
assert.ok(reads <= large.assets.length * 2 + 15, `Five Shot projection needs two catalog scans plus 15 selected-card copies, got ${reads}.`);
const first = large.assets[0];
Object.defineProperty(first, 'selected', {value: false, writable: true, configurable: true});
assert.equal(image.hmbImageAssetCompactShotRows(large)[0].assets.some(asset => asset.source_uid === first.source_uid), false);
// A thumbnail completion records only changed entries, preserving other cached
// images. No per-completion walk through every catalog thumbnail is necessary.
const presentation = {project_uid:'six-library-presentation', project_cache_uid:'six-library-cache', project_root:'C:/fixtures/project', assets:[
  {asset_library_id:'old',source_uid:'old',relative_path:'old.png',media_signature:'old-1',thumbnail_url:'https://example.invalid/old.png'},
  {asset_library_id:'new',source_uid:'new',relative_path:'new.png',media_signature:'new-1',thumbnail_url:'https://example.invalid/new.png'},
]};
assert.equal(image.hmbRememberImageAssetPresentation(presentation), 2);
Object.defineProperty(presentation.assets[0], 'thumbnail_url', {get() { throw new Error('Unchanged thumbnail scanned during partial completion'); }});
presentation.assets[1].thumbnail_url = 'https://example.invalid/new-2.png';
assert.equal(image.hmbRememberImageAssetPresentation(presentation, [presentation.assets[1]]), 1);
const adopt = {...presentation, assets: [
  {asset_library_id:'old',source_uid:'old',relative_path:'old.png',media_signature:'old-1',thumbnail_url:''},
  {asset_library_id:'new',source_uid:'new',relative_path:'new.png',media_signature:'new-1',thumbnail_url:''},
]};
assert.equal(image.hmbAdoptImageAssetPresentation(adopt).length, 2);
assert.deepEqual(adopt.assets.map(asset => asset.thumbnail_url), ['https://example.invalid/old.png','https://example.invalid/new-2.png']);
console.log(`Six-library Shot UI continuity: PASS (120 orders, ${deletions} deletions + ${additions} additions, ${checks} synchronous catalog projections; common control fonts).`);
