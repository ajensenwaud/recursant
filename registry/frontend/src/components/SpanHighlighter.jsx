import { useState } from 'react';

const ACTION_COLORS = {
  block: { bg: 'bg-red-100', border: 'border-red-300', text: 'text-red-800', tooltip: 'bg-red-700' },
  warn: { bg: 'bg-yellow-100', border: 'border-yellow-300', text: 'text-yellow-800', tooltip: 'bg-yellow-700' },
  redact: { bg: 'bg-purple-100', border: 'border-purple-300', text: 'text-purple-800', tooltip: 'bg-purple-700' },
};

function Tooltip({ span, position }) {
  const colors = ACTION_COLORS[span._action] || ACTION_COLORS.block;
  return (
    <div
      className={`absolute z-50 px-3 py-2 text-xs text-white rounded shadow-lg max-w-xs ${colors.tooltip}`}
      style={{ bottom: '100%', left: position, marginBottom: '4px' }}
    >
      <div className="font-semibold mb-1">{span.reason || 'Triggered'}</div>
      {span.confidence != null && (
        <div className="opacity-80">Confidence: {(span.confidence * 100).toFixed(0)}%</div>
      )}
    </div>
  );
}

export default function SpanHighlighter({ text, spans, action = 'block' }) {
  const [hoveredIdx, setHoveredIdx] = useState(null);

  if (!text) return null;
  if (!spans || spans.length === 0) {
    return <span className="text-sm text-gray-700 whitespace-pre-wrap">{text}</span>;
  }

  // Tag spans with the action for coloring
  const taggedSpans = spans
    .map((s) => ({ ...s, _action: action }))
    .filter((s) => s.start >= 0 && s.end > s.start && s.end <= text.length)
    .sort((a, b) => a.start - b.start);

  // Merge overlapping spans
  const merged = [];
  for (const span of taggedSpans) {
    if (merged.length > 0 && span.start <= merged[merged.length - 1].end) {
      merged[merged.length - 1].end = Math.max(merged[merged.length - 1].end, span.end);
      merged[merged.length - 1].reason = [merged[merged.length - 1].reason, span.reason]
        .filter(Boolean).join('; ');
    } else {
      merged.push({ ...span });
    }
  }

  // Build segments
  const segments = [];
  let pos = 0;
  merged.forEach((span, idx) => {
    if (span.start > pos) {
      segments.push({ text: text.slice(pos, span.start), type: 'normal' });
    }
    segments.push({ text: text.slice(span.start, span.end), type: 'highlight', span, idx });
    pos = span.end;
  });
  if (pos < text.length) {
    segments.push({ text: text.slice(pos), type: 'normal' });
  }

  const colors = ACTION_COLORS[action] || ACTION_COLORS.block;

  return (
    <span className="text-sm text-gray-700 whitespace-pre-wrap">
      {segments.map((seg, i) =>
        seg.type === 'normal' ? (
          <span key={i}>{seg.text}</span>
        ) : (
          <span
            key={i}
            className={`relative inline ${colors.bg} ${colors.text} border-b-2 ${colors.border} cursor-help`}
            onMouseEnter={() => setHoveredIdx(seg.idx)}
            onMouseLeave={() => setHoveredIdx(null)}
          >
            {seg.text}
            {hoveredIdx === seg.idx && (
              <Tooltip span={seg.span} position="0" />
            )}
          </span>
        )
      )}
    </span>
  );
}
