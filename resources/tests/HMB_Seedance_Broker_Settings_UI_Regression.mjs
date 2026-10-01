import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createRequire } from "node:module";

const source = fs.readFileSync(new URL("../../widgets/HMBSeedanceGenerationWidget.js", import.meta.url), "utf8");
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
  await icon.waitFor();
  await assertCompactModelSpacing("Initial real host allocation");
  assert.equal(await page.locator("#model-select").inputValue(), "Seedance 2.5");
  assert.equal(await page.locator("#model-select option").count(), 2);
  const bounds = await page.evaluate(() => {
    const select = document.getElementById("model-select").getBoundingClientRect();
    const icon = document.querySelector(".hmb-seedance-broker-icon").getBoundingClientRect();
    return { selectRight: select.right, iconLeft: icon.left };
  });
  assert.ok(bounds.selectRight <= bounds.iconLeft, "Broker icon must not cover native Model selector");
  assert.equal(await page.locator("#task-select").inputValue(), "Reference to Video");
  assert.equal(await page.locator("#prompt-input").inputValue(), "Preserve this prompt");
  if (process.env.HMB_SEEDANCE_SPACING_SCREENSHOT) {
    await page.locator("#node").screenshot({ path: process.env.HMB_SEEDANCE_SPACING_SCREENSHOT });
  }

  await assertRefreshTransport("Initial collapsed carriers");

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
  await page.evaluate(() => { window.seedanceWidget.cleanup(); window.commandWidget.cleanup(); });
  assert.equal(await model.locator(".hmb-seedance-broker-icon").count(), 0);
  assert.equal(await model.evaluate((row) => row.style.paddingRight), "");
  const restored = await page.evaluate(() => ["command-slot", "broker-slot"].map((id) => ({
    height: document.getElementById(id).getBoundingClientRect().height,
    margin: getComputedStyle(document.getElementById(id)).marginBottom,
    ariaHidden: document.getElementById(id).getAttribute("aria-hidden"),
  })));
  assert.deepEqual(restored, [{ height: 40, margin: "4px", ariaHidden: null }, { height: 40, margin: "4px", ariaHidden: null }], "Cleanup must restore host-owned carrier styles and accessibility");
  console.log("HMB Seedance Broker settings UI: PASS");
} finally {
  await browser.close();
}
