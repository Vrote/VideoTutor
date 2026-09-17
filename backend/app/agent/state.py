from typing import TypedDict, Annotated, List, Dict, Any, Optional
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """LangGraph State definition for VideoTutor AI Learning Agent."""

    video_id: str
    video_url: str
    video_ready: bool

    user_request: str
    messages: Annotated[List[BaseMessage], add_messages]

    retrieved_chunks: List[Dict[str, Any]]
    notes: Optional[str]
    human_feedback: Optional[str]
    requires_human_approval: bool
    final_response: Optional[str]

    
    prompt_sent: Optional[str]
    intent: Optional[str]
    search_query: Optional[str]
    llm_latency_ms: Optional[float]
    intent_latency_ms: Optional[float]
    tool_latency_ms: Optional[float]
    token_usage: Optional[Dict[str, int]]
    active_model: Optional[str]
    notes_created_at: Optional[float]
    executed_tools: Optional[List[Dict[str, Any]]]
    guardrail_status: Optional[Dict[str, Any]]
    eval_scorecard: Optional[Dict[str, Any]]
    is_blocked: Optional[bool]
