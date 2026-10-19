"""Consolidation never overlaps execution, including an unrelated idle flow."""
from __future__ import annotations
import ast
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[2]
tree = ast.parse((ROOT / '_hmb_library_bootstrap.py').read_text('utf-8'))
method = next(item for owner in tree.body if isinstance(owner, ast.ClassDef)
              for item in owner.body if isinstance(item, ast.FunctionDef)
              and item.name == '_guard_migration_mutation')
namespace = {'Any': object, 'sys': sys, '_LOAD_TYPES': ()}
exec(compile(ast.Module(body=[method], type_ignores=[]), str(ROOT / '_hmb_library_bootstrap.py'), 'exec'), namespace)
guard = namespace['_guard_migration_mutation']


def request(name, **values):
    result = type(name, (), {})()
    result.__dict__.update(values)
    return result


class Failure:
    def __init__(self, **values):
        self.__dict__.update(values)


class MigrationExecutionGuard(unittest.TestCase):
    execution_names = ('StartFlowRequest', 'StartLocalSubflowRequest', 'StartFlowFromNodeRequest',
                       'ContinueExecutionStepRequest', 'ExecuteNodeRequest', 'ResolveNodeRequest',
                       'RunWorkflowFromScratchRequest', 'RunWorkflowWithCurrentStateRequest',
                       'RunWorkflowFromRegistryRequest')

    def setUp(self):
        self.previous = {name: sys.modules.get(name) for name in (
            '_hmb_workflow_migration', 'griptape_nodes.retained_mode.events.generic_events')}
        self.inflight, self.internal = True, False
        migration = ModuleType('_hmb_workflow_migration')
        migration.mutation_is_internal = lambda: self.internal
        migration.flow_migration_inflight = lambda _engine, flow=None: self.inflight and flow in (None, 'Migrating')
        generic = ModuleType('griptape_nodes.retained_mode.events.generic_events')
        generic.GenericResultFailure = Failure
        sys.modules[migration.__name__] = migration
        sys.modules[generic.__name__] = generic
        self.engine = SimpleNamespace(
            node_manager=SimpleNamespace(_name_to_parent_flow_name={'Old': 'Migrating', 'Elsewhere': 'Other'}),
            context_manager=SimpleNamespace(has_current_flow=lambda: False))
        self.owner = SimpleNamespace(engine=lambda: self.engine)

    def tearDown(self):
        for name, previous in self.previous.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous

    def test_every_execution_entry_waits_across_all_flows(self):
        for name in self.execution_names:
            for values in ({'flow_name': 'Migrating'}, {'flow_name': 'Other'},
                           {'node_name': 'Elsewhere'}, {}):
                with self.subTest(request=name, target=values):
                    result = guard(self.owner, request(name, **values))
                    self.assertIsInstance(result, Failure)
                    self.assertIn('no render was started', result.result_details)

    def test_read_and_cancel_remain_available(self):
        for name in ('GetIsFlowRunningRequest', 'GetParameterValueRequest', 'ListNodesRequest',
                     'CancelFlowRequest', 'CancelExecuteNodeRequest'):
            self.assertIsNone(guard(self.owner, request(name, flow_name='Migrating')))

    def test_unrelated_start_services_are_not_execution(self):
        for name in ('StartWorkerRequest', 'StartSyncAllCloudWorkflowsRequest'):
            self.assertIsNone(guard(self.owner, request(name)))

    def test_authoring_mutations_still_have_flow_scope(self):
        self.assertIsInstance(guard(self.owner, request('SetParameterValueRequest', node_name='Old')), Failure)
        self.assertIsNone(guard(self.owner, request('SetParameterValueRequest', node_name='Elsewhere')))

    def test_internal_transaction_requests_are_allowed(self):
        self.internal = True
        for name in (*self.execution_names, 'DeleteNodeRequest'):
            self.assertIsNone(guard(self.owner, request(name, flow_name='Migrating')))

    def test_finished_migration_restores_normal_requests(self):
        self.inflight = False
        for name in (*self.execution_names, 'DeleteNodeRequest', 'SetParameterValueRequest'):
            self.assertIsNone(guard(self.owner, request(name, flow_name='Migrating')))


if __name__ == '__main__':
    unittest.main(verbosity=2)
