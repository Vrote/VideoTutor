import logging
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.messages import HumanMessage
from backend.app.config import settings
from backend.app.schemas import (
    HealthResponse,
    VideoProcessRequest,
    VideoProcessResponse,
    ChatRequest,
    ChatResponse,
    NotesApproveRequest,
    NotesReviseRequest
)
from backend.app.services.youtube import extract_video_id
from backend.app.mcp.client import mcp_client
from backend.app.services.vector_store import _active_embedding_type as get_embedding_mode
from backend.app.agent.graph import (
    agent_graph,
    approve_notes_workflow,
    revise_notes_workflow
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("VideoTutor")

app = FastAPI(
    title=settings.APP_NAME,
    description="Backend API for VideoTutor - AI Video Learning Agent using LangGraph, MCP, ChromaDB, and FastAPI.",
    version="1.0.0",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Health check endpoint — returns operational status, active embedding mode, and LLM model."""
    import backend.app.services.vector_store as vs
    logger.info("Health check pinged.")
    return HealthResponse(
        status="ok",
        embedding_mode=vs._active_embedding_type,
        groq_model=settings.GROQ_MODEL,
    )


@app.get("/", tags=["Health"])
async def root():
    """Root endpoint providing a welcome message and system details."""
    return {
        "message": f"Welcome to {settings.APP_NAME}",
        "docs_url": "/docs",
        "health_check": "/health"
    }


@app.post("/video/process", response_model=VideoProcessResponse, tags=["Video Processing"])
async def process_video(request: VideoProcessRequest):
    """Process a YouTube video URL: extract transcript, chunk, and index into ChromaDB."""
    logger.info(f"Received request to process video URL: '{request.video_url}'")
    try:
        res = mcp_client.execute_tool("get_transcript", video_url=request.video_url)
        if not res.get("success"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=res.get("error", "Failed to extract or process video transcript.")
            )

        video_id = res["video_id"]
        chunks_count = res.get("chunks_count", 0)

        return VideoProcessResponse(
            video_id=video_id,
            video_url=request.video_url,
            status="ready",
            chunks_count=chunks_count,
            message=f"Video '{video_id}' successfully indexed ({chunks_count} transcript chunks ready)."
        )
    except HTTPException as he:
        raise he
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.error(f"Error processing video: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An internal server error occurred while processing video.")


@app.post("/chat", response_model=ChatResponse, tags=["Agent Chat & Q&A"])
async def agent_chat(request: ChatRequest):
    """Interact with VideoTutor Agent. Dynamically selects tools and generates grounded answers or notes."""
    logger.info(f"Chat request for video '{request.video_id}' on thread '{request.thread_id}': '{request.message}'")
    try:
        clean_vid = extract_video_id(request.video_id)
        thread_id = request.thread_id or f"thread_{clean_vid}"

        config = {"configurable": {"thread_id": thread_id}}

        # Check whether this thread already has a saved checkpoint.
        # - Existing thread: only update user_request + add the new message.
        #   All other state (notes, requires_human_approval, retrieved_chunks)
        #   is preserved from the checkpoint so pending approval is not wiped.
        # - New thread: send full initialization state.
        existing = agent_graph.get_state(config)
        if existing.values:
            # Thread exists — minimal update; let the checkpointer supply the rest.
            logger.info(f"Resuming existing thread '{thread_id}' for video '{clean_vid}'.")
            invoke_state = {
                "user_request": request.message,
                "messages": [HumanMessage(content=request.message)],
            }
        else:
            # Brand-new thread — full initialization.
            logger.info(f"Starting new thread '{thread_id}' for video '{clean_vid}'.")
            invoke_state = {
                "video_id": clean_vid,
                "video_url": f"https://www.youtube.com/watch?v={clean_vid}",
                "video_ready": True,
                "user_request": request.message,
                "messages": [HumanMessage(content=request.message)],
                "retrieved_chunks": [],
                "notes": None,
                "human_feedback": None,
                "requires_human_approval": False,
                "final_response": None,
            }

        final_state = agent_graph.invoke(invoke_state, config=config)

        last_msg_content = final_state["messages"][-1].content if final_state.get("messages") else "Agent processing complete."
        if isinstance(last_msg_content, list):
            parts = []
            for item in last_msg_content:
                if isinstance(item, dict) and "text" in item:
                    parts.append(item["text"])
                elif isinstance(item, str):
                    parts.append(item)
            response_text = final_state.get("final_response") or ("\n".join(parts) if parts else str(last_msg_content))
        else:
            response_text = final_state.get("final_response") or str(last_msg_content)

        executed_tool_calls = []
        for msg in final_state.get("messages", []):
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    tc_name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "")
                    tc_args = tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", {})
                    executed_tool_calls.append({"name": tc_name, "args": tc_args})

        return ChatResponse(
            video_id=clean_vid,
            response=response_text,
            tool_calls=executed_tool_calls if executed_tool_calls else None,
            requires_human_approval=final_state.get("requires_human_approval", False),
            draft_notes=final_state.get("notes") or (response_text if final_state.get("requires_human_approval") else None)
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.error(f"Error during agent chat: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An internal server error occurred during chat reasoning: {str(e)}")


@app.post("/notes/approve", response_model=ChatResponse, tags=["Human-in-the-Loop Notes"])
async def approve_notes_endpoint(request: NotesApproveRequest):
    """Human-in-the-Loop endpoint: Approve generated study notes."""
    logger.info(f"Request to approve notes for thread ID: '{request.thread_id}'")
    try:
        updated_state = approve_notes_workflow(request.thread_id)
        video_id = updated_state.get("video_id", "")
        final_notes = updated_state.get("final_response", "")

        return ChatResponse(
            video_id=video_id,
            response=f"Notes Approved!\n\n{final_notes}",
            requires_human_approval=False,
            draft_notes=final_notes
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except Exception as e:
        logger.error(f"Error approving notes for thread '{request.thread_id}': {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An internal server error occurred during note approval.")


@app.post("/notes/revise", response_model=ChatResponse, tags=["Human-in-the-Loop Notes"])
async def revise_notes_endpoint(request: NotesReviseRequest):
    """Human-in-the-Loop endpoint: Revise study notes based on human feedback."""
    logger.info(f"Request to revise notes for thread ID '{request.thread_id}' with feedback: '{request.feedback}'")
    try:
        updated_state = revise_notes_workflow(request.thread_id, request.feedback)
        video_id = updated_state.get("video_id", "")
        revised_notes = updated_state.get("final_response", "")

        return ChatResponse(
            video_id=video_id,
            response=f"Notes Revised Based on Feedback:\n\n{revised_notes}",
            requires_human_approval=updated_state.get("requires_human_approval", True),
            draft_notes=revised_notes
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except Exception as e:
        logger.error(f"Error revising notes for thread '{request.thread_id}': {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An internal server error occurred during note revision.")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True
    )
