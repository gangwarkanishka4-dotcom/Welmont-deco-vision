import { useState } from 'react';
import { Bookmark, Download, BarChart3 } from 'lucide-react';
import ComingSoon from '../components/ComingSoon';
import { api } from '../services/api.js';
import { useDirectory } from '../hooks/useDirectory.js';
import { downloadCsv, formatDate, formatDuration, formatTime } from '../utils/format.js';

const RANGE_DAYS = { today: 1, '7days': 7, '30days': 30 };
const RANGE_LABEL = { today: 'Today', '7days': 'Last 7 days', '30days': 'Last 30 days' };

export default function Reports() {
  const { classrooms, classroomsById } = useDirectory();
  const [scope, setScope] = useState('site');
  const [classroomId, setClassroomId] = useState('');
  const [range, setRange] = useState('7days');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [generated, setGenerated] = useState([]); // session-only — no backend endpoint stores these

  async function handleGenerate() {
    setBusy(true);
    setError(null);
    try {
      const alerts = await api.listAlerts({ classroom_id: classroomId || undefined, limit: 500 });
      const cutoff = Date.now() - RANGE_DAYS[range] * 24 * 60 * 60 * 1000;
      const rows = alerts.filter((a) => new Date(a.started_at).getTime() >= cutoff);

      if (rows.length === 0) {
        setError('No alerts in this range for the selected scope — nothing to report.');
        return;
      }

      const scopeName = classroomId ? classroomsById.get(classroomId)?.name ?? classroomId : 'All sites';
      const filename = `${scopeName.replace(/[^a-z0-9]+/gi, '-')}-${range}-${Date.now()}.csv`;
      const csvRows = rows.map((a) => [
        formatDate(a.started_at), classroomsById.get(a.classroom_id)?.name ?? a.classroom_id,
        formatTime(a.started_at), a.acknowledged_at ? formatTime(a.acknowledged_at) : '-',
        a.resolved_at ? formatTime(a.resolved_at) : '-', formatDuration(a.started_at, a.resolved_at), a.status,
      ]);
      const headers = ['Date', 'Location', 'Started at', 'Acknowledged at', 'Resolved at', 'Duration', 'Status'];

      downloadCsv(filename, headers, csvRows);
      setGenerated((prev) => [
        { id: filename, name: scopeName, site: classroomsById.get(classroomId)?.location, scope: 'Site-wise', rangeLabel: RANGE_LABEL[range], generatedOn: new Date(), download: () => downloadCsv(filename, headers, csvRows) },
        ...prev,
      ]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="content-header">
        <div className="title-row"><div className="page-title">Reports</div><button className="bookmark-btn"><Bookmark size={15} /></button></div>
      </div>

      <div className="section-label">Scope</div>
      <div className="seg-row">
        <button className={`seg-card${scope === 'site' ? ' active' : ''}`} onClick={() => setScope('site')}>
          <div className="seg-radio" />
          <div><div className="seg-title">Site-wise</div><div className="seg-desc">Alert history for a site and date range</div></div>
        </button>
        <button className="seg-card" disabled title="Deeper per-metric analytics (e.g. facial recognition breakdowns) aren't computed by the backend yet">
          <div className="seg-radio" />
          <div><div className="seg-title">Analytics-wise</div><div className="seg-desc">Not available yet</div></div>
        </button>
      </div>

      {scope === 'analytics' ? (
        <ComingSoon icon={BarChart3} title="Not available yet" reason="Per-metric analytics reports aren't computed by the backend. Site-wise reports work today, built from real alert history." />
      ) : (
        <>
          <div className="toolbar" style={{ marginBottom: 14 }}>
            <select className="field-select-inline" value={classroomId} onChange={(e) => setClassroomId(e.target.value)}>
              <option value="">All sites</option>
              {classrooms.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
            <select className="field-select-inline" value={range} onChange={(e) => setRange(e.target.value)}>
              <option value="today">Today</option>
              <option value="7days">Last 7 days</option>
              <option value="30days">Last 30 days</option>
            </select>
          </div>

          <div className="export-row">
            <span className="export-link"><Download size={14} /> Export as CSV</span>
          </div>

          <button className="gen-btn ready" onClick={handleGenerate} disabled={busy}>{busy ? 'Generating…' : 'Generate report'}</button>
          {error && <p style={{ fontSize: 13, color: 'var(--amber)', marginTop: -18, marginBottom: 20 }}>{error}</p>}

          <div className="reports-generated-label">Reports generated</div>
          <p style={{ fontSize: 12, color: 'var(--text-sub)', marginTop: -6, marginBottom: 10 }}>
            This list tracks what you've generated this browser session — there's no backend storage for report history yet.
          </p>
          <div className="table-wrap">
            {generated.length === 0 ? (
              <p style={{ padding: 24, textAlign: 'center', color: 'var(--text-sub)', fontSize: 13.5 }}>No reports generated yet this session.</p>
            ) : (
              <table>
                <thead><tr><th>Report</th><th>Scope</th><th>Range</th><th>Generated on</th><th></th></tr></thead>
                <tbody>
                  {generated.map((r) => (
                    <tr key={r.id}>
                      <td className="loc">{r.name} {r.site && <span className="pill blue" style={{ marginLeft: 8 }}>{r.site}</span>}</td>
                      <td>{r.scope}</td>
                      <td>{r.rangeLabel}</td>
                      <td>{formatDate(r.generatedOn)}</td>
                      <td><a className="dl" onClick={r.download}>Download</a></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
    </>
  );
}
