# HMB GP Production

> **Public team distribution repository.** Keep this repository and its GitHub
> Releases public so every HMB team member can clone, fetch, and install updates
> without per-user repository access. Repository visibility is not a security
> boundary: never commit API keys, access tokens, passwords, private signing
> keys, credentials, or non-public media.

The source includes internal host and share defaults used for team routing.
Those values grant no access by themselves; authentication and authorization
remain the responsibility of the referenced services. Every change must still
pass the release security audit before it reaches `main`.

## Agent policy availability

Release `0.5.32` includes exactly one signed production policy at
`resources/agent/hmb_agent_core.dat`. The runtime reads, verifies, and uses only
this file from the installed library. Team members can install the complete ZIP
and run the canonical `HMBPromptLibrary -> HMBAgentLibrary` flow without a
network policy share or policy-path environment variable.

The bundled envelope is policy version
`2026-08-06.animation-look-continuity.v3`, contract SHA-256
`ab5b63a42717293cc097d51bf3048b5309c0ff52644bd0121b3045f6eeadae93`,
and file SHA-256
`6152355dd51d68da33d4df197e6ac52f2c13b37d9644aa50efd9ba8c2cf13619`.
It is a signed, compressed policy envelope rather than a confidentiality
encryption boundary, and contains no signing private key or API credentials.
The release ZIP contains
exactly 25 allowlisted runtime files and does not include `CHANGELOG.md` or
`resources/build_release.py`.
