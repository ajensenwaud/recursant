import { useState, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { observability } from '../api/client';
import useSocket from '../hooks/useSocket';
import { format } from 'date-fns';

export default function SecurityCenter() {
  const queryClient = useQueryClient();
  const [showResolved, setShowResolved] = useState(false);

  const { data: postureData, isLoading: postureLoading } = useQuery({
    queryKey: ['security-posture'],
    queryFn: () => observability.security.posture(),
    refetchInterval: 30000,
  });

  const { data: alertData, isLoading: alertsLoading } = useQuery({
    queryKey: ['alerts', showResolved],
    queryFn: () => observability.alerts.list({
      include_resolved: showResolved,
      limit: 100,
    }),
    refetchInterval: 10000,
  });

  const acknowledgeMut = useMutation({
    mutationFn: (id) => observability.alerts.acknowledge(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['alerts'] }),
  });

  const resolveMut = useMutation({
    mutationFn: (id) => observability.alerts.resolve(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['alerts'] }),
  });

  // Live alert events
  useSocket('/mesh', useCallback((eventType) => {
    if (eventType === 'alert') {
      queryClient.invalidateQueries({ queryKey: ['alerts'] });
      queryClient.invalidateQueries({ queryKey: ['security-posture'] });
    }
  }, [queryClient]));

  const posture = postureData;
  const alerts = alertData?.alerts || [];

  const scoreColour = (score) => {
    if (score >= 80) return 'text-green-600';
    if (score >= 60) return 'text-amber-600';
    return 'text-red-600';
  };

  const severityColour = (severity) => {
    switch (severity) {
      case 'critical': return 'bg-red-100 text-red-800';
      case 'high': return 'bg-orange-100 text-orange-800';
      case 'medium': return 'bg-amber-100 text-amber-800';
      case 'low': return 'bg-blue-100 text-blue-800';
      default: return 'bg-gray-100 text-gray-800';
    }
  };

  return (
    <div className="p-6 h-full overflow-auto">
      {/* Security posture score */}
      <div className="mb-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Security Posture</h2>
        {postureLoading ? (
          <div className="flex justify-center py-8"><div className="spinner" /></div>
        ) : posture ? (
          <div className="grid grid-cols-6 gap-4">
            <div className="col-span-1 bg-white border border-gray-200 rounded-lg p-4 text-center">
              <div className={`text-3xl font-bold ${scoreColour(posture.composite_score)}`}>
                {posture.composite_score}
              </div>
              <div className="text-xs text-gray-500 mt-1">Composite Score</div>
            </div>
            {posture.components && Object.entries(posture.components).map(([key, value]) => (
              <div key={key} className="bg-white border border-gray-200 rounded-lg p-4 text-center">
                <div className={`text-xl font-semibold ${scoreColour(value)}`}>
                  {value}
                </div>
                <div className="text-xs text-gray-500 mt-1">
                  {key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                </div>
              </div>
            ))}
          </div>
        ) : null}
      </div>

      {/* Alert feed */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900">Alerts</h2>
          <label className="flex items-center gap-2 text-sm text-gray-600">
            <input
              type="checkbox"
              checked={showResolved}
              onChange={(e) => setShowResolved(e.target.checked)}
              className="rounded border-gray-300"
            />
            Show resolved
          </label>
        </div>

        {alertsLoading ? (
          <div className="flex justify-center py-8"><div className="spinner" /></div>
        ) : alerts.length === 0 ? (
          <div className="text-center py-8 text-gray-500">No alerts</div>
        ) : (
          <div className="space-y-2">
            {alerts.map((alert) => (
              <div
                key={alert.id}
                className={`border rounded-lg p-4 ${alert.resolved_at ? 'bg-gray-50 border-gray-200' : 'bg-white border-gray-300'}`}
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${severityColour(alert.severity)}`}>
                        {alert.severity}
                      </span>
                      <span className="text-xs text-gray-500">{alert.anomaly_type}</span>
                      {alert.agent_name && (
                        <span className="text-xs text-teal-700 font-medium">{alert.agent_name}</span>
                      )}
                    </div>
                    <p className="text-sm text-gray-800">{alert.description}</p>
                    <div className="text-xs text-gray-400 mt-1">
                      {alert.detected_at ? format(new Date(alert.detected_at), 'MMM d HH:mm:ss') : ''}
                      {alert.resolved_at && (
                        <span className="ml-2 text-green-600">
                          Resolved {format(new Date(alert.resolved_at), 'MMM d HH:mm:ss')}
                        </span>
                      )}
                    </div>
                  </div>
                  {!alert.resolved_at && (
                    <div className="flex gap-2 ml-4">
                      {!alert.is_acknowledged && (
                        <button
                          onClick={() => acknowledgeMut.mutate(alert.id)}
                          className="px-2 py-1 text-xs border border-gray-300 rounded hover:bg-gray-50"
                        >
                          Acknowledge
                        </button>
                      )}
                      <button
                        onClick={() => resolveMut.mutate(alert.id)}
                        className="px-2 py-1 text-xs border border-green-300 text-green-700 rounded hover:bg-green-50"
                      >
                        Resolve
                      </button>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
