import { useEffect, useRef, useState } from 'react';
import { EventSocketClient } from './socket.js';
import { EventSocketContext } from './EventSocketContext.js';

export function EventSocketProvider({ children }) {
  // useRef so the socket survives re-renders and is created exactly once for the app's lifetime.
  const clientRef = useRef(null);
  if (!clientRef.current) clientRef.current = new EventSocketClient();
  const client = clientRef.current;

  const [status, setStatus] = useState(client.getStatus());

  useEffect(() => {
    const unsubscribe = client.onStatusChange(setStatus);
    client.connect();
    return () => {
      unsubscribe();
      client.disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return <EventSocketContext.Provider value={{ client, status }}>{children}</EventSocketContext.Provider>;
}
