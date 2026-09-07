import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { api } from '../services/api';
import type { Camera, Classroom } from '../types';

interface DirectoryValue {
  classrooms: Classroom[];
  cameras: Camera[];
  classroomsById: Map<string, Classroom>;
  camerasById: Map<string, Camera>;
  loading: boolean;
  refetchClassrooms: () => Promise<void>;
  refetchCameras: () => Promise<void>;
}

const DirectoryContext = createContext<DirectoryValue | null>(null);

/**
 * Fetches the classroom/camera roster once for the whole app (satisfies "fetch on mount only,
 * no polling for live state" — live state itself comes from the websocket). Pages that mutate
 * the roster (create camera, create classroom) call refetch* to resync.
 */
export function DirectoryProvider({ children }: { children: ReactNode }) {
  const [classrooms, setClassrooms] = useState<Classroom[]>([]);
  const [cameras, setCameras] = useState<Camera[]>([]);
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

  return (
    <DirectoryContext.Provider
      value={{ classrooms, cameras, classroomsById, camerasById, loading, refetchClassrooms, refetchCameras }}
    >
      {children}
    </DirectoryContext.Provider>
  );
}

export function useDirectory(): DirectoryValue {
  const ctx = useContext(DirectoryContext);
  if (!ctx) throw new Error('useDirectory must be used within DirectoryProvider');
  return ctx;
}
