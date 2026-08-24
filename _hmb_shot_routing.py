from __future__ import annotations

"""Same-flow Shot routing for the HMB production nodes.

The public UI presents this as a cable-free Shot selector.  The retained-mode
engine still needs real data edges so upstream execution, save/load, and
invalidation remain deterministic.  This module discovers only nodes in the
caller's parent flow and creates those dependency edges behind hidden
parameters.  Media and prompt payloads never enter a process-global registry.
"""

from dataclasses import dataclass
from contextlib import contextmanager
import logging
import threading
from typing import Any, Iterable, Iterator
import weakref


SUBSCRIPTION_SCHEMA = "hmb-shot-channel-subscription"
SUBSCRIPTION_VERSION = 1
SHOT_ROUTING_PROTOCOL_VERSION = "2026-08-20.shot-routing.v1"
MAX_SHOTS = 5

KIND_IMAGE_ASSET = "image_asset"
KIND_VIDEO_PICKER = "video_picker"
KIND_PROMPT = "prompt"
KIND_AGENT = "agent"
KIND_SEEDANCE = "seedance"
KNOWN_KINDS = frozenset(
    {
        KIND_IMAGE_ASSET,
        KIND_VIDEO_PICKER,
        KIND_PROMPT,
        KIND_AGENT,
        KIND_SEEDANCE,
    }
)
SINGLETON_KINDS = frozenset({KIND_IMAGE_ASSET, KIND_VIDEO_PICKER})

_LOGGER = logging.getLogger("griptape_nodes")
_ROUTING_LOCK = threading.RLock()
_CONNECTION_MUTATION_LOCK = threading.Lock()
_ROUTING_FLOW_GATES: dict[str, "_RoutingFlowGate"] = {}
_ROUTING_PASS_LOCAL = threading.local()
_POST_REGISTRATION_MAX_ATTEMPTS = 6
_POST_REGISTRATION_RETRY_DELAYS_SECONDS = (0.025, 0.100, 0.250, 0.500, 1.000)


@dataclass(frozen=True)
class ShotSubscription:
    node: Any
    node_name: str
    kind: str
    enabled: bool
    channel_uuid: str
    shot_uuid: str
    shot_number: int
    shot_name: str


@dataclass(frozen=True)
class ShotEdge:
    source: Any
    source_parameter: str
    target: Any
    target_parameter: str


@dataclass(frozen=True)
class _CachedIncomingConnection:
    """Minimal retained-edge view created during one routing transaction."""

    source_node_name: str
    source_parameter_name: str
    target_node_name: str
    target_parameter_name: str


@dataclass(frozen=True)
class _PendingReconcile:
    generation: int
    phase: str
    fingerprint: tuple[str, bool, str, str] | None


class _RoutingFlowGate:
    """One short-lived same-flow serialization gate.

    Different flows own different locks and therefore remain independent. A
    nested call from the thread already reconciling this flow is rejected, but
    another thread waits for the active pass and then performs a fresh pass so
    its newer state change cannot be lost.
    """

    __slots__ = ("lock", "owner_thread_id", "participants")

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.owner_thread_id: int | None = None
        self.participants = 0


_POST_REGISTRATION_PENDING: weakref.WeakKeyDictionary[Any, _PendingReconcile] = (
    weakref.WeakKeyDictionary()
)
_POST_RECONCILE_GENERATIONS: weakref.WeakKeyDictionary[Any, int] = (
    weakref.WeakKeyDictionary()
)
_AUTHORITATIVE_FINGERPRINTS: weakref.WeakKeyDictionary[
    Any, tuple[str, bool, str, str]
] = weakref.WeakKeyDictionary()
_SINGLETON_ADMISSIONS: weakref.WeakKeyDictionary[Any, tuple[str, str]] = (
    weakref.WeakKeyDictionary()
)
_SINGLETON_REGISTRATION_ORDERS: weakref.WeakKeyDictionary[Any, int] = (
    weakref.WeakKeyDictionary()
)
_SINGLETON_RESET_HANDOFFS: weakref.WeakKeyDictionary[
    Any, weakref.ReferenceType[Any]
] = weakref.WeakKeyDictionary()
_SINGLETON_REGISTRATION_GENERATION = 0


@contextmanager
def _claim_routing_flow(flow_name: str) -> Iterator[bool]:
    """Serialize only this flow while keeping the global registry lock short.

    The old reconciler held ``_ROUTING_LOCK`` while it called node callbacks and
    mutated retained-mode edges.  A slow callback in one canvas consequently
    stalled routing in every other canvas, and a callback waiting on another
    flow could form a cross-flow lock cycle. The process-wide lock now protects
    only the flow-gate registry. Same-thread nested re-entry remains fail-fast;
    a concurrent caller for the same flow waits and then runs its own fresh pass
    instead of silently dropping the newer state change.
    """

    thread_id = threading.get_ident()
    nested_reentry = False
    with _ROUTING_LOCK:
        gate = _ROUTING_FLOW_GATES.get(flow_name)
        if gate is None:
            gate = _RoutingFlowGate()
            _ROUTING_FLOW_GATES[flow_name] = gate
        if gate.owner_thread_id == thread_id:
            nested_reentry = True
        else:
            gate.participants += 1

    if nested_reentry:
        yield False
        return

    gate.lock.acquire()
    with _ROUTING_LOCK:
        gate.owner_thread_id = thread_id
    try:
        yield True
    finally:
        with _ROUTING_LOCK:
            gate.owner_thread_id = None
            gate.participants -= 1
        gate.lock.release()
        with _ROUTING_LOCK:
            if (
                gate.participants == 0
                and _ROUTING_FLOW_GATES.get(flow_name) is gate
            ):
                _ROUTING_FLOW_GATES.pop(flow_name, None)


class _ReconcileResult(dict[str, Any]):
    """Publicly dict-compatible result with private scheduler coverage."""

    __slots__ = ("_covered_node_ids",)

    def __init__(self, *args: Any, covered_node_ids: Iterable[int] = (), **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._covered_node_ids = frozenset(covered_node_ids)


def _clean(value: Any, limit: int = 512) -> str:
    return " ".join(str(value or "").replace("\x00", " ").split())[:limit]


def _bounded_int(value: Any, minimum: int, maximum: int, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return max(minimum, min(maximum, number))


def _subscription_for(node: Any) -> ShotSubscription | None:
    # The host calls ``after_node_deleted`` before removing the object from its
    # retained-mode flow.  Excluding that exact object here prevents one final
    # reconcile from treating a deleted Prompt as a live Shot claimant.
    if bool(getattr(node, "_hmb_node_deleted", False)):
        return None
    getter = getattr(node, "_hmb_shot_channel_subscription", None)
    if not callable(getter):
        return None
    try:
        raw = getter()
    except Exception:
        return None
    if not isinstance(raw, dict):
        return None
    if set(raw) != {
        "schema",
        "version",
        "participant_kind",
        "enabled",
        "channel_uuid",
        "shot_uuid",
        "shot_number",
        "shot_name",
    }:
        return None
    if raw.get("schema") != SUBSCRIPTION_SCHEMA or raw.get("version") != SUBSCRIPTION_VERSION:
        return None
    kind = _clean(raw.get("participant_kind"), 32).casefold()
    if kind not in KNOWN_KINDS:
        return None
    node_name = _clean(getattr(node, "name", ""), 512)
    if not node_name:
        return None
    channel_uuid = _clean(raw.get("channel_uuid"), 128)
    shot_uuid = _clean(raw.get("shot_uuid"), 128)
    enabled = bool(raw.get("enabled")) and bool(channel_uuid)
    if kind not in {KIND_IMAGE_ASSET, KIND_VIDEO_PICKER}:
        enabled = enabled and bool(shot_uuid)
    return ShotSubscription(
        node=node,
        node_name=node_name,
        kind=kind,
        enabled=enabled,
        channel_uuid=channel_uuid,
        shot_uuid=shot_uuid,
        shot_number=_bounded_int(raw.get("shot_number"), 1, MAX_SHOTS, 1),
        shot_name=_clean(raw.get("shot_name"), 128) or "Shot 1",
    )


def _same_flow_nodes(node: Any) -> tuple[str, list[Any]]:
    """Return registered nodes from exactly the caller's retained-mode flow."""

    try:
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes  # type: ignore

        node_name = _clean(getattr(node, "name", ""), 512)
        if not node_name:
            return "", []
        manager = GriptapeNodes.NodeManager()
        # Constructors run before registration.  Refuse discovery until the
        # manager resolves this exact object, avoiding noisy list requests.
        if manager.get_node_by_name(node_name) is not node:
            return "", []
        flow_name = manager.get_node_parent_flow_by_name(node_name)
        flow = GriptapeNodes.FlowManager().get_flow_by_name(flow_name)
        nodes = list(getattr(flow, "nodes", {}).values())
        return _clean(flow_name, 512), nodes
    except Exception:
        return "", []


def _subscription_fingerprint(
    node: Any,
) -> tuple[str, bool, str, str] | None:
    subscription = _subscription_for(node)
    if subscription is None:
        return None
    return (
        subscription.kind,
        subscription.enabled,
        subscription.channel_uuid,
        subscription.shot_uuid,
    )


def _singleton_owner(node: Any, nodes: Iterable[Any]) -> Any | None:
    """Return the first live same-kind singleton in retained flow order.

    ImageAsset and VideoPicker are flow-level authorities. Prompt, Agent and
    Seedance remain intentionally multi-instance because every Shot may own an
    independent downstream chain.
    """

    current = _subscription_for(node)
    if current is None or current.kind not in SINGLETON_KINDS:
        return None
    candidates = []
    for candidate in nodes:
        subscription = _subscription_for(candidate)
        if subscription is not None and subscription.kind == current.kind:
            candidates.append(candidate)
    with _ROUTING_LOCK:
        registration_orders = {
            id(candidate): _SINGLETON_REGISTRATION_ORDERS.get(candidate)
            for candidate in candidates
        }
        admissions = {
            id(candidate): _SINGLETON_ADMISSIONS.get(candidate, ("", ""))
            for candidate in candidates
        }
        authoritative_ids = {
            id(candidate)
            for candidate in candidates
            if candidate in _AUTHORITATIVE_FINGERPRINTS
        }

    def registration_rank(candidate: Any) -> tuple[int, str]:
        order = registration_orders.get(id(candidate))
        return (
            int(order) if isinstance(order, int) else 2**63 - 1,
            _clean(getattr(candidate, "name", ""), 512).casefold(),
        )

    admitted = [
        candidate
        for candidate in candidates
        if admissions.get(id(candidate), ("", ""))[1] == current.kind
    ]
    if admitted:
        return min(admitted, key=registration_rank)
    authoritative = [
        candidate for candidate in candidates if id(candidate) in authoritative_ids
    ]
    if authoritative:
        return min(authoritative, key=registration_rank)
    if candidates:
        return min(candidates, key=registration_rank)
    return None


def _try_stage_singleton_reset_handoff(
    node: Any,
    owner: Any,
) -> bool:
    """Copy durable singleton content during Griptape's reset replacement.

    Griptape 0.95 resets a node by constructing ``<old-name>_temp`` first,
    deleting the old object, and finally renaming the replacement.  The old
    and new objects therefore overlap briefly even though the workflow still
    owns one logical singleton.  Transfer only through the nodes' explicit
    export/adopt hooks; routing itself never stores media or prompt payloads.
    """

    node_name = _clean(getattr(node, "name", ""), 512)
    if not node_name.endswith("_temp"):
        return False
    owner_name = node_name[: -len("_temp")]
    if not owner_name:
        return False
    if (
        owner is None
        or owner is node
        or bool(getattr(owner, "_hmb_node_deleted", False))
        or _clean(getattr(owner, "name", ""), 512) != owner_name
    ):
        return False
    # Exact same-flow identity is mandatory. Names are process-global in the
    # current host, but relying on that implementation detail could copy one
    # workflow's durable media into another workflow's manually named temp
    # node. Both objects must already be retained in the same flow.
    owner_flow_name, owner_flow_nodes = _same_flow_nodes(owner)
    node_flow_name, node_flow_nodes = _same_flow_nodes(node)
    if (
        not owner_flow_name
        or owner_flow_name != node_flow_name
        or owner not in owner_flow_nodes
        or node not in node_flow_nodes
    ):
        return False
    node_subscription = _subscription_for(node)
    owner_subscription = _subscription_for(owner)
    if (
        node_subscription is None
        or owner_subscription is None
        or node_subscription.kind not in SINGLETON_KINDS
        or node_subscription.kind != owner_subscription.kind
    ):
        return False
    with _ROUTING_LOCK:
        previous_owner = _SINGLETON_RESET_HANDOFFS.get(node)
        if previous_owner is not None and previous_owner() is owner:
            return True
    exporter = getattr(owner, "_hmb_export_reset_handoff", None)
    adopter = getattr(node, "_hmb_adopt_reset_handoff", None)
    if not callable(exporter) or not callable(adopter):
        return False
    try:
        payload = exporter()
        if not isinstance(payload, dict):
            return False
        adopted = adopter(payload)
        if adopted is False:
            return False
    except Exception as exc:
        _LOGGER.warning(
            "Unable to preserve singleton reset state from %s to %s: %s",
            owner_name,
            node_name,
            exc,
        )
        return False
    with _ROUTING_LOCK:
        _SINGLETON_RESET_HANDOFFS[node] = weakref.ref(owner)
    return True


def prepare_node_deletion(node: Any) -> bool:
    """Preserve a same-flow reset replacement before marking ``node`` deleted."""

    flow_name, nodes = _same_flow_nodes(node)
    owner_subscription = _subscription_for(node)
    owner_name = _clean(getattr(node, "name", ""), 512)
    if (
        not flow_name
        or owner_subscription is None
        or owner_subscription.kind not in SINGLETON_KINDS
        or not owner_name
    ):
        return False
    replacement_name = f"{owner_name}_temp"
    replacement = next(
        (
            candidate
            for candidate in nodes
            if candidate is not node
            and not bool(getattr(candidate, "_hmb_node_deleted", False))
            and _clean(getattr(candidate, "name", ""), 512) == replacement_name
            and (
                (candidate_subscription := _subscription_for(candidate))
                is not None
            )
            and candidate_subscription.kind == owner_subscription.kind
        ),
        None,
    )
    return bool(
        replacement is not None
        and _try_stage_singleton_reset_handoff(replacement, node)
    )


def release_node_lifecycle(node: Any) -> None:
    """Release every identity-bound routing lease for one deleted object."""

    with _ROUTING_LOCK:
        _POST_REGISTRATION_PENDING.pop(node, None)
        _POST_RECONCILE_GENERATIONS.pop(node, None)
        _AUTHORITATIVE_FINGERPRINTS.pop(node, None)
        _SINGLETON_ADMISSIONS.pop(node, None)
        _SINGLETON_REGISTRATION_ORDERS.pop(node, None)
        _SINGLETON_RESET_HANDOFFS.pop(node, None)
        for replacement, owner_ref in list(_SINGLETON_RESET_HANDOFFS.items()):
            if owner_ref() is node:
                _SINGLETON_RESET_HANDOFFS.pop(replacement, None)


def _enforce_singleton_admission(
    node: Any,
    *,
    defer_reset_staging: bool = False,
) -> bool | None:
    """Reject a newly registered duplicate flow authority immediately.

    Engine 0.93 has no per-flow library-palette availability callback, so a
    palette item cannot be greyed out based on canvas contents. The earliest
    supported enforcement point is the identity-proven post-registration
    callback: the original node stays untouched and only the later duplicate
    is removed through the retained-mode DeleteNodeRequest lifecycle.
    """

    flow_name, nodes = _same_flow_nodes(node)
    current = _subscription_for(node)
    if not flow_name or current is None or current.kind not in SINGLETON_KINDS:
        return True
    candidates = [
        candidate
        for candidate in nodes
        if (subscription := _subscription_for(candidate)) is not None
        and subscription.kind == current.kind
    ]
    if node not in candidates:
        candidates.append(node)
    with _ROUTING_LOCK:
        registration_orders = {
            id(candidate): _SINGLETON_REGISTRATION_ORDERS.get(candidate)
            for candidate in candidates
        }
        admissions = {
            id(candidate): _SINGLETON_ADMISSIONS.get(candidate)
            for candidate in candidates
        }
        authoritative_ids = {
            id(candidate)
            for candidate in candidates
            if candidate in _AUTHORITATIVE_FINGERPRINTS
        }

    def registration_rank(candidate: Any) -> tuple[int, str]:
        order = registration_orders.get(id(candidate))
        return (
            int(order) if isinstance(order, int) else 2**63 - 1,
            _clean(getattr(candidate, "name", ""), 512).casefold(),
        )
    admitted = [
        candidate
        for candidate in candidates
        if admissions.get(id(candidate)) == (flow_name, current.kind)
    ]
    authoritative = [
        candidate
        for candidate in candidates
        if id(candidate) in authoritative_ids
    ]
    owner_pool = admitted or authoritative or candidates
    owner = min(owner_pool, key=registration_rank) if owner_pool else None
    if owner is node:
        # Construction-time registration order is recorded before hydration
        # can replace the pending callback.  It is therefore stable even when
        # React Flow inserts a newer drag at the front of its node mapping.
        with _ROUTING_LOCK:
            _SINGLETON_ADMISSIONS[node] = (flow_name, current.kind)
        return True
    node_name = _clean(getattr(node, "name", ""), 512)
    owner_name = _clean(getattr(owner, "name", ""), 512)
    if (
        defer_reset_staging
        and owner is not None
        and node_name == f"{owner_name}_temp"
    ):
        # A reset replacement is not an ordinary palette duplicate. Preserve
        # its durable state while both identities exist, then let the bounded
        # registration callback retry after the host deletes/renames them.
        _try_stage_singleton_reset_handoff(node, owner)
        return None
    if not node_name:
        return False
    _notify_status(
        node,
        ok=False,
        code="singleton_already_exists",
        details=(
            f"{owner_name or 'This flow'} already owns this library node; "
            "the duplicate was not created."
        ),
    )
    try:
        from griptape_nodes.retained_mode.events.node_events import (  # type: ignore
            DeleteNodeRequest,
        )
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes  # type: ignore

        GriptapeNodes.handle_request(DeleteNodeRequest(node_name=node_name))
    except Exception as exc:
        _LOGGER.warning(
            "Unable to remove duplicate singleton node %s: %s",
            node_name,
            exc,
        )
        return False
    return False


def _mark_authoritative(node: Any) -> tuple[str, bool, str, str] | None:
    fingerprint = _subscription_fingerprint(node)
    if fingerprint is not None:
        with _ROUTING_LOCK:
            _AUTHORITATIVE_FINGERPRINTS[node] = fingerprint
    return fingerprint


def _schedule_post_reconcile(node: Any, *, phase: str) -> bool:
    """Queue one identity-bound registration or hydration generation.

    Constructor registration is deliberately non-destructive: the host may
    register every node before replaying any serialized values.  Only an
    explicit post-hydration generation may run the full reconciler.  A newer
    generation always supersedes an older callback for the same exact object.
    """

    global _SINGLETON_REGISTRATION_GENERATION

    if phase not in {"registration", "hydrated"}:
        return False
    if phase == "registration":
        with _ROUTING_LOCK:
            if node not in _SINGLETON_REGISTRATION_ORDERS:
                _SINGLETON_REGISTRATION_GENERATION += 1
                _SINGLETON_REGISTRATION_ORDERS[node] = (
                    _SINGLETON_REGISTRATION_GENERATION
                )
    try:
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes  # type: ignore

        loop = GriptapeNodes.EventManager().event_loop
        node_ref = weakref.ref(node)
        node_name = _clean(getattr(node, "name", ""), 512)
        is_closed = getattr(loop, "is_closed", lambda: False)
        if not node_name or loop is None or is_closed():
            return False
        with _ROUTING_LOCK:
            previous = _POST_REGISTRATION_PENDING.get(node)
            # A late compatibility registration request must never downgrade a
            # hydration generation that already owns the newest state.
            if phase == "registration" and previous is not None:
                return True
            generation = int(_POST_RECONCILE_GENERATIONS.get(node, 0)) + 1
            _POST_RECONCILE_GENERATIONS[node] = generation
            fingerprint = (
                _mark_authoritative(node) if phase == "hydrated" else None
            )
            pending = _PendingReconcile(generation, phase, fingerprint)
            _POST_REGISTRATION_PENDING[node] = pending
    except Exception:
        return False

    def clear_pending(current: Any) -> None:
        with _ROUTING_LOCK:
            if _POST_REGISTRATION_PENDING.get(current) is pending:
                _POST_REGISTRATION_PENDING.pop(current, None)

    def queue_initial_attempt() -> bool:
        try:
            loop.call_soon_threadsafe(run_attempt, 0)
            return True
        except (RuntimeError, TypeError):
            current = node_ref()
            if current is not None:
                clear_pending(current)
            return False

    def queue_delayed_attempt(attempt: int) -> bool:
        if attempt >= _POST_REGISTRATION_MAX_ATTEMPTS:
            current = node_ref()
            if current is not None:
                clear_pending(current)
            return False
        delay_index = min(
            max(0, attempt - 1),
            len(_POST_REGISTRATION_RETRY_DELAYS_SECONDS) - 1,
        )
        try:
            loop.call_later(
                _POST_REGISTRATION_RETRY_DELAYS_SECONDS[delay_index],
                run_attempt,
                attempt,
            )
            return True
        except (AttributeError, RuntimeError, TypeError):
            current = node_ref()
            if current is not None:
                clear_pending(current)
            return False

    def run_attempt(attempt: int) -> None:
        current = node_ref()
        if current is None:
            return
        with _ROUTING_LOCK:
            if _POST_REGISTRATION_PENDING.get(current) is not pending:
                return
        if getattr(current, "_hmb_node_deleted", False):
            clear_pending(current)
            return
        # Reset replaces ``name_temp`` and then renames that same exact object
        # to ``name``. Resolve registration by current identity/name instead of
        # rejecting the legitimate rename against the constructor-time label.
        current_name = _clean(getattr(current, "name", ""), 512)
        if not current_name:
            clear_pending(current)
            return
        try:
            manager = GriptapeNodes.NodeManager()
            registered = manager.get_node_by_name(current_name)
        except Exception:
            manager = None
            registered = None
        if registered is not current:
            # Deletion and same-name recreation can briefly leave the previous
            # object in NodeManager while the replacement constructor has
            # already queued discovery. Treat that stale object exactly like a
            # missing registration for the bounded retry window; exact identity
            # still prevents either instance from mutating the other.
            if attempt + 1 < _POST_REGISTRATION_MAX_ATTEMPTS:
                queue_delayed_attempt(attempt + 1)
            else:
                clear_pending(current)
            return

        # Hydration can supersede the constructor's queued registration phase
        # before the event loop runs it. Singleton admission must therefore be
        # enforced for both phases once exact manager identity is proven. The
        # oldest registered ImageAsset/VideoPicker remains authoritative and a
        # rejected duplicate is retried until the host confirms its deletion.
        admitted = _enforce_singleton_admission(
            current,
            defer_reset_staging=(
                attempt + 1 < _POST_REGISTRATION_MAX_ATTEMPTS
            ),
        )
        if admitted is None:
            queue_delayed_attempt(attempt + 1)
            return
        if not admitted or bool(getattr(current, "_hmb_node_deleted", False)):
            try:
                current_name = _clean(getattr(current, "name", ""), 512)
                still_registered = bool(current_name) and (
                    manager.get_node_by_name(current_name) is current
                )
            except Exception:
                still_registered = False
            if still_registered and attempt + 1 < _POST_REGISTRATION_MAX_ATTEMPTS:
                queue_delayed_attempt(attempt + 1)
            else:
                clear_pending(current)
            return
        if pending.phase == "registration":
            if not bool(getattr(current, "_hmb_node_deleted", False)):
                discovery = getattr(
                    current,
                    "_hmb_post_registration_shot_discovery",
                    None,
                )
                if callable(discovery):
                    try:
                        discovery()
                    except Exception:
                        pass
            clear_pending(current)
            return

        # The aggregate state changed after this hydration signal.  A later
        # authoritative setter must publish a new generation; this callback
        # cannot guess that partially replayed state is final.
        if _subscription_fingerprint(current) != pending.fingerprint:
            clear_pending(current)
            return
        # A hydrated generation supersedes the constructor registration
        # callback. Give nodes with non-routing durable UI state one exact,
        # registered, next-turn restore seam before routing reconciliation.
        # The callback must remain local-only; it may not perform network I/O.
        hydration_restore = getattr(
            current,
            "_hmb_post_hydration_state_restore",
            None,
        )
        if callable(hydration_restore):
            try:
                hydration_restore()
            except Exception:
                pass
        try:
            result = reconcile_shot_routing(current)
        except Exception:
            clear_pending(current)
            return
        result_code = result.get("code") if isinstance(result, dict) else ""
        if result_code in {"not_registered", "reentrant"}:
            if attempt + 1 < _POST_REGISTRATION_MAX_ATTEMPTS:
                queue_delayed_attempt(attempt + 1)
            else:
                clear_pending(current)
            return
        if not isinstance(result, dict) or not result.get("ok", False):
            clear_pending(current)
            return
        if (
            getattr(current, "_hmb_node_deleted", False)
        ):
            clear_pending(current)
            return
        try:
            current_name = _clean(getattr(current, "name", ""), 512)
            if (
                manager is None
                or not current_name
                or manager.get_node_by_name(current_name) is not current
            ):
                clear_pending(current)
                return
        except Exception:
            clear_pending(current)
            return
        clear_pending(current)

    return queue_initial_attempt()


def schedule_post_registration_reconcile(node: Any) -> bool:
    """Wait for exact registration without running destructive reconciliation."""

    return _schedule_post_reconcile(node, phase="registration")


def schedule_post_hydration_reconcile(node: Any) -> bool:
    """Publish authoritative aggregate state and queue its newest generation."""

    return _schedule_post_reconcile(node, phase="hydrated")


def schedule_post_deletion_reconcile(node: Any) -> bool:
    """Reconcile surviving participants after ``node`` leaves its flow.

    ``after_node_deleted`` runs while the deleted object can still be present
    in ``NodeManager``.  ``_subscription_for`` already excludes an object as
    soon as its deletion flag is set, so the host deletion callback itself is
    the safest deterministic reconciliation point: it runs on the retained-
    mode dispatch thread, before the parent removes ordinary incident edges.

    Never fall back to ``threading.Timer`` here.  NodeManager, FlowManager and
    node setters are retained-mode state and may not be called from a timer
    worker.  A single synchronous pass is both bounded and sufficient because
    the deleted object remains useful as the exact same-flow anchor while its
    subscription has already become invisible.
    """

    try:
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes  # type: ignore

        manager = GriptapeNodes.NodeManager()
        node_name = _clean(getattr(node, "name", ""), 512)
        if not node_name or manager.get_node_by_name(node_name) is not node:
            return False
        flow_name = _clean(manager.get_node_parent_flow_by_name(node_name), 512)
        flow = GriptapeNodes.FlowManager().get_flow_by_name(flow_name)
        survivor = next(
            (
                candidate
                for candidate in list(getattr(flow, "nodes", {}).values())
                if candidate is not node
                and not bool(getattr(candidate, "_hmb_node_deleted", False))
                and _subscription_for(candidate) is not None
            ),
            None,
        )
        if survivor is None:
            return False
    except Exception:
        return False
    try:
        result = reconcile_shot_routing(node, _allow_unready_cleanup=True)
    except Exception:
        return False
    return isinstance(result, dict) and result.get("code") not in {
        "not_registered",
        "reentrant",
    }


def _has_parameter(node: Any, name: str) -> bool:
    try:
        return node.get_parameter_by_name(name) is not None
    except Exception:
        parameters = getattr(node, "parameters", None)
        return isinstance(parameters, dict) and name in parameters


def _incoming_connections(node: Any) -> list[Any]:
    cache = getattr(_ROUTING_PASS_LOCAL, "incoming_by_node", None)
    cache_key = id(node)
    if isinstance(cache, dict) and cache_key in cache:
        return list(cache[cache_key])
    try:
        from griptape_nodes.retained_mode.events.connection_events import (  # type: ignore
            ListConnectionsForNodeRequest,
            ListConnectionsForNodeResultSuccess,
        )
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes  # type: ignore

        result = GriptapeNodes.handle_request(
            ListConnectionsForNodeRequest(
                node_name=str(node.name),
                include_internal=True,
                broadcast_result=False,
                failure_log_level=logging.DEBUG,
            )
        )
        if isinstance(result, ListConnectionsForNodeResultSuccess):
            incoming = list(result.incoming_connections)
            if isinstance(cache, dict):
                cache[cache_key] = incoming
            return list(incoming)
    except Exception:
        pass
    if isinstance(cache, dict):
        cache[cache_key] = []
    return []


def _delete_connection(connection: Any, target: Any) -> bool:
    try:
        from griptape_nodes.retained_mode.events.connection_events import (  # type: ignore
            DeleteConnectionRequest,
        )
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes  # type: ignore

        # Griptape 0.95 stores retained connections in one process-global
        # collection. Keep only the actual mutation serialized; discovery and
        # node callbacks remain independent per flow.
        with _CONNECTION_MUTATION_LOCK:
            result = GriptapeNodes.handle_request(
                DeleteConnectionRequest(
                    source_node_name=str(connection.source_node_name),
                    source_parameter_name=str(connection.source_parameter_name),
                    target_node_name=str(target.name),
                    target_parameter_name=str(connection.target_parameter_name),
                    failure_log_level=logging.DEBUG,
                )
            )
        succeeded = bool(getattr(result, "succeeded", lambda: False)())
        if succeeded:
            cache = getattr(_ROUTING_PASS_LOCAL, "incoming_by_node", None)
            if isinstance(cache, dict):
                key = id(target)
                cached = cache.get(key)
                if isinstance(cached, list):
                    cache[key] = [
                        item
                        for item in cached
                        if item is not connection
                        and not (
                            str(getattr(item, "source_node_name", ""))
                            == str(getattr(connection, "source_node_name", ""))
                            and str(getattr(item, "source_parameter_name", ""))
                            == str(getattr(connection, "source_parameter_name", ""))
                            and str(getattr(item, "target_parameter_name", ""))
                            == str(getattr(connection, "target_parameter_name", ""))
                        )
                    ]
        return succeeded
    except Exception:
        return False


def _create_connection(edge: ShotEdge) -> bool:
    try:
        from griptape_nodes.retained_mode.events.connection_events import (  # type: ignore
            CreateConnectionRequest,
        )
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes  # type: ignore

        with _CONNECTION_MUTATION_LOCK:
            result = GriptapeNodes.handle_request(
                CreateConnectionRequest(
                    source_node_name=str(edge.source.name),
                    source_parameter_name=edge.source_parameter,
                    target_node_name=str(edge.target.name),
                    target_parameter_name=edge.target_parameter,
                    failure_log_level=logging.DEBUG,
                )
            )
        succeeded = bool(getattr(result, "succeeded", lambda: False)())
        if succeeded:
            cache = getattr(_ROUTING_PASS_LOCAL, "incoming_by_node", None)
            if isinstance(cache, dict):
                cache.setdefault(id(edge.target), []).append(
                    _CachedIncomingConnection(
                        source_node_name=str(edge.source.name),
                        source_parameter_name=edge.source_parameter,
                        target_node_name=str(edge.target.name),
                        target_parameter_name=edge.target_parameter,
                    )
                )
        return succeeded
    except Exception:
        return False


def _ensure_edge(edge: ShotEdge, subscriptions: dict[str, ShotSubscription]) -> tuple[bool, str]:
    if not _has_parameter(edge.source, edge.source_parameter):
        return False, f"missing source parameter {edge.source_parameter}"
    if not _has_parameter(edge.target, edge.target_parameter):
        return False, f"missing target parameter {edge.target_parameter}"

    incoming = [
        item
        for item in _incoming_connections(edge.target)
        if str(getattr(item, "target_parameter_name", "")) == edge.target_parameter
    ]
    exact = [
        item
        for item in incoming
        if str(getattr(item, "source_node_name", "")) == str(edge.source.name)
        and str(getattr(item, "source_parameter_name", "")) == edge.source_parameter
    ]
    if exact:
        return True, "existing"

    # A foreign/non-HMB source, or an HMB source using a different output, is
    # user-owned.  Never silently replace it.  Automatic routes always use the
    # exact source parameter declared by ``edge``.
    for item in incoming:
        source_name = str(getattr(item, "source_node_name", ""))
        source_parameter = str(getattr(item, "source_parameter_name", ""))
        if source_name not in subscriptions or source_parameter != edge.source_parameter:
            return False, "foreign connection conflict"

    for item in incoming:
        if not _delete_connection(item, edge.target):
            return False, "unable to replace stale HMB route"
    if not _create_connection(edge):
        return False, "unable to create HMB route"
    return True, "created"


def _clear_hmb_route(
    target: Any,
    target_parameter: str,
    subscriptions: dict[str, ShotSubscription],
    *,
    source_parameter: str,
) -> tuple[int, str]:
    """Remove only an automatic HMB edge from one routing-owned input.

    Ambiguous or missing publishers must not leave a previously selected
    publisher connected: downstream topology checks could otherwise consume a
    stale Shot.  Connections from non-HMB nodes, and connections using any
    other source parameter, remain user-owned and are never touched.
    """

    removed = 0
    for item in _incoming_connections(target):
        if str(getattr(item, "target_parameter_name", "")) != target_parameter:
            continue
        source_name = str(getattr(item, "source_node_name", ""))
        item_source_parameter = str(getattr(item, "source_parameter_name", ""))
        if source_name not in subscriptions or item_source_parameter != source_parameter:
            continue
        if not _delete_connection(item, target):
            return removed, "unable to clear stale HMB route"
        removed += 1
    return removed, "cleared" if removed else "absent"


def _notify_status(node: Any, *, ok: bool, code: str, details: str = "") -> None:
    callback = getattr(node, "_hmb_shot_routing_status", None)
    if not callable(callback):
        return
    try:
        callback(
            {
                "schema": "hmb-shot-routing-status",
                "version": 1,
                "ok": bool(ok),
                "code": _clean(code, 64),
                "details": _clean(details, 256),
            }
        )
    except Exception:
        pass


def _clear_remote_catalog(node: Any, reason: str) -> None:
    """Return one participant to its local-only selector state.

    The callback is deliberately optional so older nodes remain compatible.
    It must clear only Shot-routing identity/catalog state; authored prompt,
    media history, provider settings, and legacy/manual inputs stay intact.
    """

    callback = getattr(node, "_hmb_clear_shot_routing_catalog", None)
    if not callable(callback):
        return
    try:
        callback(_clean(reason, 64) or "publisher_unavailable")
        _mark_authoritative(node)
    except Exception:
        pass


def _clear_remote_edges(
    subscription: ShotSubscription,
    subscriptions: dict[str, ShotSubscription],
) -> tuple[int, list[str]]:
    """Remove edges owned by an active remote Shot subscription.

    This runs before the participant clears its channel/Shot quartet, which
    lets us distinguish a remote-managed Agent prompt edge from a normal
    local-only/manual prompt connection.
    """

    if subscription.kind == KIND_AGENT:
        removed, detail = _clear_hmb_route(
            subscription.node,
            "SHOT_PROMPT_IN",
            subscriptions,
            source_parameter="PROMPT_OUT",
        )
        return removed, [detail] if detail.startswith("unable") else []

    routes: tuple[tuple[str, str], ...]
    if subscription.kind == KIND_PROMPT:
        routes = (
            ("SHOT_ASSET_IN", "SHOT_ASSET_OUT"),
            ("SHOT_PICKER_IN", "SHOT_PICKER_OUT"),
        )
    elif subscription.kind == KIND_SEEDANCE:
        routes = (
            # Legacy automatic Agent/Prompt routes are removed during migration.
            ("SHOT_PROMPT_IN", "output"),
            ("SHOT_IMAGE_IN", "SHOT_IMAGE_OUT"),
            ("SHOT_VIDEO_IN", "SHOT_VIDEO_OUT"),
            # Current direct Shot-source routes.
            ("SHOT_ASSET_IN", "SHOT_ASSET_OUT"),
            ("SHOT_PICKER_IN", "SHOT_PICKER_OUT"),
        )
    else:
        routes = ()

    changed = 0
    failures: list[str] = []
    for target_parameter, source_parameter in routes:
        removed, detail = _clear_hmb_route(
            subscription.node,
            target_parameter,
            subscriptions,
            source_parameter=source_parameter,
        )
        changed += removed
        if detail.startswith("unable"):
            failures.append(detail)
    return changed, failures


def _reject_duplicate_prompt_selection(node: Any) -> bool:
    """Ask a Prompt to return to Only while preserving its remote catalog.

    New Prompt implementations expose the narrow callback below.  Older nodes
    remain safe: their hidden managed edges are still removed and the duplicate
    group is excluded from route creation, but no broad catalog clear is used.
    """

    callback = getattr(node, "_hmb_reject_duplicate_shot_selection", None)
    if not callable(callback):
        return False
    try:
        callback("duplicate_prompt_shot")
        _mark_authoritative(node)
    except Exception:
        return False
    current = _subscription_for(node)
    return current is not None and not current.enabled


def _reject_duplicate_agent_selection(node: Any) -> bool:
    """Return a non-owner Agent to Only without discarding its Shot catalog."""

    callback = getattr(node, "_hmb_reject_duplicate_shot_selection", None)
    if not callable(callback):
        return False
    try:
        callback("duplicate_agent_shot")
        _mark_authoritative(node)
    except Exception:
        return False
    current = _subscription_for(node)
    return current is not None and not current.enabled


def _single(
    subscriptions: Iterable[ShotSubscription],
    *,
    kind: str,
    channel_uuid: str,
    shot_uuid: str = "",
) -> tuple[ShotSubscription | None, bool]:
    matches = [
        item
        for item in subscriptions
        if item.enabled
        and item.kind == kind
        and item.channel_uuid == channel_uuid
        and (not shot_uuid or item.shot_uuid == shot_uuid)
    ]
    return (matches[0] if len(matches) == 1 else None), len(matches) > 1


def _subscription_is_authoritative(subscription: ShotSubscription) -> bool:
    fingerprint = (
        subscription.kind,
        subscription.enabled,
        subscription.channel_uuid,
        subscription.shot_uuid,
    )
    with _ROUTING_LOCK:
        return _AUTHORITATIVE_FINGERPRINTS.get(subscription.node) == fingerprint


def _subscription_requires_authority(subscription: ShotSubscription) -> bool:
    # ImageAsset never has an Only mode, so even its constructor-default
    # channel can invalidate every downstream subscriber if treated as final.
    # Disabled blank recipients are legitimate standalone/waiting nodes and do
    # not need to delay an unrelated Shot chain.
    return bool(
        subscription.kind == KIND_IMAGE_ASSET
        or subscription.enabled
        or subscription.channel_uuid
        or subscription.shot_uuid
    )


def reconcile_shot_routing(
    node: Any,
    *,
    _allow_unready_cleanup: bool = False,
) -> dict[str, Any]:
    """Reconcile all automatic Shot edges in ``node``'s current flow.

    The function is deliberately idempotent and re-entry guarded.  It performs
    no work for unregistered constructor instances or for old workflows whose
    nodes have not opted into Shot routing.
    """

    flow_name, nodes = _same_flow_nodes(node)
    if not flow_name:
        return {"ok": True, "code": "not_registered", "changed": 0}

    # Constructor-side helpers can call the reconciler before NodeManager owns
    # the object.  Only a registered caller may publish authoritative state.
    if not bool(getattr(node, "_hmb_node_deleted", False)):
        _mark_authoritative(node)

    with _claim_routing_flow(flow_name) as claimed:
        if not claimed:
            return {"ok": True, "code": "reentrant", "changed": 0}
        # A second thread may have waited for a pass that began before its
        # state mutation. Re-read the retained flow only after it owns the
        # same-flow gate so that its pass observes the newest nodes and values.
        current_flow_name, nodes = _same_flow_nodes(node)
        if not current_flow_name:
            return {"ok": True, "code": "not_registered", "changed": 0}
        if current_flow_name != flow_name:
            # Never mutate a newly moved flow while holding the old flow's
            # gate. Host move/registration hooks will reconcile the new owner.
            return {"ok": True, "code": "flow_changed", "changed": 0}
        previous_incoming_cache = getattr(
            _ROUTING_PASS_LOCAL, "incoming_by_node", None
        )
        _ROUTING_PASS_LOCAL.incoming_by_node = {}
        try:
            values = [item for item in (_subscription_for(value) for value in nodes) if item is not None]
            by_name = {item.node_name: item for item in values}
            changed = 0
            failures: list[str] = []
            catalog_rejected_node_ids: set[int] = set()
            duplicate_prompt_conflict = False

            # Workflow files create every node first and replay serialized
            # values later.  Never let one hydrated Prompt observe a temporary
            # Image channel and erase its saved Shot selection.  The last
            # authoritative participant generation performs the full pass.
            if not _allow_unready_cleanup:
                waiting = [
                    item.node_name
                    for item in values
                    if _subscription_requires_authority(item)
                    and not _subscription_is_authoritative(item)
                ]
                if waiting:
                    return _ReconcileResult(
                        {
                            "ok": True,
                            "code": "hydration_pending",
                            "changed": 0,
                            "waiting": tuple(waiting),
                        },
                        covered_node_ids=(id(value) for value in nodes),
                    )

            # Compact catalog reconciliation occurs before edge changes so the
            # participant UI can update names without storing media payloads.
            all_image_sources = [
                item for item in values if item.kind == KIND_IMAGE_ASSET
            ]
            image_sources = [item for item in all_image_sources if item.enabled]
            image_sources_by_channel: dict[str, list[ShotSubscription]] = {}
            for source in image_sources:
                image_sources_by_channel.setdefault(source.channel_uuid, []).append(source)
            known_image_channels = {
                item.channel_uuid for item in all_image_sources if item.channel_uuid
            }

            def standalone_picker_catalogs_for(
                subscriptions: Iterable[ShotSubscription],
            ) -> list[tuple[ShotSubscription, dict[str, Any]]]:
                catalogs: list[tuple[ShotSubscription, dict[str, Any]]] = []
                if image_sources:
                    return catalogs
                for candidate in subscriptions:
                    if candidate.kind != KIND_VIDEO_PICKER or not candidate.enabled:
                        continue
                    getter = getattr(
                        candidate.node,
                        "_hmb_standalone_shot_routing_catalog",
                        None,
                    )
                    if not callable(getter):
                        continue
                    try:
                        catalog = getter()
                    except Exception:
                        continue
                    if (
                        not isinstance(catalog, dict)
                        or catalog.get("schema") != "hmb-shot-routing-catalog"
                        or catalog.get("version") != 1
                        or _clean(catalog.get("channel_uuid"), 128)
                        != candidate.channel_uuid
                        or not isinstance(catalog.get("shots"), list)
                        or not catalog["shots"]
                    ):
                        continue
                    catalogs.append((candidate, catalog))
                return catalogs

            standalone_picker_catalogs = standalone_picker_catalogs_for(values)
            standalone_picker_channels = {
                source.channel_uuid for source, _catalog in standalone_picker_catalogs
            }

            # A removed/reloaded ImageAsset used to leave its former channel
            # UUID in every subscriber.  A newly created publisher then looked
            # foreign forever, while old hidden edges could keep invalidating
            # the graph.  Picker, Prompt and Agent may return to their explicit
            # ``Only`` state. Seedance also has a genuine prompt-only mode, and
            # may additionally use a standalone VideoPicker catalog when no
            # ImageAsset publisher exists.
            for recipient in tuple(values):
                if recipient.kind == KIND_IMAGE_ASSET:
                    continue
                publisher_available = bool(
                    recipient.channel_uuid in known_image_channels
                    or (
                        recipient.kind in {KIND_VIDEO_PICKER, KIND_SEEDANCE}
                        and recipient.channel_uuid in standalone_picker_channels
                    )
                )
                orphaned = bool(
                    recipient.enabled
                    and not publisher_available
                )
                stale_disabled_channel = bool(
                    not recipient.enabled
                    and recipient.channel_uuid
                    and recipient.channel_uuid not in known_image_channels
                )
                ambiguous_blank = bool(
                    not recipient.enabled and len(image_sources) != 1
                )
                if not orphaned and not stale_disabled_channel and not ambiguous_blank:
                    continue
                if orphaned or recipient.kind == KIND_SEEDANCE:
                    removed, clear_failures = _clear_remote_edges(
                        recipient, by_name
                    )
                    changed += removed
                    failures.extend(
                        f"{recipient.node_name}: {detail}"
                        for detail in clear_failures
                    )
                if recipient.kind == KIND_SEEDANCE:
                    # Seedance has a real prompt-only mode.  Removing managed
                    # edges without clearing its durable Shot quartet produced a
                    # false "Only" status while execution still tried the
                    # orphaned channel.  Clear the catalog first; the node-owned
                    # callback preserves the manual public prompt.
                    _clear_remote_catalog(
                        recipient.node,
                        "publisher_unavailable" if not image_sources else "channel_replaced",
                    )
                    _notify_status(
                        recipient.node,
                        ok=True,
                        code="only",
                        details="No media Shot publisher is active; prompt-only mode is available.",
                    )
                    continue
                if (
                    recipient.kind == KIND_VIDEO_PICKER
                    and orphaned
                    and len(image_sources) == 1
                ):
                    # Preserve the retired channel long enough for the narrow
                    # replacement callback to prove and atomically migrate the
                    # Picker's workspaces.  Clearing it here would erase the
                    # only evidence that distinguishes replacement from an
                    # ordinary new catalog and could delete owned media.
                    _notify_status(
                        recipient.node,
                        ok=False,
                        code="publisher_rebinding",
                        details="A sole ImageAsset replacement is being verified.",
                    )
                    continue
                _clear_remote_catalog(
                    recipient.node,
                    "publisher_unavailable" if not image_sources else "channel_replaced",
                )
                _notify_status(
                    recipient.node,
                    ok=True,
                    code="only",
                    details="Remote Shot publisher is unavailable; local-only mode is active.",
                )

            # Catalog-clear callbacks can change the durable subscription.
            # Re-read before deciding which publisher may advertise options.
            values = [
                item
                for item in (_subscription_for(value) for value in nodes)
                if item is not None
            ]
            by_name = {item.node_name: item for item in values}
            image_sources = [
                item
                for item in values
                if item.kind == KIND_IMAGE_ASSET and item.enabled
            ]
            image_sources_by_channel = {}
            for source in image_sources:
                image_sources_by_channel.setdefault(source.channel_uuid, []).append(source)
            standalone_picker_catalogs = standalone_picker_catalogs_for(values)
            unique_image_sources = [
                group[0] for group in image_sources_by_channel.values() if len(group) == 1
            ]
            pre_catalog_values = tuple(values)
            pre_catalog_by_name = dict(by_name)
            # A Prompt may synchronously resolve both exact publishers from
            # inside its compact-catalog callback.  Deliver the same ImageAsset
            # generation to VideoPicker first so a Shot add/rename/delete can
            # never make Prompt compare new ImageAsset metadata with an older
            # Picker snapshot merely because of arbitrary flow iteration
            # order.  UUID/name ordering keeps peers of the same kind stable.
            catalog_recipients = sorted(
                values,
                key=lambda item: (
                    {
                        KIND_VIDEO_PICKER: 0,
                        KIND_PROMPT: 1,
                        KIND_AGENT: 2,
                        KIND_SEEDANCE: 3,
                        KIND_IMAGE_ASSET: 4,
                    }.get(item.kind, 5),
                    item.node_name,
                ),
            )
            for source in unique_image_sources:
                snapshot_getter = getattr(source.node, "_hmb_shot_routing_catalog", None)
                if not callable(snapshot_getter):
                    continue
                try:
                    snapshot = snapshot_getter()
                except Exception:
                    continue
                if (
                    not isinstance(snapshot, dict)
                    or _clean(snapshot.get("channel_uuid"), 128)
                    != source.channel_uuid
                ):
                    continue
                for recipient in catalog_recipients:
                    if recipient.node is source.node:
                        continue
                    orphan_replacement = False
                    if recipient.channel_uuid and recipient.channel_uuid != source.channel_uuid:
                        orphan_replacement = bool(
                            recipient.kind in {KIND_VIDEO_PICKER, KIND_SEEDANCE}
                            and recipient.channel_uuid not in {
                                item.channel_uuid for item in image_sources
                            }
                            and len(image_sources) == 1
                        )
                        if not orphan_replacement:
                            continue
                    # An unconfigured subscriber may discover the available
                    # catalog only when the flow has one unambiguous
                    # ImageAsset publisher. A freshly registered Prompt may
                    # adopt the publisher's active Shot through its guarded
                    # one-shot hook; hydrated/saved Prompts keep their stored
                    # selection. Picker and Agent otherwise retain their own
                    # subscription, while Seedance adopts the first valid
                    # remote Shot because it has no standalone mode.
                    if not recipient.channel_uuid and len(image_sources) != 1:
                        continue
                    if recipient.kind == KIND_PROMPT and not recipient.channel_uuid:
                        prepare_initial = getattr(
                            recipient.node,
                            "_hmb_prepare_initial_shot_selection",
                            None,
                        )
                        if callable(prepare_initial):
                            try:
                                live_values = [
                                    item
                                    for item in (
                                        _subscription_for(value)
                                        for value in nodes
                                    )
                                    if item is not None
                                ]
                                claimed_prompt_shots = {
                                    item.shot_uuid
                                    for item in live_values
                                    if item.kind == KIND_PROMPT
                                    and item.node is not recipient.node
                                    and item.enabled
                                    and item.channel_uuid == source.channel_uuid
                                }
                                available_prompt_shots = [
                                    item
                                    for item in snapshot.get("shots", [])
                                    if isinstance(item, dict)
                                    and _clean(item.get("shot_uuid"), 128)
                                    not in claimed_prompt_shots
                                ]
                                preferred_prompt = next(
                                    (
                                        item
                                        for item in available_prompt_shots
                                        if _clean(item.get("shot_uuid"), 128)
                                        == source.shot_uuid
                                    ),
                                    available_prompt_shots[0]
                                    if available_prompt_shots
                                    else {},
                                )
                                prepare_initial(
                                    _clean(
                                        preferred_prompt.get("shot_uuid"),
                                        128,
                                    )
                                )
                            except Exception:
                                pass
                    if recipient.kind == KIND_AGENT and not recipient.channel_uuid:
                        # A newly added Agent follows one already-selected,
                        # unclaimed Prompt Shot immediately. Multiple possible
                        # Prompt targets remain explicit/ambiguous and keep the
                        # Agent in Only rather than guessing by node order.
                        live_values = [
                            item
                            for item in (
                                _subscription_for(value) for value in nodes
                            )
                            if item is not None
                        ]
                        claimed_agent_shots = {
                            item.shot_uuid
                            for item in live_values
                            if item.kind == KIND_AGENT
                            and item.node is not recipient.node
                            and item.enabled
                            and item.channel_uuid == source.channel_uuid
                        }
                        prompt_candidates = [
                            item
                            for item in live_values
                            if item.kind == KIND_PROMPT
                            and item.enabled
                            and item.channel_uuid == source.channel_uuid
                            and item.shot_uuid not in claimed_agent_shots
                        ]
                        if len(prompt_candidates) == 1:
                            prepare_initial = getattr(
                                recipient.node,
                                "_hmb_prepare_initial_shot_selection",
                                None,
                            )
                            if callable(prepare_initial):
                                try:
                                    prepare_initial(prompt_candidates[0].shot_uuid)
                                except Exception:
                                    pass
                    callback = getattr(
                        recipient.node,
                        (
                            "_hmb_reconcile_replacement_shot_routing"
                            if orphan_replacement
                            else "_hmb_reconcile_shot_routing"
                        ),
                        None,
                    )
                    if callable(callback):
                        try:
                            callback(snapshot)
                            _mark_authoritative(recipient.node)
                        except Exception as exc:
                            # Stale generations and same-generation hash
                            # conflicts are recipient contract failures, not a
                            # best-effort UI refresh. Keep that participant out
                            # of this pass so no old subscription can be marked
                            # ready or receive a newly managed edge.
                            detail = _clean(exc, 256) or exc.__class__.__name__
                            catalog_rejected_node_ids.add(id(recipient.node))
                            failures.append(
                                f"{recipient.node_name}: catalog_rejected: {detail}"
                            )
                            _notify_status(
                                recipient.node,
                                ok=False,
                                code="catalog_rejected",
                                details=detail,
                            )

            # With no ImageAsset, one standalone VideoPicker is a bounded Shot
            # publisher for Seedance only. Prompt/Agent continue to use
            # ImageAsset as their catalog authority.
            if not image_sources and len(standalone_picker_catalogs) == 1:
                source, snapshot = standalone_picker_catalogs[0]
                for recipient in catalog_recipients:
                    if recipient.kind != KIND_SEEDANCE:
                        continue
                    replacement = bool(
                        recipient.channel_uuid
                        and recipient.channel_uuid != source.channel_uuid
                    )
                    callback = getattr(
                        recipient.node,
                        (
                            "_hmb_reconcile_replacement_shot_routing"
                            if replacement
                            else "_hmb_reconcile_shot_routing"
                        ),
                        None,
                    )
                    if not callable(callback):
                        continue
                    try:
                        callback(snapshot)
                        _mark_authoritative(recipient.node)
                    except Exception as exc:
                        detail = _clean(exc, 256) or exc.__class__.__name__
                        catalog_rejected_node_ids.add(id(recipient.node))
                        failures.append(
                            f"{recipient.node_name}: catalog_rejected: {detail}"
                        )
                        _notify_status(
                            recipient.node,
                            ok=False,
                            code="catalog_rejected",
                            details=detail,
                        )

            # A catalog callback can invalidate a selected Shot after the
            # publisher deletes it.  Remove the old remote-owned edges while
            # the previous subscription still proves their ownership.  Blank
            # discovery callbacks must never remove a user's manual legacy
            # connection, so only an enabled -> disabled transition qualifies.
            values = [
                item
                for item in (_subscription_for(value) for value in nodes)
                if item is not None
            ]
            by_name = {item.node_name: item for item in values}
            post_catalog_by_name = {item.node_name: item for item in values}
            for rejected in tuple(values):
                if id(rejected.node) not in catalog_rejected_node_ids:
                    continue
                removed, clear_failures = _clear_remote_edges(
                    rejected, by_name
                )
                changed += removed
                failures.extend(
                    f"{rejected.node_name}: {detail}"
                    for detail in clear_failures
                )
            for previous in pre_catalog_values:
                if previous.kind == KIND_IMAGE_ASSET or not previous.enabled:
                    continue
                current = post_catalog_by_name.get(previous.node_name)
                if current is not None and current.enabled:
                    continue
                removed, clear_failures = _clear_remote_edges(
                    previous, pre_catalog_by_name
                )
                changed += removed
                failures.extend(
                    f"{previous.node_name}: {detail}"
                    for detail in clear_failures
                )

            # Explicitly choosing ``Only`` does not pass through a catalog
            # callback, so there is no enabled -> disabled snapshot above.
            # Prompt uses dedicated hidden remote inputs; clearing those exact
            # HMB edges is safe and prevents inactive upstream invalidations.
            # A blank Seedance is remote-waiting, never Only, but its hidden
            # stale routes are likewise safe to clear.
            # Agent keeps public ``prompt`` exclusively for native Only mode;
            # only its dedicated hidden SHOT_PROMPT_IN route is managed here.
            for recipient in tuple(values):
                if recipient.enabled:
                    continue
                if recipient.kind not in {KIND_PROMPT, KIND_AGENT, KIND_SEEDANCE}:
                    continue
                removed, clear_failures = _clear_remote_edges(
                    recipient, by_name
                )
                changed += removed
                failures.extend(
                    f"{recipient.node_name}: {detail}"
                    for detail in clear_failures
                )

            # One Prompt owns one Shot in one flow.  Never use node age/name as
            # an ownership guess.  A restored exact Prompt -> Agent edge may
            # prove one established owner; otherwise every duplicate claimant
            # returns to Only so the user can choose an available Shot again.
            prompt_groups: dict[tuple[str, str], list[ShotSubscription]] = {}
            for prompt in values:
                if (
                    prompt.kind == KIND_PROMPT
                    and prompt.enabled
                    and id(prompt.node) not in catalog_rejected_node_ids
                ):
                    prompt_groups.setdefault(
                        (prompt.channel_uuid, prompt.shot_uuid), []
                    ).append(prompt)
            for key, contenders in prompt_groups.items():
                if len(contenders) < 2:
                    continue
                contender_by_name = {
                    contender.node_name: contender for contender in contenders
                }
                established_names: set[str] = set()
                for agent in values:
                    if (
                        agent.kind != KIND_AGENT
                        or not agent.enabled
                        or (agent.channel_uuid, agent.shot_uuid) != key
                    ):
                        continue
                    established_names.update(
                        str(getattr(connection, "source_node_name", ""))
                        for connection in _incoming_connections(agent.node)
                        if str(getattr(connection, "target_parameter_name", ""))
                        == "SHOT_PROMPT_IN"
                        and str(getattr(connection, "source_parameter_name", ""))
                        == "PROMPT_OUT"
                        and str(getattr(connection, "source_node_name", ""))
                        in contender_by_name
                    )
                owner_name = (
                    next(iter(established_names))
                    if len(established_names) == 1
                    else ""
                )
                rejected_prompts = [
                    contender
                    for contender in contenders
                    if not owner_name or contender.node_name != owner_name
                ]
                for rejected_prompt in rejected_prompts:
                    removed, clear_failures = _clear_remote_edges(
                        rejected_prompt, by_name
                    )
                    changed += removed
                    failures.extend(
                        f"{rejected_prompt.node_name}: {detail}"
                        for detail in clear_failures
                    )
                    cleared_to_only = _reject_duplicate_prompt_selection(
                        rejected_prompt.node
                    )
                    detail = (
                        "duplicate Prompt Shot claim rejected; Only mode is active"
                        if cleared_to_only
                        else "duplicate Prompt Shot claim is ambiguous"
                    )
                    if not cleared_to_only or not owner_name:
                        duplicate_prompt_conflict = True
                        failures.append(
                            f"{rejected_prompt.node_name}: duplicate_prompt"
                        )
                    _notify_status(
                        rejected_prompt.node,
                        ok=bool(cleared_to_only and owner_name),
                        code=(
                            "only"
                            if cleared_to_only and owner_name
                            else "duplicate_prompt"
                        ),
                        details=detail,
                    )

            # Selection-rejection callbacks are deliberately non-recursive but
            # can change durable subscriptions.  Re-read before deciding which
            # Prompt inputs or downstream chain may be built.
            values = [
                item
                for item in (_subscription_for(value) for value in nodes)
                if item is not None
            ]
            by_name = {item.node_name: item for item in values}
            routable_values = [
                item
                for item in values
                if id(item.node) not in catalog_rejected_node_ids
            ]
            remaining_prompt_groups: dict[
                tuple[str, str], list[ShotSubscription]
            ] = {}
            for prompt in routable_values:
                if prompt.kind == KIND_PROMPT and prompt.enabled:
                    remaining_prompt_groups.setdefault(
                        (prompt.channel_uuid, prompt.shot_uuid), []
                    ).append(prompt)
            unresolved_prompt_ids: set[int] = set()
            for contenders in remaining_prompt_groups.values():
                if len(contenders) < 2:
                    continue
                duplicate_prompt_conflict = True
                for contender in contenders:
                    unresolved_prompt_ids.add(id(contender.node))
                    removed, clear_failures = _clear_remote_edges(
                        contender, by_name
                    )
                    changed += removed
                    failures.extend(
                        f"{contender.node_name}: {detail}"
                        for detail in clear_failures
                    )
                    duplicate_failure = f"{contender.node_name}: duplicate_prompt"
                    if duplicate_failure not in failures:
                        failures.append(duplicate_failure)
                    _notify_status(
                        contender.node,
                        ok=False,
                        code="duplicate_prompt",
                        details=(
                            "Duplicate Prompt Shot ownership is ambiguous; "
                            "automatic routing is disabled."
                        ),
                    )

            # Agent ownership is also exactly 1:1 per Shot.  Never choose an
            # Agent merely because it was registered first.  A saved exact
            # Seedance <- Agent edge is the only admissible tie breaker; it
            # preserves that established pair and returns additional claimants
            # to Only.  With no exact edge, every duplicate stays fail-closed.
            agent_groups: dict[tuple[str, str], list[ShotSubscription]] = {}
            for agent in routable_values:
                if agent.kind == KIND_AGENT and agent.enabled:
                    agent_groups.setdefault(
                        (agent.channel_uuid, agent.shot_uuid), []
                    ).append(agent)
            for key, contenders in agent_groups.items():
                if len(contenders) < 2:
                    continue
                contender_by_name = {
                    contender.node_name: contender for contender in contenders
                }
                established_names: set[str] = set()
                for seedance in routable_values:
                    if (
                        seedance.kind != KIND_SEEDANCE
                        or not seedance.enabled
                        or (seedance.channel_uuid, seedance.shot_uuid) != key
                    ):
                        continue
                    established_names.update(
                        str(getattr(connection, "source_node_name", ""))
                        for connection in _incoming_connections(seedance.node)
                        if str(getattr(connection, "target_parameter_name", ""))
                        == "SHOT_PROMPT_IN"
                        and str(getattr(connection, "source_parameter_name", ""))
                        == "output"
                        and str(getattr(connection, "source_node_name", ""))
                        in contender_by_name
                    )
                if len(established_names) != 1:
                    continue
                owner_name = next(iter(established_names))
                for rejected_agent in contenders:
                    if rejected_agent.node_name == owner_name:
                        continue
                    removed, clear_failures = _clear_remote_edges(
                        rejected_agent, by_name
                    )
                    changed += removed
                    failures.extend(
                        f"{rejected_agent.node_name}: {detail}"
                        for detail in clear_failures
                    )
                    if _reject_duplicate_agent_selection(rejected_agent.node):
                        _notify_status(
                            rejected_agent.node,
                            ok=True,
                            code="only",
                            details=(
                                "Another Agent owns this Shot's exact "
                                "Seedance route; Only mode is active."
                            ),
                        )

            # The narrow callback can change Agent subscriptions. Re-read and
            # mark any unresolved duplicate group before building dependencies.
            values = [
                item
                for item in (_subscription_for(value) for value in nodes)
                if item is not None
            ]
            by_name = {item.node_name: item for item in values}
            routable_values = [
                item
                for item in values
                if id(item.node) not in catalog_rejected_node_ids
            ]
            unresolved_agent_ids: set[int] = set()
            remaining_agent_groups: dict[
                tuple[str, str], list[ShotSubscription]
            ] = {}
            for agent in routable_values:
                if agent.kind == KIND_AGENT and agent.enabled:
                    remaining_agent_groups.setdefault(
                        (agent.channel_uuid, agent.shot_uuid), []
                    ).append(agent)
            for contenders in remaining_agent_groups.values():
                if len(contenders) < 2:
                    continue
                for contender in contenders:
                    unresolved_agent_ids.add(id(contender.node))
                    removed, clear_failures = _clear_remote_edges(
                        contender, by_name
                    )
                    changed += removed
                    failures.extend(
                        f"{contender.node_name}: {detail}"
                        for detail in clear_failures
                    )
                    failure = f"{contender.node_name}: duplicate_agent"
                    if failure not in failures:
                        failures.append(failure)
                    _notify_status(
                        contender.node,
                        ok=False,
                        code="duplicate_agent",
                        details=(
                            "Duplicate Agent Shot ownership is ambiguous; "
                            "select a different available Shot."
                        ),
                    )

            # Prompt dependencies: one ImageAsset publisher per channel and one
            # optional VideoPicker publisher per channel.  Unresolved duplicate
            # groups stay fail-closed even if an older Prompt lacks the narrow
            # selection-rejection callback.
            prompts = [
                item
                for item in routable_values
                if item.kind == KIND_PROMPT
                and item.enabled
                and id(item.node) not in unresolved_prompt_ids
            ]
            for prompt in prompts:
                prompt_failures: list[str] = []
                image, image_duplicate = _single(
                    routable_values,
                    kind=KIND_IMAGE_ASSET,
                    channel_uuid=prompt.channel_uuid,
                )
                picker, picker_duplicate = _single(
                    routable_values,
                    kind=KIND_VIDEO_PICKER,
                    channel_uuid=prompt.channel_uuid,
                )
                if image_duplicate or image is None:
                    removed, detail = _clear_hmb_route(
                        prompt.node,
                        "SHOT_ASSET_IN",
                        by_name,
                        source_parameter="SHOT_ASSET_OUT",
                    )
                    changed += removed
                    if detail.startswith("unable"):
                        prompt_failures.append(detail)
                    prompt_failures.append(
                        "duplicate upstream publisher"
                        if image_duplicate
                        else "image publisher unavailable"
                    )
                else:
                    edge = ShotEdge(
                        image.node, "SHOT_ASSET_OUT", prompt.node, "SHOT_ASSET_IN"
                    )
                    ok, detail = _ensure_edge(edge, by_name)
                    changed += int(ok and detail == "created")
                    if not ok:
                        prompt_failures.append(detail)

                if picker_duplicate or picker is None:
                    removed, detail = _clear_hmb_route(
                        prompt.node,
                        "SHOT_PICKER_IN",
                        by_name,
                        source_parameter="SHOT_PICKER_OUT",
                    )
                    changed += removed
                    if detail.startswith("unable"):
                        prompt_failures.append(detail)
                    rejected_picker = any(
                        item.kind == KIND_VIDEO_PICKER
                        and item.channel_uuid == prompt.channel_uuid
                        and id(item.node) in catalog_rejected_node_ids
                        for item in values
                    )
                    if rejected_picker:
                        prompt_failures.append("video picker catalog rejected")
                    elif picker_duplicate:
                        prompt_failures.append("duplicate upstream publisher")
                else:
                    edge = ShotEdge(
                        picker.node, "SHOT_PICKER_OUT", prompt.node, "SHOT_PICKER_IN"
                    )
                    ok, detail = _ensure_edge(edge, by_name)
                    changed += int(ok and detail == "created")
                    if not ok:
                        prompt_failures.append(detail)

                failures.extend(
                    f"{prompt.node_name}: {detail}" for detail in prompt_failures
                )
                _notify_status(
                    prompt.node,
                    ok=not prompt_failures,
                    code="ready" if not prompt_failures else "route_incomplete",
                )
                if not prompt_failures:
                    finalize_initial = getattr(
                        prompt.node,
                        "_hmb_finalize_initial_shot_discovery",
                        None,
                    )
                    if callable(finalize_initial):
                        try:
                            finalize_initial()
                        except Exception as exc:
                            detail = _clean(exc, 256) or exc.__class__.__name__
                            failures.append(
                                f"{prompt.node_name}: initial_sync_failed: {detail}"
                            )
                            _notify_status(
                                prompt.node,
                                ok=False,
                                code="initial_sync_failed",
                                details=detail,
                            )

            # Agent input is the exact Prompt selected for the same Shot.
            agents = [
                item
                for item in routable_values
                if item.kind == KIND_AGENT
                and item.enabled
                and id(item.node) not in unresolved_agent_ids
            ]
            for agent in agents:
                prompt, duplicate = _single(
                    routable_values,
                    kind=KIND_PROMPT,
                    channel_uuid=agent.channel_uuid,
                    shot_uuid=agent.shot_uuid,
                )
                if duplicate or prompt is None:
                    code = "duplicate_prompt" if duplicate else "prompt_unavailable"
                    failures.append(f"{agent.node_name}: {code}")
                    removed, detail = _clear_hmb_route(
                        agent.node,
                        "SHOT_PROMPT_IN",
                        by_name,
                        source_parameter="PROMPT_OUT",
                    )
                    changed += removed
                    if detail.startswith("unable"):
                        failures.append(f"{agent.node_name}: {detail}")
                    _notify_status(agent.node, ok=False, code=code)
                    continue
                ok, detail = _ensure_edge(
                    ShotEdge(
                        prompt.node,
                        "PROMPT_OUT",
                        agent.node,
                        "SHOT_PROMPT_IN",
                    ),
                    by_name,
                )
                changed += int(ok and detail == "created")
                if ok:
                    # Restored workflows can already own the exact hidden edge.
                    # In that case the host does not fire
                    # ``after_incoming_connection`` again, so the Agent's
                    # non-serializable SHOT_PROMPT_IN value would remain empty
                    # until the user touched Prompt.  Hydrate from the exact
                    # proven source for both existing and newly-created edges;
                    # the callback is idempotent and does not compile Prompt.
                    hydrate = getattr(
                        agent.node,
                        "_hmb_hydrate_shot_prompt_from_source",
                        None,
                    )
                    if callable(hydrate):
                        try:
                            if hydrate(prompt.node, "PROMPT_OUT") is not True:
                                ok = False
                                detail = "unable to hydrate exact Prompt value"
                        except Exception:
                            ok = False
                            detail = "unable to hydrate exact Prompt value"
                if not ok:
                    failures.append(f"{agent.node_name}: {detail}")
                _notify_status(agent.node, ok=ok, code="ready" if ok else "route_incomplete")

            # Seedance prompt input is intentionally manual. Hidden routing only
            # supplies exact ImageAsset and VideoPicker sources for its Shot.
            unresolved_seedance_ids: set[int] = set()
            seedance_groups: dict[
                tuple[str, str], list[ShotSubscription]
            ] = {}
            for target in routable_values:
                if target.kind == KIND_SEEDANCE and target.enabled:
                    seedance_groups.setdefault(
                        (target.channel_uuid, target.shot_uuid), []
                    ).append(target)
            for contenders in seedance_groups.values():
                if len(contenders) < 2:
                    continue
                for contender in contenders:
                    removed, clear_failures = _clear_remote_edges(
                        contender, by_name
                    )
                    changed += removed
                    failures.extend(
                        f"{contender.node_name}: {detail}"
                        for detail in clear_failures
                    )
                    reject = getattr(
                        contender.node,
                        "_hmb_reject_duplicate_shot_selection",
                        None,
                    )
                    rejected = False
                    if callable(reject):
                        try:
                            subscription = reject("duplicate_seedance_shot")
                            rejected = bool(
                                isinstance(subscription, dict)
                                and not subscription.get("enabled")
                            )
                        except Exception:
                            rejected = False
                    if rejected:
                        _notify_status(
                            contender.node,
                            ok=True,
                            code="only",
                            details=(
                                "Duplicate Seedance Shot ownership was rejected; "
                                "Only mode is active."
                            ),
                        )
                    else:
                        unresolved_seedance_ids.add(id(contender.node))
                        failures.append(
                            f"{contender.node_name}: duplicate_seedance_shot"
                        )
                        _notify_status(
                            contender.node,
                            ok=False,
                            code="duplicate_seedance_shot",
                            details=(
                                "Another Seedance generator already owns this Shot."
                            ),
                        )

            # Rejection callbacks change the durable quartet.  Re-read before
            # constructing media edges so a node returned to Only cannot retain
            # an edge from the just-rejected Shot.
            values = [
                item
                for item in (_subscription_for(value) for value in nodes)
                if item is not None
            ]
            by_name = {item.node_name: item for item in values}
            routable_values = [
                item
                for item in values
                if id(item.node) not in catalog_rejected_node_ids
            ]

            seedance_nodes = [
                item
                for item in routable_values
                if item.kind == KIND_SEEDANCE
                and item.enabled
                and id(item.node) not in unresolved_seedance_ids
            ]
            for target in seedance_nodes:
                image, image_duplicate = _single(
                    routable_values,
                    kind=KIND_IMAGE_ASSET,
                    channel_uuid=target.channel_uuid,
                )
                picker, picker_duplicate = _single(
                    routable_values,
                    kind=KIND_VIDEO_PICKER,
                    channel_uuid=target.channel_uuid,
                )
                source_rejected = bool(
                    image is not None and id(image.node) in catalog_rejected_node_ids
                    or picker is not None and id(picker.node) in catalog_rejected_node_ids
                )
                if (
                    image_duplicate
                    or picker_duplicate
                    or (image is None and picker is None)
                    or source_rejected
                ):
                    code = (
                        "duplicate_shot_source"
                        if (image_duplicate or picker_duplicate)
                        else "shot_source_unavailable"
                    )
                    failures.append(f"{target.node_name}: {code}")
                    for target_parameter, source_parameter in (
                        ("SHOT_ASSET_IN", "SHOT_ASSET_OUT"),
                        ("SHOT_PICKER_IN", "SHOT_PICKER_OUT"),
                        # Remove saved automatic Agent/Prompt routes without
                        # touching the public manual `prompt` parameter.
                        ("SHOT_PROMPT_IN", "output"),
                        ("SHOT_IMAGE_IN", "SHOT_IMAGE_OUT"),
                        ("SHOT_VIDEO_IN", "SHOT_VIDEO_OUT"),
                    ):
                        removed, detail = _clear_hmb_route(
                            target.node,
                            target_parameter,
                            by_name,
                            source_parameter=source_parameter,
                        )
                        changed += removed
                        if detail.startswith("unable"):
                            failures.append(f"{target.node_name}: {detail}")
                    _notify_status(target.node, ok=False, code=code)
                    continue
                # Always retire legacy automatic prompt/media connections before
                # creating the two direct source dependencies.
                for target_parameter, source_parameter in (
                    ("SHOT_PROMPT_IN", "output"),
                    ("SHOT_IMAGE_IN", "SHOT_IMAGE_OUT"),
                    ("SHOT_VIDEO_IN", "SHOT_VIDEO_OUT"),
                ):
                    removed, detail = _clear_hmb_route(
                        target.node,
                        target_parameter,
                        by_name,
                        source_parameter=source_parameter,
                    )
                    changed += removed
                    if detail.startswith("unable"):
                        failures.append(f"{target.node_name}: {detail}")
                for source, source_parameter, target_parameter in (
                    (image, "SHOT_ASSET_OUT", "SHOT_ASSET_IN"),
                    (picker, "SHOT_PICKER_OUT", "SHOT_PICKER_IN"),
                ):
                    if source is None:
                        removed, detail = _clear_hmb_route(
                            target.node,
                            target_parameter,
                            by_name,
                            source_parameter=source_parameter,
                        )
                        changed += removed
                        if detail.startswith("unable"):
                            failures.append(f"{target.node_name}: {detail}")
                        continue
                    ok, detail = _ensure_edge(
                        ShotEdge(
                            source.node,
                            source_parameter,
                            target.node,
                            target_parameter,
                        ),
                        by_name,
                    )
                    changed += int(ok and detail == "created")
                    if not ok:
                        failures.append(f"{target.node_name}: {detail}")
                target_failed = any(item.startswith(target.node_name + ":") for item in failures)
                _notify_status(target.node, ok=not target_failed, code="ready" if not target_failed else "route_incomplete")

            return _ReconcileResult(
                {
                    "ok": not failures,
                    "code": (
                        "ready"
                        if not failures
                        else "duplicate_prompt"
                        if duplicate_prompt_conflict
                        else "incomplete"
                    ),
                    "changed": changed,
                    "failures": tuple(failures),
                },
                covered_node_ids=(id(value) for value in nodes),
            )
        finally:
            if previous_incoming_cache is None:
                try:
                    delattr(_ROUTING_PASS_LOCAL, "incoming_by_node")
                except AttributeError:
                    pass
            else:
                _ROUTING_PASS_LOCAL.incoming_by_node = previous_incoming_cache


__all__ = [
    "KIND_AGENT",
    "KIND_IMAGE_ASSET",
    "KIND_PROMPT",
    "KIND_SEEDANCE",
    "KIND_VIDEO_PICKER",
    "MAX_SHOTS",
    "SINGLETON_KINDS",
    "SHOT_ROUTING_PROTOCOL_VERSION",
    "SUBSCRIPTION_SCHEMA",
    "SUBSCRIPTION_VERSION",
    "prepare_node_deletion",
    "release_node_lifecycle",
    "reconcile_shot_routing",
    "schedule_post_deletion_reconcile",
    "schedule_post_hydration_reconcile",
    "schedule_post_registration_reconcile",
]
