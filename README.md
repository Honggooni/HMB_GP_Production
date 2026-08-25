# HMB GP Production

Current team release: `v0.6.55`.

Odd patch versions are team releases; even patch versions are local test builds
and must not be published or distributed until promoted to the next odd version.

HMBAgentLibrary keeps Korean authoring input intact inside the private Prompt
contract, but its final video-generator instruction is English-only. Prompt
video snapshots are compiled without re-entering Shot graph mutation, and an
unchanged valid VideoPicker catalog remains ready instead of becoming a false
missing-source failure.

The hidden VideoPicker Shot publication and its Prompt/Seedance inputs use one
strict `dict` contract. Workflows saved by older builds with bounded JSON text
are migrated during hydration; malformed or oversized legacy values are cleared
without being interpreted as media. Prompt keeps accepted user edits across
simultaneous Picker refresh/disconnect, and ImageAsset performs its first
catalog scan outside the node-registration UI callback.

HMBSeedanceGeneration supports Seedance 2.0, 2.0 Fast, and 2.5 through the
authenticated FN AI Broker. Seedance 2.0/2.0 Fast expose the stock `Input Mode`
choices `Text Only`, `First/Last Frame`, and `Multimodal References`. Seedance
2.5 instead exposes the stock `Task` choices, including `Reference to Video`,
`Video Editing`, and `Video Extension`. In `Only`, those operations use the
node's manually authored image, video, audio, and frame references. In a
numbered `Shot`, manual media is preserved but ignored and generation resolves
only the exact same-Shot ImageAsset and VideoPicker publications as 2.0
multimodal reference or 2.5 `Reference to Video`, according to the model.

Seedance 2.5 defaults to 720p, offers optional 1080p 10-bit HEVC, accepts
explicit 4-30 second duration, and supports up to 30 image, 10 video, and 10
audio references, including audio-only input where the selected task permits
it. The HMB 2.5 production profile intentionally omits 480p and smart duration.
It can save verified MP4 or MOV output and, when requested, a separately
verified local PNG last frame; signed result URLs are never persisted. The
existing Seedance 2.0 limits and saved three-port video compatibility contract
remain unchanged. Task-declared 2.5 Reference-to-Video, Editing, Extension,
MOV, and last-frame requests require an exact authenticated Broker capability
contract and fail closed before media upload or billable submission when that
contract is unavailable.

The native video preview reports submission, render, retrieval, download,
verification, cancellation, timeout, failure, and unsupported local MOV
preview states. A completed prior video remains visible while a new task runs,
and the recovery action checks the existing authoritative task without
submitting a duplicate generation.

Shot 1 through Shot 5 may each own an independent Prompt -> Agent -> Seedance
branch and all five Seedance nodes can submit and poll concurrently. The HMB
same-Shot router connects each Agent final-text `output` to the matching
Seedance public `prompt`; both public string ports show their normal connected
color while only the exact cable is visually hidden. `Only` has no managed
Agent-to-Seedance prompt connection, so both ports remain unlit. Griptape's
workflow execution mode must be `parallel` with `max_nodes_in_parallel` set to
at least `5`; this is a local host setting, while any lower Broker/provider
account quota can still queue accepted jobs on the server. To satisfy the
Broker's same-account ingress rule, only the five billable POST starts are
spaced by 1.20 seconds; accepted renders are not serialized.

HMBVideoPickerLibrary opens and reloads in its compact 1400x360 Loader view.
The one-Shot state row is 252px and native node resizing is locked while this
compact view is active; each added Shot grows the node by one complete 180px
loader row plus its 6px gap. An explicit header toggle opens the expanded
authoring surface without resizing or reframing the React Flow workspace, and
the Picker-owned body fills the live node instead of leaving a lower black
band. Saved video cards and their exact Shot-local order are restored even
though the view itself starts compact. Shot routing serializes only participants
in the same flow; independent canvases no longer wait behind another flow's
callbacks, and a queued same-flow update reruns against a fresh retained-node
snapshot.

Team members should download the tagged runtime ZIP and matching `.sha256`
from [GitHub Releases](https://github.com/Honggooni/HMB_GP_Production/releases/latest),
not GitHub's automatically generated source-code archive.

Build the verified runtime-only team package with:

```powershell
python tools/package_runtime_release.py
python tools/package_runtime_release.py --check-output
```

The ZIP contains `release-manifest.json` and `SHA256SUMS`. Extract it outside
the Griptape library directory, close Griptape completely, and run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\HMB_GP_Production\Install_HMB_GP_Production.ps1
```

After installation, start Griptape normally from the supported Desktop app.
The runtime package no longer ships a separate HMB launcher; Agent policy
bootstrap is authorized by the exact packaged Griptape process provenance.

The installer verifies every manifest hash and replaces the target with the
exact runtime closure. It never creates a backup folder under
`Documents\GriptapeNodes\libraries`; the previous install is moved to a
recoverable rollback location under `%LOCALAPPDATA%\HMB_GP_Production`.
Existing `.venv` is preserved in the new install. Source-checkout metadata,
tests, tools, caches, and obsolete files therefore no longer remain in the
active library. Never install by Git clone/pull alone or copy a ZIP without
running the installer: those overlay methods retain obsolete development
files. The installed `resources` tree contains only Maya runtime support, the
Picker catalog, and the pinned public Broker CA.

All files inside a runtime ZIP use the actual local package-build time. The
builder records one uniform ZIP-compatible timestamp (two-second resolution),
so Windows Explorer shows the real build hour and minute instead of a fixed
midnight value. Verify an installation with `metadata.library_version`,
`release-manifest.json`, and `SHA256SUMS`; content hashes remain authoritative.

> **Public team distribution.** This repository and its signed release package
> contain the public Broker CA and the HMB team's default service address, but
> no bearer token, private key, signed policy body, or team media. Broker access
> remains authenticated and server-authorized. Report operational details and
> credentials only through a private channel.
