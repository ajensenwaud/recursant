import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { format } from 'date-fns';
import { PlusIcon, DocumentDuplicateIcon, BoltIcon, TrashIcon } from '@heroicons/react/24/outline';
import { guardrailConfigs } from '../api/client';

function CreateConfigModal({ onClose, onSubmit, submitting }) {
  const [form, setForm] = useState({ name: '', description: '' });

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-md p-6">
        <h2 className="text-lg font-semibold mb-4">Create Configuration</h2>
        <form onSubmit={(e) => { e.preventDefault(); onSubmit(form); }} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
            <input type="text" required value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
              placeholder="e.g. production, staging, canary" />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
            <textarea value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm" rows={2} />
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

function EntriesPanel({ configId }) {
  const queryClient = useQueryClient();
  const { data } = useQuery({
    queryKey: ['config-entries', configId],
    queryFn: () => guardrailConfigs.entries.list(configId),
    enabled: !!configId,
  });

  const deleteMutation = useMutation({
    mutationFn: (entryId) => guardrailConfigs.entries.delete(configId, entryId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['config-entries', configId] }),
  });

  const entries = data?.entries || [];
  if (entries.length === 0) return <p className="text-sm text-gray-500">No entries. Add guardrails to this configuration.</p>;

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-gray-200 text-sm">
        <thead className="bg-gray-100">
          <tr>
            <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Guardrail</th>
            <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Enabled</th>
            <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Mode Override</th>
            <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Priority Override</th>
            <th className="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase">Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-200">
          {entries.map((e) => (
            <tr key={e.id}>
              <td className="px-3 py-2 font-mono text-xs">{e.guardrail_id?.slice(0, 12)}...</td>
              <td className="px-3 py-2">
                <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${
                  e.enabled ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                }`}>{e.enabled ? 'Yes' : 'No'}</span>
              </td>
              <td className="px-3 py-2 text-gray-600">{e.enforcement_mode_override || '-'}</td>
              <td className="px-3 py-2 text-gray-600">{e.priority_override ?? '-'}</td>
              <td className="px-3 py-2 text-right">
                <button onClick={() => deleteMutation.mutate(e.id)}
                  className="text-red-500 hover:text-red-700">
                  <TrashIcon className="h-4 w-4" />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function GuardrailConfigs() {
  const [showCreate, setShowCreate] = useState(false);
  const [expandedId, setExpandedId] = useState(null);
  const queryClient = useQueryClient();

  const { data, isLoading, error } = useQuery({
    queryKey: ['guardrail-configs'],
    queryFn: () => guardrailConfigs.list(),
  });

  const createMutation = useMutation({
    mutationFn: (data) => guardrailConfigs.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['guardrail-configs'] });
      setShowCreate(false);
    },
  });

  const activateMutation = useMutation({
    mutationFn: (id) => guardrailConfigs.activate(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['guardrail-configs'] }),
  });

  const cloneMutation = useMutation({
    mutationFn: ({ id, name }) => guardrailConfigs.clone(id, { name }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['guardrail-configs'] }),
  });

  const deleteMutation = useMutation({
    mutationFn: (id) => guardrailConfigs.delete(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['guardrail-configs'] }),
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
        <p className="text-red-800">Failed to load configurations: {error.message}</p>
      </div>
    );
  }

  const items = data?.configs || [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-gray-900">Guardrail Configurations</h1>
        <button onClick={() => setShowCreate(true)}
          className="inline-flex items-center gap-2 px-4 py-2 bg-teal-600 text-white text-sm font-medium rounded-md hover:bg-teal-700">
          <PlusIcon className="h-4 w-4" />
          Create Config
        </button>
      </div>

      <div className="bg-white shadow rounded-lg overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Name</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Description</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Updated</th>
              <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Actions</th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {items.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-6 py-12 text-center text-gray-500">
                  No configurations defined.
                </td>
              </tr>
            ) : (
              items.map((c) => (
                <>
                  <tr key={c.id} className="hover:bg-gray-50 cursor-pointer"
                    onClick={() => setExpandedId(expandedId === c.id ? null : c.id)}>
                    <td className="px-6 py-4 font-medium text-gray-900">{c.name}</td>
                    <td className="px-6 py-4 text-sm text-gray-500">{c.description || '-'}</td>
                    <td className="px-6 py-4">
                      <span className={`inline-flex px-2.5 py-0.5 rounded-full text-xs font-medium ${
                        c.is_active ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'
                      }`}>{c.is_active ? 'Active' : 'Inactive'}</span>
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-500">
                      {c.updated_at ? format(new Date(c.updated_at), 'MMM d, HH:mm') : '-'}
                    </td>
                    <td className="px-6 py-4 text-right">
                      <div className="flex items-center justify-end gap-2">
                        {!c.is_active && (
                          <button
                            onClick={(e) => { e.stopPropagation(); activateMutation.mutate(c.id); }}
                            className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium text-green-700 bg-green-50 rounded hover:bg-green-100"
                            title="Activate">
                            <BoltIcon className="h-3.5 w-3.5" />
                            Activate
                          </button>
                        )}
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            const name = prompt('Clone name:');
                            if (name) cloneMutation.mutate({ id: c.id, name });
                          }}
                          className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium text-teal-700 bg-teal-50 rounded hover:bg-teal-100"
                          title="Clone">
                          <DocumentDuplicateIcon className="h-3.5 w-3.5" />
                          Clone
                        </button>
                        {!c.is_active && (
                          <button
                            onClick={(e) => { e.stopPropagation(); if (confirm('Delete?')) deleteMutation.mutate(c.id); }}
                            className="px-2.5 py-1.5 text-xs font-medium text-red-600 bg-red-50 rounded hover:bg-red-100">
                            Delete
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                  {expandedId === c.id && (
                    <tr key={`${c.id}-entries`}>
                      <td colSpan={5} className="px-6 py-4 bg-gray-50 border-t border-gray-100">
                        <h4 className="text-sm font-medium text-gray-700 mb-2">Guardrail Entries</h4>
                        <EntriesPanel configId={c.id} />
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
        <CreateConfigModal
          onClose={() => setShowCreate(false)}
          onSubmit={(data) => createMutation.mutateAsync(data)}
          submitting={createMutation.isPending}
        />
      )}
    </div>
  );
}
