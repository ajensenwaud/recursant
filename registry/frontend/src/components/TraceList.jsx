import { useState, useCallback, useRef } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { observability } from '../api/client';
import { format } from 'date-fns';
import useSocket from '../hooks/useSocket';
import TraceWaterfall from './TraceWaterfall';

const MAX_LIVE_TRACES = 200;

export default function TraceList() {
  const [page, setPage] = useState(1);
  const [agentFilter, setAgentFilter] = useState('');
  const [selectedTaskId, setSelectedTaskId] = useState(null);
  const [live, setLive] = useState(true);

  // Accumulates live trace summaries from WebSocket events.
  // Key: task_id -> { task_id, hop_count, start_time, end_time, duration_ms, agents }
  const liveTracesRef = useRef(new Map());
  const [liveTraces, setLiveTraces] = useState([]);

  const queryClient = useQueryClient();

  // Initial REST fetch (page 1 seeds historical data)
  const { data, isLoading } = useQuery({
    queryKey: ['traces', page, agentFilter],
    queryFn: () => observability.traces.list({
      page,
      per_page: 50,
      ...(agentFilter ? { agent_name: agentFilter } : {}),
    }),
    keepPreviousData: true,
  });

  // WebSocket: accumulate audit events into trace summaries
  useSocket('/mesh', useCallback((eventType, eventData) => {
    if (eventType !== 'audit') return;
    const taskId = eventData.task_id;
    if (!taskId) return;

    const map = liveTracesRef.current;
    const ts = eventData.timestamp || new Date().toISOString();
    const existing = map.get(taskId);

    if (existing) {
      existing.hop_count += 1;
      existing.end_time = ts;
      const start = new Date(existing.start_time).getTime();
      const end = new Date(ts).getTime();
      existing.duration_ms = end - start;
      // Track agents involved
      if (eventData.source_agent_name) existing.agents.add(eventData.source_agent_name);
      if (eventData.dest_agent_name) existing.agents.add(eventData.dest_agent_name);
      existing.has_cot = existing.has_cot || !!(eventData.details?.cot_analysis);
      existing.has_error = existing.has_error || eventData.outcome === 'error' || eventData.outcome === 'blocked';
    } else {
      map.set(taskId, {
        task_id: taskId,
        hop_count: 1,
        start_time: ts,
        end_time: ts,
        duration_ms: 0,
        agents: new Set([eventData.source_agent_name, eventData.dest_agent_name].filter(Boolean)),
        has_cot: !!(eventData.details?.cot_analysis),
        has_error: eventData.outcome === 'error' || eventData.outcome === 'blocked',
      });

      // Cap size: remove oldest entries
      if (map.size > MAX_LIVE_TRACES) {
        const firstKey = map.keys().next().value;
        map.delete(firstKey);
      }
    }

    // Convert map to sorted array (newest first)
    const arr = Array.from(map.values())
      .sort((a, b) => new Date(b.start_time) - new Date(a.start_time));
    setLiveTraces(arr);
  }, []));

  const restTraces = data?.traces || [];
  const total = data?.total || 0;
  const totalPages = Math.ceil(total / 50);

  // On page 1 with live mode, merge live traces on top of REST data
  const displayTraces = (live && page === 1)
    ? deduplicateTraces(liveTraces, restTraces)
    : restTraces;

  // Filter by agent if needed (live traces need client-side filtering)
  const filteredTraces = agentFilter
    ? displayTraces.filter(t =>
        t.agents
          ? [...t.agents].some(a => a.toLowerCase().includes(agentFilter.toLowerCase()))
          : true // REST traces don't have agents set, rely on server filter
      )
    : displayTraces;

  if (selectedTaskId) {
    return (
      <TraceWaterfall
        taskId={selectedTaskId}
        onClose={() => setSelectedTaskId(null)}
      />
    );
  }

  return (
    <div className="p-6 h-full overflow-auto">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold text-gray-900">Request Traces</h2>
          {live && liveTraces.length > 0 && (
            <span className="flex items-center gap-1.5 text-xs text-teal-600 bg-teal-50 border border-teal-200 rounded-full px-2 py-0.5">
              <span className="w-1.5 h-1.5 rounded-full bg-teal-500 animate-pulse" />
              {liveTraces.length} live
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setLive(l => !l)}
            className={`text-xs border rounded px-2 py-1 transition-colors ${
              live
                ? 'bg-teal-50 border-teal-300 text-teal-700'
                : 'bg-white border-gray-300 text-gray-600 hover:bg-gray-50'
            }`}
          >
            {live ? 'Live' : 'Paused'}
          </button>
          <input
            type="text"
            placeholder="Filter by agent name..."
            value={agentFilter}
            onChange={(e) => { setAgentFilter(e.target.value); setPage(1); }}
            className="border border-gray-300 rounded-md px-3 py-1.5 text-sm w-64"
          />
        </div>
      </div>

      {isLoading && liveTraces.length === 0 ? (
        <div className="flex justify-center py-12"><div className="spinner" /></div>
      ) : filteredTraces.length === 0 ? (
        <div className="text-center py-12 text-gray-500">No traces found</div>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Task ID</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Hops</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Duration</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Start</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {filteredTraces.map((trace) => (
                  <tr
                    key={trace.task_id}
                    className="hover:bg-gray-50 cursor-pointer"
                    onClick={() => setSelectedTaskId(trace.task_id)}
                  >
                    <td className="px-4 py-3 text-sm font-mono text-teal-700 truncate max-w-[200px]">
                      {trace.task_id}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-700">{trace.hop_count}</td>
                    <td className="px-4 py-3 text-sm text-gray-700">
                      {trace.duration_ms != null ? `${Number(trace.duration_ms).toFixed(1)}ms` : '-'}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-500">
                      {trace.start_time ? format(new Date(trace.start_time), 'MMM d HH:mm:ss') : '-'}
                    </td>
                    <td className="px-4 py-3 text-sm">
                      <span className="flex items-center gap-1.5">
                        {trace.has_error && (
                          <span className="inline-block w-2 h-2 rounded-full bg-red-500" title="Has errors" />
                        )}
                        {trace.has_cot && (
                          <span className="text-xs text-purple-600 bg-purple-50 border border-purple-200 rounded px-1.5 py-0.5" title="Chain-of-thought analysis">
                            CoT
                          </span>
                        )}
                        {!trace.has_error && !trace.has_cot && (
                          <span className="inline-block w-2 h-2 rounded-full bg-green-500" title="OK" />
                        )}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div className="flex items-center justify-between mt-4">
              <span className="text-sm text-gray-500">{total} total traces</span>
              <div className="flex gap-2">
                <button
                  onClick={() => setPage(p => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className="px-3 py-1 text-sm border rounded disabled:opacity-50"
                >
                  Previous
                </button>
                <span className="px-3 py-1 text-sm text-gray-600">
                  Page {page} of {totalPages}
                </span>
                <button
                  onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                  disabled={page === totalPages}
                  className="px-3 py-1 text-sm border rounded disabled:opacity-50"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

/**
 * Merge live WebSocket traces with REST traces, deduplicating by task_id.
 * Live traces take priority (they have more up-to-date hop counts).
 */
function deduplicateTraces(live, rest) {
  const seen = new Set();
  const result = [];
  for (const t of live) {
    seen.add(t.task_id);
    result.push(t);
  }
  for (const t of rest) {
    if (!seen.has(t.task_id)) {
      seen.add(t.task_id);
      result.push(t);
    }
  }
  return result;
}
