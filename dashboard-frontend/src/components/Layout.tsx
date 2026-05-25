import { useState } from 'react';
import { Outlet, Navigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { useIsMobile } from '../hooks/useIsMobile';
import Sidebar from './Sidebar';

export default function Layout() {
  const { user, loading, logout } = useAuth();
  const isMobile = useIsMobile();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  if (loading) {
    return (
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '100vh',
        background: 'var(--color-bg-primary)',
      }}>
        <div className="animate-pulse-glow" style={{ fontSize: '3rem' }}>🐷</div>
      </div>
    );
  }

  if (!user) return <Navigate to="/login" replace />;

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      <Sidebar
        user={user}
        onLogout={logout}
        isMobileOpen={sidebarOpen}
        onMobileClose={() => setSidebarOpen(false)}
      />

      {/* Mobile backdrop */}
      {isMobile && sidebarOpen && (
        <div
          onClick={() => setSidebarOpen(false)}
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.55)',
            zIndex: 35,
            backdropFilter: 'blur(2px)',
          }}
        />
      )}

      <main style={{
        marginLeft: isMobile ? 0 : 260,
        flex: 1,
        padding: isMobile ? '1rem' : '2rem',
        paddingTop: isMobile ? '4.5rem' : '2rem',
        background: 'var(--color-bg-primary)',
        minHeight: '100vh',
      }}>
        {/* Mobile hamburger */}
        {isMobile && (
          <button
            onClick={() => setSidebarOpen(true)}
            aria-label="Open menu"
            style={{
              position: 'fixed',
              top: '0.875rem',
              left: '1rem',
              zIndex: 20,
              background: 'var(--color-bg-secondary)',
              border: '1px solid var(--color-border)',
              borderRadius: 'var(--radius-sm)',
              color: 'var(--color-text-primary)',
              cursor: 'pointer',
              padding: '0.45rem 0.6rem',
              fontSize: '1.1rem',
              lineHeight: 1,
              boxShadow: 'var(--shadow-card)',
            }}
          >
            ☰
          </button>
        )}

        <Outlet />
      </main>
    </div>
  );
}
