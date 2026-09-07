import { useApiHealth } from '../../hooks/useApiHealth';
import { useSocketStatus } from '../../hooks/useEventSocket';

const SOCKET_LABEL: Record<string, string> = {
  connecting: 'Connecting…',
  open: 'Live',
  closed: 'Disconnected',
  reconnecting: 'Reconnecting…',
};

export function Topbar({ title }: { title: string }) {
  const health = useApiHealth();
  const socketStatus = useSocketStatus();

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-surface-700 bg-surface-900 px-6">
      <h1 className="text-sm font-semibold text-slate-100">{title}</h1>
      <div className="flex items-center gap-4 text-xs text-slate-400">
        <div className="flex items-center gap-1.5" title="Realtime event socket">
          <span
            className={`h-1.5 w-1.5 rounded-full ${
              socketStatus === 'open'
                ? 'bg-status-supervised'
                : socketStatus === 'reconnecting' || socketStatus === 'connecting'
                  ? 'bg-status-waiting'
                  : 'bg-status-unsupervised'
            }`}
          />
          {SOCKET_LABEL[socketStatus] ?? socketStatus}
        </div>
        <div className="flex items-center gap-1.5" title="Backend API health">
          <span
            className={`h-1.5 w-1.5 rounded-full ${
              health === 'ok' ? 'bg-status-supervised' : health === 'checking' ? 'bg-status-waiting' : 'bg-status-unsupervised'
            }`}
          />
          API {health === 'ok' ? 'Healthy' : health === 'checking' ? 'Checking…' : 'Unreachable'}
        </div>
      </div>
    </header>
  );
}
