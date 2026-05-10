import { useCallback, useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import { useOutletContext } from 'react-router-dom';
import api from '../../../lib/api';
import ModuleCard from '../../../components/prompt/ModuleCard';
import type { PromptModule } from '../../../components/prompt/ModuleCard';

interface ModulesData {
  sp_enabled: boolean;
  modules: PromptModule[];
  module_order: string[];
}

interface GuildContext {
  guildId: string;
}

export default function GuildPrompt() {
  const { guildId } = useOutletContext<GuildContext>();
  const { t } = useTranslation();
  const [data, setData] = useState<ModulesData | null>(null);
  const [loading, setLoading] = useState(true);
  const [enablingToggle, setEnablingToggle] = useState(false);

  const fetchModules = useCallback(() => {
    api.get(`/api/guild/${guildId}/prompt/modules`)
      .then(({ data }) => setData(data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [guildId]);

  useEffect(() => { fetchModules(); }, [fetchModules]);

  const toggleEnabled = async () => {
    if (!data) return;
    setEnablingToggle(true);
    try {
      await api.put(`/api/guild/${guildId}/prompt/modules/identity`, {
        sp_enabled: !data.sp_enabled,
      });
      setData(d => d ? { ...d, sp_enabled: !d.sp_enabled } : d);
    } finally { setEnablingToggle(false); }
  };

  const handleModuleSaved = (name: string, newCustom: string | null) => {
    setData(d => {
      if (!d) return d;
      return {
        ...d,
        modules: d.modules.map(m =>
          m.name === name ? { ...m, custom_content: newCustom, is_customized: newCustom !== null } : m,
        ),
      };
    });
  };

  if (loading || !data) return (
    <div style={{ display: 'flex', justifyContent: 'center', padding: '3rem' }}>
      <div className="animate-pulse-glow">✍️</div>
    </div>
  );

  // Only show customizable modules — protected ones are hidden
  const customizableMods = data.modules.filter(m => !m.protected);
  const customizedCount = customizableMods.filter(m => m.is_customized).length;

  return (
    <div>
      {/* Header + toggle */}
      <motion.div
        className="glass-card"
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        style={{
          padding: '1.25rem 1.5rem',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          flexWrap: 'wrap', gap: '1rem', marginBottom: '1.5rem',
        }}
      >
        <div>
          <h2 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '0.25rem' }}>
            🧩 {t('guild.modulesTitle')}
          </h2>
          <p style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
            {customizableMods.length} {t('guild.customizableModules')} · {customizedCount} {t('guild.customizedCount')}
          </p>
        </div>

        <label style={{ display: 'flex', alignItems: 'center', gap: '0.625rem', cursor: 'pointer' }}>
          <span style={{ fontSize: '0.875rem', color: 'var(--color-text-secondary)' }}>
            {t('guild.systemPrompt')}
          </span>
          <div
            onClick={enablingToggle ? undefined : toggleEnabled}
            style={{
              width: 44, height: 24, borderRadius: 12,
              background: data.sp_enabled ? 'var(--color-accent-blue)' : 'var(--color-border)',
              position: 'relative', cursor: enablingToggle ? 'wait' : 'pointer',
              transition: 'background 0.2s', opacity: enablingToggle ? 0.7 : 1,
            }}
          >
            <div style={{
              position: 'absolute', top: 3, left: data.sp_enabled ? 22 : 3,
              width: 18, height: 18, borderRadius: '50%',
              background: 'white', transition: 'left 0.2s',
            }} />
          </div>
        </label>
      </motion.div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
        {customizableMods.map((mod, i) => (
          <motion.div key={mod.name} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.06 }}>
            <ModuleCard mod={mod} guildId={guildId} onSaved={handleModuleSaved} />
          </motion.div>
        ))}
      </div>
    </div>
  );
}
