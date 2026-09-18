export default function KpiCard({ accent = 'blue', icon: Icon, number, label, cornerBadge, children }) {
  return (
    <div className="kpi-card" data-accent={accent}>
      <div className="kpi-top">
        {Icon ? <div className="kpi-icon-box"><Icon /></div> : <div />}
        {cornerBadge}
      </div>
      <div className="kpi-number">{number}</div>
      <div className="kpi-label">{label}</div>
      {children}
    </div>
  );
}
