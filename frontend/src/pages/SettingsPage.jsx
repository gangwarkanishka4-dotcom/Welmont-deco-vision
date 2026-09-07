import { useAlertSoundSetting, playAlertBeep } from '../hooks/useAlertSound.js';
import { API_BASE_URL } from '../services/api.js';

export function SettingsPage() {
  const [soundEnabled, setSoundEnabled] = useAlertSoundSetting();
  const wsBaseUrl = API_BASE_URL.replace(/^http/, 'ws');

  return (
    <div className="max-w-2xl space-y-6">
      <div className="panel p-5">
        <p className="mb-1 text-sm font-semibold text-slate-100">Alert Notifications</p>
        <p className="mb-4 text-sm text-slate-500">Controls the in-app toast for HIGH severity alerts.</p>

        <label className="flex items-center justify-between">
          <span className="text-sm text-slate-300">Play sound on new HIGH severity alert</span>
          <input
            type="checkbox"
            checked={soundEnabled}
            onChange={(e) => setSoundEnabled(e.target.checked)}
            className="h-4 w-4"
          />
        </label>
        {soundEnabled && (
          <button className="btn-ghost mt-3 text-xs" onClick={playAlertBeep}>
            ▶ Test sound
          </button>
        )}
      </div>

      <div className="panel p-5">
        <p className="mb-1 text-sm font-semibold text-slate-100">Connection</p>
        <p className="mb-4 text-sm text-slate-500">Read from the build-time VITE_API_BASE environment variable.</p>
        <dl className="space-y-2 text-sm">
          <div className="flex justify-between">
            <dt className="text-slate-500">API Base URL</dt>
            <dd className="font-mono text-slate-300">{API_BASE_URL}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-slate-500">WebSocket URL</dt>
            <dd className="font-mono text-slate-300">{wsBaseUrl}/ws/events</dd>
          </div>
        </dl>
      </div>

      {/* No backend endpoints exist yet for retention policy or notification channels (email/SMS) —
          shown as a disabled shell rather than fabricated, editable settings. */}
      <div className="rounded-lg border border-dashed border-surface-600 p-5 text-center">
        <p className="text-sm font-medium text-slate-300">More settings coming soon</p>
        <p className="mt-1 text-sm text-slate-500">
          Recording retention policy and email/SMS notification channels will appear here once the backend supports
          them.
        </p>
      </div>
    </div>
  );
}
