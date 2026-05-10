import { Routes, Route, NavLink } from 'react-router-dom';
import { motion } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import { type User, getAvatarUrl } from '../../lib/auth';
import UserProfile from './user/Profile';
import UserMemory from './user/Memory';
import UserStatsPage from './user/UserStats';
import DeleteData from './user/DeleteData';

interface UserPortalProps {
  user: User;
}

const USER_NAV = [
  { path: '', label: 'user.profile', icon: '👤', end: true },
  { path: 'stats', label: 'user.stats', icon: '📊' },
  { path: 'memory', label: 'user.memory', icon: '🧠' },
  { path: 'delete', label: 'user.deleteData', icon: '🗑️' },
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

      {/* Sub-nav */}
      <div style={{ display: 'flex', gap: '0.375rem', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
        {USER_NAV.map(({ path, label, icon, end }) => (
          <NavLink
            key={label}
            to={path}
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

      <Routes>
        <Route index element={<UserProfile user={user} />} />
        <Route path="stats" element={<UserStatsPage />} />
        <Route path="memory" element={<UserMemory />} />
        <Route path="delete" element={<DeleteData />} />
      </Routes>
    </div>
  );
}
