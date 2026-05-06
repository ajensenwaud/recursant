import { useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeftIcon,
  PlusIcon,
  PencilIcon,
  TrashIcon,
} from '@heroicons/react/24/outline';
import { evaluationSuites } from '../api/client';
import ConfirmDialog from '../components/ConfirmDialog';

const CATEGORIES = ['safety', 'policy', 'hallucination', 'boundary', 'quality'];
const AGGREGATION_METHODS = ['minimum', 'average', 'maximum'];

function TestCaseModal({ suiteId, testCase, onClose }) {
  const queryClient = useQueryClient();
  const isEdit = !!testCase;

  const [form, setForm] = useState({
    name: testCase?.name || '',
    category: testCase?.category || 'safety',
    description: testCase?.description || '',
    passing_threshold: testCase?.passing_threshold ?? 0.7,
    aggregation_method: testCase?.aggregation_method || 'minimum',
    is_blocking: testCase?.is_blocking ?? false,
    weight: testCase?.weight ?? 1.0,
    evaluation_cases: testCase?.evaluation_cases?.length
      ? testCase.evaluation_cases
      : [{ input: '', expected: '' }],
    grading_criteria: testCase?.grading_criteria?.length
      ? testCase.grading_criteria
      : [{ criterion: '', weight: 1.0 }],
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  function updateField(field, value) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  function updateEvalCase(index, field, value) {
    setForm((prev) => {
      const cases = [...prev.evaluation_cases];
      cases[index] = { ...cases[index], [field]: value };
      return { ...prev, evaluation_cases: cases };
    });
  }

  function addEvalCase() {
    setForm((prev) => ({
      ...prev,
      evaluation_cases: [...prev.evaluation_cases, { input: '', expected: '' }],
    }));
  }

  function removeEvalCase(index) {
    setForm((prev) => ({
      ...prev,
      evaluation_cases: prev.evaluation_cases.filter((_, i) => i !== index),
    }));
  }

  function updateCriterion(index, field, value) {
    setForm((prev) => {
      const criteria = [...prev.grading_criteria];
      criteria[index] = { ...criteria[index], [field]: value };
      return { ...prev, grading_criteria: criteria };
    });
  }

  function addCriterion() {
    setForm((prev) => ({
      ...prev,
      grading_criteria: [...prev.grading_criteria, { criterion: '', weight: 1.0 }],
    }));
  }

  function removeCriterion(index) {
    setForm((prev) => ({
      ...prev,
      grading_criteria: prev.grading_criteria.filter((_, i) => i !== index),
    }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSaving(true);

    const payload = {
      ...form,
      passing_threshold: parseFloat(form.passing_threshold),
      weight: parseFloat(form.weight),
      grading_criteria: form.grading_criteria.map((c) => ({
        ...c,
        weight: parseFloat(c.weight),
      })),
    };

    try {
      if (isEdit) {
        await evaluationSuites.testCases.update(suiteId, testCase.id, payload);
      } else {
        await evaluationSuites.testCases.create(suiteId, payload);
      }
      queryClient.invalidateQueries({ queryKey: ['evaluation-suite-test-cases', suiteId] });
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="flex items-center justify-center min-h-screen p-4">
        <div className="fixed inset-0 bg-black bg-opacity-25" onClick={onClose} />
        <div className="relative bg-white rounded-lg shadow-xl max-w-2xl w-full p-6 max-h-[90vh] overflow-y-auto">
          <h2 className="text-lg font-medium text-gray-900 mb-4">
            {isEdit ? 'Edit Test Case' : 'Add Test Case'}
          </h2>

          {error && (
            <div className="mb-4 bg-red-50 border border-red-200 text-red-700 px-3 py-2 rounded text-sm">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Name & Category */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700">Name</label>
                <input
                  type="text"
                  value={form.name}
                  onChange={(e) => updateField('name', e.target.value)}
                  required
                  className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-teal-500 focus:border-teal-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">Category</label>
                <select
                  value={form.category}
                  onChange={(e) => updateField('category', e.target.value)}
                  className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-teal-500 focus:border-teal-500"
                >
                  {CATEGORIES.map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
              </div>
            </div>

            {/* Description */}
            <div>
              <label className="block text-sm font-medium text-gray-700">Description</label>
              <textarea
                value={form.description}
                onChange={(e) => updateField('description', e.target.value)}
                rows={2}
                className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-teal-500 focus:border-teal-500"
              />
            </div>

            {/* Threshold, Aggregation, Weight, Blocking */}
            <div className="grid grid-cols-4 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700">Threshold</label>
                <input
                  type="number"
                  min="0"
                  max="1"
                  step="0.05"
                  value={form.passing_threshold}
                  onChange={(e) => updateField('passing_threshold', e.target.value)}
                  className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-teal-500 focus:border-teal-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">Aggregation</label>
                <select
                  value={form.aggregation_method}
                  onChange={(e) => updateField('aggregation_method', e.target.value)}
                  className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-teal-500 focus:border-teal-500"
                >
                  {AGGREGATION_METHODS.map((m) => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">Weight</label>
                <input
                  type="number"
                  min="0"
                  max="10"
                  step="0.1"
                  value={form.weight}
                  onChange={(e) => updateField('weight', e.target.value)}
                  className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-teal-500 focus:border-teal-500"
                />
              </div>
              <div className="flex items-end pb-2">
                <label className="flex items-center gap-2 text-sm font-medium text-gray-700">
                  <input
                    type="checkbox"
                    checked={form.is_blocking}
                    onChange={(e) => updateField('is_blocking', e.target.checked)}
                    className="h-4 w-4 rounded border-gray-300 text-teal-600 focus:ring-teal-500"
                  />
                  Blocking
                </label>
              </div>
            </div>

            {/* Evaluation Cases */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="block text-sm font-medium text-gray-700">Evaluation Cases</label>
                <button
                  type="button"
                  onClick={addEvalCase}
                  className="text-sm text-teal-600 hover:text-teal-700"
                >
                  + Add case
                </button>
              </div>
              <div className="space-y-3">
                {form.evaluation_cases.map((ec, i) => (
                  <div key={i} className="border border-gray-200 rounded-md p-3 bg-gray-50">
                    <div className="flex items-start justify-between mb-2">
                      <span className="text-xs text-gray-500 font-medium">Case {i + 1}</span>
                      {form.evaluation_cases.length > 1 && (
                        <button
                          type="button"
                          onClick={() => removeEvalCase(i)}
                          className="text-red-400 hover:text-red-600"
                        >
                          <TrashIcon className="h-4 w-4" />
                        </button>
                      )}
                    </div>
                    <div className="space-y-2">
                      <div>
                        <label className="block text-xs text-gray-500">Input prompt</label>
                        <textarea
                          value={ec.input}
                          onChange={(e) => updateEvalCase(i, 'input', e.target.value)}
                          required
                          rows={2}
                          className="mt-1 block w-full px-2 py-1.5 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-teal-500 focus:border-teal-500"
                        />
                      </div>
                      <div>
                        <label className="block text-xs text-gray-500">Expected behavior</label>
                        <textarea
                          value={ec.expected}
                          onChange={(e) => updateEvalCase(i, 'expected', e.target.value)}
                          required
                          rows={2}
                          className="mt-1 block w-full px-2 py-1.5 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-teal-500 focus:border-teal-500"
                        />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Grading Criteria */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="block text-sm font-medium text-gray-700">Grading Criteria</label>
                <button
                  type="button"
                  onClick={addCriterion}
                  className="text-sm text-teal-600 hover:text-teal-700"
                >
                  + Add criterion
                </button>
              </div>
              <div className="space-y-2">
                {form.grading_criteria.map((gc, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <input
                      type="text"
                      value={gc.criterion}
                      onChange={(e) => updateCriterion(i, 'criterion', e.target.value)}
                      required
                      placeholder="Criterion description"
                      className="flex-1 px-2 py-1.5 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-teal-500 focus:border-teal-500"
                    />
                    <input
                      type="number"
                      min="0"
                      max="10"
                      step="0.1"
                      value={gc.weight}
                      onChange={(e) => updateCriterion(i, 'weight', e.target.value)}
                      className="w-20 px-2 py-1.5 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-teal-500 focus:border-teal-500"
                    />
                    {form.grading_criteria.length > 1 && (
                      <button
                        type="button"
                        onClick={() => removeCriterion(i)}
                        className="text-red-400 hover:text-red-600"
                      >
                        <TrashIcon className="h-4 w-4" />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* Actions */}
            <div className="flex justify-end gap-3 pt-4 border-t">
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
                {saving ? 'Saving...' : isEdit ? 'Update' : 'Create'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

export default function EvaluationSuiteDetail() {
  const { id } = useParams();
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [editingTC, setEditingTC] = useState(null);
  const [deleteTC, setDeleteTC] = useState(null);

  const { data: suite, isLoading: suiteLoading, error: suiteError } = useQuery({
    queryKey: ['evaluation-suite', id],
    queryFn: () => evaluationSuites.get(id),
  });

  const { data: tcData, isLoading: tcLoading } = useQuery({
    queryKey: ['evaluation-suite-test-cases', id],
    queryFn: () => evaluationSuites.testCases.list(id),
  });

  const [deleteError, setDeleteError] = useState(null);
  const deleteMutation = useMutation({
    mutationFn: (tcId) => evaluationSuites.testCases.delete(id, tcId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['evaluation-suite-test-cases', id] });
      setDeleteTC(null);
      setDeleteError(null);
    },
    onError: (err) => {
      setDeleteError(err.message || 'Failed to delete test case');
    },
  });

  function openCreate() {
    setEditingTC(null);
    setModalOpen(true);
  }

  function openEdit(tc) {
    // Fetch full test case details for editing (list response is lightweight)
    evaluationSuites.testCases.get(id, tc.id).then((full) => {
      setEditingTC(full);
      setModalOpen(true);
    });
  }

  function handleDelete() {
    if (deleteTC) {
      deleteMutation.mutate(deleteTC.id);
    }
  }

  if (suiteLoading || tcLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="spinner" />
      </div>
    );
  }

  if (suiteError) {
    return (
      <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-md">
        Failed to load evaluation suite: {suiteError.message}
      </div>
    );
  }

  const testCases = tcData?.test_cases || [];

  return (
    <div className="space-y-6">
      {/* Back link */}
      <Link
        to="/evaluation-suites"
        className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700"
      >
        <ArrowLeftIcon className="h-4 w-4" />
        Back to Evaluation Suites
      </Link>

      {/* Suite header */}
      <div className="bg-white shadow rounded-lg p-6">
        <h1 className="text-2xl font-bold text-gray-900">{suite.name}</h1>
        {suite.description && (
          <p className="mt-1 text-gray-500">{suite.description}</p>
        )}
        <div className="mt-4 flex flex-wrap gap-4 text-sm text-gray-600">
          <span>Version: <span className="font-medium">{suite.version}</span></span>
          {suite.judge_config && (
            <span>
              Judge: <span className="font-medium">
                {suite.judge_config.provider} / {suite.judge_config.model}
              </span>
            </span>
          )}
        </div>
        {suite.applicable_risk_tiers?.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {suite.applicable_risk_tiers.map((tier) => (
              <span
                key={tier}
                className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-teal-50 text-teal-700 border border-teal-200"
              >
                {tier}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Test cases section */}
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-900">
          Test Cases ({testCases.length})
        </h2>
        <button
          onClick={openCreate}
          className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-teal-600 rounded-md hover:bg-teal-700"
        >
          <PlusIcon className="h-4 w-4" />
          Add Test Case
        </button>
      </div>

      {testCases.length === 0 ? (
        <div className="bg-white shadow rounded-lg p-8 text-center text-gray-500">
          No test cases yet. Add one to get started.
        </div>
      ) : (
        <div className="bg-white shadow rounded-lg overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Name
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Category
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Threshold
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Blocking
                </th>
                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {testCases.map((tc) => (
                <tr key={tc.id} className="hover:bg-gray-50">
                  <td className="px-6 py-4 text-sm font-medium text-gray-900">
                    {tc.name}
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-500 capitalize">
                    {tc.category}
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-500">
                    {tc.passing_threshold}
                  </td>
                  <td className="px-6 py-4 text-sm">
                    {tc.is_blocking ? (
                      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-red-50 text-red-700 border border-red-200">
                        Yes
                      </span>
                    ) : (
                      <span className="text-gray-400">No</span>
                    )}
                  </td>
                  <td className="px-6 py-4 text-right text-sm">
                    <button
                      onClick={() => openEdit(tc)}
                      className="text-gray-400 hover:text-teal-600 mr-3"
                      title="Edit"
                    >
                      <PencilIcon className="h-4 w-4 inline" />
                    </button>
                    <button
                      onClick={() => setDeleteTC(tc)}
                      className="text-gray-400 hover:text-red-600"
                      title="Delete"
                    >
                      <TrashIcon className="h-4 w-4 inline" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Modals */}
      {modalOpen && (
        <TestCaseModal
          suiteId={id}
          testCase={editingTC}
          onClose={() => {
            setModalOpen(false);
            setEditingTC(null);
          }}
        />
      )}

      <ConfirmDialog
        open={!!deleteTC}
        onClose={() => { setDeleteTC(null); setDeleteError(null); }}
        onConfirm={handleDelete}
        title="Delete Test Case"
        message={deleteError
          ? `Error: ${deleteError}`
          : `Are you sure you want to delete "${deleteTC?.name}"? This cannot be undone.`}
        confirmText="Delete"
        confirmStyle="danger"
        loading={deleteMutation.isPending}
      />
    </div>
  );
}
