import assert from "node:assert/strict";
import fs from "node:fs";


const widgetPath = new URL(
  "../../widgets/HMBImageAssetLibraryWidget.js",
  import.meta.url,
);
const source = fs.readFileSync(widgetPath, "utf8");
const widget = await import(widgetPath);


class FakeBackdrop {
  constructor() {
    this.listeners = new Map();
  }

  addEventListener(type, handler, options) {
    const listeners = this.listeners.get(type) || [];
    listeners.push({ handler, options });
    this.listeners.set(type, listeners);
  }

  removeEventListener(type, handler, options) {
    this.listeners.set(
      type,
      (this.listeners.get(type) || []).filter(
        (listener) => listener.handler !== handler || listener.options !== options,
      ),
    );
  }

  dispatch(type, target, details = {}) {
    for (const listener of this.listeners.get(type) || []) {
      listener.handler({ type, target, ...details });
    }
  }
}


const backdrop = new FakeBackdrop();
const nameInput = { parentElement: backdrop };
let closeCount = 0;
const cleanup = widget.hmbInstallImageAssetRegistrationBackdropDismissal(
  backdrop,
  () => { closeCount += 1; },
);

for (const type of ["pointerdown", "mousedown", "pointerup", "mouseup"]) {
  assert.equal(
    backdrop.listeners.get(type)?.[0]?.options,
    true,
    `${type} must record the gesture in capture phase before form controls can stop it.`,
  );
}

// The reported failure: selecting the whole image name starts in the input,
// ends outside the passport, and creates a backdrop-targeted synthetic click.
backdrop.dispatch("pointerdown", nameInput, { pointerId: 7, button: 0, isPrimary: true, clientX: 100, clientY: 100 });
backdrop.dispatch("mousedown", nameInput);
backdrop.dispatch("pointerup", backdrop, { pointerId: 7, button: 0, isPrimary: true, clientX: 260, clientY: 100 });
backdrop.dispatch("mouseup", backdrop);
backdrop.dispatch("click", backdrop);
assert.equal(
  closeCount,
  0,
  "Dragging a name selection out of the dialog must keep registration open.",
);

// Pointer capture can retarget the release back to the input; that sequence is
// also an interior gesture and cannot dismiss the registration dialog.
backdrop.dispatch("pointerdown", nameInput, { pointerId: 8, button: 0, isPrimary: true });
backdrop.dispatch("pointerup", nameInput, { pointerId: 8, button: 0, isPrimary: true });
backdrop.dispatch("click", nameInput);
assert.equal(closeCount, 0, "Pointer-captured input selection must remain open.");

// A deliberate press and release on the real backdrop retains the established
// click-outside behavior.
backdrop.dispatch("pointerdown", backdrop, { pointerId: 9, button: 0, isPrimary: true, clientX: 40, clientY: 40 });
backdrop.dispatch("mousedown", backdrop);
backdrop.dispatch("pointerup", backdrop, { pointerId: 9, button: 0, isPrimary: true, clientX: 42, clientY: 42 });
backdrop.dispatch("mouseup", backdrop);
backdrop.dispatch("click", backdrop);
assert.equal(closeCount, 1, "A direct backdrop click must still close once.");

// Starting on the backdrop and releasing over the passport is a drag, not a
// backdrop click, even if a browser reports the common ancestor as the target.
backdrop.dispatch("pointerdown", backdrop, { pointerId: 10, button: 0, isPrimary: true });
backdrop.dispatch("pointerup", nameInput, { pointerId: 10, button: 0, isPrimary: true });
backdrop.dispatch("click", backdrop);
assert.equal(closeCount, 1, "Both gesture endpoints must be the backdrop.");

// A real drag on the dark backdrop is not an intent to dismiss, even though
// both endpoints happen to remain on that same large surface.
backdrop.dispatch("pointerdown", backdrop, { pointerId: 11, button: 0, isPrimary: true, clientX: 20, clientY: 20 });
backdrop.dispatch("pointermove", backdrop, { pointerId: 11, clientX: 80, clientY: 20 });
backdrop.dispatch("pointerup", backdrop, { pointerId: 11, button: 0, isPrimary: true, clientX: 80, clientY: 20 });
backdrop.dispatch("click", backdrop);
assert.equal(closeCount, 1, "Backdrop dragging beyond the movement threshold must remain open.");

// A different pointer cannot complete the primary pointer's press.
backdrop.dispatch("pointerdown", backdrop, { pointerId: 12, button: 0, isPrimary: true });
backdrop.dispatch("pointerup", backdrop, { pointerId: 13, button: 0, isPrimary: false });
backdrop.dispatch("click", backdrop);
assert.equal(closeCount, 1, "A different pointer must not complete backdrop dismissal.");

// Secondary buttons never arm dismissal.
backdrop.dispatch("pointerdown", backdrop, { pointerId: 14, button: 2, isPrimary: true });
backdrop.dispatch("pointerup", backdrop, { pointerId: 14, button: 2, isPrimary: true });
backdrop.dispatch("click", backdrop);
assert.equal(closeCount, 1, "A secondary-button gesture must never dismiss the dialog.");

// Cancellation clears a stale start and cannot arm a later synthetic click.
backdrop.dispatch("pointerdown", backdrop, { pointerId: 15, button: 0, isPrimary: true });
backdrop.dispatch("pointercancel", backdrop, { pointerId: 15 });
backdrop.dispatch("click", backdrop);
assert.equal(closeCount, 1, "A cancelled gesture must never dismiss the dialog.");

backdrop.dispatch("pointerdown", backdrop, { pointerId: 16, button: 0, isPrimary: true });
backdrop.dispatch("lostpointercapture", backdrop, { pointerId: 16 });
backdrop.dispatch("click", backdrop);
assert.equal(closeCount, 1, "Lost pointer capture must never leave dismissal armed.");

assert.match(
  source,
  /querySelectorAll\("\[data-registration-cancel\]"\)[\s\S]*?closeRegistration\(\)/,
  "The X and Cancel controls must retain explicit close semantics.",
);
assert.match(
  source,
  /if \(event\.key === "Escape"\) \{[\s\S]*?closeRegistration\(\)/,
  "Escape must retain explicit close semantics.",
);

cleanup();
for (const listeners of backdrop.listeners.values()) assert.equal(listeners.length, 0);

console.log("HMB ImageAsset registration drag-dismissal regression: PASS");
