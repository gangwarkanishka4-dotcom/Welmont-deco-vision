// The backend does not yet expose a user/role management API. This page is an interface
// shell describing the intended access model without inventing fake accounts or numbers —
// wire it up to a real /api/users endpoint when one exists.

const ROLES = [
  { name: 'Administrator', description: 'Full access — manage cameras, ROI/calibration, users, and settings.' },
  { name: 'Operator', description: 'Acknowledge and resolve alerts, view live feeds and analytics.' },
  { name: 'Viewer', description: 'Read-only access to dashboards, alerts, and analytics.' },
];

export function UserAccessPage() {
  return (
    <div className="max-w-3xl space-y-6">
      <div className="panel p-5">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-sm font-semibold text-slate-100">Roles & Permissions</p>
            <p className="mt-1 text-sm text-slate-500">Planned access tiers for operators of this system.</p>
          </div>
          <button className="btn-secondary" disabled title="Requires a user management API">
            + Invite User
          </button>
        </div>
        <div className="mt-4 divide-y divide-surface-700">
          {ROLES.map((role) => (
            <div key={role.name} className="flex items-center justify-between py-3">
              <div>
                <p className="text-sm font-medium text-slate-200">{role.name}</p>
                <p className="text-xs text-slate-500">{role.description}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="rounded-lg border border-dashed border-surface-600 p-5 text-center">
        <p className="text-sm font-medium text-slate-300">No user accounts endpoint yet</p>
        <p className="mt-1 text-sm text-slate-500">
          Once the backend exposes user/session management, this page will list real accounts, roles, and last-active
          times here.
        </p>
      </div>
    </div>
  );
}
