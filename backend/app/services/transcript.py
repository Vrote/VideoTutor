import logging
from typing import List, Dict, Any
from youtube_transcript_api import (
    YouTubeTranscriptApi,
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable
)
from backend.app.services.youtube import extract_video_id

logger = logging.getLogger("VideoTutor.Transcript")


def get_video_transcript(video_id_or_url: str, languages: List[str] = None) -> List[Dict[str, Any]]:
    """Retrieve timestamped transcript for a YouTube video with multi-language fallback.

    Args:
        video_id_or_url: YouTube URL or 11-character Video ID.
        languages: Preferred language codes (default: ['en', 'en-US', 'en-GB']).

    Returns:
        List of dicts containing timestamped segments:
        [
            {
                "start": 0.0,
                "end": 5.2,
                "text": "Hello world"
            }, ...
        ]

    Raises:
        ValueError: If video ID is invalid, transcript is disabled, empty, or unavailable.
    """
    video_id = extract_video_id(video_id_or_url)
    if not languages:
        languages = ["en", "en-US", "en-GB", "hi", "hi-Latn"]

    logger.info(f"Fetching transcript for video ID: '{video_id}'")

    raw_transcript = None
    api = YouTubeTranscriptApi()

    try:
        if hasattr(api, "fetch"):
            raw_transcript = api.fetch(video_id, languages=languages)
        elif hasattr(YouTubeTranscriptApi, "get_transcript"):
            raw_transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=languages)
    except TranscriptsDisabled:
        raise ValueError(f"Subtitles/Transcripts are disabled for YouTube video '{video_id}'.")
    except VideoUnavailable:
        raise ValueError(f"YouTube video '{video_id}' is unavailable or private.")
    except NoTranscriptFound:
        logger.info(f"No preferred transcript found for '{video_id}', attempting fallback...")
    except Exception as e:
        logger.info(f"Primary language fetch failed for '{video_id}', attempting fallback: {e}")

    if not raw_transcript and hasattr(api, "list"):
        try:
            transcript_list = api.list(video_id)
            selected_transcript = None

            if transcript_list:
                for t in transcript_list:
                    if getattr(t, "language_code", "") in languages:
                        selected_transcript = t
                        break

                if not selected_transcript:
                    for t in transcript_list:
                        if getattr(t, "is_translatable", False):
                            try:
                                selected_transcript = t.translate("en")
                                break
                            except Exception:
                                pass

                if not selected_transcript:
                    available = list(transcript_list)
                    if available:
                        selected_transcript = available[0]

            if selected_transcript and hasattr(selected_transcript, "fetch"):
                logger.info(f"Selected fallback transcript language for '{video_id}'")
                raw_transcript = selected_transcript.fetch()
        except TranscriptsDisabled:
            raise ValueError(f"Subtitles/Transcripts are disabled for YouTube video '{video_id}'.")
        except VideoUnavailable:
            raise ValueError(f"YouTube video '{video_id}' is unavailable or private.")
        except Exception as fallback_err:
            logger.error(f"Fallback transcript resolution failed for '{video_id}': {fallback_err}")

    if not raw_transcript:
        raise ValueError(f"No transcript or captions found for YouTube video '{video_id}'.")

    formatted_transcript = []
    for item in raw_transcript:
        if isinstance(item, dict):
            text_val = item.get("text", "")
            start_val = item.get("start", 0.0)
            dur_val = item.get("duration", 0.0)
        else:
            text_val = getattr(item, "text", "")
            start_val = getattr(item, "start", 0.0)
            dur_val = getattr(item, "duration", 0.0)

        clean_text = str(text_val).replace("\n", " ").strip()
        if not clean_text:
            continue

        start = round(float(start_val), 2)
        duration = round(float(dur_val), 2)
        end = round(start + duration, 2)

        formatted_transcript.append({
            "start": start,
            "end": end,
            "text": clean_text
        })

    if not formatted_transcript:
        raise ValueError(f"No usable transcript text items found for video '{video_id}'.")

    logger.info(f"Successfully retrieved {len(formatted_transcript)} transcript items for video '{video_id}'.")
    return formatted_transcript


def chunk_transcript(
    transcript_items: List[Dict[str, Any]],
    video_id: str,
    max_chunk_chars: int = 1000
) -> List[Dict[str, Any]]:
    """Group contiguous timestamped transcript items into windowed text chunks (approx 1.5 minutes).

    Args:
        transcript_items: List of dicts with 'start', 'end', 'text'.
        video_id: 11-character YouTube Video ID.
        max_chunk_chars: Maximum character threshold per chunk (default: 1000 ~ 1.5 minutes).

    Returns:
        List of chunk dicts ready for ChromaDB embedding & retrieval.
    """
    if not transcript_items:
        return []

    chunks = []
    current_texts = []
    chunk_start_time = None
    chunk_end_time = None
    current_char_count = 0
    chunk_index = 0

    for item in transcript_items:
        text = item.get("text", "").strip()
        if not text:
            continue

        item_start = float(item.get("start", 0.0))
        item_end = float(item.get("end", item_start))

        if chunk_start_time is None:
            chunk_start_time = item_start

        if current_char_count + len(text) > max_chunk_chars and current_texts:
            chunks.append({
                "text": " ".join(current_texts),
                "start_time": round(chunk_start_time, 2),
                "end_time": round(chunk_end_time, 2),
                "video_id": video_id,
                "chunk_index": chunk_index
            })
            chunk_index += 1

            overlap_item = current_texts[-1] if len(current_texts) > 1 else ""
            if overlap_item and len(overlap_item) < 200:
                current_texts = [overlap_item, text]
                current_char_count = len(overlap_item) + len(text) + 1
            else:
                current_texts = [text]
                current_char_count = len(text)

            chunk_start_time = item_start
            chunk_end_time = item_end
        else:
            current_texts.append(text)
            chunk_end_time = item_end
            current_char_count += len(text) + 1

    if current_texts and chunk_start_time is not None:
        chunks.append({
            "text": " ".join(current_texts),
            "start_time": round(chunk_start_time, 2),
            "end_time": round(chunk_end_time, 2),
            "video_id": video_id,
            "chunk_index": chunk_index
        })

    logger.info(f"Chunked {len(transcript_items)} transcript segments into {len(chunks)} chunks (~1.5-min window) for video '{video_id}'.")
    return chunks
