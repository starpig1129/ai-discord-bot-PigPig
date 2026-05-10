import { useState } from 'react';
import { motion } from 'framer-motion';
import api from '../../lib/api';

export default function Update() {
  const [checking, setChecking] = useState(false);
  const [updating, setUpdating] = useState(false);
  const [updateInfo, setUpdateInfo] = useState<any>(null);
  const [message, setMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null);

  const checkUpdate = async () => {
    setChecking(true);
    setMessage(null);
    try {
      const { data } = await api.post('/api/admin/update/check');
      setUpdateInfo(data);
    } catch (err: any) {
      setMessage({ text: err?.response?.data?.detail || 'Check failed', type: 'error' });
    } finally {
      setChecking(false);
    }
  };

  const executeUpdate = async () => {
    if (!confirm('Are you sure you want to update the bot?')) return;
    setUpdating(true);
    setMessage(null);
    try {
      const { data } = await api.post('/api/admin/update/execute', { confirm: true });
      setMessage({ text: data.detail || 'Update initiated!', type: 'success' });
    } catch (err: any) {
      setMessage({ text: err?.response?.data?.detail || 'Update failed', type: 'error' });
    } finally {
      setUpdating(false);
    }
  };

  return (
    <div>
      <h1 style={{ fontSize: '1.75rem', fontWeight: 700, marginBottom: '2rem' }}>🔄 Update Management</h1>

      <motion.div
        className="glass-card"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        style={{ padding: '2rem', maxWidth: 600 }}
      >
        <h2 style={{ fontSize: '1.125rem', fontWeight: 600, marginBottom: '1.5rem' }}>Version Check</h2>

        {updateInfo && (
          <div style={{ marginBottom: '1.5rem', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--color-text-secondary)' }}>Current Version</span>
              <span style={{ fontWeight: 600, fontFamily: 'monospace' }}>{updateInfo.current_version}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--color-text-secondary)' }}>Latest Version</span>
              <span style={{
                fontWeight: 600,
                fontFamily: 'monospace',
                color: updateInfo.update_available ? 'var(--color-accent-emerald)' : 'var(--color-text-primary)',
              }}>
                {updateInfo.latest_version}
              </span>
            </div>
            {updateInfo.update_available && (
              <div style={{
                padding: '0.75rem',
                borderRadius: 'var(--radius-sm)',
                background: 'rgba(16, 185, 129, 0.1)',
                border: '1px solid rgba(16, 185, 129, 0.3)',
                color: 'var(--color-accent-emerald)',
                fontSize: '0.8125rem',
              }}>
                🎉 A new version is available!
              </div>
            )}
          </div>
        )}

        {message && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            style={{
              padding: '0.75rem',
              borderRadius: 'var(--radius-sm)',
              background: message.type === 'success' ? 'rgba(16,185,129,0.1)' : 'rgba(244,63,94,0.1)',
              color: message.type === 'success' ? 'var(--color-accent-emerald)' : 'var(--color-accent-rose)',
              fontSize: '0.8125rem',
              marginBottom: '1rem',
            }}
          >
            {message.text}
          </motion.div>
        )}

        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <button
            className="btn-gradient"
            onClick={checkUpdate}
            disabled={checking}
            style={{ opacity: checking ? 0.7 : 1 }}
          >
            {checking ? 'Checking...' : '🔍 Check for Updates'}
          </button>
          {updateInfo?.update_available && (
            <button
              onClick={executeUpdate}
              disabled={updating}
              style={{
                padding: '0.625rem 1.5rem',
                borderRadius: 'var(--radius-md)',
                border: '1px solid var(--color-accent-emerald)',
                background: 'rgba(16, 185, 129, 0.1)',
                color: 'var(--color-accent-emerald)',
                cursor: 'pointer',
                fontWeight: 600,
                fontSize: '0.875rem',
                opacity: updating ? 0.7 : 1,
              }}
            >
              {updating ? 'Updating...' : '🚀 Update Now'}
            </button>
          )}
        </div>
      </motion.div>
    </div>
  );
}
