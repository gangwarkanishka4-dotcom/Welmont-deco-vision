import { useEffect, useState } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import {
  LayoutGrid, Video, Bell, FileBarChart, Camera as CameraIcon,
  MapPin, Users, Settings as SettingsIcon, ChevronDown, Boxes,
} from 'lucide-react';
import { api } from '../services/api.js';
import { useEventSocket } from '../hooks/useEventSocket.js';
import logo from '../assets/logo.png';

/** Real count of currently-ACTIVE alerts — fetched once on mount, kept live
 * via the same alert lifecycle events the rest of the app listens to. */
function useActiveAlertCount() {
  const [count, setCount] = useState(0);

  useEffect(() => {
    let cancelled = false;
    api
      .listAlerts({ status: 'ACTIVE' })
      .then((alerts) => {
        if (!cancelled) setCount(alerts.length);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  useEventSocket(['ALERT_CREATED'], () => setCount((c) => c + 1));
  useEventSocket(['ALERT_RESOLVED'], () => setCount((c) => Math.max(0, c - 1)));

  return count;
}

function Item({ to, icon: Icon, children, badge }) {
  return (
    <NavLink to={to} className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}>
      <Icon />
      {children}
      {badge != null && <span className="badge">{badge}</span>}
    </NavLink>
  );
}

export default function Sidebar() {
  const activeAlerts = useActiveAlertCount();
  const location = useLocation();
  const managementPaths = ['/cameras', '/sites', '/users'];
  const [mgmtOpen, setMgmtOpen] = useState(managementPaths.includes(location.pathname));

  useEffect(() => {
    if (managementPaths.includes(location.pathname)) setMgmtOpen(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname]);

  return (
    <aside className="sidebar">
      <div className="brand">
        <img src={logo} alt="Deco Vision" className="brand-logo" />
        <span className="brand-name">Deco Vision</span>
      </div>

      <Item to="/" icon={LayoutGrid}>Dashboard</Item>

      <div className="nav-section-label">Monitoring</div>
      <Item to="/live-feed" icon={Video}>Live feed</Item>
      <Item to="/alerts" icon={Bell} badge={activeAlerts || undefined}>Alerts</Item>
      <Item to="/reports" icon={FileBarChart}>Report</Item>

      <button
        type="button"
        className={`nav-item${mgmtOpen ? ' parent-open' : ''}`}
        onClick={() => setMgmtOpen((v) => !v)}
      >
        <Boxes />
        Management
        <ChevronDown className="chev" />
      </button>
      {mgmtOpen && (
        <div className="nav-sub">
          <Item to="/cameras" icon={CameraIcon}>Camera</Item>
          <Item to="/sites" icon={MapPin}>Site</Item>
          <Item to="/users" icon={Users}>User</Item>
        </div>
      )}

      <Item to="/settings" icon={SettingsIcon}>Settings</Item>
    </aside>
  );
}
