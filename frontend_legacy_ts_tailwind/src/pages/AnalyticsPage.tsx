import { useEffect, useMemo, useState } from 'react';
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { api } from '../services/api';
import { EmptyState } from '../components/EmptyState';
import { formatDuration } from '../utils/format';
import type { Alert, AlertSeverity } from '../types';

// recharts: small, composable, no-frills SVG charting — enough for a handful of bar charts
// without pulling in a heavier dashboarding library.

const SEVERITY_COLORS: Record<AlertSeverity, string> = { LOW: '#64748b', MEDIUM: '#f59e0b', HIGH: '#ef4444' };

function averageResolutionSeconds(alerts: Alert[]): number | null {
  const resolved = alerts.filter((a) => a.resolved_at);
  if (resolved.length === 0) return null;
  const total = resolved.reduce((sum, a) => sum + (new Date(a.resolved_at!).getTime() - new Date(a.started_at).getTime()), 0);
  return total / resolved.length / 1000;
}

export function AnalyticsPage() {
  const [alerts, setAlerts] = useState<Alert[] | null>(null);

  useEffect(() => {
    api.listAlerts({ limit: 500 }).then(setAlerts);
  }, []);

  const severityData = useMemo(() => {
    if (!alerts) return [];
    const counts: Record<AlertSeverity, number> = { LOW: 0, MEDIUM: 0, HIGH: 0 };
    alerts.forEach((a) => (counts[a.severity] = (counts[a.severity] ?? 0) + 1));
    return (Object.keys(counts) as AlertSeverity[]).map((severity) => ({ severity, count: counts[severity] }));
  }, [alerts]);

  const dailyData = useMemo(() => {
    if (!alerts) return [];
    const days: { date: string; count: number }[] = [];
    for (let i = 13; i >= 0; i--) {
      const d = new Date();
      d.setDate(d.getDate() - i);
      const key = d.toISOString().slice(0, 10);
      days.push({ date: key.slice(5), count: 0 });
    }
    const indexByDate = new Map(days.map((d, i) => [d.date, i]));
    alerts.forEach((a) => {
      const key = a.started_at.slice(5, 10);
      const idx = indexByDate.get(key);
      if (idx !== undefined) days[idx].count += 1;
    });
    return days;
  }, [alerts]);

  if (alerts === null) return <p className="text-sm text-slate-500">Loading analytics…</p>;

  if (alerts.length === 0) {
    return <EmptyState title="No alert history yet" description="Analytics populate once alerts have been recorded." />;
  }

  const avgResolution = averageResolutionSeconds(alerts);
  const active = alerts.filter((a) => a.status === 'ACTIVE').length;
  const resolved = alerts.filter((a) => a.status === 'RESOLVED').length;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Tile label="Total Alerts" value={alerts.length} />
        <Tile label="Active" value={active} accent="text-status-unsupervised" />
        <Tile label="Resolved" value={resolved} accent="text-status-supervised" />
        <Tile label="Avg. Resolution" value={avgResolution !== null ? formatDuration(new Date(Date.now() - avgResolution * 1000).toISOString()) : '—'} />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="panel p-4">
          <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-500">Alerts by Severity</p>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={severityData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e2635" />
              <XAxis dataKey="severity" stroke="#64748b" fontSize={12} />
              <YAxis stroke="#64748b" fontSize={12} allowDecimals={false} />
              <Tooltip contentStyle={{ background: '#131822', border: '1px solid #2a3446', fontSize: 12 }} />
              <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                {severityData.map((entry) => (
                  <Cell key={entry.severity} fill={SEVERITY_COLORS[entry.severity]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="panel p-4">
          <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-500">Alerts — Last 14 Days</p>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={dailyData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e2635" />
              <XAxis dataKey="date" stroke="#64748b" fontSize={11} />
              <YAxis stroke="#64748b" fontSize={12} allowDecimals={false} />
              <Tooltip contentStyle={{ background: '#131822', border: '1px solid #2a3446', fontSize: 12 }} />
              <Bar dataKey="count" fill="#2f7fff" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}

function Tile({ label, value, accent }: { label: string; value: string | number; accent?: string }) {
  return (
    <div className="panel p-4">
      <p className={`text-2xl font-bold ${accent ?? 'text-slate-100'}`}>{value}</p>
      <p className="text-xs text-slate-500">{label}</p>
    </div>
  );
}
