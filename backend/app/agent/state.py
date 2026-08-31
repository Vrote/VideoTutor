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
