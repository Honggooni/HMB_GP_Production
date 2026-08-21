import assert from "node:assert/strict";
import fs from "node:fs";


const widgetPath = new URL(
  "../../widgets/HMBImageAssetLibraryWidget.js",
  import.meta.url,
);
const source = fs.readFileSync(widgetPath, "utf8");
const widget = await import(widgetPath);

const pending = widget.hmbNormalizeImageAssetState({
  disconnect_import_uid: "import:guarded-source",
});
assert.equal(pending.disconnect_import_uid, "import:guarded-source");
assert.equal(
  widget.hmbNormalizeImageAssetState({ disconnect_import_uid: "forged" })
    .disconnect_import_uid,
  "",
);

const selectedHandler = source.match(
  /on\(selectedTray, "click"[\s\S]*?\n  \}\);/,
)?.[0] || "";
assert.match(
  selectedHandler,
  /const asset = assetsBySourceUid\.get\(key\)[\s\S]*?commitShotMutation\([\s\S]*?hmbToggleImageAssetShotAsset\(state, shotUuid, key, asset\)[\s\S]*?paintActiveShotSelection/,
  "A Shot tray X must remove only that Shot membership without disconnecting the shared source.",
);
assert.doesNotMatch(selectedHandler, /disconnect_import_uid|_disconnect_import_connection/);
assert.match(
  source,
  /Disconnect this external image from IMAGE_IMPORT_IN\. Multi-image or ambiguous links must be removed at the input port\./,
);
assert.match(
  source,
  /이 외부 이미지를 IMAGE_IMPORT_IN에서 연결 해제합니다\./,
);
assert.match(
  source,
  /clean\(asset\.image_main_type\) === "Select Image Main Type"[\s\S]*?\? unclassified/,
  "The released v2 taxonomy sentinel must render as an unclassified label.",
);
assert.match(source, /unclassified: "미분류"/);

console.log("HMB ImageAsset guarded external disconnect widget regression: PASS");
