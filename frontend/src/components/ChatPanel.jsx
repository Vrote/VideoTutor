import React, { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { parseTimeToSeconds, enrichMarkdownTimestamps } from '../utils/timestamp';

export default function ChatPanel({ messages, onSendMessage, isLoading, onSeekTimestamp, videoId }) {
  const [input, setInput] = useState('');
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (input.trim() && !isLoading) {
      onSendMessage(input.trim());
      setInput('');
    }
  };

  const MarkdownComponents = {
    a: ({ href, children }) => {
      const match = href && href.match(/[?&]t=(\d+)/);
      let seconds = match ? parseInt(match[1], 10) : parseTimeToSeconds(Array.isArray(children) ? children.join('') : String(children || ''));

      if (seconds !== null) {
        return (
          <button
            type="button"
            className="timestamp-chip"
            onClick={() => onSeekTimestamp && onSeekTimestamp(seconds)}
          >
            ▶ {children}
          </button>
        );
      }
      return <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>;
    }
  };

  return (
    <div className="chat-container">
      <div className="chat-header">
        <h3>Video Q&A</h3>
      </div>

      <div className="chat-messages">
        {messages.map((msg, i) => (
          <div key={i} className={`chat-msg ${msg.role}`}>
            <span className="msg-sender">{msg.role === 'agent' ? 'VideoTutor' : 'You'}</span>
            <div className="msg-bubble markdown-body">
              <ReactMarkdown remarkPlugins={[remarkGfm]} components={MarkdownComponents}>
                {enrichMarkdownTimestamps(msg.content, videoId)}
              </ReactMarkdown>
            </div>
          </div>
        ))}
        {isLoading && (
          <div className="chat-msg agent">
            <span className="msg-sender">VideoTutor</span>
            <div className="msg-bubble" style={{ color: 'var(--muted)' }}>Generating answer...</div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      <div className="quick-prompts">
        {['Create study notes', 'Key milestones', 'Summary & takeaways', 'Practice quiz'].map((p) => (
          <button key={p} className="prompt-btn" onClick={() => !isLoading && onSendMessage(p)}>
            {p}
          </button>
        ))}
      </div>

      <div className="chat-input-bar">
        <form className="chat-form" onSubmit={handleSubmit}>
          <input
            type="text"
            className="chat-input"
            placeholder="Ask a question about this video..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={isLoading}
          />
          <button type="submit" className="btn-primary" disabled={!input.trim() || isLoading}>
            Send
          </button>
        </form>
      </div>
    </div>
  );
}
