# Changelog

## 0.6.22 - 2026-08-12

- Recover the paired Prompt snapshot when Griptape `initial_setup` hydrates
  persisted state without invoking the Prompt lifecycle hook, leaving the
  constructor-time cache stale.
- Keep `PROMPT_OUT` as the user-readable sectioned document and normalize only
  terminal LF transport differences during exact visible-prompt matching.
- Rebuild the visible document and private Agent snapshot atomically from the
  same current source state when recovery is safe, while preserving fail-closed
  pairing for genuine state mismatches.
- Add safe stage-code logging for source-contract failures without exposing
  private prompt content, structured payloads, or internal exception details.
- Propagate late Video Picker output through the real retained-mode graph so
  `PICKER_OUT -> PICKER_IN -> PROMPT_OUT -> Agent` updates immediately, while
  discarding superseded re-entrant publications instead of restoring stale
  values.
- Restore the complete pre-connection manual video state when Picker is
  disconnected, including video rows, image bindings, Frame Range state,
  text references, and textarea sizing, while retaining edits made during the
  connection and dormant Picker settings for a later reconnect.
- Lock both add and delete controls for video rows while Picker owns their
  order, and avoid rebuilding unchanged Main Type/Sub Type option DOM so
  selection changes no longer flicker.

## 0.6.21 - 2026-08-12

- Keep Frame Range optional for `FX Reference` and `Timing / Edit Reference`:
  Range OFF or unset uses the full source, a valid Range ON selection takes
  temporal priority, and an invalid Range ON selection leaves only that image
  binding unresolved instead of blocking the Agent run.
- Clarify the protected Agent error so an absent role, emitter cue, or Frame
  Range is not described as a required input.
- Lock the Video Source `+` button while `PICKER_IN` is connected, matching the
  existing Image Asset connection lock, and restore it immediately on Picker
  disconnect.

## 0.6.20 - 2026-08-12

- Preserve the complete `0.5.74` user-facing feature and UI contract while
  distributing exactly one signed Agent runtime artifact with the Library at
  `resources/agent/hmb_agent_core.dat`.
- Keep `hmb_agent_core.dat` as a signed, compressed integrity artifact. Each
  installed artifact is freshly verified for Agent execution; missing or
  unsigned edits, schema or contract drift, and malformed Behavior 1/2
  structures fail closed.
- Restore the concise, user-readable Target Generator, Image Source, Image
  Role, Replacement Binding, and Video Source view on `PROMPT_OUT`, while the
  directly connected Agent consumes an atomically paired, private, closed
  JOB/FX/USER machine envelope from the same Prompt state. USER DESCRIPTION
  contains only the five fields directly authored in the Prompt UI; connected
  transport metadata and policy prose remain excluded from the machine input.
- Apply the reviewed v4.1 FX Reference, Timing/Edit, exact emitter point, and
  Range ON contract internally without changing existing controls, ports,
  defaults, layouts, or saved-state behavior.
- Activate Video Source Binding immediately on the first populated `PICKER_IN`
  update by preventing a delayed pre-connection widget echo from restoring the
  older empty state. Keep the Frame Range row at one stable vertical position
  for one or multiple Color Picks, expanding it only when a visible Custom
  Scope input actually requires the extra row height.
- Keep the four shared libraries generator-neutral and register only the final
  `HMBSeedanceGeneration` module/class name.
- Harden non-billable output preflight, cancellation handling, atomic MP4
  publication, and bounded `ftyp`/`moov`/`mdat` validation without changing the
  existing Generator UI or normal job flow.
- Exclude every additional `.dat` and every English/Korean policy document from
  GitHub release packages, including nested archives; Korean review files
  remain local-only.

## 0.5.74 - 2026-08-11

- Reduced `HMBPromptLibrary.PROMPT_OUT` to the five user-verifiable Target Generator, Image Source, Image Role, Replacement Binding, and Video Source sections. Internal interpretation, authority, alignment, and multi-video policy prose is no longer serialized; the signed Agent v4 policy remains unchanged and runtime-only.
- Removed the complete `USER DESCRIPTION DATA (JSON)` block and connected-source diagnostic fallback payloads from public Prompt output, preventing local paths, scene identifiers, render reports, and transport diagnostics from entering Agent conversation input.
- Corrected terminal Seedance failure reporting so an unconfirmed provider submission is not described as a render that may still continue, while preserving the existing task ID and fail-closed no-resubmit contract.

## 0.5.73 - 2026-08-11

- Corrected the v0.5.72 middle-button interpretation: the ImageAsset viewport no longer captures or scrolls its own grid during a middle-button drag.
- Kept wheel rotation as local image-list scrolling while passing middle-button pointer and mouse gestures through to Griptape's native whole-canvas pan, including at high canvas zoom.
- Preserved left-click image selection, the v0.5.71 manifest-poll flicker fix, and non-middle interaction isolation inside the red asset viewport.

## 0.5.72 - 2026-08-11

- Restored hold-to-drag middle-button panning inside the ImageAsset viewport by isolating React Flow's compatibility `mousedown` before it can claim the gesture.
- Kept an active local pan across pointer-capture loss and legacy embedded-WebView mouse streams, with bounded window-level cleanup on release, cancel, blur, or widget teardown.
- Preserved the v0.5.71 flicker fix, local wheel scrolling, image selection behavior, and canvas zoom/pan outside the red asset viewport.

## 0.5.71 - 2026-08-11

- Prevented the Image Asset Library's lightweight 10-12 second manifest poll
  echo from being normalized as an empty catalog and remounting the full asset
  grid. Unchanged polls now preserve cards, loaded thumbnails, selection,
  focus, and scroll position; real manifest changes still remount once.
- Added vertical wheel scrolling and middle-button drag panning only inside the
  main asset viewport. Griptape canvas zoom remains unchanged everywhere
  outside that viewport, and left-click selection plus tray ordering are
  preserved.
- Added deterministic regressions for raw string/object poll echoes, canonical
  authority updates, callback replacement, pointer capture failure and cleanup,
  local wheel isolation, and middle-button movement.

## 0.5.70 - 2026-08-11

- Activated signed Agent policy `2026-08-11.agent-shot-quality.v4` with its
  matching runtime, Prompt, release-builder, CI, documentation, and regression
  identities. The bundled policy remains the only production policy source.
- Added pre-generation policy boundaries for Actor 7, Ghost 3, Pattern 4,
  scale authority, character-color continuity, children's TV readability, and
  temporal identity stability. The policy explicitly does not claim generated
  video inspection, defect grading, approval, rejection, or regeneration.
- Added a signed-payload semantic regression to the release workflow and the
  bounded 26-file CI validation archive. It verifies v4 meaning without
  exposing a private signing key or introducing an external policy path.

## 0.5.33 - 2026-08-11

- Restored the established team rollout contract: approved changes reach the
  public GitHub `main` branch, and team members apply them with Griptape's
  Git-backed Library Update button.
- Bumped the library version so existing Git installations can discover this
  update, and documented that the registered Library must retain `.git`, its
  GitHub `origin`, and the `main` tracking branch.
- Retired ZIP replacement, copied-folder, network-drive, and SMB rollout as
  installation paths. Generated archives remain bounded CI validation outputs,
  are not installation packages, and must not replace a registered Git Library.

## 0.5.32 - 2026-08-10

- Removed the retired client-side Seedance usage ledger, its local retry queue,
  and every runtime dependency on the temporary Composite Team source share.
  Authenticated FN AI Broker generation is now the sole production usage,
  quota, and accounting boundary.
- Kept the signed Agent policy inside the installable library and retained its
  bounded signature, version, contract, and payload-integrity validation. No
  policy share or policy-path environment configuration is required.
- Added source and release gates that reject the retired share marker, legacy
  usage-ledger symbols, and stale copies in a team package.

## 0.5.31 - 2026-08-10

- Send FN AI Broker requests directly, without inheriting system or environment
  proxies, while leaving all non-Broker internet traffic unchanged.
- Retry bounded device-authorization start transport failures and recover
  transient token-polling failures on the same device request without opening
  duplicate browser windows or creating duplicate render jobs.
- Preserve valid per-user DPAPI tokens across transport failures and add
  credential-safe diagnostics for Broker connection failures.

## 0.5.30 - 2026-08-10

- Display FN AI Broker `queued` and `running` refresh results as neutral
  in-progress status instead of a false warning, while preserving warnings for
  actual terminal failures and connection errors.

## 0.5.29 - 2026-08-09

- Established GitHub and GitHub Releases as the permanent public team
  distribution channel. Repository visibility is no longer treated as a
  security boundary; release audits continue to reject credentials, tokens,
  private signing keys, and non-public media.
- Removed Image Asset selection cadence stalls by updating only the clicked
  card, retaining keyed tray nodes and decoded thumbnails, and moving canonical
  state publication after the immediate visual response.
- Replaced full-catalog background manifest polling with a lightweight identity
  probe and reused bounded verified project/import resolutions across ordinary
  selection changes. Explicit execution still performs fresh validation.

## 0.5.28 - 2026-08-09

- Advanced the manifest, Python package, README, SBOM, and release-security
  contract to `0.5.28` so Griptape Nodes update discovery no longer treats the
  validated world-projection/team release as the already installed `0.5.27`.
- Republished the exact validated four-library runtime and Video Picker render
  behavior without changing node types, saved state, ports, Broker payloads,
  Maya output roles, or signed Agent policy identity.

## 0.5.27 - 2026-08-08

- Split the Video Picker color palette into Actor 7, shared Ghost 3, and
  Object-pattern 4 rows. Existing marker names, repeat behavior, saved
  bindings, and solid-color Lambert rendering remain unchanged.
- Replaced the four Object patterns' frame-locked screen-space compositor with
  temporary UV-independent Maya projection graphs. Floor Grid uses top-planar
  XZ projection while Direction Checker, Sky Grid, and Position Pattern use
  triplanar XYZ projection; all four follow the selected background root and
  retain camera perspective without modifying or saving authored UVs.
- Fixed the projected pattern density at 3x the 15-unit baseline (5 Maya world
  units per cell), with first-output-frame anchoring, root scale compensation,
  cutout-alpha preservation, and fail-closed runner metadata validation.
- Exposed the shared Ghost 3 colors to Prompt and Image Asset character
  sources while keeping object/background choices at Ghost 3 plus Pattern 4
  and preserving the unique 14-choice Custom order.
- Compacted Video Picker FPS, format, and Maya information into one settings
  row and reassigned the recovered 68 px to the initial Current Cut Videos
  area, with a one-time saved-layout migration.
- Added one-dialog ordered MP4 multi-selection on Windows and one atomic batch
  import, preserving the 10-active-video limit while retaining overflow files
  in the catalog.
- Made Generate carry the exact visible camera, Color Pick, visibility, output
  role, and resolution snapshot; terminal cleanup now completes before the
  ready state is published, so immediate recoloring and consecutive renders
  cannot strand the picker in a stale busy state.
- Added strict Redshift proxy-placeholder Depth verification for drawable proxy
  meshes that accept the expected whole-object shading group but do not expose
  an `MFnMesh`, while keeping ordinary mesh and per-face checks fail-closed.
- Renamed the public node file to `HMBSeedanceGeneration.py` and the Griptape
  palette label to `HMB Seedance Generation` so future Broker render options are
  not tied to one model version. The legacy serialized node type remains as an
  override-free compatibility wrapper, preserving existing saved workflows.
- Made Image Asset, Video Picker, and Prompt selections paint locally before
  their authoritative host round trip, while preserving the existing state
  schemas, parameter names, saved-workflow format, and Agent connection flow.
- Removed large-grid listener/remount hot paths, cached immutable widget CSS
  and manifest parses with bounded lifetimes, and coalesced repeated Prompt
  output/resize work to eliminate click stalls and visible flicker.
- Published the Image pair, `PICKER_OUT`, and `PROMPT_OUT` explicitly so every
  connected Prompt/Agent consumer receives one coherent current snapshot;
  generation settings and render behavior remain unchanged.
- Added concurrency and no-loss regressions for stale host echoes, IME editing,
  video source switching, command submission guards, output propagation, and
  the complete four-library composition contract.
- Replaced the Seedance node's CGTeamwork token exchange with the Broker's
  one-time browser authorization and Windows DPAPI-protected permanent token.
- Added one stable client request ID and matching idempotency header per render,
  allowing lost responses to recover the same server task without duplicate
  submission or billing.
- Aligned Refresh and terminal-expiry handling with the durable Broker job API;
  Refresh checks only the existing job and never creates a replacement render.
- Added server-contract regressions for device authorization, idempotent retry,
  provisional job aliases, and expired retained results.

## 0.5.26 - 2026-08-08

- Changed only the new Full Seedance 2.0 node default from 4K to the existing
  `1080p` (1K) option. Explicitly saved 4K selections remain supported, and
  the selected value is passed unchanged through Broker validation to
  Volcengine.
- Removed Griptape `process() returned unexpected type: dict` warnings from the
  Image Asset, Video Picker, and Prompt data nodes while preserving their real
  output-parameter payloads.
- Prevented Refresh from overwriting an active Seedance render status while the
  Broker submission is still waiting for its task ID.

- Fixed FN AI Broker HTTP 400 failures caused by embedded reference media.
  Seedance generation requests now share a tested 64 MiB client/server limit;
  ordinary API endpoints retain their 2 MiB limit.
- Aligned media-only Full/Fast/Mini generation, smart duration `-1`, and
  first/last-frame validation across HMB, the Broker schema, and the Volcengine
  payload adapter.
- Added credential-safe HTTP 400/413 classification. Response bodies, provider
  keys, and tokens are never copied into node state or logs.
- Added a real HTTP regression with a Base64 reference payload larger than
  2 MiB, while keeping the billable Volcengine call stubbed.

## 0.5.25 - 2026-08-07

- Expanded the FN AI Broker generation contract to the exact Volcengine
  Seedance 2.0 Full, Fast, and Mini endpoint IDs; arbitrary catalog models and
  non-Volcengine providers remain rejected locally.
- Made Full Seedance 2.0 the default at 4K. Full exposes
  4K/1080p/720p/480p, while Fast and Mini default to 720p and expose only
  720p/480p. Switching models immediately updates and safely coerces the
  resolution selector.
- Kept the collapsed AI Broker panel limited to connection and account state.
  No provider key, masked key characters, registration/update control, usage,
  quota, or credit field is stored or displayed by the node.
- Fixed the client/server request contract so HMB's auxiliary pixel-resolution
  compatibility field is ignored by schema validation while the selected
  Seedance quality remains authoritative, preventing the pre-provider HTTP 400.

## 0.5.24 - 2026-08-07

- Aligned HMB's Fast-model Broker request with the server's confirmed successful
  generation contract by including the required pixel `resolution` plus the
  explicit `web_search=false` and `content_filter=true` defaults. Portrait
  ratios use `720x1280`; all other supported ratios use `1280x720`.
- Fixed the remaining immediate HTTP 400 seen only from HMB clients. Admin
  access logs showed the HMB requests being rejected in roughly 30-40 ms,
  before provider execution or usage recording, while the server-native Fast
  request containing these common fields succeeded.
- Added bounded, allowlisted HTTP 400 classification. Broker response bodies are
  never copied to node state or logs; users receive only a fixed safe category
  for settings, reference media, or model validation.

## 0.5.23 - 2026-08-07

- Matched the Seedance node to the replacement FN AI Broker's verified runtime
  contract. The server currently exposes catalog metadata for Full, Fast, and
  Mini, but only `doubao-seedance-2-0-fast-260128` has the asynchronous video
  generation adapter and a confirmed successful production request.
- Made `Seedance 2.0 Fast` the node default and the only selectable Broker
  model, with its verified 480p/720p resolution choices. Saved workflows that
  still contain Full or Mini now fail locally with an actionable model message
  instead of reaching the server and returning an opaque HTTP 400.
- Added regression coverage for the Fast-only Broker boundary while preserving
  legacy internal payload helpers. No provider key, Broker token, usage, quota,
  or key-registration UI/state was added or exposed.

## 0.5.22 - 2026-08-07

- Changed the default FN AI Broker origin from
  `http://192.168.204.242:8080` to `http://192.168.203.245:8080` after
  confirming the replacement server health, CGTeamwork public-key endpoint,
  and all three Volcengine Seedance 2.0 model definitions.
- Preserved `HMB_AI_BROKER_URL` as the explicit installation override and kept
  the existing strict origin validation and credential boundary unchanged.

## 0.5.21 - 2026-08-07

- Aligned HMB Seedance requests with each FN AI Broker model schema. The full
  and mini models no longer receive Fast-only or unsupported `input_mode`,
  last-frame, expiry, or priority fields, eliminating the HTTP 400 response on
  otherwise valid default requests.
- Added pre-submission validation for model-specific prompt, First/Last Frame,
  Last Frame return, custom expiry, and priority support. Unsupported choices
  now fail locally with a safe explanation before any billable request.
- Added regressions that verify the exact full-model payload, preserve the Fast
  frame contract, and prevent invalid model-field combinations from reaching
  FN AI Broker.

## 0.5.20 - 2026-08-07

- Allowed the current production CGTeamwork origin
  `cgteamwork.funnyflux.kr:443` alongside the legacy internal origin when
  starting FN AI Broker approval, while retaining an exact normalized
  allowlist and rejecting user-info, path, query, fragment, and lookalike-host
  inputs.
- Added regression coverage for both approved CGTeamwork origins and unsafe
  origin variants so `Connect / Refresh` can create the `comp` approval request
  without weakening the credential boundary.

## 0.5.19 - 2026-08-07

- Routed HMB Seedance 2.0 generation, task refresh, resume, and trusted result
  downloads through the authenticated FN AI Broker at the configured server
  origin. Provider API keys remain server-side and are never placed in node
  parameters, outputs, logs, or serialized state.
- Added a collapsed `AI Broker` group directly below Status with connection
  state, account, and one nonblocking `Connect / Refresh` action. Key values,
  key-registration controls, usage, quota, and reset information are absent;
  Broker renders also perform no usage collection or local usage recording.
- Made Picker Depth use Maya-authored visibility plus the Picker eye state
  independently of Color Assignment, and made Mask recoloring replace stale
  duplicate bindings by Maya UUID or exact DAG path.
- Added Broker credential-boundary, async-button, generation/resume/refresh,
  Picker visibility, Depth, and Mask recolor regressions.

## 0.5.18 - 2026-08-06

- Removed the redundant visible `ASSET · Asset ID` helper line beneath Image
  Name in HMBPromptLibrary while preserving Asset ID data, binding authority,
  tooltip diagnostics, and compiled `PROMPT_OUT` behavior.
- Reclaimed the helper line's unused vertical space so frame-range controls no
  longer shift downward merely because an image carries an Asset ID.
- Kept the HMBImageAssetLibrary Add passport and its in-progress text intact
  across asynchronous host/catalog updates. The latest deferred state is
  applied once the dialog is cancelled or submitted instead of remounting its
  live input controls while the user is typing.

## 0.5.17 - 2026-08-06

- Reduced the public `TARGET GENERATOR` preamble to target identification only.
  Detailed production integration defaults are no longer duplicated in the
  compiled user-visible Prompt and remain exclusively enforced by the bundled,
  signed v3 Agent policy.
- Added regressions that reject future policy-detail exposure in public Prompt
  text while confirming the signed local policy remains the runtime authority.

## 0.5.16 - 2026-08-06

- Replaced the Agent policy with signed policy
  `2026-08-06.animation-look-continuity.v3`, contract SHA-256
  `ab5b63a42717293cc097d51bf3048b5309c0ff52644bd0121b3045f6eeadae93`,
  and envelope SHA-256
  `6152355dd51d68da33d4df197e6ac52f2c13b37d9644aa50efd9ba8c2cf13619`.
- Removed external and network-share policy resolution. The Agent now reads and
  verifies only the `resources/agent/hmb_agent_core.dat` installed beside the
  library, with no policy-path environment variable or fallback order.
- Deferred the required team-project `{_index}` output macro until Griptape's
  collision-safe write stage, preventing Seedance generation and Refresh from
  failing before the engine assigns the output index. Other missing macro
  variables and destination errors still fail before task submission.
- Reduced the production ZIP to exactly 25 allowlisted runtime files. The signed
  `.dat` is included; `CHANGELOG.md`, `resources/build_release.py`, policy
  administration scripts, private keys, credentials, tokens, and every other
  `.dat` are excluded. The release audit verifies the exact policy hash and
  source security boundary; release preparation also verifies two identical
  reproducible builds and the complete archive security regression.

## 0.5.15 - 2026-08-06

- Bundled the exact signed Agent policy
  `2026-08-01.goal-final-authority.v2` as the first local policy precursor. Its
  temporary network-precedence experiment was later retired; current releases
  resolve only the signed policy installed inside the library.
- Pinned the bundled envelope to SHA-256
  `94533d84ab914971026f624634c2553a0c7abba298f6dd76242d996ee5c9137f`
  and retained the v2 contract SHA-256
  `a17809e4103628c1b0ab0b96081f6325faf9d16703a5fac57ef7d1eaa7d043bf`.
  Release creation now verifies the RSA signature, policy identity, internal
  field digests, and runtime fallback path before packaging.
- Expanded the complete production ZIP to exactly 26 files: the prior 25-file
  allowlist plus one `resources/agent/hmb_agent_core.dat`. CI and archive
  regressions reject every other `.dat`, private key, credential, token, or
  secret file. No private signing key or API credential is included.

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

- Introduced a temporary external Agent-policy distribution experiment. It was
  fully superseded by the signed bundled-policy contract and is not a runtime,
  installation, or release dependency in the current library.
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
  `HMB Seedance 2.0 Video Generation` node from `True` to `False`.
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

- Added `4k` to the resolution selector of the existing HMB Seedance 2.0
  generator without changing its node identity, saved-workflow ports, or
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

- Fixed local MP4 references in the existing `HMB Seedance 2.0 Video
  Generation` node without adding or replacing a generator. Local videos are
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

- Upgraded the existing HMB Seedance generator node in place from a
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
- Registered `ARK_API_KEY` in Griptape Secrets and added `httpx==0.28.1` as a
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

- Added the predecessor HMB video generator as a thin extension of the
  registered Standard Library video-generation node. The node replaces only the
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
