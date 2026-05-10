import { NavLink, useLocation } from 'react-router-dom';
import { motion } from 'framer-motion';
import { type User, getAvatarUrl } from '../lib/auth';

interface SidebarProps {
  user: User;
  onLogout: () => void;
}

const NAV_ITEMS = [
  { path: '/admin', label: 'Dashboard', icon: '📊' },
  { path: '/admin/stats', label: 'Statistics', icon: '📈' },
  { path: '/admin/guilds', label: 'Servers', icon: '🏠' },
  { path: '/admin/config', label: 'Config', icon: '⚙️' },
  { path: '/admin/logs', label: 'Logs', icon: '📝' },
  { path: '/admin/update', label: 'Update', icon: '🔄' },
];

export default function Sidebar({ user, onLogout }: SidebarProps) {
  const location = useLocation();

  return (
    <motion.aside
      initial={{ x: -260 }}
      animate={{ x: 0 }}
      transition={{ type: 'spring', stiffness: 300, damping: 30 }}
      style={{
        width: 260,
        minHeight: '100vh',
        background: 'var(--color-bg-secondary)',
        borderRight: '1px solid var(--color-border)',
        display: 'flex',
        flexDirection: 'column',
        position: 'fixed',
        top: 0,
        left: 0,
        zIndex: 40,
      }}
    >
      {/* Logo */}
      <div style={{
        padding: '1.5rem',
        borderBottom: '1px solid var(--color-border)',
      }}>
        <h1
          className="gradient-text"
          style={{ fontSize: '1.5rem', fontWeight: 700, letterSpacing: '-0.02em' }}
        >
          🐷 PigPig
        </h1>
        <p style={{ color: 'var(--color-text-muted)', fontSize: '0.75rem', marginTop: '0.25rem' }}>
          Dashboard
        </p>
      </div>

      {/* Navigation */}
      <nav style={{ flex: 1, padding: '1rem 0.75rem', display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
        {NAV_ITEMS.map((item) => {
          const isActive = location.pathname === item.path ||
            (item.path !== '/admin' && location.pathname.startsWith(item.path));
          return (
            <NavLink
              key={item.path}
              to={item.path}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.75rem',
                padding: '0.625rem 1rem',
                borderRadius: 'var(--radius-md)',
                color: isActive ? 'var(--color-text-primary)' : 'var(--color-text-secondary)',
                background: isActive ? 'rgba(59, 130, 246, 0.15)' : 'transparent',
                textDecoration: 'none',
                fontSize: '0.875rem',
                fontWeight: isActive ? 600 : 400,
                transition: 'all var(--transition-fast)',
                borderLeft: isActive ? '3px solid var(--color-accent-blue)' : '3px solid transparent',
              }}
              onMouseEnter={(e) => {
                if (!isActive) e.currentTarget.style.background = 'rgba(148, 163, 184, 0.08)';
              }}
              onMouseLeave={(e) => {
                if (!isActive) e.currentTarget.style.background = 'transparent';
              }}
            >
              <span style={{ fontSize: '1.1rem' }}>{item.icon}</span>
              {item.label}
            </NavLink>
          );
        })}
      </nav>

      {/* User Profile */}
      <div style={{
        padding: '1rem 1.25rem',
        borderTop: '1px solid var(--color-border)',
        display: 'flex',
        alignItems: 'center',
        gap: '0.75rem',
      }}>
        <img
          src={getAvatarUrl(user)}
          alt="avatar"
          style={{
            width: 36,
            height: 36,
            borderRadius: '50%',
            border: '2px solid var(--color-accent-blue)',
          }}
        />
        <div style={{ flex: 1, minWidth: 0 }}>
          <p style={{
            fontSize: '0.8125rem',
            fontWeight: 600,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}>
            {user.username}
          </p>
          <p style={{
            fontSize: '0.6875rem',
            color: 'var(--color-accent-blue)',
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
          }}>
            {user.role}
          </p>
        </div>
        <button
          onClick={onLogout}
          style={{
            background: 'none',
            border: 'none',
            color: 'var(--color-text-muted)',
            cursor: 'pointer',
            fontSize: '1.1rem',
            padding: '0.25rem',
          }}
          title="Logout"
        >
          🚪
        </button>
      </div>
    </motion.aside>
  );
}
