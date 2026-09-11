import assert from 'node:assert/strict';
import fs from 'node:fs';
const source = fs.readFileSync(new URL('../../widgets/HMBImageAssetLibraryWidget.js', import.meta.url), 'utf8');
const widget = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));
const old = '//fin-rcomp1/Composite_Team/projects_AI';
const next = '//192.168.200.19/v/projects/Ai_Ct_image';
for (const prefix of [old, old.toUpperCase(), old.replaceAll('/', '\\')]) {
  assert.equal(widget.hmbRelocateImageProjectPath(prefix + '/superwings12/캐릭터/Hero.png'), next + '/superwings12/캐릭터/Hero.png');
}
for (const path of [old + '_archive/Hero.png', '//artist-server/custom-projects', 'D:/MyProject', 'https://example.com/hero.png']) {
  assert.equal(widget.hmbRelocateImageProjectPath(path), path);
}
const raw = {catalog_root: old, project_root: old+'/superwings12',project_id:'superwings12',project_uid:'project-uid',
  projects:[{path:old+'/superwings12',project_id:'superwings12',name:'superwings12'}],
  assets:[{asset_library_id:'hero',asset_id:'Hero',image_name:'Hero',source_uid:'project:hero',source_kind:'project',
    registered:true,selected:true,selection_order:1,path:old+'/superwings12/Character/Hero.png',relative_path:'Character/Hero.png'}]};
raw.shot_routing = widget.hmbNormalizeImageAssetState({}).shot_routing;
const before = JSON.stringify(raw);
const moved = widget.hmbNormalizeImageAssetState(raw);
assert.equal(moved.catalog_root,next);
assert.equal(moved.project_root,next+'/superwings12');
assert.equal(moved.projects[0].path,moved.project_root);
assert.equal(moved.assets[0].path,next+'/superwings12/Character/Hero.png');
for (const key of ['asset_library_id','source_uid','asset_id','selected','selection_order']) assert.equal(moved.assets[0][key],raw.assets[0][key]);
assert.deepEqual(widget.hmbNormalizeImageAssetState(JSON.parse(before.replaceAll(old,next))),moved);
assert.deepEqual(widget.hmbNormalizeImageAssetState(moved),moved);
assert.equal(JSON.stringify(raw),before);
assert.equal(widget.hmbNormalizeImageAssetState({}).catalog_root,next);
assert.match(source,/const nativePath = hmbRelocateImageProjectPath\(nativeProjectRootValue\(container\)\)/);
console.log('ImageAsset UI share relocation, saved state and native-root echo: PASS');
