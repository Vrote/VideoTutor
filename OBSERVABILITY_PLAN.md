# VideoTutor AI Agent – Observability & Monitoring Plan (LangSmith)

This document outlines the observability, monitoring, and tracing architecture for the **VideoTutor AI Agent** using **LangSmith**. It establishes end-to-end visibility across LLM calls, educational content checks, MCP tools, ChromaDB vector search, session request tracing, answer quality evaluation, and real-time dashboard metrics.

---

## 1. LLM Monitoring

All LLM calls (Groq / OpenAI / Gemini) are automatically tracked in LangSmith to monitor quality, latency, token consumption, and cost.

- **Prompt Logging:** Captures exact prompts, system instructions, chat context history, and raw/processed transcript context passed to the LLM.
- **Token & Cost Tracking:** Records prompt tokens, completion tokens, total token usage, and real-time estimated cost per session and per model.
- **Latency / Speed:** Measures execution latency for each individual LLM inference step.
- **Question Type Accuracy:** Verifies and tracks the agent's intent classification:
  - `timestamp_query`: Exact video moment / topic timestamp lookup.
  - `whole_video_notes`: Comprehensive structured notes synthesis.
  - `general_knowledge`: Out-of-video domain knowledge routing.
- **Retries & Errors:** Tracks model retries, HTTP 429 rate limits, socket timeouts, and automatic failovers to fallback models (e.g., Groq $\leftrightarrow$ Gemini).
- **Output Format Validation:** Ensures generated output adheres strictly to expected JSON schemas, `MM:SS` timestamp links, and markdown structure.

### Key LLM Metrics
| Metric | Description / Goal |
|---|---|
| **First-Attempt Answer Rate** | Frequency of valid responses generated without triggering model retries. |
| **LLM Speed (Avg / P95)** | Typical response time and 95th-percentile worst-case tail latency. |
| **Tokens per Question** | Average prompt and completion token footprint per student query. |
| **Model Error Rate** | Percentage of LLM calls failing, timing out, or encountering rate limits. |
| **Cost per Active User** | Aggregated model expenditure per unique active student session. |

---

## 2. Content Checks & Educational Moderation

Before the agent invokes retrieval or generation, incoming video links and user queries pass through validation and educational filtering:

- **Link Reading & Extraction:** Tracks extraction success rate across various YouTube URL formats (standard `watch?v=`, `youtu.be/`, Shorts, embeds, live streams, and plain IDs).
- **Category & Educational Check:** Logs whether video metadata qualifies as educational or is rejected by guardrails.
- **Allow / Block Reason:** Records the exact reason for moderation decisions, including matched topic keywords and category tags.
- **False-Positive Tracking:** Logs and audits valid educational videos that were incorrectly blocked to continually tune classifier heuristics.
- **Off-Topic Questions:** Detects queries extending beyond video scope and ensures routing to `answer_from_general_knowledge`.

---

## 3. MCP Tools & Search Layer

Model Context Protocol (MCP) tools and ChromaDB vector operations are tracked as distinct traced spans in LangSmith (`@traceable(run_type="tool")`).

### Core MCP Tools Tracked
| Tool | Purpose |
|---|---|
| `get_video_info` | Extracts and validates YouTube video metadata, title, and channel information. |
| `get_transcript` | Extracts subtitle chunks with exact second offsets, partitions windows, and indexes into ChromaDB. |
| `search_transcript` | Performs semantic similarity search against indexed transcript chunks with relevance scoring. |
| `generate_video_notes` | Compiles whole-video structured revision notes with Human-in-the-Loop review gates. |
| `answer_from_general_knowledge` | Formulates responses for queries outside the video's transcript scope. |

### Additional Tracing Details
- **Tool Error Classification:** Differentiates upstream YouTube API errors (e.g., disabled transcripts), MCP connection issues, and invalid tool parameter schemas.
- **Search & Retrieval Logging:** Captures vector query embeddings, top-$k$ matched chunks, cosine similarity scores, and distance thresholds.
- **Embedding Model Monitoring:** Logs the active embedding model (`all-MiniLM-L6-v2` or lightweight universal fallback) and embedding generation latency.
- **Storage & Vector Store Health:** Tracks indexing speed, ChromaDB read/write latency, and storage footprint.
- **Tool Usage Distribution:** Identifies the most and least frequently invoked agent tools to optimize reasoning pathways.

---

## 4. End-to-End Request Tracing

Every incoming request is tagged with a unique **Trace ID** to provide end-to-end visibility:

```
User Question ──► FastAPI App ──► Content Checks ──► LangGraph Agent ──► MCP Tools ──► ChromaDB / YouTube ──► Final Answer
```

- **Step-by-Step Execution Tree:** Provides an interactive waterfall view in LangSmith showing agent reasoning steps, dynamic tool calls, and LLM completions.
- **Session & Thread Tracking:** Groups multi-turn student interactions under unified `thread_id` sessions for conversational context auditing.

---

## 5. Answer Quality & Evaluation

The system validates output veracity and educational efficacy against ground-truth transcript data:

- **Hallucination Detection:** Flags agent responses containing factual assertions or claims not supported by transcript context chunks.
- **Notes Completeness:** Evaluates generated study notes to verify comprehensive coverage of all major video sections and topics.
- **User Feedback Linking:** Ingests user reactions (thumbs up, thumbs down, copy to clipboard, notes approval/revision) and links them directly to the corresponding LangSmith Trace ID.

---

## 6. Dashboard Metrics

The LangSmith dashboard displays live operational telemetry:

| Metric | Description |
|---|---|
| **Request Volume** | Total count of student questions, video imports, and generated study notes over time. |
| **Total Response Time** | Latency breakdown across transcript retrieval, vector search, and LLM inference. |
| **Tokens & Cost** | Cumulative token consumption and monetary cost broken down by provider (Groq, OpenAI, Gemini). |
| **Blocked Videos Rate** | Ratio of URLs rejected due to non-educational content or invalid formatting. |
| **MCP Success Rate** | Success rate, timeout frequency, and execution speed across each MCP tool. |
| **Transcript Availability** | Proportion of videos with manual subtitles, auto-generated captions, or missing transcripts. |

---

## 7. Expected Outcome

Implementing this observability and monitoring plan provides:
1. **Immediate Root-Cause Analysis:** Fast diagnosis of failed transcripts, missing subtitles, or out-of-bounds timestamps.
2. **Reliable Quality Control:** Rapid detection of hallucinated facts or incorrect timestamp links.
3. **Performance & Cost Optimization:** Real-time visibility into token spend, latency bottlenecks, and model failovers.
4. **Continuous Learning:** Actionable user feedback tied to execution traces for ongoing refinement of agent prompts and tool definitions.
