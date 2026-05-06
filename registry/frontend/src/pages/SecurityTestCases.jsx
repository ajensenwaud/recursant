import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  PlusIcon,
  PencilIcon,
  TrashIcon,
  ArrowPathIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';
import { securityTestCases } from '../api/client';
import StatusBadge from '../components/StatusBadge';
import ConfirmDialog from '../components/ConfirmDialog';

const SCAN_TYPES = [
  { value: 'prompt_injection', label: 'Prompt Injection' },
  { value: 'data_exfiltration', label: 'Data Exfiltration' },
  { value: 'tool_abuse', label: 'Tool Abuse' },
  { value: 'egress_validation', label: 'Egress Validation' },
  { value: 'credential_handling', label: 'Credential Handling' },
  { value: 'input_validation', label: 'Input Validation' },
  { value: 'custom', label: 'Custom' },
];

const SEVERITY_LEVELS = [
  { value: 'info', label: 'Info' },
  { value: 'low', label: 'Low' },
  { value: 'medium', label: 'Medium' },
  { value: 'high', label: 'High' },
  { value: 'critical', label: 'Critical' },
];

const DETECTION_METHODS = [
  { value: 'regex', label: 'Regex' },
  { value: 'keyword', label: 'Keyword' },
  { value: 'semantic', label: 'Semantic' },
];

function DynamicStringList({ label, items, onChange }) {
  function addItem() {
    onChange([...items, '']);
  }

  function removeItem(index) {
    onChange(items.filter((_, i) => i !== index));
  }

  function updateItem(index, value) {
    const updated = [...items];
    updated[index] = value;
    onChange(updated);
  }

  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1">
        {label}
      </label>
      <div className="space-y-2">
        {items.map((item, index) => (
          <div key={index} className="flex gap-2">
            <input
              type="text"
              value={item}
              onChange={(e) => updateItem(index, e.target.value)}
              className="flex-1 px-3 py-1.5 text-sm border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-teal-500 focus:border-teal-500 font-mono"
            />
            <button
              type="button"
              onClick={() => removeItem(index)}
              className="p-1.5 text-gray-400 hover:text-red-500"
            >
              <XMarkIcon className="h-4 w-4" />
            </button>
          </div>
        ))}
      </div>
      <button
        type="button"
        onClick={addItem}
        className="mt-2 text-sm text-teal-600 hover:text-teal-700"
      >
        + Add pattern
      </button>
    </div>
  );
}

function TestCaseModal({ testCase, onClose, onSave }) {
  const [form, setForm] = useState({
    name: testCase?.name || '',
    scan_type: testCase?.scan_type || 'prompt_injection',
    category: testCase?.category || '',
    description: testCase?.description || '',
    severity: testCase?.severity || 'medium',
    is_blocking: testCase?.is_blocking ?? true,
    input_template: testCase?.input_template || '',
    detection_method: testCase?.detection_patterns?.detection_method || 'regex',
    success_indicators: testCase?.detection_patterns?.success_indicators || [''],
    failure_indicators: testCase?.detection_patterns?.failure_indicators || [''],
    expected_behavior: testCase?.expected_behavior || '',
    remediation_guidance: testCase?.remediation_guidance || '',
    owasp_reference: testCase?.owasp_reference || '',
    cwe_reference: testCase?.cwe_reference || '',
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  function updateField(field, value) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSaving(true);
    try {
      const payload = {
        name: form.name,
        scan_type: form.scan_type,
        category: form.category,
        description: form.description,
        severity: form.severity,
        is_blocking: form.is_blocking,
        input_template: form.input_template,
        detection_patterns: {
          detection_method: form.detection_method,
          success_indicators: form.success_indicators.filter((s) => s.trim()),
          failure_indicators: form.failure_indicators.filter((s) => s.trim()),
        },
        expected_behavior: form.expected_behavior,
        remediation_guidance: form.remediation_guidance || undefined,
        owasp_reference: form.owasp_reference || undefined,
        cwe_reference: form.cwe_reference || undefined,
      };
      await onSave(payload);
      onClose();
    } catch (err) {
      setError(err.data?.message || err.message);
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
            {testCase ? 'Edit Test Case' : 'Create Test Case'}
          </h2>

          {error && (
            <div className="mb-4 bg-red-50 border border-red-200 text-red-700 px-3 py-2 rounded text-sm">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="col-span-2">
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
                <label className="block text-sm font-medium text-gray-700">Scan Type</label>
                <select
                  value={form.scan_type}
                  onChange={(e) => updateField('scan_type', e.target.value)}
                  required
                  className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-teal-500 focus:border-teal-500"
                >
                  {SCAN_TYPES.map((t) => (
                    <option key={t.value} value={t.value}>{t.label}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700">Category</label>
                <input
                  type="text"
                  value={form.category}
                  onChange={(e) => updateField('category', e.target.value)}
                  required
                  className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-teal-500 focus:border-teal-500"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700">Severity</label>
                <select
                  value={form.severity}
                  onChange={(e) => updateField('severity', e.target.value)}
                  className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-teal-500 focus:border-teal-500"
                >
                  {SEVERITY_LEVELS.map((s) => (
                    <option key={s.value} value={s.value}>{s.label}</option>
                  ))}
                </select>
              </div>

              <div className="flex items-end">
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={form.is_blocking}
                    onChange={(e) => updateField('is_blocking', e.target.checked)}
                    className="h-4 w-4 rounded border-gray-300 text-teal-600 focus:ring-teal-500"
                  />
                  <span className="text-sm font-medium text-gray-700">Blocking</span>
                </label>
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700">Description</label>
              <textarea
                value={form.description}
                onChange={(e) => updateField('description', e.target.value)}
                rows={2}
                className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-teal-500 focus:border-teal-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700">
                Input Template (prompt sent to agent)
              </label>
              <textarea
                value={form.input_template}
                onChange={(e) => updateField('input_template', e.target.value)}
                required
                rows={3}
                className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-teal-500 focus:border-teal-500 font-mono text-sm"
              />
            </div>

            <div className="border-t pt-4">
              <h3 className="text-sm font-medium text-gray-900 mb-3">Detection Patterns</h3>

              <div className="mb-3">
                <label className="block text-sm font-medium text-gray-700">Detection Method</label>
                <select
                  value={form.detection_method}
                  onChange={(e) => updateField('detection_method', e.target.value)}
                  className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-teal-500 focus:border-teal-500"
                >
                  {DETECTION_METHODS.map((m) => (
                    <option key={m.value} value={m.value}>{m.label}</option>
                  ))}
                </select>
              </div>

              <div className="space-y-4">
                <DynamicStringList
                  label="Success Indicators"
                  items={form.success_indicators}
                  onChange={(v) => updateField('success_indicators', v)}
                />
                <DynamicStringList
                  label="Failure Indicators"
                  items={form.failure_indicators}
                  onChange={(v) => updateField('failure_indicators', v)}
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700">Expected Behavior</label>
              <textarea
                value={form.expected_behavior}
                onChange={(e) => updateField('expected_behavior', e.target.value)}
                required
                rows={2}
                className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-teal-500 focus:border-teal-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700">
                Remediation Guidance
              </label>
              <textarea
                value={form.remediation_guidance}
                onChange={(e) => updateField('remediation_guidance', e.target.value)}
                rows={2}
                className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-teal-500 focus:border-teal-500"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700">OWASP Reference</label>
                <input
                  type="text"
                  value={form.owasp_reference}
                  onChange={(e) => updateField('owasp_reference', e.target.value)}
                  placeholder="e.g. LLM01:2025"
                  className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-teal-500 focus:border-teal-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">CWE Reference</label>
                <input
                  type="text"
                  value={form.cwe_reference}
                  onChange={(e) => updateField('cwe_reference', e.target.value)}
                  placeholder="e.g. CWE-94"
                  className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-teal-500 focus:border-teal-500"
                />
              </div>
            </div>

            <div className="flex justify-end gap-3 pt-4">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-teal-500"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={saving}
                className="px-4 py-2 text-sm font-medium text-white bg-teal-600 rounded-md hover:bg-teal-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-teal-500 disabled:opacity-50"
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

export default function SecurityTestCases() {
  const [modalOpen, setModalOpen] = useState(false);
  const [editingTestCase, setEditingTestCase] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [resetConfirmOpen, setResetConfirmOpen] = useState(false);
  const [filterScanType, setFilterScanType] = useState('');
  const [filterBuiltin, setFilterBuiltin] = useState('');
  const [page, setPage] = useState(1);
  const queryClient = useQueryClient();

  const params = { page, per_page: 50 };
  if (filterScanType) params.scan_type = filterScanType;
  if (filterBuiltin) params.is_builtin = filterBuiltin;

  const { data, isLoading, error } = useQuery({
    queryKey: ['security-test-cases', params],
    queryFn: () => securityTestCases.list(params),
  });

  const createMutation = useMutation({
    mutationFn: (data) => securityTestCases.create(data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['security-test-cases'] }),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }) => securityTestCases.update(id, data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['security-test-cases'] }),
  });

  const deleteMutation = useMutation({
    mutationFn: (id) => securityTestCases.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['security-test-cases'] });
      setDeleteTarget(null);
    },
  });

  const resetMutation = useMutation({
    mutationFn: () => securityTestCases.resetDefaults(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['security-test-cases'] });
      setResetConfirmOpen(false);
    },
  });

  function handleSave(payload) {
    if (editingTestCase) {
      return updateMutation.mutateAsync({ id: editingTestCase.id, data: payload });
    }
    return createMutation.mutateAsync(payload);
  }

  function openCreate() {
    setEditingTestCase(null);
    setModalOpen(true);
  }

  function openEdit(tc) {
    setEditingTestCase(tc);
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
        Failed to load security test cases: {error.message}
      </div>
    );
  }

  const testCases = data?.test_cases || [];
  const pagination = data?.pagination || {};
  const totalPages = pagination.pages || 1;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Security Test Cases</h1>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setResetConfirmOpen(true)}
            className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50"
          >
            <ArrowPathIcon className="h-4 w-4" />
            Reset to OWASP Defaults
          </button>
          <button
            onClick={openCreate}
            className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-teal-600 rounded-md hover:bg-teal-700"
          >
            <PlusIcon className="h-4 w-4" />
            Add Test Case
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-4">
        <select
          value={filterScanType}
          onChange={(e) => { setFilterScanType(e.target.value); setPage(1); }}
          className="px-3 py-2 text-sm border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-teal-500 focus:border-teal-500"
        >
          <option value="">All Scan Types</option>
          {SCAN_TYPES.map((t) => (
            <option key={t.value} value={t.value}>{t.label}</option>
          ))}
        </select>

        <select
          value={filterBuiltin}
          onChange={(e) => { setFilterBuiltin(e.target.value); setPage(1); }}
          className="px-3 py-2 text-sm border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-teal-500 focus:border-teal-500"
        >
          <option value="">All (Built-in + Custom)</option>
          <option value="true">Built-in Only</option>
          <option value="false">Custom Only</option>
        </select>

        <span className="text-sm text-gray-500">
          {pagination.total || 0} test case{(pagination.total || 0) !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Table */}
      <div className="bg-white shadow rounded-lg overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Name
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Scan Type
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Category
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Severity
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Blocking
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Type
              </th>
              <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {testCases.map((tc) => (
              <tr key={tc.id} className="hover:bg-gray-50">
                <td className="px-6 py-4 whitespace-nowrap">
                  <div className="text-sm font-medium text-gray-900">{tc.name}</div>
                  {tc.owasp_reference && (
                    <div className="text-xs text-gray-500">{tc.owasp_reference}</div>
                  )}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 capitalize">
                  {tc.scan_type?.replace(/_/g, ' ')}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 capitalize">
                  {tc.category?.replace(/_/g, ' ')}
                </td>
                <td className="px-6 py-4 whitespace-nowrap">
                  <StatusBadge status={tc.severity} />
                </td>
                <td className="px-6 py-4 whitespace-nowrap">
                  {tc.is_blocking ? (
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800">
                      Blocking
                    </span>
                  ) : (
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-600">
                      Non-blocking
                    </span>
                  )}
                </td>
                <td className="px-6 py-4 whitespace-nowrap">
                  {tc.is_builtin ? (
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                      Built-in
                    </span>
                  ) : (
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-teal-100 text-teal-800">
                      Custom
                    </span>
                  )}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                  <div className="flex items-center justify-end gap-2">
                    <button
                      onClick={() => openEdit(tc)}
                      disabled={tc.is_builtin}
                      className="text-gray-400 hover:text-gray-600 disabled:opacity-30 disabled:cursor-not-allowed"
                      title={tc.is_builtin ? 'Built-in tests cannot be edited' : 'Edit'}
                    >
                      <PencilIcon className="h-5 w-5" />
                    </button>
                    <button
                      onClick={() => setDeleteTarget(tc)}
                      disabled={tc.is_builtin}
                      className="text-gray-400 hover:text-red-600 disabled:opacity-30 disabled:cursor-not-allowed"
                      title={tc.is_builtin ? 'Built-in tests cannot be deleted' : 'Delete'}
                    >
                      <TrashIcon className="h-5 w-5" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {testCases.length === 0 && (
              <tr>
                <td colSpan={7} className="px-6 py-8 text-center text-gray-500">
                  No security test cases found. Use "Reset to OWASP Defaults" to seed built-in tests
                  or "Add Test Case" to create a custom one.
                </td>
              </tr>
            )}
          </tbody>
        </table>

        {/* Pagination — inside card, matching Submissions style */}
        {totalPages > 1 && (
          <div className="px-6 py-3 border-t border-gray-200 flex items-center justify-between">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="px-3 py-1 text-sm text-gray-600 hover:text-gray-900 disabled:opacity-50"
            >
              Previous
            </button>
            <span className="text-sm text-gray-500">
              Page {page} of {totalPages}
            </span>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              className="px-3 py-1 text-sm text-gray-600 hover:text-gray-900 disabled:opacity-50"
            >
              Next
            </button>
          </div>
        )}
      </div>

      {/* Modals */}
      {modalOpen && (
        <TestCaseModal
          testCase={editingTestCase}
          onClose={() => setModalOpen(false)}
          onSave={handleSave}
        />
      )}

      {/* Delete Confirmation — shared ConfirmDialog component */}
      <ConfirmDialog
        open={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => deleteMutation.mutate(deleteTarget.id)}
        title="Delete Test Case"
        message={`Are you sure you want to delete "${deleteTarget?.name}"? This action cannot be undone.`}
        confirmText="Delete"
        confirmStyle="danger"
        loading={deleteMutation.isPending}
      />

      {/* Reset Confirmation — shared ConfirmDialog component */}
      <ConfirmDialog
        open={resetConfirmOpen}
        onClose={() => setResetConfirmOpen(false)}
        onConfirm={() => resetMutation.mutate()}
        title="Reset to OWASP Defaults"
        message="This will re-create or update all built-in OWASP security test cases. Custom test cases will not be affected."
        confirmText="Reset"
        confirmStyle="primary"
        loading={resetMutation.isPending}
      />
    </div>
  );
}
