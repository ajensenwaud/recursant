import { useCallback, useRef, useState } from 'react';

const MAX_EVENT_LOG = 500;
// 8s glow per audit event — chosen to give viewers enough time to track
// activity on screen recordings, where short flashes are easy to miss.
const ACTIVITY_DURATION_MS = 8000;

/**
 * Extract hostname from a sidecar URL for host-based clustering.
 * e.g. "http://10.0.1.5:9000" -> "10.0.1.5"
 */
function extractHost(sidecarUrl) {
  if (!sidecarUrl) return 'unknown';
  try {
    const u = new URL(sidecarUrl);
    return u.hostname;
  } catch {
    return 'unknown';
  }
}

/**
 * Compute health status from golden signals error_rate.
 * @returns 'healthy'|'degraded'|'failing'|'idle'
 */
export function getNodeHealth(agentName, goldenSignals) {
  if (!goldenSignals?.agents?.[agentName]) return 'idle';
  const agent = goldenSignals.agents[agentName];
  if (!agent.total_requests || agent.total_requests === 0) return 'idle';
  const errorRate = agent.error_rate || 0;
  if (errorRate > 0.05) return 'failing';
  if (errorRate > 0.01) return 'degraded';
  return 'healthy';
}

/**
 * Compute edge-level health from blocked/error counts.
 * @returns 'healthy'|'degraded'|'failing'|'idle'
 */
export function getEdgeHealth(edgeData) {
  if (!edgeData || edgeData.count === 0) return 'idle';
  const errorRate = ((edgeData.blockedCount || 0) + (edgeData.errorCount || 0)) / edgeData.count;
  if (errorRate > 0.05) return 'failing';
  if (errorRate > 0.01) return 'degraded';
  return 'healthy';
}

export const HEALTH_COLORS = {
  healthy: '#10B981',
  degraded: '#F59E0B',
  failing: '#EF4444',
  idle: '#9CA3AF',
};

/**
 * Custom hook that manages the graph data model for the mesh visualiser.
 *
 * Maintains:
 * - nodes: Map<agentName, nodeData>
 * - edges: Map<"src->dest", edgeData>
 * - eventLog: array of recent events (newest first)
 * - activeEdges: Set of edge keys currently glowing
 *
 * Returns state + handler for processing incoming events.
 */
export default function useMeshGraph() {
  const [nodes, setNodes] = useState(new Map());
  const [edges, setEdges] = useState(new Map());
  const [eventLog, setEventLog] = useState([]);
  const [activeEdges, setActiveEdges] = useState(new Set());
  const timersRef = useRef(new Map());

  /**
   * Seed the graph with initial data from REST endpoints.
   * @param {Array} registrations - sidecar registrations
   * @param {Array} auditRecords - recent audit log records
   * @param {Array} tools - tools with assignments (from /mesh/tools/with-assignments)
   */
  const seedFromRest = useCallback((registrations, auditRecords, tools) => {
    // Build nodes from registrations
    const nodeMap = new Map();
    for (const reg of registrations) {
      const name = reg.agent_name || reg.agent_id;
      nodeMap.set(name, {
        id: reg.agent_id,
        name,
        sidecarUrl: reg.sidecar_url,
        host: extractHost(reg.sidecar_url),
        sovereigntyZone: reg.sovereignty_zone,
        status: reg.status,
        registeredAt: reg.registered_at,
        lastHeartbeat: reg.last_heartbeat,
        agentCard: reg.agent_card || {},
        endpointType: reg.endpoint_type,
        classification: reg.classification,
        riskTier: reg.risk_tier,
        dataSensitivity: reg.data_sensitivity,
      });
    }
    // Add tool nodes (approved tools only)
    const toolArray = tools || [];
    for (const tool of toolArray) {
      if (tool.status !== 'approved') continue;
      const name = `tool:${tool.name}`;
      nodeMap.set(name, {
        id: tool.id,
        name,
        displayName: tool.name,
        nodeType: 'tool',
        host: 'tools',
        status: tool.status,
        description: tool.description,
        mcpServerName: tool.mcp_server_name,
        mcpServerUrl: tool.mcp_server_url,
        mcpServerDescription: tool.mcp_server_description,
        backendServices: tool.backend_services,
        approvedBy: tool.approved_by,
        approvedAt: tool.approved_at,
        assignedAgents: (tool.assignments || []).map((a) => a.agent_name),
      });
    }
    setNodes(nodeMap);

    // Build edges from audit records
    const edgeMap = new Map();
    const logEntries = [];
    for (const rec of auditRecords) {
      const src = rec.source_agent_name;
      const dst = rec.dest_agent_name;
      if (!src || !dst) continue;
      // Tool calls target tool nodes (prefixed with "tool:")
      const isToolCall = rec.a2a_method === 'tools/call';
      const key = isToolCall ? `${src}->tool:${dst}` : `${src}->${dst}`;
      const target = isToolCall ? `tool:${dst}` : dst;
      const existing = edgeMap.get(key);
      if (existing) {
        existing.count += 1;
        if (rec.outcome === 'blocked') { existing.outcome = 'blocked'; existing.blockedCount = (existing.blockedCount || 0) + 1; }
        if (rec.outcome === 'error') { existing.errorCount = (existing.errorCount || 0) + 1; }
        // Always update to the newest record's details
        const recTime = rec.timestamp || '';
        const existTime = existing.lastTimestamp || '';
        if (recTime >= existTime) {
          existing.lastMethod = rec.a2a_method;
          existing.lastDirection = rec.direction;
          existing.lastDecision = rec.decision;
          existing.lastMessageHash = rec.message_hash;
          existing.lastTaskId = rec.task_id;
          existing.lastTimestamp = rec.timestamp;
          if (rec.outcome && rec.outcome !== 'pending') {
            existing.outcome = rec.outcome;
          }
        }
      } else {
        edgeMap.set(key, {
          source: src,
          target,
          lastActivity: null,
          outcome: rec.outcome || 'allowed',
          count: 1,
          blockedCount: rec.outcome === 'blocked' ? 1 : 0,
          errorCount: rec.outcome === 'error' ? 1 : 0,
          lastMethod: rec.a2a_method,
          lastDirection: rec.direction,
          lastDecision: rec.decision,
          lastMessageHash: rec.message_hash,
          lastTaskId: rec.task_id,
          lastTimestamp: rec.timestamp,
        });
      }
      logEntries.push({
        timestamp: rec.timestamp,
        source: src,
        dest: dst,
        method: rec.a2a_method,
        outcome: rec.outcome || 'allowed',
      });
    }
    // Build tool-assignment edges
    for (const tool of toolArray) {
      if (tool.status !== 'approved') continue;
      for (const assignment of tool.assignments || []) {
        const toolNodeName = `tool:${tool.name}`;
        const agentName = assignment.agent_name;
        const key = `${agentName}->tool:${tool.name}`;
        if (!edgeMap.has(key)) {
          edgeMap.set(key, {
            source: agentName,
            target: toolNodeName,
            edgeType: 'tool-assignment',
            lastActivity: null,
            outcome: 'allowed',
            count: 0,
            blockedCount: 0,
            errorCount: 0,
            lastMethod: null,
            lastDirection: null,
            lastDecision: null,
            lastMessageHash: null,
            lastTaskId: null,
            lastTimestamp: null,
          });
        }
      }
    }

    setEdges(edgeMap);
    setEventLog(logEntries.slice(0, MAX_EVENT_LOG));
  }, []);

  /**
   * Handle a real-time event from the WebSocket.
   */
  const handleEvent = useCallback((eventType, data) => {
    if (eventType === 'registration') {
      if (data.type === 'register') {
        setNodes((prev) => {
          const next = new Map(prev);
          next.set(data.agent_name, {
            id: data.agent_id,
            name: data.agent_name,
            sidecarUrl: data.sidecar_url,
            host: extractHost(data.sidecar_url),
            sovereigntyZone: data.sovereignty_zone,
            status: 'healthy',
            agentCard: data.agent_card || {},
          });
          return next;
        });
      } else if (data.type === 'deregister') {
        setNodes((prev) => {
          const next = new Map(prev);
          next.delete(data.agent_name);
          return next;
        });
      }
    } else if (eventType === 'audit') {
      const src = data.source_agent_name;
      const dst = data.dest_agent_name;
      if (!src || !dst) return;

      // For tool calls, route to the tool-assignment edge
      const isToolCall = data.a2a_method === 'tools/call';
      const key = isToolCall ? `${src}->tool:${dst}` : `${src}->${dst}`;

      // Upsert edge
      setEdges((prev) => {
        const next = new Map(prev);
        const existing = next.get(key);
        const edgeUpdate = {
          lastMethod: data.a2a_method,
          lastDirection: data.direction,
          lastDecision: data.decision,
          lastMessageHash: data.message_hash,
          lastTaskId: data.task_id,
          lastTimestamp: data.timestamp || new Date().toISOString(),
        };
        if (existing) {
          next.set(key, {
            ...existing,
            ...edgeUpdate,
            lastActivity: Date.now(),
            outcome: data.outcome || existing.outcome,
            count: existing.count + 1,
            blockedCount: (existing.blockedCount || 0) + (data.outcome === 'blocked' ? 1 : 0),
            errorCount: (existing.errorCount || 0) + (data.outcome === 'error' ? 1 : 0),
          });
        } else {
          next.set(key, {
            source: src,
            target: dst,
            lastActivity: Date.now(),
            outcome: data.outcome || 'allowed',
            count: 1,
            blockedCount: data.outcome === 'blocked' ? 1 : 0,
            errorCount: data.outcome === 'error' ? 1 : 0,
            ...edgeUpdate,
          });
        }
        return next;
      });

      // Activate edge glow
      setActiveEdges((prev) => {
        const next = new Set(prev);
        next.add(key);
        return next;
      });

      // Clear previous timer for this edge
      const prevTimer = timersRef.current.get(key);
      if (prevTimer) clearTimeout(prevTimer);

      // Set timer to deactivate glow
      const timer = setTimeout(() => {
        setActiveEdges((prev) => {
          const next = new Set(prev);
          next.delete(key);
          return next;
        });
        timersRef.current.delete(key);
      }, ACTIVITY_DURATION_MS);
      timersRef.current.set(key, timer);

      // Add to event log
      setEventLog((prev) => {
        const entry = {
          timestamp: data.timestamp || new Date().toISOString(),
          source: src,
          dest: dst,
          method: data.a2a_method || 'unknown',
          outcome: data.outcome || 'allowed',
        };
        const next = [entry, ...prev];
        if (next.length > MAX_EVENT_LOG) next.length = MAX_EVENT_LOG;
        return next;
      });
    }
  }, []);

  return {
    nodes,
    edges,
    eventLog,
    activeEdges,
    handleEvent,
    seedFromRest,
  };
}
