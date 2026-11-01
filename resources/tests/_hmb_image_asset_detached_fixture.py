"""Constructor-owned admission fields for offline detached ImageAsset tests.

This initializes no SDK, filesystem, media resolver, background worker or
privileged assignment scope. Tests still call the production admission and
baseline methods; their live request payloads must carry the returned lease.
"""

from collections import OrderedDict
import contextvars
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4


def initialize_detached_image_asset(node, module, *, state=None, name=None):
    """Initialize a new ``object.__new__`` fixture and optionally accept state.

    Do not use this on constructed/registered nodes: it deliberately issues a
    new runtime lease, as the actual constructor does for a new owner.
    """
    if getattr(node, "_hmb_widget_runtime_lease", None):
        raise ValueError("Detached admission initialization requires a new owner.")
    node.name = name or getattr(node, "name", "SyntheticDetachedImageAsset")
    node.engine = SimpleNamespace(event_manager=SimpleNamespace(
        _hmb_asset_initial_assignment_context=contextvars.ContextVar(
            "fixture_asset_initial_assignment", default=None),
        _hmb_asset_workspace_assignment_context=contextvars.ContextVar(
            "fixture_asset_workspace_assignment", default=None),
    ))
    node._hmb_widget_runtime_lease = str(uuid4())
    node._hmb_workspace_local_assignment = contextvars.ContextVar(
        "fixture_asset_workspace_local", default=None)
    node._hmb_image_bash_mutation_receipts = OrderedDict()
    node._hmb_widget_constructing = False
    node._hmb_state_syncing = False
    node._hmb_restoring_widget_state = False
    node._hmb_thumbnail_bridge_syncing = False
    node._hmb_widget_live_authored = False
    node._hmb_widget_hydration_digest = ""
    node._hmb_last_accepted_widget_state = None
    node._hmb_last_accepted_widget_revisions = (0, 0)
    node._hmb_last_accepted_thumbnail_revision = 0
    if state is None:
        return None
    normalized = module._normalize_state(deepcopy(state))
    node._accept_normalized_widget_state_baseline(normalized)
    return normalized
