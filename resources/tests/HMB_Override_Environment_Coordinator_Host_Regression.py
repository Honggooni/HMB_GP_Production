"""Actual public SDK registration with the exact shipped environment coordinator.

A disposable uv venv contains RECORD-owned legacy sentinels only. No package is
installed, no provider is contacted, and installed/editor data is never opened.
Dependency installation is a recorder; targeted uv uninstall is real.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from unittest import mock

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'resources/tests')]
import HMB_Seedance_Execution_Mode_Host_Regression as host


def inventory(directory):
    return {str(p.relative_to(directory)):dict(sha=hashlib.sha256(p.read_bytes()).hexdigest(),mtime=p.stat().st_mtime_ns)
            for p in directory.rglob('*') if p.is_file()}


def setup(out, name, *, loaded=False, existing_lock=True):
    folder=out/'libraries'/name
    folder.mkdir(parents=True)
    result=subprocess.run([sys.executable,'-I','-B','-m','uv','venv','--no-project','--python',sys.executable,str(folder/'.venv')],capture_output=True,timeout=45)
    assert result.returncode==0,result.stderr.decode(errors='replace')
    site=folder/'.venv/Lib/site-packages'
    site.mkdir(parents=True,exist_ok=True)
    if existing_lock:
        (folder/'.venv/.lock').write_bytes(b'')
    schema=deepcopy(json.loads((ROOT/'griptape-nodes-library.json').read_text('utf-8-sig')))
    schema['metadata']['dependencies']={'pip_dependencies':[]}
    schema['metadata']['declarations']=[]
    schema['advanced_library_path']='_hmb_library_bootstrap.py'
    definition=deepcopy(schema['nodes'][0]);definition.update(class_name='OfflineColdProbe',file_path='HMBPromptLibrary.py')
    schema['nodes']=[definition];schema['widgets']=[];schema['settings']=[]
    (folder/'griptape-nodes-library.json').write_text(json.dumps(schema),encoding='utf-8')
    (folder/'_hmb_library_bootstrap.py').write_bytes((ROOT/'_hmb_library_bootstrap.py').read_bytes())
    (folder/'HMBPromptLibrary.py').write_text('from griptape_nodes.exe_types.node_types import DataNode\nclass OfflineColdProbe(DataNode):\n    def process(self): raise AssertionError("No execution allowed")\n',encoding='utf-8')
    for package,version in [('wrapt','1.16.0'),('Deprecated','1.3.1')]:
        leaf=package.lower()+'/__init__.py'
        (site/package.lower()).mkdir()
        (site/leaf).write_text('VALUE=1\n' if loaded else 'raise AssertionError("Legacy edit dependency imported before cleanup")\n',encoding='utf-8')
        dist=site/(package+'-'+version+'.dist-info');dist.mkdir()
        (dist/'METADATA').write_text('Metadata-Version: 2.1\nName: '+package+'\nVersion: '+version+'\n',encoding='utf-8')
        (dist/'RECORD').write_text(leaf+',,\n'+dist.name+'/METADATA,,\n'+dist.name+'/RECORD,,\n',encoding='utf-8')
    return folder,site


async def exercise(engine,phase,out):
    from griptape_nodes.retained_mode.events.library_events import RegisterLibraryFromFileRequest,InstallLibraryDependenciesResultSuccess,UnloadLibraryFromRegistryRequest
    observations=[];instances=[];dependency_operations=[]
    async def install(request):
        dependency_operations.append('sdk_install_offline_recorder')
        return InstallLibraryDependenciesResultSuccess(library_name='HMB_GP_Production',dependencies_installed=0,result_details='Offline dependency recorder')
    original=engine.library_manager.module_loading.load_advanced_library_module
    def load(*args,**kwargs):
        # The exact product module import and constructor run first. Unrelated
        # editor migration/web worker callbacks are outside this environment test.
        instance=original(*args,**kwargs)
        instances.append(instance)
        instance.before_library_nodes_loaded=lambda *a,**k:None
        return instance
    async def register(folder):
        host.REQUESTS+=1
        result=await engine.ahandle_request(RegisterLibraryFromFileRequest(file_path=str(folder/'griptape-nodes-library.json'),broadcast_result=False))
        assert result.succeeded(),str(result.result_details)
        return instances[-1]._hmb_environment_repair_summary
    with mock.patch.object(engine.library_manager.dependencies,'install_library_dependencies_request',install),mock.patch.object(engine.library_manager.module_loading,'should_lazy_load_nodes',return_value=False),mock.patch.object(engine.library_manager.module_loading,'load_advanced_library_module',load):
        folder,site=setup(out,'cold',existing_lock=False)
        before=inventory(folder/'.venv')
        own_payloads=[site/'wrapt/__init__.py',site/'deprecated/__init__.py']
        cold=await register(folder)
        assert cold['status']=='repaired' and not cold['restart_required'],cold
        assert set(cold['removed_distributions'])=={'wrapt','deprecated'},cold
        assert all(not p.exists() for p in own_payloads)
        after=inventory(folder/'.venv')
        removed=set(before)-set(after)
        assert len(removed)==6 and all(before[k]==v for k,v in after.items() if k in before),(removed,set(after)-set(before))
        assert set(after)-set(before)=={'.lock'} and (folder/'.venv/.lock').read_bytes()==b''
        assert str(site) in sys.path
        assert not any(getattr(m,'__file__',None) in map(str,own_payloads) for m in list(sys.modules.values()) if m is not None)
        first_info=engine.library_manager.get_library_info_by_library_name('HMB_GP_Production')
        assert 'ShadowedEnginePackagesProblem' in {type(p).__name__ for p in first_info.problems}
        observations.append(dict(case='actual_cold_constructor_targeted_cleanup',summary=cold,removed_files=len(removed),unrelated_files_preserved=len(after)-1,legacy_module_imports=0,verified_new_uv_housekeeping_lock=1,initial_sdk_shadow_problem_retained_until_refresh=True))
        host.send(engine,UnloadLibraryFromRegistryRequest(library_name='HMB_GP_Production'))
        refresh=await register(folder)
        assert refresh['status']=='repaired' and refresh.get('cached') is True and not refresh['restart_required'],refresh
        assert inventory(folder/'.venv')==after
        refreshed_info=engine.library_manager.get_library_info_by_library_name('HMB_GP_Production')
        assert 'ShadowedEnginePackagesProblem' not in {type(p).__name__ for p in refreshed_info.problems}
        observations.append(dict(case='same_code_normal_refresh_fast_cache',summary=refresh,original_files_unchanged=True,previous_shadow_problem_cleared_by_public_sdk_refresh=True))
        host.send(engine,UnloadLibraryFromRegistryRequest(library_name='HMB_GP_Production'))
        with (folder/'_hmb_library_bootstrap.py').open('a',encoding='utf-8') as stream:stream.write('\n# New Override authoring identity\n')
        update=await register(folder)
        assert update==dict(status='pending',restart_required=True,reason='loaded_hmb_code'),update
        assert inventory(folder/'.venv')==after
        observations.append(dict(case='new_override_loaded_nodes_defers',summary=update,original_files_unchanged=True))
        host.send(engine,UnloadLibraryFromRegistryRequest(library_name='HMB_GP_Production'))
        second,second_site=setup(out,'loaded-dependency',loaded=True)
        payload=second_site/'wrapt/__init__.py'
        spec=importlib.util.spec_from_file_location('_hmb_loaded_legacy_dependency_fixture',payload)
        module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
        second_before=inventory(second/'.venv')
        loaded=await register(second)
        assert loaded==dict(status='pending',restart_required=True,reason='loaded_dependency'),loaded
        assert inventory(second/'.venv')==second_before
        observations.append(dict(case='actual_loaded_record_member_preserved',summary=loaded,original_files_unchanged=True))
        host.send(engine,UnloadLibraryFromRegistryRequest(library_name='HMB_GP_Production'))
        sys.modules.pop(spec.name,None)
    for row in observations:host.record(row['case'],**{k:v for k,v in row.items() if k!='case'})
    report=dict(passed=True,scope='Actual SDK RegisterLibraryFromFileRequest and exact product constructor; disposable venv targeted uv uninstall only',cases=observations,source_sha256=hashlib.sha256((ROOT/'_hmb_library_bootstrap.py').read_bytes()).hexdigest(),actual_package_install_calls=0,actual_provider_calls=0,actual_live_engine_connections=0,actual_cleanup_commands=1,optional_tos_prepare_calls=0)
    (out/'coordinator-native-summary.json').write_text(json.dumps(report,indent=2),encoding='utf-8')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,default=ROOT/'reports/release811-local812-20261019/override-sdk/coordinator-r1')
    args=parser.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=True)
    host.exercise=exercise;host.run_phase('coordinator-native',out)
    print('HMB_OVERRIDE_COORDINATOR_NATIVE=PASS cases=4 cleanup=1 provider=0 network=0')
if __name__=='__main__':main()
