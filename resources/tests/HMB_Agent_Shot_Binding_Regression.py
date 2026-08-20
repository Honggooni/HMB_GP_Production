from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import uuid


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import HMBAgentLibrary as agent  # noqa: E402


channel = str(uuid.uuid4())
publisher = str(uuid.uuid4())
shot = str(uuid.uuid4())
shots = [
    {
        "shot_uuid": shot,
        "number": 1,
        "name": "Shot 1",
        "revision": 1,
    }
]
metadata_document = {
    "channel_uuid": channel,
    "generation": 1,
    "shots": shots,
}
catalog = {
    "schema": "hmb-shot-routing-catalog",
    "version": 1,
    "publisher_instance_uuid": publisher,
    **metadata_document,
    "metadata_sha256": hashlib.sha256(
        json.dumps(
            metadata_document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest(),
}
assert agent._strict_agent_shot_catalog(catalog) == catalog

bad_hash = dict(catalog)
bad_hash["metadata_sha256"] = "0" * 64
try:
    agent._strict_agent_shot_catalog(bad_hash)
except RuntimeError as exc:
    assert "hash" in str(exc)
else:
    raise AssertionError("Agent accepted a catalog with a forged metadata hash.")

noncanonical = {**catalog, "shots": [{**shots[0], "name": " Shot 1 "}]}
try:
    agent._strict_agent_shot_catalog(noncanonical)
except RuntimeError as exc:
    assert "canonical" in str(exc)
else:
    raise AssertionError("Agent silently normalized a non-canonical catalog.")


def subscription(kind: str, shot_uuid: str = shot) -> dict:
    return {
        "schema": "hmb-shot-channel-subscription",
        "version": 1,
        "participant_kind": kind,
        "enabled": True,
        "channel_uuid": channel,
        "shot_uuid": shot_uuid,
        "shot_number": 1,
        "shot_name": "Shot 1",
    }


prompt_source = SimpleNamespace(
    _hmb_shot_channel_subscription=lambda: subscription("prompt"),
    _hmb_shot_route_status={"ok": True, "code": "ready"},
)
fake_agent = SimpleNamespace(
    _hmb_shot_channel_subscription=lambda: subscription("agent"),
    _hmb_shot_route_status={"ok": True, "code": "ready"},
    _native_parameter_value=lambda _name, _default="": "compiled prompt",
)
setattr(fake_agent, agent._VERIFIED_PROMPT_SOURCE_ATTRIBUTE, prompt_source)
agent.HMBAgentLibrary._assert_exact_prompt_shot_route(fake_agent)

prompt_source._hmb_shot_channel_subscription = lambda: subscription(
    "prompt",
    str(uuid.uuid4()),
)
try:
    agent.HMBAgentLibrary._assert_exact_prompt_shot_route(fake_agent)
except RuntimeError as exc:
    assert "not ready" in str(exc) or "do not match" in str(exc)
else:
    raise AssertionError("Agent accepted a Prompt from another Shot UUID.")

print(
    "HMB Agent Shot binding regression: PASS "
    "(catalog fail-closed, exact Prompt/Agent Shot identity)"
)
