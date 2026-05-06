import { HEALTH_COLORS } from '../hooks/useMeshGraph';

export default function TopologyLegend({ showZones, zoneLegend }) {
  return (
    <div className="absolute bottom-4 right-4 bg-white/95 border border-gray-200 rounded-lg shadow-sm px-3 py-2.5 text-xs z-10 w-52">
      {/* Node health */}
      <div className="font-semibold text-gray-600 mb-1.5">Node Health</div>
      <div className="space-y-1 mb-2">
        {[
          { color: HEALTH_COLORS.healthy, label: 'Healthy (error < 1%)' },
          { color: HEALTH_COLORS.degraded, label: 'Degraded (1-5%)' },
          { color: HEALTH_COLORS.failing, label: 'Failing (> 5%)' },
          { color: HEALTH_COLORS.idle, label: 'Idle / no traffic' },
        ].map(({ color, label }) => (
          <div key={label} className="flex items-center gap-2">
            <span className="inline-block w-3 h-3 rounded-full flex-shrink-0" style={{ backgroundColor: color }} />
            <span className="text-gray-700">{label}</span>
          </div>
        ))}
      </div>

      {/* Node shapes */}
      <div className="font-semibold text-gray-600 mb-1.5 border-t border-gray-200 pt-2">Node Shapes</div>
      <div className="space-y-1 mb-2">
        <div className="flex items-center gap-2">
          <span className="inline-block w-3 h-3 rounded-full border border-gray-400 flex-shrink-0" />
          <span className="text-gray-700">A2A Agent</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="inline-block w-3 h-3 rounded-sm border border-gray-400 flex-shrink-0" style={{ backgroundColor: '#F59E0B' }} />
          <span className="text-gray-700">Tool</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="inline-block w-3 h-3 rotate-45 border border-gray-400 flex-shrink-0" style={{ backgroundColor: '#8B5CF6' }} />
          <span className="text-gray-700">MCP Server</span>
        </div>
      </div>

      {/* Badges */}
      <div className="font-semibold text-gray-600 mb-1.5 border-t border-gray-200 pt-2">Badges</div>
      <div className="space-y-1 mb-2">
        <div className="flex items-center gap-2">
          <svg className="w-3.5 h-3.5 text-teal-500 flex-shrink-0" viewBox="0 0 16 16" fill="currentColor">
            <path d="M8 1L10.5 6H14L11 9.5L12.5 14L8 11L3.5 14L5 9.5L2 6H5.5L8 1Z" />
          </svg>
          <span className="text-gray-700">Has guardrails</span>
        </div>
        <div className="flex items-center gap-2">
          <svg className="w-3.5 h-3.5 text-green-500 flex-shrink-0" viewBox="0 0 16 16" fill="currentColor">
            <path d="M8 1C5.2 1 3 3.2 3 6v3l-1 2v1h12v-1l-1-2V6c0-2.8-2.2-5-5-5zm-2 13c0 1.1.9 2 2 2s2-.9 2-2H6z" />
          </svg>
          <span className="text-gray-700">mTLS healthy</span>
        </div>
        <div className="flex items-center gap-2">
          <svg className="w-3.5 h-3.5 text-amber-500 flex-shrink-0" viewBox="0 0 16 16" fill="currentColor">
            <path d="M8 1L1 15h14L8 1zm0 5l1 5H7l1-5zm0 7a1 1 0 110 2 1 1 0 010-2z" />
          </svg>
          <span className="text-gray-700">Active alert</span>
        </div>
      </div>

      {/* Edge styles */}
      <div className="font-semibold text-gray-600 mb-1.5 border-t border-gray-200 pt-2">Edge Styles</div>
      <div className="space-y-1">
        <div className="flex items-center gap-2">
          <div className="w-6 h-0 border-t-2 border-green-500 flex-shrink-0" />
          <span className="text-gray-700">Healthy traffic</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-6 h-0 border-t-2 border-red-500 flex-shrink-0" />
          <span className="text-gray-700">High errors</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-6 h-0 border-t-2 border-dashed border-red-400 flex-shrink-0" />
          <span className="text-gray-700">Policy deny</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-6 h-0 border-t border-gray-400 flex-shrink-0" />
          <span className="text-gray-700">Idle / low traffic</span>
        </div>
      </div>

      {/* Zone legend */}
      {showZones && zoneLegend && zoneLegend.length > 0 && (
        <>
          <div className="font-semibold text-gray-600 mt-2 mb-1.5 border-t border-gray-200 pt-2">Sovereignty Zones</div>
          <div className="space-y-1">
            {zoneLegend.map(({ zone, colour }) => (
              <div key={zone} className="flex items-center gap-2">
                <span className="inline-block w-4 h-0.5 flex-shrink-0" style={{ backgroundColor: colour }} />
                <span className="text-gray-700">{zone}</span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
