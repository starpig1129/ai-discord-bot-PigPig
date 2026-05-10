import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import api from '../../../lib/api';

interface UserStatsData {
  total_messages: number;
  total_commands: number;
  guild_breakdown: { guild_id: string; guild_name?: string; messages: number }[];
}

export default function UserStatsPage() {
  const { t } = useTranslation();
  const [period, setPeriod] = useState('30d');
  const [data, setData] = useState<UserStatsData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.get(`/api/user/stats?period=${period}`)
      .then(({ data }) => setData(data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [period]);

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
        <h2 style={{ fontSize: '1.125rem', fontWeight: 600 }}>📊 {t('user.stats')}</h2>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          {['7d', '30d', '90d'].map(p => (
            <button key={p} onClick={() => setPeriod(p)} style={{
              padding: '0.375rem 0.875rem', borderRadius: 'var(--radius-sm)', border: '1px solid',
              borderColor: period === p ? 'var(--color-accent-blue)' : 'var(--color-border)',
              background: period === p ? 'rgba(59,130,246,0.15)' : 'transparent',
              color: period === p ? 'var(--color-accent-blue)' : 'var(--color-text-secondary)',
              cursor: 'pointer', fontSize: '0.8125rem',
            }}>{p}</button>
          ))}
        </div>
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--color-text-muted)' }}>{t('common.loading')}</div>
      ) : data ? (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '1rem', marginBottom: '1.5rem' }}>
            {[
              { label: t('stats.totalMessages'), value: data.total_messages.toLocaleString(), icon: '💬' },
              { label: 'Commands', value: data.total_commands.toLocaleString(), icon: '⌨️' },
              { label: t('guild.activeUsers').replace('Active', 'Active on'), value: data.guild_breakdown.length + ' servers', icon: '🏠' },
            ].map((card, i) => (
              <motion.div key={card.label} className="glass-card"
                initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.07 }} style={{ padding: '1.25rem' }}>
                <div style={{ color: 'var(--color-text-muted)', fontSize: '0.75rem', marginBottom: '0.375rem' }}>{card.icon} {card.label}</div>
                <div style={{ fontSize: '1.5rem', fontWeight: 700 }}>{card.value}</div>
              </motion.div>
            ))}
          </div>

          <motion.div className="glass-card" initial={{ opacity: 0 }} animate={{ opacity: 1 }} style={{ padding: '1.5rem' }}>
            <h3 style={{ fontSize: '0.9375rem', fontWeight: 600, marginBottom: '1rem' }}>{t('user.guildBreakdown')}</h3>
            {data.guild_breakdown.length === 0 ? (
              <p style={{ color: 'var(--color-text-muted)', fontSize: '0.875rem' }}>{t('user.noActivity')}</p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                {data.guild_breakdown.map(entry => (
                  <div key={entry.guild_id} style={{ display: 'flex', justifyContent: 'space-between', padding: '0.5rem 0', borderBottom: '1px solid var(--color-border)' }}>
                    <span style={{ fontSize: '0.875rem' }}>{entry.guild_name || entry.guild_id}</span>
                    <span style={{ fontWeight: 600, fontSize: '0.875rem' }}>{entry.messages.toLocaleString()}</span>
                  </div>
                ))}
              </div>
            )}
          </motion.div>
        </>
      ) : null}
    </div>
  );
}
