import { useEffect, useRef } from 'react';
import { XMarkIcon } from '@heroicons/react/24/outline';
import StatusBadge from './StatusBadge';

/**
 * Edge detail popup — appears when clicking an edge in the mesh graph.
 *
 * Props:
 * - edge: edge data object (or null to hide)
 * - position: { x, y } screen coordinates for positioning
 * - policies: array of mesh policies
 * - onClose: () => void
 */
export default function EdgeDetailPopup({ edge, position, policies = [], onClose }) {
  const ref = useRef(null);

  // Close on click outside
  useEffect(() => {
    if (!edge) return;
    const handler = (e) => {
      if (ref.current && !ref.current.contains(e.target)) {
        onClose();
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [edge, onClose]);

  if (!edge) return null;

  const sourceName = typeof edge.source === 'object' ? edge.source.name : edge.source;
  const targetName = typeof edge.target === 'object' ? edge.target.name : edge.target;

  const isBlocked = edge.outcome === 'blocked';

  // Find matching policies for this edge pair
  const matchingPolicies = policies.filter((p) => {
    const srcMatch = p.source_agent_name === '*' || p.source_agent_name === sourceName;
    const dstMatch = p.dest_agent_name === '*' || p.dest_agent_name === targetName;
    return srcMatch && dstMatch;
  });

  const denyPolicies = matchingPolicies.filter((p) => p.action === 'deny');

  // Clamp position to viewport
  const popupWidth = 340;
  const popupHeight = 400;
  const left = Math.min(
    Math.max(position?.x ?? 0, 10),
    window.innerWidth - popupWidth - 10
  );
  const top = Math.min(
    Math.max((position?.y ?? 0) + 20, 10),
    window.innerHeight - popupHeight - 10
  );

  return (
    <div
      ref={ref}
      className="fixed bg-white rounded-lg shadow-xl border border-gray-200 z-50 p-4"
      style={{ left, top, width: popupWidth, maxHeight: popupHeight, overflow: 'auto' }}
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2 min-w-0">
          <h3 className="text-base font-semibold text-gray-900 truncate">
            {sourceName}
          </h3>
          <span className="text-gray-400 flex-shrink-0">&rarr;</span>
          <h3 className="text-base font-semibold text-gray-900 truncate">
            {targetName}
          </h3>
          <span className="flex-shrink-0 inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-600">
            {edge.count}
          </span>
        </div>
        <button
          onClick={onClose}
          className="text-gray-400 hover:text-gray-600 flex-shrink-0 ml-2"
        >
          <XMarkIcon className="h-5 w-5" />
        </button>
      </div>

      <div className="space-y-3 text-sm">
        {/* Status */}
        <div className="flex justify-between items-center">
          <span className="text-gray-500">Status</span>
          <StatusBadge status={isBlocked ? 'blocked' : 'active'} />
        </div>

        {/* Last interaction */}
        {edge.lastTimestamp && (
          <div className="border-t border-gray-100 pt-2">
            <div className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5">
              Last Interaction
            </div>
            <div className="space-y-1.5">
              <div className="flex justify-between">
                <span className="text-gray-500">Time</span>
                <span className="text-gray-700 text-xs">
                  {new Date(edge.lastTimestamp).toLocaleString()}
                </span>
              </div>
              {edge.lastMethod && (
                <div className="flex justify-between">
                  <span className="text-gray-500">Method</span>
                  <span className="text-gray-900 font-mono text-xs">{edge.lastMethod}</span>
                </div>
              )}
              {edge.lastDirection && (
                <div className="flex justify-between">
                  <span className="text-gray-500">Direction</span>
                  <span className="text-gray-900 text-xs">
                    {edge.lastDirection === 'outbound' ? sourceName + ' \u2192' : '\u2190 ' + sourceName}
                  </span>
                </div>
              )}
              {edge.lastDecision && (
                <div className="flex justify-between">
                  <span className="text-gray-500">Decision</span>
                  <StatusBadge status={edge.lastDecision} />
                </div>
              )}
              {edge.lastMessageHash && (
                <div className="flex justify-between">
                  <span className="text-gray-500">Message Hash</span>
                  <span className="text-gray-700 font-mono text-xs truncate max-w-[160px]" title={edge.lastMessageHash}>
                    {edge.lastMessageHash.substring(0, 16)}...
                  </span>
                </div>
              )}
              {edge.lastTaskId && (
                <div className="flex justify-between">
                  <span className="text-gray-500">Task ID</span>
                  <span className="text-gray-700 font-mono text-xs truncate max-w-[160px]" title={edge.lastTaskId}>
                    {edge.lastTaskId.substring(0, 16)}...
                  </span>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Transport */}
        <div className="border-t border-gray-100 pt-2">
          <div className="flex justify-between">
            <span className="text-gray-500">Transport</span>
            <span className="text-gray-900 text-xs">TLS 1.3</span>
          </div>
        </div>

        {/* Blocked by policy */}
        {isBlocked && denyPolicies.length > 0 && (
          <div className="border-t border-gray-100 pt-2">
            <div className="text-xs font-medium text-red-600 uppercase tracking-wide mb-1.5">
              Blocked by Policy
            </div>
            {denyPolicies.map((p, i) => (
              <div key={i} className="bg-red-50 border border-red-100 rounded p-2 mb-1 text-xs">
                <span className="font-medium text-red-800">
                  {p.source_agent_name} &rarr; {p.dest_agent_name}
                </span>
                <span className="text-red-600 ml-2">({p.action})</span>
                {p.priority != null && (
                  <span className="text-red-400 ml-1">priority {p.priority}</span>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Applicable policies */}
        {matchingPolicies.length > 0 && (
          <div className="border-t border-gray-100 pt-2">
            <div className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5">
              Applicable Policies
            </div>
            {matchingPolicies.map((p, i) => (
              <div key={i} className="flex items-center justify-between py-0.5 text-xs">
                <span className="text-gray-700">
                  {p.source_agent_name} &rarr; {p.dest_agent_name}
                </span>
                <span className={`font-medium ${p.action === 'deny' ? 'text-red-600' : 'text-green-600'}`}>
                  {p.action}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
