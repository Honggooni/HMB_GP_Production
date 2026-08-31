from __future__ import annotations

import ast
import inspect
from pathlib import Path
import sys
import textwrap
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import HMBAgentLibrary as agent


class BoundaryHarness:
    """Minimal host surface for the current sanitizer and Shot publication."""

    _secure_hmb_outputs = agent.HMBAgentLibrary._secure_hmb_outputs
    _hmb_generator_shot_snapshot = (
        agent.HMBAgentLibrary._hmb_generator_shot_snapshot
    )
    _hmb_commit_remote_prompt_publication = (
        agent.HMBAgentLibrary._hmb_commit_remote_prompt_publication
    )

    def __init__(self) -> None:
        self._hmb_node_deleted = False
        self._hmb_suppress_visible_publication = False
        self._hmb_last_sanitizer_status = "clean"
        self._hmb_last_generator_snapshot: dict[str, Any] = {}
        self._hmb_remote_prompt_publication: dict[str, Any] = {}
        self._hmb_remote_prompt_revision = 0
        self._hmb_remote_prompt_source_token = "boundary-source-token"
        self.parameter_output_values: dict[str, Any] = {
            "output": "",
            "agent": {},
            "logs": "",
        }
        self.visible_output = ""

    def _set_visible_output(self, value: str) -> None:
        self.visible_output = value
        self.parameter_output_values["output"] = value


def clean_output(value: Any, agent_state: Any | None = None) -> BoundaryHarness:
    node = BoundaryHarness()
    node.parameter_output_values["output"] = value
    node.parameter_output_values["agent"] = agent_state if agent_state is not None else {}
    assert node._secure_hmb_outputs() is False
    return node


# Final natural language is model/policy-owned. The client boundary must not
# phrase-match, require @source/target keywords, or rewrite a nonempty result.
natural_outputs = (
    "Create one coherent shot.",
    "배우의 움직임과 장면의 분위기를 자연스럽게 연결한다.",
    (
        "A concise instruction with no explicit @image, @video, target, authority, "
        "identity, lighting, or exclusion phrase."
    ),
    (
        '{"final_prompt":"This serialized user-facing text mentions rulesets and '
        'conversation_memory but is still ordinary string output."}'
    ),
)
for expected in natural_outputs:
    boundary = clean_output(expected)
    assert boundary.parameter_output_values["output"] == expected
    assert boundary.visible_output == expected
    assert boundary._hmb_last_sanitizer_status == "clean"


# Private state is still removed from the separate Agent-state port. Runtime
# scope and sealed policy fields never survive merely because FINAL TEXT is
# now opaque natural language.
policy_wrapper = {
    "agent": {
        "conversation_memory": {
            "runs": [
                {
                    "input": (
                        "PUBLIC PROMPT DATA\n"
                        f"{agent._RUNTIME_FX_SCOPE_HEADER}\n"
                        "PRIVATE DERIVED RUNTIME SCOPE"
                    )
                }
            ]
        }
    },
    "rulesets": ["PRIVATE SERVER POLICY"],
    "system": "PRIVATE SYSTEM PROMPT",
    "nested": {"instructions": "PRIVATE INTERNAL INSTRUCTIONS"},
}
protected = clean_output("Publish this exact final instruction.", policy_wrapper)
scrubbed_wrapper = protected.parameter_output_values["agent"]
assert scrubbed_wrapper["rulesets"] == []
assert scrubbed_wrapper["system"] == agent._PUBLIC_OUTPUT_BLOCKED
assert scrubbed_wrapper["nested"]["instructions"] == agent._PUBLIC_OUTPUT_BLOCKED
memory_input = scrubbed_wrapper["agent"]["conversation_memory"]["runs"][0]["input"]
assert memory_input == "PUBLIC PROMPT DATA"
assert "PRIVATE" not in str(scrubbed_wrapper)

# A directly supplied native Agent/runtime object is not final natural language
# and therefore remains fail-closed at the public output port.
structured_state = {
    "agent": {
        "type": "GriptapeNodesAgent",
        "conversation_memory": {"runs": []},
    }
}
blocked = clean_output(structured_state)
assert blocked.parameter_output_values["output"] == agent._PUBLIC_OUTPUT_BLOCKED
assert blocked.visible_output == agent._PUBLIC_OUTPUT_BLOCKED
assert blocked._hmb_last_sanitizer_status == "state"


# A sanitized nonempty result can become the exact selected-Shot publication.
# Empty text cannot manufacture a successful snapshot/publication.
final_text = natural_outputs[2]
shot_context = {
    "channel_uuid": "channel-regression",
    "shot_uuid": "shot-regression",
    "shot_number": 3,
    "shot_name": "Shot 3",
    "prompt_generation": 11,
    "visible_prompt_sha256": "1" * 64,
    "image_media_sha256": "2" * 64,
    "video_media_sha256": "3" * 64,
}
publisher = BoundaryHarness()
publisher._hmb_last_generator_snapshot = {
    "schema": agent._AGENT_GENERATOR_SNAPSHOT_SCHEMA,
    "version": agent._AGENT_GENERATOR_SNAPSHOT_VERSION,
    **shot_context,
    "final_text_sha256": agent._prompt_text_sha256(final_text),
}
publication = publisher._hmb_commit_remote_prompt_publication(final_text)
assert publication["final_text"] == final_text
assert publication["final_text_sha256"] == agent._prompt_text_sha256(final_text)
assert publication["shot_uuid"] == "shot-regression"
assert publisher._hmb_remote_prompt_publication == publication

empty_publisher = BoundaryHarness()
empty_publisher._hmb_last_generator_snapshot = {
    "schema": agent._AGENT_GENERATOR_SNAPSHOT_SCHEMA,
    "version": agent._AGENT_GENERATOR_SNAPSHOT_VERSION,
    **shot_context,
    "final_text_sha256": agent._prompt_text_sha256(""),
}
try:
    empty_publisher._hmb_commit_remote_prompt_publication("")
except RuntimeError as exc:
    assert str(exc) == "HMB Agent Shot result snapshot is unavailable."
else:
    raise AssertionError("Empty Agent output was published to a Shot.")
assert empty_publisher._hmb_remote_prompt_publication == {}


# Guard the actual process orchestration: sanitizer and Shot publication remain
# present, while the deleted client-side semantic manifest/phrase-rewrite APIs
# remain absent. This intentionally does not recreate those old validators.
process_source = textwrap.dedent(inspect.getsource(agent.HMBAgentLibrary.process))
process_tree = ast.parse(process_source)
called_names: set[str] = set()
for node in ast.walk(process_tree):
    if not isinstance(node, ast.Call):
        continue
    if isinstance(node.func, ast.Name):
        called_names.add(node.func.id)
    elif isinstance(node.func, ast.Attribute):
        called_names.add(node.func.attr)

assert "_secure_hmb_outputs" in called_names
assert "_hmb_commit_remote_prompt_publication" in called_names
assert "strip" in called_names  # the sole success criterion is nonempty text
for obsolete_semantic_api in (
    "_build_final_output_semantic_manifest",
    "_assert_final_output_semantic_integrity",
    "_strip_semantic_evidence_tags",
    "_rewrite_final_output",
):
    assert obsolete_semantic_api not in called_names
    assert not hasattr(agent, obsolete_semantic_api)

print("HMB Agent generator natural-language publication boundary regression: PASS")
