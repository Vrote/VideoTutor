import logging
import re
from typing import Dict, Any, List
from backend.app.config import settings
from backend.app.services.youtube import extract_video_id
from backend.app.services.transcript import get_video_transcript, chunk_transcript
from backend.app.services.vector_store import (
    add_transcript_chunks,
    search_transcript as db_search_transcript,
    is_video_processed,
    get_all_transcript_chunks
)

logger = logging.getLogger("VideoTutor.MCPServer")


def get_video_info_tool(video_url: str) -> Dict[str, Any]:
    """MCP Tool: Validate a YouTube URL and retrieve video information and index status.

    Args:
        video_url: Full YouTube URL (watch, short, embed) or 11-character Video ID.

    Returns:
        Dict containing video_id, original_url, and whether transcript is indexed in ChromaDB.
    """
    try:
        video_id = extract_video_id(video_url)
        processed = is_video_processed(video_id)
        return {
            "success": True,
            "video_id": video_id,
            "video_url": video_url,
            "is_indexed": processed,
            "message": "Video info retrieved successfully."
        }
    except Exception as e:
        logger.error(f"MCP tool get_video_info error for '{video_url}': {e}")
        return {
            "success": False,
            "error": str(e),
            "video_url": video_url
        }


def get_transcript_tool(video_url: str) -> Dict[str, Any]:
    """MCP Tool: Fetch timestamped transcript for a YouTube video, chunk it, and store in ChromaDB.

    Args:
        video_url: Full YouTube URL or 11-character Video ID.

    Returns:
        Dict containing video_id, total_chunks, timestamped sample segments, and processing status.
    """
    try:
        video_id = extract_video_id(video_url)

        raw_items = get_video_transcript(video_id)

        chunks = chunk_transcript(raw_items, video_id=video_id)

        added_count = add_transcript_chunks(video_id, chunks)

        return {
            "success": True,
            "video_id": video_id,
            "video_url": video_url,
            "raw_segments_count": len(raw_items),
            "chunks_count": len(chunks),
            "newly_indexed_chunks": added_count,
            "message": f"Successfully processed video transcript ({len(chunks)} chunks ready)."
        }
    except Exception as e:
        logger.error(f"MCP tool get_transcript error for '{video_url}': {e}")
        return {
            "success": False,
            "error": str(e),
            "video_url": video_url
        }


def search_transcript_tool(video_id: str, query: str, top_k: int = 5) -> Dict[str, Any]:
    """MCP Tool: Search for specific factual concepts or focused topics in the video transcript.

    Args:
        video_id: 11-character YouTube video ID.
        query: Concise concept or keyword to search (e.g., 'client server architecture', 'context switching', 'protocol specification'). Extract the core search term; do not include conversational instructions like 'give me a quiz' or 'can you explain'.
        top_k: Number of relevant transcript chunks to return (default: 5).

    Returns:
        Dict containing matching transcript chunks with exact timestamps, relevance flag, and match status.
    """
    try:
        if not video_id:
            return {"success": False, "error": "video_id is required."}
        if not query or not query.strip():
            return {"success": False, "error": "query string cannot be empty."}

        clean_vid = extract_video_id(video_id)

        if not is_video_processed(clean_vid):
            logger.info(f"Video '{clean_vid}' not indexed yet. Auto-indexing before search...")
            get_transcript_tool(clean_vid)

        results = db_search_transcript(clean_vid, query, top_k=top_k)

        has_relevant_match = len(results) > 0
        if results and results[0].get("distance") is not None:
            top_dist = results[0].get("distance")
            # Use the configurable threshold from settings (SEARCH_RELEVANCE_THRESHOLD).
            # Default: 1.4 suits SentenceTransformer L2 distances.
            # Tune higher in .env if using the lightweight hash fallback.
            has_relevant_match = top_dist < settings.SEARCH_RELEVANCE_THRESHOLD

        return {
            "success": True,
            "video_id": clean_vid,
            "query": query,
            "results_count": len(results),
            "relevant_match_found": has_relevant_match,
            "results": results,
            "message": "Relevant transcript chunks found." if has_relevant_match else f"No relevant discussion about '{query}' found in this video's transcript."
        }
    except Exception as e:
        logger.error(f"MCP tool search_transcript error for '{video_id}', query '{query}': {e}")
        return {
            "success": False,
            "error": str(e),
            "video_id": video_id,
            "query": query
        }


def generate_video_notes_tool(video_id: str) -> Dict[str, Any]:
    """MCP Tool: Retrieve representative multi-section transcript timeline chunks covering the ENTIRE video lecture.

    Use this tool whenever the user request requires synthesis across the whole lecture, such as:
    - Creating structured study notes, summaries, or cheat sheets.
    - Generating quizzes, self-tests, review questions, or comprehension checks based on the video.
    - Providing an overarching lecture timeline, milestones, or core takeaways breakdown.

    Args:
        video_id: 11-character YouTube Video ID.

    Returns:
        Dict containing full-video representative chunks across timeline with timestamps.
    """
    try:
        if not video_id:
            return {"success": False, "error": "video_id is required."}

        clean_vid = extract_video_id(video_id)

        if not is_video_processed(clean_vid):
            logger.info(f"Video '{clean_vid}' not indexed yet. Auto-indexing for whole-video notes...")
            get_transcript_tool(clean_vid)

        all_chunks = get_all_transcript_chunks(clean_vid)
        if not all_chunks:
            get_transcript_tool(clean_vid)
            all_chunks = get_all_transcript_chunks(clean_vid)

        total_count = len(all_chunks)
        # Sample 8 key milestone chunks across video timeline to stay well within Groq request limits
        target_samples = 8
        if total_count <= target_samples:
            sampled = all_chunks
        else:
            step = total_count / float(target_samples)
            sampled = []
            selected_indices = set()
            for i in range(target_samples):
                idx = min(int(round(i * step)), total_count - 1)
                if idx not in selected_indices:
                    selected_indices.add(idx)
                    sampled.append(all_chunks[idx])
            if (total_count - 1) not in selected_indices:
                sampled.append(all_chunks[-1])

        collected_chunks = []
        for c in sampled:
            text_snippet = c.get("text", "").strip()
            # Retain up to 220 characters of context per milestone chunk
            if len(text_snippet) > 220:
                text_snippet = text_snippet[:220] + "..."
            collected_chunks.append({
                "chunk_index": c.get("chunk_index", 0),
                "start_time": c.get("start_time", 0.0),
                "end_time": c.get("end_time", 0.0),
                "video_id": clean_vid,
                "text": text_snippet
            })

        collected_chunks.sort(key=lambda x: x.get("start_time", 0.0))

        logger.info(f"generate_video_notes_tool: Compactly sampled {len(collected_chunks)} chunks spanning {collected_chunks[0].get('start_time', 0)}s to {collected_chunks[-1].get('start_time', 0)}s.")

        return {
            "success": True,
            "video_id": clean_vid,
            "chunks_count": len(collected_chunks),
            "chunks": collected_chunks,
            "message": f"Retrieved {len(collected_chunks)} full-timeline chunks spanning entire video lecture."
        }
    except Exception as e:
        logger.error(f"MCP tool generate_video_notes error for '{video_id}': {e}")
        return {
            "success": False,
            "error": str(e),
            "video_id": video_id
        }


def answer_from_general_knowledge_tool(query: str, reason: str = "Topic not covered in video transcript") -> Dict[str, Any]:
    """MCP Tool: Provide a knowledge-based explanation for concepts when the question is NOT present in the video transcript.

    Args:
        query: The user's question or topic.
        reason: Explanation of why general knowledge is being used.

    Returns:
        Dict confirming general knowledge mode and acknowledging out-of-video topic.
    """
    return {
        "success": True,
        "is_out_of_video": True,
        "query": query,
        "reason": reason,
        "instruction": "Respond clearly explaining that this topic is not discussed in the loaded video, then provide a helpful explanation based on general knowledge."
    }


MCP_TOOLS = {
    "get_video_info": get_video_info_tool,
    "get_transcript": get_transcript_tool,
    "search_transcript": search_transcript_tool,
    "generate_video_notes": generate_video_notes_tool,
    "answer_from_general_knowledge": answer_from_general_knowledge_tool,
}
