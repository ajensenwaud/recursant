import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { format } from 'date-fns';
import { PlusIcon, RocketLaunchIcon, BeakerIcon } from '@heroicons/react/24/outline';
import { guardrailMetrics } from '../api/client';

const CATEGORY_BADGES = {
  safety: 'bg-red-100 text-red-800',
  policy: 'bg-purple-100 text-purple-800',
  hallucination: 'bg-orange-100 text-orange-800',
  boundary: 'bg-blue-100 text-blue-800',
  quality: 'bg-green-100 text-green-800',
  tone: 'bg-yellow-100 text-yellow-800',
  custom: 'bg-gray-100 text-gray-800',
};

const MECHANISM_LABELS = {
  regex: 'Regex',
  vector_lookup: 'Vector Lookup',
  llm_judge: 'LLM Judge',
  ml_classifier: 'ML Classifier',
};

function CreateMetricModal({ onClose, onSubmit, submitting }) {
  const [form, setForm] = useState({
    name: '',
    display_name: '',
    description: '',
    category: 'custom',
    mechanism: 'llm_judge',
    config: '{}',
    scoring_rubric: '',
  });

  const handleSubmit = (e) => {
    e.preventDefault();
    const data = {
      ...form,
      config: JSON.parse(form.config || '{}'),
      scoring_rubric: form.scoring_rubric ? JSON.parse(form.scoring_rubric) : null,
    };
    onSubmit(data);
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-lg p-6 max-h-[90vh] overflow-y-auto">
        <h2 className="text-lg font-semibold mb-4">Create Metric</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
            <input
              type="text" required value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
              placeholder="e.g. pii_leakage"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Display Name</label>
            <input
              type="text" value={form.display_name}
              onChange={(e) => setForm({ ...form, display_name: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
              placeholder="e.g. PII Leakage Detection"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
            <textarea
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
              rows={2}
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Category</label>
              <select
                value={form.category}
                onChange={(e) => setForm({ ...form, category: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
              >
                <option value="safety">Safety</option>
                <option value="policy">Policy</option>
                <option value="hallucination">Hallucination</option>
                <option value="boundary">Boundary</option>
                <option value="quality">Quality</option>
                <option value="tone">Tone</option>
                <option value="custom">Custom</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Mechanism</label>
              <select
                value={form.mechanism}
                onChange={(e) => setForm({ ...form, mechanism: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
              >
                <option value="llm_judge">LLM Judge</option>
                <option value="regex">Regex</option>
                <option value="vector_lookup">Vector Lookup</option>
                <option value="ml_classifier">ML Classifier</option>
              </select>
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Config (JSON)</label>
            <textarea
              value={form.config}
              onChange={(e) => setForm({ ...form, config: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm font-mono"
              rows={4}
            />
          </div>
          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onClose}
              className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200">
              Cancel
            </button>
            <button type="submit" disabled={submitting}
              className="px-4 py-2 text-sm font-medium text-white bg-teal-600 rounded-md hover:bg-teal-700 disabled:opacity-50">
              {submitting ? 'Creating...' : 'Create'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function DeployModal({ metric, onClose, onSubmit, submitting }) {
  const [form, setForm] = useState({
    name: `${metric.name}-guardrail`,
    type: 'pre_processing',
    enforcement_mode: 'block',
    scope: 'all_agents',
    priority: 100,
  });

  const handleSubmit = (e) => {
    e.preventDefault();
    onSubmit(metric.id, form);
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-md p-6">
        <h2 className="text-lg font-semibold mb-4">Deploy as Guardrail</h2>
        <p className="text-sm text-gray-500 mb-4">
          Create a guardrail from metric <span className="font-medium">{metric.display_name || metric.name}</span>
        </p>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Guardrail Name</label>
            <input
              type="text" required value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Type</label>
              <select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm">
                <option value="pre_processing">Pre-processing</option>
                <option value="post_processing">Post-processing</option>
                <option value="structural">Structural</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Enforcement</label>
              <select value={form.enforcement_mode} onChange={(e) => setForm({ ...form, enforcement_mode: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm">
                <option value="block">Block</option>
                <option value="warn">Warn</option>
                <option value="redact">Redact</option>
              </select>
            </div>
          </div>
          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onClose}
              className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200">
              Cancel
            </button>
            <button type="submit" disabled={submitting}
              className="px-4 py-2 text-sm font-medium text-white bg-teal-600 rounded-md hover:bg-teal-700 disabled:opacity-50">
              {submitting ? 'Deploying...' : 'Deploy'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function ScoresPanel({ metricId }) {
  const { data, isLoading } = useQuery({
    queryKey: ['metric-scores', metricId],
    queryFn: () => guardrailMetrics.scores.list(metricId),
    enabled: !!metricId,
  });

  if (isLoading) return <div className="text-sm text-gray-500 py-4">Loading scores...</div>;

  const scores = data?.scores || [];
  if (scores.length === 0) return <div className="text-sm text-gray-500 py-4">No scores recorded yet.</div>;

  return (
    <div className="space-y-2">
      {scores.map((s) => (
        <div key={s.id} className="flex items-center justify-between py-2 px-3 bg-gray-50 rounded">
          <div className="text-sm">
            <span className="font-medium">{s.agent_name || 'N/A'}</span>
            <span className="text-gray-500 ml-2">{s.source}</span>
          </div>
          <div className="flex items-center gap-3">
            <div className="w-24 bg-gray-200 rounded-full h-2">
              <div
                className={`h-2 rounded-full ${s.score >= 0.7 ? 'bg-green-500' : s.score >= 0.4 ? 'bg-yellow-500' : 'bg-red-500'}`}
                style={{ width: `${(s.score || 0) * 100}%` }}
              />
            </div>
            <span className="text-sm font-mono w-12 text-right">{((s.score || 0) * 100).toFixed(0)}%</span>
          </div>
        </div>
      ))}
    </div>
  );
}

export default function GuardrailMetrics() {
  const [showCreate, setShowCreate] = useState(false);
  const [deployMetric, setDeployMetric] = useState(null);
  const [expandedId, setExpandedId] = useState(null);
  const [categoryFilter, setCategoryFilter] = useState('');
  const [mechanismFilter, setMechanismFilter] = useState('');
  const queryClient = useQueryClient();

  const { data, isLoading, error } = useQuery({
    queryKey: ['guardrail-metrics', categoryFilter, mechanismFilter],
    queryFn: () => guardrailMetrics.list({
      category: categoryFilter || undefined,
      mechanism: mechanismFilter || undefined,
    }),
  });

  const createMutation = useMutation({
    mutationFn: (data) => guardrailMetrics.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['guardrail-metrics'] });
      setShowCreate(false);
    },
  });

  const deployMutation = useMutation({
    mutationFn: ({ metricId, data }) => guardrailMetrics.createGuardrail(metricId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['guardrails'] });
      setDeployMetric(null);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id) => guardrailMetrics.delete(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['guardrail-metrics'] }),
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
        <p className="text-red-800">Failed to load metrics: {error.message}</p>
      </div>
    );
  }

  const items = data?.metrics || [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-gray-900">Metric Store</h1>
        <button
          onClick={() => setShowCreate(true)}
          className="inline-flex items-center gap-2 px-4 py-2 bg-teal-600 text-white text-sm font-medium rounded-md hover:bg-teal-700"
        >
          <PlusIcon className="h-4 w-4" />
          Create Metric
        </button>
      </div>

      <div className="flex gap-4">
        <select value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)}
          className="px-3 py-2 border border-gray-300 rounded-md text-sm">
          <option value="">All Categories</option>
          <option value="safety">Safety</option>
          <option value="policy">Policy</option>
          <option value="hallucination">Hallucination</option>
          <option value="boundary">Boundary</option>
          <option value="quality">Quality</option>
          <option value="tone">Tone</option>
          <option value="custom">Custom</option>
        </select>
        <select value={mechanismFilter} onChange={(e) => setMechanismFilter(e.target.value)}
          className="px-3 py-2 border border-gray-300 rounded-md text-sm">
          <option value="">All Mechanisms</option>
          <option value="llm_judge">LLM Judge</option>
          <option value="regex">Regex</option>
          <option value="vector_lookup">Vector Lookup</option>
          <option value="ml_classifier">ML Classifier</option>
        </select>
      </div>

      <div className="bg-white shadow rounded-lg overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Name</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Category</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Mechanism</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Version</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Created</th>
              <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Actions</th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {items.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-6 py-12 text-center text-gray-500">
                  No metrics found. Create one or seed built-in metrics.
                </td>
              </tr>
            ) : (
              items.map((m) => (
                <>
                  <tr key={m.id} className="hover:bg-gray-50 cursor-pointer"
                    onClick={() => setExpandedId(expandedId === m.id ? null : m.id)}>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-2">
                        <span className="text-teal-600 font-medium">{m.display_name || m.name}</span>
                        {m.is_builtin && (
                          <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold bg-teal-100 text-teal-800">
                            Built-in
                          </span>
                        )}
                      </div>
                      <span className="text-xs text-gray-500">{m.name}</span>
                    </td>
                    <td className="px-6 py-4">
                      <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${CATEGORY_BADGES[m.category] || CATEGORY_BADGES.custom}`}>
                        {m.category}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-600">{MECHANISM_LABELS[m.mechanism] || m.mechanism}</td>
                    <td className="px-6 py-4 text-sm text-gray-600">{m.version || '-'}</td>
                    <td className="px-6 py-4 text-sm text-gray-500">
                      {m.created_at ? format(new Date(m.created_at), 'MMM d, yyyy') : '-'}
                    </td>
                    <td className="px-6 py-4 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={(e) => { e.stopPropagation(); setDeployMetric(m); }}
                          className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium text-teal-700 bg-teal-50 rounded hover:bg-teal-100"
                          title="Deploy as Guardrail"
                        >
                          <RocketLaunchIcon className="h-3.5 w-3.5" />
                          Deploy
                        </button>
                        {!m.is_builtin && (
                          <button
                            onClick={(e) => { e.stopPropagation(); if (confirm('Delete this metric?')) deleteMutation.mutate(m.id); }}
                            className="px-2.5 py-1.5 text-xs font-medium text-red-600 bg-red-50 rounded hover:bg-red-100"
                          >
                            Delete
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                  {expandedId === m.id && (
                    <tr key={`${m.id}-scores`}>
                      <td colSpan={6} className="px-6 py-4 bg-gray-50 border-t border-gray-100">
                        <h4 className="text-sm font-medium text-gray-700 mb-2">Score History</h4>
                        <ScoresPanel metricId={m.id} />
                      </td>
                    </tr>
                  )}
                </>
              ))
            )}
          </tbody>
        </table>
      </div>

      {showCreate && (
        <CreateMetricModal
          onClose={() => setShowCreate(false)}
          onSubmit={(data) => createMutation.mutateAsync(data)}
          submitting={createMutation.isPending}
        />
      )}

      {deployMetric && (
        <DeployModal
          metric={deployMetric}
          onClose={() => setDeployMetric(null)}
          onSubmit={(metricId, data) => deployMutation.mutateAsync({ metricId, data })}
          submitting={deployMutation.isPending}
        />
      )}
    </div>
  );
}
