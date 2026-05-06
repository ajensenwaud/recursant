import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { format } from 'date-fns';
import { NoSymbolIcon } from '@heroicons/react/24/outline';
import { activeAgents } from '../api/client';
import StatusBadge from '../components/StatusBadge';

function RevokeModal({ agent, onClose, onSubmit }) {
  const [justification, setJustification] = useState('');
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!justification.trim()) {
      alert('Justification is required');
      return;
    }
    setSubmitting(true);
    try {
      await onSubmit(justification);
      onClose();
    } catch (error) {
      alert(error.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="flex items-center justify-center min-h-screen p-4">
        <div className="fixed inset-0 bg-black bg-opacity-25" onClick={onClose} />
        <div className="relative bg-white rounded-lg shadow-xl max-w-md w-full p-6">
          <h2 className="text-lg font-medium text-gray-900 mb-4">
            Revoke Agent
          </h2>

          <p className="text-sm text-gray-500 mb-4">
            You are about to suspend <strong>{agent.name}</strong>. This will
            remove it from the active registry. Please provide a justification.
          </p>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700">
                Justification (required)
              </label>
              <textarea
                value={justification}
                onChange={(e) => setJustification(e.target.value)}
                required
                rows={4}
                placeholder="Reason for revoking this agent..."
                className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-red-500 focus:border-red-500"
              />
            </div>

            <div className="flex justify-end gap-3 pt-4">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={submitting}
                className="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-md hover:bg-red-700 disabled:opacity-50"
              >
                {submitting ? 'Suspending...' : 'Revoke'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

export default function ActiveAgents() {
  const [revokeAgent, setRevokeAgent] = useState(null);
  const queryClient = useQueryClient();

  const { data, isLoading, error } = useQuery({
    queryKey: ['active-agents'],
    queryFn: () => activeAgents.list(),
  });

  const suspendMutation = useMutation({
    mutationFn: ({ agentId, justification }) =>
      activeAgents.suspend(agentId, { justification }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['active-agents'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard-stats'] });
    },
  });

  async function handleRevoke(justification) {
    await suspendMutation.mutateAsync({
      agentId: revokeAgent.id,
      justification,
    });
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="spinner" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-md">
        Failed to load active agents: {error.message}
      </div>
    );
  }

  const agents = data?.agents || [];

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">Active Agents</h1>

      {agents.length === 0 ? (
        <div className="bg-white shadow rounded-lg p-8 text-center text-gray-500">
          No active or approved agents
        </div>
      ) : (
        <div className="bg-white shadow rounded-lg overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Agent
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  UUID
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Endpoint
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Risk Tier
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Owner
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Status
                </th>
                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {agents.map((agent) => (
                <tr key={agent.id} className="hover:bg-gray-50">
                  <td className="px-6 py-4 whitespace-nowrap">
                    <Link
                      to={`/submissions/${agent.id}`}
                      className="text-teal-600 hover:text-teal-800 font-medium"
                    >
                      {agent.name}
                    </Link>
                    <p className="text-xs text-gray-500">v{agent.version}</p>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <code className="text-xs text-gray-500 bg-gray-100 px-1.5 py-0.5 rounded">
                      {agent.id.slice(0, 8)}...
                    </code>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className="text-sm text-gray-700 truncate block max-w-xs" title={agent.endpoint_url}>
                      {agent.endpoint_url}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className="capitalize text-sm text-gray-900">
                      {agent.risk_tier}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {agent.owner_id}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <StatusBadge status={agent.status} />
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right">
                    <button
                      onClick={() => setRevokeAgent(agent)}
                      className="inline-flex items-center gap-1 px-3 py-1.5 text-sm font-medium text-white bg-red-600 rounded-md hover:bg-red-700"
                    >
                      <NoSymbolIcon className="h-4 w-4" />
                      Revoke
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {revokeAgent && (
        <RevokeModal
          agent={revokeAgent}
          onClose={() => setRevokeAgent(null)}
          onSubmit={handleRevoke}
        />
      )}
    </div>
  );
}
