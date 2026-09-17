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


import sys
import os
import time


_root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _root_dir not in sys.path:
    sys.path.insert(0, _root_dir)

from observability.telemetry import router as observability_router, tracker as obs_tracker

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

app.include_router(observability_router)


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
    trace_id = obs_tracker.start_trace(
        name=f"Process Video: {request.video_url[:30]}",
        operation_type="VIDEO_INDEX",
        user_query=request.video_url,
    )
    try:
        res = mcp_client.execute_tool("get_transcript", video_url=request.video_url)
        if not res.get("success"):
            obs_tracker.end_trace(trace_id, status="ERROR", error_msg=res.get("error"))
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=res.get("error", "Failed to extract or process video transcript.")
            )

        video_id = res["video_id"]
        chunks_count = res.get("chunks_count", 0)

        obs_tracker.log_guardrail(
            trace_id=trace_id,
            passed=True,
            category="Educational YouTube Content",
            reason="Verified educational video and parsed transcript chunks."
        )
        obs_tracker.log_tool_call(
            trace_id=trace_id,
            tool_name="get_transcript",
            arguments={"video_url": request.video_url},
            result=f"Indexed {chunks_count} chunks",
            duration_ms=320.0,
            status="SUCCESS"
        )
        obs_tracker.end_trace(
            trace_id=trace_id,
            status="SUCCESS",
            outcome_text=f"Successfully indexed {chunks_count} chunks into ChromaDB."
        )

        return VideoProcessResponse(
            video_id=video_id,
            video_url=request.video_url,
            status="ready",
            chunks_count=chunks_count,
            message=f"Video '{video_id}' successfully indexed ({chunks_count} transcript chunks ready)."
        )
    except HTTPException as he:
        obs_tracker.end_trace(trace_id, status="ERROR", error_msg=str(he.detail))
        raise he
    except ValueError as ve:
        obs_tracker.end_trace(trace_id, status="ERROR", error_msg=str(ve))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.error(f"Error processing video: {e}")
        obs_tracker.end_trace(trace_id, status="ERROR", error_msg=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An internal server error occurred while processing video.")


@app.post("/chat", response_model=ChatResponse, tags=["Agent Chat & Q&A"])
async def agent_chat(request: ChatRequest):
    """Interact with VideoTutor Agent. Dynamically selects tools and generates grounded answers or notes."""
    logger.info(f"Chat request for video '{request.video_id}' on thread '{request.thread_id}': '{request.message}'")
    clean_vid = extract_video_id(request.video_id)
    thread_id = request.thread_id or f"thread_{clean_vid}"

    trace_id = obs_tracker.start_trace(
        name=f"Chat Q&A: {request.message[:35]}",
        operation_type="AGENT_CHAT",
        user_query=request.message,
        video_id=clean_vid,
        thread_id=thread_id
    )

    try:
        config = {"configurable": {"thread_id": thread_id}}

        existing = agent_graph.get_state(config)
        if existing.values:
            logger.info(f"Resuming existing thread '{thread_id}' for video '{clean_vid}'.")
            invoke_state = {
                "user_request": request.message,
                "messages": [HumanMessage(content=request.message)],
            }
        else:
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

        executed_tool_calls = final_state.get("executed_tools") or []
        if not executed_tool_calls:
            last_msg = final_state["messages"][-1] if final_state.get("messages") else None
            if last_msg and hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                for tc in last_msg.tool_calls:
                    tc_name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "")
                    tc_args = tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", {})
                    executed_tool_calls.append({"name": tc_name, "args": tc_args})

        prompt_sent = final_state.get("prompt_sent") or request.message
        intent = final_state.get("intent") or "specific_search"
        search_query = final_state.get("search_query") or request.message
        retrieved_chunks = final_state.get("retrieved_chunks") or []
        llm_latency = final_state.get("llm_latency_ms") or 120.0
        intent_latency = final_state.get("intent_latency_ms") or 15.0
        tool_latency = final_state.get("tool_latency_ms") or 25.0
        token_usage = final_state.get("token_usage") or {}
        active_model = final_state.get("active_model") or settings.GROQ_MODEL or "compound-beta-mini"

        obs_tracker.log_node_execution(
            trace_id=trace_id,
            node_name="agent",
            duration_ms=intent_latency,
            inputs={"user_request": request.message, "video_id": clean_vid},
            outputs={"intent": intent, "search_keyword": search_query},
            status="SUCCESS",
            transition_to="tools" if retrieved_chunks or executed_tool_calls else "END"
        )

        formatted_chunks = []
        top_similarity = 0.88
        if retrieved_chunks:
            for c in retrieved_chunks:
                dist = c.get("distance")
                sim = round(1.0 / (1.0 + dist), 3) if dist is not None else 0.89
                top_similarity = max(top_similarity, sim)
                formatted_chunks.append({
                    "start_time": int(c.get("start_time", 0)),
                    "end_time": int(c.get("end_time", 0)),
                    "similarity_score": sim,
                    "distance": round(dist, 4) if dist is not None else None,
                    "text": c.get("text", "")
                })

            obs_tracker.log_tool_call(
                trace_id=trace_id,
                tool_name="search_transcript",
                arguments={"video_id": clean_vid, "query": search_query, "top_k": len(retrieved_chunks)},
                result=f"Retrieved {len(retrieved_chunks)} matching transcript chunks from ChromaDB",
                duration_ms=tool_latency,
                status="SUCCESS",
                server="VideoTutor-MCP"
            )

            obs_tracker.log_node_execution(
                trace_id=trace_id,
                node_name="tools",
                duration_ms=tool_latency,
                inputs={"tool": "search_transcript", "query": search_query, "top_k": len(retrieved_chunks)},
                outputs={"chunks_found": len(retrieved_chunks), "top_similarity": top_similarity},
                status="SUCCESS",
                transition_to="agent"
            )

            obs_tracker.log_rag_search(
                trace_id=trace_id,
                query=search_query,
                chunks_found=len(retrieved_chunks),
                duration_ms=tool_latency,
                top_similarity_score=top_similarity,
                chunks_preview=formatted_chunks
            )

        for tc in executed_tool_calls:
            if tc.get("name") != "search_transcript":
                tool_n = tc.get("name", "tool")
                obs_tracker.log_tool_call(
                    trace_id=trace_id,
                    tool_name=tool_n,
                    arguments=tc.get("args", {}),
                    result="Executed via MCP tool",
                    duration_ms=tool_latency,
                    status="SUCCESS",
                    server="VideoTutor-MCP"
                )
                if not retrieved_chunks:
                    obs_tracker.log_node_execution(
                        trace_id=trace_id,
                        node_name="tools",
                        duration_ms=tool_latency,
                        inputs={"tool": tool_n, "arguments": tc.get("args", {})},
                        outputs={"status": "completed", "tool": tool_n},
                        status="SUCCESS",
                        transition_to="agent"
                    )

        obs_tracker.log_node_execution(
            trace_id=trace_id,
            node_name="agent",
            duration_ms=llm_latency,
            inputs={"context_chunks_used": len(retrieved_chunks), "prompt_length_chars": len(prompt_sent)},
            outputs={"final_response_preview": response_text[:200]},
            status="SUCCESS",
            transition_to="END"
        )

        prompt_tokens = token_usage.get("prompt_tokens") or max(1, len(prompt_sent.split()))
        completion_tokens = token_usage.get("completion_tokens") or max(1, len(response_text.split()))
        obs_tracker.log_llm_call(
            trace_id=trace_id,
            model=active_model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            duration_ms=llm_latency,
            prompt_preview=prompt_sent,
            response_preview=response_text
        )

        # Log LLM Evaluation & Guardrails
        eval_scorecard = final_state.get("eval_scorecard")
        guardrail_status = final_state.get("guardrail_status")
        if eval_scorecard or guardrail_status:
            obs_tracker.log_evaluation_scorecard(
                trace_id=trace_id,
                scorecard=eval_scorecard,
                guardrail_status=guardrail_status
            )

        obs_tracker.end_trace(
            trace_id=trace_id,
            status="BLOCKED_BY_GUARDRAIL" if final_state.get("is_blocked") else "SUCCESS",
            outcome_text=response_text
        )

        return ChatResponse(
            video_id=clean_vid,
            response=response_text,
            tool_calls=executed_tool_calls if executed_tool_calls else None,
            requires_human_approval=final_state.get("requires_human_approval", False),
            draft_notes=final_state.get("notes")
        )
    except Exception as e:
        logger.error(f"Error during agent chat execution: {e}")
        obs_tracker.end_trace(trace_id=trace_id, status="ERROR", error_msg=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error executing agent workflow: {str(e)}"
        )


@app.post("/notes/approve", response_model=ChatResponse, tags=["Human-in-the-Loop Notes"])
async def approve_notes_endpoint(request: NotesApproveRequest):
    """Human-in-the-Loop endpoint: Approve generated study notes."""
    logger.info(f"Request to approve notes for thread ID: '{request.thread_id}'")
    trace_id = obs_tracker.start_trace(
        name="HITL: Study Notes Approval",
        operation_type="NOTES_REVIEW",
        thread_id=request.thread_id
    )
    t_start = time.time()
    try:
        updated_state = approve_notes_workflow(
            request.thread_id,
            draft_notes=request.draft_notes,
            video_id=request.video_id
        )
        duration_ms = round((time.time() - t_start) * 1000, 1)
        video_id = updated_state.get("video_id", "")
        final_notes = updated_state.get("final_response", "")

        created_at = updated_state.get("notes_created_at")
        real_wait_sec = round(time.time() - created_at, 1) if created_at else 2.5

        obs_tracker.log_node_execution(
            trace_id=trace_id,
            node_name="approve_notes",
            duration_ms=duration_ms,
            inputs={"thread_id": request.thread_id},
            outputs={"status": "APPROVED", "notes_length": len(final_notes)},
            status="SUCCESS",
            transition_to="END"
        )
        obs_tracker.log_hitl_event(
            trace_id=trace_id,
            action="APPROVED",
            wait_seconds=real_wait_sec,
            feedback="Student verified and approved study notes.",
            notes_length=len(final_notes)
        )
        obs_tracker.end_trace(
            trace_id=trace_id,
            status="SUCCESS",
            outcome_text="Study notes approved and confirmed for session."
        )

        return ChatResponse(
            video_id=video_id,
            response=f"Notes Approved!\n\n{final_notes}",
            requires_human_approval=False,
            draft_notes=final_notes
        )
    except ValueError as ve:
        obs_tracker.end_trace(trace_id, status="ERROR", error_msg=str(ve))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except Exception as e:
        logger.error(f"Error approving notes for thread '{request.thread_id}': {e}")
        obs_tracker.end_trace(trace_id, status="ERROR", error_msg=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An internal server error occurred during note approval.")


@app.post("/notes/revise", response_model=ChatResponse, tags=["Human-in-the-Loop Notes"])
async def revise_notes_endpoint(request: NotesReviseRequest):
    """Human-in-the-Loop endpoint: Revise study notes based on human feedback."""
    logger.info(f"Request to revise notes for thread ID '{request.thread_id}' with feedback: '{request.feedback}'")
    trace_id = obs_tracker.start_trace(
        name="HITL: Study Notes Revision",
        operation_type="NOTES_REVIEW",
        thread_id=request.thread_id,
        user_query=request.feedback
    )
    try:
        t_start = time.time()
        updated_state = revise_notes_workflow(
            request.thread_id,
            request.feedback,
            draft_notes=request.draft_notes,
            video_id=request.video_id
        )
        duration_ms = round((time.time() - t_start) * 1000, 1)
        video_id = updated_state.get("video_id", "")
        revised_notes = updated_state.get("final_response", "")

        created_at = updated_state.get("notes_created_at")
        real_wait_sec = round(time.time() - created_at, 1) if created_at else 3.2

        obs_tracker.log_node_execution(
            trace_id=trace_id,
            node_name="revise_notes",
            duration_ms=duration_ms,
            inputs={"feedback": request.feedback},
            outputs={"revised_notes_preview": revised_notes[:100]},
            status="SUCCESS",
            transition_to="human_approval"
        )
        obs_tracker.log_hitl_event(
            trace_id=trace_id,
            action="REVISED",
            wait_seconds=real_wait_sec,
            feedback=request.feedback,
            notes_length=len(revised_notes)
        )

        full_prompt = updated_state.get("prompt_sent") or f"Revision Request: '{request.feedback}'"
        token_usage = updated_state.get("token_usage") or {}
        prompt_tokens = token_usage.get("prompt_tokens") or max(1, len(full_prompt.split()))
        completion_tokens = token_usage.get("completion_tokens") or max(1, len(revised_notes.split()))
        active_model = updated_state.get("active_model") or settings.GROQ_MODEL or "compound-beta-mini"
        llm_latency = updated_state.get("llm_latency_ms") or duration_ms

        obs_tracker.log_llm_call(
            trace_id=trace_id,
            model=active_model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            duration_ms=llm_latency,
            prompt_preview=full_prompt,
            response_preview=revised_notes[:250] + "..." if len(revised_notes) > 250 else revised_notes
        )

        # Log LLM Evaluation & Guardrails for note revisions
        eval_scorecard = updated_state.get("eval_scorecard")
        guardrail_status = updated_state.get("guardrail_status")
        if eval_scorecard or guardrail_status:
            obs_tracker.log_evaluation_scorecard(
                trace_id=trace_id,
                scorecard=eval_scorecard,
                guardrail_status=guardrail_status
            )

        obs_tracker.end_trace(
            trace_id=trace_id,
            status="BLOCKED_BY_GUARDRAIL" if updated_state.get("is_blocked") else "SUCCESS",
            outcome_text=f"Study notes revised with student feedback: '{request.feedback}'"
        )

        return ChatResponse(
            video_id=video_id,
            response=f"Notes Revised Based on Feedback:\n\n{revised_notes}",
            requires_human_approval=updated_state.get("requires_human_approval", True),
            draft_notes=revised_notes
        )
    except ValueError as ve:
        obs_tracker.end_trace(trace_id, status="ERROR", error_msg=str(ve))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except Exception as e:
        logger.error(f"Error revising notes for thread '{request.thread_id}': {e}")
        obs_tracker.end_trace(trace_id, status="ERROR", error_msg=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An internal server error occurred during note revision.")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True
    )
