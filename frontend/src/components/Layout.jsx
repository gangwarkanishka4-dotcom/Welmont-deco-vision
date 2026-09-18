import Sidebar from './Sidebar';
import Topbar from './Topbar';

export default function Layout({ children }) {
  return (
    <div className="deco">
      <div className="app">
        <Sidebar />
        <div className="main">
          <Topbar />
          <div className="content">{children}</div>
        </div>
      </div>
    </div>
  );
}
