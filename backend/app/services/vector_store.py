import os
import logging
import threading
from typing import List, Dict, Any, Optional
import chromadb
from chromadb.config import Settings as ChromaSettings
from backend.app.config import settings
from backend.app.services.youtube import extract_video_id

logger = logging.getLogger("VideoTutor.VectorStore")

COLLECTION_NAME = "videotutor_transcripts"

# Tracks which embedding function is currently active.
# Set during get_embedding_function(); used for logging and diagnostics.
_active_embedding_type: str = "unknown"

# Per-video insertion locks: prevents race conditions when two concurrent
# requests for the same video both pass the is_video_processed() check.
_video_insert_locks: Dict[str, threading.Lock] = {}
_video_locks_meta: threading.Lock = threading.Lock()  # guards _video_insert_locks itself


def _get_video_lock(video_id: str) -> threading.Lock:
    """Return a per-video threading.Lock, creating it if needed."""
    with _video_locks_meta:
        if video_id not in _video_insert_locks:
            _video_insert_locks[video_id] = threading.Lock()
        return _video_insert_locks[video_id]

from chromadb.api.types import EmbeddingFunction, Documents, Embeddings

class LightweightDefaultEmbeddingFunction(EmbeddingFunction):
    """Universal lightweight embedding function for zero-download vector indexing.

    Uses a 64-dimensional representation built from:
    - Word presence hashing across 48 buckets (FNV-1a style, mod 48)
    - Character bigram density in 8 feature buckets
    - Normalized text length and average word length
    - Punctuation/digit density signals

    This produces meaningfully different vectors for different topics and
    domains without requiring any ML model download.
    """
    DIM = 64

    def __init__(self):
        pass

    def name(self) -> str:
        return "default"

    def get_config(self) -> dict:
        return {}

    @classmethod
    def build_from_config(cls, config: dict):
        return cls()

    @staticmethod
    def _fnv1a_hash(s: str) -> int:
        """FNV-1a 32-bit hash for a string."""
        h = 0x811C9DC5
        for ch in s.encode("utf-8", errors="replace"):
            h ^= ch
            h = (h * 0x01000193) & 0xFFFFFFFF
        return h

    def __call__(self, input: Documents) -> Embeddings:
        embeddings = []
        for text in input:
            text = text or ""
            text_lower = text.lower()
            words = text_lower.split()
            total_words = max(len(words), 1)
            total_chars = max(len(text_lower), 1)

            vec = [0.0] * self.DIM

            # Buckets 0-47: word-level hashing (FNV-1a mod 48)
            for word in words:
                # strip punctuation edges
                word = word.strip(".,!?;:()[]{}\"'")
                if len(word) < 2:
                    continue
                bucket = self._fnv1a_hash(word) % 48
                vec[bucket] += 1.0

            # Normalize word buckets by total word count
            for i in range(48):
                vec[i] = vec[i] / total_words

            # Buckets 48-55: character bigram density (8 buckets)
            bigram_counts = [0] * 8
            for i in range(len(text_lower) - 1):
                bigram = text_lower[i:i+2]
                if bigram.strip():
                    bucket = self._fnv1a_hash(bigram) % 8
                    bigram_counts[bucket] += 1
            total_bigrams = max(sum(bigram_counts), 1)
            for i in range(8):
                vec[48 + i] = bigram_counts[i] / total_bigrams

            # Bucket 56: normalized text length (log scale, cap at 2000 chars)
            import math
            vec[56] = math.log1p(min(total_chars, 2000)) / math.log1p(2000)

            # Bucket 57: average word length / 10
            avg_word_len = sum(len(w) for w in words) / total_words if words else 0
            vec[57] = min(avg_word_len / 10.0, 1.0)

            # Bucket 58: digit density
            digit_count = sum(1 for c in text_lower if c.isdigit())
            vec[58] = digit_count / total_chars

            # Bucket 59: uppercase ratio (from original text)
            upper_count = sum(1 for c in text if c.isupper())
            vec[59] = upper_count / total_chars

            # Bucket 60: punctuation density
            punct_count = sum(1 for c in text if c in ".,!?;:()[]{}\"'")
            vec[60] = punct_count / total_chars

            # Bucket 61: unique word ratio
            unique_words = len(set(words))
            vec[61] = unique_words / total_words

            # Buckets 62-63: sentence-level hash features
            sentences = [s.strip() for s in text_lower.replace("!", ".").replace("?", ".").split(".") if s.strip()]
            total_sents = max(len(sentences), 1)
            vec[62] = min(total_sents / 20.0, 1.0)  # sentence count (normalized)
            avg_sent_len = sum(len(s) for s in sentences) / total_sents if sentences else 0
            vec[63] = min(avg_sent_len / 200.0, 1.0)  # avg sentence length (normalized)

            embeddings.append(vec)
        return embeddings


_chroma_client: Optional[chromadb.PersistentClient] = None
_collection = None


def get_chroma_client() -> chromadb.PersistentClient:
    """Initialize or return persistent local ChromaDB client."""
    global _chroma_client
    if _chroma_client is None:
        raw_path = settings.CHROMA_PERSIST_DIRECTORY or "../chroma_data"
        if os.path.isabs(raw_path):
            persist_dir = raw_path
        else:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
            persist_dir = os.path.abspath(os.path.join(base_dir, raw_path))
        os.makedirs(persist_dir, exist_ok=True)
        logger.info(f"Initializing persistent ChromaDB client at: '{persist_dir}'")
        _chroma_client = chromadb.PersistentClient(path=persist_dir)
    return _chroma_client


def get_embedding_function():
    """Get the configured embedding function for ChromaDB vector indexing and search.

    Tries SentenceTransformerEmbeddingFunction first (using EMBEDDING_MODEL from
    settings). Falls back to LightweightDefaultEmbeddingFunction if the model
    cannot be loaded, and logs a WARNING so the degradation is visible.
    """
    global _active_embedding_type
    model_name = settings.EMBEDDING_MODEL or "all-MiniLM-L6-v2"
    try:
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
        logger.info(f"Initializing SentenceTransformerEmbeddingFunction (model: '{model_name}')...")
        ef = SentenceTransformerEmbeddingFunction(model_name=model_name)
        _active_embedding_type = f"sentence-transformers/{model_name}"
        logger.info(f"Embedding function active: {_active_embedding_type}")
        return ef
    except Exception as e:
        _active_embedding_type = "lightweight-hash-fallback"
        logger.warning(
            f"[DEGRADED SEARCH] Could not load SentenceTransformerEmbeddingFunction "
            f"(model='{model_name}'): {e}. "
            f"Falling back to LightweightDefaultEmbeddingFunction (64-dim hash). "
            f"Semantic search quality will be reduced. "
            f"Install sentence-transformers to restore full search quality."
        )
        return LightweightDefaultEmbeddingFunction()


def get_transcript_collection(embedding_function=None):
    """Get or create the ChromaDB collection for video transcripts."""
    global _collection
    client = get_chroma_client()
    ef = embedding_function or get_embedding_function()
    try:
        _collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"description": "VideoTutor YouTube Video Transcript Chunks"},
            embedding_function=ef
        )
    except Exception as e:
        logger.warning(f"Failed to load existing ChromaDB collection ({e}). Deleting and recreating...")
        try:
            client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass
        _collection = client.create_collection(
            name=COLLECTION_NAME,
            metadata={"description": "VideoTutor YouTube Video Transcript Chunks"},
            embedding_function=ef
        )
    return _collection






def reset_collection():
    """Wipe and recreate the ChromaDB collection to recover from embedding dimension changes."""
    global _collection
    client = get_chroma_client()
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    ef = get_embedding_function()
    _collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={"description": "VideoTutor YouTube Video Transcript Chunks"},
        embedding_function=ef
    )
    logger.info("Successfully reset ChromaDB collection with active embedding function.")
    return _collection


def is_video_processed(video_id: str) -> bool:
    """Check if a video's transcript chunks are already indexed in ChromaDB."""
    try:
        collection = get_transcript_collection()
        results = collection.get(
            where={"video_id": video_id},
            limit=1
        )
        processed = len(results.get("ids", [])) > 0
        logger.info(f"Check is_video_processed('{video_id}'): {processed}")
        return processed
    except Exception as e:
        if "dimension" in str(e).lower():
            reset_collection()
        logger.error(f"Error checking if video '{video_id}' is processed: {e}")
        return False


def add_transcript_chunks(video_id: str, chunks: List[Dict[str, Any]]) -> int:
    """Add transcript chunks into persistent ChromaDB store.

    Thread-safe: acquires a per-video lock before the is_video_processed
    check so concurrent requests for the same video cannot both pass the
    duplicate guard and corrupt the store.

    Args:
        video_id: 11-character YouTube Video ID.
        chunks: List of chunk dicts from chunk_transcript.

    Returns:
        Number of inserted chunks.
    """
    if not chunks:
        logger.warning(f"No chunks provided to insert for video '{video_id}'.")
        return 0

    video_lock = _get_video_lock(video_id)
    with video_lock:
        # Re-check inside the lock — another thread may have inserted while
        # we were waiting to acquire.
        if is_video_processed(video_id):
            logger.info(f"Video '{video_id}' is already indexed in ChromaDB. Skipping duplicate insertion.")
            return 0

        collection = get_transcript_collection()

        ids = []
        documents = []
        metadatas = []

        for chunk in chunks:
            chunk_idx = chunk["chunk_index"]
            doc_id = f"{video_id}_chunk_{chunk_idx}"
            ids.append(doc_id)
            documents.append(chunk["text"])
            metadatas.append({
                "video_id": video_id,
                "start_time": float(chunk["start_time"]),
                "end_time": float(chunk["end_time"]),
                "chunk_index": int(chunk_idx)
            })

        try:
            clear_video_data(video_id)
            collection = get_transcript_collection()
            collection.add(
                ids=ids,
                documents=documents,
                metadatas=metadatas
            )
        except Exception as e:
            if "dimension" in str(e).lower() or "not exist" in str(e).lower() or "notfound" in str(e).lower():
                logger.warning(f"ChromaDB issue detected ({e}). Resetting collection...")
                collection = reset_collection()
                collection.add(
                    ids=ids,
                    documents=documents,
                    metadatas=metadatas
                )
            else:
                raise e

        logger.info(f"Successfully indexed {len(ids)} chunks for video '{video_id}' in ChromaDB.")
        return len(ids)


def search_transcript(video_id: str, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """Perform semantic similarity search over stored transcript chunks for a video.

    Args:
        video_id: 11-character YouTube video ID to filter search scope.
        query: User question or topic search query.
        top_k: Maximum number of relevant chunks to return (default: 5).

    Returns:
        List of matching chunk result dicts:
        [
            {
                "text": "...",
                "start_time": 920.0,
                "end_time": 970.0,
                "video_id": "abc123",
                "chunk_index": 10,
                "distance": 0.25
            }, ...
        ]
    """
    if not query or not query.strip():
        return []

    query_clean = query.strip()
    query_texts = [query_clean]
    if "mcp" in query_clean.lower():
        query_texts.extend(["Model Context Protocol", "एमसीपी", "MCP server client context"])

    collection = get_transcript_collection()

    results = collection.query(
        query_texts=query_texts,
        n_results=top_k,
        where={"video_id": video_id}
    )

    formatted_results = []
    seen_indices = set()

    all_docs = results.get("documents", [])
    all_metas = results.get("metadatas", [])
    all_dists = results.get("distances", [])

    for q_idx in range(len(all_docs)):
        docs = all_docs[q_idx] if q_idx < len(all_docs) else []
        metas = all_metas[q_idx] if q_idx < len(all_metas) else []
        dists = all_dists[q_idx] if q_idx < len(all_dists) else [0.0] * len(docs)

        for doc, meta, dist in zip(docs, metas, dists):
            chunk_idx = int(meta.get("chunk_index", 0))
            if chunk_idx not in seen_indices:
                seen_indices.add(chunk_idx)
                formatted_results.append({
                    "text": doc,
                    "start_time": float(meta.get("start_time", 0.0)),
                    "end_time": float(meta.get("end_time", 0.0)),
                    "video_id": meta.get("video_id", video_id),
                    "chunk_index": chunk_idx,
                    "distance": round(float(dist), 4) if dist is not None else 0.0
                })

    # Sort results by semantic relevance (smallest distance = highest similarity)
    formatted_results.sort(key=lambda x: x["distance"])
    logger.info(f"Semantic search for '{query}' on video '{video_id}' returned {len(formatted_results)} results.")
    return formatted_results


def get_all_transcript_chunks(video_id: str) -> List[Dict[str, Any]]:
    """Retrieve all indexed chunks for a video, sorted chronologically from start to end.

    Args:
        video_id: 11-character YouTube video ID.

    Returns:
        List of all transcript chunks sorted by start_time.
    """
    try:
        clean_vid = extract_video_id(video_id)
        collection = get_transcript_collection()
        data = collection.get(
            where={"video_id": clean_vid},
            include=["documents", "metadatas"]
        )
        docs = data.get("documents", [])
        metas = data.get("metadatas", [])

        chunks = []
        for doc, meta in zip(docs, metas):
            chunks.append({
                "text": doc,
                "start_time": float(meta.get("start_time", 0.0)),
                "end_time": float(meta.get("end_time", 0.0)),
                "video_id": meta.get("video_id", clean_vid),
                "chunk_index": int(meta.get("chunk_index", 0))
            })
        chunks.sort(key=lambda x: x["start_time"])
        logger.info(f"Retrieved {len(chunks)} total chronological chunks for video '{clean_vid}'.")
        return chunks
    except Exception as e:
        logger.error(f"Error fetching all chunks for video '{video_id}': {e}")
        return []


def clear_video_data(video_id: str) -> int:
    """Delete all stored transcript chunks for a specific video ID.

    Returns:
        Number of deleted chunks.
    """
    try:
        collection = get_transcript_collection()
        existing = collection.get(where={"video_id": video_id})
        ids_to_delete = existing.get("ids", [])
        if ids_to_delete:
            collection.delete(ids=ids_to_delete)
            logger.info(f"Deleted {len(ids_to_delete)} stored chunks for video '{video_id}'.")
            return len(ids_to_delete)
        return 0
    except Exception as e:
        logger.error(f"Error clearing video data for '{video_id}': {e}")
        return 0

