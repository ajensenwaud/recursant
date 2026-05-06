import { useQuery } from '@tanstack/react-query';
import { observability } from '../api/client';

export default function GuardrailEffectiveness() {
  const { data, isLoading } = useQuery({
    queryKey: ['guardrail-effectiveness'],
    queryFn: () => observability.tools.effectiveness({ hours: 24 }),
    refetchInterval: 30000,
  });

  const guardrails = data?.guardrails || [];

  return (
    <div className="p-6 h-full overflow-auto">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-gray-900">Guardrail Effectiveness</h2>
        <span className="text-sm text-gray-500">Last 24 hours</span>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-12"><div className="spinner" /></div>
      ) : guardrails.length === 0 ? (
        <div className="text-center py-12 text-gray-500">No guardrail data available</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Guardrail</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Type</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Mechanism</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Total Events</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Blocked</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Block Rate</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">FP Count</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">FP Rate</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {guardrails.map((g) => (
                <tr key={g.guardrail_id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 text-sm font-medium text-gray-900">{g.guardrail_name}</td>
                  <td className="px-4 py-3 text-sm text-gray-600">{g.guardrail_type}</td>
                  <td className="px-4 py-3 text-sm">
                    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-700">
                      {g.mechanism}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-sm text-right text-gray-700">{g.total_events}</td>
                  <td className="px-4 py-3 text-sm text-right text-gray-700">{g.blocked_events}</td>
                  <td className="px-4 py-3 text-sm text-right">
                    <span className={`font-mono ${g.block_rate > 0.5 ? 'text-red-600' : g.block_rate > 0.2 ? 'text-amber-600' : 'text-green-600'}`}>
                      {(g.block_rate * 100).toFixed(1)}%
                    </span>
                  </td>
                  <td className="px-4 py-3 text-sm text-right text-gray-700">{g.false_positive_count}</td>
                  <td className="px-4 py-3 text-sm text-right font-mono text-gray-600">
                    {(g.false_positive_rate * 100).toFixed(1)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
