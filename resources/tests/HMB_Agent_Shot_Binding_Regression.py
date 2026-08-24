from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sys
import threading
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

only_subscription = {
    "schema": "hmb-shot-channel-subscription",
    "version": 1,
    "participant_kind": "agent",
    "enabled": False,
    "channel_uuid": "",
    "shot_uuid": "",
    "shot_number": 1,
    "shot_name": "Only",
}
only_prompt_subscription = {
    **only_subscription,
    "participant_kind": "prompt",
}
only_prompt_source = SimpleNamespace(
    _hmb_shot_channel_subscription=lambda: only_prompt_subscription,
)
only_agent = SimpleNamespace(
    _hmb_shot_channel_subscription=lambda: only_subscription,
)
setattr(only_agent, agent._VERIFIED_PROMPT_SOURCE_ATTRIBUTE, only_prompt_source)
assert agent.HMBAgentLibrary._assert_exact_prompt_shot_route(only_agent) == {}

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


# Five same-flow Agent instances may publish execution phases concurrently.
# Their widget state is display transport, not source authority: a malformed
# retained-mode echo must not erase or exchange the strict Shot captured at
# process start. This regression is local-only and never submits a provider job.
concurrent_channel = str(uuid.uuid4())
concurrent_shots = [
    {
        "shot_uuid": str(uuid.uuid4()),
        "number": index,
        "name": f"Shot {index}",
        "revision": 1,
    }
    for index in range(1, 6)
]
concurrent_metadata = {
    "channel_uuid": concurrent_channel,
    "generation": 1,
    "shots": concurrent_shots,
}
concurrent_catalog = {
    "schema": "hmb-shot-routing-catalog",
    "version": 1,
    "publisher_instance_uuid": str(uuid.uuid4()),
    **concurrent_metadata,
    "metadata_sha256": hashlib.sha256(
        json.dumps(
            concurrent_metadata,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest(),
}


class ExecutionBindingHarness(agent.HMBAgentLibrary):
    def configure(self, selected: dict) -> None:
        self.name = f"Agent Shot {selected['number']}"
        self._hmb_node_deleted = False
        self._hmb_execution_shot_binding = {}
        self._hmb_shot_catalog_snapshot = concurrent_catalog
        self._hmb_shot_context = {}
        self._hmb_last_generator_snapshot = {
            "channel_uuid": concurrent_channel,
            "shot_uuid": selected["shot_uuid"],
            "shot_number": selected["number"],
            "shot_name": selected["name"],
        }
        self._hmb_remote_prompt_publication = {"authority": "completed"}
        self._hmb_shot_clear_syncing = False
        self._hmb_shot_catalog_syncing = False
        self._hmb_execution_phase_syncing = False
        self._hmb_initial_shot_autoclaim_pending = False
        self._hmb_initial_shot_preferred_uuid = ""
        self._widget_parameter = SimpleNamespace(
            name=agent._AGENT_WIDGET_PARAMETER,
            default_value=agent._agent_widget_value(
                {
                    "channel_uuid": concurrent_channel,
                    "shot_uuid": selected["shot_uuid"],
                    "number": selected["number"],
                    "name": selected["name"],
                },
                concurrent_catalog,
            ),
        )

    def get_parameter_by_name(self, name: str):
        return self._widget_parameter if name == agent._AGENT_WIDGET_PARAMETER else None

    def set_parameter_value(self, name: str, value, *args, **kwargs) -> None:
        del args, kwargs
        assert name == agent._AGENT_WIDGET_PARAMETER
        normalized = agent.HMBAgentLibrary.before_value_set(
            self,
            self._widget_parameter,
            value,
        )
        self._widget_parameter.default_value = normalized
        agent.HMBAgentLibrary.after_value_set(
            self,
            self._widget_parameter,
            normalized,
        )

    def _hmb_available_agent_shot_catalog(self, *_args, **_kwargs) -> dict:
        return concurrent_catalog

    def _refresh_agent_shot_route(self, **_kwargs) -> dict:
        return {"ok": True, "code": "ready", "changed": 0}

    def _refresh_routed_prompt_preview(self) -> None:
        return None


agents = []
for selected in concurrent_shots:
    node = object.__new__(ExecutionBindingHarness)
    node.configure(selected)
    agents.append(node)

phase_barrier = threading.Barrier(len(agents))


def exercise_concurrent_phases(node: ExecutionBindingHarness) -> tuple:
    expected = node._capture_execution_shot_binding()
    phase_barrier.wait(timeout=5)
    # Simulate the empty display echo seen during managed-edge churn.
    node.set_parameter_value(
        agent._AGENT_WIDGET_PARAMETER,
        agent._agent_widget_value({}, concurrent_catalog, "running"),
    )
    for phase in ("authorizing", "preparing", "running", ""):
        node._set_agent_execution_phase(phase)
        current = node._hmb_shot_channel_subscription()
        assert current.get("participant_kind") == "agent"
        assert current.get("enabled") is True
        assert current == expected
        phase_barrier.wait(timeout=5)
    node._clear_execution_shot_binding()
    restored = node._hmb_shot_channel_subscription()
    assert restored == expected
    return (
        expected["channel_uuid"],
        expected["shot_uuid"],
        expected["shot_number"],
        expected["shot_name"],
    )


with ThreadPoolExecutor(max_workers=5) as executor:
    identities = list(executor.map(exercise_concurrent_phases, agents))
assert len(set(identities)) == 5
assert [identity[2] for identity in identities] == [1, 2, 3, 4, 5]

# process() receives this exact empty verified result for a canonical HMB Prompt
# in Only mode. It must clear a stale execution binding and continue without
# attempting to capture a Shot identity.
only_gate_probe = agents[0]
only_gate_probe._hmb_execution_shot_binding = subscription(
    "agent",
    concurrent_shots[0]["shot_uuid"],
)
only_gate_probe._hmb_execution_shot_binding.update(
    channel_uuid=concurrent_channel,
    shot_number=1,
    shot_name="Shot 1",
)
assert only_gate_probe._adopt_verified_execution_shot_binding({}) == {}
assert only_gate_probe._hmb_execution_shot_binding == {}

# The binding is execution-scoped. Once released, a real Only selection and a
# real Shot switch immediately invalidate the old completed authority; Seedance
# must not fall back to the retained result snapshot.
authority_probe = agents[0]
authority_probe._clear_execution_shot_binding()
authority_probe.set_parameter_value(
    agent._AGENT_WIDGET_PARAMETER,
    agent._agent_widget_value({}, concurrent_catalog),
)
assert authority_probe._hmb_last_generator_snapshot == {}
assert authority_probe._hmb_remote_prompt_publication == {}
only_subscription = authority_probe._hmb_shot_channel_subscription()
assert only_subscription.get("participant_kind") == "agent"
assert only_subscription.get("enabled") is False

authority_probe._widget_parameter.default_value = agent._agent_widget_value(
    {
        "channel_uuid": concurrent_channel,
        "shot_uuid": concurrent_shots[0]["shot_uuid"],
        "number": 1,
        "name": "Shot 1",
    },
    concurrent_catalog,
)
authority_probe._hmb_last_generator_snapshot = {
    "channel_uuid": concurrent_channel,
    "shot_uuid": concurrent_shots[0]["shot_uuid"],
    "shot_number": 1,
    "shot_name": "Shot 1",
}
authority_probe._hmb_remote_prompt_publication = {"authority": "completed"}
authority_probe.set_parameter_value(
    agent._AGENT_WIDGET_PARAMETER,
    agent._agent_widget_value(
        {
            "channel_uuid": concurrent_channel,
            "shot_uuid": concurrent_shots[1]["shot_uuid"],
            "number": 2,
            "name": "Shot 2",
        },
        concurrent_catalog,
    ),
)
assert authority_probe._hmb_last_generator_snapshot == {}
assert authority_probe._hmb_remote_prompt_publication == {}

print(
    "HMB Agent Shot binding regression: PASS "
    "(catalog fail-closed, exact identity, five concurrent execution bindings)"
)
