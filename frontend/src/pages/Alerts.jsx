import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { X, ChevronLeft, ChevronRight, Search, Bell, Bookmark, Filter as FilterIcon, Clock } from 'lucide-react';
import SidePanel from '../components/SidePanel';
import StatusPill from '../components/StatusPill';
import { PrimaryButton } from '../components/Field';
import { api } from '../services/api.js';
import { useDirectory } from '../hooks/useDirectory.js';
import { useEventSocket } from '../hooks/useEventSocket.js';
import { useLiveStatus } from '../hooks/useLiveStatus.js';
import { alertStatusLabel, downloadCsv, formatDate, formatDuration, formatTime, isToday, isYesterday } from '../utils/format.js';

const PAGE_SIZE = 8;
const STATUS_LABELS = ['Active', 'Unsupervised', 'Missed'];
const DATE_PRESETS = [
  { value: '', label: 'All time' },
  { value: 'today', label: 'Today' },
  { value: 'yesterday', label: 'Yesterday' },
  { value: '7days', label: 'Last 7 days' },
];

function matchesDatePreset(alert, preset) {
  if (!preset) return true;
  if (preset === 'today') return isToday(alert.started_at);
  if (preset === 'yesterday') return isYesterday(alert.started_at);
  if (preset === '7days') return Date.now() - new Date(alert.started_at).getTime() <= 7 * 24 * 60 * 60 * 1000;
  return true;
}

function AlertDetailPanel({ alert, classroomName, onClose, onAcknowledged }) {
  const [tab, setTab] = useState('details');
  const [busy, setBusy] = useState(false);
  if (!alert) return null;

  async function handleAcknowledge() {
    setBusy(true);
    try {
      const updated = await api.acknowledgeAlert(alert.alert_id);
      onAcknowledged(updated);
    } finally {
      setBusy(false);
    }
  }

  const buzzerStatus = alert.acknowledged_at ? 'Silenced' : 'Active';

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
      footer={tab === 'details' && (
        <PrimaryButton style={{ width: '100%' }} onClick={handleAcknowledge} disabled={busy || alert.status !== 'ACTIVE'}>
          {alert.status !== 'ACTIVE' ? 'Acknowledged' : 'Acknowledge'}
        </PrimaryButton>
      )}
    >
      {tab === 'details' ? (
        <>
          <div className="cam-thumb">
            {alert.clip_url ? <video src={api.clipUrl(alert)} muted /> : null}
            <span className="cam-badge">{alert.status}</span>
          </div>
          <ul className="sp-list">
            <li><span className="k">Adult detected</span><span className="v">{alert.adult_count > 0 ? 'Yes' : 'No'}</span></li>
            <li><span className="k">Location</span><span className="v">{classroomName}</span></li>
          </ul>
          <ul className="sp-list">
            <li><span className="k">Duration unattended</span><span className="v" style={{ display: 'flex', alignItems: 'center', gap: 4, justifyContent: 'flex-end' }}><Clock size={12} />{formatDuration(alert.started_at, alert.resolved_at)}</span></li>
            <li><span className="k">Alert started</span><span className="v">{formatTime(alert.started_at)}</span></li>
            {alert.acknowledged_at && <li><span className="k">Acknowledged at</span><span className="v">{formatTime(alert.acknowledged_at)}</span></li>}
            <li><span className="k">Buzzer status</span><span className="v" style={{ color: buzzerStatus === 'Active' ? 'var(--red)' : 'var(--text-sub)' }}>{buzzerStatus}</span></li>
            <li><span className="k">Status</span><StatusPill status={alertStatusLabel(alert)} variant="alert" /></li>
          </ul>
        </>
      ) : (
        <>
          {alert.clip_url ? (
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
            <p style={{ color: 'var(--text-sub)', fontSize: 13.5 }}>No clip was recorded for this alert.</p>
          )}
        </>
      )}
    </SidePanel>
  );
}

export default function Alerts() {
  const [bannerOpen, setBannerOpen] = useState(true);
  const [filterOpen, setFilterOpen] = useState(false);
  const [filterCategory, setFilterCategory] = useState('date');
  const [datePreset, setDatePreset] = useState('');
  const [statusLabels, setStatusLabels] = useState([]);
  const [classroomId, setClassroomId] = useState('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [openAlert, setOpenAlert] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();
  const filterRef = useRef(null);
  const { classrooms, classroomsById } = useDirectory();
  const { entries } = useLiveStatus();

  useEffect(() => {
    setLoading(true);
    api.listAlerts({ classroom_id: classroomId || undefined, limit: 500 }).then(setAlerts).finally(() => setLoading(false));
  }, [classroomId]);

  useEventSocket(['ALERT_CREATED', 'ALERT_ACKNOWLEDGED', 'ALERT_RESOLVED'], (evt) => {
    const alert = evt.payload;
    setAlerts((prev) => {
      if (classroomId && alert.classroom_id !== classroomId) return prev;
      const exists = prev.some((a) => a.alert_id === alert.alert_id);
      return exists ? prev.map((a) => (a.alert_id === alert.alert_id ? alert : a)) : [alert, ...prev];
    });
    setOpenAlert((prev) => (prev && prev.alert_id === alert.alert_id ? alert : prev));
  });

  useEffect(() => {
    if (!filterOpen) return;
    const onDocClick = (e) => { if (filterRef.current && !filterRef.current.contains(e.target)) setFilterOpen(false); };
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, [filterOpen]);

  const unsupervised = Array.from(entries.values()).find((e) => e.supervision_status === 'UNSUPERVISED');
  const activeCount = alerts.filter((a) => a.status === 'ACTIVE').length;

  const appliedFilters = [
    datePreset && { key: 'date', label: DATE_PRESETS.find((d) => d.value === datePreset).label, clear: () => setDatePreset('') },
    statusLabels.length > 0 && { key: 'status', label: statusLabels.join(', '), clear: () => setStatusLabels([]) },
  ].filter(Boolean);

  const filtered = useMemo(() => {
    return alerts.filter((a) => {
      if (!matchesDatePreset(a, datePreset)) return false;
      if (statusLabels.length > 0 && !statusLabels.includes(alertStatusLabel(a))) return false;
      if (search.trim()) {
        const name = classroomsById.get(a.classroom_id)?.name ?? '';
        if (!name.toLowerCase().includes(search.trim().toLowerCase())) return false;
      }
      return true;
    });
  }, [alerts, datePreset, statusLabels, search, classroomsById]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, pageCount);
  const pageRows = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

  function resetAllFilters() {
    setDatePreset('');
    setStatusLabels([]);
    setSearch('');
    setPage(1);
  }

  function toggleStatusLabel(label) {
    setPage(1);
    setStatusLabels((prev) => (prev.includes(label) ? prev.filter((l) => l !== label) : [...prev, label]));
  }

  function toggleRow(id) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  function exportSelected() {
    const rows = filtered.filter((a) => selectedIds.has(a.alert_id));
    downloadCsv(
      'alerts-selected.csv',
      ['Date', 'Location', 'Started at', 'Acknowledged at', 'Unattended Duration', 'Status'],
      rows.map((a) => [
        formatDate(a.started_at), classroomsById.get(a.classroom_id)?.name ?? a.classroom_id,
        formatTime(a.started_at), a.acknowledged_at ? formatTime(a.acknowledged_at) : '-',
        formatDuration(a.started_at, a.resolved_at), alertStatusLabel(a),
      ]),
    );
  }

  const allOnPageSelected = pageRows.length > 0 && pageRows.every((a) => selectedIds.has(a.alert_id));

  return (
    <>
      <div className="content-header">
        <div className="title-row">
          <div className="page-title">Alerts</div>
          {activeCount > 0 && <span className="count-badge">{activeCount}</span>}
          <button className="bookmark-btn"><Bookmark size={15} /></button>
        </div>
        <button className="check-incidents-btn" onClick={() => navigate('/alerts/incidents')}>Check Incidents</button>
      </div>

      {bannerOpen && unsupervised && (
        <div className="buzzer-banner">
          <div className="buzzer-icon"><Bell /></div>
          <div className="buzzer-text">{unsupervised.classroom_name} left unsupervised</div>
          <button className="buzzer-view" onClick={() => navigate('/live-feed')}>View</button>
          <button className="buzzer-close" onClick={() => setBannerOpen(false)}><X size={14} /></button>
        </div>
      )}

      <div className="toolbar">
        <button className={`tab-pill${appliedFilters.length === 0 && !classroomId && !search ? ' active' : ''}`} onClick={resetAllFilters}>All</button>

        <div style={{ position: 'relative' }} ref={filterRef}>
          <button className="dropdown-btn" onClick={() => setFilterOpen((v) => !v)}>
            <FilterIcon size={13} /> Filter {appliedFilters.length > 0 && `(${appliedFilters.length})`}
          </button>
          <div className={`filter-popover${filterOpen ? ' open' : ''}`}>
            <div className="filter-cats">
              {['date', 'status'].map((cat) => (
                <button key={cat} className={`fc-item${filterCategory === cat ? ' sel' : ''}`} onClick={() => setFilterCategory(cat)} style={{ textTransform: 'capitalize' }}>
                  {cat}
                </button>
              ))}
            </div>
            <div className="filter-body">
              <div className="filter-row-wrap">
                {appliedFilters.map((f) => (
                  <span key={f.key} className="applied-chip">{f.label}<button onClick={f.clear}>✕</button></span>
                ))}
                <span className="reset-link" onClick={resetAllFilters} style={{ cursor: 'pointer' }}>Reset</span>
              </div>
              {filterCategory === 'date' && DATE_PRESETS.map((d) => (
                <div key={d.value} className="status-opt">
                  <span>{d.label}</span>
                  <button className={`switch${datePreset === d.value ? ' on' : ''}`} onClick={() => { setDatePreset(d.value); setPage(1); }} />
                </div>
              ))}
              {filterCategory === 'status' && STATUS_LABELS.map((label) => (
                <div key={label} className="status-opt">
                  <span>{label} only</span>
                  <button className={`switch${statusLabels.includes(label) ? ' on' : ''}`} onClick={() => toggleStatusLabel(label)} />
                </div>
              ))}
            </div>
          </div>
        </div>

        <select className="dropdown-select" value={classroomId} onChange={(e) => { setClassroomId(e.target.value); setPage(1); }}>
          <option value="">All sites</option>
          {classrooms.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>

        <div className="search-wrap">
          <Search />
          <input value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }} placeholder="Search by location" />
        </div>

        <div className="pager">
          {selectedIds.size > 0 && (
            <button className="dropdown-btn" onClick={exportSelected} style={{ marginRight: 8 }}>Export {selectedIds.size} selected</button>
          )}
          <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={currentPage === 1}><ChevronLeft /></button>
          <span className="cur">{currentPage}</span>
          <button onClick={() => setPage((p) => Math.min(pageCount, p + 1))} disabled={currentPage === pageCount}><ChevronRight /></button>
        </div>
      </div>

      <div className="table-wrap">
        {loading ? (
          <p style={{ padding: 32, textAlign: 'center', color: 'var(--text-sub)', fontSize: 13.5 }}>Loading alerts…</p>
        ) : filtered.length === 0 ? (
          <p style={{ padding: 32, textAlign: 'center', color: 'var(--text-sub)', fontSize: 13.5 }}>Nothing matches the current filters, or none have fired yet.</p>
        ) : (
          <table className="col-fixed">
            <colgroup>
              <col style={{ width: 40 }} />
              <col style={{ width: 84 }} />
              <col />
              <col style={{ width: 96 }} />
              <col style={{ width: 128 }} />
              <col style={{ width: 150 }} />
              <col style={{ width: 128 }} />
              <col style={{ width: 128 }} />
            </colgroup>
            <thead>
              <tr>
                <th className="chk">
                  <input
                    type="checkbox"
                    checked={allOnPageSelected}
                    onChange={() => setSelectedIds((prev) => {
                      const next = new Set(prev);
                      if (allOnPageSelected) pageRows.forEach((a) => next.delete(a.alert_id));
                      else pageRows.forEach((a) => next.add(a.alert_id));
                      return next;
                    })}
                  />
                </th>
                <th>Date</th><th>Location</th><th>Started at</th><th>Acknowledged at</th>
                <th className="num">Unattended Duration</th><th className="center">Status</th><th className="center">Acknowledged</th>
              </tr>
            </thead>
            <tbody>
              {pageRows.map((a) => (
                <tr key={a.alert_id} className="clickable" onClick={() => setOpenAlert(a)}>
                  <td onClick={(e) => e.stopPropagation()}><input type="checkbox" checked={selectedIds.has(a.alert_id)} onChange={() => toggleRow(a.alert_id)} /></td>
                  <td>{formatDate(a.started_at)}</td>
                  <td className="loc">{classroomsById.get(a.classroom_id)?.name ?? a.classroom_id}</td>
                  <td>{formatTime(a.started_at)}</td>
                  <td>{a.acknowledged_at ? formatTime(a.acknowledged_at) : '-'}</td>
                  <td className="num tabular">{formatDuration(a.started_at, a.resolved_at)}</td>
                  <td className="center"><StatusPill status={alertStatusLabel(a)} variant="alert" /></td>
                  <td className={`center${a.acknowledged_at ? '' : ' ack-not-yet'}`}>{a.acknowledged_at ? 'Yes' : 'Not Yet'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <AlertDetailPanel
        alert={openAlert}
        classroomName={openAlert ? (classroomsById.get(openAlert.classroom_id)?.name ?? openAlert.classroom_id) : ''}
        onClose={() => setOpenAlert(null)}
        onAcknowledged={(updated) => {
          setOpenAlert(updated);
          setAlerts((prev) => prev.map((a) => (a.alert_id === updated.alert_id ? updated : a)));
        }}
      />
    </>
  );
}
