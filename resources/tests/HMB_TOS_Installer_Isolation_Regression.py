"""Exact public installer repair: no real environment or package operations."""
from __future__ import annotations

from contextlib import redirect_stdout
import ast
import hashlib
import importlib.metadata as metadata
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
TEXT = (ROOT / "Install_HMB_GP_Production.ps1").read_text(encoding="utf-8-sig")
SCRIPTS = re.findall(r"(?ms)^    \$repair = @'\n(.*?)^'@\n", TEXT)
assert len(SCRIPTS) == 1, "The installer must expose one bounded shared-repair loader"
assert "_HMB_TOS_ENVIRONMENT_REPAIR_SOURCE" in SCRIPTS[0]
TREE = ast.parse((ROOT / "_hmb_library_bootstrap.py").read_text(encoding="utf-8-sig"))
CORES = [ast.literal_eval(node.value) for node in TREE.body if isinstance(node, ast.Assign)
         and any(isinstance(target, ast.Name) and target.id == "_HMB_TOS_ENVIRONMENT_REPAIR_SOURCE" for target in node.targets)]
assert len(CORES) == 1
REPAIR = compile(CORES[0], "<exact-shared-installer-TOS-repair>", "exec")
ENGINE = {"anyio":"4.15.1", "charset-normalizer":"3.5.2", "idna":"3.20", "urllib3":"2.8.0"}
OLD = {"anyio":"4.14.2", "charset-normalizer":"3.5.1", "idna":"3.19", "urllib3":"2.7.0"}


class InstallerRepair(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="hmb-tos-installer-contract-")
        # The public protocol resolves its root before constructing owned paths.
        # CI TEMP may use an 8.3 alias; private inventory helpers require that
        # same canonical root rather than a second spelling of the directory.
        self.root = (Path(self.tmp.name) / "HMB_GP_Production").resolve()
        self.site = self.root / ".venv/Lib/site-packages"
        self.site.mkdir(parents=True)
        (self.root/"griptape-nodes-library.json").write_text('{"name":"HMB_GP_Production"}',encoding="utf-8")
        python = self.root / ".venv/Scripts/python.exe"
        python.parent.mkdir(parents=True)
        python.write_bytes(b"Never executed: fixture only")
        self.calls = []

    def tearDown(self):
        self.tmp.cleanup()

    def package(self,name,version,requires=(),*,record=True,scripts=False):
        folder = self.site / (name.replace("-","_")+"-"+version+".dist-info")
        folder.mkdir()
        info = "Metadata-Version: 2.1\nName: "+name+"\nVersion: "+version+"\n"
        info += "".join("Requires-Dist: "+value+"\n" for value in requires)
        (folder/"METADATA").write_text(info,encoding="utf-8")
        payload=self.site/(name.replace("-","_")+"_fixture.py")
        payload.write_text("fixture only\n",encoding="utf-8")
        rows=[folder.name+"/METADATA,,",folder.name+"/RECORD,,",payload.name+",,"]
        if scripts:
            entry=self.root/".venv/Scripts/tos-fixture.exe";entry.write_bytes(b"fixture")
            rows.append("../../Scripts/tos-fixture.exe,,")
        if record:(folder/"RECORD").write_text("\n".join(rows)+"\n",encoding="utf-8")
        return folder

    def legacy(self):
        self.package("tos","2.9.2",["wrapt==1.16.0","Deprecated<2.0.0,>=1.2.13"])
        self.package("wrapt","1.16.0")
        self.package("Deprecated","1.3.1",["wrapt<3,>=1.10"])

    def fake_uv(self,args,**kwargs):
        self.calls.append(args)
        self.assertEqual(args[1:7],["-I","-B","-m","uv","pip","uninstall"])
        self.assertEqual(args[7],"--python")
        # Windows runners may expose TEMP through its 8.3 alias. The repair
        # resolves the library root; both spellings must identify this exact exe.
        self.assertEqual(Path(args[8]).resolve(),(self.root/".venv/Scripts/python.exe").resolve())
        removals=set(args[9:])
        for dist in list(metadata.distributions(path=[str(self.site)])):
            name=re.sub(r"[-_.]+","-",dist.metadata["Name"]).lower()
            if name not in removals:continue
            for member in dist.files or []:
                file=Path(dist.locate_file(member)).resolve()
                self.assertTrue(file.is_relative_to((self.root/".venv").resolve()))
                if file.is_file():file.unlink()
            dist._path.rmdir()
        return SimpleNamespace(returncode=0,stdout="",stderr="")

    def run_repair(self,*,version=(3,12,13),root=None):
        output=io.StringIO()
        with mock.patch.object(sys,"version_info",version), mock.patch.object(metadata,"version",side_effect=lambda name:ENGINE[name]), mock.patch.object(subprocess,"run",side_effect=self.fake_uv), redirect_stdout(output):
            namespace={"__name__":"_fixture_exact_installer_repair"}
            exec(REPAIR,namespace)
            return namespace["_repair_request"]({"version":1,"operation":"install","library_root":str(root or self.root),"clean_legacy":True,"prepare_runtime":False})

    def test_legacy_three_only_and_removed_versions_are_captured_before_deletion(self):
        self.legacy();self.package("custom","1.0")
        result=self.run_repair()
        self.assertEqual(result["legacy_packages_removed"],["deprecated","tos","wrapt"])
        self.assertEqual(result["engine_backed_duplicates_removed"],[])
        self.assertEqual(result["removed_versions"],{"deprecated":"1.3.1","tos":"2.9.2","wrapt":"1.16.0"})
        self.assertEqual([d.metadata["Name"] for d in metadata.distributions(path=[str(self.site)])],["custom"])
        self.assertEqual(len(self.calls),1)

    def test_only_known_four_older_duplicates_can_use_compatible_engine_requirements(self):
        for name,version in OLD.items():self.package(name,version)
        self.package("custom","1.0",["anyio>=4.0","urllib3>=2.7,<3"])
        self.package("unrelated","1.0")
        result=self.run_repair()
        self.assertEqual(result["legacy_packages_removed"],[])
        self.assertEqual(result["engine_backed_duplicates_removed"],sorted(OLD))
        self.assertEqual(result["removed_versions"],OLD)
        self.assertEqual({d.metadata["Name"] for d in metadata.distributions(path=[str(self.site)])},{"custom","unrelated"})

    def test_current_engine_duplicates_are_preserved_without_uv(self):
        for name,version in ENGINE.items():self.package(name,version)
        result=self.run_repair()
        self.assertEqual(result["removed_versions"],{})
        self.assertEqual(self.calls,[])
        self.assertEqual(len(list(metadata.distributions(path=[str(self.site)]))),4)

    def test_custom_legacy_requirement_fails_before_uv(self):
        self.legacy();self.package("custom","1.0",["wrapt>=1.16"])
        with self.assertRaisesRegex(RuntimeError,"custom edit dependency"):
            self.run_repair()
        self.assertEqual(self.calls,[])
        self.assertEqual(len(list(metadata.distributions(path=[str(self.site)]))),4)

    def test_custom_engine_version_or_direct_URL_must_not_be_silently_replaced(self):
        for requirement in ("urllib3<2.8","urllib3 @ https://public.invalid/custom.whl"):
            with self.subTest(requirement=requirement):
                folder=self.package("urllib3",OLD["urllib3"])
                custom=self.package("custom","1.0",[requirement])
                with self.assertRaisesRegex(RuntimeError,"rejects the engine"):
                    self.run_repair()
                self.assertEqual(self.calls,[])
                for directory in (folder,custom):
                    for file in directory.iterdir():file.unlink()
                    directory.rmdir()

    def test_foreign_RECORD_is_rejected_before_uv_and_external_file_is_untouched(self):
        folder=self.package("tos","2.9.2")
        victim=self.root.parent/"do-not-remove.txt";victim.write_text("unchanged",encoding="utf-8")
        with (folder/"RECORD").open("a",encoding="utf-8") as stream:stream.write(str(victim)+",,\n")
        with self.assertRaisesRegex(RuntimeError,"escaped"):
            self.run_repair()
        self.assertEqual(self.calls,[])
        self.assertEqual(victim.read_text("utf-8"),"unchanged")

    def test_missing_RECORD_fails_before_uv(self):
        self.package("tos","2.9.2",record=False)
        with self.assertRaisesRegex(RuntimeError,"no file inventory"):
            self.run_repair()
        self.assertEqual(self.calls,[])

    def test_missing_foreign_RECORD_path_is_also_rejected_before_uv(self):
        folder=self.package("tos","2.9.2")
        victim=self.root.parent/"absent-outside-env.txt"
        self.assertFalse(victim.exists())
        with (folder/"RECORD").open("a",encoding="utf-8") as stream:stream.write(str(victim)+",,\n")
        with self.assertRaisesRegex(RuntimeError,"escaped"):
            self.run_repair()
        self.assertEqual(self.calls,[])
        self.assertFalse(victim.exists())

    def test_normal_wheel_Scripts_entry_inside_edit_environment_is_allowed(self):
        self.package("tos","2.9.2",scripts=True)
        result=self.run_repair()
        self.assertEqual(result["legacy_packages_removed"],["tos"])
        self.assertFalse((self.root/".venv/Scripts/tos-fixture.exe").exists())

    def test_unsupported_python_or_root_is_rejected_before_uv(self):
        self.legacy()
        with self.assertRaisesRegex(RuntimeError,"Unsupported"):
            self.run_repair(version=(3,13,0))
        wrong=self.root.parent/"wrong-library";wrong.mkdir()
        (wrong/"griptape-nodes-library.json").write_text('{"name":"OtherLibrary"}',encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError,"Unsupported"):
            self.run_repair(root=wrong)
        self.assertEqual(self.calls,[])


@unittest.skipUnless(os.name == "nt" and shutil.which("powershell"), "Windows PowerShell installer transaction")
class InstallerTransaction(unittest.TestCase):
    """Run the real transaction against a workspace-only installation fixture."""

    def setUp(self):
        work = ROOT / "reports" / "predeploy-fixes-20261026" / "installer"
        work.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(prefix="installer-transaction-", dir=work)
        self.base = Path(self.tmp.name).resolve()
        self.junctions = []
        self.engine_python = sys.executable
        self.target = self.base / "libraries" / "HMB_GP_Production"
        self.rollback = self.base / "rollback"
        self.source = self.base / "source"
        self.source.mkdir()
        self.target.mkdir(parents=True)
        for name, content in {
            "old-runtime.py": b"previous runtime retained",
            ".hmb-install-receipt.json": b'{"previous":true}',
            "reports/result.json": b'{"task_id":"fixture-task","result":"preserve"}',
            ".venv/Scripts/keep.bin": b"existing environment retained",
            ".venv-tos/Scripts/keep.bin": b"existing isolated environment retained",
        }.items():
            path = self.target / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        self.before = self.inventory(self.target)
        constants = {}
        for node in ast.parse((ROOT / "tools/package_runtime_release.py").read_text("utf-8")).body:
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
                if node.targets[0].id in ("RUNTIME_INSTALL_FILES", "DISTRIBUTION_ONLY_FILES"):
                    constants[node.targets[0].id] = ast.literal_eval(node.value)
        # Installer paths and explicit fault injection are fixture-only. No
        # production path, app process or provider is accessed.
        expected_parent = "Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'GriptapeNodes\\libraries'"
        self.assertEqual(TEXT.count(expected_parent), 1)
        fixture_text = TEXT.replace(expected_parent, "'" + str(self.target.parent).replace("'", "''") + "'")
        fixture_text = fixture_text.replace("    $receiptPath = Join-Path $target '.hmb-install-receipt.json'",
            "    if ($global:fixtureFailure -eq 'receipt') { throw 'INJECTED receipt failure after native apply' }\n"
            "    $receiptPath = Join-Path $target '.hmb-install-receipt.json'")
        self.native_original = b"synthetic pristine editor for PS installation transaction\n"
        self.native_candidate = b"synthetic patched editor for PS installation transaction\n"
        self.native = self.base / "app/current/resources/editor-bundle/assets/index-DEZU41rc.js"
        self.native.parent.mkdir(parents=True)
        self.native.write_bytes(self.native_original)
        (self.native.parent.parent / ".version").write_text("0.128.1")
        sdk_site = self.native.parents[2] / "engine-bundle/python/Lib/site-packages"
        self.sdk_engine = sdk_site / "griptape_nodes/retained_mode/engine.py"
        sdk_events = self.sdk_engine.parent / "managers/event_manager.py"
        sdk_metadata = sdk_site / "griptape_nodes-0.101.3.dist-info/METADATA"
        for path in (self.sdk_engine, sdk_events, sdk_metadata):
            path.parent.mkdir(parents=True, exist_ok=True)
        self.sdk_engine.write_text("raise AssertionError('SDK must not execute')\ndef current_engine(): pass\n")
        sdk_events.write_text("class EventManager:\n    def add_pre_dispatch_hook(self, hook): pass\n    def remove_pre_dispatch_hook(self, hook): pass\n    def register_request_handlers(self, owner): pass\n")
        sdk_metadata.write_text("Name: griptape-nodes\nVersion: 0.101.3\n")
        self.native_state = self.base / "native-editor-installs"
        patcher_name = "tools/hmb_color_lut_native_header_patch.py"
        patcher_text = (ROOT / patcher_name).read_text("utf-8")
        footer = ("\nDEFAULT_SOURCE = Path(" + repr(str(self.native)) + ")\n"
                  "RELEASE_STATE_ROOT = Path(" + repr(str(self.native_state)) + ")\n"
                  "EXPECTED_SOURCE_SHA256 = " + repr(hashlib.sha256(self.native_original).hexdigest()) + "\n"
                  "patch_editor_source = lambda source: (" + repr(self.native_candidate.decode()) + ", {})\n"
                  "_require_release_stopped = lambda: None\n")
        self.assertEqual(patcher_text.count('if __name__ == "__main__":'), 1)
        patcher_data = patcher_text.replace('if __name__ == "__main__":', footer + '\nif __name__ == "__main__":').encode("utf-8")
        helper_name = "resources/editor/hmb-color-lut-native-header.js"
        helper_data = (ROOT / helper_name).read_bytes()
        descriptor_data = json.dumps({
            "schema": "hmb-native-editor-patch-release", "version": 1, "editor_version": "0.128.1",
            "bundle_name": "index-DEZU41rc.js", "source_sha256": hashlib.sha256(self.native_original).hexdigest(),
            "candidate_sha256": hashlib.sha256(self.native_candidate).hexdigest(),
            "helper_path": helper_name, "helper_sha256": hashlib.sha256(helper_data).hexdigest(),
            "patcher_path": patcher_name, "patcher_sha256": hashlib.sha256(patcher_data).hexdigest(),
        }).encode()
        overrides = {"Install_HMB_GP_Production.ps1": fixture_text.encode("utf-8-sig"),
                     patcher_name: patcher_data, helper_name: helper_data,
                     "resources/editor/native-editor-patch.json": descriptor_data}
        rows = []
        for name in (*constants["RUNTIME_INSTALL_FILES"], *constants["DISTRIBUTION_ONLY_FILES"]):
            data = overrides[name] if name in overrides else (ROOT / name).read_bytes()
            destination = self.source / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
            rows.append({"path": name, "install": name in constants["RUNTIME_INSTALL_FILES"],
                         "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
        self.runtime = [row for row in rows if row["install"]]
        manifest = {"schema": "hmb-release-closure", "version": 1, "release_version": "0.8.30",
                    "file_count": 67, "install_file_count": 60, "distribution_file_count": 7,
                    "files": rows, "policy_identity": {"fixture": True},
                    "build_fingerprint_sha256": self.fingerprint(rows),
                    "runtime_fingerprint_sha256": self.fingerprint(self.runtime)}
        encoded = json.dumps(manifest, ensure_ascii=True).encode()
        (self.source / "release-manifest.json").write_bytes(encoded)
        (self.source / "SHA256SUMS").write_text("".join(row["sha256"] + "  " + row["path"] + "\n" for row in rows)
                                                + hashlib.sha256(encoded).hexdigest() + "  release-manifest.json\n", encoding="utf-8")

    def tearDown(self):
        # TemporaryDirectory owns only the verified workspace fixture subtree.
        self.assertTrue(self.base.is_relative_to((ROOT / "reports").resolve()))
        for junction, original in reversed(self.junctions):
            self.assertTrue(junction.is_relative_to(self.base))
            # On Windows rmdir removes the junction itself, never its target.
            os.rmdir(junction)
            original.rename(junction)
        self.tmp.cleanup()

    def make_junction(self, folder):
        self.assertTrue(folder.is_relative_to(self.base))
        original = self.base / ("private-junction-target-" + str(len(self.junctions)))
        folder.rename(original)
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(folder), str(original)],
                                capture_output=True, text=True, timeout=10)
        if result.returncode:
            original.rename(folder)
            self.fail("Could not create the isolated junction fixture: " + result.stderr)
        self.junctions.append((folder, original))
        return original

    @staticmethod
    def inventory(folder):
        return {path.relative_to(folder).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in folder.rglob("*") if path.is_file()}

    @staticmethod
    def fingerprint(rows):
        values = [{key: row[key] for key in ("bytes", "path", "sha256")}
                  for row in sorted(rows, key=lambda row: row["path"])]
        return hashlib.sha256(json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def run_install(self, failure="none", *, background=False):
        quote = lambda value: "'" + str(value).replace("'", "''") + "'"
        harness = self.base / ("fixture-run-" + failure + ".ps1")
        prefix = "\n".join([
            "$global:fixtureRoot = " + quote(self.base), "$global:fixtureTarget = " + quote(self.target),
            "$global:fixtureFailure = " + quote(failure), "$global:backupPerformed = $false",
        ])
        harness.write_text(prefix + r'''
$ErrorActionPreference = 'Stop'
# A PowerShell 7 parent may pass its PSModulePath to Windows PowerShell 5.1.
# Load the child's own built-ins before installing the fixture interceptors.
Import-Module (Join-Path $PSHOME 'Modules\Microsoft.PowerShell.Utility\Microsoft.PowerShell.Utility.psd1')
Import-Module (Join-Path $PSHOME 'Modules\Microsoft.PowerShell.Management\Microsoft.PowerShell.Management.psd1')
function Assert-FixturePath([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    if (-not $full.StartsWith($global:fixtureRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Outside fixture' }
}
function Get-Process { [CmdletBinding()] param() return @() }
function Move-Item {
    [CmdletBinding()] param([string]$LiteralPath, [string]$Destination)
    Assert-FixturePath $LiteralPath; Assert-FixturePath $Destination
    $backup = $LiteralPath -eq $global:fixtureTarget -and -not $global:backupPerformed
    if ($backup -and $global:fixtureFailure -eq 'move') { throw 'INJECTED backup move failure' }
    if ($backup -and $global:fixtureFailure -eq 'pause_before_move') {
        [IO.File]::WriteAllText((Join-Path $global:fixtureRoot 'mutex-held'), 'ready')
        $watch = [Diagnostics.Stopwatch]::StartNew()
        while (-not (Test-Path -LiteralPath (Join-Path $global:fixtureRoot 'mutex-release'))) {
            if ($watch.Elapsed.TotalSeconds -gt 15) { throw 'fixture concurrency wait expired' }
            Start-Sleep -Milliseconds 50
        }
    }
    Microsoft.PowerShell.Management\Move-Item @PSBoundParameters
    if ($backup) {
        $global:backupPerformed = $true
        if ($global:fixtureFailure -eq 'after_move') { throw 'INJECTED after completed move' }
    }
}
function New-Item {
    [CmdletBinding()] param([string]$ItemType, [string]$Path, [switch]$Force)
    Assert-FixturePath $Path
    if ($Path -eq $global:fixtureTarget -and $global:backupPerformed -and $global:fixtureFailure -eq 'create') {
        throw 'INJECTED immediate post-backup failure'
    }
    Microsoft.PowerShell.Management\New-Item @PSBoundParameters
}
function Get-ChildItem {
    [CmdletBinding()] param([string]$LiteralPath, [switch]$Force, [switch]$Recurse, [switch]$Directory, [switch]$File, [string]$Filter)
    Assert-FixturePath $LiteralPath
    if ($LiteralPath -eq $global:fixtureTarget -and -not $Recurse -and $global:fixtureFailure -eq 'enumerate') {
        throw 'INJECTED preflight inventory failure'
    }
    Microsoft.PowerShell.Management\Get-ChildItem @PSBoundParameters
}
try {
''' + "& " + quote(self.source / "Install_HMB_GP_Production.ps1") + " -SourceRoot " + quote(self.source)
                           + " -TargetRoot " + quote(self.target) + " -RollbackRoot " + quote(self.rollback)
                           + " -EnginePython " + quote(self.engine_python)
                           + "\n} catch { Write-Output $_.Exception.Message; exit 17 }\n", encoding="utf-8-sig")
        arguments = [shutil.which("powershell"), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(harness)]
        if background:
            return subprocess.Popen(arguments, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        result = subprocess.run(arguments,
                                capture_output=True, text=True, timeout=45)
        return result

    def assert_preserved_failure(self, mode, message):
        result = self.run_install(mode)
        self.assertEqual(result.returncode, 17, result.stdout + result.stderr)
        self.assertIn(message, result.stdout)
        self.assertEqual(self.inventory(self.target), self.before)
        self.assertFalse(list(self.rollback.glob("failed-first-install-*")))
        self.assertEqual(self.native.read_bytes(), self.native_original)

    def test_backup_move_failure_leaves_existing_target_untouched(self):
        self.assert_preserved_failure("move", "INJECTED backup move failure")
        self.assertEqual(list(self.rollback.iterdir()), [])

    def test_unsupported_sdk_stops_before_first_library_move(self):
        self.sdk_engine.write_text("def unsupported_old_engine(): pass\n")
        result = self.run_install()
        self.assertEqual(result.returncode, 17, result.stdout + result.stderr)
        self.assertIn("Native editor prepare failed", result.stdout)
        self.assertIn("Missing engine.current_engine", result.stderr)
        self.assertEqual(self.inventory(self.target), self.before)
        self.assertEqual(self.native.read_bytes(), self.native_original)
        self.assertFalse(self.native_state.exists())
        self.assertEqual(list(self.rollback.iterdir()), [])

    def test_immediate_post_backup_failure_restores_exact_previous_files(self):
        self.assert_preserved_failure("create", "INJECTED immediate post-backup failure")
        self.assertEqual(list(self.rollback.iterdir()), [])

    def test_completed_backup_move_then_error_is_also_recovered(self):
        self.assert_preserved_failure("after_move", "INJECTED after completed move")
        self.assertEqual(list(self.rollback.iterdir()), [])

    def test_preflight_inventory_failure_never_moves_target(self):
        self.assert_preserved_failure("enumerate", "INJECTED preflight inventory failure")
        self.assertFalse(list(self.rollback.glob("v*")))

    def test_receipt_failure_restores_native_editor_and_old_library(self):
        self.assert_preserved_failure("receipt", "INJECTED receipt failure after native apply")
        self.assertEqual(len(list(self.rollback.glob("failed-new-*"))), 1)
        plans = list(self.native_state.glob("*/plan.json"))
        self.assertEqual(len(plans), 1)
        self.assertEqual(json.loads(plans[0].read_text())["status"], "rolled_back")

    def test_unknown_native_editor_fails_before_runtime_move(self):
        self.native.write_bytes(b"foreign native editor")
        result = self.run_install()
        self.assertEqual(result.returncode, 17)
        self.assertIn("Native editor prepare failed", result.stdout + result.stderr)
        self.assertEqual(self.inventory(self.target), self.before)
        self.assertEqual(self.native.read_bytes(), b"foreign native editor")
        self.assertFalse(list(self.rollback.glob("v*")))

    def test_already_current_native_editor_is_kept(self):
        self.native.write_bytes(self.native_candidate)
        result = self.run_install()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.native.read_bytes(), self.native_candidate)
        receipt = json.loads((self.target / ".hmb-install-receipt.json").read_text("utf-8-sig"))
        self.assertTrue(receipt["native_editor_patch"]["already_current"])
        self.assertFalse(receipt["native_editor_patch"]["changed"])

    def test_concurrent_second_installer_is_blocked_before_any_move(self):
        first = self.run_install("pause_before_move", background=True)
        try:
            deadline = time.monotonic() + 10
            while not (self.base / "mutex-held").exists() and first.poll() is None and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertTrue((self.base / "mutex-held").exists(), "first installer did not hold the transaction mutex")
            second = self.run_install()
            self.assertEqual(second.returncode, 17, second.stdout + second.stderr)
            self.assertIn("Another HMB installation", second.stdout)
            self.assertEqual(self.inventory(self.target), self.before)
            self.assertEqual(self.native.read_bytes(), self.native_original)
            (self.base / "mutex-release").write_text("release")
            stdout, stderr = first.communicate(timeout=30)
            self.assertEqual(first.returncode, 0, stdout + stderr)
            self.assertEqual(self.native.read_bytes(), self.native_candidate)
        finally:
            (self.base / "mutex-release").write_text("release")
            if first.poll() is None:
                first.communicate(timeout=30)

    def assert_reparse_rejected(self, original):
        before = self.inventory(original)
        result = self.run_install()
        self.assertEqual(result.returncode, 17, result.stdout + result.stderr)
        self.assertIn("reparse point", result.stdout)
        self.assertEqual(self.inventory(original), before)
        self.assertEqual(self.inventory(self.target), self.before)
        self.assertEqual(self.native.read_bytes(), self.native_original)
        self.assertFalse(self.native_state.exists())
        self.assertFalse(list(self.rollback.glob("v*")))

    def test_target_root_junction_cannot_move_external_user_data(self):
        self.assert_reparse_rejected(self.make_junction(self.target))

    def test_target_parent_junction_is_rejected_before_mutation(self):
        self.assert_reparse_rejected(self.make_junction(self.target.parent))

    def test_source_root_junction_is_rejected_before_mutation(self):
        self.assert_reparse_rejected(self.make_junction(self.source))

    def test_source_member_parent_junction_is_rejected_before_mutation(self):
        self.assert_reparse_rejected(self.make_junction(self.source / "resources"))

    def test_rollback_root_junction_is_rejected_before_mutation(self):
        self.rollback.mkdir()
        (self.rollback / "private.txt").write_text("preserve")
        self.assert_reparse_rejected(self.make_junction(self.rollback))

    def test_missing_rollback_below_junction_parent_is_rejected(self):
        parent = self.base / "backups"
        parent.mkdir()
        self.rollback = parent / "rollback"
        self.assert_reparse_rejected(self.make_junction(parent))

    def test_engine_python_parent_junction_is_rejected_before_execution(self):
        engine = self.base / "engine-python"
        engine.mkdir()
        self.engine_python = engine / "python.exe"
        self.engine_python.write_bytes(b"not an executable; must never be invoked")
        self.assert_reparse_rejected(self.make_junction(engine))

    def test_success_verifies_60_runtime_files_and_preserves_user_state(self):
        result = self.run_install()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("HMB_RUNTIME_INSTALL_OK", result.stdout)
        self.assertIn("RUNTIME_FILES=60", result.stdout)
        receipt = json.loads((self.target / ".hmb-install-receipt.json").read_text("utf-8-sig"))
        self.assertEqual(receipt["runtime_fingerprint_sha256"], self.fingerprint(self.runtime))
        self.assertEqual(len(receipt["runtime_files"]), 60)
        self.assertTrue(receipt["native_editor_patch"]["changed"])
        self.assertEqual(self.native.read_bytes(), self.native_candidate)
        installed = self.inventory(self.target)
        for row in self.runtime:
            self.assertEqual(installed[row["path"]], row["sha256"])
        for name in ("reports/result.json", ".venv/Scripts/keep.bin", ".venv-tos/Scripts/keep.bin"):
            self.assertEqual(installed[name], self.before[name])
        backups = list(self.rollback.glob("v*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(self.inventory(backups[0]), {name: value for name, value in self.before.items()
                                                     if name in ("old-runtime.py", ".hmb-install-receipt.json")})


if __name__=="__main__":
    unittest.main(verbosity=2)
