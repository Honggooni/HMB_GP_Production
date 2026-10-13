"""Bounded project identities shared by policy selection and video records.

Project names are identifiers, never paths supplied to a policy reader. Unknown
explicit projects fail closed; only old workflows with no project metadata use
the historical Super Wings 12 assignment.
"""
from __future__ import annotations

import json
import unicodedata
from typing import Any


DEFAULT_PROJECT_ID = "superwings12"
PROJECTS = {
    "dinoster5": {"project_id": "dinoster5", "project_name": "다이노스터", "project_folder": "Dinoster5"},
    "katuri8": {"project_id": "katuri8", "project_name": "까투리8", "project_folder": "Katuri8"},
    "superwings12": {"project_id": "superwings12", "project_name": "슈퍼윙즈12", "project_folder": "superwings12"},
}
_ALIASES = {
    "dinoster5": "dinoster5", "dinoster": "dinoster5", "다이노스터": "dinoster5", "다이노스터5": "dinoster5",
    "katuri8": "katuri8", "까투리8": "katuri8",
    "superwings12": "superwings12", "super wings 12": "superwings12",
    "슈퍼윙즈12": "superwings12", "슈퍼윙즈 12": "superwings12",
    "슈퍼윙스12": "superwings12", "슈퍼윙스 12": "superwings12",
}


class ProjectPolicyPendingError(RuntimeError):
    """A selected known project has no separately supplied signed policy yet."""


def _identity(value: Any, *, path: bool = False) -> str:
    if not isinstance(value, str) or len(value) > 4096 or "\x00" in value:
        raise ValueError("project_identity_invalid")
    text = unicodedata.normalize("NFC", value).strip()
    if path:
        pieces = text.replace("\\", "/").rstrip("/").split("/")
        if any(part in {".", ".."} for part in pieces):
            raise ValueError("project_identity_invalid")
        text = pieces[-1]
    elif "/" in text or "\\" in text or ":" in text:
        raise ValueError("project_identity_invalid")
    identity = _ALIASES.get(text.casefold())
    if identity is None:
        raise ValueError("project_unknown")
    return identity


def _resolve_candidates(candidates: list[str], default_legacy: bool) -> dict[str, str]:
    unique = set(candidates)
    if len(unique) > 1:
        raise ValueError("project_identity_mismatch")
    if not unique and not default_legacy:
        raise ValueError("project_required")
    return dict(PROJECTS[next(iter(unique), DEFAULT_PROJECT_ID)])


def resolve_project(value: Any = None, *, default_legacy: bool = True) -> dict[str, str]:
    """Resolve a canonical ID, approved display name, or explicit record."""
    if value is None or value == "":
        return _resolve_candidates([], default_legacy)
    if isinstance(value, dict):
        return project_from_asset_payload(value, default_legacy=default_legacy)
    return dict(PROJECTS[_identity(value)])


def project_from_asset_payload(value: Any, *, default_legacy: bool = True) -> dict[str, str]:
    """Read project fields from ImageAsset state/payload, without reading files.

    Image arrays/catalog choices are intentionally excluded: the selected
    library project determines routing even when it contains imported images.
    """
    if value is None or value == "":
        return _resolve_candidates([], default_legacy)
    if isinstance(value, str):
        if len(value) > 1024 * 1024:
            raise ValueError("project_payload_too_large")
        try:
            value = json.loads(value)
        except (ValueError, TypeError) as exc:
            raise ValueError("project_payload_invalid") from exc
    if not isinstance(value, dict):
        raise ValueError("project_payload_invalid")
    candidates: list[str] = []
    visited: set[int] = set()

    def visit(record: dict[str, Any], depth: int) -> None:
        if depth > 4 or id(record) in visited:
            raise ValueError("project_payload_invalid")
        visited.add(id(record))
        for key in ("project_id", "project_name", "project_folder", "project_root"):
            raw = record.get(key)
            if raw is None or raw == "":
                continue
            candidates.append(_identity(raw, path=key == "project_root"))
        for key in ("project", "library", "image_asset", "asset_payload"):
            nested = record.get(key)
            if isinstance(nested, dict):
                visit(nested, depth + 1)
            elif key == "project" and nested not in (None, ""):
                candidates.append(_identity(nested))

    visit(value, 0)
    return _resolve_candidates(candidates, default_legacy)
