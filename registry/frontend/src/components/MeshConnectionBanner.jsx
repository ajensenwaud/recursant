import { useCallback, useEffect, useState } from 'react';
import { ExclamationTriangleIcon, XMarkIcon } from '@heroicons/react/24/outline';
import useSocket from '../hooks/useSocket';

/**
 * Tiny floating banner that warns the user when the mesh observability
 * WebSocket has dropped — common after a registry pod restart, when
 * silent disconnects would otherwise leave the topology view frozen.
 *
 * Stays hidden until the connection has been established at least once
 * (so it doesn't flash on every cold page load).
 */
export default function MeshConnectionBanner() {
  const noop = useCallback(() => {}, []);
  const { connected } = useSocket('/mesh', noop);

  const [hasEverConnected, setHasEverConnected] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    if (connected) {
      setHasEverConnected(true);
      setDismissed(false);
    }
  }, [connected]);

  if (!hasEverConnected || connected || dismissed) return null;

  return (
    <div className="fixed bottom-4 right-4 z-50 max-w-sm bg-amber-100 border border-amber-700 rounded-md shadow-lg p-3 flex items-start gap-2">
      <ExclamationTriangleIcon className="h-5 w-5 text-amber-700 flex-shrink-0 mt-0.5" />
      <div className="flex-1 text-sm text-amber-700">
        <div className="font-semibold">Mesh stream disconnected</div>
        <div className="text-xs mt-0.5">
          Live topology updates have stopped. Reconnecting automatically — if it doesn't
          come back in a few seconds, refresh the page.
        </div>
      </div>
      <button
        onClick={() => setDismissed(true)}
        className="text-amber-700 hover:text-amber-700 flex-shrink-0"
        aria-label="Dismiss"
      >
        <XMarkIcon className="h-4 w-4" />
      </button>
    </div>
  );
}
