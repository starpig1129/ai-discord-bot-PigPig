import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { ConfigFieldDef } from './configSchema';

const BASE_INPUT: React.CSSProperties = {
  width: '100%',
  padding: '0.5rem 0.75rem',
  background: 'rgba(15, 23, 42, 0.6)',
  border: '1px solid var(--color-border)',
  borderRadius: 'var(--radius-sm)',
  color: 'var(--color-text-primary)',
  fontSize: '0.875rem',
  outline: 'none',
  boxSizing: 'border-box',
};

const LABEL_STYLE: React.CSSProperties = {
  display: 'block',
  fontSize: '0.8125rem',
  fontWeight: 500,
  color: 'var(--color-text-secondary)',
  marginBottom: '0.375rem',
};

interface Props {
  def: ConfigFieldDef;
  value: unknown;
  onChange: (path: string, value: unknown) => void;
}

function TextareaField({ def, value, onChange }: Props) {
  const { t } = useTranslation();
  const serialize = (v: unknown) =>
    typeof v === 'object' && v !== null ? JSON.stringify(v, null, 2) : String(v ?? '');

  const [raw, setRaw] = useState(serialize(value));

  useEffect(() => {
    setRaw(serialize(value));
  }, [value]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleBlur = () => {
    try {
      onChange(def.path, JSON.parse(raw));
    } catch {
      onChange(def.path, raw);
    }
  };

  return (
    <div>
      <label htmlFor={def.path} style={LABEL_STYLE}>{t(def.labelKey)}</label>
      <textarea
        id={def.path}
        value={raw}
        onChange={(e) => setRaw(e.target.value)}
        onBlur={handleBlur}
        spellCheck={false}
        style={{
          ...BASE_INPUT,
          minHeight: 120,
          fontFamily: '"JetBrains Mono", "Fira Code", monospace',
          fontSize: '0.8rem',
          lineHeight: 1.5,
          resize: 'vertical',
        }}
      />
    </div>
  );
}

export function ConfigFormField({ def, value, onChange }: Props) {
  const { t } = useTranslation();

  if (def.type === 'textarea') {
    return <TextareaField def={def} value={value} onChange={onChange} />;
  }

  if (def.readOnly) {
    return (
      <div>
        <label htmlFor={def.path} style={LABEL_STYLE}>{t(def.labelKey)}</label>
        <div id={def.path} style={{ ...BASE_INPUT, opacity: 0.5, cursor: 'not-allowed' }}>
          {String(value ?? '')}
        </div>
      </div>
    );
  }

  if (def.type === 'boolean') {
    const checked = Boolean(value);
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0.375rem 0' }}>
        <label htmlFor={def.path} style={LABEL_STYLE}>{t(def.labelKey)}</label>
        <button
          id={def.path}
          onClick={() => onChange(def.path, !checked)}
          aria-pressed={checked}
          title={checked ? t('common.yes') : t('common.no')}
          style={{
            width: '3rem',
            height: '1.5rem',
            borderRadius: '999px',
            border: 'none',
            background: checked ? 'var(--color-accent-blue)' : 'var(--color-border)',
            cursor: 'pointer',
            position: 'relative',
            transition: 'background 0.2s',
            flexShrink: 0,
          }}
        >
          <span
            style={{
              position: 'absolute',
              top: '2px',
              left: checked ? 'calc(100% - 22px)' : '2px',
              width: '20px',
              height: '20px',
              borderRadius: '50%',
              background: '#fff',
              transition: 'left 0.2s',
              pointerEvents: 'none',
            }}
          />
        </button>
      </div>
    );
  }

  if (def.type === 'select') {
    return (
      <div>
        <label htmlFor={def.path} style={LABEL_STYLE}>{t(def.labelKey)}</label>
        <select
          id={def.path}
          value={String(value ?? '')}
          onChange={(e) => onChange(def.path, e.target.value)}
          style={{ ...BASE_INPUT, cursor: 'pointer' }}
        >
          {def.options?.map((opt) => (
            <option key={opt} value={opt} style={{ background: '#0f172a' }}>
              {opt}
            </option>
          ))}
        </select>
      </div>
    );
  }

  if (def.type === 'number') {
    return (
      <div>
        <label htmlFor={def.path} style={LABEL_STYLE}>{t(def.labelKey)}</label>
        <input
          id={def.path}
          type="number"
          value={value !== undefined && value !== null ? String(value) : ''}
          min={def.min}
          max={def.max}
          onChange={(e) =>
            onChange(def.path, e.target.value === '' ? undefined : Number(e.target.value))
          }
          style={BASE_INPUT}
        />
      </div>
    );
  }

  if (def.type === 'array') {
    const rawItems: string[] = Array.isArray(value) ? (value as string[]) : [];
    // Map raw strings to stable-id objects for React reconciliation
    const items = rawItems.map((val, i) => ({ id: `item-${i}-${val}`, val }));
    return (
      <div>
        <label htmlFor={def.path} style={LABEL_STYLE}>{t(def.labelKey)}</label>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.375rem' }}>
          {items.map(({ id, val }, i) => (
            <div key={id} style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
              <input
                type="text"
                value={val}
                onChange={(e) => {
                  const next = rawItems.map((v, j) => (j === i ? e.target.value : v));
                  onChange(def.path, next);
                }}
                style={{ ...BASE_INPUT, flex: 1 }}
              />
              <button
                onClick={() => onChange(def.path, rawItems.filter((_, j) => j !== i))}
                style={{
                  padding: '0.375rem 0.625rem',
                  background: 'rgba(239,68,68,0.15)',
                  border: '1px solid rgba(239,68,68,0.3)',
                  borderRadius: 'var(--radius-sm)',
                  color: 'var(--color-accent-rose)',
                  cursor: 'pointer',
                  fontSize: '0.75rem',
                  flexShrink: 0,
                  lineHeight: 1,
                }}
              >
                {t('config.removeItem')}
              </button>
            </div>
          ))}
          <button
            onClick={() => onChange(def.path, [...rawItems, ''])}
            style={{
              alignSelf: 'flex-start',
              padding: '0.375rem 0.875rem',
              background: 'rgba(59,130,246,0.1)',
              border: '1px solid rgba(59,130,246,0.3)',
              borderRadius: 'var(--radius-sm)',
              color: 'var(--color-accent-blue)',
              cursor: 'pointer',
              fontSize: '0.8125rem',
            }}
          >
            + {t('config.addItem')}
          </button>
        </div>
      </div>
    );
  }

  // default: text
  return (
    <div>
      <label htmlFor={def.path} style={LABEL_STYLE}>{t(def.labelKey)}</label>
      <input
        id={def.path}
        type="text"
        value={String(value ?? '')}
        onChange={(e) => onChange(def.path, e.target.value)}
        style={BASE_INPUT}
      />
    </div>
  );
}
