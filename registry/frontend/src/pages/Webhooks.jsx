import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { format } from 'date-fns';
import { PlusIcon, BoltIcon, TrashIcon } from '@heroicons/react/24/outline';
import { webhooks } from '../api/client';

const TYPE_BADGES = {
  slack: 'bg-purple-100 text-purple-800',
  pagerduty: 'bg-green-100 text-green-800',
  teams: 'bg-blue-100 text-blue-800',
  generic: 'bg-gray-100 text-gray-800',
};

function CreateEndpointModal({ onClose, onSubmit, submitting }) {
  const [form, setForm] = useState({
    name: '', url: '', type: 'generic', secret: '', enabled: true,
  });

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-lg p-6">
        <h2 className="text-lg font-semibold mb-4">Create Webhook Endpoint</h2>
        <form onSubmit={(e) => { e.preventDefault(); onSubmit(form); }} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
            <input type="text" required value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm" />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">URL</label>
            <input type="url" required value={form.url}
              onChange={(e) => setForm({ ...form, url: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
              placeholder="https://hooks.slack.com/..." />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Type</label>
              <select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm">
                <option value="generic">Generic</option>
                <option value="slack">Slack</option>
                <option value="pagerduty">PagerDuty</option>
                <option value="teams">Teams</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Secret (optional)</label>
              <input type="password" value={form.secret}
                onChange={(e) => setForm({ ...form, secret: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm" />
            </div>
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

function SubscriptionPanel({ endpointId }) {
  const queryClient = useQueryClient();
  const { data } = useQuery({
    queryKey: ['webhook-subscriptions', endpointId],
    queryFn: () => webhooks.subscriptions.list({ webhook_id: endpointId }),
    enabled: !!endpointId,
  });

  const deleteMutation = useMutation({
    mutationFn: (id) => webhooks.subscriptions.delete(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['webhook-subscriptions', endpointId] }),
  });

  const subs = data?.subscriptions || [];

  return (
    <div className="space-y-2">
      {subs.length === 0 ? (
        <p className="text-sm text-gray-500">No subscriptions configured.</p>
      ) : (
        subs.map((s) => (
          <div key={s.id} className="flex items-center justify-between py-2 px-3 bg-gray-50 rounded text-sm">
            <div>
              <span className="font-medium">
                {s.guardrail_id ? `Guardrail: ${s.guardrail_id.slice(0, 8)}...` :
                 s.metric_id ? `Metric: ${s.metric_id.slice(0, 8)}...` : 'All events'}
              </span>
              <span className="text-gray-500 ml-2">
                [{(s.trigger_on_actions || []).join(', ')}]
              </span>
              <span className="text-gray-400 ml-2">
                cooldown: {s.cooldown_seconds}s
              </span>
            </div>
            <button onClick={() => deleteMutation.mutate(s.id)}
              className="text-red-500 hover:text-red-700">
              <TrashIcon className="h-4 w-4" />
            </button>
          </div>
        ))
      )}
    </div>
  );
}

function DeliveryLogPanel() {
  const { data } = useQuery({
    queryKey: ['webhook-delivery-logs'],
    queryFn: () => webhooks.deliveryLogs.list({ per_page: 20 }),
  });

  const logs = data?.delivery_logs || [];

  if (logs.length === 0) return <p className="text-sm text-gray-500 py-4">No deliveries yet.</p>;

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-gray-200 text-sm">
        <thead className="bg-gray-50">
          <tr>
            <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
            <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">HTTP</th>
            <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Attempt</th>
            <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Error</th>
            <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Sent</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-200">
          {logs.map((l) => (
            <tr key={l.id}>
              <td className="px-4 py-2">
                <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${
                  l.status === 'success' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                }`}>{l.status}</span>
              </td>
              <td className="px-4 py-2 text-gray-600">{l.response_status || '-'}</td>
              <td className="px-4 py-2 text-gray-600">{l.attempt}</td>
              <td className="px-4 py-2 text-gray-500 max-w-xs truncate">{l.error_message || '-'}</td>
              <td className="px-4 py-2 text-gray-500">
                {l.sent_at ? format(new Date(l.sent_at), 'MMM d, HH:mm:ss') : '-'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function Webhooks() {
  const [showCreate, setShowCreate] = useState(false);
  const [expandedId, setExpandedId] = useState(null);
  const [showLogs, setShowLogs] = useState(false);
  const queryClient = useQueryClient();

  const { data, isLoading, error } = useQuery({
    queryKey: ['webhooks'],
    queryFn: () => webhooks.list(),
  });

  const createMutation = useMutation({
    mutationFn: (data) => webhooks.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['webhooks'] });
      setShowCreate(false);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id) => webhooks.delete(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['webhooks'] }),
  });

  const testMutation = useMutation({
    mutationFn: (id) => webhooks.test(id),
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
        <p className="text-red-800">Failed to load webhooks: {error.message}</p>
      </div>
    );
  }

  const items = data?.endpoints || [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-gray-900">Webhooks</h1>
        <div className="flex gap-3">
          <button onClick={() => setShowLogs(!showLogs)}
            className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200">
            {showLogs ? 'Hide Logs' : 'Delivery Log'}
          </button>
          <button onClick={() => setShowCreate(true)}
            className="inline-flex items-center gap-2 px-4 py-2 bg-teal-600 text-white text-sm font-medium rounded-md hover:bg-teal-700">
            <PlusIcon className="h-4 w-4" />
            Add Endpoint
          </button>
        </div>
      </div>

      {showLogs && (
        <div className="bg-white shadow rounded-lg p-4">
          <h3 className="text-sm font-medium text-gray-700 mb-3">Recent Deliveries</h3>
          <DeliveryLogPanel />
        </div>
      )}

      <div className="bg-white shadow rounded-lg overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Name</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Type</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">URL</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Created</th>
              <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Actions</th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {items.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-6 py-12 text-center text-gray-500">
                  No webhook endpoints configured.
                </td>
              </tr>
            ) : (
              items.map((ep) => (
                <>
                  <tr key={ep.id} className="hover:bg-gray-50 cursor-pointer"
                    onClick={() => setExpandedId(expandedId === ep.id ? null : ep.id)}>
                    <td className="px-6 py-4 font-medium text-gray-900">{ep.name}</td>
                    <td className="px-6 py-4">
                      <span className={`inline-flex px-2.5 py-0.5 rounded-full text-xs font-medium ${TYPE_BADGES[ep.type] || TYPE_BADGES.generic}`}>
                        {ep.type}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-500 max-w-xs truncate">{ep.url}</td>
                    <td className="px-6 py-4">
                      <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${
                        ep.enabled ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'
                      }`}>{ep.enabled ? 'Active' : 'Disabled'}</span>
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-500">
                      {ep.created_at ? format(new Date(ep.created_at), 'MMM d, yyyy') : '-'}
                    </td>
                    <td className="px-6 py-4 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={(e) => { e.stopPropagation(); testMutation.mutate(ep.id); }}
                          className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium text-teal-700 bg-teal-50 rounded hover:bg-teal-100"
                          title="Send test webhook">
                          <BoltIcon className="h-3.5 w-3.5" />
                          Test
                        </button>
                        <button
                          onClick={(e) => { e.stopPropagation(); if (confirm('Delete this endpoint?')) deleteMutation.mutate(ep.id); }}
                          className="px-2.5 py-1.5 text-xs font-medium text-red-600 bg-red-50 rounded hover:bg-red-100">
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                  {expandedId === ep.id && (
                    <tr key={`${ep.id}-subs`}>
                      <td colSpan={6} className="px-6 py-4 bg-gray-50 border-t border-gray-100">
                        <h4 className="text-sm font-medium text-gray-700 mb-2">Subscriptions</h4>
                        <SubscriptionPanel endpointId={ep.id} />
                      </td>
                    </tr>
                  )}
                </>
              ))
            )}
          </tbody>
        </table>
      </div>

      {testMutation.isSuccess && (
        <div className={`p-3 rounded text-sm ${testMutation.data?.success ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-800'}`}>
          Test result: {testMutation.data?.success ? 'Success' : 'Failed'} — {testMutation.data?.status_code || testMutation.data?.error}
        </div>
      )}

      {showCreate && (
        <CreateEndpointModal
          onClose={() => setShowCreate(false)}
          onSubmit={(data) => createMutation.mutateAsync(data)}
          submitting={createMutation.isPending}
        />
      )}
    </div>
  );
}
