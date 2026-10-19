"""Actual SDK registration order and fail-closed Advanced constructor boundary.

Only the dependency-install operation and its shadow-package query are offline
recorders. Native RegisterLibraryFromFileRequest, edit-path activation, Advanced
module loading, callbacks and eager node imports execute without an SDK patch.
All package sentinels and libraries live in this fixture's isolated directory.
"""
from __future__ import annotations
import argparse
import builtins
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'resources/tests')]
import HMB_Seedance_Execution_Mode_Host_Regression as host


async def exercise(engine, phase, out):
    from griptape_nodes.retained_mode.events.library_events import (
        RegisterLibraryFromFileRequest, InstallLibraryDependenciesResultSuccess,
        UnloadLibraryFromRegistryRequest,
    )
    from griptape_nodes.node_library.library_registry import LibraryRegistry
    original = json.loads((ROOT/'griptape-nodes-library.json').read_text('utf-8-sig'))
    all_results = []
    for variant in ('normal', 'before_callback_raises', 'constructor_raises'):
        folder = out/'fixture-libraries'/variant
        site = folder/'.venv/Lib/site-packages'
        site.mkdir(parents=True, exist_ok=True)
        sentinel = site/'hmb_order_legacy_sentinel.py'
        sentinel.write_text('raise AssertionError("Legacy dependency must never be imported")\n', encoding='utf-8')
        sentinel_sha = hashlib.sha256(sentinel.read_bytes()).hexdigest()
        trace = []
        def record(stage):
            trace.append(dict(stage=stage, site_on_path=str(site) in sys.path,
                sentinel_loaded='hmb_order_legacy_sentinel' in sys.modules))
        schema = deepcopy(original)
        schema['name'] = 'OfflineOverrideOrder_' + variant
        schema['metadata']['library_version'] = '0.0.1'
        schema['metadata']['dependencies'] = {'pip_dependencies': []}
        schema['metadata']['declarations'] = []
        schema['advanced_library_path'] = 'order_advanced.py'
        definition = deepcopy(schema['nodes'][0])
        definition.update(class_name='OfflineOrderProbeNode', file_path='order_node.py')
        schema['nodes'] = [definition]
        schema['widgets'] = []
        schema['settings'] = []
        manifest = folder/'griptape-nodes-library.json'
        manifest.write_text(json.dumps(schema), encoding='utf-8')
        advanced = '''from __future__ import annotations
import builtins
from griptape_nodes.node_library.advanced_node_library import AdvancedNodeLibrary
builtins._hmb_override_order_record("advanced_import")
class OfflineOrderLibrary(AdvancedNodeLibrary):
    def __init__(self):
        builtins._hmb_override_order_record("constructor")
        if VARIANT == "constructor_raises":
            raise RuntimeError("Offline constructor admission gate")
    def before_library_nodes_loaded(self, library_data, library):
        builtins._hmb_override_order_record("before_nodes")
        if VARIANT == "before_callback_raises":
            raise RuntimeError("Offline before callback failure")
    def after_library_nodes_loaded(self, library_data, library):
        builtins._hmb_override_order_record("after_nodes")
'''.replace('VARIANT', repr(variant))
        (folder/'order_advanced.py').write_text(advanced, encoding='utf-8')
        (folder/'order_node.py').write_text('''import builtins
from griptape_nodes.exe_types.node_types import DataNode
builtins._hmb_override_order_record("node_import")
class OfflineOrderProbeNode(DataNode):
    def process(self):
        raise AssertionError("Registration fixture must never execute a node")
''', encoding='utf-8')
        async def install(request):
            record('dependency_install')
            return InstallLibraryDependenciesResultSuccess(library_name=schema['name'], dependencies_installed=0,
                result_details='Offline ordering recorder; no package operation')
        async def shadow(*args, **kwargs):
            record('shadow_query')
            return []
        with mock.patch.object(builtins, '_hmb_override_order_record', record, create=True), \
             mock.patch.object(engine.library_manager.dependencies, 'install_library_dependencies_request', install), \
             mock.patch.object(engine.library_manager.dependencies, 'shadowed_engine_packages', shadow), \
             mock.patch.object(engine.library_manager.module_loading, 'should_lazy_load_nodes', return_value=False):
            host.REQUESTS += 1
            result = await engine.ahandle_request(RegisterLibraryFromFileRequest(file_path=str(manifest), broadcast_result=False))
        phases = [row['stage'] for row in trace]
        observation = dict(variant=variant, result_type=type(result).__name__, trace=trace,
            result_details=str(result.result_details))
        all_results.append(observation)
        (out/'hook-order-observations.json').write_text(json.dumps(all_results, indent=2), encoding='utf-8')
        assert phases[:4] == ['dependency_install','shadow_query','advanced_import','constructor'], observation
        assert all(not row['site_on_path'] for row in trace[:2]), observation
        assert all(row['site_on_path'] for row in trace[2:]), observation
        assert all(not row['sentinel_loaded'] for row in trace), observation
        assert hashlib.sha256(sentinel.read_bytes()).hexdigest() == sentinel_sha
        if variant == 'constructor_raises':
            assert result.failed() and phases == ['dependency_install','shadow_query','advanced_import','constructor'], observation
            assert schema['name'] not in LibraryRegistry.list_libraries(), observation
        else:
            assert result.succeeded(), observation
            assert phases == ['dependency_install','shadow_query','advanced_import','constructor','before_nodes','node_import','after_nodes'], observation
            info = engine.library_manager.get_library_info_by_library_name(schema['name'])
            problems = [type(problem).__name__ for problem in info.problems]
            assert ('BeforeLibraryCallbackProblem' in problems) == (variant == 'before_callback_raises'), problems
            host.send(engine, UnloadLibraryFromRegistryRequest(library_name=schema['name']))
        while str(site) in sys.path:
            sys.path.remove(str(site))
        while str(folder) in sys.path:
            sys.path.remove(str(folder))
        host.record('native_advanced_hook_order_' + variant, phases=phases,
            stale_site_exposed_before_advanced_import=True, stale_module_imported=False,
            actual_dependency_operations=0, provider_calls=0)
    (out/'hook-order-summary.json').write_text(json.dumps(dict(passed=True, cases=all_results,
        conclusion='The public Advanced constructor runs after edit-venv sys.path activation but before node registration. Constructor failure is fail-closed; before-node callback exceptions are recorded but node imports continue.',
        actual_dependency_operations=0, actual_provider_calls=0, source_or_installed_edits=0), indent=2), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, default=ROOT/'reports/release811-local812-20261019/override-sdk/order')
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    host.exercise = exercise
    host.run_phase('override-order', out)
    print('HMB_OVERRIDE_ENVIRONMENT_HOOK_ORDER_HOST=PASS cases=3 external=0 provider=0')


if __name__ == '__main__':
    main()
