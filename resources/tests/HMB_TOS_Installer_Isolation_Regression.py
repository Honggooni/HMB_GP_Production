"""Exact public installer repair: no real environment or package operations."""
from __future__ import annotations

from contextlib import redirect_stdout
import importlib.metadata as metadata
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
TEXT = (ROOT / "Install_HMB_GP_Production.ps1").read_text(encoding="utf-8-sig")
SCRIPTS = re.findall(r"(?ms)^    \$repair = @'\n(.*?)^'@\n", TEXT)
assert len(SCRIPTS) == 1, "The installer must expose one bounded repair literal"
REPAIR = compile(SCRIPTS[0], "<exact-public-installer-TOS-repair>", "exec")
ENGINE = {"anyio":"4.15.1", "charset-normalizer":"3.5.2", "idna":"3.20", "urllib3":"2.8.0"}
OLD = {"anyio":"4.14.2", "charset-normalizer":"3.5.1", "idna":"3.19", "urllib3":"2.7.0"}


class InstallerRepair(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="hmb-tos-installer-contract-")
        self.root = Path(self.tmp.name) / "HMB_GP_Production"
        self.site = self.root / ".venv/Lib/site-packages"
        self.site.mkdir(parents=True)
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
        self.assertEqual(args[7:9],["--python",str(self.root/".venv/Scripts/python.exe")])
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
        with mock.patch.object(sys,"argv",["repair",str(root or self.root),"0","1"]), mock.patch.object(sys,"version_info",version), mock.patch.object(metadata,"version",side_effect=lambda name:ENGINE[name]), mock.patch.object(subprocess,"run",side_effect=self.fake_uv), redirect_stdout(output):
            exec(REPAIR,{"__name__":"_fixture_exact_installer_repair"})
        return json.loads(output.getvalue())

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
        with self.assertRaisesRegex(SystemExit,"Unsupported"):
            self.run_repair(version=(3,13,0))
        wrong=self.root.parent/"wrong-library";wrong.mkdir()
        with self.assertRaisesRegex(SystemExit,"Unsupported"):
            self.run_repair(root=wrong)
        self.assertEqual(self.calls,[])


if __name__=="__main__":
    unittest.main(verbosity=2)
