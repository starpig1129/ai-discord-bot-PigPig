import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import { useOutletContext } from 'react-router-dom';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import api from '../../../lib/api';

interface GuildStatsData {
  total_messages: number;
  active_users: number;
  llm_calls: number;
  avg_response_ms: number;
  daily_messages: { date: string; count: number }[];
  accurate_total_messages?: number;
}

interface GuildContext {
  guildId: string;
}

export default function GuildStats() {
  const { guildId } = useOutletContext<GuildContext>();
  const { t } = useTranslation();
  const [period, setPeriod] = useState('30d');
  const [data, setData] = useState<GuildStatsData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get(`/api/guild/${guildId}/stats?period=${period}`)
      .then(({ data }) => setData(data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [guildId, period]);

  const cards = data ? [
    { 
      label: period === 'all' ? t('stats.totalMessages') : `${t('stats.totalMessages')} (${period})`, 
      value: (data.total_messages).toLocaleString(), 
      icon: '💬' 
    },
    { label: t('guild.activeUsers'), value: data.active_users.toLocaleString(), icon: '👥' },
    { label: 'LLM Calls', value: data.llm_calls.toLocaleString(), icon: '🤖' },
    { label: t('stats.avgResponse'), value: `${data.avg_response_ms}ms`, icon: '⚡' },
  ] : [];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <h2 style={{ fontSize: '1.125rem', fontWeight: 600 }}>📈 {t('guild.stats')}</h2>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          {['7d', '30d', '90d', 'all'].map(p => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              style={{
                padding: '0.375rem 0.875rem',
                borderRadius: 'var(--radius-sm)', border: '1px solid',
                borderColor: period === p ? 'var(--color-accent-blue)' : 'var(--color-border)',
                background: period === p ? 'rgba(59,130,246,0.15)' : 'transparent',
                color: period === p ? 'var(--color-accent-blue)' : 'var(--color-text-secondary)',
                cursor: 'pointer', fontSize: '0.8125rem',
              }}
            >{p === 'all' ? t('stats.periodAll') : p}</button>
          ))}
        </div>
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--color-text-muted)' }}>
          {t('common.loading')}
        </div>
      ) : (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: '1rem', marginBottom: '1.5rem' }}>
            {cards.map((card, i) => (
              <motion.div
                key={card.label}
                className="glass-card"
                initial={{ opacity: 0, y: 15 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.07 }}
                style={{ padding: '1.25rem' }}
              >
                <div style={{ color: 'var(--color-text-muted)', fontSize: '0.75rem', marginBottom: '0.375rem' }}>
                  {card.icon} {card.label}
                </div>
                <div style={{ fontSize: '1.5rem', fontWeight: 700 }}>{card.value}</div>
              </motion.div>
            ))}
          </div>

          <motion.div
            className="glass-card"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            style={{ padding: '1.5rem' }}
          >
            <h3 style={{ fontSize: '0.9375rem', fontWeight: 600, marginBottom: '1rem' }}>
              {t('stats.messageTrend')}
            </h3>
            <ResponsiveContainer width="100%" height={260}>
              <AreaChart data={data?.daily_messages?.map(d => ({ date: d.date, count: d.count })) || []}>
                <defs>
                  <linearGradient id="guildGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.1)" />
                <XAxis dataKey="date" stroke="#64748b" fontSize={12} tickLine={false} />
                <YAxis stroke="#64748b" fontSize={12} tickLine={false} />
                <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid rgba(148,163,184,0.2)', borderRadius: '0.5rem', color: '#f1f5f9' }} />
                <Area type="monotone" dataKey="count" stroke="#3b82f6" strokeWidth={2} fill="url(#guildGrad)" />
              </AreaChart>
            </ResponsiveContainer>
            <p style={{ fontSize: '0.75rem', color: '#64748b', marginTop: '1rem', textAlign: 'right' }}>
              {t('dashboard.accurateTotal')}: {data?.accurate_total_messages?.toLocaleString() || 0}
            </p>
          </motion.div>
        </>
      )}
    </div>
  );
}
