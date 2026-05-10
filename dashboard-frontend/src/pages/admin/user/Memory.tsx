import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import api from '../../../lib/api';

interface ProceduralData {
  procedural_memory: string | null;
  user_background: string | null;
  display_names: string[];
}

interface EpisodicRecord {
  guild_id: string;
  guild_name?: string;
  total_messages: number;
  streak_days: number;
  last_active_at: string | null;
  channel_memories: Record<string, string>;
}

export default function UserMemory() {
  const { t } = useTranslation();
  const [procedural, setProcedural] = useState<ProceduralData | null>(null);
  const [episodic, setEpisodic] = useState<EpisodicRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<'procedural' | 'episodic'>('procedural');
  const [deletingGuild, setDeletingGuild] = useState<string | null>(null);

  const fetchData = async (isInitial = false) => {
    if (!isInitial) setLoading(true);
    try {
      const [p, e] = await Promise.all([
        api.get('/api/user/memory/procedural'),
        api.get('/api/user/memory/episodic?limit=20'),
      ]);
      setProcedural(p.data);
      setEpisodic(e.data.records);
    } catch {
      // errors handled by layout or silently
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData(true);
  }, []);


  const [expandedGuild, setExpandedGuild] = useState<string | null>(null);

  if (loading) return (
    <div style={{ display: 'flex', justifyContent: 'center', padding: '3rem' }}>
      <div className="animate-pulse-glow">🧠</div>
    </div>
  );

  return (
    <div>
      {/* Tab switcher */}
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.25rem' }}>
        {(['procedural', 'episodic'] as const).map(t_name => (
          <button
            key={t_name}
            onClick={() => setTab(t_name)}
            style={{
              padding: '0.5rem 1.25rem',
              borderRadius: 'var(--radius-sm)', border: '1px solid',
              borderColor: tab === t_name ? 'var(--color-accent-blue)' : 'var(--color-border)',
              background: tab === t_name ? 'rgba(59,130,246,0.15)' : 'transparent',
              color: tab === t_name ? 'var(--color-accent-blue)' : 'var(--color-text-secondary)',
              cursor: 'pointer', fontSize: '0.875rem', fontWeight: 500,
            }}
          >
            {t(`user.${t_name}Memory`)}
          </button>
        ))}
      </div>

      {tab === 'procedural' && (
        <motion.div className="glass-card" initial={{ opacity: 0 }} animate={{ opacity: 1 }} style={{ padding: '1.5rem' }}>
          {procedural?.procedural_memory ? (
            <>
              <h3 style={{ fontSize: '0.9375rem', fontWeight: 600, marginBottom: '0.875rem' }}>
                {t('user.proceduralMemory')}
              </h3>
              <pre style={{
                fontSize: '0.8125rem', lineHeight: 1.7,
                color: 'var(--color-text-secondary)',
                whiteSpace: 'pre-wrap', wordBreak: 'break-word',
              }}>
                {procedural.procedural_memory}
              </pre>
              {procedural.user_background && (
                <>
                  <hr style={{ borderColor: 'var(--color-border)', margin: '1rem 0' }} />
                  <h4 style={{ fontSize: '0.875rem', fontWeight: 600, marginBottom: '0.5rem', color: 'var(--color-text-muted)' }}>
                    {t('user.background')}
                  </h4>
                  <pre style={{ fontSize: '0.8125rem', lineHeight: 1.7, color: 'var(--color-text-secondary)', whiteSpace: 'pre-wrap' }}>
                    {procedural.user_background}
                  </pre>
                </>
              )}
            </>
          ) : (
            <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--color-text-muted)' }}>
              {t('user.noMemory')}
            </div>
          )}
        </motion.div>
      )}

      {tab === 'episodic' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.625rem' }}>
          {episodic.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--color-text-muted)' }}>
              {t('user.noMemory')}
            </div>
          ) : episodic.map((rec) => (
            <motion.div
              key={rec.guild_id}
              className="glass-card"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              style={{ padding: '0', overflow: 'hidden' }}
            >
              <div 
                onClick={() => setExpandedGuild(expandedGuild === rec.guild_id ? null : rec.guild_id)}
                style={{ 
                  padding: '1.25rem', 
                  cursor: 'pointer',
                  display: 'flex', 
                  justifyContent: 'space-between', 
                  alignItems: 'flex-start',
                  background: expandedGuild === rec.guild_id ? 'rgba(255,255,255,0.03)' : 'transparent',
                  transition: 'background 0.2s'
                }}
              >
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                    <p style={{ fontWeight: 600, fontSize: '0.9375rem' }}>{rec.guild_name || rec.guild_id}</p>
                    <button
                      disabled={deletingGuild === rec.guild_id}
                      onClick={async (e) => {
                        e.stopPropagation();
                        if (!confirm(t('admin.deleteUserMemoryDesc', { id: rec.guild_name || rec.guild_id }))) return;
                        setDeletingGuild(rec.guild_id);
                        try {
                          await api.delete(`/api/user/memory/episodic/${rec.guild_id}`);
                          fetchData();
                        } catch {
                          alert(t('admin.deleteFailed'));
                        } finally {
                          setDeletingGuild(null);
                        }
                      }}
                      style={{
                        padding: '0.2rem 0.5rem',
                        fontSize: '0.7rem',
                        borderRadius: 'var(--radius-sm)',
                        border: '1px solid rgba(244,63,94,0.3)',
                        background: 'rgba(244,63,94,0.08)',
                        color: '#f43f5e',
                        cursor: 'pointer',
                        opacity: deletingGuild === rec.guild_id ? 0.5 : 1,
                      }}
                    >
                      {deletingGuild === rec.guild_id ? '...' : '🗑️'}
                    </button>
                  </div>
                  {rec.last_active_at && (
                    <p style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', marginTop: '0.25rem' }}>
                      {t('user.lastActive')}: {new Date(rec.last_active_at).toLocaleDateString()}
                    </p>
                  )}
                </div>

                <div style={{ textAlign: 'right', display: 'flex', alignItems: 'center', gap: '1rem' }}>
                  <div style={{ textAlign: 'right' }}>
                    <p style={{ fontSize: '0.875rem', fontWeight: 600 }}>{rec.total_messages.toLocaleString()} {t('stats.totalMessages').toLowerCase()}</p>
                    <p style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', marginTop: '0.25rem' }}>
                      🔥 {rec.streak_days} {t('user.streakDays')}
                    </p>
                  </div>
                  <div style={{ 
                    transform: expandedGuild === rec.guild_id ? 'rotate(180deg)' : 'rotate(0deg)',
                    transition: 'transform 0.2s',
                    color: 'var(--color-text-muted)'
                  }}>
                    ▼
                  </div>
                </div>
              </div>

              {expandedGuild === rec.guild_id && (
                <motion.div 
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  style={{ 
                    padding: '0 1.25rem 1.25rem 1.25rem',
                    borderTop: '1px solid var(--color-border)',
                    background: 'rgba(0,0,0,0.1)'
                  }}
                >
                  {Object.entries(rec.channel_memories).length > 0 ? (
                    <div style={{ paddingTop: '1rem' }}>
                      {Object.entries(rec.channel_memories).map(([cid, mem]) => (
                        <div key={cid} style={{ marginBottom: '1rem' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.375rem' }}>
                            <div style={{ fontSize: '0.7rem', color: 'var(--color-accent-blue)', fontWeight: 600 }}>#{cid}</div>
                          </div>
                          <div style={{ 
                            fontSize: '0.8125rem', 
                            color: 'var(--color-text-secondary)', 
                            lineHeight: 1.6,
                            background: 'rgba(255,255,255,0.03)', 
                            padding: '0.75rem', 
                            borderRadius: 'var(--radius-sm)',
                            border: '1px solid rgba(255,255,255,0.05)'
                          }}>
                            {mem}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div style={{ padding: '2rem 0', textAlign: 'center', color: 'var(--color-text-muted)', fontSize: '0.875rem' }}>
                      {t('user.noEpisodicMemory')}
                    </div>
                  )}
                </motion.div>
              )}
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}
