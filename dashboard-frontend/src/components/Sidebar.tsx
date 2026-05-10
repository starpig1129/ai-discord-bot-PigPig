import { NavLink, useLocation } from 'react-router-dom';
import { motion } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import { type User, getAvatarUrl } from '../lib/auth';
import { LANGUAGES } from '../i18n';

interface SidebarProps {
  user: User;
  onLogout: () => void;
}

export default function Sidebar({ user, onLogout }: SidebarProps) {
  const location = useLocation();
  const { t, i18n } = useTranslation();

  const NAV_ITEMS = [
    { path: '/admin',         label: t('nav.dashboard'), icon: '📊' },
    { path: '/admin/stats',   label: t('nav.stats'),     icon: '📈' },
    { path: '/admin/guilds',  label: t('nav.guilds'),    icon: '🏠' },
    { path: '/admin/config',  label: t('nav.config'),    icon: '⚙️' },
    { path: '/admin/logs',    label: t('nav.logs'),      icon: '📝' },
    { path: '/admin/update',  label: t('nav.update'),    icon: '🔄' },
    { path: '/me',            label: t('nav.myPortal'),  icon: '👤', divider: true },
  ];

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
      <div style={{ padding: '1.5rem', borderBottom: '1px solid var(--color-border)' }}>
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
            <div key={item.path}>
              {item.divider && (
                <div style={{ height: 1, background: 'var(--color-border)', margin: '0.5rem 0.25rem' }} />
              )}
              <NavLink
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
            </div>
          );
        })}
      </nav>

      {/* Language Switcher */}
      <div style={{
        padding: '0.75rem 1.25rem',
        borderTop: '1px solid var(--color-border)',
        display: 'flex',
        gap: '0.5rem',
        alignItems: 'center',
      }}>
        <span style={{ fontSize: '0.7rem', color: 'var(--color-text-muted)', marginRight: '0.25rem' }}>
          {t('common.language')}
        </span>
        {LANGUAGES.map((lang) => (
          <button
            key={lang.code}
            onClick={() => i18n.changeLanguage(lang.code)}
            title={lang.label}
            style={{
              background: i18n.language === lang.code
                ? 'rgba(59, 130, 246, 0.2)'
                : 'transparent',
              border: i18n.language === lang.code
                ? '1px solid var(--color-accent-blue)'
                : '1px solid var(--color-border)',
              borderRadius: 'var(--radius-sm)',
              color: 'var(--color-text-primary)',
              cursor: 'pointer',
              fontSize: '0.75rem',
              padding: '0.25rem 0.5rem',
              transition: 'all var(--transition-fast)',
              display: 'flex',
              alignItems: 'center',
              gap: '0.25rem',
            }}
          >
            <span>{lang.flag}</span>
            <span style={{ fontSize: '0.65rem', opacity: 0.8 }}>
              {lang.code === 'zh-TW' ? '中文' : 'EN'}
            </span>
          </button>
        ))}
      </div>

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
          title={t('common.logout')}
        >
          🚪
        </button>
      </div>
    </motion.aside>
  );
}
