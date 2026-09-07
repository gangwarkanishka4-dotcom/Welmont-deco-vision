import { useContext, useEffect, useRef } from 'react';
import { EventSocketContext } from '../websocket/EventSocketContext.js';

function useEventSocketContext() {
  const ctx = useContext(EventSocketContext);
  if (!ctx) throw new Error('useEventSocketContext must be used within EventSocketProvider');
  return ctx;
}

/**
 * Subscribe a component to one or more event types on the shared socket.
 * Handler identity doesn't need to be stable — we always call the latest one via a ref,
 * so callers can pass an inline closure without triggering resubscribe churn on every render
 * (important for TRACKED_STATE_UPDATE, which can arrive many times a second).
 */
export function useEventSocket(types, handler) {
  const { client } = useEventSocketContext();
  const handlerRef = useRef(handler);
  handlerRef.current = handler;

  useEffect(() => {
    const unsubs = types.map((type) => client.subscribe(type, (evt) => handlerRef.current(evt)));
    return () => unsubs.forEach((unsub) => unsub());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [client, JSON.stringify(types)]);
}

export function useSocketStatus() {
  return useEventSocketContext().status;
}
