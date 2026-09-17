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


def approve_notes_workflow(thread_id: str, draft_notes: str = None, video_id: str = None) -> AgentState:
    """Execute note approval workflow on an existing thread state or recovered state."""
    config = {"configurable": {"thread_id": thread_id}}
    state = agent_graph.get_state(config)
    if state.values:
        current_values = dict(state.values)
    else:
        logger.warning(f"Thread '{thread_id}' not found in checkpointer. Creating fallback approval state.")
        current_values = {
            "thread_id": thread_id,
            "video_id": video_id or "",
            "notes": draft_notes or "",
            "requires_human_approval": False
        }

    current_values["requires_human_approval"] = False
    notes = current_values.get("notes") or draft_notes or ""
    current_values["final_response"] = notes

    update_payload = {k: v for k, v in current_values.items() if k != "messages"}
    try:
        agent_graph.update_state(config, update_payload)
    except Exception as e:
        logger.warning(f"Failed to update state in checkpointer: {e}")
    return current_values


def revise_notes_workflow(thread_id: str, feedback: str, draft_notes: str = None, video_id: str = None) -> AgentState:
    """Execute note revision workflow on an existing thread state or recovered state."""
    config = {"configurable": {"thread_id": thread_id}}
    state = agent_graph.get_state(config)
    if state.values:
        current_values = dict(state.values)
        if draft_notes and not current_values.get("notes"):
            current_values["notes"] = draft_notes
        if video_id and not current_values.get("video_id"):
            current_values["video_id"] = video_id
    else:
        logger.warning(f"Thread '{thread_id}' not found in checkpointer (likely server restart). Recreating state with fallback draft notes.")
        current_values = {
            "thread_id": thread_id,
            "video_id": video_id or "",
            "notes": draft_notes or "",
            "requires_human_approval": True
        }

    current_values["human_feedback"] = feedback

    revision_output = revise_notes_node(current_values)
    current_values.update(revision_output)

    update_payload = {k: v for k, v in current_values.items() if k != "messages"}
    try:
        agent_graph.update_state(config, update_payload)
    except Exception as e:
        logger.warning(f"Failed to update state in checkpointer: {e}")
    return current_values
