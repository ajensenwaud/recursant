import { Fragment } from 'react';
import { Listbox, Transition, Switch } from '@headlessui/react';
import {
  ChevronUpDownIcon,
  MagnifyingGlassIcon,
  ArrowPathIcon,
  EyeSlashIcon,
  FilmIcon,
} from '@heroicons/react/20/solid';

const EDGE_LABEL_OPTIONS = [
  { value: 'none', label: 'No labels' },
  { value: 'traffic', label: 'Traffic (req/s)' },
  { value: 'errors', label: 'Error rate (%)' },
  { value: 'latency', label: 'Latency (p95 ms)' },
];

const TIME_RANGE_OPTIONS = [
  { value: 'live', label: 'Live' },
  { value: '1h', label: '1h' },
  { value: '6h', label: '6h' },
  { value: '24h', label: '24h' },
];

export default function TopologyToolbar({
  edgeLabelMode,
  setEdgeLabelMode,
  findQuery,
  setFindQuery,
  zoneFilter,
  setZoneFilter,
  zones,
  showIdleNodes,
  setShowIdleNodes,
  showAnimation,
  setShowAnimation,
  timeRange,
  setTimeRange,
  onRefresh,
  agentCount,
  toolCount,
  edgeCount,
}) {
  const selectedEdgeLabel = EDGE_LABEL_OPTIONS.find(o => o.value === edgeLabelMode) || EDGE_LABEL_OPTIONS[0];
  const selectedTimeRange = TIME_RANGE_OPTIONS.find(o => o.value === timeRange) || TIME_RANGE_OPTIONS[0];

  const zoneOptions = [{ value: '', label: 'All zones' }, ...(zones || []).map(z => ({ value: z, label: z }))];
  const selectedZone = zoneOptions.find(o => o.value === zoneFilter) || zoneOptions[0];

  return (
    <div className="flex items-center gap-3 px-3 py-2 bg-white border-b border-gray-200 text-xs">
      {/* Left section */}
      <span className="font-semibold text-gray-700 mr-1">Topology</span>

      {/* Edge labels dropdown */}
      <Listbox value={edgeLabelMode} onChange={setEdgeLabelMode}>
        <div className="relative">
          <Listbox.Button className="flex items-center gap-1 border border-gray-300 rounded px-2 py-1 bg-white hover:bg-gray-50 text-xs min-w-[120px]">
            <span className="truncate">{selectedEdgeLabel.label}</span>
            <ChevronUpDownIcon className="w-3.5 h-3.5 text-gray-400 ml-auto" />
          </Listbox.Button>
          <Transition as={Fragment} leave="transition ease-in duration-100" leaveFrom="opacity-100" leaveTo="opacity-0">
            <Listbox.Options className="absolute z-50 mt-1 w-40 bg-white border border-gray-200 rounded shadow-lg py-1">
              {EDGE_LABEL_OPTIONS.map(opt => (
                <Listbox.Option key={opt.value} value={opt.value}
                  className={({ active }) => `px-3 py-1.5 cursor-pointer ${active ? 'bg-teal-50 text-teal-700' : 'text-gray-700'}`}>
                  {opt.label}
                </Listbox.Option>
              ))}
            </Listbox.Options>
          </Transition>
        </div>
      </Listbox>

      {/* Find input */}
      <div className="relative">
        <MagnifyingGlassIcon className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" />
        <input
          type="text"
          placeholder="Find node..."
          value={findQuery}
          onChange={e => setFindQuery(e.target.value)}
          className="border border-gray-300 rounded pl-7 pr-2 py-1 text-xs w-36 focus:outline-none focus:ring-1 focus:ring-teal-400 focus:border-teal-400"
        />
      </div>

      <div className="flex-1" />

      {/* Right section */}
      {/* Zone filter */}
      {zones && zones.length > 0 && (
        <Listbox value={zoneFilter} onChange={setZoneFilter}>
          <div className="relative">
            <Listbox.Button className="flex items-center gap-1 border border-gray-300 rounded px-2 py-1 bg-white hover:bg-gray-50 text-xs min-w-[100px]">
              <span className="truncate">{selectedZone.label}</span>
              <ChevronUpDownIcon className="w-3.5 h-3.5 text-gray-400 ml-auto" />
            </Listbox.Button>
            <Transition as={Fragment} leave="transition ease-in duration-100" leaveFrom="opacity-100" leaveTo="opacity-0">
              <Listbox.Options className="absolute z-50 right-0 mt-1 w-40 bg-white border border-gray-200 rounded shadow-lg py-1">
                {zoneOptions.map(opt => (
                  <Listbox.Option key={opt.value} value={opt.value}
                    className={({ active }) => `px-3 py-1.5 cursor-pointer ${active ? 'bg-teal-50 text-teal-700' : 'text-gray-700'}`}>
                    {opt.label}
                  </Listbox.Option>
                ))}
              </Listbox.Options>
            </Transition>
          </div>
        </Listbox>
      )}

      {/* Idle toggle */}
      <button
        onClick={() => setShowIdleNodes(!showIdleNodes)}
        className={`flex items-center gap-1 border rounded px-2 py-1 transition-colors ${
          showIdleNodes ? 'bg-white border-gray-300 text-gray-600 hover:bg-gray-50' : 'bg-teal-50 border-teal-300 text-teal-700'
        }`}
        title={showIdleNodes ? 'Hide idle nodes' : 'Show idle nodes'}
      >
        <EyeSlashIcon className="w-3.5 h-3.5" />
        <span>Idle</span>
      </button>

      {/* Animation toggle */}
      <button
        onClick={() => setShowAnimation(!showAnimation)}
        className={`flex items-center gap-1 border rounded px-2 py-1 transition-colors ${
          showAnimation ? 'bg-teal-50 border-teal-300 text-teal-700' : 'bg-white border-gray-300 text-gray-600 hover:bg-gray-50'
        }`}
        title={showAnimation ? 'Disable animation' : 'Enable animation'}
      >
        <FilmIcon className="w-3.5 h-3.5" />
      </button>

      {/* Time range */}
      <div className="flex border border-gray-300 rounded overflow-hidden">
        {TIME_RANGE_OPTIONS.map(opt => (
          <button
            key={opt.value}
            onClick={() => setTimeRange(opt.value)}
            className={`px-2 py-1 text-xs ${
              timeRange === opt.value
                ? 'bg-teal-500 text-white'
                : 'bg-white text-gray-600 hover:bg-gray-50'
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {/* Refresh */}
      <button
        onClick={onRefresh}
        className="border border-gray-300 rounded p-1 bg-white hover:bg-gray-50"
        title="Refresh data"
      >
        <ArrowPathIcon className="w-3.5 h-3.5 text-gray-500" />
      </button>

      {/* Stats badges */}
      <div className="flex gap-2 ml-2 border-l border-gray-200 pl-3">
        <span className="text-teal-600 font-semibold">{agentCount}</span>
        <span className="text-gray-400">agents</span>
        <span className="text-amber-600 font-semibold">{toolCount}</span>
        <span className="text-gray-400">tools</span>
        <span className="text-gray-600 font-semibold">{edgeCount}</span>
        <span className="text-gray-400">conn</span>
      </div>
    </div>
  );
}
