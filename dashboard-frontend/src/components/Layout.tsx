import { Outlet, Navigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import Sidebar from './Sidebar';

export default function Layout() {
  const { user, loading, logout } = useAuth();

  if (loading) {
    return (
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '100vh',
        background: 'var(--color-bg-primary)',
      }}>
        <div className="animate-pulse-glow" style={{
          fontSize: '3rem',
        }}>
          🐷
        </div>
      </div>
    );
  }

  if (!user) return <Navigate to="/login" replace />;

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      <Sidebar user={user} onLogout={logout} />
      <main style={{
        marginLeft: 260,
        flex: 1,
        padding: '2rem',
        background: 'var(--color-bg-primary)',
        minHeight: '100vh',
      }}>
        <Outlet />
      </main>
    </div>
  );
}
