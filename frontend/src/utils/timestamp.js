/**
 * Format seconds into MM:SS or HH:MM:SS string
 * @param {number} totalSeconds 
 * @returns {string} formatted time
 */
export function formatSeconds(totalSeconds) {
  if (isNaN(totalSeconds) || totalSeconds < 0) return '00:00';
  
  const sec = Math.floor(totalSeconds % 60);
  const min = Math.floor((totalSeconds / 60) % 60);
  const hrs = Math.floor(totalSeconds / 3600);

  const pad = (num) => String(num).padStart(2, '0');

  if (hrs > 0) {
    return `${hrs}:${pad(min)}:${pad(sec)}`;
  }
  return `${pad(min)}:${pad(sec)}`;
}

/**
 * Parse time string (e.g. '02:15', '1:05:30', '135s', 't=135') into integer seconds
 * @param {string} timeStr 
 * @returns {number|null} seconds or null if invalid
 */
export function parseTimeToSeconds(timeStr) {
  if (!timeStr) return null;
  const clean = String(timeStr).trim();

  // Match t=123 or t=123s
  const tParamMatch = clean.match(/t=(\d+)/i);
  if (tParamMatch) {
    return parseInt(tParamMatch[1], 10);
  }

  // Match HH:MM:SS or MM:SS
  const colonMatch = clean.match(/^(\d{1,2}):(\d{2})(?::(\d{2}))?$/);
  if (colonMatch) {
    if (colonMatch[3] !== undefined) {
      const h = parseInt(colonMatch[1], 10);
      const m = parseInt(colonMatch[2], 10);
      const s = parseInt(colonMatch[3], 10);
      return h * 3600 + m * 60 + s;
    } else {
      const m = parseInt(colonMatch[1], 10);
      const s = parseInt(colonMatch[2], 10);
      return m * 60 + s;
    }
  }

  // Pure number
  if (/^\d+$/.test(clean)) {
    return parseInt(clean, 10);
  }

  return null;
}

/**
 * Helper to enrich markdown text by converting unlinked [MM:SS] timestamps
 * into clickable markdown links if they are not already linked.
 * @param {string} text 
 * @param {string} videoId 
 * @returns {string} enriched markdown
 */
export function enrichMarkdownTimestamps(text, videoId = 'video') {
  if (!text) return '';
  
  // Replace unlinked [MM:SS] or [HH:MM:SS] with [MM:SS](https://www.youtube.com/watch?v=VIDEO_ID&t=SECONDS)
  return text.replace(/\[(\d{1,2}:\d{2}(?::\d{2})?)\](?!\()/g, (match, timeStr) => {
    const sec = parseTimeToSeconds(timeStr);
    if (sec !== null) {
      return `[${timeStr}](https://www.youtube.com/watch?v=${videoId}&t=${sec})`;
    }
    return match;
  });
}
