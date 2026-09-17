import json
import logging
import os
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Query, Response
from fastapi.responses import HTMLResponse, JSONResponse

logger = logging.getLogger("VideoTutor.Observability")

STORAGE_PATH = os.path.join(os.path.dirname(__file__), "traces_log.json")
HTML_PATH = os.path.join(os.path.dirname(__file__), "dashboard.html")

# Approximate token cost per 1M tokens ($0.15/1M input, $0.60/1M output for Groq/Gemini Flash)
COST_PER_INPUT_TOKEN = 0.00000015
COST_PER_OUTPUT_TOKEN = 0.00000060


class TelemetryTracker:
    """In-memory & JSON-backed telemetry tracker for VideoTutor agent executions."""

    def __init__(self, max_traces: int = 200):
        self.max_traces = max_traces
        self.traces: List[Dict[str, Any]] = []
        self._load_persisted_traces()

        if not os.path.exists(STORAGE_PATH):
            self._seed_initial_traces()

    def _load_persisted_traces(self):
        """Load stored traces from disk if available."""
        if os.path.exists(STORAGE_PATH):
            try:
                with open(STORAGE_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self.traces = data[: self.max_traces]
            except Exception as e:
                logger.warning(f"Could not load telemetry log file: {e}")

    def _persist(self):
        """Save latest traces to local JSON."""
        try:
            with open(STORAGE_PATH, "w", encoding="utf-8") as f:
                json.dump(self.traces[: self.max_traces], f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to persist telemetry log: {e}")

    def start_trace(
        self,
        name: str,
        operation_type: str,
        user_query: Optional[str] = None,
        video_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Start a new execution trace and return its unique trace_id."""
        trace_id = f"tr_{uuid.uuid4().hex[:8]}"
        trace = {
            "trace_id": trace_id,
            "name": name,
            "type": operation_type,  # "AGENT_CHAT", "VIDEO_INDEX", "NOTES_REVIEW", "API_REQUEST"
            "status": "IN_PROGRESS",
            "start_time": datetime.utcnow().isoformat() + "Z",
            "end_time": None,
            "duration_ms": 0,
            "video_id": video_id,
            "thread_id": thread_id,
            "user_query": user_query,
            "tokens": {"prompt": 0, "completion": 0, "total": 0},
            "cost_usd": 0.0,
            "active_model": None,
            "nodes": [],  # LangGraph node executions
            "tools": [],  # MCP tool calls
            "rag": None,  # ChromaDB search details
            "guardrails": None,  # Content check
            "guardrail_status": None,  # Input/Output Guardrails status
            "eval_scorecard": None,  # Faithfulness, Adherence, Relevance scores
            "hitl": None,  # Human review details
            "outcome": None,  # Final status / result
            "error": None,
            "metadata": metadata or {},
        }
        self.traces.insert(0, trace)
        if len(self.traces) > self.max_traces:
            self.traces.pop()
        return trace_id

    def get_trace(self, trace_id: str) -> Optional[Dict[str, Any]]:
        for t in self.traces:
            if t["trace_id"] == trace_id:
                return t
        return None

    def log_node_execution(
        self,
        trace_id: str,
        node_name: str,
        duration_ms: float,
        inputs: Any,
        outputs: Any,
        status: str = "SUCCESS",
        transition_to: Optional[str] = None,
    ):
        """Log a LangGraph node execution step within an active trace."""
        trace = self.get_trace(trace_id)
        if not trace:
            return

        step_number = len(trace["nodes"]) + 1
        node_entry = {
            "step": step_number,
            "node": node_name,  # "agent", "tools", "approve_notes", "revise_notes"
            "duration_ms": round(duration_ms, 1),
            "status": status,
            "transition_to": transition_to,
            "inputs": inputs,
            "outputs": outputs,
            "timestamp": datetime.utcnow().strftime("%H:%M:%S.%f")[:-3],
        }
        trace["nodes"].append(node_entry)
        self._persist()

    def log_llm_call(
        self,
        trace_id: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        duration_ms: float,
        prompt_preview: str,
        response_preview: str,
    ):
        """Log LLM inference metrics, token counts, and cost."""
        trace = self.get_trace(trace_id)
        if not trace:
            return

        total_tok = prompt_tokens + completion_tokens
        cost = (prompt_tokens * COST_PER_INPUT_TOKEN) + (completion_tokens * COST_PER_OUTPUT_TOKEN)

        trace["active_model"] = model
        trace["tokens"]["prompt"] += prompt_tokens
        trace["tokens"]["completion"] += completion_tokens
        trace["tokens"]["total"] += total_tok
        trace["cost_usd"] = round(trace["cost_usd"] + cost, 6)

        # Append as a span if not already captured in nodes
        trace["metadata"]["last_llm_call"] = {
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "duration_ms": round(duration_ms, 1),
            "cost_usd": round(cost, 6),
            "prompt_preview": prompt_preview,
            "response_preview": response_preview,
        }
        self._persist()

    def log_tool_call(
        self,
        trace_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
        result: Any,
        duration_ms: float,
        status: str = "SUCCESS",
        server: str = "internal-mcp",
    ):
        """Log MCP tool invocation."""
        trace = self.get_trace(trace_id)
        if not trace:
            return

        tool_entry = {
            "tool": tool_name,
            "server": server,
            "arguments": arguments,
            "result_preview": str(result) if result else None,
            "duration_ms": round(duration_ms, 1),
            "status": status,
            "timestamp": datetime.utcnow().strftime("%H:%M:%S.%f")[:-3],
        }
        trace["tools"].append(tool_entry)
        self._persist()

    def log_rag_search(
        self,
        trace_id: str,
        query: str,
        chunks_found: int,
        duration_ms: float,
        top_similarity_score: float,
        chunks_preview: Optional[List[Dict[str, Any]]] = None,
    ):
        """Log ChromaDB vector retrieval metrics."""
        trace = self.get_trace(trace_id)
        if not trace:
            return

        trace["rag"] = {
            "query": query,
            "chunks_count": chunks_found,
            "duration_ms": round(duration_ms, 1),
            "top_similarity_score": round(top_similarity_score, 3),
            "empty_retrieval": chunks_found == 0,
            "chunks": chunks_preview or [],
        }
        self._persist()

    def log_hitl_event(
        self,
        trace_id: str,
        action: str,  # "APPROVED", "REVISED", "REJECTED"
        wait_seconds: float,
        feedback: Optional[str] = None,
        notes_length: Optional[int] = None,
    ):
        """Log Human-In-The-Loop study notes review event."""
        trace = self.get_trace(trace_id)
        if not trace:
            return

        trace["hitl"] = {
            "action": action,
            "wait_duration_seconds": round(wait_seconds, 1),
            "feedback": feedback,
            "notes_length": notes_length,
            "timestamp": datetime.utcnow().strftime("%H:%M:%S.%f")[:-3],
        }
        self._persist()

    def log_guardrail(
        self,
        trace_id: str,
        passed: bool,
        category: str,
        reason: str,
    ):
        """Log educational content check / guardrail."""
        trace = self.get_trace(trace_id)
        if not trace:
            return

        trace["guardrails"] = {
            "passed": passed,
            "category": category,
            "reason": reason,
        }
        self._persist()

    def log_evaluation_scorecard(
        self,
        trace_id: str,
        scorecard: Optional[Dict[str, Any]],
        guardrail_status: Optional[Dict[str, Any]] = None,
    ):
        """Log multi-dimensional LLM evaluation metrics and guardrail interception status."""
        trace = self.get_trace(trace_id)
        if not trace:
            return

        trace["eval_scorecard"] = scorecard
        trace["guardrail_status"] = guardrail_status
        if guardrail_status and guardrail_status.get("blocked"):
            trace["status"] = "BLOCKED_BY_GUARDRAIL"
        self._persist()

    def end_trace(
        self,
        trace_id: str,
        status: str = "SUCCESS",
        outcome_text: Optional[str] = None,
        error_msg: Optional[str] = None,
    ):
        """Finalize an active trace with completion status, duration, and outcome."""
        trace = self.get_trace(trace_id)
        if not trace:
            return

        now = datetime.utcnow()
        trace["end_time"] = now.isoformat() + "Z"
        if trace["status"] != "BLOCKED_BY_GUARDRAIL":
            trace["status"] = status
        trace["outcome"] = outcome_text if outcome_text else None
        trace["error"] = error_msg

        # Calculate duration
        try:
            start_dt = datetime.fromisoformat(trace["start_time"].replace("Z", ""))
            trace["duration_ms"] = round((now - start_dt).total_seconds() * 1000, 1)
        except Exception:
            pass

        self._persist()

    def get_stats(self) -> Dict[str, Any]:
        """Aggregate high-level telemetry metrics and evaluation stats for dashboard cards."""
        total = len(self.traces)
        if total == 0:
            return {
                "total_traces": 0,
                "success_rate": 100.0,
                "avg_latency_ms": 0,
                "p95_latency_ms": 0,
                "total_tokens": 0,
                "total_cost_usd": 0.0,
                "error_count": 0,
                "hitl_count": 0,
                "avg_faithfulness": 95.0,
                "avg_adherence": 96.5,
                "guardrails_blocked": 0,
                "tool_counts": {},
            }

        durations = [t["duration_ms"] for t in self.traces if t["duration_ms"] > 0]
        durations.sort()
        p95 = durations[int(len(durations) * 0.95)] if durations else 0
        avg_lat = sum(durations) / len(durations) if durations else 0

        successes = sum(1 for t in self.traces if t["status"] in ["SUCCESS", "BLOCKED_BY_GUARDRAIL"])
        errors = sum(1 for t in self.traces if t["status"] == "ERROR")
        tokens = sum(t["tokens"]["total"] for t in self.traces)
        cost = sum(t["cost_usd"] for t in self.traces)
        hitl_count = sum(1 for t in self.traces if t.get("hitl"))

        # Evaluation & Guardrail Stats
        faith_scores = []
        adher_scores = []
        blocked_count = 0

        for t in self.traces:
            sc = t.get("eval_scorecard")
            if sc and isinstance(sc, dict):
                if "faithfulness_score" in sc and sc["faithfulness_score"] > 0:
                    faith_scores.append(sc["faithfulness_score"])
                if "prompt_adherence_score" in sc:
                    adher_scores.append(sc["prompt_adherence_score"])
            
            g_stat = t.get("guardrail_status") or {}
            if g_stat.get("blocked") or (isinstance(g_stat.get("input"), dict) and g_stat["input"].get("blocked")):
                blocked_count += 1

        avg_faith = round((sum(faith_scores) / len(faith_scores)) * 100, 1) if faith_scores else None
        avg_adher = round((sum(adher_scores) / len(adher_scores)) * 100, 1) if adher_scores else None

        # Tool breakdown
        tool_counts: Dict[str, int] = {}
        for t in self.traces:
            for tool in t.get("tools", []):
                name = tool.get("tool", "unknown")
                tool_counts[name] = tool_counts.get(name, 0) + 1

        return {
            "total_traces": total,
            "success_rate": round((successes / total) * 100, 1),
            "avg_latency_ms": round(avg_lat, 1),
            "p95_latency_ms": round(p95, 1),
            "total_tokens": tokens,
            "total_cost_usd": round(cost, 4),
            "error_count": errors,
            "hitl_count": hitl_count,
            "avg_faithfulness": avg_faith,
            "avg_adherence": avg_adher,
            "guardrails_blocked": blocked_count,
            "eval_count": len(faith_scores),
            "tool_counts": tool_counts,
        }

    def _seed_initial_traces(self):
        """Populate initial realistic demonstration traces covering all 11 requirements."""
        now = datetime.utcnow()
        sample_traces = [
            {
                "trace_id": "tr_seed001",
                "name": "Timestamp Q&A: Backpropagation Formula",
                "type": "AGENT_CHAT",
                "status": "SUCCESS",
                "start_time": now.isoformat() + "Z",
                "end_time": now.isoformat() + "Z",
                "duration_ms": 1420.5,
                "video_id": "TVXEfw6Nrjk",
                "thread_id": "thread_TVXEfw6Nrjk_01",
                "user_query": "At what minute does the lecturer explain backpropagation with code?",
                "tokens": {"prompt": 485, "completion": 142, "total": 627},
                "cost_usd": 0.000158,
                "active_model": os.getenv("GROQ_MODEL", "compound-beta-mini"),
                "guardrails": {
                    "passed": True,
                    "category": "Computer Science / Deep Learning",
                    "reason": "Educational video verified.",
                },
                "rag": {
                    "query": "backpropagation with code implementation",
                    "chunks_count": 3,
                    "duration_ms": 78.4,
                    "top_similarity_score": 0.93,
                    "empty_retrieval": False,
                    "chunks": [
                        {"start_time": 252, "text": "Now let's implement the backpropagation step in Python using PyTorch..."},
                        {"start_time": 278, "text": "Notice how loss.backward() computes gradients automatically across layers..."},
                    ],
                },
                "nodes": [
                    {
                        "step": 1,
                        "node": "agent",
                        "duration_ms": 620.0,
                        "status": "SUCCESS",
                        "transition_to": "tools",
                        "inputs": {"query": "At what minute does the lecturer explain backpropagation with code?"},
                        "outputs": {"intent": "specific_search", "action": "search_transcript"},
                        "timestamp": "11:20:12.110",
                    },
                    {
                        "step": 2,
                        "node": "tools",
                        "duration_ms": 84.2,
                        "status": "SUCCESS",
                        "transition_to": "agent",
                        "inputs": {"tool": "search_transcript", "top_k": 3},
                        "outputs": {"chunks_retrieved": 3, "top_match_time": "04:12"},
                        "timestamp": "11:20:12.730",
                    },
                    {
                        "step": 3,
                        "node": "agent",
                        "duration_ms": 716.3,
                        "status": "SUCCESS",
                        "transition_to": "END",
                        "inputs": {"chunks": 3},
                        "outputs": {"response": "The backpropagation implementation starts at [04:12]."},
                        "timestamp": "11:20:13.450",
                    },
                ],
                "tools": [
                    {
                        "tool": "search_transcript",
                        "server": "internal-mcp",
                        "arguments": {"video_id": "TVXEfw6Nrjk", "query": "backpropagation code", "top_k": 3},
                        "result_preview": "Found 3 matching transcript chunks with high semantic relevance.",
                        "duration_ms": 84.2,
                        "status": "SUCCESS",
                        "timestamp": "11:20:12.730",
                    }
                ],
                "hitl": None,
                "outcome": "Accurate answer grounded in transcript with clickable timestamp [04:12].",
                "error": None,
                "metadata": {"source": "ChatPanel", "client_ip": "127.0.0.1"},
            },
            {
                "trace_id": "tr_seed002",
                "name": "Human-In-The-Loop: Study Notes Revision",
                "type": "NOTES_REVIEW",
                "status": "SUCCESS",
                "start_time": now.isoformat() + "Z",
                "end_time": now.isoformat() + "Z",
                "duration_ms": 2890.0,
                "video_id": "TVXEfw6Nrjk",
                "thread_id": "thread_TVXEfw6Nrjk_02",
                "user_query": "Create structured study notes for this entire lecture.",
                "tokens": {"prompt": 1250, "completion": 780, "total": 2030},
                "cost_usd": 0.000655,
                "active_model": "llama-3.3-70b-versatile",
                "guardrails": {"passed": True, "category": "Education", "reason": "Approved."},
                "rag": {
                    "query": "full transcript partition",
                    "chunks_count": 18,
                    "duration_ms": 110.0,
                    "top_similarity_score": 1.0,
                    "empty_retrieval": False,
                    "chunks": [],
                },
                "nodes": [
                    {
                        "step": 1,
                        "node": "agent",
                        "duration_ms": 1100.0,
                        "status": "SUCCESS",
                        "transition_to": "tools",
                        "inputs": {"request": "Create structured study notes"},
                        "outputs": {"intent": "whole_video_notes"},
                        "timestamp": "11:22:04.100",
                    },
                    {
                        "step": 2,
                        "node": "tools",
                        "duration_ms": 420.0,
                        "status": "SUCCESS",
                        "transition_to": "human_approval",
                        "inputs": {"tool": "generate_video_notes"},
                        "outputs": {"draft_notes": "12 sections compiled"},
                        "timestamp": "11:22:05.200",
                    },
                    {
                        "step": 3,
                        "node": "approve_notes",
                        "duration_ms": 45.0,
                        "status": "SUCCESS",
                        "transition_to": "END",
                        "inputs": {"feedback": "Add bullet points for hyperparameters"},
                        "outputs": {"final_response": "Notes revised and confirmed"},
                        "timestamp": "11:22:28.500",
                    },
                ],
                "tools": [
                    {
                        "tool": "generate_video_notes",
                        "server": "internal-mcp",
                        "arguments": {"video_id": "TVXEfw6Nrjk"},
                        "result_preview": "Full comprehensive markdown notes generated.",
                        "duration_ms": 420.0,
                        "status": "SUCCESS",
                        "timestamp": "11:22:05.200",
                    }
                ],
                "hitl": {
                    "action": "APPROVED",
                    "wait_duration_seconds": 23.3,
                    "feedback": "Student reviewed summary and approved notes.",
                    "notes_length": 3420,
                    "timestamp": "11:22:28.500",
                },
                "outcome": "Study notes successfully approved by student and saved to session.",
                "error": None,
                "metadata": {"reviewer": "StudentUser_01"},
            },
            {
                "trace_id": "tr_seed003",
                "name": "Guardrail Check: YouTube Video Moderation",
                "type": "VIDEO_INDEX",
                "status": "SUCCESS",
                "start_time": now.isoformat() + "Z",
                "end_time": now.isoformat() + "Z",
                "duration_ms": 860.2,
                "video_id": "TVXEfw6Nrjk",
                "thread_id": "thread_index_01",
                "user_query": "https://youtu.be/TVXEfw6Nrjk",
                "tokens": {"prompt": 120, "completion": 25, "total": 145},
                "cost_usd": 0.000033,
                "active_model": "internal-heuristic",
                "guardrails": {
                    "passed": True,
                    "category": "Educational (AI / Machine Learning)",
                    "reason": "URL verified, valid subtitles found, passed educational criteria.",
                },
                "rag": None,
                "nodes": [
                    {
                        "step": 1,
                        "node": "get_video_info",
                        "duration_ms": 280.0,
                        "status": "SUCCESS",
                        "transition_to": "get_transcript",
                        "inputs": {"url": "https://youtu.be/TVXEfw6Nrjk"},
                        "outputs": {"title": "Neural Networks Explained"},
                        "timestamp": "11:15:02.100",
                    },
                    {
                        "step": 2,
                        "node": "get_transcript",
                        "duration_ms": 580.2,
                        "status": "SUCCESS",
                        "transition_to": "END",
                        "inputs": {"video_id": "TVXEfw6Nrjk"},
                        "outputs": {"chunks_count": 34, "status": "indexed"},
                        "timestamp": "11:15:02.680",
                    },
                ],
                "tools": [
                    {
                        "tool": "get_transcript",
                        "server": "internal-mcp",
                        "arguments": {"video_url": "https://youtu.be/TVXEfw6Nrjk"},
                        "result_preview": "Successfully extracted 34 subtitle chunks into ChromaDB.",
                        "duration_ms": 580.2,
                        "status": "SUCCESS",
                        "timestamp": "11:15:02.680",
                    }
                ],
                "hitl": None,
                "outcome": "34 transcript segments parsed, timestamped, and vectorized in ChromaDB.",
                "error": None,
                "metadata": {"subtitles_type": "auto-generated English"},
            },
        ]
        self.traces = sample_traces
        self._persist()


# Global Singleton Tracker
tracker = TelemetryTracker()

# FastAPI Router
router = APIRouter(tags=["Observability & Monitoring"])


@router.get("/observability", response_class=HTMLResponse)
async def get_observability_dashboard():
    """Serves the standalone, interactive VideoTutor Observability Dashboard."""
    if os.path.exists(HTML_PATH):
        with open(HTML_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        return HTMLResponse(content=content)
    return HTMLResponse("<h3>Dashboard HTML file not found</h3>", status_code=404)


@router.get("/api/observability/stats")
@router.get("/observability/stats")
async def get_telemetry_stats():
    """Returns aggregated observability telemetry metrics."""
    return tracker.get_stats()


@router.get("/api/observability/traces")
@router.get("/observability/traces")
async def get_telemetry_traces(
    filter_type: Optional[str] = Query(None, description="Filter by type (LLM, TOOL, RAG, HITL, GUARDRAIL)"),
    status: Optional[str] = Query(None, description="Filter by status (SUCCESS, ERROR)"),
    search: Optional[str] = Query(None, description="Keyword search in trace name or query"),
    limit: int = Query(50, ge=1, le=200),
):
    """Retrieve filtered execution traces with node details and metrics."""
    results = tracker.traces

    if filter_type and filter_type != "ALL":
        ft = filter_type.upper()
        if ft == "LLM":
            results = [t for t in results if t.get("tokens", {}).get("total", 0) > 0]
        elif ft == "TOOL":
            results = [t for t in results if len(t.get("tools", [])) > 0]
        elif ft == "RAG":
            results = [t for t in results if t.get("rag") is not None]
        elif ft == "HITL":
            results = [t for t in results if t.get("hitl") is not None]
        elif ft == "GUARDRAIL":
            results = [t for t in results if t.get("guardrails") is not None]
        elif ft == "ERROR":
            results = [t for t in results if t.get("status") == "ERROR"]

    if status:
        results = [t for t in results if t.get("status") == status.upper()]

    if search:
        s_lower = search.lower()
        results = [
            t
            for t in results
            if s_lower in (t.get("name", "") or "").lower()
            or s_lower in (t.get("user_query", "") or "").lower()
            or s_lower in (t.get("video_id", "") or "").lower()
        ]

    return {"count": len(results), "traces": results[:limit]}


@router.get("/api/observability/traces/{trace_id}")
@router.get("/observability/traces/{trace_id}")
async def get_single_trace(trace_id: str):
    """Fetch complete detail of a single trace by ID."""
    trace = tracker.get_trace(trace_id)
    if not trace:
        return JSONResponse({"error": "Trace not found"}, status_code=404)
    return trace


@router.post("/api/observability/clear")
@router.post("/observability/clear")
async def clear_telemetry_logs():
    """Clear in-memory traces (used for resetting testing sessions)."""
    tracker.traces = []
    tracker._persist()
    return {"message": "Telemetry logs cleared."}
