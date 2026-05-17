import { useCallback, useEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import api from '../../lib/api';
import { CONFIG_SCHEMAS, getNestedValue, setNestedValue } from './config/configSchema';
import { ConfigFormField } from './config/ConfigFormField';

const CONFIG_FILES = ['base', 'llm', 'memory', 'music'] as const;
type ConfigFile = (typeof CONFIG_FILES)[number];

export default function Config() {
  const { t } = useTranslation();
  const [selectedFile, setSelectedFile] = useState<ConfigFile>('base');
  const [configData, setConfigData] = useState<Record<string, unknown>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null);
  const messageTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (messageTimerRef.current !== null) clearTimeout(messageTimerRef.current);
    };
  }, []);

  useEffect(() => {
    setLoading(true);
    setConfigData({});
    api
      .get(`/api/admin/config/${selectedFile}`)
      .then(({ data }) => setConfigData((data.config as Record<string, unknown>) ?? {}))
      .catch(() => {
        setConfigData({});
        setMessage({ text: t('config.loadError'), type: 'error' });
      })
      .finally(() => setLoading(false));
  }, [selectedFile]);

  const handleFieldChange = useCallback((path: string, value: unknown) => {
    setConfigData((prev) => setNestedValue(prev, path, value));
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setMessage(null);
    try {
      await api.put(`/api/admin/config/${selectedFile}`, { config: configData });
      setMessage({ text: t('config.saved'), type: 'success' });
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        t('config.saveError');
      setMessage({ text: detail, type: 'error' });
    } finally {
      setSaving(false);
      if (messageTimerRef.current !== null) clearTimeout(messageTimerRef.current);
      messageTimerRef.current = setTimeout(() => setMessage(null), 4000);
    }
  };

  const schema = CONFIG_SCHEMAS[selectedFile] ?? [];

  const sectionMap = new Map<string, typeof schema>();
  for (const field of schema) {
    if (!sectionMap.has(field.section)) sectionMap.set(field.section, []);
    sectionMap.get(field.section)!.push(field);
  }

  return (
    <div>
      <h1 style={{ fontSize: '1.75rem', fontWeight: 700, marginBottom: '0.5rem' }}>
        ⚙️ {t('config.title')}
      </h1>
      <p style={{ color: 'var(--color-text-muted)', marginBottom: '2rem', fontSize: '0.875rem' }}>
        {t('config.subtitle')}
      </p>

      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
        {CONFIG_FILES.map((f) => (
          <button
            key={f}
            onClick={() => setSelectedFile(f)}
            style={{
              padding: '0.5rem 1.25rem',
              borderRadius: 'var(--radius-sm)',
              border: '1px solid',
              borderColor: selectedFile === f ? 'var(--color-accent-blue)' : 'var(--color-border)',
              background: selectedFile === f ? 'rgba(59,130,246,0.15)' : 'transparent',
              color: selectedFile === f ? 'var(--color-accent-blue)' : 'var(--color-text-secondary)',
              cursor: 'pointer',
              fontSize: '0.875rem',
              fontWeight: 500,
            }}
          >
            {f}.yaml
          </button>
        ))}
      </div>

      <motion.div
        key={selectedFile}
        className="glass-card"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        style={{ padding: '1.5rem' }}
      >
        {loading ? (
          <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--color-text-muted)' }}>
            {t('common.loading')}
          </div>
        ) : (
          <>
            {Array.from(sectionMap.entries()).map(([sectionKey, fields]) => (
              <div key={sectionKey} style={{ marginBottom: '2rem' }}>
                <h3
                  style={{
                    fontSize: '0.75rem',
                    fontWeight: 600,
                    color: 'var(--color-accent-blue)',
                    textTransform: 'uppercase',
                    letterSpacing: '0.06em',
                    marginBottom: '1rem',
                    paddingBottom: '0.5rem',
                    borderBottom: '1px solid var(--color-border)',
                  }}
                >
                  {t(sectionKey)}
                </h3>

                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
                    gap: '1rem',
                  }}
                >
                  {fields.map((field) => (
                    <div
                      key={field.path}
                      style={
                        field.type === 'array' || field.type === 'textarea'
                          ? { gridColumn: '1 / -1' }
                          : undefined
                      }
                    >
                      <ConfigFormField
                        def={field}
                        value={getNestedValue(configData, field.path)}
                        onChange={handleFieldChange}
                      />
                    </div>
                  ))}
                </div>
              </div>
            ))}

            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginTop: '1rem',
                paddingTop: '1rem',
                borderTop: '1px solid var(--color-border)',
              }}
            >
              {message ? (
                <motion.span
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  style={{
                    fontSize: '0.8125rem',
                    color:
                      message.type === 'success'
                        ? 'var(--color-accent-emerald)'
                        : 'var(--color-accent-rose)',
                  }}
                >
                  {message.type === 'success' ? '✅' : '❌'} {message.text}
                </motion.span>
              ) : (
                <span />
              )}
              <button
                className="btn-gradient"
                onClick={handleSave}
                disabled={saving}
                style={{ opacity: saving ? 0.7 : 1 }}
              >
                {saving ? t('config.saving') : `💾 ${t('config.save')}`}
              </button>
            </div>
          </>
        )}
      </motion.div>
    </div>
  );
}
