from __future__ import annotations

from typing import Any, Callable

from paper_blog_agent import workflow


Node = Callable[[dict[str, Any]], dict[str, Any]]


WORKFLOW_NODES: tuple[Node, ...] = (
    workflow.init_context,
    workflow.load_user_memory,
    workflow.resolve_source,
    workflow.load_source,
    workflow.normalize_paper,
    workflow.check_cache,
    workflow.chunk_source_text,
    workflow.extract_info,
    workflow.save_paper_memory,
    workflow.plan_blog_node,
    workflow.generate_blog_node,
    workflow.verify_blog_node,
    workflow.revise_if_needed,
    workflow.export_outputs,
    workflow.save_generation_history,
)


def langgraph_available() -> bool:
    try:
        import langgraph  # noqa: F401
    except Exception:
        return False
    return True


def build_langgraph():
    """Build the same workflow with LangGraph when the dependency is installed."""
    try:
        from langgraph.graph import END, StateGraph
    except Exception as exc:
        raise RuntimeError("LangGraph is not installed. Install project dependencies to use build_langgraph().") from exc

    graph = StateGraph(dict)
    for node in WORKFLOW_NODES:
        graph.add_node(node.__name__, node)
    graph.set_entry_point(WORKFLOW_NODES[0].__name__)
    for current, nxt in zip(WORKFLOW_NODES, WORKFLOW_NODES[1:]):
        graph.add_edge(current.__name__, nxt.__name__)
    graph.add_edge(WORKFLOW_NODES[-1].__name__, END)
    return graph.compile()
