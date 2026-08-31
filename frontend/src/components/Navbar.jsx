import React, { useState } from 'react';

export default function Navbar({ currentUrl, onProcessVideo, isLoading, viewMode, onChangeViewMode }) {
  const [url, setUrl] = useState(currentUrl || '');

  const handleSubmit = (e) => {
    e.preventDefault();
    if (url.trim()) onProcessVideo(url.trim());
  };

  return (
    <header className="navbar">
      <div className="brand">VideoTutor</div>

      <form className="url-form" onSubmit={handleSubmit}>
        <input
          type="text"
          className="url-input"
          placeholder="Paste YouTube Video URL..."
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          disabled={isLoading}
        />
        <button type="submit" className="btn-primary" disabled={isLoading || !url.trim()}>
          {isLoading ? 'Loading...' : 'Load Video'}
        </button>
      </form>

      <div className="view-mode-tabs">
        <button
          type="button"
          className={`tab-btn ${viewMode === 'notes' ? 'active' : ''}`}
          onClick={() => onChangeViewMode('notes')}
        >
          Study Notes
        </button>
        <button
          type="button"
          className={`tab-btn ${viewMode === 'chat' ? 'active' : ''}`}
          onClick={() => onChangeViewMode('chat')}
        >
          AI Tutor
        </button>
        <button
          type="button"
          className={`tab-btn ${viewMode === 'split' ? 'active' : ''}`}
          onClick={() => onChangeViewMode('split')}
        >
          Split View
        </button>
      </div>
    </header>
  );
}
