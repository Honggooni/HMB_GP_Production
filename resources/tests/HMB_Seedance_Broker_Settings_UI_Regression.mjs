import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import crypto from "node:crypto";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const argument = (name) => { const index = process.argv.indexOf(name); return index < 0 ? "" : process.argv[index + 1] || ""; };
const libraryRoot = path.resolve(argument("--library-root") || fileURLToPath(new URL("../..", import.meta.url)));
const sourcePath = path.join(libraryRoot, "widgets/HMBSeedanceGenerationWidget.js");
const sourceBytes = fs.readFileSync(sourcePath);
const source = sourceBytes.toString("utf8");
const sha = (value) => crypto.createHash("sha256").update(value).digest("hex");
const evidenceDir = argument("--evidence-dir") || process.env.HMB_SEEDANCE_BROKER_EVIDENCE_DIR;
if (evidenceDir) fs.mkdirSync(evidenceDir, { recursive: true });
const lifecycleEvidence = { schema: "hmb-seedance-broker-modal-ownership", version: 1, source_root: libraryRoot,
  source_sha256: sha(sourceBytes), scope: "Actual Chrome native-row fixtures with controlled pending transport and second-node modal click event; no live engine, credentials, network or paid API",
  provider_paid_calls: 0, cases: [] };
const saveEvidence = () => { if (evidenceDir) fs.writeFileSync(path.join(evidenceDir, "modal-ownership-receipt.json"), JSON.stringify(lifecycleEvidence, null, 2)); };
const require = createRequire(import.meta.url);
let playwright;
try { playwright = require("playwright"); }
catch {
  try { playwright = require(path.join(os.homedir(), ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright")); }
  catch {
    if (process.env.HMB_SEEDANCE_REQUIRE_BROWSER === "1") throw new Error("Playwright required");
    console.log("HMB Seedance Broker settings UI: SKIP (Playwright unavailable)");
    process.exit(0);
  }
}
const executablePath = process.env.HMB_SEEDANCE_TEST_BROWSER || "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
if (!fs.existsSync(executablePath)) {
  if (process.env.HMB_SEEDANCE_REQUIRE_BROWSER === "1") throw new Error("Browser required");
  console.log("HMB Seedance Broker settings UI: SKIP (browser unavailable)");
  process.exit(0);
}

const browser = await playwright.chromium.launch({ executablePath, headless: true });
try {
  const page = await browser.newPage();
  await page.route("**/*", (route) => route.abort());
  const assertCompactModelSpacing = async (reason) => {
    const layout = await page.evaluate(() => {
      const bounds = (id) => document.getElementById(id).getBoundingClientRect();
      const header = bounds("shot-header");
      const model = bounds("model-slot");
      const task = bounds("task-slot");
      const hidden = ["command-slot", "broker-slot"].map((id) => {
        const slot = document.getElementById(id);
        const box = slot.getBoundingClientRect();
        const style = getComputedStyle(slot);
        return { id, height: box.height, margin: parseFloat(style.marginBottom), display: style.display };
      });
      return { above: model.top - header.bottom, below: task.top - model.bottom, modelHeight: model.height, taskHeight: task.height, hidden };
    });
    assert.ok(layout.above >= 0 && layout.above <= 4.01, `${reason}: no blank carrier gap above Model (${layout.above}px)`);
    assert.ok(layout.below >= 0 && layout.below <= 4.01, `${reason}: no blank carrier gap below Model (${layout.below}px)`);
    assert.equal(layout.modelHeight, 40, `${reason}: native Model must keep its normal height`);
    assert.equal(layout.taskHeight, 40, `${reason}: native Task must keep its normal height`);
    for (const slot of layout.hidden) {
      assert.equal(slot.height, 0, `${reason}: ${slot.id} must not reserve host row height`);
      assert.equal(slot.margin, 0, `${reason}: ${slot.id} must not reserve host row margin`);
      assert.notEqual(slot.display, "none", `${reason}: custom carrier must remain mounted for refresh transport`);
    }
  };
  const assertRefreshTransport = async (reason) => {
    const previous = await page.evaluate(() => ({ count: window.refreshCommands.length, urls: window.savedUrls }));
    await page.evaluate(() => {
      const probe = document.createElement("div");
      probe.id = "refresh-probe";
      document.getElementById("node").appendChild(probe);
      probe.__hmbSeedanceLatestProps = {
        value: {
          schema: "hmb-seedance-shot-ui", schema_version: 2, shot_catalog: {}, shot: {},
          generation: { schema: "hmb-seedance-generation-preview", version: 1, phase: "timed_out", job_id: "existing-job", action: "refresh_existing" },
        },
      };
      if (!window.seedance.hmbSeedanceRequestExistingResult(probe)) throw new Error("Hidden carrier lost existing-result command transport");
    });
    await page.waitForFunction((count) => window.refreshCommands.length === count + 1, previous.count);
    const command = await page.evaluate(() => window.refreshCommands.at(-1));
    assert.equal(command.action, "refresh_existing", `${reason}: refresh transport must retain its action`);
    assert.equal(command.schema, "hmb-seedance-refresh-command");
    assert.deepEqual(await page.evaluate(() => window.savedUrls), previous.urls, `${reason}: refresh transport must not modify Broker settings`);
    await page.evaluate(() => {
      const probe = document.getElementById("refresh-probe");
      window.seedance.hmbSeedanceCleanupPreviewOverlay(probe);
      probe.remove();
    });
  };
  await page.setContent(`<!doctype html><meta charset="utf-8"><style>
    body{background:#090d17}#node{width:600px}#parameters{position:relative;display:flex;flex-direction:column}
    .flex-shrink-0{flex-shrink:0}.overflow-hidden{overflow:hidden}
    .native-slot{height:40px;min-height:40px;margin-bottom:4px;box-sizing:border-box}
    #model,#task{display:flex;align-items:center;box-sizing:border-box;width:600px;height:40px;padding:0 12px;background:#252525;color:white}
    #model label{flex:1}#model select{width:200px;height:35px}
  </style><div class="react-flow__node" id="node">
    <div id="parameters" class="relative flex flex-col h-full px-3 pt-2 bg-card">
      <div class="native-slot" id="shot-header">HMBSeedanceGeneration</div>
      <div class="native-slot flex-shrink-0 overflow-hidden" id="command-slot" style="height:40px;min-height:40px;margin-bottom:4px">
        <div data-parameter-name="HMB_SEEDANCE_REFRESH_COMMAND"><div class="widget-container" id="command-container"></div></div>
      </div>
      <div class="native-slot" id="model-slot"><div data-parameter-name="model_id" id="model"><label>Model</label><select id="model-select"><option>Seedance 2.0</option><option selected>Seedance 2.5</option></select></div></div>
      <div class="native-slot flex-shrink-0 overflow-hidden" id="broker-slot" style="height:40px;min-height:40px;margin-bottom:4px">
        <div data-parameter-name="broker_server_url"><div class="widget-container" id="broker-container"></div></div>
      </div>
      <div class="native-slot" id="task-slot"><div data-parameter-name="task" id="task">Task <select id="task-select"><option>Reference to Video</option></select></div></div>
      <div data-parameter-name="prompt" id="prompt"><textarea id="prompt-input">Preserve this prompt</textarea></div>
    </div>
  </div>`);
  const uri = `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`;
  await page.evaluate(async (moduleUri) => {
    window.seedance = await import(moduleUri);
    window.savedUrls = [];
    window.refreshCommands = [];
    window.nodePointerDowns = 0;
    document.getElementById("node").addEventListener("pointerdown", () => { window.nodePointerDowns += 1; });
    const container = document.getElementById("broker-container");
    window.seedanceWidget = window.seedance.default(container, {
      value: "",
      onChange: (value) => { window.savedUrls.push(value); return Promise.resolve(); },
    });
    window.commandWidget = window.seedance.default(document.getElementById("command-container"), {
      value: { schema: "hmb-seedance-refresh-command", version: 1 },
      onChange: (value) => { window.refreshCommands.push(value); return Promise.resolve(); },
    });
  }, uri);
  const model = page.locator("#model");
  const icon = model.locator(".hmb-seedance-broker-icon");
  const gallery = model.locator(".hmb-seedance-gallery-icon");
  await icon.waitFor();
  await gallery.waitFor();
  assert.equal(await gallery.count(), 1, "Exactly one gallery action beside Broker settings");
  await assertCompactModelSpacing("Initial real host allocation");
  assert.equal(await page.locator("#model-select").inputValue(), "Seedance 2.5");
  assert.equal(await page.locator("#model-select option").count(), 2);
  const bounds = await page.evaluate(() => {
    const select = document.getElementById("model-select").getBoundingClientRect();
    const icon = document.querySelector(".hmb-seedance-broker-icon").getBoundingClientRect();
    const gallery = document.querySelector(".hmb-seedance-gallery-icon").getBoundingClientRect();
    return { selectRight: select.right, iconLeft: icon.left, galleryLeft: gallery.left, galleryRight: gallery.right,
      gearSize: [icon.width, icon.height], gallerySize: [gallery.width, gallery.height], aligned: icon.top === gallery.top };
  });
  assert.ok(bounds.selectRight <= bounds.galleryLeft && bounds.galleryRight <= bounds.iconLeft, "Neither icon may cover the native selector or each other");
  assert.deepEqual(bounds.gearSize, [29, 29]);
  assert.deepEqual(bounds.gallerySize, bounds.gearSize);
  assert.equal(bounds.aligned, true);
  assert.equal(await page.locator("#task-select").inputValue(), "Reference to Video");
  assert.equal(await page.locator("#prompt-input").inputValue(), "Preserve this prompt");
  if (process.env.HMB_SEEDANCE_SPACING_SCREENSHOT) {
    await page.locator("#node").screenshot({ path: process.env.HMB_SEEDANCE_SPACING_SCREENSHOT });
  }

  await assertRefreshTransport("Initial collapsed carriers");
  const beforeGallery = await page.evaluate(() => ({ count: window.refreshCommands.length, urls: window.savedUrls }));
  await gallery.click();
  await page.waitForFunction((count) => window.refreshCommands.length === count + 1, beforeGallery.count);
  const galleryCommand = await page.evaluate(() => window.refreshCommands.at(-1));
  assert.equal(galleryCommand.action, "open_gallery");
  assert.equal(galleryCommand.schema, "hmb-seedance-refresh-command");
  assert.deepEqual(Object.keys(galleryCommand).sort(), ["action", "action_id", "issued_at_ms", "schema", "version"]);
  assert.deepEqual(await page.evaluate(() => window.savedUrls), beforeGallery.urls);
  assert.equal(await page.locator("#prompt-input").inputValue(), "Preserve this prompt");
  assert.equal(await page.evaluate(() => window.nodePointerDowns), 0, "Gallery click must not start graph drag");
  // React may remove only the injected gallery action while retaining Model/gear.
  await page.evaluate(() => document.querySelector(".hmb-seedance-gallery-icon").remove());
  await page.waitForFunction(() => document.querySelectorAll("#model .hmb-seedance-gallery-icon").length === 1);
  assert.equal(await icon.count(), 1);

  await page.evaluate(() => {
    for (const id of ["command-slot", "broker-slot"]) {
      document.getElementById(id).setAttribute("style", "height:40px;min-height:40px;margin-bottom:4px");
    }
  });
  await page.waitForFunction(() => ["command-slot", "broker-slot"].every((id) => document.getElementById(id).getBoundingClientRect().height === 0));
  await assertCompactModelSpacing("Host rewrote slot style");

  await icon.click();
  const dialog = page.getByRole("dialog", { name: "FN AI Broker 주소" });
  await dialog.waitFor();
  await page.evaluate(() => {
    window.seedanceWidget = window.seedance.default(document.getElementById("broker-container"), {
      value: "",
      onChange: (value) => { window.savedUrls.push(value); return Promise.resolve(); },
    });
  });
  assert.equal(await dialog.count(), 1, "A widget factory refresh must not dismiss an open settings dialog");
  await assertCompactModelSpacing("Repeated custom widget factory");
  assert.equal(await dialog.locator("[data-broker-url]").inputValue(), "");
  await dialog.locator("[data-broker-url]").press("Shift+Tab");
  assert.equal(await page.evaluate(() => document.activeElement?.hasAttribute("data-broker-save")), true);
  await dialog.locator("[data-broker-save]").press("Tab");
  assert.equal(await page.evaluate(() => document.activeElement?.hasAttribute("data-broker-url")), true);
  await dialog.locator("[data-broker-url]").fill("http://other.example.com:8080");
  await dialog.locator("[data-broker-save]").click();
  assert.match(await dialog.locator("[data-broker-error]").innerText(), /HTTPS/);
  assert.deepEqual(await page.evaluate(() => window.savedUrls), []);
  await dialog.locator("[data-broker-url]").fill("https://other.example.com:8443/path");
  await dialog.locator("[data-broker-save]").click();
  assert.match(await dialog.locator("[data-broker-error]").innerText(), /원점/);
  assert.deepEqual(await page.evaluate(() => window.savedUrls), []);
  await dialog.locator("[data-broker-url]").fill("https://other.example.com:8443/");
  await dialog.locator("[data-broker-save]").click();
  await dialog.waitFor({ state: "detached" });
  assert.deepEqual(await page.evaluate(() => window.savedUrls), ["https://other.example.com:8443"]);
  assert.equal(await page.locator("#model-select").inputValue(), "Seedance 2.5");
  assert.equal(await page.evaluate(() => window.nodePointerDowns), 0, "Settings button should not initiate graph drag");

  await page.evaluate(() => {
    window.seedanceWidget.update({
      value: "https://other.example.com:8443",
      onChange: (value) => { window.savedUrls.push(value); return Promise.resolve(); },
    });
    const old = document.getElementById("model");
    const replacement = document.createElement("div");
    replacement.id = "model";
    replacement.setAttribute("data-parameter-name", "model_id");
    replacement.innerHTML = '<label>Model</label><select id="model-select"><option>Seedance 2.0</option><option selected>Seedance 2.5</option></select>';
    old.replaceWith(replacement);
  });
  await page.waitForFunction(() => document.querySelectorAll("#model .hmb-seedance-broker-icon").length === 1);
  assert.equal(await gallery.count(), 1);
  await assertCompactModelSpacing("Native Model React rerender");
  await icon.click();
  await dialog.waitFor();
  assert.equal(await dialog.locator("[data-broker-url]").inputValue(), "https://other.example.com:8443");
  await dialog.locator("[data-broker-url]").fill("");
  await dialog.locator("[data-broker-save]").click();
  await dialog.waitFor({ state: "detached" });
  assert.deepEqual(await page.evaluate(() => window.savedUrls), ["https://other.example.com:8443", ""]);

  await page.evaluate(() => {
    for (const id of ["command-slot", "broker-slot"]) {
      const old = document.getElementById(id);
      const next = document.createElement("div");
      next.className = "native-slot flex-shrink-0 overflow-hidden";
      next.id = id;
      next.setAttribute("style", "height:40px;min-height:40px;margin-bottom:4px");
      next.appendChild(old.firstElementChild);
      old.replaceWith(next);
      window[`old_${id}`] = old;
    }
  });
  await page.waitForFunction(() => ["command-slot", "broker-slot"].every((id) => document.getElementById(id).getBoundingClientRect().height === 0));
  await assertCompactModelSpacing("Host reparented mounted carriers");
  assert.deepEqual(await page.evaluate(() => ["command-slot", "broker-slot"].map((id) => window[`old_${id}`].style.height)), ["40px", "40px"], "Detached host wrappers must regain original style");
  await assertRefreshTransport("Host reparented mounted carriers");

  await icon.click();
  await dialog.waitFor();
  await dialog.locator("[data-broker-url]").press("Escape");
  await dialog.waitFor({ state: "detached" });

  // Model a host opening node B's settings while A's previous save is pending.
  // The actual production click handler replaces the document-owned dialog.
  // An old success must not focus A's gear through the newly active B dialog.
  await page.evaluate(() => {
    window.modalPending = [];
    window.seedanceWidget.update({ value: "", onChange: () => new Promise((resolve, reject) => window.modalPending.push({ resolve, reject })) });
    const second = document.createElement("div");
    second.className = "react-flow__node";
    second.id = "second-node";
    second.innerHTML = '<div data-parameter-name="model_id" id="second-model"><label>Model B</label><select><option>Seedance 2.5</option></select></div><div data-parameter-name="broker_server_url"><div id="second-broker-container"></div></div>';
    document.body.appendChild(second);
    window.secondBrokerWidget = window.seedance.default(document.getElementById("second-broker-container"), {
      value: "https://second.example.com", onChange: () => Promise.resolve(),
    });
  });
  for (const outcome of ["resolve", "reject"]) {
    await icon.click();
    await dialog.locator("[data-broker-url]").fill("https://first.example.com");
    await dialog.locator("[data-broker-save]").click();
    await page.evaluate(() => {
      document.querySelector("#second-model .hmb-seedance-broker-icon").dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    assert.equal(await dialog.locator("[data-broker-url]").inputValue(), "https://second.example.com");
    const before = await page.evaluate(() => ({ active_in_dialog: Boolean(document.activeElement?.closest('.hmb-seedance-broker-dialog')),
      active_is_input: document.activeElement?.hasAttribute('data-broker-url'), dialogs: document.querySelectorAll('.hmb-seedance-broker-dialog').length }));
    assert.equal(before.active_is_input, true);
    await page.evaluate(async (outcome) => {
      const pending = window.modalPending.at(-1);
      if (outcome === "resolve") pending.resolve(); else pending.reject(new Error("obsolete settings failure"));
      await Promise.resolve(); await Promise.resolve();
    }, outcome);
    const after = await page.evaluate(() => ({ active_in_dialog: Boolean(document.activeElement?.closest('.hmb-seedance-broker-dialog')),
      active_is_input: document.activeElement?.hasAttribute('data-broker-url'), dialogs: document.querySelectorAll('.hmb-seedance-broker-dialog').length,
      current_value: document.querySelector('[data-broker-url]')?.value, current_error: document.querySelector('[data-broker-error]')?.textContent,
      focused_node: document.activeElement?.closest('.react-flow__node')?.id || '' }));
    lifecycleEvidence.cases.push({ case: `closed-A-${outcome}-while-B-active`, before, after });
    saveEvidence();
    if (evidenceDir && outcome === "resolve") await page.screenshot({ path: path.join(evidenceDir, "cross-node-pending-completion.png") });
    assert.equal(after.active_is_input, true, "A closed dialog's delayed completion must not steal the new dialog's input focus.");
    assert.equal(after.dialogs, 1);
    assert.equal(after.current_value, "https://second.example.com");
    assert.equal(after.current_error, "");
    await dialog.locator("[data-broker-cancel]").click();
  }

  // Cleanup closes A and restores its carrier. A late response cannot acquire
  // the replacement mount or its fresh settings dialog on the same container.
  await icon.click();
  await dialog.locator("[data-broker-url]").fill("https://first.example.com");
  await dialog.locator("[data-broker-save]").click();
  await page.evaluate(() => {
    window.retiredModal = window.modalPending.at(-1);
    window.seedanceWidget.cleanup();
    window.seedanceWidget = window.seedance.default(document.getElementById("broker-container"), {
      value: "https://replacement.example.com", onChange: () => Promise.resolve(),
    });
  });
  await icon.click();
  await page.evaluate(async () => { window.retiredModal.resolve(); await Promise.resolve(); await Promise.resolve(); });
  const replacement = await page.evaluate(() => ({ input_focused: document.activeElement?.hasAttribute('data-broker-url'),
    value: document.querySelector('[data-broker-url]')?.value, dialogs: document.querySelectorAll('.hmb-seedance-broker-dialog').length }));
  assert.deepEqual(replacement, { input_focused: true, value: "https://replacement.example.com", dialogs: 1 });
  lifecycleEvidence.cases.push({ case: "retired-A-completion-with-replacement-dialog", after: replacement });
  await dialog.locator("[data-broker-cancel]").click();
  await page.evaluate(() => { window.secondBrokerWidget.cleanup(); document.getElementById('second-node').remove(); });
  lifecycleEvidence.source_sha256_after = sha(fs.readFileSync(sourcePath));
  assert.equal(lifecycleEvidence.source_sha256_after, lifecycleEvidence.source_sha256);
  lifecycleEvidence.result = "PASS"; saveEvidence();
  await page.evaluate(() => { window.seedanceWidget.cleanup(); window.commandWidget.cleanup(); });
  assert.equal(await model.locator(".hmb-seedance-broker-icon").count(), 0);
  assert.equal(await model.locator(".hmb-seedance-gallery-icon").count(), 0);
  assert.equal(await model.evaluate((row) => row.style.paddingRight), "");
  const restored = await page.evaluate(() => ["command-slot", "broker-slot"].map((id) => ({
    height: document.getElementById(id).getBoundingClientRect().height,
    margin: getComputedStyle(document.getElementById(id)).marginBottom,
    ariaHidden: document.getElementById(id).getAttribute("aria-hidden"),
  })));
  assert.deepEqual(restored, [{ height: 40, margin: "4px", ariaHidden: null }, { height: 40, margin: "4px", ariaHidden: null }], "Cleanup must restore host-owned carrier styles and accessibility");
  console.log("HMB Seedance Broker settings/gallery UI: PASS (real Chrome native-row fixture, both icons 29px; settings/refresh/rerender/cleanup and cross-node pending modal ownership preserved)");
} finally {
  await browser.close();
}
