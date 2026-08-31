import logging
from typing import List, Dict, Any, Callable
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from backend.app.mcp.server import (
    get_video_info_tool,
    get_transcript_tool,
    search_transcript_tool,
    generate_video_notes_tool,
    answer_from_general_knowledge_tool,
    MCP_TOOLS
)

logger = logging.getLogger("VideoTutor.MCPClient")


class GetVideoInfoInput(BaseModel):
    video_url: str = Field(description="YouTube video URL or 11-character Video ID.")


class GetTranscriptInput(BaseModel):
    video_url: str = Field(description="YouTube video URL or 11-character Video ID.")


class SearchTranscriptInput(BaseModel):
    video_id: str = Field(description="11-character YouTube Video ID.")
    query: str = Field(description="Question or topic search query to look up inside the video transcript.")
    top_k: int = Field(default=5, description="Number of relevant transcript chunks to return.")


class GenerateVideoNotesInput(BaseModel):
    video_id: str = Field(description="11-character YouTube Video ID to generate comprehensive whole-video study notes for.")


class AnswerGeneralKnowledgeInput(BaseModel):
    query: str = Field(description="The user's question or topic that is not present or discussed in the video.")
    reason: str = Field(default="Topic is not covered in the current video transcript", description="Reason why general knowledge is needed.")


class MCPClient:
    """MCP Client bridge providing standardized tools to the LangGraph Agent."""

    def __init__(self, tools_registry: Dict[str, Callable] = None):
        self.tools_registry = tools_registry or MCP_TOOLS

    def execute_tool(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """Execute an MCP tool by name with arguments."""
        if tool_name not in self.tools_registry:
            logger.error(f"Tool '{tool_name}' not found in MCP registry.")
            return {"success": False, "error": f"Tool '{tool_name}' not registered in MCP server."}

        logger.info(f"MCP Client executing tool '{tool_name}' with kwargs: {kwargs}")
        try:
            result = self.tools_registry[tool_name](**kwargs)
            return result
        except Exception as e:
            logger.error(f"Error executing MCP tool '{tool_name}': {e}")
            return {"success": False, "error": str(e)}

    def get_langchain_tools(self) -> List[StructuredTool]:
        """Convert MCP tools into LangChain / LangGraph compatible StructuredTool objects."""

        def _get_info(video_url: str):
            return self.execute_tool("get_video_info", video_url=video_url)

        def _get_trans(video_url: str):
            return self.execute_tool("get_transcript", video_url=video_url)

        def _search_trans(video_id: str, query: str, top_k: int = 5):
            return self.execute_tool("search_transcript", video_id=video_id, query=query, top_k=top_k)

        def _gen_notes(video_id: str):
            return self.execute_tool("generate_video_notes", video_id=video_id)

        def _gen_knowledge(query: str, reason: str = "Topic not covered in video transcript"):
            return self.execute_tool("answer_from_general_knowledge", query=query, reason=reason)

        tools = [
            StructuredTool.from_function(
                func=_get_info,
                name="get_video_info",
                description="Retrieve video ID, URL validation, and index status for a YouTube video URL.",
                args_schema=GetVideoInfoInput
            ),
            StructuredTool.from_function(
                func=_get_trans,
                name="get_transcript",
                description="Fetch, chunk, and index the timestamped transcript of a YouTube video into ChromaDB.",
                args_schema=GetTranscriptInput
            ),
            StructuredTool.from_function(
                func=_search_trans,
                name="search_transcript",
                description="Perform semantic search on stored transcript chunks for a video. Returns exact text, timestamps, and relevance match flag.",
                args_schema=SearchTranscriptInput
            ),
            StructuredTool.from_function(
                func=_gen_notes,
                name="generate_video_notes",
                description="Retrieve whole-video multi-section timeline chunks to create comprehensive in-depth study notes.",
                args_schema=GenerateVideoNotesInput
            ),
            StructuredTool.from_function(
                func=_gen_knowledge,
                name="answer_from_general_knowledge",
                description="Use when the user's question or topic is NOT covered or present in the video transcript to provide an answer based on general knowledge.",
                args_schema=AnswerGeneralKnowledgeInput
            ),
        ]
        return tools


mcp_client = MCPClient()
