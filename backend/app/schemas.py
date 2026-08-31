from typing import Optional, List, Any, Dict
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Health check response schema."""
    status: str = Field(..., json_schema_extra={"example": "ok"})
    embedding_mode: Optional[str] = Field(
        default=None,
        description="Active embedding function: 'sentence-transformers/<model>' or 'lightweight-hash-fallback'."
    )
    groq_model: Optional[str] = Field(
        default=None,
        description="Configured Groq LLM model name."
    )


class VideoProcessRequest(BaseModel):
    """Request payload for processing a YouTube video URL."""
    video_url: str = Field(..., json_schema_extra={"example": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"})


class VideoProcessResponse(BaseModel):
    """Response payload after processing a video."""
    video_id: str
    video_url: str
    status: str
    chunks_count: int
    message: str


class ChatRequest(BaseModel):
    """Request payload for interacting with the VideoTutor agent."""
    video_id: str = Field(..., json_schema_extra={"example": "dQw4w9WgXcQ"})
    message: str = Field(..., json_schema_extra={"example": "What is context switching?"})
    thread_id: Optional[str] = Field(
        default=None,
        description="Conversation thread ID for state persistence. If omitted, defaults to 'thread_<video_id>' ensuring per-video isolation."
    )


class ChatResponse(BaseModel):
    """Response payload from the VideoTutor agent."""
    video_id: str
    response: str
    tool_calls: Optional[List[Dict[str, Any]]] = None
    requires_human_approval: bool = False
    draft_notes: Optional[str] = None


class NotesApproveRequest(BaseModel):
    """Request payload for approving generated notes in Human-in-the-Loop workflow."""
    thread_id: str = Field(..., json_schema_extra={"example": "default_thread"})


class NotesReviseRequest(BaseModel):
    """Request payload for requesting modifications to generated notes."""
    thread_id: str = Field(..., json_schema_extra={"example": "default_thread"})
    feedback: str = Field(..., json_schema_extra={"example": "Make the notes shorter and add two key examples."})

