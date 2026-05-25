import { useState, useRef, useEffect } from 'react';
import { motion } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import { useWebSocket, type LogEntry } from '../../hooks/useWebSocket';
import { useIsMobile } from '../../hooks/useIsMobile';

const LEVEL_COLORS: Record<string, string> = {
  DEBUG: '#06b6d4',
  INFO: '#10b981',
  WARNING: '#f59e0b',
  ERROR: '#f43f5e',
  CRITICAL: '#dc2626',
};

export default function Logs() {
  const { t } = useTranslation();
  const isMobile = useIsMobile();
  const token = localStorage.getItem('access_token');
  const { logs, connected, sendFilter, clearLogs } = useWebSocket({
    url: '/ws/admin/logs',
    token,
  });
  const [levelFilter, setLevelFilter] = useState<string>('');
  const [guildFilter, setGuildFilter] = useState<string>('');
  const [autoScroll, setAutoScroll] = useState(true);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (autoScroll && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [logs, autoScroll]);

  const handleLevelChange = (level: string) => {
    setLevelFilter(level);
    sendFilter({ level: level || null, guild_id: guildFilter || null });
  };

  const handleGuildChange = (guild: string) => {
    setGuildFilter(guild);
    sendFilter({ level: levelFilter || null, guild_id: guild || null });
  };

  const filteredLogs = logs;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: isMobile ? 'calc(100vh - 6rem)' : 'calc(100vh - 4rem)' }}>
      {/* Header: stacks on mobile */}
      <div style={{
        display: 'flex',
        flexDirection: isMobile ? 'column' : 'row',
        justifyContent: 'space-between',
        alignItems: isMobile ? 'flex-start' : 'center',
        gap: isMobile ? '0.75rem' : 0,
        marginBottom: '1rem',
      }}>
        <div>
          <h1 style={{ fontSize: '1.75rem', fontWeight: 700 }}>📝 {t('logs.title')}</h1>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '0.25rem' }}>
            <span className={`status-dot ${connected ? 'online' : 'offline'}`} />
            <span style={{ color: 'var(--color-text-muted)', fontSize: '0.75rem' }}>
              {connected ? t('logs.connected') : t('logs.disconnected')} · {logs.length} entries
            </span>
          </div>
        </div>

        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <select
            value={levelFilter}
            onChange={(e) => handleLevelChange(e.target.value)}
            style={{
              padding: '0.375rem 0.75rem',
              borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--color-border)',
              background: 'var(--color-bg-secondary)',
              color: 'var(--color-text-primary)',
              fontSize: '0.8125rem',
              outline: 'none',
            }}
          >
            <option value="">{t('logs.allLevels')}</option>
            {Object.keys(LEVEL_COLORS).map((l) => (
              <option key={l} value={l}>{l}</option>
            ))}
          </select>

          <input
            type="text"
            placeholder={t('logs.filterGuild') + '...'}
            value={guildFilter}
            onChange={(e) => handleGuildChange(e.target.value)}
            style={{
              padding: '0.375rem 0.75rem',
              borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--color-border)',
              background: 'var(--color-bg-secondary)',
              color: 'var(--color-text-primary)',
              fontSize: '0.8125rem',
              outline: 'none',
              width: isMobile ? '100%' : 140,
              minWidth: 100,
            }}
          />

          <label style={{ display: 'flex', alignItems: 'center', gap: '0.375rem', cursor: 'pointer', fontSize: '0.8125rem', color: 'var(--color-text-secondary)' }}>
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={(e) => setAutoScroll(e.target.checked)}
            />
            {t('logs.autoScroll')}
          </label>

          <button
            onClick={clearLogs}
            style={{
              padding: '0.375rem 0.75rem',
              borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--color-border)',
              background: 'transparent',
              color: 'var(--color-text-secondary)',
              cursor: 'pointer',
              fontSize: '0.8125rem',
            }}
          >
            {t('logs.clear')}
          </button>
        </div>
      </div>

      {/* Log Viewer */}
      <motion.div
        className="glass-card"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        ref={containerRef}
        style={{
          flex: 1,
          padding: '1rem',
          overflow: 'auto',
          fontFamily: '"JetBrains Mono", "Fira Code", monospace',
          fontSize: isMobile ? '0.6875rem' : '0.75rem',
          lineHeight: 1.8,
        }}
      >
        {filteredLogs.length === 0 ? (
          <div style={{ textAlign: 'center', color: 'var(--color-text-muted)', paddingTop: '3rem' }}>
            {connected ? t('logs.empty') : t('logs.connecting')}
          </div>
        ) : (
          filteredLogs.map((entry: LogEntry, i: number) => (
            <div key={i} style={{ display: 'flex', gap: '0.5rem', padding: '0.125rem 0', flexWrap: isMobile ? 'wrap' : 'nowrap' }}>
              <span style={{ color: 'var(--color-text-muted)', minWidth: isMobile ? 60 : 80, flexShrink: 0 }}>
                {entry.timestamp ? new Date(entry.timestamp).toLocaleTimeString() : '--:--:--'}
              </span>
              <span style={{
                color: LEVEL_COLORS[entry.level?.toUpperCase()] || 'var(--color-text-secondary)',
                minWidth: 56,
                fontWeight: 600,
                flexShrink: 0,
              }}>
                {entry.level?.toUpperCase() || 'INFO'}
              </span>
              {!isMobile && (
                <span style={{ color: 'var(--color-accent-blue)', minWidth: 80, flexShrink: 0 }}>
                  {entry.server_id || 'Bot'}
                </span>
              )}
              <span style={{ color: 'var(--color-text-primary)', flex: 1, wordBreak: 'break-all', minWidth: 0 }}>
                {isMobile && entry.server_id ? `[${entry.server_id}] ` : ''}{entry.message}
              </span>
            </div>
          ))
        )}
      </motion.div>
    </div>
  );
}
