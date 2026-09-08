import { NavLink } from 'react-router-dom';

const NAV_ITEMS = [
  { to: '/', label: 'Dashboard', icon: '▦' },
  { to: '/cameras', label: 'Cameras', icon: '▣' },
  { to: '/live', label: 'Live Monitoring', icon: '▶' },
  { to: '/alerts', label: 'Alerts', icon: '⚠' },
  { to: '/analytics', label: 'Analytics', icon: '▩' },
  { to: '/user-access', label: 'User Access', icon: '☺' },
  { to: '/settings', label: 'Settings', icon: '⚙' },
];

export function Sidebar() {
  return (
    <aside className="flex h-full w-60 shrink-0 flex-col border-r border-surface-700 bg-surface-900">
      <div className="flex items-center gap-2 px-5 py-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-md bg-accent-500 text-sm font-bold text-white">
          W
        </div>
        <div>
          <p className="text-sm font-semibold leading-tight text-slate-100">Welmont</p>
          <p className="text-[11px] leading-tight text-slate-500">Deco Vision</p>
        </div>
      </div>
      <nav className="flex-1 space-y-0.5 px-3">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-accent-500/15 text-accent-400'
                  : 'text-slate-400 hover:bg-surface-800 hover:text-slate-200'
              }`
            }
          >
            <span className="w-4 text-center text-xs">{item.icon}</span>
            {item.label}
          </NavLink>
        ))}
      </nav>
      <div className="px-5 py-4 text-[11px] text-slate-600">v0.1.0</div>
    </aside>
  );
}
