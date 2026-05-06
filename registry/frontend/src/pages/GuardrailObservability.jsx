import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import * as d3 from 'd3';
import {
  ShieldCheckIcon,
  NoSymbolIcon,
  ClockIcon,
  BoltIcon,
} from '@heroicons/react/24/outline';
import { guardrailObservability } from '../api/client';
import useSocket from '../hooks/useSocket';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const ACTION_BADGE = {
  pass: 'bg-green-100 text-green-800',
  block: 'bg-red-100 text-red-800',
  warn: 'bg-yellow-100 text-yellow-800',
  redact: 'bg-purple-100 text-purple-800',
};

const TRIGGER_COLORS = {
  pass: '#22C55E',
  block: '#EF4444',
  warn: '#EAB308',
  redact: '#A855F7',
};

const LATENCY_COLORS = {
  p50: '#14B8A6',
  p95: '#F59E0B',
  p99: '#EF4444',
};

const DRIFT_ARROWS = {
  up: { symbol: '\u2191', color: 'text-red-600' },
  down: { symbol: '\u2193', color: 'text-green-600' },
  stable: { symbol: '\u2192', color: 'text-gray-500' },
};

const DEBOUNCE_MS = 3000;
const MAX_LIVE_EVENTS = 20;

// ---------------------------------------------------------------------------
// Summary Card
// ---------------------------------------------------------------------------

function SummaryCard({ icon: Icon, value, label, color }) {
  return (
    <div className="bg-white rounded-lg border border-gray-200 p-5">
      <div className="flex items-center gap-3">
        <div className={`p-2.5 rounded-lg ${color}`}>
          <Icon className="h-5 w-5 text-white" />
        </div>
        <div>
          <p className="text-2xl font-bold text-gray-900">{value}</p>
          <p className="text-sm text-gray-500">{label}</p>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Trigger Rate Time Series (d3 line chart)
// ---------------------------------------------------------------------------

function TriggerRateChart({ data }) {
  const svgRef = useRef(null);
  const containerRef = useRef(null);

  useEffect(() => {
    if (!data || !data.buckets || data.buckets.length === 0) return;

    const container = containerRef.current;
    const width = container.clientWidth;
    const height = 300;
    const margin = { top: 20, right: 20, bottom: 40, left: 50 };

    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();
    svg.attr('width', width).attr('height', height);

    const innerW = width - margin.left - margin.right;
    const innerH = height - margin.top - margin.bottom;

    const g = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`);

    const buckets = data.buckets;

    const x = d3.scaleTime()
      .domain(d3.extent(buckets, (d) => new Date(d.timestamp)))
      .range([0, innerW]);

    const allCounts = buckets.flatMap((b) => [b.pass || 0, b.block || 0, b.warn || 0, b.redact || 0]);
    const y = d3.scaleLinear()
      .domain([0, d3.max(allCounts) || 1])
      .nice()
      .range([innerH, 0]);

    // Grid lines
    g.append('g')
      .attr('class', 'grid')
      .call(d3.axisLeft(y).tickSize(-innerW).tickFormat(''))
      .selectAll('line')
      .attr('stroke', '#E5E7EB')
      .attr('stroke-dasharray', '2,2');
    g.selectAll('.grid .domain').remove();

    // Axes
    g.append('g')
      .attr('transform', `translate(0,${innerH})`)
      .call(d3.axisBottom(x).ticks(6).tickFormat(d3.timeFormat('%H:%M')))
      .selectAll('text')
      .attr('fill', '#6B7280')
      .style('font-size', '11px');

    g.append('g')
      .call(d3.axisLeft(y).ticks(5))
      .selectAll('text')
      .attr('fill', '#6B7280')
      .style('font-size', '11px');

    // Remove domain lines
    g.selectAll('.domain').attr('stroke', '#D1D5DB');

    // Line generator
    const lineGen = (key) =>
      d3.line()
        .defined((d) => d[key] != null)
        .x((d) => x(new Date(d.timestamp)))
        .y((d) => y(d[key] || 0))
        .curve(d3.curveMonotoneX);

    Object.entries(TRIGGER_COLORS).forEach(([key, color]) => {
      g.append('path')
        .datum(buckets)
        .attr('fill', 'none')
        .attr('stroke', color)
        .attr('stroke-width', 2)
        .attr('d', lineGen(key));
    });
  }, [data]);

  return (
    <div ref={containerRef} className="w-full">
      <svg ref={svgRef} className="w-full" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Latency Breakdown (d3 grouped bar chart)
// ---------------------------------------------------------------------------

function LatencyChart({ data }) {
  const svgRef = useRef(null);
  const containerRef = useRef(null);

  useEffect(() => {
    if (!data || !data.mechanisms || data.mechanisms.length === 0) return;

    const container = containerRef.current;
    const width = container.clientWidth;
    const height = 280;
    const margin = { top: 20, right: 20, bottom: 60, left: 55 };

    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();
    svg.attr('width', width).attr('height', height);

    const innerW = width - margin.left - margin.right;
    const innerH = height - margin.top - margin.bottom;

    const g = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`);

    const mechanisms = data.mechanisms;
    const percentiles = ['p50', 'p95', 'p99'];

    const x0 = d3.scaleBand()
      .domain(mechanisms.map((d) => d.mechanism))
      .range([0, innerW])
      .paddingInner(0.2);

    const x1 = d3.scaleBand()
      .domain(percentiles)
      .range([0, x0.bandwidth()])
      .padding(0.1);

    const allVals = mechanisms.flatMap((m) => percentiles.map((p) => m[p] || 0));
    const y = d3.scaleLinear()
      .domain([0, d3.max(allVals) || 1])
      .nice()
      .range([innerH, 0]);

    // Grid
    g.append('g')
      .call(d3.axisLeft(y).tickSize(-innerW).tickFormat(''))
      .selectAll('line')
      .attr('stroke', '#E5E7EB')
      .attr('stroke-dasharray', '2,2');
    g.selectAll('.grid .domain').remove();

    // Axes
    g.append('g')
      .attr('transform', `translate(0,${innerH})`)
      .call(d3.axisBottom(x0))
      .selectAll('text')
      .attr('fill', '#6B7280')
      .style('font-size', '11px')
      .attr('transform', 'rotate(-25)')
      .attr('text-anchor', 'end');

    g.append('g')
      .call(d3.axisLeft(y).ticks(5).tickFormat((d) => `${d}ms`))
      .selectAll('text')
      .attr('fill', '#6B7280')
      .style('font-size', '11px');

    g.selectAll('.domain').attr('stroke', '#D1D5DB');

    // Grouped bars
    const groups = g.selectAll('.bar-group')
      .data(mechanisms)
      .join('g')
      .attr('transform', (d) => `translate(${x0(d.mechanism)},0)`);

    percentiles.forEach((p) => {
      groups.append('rect')
        .attr('x', x1(p))
        .attr('width', x1.bandwidth())
        .attr('y', (d) => y(d[p] || 0))
        .attr('height', (d) => innerH - y(d[p] || 0))
        .attr('fill', LATENCY_COLORS[p])
        .attr('rx', 2);
    });
  }, [data]);

  return (
    <div ref={containerRef} className="w-full">
      <svg ref={svgRef} className="w-full" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Top Blocked Patterns table
// ---------------------------------------------------------------------------

function TopBlockedTable({ data }) {
  const [sortDir, setSortDir] = useState('desc');

  const patterns = useMemo(() => {
    if (!data || !data.patterns) return [];
    const items = [...data.patterns];
    items.sort((a, b) => sortDir === 'desc' ? b.count - a.count : a.count - b.count);
    return items;
  }, [data, sortDir]);

  const total = useMemo(
    () => patterns.reduce((s, p) => s + (p.count || 0), 0),
    [patterns],
  );

  return (
    <div className="overflow-auto">
      <table className="min-w-full divide-y divide-gray-200">
        <thead className="bg-gray-50">
          <tr>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Pattern</th>
            <th
              className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer select-none"
              onClick={() => setSortDir((d) => (d === 'desc' ? 'asc' : 'desc'))}
            >
              Count {sortDir === 'desc' ? '\u25BC' : '\u25B2'}
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">% of Total</th>
          </tr>
        </thead>
        <tbody className="bg-white divide-y divide-gray-200">
          {patterns.length === 0 ? (
            <tr>
              <td colSpan={3} className="px-4 py-8 text-center text-gray-500 text-sm">No blocked patterns recorded.</td>
            </tr>
          ) : (
            patterns.map((p, i) => (
              <tr key={i} className="hover:bg-gray-50">
                <td className="px-4 py-3 text-sm text-gray-900 font-mono">{p.pattern}</td>
                <td className="px-4 py-3 text-sm text-gray-700">{p.count.toLocaleString()}</td>
                <td className="px-4 py-3 text-sm text-gray-700">
                  {total > 0 ? ((p.count / total) * 100).toFixed(1) : '0.0'}%
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Drift Detection table
// ---------------------------------------------------------------------------

function DriftTable({ data }) {
  const rows = data?.guardrails || [];

  return (
    <div className="overflow-auto">
      <table className="min-w-full divide-y divide-gray-200">
        <thead className="bg-gray-50">
          <tr>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Guardrail</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Recent Block Rate</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Historical Block Rate</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Drift</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Trend</th>
          </tr>
        </thead>
        <tbody className="bg-white divide-y divide-gray-200">
          {rows.length === 0 ? (
            <tr>
              <td colSpan={5} className="px-4 py-8 text-center text-gray-500 text-sm">No drift data available.</td>
            </tr>
          ) : (
            rows.map((r, i) => {
              const arrow = DRIFT_ARROWS[r.trend] || DRIFT_ARROWS.stable;
              return (
                <tr key={i} className="hover:bg-gray-50">
                  <td className="px-4 py-3 text-sm text-gray-900 font-medium">{r.guardrail}</td>
                  <td className="px-4 py-3 text-sm text-gray-700">{(r.recent_block_rate * 100).toFixed(1)}%</td>
                  <td className="px-4 py-3 text-sm text-gray-700">{(r.historical_block_rate * 100).toFixed(1)}%</td>
                  <td className="px-4 py-3 text-sm text-gray-700">
                    {r.drift > 0 ? '+' : ''}{(r.drift * 100).toFixed(1)}%
                  </td>
                  <td className="px-4 py-3 text-sm">
                    <span className={`font-bold text-lg ${arrow.color}`}>{arrow.symbol}</span>
                  </td>
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Live Event Feed
// ---------------------------------------------------------------------------

function LiveEventFeed({ events }) {
  return (
    <div className="space-y-2 max-h-96 overflow-y-auto">
      {events.length === 0 ? (
        <p className="text-sm text-gray-500 text-center py-8">Waiting for live events...</p>
      ) : (
        events.map((evt, i) => (
          <div
            key={`${evt.timestamp}-${i}`}
            className="flex items-center gap-3 px-4 py-2.5 bg-gray-50 rounded-lg text-sm animate-slideIn"
          >
            <span className="text-xs text-gray-400 font-mono whitespace-nowrap">
              {evt.timestamp ? new Date(evt.timestamp).toLocaleTimeString() : '--:--:--'}
            </span>
            <span className="text-gray-700 truncate">{evt.guardrail_name || 'Unknown'}</span>
            <span className="text-gray-500 truncate">{evt.agent_name || '-'}</span>
            <span
              className={`ml-auto inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium whitespace-nowrap ${
                ACTION_BADGE[evt.action] || 'bg-gray-100 text-gray-800'
              }`}
            >
              {evt.action || 'unknown'}
            </span>
          </div>
        ))
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Page
// ---------------------------------------------------------------------------

export default function GuardrailObservability() {
  const queryClient = useQueryClient();

  // -- Filters --
  const [interval, setInterval_] = useState('1h');
  const [agentName, setAgentName] = useState('');
  const [guardrailFilter, setGuardrailFilter] = useState('');

  // -- Live events --
  const [liveEvents, setLiveEvents] = useState([]);
  const debounceRef = useRef(null);

  // -- Queries --
  const { data: summaryData, isLoading: summaryLoading } = useQuery({
    queryKey: ['guardrail-obs-summary'],
    queryFn: () => guardrailObservability.summary(),
  });

  const triggerParams = useMemo(
    () => ({
      interval: interval || undefined,
      agent_name: agentName || undefined,
      guardrail: guardrailFilter || undefined,
    }),
    [interval, agentName, guardrailFilter],
  );

  const { data: triggerData, isLoading: triggerLoading } = useQuery({
    queryKey: ['guardrail-obs-trigger-rates', triggerParams],
    queryFn: () => guardrailObservability.triggerRates(triggerParams),
  });

  const { data: latencyData, isLoading: latencyLoading } = useQuery({
    queryKey: ['guardrail-obs-latency'],
    queryFn: () => guardrailObservability.latency(),
  });

  const { data: blockedData, isLoading: blockedLoading } = useQuery({
    queryKey: ['guardrail-obs-top-blocked'],
    queryFn: () => guardrailObservability.topBlocked(),
  });

  const { data: driftData, isLoading: driftLoading } = useQuery({
    queryKey: ['guardrail-obs-drift'],
    queryFn: () => guardrailObservability.drift(),
  });

  // -- Debounced refetch helper --
  const debouncedRefetch = useCallback(() => {
    if (debounceRef.current) return;
    debounceRef.current = setTimeout(() => {
      debounceRef.current = null;
      queryClient.invalidateQueries({ queryKey: ['guardrail-obs-summary'] });
      queryClient.invalidateQueries({ queryKey: ['guardrail-obs-trigger-rates'] });
      queryClient.invalidateQueries({ queryKey: ['guardrail-obs-latency'] });
      queryClient.invalidateQueries({ queryKey: ['guardrail-obs-top-blocked'] });
      queryClient.invalidateQueries({ queryKey: ['guardrail-obs-drift'] });
    }, DEBOUNCE_MS);
  }, [queryClient]);

  // Cleanup debounce timer on unmount
  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  // -- WebSocket handler --
  const handleSocketEvent = useCallback(
    (eventType, data) => {
      if (eventType !== 'guardrail-event') return;
      setLiveEvents((prev) => [data, ...prev].slice(0, MAX_LIVE_EVENTS));
      debouncedRefetch();
    },
    [debouncedRefetch],
  );

  useSocket('/mesh', handleSocketEvent);

  // -- Summary values --
  const totalEvents = summaryData?.total_events ?? 0;
  const blockRate = summaryData?.block_rate != null
    ? (summaryData.block_rate * 100).toFixed(1)
    : '0.0';
  const avgLatency = summaryData?.avg_latency_ms != null
    ? `${Math.round(summaryData.avg_latency_ms)}ms`
    : '-';
  const activeGuardrails = summaryData?.active_guardrails ?? 0;

  const anyLoading = summaryLoading || triggerLoading || latencyLoading || blockedLoading || driftLoading;

  if (anyLoading && !summaryData && !triggerData && !latencyData && !blockedData && !driftData) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-teal-600" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Guardrail Insights</h1>
        <p className="mt-1 text-sm text-gray-500">
          Real-time observability into guardrail enforcement across the mesh.
        </p>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <SummaryCard
          icon={ShieldCheckIcon}
          value={totalEvents.toLocaleString()}
          label="Total Events"
          color="bg-teal-600"
        />
        <SummaryCard
          icon={NoSymbolIcon}
          value={`${blockRate}%`}
          label="Block Rate"
          color="bg-red-500"
        />
        <SummaryCard
          icon={ClockIcon}
          value={avgLatency}
          label="Avg Latency"
          color="bg-amber-500"
        />
        <SummaryCard
          icon={BoltIcon}
          value={activeGuardrails.toLocaleString()}
          label="Active Guardrails"
          color="bg-[#0A0F1C]"
        />
      </div>

      {/* Trigger Rate Time Series */}
      <div className="bg-white rounded-lg border border-gray-200 p-5">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
          <h2 className="text-lg font-semibold text-gray-900">Trigger Rate</h2>
          <div className="flex items-center gap-3">
            <select
              value={interval}
              onChange={(e) => setInterval_(e.target.value)}
              className="px-3 py-1.5 border border-gray-300 rounded-md text-sm focus:border-teal-500 focus:ring-teal-500"
            >
              <option value="1h">Last 1 hour</option>
              <option value="6h">Last 6 hours</option>
              <option value="1d">Last 24 hours</option>
            </select>
            <input
              type="text"
              placeholder="Agent name"
              value={agentName}
              onChange={(e) => setAgentName(e.target.value)}
              className="px-3 py-1.5 border border-gray-300 rounded-md text-sm focus:border-teal-500 focus:ring-teal-500 w-36"
            />
            <input
              type="text"
              placeholder="Guardrail"
              value={guardrailFilter}
              onChange={(e) => setGuardrailFilter(e.target.value)}
              className="px-3 py-1.5 border border-gray-300 rounded-md text-sm focus:border-teal-500 focus:ring-teal-500 w-36"
            />
          </div>
        </div>

        {/* Legend */}
        <div className="flex items-center gap-4 mb-3 text-xs text-gray-500">
          {Object.entries(TRIGGER_COLORS).map(([key, color]) => (
            <div key={key} className="flex items-center gap-1.5">
              <span className="inline-block w-3 h-0.5 rounded" style={{ backgroundColor: color }} />
              <span className="capitalize">{key}</span>
            </div>
          ))}
        </div>

        {triggerData && triggerData.buckets && triggerData.buckets.length > 0 ? (
          <TriggerRateChart data={triggerData} />
        ) : (
          <div className="flex items-center justify-center h-48 text-sm text-gray-400">
            No trigger rate data available for the selected period.
          </div>
        )}
      </div>

      {/* Charts row: Latency + Top Blocked */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Latency Breakdown */}
        <div className="bg-white rounded-lg border border-gray-200 p-5">
          <h2 className="text-lg font-semibold text-gray-900 mb-3">Latency Breakdown</h2>

          {/* Legend */}
          <div className="flex items-center gap-4 mb-3 text-xs text-gray-500">
            {Object.entries(LATENCY_COLORS).map(([key, color]) => (
              <div key={key} className="flex items-center gap-1.5">
                <span className="inline-block w-3 h-3 rounded-sm" style={{ backgroundColor: color }} />
                <span className="uppercase">{key}</span>
              </div>
            ))}
          </div>

          {latencyData && latencyData.mechanisms && latencyData.mechanisms.length > 0 ? (
            <LatencyChart data={latencyData} />
          ) : (
            <div className="flex items-center justify-center h-48 text-sm text-gray-400">
              No latency data available.
            </div>
          )}
        </div>

        {/* Top Blocked Patterns */}
        <div className="bg-white rounded-lg border border-gray-200 p-5">
          <h2 className="text-lg font-semibold text-gray-900 mb-3">Top Blocked Patterns</h2>
          <TopBlockedTable data={blockedData} />
        </div>
      </div>

      {/* Drift Detection */}
      <div className="bg-white rounded-lg border border-gray-200 p-5">
        <h2 className="text-lg font-semibold text-gray-900 mb-3">Drift Detection</h2>
        <DriftTable data={driftData} />
      </div>

      {/* Live Event Feed */}
      <div className="bg-white rounded-lg border border-gray-200 p-5">
        <div className="flex items-center gap-2 mb-4">
          <h2 className="text-lg font-semibold text-gray-900">Live Event Feed</h2>
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-green-500 animate-pulse" />
        </div>
        <LiveEventFeed events={liveEvents} />
      </div>

      {/* Slide-in animation for live events */}
      <style>{`
        @keyframes slideIn {
          from {
            opacity: 0;
            transform: translateY(-8px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
        .animate-slideIn {
          animation: slideIn 0.3s ease-out;
        }
      `}</style>
    </div>
  );
}
