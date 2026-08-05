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
  /on\(card\.querySelector\("\[data-remove-selected\]"\)[\s\S]*?compactSelectionOrder\(state\.assets\);/,
)?.[0] || "";
assert.match(
  selectedHandler,
  /externalImport[\s\S]*?state\.disconnect_import_uid = asset\.source_uid;[\s\S]*?state = emit\(props, state\);[\s\S]*?return;/,
  "An external X must request a graph disconnect and keep selection until acknowledgement.",
);
assert.match(
  source,
  /disconnectPending \? 'disabled aria-busy="true"'/,
  "The external X must expose a pending state while the backend checks the edge.",
);
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
  /UNCLASSIFIED_SOURCE_TYPES\.has\(clean\(asset\.source_type\)\)[\s\S]*?\? unclassified/,
  "The compatibility sentinel must render as an optional unclassified label.",
);
assert.match(source, /unclassified: "미분류 \(선택 사항\)"/);

console.log("HMB ImageAsset guarded external disconnect widget regression: PASS");
