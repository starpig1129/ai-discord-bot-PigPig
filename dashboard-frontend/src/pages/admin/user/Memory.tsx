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
}

export default function UserMemory() {
  const { t } = useTranslation();
  const [procedural, setProcedural] = useState<ProceduralData | null>(null);
  const [episodic, setEpisodic] = useState<EpisodicRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<'procedural' | 'episodic'>('procedural');

  useEffect(() => {
    Promise.all([
      api.get('/api/user/memory/procedural'),
      api.get('/api/user/memory/episodic?limit=20'),
    ]).then(([p, e]) => {
      setProcedural(p.data);
      setEpisodic(e.data.records);
    }).catch(() => {})
      .finally(() => setLoading(false));
  }, []);

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
              style={{ padding: '1rem 1.25rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
            >
              <div>
                <p style={{ fontWeight: 600, fontSize: '0.9rem' }}>{rec.guild_name || rec.guild_id}</p>
                {rec.last_active_at && (
                  <p style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', marginTop: '0.125rem' }}>
                    {t('user.lastActive')}: {new Date(rec.last_active_at).toLocaleDateString()}
                  </p>
                )}
              </div>
              <div style={{ textAlign: 'right' }}>
                <p style={{ fontSize: '0.875rem', fontWeight: 600 }}>{rec.total_messages.toLocaleString()} {t('stats.totalMessages').toLowerCase()}</p>
                <p style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', marginTop: '0.125rem' }}>
                  🔥 {rec.streak_days} {t('user.streakDays')}
                </p>
              </div>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}
