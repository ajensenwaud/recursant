import { useEffect, useRef, useState } from 'react';
import { XMarkIcon } from '@heroicons/react/24/outline';
import StatusBadge from './StatusBadge';
import { securityScans, evaluations } from '../api/client';

/**
 * Agent detail popup — appears when clicking a node in the mesh graph.
 *
 * Props:
 * - agent: node data object (or null to hide)
 * - position: { x, y } screen coordinates for positioning
 * - onClose: () => void
 */
export default function AgentDetailPopup({ agent, position, onClose }) {
  const ref = useRef(null);
  const [pipelineData, setPipelineData] = useState(null);
  const [pipelineLoading, setPipelineLoading] = useState(false);

  // Close on click outside
  useEffect(() => {
    if (!agent) return;
    const handler = (e) => {
      if (ref.current && !ref.current.contains(e.target)) {
        onClose();
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [agent, onClose]);

  // Lazy-load latest security scan and evaluation when popup opens
  useEffect(() => {
    if (!agent?.id) {
      setPipelineData(null);
      return;
    }
    let cancelled = false;
    setPipelineLoading(true);

    Promise.allSettled([
      securityScans.list(agent.id, { page: 1, per_page: 1 }),
      evaluations.list(agent.id, { page: 1, per_page: 1 }),
    ]).then((results) => {
      if (cancelled) return;
      const [scanResult, evalResult] = results;
      setPipelineData({
        scan: scanResult.status === 'fulfilled' ? scanResult.value?.scans?.[0] : null,
        evaluation: evalResult.status === 'fulfilled' ? evalResult.value?.evaluations?.[0] : null,
      });
      setPipelineLoading(false);
    });

    return () => { cancelled = true; };
  }, [agent?.id]);

  if (!agent) return null;

  const card = agent.agentCard || {};
  const capabilities = card.skills || card.capabilities || [];
  const endpointType = agent.endpointType || card.endpoint?.type || 'unknown';
  const endpointUrl = card.endpoint?.url || agent.sidecarUrl || '-';

  // Clamp position to viewport
  const popupWidth = 320;
  const popupHeight = 520;
  const left = Math.min(
    Math.max(position?.x ?? 0, 10),
    window.innerWidth - popupWidth - 10
  );
  const top = Math.min(
    Math.max((position?.y ?? 0) + 20, 10),
    window.innerHeight - popupHeight - 10
  );

  const scan = pipelineData?.scan;
  const evaluation = pipelineData?.evaluation;

  return (
    <div
      ref={ref}
      className="fixed bg-white rounded-lg shadow-xl border border-gray-200 z-50 p-4"
      style={{ left, top, width: popupWidth, maxHeight: popupHeight, overflow: 'auto' }}
    >
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-base font-semibold text-gray-900 truncate pr-2">
          {agent.name}
        </h3>
        <button
          onClick={onClose}
          className="text-gray-400 hover:text-gray-600 flex-shrink-0"
        >
          <XMarkIcon className="h-5 w-5" />
        </button>
      </div>

      <div className="space-y-2 text-sm">
        <div className="flex justify-between">
          <span className="text-gray-500">Status</span>
          <StatusBadge status={agent.status || 'unknown'} />
        </div>

        <div className="flex justify-between">
          <span className="text-gray-500">Platform</span>
          <span className="text-gray-900 font-medium">{endpointType}</span>
        </div>

        {agent.classification && (
          <div className="flex justify-between">
            <span className="text-gray-500">Classification</span>
            <StatusBadge status={agent.classification} />
          </div>
        )}

        {agent.riskTier && (
          <div className="flex justify-between">
            <span className="text-gray-500">Risk Tier</span>
            <StatusBadge status={agent.riskTier} />
          </div>
        )}

        {agent.dataSensitivity && agent.dataSensitivity !== 'none' && (
          <div className="flex justify-between">
            <span className="text-gray-500">Data Sensitivity</span>
            <span className="text-gray-900 text-xs font-medium uppercase">{agent.dataSensitivity}</span>
          </div>
        )}

        <div>
          <span className="text-gray-500">Endpoint</span>
          <p className="text-gray-700 text-xs mt-0.5 break-all">{endpointUrl}</p>
        </div>

        <div>
          <span className="text-gray-500">Sidecar URL</span>
          <p className="text-gray-700 text-xs mt-0.5 break-all">{agent.sidecarUrl || '-'}</p>
        </div>

        {agent.sovereigntyZone && (
          <div className="flex justify-between">
            <span className="text-gray-500">Sovereignty Zone</span>
            <span className="text-gray-900">{agent.sovereigntyZone}</span>
          </div>
        )}

        <div className="flex justify-between">
          <span className="text-gray-500">Host</span>
          <span className="text-gray-900 font-mono text-xs">{agent.host || '-'}</span>
        </div>

        {capabilities.length > 0 && (
          <div>
            <span className="text-gray-500">Capabilities</span>
            <div className="flex flex-wrap gap-1 mt-1">
              {capabilities.map((cap, i) => (
                <span
                  key={i}
                  className="inline-block px-2 py-0.5 text-xs bg-teal-50 text-teal-700 rounded"
                >
                  {cap.name || cap.id || cap}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Security scan section */}
        <div className="border-t border-gray-100 pt-2">
          <div className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5">
            Security Scan
          </div>
          {pipelineLoading ? (
            <div className="flex items-center gap-2 text-xs text-gray-400">
              <div className="w-3 h-3 border-2 border-teal-400 border-t-transparent rounded-full animate-spin" />
              Loading...
            </div>
          ) : scan ? (
            <div className="space-y-1">
              <div className="flex justify-between">
                <span className="text-gray-500">Status</span>
                <StatusBadge status={scan.all_blocking_passed ? 'passed' : 'failed'} />
              </div>
              {scan.test_results && (
                <div className="flex justify-between">
                  <span className="text-gray-500">Tests</span>
                  <span className="text-gray-700 text-xs">{scan.test_results.length} tests</span>
                </div>
              )}
              {scan.completed_at && (
                <div className="flex justify-between">
                  <span className="text-gray-500">Completed</span>
                  <span className="text-gray-700 text-xs">
                    {new Date(scan.completed_at).toLocaleDateString()}
                  </span>
                </div>
              )}
            </div>
          ) : (
            <span className="text-xs text-gray-400">No scans</span>
          )}
        </div>

        {/* Evaluation section */}
        <div className="border-t border-gray-100 pt-2">
          <div className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5">
            Evaluation
          </div>
          {pipelineLoading ? (
            <div className="flex items-center gap-2 text-xs text-gray-400">
              <div className="w-3 h-3 border-2 border-teal-400 border-t-transparent rounded-full animate-spin" />
              Loading...
            </div>
          ) : evaluation ? (
            <div className="space-y-1">
              <div className="flex justify-between">
                <span className="text-gray-500">Status</span>
                <StatusBadge status={evaluation.status || 'unknown'} />
              </div>
              {evaluation.suite_name && (
                <div className="flex justify-between">
                  <span className="text-gray-500">Suite</span>
                  <span className="text-gray-700 text-xs truncate max-w-[160px]">{evaluation.suite_name}</span>
                </div>
              )}
              {evaluation.weighted_score != null && (
                <div className="flex justify-between">
                  <span className="text-gray-500">Score</span>
                  <span className="text-gray-900 font-medium text-xs">
                    {Math.round(evaluation.weighted_score * 100)}%
                  </span>
                </div>
              )}
              {evaluation.test_results && (
                <div className="flex justify-between">
                  <span className="text-gray-500">Tests</span>
                  <span className="text-gray-700 text-xs">{evaluation.test_results.length} tests</span>
                </div>
              )}
              {evaluation.completed_at && (
                <div className="flex justify-between">
                  <span className="text-gray-500">Completed</span>
                  <span className="text-gray-700 text-xs">
                    {new Date(evaluation.completed_at).toLocaleDateString()}
                  </span>
                </div>
              )}
            </div>
          ) : (
            <span className="text-xs text-gray-400">No evaluations</span>
          )}
        </div>

        {agent.registeredAt && (
          <div className="flex justify-between">
            <span className="text-gray-500">Registered</span>
            <span className="text-gray-700 text-xs">
              {new Date(agent.registeredAt).toLocaleString()}
            </span>
          </div>
        )}

        {agent.lastHeartbeat && (
          <div className="flex justify-between">
            <span className="text-gray-500">Last Heartbeat</span>
            <span className="text-gray-700 text-xs">
              {new Date(agent.lastHeartbeat).toLocaleString()}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
