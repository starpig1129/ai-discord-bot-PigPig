import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import api from '../../lib/api';

const CONFIG_FILES = ['base', 'llm', 'memory', 'music'];

export default function Config() {
  const [selectedFile, setSelectedFile] = useState('base');
  const [config, setConfig] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null);

  useEffect(() => {
    setLoading(true);
    api.get(`/api/admin/config/${selectedFile}`)
      .then(({ data }) => {
        setConfig(JSON.stringify(data.config, null, 2));
      })
      .catch(() => setConfig('// Failed to load config'))
      .finally(() => setLoading(false));
  }, [selectedFile]);

  const handleSave = async () => {
    setSaving(true);
    setMessage(null);
    try {
      const parsed = JSON.parse(config);
      await api.put(`/api/admin/config/${selectedFile}`, { config: parsed });
      setMessage({ text: `${selectedFile}.yaml saved successfully!`, type: 'success' });
    } catch (err: any) {
      setMessage({
        text: err?.response?.data?.detail || 'Invalid JSON or save failed',
        type: 'error',
      });
    } finally {
      setSaving(false);
      setTimeout(() => setMessage(null), 4000);
    }
  };

  return (
    <div>
      <h1 style={{ fontSize: '1.75rem', fontWeight: 700, marginBottom: '2rem' }}>⚙️ Configuration</h1>

      {/* File Tabs */}
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.5rem' }}>
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

      {/* Editor */}
      <motion.div
        className="glass-card"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        style={{ padding: '1.5rem' }}
      >
        {loading ? (
          <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--color-text-muted)' }}>
            Loading...
          </div>
        ) : (
          <>
            <textarea
              value={config}
              onChange={(e) => setConfig(e.target.value)}
              spellCheck={false}
              style={{
                width: '100%',
                minHeight: 400,
                padding: '1rem',
                fontFamily: '"JetBrains Mono", "Fira Code", monospace',
                fontSize: '0.8125rem',
                lineHeight: 1.6,
                background: 'rgba(15, 23, 42, 0.8)',
                color: 'var(--color-text-primary)',
                border: '1px solid var(--color-border)',
                borderRadius: 'var(--radius-md)',
                resize: 'vertical',
                outline: 'none',
              }}
              onFocus={(e) => { e.currentTarget.style.borderColor = 'var(--color-accent-blue)'; }}
              onBlur={(e) => { e.currentTarget.style.borderColor = 'var(--color-border)'; }}
            />
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '1rem' }}>
              {message && (
                <motion.span
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
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
                  {saving ? 'Saving...' : '💾 Save'}
                </button>
              </div>
            </div>
          </>
        )}
      </motion.div>
    </div>
  );
}
