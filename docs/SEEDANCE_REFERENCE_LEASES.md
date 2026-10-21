# Temporary reference lifetime

Cloud and TOS reference uploads belong to one explicit Seedance invocation.
Before create, their live storage handles transfer into a process-private lease
bound to the original Broker origin, authenticated account fingerprint and
client request ID. A validated response from that create or same-key lookup may
bind its final Task ID once. A new Run or another Shot cannot consume that lease.

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
