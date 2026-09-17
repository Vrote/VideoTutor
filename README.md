# VideoTutor

VideoTutor is a web application that helps students learn from educational YouTube videos. By providing a YouTube link, the application extracts the video transcript and allows users to ask questions or generate study notes directly from the video content.

## Project Overview

The project is split into a frontend user interface and a backend API. It uses an AI agent to process user questions, search the transcript, and return answers with exact video timestamps.

### Key Components

- Frontend: Built with React and Vite. It contains the video player, chat interface, and a notes panel.
- Backend: Built with Python and FastAPI. It handles API requests, AI agent logic, and database interactions.
- Vector Database: Uses ChromaDB to store and search transcript chunks locally.
- Observability: A custom module that tracks the AI's execution time, token usage, and success rates.

### Core Technologies Used

- React.js
- Python (FastAPI)
- LangGraph (for structuring the AI agent workflow)
- Model Context Protocol (MCP) (for managing AI tools)
- ChromaDB
- Groq / Gemini (for Language Models)

## How It Works

1. Processing the Video: The user pastes a YouTube URL. The backend downloads the transcript, breaks it into smaller text chunks, and saves them in ChromaDB.
2. Asking Questions: The user asks a question in the chat. The LangGraph agent analyzes the question and searches ChromaDB for the most relevant transcript chunks.
3. Generating Answers: The agent reads the retrieved chunks and generates an answer, providing a direct timestamp link to that part of the video.
4. Study Notes and Human Review: If the user requests study notes, the agent generates a draft. The system pauses and waits for the user to either approve the notes or suggest revisions (Human-in-the-Loop workflow).

## How to Run the Project

### 1. Backend Setup

Open a terminal and navigate to the project root directory. Create a virtual environment:

python -m venv venv

Activate the virtual environment:
- Windows: .\venv\Scripts\activate
- Mac/Linux: source venv/bin/activate

Install the required Python packages:
pip install -r backend/requirements.txt

Create a .env file in the backend folder by copying backend/.env.example and add your API keys (like GROQ_API_KEY).

Start the backend server from the root directory:
- Windows:
$env:PYTHONPATH="."; python -m uvicorn backend.app.main:app --port 8000 --reload
- Mac/Linux:
PYTHONPATH="." python -m uvicorn backend.app.main:app --port 8000 --reload

The backend will be available at http://localhost:8000.

### 2. Frontend Setup

Open a new terminal and navigate to the frontend folder:
cd frontend

Install the Node modules:
npm install

Start the React development server:
npm run dev

The frontend will be available at http://localhost:5173.

## Observability and Monitoring

The project includes a built-in telemetry and observability module that tracks the performance and safety of the AI agent. 

### Features Monitored
- Execution Traces: Logs every step the AI takes, including intent classification and tool execution.
- Token Usage and Latency: Tracks how many tokens the language model consumes and how long each step takes.
- LLM Guardrails: Monitors input and output for safety, blocking prompt injections or harmful content.
- Evaluation Scorecard: Automatically evaluates the AI's responses for faithfulness, prompt adherence, and relevance, flagging any hallucinations.

### How to Access the Dashboard
The observability data is accessible directly from the frontend user interface. You can switch the view mode to "Observability" in the navigation bar to see real-time metrics, success rates, and detailed trace logs for every conversation.

### LangSmith Integration
For advanced monitoring, the backend is configured to support LangSmith. If you provide a `LANGCHAIN_API_KEY` in your `.env` file and set `LANGCHAIN_TRACING_V2=true`, all LangGraph agent state transitions will be automatically logged to your LangSmith project.

## Testing

The project includes an automated test suite for the backend. To run the tests, activate your virtual environment from the root directory and run:

pytest backend/tests/ -v
