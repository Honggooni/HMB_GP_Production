"""Push a new Team tag only after that exact main commit passes the release audit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import tomllib


ROOT = Path(__file__).resolve().parents[1]
WINDOWS_JOB = "windows-release-audit"
REQUIRED_STEPS = (
    "JavaScript widget regressions with required browser coverage",
    "Python release regressions with coverage receipts",
    "Runtime package static syntax audit",
    "Require tested even-to-odd runtime parity",
)


def run(*args: str) -> str:
    result = subprocess.run(
        args, cwd=ROOT, text=True, encoding="utf-8", capture_output=True, check=False,
    )
    if result.returncode:
        raise ValueError(f"{' '.join(args[:2])} failed with exit code {result.returncode}.")
    return result.stdout.strip()


def origin_repo() -> str:
    remote = run("git", "remote", "get-url", "--push", "origin")
    match = re.fullmatch(
        r"(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)"
        r"([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?",
        remote,
    )
    if not match:
        raise ValueError("Origin must have a GitHub push URL.")
    return match.group(1)


def remote_refs(*refs: str) -> dict[str, str]:
    destination = run("git", "remote", "get-url", "--push", "origin")
    rows = run("git", "ls-remote", "--refs", destination, *refs).splitlines()
    return {ref: commit for commit, ref in (row.split("\t") for row in rows)}


def require_release_audit(repo: str, commit: str) -> str:
    runs = json.loads(run(
        "gh", "run", "list", "--repo", repo, "--workflow", "release-audit.yml",
        "--branch", "main", "--event", "push", "--commit", commit, "--limit", "1",
        "--json", "databaseId,headSha,headBranch,event,status,conclusion,url",
    ))
    if not runs:
        raise ValueError("This commit has no main release-audit run.")
    latest = runs[0]
    if (latest["headSha"], latest["headBranch"], latest["event"]) != (commit, "main", "push"):
        raise ValueError("GitHub returned a run for a different commit or branch.")
    if (latest["status"], latest["conclusion"]) != ("completed", "success"):
        raise ValueError(f"The main audit is {latest['conclusion'] or latest['status']}. {latest['url']}")
    details = json.loads(run(
        "gh", "run", "view", str(latest["databaseId"]), "--repo", repo,
        "--json", "headSha,status,conclusion,jobs",
    ))
    if (details["headSha"], details["status"], details["conclusion"]) != (commit, "completed", "success"):
        raise ValueError("The main audit changed before tag verification.")
    windows = next((job for job in details["jobs"] if job["name"] == WINDOWS_JOB), {})
    passed = {step["name"] for step in windows.get("steps", []) if step["conclusion"] == "success"}
    missing = [step for step in REQUIRED_STEPS if step not in passed]
    if windows.get("conclusion") != "success" or missing:
        raise ValueError(f"Required Windows checks did not pass. {'; '.join(missing)}")
    return latest["url"]


def publish(version: str, *, push: bool) -> dict[str, str]:
    if not re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", version) or int(version.rsplit(".", 1)[1]) % 2 != 1:
        raise ValueError("Team release requires an explicit odd patch version.")
    major, minor, patch = version.split(".")
    tag = f"v{major}.{minor}.{int(patch):02d}"
    ref = f"refs/tags/{tag}"
    main_ref = "refs/heads/main"
    repo = origin_repo()
    commit = run("git", "rev-parse", "HEAD")
    configured = tomllib.loads(run("git", "show", f"{commit}:pyproject.toml"))["project"]["version"]
    if configured != version:
        raise ValueError(f"The commit declares version {configured}, but {version} was requested.")
    expected = {main_ref: commit}
    if remote_refs(main_ref, ref) != expected:
        raise ValueError("Origin main must match HEAD and the Team tag must be new.")
    audit = require_release_audit(repo, commit)
    if push:
        if remote_refs(main_ref, ref) != expected:
            raise ValueError("Origin main or the Team tag changed during verification.")
        run("git", "push", "origin", f"{commit}:{ref}")
        if remote_refs(ref) != {ref: commit}:
            raise ValueError("The remote tag does not point to the audited commit.")
    return {"tag": tag, "commit": commit, "audit": audit, "status": "pushed" if push else "verified"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="Team version, for example 0.9.61")
    parser.add_argument("--push", action="store_true", help="Push the verified new tag")
    args = parser.parse_args()
    try:
        print(json.dumps(publish(args.version, push=args.push)))
    except (KeyError, OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
