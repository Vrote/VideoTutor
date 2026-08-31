import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { parseTimeToSeconds, enrichMarkdownTimestamps } from '../utils/timestamp';

export default function NotesPanel({
  notes,
  onChangeNotes,
  requiresApproval,
  onApprove,
  onOpenRevision,
  onSeekTimestamp,
  videoId,
  isProcessing
}) {
  const [isEditing, setIsEditing] = useState(false);
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    if (notes) {
      navigator.clipboard.writeText(notes);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleDownload = () => {
    if (!notes) return;
    const blob = new Blob([notes], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `Study_Notes_${videoId || 'video'}.md`;
    a.click();
    URL.revokeObjectURL(url);
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
    <div className="notes-section">
      <div className="notes-header">
        <h2>Study Notes</h2>
        <div className="notes-actions">
          <button className="btn-secondary" onClick={() => setIsEditing(!isEditing)}>
            {isEditing ? 'Preview' : 'Edit'}
          </button>
          <button className="btn-secondary" onClick={handleCopy}>
            {copied ? 'Copied' : 'Copy'}
          </button>
          <button className="btn-secondary" onClick={handleDownload}>
            Download
          </button>
        </div>
      </div>

      {requiresApproval && (
        <div className="approval-banner">
          <span>Draft notes generated. Review and approve or revise:</span>
          <div style={{ display: 'flex', gap: '0.35rem' }}>
            <button className="btn-success" onClick={onApprove} disabled={isProcessing}>
              Approve
            </button>
            <button className="btn-secondary" onClick={onOpenRevision} disabled={isProcessing}>
              Revise
            </button>
          </div>
        </div>
      )}

      <div className="notes-body">
        {isEditing ? (
          <textarea
            className="notes-textarea"
            value={notes || ''}
            onChange={(e) => onChangeNotes && onChangeNotes(e.target.value)}
            placeholder="Write notes in Markdown..."
          />
        ) : (
          <div className="markdown-body">
            {notes ? (
              <ReactMarkdown remarkPlugins={[remarkGfm]} components={MarkdownComponents}>
                {enrichMarkdownTimestamps(notes, videoId)}
              </ReactMarkdown>
            ) : (
              <p style={{ color: 'var(--muted)' }}>No notes yet. Click "Create study notes" in Q&A to generate notes.</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
