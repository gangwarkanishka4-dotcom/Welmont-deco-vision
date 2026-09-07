import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { EventSocketProvider } from './websocket/EventSocketProvider';
import { DirectoryProvider } from './hooks/useDirectory';
import { AlertToastProvider } from './components/toast/AlertToastProvider';
import { AppLayout } from './components/layout/AppLayout';
import { DashboardPage } from './pages/DashboardPage';
import { CamerasPage } from './pages/CamerasPage';
import { LiveMonitoringIndexPage } from './pages/LiveMonitoringIndexPage';
import { LiveMonitoringPage } from './pages/LiveMonitoringPage';
import { AlertsPage } from './pages/AlertsPage';
import { AnalyticsPage } from './pages/AnalyticsPage';
import { AttendancePage } from './pages/AttendancePage';
import { UserAccessPage } from './pages/UserAccessPage';
import { SettingsPage } from './pages/SettingsPage';

export default function App() {
  return (
    <BrowserRouter>
      <EventSocketProvider>
        <DirectoryProvider>
          <AlertToastProvider>
            <Routes>
              <Route element={<AppLayout />}>
                <Route index element={<DashboardPage />} />
                <Route path="cameras" element={<CamerasPage />} />
                <Route path="live" element={<LiveMonitoringIndexPage />} />
                <Route path="live/:cameraId" element={<LiveMonitoringPage />} />
                <Route path="alerts" element={<AlertsPage />} />
                <Route path="alerts/:alertId" element={<AlertsPage />} />
                <Route path="analytics" element={<AnalyticsPage />} />
                <Route path="attendance" element={<AttendancePage />} />
                <Route path="user-access" element={<UserAccessPage />} />
                <Route path="settings" element={<SettingsPage />} />
              </Route>
            </Routes>
          </AlertToastProvider>
        </DirectoryProvider>
      </EventSocketProvider>
    </BrowserRouter>
  );
}
