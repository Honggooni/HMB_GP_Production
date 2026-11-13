"""Register deliberately synthetic nodes without depending on a removed SDK method."""


def register_fixture_node(engine, flow, node):
    if not hasattr(engine, "object_manager"):
        from griptape_nodes.retained_mode.engine import current_engine
        engine = current_engine()
    flow.add_node(node)
    legacy = getattr(engine.object_manager, "add_object_by_name", None)
    if callable(legacy):
        legacy(node.name, node)
        engine.node_manager._name_to_parent_flow_name[node.name] = flow.name
    else:
        workflow = engine.current_workflow()
        node._set_workflow(workflow)
        workflow.objects.add(node.name, node)
        workflow.nodes.name_to_parent_flow_name[node.name] = flow.name


def ensure_fixture_flow(griptape, name):
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    result = griptape.handle_request(EnsureWorkflowAndFlowRequest(flow_name=name))
    assert result.succeeded(), str(result.result_details)
    return griptape.FlowManager().get_flow_by_name(result.flow_name)


def fixture_flow_connections(engine, flow):
    workflow = engine.current_workflow_or_none() if hasattr(engine, "current_workflow_or_none") else None
    if workflow is not None:
        return engine.flow_manager._get_connections_for_flow(workflow, flow)
    return engine.flow_manager._get_connections_for_flow(flow)
