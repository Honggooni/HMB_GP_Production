# Temporary reference lifetime

Generator stages render references in Griptape Cloud for each explicit Seedance invocation.
Previously created TOS handles follow the same lease cleanup rules.
Before create, their live storage handles transfer into a process-private lease
bound to the original Broker origin, authenticated account fingerprint and
client request ID. A validated response from that create or same-key lookup may
bind its final Task ID once. A new Run or another Shot cannot consume that lease.

## Broker preflight v1

The official production Broker is detected automatically. Set
`HMB_CLOUD_PREFLIGHT_V1_BROKER_URL` to require v1 on an exact Broker base URL
including its gateway prefix. Project and My Box reference submissions first
send an authenticated empty POST to `/api/v1/preflight/griptape-cloud`. The
client requires HTTP 200, an empty `files` array and `provider_submitted: false`.
The empty probe has no media to download. For automatic production detection,
only the older Broker's exact JSON route-not-found response permits the legacy
format. Network errors, authentication errors and unrecognized replies stop the
submission before upload. An explicitly configured endpoint always requires v1.
Other custom Broker addresses retain their existing format.

On the designated Broker, the download URL carries
`#hmb-v1=<sha256>:<bytes>`. Both values describe the uploaded representation.
The Broker strips the fragment, verifies the file, and passes the signed URL
on to the provider. The client leaves per-file download retries to the Broker.
Existing job lookup, result download and Draft-ID-only Final keep their original
request paths.

Coordinate the production switch with the Broker owner. Deploy support for
both client formats on every routed worker and verify the diagnostic route
through the gateway. Then enable the exact production origin on upgraded
clients. Enforce v1 after upgrading remaining clients and accounting for queued
legacy reference jobs. A strict-only Broker like the initial TEST build needs
a coordinated cutover that keeps old clients and queued legacy creates off
that route. Keep status and result retrieval available throughout.

Cleanup authority also follows the exact authenticated HTTP response. A bearer
change, sign-out, failed token load or stale response invalidates the private
account evidence. A bounded, process-only response proof crosses validated My
Box projections without adding JSON fields or extra account requests. Missing
or evicted evidence keeps references held while normal rendering continues.

Maintenance intake is not provider acceptance. Its bounded wire metadata is
`maintenance_queued: true` and `maintenance_state` of `waiting`, `dispatching`,
`uncertain` or `blocked`. Once observed, the lease retains its queue history even
when later native responses omit the marker.

| Observation | Reference action |
| --- | --- |
| Lost create response, timeout, local Stop, node deletion or disconnected editor | Retain; do not schedule timer deletion |
| 404/503, unknown provider outcome or missing queue marker | Retain; this is not terminal evidence |
| Different Broker, account, request or Task | Retain; ignore this observation for lease release |
| Verified same-Task native success/failure without unknown or recovery hold | Release only handles owned by the current process |
| Video intake `blocked` with explicit `terminal: true` | Release this invocation's handles |
| My Box intake `blocked`/`failed` without explicit terminal proof | Retain; do not infer the video controller's terminal contract |

My Box's real `completed` result may release its own lease. The My Box wire
always disables resubmission, including successful results; that field alone
does not make a private failure conclusive.

The workflow stores only an opaque reference lease ID. A separate private
APPDATA JSON journal contains allowlisted original remote object identifiers,
origin, account fingerprint, process epoch, request/Task identity and unresolved
state. It contains no storage clients, access keys, signed URLs or prompts, and
is never written into Picker media output directories.

The journal is evidence, not a remote deletion command. There is no journal
reader which restores credentials, reconstructs storage clients or deletes old
objects after restart. If live handles are lost, remote retention/TTL remains
authoritative. Same-Task Retrieve remains the render recovery path; it never
creates a replacement render.
