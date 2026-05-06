import { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { format } from 'date-fns';
import {
  ArrowLeftIcon,
  TrashIcon,
  PlayIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  CheckCircleIcon,
  XCircleIcon,
} from '@heroicons/react/24/outline';
import { agents, securityScans, evaluations } from '../api/client';
import StatusBadge from '../components/StatusBadge';
import ConfirmDialog from '../components/ConfirmDialog';

function ScanResultDetail({ result }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="border border-gray-200 rounded-md overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-gray-50 text-left"
      >
        <div className="flex items-center gap-3">
          {result.status === 'passed' ? (
            <CheckCircleIcon className="h-5 w-5 text-green-500 flex-shrink-0" />
          ) : (
            <XCircleIcon className="h-5 w-5 text-red-500 flex-shrink-0" />
          )}
          <div>
            <span className="text-sm font-medium text-gray-900">
              {result.test_case_id}
            </span>
            <span className="text-sm text-gray-500 ml-2">
              {result.scan_type?.replace(/_/g, ' ')}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {result.is_blocking && (
            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-red-50 text-red-700 border border-red-200">
              BLOCKING
            </span>
          )}
          <StatusBadge status={result.severity} />
          <StatusBadge status={result.status} />
          {expanded ? (
            <ChevronDownIcon className="h-4 w-4 text-gray-400" />
          ) : (
            <ChevronRightIcon className="h-4 w-4 text-gray-400" />
          )}
        </div>
      </button>

      {expanded && (
        <div className="px-4 pb-4 space-y-3 border-t border-gray-100 bg-gray-50">
          <div className="pt-3">
            <h4 className="text-xs font-semibold text-gray-500 uppercase mb-1">Input Sent to Agent</h4>
            <pre className="text-sm text-gray-800 bg-white border border-gray-200 rounded p-3 whitespace-pre-wrap break-words">
              {result.input_payload}
            </pre>
          </div>

          <div>
            <h4 className="text-xs font-semibold text-gray-500 uppercase mb-1">Agent Response</h4>
            <pre className="text-sm text-gray-800 bg-white border border-gray-200 rounded p-3 whitespace-pre-wrap break-words max-h-48 overflow-y-auto">
              {result.agent_response || 'No response received'}
            </pre>
          </div>

          <div>
            <h4 className="text-xs font-semibold text-gray-500 uppercase mb-1">Expected Behavior</h4>
            <p className="text-sm text-gray-700 bg-green-50 border border-green-200 rounded p-3">
              {result.expected_behavior}
            </p>
          </div>

          {result.actual_behavior && (
            <div>
              <h4 className="text-xs font-semibold text-gray-500 uppercase mb-1">Actual Behavior</h4>
              <p className="text-sm text-gray-700 bg-yellow-50 border border-yellow-200 rounded p-3">
                {result.actual_behavior}
              </p>
            </div>
          )}

          {result.remediation_guidance && (
            <div>
              <h4 className="text-xs font-semibold text-gray-500 uppercase mb-1">Remediation Guidance</h4>
              <p className="text-sm text-gray-700 bg-blue-50 border border-blue-200 rounded p-3">
                {result.remediation_guidance}
              </p>
            </div>
          )}

          {result.execution_time_ms != null && (
            <p className="text-xs text-gray-400">
              Execution time: {result.execution_time_ms}ms
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function EvalResultDetail({ result }) {
  const [expanded, setExpanded] = useState(false);
  const passed = result.passed;
  const scorePercent = result.score != null ? (result.score * 100).toFixed(1) : null;
  const thresholdPercent = result.test_case?.passing_threshold != null
    ? (result.test_case.passing_threshold * 100).toFixed(1)
    : null;

  return (
    <div className="border border-gray-200 rounded-md overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-gray-50 text-left"
      >
        <div className="flex items-center gap-3">
          {passed ? (
            <CheckCircleIcon className="h-5 w-5 text-green-500 flex-shrink-0" />
          ) : (
            <XCircleIcon className="h-5 w-5 text-red-500 flex-shrink-0" />
          )}
          <div>
            <span className="text-sm font-medium text-gray-900">
              {result.test_case?.name || result.test_case_id}
            </span>
            {result.test_case?.category && (
              <span className="ml-2 inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-600 border border-gray-200">
                {result.test_case.category}
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {scorePercent != null && (
            <span className={`text-sm font-medium ${passed ? 'text-green-600' : 'text-red-600'}`}>
              {scorePercent}%
              {thresholdPercent != null && (
                <span className="text-gray-400 font-normal"> / {thresholdPercent}%</span>
              )}
            </span>
          )}
          {result.test_case?.is_blocking && (
            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-red-50 text-red-700 border border-red-200">
              BLOCKING
            </span>
          )}
          {expanded ? (
            <ChevronDownIcon className="h-4 w-4 text-gray-400" />
          ) : (
            <ChevronRightIcon className="h-4 w-4 text-gray-400" />
          )}
        </div>
      </button>

      {expanded && (
        <div className="px-4 pb-4 space-y-3 border-t border-gray-100 bg-gray-50">
          {result.input_sent && (
            <div className="pt-3">
              <h4 className="text-xs font-semibold text-gray-500 uppercase mb-1">Input Sent to Agent</h4>
              <pre className="text-sm text-gray-800 bg-white border border-gray-200 rounded p-3 whitespace-pre-wrap break-words">
                {result.input_sent}
              </pre>
            </div>
          )}

          {result.agent_response && (
            <div>
              <h4 className="text-xs font-semibold text-gray-500 uppercase mb-1">Agent Response</h4>
              <pre className="text-sm text-gray-800 bg-white border border-gray-200 rounded p-3 whitespace-pre-wrap break-words max-h-48 overflow-y-auto">
                {result.agent_response}
              </pre>
            </div>
          )}

          {result.judge_reasoning && (
            <div>
              <h4 className="text-xs font-semibold text-gray-500 uppercase mb-1">Judge Reasoning</h4>
              <p className="text-sm text-gray-700 bg-blue-50 border border-blue-200 rounded p-3">
                {result.judge_reasoning}
              </p>
            </div>
          )}

          {result.criteria_scores && Object.keys(result.criteria_scores).length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-gray-500 uppercase mb-1">Criteria Scores</h4>
              <div className="bg-white border border-gray-200 rounded p-3 space-y-2">
                {Object.entries(result.criteria_scores).map(([criterion, score]) => (
                  <div key={criterion} className="flex items-center gap-3">
                    <span className="text-sm text-gray-700 w-40 flex-shrink-0">{criterion}</span>
                    <div className="flex-1 bg-gray-200 rounded-full h-2">
                      <div
                        className={`h-2 rounded-full ${score >= 0.7 ? 'bg-green-500' : score >= 0.4 ? 'bg-yellow-500' : 'bg-red-500'}`}
                        style={{ width: `${Math.min(score * 100, 100)}%` }}
                      />
                    </div>
                    <span className="text-sm text-gray-600 w-14 text-right">
                      {(score * 100).toFixed(0)}%
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {result.case_results && result.case_results.length > 1 && (
            <div>
              <h4 className="text-xs font-semibold text-gray-500 uppercase mb-1">
                Per-Case Breakdown ({result.case_results.length} cases)
              </h4>
              <div className="space-y-2">
                {result.case_results.map((cr, idx) => (
                  <div key={idx} className="bg-white border border-gray-200 rounded p-3 space-y-2">
                    {cr.input_sent && (
                      <div>
                        <span className="text-xs font-semibold text-gray-500">Input:</span>
                        <pre className="text-sm text-gray-800 whitespace-pre-wrap break-words mt-1">
                          {cr.input_sent}
                        </pre>
                      </div>
                    )}
                    {cr.agent_response && (
                      <div>
                        <span className="text-xs font-semibold text-gray-500">Response:</span>
                        <pre className="text-sm text-gray-800 whitespace-pre-wrap break-words mt-1 max-h-32 overflow-y-auto">
                          {cr.agent_response}
                        </pre>
                      </div>
                    )}
                    <div className="flex items-center gap-4 text-xs text-gray-500">
                      {cr.score != null && <span>Score: {(cr.score * 100).toFixed(1)}%</span>}
                      {cr.passed != null && (
                        <span className={cr.passed ? 'text-green-600' : 'text-red-600'}>
                          {cr.passed ? 'Passed' : 'Failed'}
                        </span>
                      )}
                    </div>
                    {cr.reasoning && (
                      <p className="text-xs text-gray-600 italic">{cr.reasoning}</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="flex gap-4 text-xs text-gray-400">
            {result.agent_latency_ms != null && (
              <span>Agent latency: {result.agent_latency_ms}ms</span>
            )}
            {result.judge_latency_ms != null && (
              <span>Judge latency: {result.judge_latency_ms}ms</span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function ProgressBar({ label, completed, total, status }) {
  const progress = total > 0 ? Math.round((completed / total) * 100) : 0;
  const isIndeterminate = total === 0 || (completed === 0 && (status === 'pending' || status === 'running'));

  return (
    <div className="border border-teal-200 bg-teal-50 rounded-lg p-4 space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-teal-800">{label}</span>
        <span className="text-sm text-teal-600">
          {total > 0 ? `${completed} of ${total} tests` : 'Starting...'}
        </span>
      </div>
      <div className="w-full bg-teal-100 rounded-full h-2.5 overflow-hidden">
        {isIndeterminate ? (
          <div className="h-2.5 rounded-full bg-teal-500 animate-pulse w-full opacity-40" />
        ) : (
          <div
            className="h-2.5 rounded-full bg-teal-500 transition-all duration-500 ease-out"
            style={{ width: `${progress}%` }}
          />
        )}
      </div>
      {total > 0 && (
        <p className="text-xs text-teal-600">
          Running test {Math.min(completed + 1, total)} of {total}... ({progress}% complete)
        </p>
      )}
    </div>
  );
}

function EvalCard({ agentId, evaluation }) {
  const [expanded, setExpanded] = useState(false);

  const { data: evalDetail } = useQuery({
    queryKey: ['eval-detail', agentId, evaluation.id],
    queryFn: () => evaluations.get(agentId, evaluation.id),
    enabled: expanded,
  });

  const results = evalDetail?.results || [];
  const failedResults = results.filter((r) => !r.passed);
  const passedResults = results.filter((r) => r.passed);

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-gray-50 text-left"
      >
        <div className="flex items-center gap-4">
          <div>
            <p className="text-sm font-medium text-gray-900">
              {evaluation.suite_name && (
                <span className="mr-2">{evaluation.suite_name}</span>
              )}
              <span className="text-gray-500 font-normal">
                {evaluation.created_at
                  ? format(new Date(evaluation.created_at), 'MMM d, yyyy HH:mm')
                  : 'Unknown date'}
              </span>
            </p>
            <p className="text-xs text-gray-500">
              {evaluation.triggered_by === 'automatic' ? 'Auto-triggered' : 'Manually triggered'}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {evaluation.status === 'completed' && (
            <>
              <span className="text-sm text-gray-600">
                <span className="text-green-600 font-medium">{evaluation.passed_count}</span>
                {' / '}
                <span className="font-medium">{evaluation.total_tests}</span>
                {' passed'}
              </span>
              {evaluation.weighted_score != null && (
                <span className="text-sm font-medium text-gray-700">
                  {(evaluation.weighted_score * 100).toFixed(1)}%
                </span>
              )}
            </>
          )}
          {evaluation.all_blocking_passed === false && evaluation.status === 'completed' && (
            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-red-50 text-red-700 border border-red-200">
              BLOCKING FAILURES
            </span>
          )}
          <StatusBadge status={evaluation.status} />
          {expanded ? (
            <ChevronDownIcon className="h-4 w-4 text-gray-400" />
          ) : (
            <ChevronRightIcon className="h-4 w-4 text-gray-400" />
          )}
        </div>
      </button>

      {expanded && (
        <div className="border-t border-gray-200 bg-gray-50 p-4">
          {results.length > 0 ? (
            <div className="space-y-2">
              {failedResults.map((result) => (
                <EvalResultDetail key={result.id} result={result} />
              ))}
              {passedResults.map((result) => (
                <EvalResultDetail key={result.id} result={result} />
              ))}
            </div>
          ) : (
            <p className="text-sm text-gray-500">Loading evaluation results...</p>
          )}
        </div>
      )}
    </div>
  );
}

function ScanCard({ agentId, scan }) {
  const [expanded, setExpanded] = useState(false);

  const { data: scanDetail } = useQuery({
    queryKey: ['scan-detail', agentId, scan.id],
    queryFn: () => securityScans.get(agentId, scan.id),
    enabled: expanded,
  });

  const results = scanDetail?.results || [];
  const failedResults = results.filter((r) => r.status === 'failed');
  const passedResults = results.filter((r) => r.status === 'passed');

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-gray-50 text-left"
      >
        <div className="flex items-center gap-4">
          <div>
            <p className="text-sm font-medium text-gray-900">
              {scan.created_at
                ? format(new Date(scan.created_at), 'MMM d, yyyy HH:mm')
                : 'Unknown date'}
            </p>
            <p className="text-xs text-gray-500">
              {scan.triggered_by === 'automatic' ? 'Auto-triggered on submit' : 'Manually triggered'}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {scan.status === 'completed' && (
            <span className="text-sm text-gray-600">
              <span className="text-green-600 font-medium">{scan.passed_count}</span>
              {' / '}
              <span className="font-medium">{scan.total_tests}</span>
              {' passed'}
            </span>
          )}
          {scan.all_blocking_passed === false && scan.status === 'completed' && (
            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-red-50 text-red-700 border border-red-200">
              BLOCKING FAILURES
            </span>
          )}
          <StatusBadge status={scan.status} />
          {expanded ? (
            <ChevronDownIcon className="h-4 w-4 text-gray-400" />
          ) : (
            <ChevronRightIcon className="h-4 w-4 text-gray-400" />
          )}
        </div>
      </button>

      {expanded && (
        <div className="border-t border-gray-200 bg-gray-50 p-4">
          {results.length > 0 ? (
            <div className="space-y-2">
              {/* Show failed results first */}
              {failedResults.map((result) => (
                <ScanResultDetail key={result.id} result={result} />
              ))}
              {passedResults.map((result) => (
                <ScanResultDetail key={result.id} result={result} />
              ))}
            </div>
          ) : (
            <p className="text-sm text-gray-500">Loading scan results...</p>
          )}
        </div>
      )}
    </div>
  );
}

export default function SubmissionDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [scanPolling, setScanPolling] = useState(false);
  const [evalPolling, setEvalPolling] = useState(false);

  const { data: agent, isLoading, error } = useQuery({
    queryKey: ['agent', id],
    queryFn: () => agents.get(id),
  });

  const { data: scansData } = useQuery({
    queryKey: ['agent-scans', id],
    queryFn: () => securityScans.list(id),
    enabled: !!agent,
    refetchInterval: scanPolling ? 2000 : false,
  });

  const { data: evalsData } = useQuery({
    queryKey: ['agent-evaluations', id],
    queryFn: () => evaluations.list(id),
    enabled: !!agent,
    refetchInterval: evalPolling ? 2000 : false,
  });

  const deleteMutation = useMutation({
    mutationFn: () => agents.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents'] });
      navigate('/submissions');
    },
  });

  const triggerScanMutation = useMutation({
    mutationFn: () => securityScans.trigger(id),
    onSuccess: () => {
      setScanPolling(true);
      queryClient.invalidateQueries({ queryKey: ['agent-scans', id] });
      queryClient.invalidateQueries({ queryKey: ['agent', id] });
    },
  });

  const triggerEvalMutation = useMutation({
    mutationFn: () => evaluations.trigger(id),
    onSuccess: () => {
      setEvalPolling(true);
      queryClient.invalidateQueries({ queryKey: ['agent-evaluations', id] });
      queryClient.invalidateQueries({ queryKey: ['agent', id] });
    },
  });

  const scans = scansData?.scans || [];
  const evals = evalsData?.evaluations || [];

  const activeScan = scans.find((s) => s.status === 'pending' || s.status === 'running');
  const activeEvals = evals.filter((e) => e.status === 'pending' || e.status === 'running');
  const activeEval = activeEvals.length > 0 ? {
    status: activeEvals.some((e) => e.status === 'running') ? 'running' : 'pending',
    passed_count: activeEvals.reduce((sum, e) => sum + (e.passed_count || 0), 0),
    failed_count: activeEvals.reduce((sum, e) => sum + (e.failed_count || 0), 0),
    error_count: activeEvals.reduce((sum, e) => sum + (e.error_count || 0), 0),
    total_tests: activeEvals.reduce((sum, e) => sum + (e.total_tests || 0), 0),
  } : null;

  // Stop polling and refresh agent when scan/eval completes
  useEffect(() => {
    if (scanPolling && !activeScan && scansData) {
      setScanPolling(false);
      queryClient.invalidateQueries({ queryKey: ['agent', id] });
    }
  }, [activeScan, scanPolling, scansData, queryClient, id]);

  useEffect(() => {
    if (evalPolling && !activeEval && evalsData) {
      setEvalPolling(false);
      queryClient.invalidateQueries({ queryKey: ['agent', id] });
    }
  }, [activeEval, evalPolling, evalsData, queryClient, id]);

  // Also start polling if we load the page and there's already an in-progress scan/eval
  useEffect(() => {
    if (activeScan && !scanPolling) setScanPolling(true);
  }, [activeScan, scanPolling]);

  useEffect(() => {
    if (activeEval && !evalPolling) setEvalPolling(true);
  }, [activeEval, evalPolling]);

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
        Failed to load submission: {error.message}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link
            to="/submissions"
            className="text-gray-400 hover:text-gray-600"
          >
            <ArrowLeftIcon className="h-5 w-5" />
          </Link>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">{agent.name}</h1>
            <p className="text-sm text-gray-500">Version {agent.version}</p>
          </div>
          <StatusBadge status={agent.status} />
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => triggerScanMutation.mutate()}
            disabled={triggerScanMutation.isPending || !!activeScan}
            className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50"
          >
            <PlayIcon className="h-4 w-4" />
            {activeScan ? 'Scan Running...' : 'Run Security Scan'}
          </button>
          <button
            onClick={() => triggerEvalMutation.mutate()}
            disabled={triggerEvalMutation.isPending || !!activeEval}
            className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50"
          >
            <PlayIcon className="h-4 w-4" />
            {activeEval ? 'Evaluation Running...' : 'Run Evaluation'}
          </button>
          <button
            onClick={() => setDeleteOpen(true)}
            className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-md hover:bg-red-700"
          >
            <TrashIcon className="h-4 w-4" />
            Delete
          </button>
        </div>
      </div>

      {/* Agent Details */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white shadow rounded-lg p-6">
          <h2 className="text-lg font-medium text-gray-900 mb-4">Details</h2>
          <dl className="space-y-3">
            <div className="flex justify-between">
              <dt className="text-sm text-gray-500">Owner</dt>
              <dd className="text-sm text-gray-900">{agent.owner_id}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-sm text-gray-500">Team</dt>
              <dd className="text-sm text-gray-900">{agent.team_id}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-sm text-gray-500">Risk Tier</dt>
              <dd className="text-sm text-gray-900 capitalize">{agent.risk_tier}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-sm text-gray-500">Classification</dt>
              <dd className="text-sm text-gray-900 capitalize">{agent.classification}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-sm text-gray-500">Created</dt>
              <dd className="text-sm text-gray-900">
                {agent.created_at
                  ? format(new Date(agent.created_at), 'MMM d, yyyy HH:mm')
                  : '-'}
              </dd>
            </div>
          </dl>
        </div>

        <div className="bg-white shadow rounded-lg p-6">
          <h2 className="text-lg font-medium text-gray-900 mb-4">Endpoint</h2>
          <dl className="space-y-3">
            <div className="flex justify-between">
              <dt className="text-sm text-gray-500">Type</dt>
              <dd className="text-sm text-gray-900">{agent.endpoint?.type}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-sm text-gray-500">URL</dt>
              <dd className="text-sm text-gray-900 break-all">{agent.endpoint?.url}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-sm text-gray-500">Auth Method</dt>
              <dd className="text-sm text-gray-900">{agent.endpoint?.auth_method}</dd>
            </div>
          </dl>
        </div>
      </div>

      {/* Capabilities */}
      <div className="bg-white shadow rounded-lg p-6">
        <h2 className="text-lg font-medium text-gray-900 mb-4">Capabilities</h2>
        {agent.capabilities?.length > 0 ? (
          <div className="space-y-3">
            {agent.capabilities.map((cap, i) => (
              <div key={i} className="border border-gray-200 rounded-md p-3">
                <h3 className="font-medium text-gray-900">{cap.name}</h3>
                <p className="text-sm text-gray-500">{cap.description}</p>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-gray-500">No capabilities defined</p>
        )}
      </div>

      {/* Security Scans */}
      <div className="bg-white shadow rounded-lg p-6">
        <h2 className="text-lg font-medium text-gray-900 mb-4">Security Scans</h2>
        {activeScan && (
          <div className="mb-4">
            <ProgressBar
              label="Security Scan in Progress"
              completed={(activeScan.passed_count || 0) + (activeScan.failed_count || 0) + (activeScan.error_count || 0) + (activeScan.skipped_count || 0)}
              total={activeScan.total_tests || 0}
              status={activeScan.status}
            />
          </div>
        )}
        {scans.filter((s) => s.status !== 'pending' && s.status !== 'running').length > 0 ? (
          <div className="space-y-3">
            {scans.filter((s) => s.status !== 'pending' && s.status !== 'running').map((scan) => (
              <ScanCard key={scan.id} agentId={id} scan={scan} />
            ))}
          </div>
        ) : !activeScan ? (
          <p className="text-sm text-gray-500">No security scans yet</p>
        ) : null}
      </div>

      {/* Evaluations */}
      <div className="bg-white shadow rounded-lg p-6">
        <h2 className="text-lg font-medium text-gray-900 mb-4">Evaluations</h2>
        {activeEval && (
          <div className="mb-4">
            <ProgressBar
              label="Evaluation in Progress"
              completed={(activeEval.passed_count || 0) + (activeEval.failed_count || 0) + (activeEval.error_count || 0)}
              total={activeEval.total_tests || 0}
              status={activeEval.status}
            />
          </div>
        )}
        {evals.filter((e) => e.status !== 'pending' && e.status !== 'running').length > 0 ? (
          <div className="space-y-3">
            {evals.filter((e) => e.status !== 'pending' && e.status !== 'running').map((evaluation) => (
              <EvalCard key={evaluation.id} agentId={id} evaluation={evaluation} />
            ))}
          </div>
        ) : !activeEval ? (
          <p className="text-sm text-gray-500">No evaluations yet</p>
        ) : null}
      </div>

      {/* Delete Confirmation */}
      <ConfirmDialog
        open={deleteOpen}
        onClose={() => setDeleteOpen(false)}
        onConfirm={() => deleteMutation.mutate()}
        title="Delete Submission"
        message={`Are you sure you want to delete "${agent.name}"? This action cannot be undone.`}
        confirmText="Delete"
        confirmStyle="danger"
        loading={deleteMutation.isPending}
      />
    </div>
  );
}
