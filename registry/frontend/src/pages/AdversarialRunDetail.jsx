import { useParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { format } from 'date-fns';
import {
  ArrowLeftIcon,
  CheckCircleIcon,
  XCircleIcon,
  ShieldExclamationIcon,
} from '@heroicons/react/24/outline';
import { adversarial } from '../api/client';

const STATUS_BADGES = {
  running: 'bg-blue-100 text-blue-800',
  completed: 'bg-green-100 text-green-800',
  failed: 'bg-red-100 text-red-800',
  pending: 'bg-yellow-100 text-yellow-800',
};

export default function AdversarialRunDetail() {
  const { suiteId, runId } = useParams();

  const { data, isLoading, error } = useQuery({
    queryKey: ['adversarial-run', suiteId, runId],
    queryFn: () => adversarial.runs.get(suiteId, runId),
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
        <p className="text-red-800">Failed to load run detail: {error.message}</p>
      </div>
    );
  }

  const run = data;
  const results = run?.results || [];
  const guardrailBreakdown = run?.guardrail_breakdown || [];
  const evasionRate = run?.total_inputs > 0 ? run.evaded_count / run.total_inputs : null;
  const thresholdBreached = run?.evasion_threshold != null && evasionRate != null && evasionRate > run.evasion_threshold;

  return (
    <div className="space-y-6">
      {/* Back link */}
      <Link
        to="/adversarial-testing"
        className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700"
      >
        <ArrowLeftIcon className="h-4 w-4" />
        Back to Adversarial Testing
      </Link>

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">
            {run?.suite_name || 'Adversarial Run'}
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            Run ID: {runId}
            {run?.started_at && (
              <span className="ml-3">
                Started: {format(new Date(run.started_at), 'MMM d, yyyy HH:mm:ss')}
              </span>
            )}
          </p>
        </div>
        <span className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-medium ${STATUS_BADGES[run?.status] || 'bg-gray-100 text-gray-800'}`}>
          {run?.status || 'unknown'}
        </span>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <SummaryCard label="Total Inputs" value={run?.total_inputs ?? 0} />
        <SummaryCard label="Blocked" value={run?.blocked_count ?? 0} color="text-green-600" />
        <SummaryCard label="Evaded" value={run?.evaded_count ?? 0} color="text-red-600" />
        <SummaryCard label="Errors" value={run?.error_count ?? 0} color="text-yellow-600" />
        <div className="bg-white shadow rounded-lg p-4">
          <dt className="text-sm font-medium text-gray-500">Evasion Rate</dt>
          <dd className={`mt-1 text-2xl font-bold ${
            evasionRate == null
              ? 'text-gray-400'
              : thresholdBreached
                ? 'text-red-600'
                : 'text-green-600'
          }`}>
            {evasionRate != null ? `${(evasionRate * 100).toFixed(1)}%` : '-'}
          </dd>
          {run?.evasion_threshold != null && (
            <p className="text-xs text-gray-400 mt-1">
              Threshold: {(run.evasion_threshold * 100).toFixed(1)}%
              {thresholdBreached && (
                <span className="text-red-500 font-medium ml-1">BREACHED</span>
              )}
            </p>
          )}
        </div>
      </div>

      {/* Per-Guardrail Breakdown */}
      {guardrailBreakdown.length > 0 && (
        <div className="bg-white shadow rounded-lg overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-200">
            <h2 className="text-lg font-medium text-gray-900">Per-Guardrail Evasion Breakdown</h2>
          </div>
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Guardrail</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Tested</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Evaded</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Evasion Rate</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {guardrailBreakdown.map((g, i) => {
                const gRate = g.tested_count > 0 ? g.evaded_count / g.tested_count : null;
                return (
                  <tr key={g.guardrail_id || i} className="hover:bg-gray-50">
                    <td className="px-6 py-3 text-sm font-medium text-gray-900">{g.guardrail_name || g.guardrail_id}</td>
                    <td className="px-6 py-3 text-sm text-gray-600">{g.tested_count}</td>
                    <td className="px-6 py-3 text-sm text-gray-600">{g.evaded_count}</td>
                    <td className="px-6 py-3 text-sm">
                      {gRate != null ? (
                        <span className={`font-medium ${gRate > 0.1 ? 'text-red-600' : 'text-green-600'}`}>
                          {(gRate * 100).toFixed(1)}%
                        </span>
                      ) : (
                        <span className="text-gray-400">-</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Signature Verification */}
      {run?.signature && (
        <div className="bg-white shadow rounded-lg p-6">
          <div className="flex items-center gap-2 mb-3">
            <ShieldExclamationIcon className="h-5 w-5 text-gray-500" />
            <h2 className="text-lg font-medium text-gray-900">Signature Verification</h2>
          </div>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <dt className="font-medium text-gray-500">Algorithm</dt>
              <dd className="mt-1 text-gray-900 font-mono">{run.signature.algorithm || '-'}</dd>
            </div>
            <div>
              <dt className="font-medium text-gray-500">Signature Hash</dt>
              <dd className="mt-1 text-gray-900 font-mono text-xs break-all">{run.signature.hash || '-'}</dd>
            </div>
          </div>
        </div>
      )}

      {/* Results Table */}
      <div className="bg-white shadow rounded-lg overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-medium text-gray-900">Results ({results.length})</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Input Text</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Attack Type</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Variant</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Source</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Target Guardrail</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Expected</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Actual</th>
                <th className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase">Evaded</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {results.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-6 py-8 text-center text-gray-500">
                    No results available.
                  </td>
                </tr>
              ) : (
                results.map((r, i) => (
                  <tr key={r.id || i} className="hover:bg-gray-50">
                    <td className="px-6 py-3 text-sm text-gray-900 max-w-xs">
                      <span title={r.input_text}>
                        {r.input_text && r.input_text.length > 100
                          ? r.input_text.substring(0, 100) + '...'
                          : r.input_text || '-'}
                      </span>
                    </td>
                    <td className="px-6 py-3 text-sm text-gray-600">{r.attack_type || '-'}</td>
                    <td className="px-6 py-3 text-sm text-gray-600">{r.variant || r.variant_name || '-'}</td>
                    <td className="px-6 py-3 text-sm">
                      <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${
                        r.source === 'custom' ? 'bg-blue-100 text-blue-800' :
                        r.source?.startsWith('llm:') ? 'bg-purple-100 text-purple-800' :
                        'bg-gray-100 text-gray-800'
                      }`}>
                        {r.source || 'static'}
                      </span>
                    </td>
                    <td className="px-6 py-3 text-sm text-gray-600">{r.target_guardrail || r.guardrail_name || '-'}</td>
                    <td className="px-6 py-3 text-sm text-gray-600">{r.expected_action || '-'}</td>
                    <td className="px-6 py-3 text-sm text-gray-600">{r.actual_action || '-'}</td>
                    <td className="px-6 py-3 text-center">
                      {r.evaded ? (
                        <XCircleIcon className="h-5 w-5 text-red-500 inline" title="Evaded" />
                      ) : (
                        <CheckCircleIcon className="h-5 w-5 text-green-500 inline" title="Blocked" />
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function SummaryCard({ label, value, color = 'text-gray-900' }) {
  return (
    <div className="bg-white shadow rounded-lg p-4">
      <dt className="text-sm font-medium text-gray-500">{label}</dt>
      <dd className={`mt-1 text-2xl font-bold ${color}`}>{value}</dd>
    </div>
  );
}
