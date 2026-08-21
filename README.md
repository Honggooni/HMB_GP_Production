# HMB GP Production

Current technical release: `v0.6.42`.

HMBAgentLibrary keeps Korean authoring input intact inside the private Prompt
contract, but its final video-generator instruction is English-only. Prompt
video snapshots are compiled without re-entering Shot graph mutation, and an
unchanged valid VideoPicker catalog remains ready instead of becoming a false
missing-source failure.

HMBVideoPickerLibrary opens in expanded authoring mode on its first mount. Its
expanded UI is isolated from the React Flow canvas; switching to the compact
Shot-sized card view does not resize or reframe the surrounding workspace.
Each added Shot grows by one complete fixed loader row, with no empty lower
band. Saved video cards and their exact Shot-local order are restored on
workflow reload.

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

All files inside the v0.6.42 ZIP use the actual local package-build time. The
builder records one uniform ZIP-compatible timestamp (two-second resolution),
so Windows Explorer shows the real build hour and minute instead of a fixed
midnight value. Verify an installation with `metadata.library_version`,
`release-manifest.json`, and `SHA256SUMS`; content hashes remain authoritative.

> **Public team distribution.** This repository and its signed release package
> contain the public Broker CA and the HMB team's default service address, but
> no bearer token, private key, signed policy body, or team media. Broker access
> remains authenticated and server-authorized. Report operational details and
> credentials only through a private channel.
