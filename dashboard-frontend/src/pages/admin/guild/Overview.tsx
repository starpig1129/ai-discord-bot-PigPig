import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import { useOutletContext } from 'react-router-dom';
import api from '../../../lib/api';

interface OverviewData {
  name: string;
  member_count: number;
  channel_count: number;
  bot_online: boolean;
  mode: string;
  system_prompt_enabled: boolean;
}

interface GuildContext {
  guildId: string;
}

export default function GuildOverview() {
  const { guildId } = useOutletContext<GuildContext>();
  const { t } = useTranslation();
  const [data, setData] = useState<OverviewData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.get(`/api/guild/${guildId}/overview`)
      .then(({ data }) => setData(data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [guildId]);

  if (loading || !data) return (
    <div style={{ display: 'flex', justifyContent: 'center', padding: '3rem' }}>
      <div className="animate-pulse-glow">📊</div>
    </div>
  );

  const cards = [
    { label: t('guild.members'), value: (data.member_count ?? 0).toLocaleString(), icon: '👥' },
    { label: t('guild.channels'), value: data.channel_count, icon: '📋' },
    { label: t('guild.botStatus'), value: data.bot_online ? t('guild.online') : t('guild.offline'), icon: data.bot_online ? '🟢' : '🔴' },
    { label: t('guild.mode'), value: data.mode, icon: '⚙️' },
    { label: t('guild.promptEnabled'), value: data.system_prompt_enabled ? t('common.yes') : t('common.no'), icon: '✍️' },
  ];

  return (
    <div>
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
        gap: '1rem',
      }}>
        {cards.map((card, i) => (
          <motion.div
            key={card.label}
            className="glass-card"
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.07 }}
            style={{ padding: '1.25rem' }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
              <span style={{ color: 'var(--color-text-muted)', fontSize: '0.8125rem' }}>{card.label}</span>
              <span style={{ fontSize: '1.1rem' }}>{card.icon}</span>
            </div>
            <div style={{ fontSize: '1.5rem', fontWeight: 700 }}>{card.value}</div>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
