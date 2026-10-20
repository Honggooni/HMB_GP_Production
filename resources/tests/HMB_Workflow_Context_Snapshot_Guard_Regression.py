"""Portable admission contract for the reproduced SDK context-stack race."""
from __future__ import annotations
import ast
import asyncio
import gc
from pathlib import Path
import sys
import threading
from types import ModuleType, SimpleNamespace
import unittest
import weakref

ROOT=Path(__file__).resolve().parents[2]
tree=ast.parse((ROOT/"_hmb_library_bootstrap.py").read_text("utf-8"))
names={"_guard_context_snapshot_request","after_context_snapshot","after_workflow_load","before_create"}
methods=[item for owner in tree.body if isinstance(owner,ast.ClassDef) for item in owner.body
         if isinstance(item,(ast.FunctionDef,ast.AsyncFunctionDef)) and item.name in names]
serial=tuple(type(name,(),{}) for name in ("SerializeFlowToCommandsRequest","SerializeNodeToCommandsRequest","SerializeSelectedNodesToCommandsRequest"))
save=tuple(type(name,(),{}) for name in ("SaveWorkflowRequest","SaveWorkflowFileFromSerializedFlowRequest","SaveSubflowToWorkflowRequest"))
loads=(type("RunWorkflowWithCurrentStateRequest",(),{}),type("DeserializeFlowFromCommandsRequest",(),{}))


class Failure:
    def __init__(self,**values):self.__dict__.update(values)


class SnapshotGuardTests(unittest.TestCase):
    def setUp(self):
        self.previous={name:sys.modules.get(name) for name in ("_hmb_workflow_migration","griptape_nodes.retained_mode.events.generic_events")}
        self.internal=False;self.inflight=False;self.loading=False;self.owner_key=(10,20);self.migration_calls=[]
        migration=ModuleType("_hmb_workflow_migration")
        migration.mutation_is_internal=lambda:self.internal
        migration.flow_migration_inflight=lambda engine:self.inflight
        migration.schedule_loaded_flow_migrations=lambda engine:self.migration_calls.append("schedule")
        migration.pending_flow_names=lambda engine:["existing-flow"]
        migration.clear_flow_migration_pending=lambda *a:self.migration_calls.append("clear")
        sys.modules[migration.__name__]=migration
        generic=ModuleType("griptape_nodes.retained_mode.events.generic_events");generic.GenericResultFailure=Failure
        sys.modules[generic.__name__]=generic
        namespace={"Any":object,"sys":sys,"weakref":weakref,"_LOAD_TYPES":loads,"_SERIALIZE_TYPES":serial,"_SAVE_TYPES":save,
            "_context_snapshot_owner":lambda:self.owner_key,"is_loading_workflow":lambda:self.loading,
            "_migration_module":lambda:migration,"_CONTEXT_SNAPSHOT_BUSY_MESSAGE":"Wait and retry. Refused, not queued; no file written."}
        exec(compile(ast.Module(body=methods,type_ignores=[]),str(ROOT/"_hmb_library_bootstrap.py"),"exec"),namespace)
        owner_type=type("Owner",(),{name:namespace[name] for name in names})
        self.owner=owner_type();self.owner.lock=threading.RLock();self.engine=object();self.manager=object()
        self.owner.engine=lambda:self.engine;self.owner.manager=lambda:self.manager
        self.owner._prompt_owner=lambda engine,manager:True
        self.owner.load_requests={};self.owner.snapshot_requests={};self.owner.snapshot_refused_loads={}
        self.owner.snapshot_post_types=list(serial)

    def tearDown(self):
        for name,value in self.previous.items():
            if value is None:sys.modules.pop(name,None)
            else:sys.modules[name]=value

    def guard(self,request):return self.owner._guard_context_snapshot_request(request)
    def release(self,request):asyncio.run(self.owner.after_context_snapshot(request,Failure()))
    def tracked_load(self):
        request=loads[0]();self.owner.load_requests[id(request)]=weakref.ref(request);return request

    def test_external_known_save_and_serialize_refused_during_tracked_load(self):
        load=self.tracked_load()
        for kind in (*serial,*save):
            result=self.guard(kind());self.assertIsInstance(result,Failure);self.assertIn("not queued",result.result_details)
        self.assertEqual(self.owner.snapshot_requests,{})
        self.assertIn(id(load),self.owner.load_requests)

    def test_loader_own_snapshot_is_allowed(self):
        load=self.tracked_load();self.loading=True
        for kind in (*serial,*save):
            request=kind();self.assertIsNone(self.guard(request));self.release(request)
        self.assertIn(id(load),self.owner.load_requests)

    def test_load_admission_blocks_snapshot_before_observe_callback_can_run(self):
        # A paused pre-dispatch caller has not reached _observe_workflow_load.
        # The admission itself must already protect the shared context stack.
        self.owner._guard_context_snapshot_request.__globals__["_context_snapshot_owner"]=lambda:(threading.get_ident(),0)
        admitted=threading.Barrier(2);release=threading.Event();errors=[];request=loads[0]()
        def load_pre_dispatch():
            try:
                self.assertIsNone(self.guard(request));admitted.wait(timeout=5)
                self.assertTrue(release.wait(5))
            except BaseException as exc:errors.append(exc)
        worker=threading.Thread(target=load_pre_dispatch);worker.start()
        try:
            admitted.wait(timeout=5)
            self.assertIn(id(request),self.owner.load_requests)
            self.assertIsInstance(self.guard(serial[0]()),Failure)
            self.assertEqual(self.owner.snapshot_requests,{})
        finally:release.set();worker.join(5)
        self.assertFalse(worker.is_alive());self.assertEqual(errors,[])

    def test_later_migration_refusal_releases_admitted_load_without_cleanup(self):
        self.owner.start_web_worker=lambda:None
        self.owner._guard_migration_mutation=lambda request:Failure(result_details="Migration is active")
        request=loads[0]()
        result=self.owner.before_create(request,None)
        self.assertIsInstance(result,Failure)
        self.assertNotIn(id(request),self.owner.load_requests)
        self.assertIn(id(request),self.owner.snapshot_refused_loads)
        asyncio.run(self.owner.after_workflow_load(request,result))
        self.assertEqual(self.migration_calls,[])
        self.assertEqual(self.owner.snapshot_refused_loads,{})

    def test_migration_external_waits_and_authorized_internal_snapshot_runs(self):
        self.inflight=True
        for kind in (*serial,*save):self.assertIsInstance(self.guard(kind()),Failure)
        self.internal=True
        request=serial[0]();self.assertIsNone(self.guard(request));self.release(request)

    def test_reads_cancel_and_future_custom_names_are_not_intercepted(self):
        load=self.tracked_load()
        for name in ("GetParameterValueRequest","CancelFlowRequest","SaveCustomArtworkRequest","SerializeCustomThingRequest"):
            self.assertIsNone(self.guard(type(name,(),{})()))
        self.assertIn(id(load),self.owner.load_requests)

    def test_same_owner_nested_and_sequential_requests_allow_deferred_posts(self):
        first=serial[0]();nested=serial[1]();second=serial[0]()
        for request in (first,nested,second):self.assertIsNone(self.guard(request))
        self.assertEqual(len(self.owner.snapshot_requests),3)
        self.release(nested);self.release(first)
        self.assertEqual(list(self.owner.snapshot_requests),[id(second)])
        self.release(second);self.assertEqual(self.owner.snapshot_requests,{})

    def test_other_thread_or_task_serializers_wait_without_locking_handler(self):
        first=serial[0]();self.assertIsNone(self.guard(first))
        for key in ((11,20),(10,21)):
            self.owner_key=key;self.assertIsInstance(self.guard(serial[0]()),Failure)
        self.assertEqual(len(self.owner.snapshot_requests),1)
        self.assertTrue(self.owner.lock.acquire(blocking=False));self.owner.lock.release()

    def test_reverse_arrival_refused_load_does_not_clear_existing_migration_state(self):
        first=serial[0]();self.assertIsNone(self.guard(first));self.owner_key=(11,21)
        request=loads[0]();self.assertIsInstance(self.guard(request),Failure)
        asyncio.run(self.owner.after_workflow_load(request,Failure()))
        self.assertEqual(self.migration_calls,[])
        self.assertEqual(self.owner.snapshot_refused_loads,{})
        self.assertIn(id(first),self.owner.snapshot_requests)

    def test_native_failure_post_releases_only_own_admission(self):
        first=serial[0]();self.guard(first);self.owner_key=(11,21)
        self.assertIsInstance(self.guard(serial[0]()),Failure)
        self.release(first);self.assertIsNone(self.guard(serial[0]()))

    def test_dead_request_is_pruned_without_a_timer_expiring_live_ownership(self):
        first=serial[0]();self.guard(first);del first;gc.collect()
        self.owner_key=(11,21);next_request=serial[0]();self.assertIsNone(self.guard(next_request))
        self.assertEqual(len(self.owner.snapshot_requests),1)

    def test_missing_post_hook_support_does_not_leave_a_permanent_admission(self):
        self.owner.snapshot_post_types=[]
        request=serial[0]();self.assertIsNone(self.guard(request));self.assertEqual(self.owner.snapshot_requests,{})
        load=self.tracked_load();self.assertIsInstance(self.guard(serial[0]()),Failure)
        self.assertIn(id(load),self.owner.load_requests)

    def test_internal_migration_cannot_overlap_a_different_serialization_owner(self):
        first=serial[0]();self.guard(first);self.owner_key=(11,21);self.internal=True
        self.assertIsInstance(self.guard(serial[0]()),Failure)

    def test_completed_load_post_preserves_existing_migration_schedule(self):
        request=self.tracked_load()
        asyncio.run(self.owner.after_workflow_load(request,SimpleNamespace(succeeded=lambda:True)))
        self.assertEqual(self.owner.load_requests,{})
        self.assertEqual(self.migration_calls,["schedule"])


if __name__=="__main__":unittest.main(verbosity=2)
