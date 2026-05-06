import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { format } from 'date-fns';
import {
  PlusIcon,
  PencilIcon,
  TrashIcon,
  PlayIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  ExclamationTriangleIcon,
} from '@heroicons/react/24/outline';
import { adversarial } from '../api/client';
import AdversarialSuiteModal from '../components/AdversarialSuiteModal';
import ConfirmDialog from '../components/ConfirmDialog';

const STATUS_BADGES = {
  active: 'bg-green-100 text-green-800',
  draft: 'bg-gray-100 text-gray-800',
  disabled: 'bg-red-100 text-red-800',
  running: 'bg-blue-100 text-blue-800',
  completed: 'bg-green-100 text-green-800',
  failed: 'bg-red-100 text-red-800',
  pending: 'bg-yellow-100 text-yellow-800',
};

const ATTACK_TYPE_COLORS = {
  encoding: 'bg-purple-100 text-purple-800',
  jailbreak: 'bg-red-100 text-red-800',
  injection: 'bg-orange-100 text-orange-800',
  pii_bypass: 'bg-yellow-100 text-yellow-800',
  exfiltration: 'bg-pink-100 text-pink-800',
};

export default function AdversarialTesting() {
  const [showModal, setShowModal] = useState(false);
  const [editingSuite, setEditingSuite] = useState(null);
  const [deleteSuite, setDeleteSuite] = useState(null);
  const [expandedSuiteId, setExpandedSuiteId] = useState(null);
  const queryClient = useQueryClient();

  const { data, isLoading, error } = useQuery({
    queryKey: ['adversarial-suites'],
    queryFn: () => adversarial.suites.list(),
  });

  const { data: alertsData } = useQuery({
    queryKey: ['adversarial-alerts'],
    queryFn: () => adversarial.alerts(),
  });

  const triggerRunMutation = useMutation({
    mutationFn: (id) => adversarial.suites.triggerRun(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['adversarial-suites'] });
      queryClient.invalidateQueries({ queryKey: ['adversarial-runs'] });
      alert('Adversarial test run triggered successfully.');
    },
    onError: (err) => {
      alert('Failed to trigger run: ' + (err.message || 'Unknown error'));
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id) => adversarial.suites.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['adversarial-suites'] });
      setDeleteSuite(null);
    },
  });

  function openCreate() {
    setEditingSuite(null);
    setShowModal(true);
  }

  function openEdit(e, suite) {
    e.stopPropagation();
    setEditingSuite(suite);
    setShowModal(true);
  }

  function handleSaved() {
    queryClient.invalidateQueries({ queryKey: ['adversarial-suites'] });
    setShowModal(false);
    setEditingSuite(null);
  }

  function toggleExpand(suiteId) {
    setExpandedSuiteId((prev) => (prev === suiteId ? null : suiteId));
  }

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
        <p className="text-red-800">Failed to load adversarial suites: {error.message}</p>
      </div>
    );
  }

  const suites = data?.suites || [];
  const alerts = alertsData?.alerts || [];

  return (
    <div className="space-y-6">
      {/* Threshold Breach Alerts */}
      {alerts.length > 0 && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <div className="flex items-center gap-2 mb-2">
            <ExclamationTriangleIcon className="h-5 w-5 text-red-600" />
            <h3 className="text-sm font-medium text-red-800">Threshold Breach Alerts</h3>
          </div>
          <ul className="space-y-1">
            {alerts.map((alert, i) => (
              <li key={alert.id || i} className="text-sm text-red-700">
                <span className="font-medium">{alert.suite_name || 'Suite'}</span>
                {' '}&mdash; Evasion rate {alert.evasion_rate != null ? `${(alert.evasion_rate * 100).toFixed(1)}%` : 'N/A'}
                {' '}exceeded threshold of {alert.threshold != null ? `${(alert.threshold * 100).toFixed(1)}%` : 'N/A'}
                {alert.created_at && (
                  <span className="text-red-500 ml-2">
                    ({format(new Date(alert.created_at), 'MMM d, yyyy HH:mm')})
                  </span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-gray-900">Adversarial Testing</h1>
        <button
          onClick={openCreate}
          className="inline-flex items-center gap-2 px-4 py-2 bg-teal-600 text-white text-sm font-medium rounded-md hover:bg-teal-700"
        >
          <PlusIcon className="h-4 w-4" />
          Create Suite
        </button>
      </div>

      {/* Suites Table */}
      <div className="bg-white shadow rounded-lg overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase w-8" />
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Name</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Attack Types</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Schedule</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Last Run</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Evasion Rate</th>
              <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Actions</th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {suites.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-6 py-12 text-center text-gray-500">
                  No adversarial test suites found. Create one to get started.
                </td>
              </tr>
            ) : (
              suites.map((suite) => (
                <SuiteRow
                  key={suite.id}
                  suite={suite}
                  expanded={expandedSuiteId === suite.id}
                  onToggle={() => toggleExpand(suite.id)}
                  onRun={(e) => { e.stopPropagation(); triggerRunMutation.mutate(suite.id); }}
                  onEdit={(e) => openEdit(e, suite)}
                  onDelete={(e) => { e.stopPropagation(); setDeleteSuite(suite); }}
                  runPending={triggerRunMutation.isPending}
                />
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Create/Edit Modal */}
      {showModal && (
        <AdversarialSuiteModal
          isOpen={showModal}
          onClose={() => { setShowModal(false); setEditingSuite(null); }}
          suite={editingSuite}
          onSaved={handleSaved}
        />
      )}

      {/* Delete Confirmation */}
      <ConfirmDialog
        open={!!deleteSuite}
        onClose={() => setDeleteSuite(null)}
        onConfirm={() => deleteMutation.mutate(deleteSuite.id)}
        title="Delete Adversarial Suite"
        message={`Are you sure you want to delete "${deleteSuite?.name}"? This will also delete all associated runs and results. This cannot be undone.`}
        confirmText="Delete"
        confirmStyle="danger"
        loading={deleteMutation.isPending}
      />
    </div>
  );
}

function SuiteRow({ suite, expanded, onToggle, onRun, onEdit, onDelete, runPending }) {
  return (
    <>
      <tr className="hover:bg-gray-50 cursor-pointer" onClick={onToggle}>
        <td className="px-6 py-4">
          {expanded ? (
            <ChevronDownIcon className="h-4 w-4 text-gray-400" />
          ) : (
            <ChevronRightIcon className="h-4 w-4 text-gray-400" />
          )}
        </td>
        <td className="px-6 py-4 text-sm font-medium text-gray-900">{suite.name}</td>
        <td className="px-6 py-4">
          <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${STATUS_BADGES[suite.status] || 'bg-gray-100 text-gray-800'}`}>
            {suite.status}
          </span>
        </td>
        <td className="px-6 py-4">
          <div className="flex flex-wrap gap-1">
            {(suite.attack_types || []).map((type) => (
              <span
                key={type}
                className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${ATTACK_TYPE_COLORS[type] || 'bg-gray-100 text-gray-800'}`}
              >
                {type.replace('_', ' ')}
              </span>
            ))}
          </div>
        </td>
        <td className="px-6 py-4 text-sm text-gray-600">
          {suite.schedule_enabled ? (
            <span className="inline-flex items-center gap-1">
              <span className="h-2 w-2 rounded-full bg-green-500" />
              Every {suite.schedule_interval_minutes}m
            </span>
          ) : (
            <span className="inline-flex items-center gap-1">
              <span className="h-2 w-2 rounded-full bg-gray-300" />
              Off
            </span>
          )}
        </td>
        <td className="px-6 py-4 text-sm text-gray-500">
          {suite.last_run_at ? format(new Date(suite.last_run_at), 'MMM d, yyyy HH:mm') : '-'}
        </td>
        <td className="px-6 py-4 text-sm">
          {suite.latest_evasion_rate != null ? (
            <span className={`font-medium ${
              suite.evasion_threshold != null && suite.latest_evasion_rate > suite.evasion_threshold
                ? 'text-red-600'
                : 'text-green-600'
            }`}>
              {(suite.latest_evasion_rate * 100).toFixed(1)}%
            </span>
          ) : (
            <span className="text-gray-400">-</span>
          )}
        </td>
        <td className="px-6 py-4 text-right">
          <div className="flex items-center justify-end gap-2">
            <button
              onClick={onRun}
              disabled={runPending}
              className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium text-white bg-teal-600 rounded hover:bg-teal-700 disabled:opacity-50"
              title="Run"
            >
              <PlayIcon className="h-3.5 w-3.5" />
              Run
            </button>
            <button
              onClick={onEdit}
              className="text-gray-400 hover:text-teal-600"
              title="Edit"
            >
              <PencilIcon className="h-4 w-4" />
            </button>
            <button
              onClick={onDelete}
              className="text-gray-400 hover:text-red-600"
              title="Delete"
            >
              <TrashIcon className="h-4 w-4" />
            </button>
          </div>
        </td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={8} className="px-0 py-0">
            <RunHistoryPanel suiteId={suite.id} evasionThreshold={suite.evasion_threshold} />
          </td>
        </tr>
      )}
    </>
  );
}

function RunHistoryPanel({ suiteId, evasionThreshold }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['adversarial-runs', suiteId],
    queryFn: () => adversarial.runs.list(suiteId),
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-teal-600" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="px-6 py-4 text-sm text-red-600">
        Failed to load run history: {error.message}
      </div>
    );
  }

  const runs = data?.runs || [];

  if (runs.length === 0) {
    return (
      <div className="px-6 py-6 text-center text-sm text-gray-500 bg-gray-50">
        No runs yet. Trigger a run to get started.
      </div>
    );
  }

  return (
    <div className="bg-gray-50 border-t border-gray-200">
      <div className="px-6 py-3">
        <h4 className="text-xs font-medium text-gray-500 uppercase mb-2">Run History</h4>
      </div>
      <table className="min-w-full divide-y divide-gray-200">
        <thead className="bg-gray-100">
          <tr>
            <th className="px-6 py-2 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
            <th className="px-6 py-2 text-left text-xs font-medium text-gray-500 uppercase">Total Inputs</th>
            <th className="px-6 py-2 text-left text-xs font-medium text-gray-500 uppercase">Evaded</th>
            <th className="px-6 py-2 text-left text-xs font-medium text-gray-500 uppercase">Evasion Rate</th>
            <th className="px-6 py-2 text-left text-xs font-medium text-gray-500 uppercase">Started</th>
            <th className="px-6 py-2 text-left text-xs font-medium text-gray-500 uppercase">Completed</th>
            <th className="px-6 py-2 text-right text-xs font-medium text-gray-500 uppercase">Detail</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-200 bg-white">
          {runs.map((run) => {
            const evasionRate = run.total_inputs > 0 ? run.evaded_count / run.total_inputs : null;
            const breached = evasionThreshold != null && evasionRate != null && evasionRate > evasionThreshold;
            return (
              <tr key={run.id} className="hover:bg-gray-50">
                <td className="px-6 py-3">
                  <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_BADGES[run.status] || 'bg-gray-100 text-gray-800'}`}>
                    {run.status}
                  </span>
                </td>
                <td className="px-6 py-3 text-sm text-gray-600">{run.total_inputs ?? '-'}</td>
                <td className="px-6 py-3 text-sm text-gray-600">{run.evaded_count ?? '-'}</td>
                <td className="px-6 py-3 text-sm">
                  {evasionRate != null ? (
                    <span className={`font-medium ${breached ? 'text-red-600' : 'text-green-600'}`}>
                      {(evasionRate * 100).toFixed(1)}%
                    </span>
                  ) : (
                    <span className="text-gray-400">-</span>
                  )}
                </td>
                <td className="px-6 py-3 text-sm text-gray-500">
                  {run.started_at ? format(new Date(run.started_at), 'MMM d, yyyy HH:mm') : '-'}
                </td>
                <td className="px-6 py-3 text-sm text-gray-500">
                  {run.completed_at ? format(new Date(run.completed_at), 'MMM d, yyyy HH:mm') : '-'}
                </td>
                <td className="px-6 py-3 text-right">
                  <Link
                    to={`/adversarial-testing/${suiteId}/runs/${run.id}`}
                    className="text-sm text-teal-600 hover:text-teal-700 font-medium"
                  >
                    View Detail
                  </Link>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
