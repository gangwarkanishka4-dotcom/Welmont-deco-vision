import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ChevronLeft, Clock, Download } from 'lucide-react';
import SidePanel from '../components/SidePanel';
import StatusPill from '../components/StatusPill';
import { api } from '../services/api.js';
import { useDirectory } from '../hooks/useDirectory.js';
import { downloadCsv, formatDate, formatDuration, formatTime } from '../utils/format.js';

function IncidentDetailPanel({ alert, classroomName, onClose }) {
  const [tab, setTab] = useState('details');
  const [events, setEvents] = useState([]);

  useEffect(() => {
    if (!alert) return;
    api.getAlertEvents(alert.alert_id).then(setEvents).catch(() => setEvents([]));
  }, [alert]);

  if (!alert) return null;

  return (
    <SidePanel
      open
      onClose={onClose}
      title={classroomName}
      subtitle={
        <div className="subtab-row" style={{ marginTop: 12, marginBottom: 0, borderBottom: 'none', gap: 20 }}>
          <button className={`subtab${tab === 'details' ? ' active' : ''}`} onClick={() => setTab('details')} style={{ padding: '4px 0 8px 0' }}>Details</button>
          <button className={`subtab${tab === 'clips' ? ' active' : ''}`} onClick={() => setTab('clips')} style={{ padding: '4px 0 8px 0' }}>Show clips</button>
        </div>
      }
    >
      {tab === 'details' ? (
        <>
          <ul className="sp-list">
            <li><span className="k">Children detected</span><span className="v">{alert.children_count}</span></li>
            <li><span className="k">Adults detected</span><span className="v">{alert.adult_count}</span></li>
          </ul>
          <ul className="sp-list">
            <li><span className="k">Started</span><span className="v">{formatDate(alert.started_at)}, {formatTime(alert.started_at)}</span></li>
            <li><span className="k">Resolved</span><span className="v">{alert.resolved_at ? `${formatDate(alert.resolved_at)}, ${formatTime(alert.resolved_at)}` : '—'}</span></li>
            <li><span className="k">Duration unattended</span><span className="v">{formatDuration(alert.started_at, alert.resolved_at)}</span></li>
            <li><span className="k">Status</span><StatusPill status="Closed" variant="alert" /></li>
          </ul>
          <div style={{ marginTop: 14 }}>
            <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 8 }}>Timeline</div>
            {events.length === 0 ? (
              <p style={{ fontSize: 12.5, color: 'var(--text-sub)' }}>No events recorded.</p>
            ) : (
              <ul style={{ borderLeft: '1px solid var(--border)', paddingLeft: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
                {events.map((e) => (
                  <li key={e.id} style={{ fontSize: 12.5 }}>
                    <p>{e.event_type}{e.message ? ` — ${e.message}` : ''}</p>
                    <p style={{ color: 'var(--text-sub)' }}>{formatDate(e.created_at)}, {formatTime(e.created_at)}</p>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      ) : alert.clip_url ? (
        <>
          <div className="cam-thumb" style={{ aspectRatio: '16/10' }}>
            <video src={api.clipUrl(alert)} controls />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div style={{ fontWeight: 700, fontSize: 13.5 }}>{formatDate(alert.started_at)}, {formatTime(alert.started_at)}</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 4, color: 'var(--text-sub)', fontSize: 12.5 }}>
              <Clock size={13} />{formatDuration(alert.started_at, alert.resolved_at)}
            </div>
          </div>
        </>
      ) : (
        <p style={{ color: 'var(--text-sub)', fontSize: 13.5 }}>No clip was recorded for this incident.</p>
      )}
    </SidePanel>
  );
}

export default function Incidents() {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);
  const navigate = useNavigate();
  const { classroomsById } = useDirectory();

  useEffect(() => {
    api.listAlerts({ status: 'RESOLVED', limit: 200 }).then(setAlerts).finally(() => setLoading(false));
  }, []);

  function exportCsv() {
    downloadCsv(
      'incidents.csv',
      ['Date', 'Location', 'Started at', 'Resolved at', 'Duration', 'Status'],
      alerts.map((a) => [
        formatDate(a.started_at), classroomsById.get(a.classroom_id)?.name ?? a.classroom_id,
        formatTime(a.started_at), a.resolved_at ? formatTime(a.resolved_at) : '-',
        formatDuration(a.started_at, a.resolved_at), 'Closed',
      ]),
    );
  }

  return (
    <>
      <div className="content-header">
        <div className="title-row">
          <button className="back-link" onClick={() => navigate('/alerts')} style={{ margin: 0 }}><ChevronLeft size={14} />Alerts / Incidents</button>
        </div>
        <button className="check-incidents-btn on" onClick={() => navigate('/alerts')}>Back to Alerts</button>
      </div>

      <div className="toolbar">
        <button className="tab-pill active">All</button>
        <div className="pager" style={{ marginLeft: 0 }}>
          <button disabled><ChevronLeft /></button><span className="cur">1</span>
        </div>
        <button className="dropdown-btn" onClick={exportCsv} disabled={alerts.length === 0} style={{ marginLeft: 'auto' }}>
          <Download size={13} /> Export CSV
        </button>
      </div>

      <div className="table-wrap">
        {loading ? (
          <p style={{ padding: 32, textAlign: 'center', color: 'var(--text-sub)', fontSize: 13.5 }}>Loading…</p>
        ) : alerts.length === 0 ? (
          <p style={{ padding: 32, textAlign: 'center', color: 'var(--text-sub)', fontSize: 13.5 }}>No resolved incidents yet.</p>
        ) : (
          <table>
            <thead><tr><th>Date</th><th>Location</th><th>Started at</th><th>Resolved at</th><th>Duration</th><th>Status</th></tr></thead>
            <tbody>
              {alerts.map((a) => (
                <tr key={a.alert_id} className="clickable" onClick={() => setSelected(a)}>
                  <td>{formatDate(a.started_at)}</td>
                  <td className="loc">{classroomsById.get(a.classroom_id)?.name ?? a.classroom_id}</td>
                  <td>{formatTime(a.started_at)}</td>
                  <td>{a.resolved_at ? formatTime(a.resolved_at) : '-'}</td>
                  <td>{formatDuration(a.started_at, a.resolved_at)}</td>
                  <td><StatusPill status="Closed" variant="alert" /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <IncidentDetailPanel
        alert={selected}
        classroomName={selected ? (classroomsById.get(selected.classroom_id)?.name ?? selected.classroom_id) : ''}
        onClose={() => setSelected(null)}
      />
    </>
  );
}
