import { useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { XMarkIcon } from '@heroicons/react/24/outline';
import StatusBadge from './StatusBadge';

/**
 * Tool-edge detail popup — appears when clicking a tool-assignment edge.
 */
export default function ToolEdgeDetailPopup({ edge, position, onClose }) {
  const ref = useRef(null);

  useEffect(() => {
    if (!edge) return;
    const handler = (e) => {
      if (ref.current && !ref.current.contains(e.target)) onClose();
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [edge, onClose]);

  if (!edge) return null;

  const popupWidth = 300;
  const popupHeight = 280;
  const left = Math.min(Math.max(position?.x ?? 0, 10), window.innerWidth - popupWidth - 10);
  const top = Math.min(Math.max((position?.y ?? 0) + 10, 10), window.innerHeight - popupHeight - 10);

  const srcName = typeof edge.source === 'object' ? edge.source.name : edge.source;
  const dstName = typeof edge.target === 'object' ? edge.target.name : edge.target;

  return (
    <div
      ref={ref}
      className="fixed bg-white rounded-lg shadow-xl border border-gray-200 z-50 p-4"
      style={{ left, top, width: popupWidth, maxHeight: popupHeight, overflow: 'auto' }}
    >
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-gray-900 truncate pr-2">
          {srcName} &rarr; {dstName}
        </h3>
        <button onClick={onClose} className="text-gray-400 hover:text-gray-600 flex-shrink-0">
          <XMarkIcon className="h-5 w-5" />
        </button>
      </div>

      <div className="space-y-2 text-sm">
        <div className="flex justify-between">
          <span className="text-gray-500">Type</span>
          <span className="text-amber-700 font-medium text-xs">Tool Assignment</span>
        </div>

        <div className="flex justify-between">
          <span className="text-gray-500">Call Count</span>
          <span className="text-gray-900 font-medium">{edge.count || 0}</span>
        </div>

        {edge.lastTimestamp && (
          <div className="flex justify-between">
            <span className="text-gray-500">Last Call</span>
            <span className="text-gray-700 text-xs">{new Date(edge.lastTimestamp).toLocaleString()}</span>
          </div>
        )}

        {edge.lastDecision && (
          <div className="flex justify-between">
            <span className="text-gray-500">Last Decision</span>
            <StatusBadge status={edge.lastDecision} />
          </div>
        )}

        {edge.outcome && (
          <div className="flex justify-between">
            <span className="text-gray-500">Last Outcome</span>
            <StatusBadge status={edge.outcome} />
          </div>
        )}

        {edge.lastMessageHash && (
          <div className="flex justify-between">
            <span className="text-gray-500">Args Hash</span>
            <span className="text-gray-700 font-mono text-xs">{edge.lastMessageHash}</span>
          </div>
        )}

        <div className="border-t border-gray-100 pt-2">
          <Link
            to={`/mesh-audit?a2a_method=tools/call&source_agent=${encodeURIComponent(srcName)}&dest_agent=${encodeURIComponent(dstName)}`}
            className="text-teal-600 hover:text-teal-800 text-xs font-medium"
          >
            View audit trail &rarr;
          </Link>
        </div>
      </div>
    </div>
  );
}
