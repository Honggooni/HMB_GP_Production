"""Fast-forward the maintainer's clean chat checkout after Team publication and Local verification."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys


def git(workspace, *args, check=True):
    result = subprocess.run(
        ["git", "--no-optional-locks", "-C", str(workspace), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if check and result.returncode:
        raise ValueError(result.stderr.strip() or f"git {args[0]} failed")
    return result


def validate_checkout(workspace):
    if workspace != Path(git(workspace, "rev-parse", "--show-toplevel").stdout.strip()).resolve():
        raise ValueError("Specify the top level of the chat checkout")
    if git(workspace, "symbolic-ref", "--quiet", "HEAD", check=False).stdout.strip() != "refs/heads/main":
        raise ValueError("The chat checkout must be on main")
    if git(workspace, "status", "--porcelain=v1", "-z", "--untracked-files=all", "--ignore-submodules=none").stdout:
        raise ValueError("The chat checkout has staged, modified or untracked files")
    flags = git(workspace, "ls-files", "-v", "-z").stdout.split("\0")
    if any(entry and (entry[0] == "S" or entry[0].islower()) for entry in flags):
        raise ValueError("Git index flags hide tracked changes")
    git_dir = Path(git(workspace, "rev-parse", "--absolute-git-dir").stdout.strip())
    if any((git_dir / name).exists() for name in (
        "MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-apply", "rebase-merge", "sequencer", "BISECT_START",
    )):
        raise ValueError("Finish the active Git operation before synchronizing")
    return git(workspace, "rev-parse", "HEAD").stdout.strip()


def verified_commit(stage, tag):
    published = json.loads((stage / "publication" / "verified.json").read_bytes())
    installed = json.loads((stage / "local-verified.json").read_bytes())
    commit = published["commit"]
    local_version = installed.get("local", "")
    if not re.fullmatch(r"\d+\.\d+\.\d+", local_version) or (
        tuple(map(int, local_version.split("."))) <= tuple(map(int, tag[1:].split(".")))
    ):
        raise ValueError("The installed Local version must be higher than the published Team version")
    if not (
        re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", commit)
        and published["tag"] == tag and installed["published_team"] == tag[1:]
        and commit == installed["commit"] and published["verified_members"] > 0
        and installed["verified_runtime_files"] > 0
        and re.fullmatch(r"[0-9a-f]{64}", published["archive_sha256"])
        and published["archive_sha256"] == installed["published_archive_sha256"]
        and installed["receipt"] == "matches_recorded_inventory" and installed["policy"] == "verified"
    ):
        raise ValueError("Team publication and Local verification records do not match this release")
    receipt = json.loads((Path(installed["target"]) / ".hmb-install-receipt.json").read_bytes())
    if not (
        receipt["team_release"] == tag[1:] and receipt["team_commit"] == commit
        and receipt["release_version"] == installed["local"]
        and re.fullmatch(r"[0-9a-f]{64}", installed["runtime_fingerprint"])
        and receipt["runtime_fingerprint_sha256"] == installed["runtime_fingerprint"]
        and receipt["team_functional_parity"] is True
    ):
        raise ValueError("The current Local installation does not match the verification record")
    return commit


def check_remote(workspace, tag, commit):
    ref = "refs/tags/" + tag
    main = "refs/heads/main"
    peeled = ref + "^{}"
    lines = git(workspace, "ls-remote", "--exit-code", "origin", main, ref, peeled).stdout.splitlines()
    refs = {name: oid for oid, name in (line.split("\t") for line in lines)}
    if refs.get(main) != commit or ref not in refs or refs.get(peeled, refs.get(ref)) != commit:
        raise ValueError("Published commit differs from live origin main or release tag")
    if git(workspace, "show-ref", "--verify", "--quiet", ref, check=False).returncode == 0:
        if git(workspace, "rev-parse", ref + "^{commit}").stdout.strip() != commit:
            raise ValueError("An existing local tag points at a different commit")


def sync(workspace, tag, stage):
    if not re.fullmatch(r"v\d+\.\d+\.\d+", tag):
        raise ValueError("Expected a release tag such as v0.9.41")
    before = validate_checkout(workspace)
    commit = verified_commit(stage, tag)
    check_remote(workspace, tag, commit)
    if before != commit:
        if git(workspace, "cat-file", "-e", commit + "^{commit}", check=False).returncode:
            git(workspace, "fetch", "--no-tags", "--no-recurse-submodules", "origin", "refs/heads/main")
            check_remote(workspace, tag, commit)
        if git(workspace, "merge-base", "--is-ancestor", before, commit, check=False).returncode:
            raise ValueError("Local main cannot fast-forward to the published commit")
        if validate_checkout(workspace) != before:
            raise ValueError("The chat checkout changed during synchronization")
        git(workspace, "merge", "--ff-only", "--no-autostash", "--no-overwrite-ignore", commit)
    if validate_checkout(workspace) != commit:
        raise ValueError("The published checkout could not be verified")
    return {"tag": tag, "commit": commit, "workspace": str(workspace),
            "result": "already_current" if before == commit else "fast_forwarded"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--verified-stage", required=True, type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(sync(args.workspace.resolve(), args.tag, args.verified_stage.resolve()), ensure_ascii=False))
    except (OSError, KeyError, TypeError, ValueError) as error:
        parser.exit(1, f"Workspace sync stopped: {error}\n")


if __name__ == "__main__":
    main()
