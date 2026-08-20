# HMB GP Production

Current technical release: `v0.6.36`.

Build the verified team package with:

```powershell
python resources/build_developer_release.py
python resources/build_developer_release.py --check-output
```

The ZIP contains `release-manifest.json` and `SHA256SUMS`. Install the complete
`HMB_GP_Production` directory as one unit while Griptape is closed; never copy
individual Python or widget files across releases.

All files inside the v0.6.36 ZIP use the actual local package-build time. The
builder records one uniform ZIP-compatible timestamp (two-second resolution),
so Windows Explorer shows the real build hour and minute instead of a fixed
midnight value. Verify an installation with `metadata.library_version`,
`release-manifest.json`, and `SHA256SUMS`; content hashes remain authoritative.

> **Public team distribution.** This repository and its signed release package
> contain the public Broker CA and the HMB team's default service address, but
> no bearer token, private key, signed policy body, or team media. Broker access
> remains authenticated and server-authorized. Report operational details and
> credentials only through a private channel.
