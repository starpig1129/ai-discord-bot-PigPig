import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import api from '../../lib/api';

interface Guild {
  id: string;
  name: string;
  member_count: number;
  icon: string | null;
  owner_id: string | null;
}

export default function Guilds() {
  const { t } = useTranslation();
  const [guilds, setGuilds] = useState<Guild[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get('/api/admin/guilds')
      .then(({ data }) => setGuilds(data.guilds))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '60vh' }}>
        <div className="animate-pulse-glow" style={{ fontSize: '2rem' }}>🏠</div>
      </div>
    );
  }

  return (
    <div>
      <h1 style={{ fontSize: '1.75rem', fontWeight: 700, marginBottom: '0.5rem' }}>🏠 {t('guilds.title')}</h1>
      <p style={{ color: 'var(--color-text-secondary)', marginBottom: '2rem' }}>
        {guilds.length} {t('guilds.title').toLowerCase()}
      </p>

      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
        gap: '1rem',
      }}>
        {guilds.map((guild, i) => (
          <motion.div
            key={guild.id}
            className="glass-card"
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.05 }}
            style={{
              padding: '1.25rem',
              display: 'flex',
              alignItems: 'center',
              gap: '1rem',
              cursor: 'pointer',
            }}
          >
            {guild.icon ? (
              <img
                src={guild.icon}
                alt={guild.name}
                style={{
                  width: 48,
                  height: 48,
                  borderRadius: 'var(--radius-md)',
                  objectFit: 'cover',
                }}
              />
            ) : (
              <div style={{
                width: 48,
                height: 48,
                borderRadius: 'var(--radius-md)',
                background: 'linear-gradient(135deg, var(--color-accent-blue), var(--color-accent-violet))',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '1.25rem',
                fontWeight: 700,
              }}>
                {guild.name.charAt(0).toUpperCase()}
              </div>
            )}
            <div style={{ flex: 1, minWidth: 0 }}>
              <p style={{
                fontWeight: 600,
                fontSize: '0.9375rem',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}>
                {guild.name}
              </p>
              <p style={{ color: 'var(--color-text-muted)', fontSize: '0.75rem', marginTop: '0.125rem' }}>
                👥 {(guild.member_count ?? 0).toLocaleString()} {t('guilds.members')}
              </p>
            </div>
            <span style={{ color: 'var(--color-text-muted)', fontSize: '0.75rem' }}>
              {guild.id}
            </span>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
