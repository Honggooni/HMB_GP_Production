# Changelog

## `v0.6.55` — 2026-08-25

- Promoted the fully validated `v0.6.54` local-test line as the replacement
  team release for `main` and GitHub Latest Release.
- Reduced Agent output security to the requested two lightweight boundaries:
  authenticated server policy/contract verification and direct structured
  Agent/runtime-state suppression. Client policy-text, JSON-string, reversible
  encoding, compression, and recursive disclosure inspection remain removed.
- Restored Agent widget and output-port normalization on every saved-workflow
  deserialize so stale expandable headers and legacy labels cannot return.
- Kept replaced/future sanitizer failures fail-closed without leaking their raw
  exception through the host scheduler.

## `v0.6.54` — 2026-08-25 (local test)

- Started the local-only test line from the team-distributed `v0.6.53` build.
- Removed client-side policy-text matching, complete-document detection, and
  reversible encoding/recursive policy disclosure scans now that signed Agent
  policy content is delivered only by the server.
- Retained two lightweight boundaries: authenticated server policy contract
  verification and direct structured Agent/runtime-state suppression at public
  UI outputs. The client no longer interprets plaintext or JSON strings for
  security purposes. No `v0.6.54` commit, tag, push, or team distribution is
  authorized.

## `v0.6.53` — 2026-08-25

- Promoted the validated `v0.6.52` local-test line from the team-distributed
  `v0.6.51` baseline.
- Version policy: odd patch versions are team releases; even patch versions are
  local test builds and are not distributed directly.
- Retired the fixed 160-character policy-text publication criterion. FINAL TEXT
  now accepts policy-required generator wording in one Agent call, while native
  Agent/runtime-state structures and complete confidential document dumps remain
  blocked, and private wrapper headings are still scrubbed. Removed the policy-
  collision retry and its terminal rewrite failure path so valid policy-required
  instructions cannot be rejected by repeated overlap.

## `v0.6.51` — 2026-08-25

- Promoted the validated `v0.6.50` local-test line from the team-distributed
  `v0.6.49` baseline.
- Version policy: odd patch versions are team releases; even patch versions are
  local test builds and are not distributed directly.
- Kept the 160-character protected-policy disclosure boundary intact while
  separating genuine Agent/runtime-state leaks from generator text that echoed
  protected wording. A raw-policy-only collision now stays private and receives
  exactly one scene-specific finalization retry using the same Shot facts.
- Added a one-shot retry authority, terminal re-sanitization, and explicit
  fail-closed handling. Agent-state output never retries, a second collision
  cannot loop, and only the final clean result can publish a Seedance snapshot.
- Added a public-CI regression for the 159/160 boundary, raw-to-clean recovery,
  repeated collision, and Agent-state isolation.

## `v0.6.49` — 2026-08-25

- Promoted the validated `v0.6.48` local-test line from the team-distributed
  `v0.6.47` baseline.
- Version policy: odd patch versions are team releases; even patch versions are
  local test builds and are not distributed directly.
- Connected each numbered HMBAgent final-text `output` to the matching
  HMBSeedanceGeneration public `prompt` as a strict same-flow/same-Shot route.
  The retained edge keeps both string ports naturally lit while the widget
  hides only that exact cable; `Only` removes the managed connection and leaves
  both ports unlit. Five-Shot, reload ownership, foreign-input preservation,
  and shared-observer UI regressions cover the contract.
- Removed the redundant `Scene / Environment` Target generated for Environment
  Main/Sub Types while preserving the Target contract for named characters,
  props, FX/ranges, Global Look, and Camera/Composition. Existing canonical
  environment defaults migrate to blank; authored named Targets remain intact.
- Restored all three Video / Color binding controls by retaining the empty
  structural slots created by `+` through Python and widget normalization.
- Fixed Prompt-first workflow order: a freshly registered ImageAsset now
  advertises its first exact catalog once, Prompt text survives crossed source/UI
  revisions, and default catalog-less `Only` accepts Shot 1. A user-selected
  `Only` from the same verified publisher remains authoritative.

## `v0.6.47` — 2026-08-25

- Promoted the validated `v0.6.46` local-test line from the team-distributed
  `v0.6.45` baseline.
- Version policy: odd patch versions are team releases; even patch versions are
  local test builds and are not distributed directly.
- Preserved fast Prompt Shot/UI edits across crossed source and UI revisions,
  while retaining the newest source-owned connection diagnostics. Added
  actual-host coverage for connected edits across Picker refresh and disconnect.
- Moved ImageAsset's first catalog scan out of the node-registration UI callback,
  keeping the saved snapshot immediately available while the worker refreshes.
- Removed the process-wide Shot-routing callback bottleneck with independent
  per-flow gates, fresh queued same-flow passes, and transaction-scoped Picker
  media probes. Added early aggregate Seedance media-size rejection, chunked
  image/audio encoding, and bounded streaming for supported cloud video uploads.
- Standardized hidden VideoPicker publications and Prompt/Seedance consumers on
  a strict `dict` port contract. Bounded legacy JSON strings migrate during
  workflow hydration; malformed or oversized legacy values fail closed to `{}`.
- Split the documented Broker transport policy: Agent policy delivery remains
  strict pinned HTTPS, while the exact Seedance generation endpoint may use
  HTTP only inside the access-controlled, non-routed HMB production LAN.
- Restored VideoPicker's compact-first cold and workflow-reload mount at
  1400x360, with an exact 252px one-Shot Loader row and deterministic 186px
  growth for each additional Shot. Compact mode keeps native resize controls
  locked; an explicit expand restores the authoring surface without changing
  the React Flow canvas, workspace viewport, or saved Shot media.
- Removed the expanded Picker's residual lower black area by filling only the
  Picker-owned clip/root to the exact live node space. Host parameter stacks,
  sibling nodes, canvas transforms, zoom, and pan remain untouched.
- Healed missing or stale Maya Outliner selections after READ by stable UUID,
  DAG path, then first root, so Color Pick controls always bind to a real
  Outliner target instead of remaining disabled or storing a color-only echo.
- Made one VideoPicker publication use the same immutable Shot state and media
  probe results for `VIDEO_OUT`, `PICKER_OUT`, and `SHOT_PICKER_OUT`; five-Shot
  save/reload now verifies exact UID order and media hashes without revision
  mixing. Windows UNC previews also retain their server authority through the
  Griptape external-file route, including Original Preview after reload.
- Unified Seedance 2.5 quality and resolution payloads: `720p` publishes
  `quality=720p`/`resolution=720p`, while `1080p` publishes
  `quality=1080p`/`resolution=1080p`; aspect ratio remains independent and the
  established Seedance 2.0 Broker compatibility shape is unchanged.
- Made ImageAsset and VideoPicker singleton lifecycle reset-safe: Griptape's
  same-flow `<name>_temp` replacement inherits durable Shot images and Loader
  video membership, order, selection, and preview while runtime/error/Maya
  authoring state is renewed; ordinary delete/recreate releases every stale
  admission lease. Expanded Picker authoring now has a strict 1400x1200 floor;
  the manual viewport/activity divider is removed, Activity Log stays fixed at
  208px, and the viewport automatically fills every valid outer-node resize.
- Kept the ImageAsset registration dialog open when a name selection drag ends
  outside the dialog. The backdrop now closes only for a primary-button click
  that both starts and ends on the backdrop itself; Cancel, Close, and Escape
  retain their existing behavior.
- Fixed five simultaneous Prompt→Agent→Seedance Shot chains losing one Agent's
  source identity during retained UI/route interleaving. Each Agent now holds
  only its strictly verified execution Shot until its final phase is restored;
  Only mode remains independent and stale Shot snapshots never become routing
  authority.
- Enabled Shot 1–5 Seedance branches to prepare and poll concurrently while
  pacing only billable Broker POST starts by the server's one-second account
  interval. Managed video and returned-last-frame defaults are Shot-suffixed,
  preventing five parallel completions from overwriting one another; explicit
  user output paths remain unchanged.
- Made the runtime installer recover its extracted source directory from the
  invoked script path when a non-interactive Windows PowerShell launcher binds
  an empty `PSScriptRoot`, preserving the documented no-argument install flow.
- Made `기존 작업 결과 확인` paint its busy state before entering Griptape's
  retained value transaction. Existing-job lookup stays on the shared engine
  loop, offloads only blocking Broker I/O, rejects duplicate clicks and active
  renders, and never creates a replacement provider task.
- Removed the VideoPicker/React Flow geometry feedback that could raise
  minified React error #185. Expanded layout performs one settled mount repair
  and then reacts only to Picker-owned inner geometry or explicit view/resize
  boundaries; it no longer persistently observes and rewrites the host shell,
  allocator row, or trailing spacer on every React render.
- Persisted active Seedance task identity at submission time so a workflow can
  be reopened after an application interruption and retrieve the same Broker
  task. Recovery remains non-billable, handles definitive HTTP 429 rejection
  separately from an accepted task, and exposes a bounded non-reentrant result
  action only when an authoritative task is recoverable.
- Preserved exact ImageAsset Main/Sub classification through Prompt and Agent
  public-job contract v2. Prompt and Agent independently recompute the canonical
  source type and scope, reject mismatches, and keep Global Look references as
  scene-wide lighting/look authority unless a narrower explicit override is
  authored. Renewed field guidance separates literal dialogue/lip-sync text
  from visual action without adding a validation badge or QA display.

## `v0.6.45` — 2026-08-21

- Restored the native model-specific Seedance selector contract. Seedance
  2.0/2.0 Fast expose `Input Mode` with `Text Only`, `First/Last Frame`, and
  `Multimodal References`; Seedance 2.5 exposes `Task` with `Reference to
  Video`, `Video Editing`, and `Video Extension`. The paired hidden value stays
  synchronized so saved workflows and model switching preserve their intent.
- Added stock-style manual Reference Images, Reference Videos, and Reference
  Audio lists for `Only`. Numbered `Shot` mode preserves those authored values
  without using or deleting them, resolves only the exact same-Shot ImageAsset
  and VideoPicker publications, and forces the effective task to
  `Reference to Video` without changing the authored Only task.
- Added Seedance 2.5 verified MP4/MOV local output and optional verified local
  PNG last-frame output. The output container must match its extension, prior
  successful media remains available until atomic replacement succeeds, and
  signed Broker result URLs are not persisted in node output or logs.
- Added an authenticated Broker capability gate for task-declared 2.5
  Reference-to-Video, Editing, Extension, MOV, and returned-last-frame
  requests. R2V now declares `omni_reference_task_type=reference`, matching the
  stock 2.5 proxy; missing or mismatched capability contracts fail closed
  before reference upload or billable submission, while the 2.0/2.0 Fast
  multimodal request schema remains intact.
- Added native MOV-preview fallback text, expanded the actual-host Seedance
  generator and Picker-to-Seedance integration regressions, and kept the
  self-contained Direct Shot/MP4/widget contracts in the public Windows gate.
- Restored native image/video/audio colours on Seedance's manual reference
  rows, renamed the verified video connector label to `video_url`, and restored
  the native last-frame image preview when `Return Last Frame` is enabled.
- Deferred the preview overlay's `기존 작업 결과 확인` command until after the
  current UI value-set transaction, preventing the recovery action from
  re-entering and stalling Griptape while preserving same-task retrieval only.

## `v0.6.43` — 2026-08-21

- Added HMB Seedance Generation 2.5 with the official BytePlus saved-model
  alias, an HMB canonical Broker route, 720p default and optional 1080p HEVC,
  explicit 4-30 second duration, and model-specific limits of 30 image, 10
  video, and 10 audio references including audio-only input.
- Kept the HMB 2.5 production profile quality-focused: 480p and smart duration
  are not exposed, while 720p remains the default.
- Preserved the existing Seedance 2.0/2.0 Fast limits and exactly three legacy
  scalar video ports. Unknown model IDs, unsupported fields, and unapproved
  2.5 priority values remain fail-closed before Broker submission.
- Added native Seedance preview status overlays for submission, rendering,
  retrieval, download, verification, local cancellation, timeout, and failure.
  A prior successful video remains visible during a new render; recovery checks
  the authoritative existing job only and never creates a replacement task.
- Removed the obsolete HMB-specific Desktop launcher and its compatibility
  marker from the runtime closure. Agent policy bootstrap now relies on the
  exact packaged Griptape process provenance, and Griptape starts normally.
- Removed the legacy Maya binding setup helper from team runtime packages. It
  remains development-only; the production Maya runner never imports it.

## `v0.6.42` — 2026-08-21

- Removed VideoPicker compact mode's non-functional lower black band by
  reclaiming only the exact HMB state row's Editor-owned trailing spacer. The
  fix never mutates the workspace, viewport, canvas, or unrelated nodes.
- Kept compact sizing deterministic for Shot 1 through Shot 5: every added Shot
  grows the node by one complete 180px loader row plus its 6px gap.
- Added a fail-closed allocator fallback for changed Editor DOM signatures. An
  unrecognized host keeps the full 32px safety reserve instead of clipping the
  compact cards, and expanded mode restores all temporarily reclaimed styles.
- Fixed workflow hydration so Griptape's `initial_setup=True` replay can restore
  imported VideoPicker media instead of being rejected as a retired runtime
  publication. Shot ownership, order, selection, preview, and saved file paths
  now survive reload and subsequent ImageAsset Shot catalog updates.
- Added real saved-workflow and recursive Shot 1-through-5 round-trip gates,
  including delayed/equal widget echoes, every supported load-hook order, and
  Prompt's read-only consumption of the restored Picker catalog.
- Coalesced Prompt selection and frame-range drag publications, blocked
  equal-clock divergent echoes, and merged source/UI revision axes by stable
  image identity so rapid interaction no longer flickers or rolls back.
- Promoted the manifest-verified team runtime ZIP and SHA256 to a tagged GitHub
  Release only after the complete Windows release audit succeeds.

## `v0.6.41` — 2026-08-21

- Replaced VideoPicker's automatic top-layer dialog with an inline,
  ImageAsset-style hybrid view. The fixed internal header now switches between
  retained expanded content and a compact Shot loader without remounting the
  widget or changing the canvas viewport.
- Restored content-derived compact heights (158px empty, 252px for one
  populated Shot, capped at 360px with scrolling) and an expanded-first native
  1400x1200 cold mount, removing the clipped header and black-tail layout.
- Fixed HMBAgentLibrary's protected output contract to require generator-ready
  English instructions even when HMBPromptLibrary authoring text is Korean.
  Korean final instructions are stopped before reaching a video generator.
- Removed Prompt/Agent execution-time Shot graph re-entry from paired Prompt
  and media snapshot reads, preventing video hydration callbacks from blocking
  the next node while Prompt's synchronization lock is held.
- Preserved an accepted VideoPicker Shot catalog across unchanged router cache
  passes. Real publisher deletion, duplicate sources, stale generations, and
  catalog conflicts remain fail-closed under the central Shot router.

## `v0.6.40` — 2026-08-20

- Restored serialized VideoPicker media catalogs, Shot membership, selection,
  and fresh local media URLs across `initial_setup`, deserialize, load, and
  loaded hooks. The visible state row explicitly clears stale host hide flags,
  preventing saved cards from being trapped behind `Collapsed (3)`.
- VideoPicker now opens its expanded authoring surface on the first mount. The
  expanded surface uses a browser top-layer dialog while the host parameter row
  remains a fixed compact measurement, so neither initial load nor view changes
  resize, re-fit, pan, or split the React Flow workspace.
- Increased the visible compact state row to 360px inside a stable 480px native
  node shell and kept the hidden Maya/command transports out of adaptive row
  allocation.
- Replaced mixed Git-checkout/ZIP-overlay installation with a manifest-verified
  exact runtime replacement. Updates move the prior install to a recoverable
  `%LOCALAPPDATA%` rollback location, preserve `.venv`, and leave no source
  tests, administration tools, stale Maya fixtures, caches, obsolete files, or
  backup directory below the active Griptape libraries folder.
- Removed `resources/build_developer_release.py`. Runtime packaging now lives
  only in the development-only `tools` area and is never shipped as a library
  resource.
- Prevented Python bytecode creation in the supported HMB launcher and Maya
  runner so immutable runtime resources do not accumulate `__pycache__` data.

## `v0.6.37` — 2026-08-20

- Fixed the VideoPicker workspace-viewport hotfix path so cold load, reload,
  and compact/expanded geometry reconciliation no longer zoom, reframe, or
  shrink the surrounding React Flow workspace while the Picker settles.

## `v0.6.36` — 2026-08-20

- Approved the audited public GitHub team-distribution channel. The release
  contains only the public Broker CA and default service address; credentials,
  private keys, signed policy bodies, and team media remain excluded.
- Made HMBPromptLibrary Range a Prompt-owned per-image intent, independent of
  VideoPicker JSON, video order, Color Pick, probed duration, and capability
  flags. ON/OFF, signed 32-bit endpoints, and selected segments now survive
  Picker refresh, empty selection, reorder, disconnect, and reconnect; only a
  complete valid intent with a real video is projected to the Agent v1 media
  contract, so incomplete/no-video editing never blocks ordinary generation.
- Removed the fixed ZIP timestamp policy. Every packaged member now receives
  the actual local build time, while uniform member times and content hashes
  remain validated by the release builder and `--check-output`.
- Resolved Seedance Shot media before the public empty-input preflight so
  prompt-only, image-only, video-only, and combined jobs retain exact Shot
  binding without a false `Provide a prompt or supported media input` failure.
- Moved Agent policy retrieval, Seedance media preparation, and ImageAsset
  registration work away from UI-critical sections while preserving signed
  policy validation, durable media verification, cancellation, and rollback.
- Made VideoPicker selection, ordering, and compact/expanded transitions paint
  first, then publish coalesced state and geometry updates in the background.
- Reduced repeated Shot-routing graph reads through per-pass connection caches
  while retaining fail-closed UUID matching and ambiguity checks.

## `v0.6.35` — 2026-08-20

- Fixed Seedance StartFlow preflight so exact hidden ImageAsset/VideoPicker
  Shot media is resolved before the public empty-input check, while execution
  still revalidates Agent text, Shot UUID, and media hashes before Broker use.
- Moved Seedance media preparation and ImageAsset registration/root scanning
  off the UI/event loop, added bounded progress phases, and kept durable
  verification, rollback, cancellation, and fail-closed submission semantics.
- Made VideoPicker mode changes, selection, and drag ordering paint first and
  publish on a coalesced later frame; reduced repeated normalization, compact
  sizing passes, and eager ImageAsset thumbnail decoding.
- Kept the authenticated Agent policy fetch outside the shared session lock,
  exposed policy/preparation/run progress without policy data, and cached each
  Shot-routing target's incoming connections for one reconciliation pass.
- Unified ImageAsset and VideoPicker card ordering around Shot-local drag and
  drop, removed the ImageAsset left/right ordering controls, and kept compact,
  expanded, persisted, and downstream media order consistent.
- Reworked VideoPicker compact/expanded view ownership so host measurement,
  node geometry, and widget lifecycle cannot remove or collapse the live UI.
- Hardened five-library Shot binding across reload, publisher replacement,
  deletion, duplicate claims, and Agent-to-Seedance provenance validation.
- Added an atomic release closure manifest and SHA-256 inventory so partial or
  mixed-version installs can be detected before the library is activated.
- Cleaned generated project caches and superseded release artifacts from the
  developer workspace while retaining recovery backups and Maya prototypes.

## `v0.6.34` — 2026-08-20

- Restored Seedance `Only` prompt generation and made ImageAsset and
  VideoPicker Shot media independently optional. The selector now exposes
  `Only` plus each available numbered Shot, displays the active number, accepts
  image-only, video-only, combined, and prompt-only jobs, and keeps duplicate
  same-kind sources fail-closed.
- Added a private standalone VideoPicker Shot catalog so one Picker can provide
  video-conditioned Seedance input without requiring an ImageAsset node. When
  ImageAsset exists, its UUID catalog remains authoritative.

## `v0.6.01` (technical version `0.6.1`) — Unreleased

> This is a preparation target only. It does not mark a signed, packaged,
> committed, pushed, or otherwise completed `v0.6.01` release. The current
> worktree alignment is temporary and must be cleanly re-applied onto the
> `origin/main` `0.5.74` baseline before release preparation continues.

- Activated the offline-signed `2026-08-11.agent-shot-quality.v4.1` policy and
  its reviewed typed FX/Timing/Range contract. The verified artifact is server-managed at
  `D:\agent`; the prior signed v4 artifact is retained in the server backup.
- Replaced Prompt-to-Agent policy prose with a closed, data-only JOB/FX/USER
  JSON envelope. `USER DESCRIPTION DATA` now contains only the five fields
  authored directly in the Prompt UI; Picker/Image transport metadata, paths,
  identifiers, dimensions, diagnostics, and unknown connected fields are not
  promoted to user intent.
- Added strict Prompt/Agent schema parity, independent valid/invalid Range
  segment handling, exact Target/marker/local-point emitter validation, and
  fail-closed policy-fragment filtering for visible, nested, and JSON-wrapped
  Agent output.
- Reduced the public FX/Timing envelope to v3 raw facts: selected Main Type and
  role, Target/marker range segments, exact cues, and typed validation codes.
  Policy-dependent interpretation is now derived only after the signed Agent
  runtime has loaded and is never serialized into `PROMPT_OUT`.
- Moved the Agent policy loader to the fixed server-only
  `\\FIN-RCOMP7.funnyflux.local\HMB_AgentPolicy$\hmb_agent_core.dat` boundary,
  pinned the complete v4.1 envelope and inner digests, and removed every local,
  package, environment-variable, administrative-share, and retired-host fallback.
- Isolated canonical Agent inputs, native scheduler callbacks, stream chunks,
  logs, and final publication until output sanitization; added a regression
  against the installed Standard Agent constructor and callable-yield contract.
- Kept the four source/Prompt/Agent libraries generator-neutral and changed the
  release gate to require the active v4.1 identity while rejecting every `.dat`
  or policy document from client packages, including nested archives.
- Renamed the public generator module and class to
  `HMBSeedanceGeneration.py` / `HMBSeedanceGeneration`, and updated library
  registration, package exports, release allowlists, and generator integration
  tests to the same canonical identity.
- The retired class identifier is intentionally not exported as an alias.
  Saved workflows created before this rename must replace that generator node
  once and reconnect its existing ports; current repository workflows contain
  no serialized instance of the retired identifier.
- Hardened generator completion by probing the destination before a billable
  submission, publishing verified MP4 data atomically, retaining a successful
  primary video when optional sidecar metadata fails, and requiring bounded
  `ftyp`, non-empty `moov`, and non-empty `mdat` boxes.

## 0.5.14 - 2026-08-05

- Made server-searched MP4 imports publish a verified active-project copy even
  when no Maya scene is open. Picker cards and the main viewport now stream that
  local project copy instead of an inaccessible UNC/file URL.
- Treated explicit absolute and UNC video paths as filesystem authorities during
  media validation, preventing readable server references from being incorrectly
  resolved as missing active-project files.
- Added an Activity Log horizontal scrollbar, preserved its position during
  state refreshes, and kept long one-line diagnostics horizontally inspectable.

## 0.5.13 - 2026-08-05

- Revalidated every selected local/project video before Picker publication.
  A missing project copy now falls back to its readable source MP4; if neither
  copy is available, `PICKER_OUT` and `VIDEO_OUT` are cleared atomically and the
  Picker reports that the MP4 must be re-imported or its Playblast regenerated.
- Preserved missing/unreadable local-video errors through Seedance preparation
  instead of relabeling them as upload-service credential failures. These
  failures still stop before any Ark create-task POST.
- Made the signed Agent policy mandatory only for the exact canonical
  `HMBPromptLibrary.PROMPT_OUT -> HMBAgentLibrary.prompt` edge. Missing,
  unreadable, malformed, unsigned, stale, or contract-invalid policy data now
  produces a visible `HMB POLICY REQUIRED` error and performs zero native Agent,
  tool, or model calls.
- Preserved stock native Agent execution for requests with no canonical HMB
  Prompt edge. Ambiguous or unverifiable Prompt topology is no longer treated as
  a verified non-HMB route and is blocked with a separate connection error.
- Cleared prior FINAL TEXT, Agent wrapper state, and temporary policy data on the
  failure path so operators can detect and correct the shared-policy problem
  without receiving a silent ungoverned result.
- Retired the standalone partial Prompt/Agent release builder and artifact.
  Release automation now produces only the complete `HMB_GP_Production.zip`.

## 0.5.12 - 2026-08-05

- Introduced the external Agent-policy distribution path that is now enforced
  as the signed server-only contract. Policy artifacts are not installation or
  release-package members of the client library.
- Kept only public signature-verification material in the client; no private
  signing key, decryption key, or API key was added to release artifacts.

## 0.5.11 - 2026-08-05

- Changed `HMBPromptLibrary` image rows to one image-level Sub Type control,
  regardless of how many Color Pick/video bindings the image has. The repeated
  blank Sub Type selectors below the primary selector are no longer rendered.
- Migrated legacy per-binding Sub Type values deterministically: the verified
  registered Sub Type, otherwise the first image Sub Type, is shared across all
  Color Pick/video bindings in both widget and Python normalization. Independent
  Color Pick values, video slots, and Range addresses remain unchanged.
- Moved the compact Range row below expanded left-side content when a Custom Sub
  Type input or Asset ID line is visible, preventing those fields from
  overlapping the Range track.

## 0.5.10 - 2026-08-05

- Changed only the initial value of `Generate Audio` on a newly added
  `HMB Seedance Generation` node from `True` to `False`.
- The toggle remains user-selectable, and an explicitly saved `True` or `False`
  value on an existing workflow is not overridden. All other generation,
  media, upload, polling, output, and usage-accounting behavior is unchanged.

## 0.5.9 - 2026-08-05

- Made selected-video drag ordering in `HMBVideoPickerLibrary` resilient to the
  host canvas event lifecycle. Moving the fourth selected card onto the first
  now commits the complete `@video4 -> @video1` reorder without deselecting and
  rebuilding the selection, and the synchronized `PICKER_OUT`/`VIDEO_OUT`
  snapshot follows that order.
- Replaced the existing HMB Seedance node's three visible scalar video inputs
  with one public ordered `Reference Videos` list. Connect
  `HMBVideoPickerLibrary.VIDEO_OUT` once; the Picker selection order is carried
  unchanged into the Seedance payload. The three scalar parameters remain
  hidden as saved-workflow fallbacks and are used only when the new list is
  empty.
- Preserved the provider limit of three reference videos. Four or more list
  items fail before local-video publication or the billable create-task POST;
  the input is never truncated or renumbered.
- Removed the duplicate result connector while retaining one preview:
  `video_url` is property/preview-only and `VIDEO_OUT` is the sole graph output,
  with both still receiving the same downloaded local artifact.
- Kept the existing node identity, models, Standard 4K, image/audio handling,
  local-video upload choices, one-POST safety, recovery, download, and hidden
  usage accounting unchanged.

## 0.5.8 - 2026-08-05

- Locked the Prompt image-row `+` button whenever `IMAGE_ASSET_IN` is connected.
  The disabled button explains that Image Asset Library owns the visible image
  rows, preventing a manual row from appearing briefly before synchronization
  removes it.
- Added the same fail-closed condition to the click handler so a stale rendered
  button or forced click cannot append a manual image row during the connected
  state. Disconnecting Image Asset immediately restores the existing Prompt-only
  add behavior and maximum-image limit.
- Preserved Asset-managed row editing, dormant manual-row restoration, Prompt
  output, Picker combinations, and all Seedance generation behavior from 0.5.7.

## 0.5.7 - 2026-08-05

- Restored the existing HMB Seedance generator's editor-facing reference-image
  input to one ordered `list[str]` port. Connect Image Asset Library
  `Video Generation Out` to `Reference Images` with one wire; the selected
  library order is preserved through Ark payload construction.
- Retained the nine-image fail-closed limit. An Image Asset Library selection
  of ten or more images stops before the billable create-task POST instead of
  being truncated or renumbered.
- Kept the current render-test surface unchanged: Standard/Fast/Mini models,
  Standard 4K, three independent video inputs, audio references, local-video
  upload choices, task recovery, local MP4 output, and hidden usage accounting
  all remain as in 0.5.6.
- Saved workflows using generated `reference_images_ParameterListUniqueParamID_*`
  child ports must reconnect the Image Asset Library list output once to the
  new `Reference Images` port. The node file, class, display name, and generation
  transport are unchanged.

## 0.5.6 - 2026-08-05

- Introduced a temporary client-side usage-accounting experiment. It was fully
  retired in 0.5.32 in favor of authenticated Broker-side usage, quota, and
  accounting and is no longer present in source or release packages.

## 0.5.5 - 2026-08-05

- Added `4k` to the resolution selector of the existing HMB Seedance Generation
  node without changing its saved-workflow ports or
  default `720p` value.
- Enabled `resolution: "4k"` only for the full
  `doubao-seedance-2-0-260128` model. Fast and Mini remain fail-closed at
  `720p`, and invalid saved model/resolution combinations stop before the
  billable create-task POST.

## 0.5.4 - 2026-08-04

- Added `Volcengine TOS` as a selectable local-reference-video upload service
  inside the existing HMB Seedance node; no second generator was introduced.
- Added private-bucket upload with randomized temporary object keys, 24-hour
  signed HTTPS URLs, best-effort cleanup, and the existing 30-minute retention
  window for ambiguous task submissions.
- Registered `TOS_ACCESS_KEY_ID`, `TOS_SECRET_ACCESS_KEY`, and `TOS_BUCKET_NAME`
  as Griptape Secrets. TOS endpoints are restricted to official public HTTPS
  hosts and the official `tos==2.9.2` SDK is pinned and declared in the SBOM.
- Preserved the existing upload service as the default so installed workflows
  and currently working renders do not silently change behavior.

## 0.5.3 - 2026-08-04

- Removed the duplicate result player from the existing HMB Seedance node.
  `video_url` remains the single preview while `VIDEO_OUT` stays a connector-only
  alias of the same `VideoUrlArtifact`.
- Moved `generation_id` and `generation_status` into the Status group and added
  the Standard-style `Refresh / Retrieve Result` control. Refresh uses GET only
  to retrieve a known task or show recent candidates after an ambiguous POST;
  it never submits or automatically selects a task.
- Enforced the no-retry rule for every non-GET request inside the HTTP transport,
  widened ambiguous POST handling to all HTTPX request errors, exposed only a
  safe error type/phase, and raised the create-response timeout to 300 seconds.
- Added `submission_unknown` handling. Local reference-video uploads are retained
  for up to 30 minutes after an ambiguous POST, preventing immediate cleanup from
  racing a task that Ark may already have accepted.

## 0.5.2 - 2026-08-04

- Fixed local MP4 references in the existing `HMB Seedance Generation` node
  without adding or replacing a generator. Local videos are
  lazily uploaded to Griptape Cloud only when needed, submitted to Volcengine as
  signed HTTPS references, and removed after success, failure, timeout, or local
  cancellation.
- Added `Auto Publish Local Videos`, `GT_CLOUD_API_KEY`, and the optional
  `GT_CLOUD_BUCKET_ID`. Public HTTPS and Volcengine `asset://` references bypass
  the upload path, Resume Task ID never republishes media, and workflow input
  values are not rewritten.

## 0.5.1 - 2026-08-04

- Restored the installed Standard Seedance 2.0 media-input surface on the
  existing HMB generator: `reference_images` is now a Standard-compatible
  `ParameterList`, and videos use the independent `reference_video_1`,
  `reference_video_2`, and `reference_video_3` scalar ports in order.
- The former HMB `VIDEO_REFERENCES` list is hidden as a serialized-workflow
  migration input rather than exposed as the new public video contract.
- Griptape project-relative media paths such as `inputs\\...` now resolve through
  the active project workspace. Local video still fails before task creation
  with the required public-URL/`asset://` guidance instead of a false file-not-found
  error.

## 0.5.0 - 2026-08-04

- Upgraded the existing `HMBSeedanceGeneration` node in place from a
  Standard/BytePlus wrapper to the official Volcengine Ark asynchronous task
  API. The file, class, display name, and established HMB input/output names are
  retained, so no second generator node is introduced.
- Added direct create, status polling, immediate signed-result download, local
  project MP4 persistence, cooperative local cancellation, bounded GET/download
  retries, and `VIDEO_OUT` as an alias of the established `video_url` artifact.
  Task-creation POST requests are deliberately not retried to avoid duplicate
  billable generations when submission outcome is uncertain.
- Added `Resume Task ID` so timeouts, cancellation, download failures, and save
  failures can continue an accepted provider task without another billable POST.
  Downloads now stream under a one-gigabyte cap, do not receive Ark auth, and
  validate every DNS result and redirect hop against private-network SSRF.
- Added Standard, Fast, and Mini `doubao-seedance-*` mappings and pre-submit
  validation for the official 9 image / 3 video / 3 audio limits, duration,
  ratio, model-specific resolution, request size, and audio/media combinations.
  Local images and MP3/WAV audio can be encoded; local video fails before billing
  because Ark requires a public URL or `asset://` reference.
- Uses the Volcengine CN fail-closed resolution ceiling of 1080p rather than the
  separate BytePlus 4K capability. The `priority` field is emitted only for the
  full model and is omitted for Fast/Mini under the strict Ark schema.
- The retired direct-provider credential experiment added `httpx==0.28.1` as a
  pinned direct dependency. Secret-bearing fields are redacted from diagnostics
  and output.

## 0.4.21 - 2026-08-04

- Video Picker cards now keep their thumbnails static. The centered card button
  sends that asset to the main Preview and toggles play/pause there, eliminating
  duplicate thumbnail decoding and playback work.
- The entire lower information area now selects or deselects a card. Selected
  cards use a thicker, brighter neon outline; delete remains at the upper-right,
  and dragging selected cards updates the visible `@video1..@videoN` order.
- Catalog deletion no longer leaves `PYTHON_COMMAND_RECEIVED` as a permanent
  busy stage. Deleting the active preview pauses it and advances to a valid next
  preview, running operations reject delayed deletion without cancellation, and
  repeated deletion is an idempotent acknowledgement instead of a node-wide
  failure.
- Snapshot results now use stable IDs and an ordered ten-item history instead of
  mutable `@video` positions. A completed Snapshot opens immediately in the same
  viewport as Video, the title switches between `(Snapshot)` and `(Video)`, the
  left/right controls navigate Snapshot history, and the center control alone
  plays or pauses Video with `▶` / `Ⅱ`. The redundant local `Open` control is
  removed; card `Load` remains the single MP4 import path.

## 0.4.20 - 2026-08-04

- Video Picker freezes the four accepted Generate choices through final catalog
  publication. A validated Original is appended with Mask, Depth, and Motion
  Guide when all four were checked; an Original render or immutable snapshot
  failure is terminal instead of silently publishing an incomplete three-card
  result.
- Current-cut thumbnails now toggle inline play and pause with `▶` / `Ⅱ`
  feedback without creating a playback outline. Clicking a card title alone
  selects or deselects it and controls the selection border. The redundant
  Select/Deselect footer is removed, cards end after their metadata, and delete
  moves to the upper-right corner. The bottom video-section resize grip is
  visually hidden while its existing drag-resize hit area and behavior remain.
- The MP4 history action is now `Load` in English and `검색` in Korean, with a
  search icon and the same primary color treatment as READ. Regression and
  release gates cover the four-output orchestration and revised card controls.

## 0.4.19 - 2026-08-04

- Video Picker generation is append-only: every validated Original, Mask,
  Depth, or Motion Guide result receives a new stable video UID and unique
  catalog file instead of replacing a role/slot. The current-cut history also
  imports external MP4 files, previews them in the main viewport, deletes
  individual catalog records without deleting media, and keeps more than ten
  assets available for later selection.
- Up to ten selected cards follow the visible left-to-right, top-to-bottom
  order and can be reordered by drag-and-drop. Selection order alone creates
  transient `@video1..@videoN`; deleting or deselecting an item compacts those
  temporary tokens while all remaining stable identities stay unchanged.
- Video Picker media now reaches generators through one ordered `VIDEO_OUT`
  `list[str]` connection, paired with `PICKER_OUT` Prompt metadata. The public
  generator video surface is one `VIDEO_REFERENCES` list accepting at most ten
  items in exact Picker order; fixed per-video wiring is not part of the new
  contract.
- The native Seedance 2.0 adapter converts zero or one list item to its verified
  scalar `reference_video_1` field. Multiple videos fail explicitly unless the
  installed native field itself advertises `list[str]`, preventing silent
  first-item fallback while keeping the transport ready for a verified
  Seedance 2.5 multi-video implementation.

## 0.4.18 - 2026-08-03

- The Video Picker no longer renders a bottom status footer or a floating red
  warning overlay. Status, warning, success, and failure notifications are
  collected in the bounded Activity Log; error rows use red text and long Maya
  path diagnostics cannot expand or obscure the node.
- The no-Color-assignment auxiliary scope now admits only concrete `mesh` and
  `nurbsSurface` shapes to Depth. Controller curves, locators, and other
  unsupported drawables are excluded before shader assignment; their compact
  count is available to the UI while full type/path evidence remains in the
  on-disk sidecar and Maya diagnostic log.
- Motion Guide keeps frame-by-frame `motion_frames` evidence in its sidecar but
  removes that large array from retained node state and `PICKER_OUT`. Compact
  profile, provenance, validation, target, landmark, channel, and driver counts
  remain available to downstream consumers without multi-megabyte WebSocket
  state updates.
- Original now applies a capture-only mouth-card inner patch when an authored
  alpha card proves the exact 49-vertex/84-edge/36-face grid, inner UV coverage,
  and resolved texture-alpha bounds. The transparent outer 20 faces are removed
  only for the current frame and the source visibility is restored immediately.
  Depth takes the simpler fail-closed policy requested for production: every
  image-style mouth alpha card is removed before range analysis and shader
  assignment and is hidden on a temporary Depth-only display layer.
- The isolated runner remains parse-gated against Python 3.11 for Maya 2026.
  Regression coverage now locks the surface-only Depth scope, compact UI
  diagnostics, sidecar-only Motion frame detail, and log-only notification UI.

## 0.4.17 - 2026-08-03

- Depth advances to `hmb_camera_space_depth_v7` and preserves authored,
  resolvable cutout alpha through its temporary camera-space grayscale shader
  assignment. The shared viewport preparation also skips Smooth Preview on
  alpha cards, preventing textured mouth and eye cards from becoming opaque
  rectangles or exposing their smoothed cage boundary. Capture, source-plug,
  verification, ambiguity, and unsupported counts are recorded in the audit;
  ambiguous or unsupported cutout graphs fail closed.
- Motion Guide advances to `hmb_target_neutral_motion_guide_v5`. When target
  delta landmarks do not provide an eyelid region, bounded topology from
  render-scope, non-intermediate, deformed, authored-visible semantic eye and
  eyelid meshes supplies real surface vertices and edges. Alpha-driven cards
  remain excluded, keyed numeric controls remain provenance-only, and raw rig
  curves receive no raster authority.
- Motion Guide v4 is retained only as a legacy cleanup/diagnostic identifier;
  compatible typed-media recognition, Prompt auto-classification, and newly
  generated companion authority require v5. Motion Guide v2 and v3 remain
  fully retired.
- The release gate now parses the isolated Maya runner with Python 3.11
  grammar, matching Maya 2026's embedded Python line. Maya command/API use is
  kept free of a 2027-only runtime branch; live Jett validation for this build
  was performed in Maya 2027 because Maya 2026 was not installed locally.
- Synchronized package, manifest, SBOM, operator-guide, Widget, Prompt, Picker,
  release-gate, and regression surfaces to release 0.4.17, Depth v7, and
  Motion Guide v5.

## 0.4.16 - 2026-08-03

- Griptape project publication now passes an actual `bytes` payload to the
  0.93 engine instead of an `mmap` buffer. This fixes the cross-PC
  `write() argument must be str, not mmap.mmap` failure that left Color only
  scene-local and removed otherwise valid Depth and Motion Guide outputs.
- Depth validation now scans every full-resolution frame. GPU/driver channel
  drift of at most two 8-bit levels is converted to exact gray8 using the RGB
  channel median before FFmpeg encoding; larger chroma still fails closed with
  the frame path, pixel count, maximum spread, coordinate, and sample RGB.
- Maya Depth capture now creates fresh grayscale shader buckets and explicitly
  disables the renderer output transform used by `ogsRender`. Release gates
  cover the strict Griptape payload type, Depth raster contract, Motion Guide,
  and the Maya-free renderer contract.

## 0.4.15 - 2026-08-03

- Image Asset now resolves one authoritative selected-media snapshot for both
  `ASSET_OUT` and `Video Generation Out`. A selected row whose media cannot be
  resolved is omitted from both branches, the remaining rows are packed in the
  same order, and the missing `source_uid` stays visible in diagnostics instead
  of allowing Prompt `@imageN` and generator fan-out numbering to diverge.
- While `ASSET_IN` is connected, only resolved selected Asset-managed rows own
  active Prompt image slots. Manual rows sleep in a dedicated cache, deselected
  managed rows keep their authored Target, Role, Color Pick, and Range by exact
  `source_uid`, removed references become tombstones, and disconnect restores
  independent/manual operation.
- Video Picker now exposes four inert output selections in canonical order:
  Original, Mask, Depth, and Motion Guide. A checkbox never starts Maya or
  FFmpeg; only `Generate Playblast` executes work. Successful checked outputs
  are published once, packed without gaps in that order, while unchecked media
  is not exposed and unrelated manual slots remain recoverable.
- Packed Picker provenance now links Depth and Motion Guide to the actual Mask
  slot and bundle identity. When Mask is not selected, an explicitly zero-linked
  typed output remains valid from its own non-empty identity; missing, conflicting,
  or mismatched provenance fails closed without deleting the readable video.

## 0.4.14 - 2026-08-03

- Added the original HMB Seedance generation node as a thin extension of the
  registered Standard Library video-generation node. It replaces only the
  editor-facing `reference_images` `ParameterList` with one compatible ordered
  `list[...]` input, allowing `HMBImageAssetLibrary` Video Generation Out to
  connect with a single wire.
- Seedance model selection, prompt handling, image normalization and limits,
  video/audio references, generation settings, authentication, provider
  payloads, uploads, polling, downloads, status, and outputs remain inherited
  from the native Standard Library implementation. Missing or changed native
  contracts fail explicitly; no copied generator fallback is included.
- Preserved the native Griptape/Customer API Key Provider control across the
  HMB subclass-name boundary by reusing the Standard Library provider component
  and original Seedance lookup key. The HMB manifest does not pin a copied model
  catalog or model-usage snapshot; invocation permission keys are resolved from
  the live registered Standard Seedance catalog.
- Added native-extension regressions for dependency discovery, parameter
  replacement, reference order and duplicates, 0/1/9/10-image validation,
  prompt preservation, and parent payload/process delegation.
- While Image Asset remains connected to Prompt, selection add/remove/reorder
  now strictly mirrors Asset-managed Prompt rows and the generator media order.
  References to removed rows become non-binding deselection markers; unrelated
  manual Prompt rows and the explicit disconnect-preservation behavior remain.

## 0.4.13 — 2026-08-03

- Saved Picker workflows now adopt `HMB_PICKER_STATE` during Griptape's `initial_setup` path, restoring the saved active slot count, VIDEO1_OUT through VIDEO3_OUT visibility, and their output values even though the engine intentionally skips `after_value_set()` during workflow hydration.
- Restored VIDEO output handles now trigger one guarded React Flow node remeasurement after all saved ports are present. The temporary width pulse spans a complete render cycle and restores the exact original width, so VIDEO2_OUT and VIDEO3_OUT connections reopen on their real ports without requiring a fourth slot to be added. Native hidden-row collapse also stops before any ancestor that owns Picker output handles.

## 0.4.12 — 2026-08-03

- Prompt Image Source Binding now groups Asset-authoritative Name, Main Type, and registered Sub Type consecutively before the editable Target. Header, row, tab, responsive, and compact Range placement follow the same order, and the locked registered Sub Type shares the existing Asset-authority visual treatment.

## 0.4.11 — 2026-08-03

- External Image Add now requires one existing child Asset Folder, removes Project Root from the destination selector, and copies the original image directly into that selected folder without creating an Asset ID subdirectory. Filename collisions remain non-destructive and manifest failures roll back only the newly copied file.
- Verified Asset In metadata now binds the registered Sub Type to every Prompt binding. Target remains editable, starts from a Main-Type-aware default, and preserves user overrides across refresh and reorder.

## 0.4.10 — 2026-08-03

- Moved the shared image manifest and persistent coordination lock into the dedicated hidden `.json` project-management directory. Existing root-level manifest data remains readable and is migrated to `.json/hmb_image_assets.json` on the next successful manifest write; obsolete root metadata files are then removed on a best-effort basis.
- Excluded `.json` from image scanning and the HMB folder tree while preserving user-created asset folders such as `BG` and `CH`, cross-process locking, atomic manifest writes, and mixed-layout read compatibility during rollout.

## 0.4.9 — 2026-08-03

- Resolved Griptape `{inputs}` and `{outputs}` image references on the server before external asset registration, fixing Add failures for connected `LoadImage` artifacts that carry a portable macro path rather than embedded bytes.
- Registered imports now create a deterministic Windows-safe Asset ID directory below the selected Project Folder and store the original image inside it. Copy/manifest failures roll back the new file and empty directory, and operator documentation now explains the shared `hmb_image_assets.json` manifest and `.hmb_image_assets.lock` coordination file.

## 0.4.8 — 2026-08-03

- Declared `VIDEO1_OUT` through `VIDEO5_OUT` as a stable node schema during construction so saved auxiliary output details, values, and connections can be restored before Picker state hydration. Inactive slots now remain registered, hidden, and cleared to `None` instead of being removed, preventing `VIDEO2_OUT`/`VIDEO3_OUT` reload failures in shared and orchestrated runtimes.
- Added fresh-node, slot expansion/contraction, stable ordering, and release-gate regressions for the persistent video-output contract.

## 0.4.7 — 2026-08-03

- Retired Motion Guide v2/v3 typed authority from Picker, Prompt, and Widget runtime paths; only the current `hmb_target_neutral_motion_guide_v4` contract is accepted for active Motion Guide slots.
- Updated public library tags, descriptions, operator guidance, release checks, and rejection regressions to Motion Guide v4 without changing connection policy or the four libraries' independent-use contract.
- Preserved Depth v1-v5 identifiers strictly for safe cleanup and replacement of companions saved by older workflows; historical changelog, schema, and UI-layout migration versions remain intact.

## 0.4.6 — 2026-08-02

- Depth v6 now admits normalization candidates through deterministic Maya API mesh vertex and polygon-center screen/clip samples, then applies Actor 1st/99th percentiles or the generic 95th-percentile fallback with a linear camera-distance curve. Offscreen Actor bboxes no longer consume the signal range; all assigned set/context geometry remains rendered, API-unavailable cases record conservative bbox fallback evidence, and output continues to reserve 0.9–1.0 as safety margin. Sidecar foreground, context, screen-rejected, and Actor-priority role-excluded representative counts are disjoint outcomes whose sum is the total representative count.
- Motion Guide v4 localizes bilateral brow, eyelid, mouth, and jaw anchors from read-only Blend Shape target deltas. Missing side anchors require two agreeing authored bilateral pairs; jaw sides use the derived semantic face axis, and a missing jaw center first tries a bounded same-surface midpoint between left/right jaw anchors. If midpoint and direct mouth-center axis candidates fail, muzzle-like faces may retain the bilateral jaw midpoint's surface profile and lower it only by the agreeing left/right mouth-to-jaw progress. Profile centrality is measured from the actual L/R jaw midpoint rather than a potentially asymmetric mouth:center vertex. Every surface vertex inside the unchanged 0.06-diagonal snap sphere is filtered by the existing non-source, downward, jaw-center, and span gates before the best eligible vertex is chosen deterministically by distance then vertex index; zero eligible candidates remains fail-closed. Candidate counts, score, and accepted or rejected metrics are retained in the audit. Facial rasterization requires both endpoints of one declared face edge to pass front-facing and first-hit visibility checks; rig curves are never rendered.
- Motion Guide generation now uses frame-local visibility caching, root/shape short-circuiting, once-per-frame occluder filtering, projection-before-ray selection, and faster lossless PNG staging. Body-joint continuity remains unchanged.

## 0.4.5 — 2026-08-02

- Removed the redundant Color Assignment Target/APPLY row; clicking a color chip continues to assign it immediately to the selected Outliner target.
- Protected all four HMB library nodes from Backspace/Delete removal while preserving text editing, Prompt frame controls, and the native top-toolbar trash action.

## 0.4.4 — 2026-08-02

- Motion Guide v3 adds final evaluated Blend Shape weight values and connected numeric NURBS-curve controller plug provenance to Sidecar schema v2 without rendering raw controller-curve geometry.
- A compact face raster now uses only surface-pinned brow, eyelid, mouth, and jaw landmarks. Landmarks are emitted only when their deformed surface vertex is front-facing and passes the active-camera first-hit visibility test; unknown aliases remain raw Sidecar data and never become guessed raster semantics.
- Motion Guide v2 remains recognized as legacy metadata while newly generated companions require the v3 profile and schema-v2 contract. Core body motion, source timing, camera inheritance, optional-companion independence, and zero appearance authority remain unchanged.

## 0.4.3 — 2026-08-02

- Depth v5 now derives one fixed complete-sequence range from the same visible per-shape representative camera depths used for shader assignment, spans the full usable 0.0–0.9 palette, and reserves 0.9–1.0 as a near-camera approximation margin.
- Motion Guide v2 now prefers target-local weighted skin influences, blocks reference-wide borrowing for object/background targets, confines Character fallback to the target reference/namespace, filters facial/IK/FK/twist/helper/accessory detail, de-duplicates display skeletons, verifies target-shape visibility, and publishes stable joint identifiers.
- Preserved source-scene immutability, shader-only Depth generation, exact Color timing/camera inheritance, and independent optional companion publication.

## 0.4.2 — 2026-08-02

- Prompt의 네 가지 정식 모드(단독, +Asset, +Picker, +Asset+Picker)를 명시하고 두 입력을 임의의 읽을 수 있는 연결값에 개방
- HMB Agent 정책 활성화를 정확한 등록 클래스의 `HMBPromptLibrary.PROMPT_OUT -> HMBAgentLibrary.prompt` 단일 직접 연결로 제한
- 복사된 HMB 문구, Asset/Picker 직접 연결, 릴레이, 동일 이름·위조 메타데이터 노드가 Agent 정책을 대신 활성화하지 못하도록 출처 검증 추가
- Prompt 연결값의 알 수 없는 필드, 중복·잘못된 video slot, 이미지 50개·비디오 5개 초과 행을 삭제하거나 기존 행을 대체하지 않고 일반 사용자 의도로 보존
- 15개 라이브러리 조합 및 `OO=true / OX·XO·XX=false` 부모 경계 회귀검사 추가

## 0.4.1 — 2026-08-02

- 격리된 custom-library import 환경에서도 등록된 형제 Standard Library manifest를 검증해 Agent를 자동 로드
- 홈 디렉터리 광역 검색 없이 정확한 `griptape-nodes-library-standard` 경로만 허용

## 0.4.0 — 2026-08-02

- 연결을 편집 선행조건으로 만들던 Prompt UI 정책 제거
- HMB 정책 payload를 RSA-3072 공개키 서명 envelope로 변경
- 변조 정책의 native Agent fail-open 및 실행 후 평문 정책 제거
- Agent·Image 입력의 순환/과도한 중첩 방어
- Video/Maya 출력 경로, 작업 잠금, 실행 파일 출처와 대용량 처리 강화
- Image manifest를 persistent OS/SMB byte-range lock으로 변경
- 손상 이미지 등록 차단 및 import batch 예산 추가
- 키보드·모달·반응형 UI와 한/영 접근성 개선
- 재현 가능한 ZIP, release manifest, SHA256SUMS와 SBOM 추가

## 0.3.11 — 2026-08-02

- 기본 프로젝트 catalog를 `\\fin-rcomp1\Composite_Team\projects_AI`로 변경
