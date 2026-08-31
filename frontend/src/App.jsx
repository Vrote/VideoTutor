import React, { useState } from 'react';
import Navbar from './components/Navbar';
import VideoPlayer from './components/VideoPlayer';
import NotesPanel from './components/NotesPanel';
import ChatPanel from './components/ChatPanel';
import RevisionModal from './components/RevisionModal';
import { processVideo, sendChatMessage, approveNotes, reviseNotes } from './services/api';

export default function App() {
  const [videoId, setVideoId] = useState('TVXEfw6Nrjk');
  const [videoUrl, setVideoUrl] = useState('https://youtu.be/TVXEfw6Nrjk');
  const [currentTimestamp, setCurrentTimestamp] = useState(null);
  const [threadId, setThreadId] = useState(`thread_${Date.now()}`);
  const [notes, setNotes] = useState(null);
  const [requiresApproval, setRequiresApproval] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isChatLoading, setIsChatLoading] = useState(false);
  const [isRevisionOpen, setIsRevisionOpen] = useState(false);
  
  // Default to 'notes' so Video is on Left and Notes are full-height on Right
  const [viewMode, setViewMode] = useState('notes');
  
  // Resizable panel dimensions (for split mode)
  const [leftWidth, setLeftWidth] = useState(50); // percentage
  const [videoHeight, setVideoHeight] = useState(260); // px

  const [messages, setMessages] = useState([
    {
      role: 'agent',
      content: 'Welcome to **VideoTutor**.\n\nAsk questions about this lecture or click **Create study notes** below to generate complete notes.'
    }
  ]);

  const handleProcessVideo = async (url) => {
    setIsProcessing(true);
    try {
      const data = await processVideo(url);
      setVideoId(data.video_id);
      setVideoUrl(url);
      setThreadId(`thread_${data.video_id}_${Date.now()}`);
      setMessages([{ role: 'agent', content: `Video loaded (${data.chunks_count} segments indexed). Ask questions or generate notes!` }]);
      setNotes(null);
    } catch (err) {
      alert(err.message);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleSendMessage = async (text) => {
    if (!videoId) return alert('Please load a video first.');
    const newMsgs = [...messages, { role: 'user', content: text }];
    setMessages(newMsgs);
    setIsChatLoading(true);

    try {
      const data = await sendChatMessage(videoId, text, threadId);
      setMessages([...newMsgs, { role: 'agent', content: data.response }]);
      if (data.draft_notes || data.requires_human_approval) {
        setNotes(data.draft_notes || data.response);
        setRequiresApproval(data.requires_human_approval);
      }
    } catch (err) {
      setMessages([...newMsgs, { role: 'agent', content: `Error: ${err.message}` }]);
    } finally {
      setIsChatLoading(false);
    }
  };

  const handleApprove = async () => {
    setIsProcessing(true);
    try {
      const data = await approveNotes(threadId);
      setRequiresApproval(false);
      if (data.draft_notes) setNotes(data.draft_notes);
      setMessages((prev) => [...prev, { role: 'agent', content: 'Study notes approved.' }]);
    } catch (err) {
      alert(err.message);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleRevise = async (feedback) => {
    setIsProcessing(true);
    try {
      const data = await reviseNotes(threadId, feedback);
      setIsRevisionOpen(false);
      setRequiresApproval(true);
      if (data.draft_notes) setNotes(data.draft_notes);
      setMessages((prev) => [...prev, { role: 'agent', content: `Notes revised: "${feedback}"` }]);
    } catch (err) {
      alert(err.message);
    } finally {
      setIsProcessing(false);
    }
  };

  // Drag horizontal separator between Left Panel & Chatbot
  const handleColResize = (e) => {
    const startX = e.clientX;
    const startW = leftWidth;
    const onMove = (moveEvt) => {
      const delta = ((moveEvt.clientX - startX) / window.innerWidth) * 100;
      setLeftWidth(Math.min(80, Math.max(20, startW + delta)));
    };
    const onUp = () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  };

  // Drag vertical separator between Video & Notes
  const handleRowResize = (e) => {
    const startY = e.clientY;
    const startH = videoHeight;
    const onMove = (moveEvt) => {
      const delta = moveEvt.clientY - startY;
      setVideoHeight(Math.min(window.innerHeight - 180, Math.max(140, startH + delta)));
    };
    const onUp = () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  };

  return (
    <div>
      <Navbar
        currentUrl={videoUrl}
        onProcessVideo={handleProcessVideo}
        isLoading={isProcessing}
        viewMode={viewMode}
        onChangeViewMode={setViewMode}
      />

      <main className="main-workspace">
        {/* Mode 1: Study Notes Mode (Video Left 50% + Full Height Notes Right 50%) */}
        {viewMode === 'notes' && (
          <>
            <section className="left-panel-video">
              <VideoPlayer videoId={videoId} currentTimestamp={currentTimestamp} />
            </section>
            <section className="right-panel-full">
              <NotesPanel
                notes={notes}
                onChangeNotes={setNotes}
                requiresApproval={requiresApproval}
                onApprove={handleApprove}
                onOpenRevision={() => setIsRevisionOpen(true)}
                onSeekTimestamp={setCurrentTimestamp}
                videoId={videoId}
                isProcessing={isProcessing}
              />
            </section>
          </>
        )}

        {/* Mode 2: AI Tutor Mode (Video Left 50% + Full Height Chat Right 50%) */}
        {viewMode === 'chat' && (
          <>
            <section className="left-panel-video">
              <VideoPlayer videoId={videoId} currentTimestamp={currentTimestamp} />
            </section>
            <section className="right-panel-full">
              <ChatPanel
                messages={messages}
                onSendMessage={handleSendMessage}
                isLoading={isChatLoading}
                onSeekTimestamp={setCurrentTimestamp}
                videoId={videoId}
              />
            </section>
          </>
        )}

        {/* Mode 3: Split View (Video + Notes on Left, Chat on Right) */}
        {viewMode === 'split' && (
          <>
            <section className="left-panel" style={{ width: `${leftWidth}%` }}>
              <div style={{ height: `${videoHeight}px`, flexShrink: 0 }}>
                <VideoPlayer videoId={videoId} currentTimestamp={currentTimestamp} />
              </div>
              <div className="resizer-row" onMouseDown={handleRowResize} title="Drag to resize" />
              <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
                <NotesPanel
                  notes={notes}
                  onChangeNotes={setNotes}
                  requiresApproval={requiresApproval}
                  onApprove={handleApprove}
                  onOpenRevision={() => setIsRevisionOpen(true)}
                  onSeekTimestamp={setCurrentTimestamp}
                  videoId={videoId}
                  isProcessing={isProcessing}
                />
              </div>
            </section>

            <div className="resizer-col" onMouseDown={handleColResize} title="Drag to resize" />

            <aside className="right-panel">
              <ChatPanel
                messages={messages}
                onSendMessage={handleSendMessage}
                isLoading={isChatLoading}
                onSeekTimestamp={setCurrentTimestamp}
                videoId={videoId}
              />
            </aside>
          </>
        )}
      </main>

      <RevisionModal
        isOpen={isRevisionOpen}
        onClose={() => setIsRevisionOpen(false)}
        onSubmit={handleRevise}
        isSubmitting={isProcessing}
      />
    </div>
  );
}
