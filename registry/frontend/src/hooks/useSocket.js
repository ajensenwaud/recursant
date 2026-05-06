import { useEffect, useRef, useState } from 'react';
import { io } from 'socket.io-client';

/**
 * Custom hook for Socket.IO connection to the mesh namespace.
 * Handles JWT auth via handshake, auto-reconnection, and event routing.
 *
 * @param {string} namespace - Socket.IO namespace (e.g. '/mesh')
 * @param {function} onEvent - Callback: (eventType, data) => void
 * @returns {{ socketRef: React.MutableRefObject, connected: boolean }}
 */
export default function useSocket(namespace, onEvent) {
  const socketRef = useRef(null);
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem('token');
    const socket = io(namespace, {
      auth: { token },
      transports: ['websocket'],
      reconnection: true,
      reconnectionDelay: 1000,
      reconnectionAttempts: Infinity,
    });
    socketRef.current = socket;

    socket.on('connect', () => setConnected(true));
    socket.on('disconnect', () => setConnected(false));

    socket.on('registration', (data) => onEventRef.current('registration', data));
    socket.on('audit', (data) => onEventRef.current('audit', data));
    socket.on('guardrail-event', (data) => onEventRef.current('guardrail-event', data));

    socket.on('connect_error', (err) => {
      setConnected(false);
      console.error('Mesh WebSocket connection error:', err.message);
    });

    return () => {
      socket.disconnect();
      socketRef.current = null;
      setConnected(false);
    };
  }, [namespace]);

  return { socketRef, connected };
}
