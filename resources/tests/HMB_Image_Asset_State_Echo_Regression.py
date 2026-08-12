from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
TEMP_ROOT = ROOT / ".tmp"
TEMP_ROOT.mkdir(parents=True, exist_ok=True)


with tempfile.TemporaryDirectory(prefix="hmb_asset_echo_", dir=TEMP_ROOT) as root:
    # Keep construction deterministic and offline under both fallback Python
    # and the exact bundled Griptape host runtime.
    os.environ["HMB_IMAGE_PROJECTS_ROOT"] = root
    module_path = ROOT / "HMBImageAssetLibrary.py"
    spec = importlib.util.spec_from_file_location(
        "hmb_image_asset_state_echo_regression",
        module_path,
    )
    assert spec is not None and spec.loader is not None
    asset = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = asset
    spec.loader.exec_module(asset)

    assert asset._default_state()[asset.UI_EDIT_REVISION_KEY] == 0
    assert asset._normalize_state(
        {asset.UI_EDIT_REVISION_KEY: asset.MAX_UI_EDIT_REVISION + 100}
    )[asset.UI_EDIT_REVISION_KEY] == asset.MAX_UI_EDIT_REVISION
    assert asset._normalize_state(
        {asset.UI_EDIT_REVISION_KEY: -100}
    )[asset.UI_EDIT_REVISION_KEY] == 0

    node = asset.HMBImageAssetLibrary(name="image_asset_state_echo")
    widget = asset._get_parameter_obj(node, asset.WIDGET_STATE_PARAMETER)
    initial = node._current_state()

    # B is accepted first. The delayed same-scan A transaction must be
    # canonicalized back to B before the host assigns or processes it.
    newer_b = dict(initial)
    newer_b["scan_revision"] = 10
    newer_b[asset.UI_EDIT_REVISION_KEY] = 2
    newer_b["search"] = "newer B"
    newer_b["language"] = "ko"
    stale_a = dict(newer_b)
    stale_a[asset.UI_EDIT_REVISION_KEY] = 1
    stale_a["search"] = "stale A"
    stale_a["language"] = "en"
    node.set_parameter_value(
        asset.WIDGET_STATE_PARAMETER,
        json.dumps(newer_b),
    )
    node.set_parameter_value(
        asset.WIDGET_STATE_PARAMETER,
        json.dumps(stale_a),
    )
    after_stale = node._current_state()
    assert after_stale[asset.UI_EDIT_REVISION_KEY] == 2
    assert after_stale["search"] == "newer B"
    assert after_stale["language"] == "ko"

    # Hosts may suppress after_value_set when before_value_set canonicalizes A
    # to the already-current B string. That suppressed callback must leave no
    # global rejection latch capable of weakening the next raw-bypass guard.
    suppressed_canonical = node.before_value_set(widget, json.dumps(stale_a))
    assert json.loads(suppressed_canonical)["search"] == "newer B"
    node.set_parameter_value(
        asset.WIDGET_STATE_PARAMETER,
        json.dumps(stale_a),
        skip_before_value_set=True,
    )
    after_suppressed_then_bypass = node._current_state()
    assert after_suppressed_then_bypass[asset.UI_EDIT_REVISION_KEY] == 2
    assert after_suppressed_then_bypass["search"] == "newer B"

    # Exercise the exact Griptape bypass: skip_before_value_set writes raw A,
    # then after_value_set must detect it, restore B, and skip all A side effects.
    node.set_parameter_value(
        asset.WIDGET_STATE_PARAMETER,
        json.dumps(stale_a),
        skip_before_value_set=True,
    )
    assert node._current_state()["search"] == "newer B"

    # Also cover host code that mutates the raw Parameter cache itself and
    # invokes only after_value_set. The hook must repair the cache before A is
    # visible to any output computation.
    if hasattr(node, "parameter_values"):
        node.parameter_values[asset.WIDGET_STATE_PARAMETER] = json.dumps(stale_a)
    else:
        widget.default_value = json.dumps(stale_a)
    node.after_value_set(widget, json.dumps(stale_a))
    after_raw_hook = node._current_state()
    assert after_raw_hook[asset.UI_EDIT_REVISION_KEY] == 2
    assert after_raw_hook["search"] == "newer B"

    # scan_revision is backend authority: a newer scan wins even with a lower
    # local counter, while an older scan loses even with a larger local value.
    authoritative_scan = dict(stale_a)
    authoritative_scan["scan_revision"] = 11
    authoritative_scan[asset.UI_EDIT_REVISION_KEY] = 0
    authoritative_scan["search"] = "authoritative scan"
    node.set_parameter_value(
        asset.WIDGET_STATE_PARAMETER,
        json.dumps(authoritative_scan),
    )
    assert node._current_state()["search"] == "authoritative scan"
    old_scan = dict(authoritative_scan)
    old_scan["scan_revision"] = 10
    old_scan[asset.UI_EDIT_REVISION_KEY] = 999
    old_scan["search"] = "obsolete scan"
    node.set_parameter_value(
        asset.WIDGET_STATE_PARAMETER,
        json.dumps(old_scan),
    )
    assert node._current_state()["search"] == "authoritative scan"

    # Workflow hydration starts a new instance-local baseline. It may restore
    # revisions below the live values and bypasses normal before/after hooks.
    hydrated = dict(authoritative_scan)
    hydrated["scan_revision"] = 3
    hydrated[asset.UI_EDIT_REVISION_KEY] = 4
    hydrated["search"] = "saved hydration"
    node.set_parameter_value(
        asset.WIDGET_STATE_PARAMETER,
        json.dumps(hydrated),
        initial_setup=True,
    )
    assert node._current_state()["search"] == "saved hydration"
    assert node._hmb_last_accepted_widget_revisions == (3, 4)

    # Python/backend publication remains authoritative. A fresh scan preserves
    # the UI revision while advancing scan_revision and cannot be rejected by
    # the local stale-echo guard.
    refreshed = dict(hydrated)
    refreshed["scan_revision"] = 4
    refreshed["search"] = "scan publication"
    published = node._publish_state(refreshed)
    assert published["scan_revision"] == 4
    assert published[asset.UI_EDIT_REVISION_KEY] == 4
    assert node._current_state()["search"] == "scan publication"
    assert node._hmb_last_accepted_widget_revisions == (4, 4)


print("HMB ImageAsset monotonic widget-state echo regression: PASS")
