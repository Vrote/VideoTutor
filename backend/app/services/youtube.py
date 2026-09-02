import re
import logging
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger("VideoTutor.YouTube")

YOUTUBE_ID_REGEX = re.compile(r"^[a-zA-Z0-9_-]{11}$")


def extract_video_id(url: str) -> str:
    """Extract and validate the 11-character YouTube video ID from various URL formats.

    Supported formats:
    - https://www.youtube.com/watch?v=VIDEO_ID
    - https://m.youtube.com/watch?v=VIDEO_ID
    - https://youtu.be/VIDEO_ID
    - https://www.youtube.com/embed/VIDEO_ID
    - https://www.youtube.com/v/VIDEO_ID
    - https://www.youtube.com/shorts/VIDEO_ID
    - https://www.youtube.com/live/VIDEO_ID
    - Plain 11-character Video ID string

    Raises:
        ValueError: If URL is invalid, empty, or video ID cannot be extracted.
    """
    if not url or not isinstance(url, str):
        raise ValueError("YouTube URL or ID must be a non-empty string.")

    cleaned_url = url.strip()

    if YOUTUBE_ID_REGEX.match(cleaned_url):
        logger.info(f"Direct video ID validated: {cleaned_url}")
        return cleaned_url

    try:
        parsed = urlparse(cleaned_url)
    except Exception as e:
        raise ValueError(f"Invalid URL structure: {e}")

    domain = parsed.netloc.lower()
    path = parsed.path

    if "youtu.be" in domain:
        video_id = path.lstrip("/")
        if "/" in video_id:
            video_id = video_id.split("/")[0]
        if "?" in video_id:
            video_id = video_id.split("?")[0]
        if YOUTUBE_ID_REGEX.match(video_id):
            logger.info(f"Extracted video ID from short link: {video_id}")
            return video_id

    if "youtube.com" in domain or "youtube-nocookie.com" in domain:
        query_params = parse_qs(parsed.query)
        if "v" in query_params and query_params["v"]:
            video_id = query_params["v"][0]
            if YOUTUBE_ID_REGEX.match(video_id):
                logger.info(f"Extracted video ID from query param: {video_id}")
                return video_id

        path_parts = [p for p in path.split("/") if p]
        if path_parts:
            if path_parts[0] in ["embed", "shorts", "v", "live"] and len(path_parts) >= 2:
                candidate_id = path_parts[1]
                if YOUTUBE_ID_REGEX.match(candidate_id):
                    logger.info(f"Extracted video ID from path {path_parts[0]}: {candidate_id}")
                    return candidate_id
            
            last_part = path_parts[-1]
            if YOUTUBE_ID_REGEX.match(last_part):
                logger.info(f"Extracted video ID from path end: {last_part}")
                return last_part

    raise ValueError(f"Could not extract a valid 11-character YouTube video ID from input: '{url}'")


ALLOWED_CATEGORIES = {
    "education",
    "science & technology",
    "howto & style",
}

BLOCKED_CATEGORIES = {
    "music",
    "gaming",
    "entertainment",
    "comedy",
    "sports",
    "film & animation",
    "autos & vehicles",
    "pets & animals",
}

EDUCATIONAL_KEYWORDS = [
    "tutorial", "lecture", "course", "lesson", "how to", "explained",
    "explanation", "learn", "study", "guide", "concept", "algorithm",
    "introduction", "crash course", "full course", "training", "physics",
    "chemistry", "biology", "math", "calculus", "coding", "programming"
]


def validate_video_category(video_url: str) -> tuple[bool, str, str]:
    """Validate whether a YouTube video belongs to an educational category using yt-dlp.

    Args:
        video_url: Full YouTube URL or video ID.

    Returns:
        tuple of (is_valid: bool, category_name: str, message: str)
    """
    try:
        import yt_dlp
    except ImportError:
        logger.warning("yt-dlp is not installed. Skipping video category validation.")
        return True, "Unknown", "Category validation skipped (yt-dlp missing)."

    try:
        vid = extract_video_id(video_url)
        canonical_url = f"https://www.youtube.com/watch?v={vid}"

        ydl_opts = {
            "skip_download": True,
            "quiet": True,
            "no_warnings": True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(canonical_url, download=False)
            categories = info.get("categories") or []
            title = (info.get("title") or "").lower()

            category = categories[0] if categories else "Unknown"
            cat_lower = category.strip().lower()

            # 1. Explicitly blocked non-educational category
            if cat_lower in BLOCKED_CATEGORIES:
                return (
                    False,
                    category,
                    f"VideoTutor only supports educational videos. This video is in the '{category}' category."
                )

            # 2. Explicitly allowed educational category
            if cat_lower in ALLOWED_CATEGORIES:
                return True, category, f"Verified educational video (Category: '{category}')."

            # 3. For ambiguous categories (e.g. People & Blogs), check for educational title keywords
            if any(kw in title for kw in EDUCATIONAL_KEYWORDS):
                return True, category, f"Accepted based on educational keywords in title (Category: '{category}')."

            # 4. If category is non-educational and no keywords match, reject
            return (
                False,
                category,
                f"VideoTutor only supports educational and tutorial content. This video was identified as '{category}'."
            )

    except ValueError as ve:
        return False, "Invalid", str(ve)
    except Exception as e:
        logger.warning(f"Error during yt-dlp category check for '{video_url}': {e}. Allowing as fallback.")
        return True, "Unverified", "Category check encountered an error; proceeding with video processing."
