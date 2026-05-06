import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { format } from 'date-fns';
import { guardrails, agents as agentsApi } from '../api/client';
import { useAuth, hasMinRole } from '../hooks/useAuth';

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

export default function GuardrailDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const isAdmin = hasMinRole(user?.effective_role || 'user', 'administrator');

  const [activeTab, setActiveTab] = useState('config');
  const [testInput, setTestInput] = useState('');
  const [testAgentId, setTestAgentId] = useState('');
  const [testExpected, setTestExpected] = useState('block');

  const { data: guardrail, isLoading, error } = useQuery({
    queryKey: ['guardrail', id],
    queryFn: () => guardrails.get(id),
  });

  const { data: assignmentsData } = useQuery({
    queryKey: ['guardrail-assignments', id],
    queryFn: () => guardrails.assignments.list(id),
  });

  const { data: testRunsData } = useQuery({
    queryKey: ['guardrail-test-runs', id],
    queryFn: () => guardrails.testRuns.list(id),
  });

  const { data: agentsData } = useQuery({
    queryKey: ['active-agents-list'],
    queryFn: () => agentsApi.list({ status: 'active' }),
  });

  const activateMutation = useMutation({
    mutationFn: () => guardrails.activate(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['guardrail', id] }),
  });

  const disableMutation = useMutation({
    mutationFn: () => guardrails.disable(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['guardrail', id] }),
  });

  const deleteMutation = useMutation({
    mutationFn: () => guardrails.delete(id),
    onSuccess: () => navigate('/guardrails'),
  });

  const assignMutation = useMutation({
    mutationFn: (agentIds) => guardrails.assignments.create(id, { agent_ids: agentIds }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['guardrail-assignments', id] }),
  });

  const unassignMutation = useMutation({
    mutationFn: (assignmentId) => guardrails.assignments.delete(id, assignmentId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['guardrail-assignments', id] }),
  });

  const testMutation = useMutation({
    mutationFn: (data) => guardrails.test(id, data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['guardrail-test-runs', id] }),
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
        <p className="text-red-800">Failed to load guardrail: {error.message}</p>
      </div>
    );
  }

  const g = guardrail;
  const assignments = assignmentsData?.assignments || [];
  const testRuns = testRunsData?.test_runs || [];
  const activeAgents = agentsData?.agents || [];

  function handleRunTest() {
    if (!testInput.trim() || !testAgentId) return;
    testMutation.mutate({
      agent_id: testAgentId,
      test_inputs: [{ input: testInput, expected_action: testExpected }],
    });
    setTestInput('');
  }

  function handleAssignAgent(agentId) {
    assignMutation.mutate([agentId]);
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">{g.name}</h1>
          <p className="text-sm text-gray-500 mt-1">{g.description}</p>
        </div>
        <div className="flex items-center gap-3">
          <span className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-medium ${STATUS_BADGES[g.status] || ''}`}>
            {g.status}
          </span>
          {isAdmin && g.status === 'draft' && (
            <button
              onClick={() => activateMutation.mutate()}
              disabled={activateMutation.isPending}
              className="px-4 py-2 text-sm font-medium text-white bg-green-600 rounded-md hover:bg-green-700 disabled:opacity-50"
            >
              {activateMutation.isPending ? 'Activating...' : 'Activate'}
            </button>
          )}
          {isAdmin && g.status === 'active' && (
            <button
              onClick={() => disableMutation.mutate()}
              disabled={disableMutation.isPending}
              className="px-4 py-2 text-sm font-medium text-white bg-yellow-600 rounded-md hover:bg-yellow-700 disabled:opacity-50"
            >
              {disableMutation.isPending ? 'Disabling...' : 'Disable'}
            </button>
          )}
          {isAdmin && (
            <button
              onClick={() => { if (confirm('Delete this guardrail?')) deleteMutation.mutate(); }}
              className="px-4 py-2 text-sm font-medium text-red-700 bg-red-50 border border-red-200 rounded-md hover:bg-red-100"
            >
              Delete
            </button>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200">
        <nav className="flex -mb-px space-x-8">
          {['config', 'assignments', 'test', 'history'].map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`py-3 px-1 text-sm font-medium border-b-2 ${
                activeTab === tab
                  ? 'border-teal-500 text-teal-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              {tab.charAt(0).toUpperCase() + tab.slice(1)}
            </button>
          ))}
        </nav>
      </div>

      {/* Config tab */}
      {activeTab === 'config' && (
        <div className="bg-white shadow rounded-lg p-6 space-y-4">
          <div className="grid grid-cols-2 gap-6">
            <div>
              <dt className="text-sm font-medium text-gray-500">Type</dt>
              <dd className="mt-1 text-sm text-gray-900">{TYPE_LABELS[g.type] || g.type}</dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-gray-500">Mechanism</dt>
              <dd className="mt-1 text-sm text-gray-900">{MECHANISM_LABELS[g.mechanism] || g.mechanism}</dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-gray-500">Enforcement Mode</dt>
              <dd className="mt-1 text-sm text-gray-900 capitalize">{g.enforcement_mode}</dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-gray-500">Scope</dt>
              <dd className="mt-1 text-sm text-gray-900">
                {g.scope === 'all_agents' ? 'All Agents' : 'Specific Agents'}
              </dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-gray-500">Priority</dt>
              <dd className="mt-1 text-sm text-gray-900">{g.priority}</dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-gray-500">Version</dt>
              <dd className="mt-1 text-sm text-gray-900">{g.version || '-'}</dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-gray-500">Created By</dt>
              <dd className="mt-1 text-sm text-gray-900">{g.created_by || '-'}</dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-gray-500">Approved By</dt>
              <dd className="mt-1 text-sm text-gray-900">{g.approved_by || '-'}</dd>
            </div>
          </div>

          <div>
            <dt className="text-sm font-medium text-gray-500 mb-2">Configuration</dt>
            <pre className="bg-gray-50 border rounded-md p-4 text-sm overflow-auto max-h-96">
              {JSON.stringify(g.config, null, 2)}
            </pre>
          </div>
        </div>
      )}

      {/* Assignments tab */}
      {activeTab === 'assignments' && (
        <div className="space-y-4">
          {isAdmin && (
            <div className="bg-white shadow rounded-lg p-4">
              <h3 className="text-sm font-medium text-gray-700 mb-2">Assign to Agent</h3>
              <div className="flex gap-2">
                <select
                  className="flex-1 px-3 py-2 border border-gray-300 rounded-md text-sm"
                  onChange={(e) => {
                    if (e.target.value) handleAssignAgent(e.target.value);
                    e.target.value = '';
                  }}
                  defaultValue=""
                >
                  <option value="" disabled>Select an agent...</option>
                  {activeAgents
                    .filter((a) => !assignments.some((as) => as.agent_id === a.id))
                    .map((a) => (
                      <option key={a.id} value={a.id}>{a.name}</option>
                    ))}
                </select>
              </div>
            </div>
          )}

          <div className="bg-white shadow rounded-lg overflow-hidden">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Agent</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Assigned</th>
                  {isAdmin && <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Actions</th>}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {assignments.length === 0 ? (
                  <tr><td colSpan={3} className="px-6 py-8 text-center text-gray-500">No assignments</td></tr>
                ) : (
                  assignments.map((a) => (
                    <tr key={a.id}>
                      <td className="px-6 py-4 text-sm text-gray-900">{a.agent_name || a.agent_id}</td>
                      <td className="px-6 py-4 text-sm text-gray-500">
                        {a.created_at ? format(new Date(a.created_at), 'MMM d, yyyy HH:mm') : '-'}
                      </td>
                      {isAdmin && (
                        <td className="px-6 py-4 text-right">
                          <button
                            onClick={() => unassignMutation.mutate(a.id)}
                            className="text-sm text-red-600 hover:text-red-800"
                          >
                            Remove
                          </button>
                        </td>
                      )}
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Test tab */}
      {activeTab === 'test' && isAdmin && (
        <div className="bg-white shadow rounded-lg p-6 space-y-4">
          <h3 className="text-lg font-medium text-gray-900">Run Test</h3>
          <div className="space-y-3">
            <div>
              <label className="block text-sm font-medium text-gray-700">Target Agent</label>
              <select
                value={testAgentId}
                onChange={(e) => setTestAgentId(e.target.value)}
                className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
              >
                <option value="">Select agent...</option>
                {activeAgents.map((a) => (
                  <option key={a.id} value={a.id}>{a.name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">Test Input</label>
              <textarea
                value={testInput}
                onChange={(e) => setTestInput(e.target.value)}
                rows={3}
                placeholder="Enter text to test against the guardrail..."
                className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">Expected Action</label>
              <select
                value={testExpected}
                onChange={(e) => setTestExpected(e.target.value)}
                className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
              >
                <option value="block">Block</option>
                <option value="pass">Pass</option>
                <option value="warn">Warn</option>
                <option value="redact">Redact</option>
              </select>
            </div>
            <button
              onClick={handleRunTest}
              disabled={testMutation.isPending || !testInput.trim() || !testAgentId}
              className="px-4 py-2 text-sm font-medium text-white bg-teal-600 rounded-md hover:bg-teal-700 disabled:opacity-50"
            >
              {testMutation.isPending ? 'Running...' : 'Run Test'}
            </button>
          </div>
        </div>
      )}

      {/* History tab */}
      {activeTab === 'history' && (
        <div className="bg-white shadow rounded-lg overflow-hidden">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Date</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Passed</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Failed</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Initiated By</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {testRuns.length === 0 ? (
                <tr><td colSpan={5} className="px-6 py-8 text-center text-gray-500">No test runs yet</td></tr>
              ) : (
                testRuns.map((run) => (
                  <tr key={run.id}>
                    <td className="px-6 py-4 text-sm text-gray-900">
                      {run.created_at ? format(new Date(run.created_at), 'MMM d, yyyy HH:mm') : '-'}
                    </td>
                    <td className="px-6 py-4">
                      <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                        run.status === 'completed' ? 'bg-green-100 text-green-800' :
                        run.status === 'failed' ? 'bg-red-100 text-red-800' :
                        'bg-yellow-100 text-yellow-800'
                      }`}>
                        {run.status}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-sm text-green-600 font-medium">{run.passed_count || 0}</td>
                    <td className="px-6 py-4 text-sm text-red-600 font-medium">{run.failed_count || 0}</td>
                    <td className="px-6 py-4 text-sm text-gray-500">{run.initiated_by || '-'}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
