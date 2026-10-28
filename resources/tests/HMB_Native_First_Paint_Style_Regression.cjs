// Pure render defaults: no native store, SDK, file write or browser required.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(path.join(__dirname,'../editor/hmb-color-lut-native-header.js'),'utf8');
const original={width:712,height:489,minWidth:600,minHeight:300,overflow:'hidden',
  opacity:.6,borderColor:'rgb(239, 68, 68)',outline:'2px solid rgb(239, 68, 68)',zIndex:500};
const context={console,Sjr:()=>original,document:{querySelector:()=>null},CSS:{escape:String}};
vm.createContext(context);
vm.runInContext(source+';globalThis.nodeStyle=hmbNativeStudioNodeStyle;',context);
const style=context.nodeStyle;
for(const [collapsed,animatedSize,rolledUp] of [[false,null,false],[false,{w:712,h:489},false],[false,null,true]]){
  const value=style('HMBColorLUTLibrary',animatedSize,collapsed,300,600,true,rolledUp);
  for(const key of Object.keys(original))assert.equal(value[key],original[key],key+' native state was overwritten');
  assert.equal(value.background,'#0b111b');assert.equal(value.borderRadius,24);assert.equal(value.boxShadow,'none');
}
const capsule=style('HMBColorLUTLibrary',null,true,300,600,true,false);
assert.equal(capsule.width,320);assert.equal(capsule.height,64);
assert.equal(capsule.opacity,original.opacity);assert.equal(capsule.borderColor,original.borderColor);
assert.equal(capsule.overflow,'visible');assert.equal(capsule.background,undefined);
assert.strictEqual(style('StandardNode',null,false,300,600,true,false),original);
assert.strictEqual(style('HMBFutureTool',null,false,300,600,true,false),original);
const metadata={library:'HMB_GP_Production',hmb_native_studio_ui:{
  schema:'hmb-native-studio-ui',version:1,node_type:'HMBFutureTool',widget:'HMBFutureWidget'}};
assert.equal(style('HMBFutureTool',null,false,300,600,true,false,metadata).borderRadius,24);
assert.strictEqual(style('HMBFutureTool',null,false,300,600,true,false,{...metadata,library:'foreign'}),original);
assert.equal(original.background,undefined,'Render helper mutated the original native object');
console.log('Native first-paint render defaults: PASS (HMB shell, capsule, animation, locked/error state, foreign/future contracts)');
