import { useEffect, useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import { useOutletContext } from 'react-router-dom';
import api from '../../../lib/api';
import ModuleCard from '../../../components/prompt/ModuleCard';
import type { PromptModule } from '../../../components/prompt/ModuleCard';
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

// ─── Toggle switch ────────────────────────────────────────────────────

function Toggle({
  checked,
  onChange,
  disabled,
  color = 'var(--color-accent-blue)',
}: {
  checked: boolean;
  onChange: () => void;
  disabled?: boolean;
  color?: string;
}) {
  return (
    <div
      onClick={disabled ? undefined : onChange}
      style={{
        width: 40, height: 22, borderRadius: 11, flexShrink: 0,
        background: checked ? color : 'var(--color-border)',
        position: 'relative',
        cursor: disabled ? 'not-allowed' : 'pointer',
        transition: 'background 0.18s',
        opacity: disabled ? 0.5 : 1,
      }}
    >
      <motion.div
        animate={{ x: checked ? 20 : 2 }}
        transition={{ type: 'spring', stiffness: 500, damping: 30 }}
        style={{
          position: 'absolute', top: 3,
          width: 16, height: 16, borderRadius: '50%',
          background: 'white',
          boxShadow: '0 1px 3px rgba(0,0,0,0.3)',
        }}
      />
    </div>
  );
}

// ─── Right detail panel ───────────────────────────────────────────────

interface MemoryFragment {
  id: string;
  content: string;
  timestamp?: number;
}

interface DetailPanelProps {
  channel: Channel;
  guildId: string;
  onChannelUpdate: (updated: Partial<Channel>) => void;
}

function DetailPanel({ channel, guildId, onChannelUpdate }: DetailPanelProps) {
  const { t } = useTranslation();
  const [savingField, setSavingField] = useState<string | null>(null);

  // Prompt state
  const [promptLoaded, setPromptLoaded] = useState(false);
  const [promptEnabled, setPromptEnabled] = useState(false);
  const [modules, setModules] = useState<PromptModule[]>([]);
  const [moduleOrder, setModuleOrder] = useState<string[]>([]);

  // Memory state
  const [memory, setMemory] = useState<string | null>(null);
  const [knowledge, setKnowledge] = useState<string | null>(null);
  const [fragments, setFragments] = useState<MemoryFragment[]>([]);
  const [memoryLoading, setMemoryLoading] = useState(false);

  // Load channel prompt whenever channel changes
  useEffect(() => {
    setPromptLoaded(false);
    setMemoryLoading(true);
    
    // Fetch prompt
    api.get(`/api/guild/${guildId}/channels/${channel.id}/prompt/modules`)
      .then(({ data }) => {
        setPromptEnabled(data.enabled ?? false);
        setModules(data.modules ?? []);
        setModuleOrder(data.module_order ?? []);
        setPromptLoaded(true);
      })
      .catch(err => console.error('Failed to fetch prompt modules', err));

    // Fetch memory (summary + knowledge + fragments)
    api.get(`/api/guild/${guildId}/channels/${channel.id}/memory`)
      .then(({ data }) => {
        setMemory(data.summary);
        setKnowledge(data.knowledge);
        setFragments(data.fragments || []);
        setMemoryLoading(false);
      })
      .catch(err => {
        console.error('Failed to fetch channel memory', err);
        setMemoryLoading(false);
      });
  }, [channel.id, guildId]);

  const toggleField = async (field: 'in_whitelist' | 'in_blacklist' | 'auto_response') => {
    setSavingField(field);
    const next = !channel[field];
    try {
      await api.put(`/api/guild/${guildId}/channels/${channel.id}`, { [field]: next });
      onChannelUpdate({ [field]: next });
    } finally {
      setSavingField(null);
    }
  };

  const togglePromptEnabled = async () => {
    const next = !promptEnabled;
    setPromptEnabled(next);
    try {
      await api.put(`/api/guild/${guildId}/channels/${channel.id}/prompt`, { enabled: next });
    } catch {
      // Revert on error
      setPromptEnabled(!next);
    }
  };

  return (
    <motion.div
      key={channel.id}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.15 }}
      style={{
        display: 'flex', flexDirection: 'column', gap: '1rem',
        height: '100%', overflow: 'auto',
      }}
    >
      {/* Channel header */}
      <div style={{
        padding: '1.125rem 1.25rem',
        background: 'rgba(139,92,246,0.06)',
        border: '1px solid rgba(139,92,246,0.2)',
        borderRadius: 'var(--radius-lg)',
      }}>
        <h3 style={{ fontSize: '1.0625rem', fontWeight: 700, marginBottom: '0.2rem' }}>
          <span style={{ color: 'var(--color-text-muted)', marginRight: '0.25rem' }}>#</span>
          {channel.name}
        </h3>
        <p style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
          {channel.category ?? t('guild.noCategory')} · ID {channel.id}
        </p>
      </div>

      {/* Channel settings */}
      <div className="glass-card" style={{ padding: '1.25rem' }}>
        <h4 style={{
          fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase',
          letterSpacing: '0.08em', color: 'var(--color-text-muted)', marginBottom: '1rem',
        }}>
          {t('guild.channelSettings')}
        </h4>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.875rem' }}>
          {/* Whitelist */}
          <motion.div 
            onClick={() => { if (savingField !== 'in_whitelist') toggleField('in_whitelist'); }}
            whileHover={{ backgroundColor: 'rgba(255, 255, 255, 0.04)' }}
            style={{ 
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              cursor: savingField === 'in_whitelist' ? 'default' : 'pointer',
              padding: '0.625rem 0.75rem', margin: '-0.625rem -0.75rem', borderRadius: 'var(--radius-md)',
              transition: 'background 0.2s'
            }}
          >
            <div>
              <p style={{ fontSize: '0.875rem', fontWeight: 500 }}>{t('guild.whitelist')}</p>
              <p style={{ fontSize: '0.72rem', color: 'var(--color-text-muted)', marginTop: '0.1rem' }}>
                {t('guild.whitelistNote')}
              </p>
            </div>
            <Toggle
              checked={channel.in_whitelist}
              disabled={savingField === 'in_whitelist'}
              onChange={() => toggleField('in_whitelist')}
              color="var(--color-accent-emerald)"
            />
          </motion.div>

          <div style={{ height: 1, background: 'var(--color-border)' }} />

          {/* Blacklist */}
          <motion.div 
            onClick={() => { if (savingField !== 'in_blacklist') toggleField('in_blacklist'); }}
            whileHover={{ backgroundColor: 'rgba(255, 255, 255, 0.04)' }}
            style={{ 
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              cursor: savingField === 'in_blacklist' ? 'default' : 'pointer',
              padding: '0.625rem 0.75rem', margin: '-0.625rem -0.75rem', borderRadius: 'var(--radius-md)',
              transition: 'background 0.2s'
            }}
          >
            <div>
              <p style={{ fontSize: '0.875rem', fontWeight: 500 }}>{t('guild.blacklist')}</p>
              <p style={{ fontSize: '0.72rem', color: 'var(--color-text-muted)', marginTop: '0.1rem' }}>
                {t('guild.blacklistNote')}
              </p>
            </div>
            <Toggle
              checked={channel.in_blacklist}
              disabled={savingField === 'in_blacklist'}
              onChange={() => toggleField('in_blacklist')}
              color="var(--color-accent-rose)"
            />
          </motion.div>

          <div style={{ height: 1, background: 'var(--color-border)' }} />

          {/* Auto response */}
          <motion.div 
            onClick={() => { if (savingField !== 'auto_response') toggleField('auto_response'); }}
            whileHover={{ backgroundColor: 'rgba(255, 255, 255, 0.04)' }}
            style={{ 
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              cursor: savingField === 'auto_response' ? 'default' : 'pointer',
              padding: '0.625rem 0.75rem', margin: '-0.625rem -0.75rem', borderRadius: 'var(--radius-md)',
              transition: 'background 0.2s'
            }}
          >
            <div>
              <p style={{ fontSize: '0.875rem', fontWeight: 500 }}>{t('guild.autoResponse')}</p>
              <p style={{ fontSize: '0.72rem', color: 'var(--color-text-muted)', marginTop: '0.1rem' }}>
                {t('guild.autoResponseNote')}
              </p>
            </div>
            <Toggle
              checked={channel.auto_response}
              disabled={savingField === 'auto_response'}
              onChange={() => toggleField('auto_response')}
              />
          </motion.div>
        </div>
      </div>

      {/* Episodic Memory Section */}
      <div className="glass-card" style={{ padding: '1.25rem' }}>
        <h4 style={{
          fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase',
          letterSpacing: '0.08em', color: 'var(--color-text-muted)', marginBottom: '1rem',
          display: 'flex', alignItems: 'center', gap: '0.5rem'
        }}>
          <span>🧠</span>
          {t('user.episodicMemory')}
        </h4>
        
        {memoryLoading ? (
          <div style={{ padding: '1rem', color: 'var(--color-text-muted)', fontSize: '0.875rem' }}>
            {t('common.loading')}
          </div>
        ) : memory ? (
          <div style={{
            padding: '1rem',
            background: 'rgba(255, 255, 255, 0.03)',
            borderRadius: 'var(--radius-md)',
            border: '1px solid var(--color-border)',
            fontSize: '0.875rem',
            lineHeight: 1.6,
            color: 'var(--color-text-secondary)',
            whiteSpace: 'pre-wrap'
          }}>
            {memory}
          </div>
        ) : (
          <div style={{
            padding: '1.5rem',
            textAlign: 'center',
            color: 'var(--color-text-muted)',
            fontSize: '0.875rem',
            background: 'rgba(255, 255, 255, 0.01)',
            borderRadius: 'var(--radius-md)',
            border: '1px dashed var(--color-border)',
          }}>
            {t('user.noEpisodicMemory')}
          </div>
        )}
      </div>

      {/* Consolidated Knowledge Section */}
      <div className="glass-card" style={{ padding: '1.25rem' }}>
        <h4 style={{
          fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase',
          letterSpacing: '0.08em', color: 'var(--color-text-muted)', marginBottom: '1rem',
          display: 'flex', alignItems: 'center', gap: '0.5rem'
        }}>
          <span>📚</span>
          {t('user.consolidatedKnowledge')}
        </h4>
        
        {memoryLoading ? (
          <div style={{ padding: '1rem', color: 'var(--color-text-muted)', fontSize: '0.875rem' }}>
            {t('common.loading')}
          </div>
        ) : knowledge ? (
          <div style={{
            padding: '1rem',
            background: 'rgba(255, 255, 255, 0.03)',
            borderRadius: 'var(--radius-md)',
            border: '1px solid var(--color-border)',
            fontSize: '0.875rem',
            lineHeight: 1.6,
            color: 'var(--color-text-secondary)',
            whiteSpace: 'pre-wrap'
          }}>
            {knowledge}
          </div>
        ) : (
          <div style={{
            padding: '1.5rem',
            textAlign: 'center',
            color: 'var(--color-text-muted)',
            fontSize: '0.875rem',
            background: 'rgba(255, 255, 255, 0.01)',
            borderRadius: 'var(--radius-md)',
            border: '1px dashed var(--color-border)',
          }}>
            {t('user.noConsolidatedKnowledge')}
          </div>
        )}
      </div>

      {/* Episodic Fragments Section */}
      <div className="glass-card" style={{ padding: '1.25rem' }}>
        <h4 style={{
          fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase',
          letterSpacing: '0.08em', color: 'var(--color-text-muted)', marginBottom: '1rem',
          display: 'flex', alignItems: 'center', gap: '0.5rem'
        }}>
          <span>💬</span>
          {t('user.episodicFragments')}
        </h4>
        
        {memoryLoading ? (
          <div style={{ padding: '1rem', color: 'var(--color-text-muted)', fontSize: '0.875rem' }}>
            {t('common.loading')}
          </div>
        ) : fragments.length > 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {fragments.map((frag: MemoryFragment) => (
              <div key={frag.id} style={{
                padding: '0.875rem',
                background: 'rgba(255, 255, 255, 0.03)',
                borderRadius: 'var(--radius-md)',
                border: '1px solid var(--color-border)',
                fontSize: '0.8125rem',
                lineHeight: 1.5,
                color: 'var(--color-text-secondary)',
              }}>
                <div style={{ whiteSpace: 'pre-wrap' }}>{frag.content}</div>
                {frag.timestamp && (
                  <div style={{
                    marginTop: '0.5rem',
                    fontSize: '0.75rem',
                    color: 'var(--color-text-muted)',
                    textAlign: 'right'
                  }}>
                    {new Date(frag.timestamp * 1000).toLocaleString()}
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div style={{
            padding: '1.5rem',
            textAlign: 'center',
            color: 'var(--color-text-muted)',
            fontSize: '0.875rem',
            background: 'rgba(255, 255, 255, 0.01)',
            borderRadius: 'var(--radius-md)',
            border: '1px dashed var(--color-border)',
          }}>
            {t('user.noEpisodicFragments')}
          </div>
        )}
      </div>

      {/* Prompt editor */}
      <div className="glass-card" style={{ padding: '1.25rem', flex: 1, display: 'flex', flexDirection: 'column', gap: '0.875rem' }}>
        <h4 style={{
          fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase',
          letterSpacing: '0.08em', color: 'var(--color-text-muted)',
        }}>
          {t('guild.channelPromptOverride')}
        </h4>

        {!promptLoaded ? (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--color-text-muted)', fontSize: '0.875rem' }}>
            {t('common.loading')}
          </div>
        ) : (
          <>
            <motion.div 
              onClick={togglePromptEnabled}
              whileHover={{ backgroundColor: 'rgba(255, 255, 255, 0.04)' }}
              style={{ 
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                cursor: 'pointer', padding: '0.625rem 0.75rem', margin: '-0.625rem -0.75rem', borderRadius: 'var(--radius-md)',
                transition: 'background 0.2s'
              }}
            >
              <div>
                <p style={{ fontSize: '0.875rem', fontWeight: 500 }}>{t('guild.channelOverrideEnable')}</p>
                <p style={{ fontSize: '0.72rem', color: 'var(--color-text-muted)', marginTop: '0.1rem' }}>
                  {t('guild.channelOverrideNote')}
                </p>
              </div>
              <Toggle
                checked={promptEnabled}
                onChange={togglePromptEnabled}
                color="var(--color-accent-violet)"
              />
            </motion.div>

            {promptEnabled && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', marginTop: '0.5rem' }}>
                {moduleOrder.map(name => {
                  const mod = modules.find(m => m.name === name);
                  if (!mod || mod.protected) return null;
                  return (
                    <ModuleCard
                      key={mod.name}
                      mod={mod}
                      guildId={guildId}
                      channelId={channel.id}
                      onSaved={(modName, newCustom) => {
                        setModules(prev => prev.map(m => 
                          m.name === modName 
                            ? { ...m, custom_content: newCustom, is_customized: newCustom !== null } 
                            : m
                        ));
                      }}
                    />
                  );
                })}
              </div>
            )}
          </>
        )}
      </div>
    </motion.div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────

export default function GuildChannels() {
  const { guildId } = useOutletContext<GuildContext>();
  const { t } = useTranslation();
  const [data, setData] = useState<ChannelData | null>(null);
  const [loading, setLoading] = useState(true);
  const [savingMode, setSavingMode] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const fetchChannels = useCallback(() => {
    api.get(`/api/guild/${guildId}/channels`)
      .then(({ data }) => {
        setData(data);
        // Auto-select first channel if none selected
        setSelectedId(prev => prev ?? data.channels[0]?.id ?? null);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [guildId]);

  useEffect(() => { fetchChannels(); }, [fetchChannels]);

  const updateGuildMode = async (mode: string) => {
    setSavingMode(true);
    try {
      await api.put(`/api/guild/${guildId}/channels/__guild__`, { guild_mode: mode });
      setData(prev => prev ? { ...prev, guild_mode: mode } : prev);
    } finally { setSavingMode(false); }
  };

  const handleChannelUpdate = useCallback((id: string, updated: Partial<Channel>) => {
    setData(prev => {
      if (!prev) return prev;
      return {
        ...prev,
        channels: prev.channels.map(ch => ch.id === id ? { ...ch, ...updated } : ch),
      };
    });
  }, []);

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

  const selectedChannel = data.channels.find(c => c.id === selectedId) ?? null;

  return (
    <div style={{ display: 'flex', gap: '1rem', alignItems: 'flex-start', height: '100%' }}>

      {/* ── Left: channel selector ──────────────────────────────────── */}
      <div style={{
        width: 240, flexShrink: 0,
        display: 'flex', flexDirection: 'column', gap: '0.875rem',
        position: 'sticky', top: 0,
      }}>
        {/* Global mode pill selector */}
        <div className="glass-card" style={{ padding: '0.875rem' }}>
          <p style={{
            fontSize: '0.7rem', fontWeight: 700, textTransform: 'uppercase',
            letterSpacing: '0.08em', color: 'var(--color-text-muted)', marginBottom: '0.6rem',
          }}>
            {t('guild.globalMode')}
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
            {MODES.map(mode => (
              <motion.button
                key={mode}
                onClick={() => updateGuildMode(mode)}
                disabled={savingMode}
                whileHover={!savingMode && data.guild_mode !== mode ? { backgroundColor: 'rgba(255, 255, 255, 0.05)' } : undefined}
                style={{
                  padding: '0.4rem 0.75rem', textAlign: 'left',
                  borderRadius: 'var(--radius-sm)', border: '1px solid',
                  borderColor: data.guild_mode === mode ? 'var(--color-accent-blue)' : 'transparent',
                  background: data.guild_mode === mode ? 'rgba(59,130,246,0.12)' : 'transparent',
                  color: data.guild_mode === mode ? 'var(--color-accent-blue)' : 'var(--color-text-secondary)',
                  cursor: savingMode ? 'not-allowed' : 'pointer', fontSize: '0.8125rem', fontWeight: data.guild_mode === mode ? 600 : 400,
                  opacity: savingMode ? 0.7 : 1, transition: 'all 0.15s',
                }}
              >
                {data.guild_mode === mode ? '● ' : '○ '}{t(`guild.mode_${mode}`)}
              </motion.button>
            ))}
          </div>
        </div>

        {/* Channel list */}
        <div style={{
          display: 'flex', flexDirection: 'column', gap: '0.625rem',
          maxHeight: 'calc(100vh - 260px)', overflowY: 'auto',
          paddingRight: '0.25rem',
        }}>
          {Object.entries(grouped).map(([category, channels]) => (
            <div key={category}>
              <p style={{
                fontSize: '0.68rem', fontWeight: 700, textTransform: 'uppercase',
                letterSpacing: '0.09em', color: 'var(--color-text-muted)',
                marginBottom: '0.35rem', paddingLeft: '0.5rem',
              }}>
                {category}
              </p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.2rem' }}>
                {channels.map(ch => {
                  const isActive = ch.id === selectedId;
                  const hasBadge = ch.in_whitelist || ch.in_blacklist || ch.auto_response;
                  return (
                    <button
                      key={ch.id}
                      onClick={() => setSelectedId(ch.id)}
                      style={{
                        display: 'flex', alignItems: 'center', gap: '0.4rem',
                        padding: '0.5rem 0.75rem', width: '100%', textAlign: 'left',
                        borderRadius: 'var(--radius-md)',
                        border: '1px solid',
                        borderColor: isActive ? 'rgba(139,92,246,0.4)' : 'transparent',
                        background: isActive ? 'rgba(139,92,246,0.1)' : 'transparent',
                        color: isActive ? 'var(--color-text-primary)' : 'var(--color-text-secondary)',
                        cursor: 'pointer', fontSize: '0.8125rem',
                        fontWeight: isActive ? 600 : 400,
                        transition: 'all 0.12s',
                      }}
                    >
                      <span style={{ color: isActive ? 'var(--color-accent-violet)' : 'var(--color-text-muted)', fontSize: '0.9rem' }}>#</span>
                      <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {ch.name}
                      </span>
                      {hasBadge && (
                        <span style={{
                          width: 6, height: 6, borderRadius: '50%', flexShrink: 0,
                          background: ch.in_blacklist ? 'var(--color-accent-rose)'
                            : ch.in_whitelist ? 'var(--color-accent-emerald)'
                            : 'var(--color-accent-blue)',
                        }} />
                      )}
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Right: detail panel ─────────────────────────────────────── */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <AnimatePresence mode="wait">
          {selectedChannel ? (
            <DetailPanel
              key={selectedChannel.id}
              channel={selectedChannel}
              guildId={guildId}
              onChannelUpdate={(updated) => handleChannelUpdate(selectedChannel.id, updated)}
            />
          ) : (
            <motion.div
              key="empty"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              style={{
                height: 400, display: 'flex', flexDirection: 'column',
                alignItems: 'center', justifyContent: 'center',
                color: 'var(--color-text-muted)', gap: '0.5rem',
              }}
            >
              <span style={{ fontSize: '2rem' }}>💬</span>
              <p style={{ fontSize: '0.875rem' }}>{t('guild.selectChannel')}</p>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
