// Layout-query budgets cover a measured live-editor paging bottleneck.
import assert from 'node:assert/strict';
import fs from 'node:fs';
const load = async (file, extra = '') => import('data:text/javascript;base64,' + Buffer.from(
  fs.readFileSync(new URL('../../widgets/' + file, import.meta.url), 'utf8') + extra).toString('base64'));
const picker = await load('HMBVideoPickerLibraryWidget_v032.js');
const prompt = await load('HMBPromptLibraryScopedBindingWidget.js', '\nexport {hmbRestoreSourceScrollNow};');
let styleReads = 0;
const view = {getComputedStyle(element) { styleReads++; return element.computed || {}; }};
const node = (parent = null, classes = [], attributes = {}) => ({
  parentElement: parent, style: {}, ownerDocument: {defaultView:view},
  classList: {contains: name => classes.includes(name)},
  hasAttribute: name => Object.hasOwn(attributes, name), getAttribute: name => attributes[name] ?? null,
});
const shell = node(null, ['react-flow__node']);
let live = shell;
for (let i = 0; i < 12; i++) live = node(live);
for (let i = 0; i < 200; i++) assert.equal(picker.hmbVideoPickerIsHostMeasurementClone(live), false);
assert.equal(styleReads, 0, 'Live state echoes do not resolve computed style for unrelated ancestors.');
const wrapper = node(shell, ['absolute','left-0','right-0','pointer-events-none']);
const copy = node(wrapper);
wrapper.computed = {visibility:'hidden'};
assert.equal(picker.hmbVideoPickerIsHostMeasurementClone(copy), true);
wrapper.computed = {visibility:'visible'};
assert.equal(picker.hmbVideoPickerIsHostMeasurementClone(copy), false, 'Same host can be promoted to visible without a stale clone cache.');
assert.equal(styleReads, 2, 'CSS-only visibility is still read on the exact measurement wrapper.');
for (const name of ['data-hmb-host-measurement','data-host-measurement','data-measurement-copy']) {
  const explicit = node(shell, [], {[name]:'true'});
  assert.equal(picker.hmbVideoPickerIsHostMeasurementClone(node(explicit)), true);
}
assert.equal(styleReads, 2, 'Explicit clone identities need no layout query.');
const hiddenLive = node(shell, [], {'aria-hidden':'true'});
assert.equal(picker.hmbVideoPickerIsHostMeasurementClone(hiddenLive), false, 'A temporarily hidden live node is not a measurement clone.');

let dimensionReads = 0;
const boxes = Object.fromEntries(['imageSources','videoSources','managerBody'].map(key => [key, {
  scrollTop:0, get scrollHeight(){dimensionReads++;return 1000;}, get clientHeight(){dimensionReads++;return 400;},
}]));
const owner = {dataset:{}, __hmbPromptLibraryScrollMemory:{imageSources:0,videoSources:0,managerBody:0},
  querySelector(selector){return boxes[selector.includes('imageSources') ? 'imageSources' : selector.includes('videoSources') ? 'videoSources' : 'managerBody'];}};
for (let i = 0; i < 200; i++) prompt.hmbRestoreSourceScrollNow(owner);
assert.equal(dimensionReads, 0, 'Unchanged page scroll positions do not measure any prepared group.');
owner.__hmbPromptLibraryScrollMemory.imageSources = 250;
owner.__hmbPromptLibraryScrollMemory.videoSources = 1000;
prompt.hmbRestoreSourceScrollNow(owner);
assert.equal(boxes.imageSources.scrollTop,250);
assert.equal(boxes.videoSources.scrollTop,600, 'A saved position beyond the shortened content clamps to its actual end.');
assert.equal(boxes.managerBody.scrollTop,0);
assert.equal(dimensionReads,4, 'Only the two groups requiring a restore are measured.');
owner.__hmbPromptLibraryScrollMemory.imageSources=0;
prompt.hmbRestoreSourceScrollNow(owner);
assert.equal(boxes.imageSources.scrollTop,0, 'Returning to the top remains supported.');
// Header-ready is broadcast to every mounted HMB node. Exercise the production
// slot predicate directly, including hidden copies that become visible later.
const nativeSource = fs.readFileSync(new URL('../editor/hmb-color-lut-native-header.js', import.meta.url), 'utf8');
const validStart = nativeSource.indexOf('  const valid = (candidate) => {', nativeSource.indexOf('function hmbUseColorLUTNativeHeader('));
const validEnd = nativeSource.indexOf('  const notify = ', validStart);
assert.ok(validStart >= 0 && validEnd > validStart, 'Native slot validator remains available for ownership/visibility regression.');
const validateSlots = new Function('nodeType', 'nodeName', nativeSource.slice(validStart, validEnd) + '\nreturn valid;')('HMBImageAssetLibrary', 'owner');
let nativeStyles = 0, nativeRects = 0, candidateName = 'other', candidateType = 'HMBImageAssetLibrary';
let candidateVisible = true, candidateRect = true, candidateOwnsSlots = true, candidateMarked = true;
const nativeHost = {getAttribute:() => candidateName};
const nativeIdentity = {isConnected:true}, nativeActions = {isConnected:true};
const nativeCandidate = {identity:nativeIdentity, actions:nativeActions, container:{
  isConnected:true, parentElement:nativeHost, closest:() => nativeHost,
  matches:() => candidateMarked, hasAttribute:() => true, getAttribute:() => candidateType,
  contains:element => candidateOwnsSlots && [nativeIdentity, nativeActions].includes(element),
  ownerDocument:{defaultView:{getComputedStyle(){nativeStyles++; return {
    visibility:'visible', display:'block', opacity:candidateVisible ? '1' : '0',
  };}}},
  getClientRects(){nativeRects++; return candidateRect ? [{}] : [];},
}};
for (let i = 0; i < 200; i++) assert.equal(validateSlots(nativeCandidate), false);
candidateName = 'owner'; candidateType = 'HMBPromptLibrary';
assert.equal(validateSlots(nativeCandidate), false);
candidateType = 'HMBImageAssetLibrary'; candidateOwnsSlots = false;
assert.equal(validateSlots(nativeCandidate), false);
candidateOwnsSlots = true; candidateMarked = false;
assert.equal(validateSlots(nativeCandidate), false);
assert.equal(nativeStyles, 0, 'Foreign node/type/slots need no computed-style reads.');
assert.equal(nativeRects, 0, 'Foreign node/type/slots need no layout rect reads.');
candidateMarked = true; candidateVisible = false;
assert.equal(validateSlots(nativeCandidate), false, 'An opacity-zero measurement copy cannot own native controls.');
candidateVisible = true;
assert.equal(validateSlots(nativeCandidate), true, 'The same copy can become the live widget without a stale visibility cache.');
candidateRect = false;
assert.equal(validateSlots(nativeCandidate), false, 'A display-suppressed owner remains ineligible.');
assert.equal(nativeStyles, 3); assert.equal(nativeRects, 2);
console.log('HMB library layout read budget: PASS (live clone/unchanged scroll 0/200; foreign native header style/rect 0/200; dynamic visibility promotion and scroll restoration)');
