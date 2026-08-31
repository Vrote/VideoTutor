import React, { useState } from 'react';

export default function RevisionModal({ isOpen, onClose, onSubmit, isSubmitting }) {
  const [feedback, setFeedback] = useState('');

  if (!isOpen) return null;

  const handleSubmit = (e) => {
    e.preventDefault();
    if (feedback.trim()) {
      onSubmit(feedback.trim());
      setFeedback('');
    }
  };

  return (
    <div className="modal-backdrop">
      <div className="modal-card">
        <h3>Revise Study Notes</h3>
        <form onSubmit={handleSubmit}>
          <textarea
            placeholder="Describe what changes you want..."
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            disabled={isSubmitting}
            autoFocus
          />
          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={!feedback.trim() || isSubmitting}>
              {isSubmitting ? 'Updating...' : 'Revise'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
