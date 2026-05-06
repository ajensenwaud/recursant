import { useEffect, useRef } from 'react';
import { XMarkIcon } from '@heroicons/react/24/outline';
import StatusBadge from './StatusBadge';

/**
 * Tool detail popup — appears when clicking a tool node in the mesh graph.
 */
export default function ToolDetailPopup({ tool, position, onClose }) {
  const ref = useRef(null);

  useEffect(() => {
    if (!tool) return;
    const handler = (e) => {
      if (ref.current && !ref.current.contains(e.target)) onClose();
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [tool, onClose]);

  if (!tool) return null;

  const popupWidth = 320;
  const popupHeight = 420;
  const left = Math.min(Math.max(position?.x ?? 0, 10), window.innerWidth - popupWidth - 10);
  const top = Math.min(Math.max((position?.y ?? 0) + 20, 10), window.innerHeight - popupHeight - 10);

  return (
    <div
      ref={ref}
      className="fixed bg-white rounded-lg shadow-xl border border-gray-200 z-50 p-4"
      style={{ left, top, width: popupWidth, maxHeight: popupHeight, overflow: 'auto' }}
    >
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-base font-semibold text-gray-900 truncate pr-2">{tool.name}</h3>
        <button onClick={onClose} className="text-gray-400 hover:text-gray-600 flex-shrink-0">
          <XMarkIcon className="h-5 w-5" />
        </button>
      </div>

      <div className="space-y-2 text-sm">
        <div className="flex justify-between">
          <span className="text-gray-500">Status</span>
          <StatusBadge status={tool.status || 'unknown'} />
        </div>

        {tool.description && (
          <div>
            <span className="text-gray-500">Description</span>
            <p className="text-gray-700 text-xs mt-0.5">{tool.description}</p>
          </div>
        )}

        {tool.mcpServerName && (
          <div className="border-t border-gray-100 pt-2">
            <div className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5">MCP Server</div>
            <div className="space-y-1">
              <div className="flex justify-between">
                <span className="text-gray-500">Name</span>
                <span className="text-gray-900">{tool.mcpServerName}</span>
              </div>
              {tool.mcpServerDescription && (
                <div>
                  <span className="text-gray-500">Description</span>
                  <p className="text-gray-700 text-xs mt-0.5">{tool.mcpServerDescription}</p>
                </div>
              )}
              {tool.mcpServerUrl && (
                <div>
                  <span className="text-gray-500">SSE URL</span>
                  <p className="text-gray-700 text-xs mt-0.5 break-all font-mono">{tool.mcpServerUrl}</p>
                </div>
              )}
            </div>
          </div>
        )}

        {tool.backendServices && tool.backendServices.length > 0 && (
          <div className="border-t border-gray-100 pt-2">
            <div className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5">Backend Services</div>
            {tool.backendServices.map((svc, i) => (
              <div key={i} className="text-xs text-gray-700 mb-1">
                <span className="font-mono">{svc.method}</span> {svc.description || svc.url}
              </div>
            ))}
          </div>
        )}

        {tool.approvedBy && (
          <div className="flex justify-between">
            <span className="text-gray-500">Approved By</span>
            <span className="text-gray-900 text-xs">{tool.approvedBy}</span>
          </div>
        )}

        {tool.approvedAt && (
          <div className="flex justify-between">
            <span className="text-gray-500">Approved At</span>
            <span className="text-gray-700 text-xs">{new Date(tool.approvedAt).toLocaleString()}</span>
          </div>
        )}

        {tool.assignedAgents && tool.assignedAgents.length > 0 && (
          <div className="border-t border-gray-100 pt-2">
            <div className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5">Assigned Agents</div>
            <div className="flex flex-wrap gap-1">
              {tool.assignedAgents.map((a, i) => (
                <span key={i} className="inline-block px-2 py-0.5 text-xs bg-amber-50 text-amber-700 rounded">
                  {a}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
