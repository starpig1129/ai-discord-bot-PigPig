import { useEffect, useState } from 'react';
import { useParams, useNavigate, Routes, Route, NavLink } from 'react-router-dom';
import { motion } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import api from '../../lib/api';
import GuildOverview from './guild/Overview';
import GuildChannels from './guild/Channels';
import GuildPrompt from './guild/Prompt';
import GuildStats from './guild/GuildStats';

interface GuildInfo {
  id: string;
  name: string;
  icon: string | null;
  member_count: number;
}

const GUILD_NAV = [
  { path: '', label: 'guild.overview', icon: '📊', end: true },
  { path: 'channels', label: 'guild.channels', icon: '📋' },
  { path: 'prompt', label: 'guild.prompt', icon: '✍️' },
  { path: 'stats', label: 'guild.stats', icon: '📈' },
];

export default function GuildLayout() {
  const { guildId } = useParams<{ guildId: string }>();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [guild, setGuild] = useState<GuildInfo | null>(null);

  useEffect(() => {
    if (!guildId) return;
    api.get(`/api/guild/${guildId}/overview`)
      .then(({ data }) => setGuild(data))
      .catch(() => navigate('/admin/guilds'));
  }, [guildId, navigate]);

  if (!guild) return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '60vh' }}>
      <div className="animate-pulse-glow" style={{ fontSize: '2rem' }}>🏠</div>
    </div>
  );

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

      {/* Sub-navigation tabs */}
      <div style={{ display: 'flex', gap: '0.375rem', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
        {GUILD_NAV.map(({ path, label, icon, end }) => (
          <NavLink
            key={label}
            to={path}
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

      {/* Nested routes */}
      <Routes>
        <Route index element={<GuildOverview guildId={guildId!} />} />
        <Route path="channels" element={<GuildChannels guildId={guildId!} />} />
        <Route path="prompt" element={<GuildPrompt guildId={guildId!} />} />
        <Route path="stats" element={<GuildStats guildId={guildId!} />} />
      </Routes>
    </div>
  );
}
