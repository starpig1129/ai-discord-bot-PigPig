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

  const [editing, setEditing] = useState<'procedural' | 'background' | null>(null);
  const [editValue, setEditValue] = useState('');
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState('');

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

  const handleSave = async () => {
    if (!editing) return;
    setSaving(true);
    try {
      const body = editing === 'procedural'
        ? { procedural_memory: editValue }
        : { user_background: editValue };
      await api.put('/api/user/memory/procedural', body);
      setSaveMsg(t('user.memorySaved'));
      setTimeout(() => setSaveMsg(''), 4000);
      setEditing(null);
      // Reload data
      const p = await api.get('/api/user/memory/procedural');
      setProcedural(p.data);
    } catch (err: any) {
      setSaveMsg(err?.response?.data?.detail || t('common.error') || 'Save failed');
      setTimeout(() => setSaveMsg(''), 4000);
    } finally {
      setSaving(false);
    }
  };

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
      {saveMsg && (
        <div style={{
          padding: '0.5rem',
          marginBottom: '0.5rem',
          background: 'rgba(59,130,246,0.1)',
          border: '1px solid rgba(59,130,246,0.3)',
          borderRadius: 'var(--radius-sm)',
          color: '#3b82f6',
          fontSize: '0.875rem',
        }}>
          {saveMsg}
        </div>
      )}
      <motion.div className="glass-card" initial={{ opacity: 0 }} animate={{ opacity: 1 }} style={{ padding: '1.5rem' }}>
        {procedural?.procedural_memory || procedural?.user_background ? (
          <>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.875rem' }}>
              <h3 style={{ fontSize: '0.9375rem', fontWeight: 600, margin: 0 }}>
                {t('user.proceduralMemory')}
              </h3>
              <button
                onClick={() => { setEditing('procedural'); setEditValue(procedural?.procedural_memory || ''); }}
                style={{
                  background: 'none',
                  border: '1px solid var(--color-border)',
                  borderRadius: 'var(--radius-sm)',
                  color: 'var(--color-text-muted)',
                  cursor: 'pointer',
                  fontSize: '0.75rem',
                  padding: '0.2rem 0.5rem',
                }}
              >
                ✏️ {t('user.editMemory')}
              </button>
            </div>
            {editing === 'procedural' ? (
              <div>
                <textarea
                  value={editValue}
                  onChange={e => setEditValue(e.target.value)}
                  placeholder={t('user.memoryPlaceholderProcedural')}
                  style={{
                    width: '100%',
                    minHeight: '120px',
                    padding: '0.5rem',
                    background: 'var(--color-bg-secondary)',
                    color: 'var(--color-text)',
                    border: '1px solid var(--color-border)',
                    borderRadius: 'var(--radius-sm)',
                    fontSize: '0.875rem',
                    fontFamily: 'inherit',
                    resize: 'vertical',
                    boxSizing: 'border-box',
                  }}
                />
                <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem' }}>
                  <button
                    onClick={handleSave}
                    disabled={saving}
                    style={{
                      padding: '0.4rem 0.8rem',
                      background: '#3b82f6',
                      color: 'white',
                      border: 'none',
                      borderRadius: 'var(--radius-sm)',
                      cursor: saving ? 'not-allowed' : 'pointer',
                    }}
                  >
                    {saving ? '...' : t('user.saveMemory')}
                  </button>
                  <button
                    onClick={() => setEditing(null)}
                    style={{
                      padding: '0.4rem 0.8rem',
                      background: 'transparent',
                      color: 'var(--color-text-muted)',
                      border: '1px solid var(--color-border)',
                      borderRadius: 'var(--radius-sm)',
                      cursor: 'pointer',
                    }}
                  >
                    {t('user.cancelEdit')}
                  </button>
                </div>
              </div>
            ) : (
              <pre style={{
                fontSize: '0.8125rem',
                lineHeight: 1.7,
                color: 'var(--color-text-secondary)',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
              }}>
                {procedural?.procedural_memory}
              </pre>
            )}
            <hr style={{ borderColor: 'var(--color-border)', margin: '1rem 0' }} />
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
              <h4 style={{ fontSize: '0.875rem', fontWeight: 600, margin: 0, color: 'var(--color-text-muted)' }}>
                {t('user.background')}
              </h4>
              <button
                onClick={() => { setEditing('background'); setEditValue(procedural?.user_background || ''); }}
                style={{
                  background: 'none',
                  border: '1px solid var(--color-border)',
                  borderRadius: 'var(--radius-sm)',
                  color: 'var(--color-text-muted)',
                  cursor: 'pointer',
                  fontSize: '0.75rem',
                  padding: '0.2rem 0.5rem',
                }}
              >
                ✏️ {t('user.editMemory')}
              </button>
            </div>
            {editing === 'background' ? (
              <div>
                <textarea
                  value={editValue}
                  onChange={e => setEditValue(e.target.value)}
                  placeholder={t('user.memoryPlaceholderBackground')}
                  style={{
                    width: '100%',
                    minHeight: '120px',
                    padding: '0.5rem',
                    background: 'var(--color-bg-secondary)',
                    color: 'var(--color-text)',
                    border: '1px solid var(--color-border)',
                    borderRadius: 'var(--radius-sm)',
                    fontSize: '0.875rem',
                    fontFamily: 'inherit',
                    resize: 'vertical',
                    boxSizing: 'border-box',
                  }}
                />
                <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem' }}>
                  <button
                    onClick={handleSave}
                    disabled={saving}
                    style={{
                      padding: '0.4rem 0.8rem',
                      background: '#3b82f6',
                      color: 'white',
                      border: 'none',
                      borderRadius: 'var(--radius-sm)',
                      cursor: saving ? 'not-allowed' : 'pointer',
                    }}
                  >
                    {saving ? '...' : t('user.saveMemory')}
                  </button>
                  <button
                    onClick={() => setEditing(null)}
                    style={{
                      padding: '0.4rem 0.8rem',
                      background: 'transparent',
                      color: 'var(--color-text-muted)',
                      border: '1px solid var(--color-border)',
                      borderRadius: 'var(--radius-sm)',
                      cursor: 'pointer',
                    }}
                  >
                    {t('user.cancelEdit')}
                  </button>
                </div>
              </div>
            ) : (
              <pre style={{ fontSize: '0.8125rem', lineHeight: 1.7, color: 'var(--color-text-secondary)', whiteSpace: 'pre-wrap' }}>
                {procedural?.user_background || '—'}
              </pre>
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
