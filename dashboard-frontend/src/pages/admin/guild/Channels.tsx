import { useEffect, useState, useCallback } from 'react';
import { motion } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import { useOutletContext } from 'react-router-dom';
import api from '../../../lib/api';

interface Channel {
  id: string;
  name: string;
  category: string | null;
  in_whitelist: boolean;
  in_blacklist: boolean;
  auto_response: boolean;
  channel_mode: string;
  guild_mode: string;
}

interface ChannelData {
  guild_mode: string;
  channels: Channel[];
}

interface GuildContext {
  guildId: string;
}

const MODES = ['unrestricted', 'whitelist', 'blacklist'];

export default function GuildChannels() {
  const { guildId } = useOutletContext<GuildContext>();
  const { t } = useTranslation();
  const [data, setData] = useState<ChannelData | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<string | null>(null);

  const fetchChannels = useCallback(() => {
    api.get(`/api/guild/${guildId}/channels`)
      .then(({ data }) => setData(data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [guildId]);

  useEffect(() => {
    fetchChannels();
  }, [fetchChannels]);

  const updateGuildMode = async (mode: string) => {
    setSaving('mode');
    try {
      await api.put(`/api/guild/${guildId}/channels/__guild__`, { guild_mode: mode });
      setData(prev => prev ? { ...prev, guild_mode: mode } : prev);
    } finally { setSaving(null); }
  };

  const toggleChannel = async (
    ch: Channel,
    field: 'in_whitelist' | 'in_blacklist' | 'auto_response',
  ) => {
    setSaving(ch.id + field);
    try {
      await api.put(`/api/guild/${guildId}/channels/${ch.id}`, {
        [field]: !ch[field],
      });
      fetchChannels();
    } finally { setSaving(null); }
  };

  if (loading || !data) return (
    <div style={{ display: 'flex', justifyContent: 'center', padding: '3rem' }}>
      <div className="animate-pulse-glow">📋</div>
    </div>
  );

  const grouped = data.channels.reduce<Record<string, Channel[]>>((acc, ch) => {
    const cat = ch.category || t('guild.noCategory');
    if (!acc[cat]) acc[cat] = [];
    acc[cat].push(ch);
    return acc;
  }, {});

  return (
    <div>
      {/* Guild-level mode selector */}
      <div className="glass-card" style={{ padding: '1.25rem', marginBottom: '1.5rem' }}>
        <h2 style={{ fontSize: '0.9375rem', fontWeight: 600, marginBottom: '0.875rem' }}>
          {t('guild.globalMode')}
        </h2>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          {MODES.map((mode) => (
            <button
              key={mode}
              onClick={() => updateGuildMode(mode)}
              disabled={!!saving}
              style={{
                padding: '0.5rem 1.25rem',
                borderRadius: 'var(--radius-sm)',
                border: '1px solid',
                borderColor: data.guild_mode === mode ? 'var(--color-accent-blue)' : 'var(--color-border)',
                background: data.guild_mode === mode ? 'rgba(59,130,246,0.15)' : 'transparent',
                color: data.guild_mode === mode ? 'var(--color-accent-blue)' : 'var(--color-text-secondary)',
                cursor: 'pointer', fontSize: '0.875rem', fontWeight: 500,
                opacity: saving === 'mode' ? 0.7 : 1,
              }}
            >
              {t(`guild.mode_${mode}`)}
            </button>
          ))}
        </div>
      </div>

      {/* Per-channel list */}
      {Object.entries(grouped).map(([category, channels]) => (
        <div key={category} style={{ marginBottom: '1.5rem' }}>
          <h3 style={{
            fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase',
            letterSpacing: '0.08em', color: 'var(--color-text-muted)',
            marginBottom: '0.625rem',
          }}>
            {category}
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.375rem' }}>
            {channels.map((ch) => (
              <motion.div
                key={ch.id}
                className="glass-card"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                style={{
                  padding: '0.875rem 1.125rem',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.75rem',
                  flexWrap: 'wrap',
                }}
              >
                <span style={{ flex: 1, fontWeight: 500, fontSize: '0.875rem' }}>
                  # {ch.name}
                </span>

                <label style={{ display: 'flex', alignItems: 'center', gap: '0.375rem', cursor: 'pointer', fontSize: '0.75rem' }}>
                  <input
                    type="checkbox"
                    checked={ch.in_whitelist}
                    disabled={!!saving}
                    onChange={() => toggleChannel(ch, 'in_whitelist')}
                  />
                  {t('guild.whitelist')}
                </label>

                <label style={{ display: 'flex', alignItems: 'center', gap: '0.375rem', cursor: 'pointer', fontSize: '0.75rem' }}>
                  <input
                    type="checkbox"
                    checked={ch.in_blacklist}
                    disabled={!!saving}
                    onChange={() => toggleChannel(ch, 'in_blacklist')}
                  />
                  {t('guild.blacklist')}
                </label>

                <label style={{ display: 'flex', alignItems: 'center', gap: '0.375rem', cursor: 'pointer', fontSize: '0.75rem' }}>
                  <input
                    type="checkbox"
                    checked={ch.auto_response}
                    disabled={!!saving}
                    onChange={() => toggleChannel(ch, 'auto_response')}
                  />
                  {t('guild.autoResponse')}
                </label>
              </motion.div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
