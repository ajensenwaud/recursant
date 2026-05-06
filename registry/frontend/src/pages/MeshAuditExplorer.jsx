import { useState, useEffect, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { meshAudit } from '../api/client';
import useSocket from '../hooks/useSocket';

const DIRECTION_BADGE = {
  inbound: 'bg-blue-100 text-blue-800',
  outbound: 'bg-purple-100 text-purple-800',
};

const OUTCOME_BADGE = {
  success: 'bg-green-100 text-green-800',
  blocked: 'bg-red-100 text-red-800',
  error: 'bg-amber-100 text-amber-800',
};

const DECISION_BADGE = {
  pass: 'bg-green-100 text-green-800',
  block: 'bg-red-100 text-red-800',
};

export default function MeshAuditExplorer() {
  const [filters, setFilters] = useState({
    source_agent_name: '',
    dest_agent_name: '',
    direction: '',
    decision: '',
    outcome: '',
    date_from: '',
    date_to: '',
    search: '',
    trace_id: '',
    page: 1,
    per_page: 25,
  });
  const [expandedRow, setExpandedRow] = useState(null);
  const [liveEvents, setLiveEvents] = useState([]);
  const [socketConnected, setSocketConnected] = useState(false);

  // Build query params (omit empty values)
  const queryParams = Object.fromEntries(
    Object.entries(filters).filter(([_, v]) => v !== '')
  );

  const { data: auditData, isLoading, refetch } = useQuery({
    queryKey: ['meshAudit', queryParams],
    queryFn: () => meshAudit.list(queryParams),
    keepPreviousData: true,
  });

  const { data: statsData } = useQuery({
    queryKey: ['meshAuditStats', filters.date_from, filters.date_to],
    queryFn: () => meshAudit.stats({
      ...(filters.date_from && { date_from: filters.date_from }),
      ...(filters.date_to && { date_to: filters.date_to }),
    }),
  });

  // Socket.IO for live updates
  const handleSocketEvent = useCallback((event) => {
    if (event) {
      setLiveEvents((prev) => [event, ...prev].slice(0, 50));
    }
  }, []);

  const { socketRef } = useSocket('/mesh', handleSocketEvent);

  useEffect(() => {
    const socket = socketRef.current;
    if (socket) {
      const onConnect = () => setSocketConnected(true);
      const onDisconnect = () => setSocketConnected(false);
      socket.on('connect', onConnect);
      socket.on('disconnect', onDisconnect);
      if (socket.connected) setSocketConnected(true);
      return () => {
        socket.off('connect', onConnect);
        socket.off('disconnect', onDisconnect);
      };
    }
  }, [socketRef]);

  const records = auditData?.records || [];
  const total = auditData?.total || 0;
  const pages = auditData?.pages || 1;

  const handleFilterChange = (field, value) => {
    setFilters((prev) => ({ ...prev, [field]: value, page: 1 }));
  };

  const clearFilters = () => {
    setFilters({
      source_agent_name: '',
      dest_agent_name: '',
      direction: '',
      decision: '',
      outcome: '',
      date_from: '',
      date_to: '',
      search: '',
      trace_id: '',
      page: 1,
      per_page: 25,
    });
  };

  const formatTimestamp = (ts) => {
    if (!ts) return '-';
    const d = new Date(ts);
    return d.toLocaleString();
  };

  const truncate = (str, len = 12) => {
    if (!str) return '-';
    return str.length > len ? str.substring(0, len) + '...' : str;
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Mesh Audit Explorer</h1>
        <p className="mt-1 text-sm text-gray-500">
          Search, filter, and inspect mesh communication audit records in real time.
        </p>
      </div>

      {/* Stats cards */}
      {statsData && (
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
          <div className="bg-white rounded-lg border border-gray-200 p-4">
            <p className="text-sm text-gray-500">Total Records</p>
            <p className="text-2xl font-bold text-teal-600">{statsData.total?.toLocaleString()}</p>
          </div>
          <div className="bg-white rounded-lg border border-gray-200 p-4">
            <p className="text-sm text-gray-500">Blocked</p>
            <p className="text-2xl font-bold text-red-600">{statsData.blocked?.toLocaleString()}</p>
          </div>
          <div className="bg-white rounded-lg border border-gray-200 p-4">
            <p className="text-sm text-gray-500">Errors</p>
            <p className="text-2xl font-bold text-amber-600">{statsData.errors?.toLocaleString()}</p>
          </div>
          <div className="bg-white rounded-lg border border-gray-200 p-4">
            <p className="text-sm text-gray-500">Top Sources</p>
            <p className="text-2xl font-bold text-gray-900">{statsData.top_sources?.length || 0}</p>
          </div>
        </div>
      )}

      {/* Live indicator */}
      <div className="flex items-center gap-2 text-sm text-gray-500">
        <span className={`inline-block h-2.5 w-2.5 rounded-full ${socketConnected ? 'bg-green-500' : 'bg-gray-300'}`} />
        {socketConnected ? 'Live' : 'Disconnected'}
        {liveEvents.length > 0 && (
          <span className="text-xs text-gray-400">({liveEvents.length} new events)</span>
        )}
      </div>

      {/* Filter bar */}
      <div className="bg-white rounded-lg border border-gray-200 p-4">
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-3">
          <input
            type="text"
            placeholder="Source Agent"
            value={filters.source_agent_name}
            onChange={(e) => handleFilterChange('source_agent_name', e.target.value)}
            className="block w-full rounded-md border-gray-300 shadow-sm text-sm focus:border-teal-500 focus:ring-teal-500"
          />
          <input
            type="text"
            placeholder="Destination Agent"
            value={filters.dest_agent_name}
            onChange={(e) => handleFilterChange('dest_agent_name', e.target.value)}
            className="block w-full rounded-md border-gray-300 shadow-sm text-sm focus:border-teal-500 focus:ring-teal-500"
          />
          <select
            value={filters.direction}
            onChange={(e) => handleFilterChange('direction', e.target.value)}
            className="block w-full rounded-md border-gray-300 shadow-sm text-sm focus:border-teal-500 focus:ring-teal-500"
          >
            <option value="">All Directions</option>
            <option value="inbound">Inbound</option>
            <option value="outbound">Outbound</option>
          </select>
          <select
            value={filters.decision}
            onChange={(e) => handleFilterChange('decision', e.target.value)}
            className="block w-full rounded-md border-gray-300 shadow-sm text-sm focus:border-teal-500 focus:ring-teal-500"
          >
            <option value="">All Decisions</option>
            <option value="pass">Pass</option>
            <option value="block">Block</option>
          </select>
          <select
            value={filters.outcome}
            onChange={(e) => handleFilterChange('outcome', e.target.value)}
            className="block w-full rounded-md border-gray-300 shadow-sm text-sm focus:border-teal-500 focus:ring-teal-500"
          >
            <option value="">All Outcomes</option>
            <option value="success">Success</option>
            <option value="blocked">Blocked</option>
            <option value="error">Error</option>
          </select>
          <input
            type="date"
            placeholder="Date From"
            value={filters.date_from}
            onChange={(e) => handleFilterChange('date_from', e.target.value)}
            className="block w-full rounded-md border-gray-300 shadow-sm text-sm focus:border-teal-500 focus:ring-teal-500"
          />
          <input
            type="date"
            placeholder="Date To"
            value={filters.date_to}
            onChange={(e) => handleFilterChange('date_to', e.target.value)}
            className="block w-full rounded-md border-gray-300 shadow-sm text-sm focus:border-teal-500 focus:ring-teal-500"
          />
          <input
            type="text"
            placeholder="Search..."
            value={filters.search}
            onChange={(e) => handleFilterChange('search', e.target.value)}
            className="block w-full rounded-md border-gray-300 shadow-sm text-sm focus:border-teal-500 focus:ring-teal-500"
          />
          <input
            type="text"
            placeholder="Task / Trace ID"
            value={filters.trace_id}
            onChange={(e) => handleFilterChange('trace_id', e.target.value)}
            className="block w-full rounded-md border-gray-300 shadow-sm text-sm focus:border-teal-500 focus:ring-teal-500"
          />
          <div className="flex gap-2">
            <button
              onClick={() => refetch()}
              className="px-3 py-2 bg-teal-600 text-white text-sm rounded-md hover:bg-teal-700"
            >
              Filter
            </button>
            <button
              onClick={clearFilters}
              className="px-3 py-2 bg-gray-100 text-gray-700 text-sm rounded-md hover:bg-gray-200"
            >
              Clear
            </button>
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
        {isLoading ? (
          <div className="p-8 text-center text-gray-500">Loading...</div>
        ) : records.length === 0 ? (
          <div className="p-8 text-center text-gray-500">No audit records found.</div>
        ) : (
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Timestamp</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Source</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Destination</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Direction</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Method</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Decision</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Outcome</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Task ID</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {records.map((record) => (
                <>
                  <tr
                    key={record.id}
                    onClick={() => setExpandedRow(expandedRow === record.id ? null : record.id)}
                    className="cursor-pointer hover:bg-gray-50"
                  >
                    <td className="px-4 py-3 text-sm text-gray-700 whitespace-nowrap">
                      {formatTimestamp(record.timestamp)}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-900">{record.source_agent_name || '-'}</td>
                    <td className="px-4 py-3 text-sm text-gray-900">{record.dest_agent_name || '-'}</td>
                    <td className="px-4 py-3 text-sm">
                      <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${DIRECTION_BADGE[record.direction] || 'bg-gray-100 text-gray-800'}`}>
                        {record.direction}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-700">{record.a2a_method}</td>
                    <td className="px-4 py-3 text-sm">
                      <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${DECISION_BADGE[record.decision] || 'bg-gray-100 text-gray-800'}`}>
                        {record.decision}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm">
                      <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${OUTCOME_BADGE[record.outcome] || 'bg-gray-100 text-gray-800'}`}>
                        {record.outcome}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-500 font-mono">
                      {truncate(record.task_id)}
                    </td>
                  </tr>
                  {expandedRow === record.id && (
                    <tr key={`${record.id}-detail`}>
                      <td colSpan={8} className="px-4 py-4 bg-gray-50">
                        <div className="grid grid-cols-2 gap-4 text-sm">
                          <div>
                            <h4 className="font-medium text-gray-700 mb-2">Record Details</h4>
                            <dl className="space-y-1">
                              <div className="flex gap-2">
                                <dt className="text-gray-500">ID:</dt>
                                <dd className="font-mono text-gray-700">{record.id}</dd>
                              </div>
                              <div className="flex gap-2">
                                <dt className="text-gray-500">Sidecar:</dt>
                                <dd className="text-gray-700">{record.sidecar_id || '-'}</dd>
                              </div>
                              <div className="flex gap-2">
                                <dt className="text-gray-500">Message Hash:</dt>
                                <dd className="font-mono text-xs text-gray-700">{record.message_hash}</dd>
                              </div>
                              <div className="flex gap-2">
                                <dt className="text-gray-500">Record Hash:</dt>
                                <dd className="font-mono text-xs text-gray-700">{record.record_hash || '-'}</dd>
                              </div>
                              <div className="flex gap-2">
                                <dt className="text-gray-500">Prev Hash:</dt>
                                <dd className="font-mono text-xs text-gray-700">{record.previous_record_hash || '-'}</dd>
                              </div>
                              <div className="flex gap-2">
                                <dt className="text-gray-500">Sequence:</dt>
                                <dd className="text-gray-700">{record.sequence_number ?? '-'}</dd>
                              </div>
                              <div className="flex gap-2">
                                <dt className="text-gray-500">Task ID:</dt>
                                <dd className="font-mono text-gray-700">{record.task_id || '-'}</dd>
                              </div>
                            </dl>
                          </div>
                          <div>
                            <h4 className="font-medium text-gray-700 mb-2">Details</h4>
                            {record.details ? (
                              <pre className="text-xs bg-white border border-gray-200 rounded p-2 overflow-auto max-h-48">
                                {JSON.stringify(record.details, null, 2)}
                              </pre>
                            ) : (
                              <p className="text-gray-400 text-sm">No additional details.</p>
                            )}
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination */}
      {pages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-gray-500">
            Showing {(filters.page - 1) * filters.per_page + 1} to{' '}
            {Math.min(filters.page * filters.per_page, total)} of {total} records
          </p>
          <div className="flex gap-2">
            <button
              onClick={() => setFilters((prev) => ({ ...prev, page: Math.max(1, prev.page - 1) }))}
              disabled={filters.page <= 1}
              className="px-3 py-1 text-sm bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Previous
            </button>
            <span className="px-3 py-1 text-sm text-gray-700">
              Page {filters.page} of {pages}
            </span>
            <button
              onClick={() => setFilters((prev) => ({ ...prev, page: Math.min(pages, prev.page + 1) }))}
              disabled={filters.page >= pages}
              className="px-3 py-1 text-sm bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
