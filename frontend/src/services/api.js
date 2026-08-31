const API_BASE_URL = 'http://127.0.0.1:8000';

export async function checkHealth() {
  const response = await fetch(`${API_BASE_URL}/health`);
  if (!response.ok) throw new Error('Backend health check failed');
  return response.json();
}

export async function processVideo(videoUrl) {
  const response = await fetch(`${API_BASE_URL}/video/process`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/json'
    },
    body: JSON.stringify({ video_url: videoUrl })
  });

  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || 'Failed to process video');
  }
  return data;
}

export async function sendChatMessage(videoId, message, threadId = 'default_thread') {
  const response = await fetch(`${API_BASE_URL}/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/json'
    },
    body: JSON.stringify({
      video_id: videoId,
      message: message,
      thread_id: threadId
    })
  });

  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || 'Failed to get chat response');
  }
  return data;
}

export async function approveNotes(threadId) {
  const response = await fetch(`${API_BASE_URL}/notes/approve`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/json'
    },
    body: JSON.stringify({ thread_id: threadId })
  });

  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || 'Failed to approve notes');
  }
  return data;
}

export async function reviseNotes(threadId, feedback) {
  const response = await fetch(`${API_BASE_URL}/notes/revise`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/json'
    },
    body: JSON.stringify({
      thread_id: threadId,
      feedback: feedback
    })
  });

  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || 'Failed to revise notes');
  }
  return data;
}
