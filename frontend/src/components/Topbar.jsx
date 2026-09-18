import { Bell } from 'lucide-react';

const todayLabel = new Date().toLocaleDateString(undefined, {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  weekday: 'long',
});

export default function Topbar() {
  return (
    <div className="topbar">
      <div className="topbar-left">
        <div className="topbar-date">{todayLabel}</div>
      </div>
      <div className="topbar-right">
        <button className="icon-btn" aria-label="Notifications">
          <Bell />
          <span className="dot" />
        </button>
        <div className="avatar">A</div>
      </div>
    </div>
  );
}
