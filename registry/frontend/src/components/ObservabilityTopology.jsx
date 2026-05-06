import { useEffect, useRef, useCallback, useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import * as d3 from 'd3';
import useSocket from '../hooks/useSocket';
import useMeshGraph, { getNodeHealth, getEdgeHealth, HEALTH_COLORS } from '../hooks/useMeshGraph';
import { meshVisualiser, observability } from '../api/client';
import TopologyToolbar from './TopologyToolbar';
import TopologyLegend from './TopologyLegend';
import TopologySidebar from './TopologySidebar';

const ZONE_COLOURS = ['#3B82F6', '#8B5CF6', '#F59E0B', '#EC4899', '#10B981', '#F97316'];
const TOOL_COLOUR = '#F59E0B';
const MCP_COLOUR = '#8B5CF6';
const NODE_BORDER = '#0A0F1C';
const NODE_RADIUS = 20;
const TOOL_NODE_SIZE = 16;

const PARTICLE_SUCCESS = '#10B981';
const PARTICLE_BLOCKED = '#EF4444';
const PARTICLE_ERROR = '#F59E0B';

function hullPath(points, padding = 30) {
  if (points.length < 2) return null;
  if (points.length === 2) {
    const [a, b] = points;
    const dx = b[0] - a[0];
    const dy = b[1] - a[1];
    const len = Math.sqrt(dx * dx + dy * dy) || 1;
    const nx = (-dy / len) * padding;
    const ny = (dx / len) * padding;
    return `M${a[0] + nx},${a[1] + ny}L${b[0] + nx},${b[1] + ny}
            A${padding},${padding} 0 0,1 ${b[0] - nx},${b[1] - ny}
            L${a[0] - nx},${a[1] - ny}
            A${padding},${padding} 0 0,1 ${a[0] + nx},${a[1] + ny}Z`;
  }
  const hull = d3.polygonHull(points);
  if (!hull) return null;
  const centroid = d3.polygonCentroid(hull);
  const expanded = hull.map(([x, y]) => {
    const dx = x - centroid[0];
    const dy = y - centroid[1];
    const len = Math.sqrt(dx * dx + dy * dy) || 1;
    return [x + (dx / len) * padding, y + (dy / len) * padding];
  });
  return `M${expanded.map(p => p.join(',')).join('L')}Z`;
}

export default function ObservabilityTopology() {
  const svgRef = useRef(null);
  const canvasRef = useRef(null);
  const simRef = useRef(null);
  const gRef = useRef(null);
  const zoneColourMapRef = useRef(new Map());
  const prevNodesRef = useRef(new Set());
  const particlesRef = useRef([]);
  const animFrameRef = useRef(null);

  // Toolbar state
  const [edgeLabelMode, setEdgeLabelMode] = useState('none');
  const [findQuery, setFindQuery] = useState('');
  const [zoneFilter, setZoneFilter] = useState('');
  const [showIdleNodes, setShowIdleNodes] = useState(true);
  const [showAnimation, setShowAnimation] = useState(true);
  const [timeRange, setTimeRange] = useState('live');
  const [showZones, setShowZones] = useState(false);

  // Sidebar state
  const [sidebarItem, setSidebarItem] = useState(null);
  const [sidebarType, setSidebarType] = useState(null);

  const [zoneLegend, setZoneLegend] = useState([]);

  const { nodes, edges, activeEdges, handleEvent, seedFromRest } = useMeshGraph();

  // Golden signals (10s poll)
  const { data: goldenData } = useQuery({
    queryKey: ['golden-signals'],
    queryFn: () => observability.goldenSignals.summary(),
    refetchInterval: 10000,
  });

  // Alerts (30s poll)
  const { data: alertsData } = useQuery({
    queryKey: ['topology-alerts'],
    queryFn: () => observability.alerts.list({ status: 'active' }),
    refetchInterval: 30000,
  });

  // Policies (60s poll)
  const { data: policiesData } = useQuery({
    queryKey: ['topology-policies'],
    queryFn: () => meshVisualiser.policies(),
    refetchInterval: 60000,
  });

  // Guardrails (60s poll) - for badge computation
  const { data: guardrailsData } = useQuery({
    queryKey: ['topology-guardrails'],
    queryFn: () => observability.security.posture(),
    refetchInterval: 60000,
  });

  // Pre-compute sets for badges
  const agentsWithAlerts = useMemo(() => {
    const set = new Set();
    (alertsData?.alerts || []).forEach(a => { if (a.agent_name) set.add(a.agent_name); });
    return set;
  }, [alertsData]);

  const agentsWithGuardrails = useMemo(() => {
    const set = new Set();
    const posture = guardrailsData?.agents || guardrailsData?.posture?.agents || {};
    Object.keys(posture).forEach(name => {
      if (posture[name]?.guardrail_count > 0 || posture[name]?.guardrails?.length > 0) set.add(name);
    });
    return set;
  }, [guardrailsData]);

  const policies = policiesData?.policies || [];

  // Build set of deny policy edges
  const denyEdges = useMemo(() => {
    const set = new Set();
    policies.forEach(p => {
      if (p.action === 'deny' && p.source_agent && p.dest_agent) {
        set.add(`${p.source_agent}->${p.dest_agent}`);
      }
    });
    return set;
  }, [policies]);

  // Collect sovereignty zones
  const allZones = useMemo(() => {
    const zones = new Set();
    nodes.forEach(n => { if (n.sovereigntyZone && n.sovereigntyZone !== 'default') zones.add(n.sovereigntyZone); });
    return [...zones].sort();
  }, [nodes]);

  // Seed from REST
  const loadData = useCallback(() => {
    Promise.all([
      meshVisualiser.registrations(),
      meshVisualiser.audit(),
      meshVisualiser.toolsWithAssignments(),
    ]).then(([regsData, auditData, toolsData]) => {
      const regs = regsData?.registrations || regsData || [];
      const audit = auditData?.records || auditData || [];
      const tools = toolsData?.tools || toolsData || [];
      seedFromRest(regs, audit, tools);
    }).catch(console.error);
  }, [seedFromRest]);

  useEffect(() => { loadData(); }, [loadData]);

  // WebSocket for live events + particle spawning
  useSocket('/mesh', useCallback((eventType, data) => {
    handleEvent(eventType, data);
    if (eventType === 'audit' && data.source_agent_name && data.dest_agent_name) {
      const outcome = data.outcome || 'success';
      const colour = outcome === 'blocked' ? PARTICLE_BLOCKED
        : outcome === 'error' ? PARTICLE_ERROR : PARTICLE_SUCCESS;
      const isToolCall = data.a2a_method === 'tools/call';
      particlesRef.current.push({
        source: data.source_agent_name,
        target: isToolCall ? `tool:${data.dest_agent_name}` : data.dest_agent_name,
        progress: 0,
        colour,
        isError: outcome !== 'success' && outcome !== 'allowed',
        createdAt: Date.now(),
      });
    }
  }, [handleEvent]));

  const getZoneColour = useCallback((zone) => {
    const map = zoneColourMapRef.current;
    if (!map.has(zone)) map.set(zone, ZONE_COLOURS[map.size % ZONE_COLOURS.length]);
    return map.get(zone);
  }, []);

  // Health-based node color
  const healthColor = useCallback((name, golden) => {
    return HEALTH_COLORS[getNodeHealth(name, golden)] || HEALTH_COLORS.idle;
  }, []);

  // Edge health color
  const edgeHealthColor = useCallback((edgeData) => {
    return HEALTH_COLORS[getEdgeHealth(edgeData)] || HEALTH_COLORS.idle;
  }, []);

  // Edge thickness scale (1-4px based on count)
  const edgeThickness = useCallback((edgeData) => {
    if (!edgeData.count) return 1;
    return Math.min(4, 1 + Math.log2(edgeData.count + 1));
  }, []);

  // Canvas particle animation loop
  useEffect(() => {
    const animate = () => {
      const canvas = canvasRef.current;
      const sim = simRef.current;
      if (!canvas || !sim) {
        animFrameRef.current = requestAnimationFrame(animate);
        return;
      }

      const ctx = canvas.getContext('2d');
      const rect = canvas.getBoundingClientRect();
      canvas.width = rect.width * (window.devicePixelRatio || 1);
      canvas.height = rect.height * (window.devicePixelRatio || 1);
      ctx.scale(window.devicePixelRatio || 1, window.devicePixelRatio || 1);
      ctx.clearRect(0, 0, rect.width, rect.height);

      if (!showAnimation) {
        animFrameRef.current = requestAnimationFrame(animate);
        return;
      }

      const g = gRef.current;
      if (!g) {
        animFrameRef.current = requestAnimationFrame(animate);
        return;
      }
      const transform = d3.zoomTransform(svgRef.current);

      const simNodes = sim.nodes();
      const nodeMap = {};
      for (const n of simNodes) nodeMap[n.name] = n;

      const now = Date.now();
      const particles = particlesRef.current;

      const alive = [];
      for (const p of particles) {
        p.progress += 0.02;
        if (p.progress > 1 || now - p.createdAt > 3000) continue;
        alive.push(p);

        const src = nodeMap[p.source];
        const tgt = nodeMap[p.target];
        if (!src || !tgt) continue;

        const x = src.x + (tgt.x - src.x) * p.progress;
        const y = src.y + (tgt.y - src.y) * p.progress;
        const sx = transform.applyX(x);
        const sy = transform.applyY(y);

        ctx.globalAlpha = 1 - p.progress * 0.5;
        if (p.isError) {
          // Diamond for errors
          ctx.save();
          ctx.translate(sx, sy);
          ctx.rotate(Math.PI / 4);
          ctx.fillStyle = p.colour;
          ctx.fillRect(-3, -3, 6, 6);
          ctx.restore();
        } else {
          // Circle for success
          ctx.beginPath();
          ctx.arc(sx, sy, 4, 0, Math.PI * 2);
          ctx.fillStyle = p.colour;
          ctx.fill();
        }
        ctx.globalAlpha = 1;
      }
      particlesRef.current = alive;

      animFrameRef.current = requestAnimationFrame(animate);
    };

    animFrameRef.current = requestAnimationFrame(animate);
    return () => {
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
    };
  }, [showAnimation]);

  // Initialize SVG
  useEffect(() => {
    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    const defs = svg.append('defs');
    const filter = defs.append('filter').attr('id', 'glow');
    filter.append('feGaussianBlur').attr('stdDeviation', '3').attr('result', 'blur');
    const merge = filter.append('feMerge');
    merge.append('feMergeNode').attr('in', 'blur');
    merge.append('feMergeNode').attr('in', 'SourceGraphic');

    const g = svg.append('g');
    gRef.current = g;

    g.append('g').attr('class', 'zones');
    g.append('g').attr('class', 'hulls');
    g.append('g').attr('class', 'edges');
    g.append('g').attr('class', 'edge-labels');
    g.append('g').attr('class', 'edge-hit');
    g.append('g').attr('class', 'nodes');

    const zoom = d3.zoom()
      .scaleExtent([0.1, 4])
      .on('zoom', (event) => g.attr('transform', event.transform));
    svg.call(zoom);

    // Click on background to close sidebar
    svg.on('click', () => {
      setSidebarItem(null);
      setSidebarType(null);
    });

    simRef.current = d3.forceSimulation()
      .force('charge', d3.forceManyBody().strength(-800))
      .force('collide', d3.forceCollide(NODE_RADIUS + 40))
      .force('x', d3.forceX(-80).strength(0.03))
      .force('y', d3.forceY().strength(0.03))
      .alphaDecay(0.02)
      .on('tick', () => tick());

    return () => {
      if (simRef.current) simRef.current.stop();
    };
  }, []);

  const tick = useCallback(() => {
    const g = gRef.current;
    if (!g) return;

    g.select('.edges').selectAll('line')
      .attr('x1', d => d.source.x).attr('y1', d => d.source.y)
      .attr('x2', d => d.target.x).attr('y2', d => d.target.y);

    g.select('.edge-hit').selectAll('line')
      .attr('x1', d => d.source.x).attr('y1', d => d.source.y)
      .attr('x2', d => d.target.x).attr('y2', d => d.target.y);

    g.select('.nodes').selectAll('.node-group')
      .attr('transform', d => `translate(${d.x},${d.y})`);

    // Edge labels positioning
    g.select('.edge-labels').selectAll('.edge-label-group')
      .attr('transform', d => {
        const mx = (d.source.x + d.target.x) / 2;
        const my = (d.source.y + d.target.y) / 2;
        return `translate(${mx},${my})`;
      });

    // Hull computation
    const sim = simRef.current;
    if (!sim) return;
    const simNodes = sim.nodes();
    const zoneGroups = {};
    for (const n of simNodes) {
      if (n.nodeType === 'tool') continue;
      const zone = n.sovereigntyZone || 'default';
      if (!zoneGroups[zone]) zoneGroups[zone] = [];
      zoneGroups[zone].push([n.x, n.y]);
    }

    const zoneData = Object.entries(zoneGroups)
      .filter(([, pts]) => pts.length >= 2)
      .map(([zone, pts]) => ({ zone, path: hullPath(pts, 50) }))
      .filter(d => d.path);

    const zones = g.select('.zones').selectAll('path').data(zoneData, d => d.zone);
    zones.exit().remove();
    zones.enter().append('path')
      .attr('fill', 'none')
      .attr('stroke-width', 2)
      .attr('stroke-dasharray', '8,4')
      .merge(zones)
      .attr('d', d => d.path)
      .attr('stroke', d => getZoneColour(d.zone))
      .attr('stroke-opacity', d => d.zone === 'default' ? 0 : 0.5);
  }, [getZoneColour]);

  // Update simulation when nodes/edges/golden data change
  useEffect(() => {
    const sim = simRef.current;
    const g = gRef.current;
    if (!sim || !g) return;

    const svgEl = svgRef.current;
    const svgWidth = svgEl?.clientWidth || 800;

    const allNodeValues = Array.from(nodes.values());
    let filteredNodes = allNodeValues;

    // Zone filter
    if (zoneFilter) {
      filteredNodes = filteredNodes.filter(n =>
        n.nodeType === 'tool' || n.sovereigntyZone === zoneFilter
      );
    }

    // Idle filter
    if (!showIdleNodes) {
      filteredNodes = filteredNodes.filter(n => {
        if (n.nodeType === 'tool') return true;
        return getNodeHealth(n.name, goldenData) !== 'idle';
      });
    }

    const toolValues = filteredNodes.filter(n => n.nodeType === 'tool');
    const agentValues = filteredNodes.filter(n => n.nodeType !== 'tool');

    const toolRightX = svgWidth / 2 - 60;
    const toolSpacing = 60;
    const toolStartY = -(toolValues.length - 1) * toolSpacing / 2;

    const nodeArray = [...agentValues, ...toolValues].map((n) => {
      const existing = sim.nodes().find(sn => sn.name === n.name);
      if (n.nodeType === 'tool') {
        const toolIdx = toolValues.indexOf(n);
        const fx = toolRightX;
        const fy = toolStartY + toolIdx * toolSpacing;
        return { ...n, x: fx, y: fy, fx, fy };
      }
      return {
        ...n,
        x: existing?.x ?? undefined,
        y: existing?.y ?? undefined,
        vx: existing?.vx ?? undefined,
        vy: existing?.vy ?? undefined,
      };
    });

    const nodeNameSet = new Set(nodeArray.map(n => n.name));
    const nodeMap = new Map(nodeArray.map(n => [n.name, n]));
    const edgeArray = Array.from(edges.values())
      .filter(e => nodeNameSet.has(e.source) && nodeNameSet.has(e.target))
      .map(e => ({
        ...e,
        source: nodeMap.get(e.source),
        target: nodeMap.get(e.target),
        key: `${e.source}->${e.target}`,
      }));

    sim.nodes(nodeArray);
    sim.force('link', d3.forceLink(edgeArray).id(d => d.name).distance(300).strength(0.2));

    // Cluster force
    sim.force('cluster', () => {
      const centroids = {};
      for (const n of nodeArray) {
        if (n.nodeType === 'tool') continue;
        const key = (showZones ? (n.sovereigntyZone || 'default') : 'all');
        if (!centroids[key]) centroids[key] = { x: 0, y: 0, count: 0 };
        centroids[key].x += n.x || 0;
        centroids[key].y += n.y || 0;
        centroids[key].count += 1;
      }
      for (const k of Object.keys(centroids)) {
        centroids[k].x /= centroids[k].count;
        centroids[k].y /= centroids[k].count;
      }
      const strength = showZones ? 0.01 : 0.005;
      for (const n of nodeArray) {
        if (n.nodeType === 'tool') continue;
        const key = (showZones ? (n.sovereigntyZone || 'default') : 'all');
        const c = centroids[key];
        if (c && c.count > 1) {
          n.vx += (c.x - n.x) * strength;
          n.vy += (c.y - n.y) * strength;
        }
      }
    });

    // Find query matching
    const findLower = findQuery.toLowerCase();
    const isSearching = findLower.length > 0;
    const matchesFind = (name) => !isSearching || name.toLowerCase().includes(findLower);

    // Render edges
    const edgeSel = g.select('.edges').selectAll('line').data(edgeArray, d => d.key);
    edgeSel.exit().remove();
    const edgeEnter = edgeSel.enter().append('line');
    const allEdges = edgeEnter.merge(edgeSel);
    allEdges
      .attr('stroke', d => {
        const isDeny = denyEdges.has(d.key);
        if (isDeny) return HEALTH_COLORS.failing;
        return edgeHealthColor(d);
      })
      .attr('stroke-width', d => edgeThickness(d))
      .attr('stroke-opacity', d => {
        if (isSearching) {
          const srcName = typeof d.source === 'object' ? d.source.name : d.source;
          const tgtName = typeof d.target === 'object' ? d.target.name : d.target;
          if (!matchesFind(srcName) && !matchesFind(tgtName)) return 0.1;
        }
        return activeEdges.has(d.key) ? 1 : 0.6;
      })
      .attr('stroke-dasharray', d => {
        if (denyEdges.has(d.key)) return '6,3';
        if (d.edgeType === 'tool-assignment') return '6,3';
        return null;
      })
      .attr('filter', d => activeEdges.has(d.key) ? 'url(#glow)' : null);

    // Edge labels
    const edgeLabelData = edgeLabelMode !== 'none' ? edgeArray : [];
    const labelSel = g.select('.edge-labels').selectAll('.edge-label-group').data(edgeLabelData, d => d.key);
    labelSel.exit().remove();
    const labelEnter = labelSel.enter().append('g').attr('class', 'edge-label-group');
    labelEnter.append('rect')
      .attr('fill', 'white')
      .attr('stroke', '#E5E7EB')
      .attr('stroke-width', 0.5)
      .attr('rx', 3)
      .attr('ry', 3);
    labelEnter.append('text')
      .attr('text-anchor', 'middle')
      .attr('dominant-baseline', 'central')
      .attr('font-size', '9px')
      .attr('fill', '#374151')
      .attr('pointer-events', 'none');

    const allLabels = labelEnter.merge(labelSel);
    allLabels.select('text').text(d => {
      const agentName = typeof d.source === 'object' ? d.source.name : d.source;
      const signals = goldenData?.agents?.[agentName];
      if (edgeLabelMode === 'traffic') return `${signals?.request_rate || 0}/s`;
      if (edgeLabelMode === 'errors') {
        const rate = d.count > 0 ? ((d.blockedCount || 0) + (d.errorCount || 0)) / d.count : 0;
        return `${(rate * 100).toFixed(1)}%`;
      }
      if (edgeLabelMode === 'latency') return `${signals?.p95_latency_ms || 0}ms`;
      return '';
    });
    allLabels.select('rect').each(function() {
      const text = d3.select(this.parentNode).select('text').node();
      if (text) {
        const bbox = text.getBBox();
        d3.select(this)
          .attr('x', bbox.x - 3)
          .attr('y', bbox.y - 1)
          .attr('width', bbox.width + 6)
          .attr('height', bbox.height + 2);
      }
    });

    // Edge hit areas
    const hitSel = g.select('.edge-hit').selectAll('line').data(edgeArray, d => d.key);
    hitSel.exit().remove();
    hitSel.enter().append('line')
      .attr('stroke', 'transparent')
      .attr('stroke-width', 15)
      .style('cursor', 'pointer')
      .on('click', (event, d) => {
        event.stopPropagation();
        setSidebarItem(d);
        setSidebarType('edge');
      });

    // Render nodes
    const nodeSel = g.select('.nodes').selectAll('.node-group').data(nodeArray, d => d.name);
    nodeSel.exit().remove();
    const nodeEnter = nodeSel.enter().append('g')
      .attr('class', 'node-group')
      .style('cursor', 'pointer')
      .call(d3.drag()
        .on('start', (event, d) => {
          if (!event.active) sim.alphaTarget(0.3).restart();
          d.fx = d.x; d.fy = d.y;
        })
        .on('drag', (event, d) => { d.fx = event.x; d.fy = event.y; })
        .on('end', (event, d) => {
          if (!event.active) sim.alphaTarget(0);
          if (d.nodeType !== 'tool') { d.fx = null; d.fy = null; }
        })
      )
      .on('click', (event, d) => {
        event.stopPropagation();
        setSidebarItem(d);
        setSidebarType(d.nodeType === 'tool' ? 'tool' : 'agent');
      });

    // Node shapes
    nodeEnter.each(function(d) {
      const el = d3.select(this);
      if (d.nodeType === 'tool') {
        if (d.mcpServerName) {
          el.append('polygon')
            .attr('points', `0,${-TOOL_NODE_SIZE} ${TOOL_NODE_SIZE},0 0,${TOOL_NODE_SIZE} ${-TOOL_NODE_SIZE},0`)
            .attr('stroke', NODE_BORDER).attr('stroke-width', 2)
            .attr('fill', MCP_COLOUR);
        } else {
          el.append('rect')
            .attr('x', -TOOL_NODE_SIZE).attr('y', -TOOL_NODE_SIZE)
            .attr('width', TOOL_NODE_SIZE * 2).attr('height', TOOL_NODE_SIZE * 2)
            .attr('rx', 4)
            .attr('stroke', NODE_BORDER).attr('stroke-width', 2)
            .attr('fill', TOOL_COLOUR);
        }
      } else {
        el.append('circle')
          .attr('r', NODE_RADIUS)
          .attr('stroke', NODE_BORDER).attr('stroke-width', 2);
      }
    });

    // Badges
    nodeEnter.each(function(d) {
      if (d.nodeType === 'tool') return;
      const el = d3.select(this);
      const badgeX = NODE_RADIUS - 2;
      const badgeY = -NODE_RADIUS - 2;
      let offset = 0;

      // Shield badge (guardrails)
      if (agentsWithGuardrails.has(d.name)) {
        el.append('g')
          .attr('class', 'badge-shield')
          .attr('transform', `translate(${badgeX - offset}, ${badgeY})`)
          .append('path')
          .attr('d', 'M0-5L4-3V1C4 3.5 2 5 0 6-2 5-4 3.5-4 1V-3L0-5Z')
          .attr('fill', '#14B8A6')
          .attr('stroke', 'white')
          .attr('stroke-width', 1);
        offset += 12;
      }

      // Lock badge (mTLS) — show when sidecar has mTLS
      if (d.agentCard?.security?.mtls || d.status === 'healthy') {
        el.append('g')
          .attr('class', 'badge-lock')
          .attr('transform', `translate(${badgeX - offset}, ${badgeY})`)
          .append('path')
          .attr('d', 'M-3 0H3V4H-3V0ZM-2-2V0H2V-2C2-3.1 1.1-4 0-4S-2-3.1-2-2Z')
          .attr('fill', '#10B981')
          .attr('stroke', 'white')
          .attr('stroke-width', 0.8);
        offset += 12;
      }

      // Warning badge (alerts)
      if (agentsWithAlerts.has(d.name)) {
        el.append('g')
          .attr('class', 'badge-warning')
          .attr('transform', `translate(${badgeX - offset}, ${badgeY})`)
          .append('path')
          .attr('d', 'M0-4L4 3H-4L0-4ZM0-1V1M0 2V3')
          .attr('fill', '#F59E0B')
          .attr('stroke', 'white')
          .attr('stroke-width', 0.8);
      }
    });

    // Find highlight ring
    nodeEnter.each(function(d) {
      if (d.nodeType === 'tool') return;
      d3.select(this).append('circle')
        .attr('class', 'find-ring')
        .attr('r', NODE_RADIUS + 4)
        .attr('fill', 'none')
        .attr('stroke', '#14B8A6')
        .attr('stroke-width', 2.5)
        .attr('opacity', 0);
    });

    nodeEnter.append('text')
      .attr('text-anchor', 'middle')
      .attr('dy', d => (d.nodeType === 'tool' ? TOOL_NODE_SIZE + 14 : NODE_RADIUS + 14))
      .attr('font-size', '11px')
      .attr('fill', '#374151')
      .attr('pointer-events', 'none');

    // Update all nodes
    const allNodes = g.select('.nodes').selectAll('.node-group');

    // Health-based coloring for agent nodes
    allNodes.select('circle:not(.find-ring)').attr('fill', d => healthColor(d.name, goldenData));
    allNodes.select('text:last-child').text(d => d.displayName || d.name);

    // Find/filter opacity
    allNodes.attr('opacity', d => {
      if (isSearching && !matchesFind(d.name)) return 0.2;
      return 1;
    });

    // Find highlight ring
    allNodes.select('.find-ring')
      .attr('opacity', d => (isSearching && matchesFind(d.name)) ? 1 : 0);

    // Zone legend
    const zones = [...new Set(nodeArray.filter(n => n.nodeType !== 'tool' && n.sovereigntyZone).map(n => n.sovereigntyZone))].sort();
    setZoneLegend(zones.map(z => ({ zone: z, colour: getZoneColour(z) })));

    const currentNames = new Set(nodeArray.map(n => n.name));
    const prevNames = prevNodesRef.current;
    const changed = [...currentNames].some(n => !prevNames.has(n)) || [...prevNames].some(n => !currentNames.has(n));
    prevNodesRef.current = currentNames;
    sim.alpha(changed ? 0.5 : 0.1).restart();
  }, [nodes, edges, showZones, goldenData, edgeLabelMode, findQuery, zoneFilter, showIdleNodes, activeEdges, denyEdges, agentsWithAlerts, agentsWithGuardrails, getZoneColour, healthColor, edgeHealthColor, edgeThickness]);

  const agentCount = Array.from(nodes.values()).filter(n => n.nodeType !== 'tool').length;
  const toolCount = Array.from(nodes.values()).filter(n => n.nodeType === 'tool').length;
  const edgeCount = edges.size;

  return (
    <div className="flex flex-col w-full h-full">
      <TopologyToolbar
        edgeLabelMode={edgeLabelMode}
        setEdgeLabelMode={setEdgeLabelMode}
        findQuery={findQuery}
        setFindQuery={setFindQuery}
        zoneFilter={zoneFilter}
        setZoneFilter={setZoneFilter}
        zones={allZones}
        showIdleNodes={showIdleNodes}
        setShowIdleNodes={setShowIdleNodes}
        showAnimation={showAnimation}
        setShowAnimation={setShowAnimation}
        timeRange={timeRange}
        setTimeRange={setTimeRange}
        onRefresh={loadData}
        agentCount={agentCount}
        toolCount={toolCount}
        edgeCount={edgeCount}
      />

      <div className="relative flex-1 overflow-hidden">
        {/* SVG layer */}
        <svg
          ref={svgRef}
          className="w-full h-full absolute inset-0"
          style={{ minHeight: '500px', background: '#FAFBFC' }}
        />

        {/* Canvas overlay for particles */}
        <canvas
          ref={canvasRef}
          className="w-full h-full absolute inset-0 pointer-events-none"
        />

        {/* Legend */}
        <TopologyLegend showZones={showZones} zoneLegend={zoneLegend} />

        {/* Sidebar */}
        <TopologySidebar
          item={sidebarItem}
          type={sidebarType}
          goldenData={goldenData}
          policies={policies}
          onClose={() => { setSidebarItem(null); setSidebarType(null); }}
        />
      </div>
    </div>
  );
}
