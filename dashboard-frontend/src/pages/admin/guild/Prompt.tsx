import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import { useOutletContext } from 'react-router-dom';
import api from '../../../lib/api';

interface PromptData {
  enabled: boolean;
  prompt: string;
  prompt_name: string;
}

interface GuildContext {
  guildId: string;
}

export default function GuildPrompt() {
  const { guildId } = useOutletContext<GuildContext>();
  const { t } = useTranslation();
  const [data, setData] = useState<PromptData>({ enabled: false, prompt: '', prompt_name: '' });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null);

  useEffect(() => {
    setLoading(true);
    api.get(`/api/guild/${guildId}/prompt`)
      .then(({ data }) => setData(data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [guildId]);

  const handleSave = async () => {
    setSaving(true);
    setMessage(null);
    try {
      await api.put(`/api/guild/${guildId}/prompt`, data);
      setMessage({ text: t('guild.promptSaved'), type: 'success' });
    } catch {
      setMessage({ text: t('guild.promptSaveFailed'), type: 'error' });
    } finally {
      setSaving(false);
      setTimeout(() => setMessage(null), 4000);
    }
  };

  if (loading) return (
    <div style={{ display: 'flex', justifyContent: 'center', padding: '3rem' }}>
      <div className="animate-pulse-glow">✍️</div>
    </div>
  );

  return (
    <div>
      <motion.div
        className="glass-card"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        style={{ padding: '1.5rem' }}
      >
        <h2 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '1.25rem' }}>
          ✍️ {t('guild.systemPrompt')}
        </h2>

        {/* Enabled toggle */}
        <label style={{
          display: 'flex', alignItems: 'center', gap: '0.625rem',
          marginBottom: '1.25rem', cursor: 'pointer',
        }}>
          <div
            onClick={() => setData(d => ({ ...d, enabled: !d.enabled }))}
            style={{
              width: 44, height: 24,
              borderRadius: 12,
              background: data.enabled ? 'var(--color-accent-blue)' : 'var(--color-border)',
              position: 'relative',
              cursor: 'pointer',
              transition: 'background 0.2s',
            }}
          >
            <div style={{
              position: 'absolute', top: 3, left: data.enabled ? 22 : 3,
              width: 18, height: 18, borderRadius: '50%',
              background: 'white', transition: 'left 0.2s',
            }} />
          </div>
          <span style={{ fontSize: '0.875rem', color: 'var(--color-text-secondary)' }}>
            {data.enabled ? t('guild.promptOn') : t('guild.promptOff')}
          </span>
        </label>

        {/* Prompt name */}
        <div style={{ marginBottom: '0.875rem' }}>
          <label style={{ display: 'block', fontSize: '0.75rem', color: 'var(--color-text-muted)', marginBottom: '0.375rem' }}>
            {t('guild.promptName')}
          </label>
          <input
            type="text"
            value={data.prompt_name}
            onChange={e => setData(d => ({ ...d, prompt_name: e.target.value }))}
            placeholder={t('guild.promptNamePlaceholder')}
            style={{
              width: '100%', padding: '0.5rem 0.75rem',
              borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--color-border)',
              background: 'var(--color-bg-secondary)',
              color: 'var(--color-text-primary)',
              fontSize: '0.875rem', outline: 'none',
            }}
          />
        </div>

        {/* Prompt content */}
        <div style={{ marginBottom: '1rem' }}>
          <label style={{ display: 'block', fontSize: '0.75rem', color: 'var(--color-text-muted)', marginBottom: '0.375rem' }}>
            {t('guild.promptContent')}
          </label>
          <textarea
            value={data.prompt}
            onChange={e => setData(d => ({ ...d, prompt: e.target.value }))}
            placeholder={t('guild.promptPlaceholder')}
            style={{
              width: '100%', minHeight: 200,
              padding: '0.75rem',
              fontFamily: '"JetBrains Mono", "Fira Code", monospace',
              fontSize: '0.8125rem', lineHeight: 1.6,
              background: 'rgba(15,23,42,0.8)',
              color: 'var(--color-text-primary)',
              border: '1px solid var(--color-border)',
              borderRadius: 'var(--radius-md)',
              resize: 'vertical', outline: 'none',
            }}
          />
        </div>

        {/* Save row */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          {message && (
            <motion.span
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              style={{
                fontSize: '0.8125rem',
                color: message.type === 'success' ? 'var(--color-accent-emerald)' : 'var(--color-accent-rose)',
              }}
            >
              {message.type === 'success' ? '✅' : '❌'} {message.text}
            </motion.span>
          )}
          <div style={{ marginLeft: 'auto' }}>
            <button
              className="btn-gradient"
              onClick={handleSave}
              disabled={saving}
              style={{ opacity: saving ? 0.7 : 1 }}
            >
              {saving ? t('common.saving') : `💾 ${t('common.save')}`}
            </button>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
