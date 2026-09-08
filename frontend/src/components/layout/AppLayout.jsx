import { Outlet, useLocation } from 'react-router-dom';
import { Sidebar } from './Sidebar.jsx';
import { Topbar } from './Topbar.jsx';

const TITLES = [
  ['/cameras', 'Cameras'],
  ['/live', 'Live Monitoring'],
  ['/alerts', 'Alerts'],
  ['/analytics', 'Analytics'],
  ['/user-access', 'User Access'],
  ['/settings', 'Settings'],
];

function titleForPath(pathname) {
  const match = TITLES.find(([prefix]) => pathname.startsWith(prefix));
  return match ? match[1] : 'Dashboard';
}

export function AppLayout() {
  const location = useLocation();
  return (
    <div className="flex h-screen w-screen overflow-hidden bg-surface-950">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar title={titleForPath(location.pathname)} />
        <main className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
