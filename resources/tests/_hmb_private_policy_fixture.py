from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[2]
PRIVATE_SIGNED_POLICY_FIXTURE = (
    ROOT
    / "resources"
    / "policy"
    / "HMB_GP_Production_Rule"
    / "artifact"
    / "hmb_agent_core.dat"
)
EXPECTED_ENVELOPE_SHA256 = (
    "228b54e55dd4167f4cb58f8bdbdb8762818a636018180fe1ae97f7a023ac2144"
)


def read_private_policy_fixture_if_available() -> bytes | None:
    """Return the internal signed fixture, or None in a clean public checkout."""

    if os.environ.get("HMB_TEST_SKIP_PRIVATE_POLICY_FIXTURE", "").strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return None
    configured_path = os.environ.get(
        "HMB_TEST_PRIVATE_POLICY_FIXTURE_PATH",
        "",
    ).strip()
    fixture_path = (
        Path(configured_path).expanduser().resolve()
        if configured_path
        else PRIVATE_SIGNED_POLICY_FIXTURE
    )
    if not fixture_path.is_file():
        return None
    encoded = fixture_path.read_bytes()
    if hashlib.sha256(encoded).hexdigest() != EXPECTED_ENVELOPE_SHA256:
        raise RuntimeError("Private signed Agent policy fixture identity mismatch.")
    return encoded


def install_private_policy_reader(common: Any) -> tuple[Callable[[], bytes], bytes]:
    """Install the private signed fixture into one isolated regression process.

    Production Agent execution reads only the process-scoped READY session; it
    no longer decodes a policy on demand.  Internal regressions therefore prove
    the real signature/contract first and seed that same one-shot session.  The
    legacy reader override is retained only for tests that directly exercise
    the envelope decoder, never as a runtime fallback.
    """

    encoded = read_private_policy_fixture_if_available()
    if encoded is None:
        raise RuntimeError(
            "Private signed Agent policy fixture is required for this internal regression."
        )
    original = common._read_agent_policy_envelope
    common._read_agent_policy_envelope = lambda: encoded
    validated = common._validate_agent_policy_payload(
        common._decode_signed_agent_policy_envelope(encoded)
    )
    validated["envelope_sha256"] = hashlib.sha256(encoded).hexdigest()
    session = common._agent_process_session
    state = str(session._status_for_regression()[0]).casefold()
    if state == "empty":
        session.bootstrap_once_authorized(lambda: True, lambda: validated)
    elif state == "ready":
        current = session.read_ready()
        expected_identity = (
            validated.get("final_policy_version"),
            validated.get("final_motion_look_policy_sha256"),
        )
        current_identity = (
            current.get("final_policy_version"),
            current.get("final_motion_look_policy_sha256"),
        )
        if current_identity != expected_identity:
            raise RuntimeError("Private Agent policy regression session identity mismatch.")
    else:
        raise RuntimeError(
            f"Private Agent policy regression session is not reusable: {state}."
        )
    return original, encoded
