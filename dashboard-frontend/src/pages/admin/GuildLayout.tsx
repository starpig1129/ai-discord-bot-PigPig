import { useEffect, useState } from 'react';
import { useParams, useNavigate, NavLink, Outlet } from 'react-router-dom';
import { motion } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import api from '../../lib/api';

interface GuildInfo {
  id: string;
  name: string;
  icon: string | null;
  member_count: number;
}

const GUILD_NAV = [
  { to: '', label: 'guild.overview', icon: '📊', end: true },
  { to: 'channels', label: 'guild.channels', icon: '📋', end: false },
  { to: 'prompt', label: 'guild.prompt', icon: '✍️', end: false },
  { to: 'stats', label: 'guild.stats', icon: '📈', end: false },
];

export default function GuildLayout() {
  const { guildId } = useParams<{ guildId: string }>();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [guild, setGuild] = useState<GuildInfo | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!guildId) return;
    setError(false);
    api.get(`/api/guild/${guildId}/overview`)
      .then(({ data }) => setGuild(data))
      .catch(() => setError(true));
  }, [guildId]);

  if (error) return (
    <div style={{ textAlign: 'center', padding: '4rem', color: 'var(--color-text-muted)' }}>
      <div style={{ fontSize: '2rem', marginBottom: '1rem' }}>⚠️</div>
      <p>無法載入伺服器資訊，請確認 Bot 是否在線或權限是否正確。</p>
      <button onClick={() => navigate('/admin/guilds')} style={{
        marginTop: '1rem', padding: '0.5rem 1.25rem', cursor: 'pointer',
        borderRadius: 'var(--radius-md)', border: '1px solid var(--color-border)',
        background: 'transparent', color: 'var(--color-text-secondary)',
      }}>← 返回伺服器列表</button>
    </div>
  );

  if (!guild) return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '60vh' }}>
      <div className="animate-pulse-glow" style={{ fontSize: '2rem' }}>🏠</div>
    </div>
  );

  const basePath = `/guild/${guildId}`;

  return (
    <div>
      {/* Guild Header */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '1rem',
          marginBottom: '1.5rem',
          paddingBottom: '1.25rem',
          borderBottom: '1px solid var(--color-border)',
        }}
      >
        <button
          onClick={() => navigate('/admin/guilds')}
          style={{
            background: 'none',
            border: '1px solid var(--color-border)',
            borderRadius: 'var(--radius-sm)',
            color: 'var(--color-text-muted)',
            cursor: 'pointer',
            padding: '0.375rem 0.75rem',
            fontSize: '0.8125rem',
          }}
        >
          ← {t('common.back')}
        </button>

        {guild.icon ? (
          <img src={guild.icon} alt={guild.name}
            style={{ width: 40, height: 40, borderRadius: 'var(--radius-md)' }} />
        ) : (
          <div style={{
            width: 40, height: 40, borderRadius: 'var(--radius-md)',
            background: 'linear-gradient(135deg, var(--color-accent-blue), var(--color-accent-violet))',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontWeight: 700, fontSize: '1.1rem',
          }}>
            {guild.name.charAt(0).toUpperCase()}
          </div>
        )}

        <div>
          <h1 style={{ fontSize: '1.25rem', fontWeight: 700 }}>{guild.name}</h1>
          <p style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', marginTop: '0.125rem' }}>
            👥 {(guild.member_count ?? 0).toLocaleString()} {t('guilds.members')}
          </p>
        </div>
      </motion.div>

      {/* Sub-navigation tabs — use absolute paths to avoid nested Routes issues */}
      <div style={{ display: 'flex', gap: '0.375rem', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
        {GUILD_NAV.map(({ to, label, icon, end }) => (
          <NavLink
            key={label}
            to={to ? `${basePath}/${to}` : basePath}
            end={end}
            style={({ isActive }) => ({
              display: 'flex', alignItems: 'center', gap: '0.4rem',
              padding: '0.5rem 1rem',
              borderRadius: 'var(--radius-sm)',
              border: '1px solid',
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

      {/* Child pages rendered via Outlet (defined in App.tsx Route children) */}
      <Outlet context={{ guildId }} />
    </div>
  );
}
