import logging
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from backend.app.agent.state import AgentState
from backend.app.agent.nodes import (
    agent_node,
    tool_node,
    should_continue,
    approve_notes_node,
    revise_notes_node
)

logger = logging.getLogger("VideoTutor.AgentGraph")

checkpointer = MemorySaver()


def build_agent_graph():
    """Construct and compile the LangGraph ReAct Agent StateGraph."""
    graph_builder = StateGraph(AgentState)

    graph_builder.add_node("agent", agent_node)
    graph_builder.add_node("tools", tool_node)
    graph_builder.add_node("approve_notes", approve_notes_node)
    graph_builder.add_node("revise_notes", revise_notes_node)

    graph_builder.add_edge(START, "agent")

    graph_builder.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            "human_approval": END,
            "end": END
        }
    )

    graph_builder.add_edge("tools", "agent")

    graph_builder.add_edge("approve_notes", END)
    graph_builder.add_edge("revise_notes", END)

    compiled_graph = graph_builder.compile(checkpointer=checkpointer)

    logger.info("Successfully compiled VideoTutor LangGraph Agent StateGraph.")
    return compiled_graph


agent_graph = build_agent_graph()


def approve_notes_workflow(thread_id: str) -> AgentState:
    """Execute note approval workflow on an existing thread state."""
    config = {"configurable": {"thread_id": thread_id}}
    state = agent_graph.get_state(config)
    if not state.values:
        raise ValueError(f"No active state thread found for ID '{thread_id}'.")

    current_values = dict(state.values)
    current_values["requires_human_approval"] = False
    notes = current_values.get("notes", "")
    current_values["final_response"] = notes

    # Strip 'messages' before update_state: the messages field uses an
    # Annotated add_messages reducer — passing it as a plain list would
    # bypass the reducer and corrupt the message history in the checkpoint.
    update_payload = {k: v for k, v in current_values.items() if k != "messages"}
    agent_graph.update_state(config, update_payload)
    return current_values


def revise_notes_workflow(thread_id: str, feedback: str) -> AgentState:
    """Execute note revision workflow on an existing thread state using human feedback."""
    config = {"configurable": {"thread_id": thread_id}}
    state = agent_graph.get_state(config)
    if not state.values:
        raise ValueError(f"No active state thread found for ID '{thread_id}'.")

    current_values = dict(state.values)
    current_values["human_feedback"] = feedback

    revision_output = revise_notes_node(current_values)
    current_values.update(revision_output)

    # Strip 'messages' before update_state: the messages field uses an
    # Annotated add_messages reducer — passing it as a plain list bypasses
    # the reducer and would corrupt the checkpointed message history.
    # Messages from revise_notes_node are already reflected in current_values
    # for the return value; we just don't persist them via update_state.
    update_payload = {k: v for k, v in current_values.items() if k != "messages"}
    agent_graph.update_state(config, update_payload)
    return current_values
