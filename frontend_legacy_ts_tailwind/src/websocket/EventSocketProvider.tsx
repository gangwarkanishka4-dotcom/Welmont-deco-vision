import { createContext, useContext, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { EventSocketClient } from './socket';
import type { SocketConnectionStatus } from '../types/events';

interface EventSocketContextValue {
  client: EventSocketClient;
  status: SocketConnectionStatus;
}

const EventSocketContext = createContext<EventSocketContextValue | null>(null);

export function EventSocketProvider({ children }: { children: ReactNode }) {
  // useRef so the socket survives re-renders and is created exactly once for the app's lifetime.
  const clientRef = useRef<EventSocketClient>();
  if (!clientRef.current) clientRef.current = new EventSocketClient();
  const client = clientRef.current;

  const [status, setStatus] = useState<SocketConnectionStatus>(client.getStatus());

  useEffect(() => {
    const unsubscribe = client.onStatusChange(setStatus);
    client.connect();
    return () => {
      unsubscribe();
      client.disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <EventSocketContext.Provider value={{ client, status }}>{children}</EventSocketContext.Provider>
  );
}

export function useEventSocketContext(): EventSocketContextValue {
  const ctx = useContext(EventSocketContext);
  if (!ctx) throw new Error('useEventSocketContext must be used within EventSocketProvider');
  return ctx;
}
