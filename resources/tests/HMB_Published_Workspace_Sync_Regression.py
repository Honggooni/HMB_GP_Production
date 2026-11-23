"""Exercise the maintainer release handoff against two real worktrees and a local bare origin."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


TOOL = Path(__file__).resolve().parents[2] / "tools" / "sync_published_workspace.py"


class WorkspaceSyncTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.chat = self.base / "chat"
        self.release = self.base / "release"
        self.stage = self.base / "proof"
        self.tag = "v0.9.41"
        self.env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                        GIT_TERMINAL_PROMPT="0")
        self.git(self.base, "init", "--bare", "origin.git")
        self.git(self.base, "init", "-b", "main", "chat")
        self.git(self.chat, "config", "user.name", "Test")
        self.git(self.chat, "config", "user.email", "test@localhost")
        self.git(self.chat, "remote", "add", "origin", str(self.base / "origin.git"))
        (self.chat / ".gitignore").write_text("ignored-*\n", encoding="utf-8")
        (self.chat / "feature").write_text("baseline", encoding="utf-8")
        self.git(self.chat, "add", ".")
        self.git(self.chat, "commit", "-m", "base")
        self.before = self.git(self.chat, "rev-parse", "HEAD")
        self.git(self.chat, "push", "origin", "main")
        self.git(self.chat, "worktree", "add", "-b", "release", str(self.release), "main")
        (self.release / "feature").write_text("published", encoding="utf-8")
        (self.release / "ignored-collision").write_text("published", encoding="utf-8")
        self.git(self.release, "add", "-f", "feature", "ignored-collision")
        self.git(self.release, "commit", "-m", "release")
        self.commit = self.git(self.release, "rev-parse", "HEAD")
        self.git(self.release, "tag", "-a", self.tag, "-m", "annotated release")
        self.git(self.release, "push", "origin", "HEAD:refs/heads/main", self.tag)
        (self.stage / "publication").mkdir(parents=True)
        self.installed = self.base / "installed"
        self.installed.mkdir()
        self.proofs()

    def git(self, cwd, *command):
        return subprocess.check_output(["git", *command], cwd=cwd, env=self.env, text=True,
                                       stderr=subprocess.PIPE).strip()

    def proofs(self, local=None):
        def save(path, **values):
            path.write_text(json.dumps(values), encoding="utf-8")

        major, minor, patch = self.tag[1:].split(".")
        local = local or f"{major}.{minor}.{int(patch) + 1}"
        save(self.stage / "publication/verified.json", published=True, tag=self.tag, commit=self.commit,
             verified_members=7, archive_sha256="a"*64)
        save(self.stage / "local-verified.json", published_team=self.tag[1:], local=local, commit=self.commit,
             verified_runtime_files=6, published_archive_sha256="a"*64, receipt="matches_recorded_inventory",
             policy="verified", target=str(self.installed), runtime_fingerprint="b"*64)
        save(self.installed / ".hmb-install-receipt.json", team_release=self.tag[1:], team_commit=self.commit,
             release_version=local, runtime_fingerprint_sha256="b"*64, team_functional_parity=True)

    def invoke(self, *, rejected=False, workspace=None):
        result = subprocess.run([sys.executable, str(TOOL), "--workspace", str(workspace or self.chat),
                                 "--tag", self.tag, "--verified-stage", str(self.stage)], text=True,
                                capture_output=True, env=self.env)
        if rejected:
            self.assertNotEqual(result.returncode, 0, result.stdout)
            return result.stderr
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)["result"]

    def test_fast_forward_repeat_and_visible_edits(self):
        self.assertEqual(self.invoke(), "fast_forwarded")
        self.assertEqual(self.git(self.chat, "rev-parse", "HEAD"), self.commit)
        self.assertEqual(self.invoke(), "already_current")
        (self.chat / "feature").write_text("work in progress", encoding="utf-8")
        self.assertIn("feature", self.git(self.chat, "status", "--porcelain"))
        self.assertIn("untracked files", self.invoke(rejected=True))
        self.assertEqual((self.chat / "feature").read_text(), "work in progress")

    def test_branch_dirty_untracked_staged(self):
        self.assertIn("on main", self.invoke(rejected=True, workspace=self.release))
        pending = self.chat / "new-work"
        pending.write_text("work", encoding="utf-8")
        self.assertIn("untracked files", self.invoke(rejected=True))
        self.git(self.chat, "add", pending.name)
        self.assertIn("untracked files", self.invoke(rejected=True))
        self.assertEqual(self.git(self.chat, "rev-parse", "HEAD"), self.before)
        self.assertEqual(pending.read_text(), "work")

    def test_ref_mismatch_and_lightweight_tag(self):
        self.tag = "v0.9.43"
        self.proofs()
        self.git(self.release, "tag", self.tag, self.before)
        self.git(self.release, "push", "origin", self.tag)
        self.assertIn("live origin", self.invoke(rejected=True))
        self.assertEqual(self.git(self.chat, "rev-parse", "HEAD"), self.before)
        self.tag = "v0.9.45"
        self.proofs()
        self.git(self.release, "tag", self.tag, self.commit)
        self.git(self.release, "push", "origin", self.tag)
        self.assertEqual(self.invoke(), "fast_forwarded")

    def test_diverged_local_main_is_preserved(self):
        (self.chat / "feature").write_text("local commit", encoding="utf-8")
        self.git(self.chat, "commit", "-am", "local")
        local = self.git(self.chat, "rev-parse", "HEAD")
        self.assertIn("cannot fast-forward", self.invoke(rejected=True))
        self.assertEqual(self.git(self.chat, "rev-parse", "HEAD"), local)
        self.assertEqual((self.chat / "feature").read_text(), "local commit")

    def test_ignored_collision_is_preserved(self):
        pending = self.chat / "ignored-collision"
        pending.write_text("local ignored", encoding="utf-8")
        self.invoke(rejected=True)
        self.assertEqual(self.git(self.chat, "rev-parse", "HEAD"), self.before)
        self.assertEqual(pending.read_text(), "local ignored")

    def test_old_install_receipt_blocks_sync(self):
        path = self.installed / ".hmb-install-receipt.json"
        receipt = json.loads(path.read_bytes())
        receipt["team_commit"] = self.before
        path.write_text(json.dumps(receipt), encoding="utf-8")
        self.assertIn("current Local installation", self.invoke(rejected=True))

    def test_local_version_must_exceed_team(self):
        for version in ("0.9.40", "0.9.41"):
            with self.subTest(version=version):
                self.proofs(local=version)
                self.assertIn("Local version must be higher", self.invoke(rejected=True))
                self.assertEqual(self.git(self.chat, "rev-parse", "HEAD"), self.before)
        self.assertEqual(self.git(self.chat, "rev-parse", "HEAD"), self.before)


if __name__ == "__main__":
    unittest.main()
