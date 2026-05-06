import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { PlusIcon, PencilIcon } from '@heroicons/react/24/outline';
import { evaluationSuites } from '../api/client';
import StatusBadge from '../components/StatusBadge';

const RISK_TIERS = ['low', 'medium', 'high', 'critical'];
const JUDGE_PROVIDERS = ['openai', 'anthropic', 'google', 'openrouter'];

function SuiteModal({ suite, onClose, onSave }) {
  const [name, setName] = useState(suite?.name || '');
  const [description, setDescription] = useState(suite?.description || '');
  const [version, setVersion] = useState(suite?.version || '1.0.0');
  const [riskTiers, setRiskTiers] = useState(
    suite?.applicable_risk_tiers || ['low', 'medium', 'high', 'critical']
  );
  const [judgeProvider, setJudgeProvider] = useState(
    suite?.judge_provider || suite?.judge_config?.provider || 'openai'
  );
  const [judgeModel, setJudgeModel] = useState(
    suite?.judge_model || suite?.judge_config?.model || 'gpt-5.2'
  );
  const [saving, setSaving] = useState(false);

  function toggleRiskTier(tier) {
    setRiskTiers((prev) =>
      prev.includes(tier) ? prev.filter((t) => t !== tier) : [...prev, tier]
    );
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (riskTiers.length === 0) {
      alert('Select at least one risk tier');
      return;
    }
    setSaving(true);
    try {
      const payload = {
        name,
        description,
        version,
        applicable_risk_tiers: riskTiers,
        judge_config: { provider: judgeProvider, model: judgeModel },
      };
      await onSave(payload);
      onClose();
    } catch (error) {
      alert(error.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="flex items-center justify-center min-h-screen p-4">
        <div className="fixed inset-0 bg-black bg-opacity-25" onClick={onClose} />
        <div className="relative bg-white rounded-lg shadow-xl max-w-md w-full p-6">
          <h2 className="text-lg font-medium text-gray-900 mb-4">
            {suite ? 'Edit Evaluation Suite' : 'Create Evaluation Suite'}
          </h2>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700">
                Name
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-teal-500 focus:border-teal-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700">
                Description
              </label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={3}
                className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-teal-500 focus:border-teal-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700">
                Version
              </label>
              <input
                type="text"
                value={version}
                onChange={(e) => setVersion(e.target.value)}
                required
                className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-teal-500 focus:border-teal-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Applicable Risk Tiers
              </label>
              <div className="flex flex-wrap gap-2">
                {RISK_TIERS.map((tier) => (
                  <button
                    key={tier}
                    type="button"
                    onClick={() => toggleRiskTier(tier)}
                    className={`px-3 py-1 text-sm rounded-full border ${
                      riskTiers.includes(tier)
                        ? 'bg-teal-100 border-teal-300 text-teal-800'
                        : 'bg-gray-50 border-gray-300 text-gray-600'
                    }`}
                  >
                    {tier}
                  </button>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700">
                  Judge Provider
                </label>
                <select
                  value={judgeProvider}
                  onChange={(e) => setJudgeProvider(e.target.value)}
                  className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-teal-500 focus:border-teal-500"
                >
                  {JUDGE_PROVIDERS.map((p) => (
                    <option key={p} value={p}>{p}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">
                  Judge Model
                </label>
                <input
                  type="text"
                  value={judgeModel}
                  onChange={(e) => setJudgeModel(e.target.value)}
                  required
                  className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-teal-500 focus:border-teal-500"
                />
              </div>
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
                disabled={saving}
                className="px-4 py-2 text-sm font-medium text-white bg-teal-600 rounded-md hover:bg-teal-700 disabled:opacity-50"
              >
                {saving ? 'Saving...' : 'Save'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

export default function EvaluationSuites() {
  const [modalOpen, setModalOpen] = useState(false);
  const [editingSuite, setEditingSuite] = useState(null);
  const queryClient = useQueryClient();

  const { data, isLoading, error } = useQuery({
    queryKey: ['evaluation-suites'],
    queryFn: () => evaluationSuites.list(),
  });

  const createMutation = useMutation({
    mutationFn: (data) => evaluationSuites.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['evaluation-suites'] });
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }) => evaluationSuites.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['evaluation-suites'] });
    },
  });

  function handleSave(data) {
    if (editingSuite) {
      return updateMutation.mutateAsync({ id: editingSuite.id, data });
    }
    return createMutation.mutateAsync(data);
  }

  function openCreate() {
    setEditingSuite(null);
    setModalOpen(true);
  }

  function openEdit(suite) {
    setEditingSuite(suite);
    setModalOpen(true);
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
        Failed to load evaluation suites: {error.message}
      </div>
    );
  }

  const suites = data?.suites || [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Evaluation Suites</h1>
        <button
          onClick={openCreate}
          className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700"
        >
          <PlusIcon className="h-4 w-4" />
          Create Suite
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {suites.map((suite) => (
          <div
            key={suite.id}
            className="bg-white shadow rounded-lg p-6 hover:shadow-md transition-shadow"
          >
            <div className="flex items-start justify-between">
              <div>
                <Link to={`/evaluation-suites/${suite.id}`} className="font-medium text-gray-900 hover:text-teal-600">
                  {suite.name}
                </Link>
                <p className="text-sm text-gray-500 mt-1">{suite.description}</p>
              </div>
              <button
                onClick={() => openEdit(suite)}
                className="text-gray-400 hover:text-gray-600"
              >
                <PencilIcon className="h-5 w-5" />
              </button>
            </div>

            <div className="mt-4 flex items-center justify-between text-sm">
              <span className="text-gray-500">v{suite.version}</span>
              <StatusBadge status={suite.is_active ? 'active' : 'inactive'} />
            </div>

            <div className="mt-3 text-sm text-gray-500">
              {suite.test_case_count || 0} test cases
            </div>
          </div>
        ))}

        {suites.length === 0 && (
          <div className="col-span-full text-center py-8 text-gray-500">
            No evaluation suites yet. Create one to get started.
          </div>
        )}
      </div>

      {modalOpen && (
        <SuiteModal
          suite={editingSuite}
          onClose={() => setModalOpen(false)}
          onSave={handleSave}
        />
      )}
    </div>
  );
}
