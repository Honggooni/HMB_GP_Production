// Preserve authored layers while admitting only validated new HMB sources.
const assert = require('node:assert/strict');
const path = require('node:path');
const vm = require('node:vm');
const {spawnSync} = require('node:child_process');
const root = path.resolve(__dirname, '../..');
const python = process.env.HMB_TEST_PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
const code = `import ast,json,pathlib,sys
p=pathlib.Path(sys.argv[1])/'tools/hmb_native_semantic_adapter.py';tree=ast.parse(p.read_text('utf-8'))
f=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='_bash_live_input_bridge')
a=next(x for x in f.body if isinstance(x,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='helpers' for t in x.targets))
print(json.dumps(ast.literal_eval(a.value)))`;
const result = spawnSync(python, ['-I', '-B', '-c', code, root], {encoding: 'utf8'});
assert.equal(result.status, 0, result.stderr);
const helpers = JSON.parse(result.stdout);
let created;
class FakeImage {
  constructor() { created = this; }
  set src(value) { this._src = value; }
  get src() { return this._src; }
}
const scope = {Map, Set, Promise, Error, Number, Date, AbortController, setTimeout, clearTimeout,
  window: {Image: FakeImage}};
vm.createContext(scope);
vm.runInContext(helpers, scope);
const binding = (uid, url = '/source') => ({source_uid: uid, source_id: 'src-' + uid, url});
const layer = (uid, url = '/source') => ({id: 'layer-' + uid, type: 'image', source_uid: uid,
  source_id: 'src-' + uid, src: url, x: 71, y: 89, rotation: 19, scaleX: 2, scaleY: .5, order: 3});
const proof = {sha256: 'a'.repeat(64), rgba_sha256: 'b'.repeat(64), width: 32, height: 24};
function meta(rows, {suppressed = []} = {}) {
  return {input_images: rows.map(r => ({id: r.source_id, source_uid: r.source_uid, url: r.url, name: r.source_uid})),
    konva_json: {images: rows.map(r => layer(r.source_uid, r.url)), lines: []},
    hmb_image_bash: {source_bindings: rows, suppressed_source_uids: suppressed,
      prepared_source_hashes: Object.fromEntries(rows.map(r => ['input:' + r.source_id, {...proof}]))}};
}

(async () => {
  const before = meta([binding('one')]);
  const next = meta([binding('one'), binding('two')]);
  const canvas = {marker: 'authored-brush-canvas'};
  const brush = {id: 'brush', type: 'brush', canvas, x: 23, rotation: 42, order: 7};
  const authored = {...layer('one'), x: 109, visible: false};
  const plan = scope.hmbModalLivePlan(before, next);
  const merged = scope.hmbModalLiveMerge([authored, brush], plan.additions);
  assert.equal(merged[0], authored);
  assert.equal(merged[1], brush);
  assert.equal(merged[1].canvas, canvas);
  assert.equal(merged[2].source_uid, 'two');
  assert.equal(merged[2].order, 8);
  assert.equal(authored.x, 109);
  assert.equal(authored.visible, false);
  const hidden = meta([binding('one'), binding('two')], {suppressed: ['two']});
  assert.equal(scope.hmbModalLivePlan(before, hidden).additions.length, 0);
  assert.throws(() => scope.hmbModalLivePlan(next, before), /removed/);
  assert.throws(() => scope.hmbModalLiveBindings(meta([binding('one'), binding('one')])), /ambiguous/);
  assert.throws(() => scope.hmbModalLiveMerge([authored], [layer('one')]), /collision/);

  const alias = meta([binding('one', '/source?v=new')]);
  assert.equal(scope.hmbModalLivePlan(before, alias).additions.length, 0);
  assert.equal(scope.hmbModalLivePlan(before, alias).aliases.length, 1);
  assert.equal(authored.src, '/source', 'Same bytes must not reload the rendered authored layer');
  assert.equal(scope.hmbModalLiveOutputURL(authored, alias), '/source?v=new');
  assert.equal(scope.hmbModalLiveOutputURL(brush, alias), '');
  const changed = meta([binding('one')]);
  changed.hmb_image_bash.prepared_source_hashes['input:src-one'].sha256 = 'c'.repeat(64);
  assert.throws(() => scope.hmbModalLivePlan(before, changed), /content changed/);
  const incomplete = meta([binding('one', '/other')]);
  delete incomplete.hmb_image_bash.prepared_source_hashes;
  assert.throws(() => scope.hmbModalLivePlan(before, incomplete), /content changed/);

  const aborter = new AbortController();
  const pending = scope.hmbModalLiveImage('/fixture', aborter.signal);
  assert.equal(typeof created.onload, 'function');
  aborter.abort();
  await assert.rejects(pending, /canceled/);
  assert.equal(created.onload, null);
  assert.equal(created.onerror, null);
  assert.equal(created.src, '');
  await assert.rejects(scope.hmbModalLiveBound(new Promise(() => {}), null, 5), /source_timeout/);
  console.log('Native Bash live inputs: authored state, identities, aliases and cancellation PASS');
})().catch(error => {console.error(error); process.exitCode = 1;});
