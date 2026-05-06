import { useState, useEffect } from 'react';
import { auditLogs } from '../api/client';

const ACTION_OPTIONS = [
  'agent.created', 'agent.updated', 'agent.deleted', 'agent.submitted', 'agent.suspended',
  'security_scan.triggered',
  'security_test_case.created', 'security_test_case.updated', 'security_test_case.deleted', 'security_test_case.defaults_reset',
  'evaluation.triggered',
  'evaluation_suite.created', 'evaluation_suite.updated',
  'evaluation_test_case.created', 'evaluation_test_case.updated', 'evaluation_test_case.deleted',
  'approval.approved', 'approval.rejected',
  'user.login', 'user.logout', 'user.created', 'user.updated', 'user.deleted', 'user.groups_updated',
  'group.created', 'group.updated', 'group.deleted',
];

const RESOURCE_TYPE_OPTIONS = [
  'agent', 'security_scan', 'security_test_case',
  'evaluation', 'evaluation_suite', 'evaluation_test_case',
  'user', 'group',
];

function actionBadgeColor(action) {
  if (action.startsWith('agent.')) return 'bg-blue-100 text-blue-800';
  if (action.startsWith('security')) return 'bg-orange-100 text-orange-800';
  if (action.startsWith('evaluation')) return 'bg-purple-100 text-purple-800';
  if (action.startsWith('approval')) return 'bg-green-100 text-green-800';
  if (action.startsWith('user.') || action.startsWith('group.')) return 'bg-gray-100 text-gray-800';
  return 'bg-gray-100 text-gray-700';
}

function formatTimestamp(ts) {
  if (!ts) return '-';
  const d = new Date(ts);
  return d.toLocaleString();
}

export default function AuditLog() {
  const [logs, setLogs] = useState([]);
  const [pagination, setPagination] = useState({ page: 1, per_page: 50, total: 0, pages: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [expandedId, setExpandedId] = useState(null);
  const [expandedDetail, setExpandedDetail] = useState(null);

  // Filters
  const [action, setAction] = useState('');
  const [resourceType, setResourceType] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [page, setPage] = useState(1);

  useEffect(() => {
    loadLogs();
  }, [page]);

  async function loadLogs() {
    setLoading(true);
    setError('');
    try {
      const params = { page, per_page: 50 };
      if (action) params.action = action;
      if (resourceType) params.resource_type = resourceType;
      if (dateFrom) params.date_from = new Date(dateFrom).toISOString();
      if (dateTo) params.date_to = new Date(dateTo + 'T23:59:59').toISOString();

      const data = await auditLogs.list(params);
      setLogs(data.logs);
      setPagination(data.pagination);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  function handleFilter(e) {
    e.preventDefault();
    setPage(1);
    loadLogs();
  }

  function handleClear() {
    setAction('');
    setResourceType('');
    setDateFrom('');
    setDateTo('');
    setPage(1);
    // loadLogs will be called by the useEffect on page change
    // but since page might already be 1, call directly
    setTimeout(() => loadLogs(), 0);
  }

  async function toggleExpand(logEntry) {
    if (expandedId === logEntry.id) {
      setExpandedId(null);
      setExpandedDetail(null);
      return;
    }
    setExpandedId(logEntry.id);
    try {
      const detail = await auditLogs.get(logEntry.id);
      setExpandedDetail(detail);
    } catch {
      setExpandedDetail(null);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Audit Log</h1>
        <p className="mt-1 text-sm text-gray-500">
          Immutable record of all actions performed in the registry.
        </p>
      </div>

      {/* Filters */}
      <div className="bg-white rounded-lg shadow p-4">
        <form onSubmit={handleFilter} className="flex flex-wrap items-end gap-4">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Action</label>
            <select
              value={action}
              onChange={(e) => setAction(e.target.value)}
              className="block w-52 rounded-md border-gray-300 shadow-sm text-sm focus:border-teal-500 focus:ring-teal-500"
            >
              <option value="">All actions</option>
              {ACTION_OPTIONS.map((a) => (
                <option key={a} value={a}>{a}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Resource Type</label>
            <select
              value={resourceType}
              onChange={(e) => setResourceType(e.target.value)}
              className="block w-44 rounded-md border-gray-300 shadow-sm text-sm focus:border-teal-500 focus:ring-teal-500"
            >
              <option value="">All types</option>
              {RESOURCE_TYPE_OPTIONS.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">From</label>
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className="block rounded-md border-gray-300 shadow-sm text-sm focus:border-teal-500 focus:ring-teal-500"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">To</label>
            <input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              className="block rounded-md border-gray-300 shadow-sm text-sm focus:border-teal-500 focus:ring-teal-500"
            />
          </div>

          <button
            type="submit"
            className="px-4 py-2 bg-teal-600 text-white text-sm font-medium rounded-md hover:bg-teal-700"
          >
            Filter
          </button>
          <button
            type="button"
            onClick={handleClear}
            className="px-4 py-2 bg-gray-100 text-gray-700 text-sm font-medium rounded-md hover:bg-gray-200"
          >
            Clear
          </button>
        </form>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-md text-sm">
          {error}
        </div>
      )}

      {/* Table */}
      <div className="bg-white rounded-lg shadow overflow-hidden">
        {loading ? (
          <div className="flex justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-teal-600" />
          </div>
        ) : logs.length === 0 ? (
          <div className="text-center py-12 text-gray-500">No audit log entries found.</div>
        ) : (
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Timestamp</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">User</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Action</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Resource Type</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Resource</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">IP</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {logs.map((entry) => (
                <>
                  <tr
                    key={entry.id}
                    onClick={() => toggleExpand(entry)}
                    className="hover:bg-gray-50 cursor-pointer"
                  >
                    <td className="px-4 py-3 text-sm text-gray-600 whitespace-nowrap">
                      {formatTimestamp(entry.timestamp)}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-900">{entry.username}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${actionBadgeColor(entry.action)}`}>
                        {entry.action}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600">{entry.resource_type}</td>
                    <td className="px-4 py-3 text-sm text-gray-900">
                      {entry.resource_name || (entry.resource_id ? entry.resource_id.substring(0, 8) + '...' : '-')}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-500">{entry.ip_address || '-'}</td>
                  </tr>
                  {expandedId === entry.id && (
                    <tr key={`${entry.id}-detail`}>
                      <td colSpan={6} className="px-4 py-4 bg-gray-50">
                        {expandedDetail ? (
                          <div className="space-y-2">
                            <div className="grid grid-cols-2 gap-4 text-sm">
                              <div>
                                <span className="font-medium text-gray-700">Entry ID:</span>{' '}
                                <span className="text-gray-600 font-mono text-xs">{expandedDetail.id}</span>
                              </div>
                              <div>
                                <span className="font-medium text-gray-700">User ID:</span>{' '}
                                <span className="text-gray-600 font-mono text-xs">{expandedDetail.user_id || '-'}</span>
                              </div>
                              <div>
                                <span className="font-medium text-gray-700">Resource ID:</span>{' '}
                                <span className="text-gray-600 font-mono text-xs">{expandedDetail.resource_id || '-'}</span>
                              </div>
                              <div>
                                <span className="font-medium text-gray-700">Tenant:</span>{' '}
                                <span className="text-gray-600">{expandedDetail.tenant_id}</span>
                              </div>
                            </div>
                            {expandedDetail.detail && (
                              <div>
                                <span className="font-medium text-gray-700 text-sm">Detail:</span>
                                <pre className="mt-1 p-3 bg-white border border-gray-200 rounded text-xs text-gray-800 overflow-x-auto">
                                  {JSON.stringify(expandedDetail.detail, null, 2)}
                                </pre>
                              </div>
                            )}
                          </div>
                        ) : (
                          <div className="flex justify-center py-2">
                            <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-teal-600" />
                          </div>
                        )}
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        )}

        {/* Pagination */}
        {pagination.pages > 1 && (
          <div className="px-4 py-3 bg-gray-50 border-t border-gray-200 flex items-center justify-between">
            <span className="text-sm text-gray-700">
              Page {pagination.page} of {pagination.pages} ({pagination.total} entries)
            </span>
            <div className="flex gap-2">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="px-3 py-1 text-sm border rounded-md disabled:opacity-50 hover:bg-gray-100"
              >
                Previous
              </button>
              <button
                onClick={() => setPage((p) => Math.min(pagination.pages, p + 1))}
                disabled={page >= pagination.pages}
                className="px-3 py-1 text-sm border rounded-md disabled:opacity-50 hover:bg-gray-100"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
