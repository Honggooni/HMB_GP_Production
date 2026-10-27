"""Real SDK saved Finish store replay must not look like a redundant clear.

The native UI is still Only between two serialized parameter replay commands.
The stored authoring owner is already Shot 5 and needs the normal clear path.
No renderer, network, live user workflow, media file or policy is used.
"""
from __future__ import annotations
import asyncio
import copy
import logging
import os
from pathlib import Path
import sys
import tempfile
from unittest import mock

ROOT=Path(os.environ.get('HMB_ROUTING_TEST_ROOT',str(Path(__file__).resolve().parents[2])))
sys.path.insert(0,str(ROOT))


async def scenario(engine):
    import HMBFinishLookLibrary as finish
    import _hmb_shot_routing as routing
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
    engine.event_manager.initialize_queue()
    result=engine.handle_request(EnsureWorkflowAndFlowRequest(flow_name='RoutingPartialHydration'))
    assert result.succeeded(),str(result.result_details)
    flow=engine.flow_manager.get_flow_by_name(result.flow_name)
    node=finish.HMBFinishLookLibrary(name='Saved Finish Partial Hydration')
    flow.add_node(node);engine.object_manager.add_object_by_name(node.name,node)
    engine.node_manager._name_to_parent_flow_name[node.name]=flow.name
    await asyncio.sleep(.1)
    assert node not in routing._POST_REGISTRATION_PENDING
    standalone=copy.deepcopy(node._hmb_finish_current_document())
    channel='11111111-1111-4111-8111-111111111111'
    keys=[node._hmb_finish_key(channel,f'33333333-3333-4333-8333-{n:012d}') for n in range(1,6)]
    documents={'__standalone__':standalone}
    for number,key in enumerate(keys,1):
        documents[key]={**copy.deepcopy(standalone),'remote_revision':number}
    store={'schema':finish.SHOT_STORE_SCHEMA,'version':1,'documents':documents,'archives':{},'remote_owners':{},'active':keys[-1]}
    response=engine.handle_request(SetParameterValueRequest(node_name=node.name,
        parameter_name=finish.SHOT_STORE_PARAMETER_NAME,value=store,initial_setup=True,broadcast_result=False))
    assert response.succeeded(),str(response.result_details)
    assert node._hmb_finish_active_key==keys[-1]
    native=node.get_parameter_value(finish.WIDGET_PARAMETER_NAME)
    assert not native['shot']['channel_uuid'] and not native['shot']['shot_uuid']
    assert not native['shot_catalog'] and not node._hmb_finish_route_ready
    # Generated saved-property replay has no after_deserialize callback. The
    # accepted durable store must now signal hydration, while still granting no
    # remote catalog authority and preserving the exact private saved owner.
    pending=routing._POST_REGISTRATION_PENDING.get(node)
    assert pending is not None and pending.phase=='hydrated'
    assert pending.fingerprint==routing._subscription_fingerprint(node)
    subscription=routing._subscription_for(node)
    assert subscription is not None and not subscription.enabled
    assert routing._already_local_catalog(subscription) is False, 'Private saved Shot ownership still needs clearing'
    before={key:copy.deepcopy(node._hmb_finish_documents[key]) for key in keys}
    with mock.patch.object(node,'_hmb_clear_shot_routing_catalog',wraps=node._hmb_clear_shot_routing_catalog) as callback:
        routing._clear_remote_catalog(node,'publisher_unavailable',subscription=subscription)
        assert callback.call_count==1
        assert node._hmb_finish_active_key=='__standalone__'
        assert {key:node._hmb_finish_documents[key] for key in keys}==before
        # Finish now owns a real queued hydration notification. Let that exact
        # generation acknowledge the newest (cleared) durable state before
        # asserting the already-local fast path. Pending replay must still use
        # the conservative clear path rather than hide an unprocessed store.
        await asyncio.sleep(.05)
        assert node not in routing._POST_REGISTRATION_PENDING
        completed_calls=callback.call_count
        assert node._hmb_finish_active_key=='__standalone__'
        assert {key:node._hmb_finish_documents[key] for key in keys}==before
        routing._clear_remote_catalog(node,'publisher_unavailable',subscription=routing._subscription_for(node))
        assert callback.call_count==completed_calls, 'Already-local native/private owner should remain a no-op after hydration'
    node.after_node_deleted()


def main():
    from griptape_nodes.retained_mode.engine import engine_scope
    with tempfile.TemporaryDirectory(prefix='hmb-routing-partial-hydration-') as directory:
        folder=Path(directory)
        variables={key:str(folder/key) for key in ('XDG_CONFIG_HOME','XDG_DATA_HOME','XDG_STATE_HOME','XDG_CACHE_HOME','LOCALAPPDATA','APPDATA','GTN_CONFIG_WORKSPACE_DIRECTORY')}
        with mock.patch.dict(os.environ,variables):
            try:
                logging.disable(logging.CRITICAL)
                with engine_scope() as engine:asyncio.run(scenario(engine))
            finally:logging.shutdown()
    print('HMB_SHOT_ROUTING_PARTIAL_HYDRATION_HOST=PASS (real native saved-store replay, exact private owner, five authored documents preserved, repeated clear suppressed)')


if __name__=='__main__':main()
