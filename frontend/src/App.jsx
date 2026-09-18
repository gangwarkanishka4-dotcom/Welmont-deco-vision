import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { EventSocketProvider } from './websocket/EventSocketProvider.jsx';
import { DirectoryProvider } from './context/DirectoryProvider.jsx';
import { AlertToastProvider } from './components/toast/AlertToastProvider.jsx';
import Layout from './components/Layout';
import Dashboard from './pages/Dashboard';
import LiveFeed from './pages/LiveFeed';
import Alerts from './pages/Alerts';
import Incidents from './pages/Incidents';
import SiteManagement from './pages/SiteManagement';
import CameraManagement from './pages/CameraManagement';
import UserManagement from './pages/UserManagement';
import Reports from './pages/Reports';
import Settings from './pages/Settings';

export default function App() {
  return (
    <BrowserRouter>
      <EventSocketProvider>
        <DirectoryProvider>
          <AlertToastProvider>
            <Layout>
              <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/live-feed" element={<LiveFeed />} />
                <Route path="/alerts" element={<Alerts />} />
                <Route path="/alerts/incidents" element={<Incidents />} />
                <Route path="/sites" element={<SiteManagement />} />
                <Route path="/cameras" element={<CameraManagement />} />
                <Route path="/users" element={<UserManagement />} />
                <Route path="/reports" element={<Reports />} />
                <Route path="/settings" element={<Settings />} />
              </Routes>
            </Layout>
          </AlertToastProvider>
        </DirectoryProvider>
      </EventSocketProvider>
    </BrowserRouter>
  );
}
