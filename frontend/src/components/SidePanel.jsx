import { X } from 'lucide-react';

export default function SidePanel({ open, onClose, title, subtitle, children, footer }) {
  return (
    <>
      <div className={`overlay${open ? ' open' : ''}`} onClick={onClose} />
      <div className={`side-panel${open ? ' open' : ''}`}>
        <div className="sp-head">
          <div className="sp-title-row">
            <div>
              <div className="sp-title">{title}</div>
              {subtitle && <div className="sp-sub">{subtitle}</div>}
            </div>
            <button className="sp-close" onClick={onClose}><X /></button>
          </div>
        </div>
        <div className="sp-body">{children}</div>
        {footer && <div className="sp-footer">{footer}</div>}
      </div>
    </>
  );
}
