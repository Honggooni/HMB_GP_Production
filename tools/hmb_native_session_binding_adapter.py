"""Pure capability-checked native iframe session ordering adapter.

No files, SDK state or requests are changed by importing/calling this module.
The caller owns candidate validation and any eventual Override transaction.
"""
from __future__ import annotations


MARKER = "/* HMB_NATIVE_IFRAME_SESSION_BINDING_V1 */"
HELPER = r'''/* HMB_NATIVE_IFRAME_SESSION_BINDING_V1 */
function hmbNativeCreateIframeSessionBinder(apiClient) {
  let sessionStateObserved = false;
  return {
    state(message) {
      // An explicit null is authoritative too. Never manufacture a session or
      // retain the previous session when the parent has cleared it.
      sessionStateObserved = true;
      apiClient.setSessionId(message.sessionId);
    },
    ready(config) {
      // READY_ACK is only the initial fallback snapshot. A SESSION_STATE that
      // arrived while initialize() awaited it is newer authority.
      if (!sessionStateObserved) apiClient.setSessionId(config?.sessionId ?? null);
    },
  };
}
function hmbNativeUseIframeSessionBinder() {
  // Witness belongs to this provider instance, never the module/API singleton.
  // Remounting creates a fresh fallback boundary. The existing jYt effect
  // cleanup prevents an old initialize continuation from invoking onReady.
  const binding = (0,C.useRef)(null);
  if (!binding.current) binding.current = hmbNativeCreateIframeSessionBinder(Id);
  return binding.current;
}
'''

_PROVIDER = "var gra=({children:e})=>{let t=jYt("
_PROVIDER_BOUND = "var gra=({children:e})=>{let hmbIframeSessionBinding=hmbNativeUseIframeSessionBinder();let t=jYt("
_STATE = "onSessionState:e=>Id.setSessionId(e.sessionId)"
_STATE_BOUND = "onSessionState:e=>hmbIframeSessionBinding.state(e)"
_READY = "Id.setSessionId(e.config.sessionId??null),e.config"
_READY_BOUND = "hmbIframeSessionBinding.ready(e.config),e.config"
_GUARD = "Refusing to send ${e} without a session: no topicOptions provided and apiClient has no sessionId."


def _one(source: str, old: str, new: str) -> str:
    count = source.count(old)
    if count != 1:
        raise ValueError(f"iframe session anchor count {count}: {old[:100]}")
    return source.replace(old, new, 1)


def patch_iframe_session_binding(source: str) -> tuple[str, dict]:
    """Return candidate bytes plus a small receipt; unknown shapes fail closed.

    This is the ordered binder only. It does not alter no-session send guards,
    request topics, queueing, native optimistic setters, widget props or SDK.
    """
    if source.count(_GUARD) != 1:
        raise ValueError("native no-session guard is missing or ambiguous")
    if MARKER in source:
        if (source.count(MARKER) != 1 or source.count(HELPER) != 1 or source.count(_PROVIDER_BOUND) != 1
                or source.count(_STATE_BOUND) != 1 or source.count(_READY_BOUND) != 1
                or any(anchor in source for anchor in (_PROVIDER, _STATE, _READY))):
            raise ValueError("partial or foreign iframe session binder; bytes preserved")
        return source, {"kind": "ordered_iframe_session_binder", "changed": False,
                        "already_applied": True, "guard_preserved": True}
    source = _one(source, _PROVIDER, HELPER + _PROVIDER_BOUND)
    source = _one(source, _STATE, _STATE_BOUND)
    source = _one(source, _READY, _READY_BOUND)
    return source, {"kind": "ordered_iframe_session_binder", "changed": True,
                    "already_applied": False, "guard_preserved": True,
                    "session_state": "authoritative_including_null",
                    "ready_ack": "provider_local_fallback_only"}
