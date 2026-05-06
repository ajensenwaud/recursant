import { Fragment } from 'react';
import { Transition } from '@headlessui/react';
import { XMarkIcon } from '@heroicons/react/20/solid';
import { useQuery } from '@tanstack/react-query';
import { observability, guardrails, meshVisualiser } from '../api/client';
import { getNodeHealth, getEdgeHealth, HEALTH_COLORS } from '../hooks/useMeshGraph';

function Section({ title, children, className }) {
  return (
    <div className={`border-b border-gray-100 pb-3 mb-3 ${className || ''}`}>
      <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">{title}</div>
      {children}
    </div>
  );
}

function MetricRow({ label, value, warn }) {
  return (
    <div className="flex justify-between py-0.5">
      <span className="text-gray-500">{label}</span>
      <span className={`font-mono ${warn ? 'text-red-600' : 'text-gray-800'}`}>{value}</span>
    </div>
  );
}

function HealthDot({ health }) {
  return (
    <span
      className="inline-block w-2.5 h-2.5 rounded-full mr-1.5"
      style={{ backgroundColor: HEALTH_COLORS[health] || HEALTH_COLORS.idle }}
    />
  );
}

function AgentSidebar({ node, goldenData, onClose }) {
  const health = getNodeHealth(node.name, goldenData);
  const agentSignals = goldenData?.agents?.[node.name];

  const { data: alertsData } = useQuery({
    queryKey: ['topology-sidebar-alerts', node.name],
    queryFn: () => observability.alerts.list({ agent_name: node.name, status: 'active' }),
    enabled: true,
    refetchInterval: 30000,
  });

  const { data: tracesData } = useQuery({
    queryKey: ['topology-sidebar-traces', node.name],
    queryFn: () => observability.traces.list({ agent_name: node.name, per_page: 5 }),
    enabled: true,
  });

  const { data: guardrailsData } = useQuery({
    queryKey: ['topology-sidebar-guardrails', node.name],
    queryFn: () => guardrails.list({ agent_name: node.name }),
    enabled: true,
  });

  const alerts = alertsData?.alerts || [];
  const traces = tracesData?.traces || [];
  const guardrailList = guardrailsData?.guardrails || [];

  return (
    <>
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center min-w-0">
          <HealthDot health={health} />
          <div className="min-w-0">
            <div className="font-semibold text-gray-900 truncate">{node.name}</div>
            <div className="text-xs text-gray-500">{node.status || 'unknown'} &middot; {health}</div>
          </div>
        </div>
        <button onClick={onClose} className="p-1 hover:bg-gray-100 rounded">
          <XMarkIcon className="w-4 h-4 text-gray-400" />
        </button>
      </div>

      {/* Golden Signals */}
      <Section title="Golden Signals">
        {agentSignals ? (
          <div className="text-xs space-y-0.5">
            <MetricRow label="Request rate" value={`${agentSignals.request_rate || 0}/s`} />
            <MetricRow label="Error rate" value={`${((agentSignals.error_rate || 0) * 100).toFixed(1)}%`} warn={agentSignals.error_rate > 0.05} />
            <MetricRow label="p95 latency" value={`${agentSignals.p95_latency_ms || 0}ms`} />
            <MetricRow label="Total requests" value={agentSignals.total_requests || 0} />
          </div>
        ) : (
          <div className="text-xs text-gray-400">No traffic data</div>
        )}
      </Section>

      {/* Configuration */}
      <Section title="Configuration">
        <div className="text-xs space-y-0.5">
          <MetricRow label="Endpoint type" value={node.endpointType || '-'} />
          <MetricRow label="Classification" value={node.classification || '-'} />
          <MetricRow label="Risk tier" value={node.riskTier || '-'} />
          <MetricRow label="Data sensitivity" value={node.dataSensitivity || '-'} />
          <MetricRow label="Zone" value={node.sovereigntyZone || 'default'} />
        </div>
      </Section>

      {/* Active Alerts */}
      <Section title={`Active Alerts (${alerts.length})`}>
        {alerts.length === 0 ? (
          <div className="text-xs text-gray-400">No active alerts</div>
        ) : (
          <div className="space-y-1.5">
            {alerts.slice(0, 5).map(alert => (
              <div key={alert.id} className="text-xs bg-red-50 border border-red-100 rounded px-2 py-1.5">
                <div className="font-medium text-red-800">{alert.rule_name || alert.alert_type}</div>
                <div className="text-red-600 text-[11px]">{alert.message}</div>
              </div>
            ))}
          </div>
        )}
      </Section>

      {/* Recent Traces */}
      <Section title="Recent Traces">
        {traces.length === 0 ? (
          <div className="text-xs text-gray-400">No recent traces</div>
        ) : (
          <div className="space-y-1">
            {traces.map(trace => (
              <div key={trace.task_id} className="text-xs border border-gray-100 rounded px-2 py-1">
                <div className="flex justify-between">
                  <span className="font-mono text-gray-600 truncate max-w-[180px]">{trace.task_id}</span>
                  <span className={trace.status === 'error' ? 'text-red-600' : 'text-green-600'}>{trace.status}</span>
                </div>
                <div className="text-[11px] text-gray-400">{trace.total_duration_ms}ms &middot; {trace.span_count} spans</div>
              </div>
            ))}
          </div>
        )}
      </Section>

      {/* Guardrails */}
      <Section title={`Guardrails (${guardrailList.length})`} className="border-b-0 pb-0 mb-0">
        {guardrailList.length === 0 ? (
          <div className="text-xs text-gray-400">No guardrails assigned</div>
        ) : (
          <div className="space-y-1">
            {guardrailList.map(g => (
              <div key={g.id} className="text-xs flex items-center gap-2">
                <span className={`w-1.5 h-1.5 rounded-full ${g.status === 'active' ? 'bg-green-500' : 'bg-gray-400'}`} />
                <span className="text-gray-700">{g.name}</span>
                <span className="text-gray-400 ml-auto">{g.guardrail_type}</span>
              </div>
            ))}
          </div>
        )}
      </Section>
    </>
  );
}

function EdgeSidebar({ edge, policies, onClose }) {
  const health = getEdgeHealth(edge);
  const errorRate = edge.count > 0 ? ((edge.blockedCount || 0) + (edge.errorCount || 0)) / edge.count : 0;
  const sourceName = typeof edge.source === 'object' ? edge.source.name : edge.source;
  const targetName = typeof edge.target === 'object' ? edge.target.name : edge.target;

  // Filter policies that apply to this edge
  const applicablePolicies = (policies || []).filter(p =>
    p.source_agent === sourceName || p.dest_agent === targetName ||
    p.source_agent === '*' || p.dest_agent === '*'
  );

  return (
    <>
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="min-w-0">
          <div className="font-semibold text-gray-900 text-sm">
            <HealthDot health={health} />
            <span className="truncate">{sourceName}</span>
            <span className="text-gray-400 mx-1">&rarr;</span>
            <span className="truncate">{targetName}</span>
          </div>
          <div className="text-xs text-gray-500">{edge.count || 0} interactions &middot; {health}</div>
        </div>
        <button onClick={onClose} className="p-1 hover:bg-gray-100 rounded">
          <XMarkIcon className="w-4 h-4 text-gray-400" />
        </button>
      </div>

      {/* Traffic */}
      <Section title="Traffic">
        <div className="text-xs space-y-0.5">
          <MetricRow label="Total count" value={edge.count || 0} />
          <MetricRow label="Blocked" value={edge.blockedCount || 0} warn={(edge.blockedCount || 0) > 0} />
          <MetricRow label="Errors" value={edge.errorCount || 0} warn={(edge.errorCount || 0) > 0} />
          <MetricRow label="Error rate" value={`${(errorRate * 100).toFixed(1)}%`} warn={errorRate > 0.05} />
        </div>
      </Section>

      {/* Last Interaction */}
      <Section title="Last Interaction">
        {edge.lastMethod ? (
          <div className="text-xs space-y-0.5">
            <MetricRow label="Method" value={edge.lastMethod || '-'} />
            <MetricRow label="Decision" value={edge.lastDecision || '-'} />
            <MetricRow label="Outcome" value={edge.outcome || '-'} />
            <MetricRow label="Time" value={edge.lastTimestamp ? new Date(edge.lastTimestamp).toLocaleString() : '-'} />
          </div>
        ) : (
          <div className="text-xs text-gray-400">No interactions recorded</div>
        )}
      </Section>

      {/* Policies */}
      <Section title={`Policies (${applicablePolicies.length})`}>
        {applicablePolicies.length === 0 ? (
          <div className="text-xs text-gray-400">No policies</div>
        ) : (
          <div className="space-y-1">
            {applicablePolicies.map((p, i) => (
              <div key={i} className="text-xs border border-gray-100 rounded px-2 py-1">
                <div className="flex justify-between">
                  <span className="text-gray-700">{p.name || `Policy ${i + 1}`}</span>
                  <span className={p.action === 'deny' ? 'text-red-600' : 'text-green-600'}>{p.action}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </Section>

      {/* Audit trail link */}
      <div className="text-xs border-b-0 pb-0 mb-0">
        <a href={`/observability?tab=audit&source=${sourceName}&dest=${targetName}`}
          className="text-teal-600 hover:text-teal-700 underline">
          View full audit trail &rarr;
        </a>
      </div>
    </>
  );
}

function ToolSidebar({ node, onClose }) {
  const { data: toolMetrics } = useQuery({
    queryKey: ['topology-sidebar-tool-metrics', node.displayName || node.name],
    queryFn: () => observability.tools.metrics({ tool_name: node.displayName || node.name }),
    enabled: true,
  });

  const metrics = toolMetrics?.tools?.[node.displayName || node.name] || toolMetrics || {};

  return (
    <>
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="min-w-0">
          <div className="font-semibold text-gray-900 truncate">{node.displayName || node.name}</div>
          <div className="text-xs text-gray-500">{node.status || 'unknown'} &middot; {node.mcpServerName ? 'MCP' : 'Tool'}</div>
        </div>
        <button onClick={onClose} className="p-1 hover:bg-gray-100 rounded">
          <XMarkIcon className="w-4 h-4 text-gray-400" />
        </button>
      </div>

      {/* Usage */}
      <Section title="Usage">
        <div className="text-xs space-y-0.5">
          <MetricRow label="Call count" value={metrics.call_count || metrics.total_calls || 0} />
          <MetricRow label="Error rate" value={`${((metrics.error_rate || 0) * 100).toFixed(1)}%`} warn={metrics.error_rate > 0.05} />
          <MetricRow label="Avg latency" value={`${metrics.avg_latency_ms || 0}ms`} />
        </div>
      </Section>

      {/* MCP Config */}
      {node.mcpServerName && (
        <Section title="MCP Configuration">
          <div className="text-xs space-y-0.5">
            <MetricRow label="Server" value={node.mcpServerName} />
            <MetricRow label="URL" value={node.mcpServerUrl || '-'} />
            {node.mcpServerDescription && (
              <div className="text-gray-600 mt-1">{node.mcpServerDescription}</div>
            )}
          </div>
        </Section>
      )}

      {/* Description */}
      {node.description && (
        <Section title="Description">
          <div className="text-xs text-gray-600">{node.description}</div>
        </Section>
      )}

      {/* Assigned Agents */}
      <Section title={`Assigned Agents (${(node.assignedAgents || []).length})`} className="border-b-0 pb-0 mb-0">
        {(node.assignedAgents || []).length === 0 ? (
          <div className="text-xs text-gray-400">No agents assigned</div>
        ) : (
          <div className="space-y-1">
            {node.assignedAgents.map(name => (
              <div key={name} className="text-xs text-gray-700 flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-teal-500" />
                {name}
              </div>
            ))}
          </div>
        )}
      </Section>
    </>
  );
}

export default function TopologySidebar({ item, type, goldenData, policies, onClose }) {
  const isOpen = !!item;

  return (
    <Transition show={isOpen} as={Fragment}>
      <div className="absolute top-0 right-0 h-full z-30">
        <Transition.Child
          as={Fragment}
          enter="transform transition ease-in-out duration-200"
          enterFrom="translate-x-full"
          enterTo="translate-x-0"
          leave="transform transition ease-in-out duration-200"
          leaveFrom="translate-x-0"
          leaveTo="translate-x-full"
        >
          <div className="w-[380px] h-full bg-white border-l border-gray-200 shadow-xl overflow-y-auto p-4">
            {type === 'agent' && item && (
              <AgentSidebar node={item} goldenData={goldenData} onClose={onClose} />
            )}
            {type === 'edge' && item && (
              <EdgeSidebar edge={item} policies={policies} onClose={onClose} />
            )}
            {type === 'tool' && item && (
              <ToolSidebar node={item} onClose={onClose} />
            )}
          </div>
        </Transition.Child>
      </div>
    </Transition>
  );
}
