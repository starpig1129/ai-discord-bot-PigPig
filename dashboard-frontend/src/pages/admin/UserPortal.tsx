import { NavLink, Outlet } from 'react-router-dom';
import { motion } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import { type User, getAvatarUrl } from '../../lib/auth';

interface UserPortalProps {
  user: User;
}

const USER_NAV = [
  { to: '/me', label: 'user.profile', icon: '👤', end: true },
  { to: '/me/stats', label: 'user.stats', icon: '📊', end: false },
  { to: '/me/memory', label: 'user.memory', icon: '🧠', end: false },
  { to: '/me/delete', label: 'user.deleteData', icon: '🗑️', end: false },
];

export default function UserPortal({ user }: UserPortalProps) {
  const { t } = useTranslation();

  return (
    <div>
      {/* User header */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        style={{
          display: 'flex', alignItems: 'center', gap: '1rem',
          marginBottom: '1.5rem', paddingBottom: '1.25rem',
          borderBottom: '1px solid var(--color-border)',
        }}
      >
        <img
          src={getAvatarUrl(user)}
          alt="avatar"
          style={{ width: 48, height: 48, borderRadius: '50%', border: '2px solid var(--color-accent-blue)' }}
        />
        <div>
          <h1 style={{ fontSize: '1.25rem', fontWeight: 700 }}>{user.username}</h1>
          <p style={{ fontSize: '0.75rem', color: 'var(--color-accent-blue)', textTransform: 'uppercase', letterSpacing: '0.06em', marginTop: '0.125rem' }}>
            {user.role}
          </p>
        </div>
      </motion.div>

      {/* Sub-nav with absolute paths */}
      <div style={{ display: 'flex', gap: '0.375rem', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
        {USER_NAV.map(({ to, label, icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            style={({ isActive }) => ({
              display: 'flex', alignItems: 'center', gap: '0.4rem',
              padding: '0.5rem 1rem',
              borderRadius: 'var(--radius-sm)', border: '1px solid',
              borderColor: isActive ? 'var(--color-accent-blue)' : 'var(--color-border)',
              background: isActive ? 'rgba(59,130,246,0.15)' : 'transparent',
              color: isActive ? 'var(--color-accent-blue)' : 'var(--color-text-secondary)',
              textDecoration: 'none', fontSize: '0.875rem', fontWeight: 500,
              transition: 'all var(--transition-fast)',
            })}
          >
            <span>{icon}</span>
            {t(label)}
          </NavLink>
        ))}
      </div>

      {/* Child pages via Outlet, pass user as context */}
      <Outlet context={{ user }} />
    </div>
  );
}
