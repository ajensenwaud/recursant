import { useState } from 'react';
import { ChevronRightIcon, ChevronLeftIcon } from '@heroicons/react/24/outline';

/**
 * Right-hand sidebar showing a scrollable log of mesh interactions.
 *
 * Props:
 * - events: array of { timestamp, source, dest, method, outcome }
 */
export default function EventLog({ events }) {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div
      className={`flex-shrink-0 border-l border-gray-200 bg-white transition-all duration-200 ${
        collapsed ? 'w-10' : 'w-80'
      }`}
    >
      {/* Toggle button */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="w-full flex items-center justify-center py-2 text-gray-400 hover:text-gray-600 border-b border-gray-200"
        title={collapsed ? 'Show event log' : 'Hide event log'}
      >
        {collapsed ? (
          <ChevronLeftIcon className="h-4 w-4" />
        ) : (
          <ChevronRightIcon className="h-4 w-4" />
        )}
      </button>

      {!collapsed && (
        <>
          <div className="px-3 py-2 border-b border-gray-200">
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
              Interaction Log
            </h3>
            <span className="text-xs text-gray-400">{events.length} events</span>
          </div>

          <div className="overflow-y-auto" style={{ maxHeight: 'calc(100vh - 12rem)' }}>
            {events.length === 0 ? (
              <p className="px-3 py-4 text-sm text-gray-400 text-center">
                No interactions yet
              </p>
            ) : (
              <ul className="divide-y divide-gray-100">
                {events.map((evt, i) => (
                  <li key={i} className="px-3 py-2">
                    <div className="flex items-center justify-between mb-0.5">
                      <span className="text-xs text-gray-400">
                        {formatTime(evt.timestamp)}
                      </span>
                      <span
                        className={`inline-block px-1.5 py-0.5 text-xs rounded font-medium ${
                          evt.outcome === 'blocked'
                            ? 'bg-red-50 text-red-600'
                            : 'bg-green-50 text-green-600'
                        }`}
                      >
                        {evt.outcome}
                      </span>
                    </div>
                    <p className="text-sm text-gray-800 truncate">
                      <span className="font-medium">{evt.source}</span>
                      <span className="text-gray-400 mx-1">&rarr;</span>
                      <span className="font-medium">{evt.dest}</span>
                    </p>
                    <p className="text-xs text-gray-400 truncate">{evt.method}</p>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </div>
  );
}

function formatTime(ts) {
  if (!ts) return '';
  try {
    const d = new Date(ts);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch {
    return String(ts);
  }
}
