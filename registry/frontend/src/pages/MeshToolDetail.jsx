import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { format } from 'date-fns';
import { CheckIcon, XMarkIcon, PlusIcon, TrashIcon } from '@heroicons/react/24/outline';
import { meshTools, meshAudit } from '../api/client';
import StatusBadge from '../components/StatusBadge';

function AssignAgentModal({ toolId, onClose, onAssign }) {
  const [agentName, setAgentName] = useState('');
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!agentName.trim()) return;
    setSubmitting(true);
    try {
      await onAssign(agentName);
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
          <h2 className="text-lg font-medium text-gray-900 mb-4">Assign Agent</h2>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700">Agent Name</label>
              <input
                type="text"
                value={agentName}
                onChange={(e) => setAgentName(e.target.value)}
                required
                placeholder="e.g. Credit Agent"
                className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-teal-500 focus:border-teal-500"
              />
            </div>
            <div className="flex justify-end gap-3 pt-4">
              <button type="button" onClick={onClose} className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50">Cancel</button>
              <button type="submit" disabled={submitting} className="px-4 py-2 text-sm font-medium text-white bg-teal-600 rounded-md hover:bg-teal-700 disabled:opacity-50">
                {submitting ? 'Assigning...' : 'Assign'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

function ActionModal({ tool, action, onClose, onSubmit }) {
  const [justification, setJustification] = useState('');
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!justification.trim()) { alert('Justification is required'); return; }
    setSubmitting(true);
    try { await onSubmit(justification); onClose(); }
    catch (error) { alert(error.message); }
    finally { setSubmitting(false); }
  }

  const isApprove = action === 'approve';

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="flex items-center justify-center min-h-screen p-4">
        <div className="fixed inset-0 bg-black bg-opacity-25" onClick={onClose} />
        <div className="relative bg-white rounded-lg shadow-xl max-w-md w-full p-6">
          <h2 className="text-lg font-medium text-gray-900 mb-4">{isApprove ? 'Approve' : 'Revoke'} Tool</h2>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700">Justification (required)</label>
              <textarea value={justification} onChange={(e) => setJustification(e.target.value)} required rows={4} className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-teal-500 focus:border-teal-500" />
            </div>
            <div className="flex justify-end gap-3 pt-4">
              <button type="button" onClick={onClose} className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50">Cancel</button>
              <button type="submit" disabled={submitting} className={`px-4 py-2 text-sm font-medium text-white rounded-md disabled:opacity-50 ${isApprove ? 'bg-green-600 hover:bg-green-700' : 'bg-red-600 hover:bg-red-700'}`}>
                {submitting ? 'Submitting...' : isApprove ? 'Approve' : 'Revoke'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

export default function MeshToolDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [actionModal, setActionModal] = useState(null);
  const [showAssign, setShowAssign] = useState(false);

  const { data: tool, isLoading, error } = useQuery({
    queryKey: ['mesh-tool', id],
    queryFn: () => meshTools.get(id),
  });

  const { data: assignData } = useQuery({
    queryKey: ['mesh-tool-assignments', id],
    queryFn: () => meshTools.assignments.list({ tool_id: id }),
    enabled: !!tool,
  });

  const { data: auditData } = useQuery({
    queryKey: ['mesh-tool-audit', id],
    queryFn: () => meshAudit.list({ dest_agent_name: tool?.name, a2a_method: 'tools/call', per_page: 20 }),
    enabled: !!tool?.name,
  });

  const approveMutation = useMutation({
    mutationFn: (justification) => meshTools.approve(id, { justification }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['mesh-tool', id] }),
  });

  const revokeMutation = useMutation({
    mutationFn: (justification) => meshTools.revoke(id, { justification }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['mesh-tool', id] }),
  });

  const assignMutation = useMutation({
    mutationFn: (agentName) => meshTools.assignments.create({ tool_id: id, agent_name: agentName }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['mesh-tool-assignments', id] }),
  });

  const unassignMutation = useMutation({
    mutationFn: (assignmentId) => meshTools.assignments.delete(assignmentId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['mesh-tool-assignments', id] }),
  });

  if (isLoading) {
    return <div className="flex items-center justify-center h-64"><div className="spinner" /></div>;
  }

  if (error || !tool) {
    return <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-md">Tool not found</div>;
  }

  const assignments = assignData?.assignments || [];
  const auditRecords = auditData?.records || [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <h1 className="text-2xl font-bold text-gray-900">{tool.name}</h1>
          <StatusBadge status={tool.status} />
        </div>
        <div className="flex items-center gap-2">
          {tool.status === 'submitted' && (
            <>
              <button onClick={() => setActionModal('approve')} className="px-4 py-2 text-sm font-medium text-white bg-green-600 rounded-md hover:bg-green-700">Approve</button>
              <button onClick={() => setActionModal('revoke')} className="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-md hover:bg-red-700">Revoke</button>
            </>
          )}
          {tool.status === 'approved' && (
            <button onClick={() => setActionModal('revoke')} className="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-md hover:bg-red-700">Revoke</button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Tool Info */}
        <div className="bg-white shadow rounded-lg p-6">
          <h2 className="text-lg font-medium text-gray-900 mb-4">Tool Information</h2>
          <dl className="space-y-3">
            <div><dt className="text-sm font-medium text-gray-500">Description</dt><dd className="text-sm text-gray-900">{tool.description || '-'}</dd></div>
            <div><dt className="text-sm font-medium text-gray-500">Endpoint URL</dt><dd className="text-sm text-gray-900 font-mono break-all">{tool.endpoint_url}</dd></div>
            <div><dt className="text-sm font-medium text-gray-500">HTTP Method</dt><dd className="text-sm text-gray-900">{tool.http_method}</dd></div>
            {tool.parameters_schema && (
              <div><dt className="text-sm font-medium text-gray-500">Parameters Schema</dt><dd className="text-xs text-gray-900 font-mono bg-gray-50 p-2 rounded overflow-auto max-h-48">{JSON.stringify(tool.parameters_schema, null, 2)}</dd></div>
            )}
          </dl>
        </div>

        {/* MCP Server */}
        <div className="bg-white shadow rounded-lg p-6">
          <h2 className="text-lg font-medium text-gray-900 mb-4">MCP Server</h2>
          {tool.mcp_server_url ? (
            <dl className="space-y-3">
              <div><dt className="text-sm font-medium text-gray-500">Server Name</dt><dd className="text-sm text-gray-900">{tool.mcp_server_name || '-'}</dd></div>
              <div><dt className="text-sm font-medium text-gray-500">Description</dt><dd className="text-sm text-gray-900">{tool.mcp_server_description || '-'}</dd></div>
              <div><dt className="text-sm font-medium text-gray-500">SSE URL</dt><dd className="text-sm text-gray-900 font-mono break-all">{tool.mcp_server_url}</dd></div>
            </dl>
          ) : (
            <p className="text-sm text-gray-500">No MCP server configured. Tool uses direct HTTP calls.</p>
          )}
        </div>

        {/* Backend Services */}
        {tool.backend_services && tool.backend_services.length > 0 && (
          <div className="bg-white shadow rounded-lg p-6">
            <h2 className="text-lg font-medium text-gray-900 mb-4">Backend Services</h2>
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">URL</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Method</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Description</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {tool.backend_services.map((svc, i) => (
                  <tr key={i}>
                    <td className="px-4 py-2 text-sm font-mono text-gray-900 break-all">{svc.url}</td>
                    <td className="px-4 py-2 text-sm text-gray-500">{svc.method}</td>
                    <td className="px-4 py-2 text-sm text-gray-500">{svc.description}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Governance */}
        <div className="bg-white shadow rounded-lg p-6">
          <h2 className="text-lg font-medium text-gray-900 mb-4">Governance</h2>
          <dl className="space-y-3">
            <div><dt className="text-sm font-medium text-gray-500">Created At</dt><dd className="text-sm text-gray-900">{tool.created_at ? format(new Date(tool.created_at), 'MMM d, yyyy HH:mm') : '-'}</dd></div>
            {tool.approved_by && <div><dt className="text-sm font-medium text-gray-500">Approved By</dt><dd className="text-sm text-gray-900">{tool.approved_by}</dd></div>}
            {tool.approved_at && <div><dt className="text-sm font-medium text-gray-500">Approved At</dt><dd className="text-sm text-gray-900">{format(new Date(tool.approved_at), 'MMM d, yyyy HH:mm')}</dd></div>}
            {tool.revoked_by && <div><dt className="text-sm font-medium text-gray-500">Revoked By</dt><dd className="text-sm text-red-600">{tool.revoked_by}</dd></div>}
            {tool.revoked_at && <div><dt className="text-sm font-medium text-gray-500">Revoked At</dt><dd className="text-sm text-red-600">{format(new Date(tool.revoked_at), 'MMM d, yyyy HH:mm')}</dd></div>}
          </dl>
        </div>
      </div>

      {/* Assigned Agents */}
      <div className="bg-white shadow rounded-lg p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-medium text-gray-900">Assigned Agents</h2>
          <button
            onClick={() => setShowAssign(true)}
            className="inline-flex items-center gap-1 px-3 py-1.5 text-sm font-medium text-white bg-teal-600 rounded-md hover:bg-teal-700"
          >
            <PlusIcon className="h-4 w-4" />
            Assign Agent
          </button>
        </div>
        {assignments.length === 0 ? (
          <p className="text-sm text-gray-500">No agents assigned to this tool</p>
        ) : (
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Agent Name</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Assigned At</th>
                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {assignments.map((a) => (
                <tr key={a.id}>
                  <td className="px-6 py-3 text-sm text-gray-900">{a.agent_name}</td>
                  <td className="px-6 py-3 text-sm text-gray-500">{a.created_at ? format(new Date(a.created_at), 'MMM d, yyyy HH:mm') : '-'}</td>
                  <td className="px-6 py-3 text-right">
                    <button
                      onClick={() => unassignMutation.mutate(a.id)}
                      className="inline-flex items-center gap-1 px-2 py-1 text-sm text-red-600 hover:text-red-800"
                    >
                      <TrashIcon className="h-4 w-4" />
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Audit Trail */}
      <div className="bg-white shadow rounded-lg p-6">
        <h2 className="text-lg font-medium text-gray-900 mb-4">Recent Tool Calls</h2>
        {auditRecords.length === 0 ? (
          <p className="text-sm text-gray-500">No tool call audit records found</p>
        ) : (
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Time</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Source Agent</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Decision</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Outcome</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {auditRecords.map((rec) => (
                <tr key={rec.id}>
                  <td className="px-4 py-2 text-sm text-gray-500">{rec.timestamp ? format(new Date(rec.timestamp), 'MMM d HH:mm:ss') : '-'}</td>
                  <td className="px-4 py-2 text-sm text-gray-900">{rec.source_agent_name}</td>
                  <td className="px-4 py-2"><StatusBadge status={rec.decision} /></td>
                  <td className="px-4 py-2"><StatusBadge status={rec.outcome} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {actionModal && (
        <ActionModal
          tool={tool}
          action={actionModal}
          onClose={() => setActionModal(null)}
          onSubmit={async (justification) => {
            if (actionModal === 'approve') await approveMutation.mutateAsync(justification);
            else await revokeMutation.mutateAsync(justification);
          }}
        />
      )}

      {showAssign && (
        <AssignAgentModal
          toolId={id}
          onClose={() => setShowAssign(false)}
          onAssign={(agentName) => assignMutation.mutateAsync(agentName)}
        />
      )}
    </div>
  );
}
