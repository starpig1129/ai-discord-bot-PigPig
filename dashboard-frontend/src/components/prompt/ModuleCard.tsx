import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import api from '../../lib/api';

export interface PromptModule {
  name: string;
  description: string;
  protected: boolean;
  base_content: string;
  custom_content: string | null;
  is_customized: boolean;
}

interface ModuleCardProps {
  mod: PromptModule;
  guildId: string;
  channelId?: string; // If provided, updates channel module instead of server module
  onSaved: (name: string, newCustom: string | null) => void;
}

const MODULE_LABELS: Record<string, { label: string; emoji: string }> = {
  identity: { label: '身分識別', emoji: '🤖' },
  response_principles: { label: '回應風格', emoji: '🎨' },
  interaction: { label: '互動方式', emoji: '💬' },
  professional_personality: { label: '專業人格', emoji: '👔' },
};

export default function ModuleCard({ mod, guildId, channelId, onSaved }: ModuleCardProps) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const [useCustom, setUseCustom] = useState(() => mod.is_customized);
  const [draft, setDraft] = useState(() => mod.custom_content ?? mod.base_content);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<{ text: string; ok: boolean } | null>(null);

  const info = MODULE_LABELS[mod.name] ?? { label: mod.name, emoji: '📄' };

  const save = async () => {
    setSaving(true);
    setMsg(null);
    try {
      const endpoint = channelId 
        ? `/api/guild/${guildId}/channels/${channelId}/prompt/modules/${mod.name}`
        : `/api/guild/${guildId}/prompt/modules/${mod.name}`;
        
      if (useCustom) {
        await api.put(endpoint, { custom_content: draft });
        onSaved(mod.name, draft);
      } else {
        await api.put(endpoint, { reset: true });
        onSaved(mod.name, null);
      }
      setMsg({ text: t('guild.promptSaved'), ok: true });
    } catch {
      setMsg({ text: t('guild.promptSaveFailed'), ok: false });
    } finally {
      setSaving(false);
      setTimeout(() => setMsg(null), 4000);
    }
  };

  const accentColor = mod.is_customized ? 'var(--color-accent-violet)' : 'var(--color-accent-blue)';

  return (
    <motion.div
      className="glass-card"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      style={{ overflow: 'hidden', borderLeft: `3px solid ${accentColor}` }}
    >
      <div
        onClick={() => setExpanded(e => !e)}
        style={{
          display: 'flex', alignItems: 'center', gap: '0.75rem',
          padding: '1rem 1.25rem', cursor: 'pointer', userSelect: 'none',
        }}
      >
        <span style={{ fontSize: '1.1rem' }}>{info.emoji}</span>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
            <span style={{ fontWeight: 600, fontSize: '0.9375rem' }}>{info.label}</span>
            <code style={{
              fontSize: '0.7rem', padding: '0.1rem 0.4rem',
              borderRadius: 'var(--radius-sm)',
              background: 'rgba(148,163,184,0.1)',
              color: 'var(--color-text-muted)',
            }}>{mod.name}</code>
            {mod.is_customized && (
              <span style={{
                fontSize: '0.7rem', padding: '0.15rem 0.5rem',
                borderRadius: 'var(--radius-sm)',
                background: 'rgba(139,92,246,0.12)',
                color: 'var(--color-accent-violet)',
                border: '1px solid rgba(139,92,246,0.2)',
              }}>✏️ {t('guild.customized')}</span>
            )}
          </div>
          <p style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', marginTop: '0.15rem' }}>
            {mod.description}
          </p>
        </div>
        <span style={{ color: 'var(--color-text-muted)', fontSize: '0.875rem' }}>
          {expanded ? '▲' : '▼'}
        </span>
      </div>

      <AnimatePresence>
        {expanded && (
          <motion.div
            key="content"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            style={{ overflow: 'hidden' }}
          >
            <div style={{ padding: '0 1.25rem 1.25rem', borderTop: '1px solid var(--color-border)' }}>
              <div style={{ display: 'flex', gap: '0.375rem', margin: '0.875rem 0 0.75rem' }}>
                <button
                  onClick={() => { setUseCustom(false); setDraft(mod.base_content); }}
                  style={{
                    padding: '0.375rem 0.875rem', borderRadius: 'var(--radius-sm)', border: '1px solid',
                    borderColor: !useCustom ? 'var(--color-accent-emerald)' : 'var(--color-border)',
                    background: !useCustom ? 'rgba(16,185,129,0.12)' : 'transparent',
                    color: !useCustom ? 'var(--color-accent-emerald)' : 'var(--color-text-muted)',
                    cursor: 'pointer', fontSize: '0.8125rem',
                  }}
                >📄 {t('guild.useBase')}</button>
                <button
                  onClick={() => {
                    setUseCustom(true);
                    setDraft(mod.custom_content ?? mod.base_content);
                  }}
                  style={{
                    padding: '0.375rem 0.875rem', borderRadius: 'var(--radius-sm)', border: '1px solid',
                    borderColor: useCustom ? 'var(--color-accent-violet)' : 'var(--color-border)',
                    background: useCustom ? 'rgba(139,92,246,0.12)' : 'transparent',
                    color: useCustom ? 'var(--color-accent-violet)' : 'var(--color-text-muted)',
                    cursor: 'pointer', fontSize: '0.8125rem',
                  }}
                >✏️ {t('guild.useCustom')}</button>
              </div>

              {useCustom ? (
                <textarea
                  value={draft}
                  onChange={e => setDraft(e.target.value)}
                  style={{
                    width: '100%', minHeight: 160, padding: '0.75rem',
                    fontFamily: '"JetBrains Mono", monospace', fontSize: '0.8125rem', lineHeight: 1.65,
                    background: 'rgba(15,23,42,0.8)', color: 'var(--color-text-primary)',
                    border: '1px solid var(--color-accent-violet)',
                    borderRadius: 'var(--radius-md)', resize: 'vertical', outline: 'none',
                    boxSizing: 'border-box',
                  }}
                />
              ) : (
                <pre style={{
                  fontSize: '0.8rem', lineHeight: 1.65, color: 'var(--color-text-secondary)',
                  whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                  maxHeight: 200, overflowY: 'auto', padding: '0.875rem',
                  background: 'rgba(15,23,42,0.4)', border: '1px solid var(--color-border)',
                  borderRadius: 'var(--radius-md)', fontFamily: '"JetBrains Mono", monospace',
                }}>
                  {mod.base_content || '（無內容）'}
                </pre>
              )}

              <div style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: '0.75rem', marginTop: '0.625rem' }}>
                {msg && (
                  <span style={{ fontSize: '0.75rem', color: msg.ok ? 'var(--color-accent-emerald)' : 'var(--color-accent-rose)' }}>
                    {msg.ok ? '✅' : '❌'} {msg.text}
                  </span>
                )}
                {mod.is_customized && !useCustom && (
                  <button onClick={save} disabled={saving} style={{
                    padding: '0.375rem 1rem', borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--color-accent-rose)',
                    background: 'rgba(244,63,94,0.1)', color: 'var(--color-accent-rose)',
                    cursor: 'pointer', fontSize: '0.8125rem', fontWeight: 600, opacity: saving ? 0.7 : 1,
                  }}>🔄 {t('guild.resetToBase')}</button>
                )}
                {useCustom && (
                  <button onClick={save} disabled={saving} style={{
                    padding: '0.375rem 1rem', borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--color-accent-violet)',
                    background: 'rgba(139,92,246,0.15)', color: 'var(--color-accent-violet)',
                    cursor: 'pointer', fontSize: '0.8125rem', fontWeight: 600, opacity: saving ? 0.7 : 1,
                  }}>{saving ? t('common.saving') : `💾 ${t('common.save')}`}</button>
                )}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
