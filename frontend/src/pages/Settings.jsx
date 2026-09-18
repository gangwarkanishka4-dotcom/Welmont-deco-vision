import { useState } from 'react';
import { useAlertSoundSetting, playAlertBeep, speakAlert } from '../hooks/useAlertSound.js';
import { API_BASE_URL } from '../services/api.js';

const NOT_WIRED = 'Not available yet — no backend delivery for this channel/category';

function NotifCheckbox({ checked, onChange, disabled }) {
  return (
    <div className="chk-wrap">
      <input type="checkbox" checked={checked} onChange={onChange} disabled={disabled} title={disabled ? NOT_WIRED : undefined} />
    </div>
  );
}

function NotificationsTab() {
  const [soundEnabled, setSoundEnabled] = useAlertSoundSetting();

  return (
    <div>
      <div className="notif-head-row"><div /><div className="h">Push notification</div><div className="h">Email notification</div></div>

      <div className="notif-group-label">General</div>
      <div className="notif-row">
        <div className="label">Alerts notification (in-app beep + spoken announcement)</div>
        <NotifCheckbox checked={soundEnabled} onChange={(e) => setSoundEnabled(e.target.checked)} />
        <NotifCheckbox checked={false} disabled />
      </div>
      <div className="notif-row"><div className="label">Camera health updates</div><NotifCheckbox checked={false} disabled /><NotifCheckbox checked={false} disabled /></div>
      <div className="notif-row"><div className="label">Attendance updates</div><NotifCheckbox checked={false} disabled /><NotifCheckbox checked={false} disabled /></div>
      <div className="notif-row"><div className="label">System updates</div><NotifCheckbox checked={false} disabled /><NotifCheckbox checked={false} disabled /></div>

      {soundEnabled && (
        <div style={{ display: 'flex', gap: 8, marginTop: 14 }}>
          <button className="dropdown-btn" onClick={playAlertBeep}>▶ Test sound</button>
          <button className="dropdown-btn" onClick={() => speakAlert('Basement Class 1 is unsupervised')}>▶ Test announcement</button>
        </div>
      )}

      <p style={{ fontSize: 12.5, color: 'var(--text-sub)', marginTop: 16 }}>
        Only the in-app sound + spoken announcement above are real today — the backend has no email or mobile-push delivery yet, so the rest of this grid is shown for reference and stays disabled.
      </p>

      <button className="save-pref-btn" disabled title="Nothing else here is wired to a real preference yet">Save preferences</button>
      <div style={{ clear: 'both' }} />
    </div>
  );
}

function ProfileTab() {
  return (
    <div>
      <div className="profile-pic-row">
        <div className="profile-pic" />
        <div>
          <a className="edit-pic-link" href="#" onClick={(e) => e.preventDefault()} style={{ opacity: 0.5, pointerEvents: 'none' }}>Edit profile picture</a>
          <div className="edit-pic-sub">No login/user system yet</div>
        </div>
      </div>
      <div className="settings-field"><label>Agent's Name</label><div className="row"><input value="—" readOnly /></div></div>
      <div className="settings-field"><label>Role</label><div className="row"><input value="—" readOnly /></div></div>
      <p style={{ fontSize: 12.5, color: 'var(--text-sub)', maxWidth: 420 }}>
        There's no login/user system in the backend yet, so there's no real profile to show or edit. This tab will connect once that support exists.
      </p>
    </div>
  );
}

export default function Settings() {
  const [tab, setTab] = useState('notif');

  return (
    <>
      <div className="content-header">
        <div>
          <div className="page-title">System Settings</div>
          <div className="page-sub">Setup and edit system settings and preferences</div>
        </div>
      </div>

      <div className="subtab-row">
        <button className={`subtab${tab === 'profile' ? ' active' : ''}`} onClick={() => setTab('profile')}>Profile settings</button>
        <button className={`subtab${tab === 'notif' ? ' active' : ''}`} onClick={() => setTab('notif')}>Notifications</button>
      </div>

      {tab === 'notif' ? <NotificationsTab /> : <ProfileTab />}
    </>
  );
}
