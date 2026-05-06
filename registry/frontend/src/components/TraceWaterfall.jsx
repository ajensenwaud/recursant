import { useQuery } from '@tanstack/react-query';
import { observability } from '../api/client';
import { format } from 'date-fns';
import { useState } from 'react';

const DECISION_COLOURS = {
  allow: 'bg-green-100 text-green-800',
  block: 'bg-red-100 text-red-800',
  pass: 'bg-green-100 text-green-800',
  modify: 'bg-amber-100 text-amber-800',
  redact: 'bg-purple-100 text-purple-800',
  warn: 'bg-yellow-100 text-yellow-800',
};

const OUTCOME_COLOURS = {
  success: 'bg-green-100 text-green-800',
  allowed: 'bg-green-100 text-green-800',
  blocked: 'bg-red-100 text-red-800',
  error: 'bg-red-100 text-red-800',
};

export default function TraceWaterfall({ taskId, onClose }) {
  const [expandedHop, setExpandedHop] = useState(null);

  const { data, isLoading, error } = useQuery({
    queryKey: ['trace', taskId],
    queryFn: () => observability.traces.get(taskId),
    enabled: !!taskId,
  });

  if (!taskId) return null;

  const hops = data?.hops || [];
  const maxLatency = Math.max(...hops.map(h => h.latency_ms || 0), 1);

  return (
    <div className="h-full flex flex-col bg-white">
      {/* Header */}
      <div className="border-b border-gray-200 px-6 py-4 flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-gray-900">Trace Waterfall</h3>
          <div className="text-sm text-gray-500 font-mono mt-1">{taskId}</div>
        </div>
        <div className="flex items-center gap-4">
          {data && (
            <div className="flex gap-4 text-sm text-gray-600">
              <span>{data.agent_count} agents</span>
              <span>{hops.length} hops</span>
              <span className="font-mono">{data.total_duration_ms?.toFixed(1)}ms total</span>
              {data.status && (
                <span className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${OUTCOME_COLOURS[data.status] || 'bg-gray-100 text-gray-800'}`}>
                  {data.status}
                </span>
              )}
            </div>
          )}
          {onClose && (
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none">
              &times;
            </button>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto p-6">
        {isLoading ? (
          <div className="flex justify-center py-12"><div className="spinner" /></div>
        ) : error ? (
          <div className="text-center py-12 text-red-500">Failed to load trace</div>
        ) : hops.length === 0 ? (
          <div className="text-center py-12 text-gray-500">No hops found for this trace</div>
        ) : (
          <div className="space-y-1">
            {hops.map((hop, idx) => {
              const barWidth = maxLatency > 0 ? Math.max((hop.latency_ms / maxLatency) * 100, 2) : 2;
              const isExpanded = expandedHop === idx;

              return (
                <div key={hop.id || idx}>
                  <div
                    className="flex items-center gap-3 py-2 px-3 rounded hover:bg-gray-50 cursor-pointer"
                    onClick={() => setExpandedHop(isExpanded ? null : idx)}
                  >
                    {/* Hop index */}
                    <span className="text-xs text-gray-400 w-6 text-right font-mono">{idx}</span>

                    {/* Source -> Dest */}
                    <div className="w-56 flex-shrink-0">
                      <span className="text-sm text-teal-700 font-medium">{hop.source_agent_name || '?'}</span>
                      <span className="text-gray-400 mx-1">&rarr;</span>
                      <span className="text-sm text-gray-700">{hop.dest_agent_name || '?'}</span>
                    </div>

                    {/* Method */}
                    <span className="text-xs text-gray-500 w-24 truncate">{hop.a2a_method}</span>

                    {/* Decision badge */}
                    <span className={`inline-flex px-1.5 py-0.5 rounded text-xs font-medium w-16 justify-center ${DECISION_COLOURS[hop.decision] || 'bg-gray-100 text-gray-800'}`}>
                      {hop.decision}
                    </span>

                    {/* Outcome badge */}
                    <span className={`inline-flex px-1.5 py-0.5 rounded text-xs font-medium w-16 justify-center ${OUTCOME_COLOURS[hop.outcome] || 'bg-gray-100 text-gray-800'}`}>
                      {hop.outcome}
                    </span>

                    {/* Waterfall bar */}
                    <div className="flex-1 flex items-center gap-2">
                      <div className="flex-1 bg-gray-100 rounded h-4 relative">
                        <div
                          className={`h-full rounded ${hop.decision === 'block' || hop.outcome === 'blocked' ? 'bg-red-400' : 'bg-teal-400'}`}
                          style={{ width: `${barWidth}%` }}
                        />
                      </div>
                      <span className="text-xs text-gray-500 font-mono w-16 text-right">
                        {hop.latency_ms ? `${hop.latency_ms.toFixed(1)}ms` : '-'}
                      </span>
                    </div>

                    {/* CoT indicator */}
                    {hop.cot_analysis && (
                      <span className={`text-xs px-1.5 py-0.5 rounded ${
                        hop.cot_risk_level === 'high' ? 'bg-red-100 text-red-700' :
                        hop.cot_risk_level === 'medium' ? 'bg-amber-100 text-amber-700' :
                        'bg-blue-100 text-blue-700'
                      }`}>
                        CoT
                      </span>
                    )}
                  </div>

                  {/* Expanded details */}
                  {isExpanded && (
                    <div className="ml-9 mr-4 mb-2 p-3 bg-gray-50 rounded border border-gray-200 text-xs">
                      <div className="grid grid-cols-2 gap-2 mb-2">
                        <div><span className="text-gray-500">Timestamp:</span> {hop.timestamp ? format(new Date(hop.timestamp), 'HH:mm:ss.SSS') : '-'}</div>
                        <div><span className="text-gray-500">Direction:</span> {hop.direction}</div>
                        <div><span className="text-gray-500">Sidecar:</span> {hop.sidecar_id || '-'}</div>
                        <div><span className="text-gray-500">Latency:</span> {hop.latency_ms ? `${hop.latency_ms.toFixed(1)}ms` : '-'}</div>
                      </div>

                      {hop.details && (
                        <div className="mb-2">
                          <div className="text-gray-500 mb-1">Details:</div>
                          <pre className="bg-white border border-gray-200 rounded p-2 overflow-x-auto max-h-32 text-xs">
                            {JSON.stringify(hop.details, null, 2)}
                          </pre>
                        </div>
                      )}

                      {hop.cot_analysis && (
                        <div>
                          <div className="text-gray-500 mb-1">Chain-of-Thought Analysis:</div>
                          <pre className="bg-white border border-gray-200 rounded p-2 overflow-x-auto max-h-48 text-xs">
                            {typeof hop.cot_analysis === 'string' ? hop.cot_analysis : JSON.stringify(hop.cot_analysis, null, 2)}
                          </pre>
                          {hop.cot_risk_level && (
                            <div className="mt-1">
                              <span className="text-gray-500">Risk Level: </span>
                              <span className={`font-medium ${
                                hop.cot_risk_level === 'high' ? 'text-red-600' :
                                hop.cot_risk_level === 'medium' ? 'text-amber-600' :
                                'text-green-600'
                              }`}>
                                {hop.cot_risk_level}
                              </span>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
