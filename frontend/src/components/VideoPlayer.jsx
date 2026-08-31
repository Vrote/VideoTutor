import React, { useRef, useEffect } from 'react';

export default function VideoPlayer({ videoId, currentTimestamp }) {
  const iframeRef = useRef(null);

  useEffect(() => {
    if (currentTimestamp !== null && currentTimestamp !== undefined && iframeRef.current) {
      iframeRef.current.src = `https://www.youtube-nocookie.com/embed/${videoId}?start=${Math.floor(currentTimestamp)}&autoplay=1&enablejsapi=1`;
    }
  }, [currentTimestamp, videoId]);

  if (!videoId) return null;

  return (
    <div className="video-section">
      <div className="video-frame">
        <iframe
          ref={iframeRef}
          src={`https://www.youtube-nocookie.com/embed/${videoId}?enablejsapi=1`}
          title="Video Player"
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
          allowFullScreen
        />
      </div>
    </div>
  );
}
