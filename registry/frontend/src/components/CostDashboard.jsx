import { useCallback } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { observability } from '../api/client';
import useSocket from '../hooks/useSocket';

export default function CostDashboard() {
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ['cost-summary'],
    queryFn: () => observability.cost.summary(),
    refetchInterval: 30000,
  });

  // Live cost events
  useSocket('/mesh', useCallback((eventType) => {
    if (eventType === 'cost-event') {
      queryClient.invalidateQueries({ queryKey: ['cost-summary'] });
    }
  }, [queryClient]));

  const entries = data?.entries || [];

  // Group by agent
  const byAgent = {};
  for (const e of entries) {
    if (!byAgent[e.agent_name]) {
      byAgent[e.agent_name] = { models: [], total_cost: 0, total_input: 0, total_output: 0, total_requests: 0 };
    }
    byAgent[e.agent_name].models.push(e);
    byAgent[e.agent_name].total_cost += e.cost_usd;
    byAgent[e.agent_name].total_input += e.input_tokens;
    byAgent[e.agent_name].total_output += e.output_tokens;
    byAgent[e.agent_name].total_requests += e.request_count;
  }

  const formatCost = (usd) => {
    if (usd < 0.01) return `$${usd.toFixed(6)}`;
    if (usd < 1) return `$${usd.toFixed(4)}`;
    return `$${usd.toFixed(2)}`;
  };

  const formatTokens = (n) => {
    if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`;
    if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
    return n.toString();
  };

  return (
    <div className="p-6 h-full overflow-auto">
      <h2 className="text-lg font-semibold text-gray-900 mb-4">Cost Dashboard</h2>

      {isLoading ? (
        <div className="flex justify-center py-12"><div className="spinner" /></div>
      ) : entries.length === 0 ? (
        <div className="text-center py-12 text-gray-500">No cost data available</div>
      ) : (
        <>
          {/* Summary cards */}
          <div className="grid grid-cols-4 gap-4 mb-6">
            <div className="bg-white border border-gray-200 rounded-lg p-4">
              <div className="text-2xl font-bold text-gray-900">{formatCost(data?.total_cost_usd || 0)}</div>
              <div className="text-xs text-gray-500 mt-1">Total Cost</div>
            </div>
            <div className="bg-white border border-gray-200 rounded-lg p-4">
              <div className="text-2xl font-bold text-gray-900">{formatTokens(data?.total_input_tokens || 0)}</div>
              <div className="text-xs text-gray-500 mt-1">Input Tokens</div>
            </div>
            <div className="bg-white border border-gray-200 rounded-lg p-4">
              <div className="text-2xl font-bold text-gray-900">{formatTokens(data?.total_output_tokens || 0)}</div>
              <div className="text-xs text-gray-500 mt-1">Output Tokens</div>
            </div>
            <div className="bg-white border border-gray-200 rounded-lg p-4">
              <div className="text-2xl font-bold text-gray-900">{data?.total_requests || 0}</div>
              <div className="text-xs text-gray-500 mt-1">Total Requests</div>
            </div>
          </div>

          {/* Per-agent breakdown */}
          <h3 className="text-sm font-semibold text-gray-700 mb-3">By Agent</h3>
          <div className="space-y-3">
            {Object.entries(byAgent)
              .sort(([, a], [, b]) => b.total_cost - a.total_cost)
              .map(([agent, info]) => (
                <div key={agent} className="bg-white border border-gray-200 rounded-lg p-4">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-medium text-gray-900">{agent}</span>
                    <span className="text-sm font-mono font-semibold text-gray-900">
                      {formatCost(info.total_cost)}
                    </span>
                  </div>
                  <div className="flex gap-4 text-xs text-gray-500 mb-2">
                    <span>{formatTokens(info.total_input)} in</span>
                    <span>{formatTokens(info.total_output)} out</span>
                    <span>{info.total_requests} reqs</span>
                  </div>
                  {info.models.length > 1 && (
                    <div className="mt-2 space-y-1">
                      {info.models.map((m) => (
                        <div key={m.model_name} className="flex justify-between text-xs text-gray-600">
                          <span className="font-mono">{m.model_name}</span>
                          <span>{formatCost(m.cost_usd)} ({m.request_count} reqs)</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
          </div>
        </>
      )}
    </div>
  );
}
