import { useEffect, useState } from 'react';
import { api } from '../services/api.js';

/** Polls GET /api/health for a topbar connectivity indicator; the event socket has its own status. */
export function useApiHealth(intervalMs = 15_000) {
  const [health, setHealth] = useState('checking');

  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      try {
        await api.health();
        if (!cancelled) setHealth('ok');
      } catch {
        if (!cancelled) setHealth('down');
      }
    };
    check();
    const id = setInterval(check, intervalMs);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [intervalMs]);

  return health;
}
