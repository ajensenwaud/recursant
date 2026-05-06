import { useEffect, useState, useCallback } from 'react';
import { Outlet } from 'react-router-dom';
import Navbar from './Navbar';
import Sidebar from './Sidebar';
import MeshConnectionBanner from './MeshConnectionBanner';

const STORAGE_KEY = 'recursant.sidebar.collapsed';

export default function Layout() {
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem(STORAGE_KEY) === '1';
    } catch {
      return false;
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, collapsed ? '1' : '0');
    } catch {
      /* ignore — private mode etc. */
    }
  }, [collapsed]);

  const toggle = useCallback(() => setCollapsed((c) => !c), []);

  return (
    <div className="h-screen flex flex-col bg-brand-bg text-brand-text">
      <Navbar sidebarCollapsed={collapsed} onToggleSidebar={toggle} />
      <div className="flex flex-1 min-h-0">
        {!collapsed && <Sidebar />}
        <main className="flex-1 min-w-0 p-6 overflow-auto">
          <Outlet />
        </main>
      </div>
      <MeshConnectionBanner />
    </div>
  );
}
