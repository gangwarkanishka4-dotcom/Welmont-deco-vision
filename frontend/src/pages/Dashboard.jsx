import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  MapPin, Video, AlertTriangle, Users, X, ChevronRight, ChevronDown,
  CheckCircle2, Circle, Bell, MoreVertical, Download,
} from 'lucide-react';
import KpiCard from '../components/KpiCard';
import { api } from '../services/api.js';
import { useDirectory } from '../hooks/useDirectory.js';
import { useEventSocket } from '../hooks/useEventSocket.js';
import { useLiveStatus } from '../hooks/useLiveStatus.js';
import { alertStatusLabel, downloadCsv, formatDate, formatTime, isToday, isYesterday } from '../utils/format.js';

function SiteFilter({ value, onChange, classrooms }) {
  return (
    <select className="dropdown-select" value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">All sites</option>
      {classrooms.map((c) => (
        <option key={c.id} value={c.id}>{c.name}</option>
      ))}
    </select>
  );
}

// Deterministic color per classroom name — the same site always gets the
// same tag color, so once a second real site exists these read as visually
// distinct (matches the reference's differently-colored Jaipur/Lalkotha tags).
const TAG_COLORS = ['tag-a', 'tag-b'];
function tagClassFor(name) {
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = (hash * 31 + name.charCodeAt(i)) >>> 0;
  return hash % 2 === 0 ? 'jaipur' : 'lalkotha';
}

function KebabMenu({ onExport }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return;
    const onDocClick = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, [open]);

  return (
    <div style={{ position: 'relative' }} ref={ref}>
      <button className="kebab" onClick={() => setOpen((v) => !v)}><MoreVertical /></button>
      {open && (
        <div className="filter-popover open" style={{ left: 'auto', right: 0, width: 180, display: 'block' }}>
          <button
            onClick={() => { onExport(); setOpen(false); }}
            className="fc-item"
            style={{ display: 'flex', alignItems: 'center', gap: 8 }}
          >
            <Download size={14} /> Export as CSV
          </button>
        </div>
      )}
    </div>
  );
}

export default function Dashboard() {
  const [bannerOpen, setBannerOpen] = useState(true);
  const [alerts, setAlerts] = useState([]);
  const [siteFilter, setSiteFilter] = useState('');
  const navigate = useNavigate();
  const { classrooms, cameras } = useDirectory();
  const { entries } = useLiveStatus();

  useEffect(() => {
    api.listAlerts({ limit: 200 }).then(setAlerts);
  }, []);
  useEventSocket(['ALERT_CREATED', 'ALERT_RESOLVED'], (evt) => {
    const alert = evt.payload;
    setAlerts((prev) => {
      const exists = prev.some((a) => a.alert_id === alert.alert_id);
      return exists ? prev.map((a) => (a.alert_id === alert.alert_id ? alert : a)) : [alert, ...prev];
    });
  });

  const entryList = Array.from(entries.values());
  const onlineCameras = entryList.filter((e) => e.camera_status === 'ONLINE').length;
  const incidentsToday = alerts.filter((a) => isToday(a.started_at)).length;
  // A real day-over-day comparison — the 2-day retention window means
  // yesterday's alerts are still in the database, so this is two real counts
  // compared, not fabricated. Fewer incidents than yesterday is the good
  // direction (green); more is the bad one (red).
  const incidentsYesterday = alerts.filter((a) => isYesterday(a.started_at)).length;
  const incidentsDelta = incidentsToday - incidentsYesterday;
  const childrenPresent = entryList.reduce((sum, e) => sum + (e.child_count ?? 0), 0);

  const unsupervised = entryList.find((e) => e.supervision_status === 'UNSUPERVISED');
  const unsupervisedAlert = unsupervised
    ? alerts.find((a) => a.alert_id === unsupervised.active_alert_id)
    : null;

  const alertsForFilter = siteFilter ? alerts.filter((a) => a.classroom_id === siteFilter) : alerts;
  const recentAlerts = alertsForFilter.slice(0, 5);
  const classroomsById = new Map(classrooms.map((c) => [c.id, c]));
  const filteredClassrooms = siteFilter ? classrooms.filter((c) => c.id === siteFilter) : classrooms;

  const siteRows = filteredClassrooms.map((c) => {
    const camsHere = cameras.filter((cam) => cam.classroom_id === c.id);
    const onlineHere = camsHere.filter((cam) => entries.get(cam.id)?.camera_status === 'ONLINE').length;
    const activeAlertsHere = alerts.filter((a) => a.classroom_id === c.id && a.status !== 'RESOLVED').length;
    return {
      id: c.id,
      name: c.name,
      cameras: camsHere.length,
      ratio: `${onlineHere}/${camsHere.length}`,
      ok: onlineHere === camsHere.length,
      alerts: activeAlertsHere,
    };
  });

  return (
    <>
      <div className="content-header">
        <div className="welcome">Welcome, Jay</div>
        <SiteFilter value={siteFilter} onChange={setSiteFilter} classrooms={classrooms} />
      </div>

      {bannerOpen && unsupervised && (
        <div className="buzzer-banner">
          <div className="buzzer-icon"><Bell /></div>
          <div className="buzzer-text">{unsupervised.classroom_name} is unsupervised</div>
          {unsupervisedAlert && <span className="buzzer-time">at {formatTime(unsupervisedAlert.started_at)}</span>}
          <button className="buzzer-view" onClick={() => navigate('/live-feed')}>View</button>
          <button className="buzzer-close" onClick={() => setBannerOpen(false)}><X size={14} /></button>
        </div>
      )}

      <div className="kpi-grid kpi-grid-4">
        <KpiCard accent="blue" icon={MapPin} number={classrooms.length} label="Total sites">
          <a className="kpi-view-link" href="#/sites" onClick={(e) => { e.preventDefault(); navigate('/sites'); }}>
            View <ChevronRight size={11} />
          </a>
        </KpiCard>

        <KpiCard
          accent="green"
          icon={Video}
          number={cameras.length}
          label="Cameras"
          cornerBadge={<span className="kpi-pill">{onlineCameras}/{cameras.length}</span>}
        >
          <div className="kpi-split">
            <span className="lbl">Online <span className="on">{onlineCameras}</span></span>
            <span className="lbl">Offline <span className="off">{cameras.length - onlineCameras}</span></span>
          </div>
        </KpiCard>

        <KpiCard accent="orange" icon={AlertTriangle} number={incidentsToday} label="Incidents Today">
          {(incidentsToday > 0 || incidentsYesterday > 0) && (
            <div className={`kpi-trend ${incidentsDelta > 0 ? 'down-bad' : 'down-good'}`}>
              <ChevronDown size={12} style={{ transform: incidentsDelta > 0 ? 'none' : 'rotate(180deg)' }} />
              {Math.abs(incidentsDelta)} <span className="muted">vs yesterday</span>
            </div>
          )}
        </KpiCard>

        <KpiCard accent="purple" icon={Users} number={childrenPresent} label="Attendance">
          <div className="kpi-foot">children present right now</div>
        </KpiCard>
      </div>

      <div className="panel">
        <div className="panel-head">
          <div className="panel-title">Recent alerts</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <SiteFilter value={siteFilter} onChange={setSiteFilter} classrooms={classrooms} />
            <KebabMenu
              onExport={() =>
                downloadCsv(
                  'recent-alerts.csv',
                  ['Date', 'Location', 'Started at', 'Status'],
                  recentAlerts.map((a) => [
                    formatDate(a.started_at),
                    classroomsById.get(a.classroom_id)?.name ?? a.classroom_id,
                    formatTime(a.started_at),
                    alertStatusLabel(a),
                  ]),
                )
              }
            />
          </div>
        </div>
        {recentAlerts.length === 0 && (
          <p style={{ padding: '24px 22px', textAlign: 'center', color: 'var(--text-sub)', fontSize: 13.5 }}>No alerts yet.</p>
        )}
        {recentAlerts.map((a, i) => {
          const label = alertStatusLabel(a);
          const flagged = label === 'Missed' || label === 'Active';
          const site = classroomsById.get(a.classroom_id);
          return (
            <button key={a.alert_id} className={`alert-row${i > 0 ? ' dim' : ''}`} onClick={() => navigate('/alerts')}>
              <div className="alert-title">{site?.name ?? a.classroom_id} unsupervised</div>
              {site?.location && <span className={`tag ${tagClassFor(site.name)}`}>{site.location}</span>}
              <div className="alert-spacer" />
              {flagged ? (
                <div className="missed-badge">
                  {label}
                  <span className="bell-dot"><Bell size={11} /></span>
                </div>
              ) : null}
              <div className={`alert-time${flagged ? ' red' : ''}`}>Today, {formatTime(a.started_at)}</div>
              <ChevronRight className="chev-row" />
            </button>
          );
        })}
        <button className="panel-footer" onClick={() => navigate('/alerts')}>
          {alertsForFilter.length > recentAlerts.length && (
            <span className="plus-chip">+{alertsForFilter.length - recentAlerts.length}</span>
          )}
          View all alerts
        </button>
      </div>

      <div className="panel">
        <div className="panel-head">
          <div className="panel-title">Sites</div>
          <KebabMenu
            onExport={() =>
              downloadCsv('sites.csv', ['Site', 'Cameras', 'Online ratio', 'Active alerts'], siteRows.map((s) => [s.name, s.cameras, s.ratio, s.alerts]))
            }
          />
        </div>
        {siteRows.map((s) => (
          <button key={s.id} className="site-row" onClick={() => navigate('/sites')}>
            <div>
              <div className="site-name">{s.name}</div>
              <div className="site-meta">
                <span>{s.cameras} Cameras</span>
                <span className={s.ok ? 'ok' : 'warn-num'}>
                  {s.ok ? <CheckCircle2 size={13} style={{ marginRight: 4 }} /> : <Circle size={13} style={{ marginRight: 4 }} />}
                  {s.ratio}
                </span>
                {s.alerts > 0 && <span className="alert-count">⚠ {s.alerts} Alert{s.alerts > 1 ? 's' : ''}</span>}
              </div>
            </div>
            <ChevronRight className="chev-row" />
          </button>
        ))}
        <button className="panel-footer" onClick={() => navigate('/sites')}>View all</button>
      </div>
    </>
  );
}
