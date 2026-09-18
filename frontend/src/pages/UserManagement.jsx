import { Users } from 'lucide-react';
import ComingSoon from '../components/ComingSoon';

export default function UserManagement() {
  return (
    <>
      <div className="content-header">
        <div>
          <div className="page-title">User Management</div>
          <div className="page-sub">Manage users, roles and access across your sites.</div>
        </div>
      </div>
      <ComingSoon
        icon={Users}
        title="Not available yet"
        reason="There's no login/user-management system in the backend yet, and face-recognition enrollment for employees or visitors was deliberately never built (the system reads adult-vs-child only, never identity). This page will connect once that backend support exists."
      />
    </>
  );
}
