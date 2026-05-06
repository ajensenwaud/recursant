import { useEffect, useRef, useCallback, useState } from 'react';
import * as d3 from 'd3';

const HOST_COLOURS = [
  '#14B8A6', '#06D6A0', '#0F9690', '#6366F1', '#8B5CF6', '#EC4899',
  '#F59E0B', '#10B981', '#3B82F6', '#F97316', '#84CC16', '#06B6D4',
];

const EDGE_COLOUR_INACTIVE = '#94A3B8';
const EDGE_COLOUR_ACTIVE = '#14B8A6';
const EDGE_COLOUR_BLOCKED = '#EF4444';
const TOOL_COLOUR = '#F59E0B';
const TOOL_EDGE_COLOUR = '#D97706';
const NODE_BORDER = '#0A0F1C';
const NODE_RADIUS = 20;
const TOOL_NODE_SIZE = 16;

/**
 * Compute convex hull path for a set of points, with padding.
 */
function hullPath(points, padding = 30) {
  if (points.length < 2) return null;
  if (points.length === 2) {
    // Line between two points — create an ellipse-like path
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
  // Expand hull by padding
  const centroid = d3.polygonCentroid(hull);
  const expanded = hull.map(([x, y]) => {
    const dx = x - centroid[0];
    const dy = y - centroid[1];
    const len = Math.sqrt(dx * dx + dy * dy) || 1;
    return [x + (dx / len) * padding, y + (dy / len) * padding];
  });
  return `M${expanded.map(p => p.join(',')).join('L')}Z`;
}

/**
 * D3-powered SVG mesh graph with force layout, zoom/pan, host clustering.
 *
 * Props:
 * - nodes: Map<name, nodeData>
 * - edges: Map<key, edgeData>
 * - activeEdges: Set<key>
 * - onNodeClick: (nodeData) => void
 */
export default function MeshGraph({ nodes, edges, activeEdges, onNodeClick, onEdgeClick }) {
  const svgRef = useRef(null);
  const simRef = useRef(null);
  const gRef = useRef(null);
  const hostColourMapRef = useRef(new Map());
  const prevNodesRef = useRef(new Set());
  const [hostLegend, setHostLegend] = useState([]);

  const getHostColour = useCallback((host) => {
    const map = hostColourMapRef.current;
    if (!map.has(host)) {
      map.set(host, HOST_COLOURS[map.size % HOST_COLOURS.length]);
    }
    return map.get(host);
  }, []);

  // Initialize SVG + zoom once
  useEffect(() => {
    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    // SVG glow filter
    const defs = svg.append('defs');
    const filter = defs.append('filter').attr('id', 'glow');
    filter.append('feGaussianBlur').attr('stdDeviation', '3').attr('result', 'blur');
    const merge = filter.append('feMerge');
    merge.append('feMergeNode').attr('in', 'blur');
    merge.append('feMergeNode').attr('in', 'SourceGraphic');

    const g = svg.append('g');
    gRef.current = g;

    // Layer ordering: hulls -> edges -> edge-hit (invisible click targets) -> nodes
    g.append('g').attr('class', 'hulls');
    g.append('g').attr('class', 'edges');
    g.append('g').attr('class', 'edge-hit');
    g.append('g').attr('class', 'nodes');

    // Zoom & pan
    const zoom = d3.zoom()
      .scaleExtent([0.1, 4])
      .on('zoom', (event) => {
        g.attr('transform', event.transform);
      });
    svg.call(zoom);

    // Initialize force simulation — bias agents left to leave space for tool column on right
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

  // Tick function — updates positions of all SVG elements
  const tick = useCallback(() => {
    const g = gRef.current;
    if (!g) return;

    // Update edges
    g.select('.edges').selectAll('line')
      .attr('x1', d => d.source.x)
      .attr('y1', d => d.source.y)
      .attr('x2', d => d.target.x)
      .attr('y2', d => d.target.y);

    // Update edge hit areas
    g.select('.edge-hit').selectAll('line')
      .attr('x1', d => d.source.x)
      .attr('y1', d => d.source.y)
      .attr('x2', d => d.target.x)
      .attr('y2', d => d.target.y);

    // Update nodes
    g.select('.nodes').selectAll('.node-group')
      .attr('transform', d => `translate(${d.x},${d.y})`);

    // Update hulls — exclude tool nodes from host clustering
    const sim = simRef.current;
    if (!sim) return;
    const simNodes = sim.nodes();
    const hostGroups = {};
    for (const n of simNodes) {
      if (n.nodeType === 'tool') continue;
      if (!hostGroups[n.host]) hostGroups[n.host] = [];
      hostGroups[n.host].push([n.x, n.y]);
    }

    const hullData = Object.entries(hostGroups)
      .filter(([, pts]) => pts.length >= 2)
      .map(([host, pts]) => ({ host, path: hullPath(pts) }))
      .filter(d => d.path);

    const hulls = g.select('.hulls').selectAll('path').data(hullData, d => d.host);
    hulls.exit().remove();
    hulls.enter().append('path')
      .attr('fill', d => getHostColour(d.host))
      .attr('opacity', 0.1)
      .attr('stroke', d => getHostColour(d.host))
      .attr('stroke-width', 1)
      .attr('stroke-opacity', 0.3)
      .merge(hulls)
      .attr('d', d => d.path);
  }, [getHostColour]);

  // Update simulation when nodes/edges change
  useEffect(() => {
    const sim = simRef.current;
    const g = gRef.current;
    if (!sim || !g) return;

    // Get SVG dimensions for tool anchoring
    const svgEl = svgRef.current;
    const svgWidth = svgEl?.clientWidth || 800;
    const svgHeight = svgEl?.clientHeight || 500;

    // Separate tool nodes from agent nodes
    const allNodeValues = Array.from(nodes.values());
    const toolValues = allNodeValues.filter(n => n.nodeType === 'tool');
    const agentValues = allNodeValues.filter(n => n.nodeType !== 'tool');

    // Position tool nodes anchored to the right side
    const toolRightX = svgWidth / 2 - 60;  // right side (in simulation coords centered at 0)
    const toolSpacing = 60;
    const toolStartY = -(toolValues.length - 1) * toolSpacing / 2;

    // Convert nodes Map to array
    const nodeArray = [...agentValues, ...toolValues].map((n, _, arr) => {
      // Preserve position if node already exists in simulation
      const existing = sim.nodes().find(sn => sn.name === n.name);

      if (n.nodeType === 'tool') {
        const toolIdx = toolValues.indexOf(n);
        const fixedX = toolRightX;
        const fixedY = toolStartY + toolIdx * toolSpacing;
        return {
          ...n,
          x: fixedX,
          y: fixedY,
          fx: fixedX,  // pin x position
          fy: fixedY,  // pin y position
        };
      }

      return {
        ...n,
        x: existing?.x ?? undefined,
        y: existing?.y ?? undefined,
        vx: existing?.vx ?? undefined,
        vy: existing?.vy ?? undefined,
      };
    });

    // Convert edges Map to array with node references
    const nodeMap = new Map(nodeArray.map(n => [n.name, n]));
    const edgeArray = Array.from(edges.values())
      .filter(e => nodeMap.has(e.source) && nodeMap.has(e.target))
      .map(e => ({
        ...e,
        source: nodeMap.get(e.source),
        target: nodeMap.get(e.target),
        key: `${e.source}->${e.target}`,
      }));

    // Update simulation nodes
    sim.nodes(nodeArray);
    sim.force('link', d3.forceLink(edgeArray).id(d => d.name).distance(250).strength(0.2));

    // Custom cluster force — pull same-host agent nodes together (skip tools)
    sim.force('cluster', () => {
      const hostCentroids = {};
      for (const n of nodeArray) {
        if (n.nodeType === 'tool') continue;
        if (!hostCentroids[n.host]) hostCentroids[n.host] = { x: 0, y: 0, count: 0 };
        hostCentroids[n.host].x += n.x || 0;
        hostCentroids[n.host].y += n.y || 0;
        hostCentroids[n.host].count += 1;
      }
      for (const key of Object.keys(hostCentroids)) {
        hostCentroids[key].x /= hostCentroids[key].count;
        hostCentroids[key].y /= hostCentroids[key].count;
      }
      for (const n of nodeArray) {
        if (n.nodeType === 'tool') continue;
        const c = hostCentroids[n.host];
        if (c && c.count > 1) {
          n.vx += (c.x - n.x) * 0.005;
          n.vy += (c.y - n.y) * 0.005;
        }
      }
    });

    // --- Render edges ---
    const edgeSel = g.select('.edges').selectAll('line').data(edgeArray, d => d.key);
    edgeSel.exit().remove();
    edgeSel.enter().append('line')
      .attr('stroke', d => {
        if (d.outcome === 'blocked') return EDGE_COLOUR_BLOCKED;
        return d.edgeType === 'tool-assignment' ? TOOL_EDGE_COLOUR : EDGE_COLOUR_INACTIVE;
      })
      .attr('stroke-width', 1.5)
      .attr('stroke-opacity', d => d.outcome === 'blocked' ? 0.35 : 0.6)
      .attr('stroke-dasharray', d => {
        if (d.edgeType === 'tool-assignment') return '6,3';
        if (d.outcome === 'blocked') return '4,3';
        return null;
      });

    // --- Render edge hit areas (invisible wider lines for click targeting) ---
    const hitSel = g.select('.edge-hit').selectAll('line').data(edgeArray, d => d.key);
    hitSel.exit().remove();
    hitSel.enter().append('line')
      .attr('stroke', 'transparent')
      .attr('stroke-width', 15)
      .style('cursor', 'pointer')
      .on('click', (event, d) => {
        event.stopPropagation();
        if (onEdgeClick) onEdgeClick(d, event);
      });

    // --- Render nodes ---
    const nodeSel = g.select('.nodes').selectAll('.node-group').data(nodeArray, d => d.name);
    nodeSel.exit().remove();
    const nodeEnter = nodeSel.enter().append('g')
      .attr('class', 'node-group')
      .style('cursor', 'pointer')
      .call(d3.drag()
        .on('start', (event, d) => {
          if (!event.active) sim.alphaTarget(0.3).restart();
          d.fx = d.x;
          d.fy = d.y;
        })
        .on('drag', (event, d) => {
          d.fx = event.x;
          d.fy = event.y;
        })
        .on('end', (event, d) => {
          if (!event.active) sim.alphaTarget(0);
          // Keep tool nodes pinned; release agent nodes
          if (d.nodeType !== 'tool') {
            d.fx = null;
            d.fy = null;
          }
        })
      )
      .on('click', (event, d) => {
        event.stopPropagation();
        if (onNodeClick) onNodeClick(d);
      });

    // Render shape: rect for tools, circle for agents
    nodeEnter.each(function(d) {
      const el = d3.select(this);
      if (d.nodeType === 'tool') {
        el.append('rect')
          .attr('x', -TOOL_NODE_SIZE)
          .attr('y', -TOOL_NODE_SIZE)
          .attr('width', TOOL_NODE_SIZE * 2)
          .attr('height', TOOL_NODE_SIZE * 2)
          .attr('rx', 4)
          .attr('stroke', NODE_BORDER)
          .attr('stroke-width', 2)
          .attr('fill', TOOL_COLOUR);
      } else {
        el.append('circle')
          .attr('r', NODE_RADIUS)
          .attr('stroke', NODE_BORDER)
          .attr('stroke-width', 2);
      }
    });

    nodeEnter.append('text')
      .attr('text-anchor', 'middle')
      .attr('dy', d => (d.nodeType === 'tool' ? TOOL_NODE_SIZE + 14 : NODE_RADIUS + 14))
      .attr('font-size', '11px')
      .attr('fill', '#374151')
      .attr('pointer-events', 'none');

    // Update all nodes (enter + update)
    const allNodes = g.select('.nodes').selectAll('.node-group');
    allNodes.select('circle')
      .attr('fill', d => getHostColour(d.host));
    allNodes.select('rect')
      .attr('fill', TOOL_COLOUR);
    allNodes.select('text')
      .text(d => d.displayName || d.name);

    // Update host legend — exclude 'tools' virtual host
    const hosts = [...new Set(nodeArray.filter(n => n.nodeType !== 'tool').map(n => n.host))].sort();
    setHostLegend(hosts.map(h => ({ host: h, colour: getHostColour(h) })));

    // Check for new nodes — only reheat if topology changed
    const currentNames = new Set(nodeArray.map(n => n.name));
    const prevNames = prevNodesRef.current;
    const added = [...currentNames].some(n => !prevNames.has(n));
    const removed = [...prevNames].some(n => !currentNames.has(n));
    prevNodesRef.current = currentNames;

    if (added || removed) {
      sim.alpha(0.5).restart();
    } else {
      sim.alpha(0.1).restart();
    }
  }, [nodes, edges, onNodeClick, onEdgeClick, getHostColour]);

  // Update edge visual state for active/blocked edges
  useEffect(() => {
    const g = gRef.current;
    if (!g) return;

    g.select('.edges').selectAll('line')
      .attr('stroke', d => {
        const key = d.key;
        const isBlocked = d.outcome === 'blocked';
        if (activeEdges.has(key)) {
          if (isBlocked) return EDGE_COLOUR_BLOCKED;
          return d.edgeType === 'tool-assignment' ? TOOL_COLOUR : EDGE_COLOUR_ACTIVE;
        }
        // Inactive state: blocked edges stay red, others use default colours
        if (isBlocked) return EDGE_COLOUR_BLOCKED;
        return d.edgeType === 'tool-assignment' ? TOOL_EDGE_COLOUR : EDGE_COLOUR_INACTIVE;
      })
      .attr('stroke-width', d => activeEdges.has(d.key) ? 3 : 1.5)
      .attr('stroke-opacity', d => {
        if (activeEdges.has(d.key)) return 1;
        if (d.outcome === 'blocked') return 0.35;
        return 0.6;
      })
      .attr('filter', d => activeEdges.has(d.key) ? 'url(#glow)' : null)
      .attr('stroke-dasharray', d => {
        if (d.edgeType === 'tool-assignment') return '6,3';
        if (d.outcome === 'blocked' && !activeEdges.has(d.key)) return '4,3';
        return null;
      });
  }, [activeEdges]);

  return (
    <div className="relative w-full h-full">
      <svg
        ref={svgRef}
        className="w-full h-full"
        style={{ minHeight: '500px', background: '#FAFBFC' }}
      />
      {hostLegend.length > 0 && (
        <div className="absolute bottom-4 right-4 bg-white/90 border border-gray-200 rounded-lg shadow-sm px-3 py-2 text-xs">
          <div className="font-semibold text-gray-600 mb-1">Hosts</div>
          {hostLegend.map(({ host, colour }) => (
            <div key={host} className="flex items-center gap-2 py-0.5">
              <span
                className="inline-block w-3 h-3 rounded-full flex-shrink-0"
                style={{ backgroundColor: colour }}
              />
              <span className="text-gray-700 truncate max-w-[200px]">{host}</span>
            </div>
          ))}
          <div className="flex items-center gap-2 py-0.5 border-t border-gray-200 mt-1 pt-1">
            <span
              className="inline-block w-3 h-3 rounded-sm flex-shrink-0"
              style={{ backgroundColor: TOOL_COLOUR }}
            />
            <span className="text-gray-700">Tools</span>
          </div>
        </div>
      )}
    </div>
  );
}
