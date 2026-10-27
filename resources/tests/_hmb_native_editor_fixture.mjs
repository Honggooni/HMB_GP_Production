// Test-only access to the exact supported upstream editor. CI obtains these
// bytes from its hash-pinned official distribution; no bundle is tracked here.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {createRequire} from 'node:module';
import {spawnSync} from 'node:child_process';

const require=createRequire(import.meta.url);
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const descriptor=root=>JSON.parse(fs.readFileSync(path.join(root,'resources/editor/native-editor-patch.json'),'utf8'));

export function nativeEditorSourcePath(root){
 const preserved=path.join(root,'reports/color-lut-native-header-20261023/index-DEZU41rc.original.js');
 const installed=process.env.LOCALAPPDATA?path.join(process.env.LOCALAPPDATA,'ai.griptape.nodes.desktop/current/resources/editor-bundle/assets/index-DEZU41rc.js'):null;
 const source=process.env.HMB_NATIVE_HEADER_EDITOR_SOURCE||(fs.existsSync(preserved)?preserved:installed);
 assert.ok(source&&fs.existsSync(source),'The exact supported editor is required: set HMB_NATIVE_HEADER_EDITOR_SOURCE to the verified official source.');
 return source;
}

export function readNativeEditorSource(root){
 const bytes=fs.readFileSync(nativeEditorSourcePath(root));
 assert.equal(sha(bytes),descriptor(root).source_sha256,'Native tests require the pristine supported editor, not a synthetic fixture or a different editor build.');
 return bytes.toString('utf8');
}

export function readNativeEditorCSS(root){
 const preserved=path.join(root,'reports/color-lut-native-header-20261023/index-C-Si1lvW.original.css');
 const installed=process.env.LOCALAPPDATA?path.join(process.env.LOCALAPPDATA,'ai.griptape.nodes.desktop/current/resources/editor-bundle/assets/index-C-Si1lvW.css'):null;
 const source=process.env.HMB_NATIVE_HEADER_EDITOR_CSS||(fs.existsSync(preserved)?preserved:installed);
 assert.ok(source&&fs.existsSync(source),'The supported editor CSS is required: set HMB_NATIVE_HEADER_EDITOR_CSS to the verified official source.');
 const bytes=fs.readFileSync(source);
 assert.equal(sha(bytes),'0cdeb2a95665f7539e7f296a04b79ac44c5c3ff9772f2b88a4c050e4653a5032','Native geometry requires the exact supported editor CSS.');
 return bytes.toString('utf8');
}

export function regressionPython(root){
 const local=path.join(root,process.platform==='win32'?'.venv/Scripts/python.exe':'.venv/bin/python');
 return process.env.HMB_REGRESSION_PYTHON||process.env.HMB_NATIVE_HEADER_PYTHON||(fs.existsSync(local)?local:(process.platform==='win32'?'python':'python3'));
}

export function prepareNativeEditor(root){
 const original=readNativeEditorSource(root);
 const result=spawnSync(regressionPython(root),['-B','-c',
  "import json,sys;sys.stdout.reconfigure(encoding='utf-8',newline='');from pathlib import Path;from tools.hmb_color_lut_native_header_patch import patch_editor_source;patched,evidence=patch_editor_source(Path(sys.argv[1]).read_text(encoding='utf-8'));print(json.dumps({'patched':patched,'evidence':evidence},ensure_ascii=False),end='')",
  nativeEditorSourcePath(root)],{cwd:root,encoding:'utf8',timeout:30000,maxBuffer:60*1024*1024,
   env:{...process.env,PYTHONDONTWRITEBYTECODE:'1',PYTHONUTF8:'1',PYTHONIOENCODING:'utf-8'}});
 assert.equal(result.status,0,result.error?.message||result.stderr||'Native patch preparation failed.');
 const {patched,evidence}=JSON.parse(result.stdout);
 assert.equal(sha(patched),descriptor(root).candidate_sha256,'The native test must execute the exact reviewed patch output.');
 return {original,patched,evidence};
}

export function readPatchedNativeEditor(root,candidate){
 if(!candidate)return prepareNativeEditor(root).patched;
 const bytes=fs.readFileSync(candidate);
 assert.equal(sha(bytes),descriptor(root).candidate_sha256,'An explicit native candidate must match the reviewed patch.');
 return bytes.toString('utf8');
}

export function nativeTestPlaywright(){
 let resolved;
 try{resolved=require.resolve('playwright');}
 catch(error){
  if(error.code!=='MODULE_NOT_FOUND')throw error;
  resolved=path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
 }
 return require(resolved);
}
