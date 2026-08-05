import assert from "node:assert/strict";
import fs from "node:fs";

const videoPath = new URL("../../widgets/HMBVideoPickerLibraryWidget_v032.js", import.meta.url);
const commandPath = new URL("../../widgets/HMBVideoPickerCommandBridgeWidget_v032.js", import.meta.url);
const promptPath = new URL("../../widgets/HMBPromptLibraryScopedBindingWidget.js", import.meta.url);
const agentPath = new URL("../../widgets/HMBAgentLibraryWidget.js", import.meta.url);
const assetPath = new URL("../../widgets/HMBImageAssetLibraryWidget.js", import.meta.url);
const videoSource = fs.readFileSync(videoPath, "utf8");
const commandSource = fs.readFileSync(commandPath, "utf8");
const promptSource = fs.readFileSync(promptPath, "utf8");
const agentSource = fs.readFileSync(agentPath, "utf8");
const assetSource = fs.readFileSync(assetPath, "utf8");
const pickerModule = await import(videoPath);
const assetModule = await import(assetPath);
const promptModule = await import(promptPath);
const agentModule = await import(agentPath);

for (const [name, module, root] of [
  ["VideoPicker", pickerModule, ".hmbvp"],
  ["PromptLibrary", promptModule, ".hmb-dashboard"],
  ["AgentLibrary", agentModule, ".hmb-agent-dashboard"],
  ["ImageAssetLibrary", assetModule, ".hmb-image-assets"],
]) {
  const scoped = module.hmbScopeWidgetCss(
    `.panel,.panel-title,.warnings{color:red}@media(max-width:900px){.app-header,.header-actions{display:none}}${root} .owned{display:block}${root}-clip{overflow:hidden}`,
    root,
  );
  assert.ok(scoped.includes(`${root} .panel,${root} .panel-title,${root} .warnings{`), `${name} must scope generic selectors.`);
  assert.ok(scoped.includes(`@media(max-width:900px){${root} .app-header,${root} .header-actions{`), `${name} must scope selectors inside at-rules.`);
  assert.ok(!scoped.includes(`${root} ${root} .owned`), `${name} must not double-scope selectors already owned by its root.`);
  assert.ok(scoped.includes(`${root} ${root}-clip{`), `${name} must scope similarly named sibling classes instead of mistaking them for its exact root token.`);
}

const actualScopedStyles = [
  ["VideoPicker", videoSource, pickerModule, ".hmbvp"],
  ["PromptLibrary", promptSource, promptModule, ".hmb-dashboard"],
  ["AgentLibrary", agentSource, agentModule, ".hmb-agent-dashboard"],
  ["ImageAssetLibrary", assetSource, assetModule, ".hmb-image-assets"],
].map(([name, source, module, root]) => {
  const rawStyle = (source.match(/<style>([\s\S]*?)<\/style>/)?.[1] || "")
    .replace(/\$\{[\s\S]*?\}/g, "0");
  assert.ok(rawStyle, `${name} must expose its rendered stylesheet to the scope regression.`);
  const scopedStyle = module.hmbScopeWidgetCss(rawStyle, root);
  assert.doesNotMatch(
    scopedStyle,
    /(^|[{}])\s*\.(?:app-header|header-actions|settings-grid|panel|panel-title|warnings|topbar|layout|workspace|statusbar|status)(?=[\s.#:[>,{])/m,
    `${name}'s actual rendered CSS must contain zero unscoped generic selectors, including nested at-rules.`,
  );
  const exactRootToken = new RegExp(`${root.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?![\\w-])`);
  for (const match of scopedStyle.matchAll(/(^|[{}])\s*([^{}]+?)\{/gm)) {
    const header = String(match[2] || "").trim();
    if (!header || header.startsWith("@")) continue;
    for (const selector of header.split(",")) {
      assert.match(selector, exactRootToken, `${name} rendered an unscoped selector: ${selector.trim()}`);
    }
  }
  return scopedStyle;
});
const unsafeMountOrderSelector = /(^|[{}])\s*\.(?:app-header|header-actions|settings-grid|panel|panel-title|warnings|topbar|layout|workspace|statusbar|status)(?=[\s.#:[>,{])/m;
assert.doesNotMatch(actualScopedStyles.join("\n"), unsafeMountOrderSelector, "Forward widget mount order must keep all generic selectors isolated.");
assert.doesNotMatch([...actualScopedStyles].reverse().join("\n"), unsafeMountOrderSelector, "Reverse widget mount order must keep all generic selectors isolated.");

const markerCatalogProbe = {
  character: [
    { name: "Red", rgb: [1, 0, 0] },
    { name: "Green", rgb: [0, 1, 0] },
    { name: "Blue", rgb: [0, 0, 1] },
  ],
  background: [
    { name: "Sky Blue", rgb: [0.36, 0.72, 1] },
    { name: "Direction Checker", pattern: "direction_checker" },
  ],
};
assert.equal(pickerModule.hmbPickerMarkerAllowsRepeat("Sky Blue", markerCatalogProbe), true);
assert.equal(pickerModule.hmbPickerMarkerAllowsRepeat("Direction Checker", markerCatalogProbe), true);
assert.equal(pickerModule.hmbPickerMarkerAllowsRepeat("Red", markerCatalogProbe), false);
assert.equal(
  pickerModule.hmbPickerColorStyle("Green", markerCatalogProbe),
  "background:rgb(0,255,0)",
);
assert.equal(
  pickerModule.hmbPickerColorStyle("Blue", markerCatalogProbe),
  "background:rgb(0,0,255)",
);
const directionCheckerStyle = pickerModule.hmbPickerColorStyle("Direction Checker", markerCatalogProbe);
assert.match(directionCheckerStyle, /background-color:#000/);
assert.match(directionCheckerStyle, /#fff/);
assert.doesNotMatch(directionCheckerStyle, /#111|#f5f5f5/);

for (const [name, source] of [
  ["VideoPicker", videoSource],
  ["VideoPickerCommandBridge", commandSource],
  ["PromptLibrary", promptSource],
  ["AgentLibrary", agentSource],
  ["ImageAssetLibrary", assetSource],
]) {
  assert.match(
    source,
    /return\s*\{\s*cleanup:\s*container\.__hmb[A-Za-z]+CleanupProxy,\s*update\(nextProps\)/s,
    `${name} must return Griptape's cleanup/update widget controller.`,
  );
}

for (const [name, source] of [
  ["VideoPicker", videoSource],
  ["PromptLibrary", promptSource],
  ["AgentLibrary", agentSource],
  ["ImageAssetLibrary", assetSource],
]) {
  assert.match(source, /hmb_gp_production_ui_theme/, `${name} must use the shared HMB theme key.`);
  assert.match(source, /hmb-gp-production-theme-change/, `${name} must follow the shared HMB theme event.`);
  assert.match(
    source,
    /"Pretendard Variable",Pretendard,Inter,"Noto Sans KR",system-ui,-apple-system,"Segoe UI",sans-serif/,
    `${name} must use the unified HMB Latin/Korean font stack.`,
  );
  assert.match(source, /#(?:0b1020|090c16)/, `${name} P must use the ImageAsset deep-navy surface family.`);
  assert.match(source, /#f472b6/, `${name} P must retain the shared pink selection accent.`);
  assert.match(source, /#091525/, `${name} T must retain the shared blue surface family.`);
  assert.match(source, /#38bdf8/, `${name} T must retain the shared cyan-blue accent.`);
}
assert.match(
  assetSource,
  /function normalizeTheme\(value\)\s*\{\s*return clean\(value\)\.toUpperCase\(\) === "T" \? "T" : "P";/,
  "ImageAssetLibrary must use the same P/T theme identifiers as PromptLibrary.",
);
assert.match(promptSource, /class="title-mark" aria-hidden="true">PL<\/span>/, "Prompt must use the rounded PL monogram.");
assert.match(
  promptSource,
  /const HMB_NATIVE_ASSET_INPUT_ROW_HEIGHT = 42;[\s\S]*?HMB_START_LAYOUT_CHROME_HEIGHT \+[\s\S]*?HMB_NATIVE_ASSET_INPUT_ROW_HEIGHT;/,
  "Prompt startup height must reserve one native ASSET_IN row without reducing its dashboard area.",
);
assert.match(
  promptSource,
  /export function hmbImagePickerEnabled\(state\)[\s\S]*?return videos\.some\(isActiveVideo\);/,
  "Image color picking must be governed by any real active video, without requiring @video1.",
);
assert.match(
  promptSource,
  /class="source-select color-pick-select"[\s\S]*?aria-label=/,
  "The color picker must remain independently editable and accessible while video slots are inactive.",
);
assert.match(
  promptSource,
  /if \(kind === "video"\) hmbRefreshImageColorControls\(container, state\);/,
  "Editing any video slot must refresh picker disabled state immediately even when the local state echo skips remounting.",
);
assert.match(promptSource, /\.theme-control-button\{[^}]*width:28px;[^}]*height:28px;/, "P/T must remain compact icon tiles.");
assert.match(promptSource, /data-theme-choice="P"[^>]*>P<\/button><button[^>]*data-theme-choice="T"[^>]*>T<\/button>/, "Prompt must remain the sole P/T selector.");
assert.match(promptSource, /class="language-button" data-language-toggle[^>]*>\$\{uiLanguage\(state\) === "ko" \? "한국어" : "EN"\}<\/button>/, "Prompt language control must match the VideoPicker Korean/EN button.");
assert.match(promptSource, /data-language-toggle[\s\S]*?state\.ui\.language = uiLanguage\(state\) === "ko" \? "en" : "ko";[\s\S]*?remount\(\);/, "Prompt language changes must repaint immediately.");
assert.doesNotMatch(promptSource, /<select class="language-select"/, "The old Prompt language dropdown must not return.");
assert.match(videoSource, /\.brand-mark:after\{content:"VP";transform:none;/, "VideoPicker must use the static rounded VP mark.");
assert.match(assetSource, /class="mark">IA<\/div>/, "ImageAsset must retain the rounded IA mark.");
assert.equal(
  assetModule.hmbNormalizeImageAssetState({}).catalog_root,
  "//fin-rcomp1/Composite_Team/projects_AI",
  "ImageAssetLibrary must default new state to the shared production projects root.",
);
assert.equal(
  assetModule.hmbNormalizeImageAssetState({ catalog_root: "//artist-server/custom-projects" }).catalog_root,
  "//artist-server/custom-projects",
  "ImageAssetLibrary must preserve an existing custom catalog root.",
);
assert.match(agentSource, /class="agent-mark" aria-hidden="true"><span>AG<\/span>/, "Agent must use the static rounded AG mark.");
assert.match(assetSource, /data-project-select/, "ImageAssetLibrary must expose project switching.");
assert.doesNotMatch(assetSource, /Project and Custom \/ User Imports share this order/, "External imports must not be presented as project Custom assets.");
assert.match(assetSource, /Image \+ available metadata/, "IMAGE_IMPORT_IN must expose readable image content plus optional metadata.");
assert.match(assetSource, /MAIN TYPE \(OPTIONAL\)/, "Image creative classification must be visibly optional.");
assert.match(assetSource, /메인 유형 \(선택\)/, "The Korean Image registration label must remain explicitly optional.");
assert.doesNotMatch(
  assetSource.match(/function registrationDraftIsComplete\(draft\) \{[\s\S]*?\n\}/)?.[0] || "",
  /source_type|scope_candidate|custom_source_type/,
  "Creative role and subtype fields must not gate asset registration.",
);
assert.match(assetSource, /asset\.source_kind !== "project"/, "The project asset grid must exclude external imports.");
assert.match(assetSource, /isUserImportFolder\(folderPath\)/, "The project folder tree must hide the reserved import cache.");
assert.doesNotMatch(assetSource, /root-load-bar|data-root-edit|data-root-path|data-root-browse/, "The removed Project Set/check/path bar must not return.");
assert.match(assetSource, /data-project-set[^>]*>S<\/button>/, "The Project Set root-picker icon must remain available.");
assert.match(assetSource, /data-project-set[\s\S]*?openNativeProjectRootPicker\(container\)/, "Project Set must still open the native project-root picker.");
assert.doesNotMatch(assetSource, /project_set_request/, "Project Set root selection must not trigger default-folder creation.");
assert.match(assetSource, /data-project-reload[^>]*aria-label="\$\{escapeHtml\(imageAssetText\(state, "reload_projects"\)\)\}"/, "Project reload must use a localized accessible icon button.");
assert.match(assetSource, /<select data-project-select>[\s\S]*?<button type="button" class="language-button" data-language-toggle/, "The ImageAsset Korean/EN toggle must sit directly after the project selector.");
assert.match(assetSource, /data-language-toggle[\s\S]*?state\.language = imageAssetLanguage\(state\) === "ko" \? "en" : "ko";/, "ImageAsset language must toggle between Korean and English.");
assert.match(assetSource, /data-project-reload[\s\S]*?state\.refresh_revision = Math\.max\(0, Number\(state\.refresh_revision\) \|\| 0\) \+ 1/, "The reload icon must emit a monotonic rescan request.");
assert.match(assetSource, /grid-template-rows:58px minmax\(0,1fr\) 174px/, "Removing the red bar must also remove its empty 38px layout row.");
assert.doesNotMatch(assetSource, /<div class="status">/, "The selection status must not consume header space.");
assert.match(assetSource, /<div class="toolbar">[\s\S]*?data-asset-view-toggle[\s\S]*?<input data-search[\s\S]*?<div class="toolbar-status"[\s\S]*?<span class="filter-chip">/, "The Windows-style view toggle must lead the search/status/project-root toolbar.");
assert.match(assetSource, /\.toolbar-status\{[^}]*flex:0 0 190px;[^}]*width:190px;[^}]*min-width:190px;[^}]*height:30px;/, "The bilingual selection status must retain a fixed 190px footprint.");
assert.match(assetSource, /registered: "REG"[\s\S]*?unregistered: "UNREG"[\s\S]*?selected: "SEL"/, "English count labels must remain short enough for four-digit values.");
assert.match(assetSource, /class="toolbar-status" data-count-digits="4"/, "The toolbar status must declare its four-digit counter capacity.");
assert.match(assetSource, /font-variant-numeric:tabular-nums;letter-spacing:-\.02em;text-align:right;white-space:nowrap/, "Four-digit counters must retain stable, single-line numeric geometry.");
assert.match(assetSource, /\.toolbar \.filter-chip\{[^}]*flex:0 0 120px;[^}]*width:120px;[^}]*max-width:120px;/, "The project-root filter must retain a fixed 120px footprint beside the status.");
assert.match(assetSource, /\.asset-view-toggle\{[^}]*flex:0 0 31px;[^}]*width:31px;[^}]*height:30px;/, "The compact Windows-style view toggle must retain a fixed footprint.");
assert.match(assetSource, /details_view: "Details view"[\s\S]*?image_only_view: "Image-only view"[\s\S]*?details_view: "자세히 보기"[\s\S]*?image_only_view: "이미지만 보기"/, "The view toggle must remain localized without changing its icon geometry.");
assert.match(assetSource, /data-asset-view="\$\{detailView \? "detail" : "image"\}"/, "The asset root must expose the persisted card view mode.");
assert.match(assetSource, /data-asset-view-toggle[\s\S]*?state\.asset_view_mode = state\.asset_view_mode === "detail" \? "image" : "detail";[\s\S]*?remount\(state\);/, "The view button must toggle and immediately repaint image/detail layouts.");
assert.match(assetSource, /\.project-switch label\{[^}]*min-width:max-content;[^}]*white-space:nowrap;[^}]*word-break:keep-all/, "PROJECT must stay horizontal when the node narrows.");
assert.match(assetSource, /hmbCollapseNativeProjectRootRows/, "The hidden native PROJECT_ROOT row must remain collapsed.");
assert.match(assetSource, /selected_folder_path/, "ImageAssetLibrary must persist the active real project folder.");
assert.match(assetSource, /expanded_folders/, "ImageAssetLibrary must persist independently expanded folders.");
assert.match(assetSource, /PROJECT FOLDERS/, "ImageAssetLibrary must render real project folders rather than a synthetic taxonomy list.");
assert.match(assetSource, /key: "\$imports"[\s\S]*?sourceView: "user"[\s\S]*?importedAssets\.length/, "Connected IMAGE_IMPORT_IN sources must remain reachable in a virtual Import In tree entry after tray deselection.");
assert.match(assetSource, /state\.selected_source_view === "user"[\s\S]*?asset\.source_kind === "user"/, "Selecting Import In must render external source cards in the main grid.");
assert.match(assetSource, /SELECTED IMAGES \/ GENERATOR ORDER/, "ImageAssetLibrary must expose the ordered selection tray.");
assert.match(assetSource, /data-selected-key/, "ImageAssetLibrary must expose stable draggable selection identities.");
assert.match(assetSource, /event\.dataTransfer\.setData\("text\/plain", key\)/, "ImageAssetLibrary drag ordering must transport the stable asset key.");
assert.match(assetSource, /selection_order = index \+ 1/, "ImageAssetLibrary drag ordering must renumber @image slots.");
assert.match(assetSource, /MAX_SELECTED_IMAGES = 50/, "ImageAssetLibrary must enforce the 50-image selection limit.");
const selectedAssetRule = assetSource.match(/\.asset-card\.selected\{([^}]*)\}/)?.[1] || "";
assert.match(assetSource, /\.asset-card\{[^}]*border:1px solid/, "Asset cards must keep one fixed border width across selection changes.");
assert.match(selectedAssetRule, /border-color:var\(--asset-selection\)/, "Selected assets must retain the purple neon border color.");
assert.match(selectedAssetRule, /box-shadow:inset 0 0 0 \.3px/, "Selected assets must add the requested 0.3px neon line without changing geometry.");
assert.doesNotMatch(selectedAssetRule, /border-width:/, "Selection must not resize the card border and shift its contents.");
assert.match(assetSource, /\.asset-thumb\{[^}]*grid-template-rows:2fr 1fr;/, "The thumbnail preview must grow downward while the format footer shrinks.");
assert.match(assetSource, /class="asset-title-copy"[\s\S]*?class="asset-id-line"[\s\S]*?imageAssetText\(state, "asset_id"\)/, "Asset ID must remain visible as localized compact secondary text directly below Image Name.");
assert.doesNotMatch(assetSource, /<div class="asset-fields">/, "Asset cards must not spend half of their content width on a separate Asset ID field.");
assert.match(assetSource, /\.hmb-image-assets \.asset-card\{[^}]*min-height:167px;[^}]*padding:10px/, "Asset cards must grow by the requested rounded 10 percent.");
assert.match(assetSource, /\.hmb-image-assets \.asset-thumb\{[^}]*width:123px;[^}]*height:145px/, "Asset thumbnails must grow by the requested rounded 10 percent.");
assert.match(assetSource, /\.hmb-image-assets\[data-asset-view="image"\] \.asset-grid\{[^}]*repeat\(auto-fill,145px\)/, "Image-only must use the 10%-larger fixed thumbnail grid.");
assert.match(assetSource, /\.hmb-image-assets\[data-asset-view="image"\] \.asset-card\{[^}]*width:145px;[^}]*grid-template-columns:123px;[^}]*gap:0/, "Image-only cards must fit the enlarged thumbnail exactly without a trailing detail bar.");
assert.match(assetSource, /\.hmb-image-assets\[data-asset-view="image"\] \.asset-content\{display:none\}/, "Image-only cards must hide only the detail column.");
assert.match(assetSource, /\.hmb-image-assets\[data-asset-view="detail"\] \.asset-grid\{[^}]*repeat\(auto-fill,286px\)/, "Detailed cards must retain their compact fixed track after the requested 10% enlargement.");
assert.match(assetSource, /\.hmb-image-assets\[data-asset-view="detail"\] \.asset-card\{[^}]*width:286px;[^}]*grid-template-columns:123px minmax\(0,1fr\)/, "Detailed cards must keep the enlarged image plus a compact metadata column.");
assert.match(assetSource, /\.hmb-image-assets\[data-asset-view="detail"\] \.asset-content\{display:flex\}/, "Detailed view must restore the red-box metadata region.");
assert.doesNotMatch(assetSource, /data-asset-view="image"[\s\S]{0,500}asset-thumb-footer\{display:none/, "Image-only mode must retain the Add/format thumbnail footer.");
assert.doesNotMatch(assetSource, /@media\(max-width:920px\)\{[^}]*\.asset-grid\{grid-template-columns:1fr\}/, "Responsive layout must not restore the stretched green trailing area.");
assert.match(assetSource, /data-registration-field="asset_id"/, "The Add passport must retain editable Asset ID because Picker and Prompt bind against it.");
assert.match(assetSource, /asset\.registered[\s\S]*?class="asset-format"[\s\S]*?data-asset-add[\s\S]*?imageAssetText\(state, "add"\)/, "Registered cards show their format while unregistered cards show localized Add.");
assert.match(assetSource, /role="dialog" aria-modal="true"[\s\S]*?imageAssetText\(state, "asset_passport"\)[\s\S]*?data-registration-main[\s\S]*?data-registration-sub/, "Add must open a localized passport registration dialog with Main and Sub Type selectors.");
assert.match(assetSource, /function registrationFolderField\(state, draft, externalImport\)[\s\S]*?if \(!externalImport\) return "";[\s\S]*?<select data-registration-folder>/, "Only external imports should render the destination Asset Folder selector.");
const registrationFolderOptionsSource = assetSource.match(/function registrationFolderOptions\(state, draft\) \{[\s\S]*?\n\}/)?.[0] || "";
assert.match(registrationFolderOptionsSource, /state\.folders[\s\S]*?!isUserImportFolder\(folder\)/, "Add must offer real project child asset folders.");
assert.doesNotMatch(registrationFolderOptionsSource, /ROOT_FOLDER_KEY|project_root/, "Add must never offer the already-selected project root as a destination folder.");
assert.match(assetSource, /source_kind: draft\.source_kind[\s\S]*?source_uid: draft\.source_uid[\s\S]*?target_folder:/, "External registration requests must carry trusted source identity and the selected destination folder.");
assert.match(assetSource, /asset_registration_request/, "The registration dialog must submit a one-shot backend request.");
assert.match(promptSource, /function renderSubtypeControls\(item, state, locked = false\)[\s\S]*?data-field="binding_scopes"[\s\S]*?\$\{locked \? "disabled" : ""\}/, "Verified registered Sub Type controls must support a locked state.");
assert.match(promptSource, /data-field="owner">\$\{targetSelectOptions\(item, images, state\)\}<\/select>/, "Verified Asset Target must remain freely editable.");
assert.match(promptSource, /renderSubtypeControls\(item, state, Boolean\(verifiedAsset && verifiedRegisteredSubtype\(item\)\)\)/, "Only verified assets with a registered Sub Type should lock the Prompt subtype control.");
const promptImageRowSource = promptSource.match(/function renderImageRow\([\s\S]*?\n\}\n\nfunction renderVideoRow/)?.[0] || "";
assert.match(
  promptImageRowSource,
  /image-main-type-cell[\s\S]*?binding-scope-cell[\s\S]*?image-target-cell[\s\S]*?color-pick-cell/,
  "Prompt Image rows must group automatic Main Type and Sub Type before the editable Target.",
);
assert.match(
  promptImageRowSource,
  /\$\{verifiedAsset \? "asset-authority-managed" : ""\}/,
  "Verified Asset rows must expose one semantic class for their automatic authority fields.",
);
const promptImageHeaderSource = promptSource.match(/class="source-header image-header"[\s\S]*?<\/div>\$\{images\.map/)?.[0] || "";
assert.match(
  promptImageHeaderSource,
  /uiText\(state, "name"[\s\S]*?uiText\(state, "main_type"[\s\S]*?uiText\(state, "sub_type"[\s\S]*?uiText\(state, "target"[\s\S]*?uiText\(state, "video_color_pick"/,
  "Prompt Image headers must display NAME, MAIN TYPE, and SUB TYPE together before TARGET.",
);
assert.match(
  promptSource,
  /\.source-row\.image>\.binding-scope-cell\{grid-column:4;grid-row:1\}[\s\S]*?\.source-row\.image>\.image-target-cell\{grid-column:5;grid-row:1\}/,
  "Wide Prompt rows must place Sub Type in column 4 and editable Target in column 5.",
);
assert.match(
  promptSource,
  /\.source-row\.asset-authority-managed \.binding-scope-cell select:disabled\{border-color:/,
  "Registered Sub Type must share the automatic-field visual treatment.",
);
assert.match(assetSource, /if \(!hmbImageAssetCanSelect\(asset\)\) return;/, "Unregistered project cards must not enter generator selection.");
assert.match(assetSource, /applyAssetSearchFilter\(container, state\.search\)/, "Search must filter locally without remounting on every character.");
assert.match(assetSource, /class="hmb-image-assets nodrag"/, "Asset interior gestures must not drag the node.");
assert.doesNotMatch(assetSource, /class="hmb-image-assets nodrag nowheel"/, "Asset must not broadly disable Griptape wheel zoom.");
assert.doesNotMatch(assetSource, /on\(container, "wheel",|addEventListener\?\.\("wheel",/, "Asset must pass wheel input from its entire surface to Griptape zoom.");
assert.match(assetSource, /export function hmbPrepareImageAssetCanvasGestures\(container\)/, "Asset must expose Prompt-style persistent-host wheel cleanup.");
assert.match(assetSource, /canvasPanRoots\.forEach\(\(element\) => \{\s*element\.classList\?\.remove\("nopan", "nowheel"\);\s*element\.classList\?\.add\("nodrag"\);/, "Asset remounts must clear stale pan/wheel blockers from both host and dashboard.");
assert.match(assetSource, /container\.innerHTML = hmbScopeWidgetStyleMarkup\(render\([\s\S]*?container\.__hmbImageAssetRegistrationDraft \|\| null,[\s\S]*?\), "\.hmb-image-assets"\);[\s\S]*?hmbPrepareImageAssetCanvasGestures\(container\);/, "Every Asset remount must render scoped local registration state, apply modal isolation when needed, and restore canvas wheel behavior.");
assert.match(assetSource, /container\.__hmbImageAssetApplyProps/, "Asset must reuse one mounted controller across host refreshes.");
assert.match(assetSource, /if \(currentValue === nextValue\) return;/, "An identical Asset state update must not rebuild the dashboard.");
assert.match(assetSource, /detachReusableImageAssets\(container\)[\s\S]*?restoreReusableImageAssets\(container, reusableImages\)/, "Asset remounts must reuse loaded thumbnail elements.");
assert.match(assetSource, /IMAGE_ASSET_AUTO_SYNC_MS = 10000/, "Asset must probe the shared manifest every ten seconds.");
assert.match(assetSource, /__hmb_manifest_poll_nonce/, "Asset auto-sync probes must use a transient backend nonce.");
assert.match(assetSource, /clearAutoSyncTimer\(\)[\s\S]*?removeEventListener/, "Asset cleanup must stop its sync timer and global listeners.");
assert.match(assetSource, /\.asset-scroll\{[^}]*scrollbar-gutter:stable/, "Asset scrollbars must reserve stable layout space.");
assert.doesNotMatch(assetSource, /data-asset-selected|type="checkbox" data-asset-selected/, "Asset selection must use the card outline, not per-card checkboxes.");
assert.doesNotMatch(assetSource, /candidate-list|writing-mode/, "Removed color chips and rotated slot text must not return.");
assert.match(assetSource, /String\(index \+ 1\)\.padStart\(2, "0"\)/, "Selected cards must use horizontal 01/02 numbering.");
assert.doesNotMatch(assetSource, /IMAGE_IMPORT_IN →[\s\S]*?Video Generation Out → Generator/, "The removed header flow-help text must not return.");
const selectedCardMarkup = assetSource.match(/function renderSelectedCard\([\s\S]*?\n\}\n\nfunction displayWindowsPath/)?.[0] || "";
assert.match(selectedCardMarkup, /class="slot"[\s\S]*?data-move="-1"[\s\S]*?data-move="1"[\s\S]*?data-remove-selected[\s\S]*?selected-thumb/, "Compact selected cards must keep number, left, right, delete, and image controls inside one box.");
assert.doesNotMatch(selectedCardMarkup, /drag-handle|selected-copy/, "Compact selected cards must not render drag hints or metadata text.");
assert.match(selectedCardMarkup, /externalImport[\s\S]*?disconnectPending[\s\S]*?remove_external_selection/, "External selected-card X must describe its guarded graph disconnect.");
assert.match(assetSource, /state\.disconnect_import_uid = asset\.source_uid;[\s\S]*?state = emit\(props, state\);[\s\S]*?return;/, "External selected-card X must submit the source UID without optimistically deselecting the card.");
assert.match(assetSource, /Disconnect this external image from IMAGE_IMPORT_IN\. Multi-image or ambiguous links must be removed at the input port\./, "The external X tooltip must explain the exact safe-disconnect boundary.");
assert.match(assetSource, /이 외부 이미지를 IMAGE_IMPORT_IN에서 연결 해제합니다\./, "The external X connection explanation must be available in Korean too.");
assert.match(assetSource, /\.selected-card\{flex-basis:120px;width:120px;height:118px;grid-template-rows:23px minmax\(0,1fr\)\}/, "Selected cards must match the confirmed 120x118 blue-box footprint.");
assert.match(assetSource, /\.selected-actions\{[^}]*grid-template-columns:repeat\(3,22px\);[^}]*margin-left:auto/, "All three selected-card action icons must fit inside the compact header.");
assert.doesNotMatch(assetSource, /@media\(max-width:920px\)[\s\S]*?\.selected-card\{flex-basis:225px\}/, "Responsive layout must not restore the old wide selected card.");

assert.equal(
  assetModule.hmbImageAssetStatusSummary({
    language: "en",
    status: { registered_asset_count: 9999, unregistered_asset_count: 9999, selected_count: 9999 },
  }),
  "9999 REG | 9999 UNREG | 9999/50 SEL",
  "The 190px status contract must support four-digit counters with shortened English labels.",
);
const assetStateProbe = assetModule.hmbNormalizeImageAssetState({
  language: "ko",
  asset_view_mode: "detail",
  project_root: "C:/Project/sw12",
  project_id: "sw12",
  project_uid: "sw12:test",
  assets: Array.from({ length: 53 }, (_, index) => ({
    asset_library_id: `asset-${index + 1}`,
    source_uid: `source-${index + 1}`,
    source_kind: "project",
    registered: true,
    asset_id: `Asset_${index + 1}`,
    image_name: `Image ${index + 1}`,
    selected: true,
    selection_order: index + 1,
  })),
});
assert.equal(assetStateProbe.language, "ko", "ImageAsset language must survive state normalization.");
assert.equal(assetStateProbe.asset_view_mode, "detail", "Detailed card view must survive state normalization.");
assert.equal(assetModule.hmbNormalizeImageAssetState({ asset_view_mode: "invalid" }).asset_view_mode, "image", "Image-only must be the safe default card view.");
assert.equal(assetStateProbe.status.selected_count, 50);
assert.deepEqual(
  assetStateProbe.assets.filter((item) => item.selected).map((item) => item.selection_order),
  Array.from({ length: 50 }, (_, index) => index + 1),
);
assert.equal(
  assetModule.hmbMoveSelectedAsset(assetStateProbe, "asset-1", "asset-3"),
  true,
);
assert.deepEqual(
  assetStateProbe.assets
    .filter((item) => item.selected)
    .sort((left, right) => left.selection_order - right.selection_order)
    .map((item) => item.asset_library_id)
    .slice(0, 3),
  ["asset-2", "asset-3", "asset-1"],
);
const unverifiedAssetProbe = assetModule.hmbNormalizeImageAssetState({
  assets: [{
    asset_library_id: "unknown-source",
    source_uid: "unknown-source",
    source_kind: "forged",
    asset_id: "Forged",
    image_name: "Forged",
  }],
});
assert.equal(unverifiedAssetProbe.assets[0].source_kind, "user");
const unregisteredProjectProbe = assetModule.hmbNormalizeImageAssetState({
  assets: [{
    asset_library_id: "project-unregistered",
    source_uid: "project-unregistered",
    source_kind: "project",
    asset_id: "Draft",
    image_name: "Draft",
    selected: true,
  }],
});
assert.equal(unregisteredProjectProbe.assets[0].registered, false);
assert.equal(unregisteredProjectProbe.assets[0].selected, false);
assert.equal(assetModule.hmbImageAssetCanSelect(unregisteredProjectProbe.assets[0]), false);
const registrationDraftProbe = assetModule.hmbCreateImageAssetRegistrationDraft({
  asset_library_id: "project-unregistered",
  relative_path: "Character/Hero.png",
  asset_id: "Hero",
  image_name: "Hero Beauty",
  source_type: "Character Appearance",
  scope_candidate: "Full body / full appearance",
}, {
  source_type_choices: ["Role Required / Select Source Type", "Character Appearance", "Custom"],
  scope_choices: ["", "Custom scope"],
  scope_choices_by_source_type: {
    "Character Appearance": ["", "Full body / full appearance", "Head / face only"],
  },
});
assert.equal(registrationDraftProbe.source_type, "Character Appearance");
assert.equal(registrationDraftProbe.scope_candidate, "Full body / full appearance");
assert.equal(registrationDraftProbe.source_kind, "project");
assert.equal(registrationDraftProbe.target_folder, "Character");
assert.equal(registrationDraftProbe.target_folder_confirmed, true);
const externalRegistrationDraftProbe = assetModule.hmbCreateImageAssetRegistrationDraft({
  asset_library_id: "import-source",
  source_uid: "import:source",
  source_kind: "user",
  import_index: 1,
  asset_id: "External",
  image_name: "External Image",
  source_type: "Character Appearance",
  scope_candidate: "Full body / full appearance",
}, {
  source_type_choices: ["Character Appearance", "Custom"],
  scope_choices_by_source_type: {
    "Character Appearance": ["Full body / full appearance"],
  },
});
assert.equal(externalRegistrationDraftProbe.source_kind, "user");
assert.equal(externalRegistrationDraftProbe.source_uid, "import:source");
assert.equal(externalRegistrationDraftProbe.target_folder, "");
assert.equal(externalRegistrationDraftProbe.target_folder_confirmed, false);
const legacyUnclassifiedProbe = assetModule.hmbNormalizeImageAssetState({
  assets: [{
    asset_library_id: "legacy-import",
    source_uid: "import:legacy",
    source_kind: "user",
    asset_id: "Legacy",
    image_name: "Legacy Image",
    source_type: "Role Required / Select Source Type",
    selected: true,
  }],
});
assert.equal(legacyUnclassifiedProbe.assets[0].source_type, "Custom");
const legacyDraftProbe = assetModule.hmbCreateImageAssetRegistrationDraft(
  legacyUnclassifiedProbe.assets[0],
  {
    source_type_choices: ["Role Required / Select Source Type", "Character Appearance", "Custom"],
    scope_choices: ["", "Custom scope"],
  },
);
assert.equal(legacyDraftProbe.source_type, "", "Legacy mandatory-looking roles must normalize to an optional blank choice.");
assert.equal(legacyDraftProbe.scope_candidate, "");
assert.deepEqual(
  assetModule.hmbImageAssetRegistrationSubTypes({
    scope_choices_by_source_type: { "Character Appearance": ["", "Head / face only"] },
  }, "Character Appearance"),
  ["Head / face only"],
);
assert.equal(
  assetModule.hmbImageAssetImageSource({
    thumbnail_url: "http://localhost:8124/workspace/static_files/thumb.webp",
    path: "//SERVER/Share/Hero.png",
  }),
  "http://localhost:8124/workspace/static_files/thumb.webp",
  "Browser thumbnails must prefer the backend HTTP URL over a UNC source path.",
);
assert.equal(
  assetModule.hmbImageAssetImageSource({ path: "C:/ServerShare/Hero.png" }),
  "",
  "The widget must never turn a local or mapped-drive path into file://.",
);
const autoSyncPayloadProbe = JSON.parse(assetModule.hmbImageAssetAutoSyncPayload({
  project_root: "//SERVER/Share/ProjectA",
  project_id: "ProjectA",
  project_uid: "hmbp2:test",
  manifest_signature: "signature-a",
}, "poll-1"));
assert.equal(autoSyncPayloadProbe.__hmb_manifest_poll_nonce, "poll-1");
assert.equal(autoSyncPayloadProbe.manifest_signature, "signature-a");
assert.match(promptSource, /asset_verified:\s*false/, "Prompt rows must default to unverified.");
assert.match(promptSource, /item\.asset_verified/, "Prompt metadata locking must require verified provenance.");
assert.match(promptSource, /Name and Prompt fields remain editable/, "External imported Prompt rows must remain editable.");
assert.doesNotMatch(
  promptSource,
  /hmbPublishSharedUiTheme\(state\.ui\s*&&\s*state\.ui\.theme\)/,
  "Prompt mount and engine-prop updates must never overwrite the shared workflow theme.",
);
assert.match(
  promptSource,
  /\[data-theme-choice\][\s\S]*?const handler = \(\) => \{[\s\S]*?hmbPublishSharedUiTheme\(theme\)/,
  "Only an explicit Prompt P/T selector action may publish the shared workflow theme.",
);
assert.equal(
  (promptSource.match(/hmbPublishSharedUiTheme\(/g) || []).length,
  2,
  "Shared theme publication must be limited to its function definition and the explicit P/T click handler.",
);
for (const [name, source, reader] of [
  ["VideoPicker", videoSource, "hmbReadSharedUiTheme"],
  ["PromptLibrary", promptSource, "hmbReadSharedUiTheme"],
  ["AgentLibrary", agentSource, "hmbReadSharedUiTheme"],
  ["ImageAssetLibrary", assetSource, "readTheme"],
]) {
  assert.match(
    source,
    new RegExp(`function ${reader}\\(fallback = "P"\\)`),
    `${name} must mount independently with P while honoring an existing shared selection.`,
  );
}
assert.match(
  videoSource,
  /state\.ui_theme = hmbReadSharedUiTheme\(state\.ui_theme\)/,
  "A new VideoPicker must adopt the shared theme locally without publishing it.",
);
const videoThemeReceiver = videoSource.match(/const sharedThemeHandler = \(event\) => \{([\s\S]*?)\n  \};/)?.[1] || "";
assert.ok(videoThemeReceiver, "VideoPicker must retain a shared-theme paint receiver.");
assert.doesNotMatch(videoThemeReceiver, /\bcommit\(|props\.onChange|dispatchEvent/, "VideoPicker theme reception must be paint-only.");
const promptThemeReceiver = promptSource.match(/const sharedThemeHandler = \(event\) => \{([\s\S]*?)\n    \};/)?.[1] || "";
assert.ok(promptThemeReceiver, "PromptLibrary must retain a shared-theme paint receiver.");
assert.doesNotMatch(promptThemeReceiver, /\bemit\(|hmbPublishSharedUiTheme|dispatchEvent/, "Prompt theme reception must be paint-only.");
assert.match(
  assetSource,
  /window\.__hmbGpProductionUiTheme[\s\S]*?sessionStorage\?\.getItem\(HMB_UI_THEME_STORAGE_KEY\)/,
  "ImageAsset must use the same in-memory then session-storage theme precedence as the other libraries.",
);
assert.doesNotMatch(
  agentSource,
  /PROJECT_IDENTITY_SOURCE_AUTHORITY_AND_LANGUAGE|SHOT_ACTIVATION_IDENTIFIERS_IMAGE_AND_MARKER_BINDING/,
  "Agent widget source must not contain internal policy identifiers.",
);
assert.match(agentSource, /<b>HMBAgentLibrary<\/b>/, "Agent must use the HMBAgentLibrary title.");
assert.match(agentSource, /DISPLAY → FINAL TEXT/, "Agent header must identify the public text output.");
assert.match(agentSource, /AGENT STATE · CHAIN/, "Agent header must mark native state as chain-only.");
assert.doesNotMatch(
  agentSource,
  /class="agent-flow"|class="agent-statusbar"/,
  "Agent customization must stop at the compact title header and leave the native controls unchanged.",
);
assert.match(
  agentSource,
  /class="hmb-agent-dashboard nodrag"/,
  "Agent's custom background must keep only nodrag so left/middle drag pans the canvas instead of moving the node.",
);
assert.match(
  agentSource,
  /export function hmbPrepareAgentCanvasGestures\(container\)/,
  "Agent must expose its persistent-host gesture cleanup for behavioral regression tests.",
);
assert.match(
  agentSource,
  /container\.classList\?\.remove\("nopan", "nowheel"\);\s*container\.classList\?\.add\("nodrag"\);/,
  "Agent's persistent host must clear stale pan/wheel blockers while retaining node-drag protection.",
);
assert.match(
  agentSource,
  /root\?\.classList\?\.remove\("nopan", "nowheel"\);\s*root\?\.classList\?\.add\("nodrag"\);/,
  "Agent's rendered dashboard must also clear stale pan/wheel blockers.",
);
assert.match(
  agentSource,
  /container\.innerHTML = hmbScopeWidgetStyleMarkup\([\s\S]*?renderAgentDashboard\(hmbReadSharedUiTheme\(\)\),[\s\S]*?"\.hmb-agent-dashboard",[\s\S]*?\);\s*hmbPrepareAgentCanvasGestures\(container\);/,
  "The first Agent mount must apply the native canvas gesture contract.",
);
assert.equal(
  (agentSource.match(/container\.innerHTML = hmbScopeWidgetStyleMarkup/g) || []).length,
  1,
  "Agent updates must retain the existing static dashboard DOM.",
);
assert.match(agentSource, /hmbRefreshAgentDashboard\(container\)/, "Agent updates must refresh theme and gestures in place.");
assert.doesNotMatch(
  agentSource,
  /class="[^"]*\b(?:nopan|nowheel)\b[^"]*"/,
  "Agent markup must never ship with a pan or wheel blocker.",
);
assert.match(agentSource, /container\.addEventListener\?\.\("pointerdown", stopInteriorNodeSelection\)/);
assert.doesNotMatch(
  agentSource,
  /(?:^|[;{])\s*cursor\s*:|pointer-events\s*:/m,
  "Agent must inherit Griptape's native grab/grabbing cursor and pointer hit testing.",
);
assert.doesNotMatch(
  agentSource,
  /<(?:button|input|select|textarea)\b/i,
  "Agent's custom widget remains a background-only title header with no controls to isolate.",
);

for (const [name, source] of [
  ["VideoPicker", videoSource],
  ["PromptLibrary", promptSource],
  ["AgentLibrary", agentSource],
  ["ImageAssetLibrary", assetSource],
]) {
  assert.match(
    source,
    /export function hmbGuardSelectedNodeKeyboardDelete\(container, event\)/,
    `${name} must expose the selected-node keyboard deletion guard.`,
  );
  assert.match(
    source,
    /stopNodeDeleteShortcut/,
    `${name} must keep widget-interior deletion keys from bubbling to React Flow.`,
  );
  assert.match(source, /data-hmb-node-delete-protected/);
  assert.match(source, /event\.preventDefault\?\.\(\)/);
  assert.match(source, /event\.stopImmediatePropagation\?\.\(\)/);
  assert.match(source, /removeAttribute\?\.\("data-hmb-node-delete-protected"\)/);
}
assert.match(agentSource, /window\.addEventListener\("keydown", stopSelectedNodeDeleteShortcut, true\)/);
assert.match(videoSource, /window\.addEventListener\("keydown", stopSelectedNodeDeleteShortcut, true\)/);
assert.match(promptSource, /window\.addEventListener\("keydown", stopSelectedNodeDeleteShortcut, true\)/);
assert.match(agentSource, /window\.removeEventListener\("keydown", stopSelectedNodeDeleteShortcut, true\)/);
assert.match(videoSource, /window\.removeEventListener\("keydown", stopSelectedNodeDeleteShortcut, true\)/);
assert.match(promptSource, /listeners\.push\(\[window, "keydown", stopSelectedNodeDeleteShortcut, true\]\)/);
assert.match(assetSource, /on\(window, "keydown", stopSelectedNodeDeleteShortcut, true\)/);
for (const [name, source] of [
  ["VideoPicker", videoSource],
  ["PromptLibrary", promptSource],
  ["AgentLibrary", agentSource],
  ["ImageAssetLibrary", assetSource],
]) {
  assert.match(
    source,
    /stopInteriorNodeSelection/,
    `${name} must reserve whole-node selection and resize activation for the native title bar.`,
  );
}

// Each custom widget updates only its own parameter. The visible picker commits
// HMB_PICKER_STATE; the hidden bridge commits only HMB_PICKER_COMMAND.
assert.match(videoSource, /props\.onChange\(JSON\.parse\(JSON\.stringify\(normalized\)\)\)/);
assert.match(videoSource, /shell\?\.__hmbPickerCommandBridge/);
assert.match(commandSource, /return props\.onChange\(command\)/);
assert.match(commandSource, /shell\.__hmbPickerCommandBridge = \{ token, dispatch \}/);
assert.doesNotMatch(videoSource, /pending_action:\s*"(?:read_scene|run_video|render_snapshot|stop_read)"/);
assert.doesNotMatch(videoSource, /commitAndRemount/);
assert.doesNotMatch(videoSource, /HMBVideoPickerLibraryWidget\(container,\s*\{/);
assert.equal(typeof pickerModule.hmbRememberPendingPickerStateEcho, "function");
assert.equal(typeof pickerModule.hmbConsumePendingPickerStateEcho, "function");
assert.match(videoSource, /const commit = \(next, options = \{\}\) =>/);
assert.match(
  videoSource,
  /options && options\.suppressMatchingEcho === true[\s\S]*?hmbRememberPendingPickerStateEcho\(container, normalized, props\)/,
);
assert.match(
  videoSource,
  /update\(nextProps\)\s*\{\s*if \(hmbConsumePendingPickerStateEcho\(container, nextProps \|\| \{\}\)\)\s*\{\s*props = nextProps \|\| \{\};\s*return;/s,
  "An exact safe local echo must return before cleanup, DOM morphing, and resize reinstallation.",
);

const localPickerEcho = {
  state_revision: 41,
  state_writer: "widget",
  state_published_at_ms: 123456,
  frontend_seen_revision: 40,
  status: "READY",
  message: "Local selection",
};
const pickerEchoContainer = {};
pickerModule.hmbRememberPendingPickerStateEcho(
  pickerEchoContainer,
  localPickerEcho,
  { disabled: false },
);
assert.equal(
  pickerModule.hmbConsumePendingPickerStateEcho(
    pickerEchoContainer,
    {
      value: {
        ...localPickerEcho,
        state_writer: "python",
        frontend_seen_revision: 41,
      },
      disabled: false,
    },
  ),
  true,
  "Transport-only Python ownership metadata must not remount an otherwise exact safe local echo.",
);
assert.equal(pickerEchoContainer.__hmbPendingPickerStateEchoes, undefined);

const pickerBackendUpdateContainer = {};
pickerModule.hmbRememberPendingPickerStateEcho(
  pickerBackendUpdateContainer,
  localPickerEcho,
  { disabled: false },
);
assert.equal(
  pickerModule.hmbConsumePendingPickerStateEcho(
    pickerBackendUpdateContainer,
    {
      value: {
        ...localPickerEcho,
        state_writer: "python",
        frontend_seen_revision: 41,
        status: "RUNNING",
        message: "Authoritative Maya progress",
      },
      disabled: false,
    },
  ),
  false,
  "A functional Python status/progress update must use the normal authoritative render path.",
);
pickerModule.hmbClearPendingPickerStateEcho(pickerBackendUpdateContainer);

const pickerNewRevisionContainer = {};
pickerModule.hmbRememberPendingPickerStateEcho(
  pickerNewRevisionContainer,
  localPickerEcho,
  { disabled: false },
);
assert.equal(
  pickerModule.hmbConsumePendingPickerStateEcho(
    pickerNewRevisionContainer,
    {
      value: {
        ...localPickerEcho,
        state_revision: 42,
        state_writer: "python",
        state_published_at_ms: 123457,
        frontend_seen_revision: 42,
      },
      disabled: false,
    },
  ),
  false,
  "A newer Python revision must never be consumed as a disposable local echo.",
);
pickerModule.hmbClearPendingPickerStateEcho(pickerNewRevisionContainer);

const pickerDisabledUpdateContainer = {};
pickerModule.hmbRememberPendingPickerStateEcho(
  pickerDisabledUpdateContainer,
  localPickerEcho,
  { disabled: false },
);
assert.equal(
  pickerModule.hmbConsumePendingPickerStateEcho(
    pickerDisabledUpdateContainer,
    { value: localPickerEcho, disabled: true },
  ),
  false,
  "A host disabled-state change must never be consumed as a local picker echo.",
);
pickerModule.hmbClearPendingPickerStateEcho(pickerDisabledUpdateContainer);

const pickerResolutionHandler = videoSource.slice(
  videoSource.indexOf('on(container.querySelector("#playblast-resolution")'),
  videoSource.indexOf('on(container.querySelector("#clear-activity-log")'),
);
assert.doesNotMatch(
  pickerResolutionHandler,
  /suppressMatchingEcho:\s*true/,
  "Resolution changes need the normal morph to refresh the resolution summary, message, and activity log.",
);
const pickerSelectionHandler = videoSource.slice(
  videoSource.indexOf('container.querySelectorAll("[data-toggle-video-uid]")'),
  videoSource.indexOf('container.querySelectorAll("[data-delete-video-uid]")'),
);
assert.doesNotMatch(
  pickerSelectionHandler,
  /suppressMatchingEcho:\s*true/,
  "UID selection changes need the normal morph to refresh card order, viewport, and dependent controls.",
);
assert.match(pickerSelectionHandler, /selectionSurface\.getAttribute\("aria-disabled"\) === "true"/);
assert.match(pickerSelectionHandler, /container\.__hmbSuppressVideoSelectionClick/);
assert.match(pickerSelectionHandler, /on\(selectionSurface, "click", toggleSelection\)/);
assert.match(pickerSelectionHandler, /on\(selectionSurface, "keydown"/);
assert.match(pickerSelectionHandler, /\["Enter", " "\]\.includes\(event\.key\)/);
const pickerPlaybackHandlerStart = videoSource.indexOf(
  'container.querySelectorAll("[data-play-video-uid]")',
  videoSource.indexOf('on(container.querySelector("#import-video-asset"), "change"'),
);
const pickerPlaybackHandler = videoSource.slice(
  pickerPlaybackHandlerStart,
  videoSource.indexOf(
    'container.querySelectorAll("[data-toggle-video-uid]")',
    pickerPlaybackHandlerStart,
  ),
);
assert.match(pickerPlaybackHandler, /container\.querySelector\("#picker-video"\)/);
assert.match(pickerPlaybackHandler, /container\.__hmbAutoplayVideoUid = uid/);
assert.match(pickerPlaybackHandler, /container\.__hmbForceVideoPreviewUid = uid/);
assert.match(
  pickerPlaybackHandler,
  /commit\(\{ \.\.\.hmbPreviewVideoAsset\(liveState, uid\), viewport_mode: "video" \}\)/,
);
assert.doesNotMatch(
  pickerPlaybackHandler,
  /video-asset-thumb-media|\bmedia\.play|\bmedia\.pause|\botherMedia\b/,
  "Catalog play controls must route only the main preview player.",
);
const pickerSearchHandler = videoSource.slice(
  videoSource.indexOf('on(container.querySelector("#outliner-search")'),
  videoSource.indexOf('container.querySelectorAll("[data-group-path]")'),
);
assert.doesNotMatch(
  pickerSearchHandler,
  /suppressMatchingEcho:\s*true/,
  "Outliner search needs the normal morph to rebuild the filtered rows.",
);
const pickerCameraHandler = videoSource.slice(
  videoSource.indexOf('container.querySelectorAll("[data-camera-path]")'),
  videoSource.indexOf('container.querySelectorAll("[data-color]")'),
);
assert.doesNotMatch(
  pickerCameraHandler,
  /suppressMatchingEcho:\s*true/,
  "Camera changes need the normal morph to refresh the active camera and output controls.",
);
const pickerClearLogHandler = videoSource.slice(
  videoSource.indexOf('on(container.querySelector("#clear-activity-log")'),
  videoSource.indexOf('on(container.querySelector("#outliner-search")'),
);
assert.doesNotMatch(
  pickerClearLogHandler,
  /suppressMatchingEcho:\s*true/,
  "Clearing the activity log needs the normal morph to clear visible text, message, and button state.",
);
const pickerVisibilityHandler = videoSource.slice(
  videoSource.indexOf('container.querySelectorAll("[data-visibility-path]")'),
  videoSource.indexOf('container.querySelectorAll("[data-camera-path]")'),
);
assert.doesNotMatch(
  pickerVisibilityHandler,
  /suppressMatchingEcho:\s*true/,
  "Visibility changes need the normal morph to refresh the authoritative message and dependent state.",
);
assert.doesNotMatch(
  videoSource,
  /\.outliner-row\{transition:|transition:[^}]*background-color/,
  "Selection-bearing backgrounds must update instantly instead of flashing through a transition.",
);
assert.equal(
  (promptSource.match(/\bremount\(\);/g) || []).length,
  4,
  "PromptLibrary may additionally remount for translated labels and standalone structural source edits.",
);
assert.match(
  promptSource,
  /export function hmbCommitLocalPromptStructure[\s\S]*?hmbEmitLocalPromptState\(container, props, state\);[\s\S]*?remount\(\);/,
  "Prompt structural source edits must repaint immediately without waiting for a Picker props event.",
);
assert.match(promptSource, /if \(currentValue === nextValue && !disabledChanged\) return;[\s\S]*?state = nextState;\s*remount\(\);/);
assert.match(promptSource, /hmbCapturePromptControlFocus\(container\)[\s\S]*?hmbRestorePromptControlFocus\(container\)/, "Prompt structural refreshes must preserve non-text control focus.");
assert.match(promptSource, /container\.__hmbPromptLibraryApplyProps/, "Prompt must reuse one mounted controller across host refreshes.");
assert.match(promptSource, /data-image-drag-handle draggable=/);
assert.match(promptSource, /addEventListener\("dragstart", dragStart\)/);
assert.match(promptSource, /addEventListener\("dragover", dragOver\)/);
assert.match(promptSource, /addEventListener\("drop", drop\)/);
assert.match(promptSource, /export function moveImageRowWithoutReset\(state, sourceIndex, targetIndex\)/);
assert.match(promptSource, /export function removeImageRowAndPromote\(state, sourceIndex\)/);
assert.match(promptSource, /state\.images\.splice\(index, 1\)/);
assert.match(
  promptSource,
  /if \(kind === "image"\) \{[\s\S]*?removeImageRowAndPromote\(state, index\)/,
  "Image X must delete the selected row instead of clearing a middle slot.",
);
assert.doesNotMatch(
  promptSource,
  /target\[index\] = kind === "image" \? defaultImage\(slot\)/,
  "Middle image deletion must not leave an empty numbered line.",
);
assert.match(
  videoSource,
  /READ request submitted through HMB_PICKER_COMMAND\. Waiting for Python acknowledgement\./,
  "VideoPicker must not report READ completion before Python acknowledgement.",
);
assert.match(
  videoSource,
  /READ transport timed out before Python acknowledgement \(20 seconds\)\./,
  "VideoPicker must release the local pending state when Python does not acknowledge READ.",
);
assert.match(videoSource, /const action = processPid > 0 \? "stop_read" : "cancel_pending";/);
assert.match(videoSource, /Pending operation cancelled before an external process PID existed\./);

assert.match(videoSource, /const HMB_DEFAULT_NODE_WIDTH = 1400;/, "Picker must start at the requested 1400px width.");
assert.match(videoSource, /const HMB_DEFAULT_NODE_HEIGHT = 1200;/, "Picker must start at the requested 1200px height.");
assert.match(videoSource, /const HMB_MIN_NODE_HEIGHT = 1151;/, "Picker must preserve the established manual-resize floor.");
assert.doesNotMatch(videoSource, /class="step-nav"|\.step-nav\{|\.step\.active\{|1&nbsp;/);
assert.match(videoSource, /\.app-header\{height:68px;display:flex;align-items:center;justify-content:space-between/);
assert.match(
  videoSource,
  /\.scene-load-bar\{height:36px;flex:0 0 36px;display:grid;grid-template-columns:auto minmax\(120px,1fr\) auto auto max-content max-content max-content max-content;/,
  "The reduced Maya Scene bar must reserve eight columns for path, actions, Original, Mask, Depth, and Motion Guide.",
);
assert.match(videoSource, /\.scene-path-input\{height:25px;/);
assert.match(videoSource, /\.scene-load-bar button\{height:25px;/);
assert.match(videoSource, /id="depth-playblast-toggle"/);
assert.match(videoSource, /id="mask-playblast-toggle"/);
assert.match(videoSource, /id="motion-guide-toggle"/);
assert.doesNotMatch(videoSource, /Unassigned polygon geometry is rendered pure black\./, "The removed black-unassigned render policy must not return to the Picker UI.");
assert.match(
  videoSource,
  /const liveSlot = 1;/,
  "Generate keeps the canonical initial @video1 Color destination without turning Color Pick bindings into a prerequisite.",
);
assert.doesNotMatch(
  videoSource,
  /const playblastSlot = \(state\.depth_enabled \|\| state\.motion_guide_enabled\)/,
  "Color-only generation must not fall back to whichever auxiliary video is selected.",
);
assert.doesNotMatch(
  videoSource,
  /playblastBindingReady|bindingReady/,
  "Button availability must not create a Color Pick prerequisite.",
);
assert.match(
  videoSource,
  /playblastEnabled:[\s\S]*?&& readSnapshotReady[\s\S]*?&& cameraReady[\s\S]*?&& outputReady/,
);
assert.match(
  videoSource,
  /snapshotEnabled:[\s\S]*?&& readSnapshotReady[\s\S]*?&& cameraReady[\s\S]*?&& outputReady/,
  "Snapshot availability keeps only READ, camera, frame, and output technical conditions.",
);
assert.doesNotMatch(videoSource, /PLAYBLAST requires[^\n]*Color Pick binding/);
assert.doesNotMatch(videoSource, /SNAPSHOT requires[^\n]*Color Pick binding/);
assert.match(videoSource, /const HMB_PICKER_MAX_SELECTED_VIDEOS = 10;/);
assert.match(videoSource, /export function hmbSelectedVideoAssets/);
assert.match(videoSource, /export function hmbToggleVideoAssetSelection/);
assert.match(videoSource, /export function hmbMoveSelectedVideoAsset/);
assert.match(videoSource, /export function hmbApplySelectedVideoAssetOrderToDom/);
assert.match(videoSource, /export function hmbInstallVideoAssetDragReorder/);
assert.match(videoSource, /export function hmbPreviewVideoAsset/);
assert.match(videoSource, /export function hmbDeleteVideoAsset/);
assert.match(
  videoSource,
  /<video class="video-asset-thumb-media"[^>]*draggable="false"[^>]*aria-hidden="true"><\/video>/,
  "Catalog videos remain static thumbnail media and cannot steal the selected-card drag.",
);
assert.match(
  videoSource,
  /<button type="button" class="video-asset-play" data-play-video-uid=/,
  "Only the centered button owns catalog play/pause routing.",
);
assert.match(
  videoSource,
  /class="video-asset-copy" data-toggle-video-uid=[^>]*role="button"[^>]*aria-disabled=/,
  "The complete lower copy region owns selection and its accessible disabled state.",
);
assert.doesNotMatch(videoSource, /syncInlineVideoIndicator|toggleInlineVideo/);
assert.match(
  videoSource,
  /\.video-asset-card\.selected\{border-width:2px;[^}]*box-shadow:0 0 0 2px rgba\(var\(--selection-rgb\),\.82\),0 0 28px rgba\(var\(--selection-rgb\),\.62\)/,
  "Video selection uses the stronger two-pixel neon treatment.",
);
const pickerMoveContract = videoSource.slice(
  videoSource.indexOf("export function hmbMoveSelectedVideoAsset"),
  videoSource.indexOf("export function hmbPreviewVideoAsset"),
);
assert.match(pickerMoveContract, /ordered\.splice\(currentIndex, 1\)/);
assert.match(pickerMoveContract, /hmbApplyVideoAssetSelection\(state, ordered, targetUid\)/);
const pickerDragContract = videoSource.slice(
  videoSource.indexOf("export function hmbInstallVideoAssetDragReorder"),
  videoSource.indexOf("export function hmbPreviewVideoAsset"),
);
assert.match(
  pickerDragContract,
  /closest\?\.\("\[data-play-video-uid\], \[data-delete-video-uid\]"\)/,
);
assert.doesNotMatch(pickerDragContract, /data-toggle-video-uid/);
assert.match(pickerDragContract, /container\.__hmbSuppressVideoSelectionClick = true/);
assert.match(
  pickerDragContract,
  /container\.addEventListener\(eventName, handler, true\)/,
  "Video reorder events must survive card morphs through capture-phase delegation.",
);
assert.match(
  pickerDragContract,
  /setTimeout\(\(\) => \{ delete container\.__hmbSuppressVideoSelectionClick; \}, 0\)/,
);
assert.match(pickerDragContract, /hmbMoveSelectedVideoAsset\(liveState, sourceUid, targetIndex\)/);
assert.match(
  pickerDragContract,
  /session\.targetUid = targetUid[\s\S]*?finalize\("drop"\)[\s\S]*?finalize\("dragend"\)/,
  "Dragend must commit the last valid target if the embedded host swallows drop.",
);
assert.match(pickerDragContract, /hmbApplySelectedVideoAssetOrderToDom\(container, nextState\)/);
assert.doesNotMatch(videoSource, /on\(card, "(?:dragstart|dragover|drop|dragend)"/);
const pickerDeleteContract = videoSource.slice(
  videoSource.indexOf("export function hmbDeleteVideoAsset"),
  videoSource.indexOf("\nfunction defaultState"),
);
assert.match(pickerDeleteContract, /videos: remaining/);
assert.doesNotMatch(pickerDeleteContract, /unlink|removeItem|deleteFile/);
assert.match(videoSource, /function hmbVideoAssetRole/);
assert.match(videoSource, /if \(role\.includes\("motion"\)\) return "Motion Guide"/);
assert.match(videoSource, /if \(role\.includes\("depth"\)\) return "Depth"/);
const pickerGenerateContract = videoSource.slice(
  videoSource.indexOf('on(container.querySelector("#run-video")'),
  videoSource.indexOf('on(container.querySelector("#playblast-resolution")'),
);
assert.match(pickerGenerateContract, /const liveSlot = 1;/);
assert.match(pickerGenerateContract, /include_original: originalEnabled/);
assert.match(pickerGenerateContract, /include_mask: maskEnabled/);
assert.match(pickerGenerateContract, /include_depth: depthEnabled/);
assert.match(pickerGenerateContract, /include_motion_guide: motionGuideEnabled/);
assert.match(pickerGenerateContract, /Generate requested for new history assets:/);
assert.match(pickerGenerateContract, /Existing assets will be preserved/);
assert.match(
  videoSource,
  /\.snapshot-toolbar\{[\s\S]*?display:grid;grid-template-columns:minmax\(96px,4fr\) max-content minmax\(145px,6fr\)/,
);
assert.match(videoSource, /\.snapshot-toolbar>button\{[\s\S]*?white-space:nowrap;overflow:hidden;text-overflow:ellipsis/);
assert.match(videoSource, /\.snapshot-toolbar #delete-snapshot\{width:max-content;min-width:124px/);
assert.match(
  videoSource,
  /\.snapshot-toolbar \.output-camera-inline\{width:100%;height:29px;[\s\S]*?grid-template-columns:max-content minmax\(0,1fr\)/,
);
assert.match(videoSource, /\.snapshot-toolbar \.output-camera-label\{white-space:nowrap;line-height:29px\}/);
assert.match(
  videoSource,
  /\.snapshot-toolbar \.camera-fixed,\.snapshot-toolbar \.camera-dropdown\{[\s\S]*?min-height:29px;max-height:29px/,
);
assert.match(
  videoSource,
  /const HMB_RIGHT_SECTION_DEFAULT_HEIGHTS = \{ settings: 285, color: 628, log: 208 \};/,
  "Playblast Settings must start 50 percent taller.",
);
assert.match(videoSource, /value: "1280x720", width: 1280, height: 720/);
assert.match(videoSource, /value: "1920x1080", width: 1920, height: 1080/);
assert.match(videoSource, /id="playblast-resolution"/);
assert.match(videoSource, /output_width: Number\(currentLocal\.output_width \|\| 1280\)/);
assert.match(videoSource, /output_height: Number\(currentLocal\.output_height \|\| 720\)/);
assert.match(videoSource, /function hmbApplyPickerInitialNodeSizeOnce\(container\)/);
assert.match(
  videoSource,
  /stopInteriorNodeSelection/,
  "Picker interior clicks must not select or resize the node; the native title bar owns activation.",
);
assert.match(
  videoSource,
  /container\.classList\?\.remove\("nodrag", "nopan", "nowheel"\);/,
  "Picker must clear stale canvas-gesture blockers from its persistent host.",
);
assert.match(videoSource, /clip\?\.classList\?\.add\("nodrag"\);/);
assert.doesNotMatch(
  videoSource,
  /const scrollSelectors = /,
  "Picker broad panels must not consume the wheel that Griptape uses for zoom.",
);
assert.match(
  promptSource,
  /const canvasPanRoots = \[\s*container,\s*container\.querySelector\?\.\("\.hmb-dashboard-clip"\),\s*container\.querySelector\?\.\("\.hmb-dashboard"\),\s*\]\.filter\(Boolean\);/,
  "Prompt must identify the persistent roots whose stale pan/wheel guards need clearing.",
);
assert.match(
  promptSource,
  /canvasPanRoots\.forEach\(\(element\) => element\.classList\?\.remove\("nopan", "nowheel"\)\);/,
);
assert.match(
  promptSource,
  /stopInteriorNodeSelection/,
  "Prompt interior clicks must not select or resize the node; the native title bar owns activation.",
);
assert.match(promptSource, /container\.querySelector\?\.\("\.image-card"\)/);
assert.match(
  promptSource,
  /imageSourceBinding\?\.classList\?\.remove\("nodrag", "nopan", "nowheel"\);/,
  "IMAGE SOURCE BINDING must release its former full-card gesture isolation.",
);
for (const source of [videoSource, promptSource]) {
  assert.match(
    source,
    /\["pointerdown", "mousedown", "click", "dblclick"\]\.forEach\(\(eventName\) => \{/,
    "Concrete widget controls must still stop node/canvas pointer gestures.",
  );
  assert.match(
    source,
    /element\.classList\?\.add\("nodrag", "nopan", "nowheel"\);/,
    "Concrete controls must retain their native pointer and wheel behavior.",
  );
}
assert.match(videoSource, /class="hmbvp-clip nodrag"/);
assert.match(promptSource, /class="hmb-dashboard-clip nodrag"/);
assert.match(videoSource, /hmbApplyPickerInitialNodeSizeOnce\(container\);\s*concealNativeMayaPicker\(container\);/);
assert.match(videoSource, /shell\.style\.width = `\$\{HMB_DEFAULT_NODE_WIDTH\}px`/);
assert.match(videoSource, /shell\.style\.height = `\$\{HMB_DEFAULT_NODE_HEIGHT\}px`/);
assert.doesNotMatch(videoSource, /shell\.style\.width = `\$\{targetWidth\}px`/);
assert.match(
  videoSource,
  /export function hmbAlignPickerOuterBottom\(container, preferredShell = null, allowShrink = true\)/,
  "Picker must expose the settled-layout outer-bottom alignment helper.",
);
assert.match(
  videoSource,
  /pickerRect\.bottom \|\| 0\) - Number\(shellRect\.bottom \|\| 0\)/,
  "Outer-bottom alignment must use the rendered visual endpoint and React Flow bottom edges.",
);
assert.match(
  videoSource,
  /const pickerRect = picker\.getBoundingClientRect\?\.\(\);/,
  "Picker outer alignment must use the dashboard's actual bottom edge.",
);
assert.match(videoSource, /shell\.style\.height = `\$\{targetHeight\}px`/);
assert.match(videoSource, /shell\.style\.minHeight = `\$\{targetHeight\}px`/);
assert.match(
  videoSource,
  /if \(shell\?\.style\) shell\.style\.minHeight = `\$\{HMB_MIN_NODE_HEIGHT\}px`/,
  "Native node resizing must release the automatic slot-height floor.",
);
assert.match(videoSource, /let resizeApplying = false;/);
assert.match(videoSource, /let pointerInteractionActive = false;/);
assert.match(videoSource, /let nativeNodeResizeActive = false;/);
assert.doesNotMatch(commandSource, /HMB_PICKER_BOOTSTRAP_(?:WIDTH|HEIGHT)|hmbEnsurePickerBootstrapNode/);
assert.doesNotMatch(commandSource, /window\.setTimeout/);
assert.match(commandSource, /hmbCollapseCommandBridgeLayoutRow\(container\)/);
assert.match(videoSource, /hmbApplyPickerCommandRowReclaim\(container\)/);
assert.match(
  videoSource,
  /!hmbPickerBranchContainsVideoOutputs\(parameterBranch\.parentElement\)/,
  "MAYA_SCENE row concealment must never collapse an ancestor that owns VIDEO output handles.",
);
assert.match(commandSource, /branchContainsVideoOutputs/);
assert.match(videoSource, /VIDEO_OUT/);

assert.match(videoSource, /const HMB_PICKER_CONTENT_FALLBACK_HEIGHT = 960;/);
assert.match(videoSource, /\.hmbvp-clip\{width:100%;height:100%;/);
assert.match(videoSource, /\.hmbvp\{--safe-x:16px;position:relative;width:100%;height:100%;/);
assert.match(videoSource, /border-radius:11px/);
assert.match(videoSource, /\.panel\{[\s\S]*?border-radius:10px/);
assert.match(videoSource, /\.side-section\{[\s\S]*?border-radius:10px/);
assert.doesNotMatch(videoSource, /class="statusbar"|\.statusbar\{|class="warnings"|\.warnings\{/,
  "Picker notifications must live only in Activity Log; no footer status bar or warning overlay may return.");
assert.doesNotMatch(videoSource, /const available = hmbPickerAvailableHeightToShell\(container, shell\);/);
assert.match(videoSource, /const required = minimumRequired;/);
assert.match(videoSource, /clip\.style\.height = `\$\{required\}px`/);
assert.match(videoSource, /picker\.style\.height = `\$\{required\}px`/);
assert.match(videoSource, /hmbPickerLocalHostAncestors\(container\)\.forEach\(applyMinimum\)/);
assert.doesNotMatch(videoSource, /layoutRow\.style\.setProperty\("flex", "1 1 0%", "important"\)/);
assert.doesNotMatch(videoSource, /element\.style\.setProperty\("flex", `0 0 \$\{height\}px`, "important"\)/);
assert.match(videoSource, /resizeObserver = new ResizeObserverClass\(\(\) => schedulePickerFit\(false\)\)/);
assert.match(videoSource, /resizeObserver\.observe\(container\)/);
assert.match(videoSource, /resizeObserver\.observe\(rightStackForResizeSync\)/);
assert.match(videoSource, /resizeObserver\.observe\(centerStackForResizeSync\)/);
assert.doesNotMatch(videoSource, /resizeObserver\.observe\(shell/);
assert.match(videoSource, /hmbCollapseNativeMayaLayoutRows\(container\)/);
assert.doesNotMatch(videoSource, /transition-property:height,flex-basis/);
assert.doesNotMatch(
  videoSource,
  /layoutRow\.style\.setProperty\("position", "absolute", "important"\)/,
);
assert.match(videoSource, /trailingSpacer\.style\.setProperty\("flex", "0 0 0px", "important"\)/);
assert.doesNotMatch(videoSource, /hmbPickerReclaimAppliedHeight|hmbPickerReclaimBaseHeight/);
assert.doesNotMatch(
  videoSource,
  /hmbAdjustPickerNodeHeightForVideoSlots|shell\.style\.setProperty\("height"/,
  "Slot changes must not write React Flow height from the frontend.",
);
assert.match(videoSource, /hmbEnsurePickerNodeFits\(container, shellForResizeSync \|\| findReactFlowNode\(container\)\);/);
assert.doesNotMatch(
  videoSource,
  /hmbEnsurePickerNodeFits\(container, shellForResizeSync \|\| findReactFlowNode\(container\)\);[\s\S]{0,260}?hmbAlignPickerOuterBottom\(/,
  "Settled fitting must keep Prompt's fixed inner frame instead of bottom-edge chasing.",
);
assert.match(videoSource, /function hmbApplyPickerDominoResizeFrame\(container, startNodeHeight, startRequiredHeight\)/);
assert.equal(
  (videoSource.match(/hmbApplyPickerDominoResizeFrame\(container, startNodeHeight, startRequiredHeight\)/g) || []).length,
  3,
  "Both Picker resize handles must use the shared Prompt-style domino frame.",
);
assert.doesNotMatch(videoSource, /outerBottomAlignTimer/);
assert.match(videoSource, /const HMB_PICKER_MAX_SELECTED_VIDEOS = 10;/);
assert.doesNotMatch(videoSource, /hmbPreparePickerSlotTransition\(container, [+-]?1\)/);
assert.doesNotMatch(videoSource, /data-hmb-picker-slot-transition="true"/);
assert.doesNotMatch(videoSource, /hmb-picker-native-row-in/);
assert.doesNotMatch(videoSource, /transition:height 180ms/);
assert.match(videoSource, /hmbRenderPickerMarkup\([\s\S]*?container,[\s\S]*?hmbScopeWidgetStyleMarkup\(pickerMarkup, "\.hmbvp"\),[\s\S]*?\)/);
assert.doesNotMatch(videoSource, /container\.innerHTML = `\s*<style>/);
assert.match(
  videoSource,
  /hmbPickerLocalHostAncestors\(container\)\.forEach\(applyMinimum\)/,
  "Stable v0.2.0 sizing propagates only the minimum content height.",
);
assert.match(videoSource, /container\.style\.maxWidth = "none"/);
assert.match(videoSource, /container\.style\.overflow = "visible"/);
assert.doesNotMatch(videoSource, /container\.style\.height = "100%"/);
assert.match(videoSource, /concealNativeMayaPicker\(container\);\s*hmbEnsurePickerNodeFits/s);
assert.doesNotMatch(videoSource, /initialFitTimers|\[80,\s*250,\s*750\]/);
assert.match(agentSource, /compactAgentWidgetHost\(container\)/);
assert.match(agentSource, /setProperty\("height",\s*"64px",\s*"important"\)/);

assert.doesNotMatch(videoSource, /data-resize-panel="outliner"/);
assert.match(videoSource, /data-resize-panel="viewport"/);
assert.match(videoSource, /right_section_heights:\s*heights/);
assert.doesNotMatch(videoSource, /node_height:\s*latestNodeHeight/);
assert.match(
  videoSource,
  /function hmbApplyPickerDominoResizeFrame\(container, startNodeHeight, startRequiredHeight\)[\s\S]*?hmbApplyPickerOuterNodeHeight/,
  "Only explicit Prompt-style panel resizing should drive outer-node height.",
);
assert.doesNotMatch(videoSource, /data-resize-section="log"/);
assert.match(videoSource, /data-resize-section="color"/);
assert.match(videoSource, /data-resize-section="settings"/);
assert.doesNotMatch(videoSource, /HMB_RIGHT_SECTION_HEIGHTS_KEY|hmbWriteRightSectionHeights/);
assert.match(promptSource, /state\.ui\.theme\s*=\s*theme/);
assert.equal((videoSource.match(/data-section-key="log"/g) || []).length, 1);
assert.ok(
  videoSource.indexOf('<div class="center-stack">') < videoSource.indexOf('data-section-key="log"')
    && videoSource.indexOf('data-section-key="log"') < videoSource.indexOf('<aside class="right-stack">'),
  "Activity Log must be below the video preview in the center column.",
);
assert.match(videoSource, /\.center-stack>\.activity-section\{flex:1 1 0;min-height:150px\}/);
assert.doesNotMatch(videoSource, /const statusHeight = hmbPickerCssHeight|class="statusbar"|\.status-message|\.status-meta/,
  "Removing the footer must also remove its reserved height and message/meta render path.");
assert.match(videoSource, /id="activity-log-view" class="activity-log-view" role="log" aria-live="polite"/,
  "Activity Log must be the single accessible notification surface.");
assert.match(videoSource, /\.activity-log-row\[data-level="ERROR"\]\{color:#fb7185\}/,
  "Activity Log errors must render as red text.");
assert.match(videoSource, /\.activity-log-row\[data-level="WARNING"\]\{color:#fbbf24\}/,
  "Activity Log warnings must render with a distinct warning color.");
assert.match(videoSource, /\.activity-log-view\{[^}]*overflow-x:auto;overflow-y:auto;scrollbar-gutter:stable both-edges/,
  "Long log messages must expose a stable horizontal scrollbar.");
assert.match(videoSource, /\.activity-log-row\{[^}]*width:max-content;min-width:100%;[^}]*white-space:nowrap/,
  "Long log messages must remain one intrinsically wide row.");
assert.match(videoSource, /\.activity-log-message\{[^}]*min-width:max-content;max-width:none;[^}]*text-overflow:clip;white-space:nowrap/,
  "Long log messages must remain horizontally inspectable instead of being ellipsized.");
assert.match(videoSource, /\.outliner-palette\{padding:8px;border-bottom:/);
assert.ok(
  videoSource.indexOf('<div class="outliner-palette">')
    < videoSource.indexOf('<div class="outliner-toolbar">'),
  "The compact actor/object palette must sit directly above the Outliner controls.",
);
assert.doesNotMatch(videoSource, /id="apply-color"|class="selected-target"|\.apply-button/);
assert.match(
  videoSource,
  /container\.querySelectorAll\("\[data-color\]"\)[\s\S]*?if \(selectedNode\) applyColor\(color\)/,
  "A palette click must continue to assign its color immediately after removing the redundant Target/APPLY row.",
);
assert.doesNotMatch(videoSource, /assignmentHtml\(|id="clear-colors"|No color assignments/);
assert.doesNotMatch(videoSource, /id="node-(?:width|height)-handle"/);

console.log("HMB custom-widget lifecycle, command bridge, cleanup, and update contract: PASS");
