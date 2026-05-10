import { useState } from 'react';
import { motion } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import api from '../../../lib/api';

export default function DeleteData() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [confirmed, setConfirmed] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleDelete = async () => {
    if (!confirmed) return;
    setDeleting(true);
    setError(null);
    try {
      await api.delete('/api/user/memory', { data: { confirm: true } });
      setDone(true);
      // Clear auth and redirect after 3s
      setTimeout(() => {
        localStorage.removeItem('access_token');
        navigate('/login');
      }, 3000);
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      setError(e?.response?.data?.detail || t('user.deleteFailed'));
    } finally {
      setDeleting(false);
    }
  };

  if (done) return (
    <motion.div
      className="glass-card"
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      style={{ padding: '2.5rem', maxWidth: 500, textAlign: 'center' }}
    >
      <div style={{ fontSize: '3rem', marginBottom: '1rem' }}>✅</div>
      <h2 style={{ fontSize: '1.25rem', fontWeight: 700, marginBottom: '0.5rem' }}>
        {t('user.deleteSuccess')}
      </h2>
      <p style={{ color: 'var(--color-text-muted)', fontSize: '0.875rem' }}>
        {t('user.redirecting')}
      </p>
    </motion.div>
  );

  return (
    <div>
      <motion.div
        className="glass-card"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        style={{ padding: '2rem', maxWidth: 560, border: '1px solid rgba(244,63,94,0.25)' }}
      >
        {/* Warning header */}
        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'flex-start', marginBottom: '1.5rem' }}>
          <span style={{ fontSize: '2rem' }}>⚠️</span>
          <div>
            <h2 style={{ fontSize: '1.125rem', fontWeight: 700, color: 'var(--color-accent-rose)' }}>
              {t('user.deleteTitle')}
            </h2>
            <p style={{ color: 'var(--color-text-secondary)', fontSize: '0.875rem', marginTop: '0.375rem', lineHeight: 1.6 }}>
              {t('user.deleteDescription')}
            </p>
          </div>
        </div>

        {/* What will be deleted */}
        <div style={{
          padding: '1rem',
          borderRadius: 'var(--radius-md)',
          background: 'rgba(244,63,94,0.05)',
          border: '1px solid rgba(244,63,94,0.15)',
          marginBottom: '1.5rem',
        }}>
          <p style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--color-text-muted)', marginBottom: '0.5rem' }}>
            {t('user.deleteWillRemove')}:
          </p>
          {[
            t('user.deleteItem1'),
            t('user.deleteItem2'),
            t('user.deleteItem3'),
          ].map((item) => (
            <div key={item} style={{ display: 'flex', gap: '0.5rem', fontSize: '0.8125rem', color: 'var(--color-accent-rose)', padding: '0.2rem 0' }}>
              <span>•</span>
              <span>{item}</span>
            </div>
          ))}
        </div>

        {/* Confirmation checkbox */}
        <label style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', cursor: 'pointer', marginBottom: '1.25rem' }}>
          <input
            type="checkbox"
            checked={confirmed}
            onChange={e => setConfirmed(e.target.checked)}
            style={{ width: 16, height: 16, accentColor: 'var(--color-accent-rose)' }}
          />
          <span style={{ fontSize: '0.875rem', color: 'var(--color-text-secondary)' }}>
            {t('user.deleteConfirmCheck')}
          </span>
        </label>

        {error && (
          <p style={{ color: 'var(--color-accent-rose)', fontSize: '0.8125rem', marginBottom: '0.75rem' }}>
            ❌ {error}
          </p>
        )}

        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <button
            onClick={() => navigate(-1)}
            style={{
              flex: 1, padding: '0.75rem',
              borderRadius: 'var(--radius-md)', border: '1px solid var(--color-border)',
              background: 'transparent', color: 'var(--color-text-secondary)',
              cursor: 'pointer', fontWeight: 500,
            }}
          >
            {t('common.cancel')}
          </button>
          <button
            onClick={handleDelete}
            disabled={!confirmed || deleting}
            style={{
              flex: 1, padding: '0.75rem',
              borderRadius: 'var(--radius-md)', border: '1px solid var(--color-accent-rose)',
              background: confirmed ? 'rgba(244,63,94,0.15)' : 'transparent',
              color: confirmed ? 'var(--color-accent-rose)' : 'var(--color-text-muted)',
              cursor: confirmed ? 'pointer' : 'not-allowed',
              fontWeight: 600, opacity: deleting ? 0.7 : 1,
            }}
          >
            {deleting ? t('common.loading') : `🗑️ ${t('user.confirmDelete')}`}
          </button>
        </div>
      </motion.div>
    </div>
  );
}
