import pytest
from backend.app.services.youtube import validate_video_category
from backend.app.mcp.server import get_transcript_tool


def test_educational_video_accepted():
    # Known educational lecture: C++ Tutorials (GateSmashers)
    is_valid, category, msg = validate_video_category("https://www.youtube.com/watch?v=TVXEfw6Nrjk")
    assert is_valid is True
    assert category.lower() in ["education", "science & technology"]
    assert "educational" in msg.lower() or "accepted" in msg.lower()


def test_music_video_rejected():
    # Known music video: Rick Astley
    is_valid, category, msg = validate_video_category("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert is_valid is False
    assert category.lower() == "music"
    assert "only supports educational" in msg


def test_get_transcript_tool_blocks_music_video():
    res = get_transcript_tool("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert res["success"] is False
    assert "Music" in res["error"] or res.get("category") == "Music"
