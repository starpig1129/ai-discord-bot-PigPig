import { useState, useRef, useEffect } from 'react';
import { motion } from 'framer-motion';
import { useWebSocket, type LogEntry } from '../../hooks/useWebSocket';

const LEVEL_COLORS: Record<string, string> = {
  DEBUG: '#06b6d4',
  INFO: '#10b981',
  WARNING: '#f59e0b',
  ERROR: '#f43f5e',
  CRITICAL: '#dc2626',
};

export default function Logs() {
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
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 4rem)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <div>
          <h1 style={{ fontSize: '1.75rem', fontWeight: 700 }}>📝 Live Logs</h1>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '0.25rem' }}>
            <span className={`status-dot ${connected ? 'online' : 'offline'}`} />
            <span style={{ color: 'var(--color-text-muted)', fontSize: '0.75rem' }}>
              {connected ? 'Connected' : 'Disconnected'} · {logs.length} entries
            </span>
          </div>
        </div>

        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
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
            <option value="">All Levels</option>
            {Object.keys(LEVEL_COLORS).map((l) => (
              <option key={l} value={l}>{l}</option>
            ))}
          </select>

          <input
            type="text"
            placeholder="Guild ID filter..."
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
              width: 140,
            }}
          />

          <label style={{ display: 'flex', alignItems: 'center', gap: '0.375rem', cursor: 'pointer', fontSize: '0.8125rem', color: 'var(--color-text-secondary)' }}>
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={(e) => setAutoScroll(e.target.checked)}
            />
            Auto-scroll
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
            Clear
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
          fontSize: '0.75rem',
          lineHeight: 1.8,
        }}
      >
        {filteredLogs.length === 0 ? (
          <div style={{ textAlign: 'center', color: 'var(--color-text-muted)', paddingTop: '3rem' }}>
            {connected ? 'Waiting for log entries...' : 'Connecting to log stream...'}
          </div>
        ) : (
          filteredLogs.map((entry: LogEntry, i: number) => (
            <div key={i} style={{ display: 'flex', gap: '0.75rem', padding: '0.125rem 0' }}>
              <span style={{ color: 'var(--color-text-muted)', minWidth: 80 }}>
                {entry.timestamp ? new Date(entry.timestamp).toLocaleTimeString() : '--:--:--'}
              </span>
              <span style={{
                color: LEVEL_COLORS[entry.level?.toUpperCase()] || 'var(--color-text-secondary)',
                minWidth: 60,
                fontWeight: 600,
              }}>
                {entry.level?.toUpperCase() || 'INFO'}
              </span>
              <span style={{ color: 'var(--color-accent-blue)', minWidth: 80 }}>
                {entry.server_id || 'Bot'}
              </span>
              <span style={{ color: 'var(--color-text-primary)', flex: 1, wordBreak: 'break-all' }}>
                {entry.message}
              </span>
            </div>
          ))
        )}
      </motion.div>
    </div>
  );
}
