import assert from "node:assert/strict";
import fs from "node:fs";

const widgetPath = new URL("../../widgets/HMBVideoPickerLibraryWidget_v032.js", import.meta.url);
const widgetSource = fs.readFileSync(widgetPath, "utf8");
const widget = await import(`data:text/javascript;base64,${Buffer.from(widgetSource).toString("base64")}`);

assert.equal(widget.hmbNormalizeActivityLevel("critical"), "ERROR");
assert.equal(widget.hmbNormalizeActivityLevel("failed"), "ERROR");
assert.equal(widget.hmbNormalizeActivityLevel("warn"), "WARNING");
assert.equal(widget.hmbNormalizeActivityLevel("done"), "SUCCESS");
assert.equal(widget.hmbNormalizeActivityLevel("debug"), "INFO");

const longDagFailure = [
  "Depth shading failed for 148/333 paths:",
  ...Array.from({ length: 148 }, (_value, index) => `|Jett|rig|control_${index}`),
].join(", ");
const summarized = widget.hmbSummarizeActivityMessage(longDagFailure);
assert.match(summarized, /^Depth shading failed for 148\/333 paths/);
assert.match(summarized, /148 DAG paths omitted; see the Maya log file\.$/);
assert.doesNotMatch(summarized, /\|Jett\|rig\|control_/);
assert.equal(summarized.includes("\n"), false, "A rendered log entry must always remain one line.");
assert.ok(summarized.length <= 260, "A defensive widget summary must stay within its fixed row budget.");
assert.equal(
  widget.hmbSummarizeActivityMessage("|Jett|rig|mouth visibility OFF"),
  "[DAG path] visibility OFF",
  "Even a single Maya path must be redacted from the visible UI while retaining its action summary.",
);

const failedRows = widget.hmbActivityLogRowsForDisplay({
  status: "FAILED",
  message: longDagFailure,
  warnings: [longDagFailure],
  activity_log: [],
});
assert.equal(failedRows.length, 1, "The same warning and failure message must render only once.");
assert.equal(failedRows[0].level, "ERROR", "FAILED must upgrade a duplicate warning to red ERROR severity.");
assert.equal(failedRows[0].message, summarized);

const persistedFailure = widget.hmbStateWithNotificationsLogged({
  status: "FAILED",
  message: longDagFailure,
  warnings: [longDagFailure],
  activity_log: [],
}, {});
assert.equal(persistedFailure.activity_log.length, 1);
assert.equal(persistedFailure.activity_log[0].level, "ERROR");
assert.equal(persistedFailure.activity_log[0].message, summarized);
assert.doesNotMatch(persistedFailure.activity_log_text, /\|Jett\|rig\|control_/,
  "Frontend state commits must persist only the compact summary, never the full DAG list.");
const unchangedFailure = widget.hmbStateWithNotificationsLogged(persistedFailure, persistedFailure);
assert.equal(unchangedFailure.activity_log.length, 1, "An unchanged notification must not duplicate itself on state echo.");

const allLevels = widget.hmbActivityLogRowsForDisplay({
  status: "READY",
  message: "Waiting for a command.",
  warnings: ["Optional camera is missing."],
  activity_log: [
    { time: "10:00:00", level: "SUCCESS", message: "Maya scene loaded." },
    { time: "10:00:01", level: "INFO", message: "Reading frame range." },
    { time: "10:00:02", level: "ERROR", message: "Depth render failed." },
  ],
});
assert.deepEqual(
  allLevels.map((entry) => entry.level),
  ["SUCCESS", "INFO", "ERROR", "WARNING", "INFO"],
  "Success, info, error, warning, and current-state notifications must share Activity Log.",
);

const multiline = widget.hmbSummarizeActivityMessage("Critical error\nsecond line\r\nthird line");
assert.equal(multiline, "Critical error second line third line");
const inferredError = widget.hmbActivityLogRowsForDisplay({ activity_log: ["Depth render failed for the selected scope."] });
assert.equal(inferredError[0].level, "ERROR", "Legacy string errors without a level must still render red.");
const bareCritical = widget.hmbActivityLogRowsForDisplay({ activity_log_text: "CRITICAL renderer disconnected" });
assert.equal(bareCritical[0].level, "ERROR", "Bare critical log prefixes must render red without requiring a colon.");
const newlineDagDump = widget.hmbActivityLogRowsForDisplay({
  status: "FAILED",
  message: longDagFailure,
  activity_log_text: [
    "ERROR: Depth shading failed for 148/333 paths",
    ...Array.from({ length: 148 }, (_value, index) => `  |Jett|rig|control_${index}`),
  ].join("\n"),
});
assert.equal(newlineDagDump.some((entry) => entry.message.includes("|Jett|")), false,
  "A newline-formatted DAG dump must never leak individual Maya paths into Activity Log.");
assert.ok(newlineDagDump.length <= 2,
  "A newline-formatted DAG dump must collapse to summary rows instead of flooding the log.");
const genericLong = widget.hmbSummarizeActivityMessage("X".repeat(1000));
assert.ok(genericLong.length <= 260);
assert.match(genericLong, /details truncated; see Maya log/);

const cappedRows = widget.hmbActivityLogRowsForDisplay({
  activity_log: Array.from({ length: 240 }, (_value, index) => ({ level: "INFO", message: `row-${index}` })),
});
assert.equal(cappedRows.length, 80, "The visible Activity Log must match the backend's bounded 80-row history.");
assert.equal(cappedRows[0].message, "row-160");

assert.doesNotMatch(
  widgetSource,
  /class="statusbar"|\.statusbar\{|class="warnings"|\.warnings\{/,
  "The footer status bar and floating warning overlay must remain completely removed.",
);
assert.match(widgetSource, /id="activity-log-view" class="activity-log-view" role="log" aria-live="polite"/);
assert.match(widgetSource, /\.activity-log-row\[data-level="ERROR"\]\{color:#fb7185\}/);
assert.match(widgetSource, /\.activity-log-row\[data-level="WARNING"\]\{color:#fbbf24\}/);
assert.match(widgetSource, /\.activity-body\{[^}]*overflow:hidden;[^}]*contain:layout paint/);
assert.match(widgetSource, /\.activity-log-view\{[^}]*overflow-x:auto;overflow-y:auto;scrollbar-gutter:stable both-edges/);
assert.match(widgetSource, /\.activity-log-row\{[^}]*width:max-content;min-width:100%;[^}]*height:18px;min-height:18px;max-height:18px;[^}]*white-space:nowrap/);
assert.match(widgetSource, /\.activity-log-message\{[^}]*min-width:max-content;max-width:none;[^}]*text-overflow:clip;white-space:nowrap/);
assert.match(widgetSource, /const scrollLeft = Number\(logView\.scrollLeft \|\| 0\);/);
assert.match(widgetSource, /logView\.scrollLeft = scrollLeft;/);
assert.doesNotMatch(widgetSource, /id="activity-log-editor"|<textarea[^>]*activity/);
assert.doesNotMatch(widgetSource, /<span>\$\{escapeHtml\(state\.message\)\}<\/span>/,
  "Critical messages must not leak into empty Outliner or viewport layout surfaces.");

console.log("HMB VideoPicker log-only notification UI regression: PASS");
