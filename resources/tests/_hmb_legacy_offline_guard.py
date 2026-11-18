"""Audit-only replacement for historical offline runner. No live network/service calls."""
import atexit, hashlib, json, os, runpy, socket, sys, threading
from pathlib import Path
root=Path(os.environ['HMB_SDK_ISOLATED_ROOT']).resolve(); root.mkdir(parents=True,exist_ok=True)
for key in ('APPDATA','LOCALAPPDATA','GTN_ENGINE_CONFIG_DIR','GTN_ENGINE_DATA_DIR','GTN_ENGINE_STATE_DIR','GTN_CONFIG_WORKSPACE_DIRECTORY','XDG_DATA_HOME','XDG_STATE_HOME','XDG_CONFIG_HOME','XDG_CACHE_HOME'):
    location=root/key; location.mkdir(exist_ok=True); os.environ[key]=str(location)
seen=[]; scope=threading.local(); pair=socket.socketpair; bind=socket.socket.bind

def guardedpair(*a,**k):
    prev=getattr(scope,'own',None);scope.own=set()
    try:return pair(*a,**k)
    finally:scope.own=prev

def guardedbind(self,addr):
    if getattr(scope,'own',None) is None or addr[0] not in ('127.0.0.1','::1') or addr[1]!=0: raise RuntimeError('No service listeners')
    result=bind(self,addr);scope.own.add(tuple(self.getsockname()[:2]));return result

def audit(event,args):
    if event=='socket.connect' and tuple(args[1][:2]) not in (getattr(scope,'own',None) or ()):
        seen.append(event);raise RuntimeError('External or live-engine networking blocked')
    if event=='socket.getaddrinfo' and args[0] not in ('127.0.0.1','localhost','::1',None):
        seen.append(event);raise RuntimeError('External DNS blocked')
    if event=='subprocess.Popen':raise PermissionError('Offline test: optional hardware detection unavailable')
    if event=='os.system':raise RuntimeError('No shell in SDK phase')
socket.socketpair=guardedpair;socket.socket.bind=guardedbind;sys.addaudithook(audit)
receipt=Path(os.environ['HMB_SDK_GUARD_RECEIPT']); guard_sha=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
atexit.register(lambda:receipt.write_text(json.dumps(dict(external_network_attempt_count=len(seen),events=seen,audit_guard_sha256=guard_sha))))
target=sys.argv.pop(1);sys.argv[0]=target;sys.path.insert(0,str(Path(target).resolve().parent));runpy.run_path(target,run_name='__main__')
