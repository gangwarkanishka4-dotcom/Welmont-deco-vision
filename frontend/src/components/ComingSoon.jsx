/** Honest placeholder for a page with no backend support yet — shown instead
 * of fabricated data or dead buttons, same principle the old dashboard's
 * Settings > User Access page followed ("Requires a user management API"). */
export default function ComingSoon({ icon: Icon, title, reason }) {
  return (
    <div
      className="rounded-xl border border-dashed flex flex-col items-center justify-center text-center px-6 py-16"
      style={{ borderColor: 'var(--line)', background: 'var(--surface)' }}
    >
      {Icon && (
        <div className="rounded-full p-3 mb-3" style={{ background: 'var(--neutral-bg)' }}>
          <Icon size={22} style={{ color: 'var(--ink-faint)' }} />
        </div>
      )}
      <p className="text-sm font-medium" style={{ color: 'var(--ink-soft)' }}>{title}</p>
      <p className="text-sm mt-1.5 max-w-sm" style={{ color: 'var(--ink-faint)' }}>{reason}</p>
    </div>
  );
}
