import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { format } from 'date-fns';
import {
  MagnifyingGlassIcon,
  ArrowPathIcon,
  ShieldCheckIcon,
  ShieldExclamationIcon,
  XCircleIcon,
  CheckCircleIcon,
} from '@heroicons/react/24/outline';
import { discovery } from '../api/client';
import StatusBadge from '../components/StatusBadge';

const govStatusColors = {
  governed: 'bg-green-100 text-green-800',
  known_ungoverned: 'bg-yellow-100 text-yellow-800',
  unknown: 'bg-red-100 text-red-800',
  onboarded: 'bg-blue-100 text-blue-800',
  quarantined: 'bg-purple-100 text-purple-800',
  dismissed: 'bg-gray-100 text-gray-800',
  ungoverned: 'bg-red-100 text-red-800',
};

function GovernanceBadge({ status }) {
  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${govStatusColors[status] || 'bg-gray-100 text-gray-800'}`}
    >
      {status?.replace(/_/g, ' ')}
    </span>
  );
}

function NewScanModal({ onClose, onSubmit }) {
  const [name, setName] = useState('');
  const [scanType, setScanType] = useState('network');
  const [cidrs, setCidrs] = useState('');
  const [ports, setPorts] = useState('5000');
  const [timeout_, setTimeout_] = useState(5000);
  const [maxProbes, setMaxProbes] = useState(50);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    try {
      await onSubmit({
        name,
        scan_type: scanType,
        config: {
          cidrs: cidrs.split('\n').map(s => s.trim()).filter(Boolean),
          ports: ports.split(',').map(s => parseInt(s.trim())).filter(n => !isNaN(n)),
          timeout_ms: timeout_,
          max_concurrent_probes: maxProbes,
        },
      });
      onClose();
    } catch (error) {
      alert(error.message || 'Failed to create scan');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-lg mx-4">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900">New Network Scan</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <XCircleIcon className="h-6 w-6" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="px-6 py-4 space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Scan Name</label>
            <input
              type="text"
              value={name}
              onChange={e => setName(e.target.value)}
              required
              placeholder="e.g. Production network scan"
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Scan Type</label>
            <select
              value={scanType}
              onChange={e => setScanType(e.target.value)}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
            >
              <option value="network">Network (CIDR scan)</option>
              <option value="a2a">A2A Protocol Discovery</option>
              <option value="mcp">MCP Server Discovery</option>
              <option value="kubernetes">Kubernetes Service Discovery</option>
              <option value="hybrid">Hybrid (all methods)</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              CIDRs / Hosts <span className="text-gray-400 font-normal">(one per line)</span>
            </label>
            <textarea
              value={cidrs}
              onChange={e => setCidrs(e.target.value)}
              rows={3}
              placeholder={"10.0.0.0/24\n192.168.1.0/24"}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
            />
          </div>

          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Ports <span className="text-gray-400 font-normal">(comma-sep)</span>
              </label>
              <input
                type="text"
                value={ports}
                onChange={e => setPorts(e.target.value)}
                placeholder="5000,8080"
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Timeout (ms)</label>
              <input
                type="number"
                value={timeout_}
                onChange={e => setTimeout_(parseInt(e.target.value) || 0)}
                min={500}
                max={60000}
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Max Probes</label>
              <input
                type="number"
                value={maxProbes}
                onChange={e => setMaxProbes(parseInt(e.target.value) || 1)}
                min={1}
                max={500}
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
              />
            </div>
          </div>

          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting || !name.trim()}
              className="inline-flex items-center px-4 py-2 text-sm font-medium text-white bg-teal-600 rounded-md hover:bg-teal-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {submitting ? (
                <>
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2" />
                  Starting...
                </>
              ) : (
                <>
                  <MagnifyingGlassIcon className="h-4 w-4 mr-1.5" />
                  Start Scan
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function NetworkDiscovery() {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState('scans');
  const [showNewScan, setShowNewScan] = useState(false);
  const [govFilter, setGovFilter] = useState('');

  // Queries
  const statsQuery = useQuery({
    queryKey: ['discovery-stats'],
    queryFn: discovery.stats,
  });

  const scansQuery = useQuery({
    queryKey: ['discovery-scans'],
    queryFn: () => discovery.scans.list(),
  });

  const agentsQuery = useQuery({
    queryKey: ['discovery-agents', govFilter],
    queryFn: () => discovery.agents.list({ governance_status: govFilter || undefined }),
    enabled: activeTab === 'agents',
  });

  const toolsQuery = useQuery({
    queryKey: ['discovery-tools'],
    queryFn: () => discovery.tools.list(),
    enabled: activeTab === 'tools',
  });

  const topologyQuery = useQuery({
    queryKey: ['discovery-topology'],
    queryFn: discovery.topology,
    enabled: activeTab === 'topology',
  });

  // Mutations
  const createScan = useMutation({
    mutationFn: discovery.scans.create,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['discovery-scans'] }),
  });

  const onboardAgent = useMutation({
    mutationFn: (id) => discovery.agents.onboard(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['discovery-agents'] });
      queryClient.invalidateQueries({ queryKey: ['discovery-stats'] });
    },
  });

  const quarantineAgent = useMutation({
    mutationFn: (id) => discovery.agents.quarantine(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['discovery-agents'] });
      queryClient.invalidateQueries({ queryKey: ['discovery-stats'] });
    },
  });

  const dismissAgent = useMutation({
    mutationFn: (id) => discovery.agents.dismiss(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['discovery-agents'] });
      queryClient.invalidateQueries({ queryKey: ['discovery-stats'] });
    },
  });

  const onboardTool = useMutation({
    mutationFn: (id) => discovery.tools.onboard(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['discovery-tools'] });
      queryClient.invalidateQueries({ queryKey: ['discovery-stats'] });
    },
  });

  const rerunScan = useMutation({
    mutationFn: (id) => discovery.scans.rerun(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['discovery-scans'] }),
  });

  const cancelScan = useMutation({
    mutationFn: (id) => discovery.scans.cancel(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['discovery-scans'] }),
  });

  // Auto-refresh scans that are running
  useEffect(() => {
    const hasRunning = scansQuery.data?.scans?.some(
      s => s.status === 'running' || s.status === 'pending'
    );
    if (hasRunning) {
      const interval = setInterval(() => {
        queryClient.invalidateQueries({ queryKey: ['discovery-scans'] });
        queryClient.invalidateQueries({ queryKey: ['discovery-stats'] });
      }, 3000);
      return () => clearInterval(interval);
    }
  }, [scansQuery.data, queryClient]);

  const stats = statsQuery.data || {};
  const tabs = [
    { id: 'scans', label: 'Scans' },
    { id: 'agents', label: `Discovered Agents (${stats.total_agents || 0})` },
    { id: 'tools', label: `Discovered Tools (${stats.total_tools || 0})` },
    { id: 'topology', label: 'Topology' },
  ];

  function formatDuration(seconds) {
    if (seconds == null) return '-';
    if (seconds < 60) return `${seconds}s`;
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}m ${secs}s`;
  }

  function renderStatsBar() {
    const statCards = [
      { label: 'Governed', value: stats.governed || 0, color: 'text-green-600', bg: 'bg-green-50' },
      { label: 'Ungoverned', value: stats.ungoverned || 0, color: 'text-red-600', bg: 'bg-red-50' },
      { label: 'Onboarded', value: stats.onboarded || 0, color: 'text-blue-600', bg: 'bg-blue-50' },
      { label: 'Quarantined', value: stats.quarantined || 0, color: 'text-purple-600', bg: 'bg-purple-50' },
    ];

    return (
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {statCards.map(card => (
          <div key={card.label} className={`${card.bg} rounded-lg p-4`}>
            <p className="text-sm font-medium text-gray-600">{card.label}</p>
            <p className={`text-2xl font-bold ${card.color}`}>{card.value}</p>
          </div>
        ))}
      </div>
    );
  }

  function renderScansTab() {
    if (scansQuery.isLoading) {
      return (
        <div className="flex items-center justify-center h-32">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-teal-600" />
        </div>
      );
    }

    if (scansQuery.error) {
      return (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <p className="text-red-700">Error loading scans: {scansQuery.error.message}</p>
        </div>
      );
    }

    const scans = scansQuery.data?.scans || [];

    if (scans.length === 0) {
      return (
        <div className="text-center py-12 bg-gray-50 rounded-lg">
          <MagnifyingGlassIcon className="mx-auto h-12 w-12 text-gray-400" />
          <h3 className="mt-2 text-sm font-medium text-gray-900">No scans yet</h3>
          <p className="mt-1 text-sm text-gray-500">Start a network scan to discover agents and tools.</p>
          <button
            onClick={() => setShowNewScan(true)}
            className="mt-4 inline-flex items-center px-4 py-2 text-sm font-medium text-white bg-teal-600 rounded-md hover:bg-teal-700"
          >
            <MagnifyingGlassIcon className="h-4 w-4 mr-1.5" />
            New Scan
          </button>
        </div>
      );
    }

    return (
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Name</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Type</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Hosts</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Agents</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Tools</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Duration</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Started</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {scans.map(scan => (
              <tr key={scan.id} className="hover:bg-gray-50">
                <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                  {scan.name}
                </td>
                <td className="px-6 py-4 whitespace-nowrap">
                  <StatusBadge status={scan.status} />
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                  {scan.scan_type}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                  {scan.hosts_scanned ?? '-'}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                  {scan.agents_found ?? 0}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                  {scan.tools_found ?? 0}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                  {formatDuration(scan.duration_seconds)}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                  {scan.started_at ? format(new Date(scan.started_at), 'MMM d, HH:mm') : '-'}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm">
                  <div className="flex items-center gap-2">
                    {(scan.status === 'completed' || scan.status === 'failed') && (
                      <button
                        onClick={() => rerunScan.mutate(scan.id)}
                        disabled={rerunScan.isPending}
                        className="inline-flex items-center px-2.5 py-1 text-xs font-medium text-teal-700 bg-teal-50 rounded hover:bg-teal-100 disabled:opacity-50"
                        title="Re-run scan"
                      >
                        <ArrowPathIcon className="h-3.5 w-3.5 mr-1" />
                        Re-run
                      </button>
                    )}
                    {(scan.status === 'running' || scan.status === 'pending') && (
                      <button
                        onClick={() => cancelScan.mutate(scan.id)}
                        disabled={cancelScan.isPending}
                        className="inline-flex items-center px-2.5 py-1 text-xs font-medium text-red-700 bg-red-50 rounded hover:bg-red-100 disabled:opacity-50"
                        title="Cancel scan"
                      >
                        <XCircleIcon className="h-3.5 w-3.5 mr-1" />
                        Cancel
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  function renderAgentsTab() {
    if (agentsQuery.isLoading) {
      return (
        <div className="flex items-center justify-center h-32">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-teal-600" />
        </div>
      );
    }

    if (agentsQuery.error) {
      return (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <p className="text-red-700">Error loading agents: {agentsQuery.error.message}</p>
        </div>
      );
    }

    const agents = agentsQuery.data?.agents || [];

    return (
      <div className="space-y-4">
        {/* Filter bar */}
        <div className="flex items-center gap-3">
          <label className="text-sm font-medium text-gray-700">Filter by status:</label>
          <select
            value={govFilter}
            onChange={e => setGovFilter(e.target.value)}
            className="rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
          >
            <option value="">All</option>
            <option value="governed">Governed</option>
            <option value="ungoverned">Ungoverned</option>
            <option value="onboarded">Onboarded</option>
            <option value="quarantined">Quarantined</option>
            <option value="dismissed">Dismissed</option>
          </select>
        </div>

        {agents.length === 0 ? (
          <div className="text-center py-12 bg-gray-50 rounded-lg">
            <ShieldExclamationIcon className="mx-auto h-12 w-12 text-gray-400" />
            <h3 className="mt-2 text-sm font-medium text-gray-900">No discovered agents</h3>
            <p className="mt-1 text-sm text-gray-500">
              Run a network scan to discover agents in your environment.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Name</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Version</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Framework</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Host</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Governance</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Discovered</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {agents.map(agent => (
                  <tr key={agent.id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                      {agent.name || 'Unknown'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {agent.version || '-'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {agent.framework || '-'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 font-mono">
                      {agent.host}:{agent.port}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <GovernanceBadge status={agent.governance_status} />
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {agent.discovered_at
                        ? format(new Date(agent.discovered_at), 'MMM d, HH:mm')
                        : '-'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm">
                      <div className="flex items-center gap-2">
                        {agent.governance_status !== 'onboarded' &&
                          agent.governance_status !== 'governed' && (
                            <button
                              onClick={() => onboardAgent.mutate(agent.id)}
                              disabled={onboardAgent.isPending}
                              className="inline-flex items-center px-2.5 py-1 text-xs font-medium text-green-700 bg-green-50 rounded hover:bg-green-100 disabled:opacity-50"
                              title="Onboard agent into registry"
                            >
                              <CheckCircleIcon className="h-3.5 w-3.5 mr-1" />
                              Onboard
                            </button>
                          )}
                        {agent.governance_status !== 'quarantined' && (
                          <button
                            onClick={() => quarantineAgent.mutate(agent.id)}
                            disabled={quarantineAgent.isPending}
                            className="inline-flex items-center px-2.5 py-1 text-xs font-medium text-purple-700 bg-purple-50 rounded hover:bg-purple-100 disabled:opacity-50"
                            title="Quarantine agent"
                          >
                            <ShieldExclamationIcon className="h-3.5 w-3.5 mr-1" />
                            Quarantine
                          </button>
                        )}
                        {agent.governance_status !== 'dismissed' && (
                          <button
                            onClick={() => dismissAgent.mutate(agent.id)}
                            disabled={dismissAgent.isPending}
                            className="inline-flex items-center px-2.5 py-1 text-xs font-medium text-gray-700 bg-gray-50 rounded hover:bg-gray-100 disabled:opacity-50"
                            title="Dismiss agent"
                          >
                            <XCircleIcon className="h-3.5 w-3.5 mr-1" />
                            Dismiss
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    );
  }

  function renderToolsTab() {
    if (toolsQuery.isLoading) {
      return (
        <div className="flex items-center justify-center h-32">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-teal-600" />
        </div>
      );
    }

    if (toolsQuery.error) {
      return (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <p className="text-red-700">Error loading tools: {toolsQuery.error.message}</p>
        </div>
      );
    }

    const tools = toolsQuery.data?.tools || [];

    if (tools.length === 0) {
      return (
        <div className="text-center py-12 bg-gray-50 rounded-lg">
          <MagnifyingGlassIcon className="mx-auto h-12 w-12 text-gray-400" />
          <h3 className="mt-2 text-sm font-medium text-gray-900">No discovered tools</h3>
          <p className="mt-1 text-sm text-gray-500">
            Run a scan with MCP discovery enabled to find tools.
          </p>
        </div>
      );
    }

    return (
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Tool Name</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">MCP Server</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Description</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Governance</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Discovered</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {tools.map(tool => (
              <tr key={tool.id} className="hover:bg-gray-50">
                <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                  {tool.name}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 font-mono">
                  {tool.mcp_server_url || '-'}
                </td>
                <td className="px-6 py-4 text-sm text-gray-500 max-w-xs truncate">
                  {tool.description || '-'}
                </td>
                <td className="px-6 py-4 whitespace-nowrap">
                  <GovernanceBadge status={tool.governance_status} />
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                  {tool.discovered_at
                    ? format(new Date(tool.discovered_at), 'MMM d, HH:mm')
                    : '-'}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm">
                  {tool.governance_status !== 'onboarded' &&
                    tool.governance_status !== 'governed' && (
                      <button
                        onClick={() => onboardTool.mutate(tool.id)}
                        disabled={onboardTool.isPending}
                        className="inline-flex items-center px-2.5 py-1 text-xs font-medium text-green-700 bg-green-50 rounded hover:bg-green-100 disabled:opacity-50"
                        title="Onboard tool into registry"
                      >
                        <CheckCircleIcon className="h-3.5 w-3.5 mr-1" />
                        Onboard
                      </button>
                    )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  function renderTopologyTab() {
    if (topologyQuery.isLoading) {
      return (
        <div className="flex items-center justify-center h-32">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-teal-600" />
        </div>
      );
    }

    if (topologyQuery.error) {
      return (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <p className="text-red-700">Error loading topology: {topologyQuery.error.message}</p>
        </div>
      );
    }

    const topology = topologyQuery.data || {};
    const nodes = topology.nodes || [];
    const edges = topology.edges || [];

    if (nodes.length === 0) {
      return (
        <div className="text-center py-12 bg-gray-50 rounded-lg">
          <MagnifyingGlassIcon className="mx-auto h-12 w-12 text-gray-400" />
          <h3 className="mt-2 text-sm font-medium text-gray-900">No topology data</h3>
          <p className="mt-1 text-sm text-gray-500">
            Run a scan to build the network topology map.
          </p>
        </div>
      );
    }

    return (
      <div className="space-y-6">
        {/* Summary */}
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          <div className="bg-gray-50 rounded-lg p-4">
            <p className="text-sm font-medium text-gray-600">Nodes</p>
            <p className="text-2xl font-bold text-gray-900">{nodes.length}</p>
          </div>
          <div className="bg-gray-50 rounded-lg p-4">
            <p className="text-sm font-medium text-gray-600">Connections</p>
            <p className="text-2xl font-bold text-gray-900">{edges.length}</p>
          </div>
          <div className="bg-gray-50 rounded-lg p-4">
            <p className="text-sm font-medium text-gray-600">Clusters</p>
            <p className="text-2xl font-bold text-gray-900">{topology.clusters || 0}</p>
          </div>
        </div>

        {/* Node list */}
        <div>
          <h3 className="text-sm font-medium text-gray-700 mb-3">Discovered Nodes</h3>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Node</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Type</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Address</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Governance</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Connections</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {nodes.map(node => (
                  <tr key={node.id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                      {node.name || node.id}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {node.type || '-'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 font-mono">
                      {node.address || '-'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <GovernanceBadge status={node.governance_status} />
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {node.connection_count ?? 0}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Edge list */}
        {edges.length > 0 && (
          <div>
            <h3 className="text-sm font-medium text-gray-700 mb-3">Connections</h3>
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Source</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Target</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Protocol</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Last Seen</th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {edges.map((edge, idx) => (
                    <tr key={idx} className="hover:bg-gray-50">
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                        {edge.source_name || edge.source}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                        {edge.target_name || edge.target}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                        {edge.protocol || '-'}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                        {edge.last_seen
                          ? format(new Date(edge.last_seen), 'MMM d, HH:mm')
                          : '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Network Discovery</h1>
          <p className="mt-1 text-sm text-gray-500">
            Scan your network to discover agents and tools, and manage governance coverage.
          </p>
        </div>
        <button
          onClick={() => setShowNewScan(true)}
          className="inline-flex items-center px-4 py-2 text-sm font-medium text-white bg-teal-600 rounded-md hover:bg-teal-700"
        >
          <MagnifyingGlassIcon className="h-4 w-4 mr-1.5" />
          New Scan
        </button>
      </div>

      {/* Stats bar */}
      {renderStatsBar()}

      {/* Tabs */}
      <div className="border-b border-gray-200">
        <nav className="-mb-px flex space-x-8">
          {tabs.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm ${
                activeTab === tab.id
                  ? 'border-teal-500 text-teal-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Tab content */}
      <div>
        {activeTab === 'scans' && renderScansTab()}
        {activeTab === 'agents' && renderAgentsTab()}
        {activeTab === 'tools' && renderToolsTab()}
        {activeTab === 'topology' && renderTopologyTab()}
      </div>

      {/* New Scan Modal */}
      {showNewScan && (
        <NewScanModal
          onClose={() => setShowNewScan(false)}
          onSubmit={(data) => createScan.mutateAsync(data)}
        />
      )}
    </div>
  );
}
