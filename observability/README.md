# VideoTutor AI Agent – Observability & Monitoring System

This folder contains the complete, self-contained **Observability & Monitoring Subsystem** for the **VideoTutor** AI application. It provides real-time visibility into agent reasoning, LangGraph node transitions, LLM model calls, MCP tool invocations, ChromaDB RAG vector searches, and Human-in-the-Loop review events.

---

## 1. Where Observability Is Implemented

| # | Observability Area | How It Is Tracked in VideoTutor |
|---|---|---|
| **1** | **Agent / Orchestration** | Traces LangGraph workflow steps (`agent` ➔ `tools` ➔ `approve_notes` ➔ `revise_notes`), state changes, retry loops, and node transitions. |
| **2** | **LLM Calls** | Tracks active model (`gemini-1.5-flash` / `llama-3.3-70b`), call count, prompt/completion tokens, latency (ms), retries, and estimated cost ($). |
| **3** | **Tools / MCP** | Logs every tool call (`get_video_info`, `get_transcript`, `search_transcript`, `generate_video_notes`), arguments passed, JSON result, and duration. |
| **4** | **Tool Selection** | Tracks intent classification accuracy (`timestamp_query`, `notes`, `general_knowledge`), wrong-tool confusion, and redundant calls. |
| **5** | **Retrieval / RAG** | ChromaDB semantic search queries, top-$k$ subtitle chunks retrieved with `MM:SS` timestamps, cosine similarity scores, retrieval latency, and empty-chunk warnings. |
| **6** | **External APIs** | YouTube Transcript API, YouTube video metadata fetch, ChromaDB vector store read/write latency, and HTTP status codes (200, 404, 429). |
| **7** | **HITL (Human-in-the-Loop)** | Study Notes Revision & Approval modal: logs reviewer actions (`APPROVED`, `REVISED`), wait duration in seconds, and revision feedback diffs. |
| **8** | **Guardrails** | Educational video checks, content moderation category, and allow/block rationale. |
| **9** | **Performance** | End-to-end question answering latency, P95 tail latency, and slowest-step bottleneck identification. |
| **10**| **Cost** | Token consumption and cost attribution per student question, notes generation cost, and cumulative spend by model. |
| **11**| **Outcome** | Grounded answer verified with clickable `MM:SS` timestamp links, complete structured markdown notes, or educational rejection. |

---

## 2. Directory Architecture

```
observability/
  ├── __init__.py           # Package exports (tracker, router)
  ├── telemetry.py          # Core tracker singleton & FastAPI REST router
  ├── dashboard.html        # Standalone, ultra-fast dark UI (served at /observability)
  ├── ObservabilityView.jsx # In-app React component for navbar tab
  └── traces_log.json       # Persistent local log snapshot of recent execution traces
```

---

## 3. How to Access the Observability Dashboard

### Option A: Standalone Web Interface (Fastest)
Open your browser directly at:
```
http://localhost:8000/observability
```
* Shows KPI cards (Total Traces, P95 Latency, Success Rate, Tokens & Cost).
* Filter by: `All`, `LLM Calls`, `MCP Tools`, `ChromaDB RAG`, `HITL Reviews`, `Guardrails`, `Errors`.
* Real-time auto-refresh every 3.5 seconds.
* Click **Inspect** on any row to see the complete LangGraph execution waterfall and inputs/outputs.

### Option B: Inside the VideoTutor React App
1. Open the VideoTutor frontend at `http://localhost:5173`.
2. Click the **"Observability"** tab in the top navigation bar.

---

## 4. API Endpoints

- `GET /observability`: Serves the standalone HTML dashboard.
- `GET /api/observability/stats`: Returns JSON summary KPIs (total runs, P95 latency, tokens, cost, error rate).
- `GET /api/observability/traces`: Returns paginated, filterable traces with full node execution history.
- `GET /api/observability/traces/{trace_id}`: Returns complete detail for a specific trace ID.
- `POST /api/observability/clear`: Clears session logs for fresh testing.
