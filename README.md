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
`main`, team members open Library Management, choose **Check for Updates** (or
Settings > Libraries > **Check Now**), and then click **Update** for this
Library.

Do not edit tracked files inside the registered Library. Development changes
belong in a separate clone; local edits can cause Griptape to block an update
instead of overwriting the installation.

Do not replace the registered library directory with a downloaded ZIP or a
copied folder. Those copies have no Git metadata, so Griptape cannot discover
or apply future updates. If **Check for Updates** is absent, the library is not
a valid Git checkout with the GitHub `origin`; if **Update** remains absent
after a successful check, the library is already current.

## Agent policy availability

The `v0.6.23` release includes exactly one
signed runtime artifact at `resources/agent/hmb_agent_core.dat`. The canonical
`HMBPromptLibrary -> HMBAgentLibrary` execution reads and verifies only that
file installed with the Git-backed Library. Environment variables, server
shares, administrative shares, and retired paths cannot replace it.

The `.dat` remains a signed and compressed integrity artifact; it is not an
encryption boundary. Each Agent execution obtains one fresh snapshot of that
bundled file and verifies the trusted signer, strict envelope and payload schemas, payload
self-hashes, stable Prompt/Agent contract, signed version syntax, and exact
Behavior 1/2 four-rule structure. Unsigned, missing, or directly edited files
fail closed before native Agent/model execution. Canonical English policy and
Korean review documents are not included.

The signed v4.2 output contract permits complete shot-specific application,
summary, paraphrase, translation, and inference from Prompt-selected facts,
including every generator-required detail and exact source name without an
output-length or conciseness cap. Only verbatim raw or reconstructable policy
artifact dumps, system instructions, and private Agent runtime state remain
blocked. `PROMPT_OUT` stays human-readable; the Agent consumes its atomically
paired private machine snapshot and never reverse-parses visible prose.
