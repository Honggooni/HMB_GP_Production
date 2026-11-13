"""Activate the reviewed Editor 0.130 overlay for ZIP and Git installations."""
from pathlib import Path
import uuid

from .hmb_rodong_editor_0130 import build
from .restore_rodong_local_editor import (
    OVERLAY, OVERLAY_DIGEST, STOCK_BUNDLE, STOCK_DIGEST,
    entry_for_overlay, stock_entry_from_active,
)


LEGACY_CANDIDATE = "109600be6fc2d6dde89c934bda219a7fbc4be7e4bdcaa9b8c21f5bd091af7d8e"
LEGACY_ENTRY = "8696c149551a9326b9457c2ed353f0cef8e5aa3054e1656e8842ecc42803bbe5"
PLAN_SCHEMA = "hmb-native-editor-0130-install-plan"


def _stock_entry(entry: bytes, digest) -> bytes:
    if digest(entry) == LEGACY_ENTRY:
        ref = f"./assets/{STOCK_BUNDLE}".encode("ascii")
        versioned = ref + b"?hmb-team=" + LEGACY_CANDIDATE[:16].encode("ascii")
        mapping = b'<script type="importmap">{"imports":{"' + ref + b'":"' + versioned + b'"}}</script>\n    '
        entry = entry.replace(mapping, b"", 1).replace(b'src="' + versioned + b'"', b'src="' + ref + b'"', 1)
    return stock_entry_from_active(entry, OVERLAY)


def _stock_source(source: bytes, state: Path, io) -> bytes:
    if io.sha256(source) == STOCK_DIGEST:
        return source
    if io.sha256(source) != LEGACY_CANDIDATE:
        raise ValueError("Unknown Editor 0.130 source; existing files preserved.")
    # The previous updater edited the original bundle in place. Recover the
    # exact original from its bounded backup inventory.
    for index, directory in enumerate(state.iterdir() if state.is_dir() else ()):
        if index >= 128:
            break
        if len(directory.name) != 32 or any(c not in "0123456789abcdef" for c in directory.name):
            continue
        try:
            backup = io._release_plain_path(directory / "before.js")
            if backup.is_file() and backup.stat().st_size <= 64 * 1024 * 1024:
                value = backup.read_bytes()
                if io.sha256(value) == STOCK_DIGEST:
                    return value
        except (OSError, ValueError):
            continue
    raise ValueError("The previous Team Editor patch requires its reviewed original backup.")


def _inputs(editor: Path, io, descriptor_sha: str):
    entry = io._release_plain_path(editor / "index-editor.html")
    stock = io._release_plain_path(editor / "assets" / STOCK_BUNDLE)
    target = io._release_plain_path(editor / "assets" / OVERLAY)
    if entry.stat().st_size > 1024 * 1024 or stock.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("Editor 0.130 source is oversized.")
    before = entry.read_bytes()
    original = stock.read_bytes()
    after = entry_for_overlay(_stock_entry(before, io.sha256), OVERLAY)
    state = io._release_plain_path(io.RELEASE_STATE_ROOT)
    candidate = build(_stock_source(original, state, io))
    if io.sha256(candidate) != OVERLAY_DIGEST:
        raise ValueError("Editor 0.130 candidate differs from the verified Local build.")
    if target.exists() and (target.stat().st_size != len(candidate) or target.read_bytes() != candidate):
        raise ValueError("Editor 0.130 overlay path contains unreviewed bytes.")
    plan = {"schema": PLAN_SCHEMA, "version": 1, "status": "prepared",
            "target": str(target), "source_profile": "reviewed-adapter", "candidate_sha256": OVERLAY_DIGEST,
            "descriptor_sha256": descriptor_sha, "original_sha256": io.sha256(original),
            "entry_target": str(entry), "entry_original_sha256": io.sha256(before), "entry_candidate_sha256": io.sha256(after),
            "app_identity": io._git_override_app_identity(), "sdk_preflight": io._release_sdk_preflight(),
            "already_current": before == after and target.is_file()}
    return plan, entry, target, stock, before, after, candidate


def _prepare(io, snapshot) -> dict:
    plan, _, _, _, before, _, candidate = snapshot
    transaction = io._release_plain_path(io.RELEASE_STATE_ROOT) / uuid.uuid4().hex
    transaction.mkdir(parents=True, exist_ok=False)
    io._atomic_write(transaction / "before.html", before)
    io._atomic_write(transaction / "candidate.js", candidate)
    path = transaction / "plan.json"
    io._json_write(path, plan)
    return {**plan, "plan": str(path)}


def _owned_plan(path: Path, io, descriptor_sha: str) -> tuple[Path, dict]:
    path = io._release_plain_path(path)
    root = io._release_plain_path(io.RELEASE_STATE_ROOT)
    if path.name != "plan.json" or path.parent.parent != root or uuid.UUID(path.parent.name).hex != path.parent.name:
        raise ValueError("Editor 0.130 install plan is outside the owned install-state folder.")
    plan = io.json.loads(path.read_bytes())
    if (plan.get("schema") != PLAN_SCHEMA or plan.get("version") != 1
            or plan.get("descriptor_sha256") != descriptor_sha
            or plan.get("status") not in ("prepared", "applying", "applied", "rolled_back")):
        raise ValueError("Editor 0.130 install plan changed or belongs to another release.")
    return path, plan


def _rollback(editor: Path, io, descriptor_sha: str, path: Path) -> dict:
    path, plan = _owned_plan(path, io, descriptor_sha)
    entry = io._release_plain_path(editor / "index-editor.html")
    if plan["status"] in ("prepared", "rolled_back") or plan["already_current"]:
        return {"rolled_back": False}
    backup = io._release_plain_path(path.parent / "before.html").read_bytes()
    if io.sha256(backup) != plan["entry_original_sha256"]:
        raise ValueError("Editor 0.130 backup changed; rollback refused.")
    reviewed = entry_for_overlay(_stock_entry(backup, io.sha256), OVERLAY)
    current = entry.read_bytes()
    if io._git_override_app_identity() != plan["app_identity"] or current not in (backup, reviewed):
        raise ValueError("Editor changed outside this installation; rollback refused.")
    if current != backup:
        io._atomic_write(entry, backup)
        if entry.read_bytes() != backup:
            raise RuntimeError("Editor 0.130 rollback verification failed.")
    io._json_write(path, {**plan, "status": "rolled_back"})
    return {"rolled_back": current != backup}


def _apply(editor: Path, io, descriptor_sha: str, path: Path) -> dict:
    path, plan = _owned_plan(path, io, descriptor_sha)
    observed, entry, target, stock, before, after, candidate = _inputs(editor, io, descriptor_sha)
    stable = ("target", "descriptor_sha256", "original_sha256", "candidate_sha256",
              "entry_target", "entry_candidate_sha256", "app_identity", "sdk_preflight")
    if any(plan[key] != observed[key] for key in stable):
        raise ValueError("Editor or SDK changed after preparation.")
    if plan["status"] == "applied" and observed["already_current"]:
        return {**plan, "plan": str(path), "changed": not plan["already_current"]}
    if plan["status"] not in ("prepared", "applying") or plan["entry_original_sha256"] != observed["entry_original_sha256"]:
        raise ValueError("Editor entry changed after preparation.")
    backup = io._release_plain_path(path.parent / "before.html")
    staged = io._release_plain_path(path.parent / "candidate.js")
    if backup.read_bytes() != before or staged.read_bytes() != candidate:
        raise ValueError("Editor 0.130 staged candidate or backup changed.")

    if not target.is_file():
        io._atomic_write(target, candidate)
    if target.read_bytes() != candidate:
        raise ValueError("Prepared Editor 0.130 overlay differs from the reviewed build.")
    if (io._release_descriptor()[1] != descriptor_sha or io._git_override_app_identity() != plan["app_identity"]
            or io._release_sdk_preflight() != plan["sdk_preflight"] or entry.read_bytes() != before
            or io.sha256(stock.read_bytes()) != plan["original_sha256"]):
        raise ValueError("Editor or release changed during preparation; the original entry was retained.")
    io._json_write(path, {**plan, "status": "applying"})
    if entry.read_bytes() != before:
        io._json_write(path, {**plan, "status": "prepared"})
        raise ValueError("Editor entry changed before activation.")
    try:
        if before != after:
            io._atomic_write(entry, after)
        if entry.read_bytes() != after or target.read_bytes() != candidate:
            raise RuntimeError("Installed Editor overlay verification failed.")
        io._json_write(path, {**plan, "status": "applied"})
    except Exception:
        try:
            _rollback(editor, io, descriptor_sha, path)
        except Exception as recovery_error:
            raise RuntimeError("Editor rollback could not be verified. Preserved backup: " + str(backup)) from recovery_error
        raise
    return {**plan, "plan": str(path), "changed": not plan["already_current"], "backup": str(backup)}


def run(editor: Path, io, descriptor_sha: str, action: str, path: Path | None = None) -> dict:
    if action == "prepare":
        return _prepare(io, _inputs(editor, io, descriptor_sha))
    if action == "apply":
        return _apply(editor, io, descriptor_sha, path)
    if action == "rollback":
        return _rollback(editor, io, descriptor_sha, path)
    # The Git entry point permits one atomic replacement while the Desktop
    # runs. The ZIP entry points separately require the Desktop to be stopped.
    snapshot = _inputs(editor, io, descriptor_sha)
    observed = snapshot[0]
    if observed["already_current"]:
        return io._git_override_result("current", "Reviewed Editor overlay is already active on disk.",
                                       **{k: observed[k] for k in ("target", "source_profile", "candidate_sha256", "entry_candidate_sha256")})
    prepared = _prepare(io, snapshot)
    details = {k: prepared[k] for k in ("target", "source_profile", "candidate_sha256", "entry_candidate_sha256")}
    try:
        result = _apply(editor, io, descriptor_sha, Path(prepared["plan"]))
    except PermissionError:
        return io._git_override_result("pending", "Editor files were busy; the existing entry was retained.",
                                       plan=prepared["plan"], **details)
    return io._git_override_result("applied", "Editor overlay is ready on disk. Save work and restart Griptape normally once.",
                                   changed=True, plan=result["plan"], backup=result["backup"], **details)
