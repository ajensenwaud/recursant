import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { format } from 'date-fns';
import { CheckIcon, XMarkIcon, PlusIcon } from '@heroicons/react/24/outline';
import { meshTools } from '../api/client';
import StatusBadge from '../components/StatusBadge';

function ToolActionModal({ tool, action, onClose, onSubmit }) {
  const [justification, setJustification] = useState('');
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!justification.trim()) {
      alert('Justification is required');
      return;
    }
    setSubmitting(true);
    try {
      await onSubmit(justification);
      onClose();
    } catch (error) {
      alert(error.message);
    } finally {
      setSubmitting(false);
    }
  }

  const isApprove = action === 'approve';

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="flex items-center justify-center min-h-screen p-4">
        <div className="fixed inset-0 bg-black bg-opacity-25" onClick={onClose} />
        <div className="relative bg-white rounded-lg shadow-xl max-w-md w-full p-6">
          <h2 className="text-lg font-medium text-gray-900 mb-4">
            {isApprove ? 'Approve' : 'Revoke'} Tool
          </h2>
          <p className="text-sm text-gray-500 mb-4">
            You are about to {isApprove ? 'approve' : 'revoke'}{' '}
            <strong>{tool.name}</strong>. Please provide a justification.
          </p>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700">
                Justification (required)
              </label>
              <textarea
                value={justification}
                onChange={(e) => setJustification(e.target.value)}
                required
                rows={4}
                placeholder="Enter your justification..."
                className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-teal-500 focus:border-teal-500"
              />
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
                disabled={submitting}
                className={`px-4 py-2 text-sm font-medium text-white rounded-md disabled:opacity-50 ${
                  isApprove ? 'bg-green-600 hover:bg-green-700' : 'bg-red-600 hover:bg-red-700'
                }`}
              >
                {submitting ? 'Submitting...' : isApprove ? 'Approve' : 'Revoke'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

function CreateToolModal({ onClose, onCreate }) {
  const [form, setForm] = useState({
    name: '',
    description: '',
    endpoint_url: '',
    http_method: 'POST',
    mcp_server_url: '',
    mcp_server_name: '',
    mcp_server_description: '',
    parameters_schema: '',
    backend_services: '',
  });
  const [submitting, setSubmitting] = useState(false);

  function handleChange(field, value) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!form.name.trim() || !form.endpoint_url.trim()) {
      alert('Name and endpoint URL are required');
      return;
    }
    setSubmitting(true);
    try {
      const payload = {
        name: form.name,
        description: form.description || null,
        endpoint_url: form.endpoint_url,
        http_method: form.http_method,
        mcp_server_url: form.mcp_server_url || null,
        mcp_server_name: form.mcp_server_name || null,
        mcp_server_description: form.mcp_server_description || null,
      };
      if (form.parameters_schema.trim()) {
        try { payload.parameters_schema = JSON.parse(form.parameters_schema); } catch { alert('Invalid JSON in parameters schema'); setSubmitting(false); return; }
      }
      if (form.backend_services.trim()) {
        try { payload.backend_services = JSON.parse(form.backend_services); } catch { alert('Invalid JSON in backend services'); setSubmitting(false); return; }
      }
      await onCreate(payload);
      onClose();
    } catch (error) {
      alert(error.message);
    } finally {
      setSubmitting(false);
    }
  }

  const inputClass = 'mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-teal-500 focus:border-teal-500 text-sm';

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="flex items-center justify-center min-h-screen p-4">
        <div className="fixed inset-0 bg-black bg-opacity-25" onClick={onClose} />
        <div className="relative bg-white rounded-lg shadow-xl max-w-lg w-full p-6 max-h-[90vh] overflow-y-auto">
          <h2 className="text-lg font-medium text-gray-900 mb-4">Register New Tool</h2>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700">Name *</label>
              <input type="text" value={form.name} onChange={(e) => handleChange('name', e.target.value)} required className={inputClass} />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">Description</label>
              <textarea value={form.description} onChange={(e) => handleChange('description', e.target.value)} rows={2} className={inputClass} />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700">Endpoint URL *</label>
                <input type="text" value={form.endpoint_url} onChange={(e) => handleChange('endpoint_url', e.target.value)} required className={inputClass} />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">HTTP Method</label>
                <select value={form.http_method} onChange={(e) => handleChange('http_method', e.target.value)} className={inputClass}>
                  {['GET', 'POST', 'PUT', 'PATCH', 'DELETE'].map((m) => <option key={m}>{m}</option>)}
                </select>
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">MCP Server URL</label>
              <input type="text" value={form.mcp_server_url} onChange={(e) => handleChange('mcp_server_url', e.target.value)} placeholder="http://mcp-server:8080/sse" className={inputClass} />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700">MCP Server Name</label>
                <input type="text" value={form.mcp_server_name} onChange={(e) => handleChange('mcp_server_name', e.target.value)} className={inputClass} />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">MCP Server Description</label>
                <input type="text" value={form.mcp_server_description} onChange={(e) => handleChange('mcp_server_description', e.target.value)} className={inputClass} />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">Parameters Schema (JSON)</label>
              <textarea value={form.parameters_schema} onChange={(e) => handleChange('parameters_schema', e.target.value)} rows={3} placeholder='{"type": "object", ...}' className={`${inputClass} font-mono text-xs`} />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">Backend Services (JSON)</label>
              <textarea value={form.backend_services} onChange={(e) => handleChange('backend_services', e.target.value)} rows={3} placeholder='[{"url": "...", "method": "POST", "description": "..."}]' className={`${inputClass} font-mono text-xs`} />
            </div>
            <div className="flex justify-end gap-3 pt-4">
              <button type="button" onClick={onClose} className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50">Cancel</button>
              <button type="submit" disabled={submitting} className="px-4 py-2 text-sm font-medium text-white bg-teal-600 rounded-md hover:bg-teal-700 disabled:opacity-50">
                {submitting ? 'Creating...' : 'Register Tool'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

export default function SubmittedTools() {
  const [modalState, setModalState] = useState({ open: false, tool: null, action: null });
  const [showCreate, setShowCreate] = useState(false);
  const queryClient = useQueryClient();

  const { data, isLoading, error } = useQuery({
    queryKey: ['submitted-tools'],
    queryFn: () => meshTools.list({ status: 'submitted' }),
  });

  const approveMutation = useMutation({
    mutationFn: ({ id, justification }) => meshTools.approve(id, { justification }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['submitted-tools'] });
      queryClient.invalidateQueries({ queryKey: ['approved-tools'] });
    },
  });

  const revokeMutation = useMutation({
    mutationFn: ({ id, justification }) => meshTools.revoke(id, { justification }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['submitted-tools'] }),
  });

  const createMutation = useMutation({
    mutationFn: (data) => meshTools.create(data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['submitted-tools'] }),
  });

  function openModal(tool, action) {
    setModalState({ open: true, tool, action });
  }

  function closeModal() {
    setModalState({ open: false, tool: null, action: null });
  }

  async function handleAction(justification) {
    const { tool, action } = modalState;
    if (action === 'approve') {
      await approveMutation.mutateAsync({ id: tool.id, justification });
    } else {
      await revokeMutation.mutateAsync({ id: tool.id, justification });
    }
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
        Failed to load submitted tools: {error.message}
      </div>
    );
  }

  const tools = data?.tools || [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Submitted Tools</h1>
        <button
          onClick={() => setShowCreate(true)}
          className="inline-flex items-center gap-1 px-4 py-2 text-sm font-medium text-white bg-teal-600 rounded-md hover:bg-teal-700"
        >
          <PlusIcon className="h-4 w-4" />
          Register New Tool
        </button>
      </div>

      {tools.length === 0 ? (
        <div className="bg-white shadow rounded-lg p-8 text-center text-gray-500">
          No submitted tools awaiting review
        </div>
      ) : (
        <div className="bg-white shadow rounded-lg overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Name</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">MCP Server</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Endpoint URL</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Method</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Created</th>
                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {tools.map((tool) => (
                <tr key={tool.id} className="hover:bg-gray-50">
                  <td className="px-6 py-4 whitespace-nowrap">
                    <Link to={`/mesh-tools/${tool.id}`} className="text-teal-600 hover:text-teal-800 font-medium">
                      {tool.name}
                    </Link>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {tool.mcp_server_name || '-'}
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-500 max-w-xs truncate" title={tool.endpoint_url}>
                    {tool.endpoint_url}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {tool.http_method}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {tool.created_at ? format(new Date(tool.created_at), 'MMM d, yyyy') : '-'}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right">
                    <div className="flex items-center justify-end gap-2">
                      <button
                        onClick={() => openModal(tool, 'approve')}
                        className="inline-flex items-center gap-1 px-3 py-1.5 text-sm font-medium text-white bg-green-600 rounded-md hover:bg-green-700"
                      >
                        <CheckIcon className="h-4 w-4" />
                        Approve
                      </button>
                      <button
                        onClick={() => openModal(tool, 'revoke')}
                        className="inline-flex items-center gap-1 px-3 py-1.5 text-sm font-medium text-white bg-red-600 rounded-md hover:bg-red-700"
                      >
                        <XMarkIcon className="h-4 w-4" />
                        Revoke
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {modalState.open && (
        <ToolActionModal
          tool={modalState.tool}
          action={modalState.action}
          onClose={closeModal}
          onSubmit={handleAction}
        />
      )}

      {showCreate && (
        <CreateToolModal
          onClose={() => setShowCreate(false)}
          onCreate={(data) => createMutation.mutateAsync(data)}
        />
      )}
    </div>
  );
}
