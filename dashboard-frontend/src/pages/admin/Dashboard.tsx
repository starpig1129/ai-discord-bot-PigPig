import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import api from '../../lib/api';

interface BotStatus {
  status: string;
  latency_ms: number;
  uptime_seconds: number;
  guilds: number;
  users: number;
  memory_mb: number;
  bot_name: string;
  bot_id: string;
}

function formatUptime(seconds: number): string {
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d}d ${h}h ${m}m`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

const cardVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.1, duration: 0.5, ease: [0.16, 1, 0.3, 1] as [number, number, number, number] },
  }),
};

export default function Dashboard() {
  const { t } = useTranslation();
  const [status, setStatus] = useState<BotStatus | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchStatus = () => {
      api.get('/api/admin/status')
        .then(({ data }) => setStatus(data))
        .catch(() => {})
        .finally(() => setLoading(false));
    };
    fetchStatus();
    const interval = setInterval(fetchStatus, 10000);
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '60vh' }}>
        <div className="animate-pulse-glow" style={{ fontSize: '2rem' }}>🐷</div>
      </div>
    );
  }

  const cards = [
    { label: t('dashboard.status'),  value: status?.status || 'offline', icon: '🟢', isStatus: true },
    { label: t('dashboard.latency'), value: `${status?.latency_ms ?? 0}ms`, icon: '⚡' },
    { label: t('dashboard.uptime'),  value: formatUptime(status?.uptime_seconds ?? 0), icon: '⏱️' },
    { label: t('dashboard.guilds'),  value: status?.guilds ?? 0, icon: '🏠' },
    { label: t('dashboard.users'),   value: (status?.users ?? 0).toLocaleString(), icon: '👥' },
    { label: t('dashboard.memory'),  value: `${status?.memory_mb ?? 0} MB`, icon: '💾' },
  ];

  return (
    <div>
      {/* Header */}
      <div style={{ marginBottom: '2rem' }}>
        <h1 style={{ fontSize: '1.75rem', fontWeight: 700 }}>Welcome back 👋</h1>
        <p style={{ color: 'var(--color-text-secondary)', marginTop: '0.25rem' }}>
          {status?.bot_name || 'PigPig'} · {t('dashboard.subtitle')}
        </p>
      </div>

      {/* Status Cards Grid */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
        gap: '1.25rem',
        marginBottom: '2rem',
      }}>
        {cards.map((card, i) => (
          <motion.div
            key={card.label}
            className="glass-card"
            custom={i}
            initial="hidden"
            animate="visible"
            variants={cardVariants}
            style={{ padding: '1.5rem' }}
          >
            <div style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginBottom: '0.75rem',
            }}>
              <span style={{ color: 'var(--color-text-muted)', fontSize: '0.8125rem' }}>
                {card.label}
              </span>
              <span style={{ fontSize: '1.25rem' }}>{card.icon}</span>
            </div>
            <div style={{
              fontSize: '1.75rem',
              fontWeight: 700,
              color: card.isStatus
                ? (status?.status === 'online' ? 'var(--color-accent-emerald)' : 'var(--color-accent-rose)')
                : 'var(--color-text-primary)',
            }}>
              {card.isStatus ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <span
                    className={`status-dot ${status?.status === 'online' ? 'online' : 'offline'}`}
                  />
                  {String(card.value).charAt(0).toUpperCase() + String(card.value).slice(1)}
                </div>
              ) : card.value}
            </div>
          </motion.div>
        ))}
      </div>

      {/* Quick Actions */}
      <motion.div
        className="glass-card"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.6, duration: 0.5 }}
        style={{ padding: '1.5rem' }}
      >
        <h2 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '1rem' }}>Quick Actions</h2>
        <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
          <a href="/admin/config" className="btn-gradient" style={{ textDecoration: 'none' }}>
            ⚙️ Edit Config
          </a>
          <a href="/admin/logs" className="btn-gradient" style={{ textDecoration: 'none' }}>
            📝 View Logs
          </a>
          <a href="/admin/stats" className="btn-gradient" style={{ textDecoration: 'none' }}>
            📈 View Stats
          </a>
        </div>
      </motion.div>
    </div>
  );
}
