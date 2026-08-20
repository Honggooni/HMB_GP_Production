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
    "6debb90960499ff6fe163a8a5a6db42a0da028f7a7606f993175edbd5712e65e"
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
    if not PRIVATE_SIGNED_POLICY_FIXTURE.is_file():
        return None
    encoded = PRIVATE_SIGNED_POLICY_FIXTURE.read_bytes()
    if hashlib.sha256(encoded).hexdigest() != EXPECTED_ENVELOPE_SHA256:
        raise RuntimeError("Private signed Agent policy fixture identity mismatch.")
    return encoded


def install_private_policy_reader(common: Any) -> tuple[Callable[[], bytes], bytes]:
    """Inject the private signed fixture into one isolated regression process."""

    encoded = read_private_policy_fixture_if_available()
    if encoded is None:
        raise RuntimeError(
            "Private signed Agent policy fixture is required for this internal regression."
        )
    original = common._read_agent_policy_envelope
    common._read_agent_policy_envelope = lambda: encoded
    return original, encoded
