export function Field({ label, children }) {
  return (
    <label className="block">
      {label && <span className="field-label">{label}</span>}
      {children}
    </label>
  );
}

export function TextInput(props) {
  return <input {...props} className={`field-input ${props.className || ''}`} />;
}

export function Select({ children, ...props }) {
  return (
    <select {...props} className={`field-select ${props.className || ''}`}>
      {children}
    </select>
  );
}

export function PrimaryButton({ children, className = '', ...props }) {
  return (
    <button {...props} className={`primary-btn ${className}`}>
      {children}
    </button>
  );
}

export function GhostButton({ children, className = '', ...props }) {
  return (
    <button {...props} className={`dropdown-btn ${className}`}>
      {children}
    </button>
  );
}

export function DangerButton({ children, className = '', ...props }) {
  return (
    <button {...props} className={`trash-btn ${className}`} style={{ width: 'auto', height: 'auto', padding: '9px 18px', borderRadius: 9, fontWeight: 700, fontSize: '13.5px', ...props.style }}>
      {children}
    </button>
  );
}
