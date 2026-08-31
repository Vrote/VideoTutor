# VideoTutor – AI Video Learning Agent (Backend)

VideoTutor is an **Agentic AI application** designed to help students learn effectively from educational YouTube videos. By leveraging **LangGraph**, **MCP (Model Context Protocol)**, **ChromaDB**, **YouTube Transcript Extraction**, and an **LLM**, VideoTutor dynamically parses video content, performs semantic transcript searches, answers student questions with exact timestamp links, generates beginner-friendly explanations, creates structured study notes, and incorporates **Human-in-the-Loop (HITL)** note review.

---

## 1. Project Overview
Educational videos on YouTube are rich in knowledge, but students often struggle to locate exact topic explanations, revise key concepts efficiently, or extract structured study notes. VideoTutor solves this by acting as an autonomous learning assistant that converts raw video transcripts into interactive, searchable, and timestamped educational intelligence.

---

## 2. Problem Statement
Traditional video learning requires students to manually skip through hours of video seeking specific explanations. Generic RAG chatbots often return text without exact video timestamps, or follow rigid static pipelines. VideoTutor provides an **autonomous agentic workflow** that reasons dynamically about user intent, decides when and how to query vector databases, calculates exact `MM:SS` timestamps, and creates human-reviewed study notes.

---

## 3. Key Features
- **YouTube URL Processing:** Extracts and validates 11-character video IDs from watch, short, embed, live, and shortened URLs.
- **Timestamped Transcript Extraction:** Retrieves subtitle segments with precise `start` and `end` second offsets using `youtube-transcript-api`.
- **Metadata-Aware Chunking:** Groups transcript segments into ~500-character windows preserving `start_time`, `end_time`, `video_id`, and `chunk_index`.
- **Persistent Local Vector Store:** Stores vector embeddings and chunk metadata in local persistent ChromaDB (`./chroma_data`).
- **Standardized MCP Server & Client:** Exposes core capabilities (`get_video_info`, `get_transcript`, `search_transcript`) as standardized Model Context Protocol tools.
- **LangGraph ReAct Agent:** Autonomous StateGraph that reasons, selects tools dynamically, evaluates tool outputs, and generates grounded answers.
- **Exact Timestamp Links:** Calculates formatted `MM:SS` timestamps and direct YouTube URL links (`https://www.youtube.com/watch?v=VIDEO_ID&t=SECONDS`).
- **Beginner-Friendly Explanations & Study Notes:** Generates clean, concise concept summaries and structured study notes.
- **Human-in-the-Loop (HITL) Workflow:** Pauses state execution when study notes are generated, allowing humans to **APPROVE** or **MODIFY** notes with custom feedback.

---

## 4. High-Level Architecture

```
                         ┌──────────────────┐
                         │      USER        │
                         └────────┬─────────┘
                                  │
                                  ▼
                         ┌──────────────────┐
                         │     FastAPI      │
                         │    REST API      │
                         └────────┬─────────┘
                                  │
                                  ▼
                    ┌──────────────────────────┐
                    │       LangGraph          │
                    │        Agent             │
                    │                          │
                    │  LLM + State + Reasoning │
                    └────────────┬─────────────┘
                                 │
                         Agent decides
                         which tool to use
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                  │
              ▼                  ▼                  ▼
       ┌─────────────┐   ┌──────────────┐   ┌──────────────┐
       │ get_video   │   │ get_transcript│   │ search_      │
       │ _info       │   │              │   │ transcript   │
       └──────┬──────┘   └──────┬───────┘   └──────┬───────┘
              │                 │                  │
              └─────────────────┼──────────────────┘
                                ▼
                       ┌─────────────────┐
                       │   MCP Server    │
                       │  VideoTutor     │
                       │     Tools       │
                       └────────┬────────┘
                                │
                    ┌───────────┴───────────┐
                    │                       │
                    ▼                       ▼
           ┌──────────────────┐    ┌─────────────────┐
           │ YouTube Transcript│    │    ChromaDB     │
           │      Service      │    │ Vector Storage  │
           └──────────────────┘    └────────┬────────┘
                                            │
                                            ▼
                                   Relevant Transcript
                                        Chunks
                                            │
                                            ▼
                                  ┌──────────────────┐
                                  │   MCP Response   │
                                  └────────┬─────────┘
                                           │
                                           ▼
                                  ┌──────────────────┐
                                  │  LangGraph Agent │
                                  │ evaluates result │
                                  └────────┬─────────┘
                                           │
                         ┌─────────────────┴────────────────┐
                         │                                  │
                         ▼                                  ▼
                 Need more information?                 Enough?
                         │                                  │
                         ▼                                  ▼
                  Another tool call                   Final Answer
                         │
                         ▼
                       Agent
```

### Human-in-the-Loop (HITL) Note Workflow

```
                     Agent
                       │
                 Generate Notes
                       │
                Human-in-the-Loop
                       │
              ┌────────┴────────┐
              │                 │
           APPROVE            MODIFY
              │                 │
              ▼                 ▼
         Final Notes      Agent revises notes
                                │
                                ▼
                           Final Notes
```

---

## 5. Pure Agentic Behavior
VideoTutor does NOT use fixed `if/else` intent classification pipelines. Instead, it runs an autonomous **ReAct (Reason + Act + Observe)** loop inside a LangGraph StateGraph:
1. **User Request Received:** Agent receives query.
2. **LLM Reasoning:** LLM evaluates state messages and decides *if* external data is needed.
3. **MCP Tool Invocation:** LLM selects standard tool (`search_transcript`), formulates parameter arguments, and executes via MCP Client.
4. **Observation:** Tool output returns to agent state.
5. **Reflection / Iteration:** Agent decides whether another tool call is necessary or if it has enough context to synthesize the final grounded response.

---

## 6. Technology Stack
- **Language:** Python 3.10+
- **API Framework:** FastAPI, Uvicorn
- **Agent Orchestration:** LangGraph, LangChain
- **Tool Protocol:** MCP (Model Context Protocol)
- **Vector Storage:** ChromaDB (Local Persistent)
- **YouTube Service:** `youtube-transcript-api`
- **Data Validation & Settings:** Pydantic V2, `pydantic-settings`
- **Environment:** `python-dotenv`
- **Testing:** Pytest, HTTPX TestClient

---

## 7. Why LangGraph?
LangGraph provides native state graph orchestration, state checkpointing (`MemorySaver`), and execution interrupts. Standard LLM tool-calling loops cannot reliably handle persistent Human-in-the-Loop state interruptions (`interrupt`), whereas LangGraph allows pausing execution during note generation, receiving human feedback, and resuming state seamlessly.

---

## 8. Why MCP (Model Context Protocol)?
MCP decouples tool implementation from agent reasoning. By exposing video capabilities (`get_video_info`, `get_transcript`, `search_transcript`) as standardized MCP tools, the underlying storage or YouTube API logic can change without rewriting agent logic.

---

## 9. Why ChromaDB?
ChromaDB is a lightweight, zero-dependency, local persistent vector database. For educational videos (which often span 1–2 hours and tens of thousands of words), local vector indexing allows instant semantic retrieval of exact 30-second transcript chunks without exceeding LLM context windows or incurring heavy hosting fees.

---

## 10. Why Embeddings?
Embeddings convert raw transcript text into dense numerical vector representations. This enables **semantic similarity search** — allowing students to find where "context switching" or "process starvation" is explained even if the teacher used slightly different phrasing in the lecture.

---

## 11. Backend Folder Structure

```
VideoTutor/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py             # FastAPI entrypoint (/health, /video/process, /chat, /notes/*)
│   │   ├── config.py           # Environment variables & settings loading
│   │   ├── schemas.py          # Pydantic request & response models
│   │   ├── agent/              # LangGraph Agent logic
│   │   │   ├── __init__.py
│   │   │   ├── state.py        # AgentState schema
│   │   │   ├── nodes.py        # Agent reasoning & tool nodes
│   │   │   └── graph.py        # StateGraph construction & compilation
│   │   ├── mcp/                # Model Context Protocol
│   │   │   ├── __init__.py
│   │   │   ├── server.py       # VideoTutor MCP tools
│   │   │   └── client.py       # LangChain tool bridge
│   │   ├── services/           # Domain services
│   │   │   ├── __init__.py
│   │   │   ├── youtube.py      # URL parsing & video ID extraction
│   │   │   ├── transcript.py   # Subtitle extraction & chunking
│   │   │   └── vector_store.py # Persistent ChromaDB operations
│   │   └── prompts/
│   │       ├── __init__.py
│   │       └── learning.py     # System prompts for agent & HITL
│   ├── tests/                  # Automated Pytest suite
│   │   ├── test_api.py
│   │   ├── test_youtube.py
│   │   ├── test_transcript.py
│   │   ├── test_vector_store.py
│   │   ├── test_mcp.py
│   │   ├── test_mcp_client.py
│   │   ├── test_agent.py
│   │   ├── test_features.py
│   │   ├── test_hitl.py
│   │   └── test_e2e.py
│   ├── requirements.txt
│   └── .env.example
├── chroma_data/                 # Local persistent ChromaDB store
└── README.md
```

---

## 12. Installation & Setup

1. **Clone the repository:**
   ```bash
   git clone <repository_url>
   cd VideoTutor
   ```

2. **Create and activate a virtual environment:**
   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

3. **Install dependencies:**
   ```bash
   pip install -r backend/requirements.txt
   ```

---

## 13. Environment Configuration

Copy `.env.example` to `.env` inside `backend/`:
```bash
cp backend/.env.example backend/.env
```

Configurable `.env` parameters:
```env
HOST=0.0.0.0
PORT=8000
ENVIRONMENT=development

# Provide Google Gemini API Key or OpenAI API Key
GOOGLE_API_KEY=your_free_google_ai_studio_key
OPENAI_API_KEY=your_openai_api_key_optional

LLM_MODEL=gemini-1.5-flash
CHROMA_PERSIST_DIRECTORY=../chroma_data
```

---

## 14. Running the Server

Start the FastAPI application:
```powershell
$env:PYTHONPATH="."; python -m uvicorn backend.app.main:app --port 8000 --reload
```
Interactive Swagger UI documentation is available at:
`http://127.0.0.1:8000/docs`

---

## 15. API Endpoints & Curl Examples

### 1. Health Check (`GET /health`)
```bash
curl -X GET http://127.0.0.1:8000/health
```
**Response:**
```json
{
  "status": "ok"
}
```

### 2. Process YouTube Video (`POST /video/process`)
```bash
curl -X POST http://127.0.0.1:8000/video/process \
  -H "Content-Type: application/json" \
  -d '{"video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}'
```
**Response:**
```json
{
  "video_id": "dQw4w9WgXcQ",
  "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
  "status": "ready",
  "chunks_count": 5,
  "message": "Video 'dQw4w9WgXcQ' successfully indexed (5 transcript chunks ready)."
}
```

### 3. Ask Video Question (`POST /chat`)
```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "video_id": "dQw4w9WgXcQ",
    "message": "Where does the teacher explain context switching?",
    "thread_id": "student_session_1"
  }'
```
**Response:**
```json
{
  "video_id": "dQw4w9WgXcQ",
  "response": "Based on the video transcript, this topic is explained around **02:00**.\n\n**Explanation:**\nContext switching occurs when the operating system saves state of a running process...\n\n🔗 **Watch on YouTube:** [02:00](https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=120)",
  "requires_human_approval": false,
  "draft_notes": null
}
```

### 4. Create Easy Study Notes (`POST /chat`)
```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "video_id": "dQw4w9WgXcQ",
    "message": "Create easy notes from this video.",
    "thread_id": "student_session_2"
  }'
```
**Response:**
```json
{
  "video_id": "dQw4w9WgXcQ",
  "response": "I have created draft study notes from the video. Please review:\n\n# Study Notes...",
  "requires_human_approval": true,
  "draft_notes": "# Study Notes for Video (dQw4w9WgXcQ)\n\n## 📌 Summary..."
}
```

### 5. Approve Draft Notes (`POST /notes/approve`)
```bash
curl -X POST http://127.0.0.1:8000/notes/approve \
  -H "Content-Type: application/json" \
  -d '{"thread_id": "student_session_2"}'
```

### 6. Revise Draft Notes with Feedback (`POST /notes/revise`)
```bash
curl -X POST http://127.0.0.1:8000/notes/revise \
  -H "Content-Type: application/json" \
  -d '{
    "thread_id": "student_session_2",
    "feedback": "Make the notes shorter and add one real world example."
  }'
```

---

## 16. Example Student Questions
- *"What is context switching?"*
- *"Where does the teacher explain process starvation?"*
- *"Explain context switching like I am a beginner."*
- *"Create easy notes from this video."*
- *"First find where the teacher explains context switching and then explain it to me."*

---

## 17. Human-in-the-Loop (HITL) Flow
1. **User asks:** "Create easy study notes from this video."
2. **Agent retrieves:** Transcript chunks from ChromaDB and compiles draft notes.
3. **State Pauses:** LangGraph sets `requires_human_approval = True` and returns draft notes to frontend.
4. **Human Review:** Student or teacher inspects draft notes.
   - Click **APPROVE** $\rightarrow$ Triggers `POST /notes/approve`, finalizing notes.
   - Enter **FEEDBACK** ("Make notes shorter") $\rightarrow$ Triggers `POST /notes/revise`, prompting agent to revise and output updated notes.

---

## 18. Testing
Run the complete automated test suite (41 tests):
```powershell
$env:PYTHONPATH="."; .\venv\Scripts\pytest.exe -v
```

Test Module Breakdown:
- `test_api.py`: FastAPI endpoints (/health, /video/process, /chat, /notes/*)
- `test_youtube.py`: YouTube URL validation & ID extraction
- `test_transcript.py`: Timestamped subtitle extraction & chunking
- `test_vector_store.py`: ChromaDB indexing, search, duplicate prevention
- `test_mcp.py`: VideoTutor MCP tools
- `test_mcp_client.py`: LangChain tool binding & execution
- `test_agent.py`: LangGraph state graph compilation & reasoning
- `test_features.py`: Video Q&A, topic search, simple explanation, notes
- `test_hitl.py`: Human-in-the-Loop approval & revision workflows
- `test_e2e.py`: Complete end-to-end user journey

---

## 19. Future Improvements
- 📺 **Playlist Processing:** Ingest full YouTube playlists and index multiple videos.
- 🔍 **Cross-Video Search:** Query concepts across multiple lectures simultaneously.
- 🎓 **Student Profile & Weak-Topic Detection:** Track student queries to recommend personalized revision topics.
- 🎴 **Flashcards & Quiz Generation:** Automatically generate study flashcards and interactive quizzes from video transcripts.
