import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../services/api.js';
import { DirectoryContext } from './DirectoryContext.js';

/**
 * Fetches the classroom/camera roster once for the whole app (satisfies "fetch on mount only,
 * no polling for live state" — live state itself comes from the websocket). Pages that mutate
 * the roster (create camera, create classroom) call refetch* to resync.
 */
export function DirectoryProvider({ children }) {
  const [classrooms, setClassrooms] = useState([]);
  const [cameras, setCameras] = useState([]);
  const [loading, setLoading] = useState(true);

  const refetchClassrooms = useCallback(async () => {
    setClassrooms(await api.listClassrooms());
  }, []);
  const refetchCameras = useCallback(async () => {
    setCameras(await api.listCameras());
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [c, cam] = await Promise.all([api.listClassrooms(), api.listCameras()]);
        if (!cancelled) {
          setClassrooms(c);
          setCameras(cam);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const classroomsById = useMemo(() => new Map(classrooms.map((c) => [c.id, c])), [classrooms]);
  const camerasById = useMemo(() => new Map(cameras.map((c) => [c.id, c])), [cameras]);

  const value = { classrooms, cameras, classroomsById, camerasById, loading, refetchClassrooms, refetchCameras };

  return <DirectoryContext.Provider value={value}>{children}</DirectoryContext.Provider>;
}
