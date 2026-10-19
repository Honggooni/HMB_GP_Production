"""TOS subprocess isolation, private stdio and cleanup; no storage/model calls."""
from __future__ import annotations

import ast
from contextlib import suppress
from dataclasses import dataclass
import importlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import time
import tomllib
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlparse
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "HMBSeedanceGeneration.py"
TREE = ast.parse(SOURCE.read_text(encoding="utf-8"))
NAMES = {"_TOS_RPC_BYTES", "_TOS_RUNTIME_REQUIREMENT", "_TOS_HELPER_SOURCE",
         "_isolated_tos_runtime_python", "_IsolatedTOSResponse", "_IsolatedTOSModule", "_IsolatedTOSClient"}
PARTS = [n for n in TREE.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in NAMES
         or isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in NAMES for t in n.targets)]
NS = dict(Any=Any, Path=Path, os=os, re=re, json=json, subprocess=subprocess, threading=threading,
          time=time, dataclass=dataclass, suppress=suppress, urlparse=urlparse, _THIS_DIR=ROOT)
exec(compile(ast.Module(body=PARTS, type_ignores=[]), str(SOURCE), "exec"), NS)
GEN = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == "HMBSeedanceGeneration")
METHODS = {"_create_tos_storage_context", "_upload_local_video_to_tos", "_delete_temporary_tos_video_uploads"}
SHELL = ast.ClassDef(name="Generator", bases=[], keywords=[], body=[n for n in GEN.body if isinstance(n, ast.FunctionDef) and n.name in METHODS], decorator_list=[], type_params=[])
NS.update(TOS_ACCESS_KEY_ID_SECRET="AK", TOS_SECRET_ACCESS_KEY_SECRET="SK", TOS_BUCKET_NAME_SECRET="BUCKET",
          TOS_TEMP_OBJECT_PREFIX="hmb-seedance-temp", _TOS_BUCKET_PATTERN=re.compile(r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$"))
import mimetypes
from uuid import uuid4
NS.update(mimetypes=mimetypes, uuid4=uuid4)
exec(compile(ast.fix_missing_locations(ast.Module(body=[SHELL], type_ignores=[])), str(SOURCE), "exec"), NS)
Proxy = NS["_IsolatedTOSClient"]
AUTH = dict(ak="AK_SENTINEL_PRIVATE", sk="SK_SENTINEL_PRIVATE", endpoint="tos-cn-beijing.volces.com", region="cn-beijing")
KEY = "hmb-seedance-temp/" + "a" * 32 + ".mov"


class Child:
    """Controlled stdio boundary: the product proxy remains unmodified."""
    def __init__(self, args, **kwargs):
        self.args, self.kwargs = args, kwargs
        self.returncode = None
        self.inputs = []
        self.killed = False

    def communicate(self, input=None, timeout=None):
        self.inputs.append(input)
        self.returncode = 0
        return json.dumps(dict(version=1, ok=True, status_code=200, signed_url="https://bucket.tos-cn-beijing.volces.com/" + KEY + "?signed=fixture")).encode(), None

    def poll(self):
        return self.returncode

    def kill(self):
        self.killed = True
        self.returncode = -9


class Isolation(unittest.TestCase):
    def client(self, live=lambda: True):
        return Proxy(Path("C:/fixture/.venv-tos/Scripts/python.exe"), AUTH, is_live=live)

    def test_edit_dependencies_cannot_resolve_TOS_or_wrapt_into_engine(self):
        project = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))["project"]
        manifest = json.loads((ROOT / "griptape-nodes-library.json").read_text("utf-8"))
        edit = manifest["metadata"]["dependencies"]["pip_dependencies"]
        self.assertEqual(set(edit), set(project["dependencies"]))
        self.assertFalse(any(re.match(r"(?i)(tos|wrapt|griptape-nodes-engine)(?:[<>=\[]|$)", x) for x in edit))
        self.assertEqual(project["optional-dependencies"]["tos-runtime"], ["tos==2.9.2"])

    def test_TOS_import_exists_only_inside_fixed_child_literal(self):
        for node in ast.walk(TREE):
            if isinstance(node, ast.Import):
                self.assertFalse(any(a.name in {"tos", "wrapt"} for a in node.names))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "import_module" and node.args:
                self.assertFalse(isinstance(node.args[0], ast.Constant) and node.args[0].value in {"tos", "wrapt"})
        self.assertIn('importlib.import_module("tos")', NS["_TOS_HELPER_SOURCE"])
        compile(NS["_TOS_HELPER_SOURCE"], "<fixed-TOS-child>", "exec")

    def test_missing_runtime_is_actionable_and_does_not_import_TOS(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(NS, _THIS_DIR=Path(tmp)):
            with self.assertRaisesRegex(RuntimeError, "isolated.*runtime.*setup"):
                NS["_isolated_tos_runtime_python"]()

    def test_runtime_is_exact_local_venv_with_system_site_disabled(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(NS, _THIS_DIR=Path(tmp)):
            runtime = Path(tmp) / ".venv-tos"
            python = runtime / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            python.parent.mkdir(parents=True)
            python.write_bytes(b"fixture only")
            (runtime / "pyvenv.cfg").write_text("include-system-site-packages = false\n", encoding="utf-8")
            self.assertEqual(NS["_isolated_tos_runtime_python"](), python.resolve())
            (runtime / "pyvenv.cfg").write_text("include-system-site-packages = true\n", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                NS["_isolated_tos_runtime_python"]()
            (runtime / "pyvenv.cfg").write_text("include-system-site-packages = false\ninclude-system-site-packages = true\n", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                NS["_isolated_tos_runtime_python"]()

    def test_secrets_use_stdin_only_and_environment_is_scrubbed(self):
        children = []
        def start(*a, **k):
            children.append(Child(*a, **k)); return children[-1]
        with mock.patch.object(subprocess, "Popen", start), mock.patch.dict(os.environ, {"TOS_ACCESS_KEY_ID": AUTH["ak"], "HTTP_PROXY": "http://private.invalid", "OPENAI_API_KEY": "unrelated-private"}):
            self.client().put_object_from_file("bucket-name", KEY, "C:/fixture.mov", content_type="video/quicktime")
        child = children[0]
        self.assertEqual(child.args[1:4], ["-I", "-B", "-c"])
        self.assertEqual(child.args[4], NS["_TOS_HELPER_SOURCE"])
        self.assertNotIn(AUTH["ak"], repr(child.args) + repr(child.kwargs))
        self.assertNotIn(AUTH["sk"], repr(child.args) + repr(child.kwargs))
        self.assertNotIn("HTTP_PROXY", child.kwargs["env"])
        self.assertNotIn("OPENAI_API_KEY", child.kwargs["env"])
        self.assertEqual(child.kwargs["stderr"], subprocess.DEVNULL)
        self.assertTrue(child.kwargs["close_fds"])
        request = json.loads(child.inputs[0])
        self.assertEqual(request["auth"], AUTH)
        self.assertLessEqual(len(child.inputs[0]), NS["_TOS_RPC_BYTES"])

    def test_context_constructs_proxy_and_preserves_engine_import_state(self):
        node = NS["Generator"]()
        node._get_optional_secret = {"AK":AUTH["ak"],"SK":AUTH["sk"],"BUCKET":"bucket-name"}.get
        node._normalize_tos_endpoint = lambda value: value
        node._runtime_node_is_live = lambda **kwargs: True
        before = {name: sys.modules.get(name) for name in ("tos", "wrapt")}
        with mock.patch.dict(NS, _isolated_tos_runtime_python=lambda: Path("C:/fixture/.venv-tos/Scripts/python.exe")):
            module, proxy, bucket = node._create_tos_storage_context(dict(tos_endpoint=AUTH["endpoint"], tos_region=AUTH["region"]))
        self.assertIsInstance(proxy, Proxy)
        self.assertEqual(bucket, "bucket-name")
        self.assertEqual(module.HttpMethodType.Http_Method_Get, "GET")
        self.assertEqual({name:sys.modules.get(name) for name in before}, before)

    def test_request_bound_rejects_before_child_start(self):
        client = self.client()
        client._auth["sk"] = "X" * 40000
        with mock.patch.object(subprocess, "Popen") as spawn, self.assertRaisesRegex(RuntimeError, "bounded"):
            client._request("presign", "bucket-name", KEY, expires=3600)
        spawn.assert_not_called()

    def test_malformed_or_oversized_response_fails_without_secret_error_chain(self):
        for output in (b"not-json", b"x"*32769, b'{"version":2,"ok":true}', b'{"version":true,"ok":true}', b'{"version":1,"ok":false}'):
            with self.subTest(output_length=len(output)):
                child = Child([])
                def response(**kwargs):
                    child.returncode=0; return output,None
                child.communicate=response
                with mock.patch.object(subprocess,"Popen",return_value=child), self.assertRaises(RuntimeError) as caught:
                    self.client()._request("presign","bucket-name",KEY,expires=3600)
                self.assertIsNone(caught.exception.__cause__)
                self.assertNotIn(AUTH["ak"],str(caught.exception))
                self.assertNotIn(AUTH["sk"],str(caught.exception))

    def test_cancelled_upload_kills_child_then_attempts_delete_even_when_not_live(self):
        children=[]; live=iter([True,True,False])
        def start(*a,**k):
            child=Child(*a,**k);children.append(child)
            if len(children)==1:
                def wait(**kwargs):
                    if child.killed:return b"",None
                    raise subprocess.TimeoutExpired("fixed helper",0.1)
                child.communicate=wait
            return child
        with mock.patch.object(subprocess,"Popen",start):
            with self.assertRaises(RuntimeError):
                self.client(lambda:next(live,False)).put_object_from_file("bucket-name",KEY,"C:/fixture.mov",content_type="video/quicktime")
        self.assertTrue(children[0].killed)
        self.assertEqual(json.loads(children[1].inputs[0])["operation"],"delete")

    def test_timeout_kills_child_and_does_not_report_success(self):
        child=Child([])
        with mock.patch.object(subprocess,"Popen",return_value=child), mock.patch.object(time,"monotonic",side_effect=[0,1000]):
            with self.assertRaises(RuntimeError):
                self.client()._request("put","bucket-name",KEY,path="C:/fixture.mov",content_type="video/quicktime")
        self.assertTrue(child.killed)

    def test_late_completion_after_deletion_is_rejected_and_cleanup_is_still_allowed(self):
        live=iter([True,True,False]);children=[]
        def start(*a,**k):
            child=Child(*a,**k);children.append(child);return child
        with mock.patch.object(subprocess,"Popen",start),self.assertRaises(RuntimeError):
            self.client(lambda:next(live,False)).put_object_from_file("bucket-name",KEY,"C:/fixture.mov",content_type="video/quicktime")
        self.assertEqual(json.loads(children[-1].inputs[0])["operation"],"delete")

    def test_original_upload_presign_cleanup_contract_keeps_unique_key_and_expiry(self):
        requests=[]
        class RecordingChild(Child):
            def communicate(self,input=None,timeout=None):
                if input: requests.append(json.loads(input))
                return super().communicate(input=input,timeout=timeout)
        node=NS["Generator"]();node._temporary_tos_video_uploads=[]
        client=self.client()
        with mock.patch.object(subprocess,"Popen",RecordingChild):
            value=node._upload_local_video_to_tos(Path("C:/fixture.mov"),dict(tos_url_validity_seconds=86400),(NS["_IsolatedTOSModule"],client,"bucket-name"))
            self.assertTrue(value.startswith("https://"))
            self.assertEqual(len(node._temporary_tos_video_uploads),1)
            node._delete_temporary_tos_video_uploads(node._temporary_tos_video_uploads)
        self.assertEqual([r['operation'] for r in requests],["put","presign","delete"])
        self.assertEqual(len({r['key'] for r in requests}),1)
        self.assertEqual(requests[1]['expires'],86400)
        self.assertTrue(client._closed)
        self.assertFalse(client._auth)

    def test_presign_error_deletes_uploaded_object_and_closes_client(self):
        requests=[]
        class BadSignChild(Child):
            def communicate(self,input=None,timeout=None):
                if input:
                    request=json.loads(input);requests.append(request)
                    if request['operation']=='presign':
                        self.returncode=0;return b'{"version":1,"ok":true,"signed_url":"https://secret@invalid.example/"}',None
                return super().communicate(input=input,timeout=timeout)
        node=NS["Generator"]();node._temporary_tos_video_uploads=[];client=self.client()
        with mock.patch.object(subprocess,"Popen",BadSignChild),self.assertRaises(RuntimeError):
            node._upload_local_video_to_tos(Path("C:/fixture.mov"),dict(tos_url_validity_seconds=3600),(NS["_IsolatedTOSModule"],client,"bucket-name"))
        self.assertEqual([r['operation'] for r in requests],["put","presign","delete"])
        self.assertEqual(node._temporary_tos_video_uploads,[])
        self.assertTrue(client._closed)

    def run_helper(self,operation,**changes):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name in ("tos","wrapt"):
                (root/(name+".py")).write_text("fixture",encoding="utf-8")
            movie=root/"source.mov";movie.write_bytes(b"fixture-video")
            request=dict(version=1,runtime_root=str(root),auth=AUTH,operation=operation,bucket="bucket-name",key=KEY,path=str(movie),content_type="video/quicktime",expires=3600)
            request.update(changes)
            # This is a real child executing the exact fixed helper, with only
            # TOS/network APIs substituted. It never reads installed secrets.
            bootstrap='''import sys,json,importlib,importlib.metadata,importlib.util,types,contextlib,logging,re
from pathlib import Path
from urllib.parse import urlparse
root=Path(sys.argv[1]);sys.prefix=str(root)
importlib.metadata.version=lambda name: {"tos":"2.9.2","wrapt":"1.16.0"}[name]
importlib.util.find_spec=lambda name: types.SimpleNamespace(origin=str(root/(name+".py")))
class Client:
 def __init__(self,*args,**kwargs):
  assert args==("AK_SENTINEL_PRIVATE","SK_SENTINEL_PRIVATE","tos-cn-beijing.volces.com","cn-beijing")
  assert kwargs==dict(connection_time=10,socket_timeout=30,max_retry_count=0)
 def put_object_from_file(self,bucket,key,path,**kwargs):
  assert Path(path).read_bytes()==b"fixture-video"
  print("SDK diagnostic SK_SENTINEL_PRIVATE")
  return types.SimpleNamespace(status_code=200)
 def pre_signed_url(self,method,bucket,key,**kwargs):
  assert method=="GET"
  return types.SimpleNamespace(signed_url="https://bucket.tos-cn-beijing.volces.com/"+key+"?fixture=signature")
 def delete_object(self,*args): print("SDK diagnostic AK_SENTINEL_PRIVATE")
 def close(self): print("SDK diagnostic SK_SENTINEL_PRIVATE")
sys.modules["tos"]=types.SimpleNamespace(TosClientV2=Client,HttpMethodType=types.SimpleNamespace(Http_Method_Get="GET"))
sys.modules["wrapt"]=types.SimpleNamespace()
'''
            result=subprocess.run([sys.executable,"-I","-B","-c",bootstrap+"\n"+NS["_TOS_HELPER_SOURCE"],str(root)],input=json.dumps(request).encode(),capture_output=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr.decode(errors="replace"))
            self.assertNotIn(b"SENTINEL_PRIVATE",result.stdout+result.stderr)
            self.assertLessEqual(len(result.stdout),NS["_TOS_RPC_BYTES"])
            return json.loads(result.stdout)

    def test_real_child_exact_helper_probe_requires_no_credentials(self):
        result=self.run_helper("probe",auth=None)
        self.assertTrue(result["ok"])
        self.assertEqual(result["tos_version"],"2.9.2")
        self.assertEqual(result["wrapt_version"],"1.16.0")
        self.assertTrue(result["isolated"])

    def test_real_child_put_presign_delete_and_SDK_stdout_scrubbing(self):
        for operation in ("put","presign","delete"):
            with self.subTest(operation=operation):
                self.assertTrue(self.run_helper(operation)["ok"])

    def test_real_child_rejects_foreign_prefix_and_oversized_stdin(self):
        self.assertFalse(self.run_helper("probe",runtime_root=str(ROOT))["ok"])
        self.assertFalse(self.run_helper("put",auth=dict(AUTH,sk="X"*40000))["ok"])

    def test_real_child_rejects_untrusted_object_endpoint_and_expiry(self):
        for operation,changes in (("put",dict(key="foreign/object.mov")),("put",dict(auth=dict(AUTH,endpoint="evil.invalid"))),("put",dict(auth=dict(AUTH,endpoint="secret@tos-cn-beijing.volces.com"))),("presign",dict(expires=True)),("presign",dict(expires=1)),("presign",dict(expires=2592001)),("arbitrary",{}),("put",dict(version=True))):
            with self.subTest(operation=operation,changed_fields=list(changes)):
                self.assertFalse(self.run_helper(operation,**changes)["ok"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
