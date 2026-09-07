import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { EventSocketProvider } from './websocket/EventSocketProvider.jsx';
import { DirectoryProvider } from './context/DirectoryProvider.jsx';
import { AlertToastProvider } from './components/toast/AlertToastProvider.jsx';
import { AppLayout } from './components/layout/AppLayout.jsx';
import { DashboardPage } from './pages/DashboardPage.jsx';
import { CamerasPage } from './pages/CamerasPage.jsx';
import { LiveMonitoringIndexPage } from './pages/LiveMonitoringIndexPage.jsx';
import { LiveMonitoringPage } from './pages/LiveMonitoringPage.jsx';
import { AlertsPage } from './pages/AlertsPage.jsx';
import { AnalyticsPage } from './pages/AnalyticsPage.jsx';
import { AttendancePage } from './pages/AttendancePage.jsx';
import { UserAccessPage } from './pages/UserAccessPage.jsx';
import { SettingsPage } from './pages/SettingsPage.jsx';

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
