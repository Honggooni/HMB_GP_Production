# HMB GP Production

> **Private repository only.** This source tree and its production release keep
> authorized internal host/share defaults required by the HMB team workflow.
> Do not make the GitHub repository or release assets public without replacing
> those defaults and repeating the release security audit.

## Agent policy availability

Release `0.5.15` includes exactly one signed production fallback policy at
`resources/agent/hmb_agent_core.dat`. The runtime first tries the optional
administrator path configured through `HMB_AGENT_POLICY_PATH`; if that path is
missing, unavailable, or invalid, it verifies and uses the bundled policy. Team
members can therefore install the complete ZIP and run the canonical
`HMBPromptLibrary -> HMBAgentLibrary` flow without configuring a network-share
environment variable.

The bundled envelope is policy version
`2026-08-01.goal-final-authority.v2`, contract SHA-256
`a17809e4103628c1b0ab0b96081f6325faf9d16703a5fac57ef7d1eaa7d043bf`,
and file SHA-256
`94533d84ab914971026f624634c2553a0c7abba298f6dd76242d996ee5c9137f`.
It contains no signing private key or API credentials. Existing external-policy
deployment remains supported and has priority when its signature and contract
are valid.
