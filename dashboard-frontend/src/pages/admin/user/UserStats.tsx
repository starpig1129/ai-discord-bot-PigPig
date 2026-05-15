import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import api from '../../../lib/api';

interface UserStatsData {
  total_messages: number;
  total_commands: number;
  accurate_total_messages: number;
  guild_breakdown: { guild_id: string; guild_name?: string; messages: number }[];
  channel_breakdown: { channel_name: string; messages: number; guild_name?: string; channel_id?: string }[];
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
          {['7d', '30d', '90d', 'all'].map(p => (
            <button key={p} onClick={() => setPeriod(p)} style={{
              padding: '0.375rem 0.875rem', borderRadius: 'var(--radius-sm)', border: '1px solid',
              borderColor: period === p ? 'var(--color-accent-blue)' : 'var(--color-border)',
              background: period === p ? 'rgba(59,130,246,0.15)' : 'transparent',
              color: period === p ? 'var(--color-accent-blue)' : 'var(--color-text-secondary)',
              cursor: 'pointer', fontSize: '0.8125rem',
            }}>{p === 'all' ? 'All-time' : p}</button>
          ))}
        </div>
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--color-text-muted)' }}>{t('common.loading')}</div>
      ) : data ? (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '1rem', marginBottom: '1.5rem' }}>
            {[
              { 
                label: period === 'all' ? t('stats.totalMessages') : `Messages (${period})`, 
                value: (data.total_messages ?? 0).toLocaleString(), 
                icon: '💬',
                accurate: period !== 'all' ? data.accurate_total_messages : null
              },
              { label: t('user.commands'), value: (data.total_commands ?? 0).toLocaleString(), icon: '⌨️' },
              { label: t('guild.activeUsers').replace('Active', 'Active on'), value: (data.guild_breakdown?.length || 0) + ' servers', icon: '🏠' },
            ].map((card, i) => (
              <motion.div key={`${card.label}-${i}`} className="glass-card"
                initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.07 }} style={{ padding: '1.25rem' }}>
                <div style={{ color: 'var(--color-text-muted)', fontSize: '0.75rem', marginBottom: '0.375rem' }}>{card.icon} {card.label}</div>
                <div style={{ fontSize: '1.5rem', fontWeight: 700 }}>{card.value}</div>
                {card.accurate != null && (
                  <div style={{ fontSize: '0.7rem', color: 'var(--color-text-muted)', marginTop: '0.25rem' }}>
                    Total: {card.accurate.toLocaleString()}
                  </div>
                )}
              </motion.div>
            ))}
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
            {/* Guild Breakdown */}
            <motion.div className="glass-card" initial={{ opacity: 0 }} animate={{ opacity: 1 }} style={{ padding: '1.5rem' }}>
              <h3 style={{ fontSize: '0.9375rem', fontWeight: 600, marginBottom: '1rem' }}>{t('user.guildBreakdown')}</h3>
              {!data.guild_breakdown || data.guild_breakdown.length === 0 ? (
                <p style={{ color: 'var(--color-text-muted)', fontSize: '0.875rem' }}>{t('user.noActivity')}</p>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', maxHeight: '400px', overflowY: 'auto', paddingRight: '0.5rem' }}>
                  {data.guild_breakdown.map((entry, idx) => (
                    <div key={`${entry.guild_id}-${idx}`} style={{ display: 'flex', justifyContent: 'space-between', padding: '0.5rem 0', borderBottom: '1px solid var(--color-border)' }}>
                      <span style={{ fontSize: '0.875rem' }}>{entry.guild_name || entry.guild_id}</span>
                      <span style={{ fontWeight: 600, fontSize: '0.875rem' }}>{(entry.messages ?? 0).toLocaleString()}</span>
                    </div>
                  ))}
                </div>
              )}
            </motion.div>

            {/* Channel Breakdown */}
            <motion.div className="glass-card" initial={{ opacity: 0 }} animate={{ opacity: 1 }} style={{ padding: '1.5rem' }}>
              <h3 style={{ fontSize: '0.9375rem', fontWeight: 600, marginBottom: '1rem' }}>📊 {t('user.channelStats')}</h3>
              {!data.channel_breakdown || data.channel_breakdown.length === 0 ? (
                <p style={{ color: 'var(--color-text-muted)', fontSize: '0.875rem' }}>{t('user.noChannelData')}</p>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', maxHeight: '400px', overflowY: 'auto', paddingRight: '0.5rem' }}>
                  {data.channel_breakdown.map((entry) => (
                    <div key={`${entry.channel_id ?? entry.guild_name}-${entry.channel_name}`} style={{ display: 'flex', justifyContent: 'space-between', padding: '0.5rem 0', borderBottom: '1px solid var(--color-border)' }}>
                      <div style={{ display: 'flex', flexDirection: 'column' }}>
                        <span style={{ fontSize: '0.875rem', fontWeight: 500 }}>#{entry.channel_name}</span>
                        <span style={{ fontSize: '0.7rem', color: 'var(--color-text-muted)' }}>{entry.guild_name}</span>
                      </div>
                      <span style={{ fontWeight: 600, fontSize: '0.875rem' }}>{(entry.messages ?? 0).toLocaleString()}</span>
                    </div>
                  ))}
                </div>
              )}
            </motion.div>
          </div>
        </>
      ) : null}
    </div>
  );
}
