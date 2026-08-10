# HMB GP Production

> **Public team Git repository.** The supported team rollout path is the
> repository's `main` branch through Griptape's Git-backed Library updater.
> GitHub Release archives, copied folders, network drives, and ZIP replacement
> are not supported install or update paths.

Repository visibility is not a security boundary. Never commit API keys,
access tokens, passwords, private signing keys, credentials, or non-public
media. Every change must pass the release security audit before it reaches
`main`.

## Team install and update

For the first installation, add this repository to Griptape as a Git-backed
Library by using the following repository URL:

`https://github.com/Honggooni/HMB_GP_Production.git`

The registered library directory must retain its `.git` metadata and track the
`main` branch. After a maintainer pushes or merges an approved version to
`main`, team members only need to refresh Griptape's Library view and click the
Library **Update** button.

Do not edit tracked files inside the registered Library. Development changes
belong in a separate clone; local edits can cause Griptape to block an update
instead of overwriting the installation.

Do not replace the registered library directory with a downloaded ZIP or a
copied folder. Those copies have no Git metadata, so Griptape cannot discover
or apply future updates. If the Update button is absent, the library is either
already current or is no longer a valid Git checkout with the GitHub `origin`.

## Agent policy availability

Release `0.5.33` includes exactly one signed production policy at
`resources/agent/hmb_agent_core.dat`. The runtime reads, verifies, and uses only
this file from the installed Git library. The canonical
`HMBPromptLibrary -> HMBAgentLibrary` flow requires no network policy share or
policy-path environment variable.

The bundled envelope is policy version
`2026-08-06.animation-look-continuity.v3`, contract SHA-256
`ab5b63a42717293cc097d51bf3048b5309c0ff52644bd0121b3045f6eeadae93`,
and file SHA-256
`6152355dd51d68da33d4df197e6ac52f2c13b37d9644aa50efd9ba8c2cf13619`.
It is a signed, compressed policy envelope rather than a confidentiality
encryption boundary, and contains no signing private key or API credentials.
