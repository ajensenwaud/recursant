import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { format } from 'date-fns';
import { XMarkIcon } from '@heroicons/react/24/outline';
import { meshTools } from '../api/client';

function RevokeModal({ tool, onClose, onSubmit }) {
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
          <h2 className="text-lg font-medium text-gray-900 mb-4">Revoke Tool</h2>
          <p className="text-sm text-gray-500 mb-4">
            You are about to revoke <strong>{tool.name}</strong>. This will prevent agents from using it.
          </p>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700">Justification (required)</label>
              <textarea
                value={justification}
                onChange={(e) => setJustification(e.target.value)}
                required
                rows={4}
                placeholder="Enter your justification..."
                className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-teal-500 focus:border-teal-500"
              />
            </div>
            <div className="flex justify-end gap-3 pt-4">
              <button type="button" onClick={onClose} className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50">Cancel</button>
              <button type="submit" disabled={submitting} className="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-md hover:bg-red-700 disabled:opacity-50">
                {submitting ? 'Revoking...' : 'Revoke'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

export default function ApprovedTools() {
  const [revokeTarget, setRevokeTarget] = useState(null);
  const queryClient = useQueryClient();

  const { data, isLoading, error } = useQuery({
    queryKey: ['approved-tools'],
    queryFn: () => meshTools.list({ status: 'approved' }),
  });

  const revokeMutation = useMutation({
    mutationFn: ({ id, justification }) => meshTools.revoke(id, { justification }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['approved-tools'] });
      queryClient.invalidateQueries({ queryKey: ['submitted-tools'] });
    },
  });

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
        Failed to load approved tools: {error.message}
      </div>
    );
  }

  const tools = data?.tools || [];

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">Approved Tools</h1>

      {tools.length === 0 ? (
        <div className="bg-white shadow rounded-lg p-8 text-center text-gray-500">
          No approved tools
        </div>
      ) : (
        <div className="bg-white shadow rounded-lg overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Name</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">MCP Server</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Endpoint URL</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Approved By</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Approved At</th>
                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {tools.map((tool) => (
                <tr key={tool.id} className="hover:bg-gray-50">
                  <td className="px-6 py-4 whitespace-nowrap">
                    <Link to={`/mesh-tools/${tool.id}`} className="text-teal-600 hover:text-teal-800 font-medium">
                      {tool.name}
                    </Link>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {tool.mcp_server_name || '-'}
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-500 max-w-xs truncate" title={tool.endpoint_url}>
                    {tool.endpoint_url}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {tool.approved_by || '-'}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {tool.approved_at ? format(new Date(tool.approved_at), 'MMM d, yyyy HH:mm') : '-'}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right">
                    <button
                      onClick={() => setRevokeTarget(tool)}
                      className="inline-flex items-center gap-1 px-3 py-1.5 text-sm font-medium text-white bg-red-600 rounded-md hover:bg-red-700"
                    >
                      <XMarkIcon className="h-4 w-4" />
                      Revoke
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {revokeTarget && (
        <RevokeModal
          tool={revokeTarget}
          onClose={() => setRevokeTarget(null)}
          onSubmit={async (justification) => {
            await revokeMutation.mutateAsync({ id: revokeTarget.id, justification });
            setRevokeTarget(null);
          }}
        />
      )}
    </div>
  );
}
