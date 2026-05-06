import { useQuery } from '@tanstack/react-query';
import { observability } from '../api/client';

export default function ToolObservatory() {
  const { data, isLoading } = useQuery({
    queryKey: ['tool-metrics'],
    queryFn: () => observability.tools.metrics({ hours: 24 }),
    refetchInterval: 30000,
  });

  const tools = data?.tools || [];

  return (
    <div className="p-6 h-full overflow-auto">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-gray-900">Tool Observatory</h2>
        <span className="text-sm text-gray-500">Last {data?.period_hours || 24} hours</span>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-12"><div className="spinner" /></div>
      ) : tools.length === 0 ? (
        <div className="text-center py-12 text-gray-500">No tool metrics available</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Tool</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Calls</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Errors</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Error Rate</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Agents Using</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {tools.map((t) => (
                <tr key={t.tool_id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 text-sm font-medium text-gray-900">{t.tool_name}</td>
                  <td className="px-4 py-3 text-sm text-right text-gray-700">{t.call_count}</td>
                  <td className="px-4 py-3 text-sm text-right text-gray-700">{t.error_count}</td>
                  <td className="px-4 py-3 text-sm text-right">
                    <span className={`font-mono ${t.error_rate > 0.1 ? 'text-red-600' : 'text-green-600'}`}>
                      {(t.error_rate * 100).toFixed(1)}%
                    </span>
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-600">
                    <div className="flex flex-wrap gap-1">
                      {t.agents_using.map((a) => (
                        <span key={a} className="inline-flex px-2 py-0.5 rounded text-xs bg-teal-50 text-teal-700">
                          {a}
                        </span>
                      ))}
                      {t.agents_using.length === 0 && <span className="text-gray-400">none</span>}
                    </div>
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
