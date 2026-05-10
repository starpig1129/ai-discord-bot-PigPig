import { useEffect, useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
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

interface ChannelPrompt {
  enabled: boolean;
  prompt: string;
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

  // Per-channel prompt editing state
  const [expandedPrompt, setExpandedPrompt] = useState<string | null>(null);
  const [channelPrompts, setChannelPrompts] = useState<Record<string, ChannelPrompt>>({});
  const [savingPrompt, setSavingPrompt] = useState<string | null>(null);
  const [promptMsg, setPromptMsg] = useState<Record<string, { text: string; ok: boolean }>>({});

  const fetchChannels = useCallback(() => {
    api.get(`/api/guild/${guildId}/channels`)
      .then(({ data }) => setData(data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [guildId]);

  useEffect(() => { fetchChannels(); }, [fetchChannels]);

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

  const openPromptEditor = async (chId: string) => {
    if (expandedPrompt === chId) { setExpandedPrompt(null); return; }
    setExpandedPrompt(chId);
    if (!channelPrompts[chId]) {
      try {
        const { data } = await api.get(`/api/guild/${guildId}/channels/${chId}/prompt`);
        setChannelPrompts(prev => ({ ...prev, [chId]: { enabled: data.enabled, prompt: data.prompt } }));
      } catch {
        setChannelPrompts(prev => ({ ...prev, [chId]: { enabled: false, prompt: '' } }));
      }
    }
  };

  const saveChannelPrompt = async (chId: string) => {
    const p = channelPrompts[chId];
    if (!p) return;
    setSavingPrompt(chId);
    setPromptMsg(prev => ({ ...prev, [chId]: undefined as unknown as { text: string; ok: boolean } }));
    try {
      await api.put(`/api/guild/${guildId}/channels/${chId}/prompt`, { enabled: p.enabled, prompt: p.prompt });
      setPromptMsg(prev => ({ ...prev, [chId]: { text: t('guild.promptSaved'), ok: true } }));
    } catch {
      setPromptMsg(prev => ({ ...prev, [chId]: { text: t('guild.promptSaveFailed'), ok: false } }));
    } finally {
      setSavingPrompt(null);
      setTimeout(() => setPromptMsg(prev => ({ ...prev, [chId]: undefined as unknown as { text: string; ok: boolean } })), 4000);
    }
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
                borderRadius: 'var(--radius-sm)', border: '1px solid',
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
              <div key={ch.id}>
                <motion.div
                  className="glass-card"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  style={{ padding: '0.875rem 1.125rem' }}
                >
                  {/* Channel row */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
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

                    {/* Toggle prompt editor */}
                    <button
                      onClick={() => openPromptEditor(ch.id)}
                      style={{
                        padding: '0.25rem 0.75rem',
                        borderRadius: 'var(--radius-sm)',
                        border: '1px solid',
                        borderColor: expandedPrompt === ch.id ? 'var(--color-accent-violet)' : 'var(--color-border)',
                        background: expandedPrompt === ch.id ? 'rgba(139,92,246,0.12)' : 'transparent',
                        color: expandedPrompt === ch.id ? 'var(--color-accent-violet)' : 'var(--color-text-muted)',
                        cursor: 'pointer', fontSize: '0.75rem',
                        transition: 'all 0.15s',
                      }}
                    >
                      ✍️ {t('guild.prompt')} {expandedPrompt === ch.id ? '▲' : '▼'}
                    </button>
                  </div>

                  {/* Expandable channel prompt editor */}
                  <AnimatePresence>
                    {expandedPrompt === ch.id && (
                      <motion.div
                        key="prompt-editor"
                        initial={{ opacity: 0, height: 0, marginTop: 0 }}
                        animate={{ opacity: 1, height: 'auto', marginTop: '0.875rem' }}
                        exit={{ opacity: 0, height: 0, marginTop: 0 }}
                        style={{ overflow: 'hidden' }}
                      >
                        <div style={{ borderTop: '1px solid var(--color-border)', paddingTop: '0.875rem' }}>
                          {!channelPrompts[ch.id] ? (
                            <div style={{ color: 'var(--color-text-muted)', fontSize: '0.8125rem' }}>
                              {t('common.loading')}
                            </div>
                          ) : (
                            <>
                              <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.625rem', cursor: 'pointer' }}>
                                <div
                                  onClick={() => setChannelPrompts(prev => ({
                                    ...prev,
                                    [ch.id]: { ...prev[ch.id], enabled: !prev[ch.id]?.enabled },
                                  }))}
                                  style={{
                                    width: 36, height: 20, borderRadius: 10,
                                    background: channelPrompts[ch.id]?.enabled ? 'var(--color-accent-violet)' : 'var(--color-border)',
                                    position: 'relative', cursor: 'pointer', transition: 'background 0.2s', flexShrink: 0,
                                  }}
                                >
                                  <div style={{
                                    position: 'absolute', top: 3,
                                    left: channelPrompts[ch.id]?.enabled ? 18 : 3,
                                    width: 14, height: 14, borderRadius: '50%',
                                    background: 'white', transition: 'left 0.2s',
                                  }} />
                                </div>
                                <span style={{ fontSize: '0.8125rem', color: 'var(--color-text-secondary)' }}>
                                  {t('guild.channelPromptOverride')}
                                </span>
                              </label>

                              <textarea
                                value={channelPrompts[ch.id]?.prompt ?? ''}
                                onChange={e => setChannelPrompts(prev => ({
                                  ...prev,
                                  [ch.id]: { ...prev[ch.id], prompt: e.target.value },
                                }))}
                                placeholder={t('guild.promptPlaceholder')}
                                style={{
                                  width: '100%', minHeight: 120,
                                  padding: '0.625rem 0.75rem',
                                  fontFamily: '"JetBrains Mono", monospace',
                                  fontSize: '0.8125rem', lineHeight: 1.6,
                                  background: 'rgba(15,23,42,0.8)',
                                  color: 'var(--color-text-primary)',
                                  border: '1px solid var(--color-border)',
                                  borderRadius: 'var(--radius-md)',
                                  resize: 'vertical', outline: 'none',
                                  boxSizing: 'border-box',
                                }}
                              />

                              <div style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: '0.75rem', marginTop: '0.5rem' }}>
                                {promptMsg[ch.id] && (
                                  <span style={{ fontSize: '0.75rem', color: promptMsg[ch.id].ok ? 'var(--color-accent-emerald)' : 'var(--color-accent-rose)' }}>
                                    {promptMsg[ch.id].ok ? '✅' : '❌'} {promptMsg[ch.id].text}
                                  </span>
                                )}
                                <button
                                  onClick={() => saveChannelPrompt(ch.id)}
                                  disabled={savingPrompt === ch.id}
                                  style={{
                                    padding: '0.375rem 1rem',
                                    borderRadius: 'var(--radius-sm)',
                                    border: '1px solid var(--color-accent-violet)',
                                    background: 'rgba(139,92,246,0.15)',
                                    color: 'var(--color-accent-violet)',
                                    cursor: 'pointer', fontSize: '0.8125rem', fontWeight: 600,
                                    opacity: savingPrompt === ch.id ? 0.7 : 1,
                                  }}
                                >
                                  {savingPrompt === ch.id ? t('common.saving') : `💾 ${t('common.save')}`}
                                </button>
                              </div>
                            </>
                          )}
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </motion.div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
