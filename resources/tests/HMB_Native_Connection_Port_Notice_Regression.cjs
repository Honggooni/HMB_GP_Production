// Expected port retention is information; unrelated failures must remain failures.
const assert = require('node:assert/strict');
const path = require('node:path');
const vm = require('node:vm');
const {spawnSync} = require('node:child_process');
const root = path.resolve(__dirname, '../..');
const python = process.env.HMB_TEST_PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
const code = `import importlib.util,json,pathlib,sys
r=pathlib.Path(sys.argv[1]);s=importlib.util.spec_from_file_location('a',r/'tools/hmb_native_semantic_adapter.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
h=m._compiled_helper((r/'resources/editor/hmb-color-lut-native-header.js').read_text('utf-8'))
a=h.index('function hmbNativePortRetainedNotice(');b=h.index('function hmbNativeConnectionDeletionNotice(',a)
print(json.dumps({'notice':h[a:b],'dirty_correct':'vY.getState().setDirty(true)' in h,'old_dirty_absent':'kq.getState()' not in h}))`;
const result = spawnSync(python, ['-I', '-B', '-c', code, root], {encoding:'utf8'});
assert.equal(result.status, 0, result.stderr);
const compiled = JSON.parse(result.stdout);
assert.equal(compiled.dirty_correct, true);
assert.equal(compiled.old_dirty_absent, true);
const calls = [];
const context = {hmbNativeStudioFlowEpoch:1, hmbNativeConnectionNotices:new Map(),
  __r:x=>typeof x==='string'?x:x?.details||x?.result_details||'',
  CJ:{info:(...args)=>calls.push(args)}};
vm.createContext(context);
vm.runInContext(compiled.notice+';globalThis.notice=hmbNativePortRetainedNotice;', context);
for (const value of [null, {}, 'Unknown failure', {details:'[HMB_CONNECTION_DETACHED] explicit connect refused'},
  {details:'[HMB_DELETE_CONNECTED] connected node cannot be deleted'}]) {
  assert.equal(context.notice(value, {node_name:'fixture'}), false);
}
assert.equal(calls.length, 0);
const protectedResult = {details:'[HMB_CONNECTION_PORT_RETAINED] original port retained'};
assert.equal(context.notice(protectedResult, {node_name:'fixture'}), true);
assert.equal(calls.length, 1);
assert.equal(context.notice(protectedResult, {node_name:'fixture'}), true);
assert.equal(calls.length, 1, 'Duplicate automatic cleanup must not flood notifications');
assert.equal(context.notice({result_details:'[HMB_CONNECTION_PORT_RETAINED] another port'}, {node_name:'other'}), true);
assert.equal(calls.length, 2);
assert.ok(calls.every(x=>x[1].duration===3000));
console.log('Native port retention notice and dirty store: PASS');
