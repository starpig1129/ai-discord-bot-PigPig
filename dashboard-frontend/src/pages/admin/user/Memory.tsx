import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import api from '../../../lib/api';

interface ProceduralData {
  procedural_memory: string | null;
  user_background: string | null;
  display_names: string[];
}

export default function UserMemory() {
  const { t } = useTranslation();
  const [procedural, setProcedural] = useState<ProceduralData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const fetchData = async () => {
      try {
        const p = await api.get('/api/user/memory/procedural');
        setProcedural(p.data);
      } catch (err: any) {
        setError(err?.response?.data?.detail || err?.message || 'Failed to load memory data');
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  if (loading) return (
    <div style={{ display: 'flex', justifyContent: 'center', padding: '3rem' }}>
      <div className="animate-pulse-glow">🧠</div>
    </div>
  );

  return (
    <div>
      {error && (
        <div style={{
          padding: '0.75rem 1rem',
          marginBottom: '1rem',
          borderRadius: 'var(--radius-md)',
          background: 'rgba(244,63,94,0.1)',
          border: '1px solid rgba(244,63,94,0.3)',
          color: '#f43f5e',
          fontSize: '0.875rem',
        }}>
          ⚠️ {error}
        </div>
      )}
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
    </div>
  );
}
