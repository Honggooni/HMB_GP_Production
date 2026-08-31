from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[2]
BUNDLED_POLICY_DAT = ROOT / "resources" / "agent" / "hmb_agent_core.dat"


def read_bundled_policy_artifact() -> bytes:
    """Read the exact signed DAT shipped and installed with the runtime."""

    if not BUNDLED_POLICY_DAT.is_file() or BUNDLED_POLICY_DAT.is_symlink():
        raise RuntimeError(f"Bundled signed Agent policy DAT is missing: {BUNDLED_POLICY_DAT}")
    encoded = BUNDLED_POLICY_DAT.read_bytes()
    if not encoded or len(encoded) > 128 * 1024:
        raise RuntimeError("Bundled signed Agent policy DAT has an invalid size.")
    return encoded


def install_bundled_policy_session(
    common: Any,
) -> tuple[Callable[[], bytes], bytes]:
    """Seed an isolated regression process through the production DAT reader."""

    encoded = common._read_agent_policy_envelope()
    expected = read_bundled_policy_artifact()
    if encoded != expected:
        raise RuntimeError("Production Agent policy reader did not use the bundled DAT.")
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
            validated.get("policy_pair_sha256"),
        )
        current_identity = (
            current.get("final_policy_version"),
            current.get("policy_pair_sha256"),
        )
        if current_identity != expected_identity:
            raise RuntimeError("Bundled Agent policy regression identity mismatch.")
    else:
        raise RuntimeError(f"Bundled Agent policy session is not reusable: {state}.")
    return common._read_agent_policy_envelope, encoded
