import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { format } from 'date-fns';
import { PlusIcon } from '@heroicons/react/24/outline';
import { guardrails } from '../api/client';
import GuardrailModal from '../components/GuardrailModal';

const STATUS_BADGES = {
  draft: 'bg-gray-100 text-gray-800',
  active: 'bg-green-100 text-green-800',
  disabled: 'bg-red-100 text-red-800',
};

const TYPE_LABELS = {
  pre_processing: 'Pre-processing',
  post_processing: 'Post-processing',
  structural: 'Structural',
};

const MECHANISM_LABELS = {
  regex: 'Regex',
  vector_lookup: 'Vector Lookup',
  llm_judge: 'LLM Judge',
  ml_classifier: 'ML Classifier',
};

export default function Guardrails() {
  const [showModal, setShowModal] = useState(false);
  const [typeFilter, setTypeFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const queryClient = useQueryClient();

  const { data, isLoading, error } = useQuery({
    queryKey: ['guardrails', typeFilter, statusFilter],
    queryFn: () => guardrails.list({ type: typeFilter || undefined, status: statusFilter || undefined }),
  });

  const createMutation = useMutation({
    mutationFn: (data) => guardrails.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['guardrails'] });
      setShowModal(false);
    },
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-teal-600" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4">
        <p className="text-red-800">Failed to load guardrails: {error.message}</p>
      </div>
    );
  }

  const items = data?.guardrails || [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-gray-900">Guardrails</h1>
        <button
          onClick={() => setShowModal(true)}
          className="inline-flex items-center gap-2 px-4 py-2 bg-teal-600 text-white text-sm font-medium rounded-md hover:bg-teal-700"
        >
          <PlusIcon className="h-4 w-4" />
          Create Guardrail
        </button>
      </div>

      <div className="flex gap-4">
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="px-3 py-2 border border-gray-300 rounded-md text-sm"
        >
          <option value="">All Types</option>
          <option value="pre_processing">Pre-processing</option>
          <option value="post_processing">Post-processing</option>
          <option value="structural">Structural</option>
        </select>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="px-3 py-2 border border-gray-300 rounded-md text-sm"
        >
          <option value="">All Statuses</option>
          <option value="draft">Draft</option>
          <option value="active">Active</option>
          <option value="disabled">Disabled</option>
        </select>
      </div>

      <div className="bg-white shadow rounded-lg overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Name</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Type</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Mechanism</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Scope</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Priority</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Created</th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {items.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-6 py-12 text-center text-gray-500">
                  No guardrails found. Create one to get started.
                </td>
              </tr>
            ) : (
              items.map((g) => (
                <tr key={g.id} className="hover:bg-gray-50">
                  <td className="px-6 py-4">
                    <Link to={`/guardrails/${g.id}`} className="text-teal-600 hover:text-teal-700 font-medium">
                      {g.name}
                    </Link>
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-600">{TYPE_LABELS[g.type] || g.type}</td>
                  <td className="px-6 py-4 text-sm text-gray-600">{MECHANISM_LABELS[g.mechanism] || g.mechanism}</td>
                  <td className="px-6 py-4">
                    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${STATUS_BADGES[g.status] || 'bg-gray-100 text-gray-800'}`}>
                      {g.status}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-600">
                    {g.scope === 'all_agents' ? 'All Agents' : 'Specific'}
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-600">{g.priority}</td>
                  <td className="px-6 py-4 text-sm text-gray-500">
                    {g.created_at ? format(new Date(g.created_at), 'MMM d, yyyy') : '-'}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {showModal && (
        <GuardrailModal
          onClose={() => setShowModal(false)}
          onSubmit={(data) => createMutation.mutateAsync(data)}
          submitting={createMutation.isPending}
        />
      )}
    </div>
  );
}
