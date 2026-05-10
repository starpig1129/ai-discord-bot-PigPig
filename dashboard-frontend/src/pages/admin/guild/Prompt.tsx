import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import { useOutletContext } from 'react-router-dom';
import api from '../../../lib/api';

interface EffectivePromptData {
  base_prompt: string;
  override_enabled: boolean;
  override_prompt: string;
  override_name: string;
}

interface GuildContext {
  guildId: string;
}

type ViewMode = 'base' | 'override';

export default function GuildPrompt() {
  const { guildId } = useOutletContext<GuildContext>();
  const { t } = useTranslation();

  const [data, setData] = useState<EffectivePromptData | null>(null);
  const [loading, setLoading] = useState(true);

  // Editable override fields
  const [overrideEnabled, setOverrideEnabled] = useState(false);
  const [overridePrompt, setOverridePrompt] = useState('');
  const [overrideName, setOverrideName] = useState('');

  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null);

  // Which pane is visible: base YAML preview OR server-level override editor
  const [view, setView] = useState<ViewMode>('base');

  useEffect(() => {
    setLoading(true);
    api.get(`/api/guild/${guildId}/prompt/effective`)
      .then(({ data }) => {
        setData(data);
        setOverrideEnabled(data.override_enabled);
        setOverridePrompt(data.override_prompt);
        setOverrideName(data.override_name);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [guildId]);

  const handleSave = async () => {
    setSaving(true);
    setMessage(null);
    try {
      await api.put(`/api/guild/${guildId}/prompt`, {
        enabled: overrideEnabled,
        prompt: overridePrompt,
        prompt_name: overrideName,
      });
      // Refresh data
      const res = await api.get(`/api/guild/${guildId}/prompt/effective`);
      setData(res.data);
      setMessage({ text: t('guild.promptSaved'), type: 'success' });
    } catch {
      setMessage({ text: t('guild.promptSaveFailed'), type: 'error' });
    } finally {
      setSaving(false);
      setTimeout(() => setMessage(null), 4000);
    }
  };

  if (loading || !data) return (
    <div style={{ display: 'flex', justifyContent: 'center', padding: '3rem' }}>
      <div className="animate-pulse-glow">✍️</div>
    </div>
  );

  return (
    <div>
      {/* View switcher */}
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.25rem' }}>
        <button
          onClick={() => setView('base')}
          style={{
            padding: '0.5rem 1.25rem',
            borderRadius: 'var(--radius-sm)', border: '1px solid',
            borderColor: view === 'base' ? 'var(--color-accent-emerald)' : 'var(--color-border)',
            background: view === 'base' ? 'rgba(16,185,129,0.12)' : 'transparent',
            color: view === 'base' ? 'var(--color-accent-emerald)' : 'var(--color-text-secondary)',
            cursor: 'pointer', fontSize: '0.875rem', fontWeight: 500,
          }}
        >
          👁 {t('guild.basePromptPreview')}
        </button>
        <button
          onClick={() => setView('override')}
          style={{
            padding: '0.5rem 1.25rem',
            borderRadius: 'var(--radius-sm)', border: '1px solid',
            borderColor: view === 'override' ? 'var(--color-accent-blue)' : 'var(--color-border)',
            background: view === 'override' ? 'rgba(59,130,246,0.12)' : 'transparent',
            color: view === 'override' ? 'var(--color-accent-blue)' : 'var(--color-text-secondary)',
            cursor: 'pointer', fontSize: '0.875rem', fontWeight: 500,
          }}
        >
          ✍️ {t('guild.serverOverride')}
        </button>
      </div>

      {/* Base YAML prompt preview (read-only) */}
      {view === 'base' && (
        <motion.div
          className="glass-card"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          style={{ padding: '1.5rem' }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.875rem' }}>
            <h2 style={{ fontSize: '0.9375rem', fontWeight: 600 }}>
              📄 {t('guild.basePromptPreview')}
            </h2>
            <span style={{
              fontSize: '0.75rem', padding: '0.2rem 0.6rem',
              borderRadius: 'var(--radius-sm)',
              background: 'rgba(16,185,129,0.12)',
              color: 'var(--color-accent-emerald)',
              border: '1px solid rgba(16,185,129,0.25)',
            }}>
              YAML default · 唯讀
            </span>
          </div>
          <p style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', marginBottom: '0.875rem', lineHeight: 1.5 }}>
            {t('guild.basePromptNote')}
          </p>
          <pre style={{
            fontSize: '0.8125rem', lineHeight: 1.7,
            color: 'var(--color-text-secondary)',
            whiteSpace: 'pre-wrap', wordBreak: 'break-word',
            maxHeight: 480, overflowY: 'auto',
            padding: '1rem',
            background: 'rgba(15,23,42,0.6)',
            border: '1px solid var(--color-border)',
            borderRadius: 'var(--radius-md)',
            fontFamily: '"JetBrains Mono", "Fira Code", monospace',
          }}>
            {data.base_prompt || t('common.noData')}
          </pre>
        </motion.div>
      )}

      {/* Server-level override editor */}
      {view === 'override' && (
        <motion.div
          className="glass-card"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          style={{ padding: '1.5rem' }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
            <h2 style={{ fontSize: '0.9375rem', fontWeight: 600 }}>
              ✍️ {t('guild.serverOverride')}
            </h2>
            {data.override_prompt && (
              <span style={{
                fontSize: '0.75rem', padding: '0.2rem 0.6rem',
                borderRadius: 'var(--radius-sm)',
                background: 'rgba(59,130,246,0.12)',
                color: 'var(--color-accent-blue)',
                border: '1px solid rgba(59,130,246,0.25)',
              }}>
                {t('guild.hasCustomPrompt')}
              </span>
            )}
          </div>

          <p style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', marginBottom: '1rem', lineHeight: 1.5 }}>
            {t('guild.overrideNote')}
          </p>

          {/* Enabled toggle */}
          <label style={{
            display: 'flex', alignItems: 'center', gap: '0.625rem',
            marginBottom: '1.25rem', cursor: 'pointer',
          }}>
            <div
              onClick={() => setOverrideEnabled(e => !e)}
              style={{
                width: 44, height: 24, borderRadius: 12,
                background: overrideEnabled ? 'var(--color-accent-blue)' : 'var(--color-border)',
                position: 'relative', cursor: 'pointer', transition: 'background 0.2s',
              }}
            >
              <div style={{
                position: 'absolute', top: 3, left: overrideEnabled ? 22 : 3,
                width: 18, height: 18, borderRadius: '50%',
                background: 'white', transition: 'left 0.2s',
              }} />
            </div>
            <span style={{ fontSize: '0.875rem', color: 'var(--color-text-secondary)' }}>
              {overrideEnabled ? t('guild.promptOn') : t('guild.promptOff')}
            </span>
          </label>

          {/* Prompt name */}
          <div style={{ marginBottom: '0.875rem' }}>
            <label style={{ display: 'block', fontSize: '0.75rem', color: 'var(--color-text-muted)', marginBottom: '0.375rem' }}>
              {t('guild.promptName')}
            </label>
            <input
              type="text"
              value={overrideName}
              onChange={e => setOverrideName(e.target.value)}
              placeholder={t('guild.promptNamePlaceholder')}
              style={{
                width: '100%', padding: '0.5rem 0.75rem',
                borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--color-border)',
                background: 'var(--color-bg-secondary)',
                color: 'var(--color-text-primary)',
                fontSize: '0.875rem', outline: 'none', boxSizing: 'border-box',
              }}
            />
          </div>

          {/* Prompt content */}
          <div style={{ marginBottom: '1rem' }}>
            <label style={{ display: 'block', fontSize: '0.75rem', color: 'var(--color-text-muted)', marginBottom: '0.375rem' }}>
              {t('guild.promptContent')}
            </label>
            <textarea
              value={overridePrompt}
              onChange={e => setOverridePrompt(e.target.value)}
              placeholder={t('guild.promptPlaceholder')}
              style={{
                width: '100%', minHeight: 240,
                padding: '0.75rem',
                fontFamily: '"JetBrains Mono", "Fira Code", monospace',
                fontSize: '0.8125rem', lineHeight: 1.6,
                background: 'rgba(15,23,42,0.8)',
                color: 'var(--color-text-primary)',
                border: '1px solid var(--color-border)',
                borderRadius: 'var(--radius-md)',
                resize: 'vertical', outline: 'none', boxSizing: 'border-box',
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
      )}
    </div>
  );
}
