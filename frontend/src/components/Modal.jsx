export default function Modal({ open, onClose, title, subtitle, width = 420, children }) {
  if (!open) return null;
  return (
    <div className="modal-overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose?.(); }}>
      <div className="modal-card" style={{ width }}>
        <div className="modal-title">{title}</div>
        {subtitle && <div className="modal-sub">{subtitle}</div>}
        {children}
      </div>
    </div>
  );
}
