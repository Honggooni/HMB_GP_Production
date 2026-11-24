"""Bind real SDK requests for the duration of an isolated host fixture."""
from contextlib import contextmanager


@contextmanager
def scoped_fixture_workflow(engine, flow_name):
    if not hasattr(engine, "bind_workflow"):
        # Single-workflow engines keep their existing current-flow context.
        yield
        return

    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest

    result = engine.handle_request(EnsureWorkflowAndFlowRequest(flow_name=flow_name, broadcast_result=False))
    assert result.succeeded(), result.result_details
    runtime = engine.open_workflows.get(result.workflow_id)
    with engine.bind_workflow(runtime):
        assert engine.current_workflow() is runtime
        yield


async def run_in_fixture_workflow(engine, flow_name, exercise, *args, **kwargs):
    with scoped_fixture_workflow(engine, flow_name):
        return await exercise(engine, *args, **kwargs)
