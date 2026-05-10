import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend, BarChart, Bar,
} from 'recharts';
import api from '../../lib/api';

const COLORS = ['#3b82f6', '#8b5cf6', '#10b981', '#f59e0b', '#f43f5e', '#06b6d4'];

export default function Stats() {
  const [period, setPeriod] = useState('30d');
  const [globalStats, setGlobalStats] = useState<any>(null);
  const [modelStats, setModelStats] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      api.get(`/api/admin/stats/global?period=${period}`),
      api.get(`/api/admin/stats/models?period=${period}`),
    ])
      .then(([g, m]) => {
        setGlobalStats(g.data);
        setModelStats(m.data);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [period]);

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '60vh' }}>
        <div className="animate-pulse-glow" style={{ fontSize: '2rem' }}>📈</div>
      </div>
    );
  }

  const summaryCards = [
    { label: 'Total Messages', value: (globalStats?.total_messages ?? 0).toLocaleString(), icon: '💬', color: 'var(--color-accent-blue)' },
    { label: 'LLM Calls', value: (globalStats?.total_llm_calls ?? 0).toLocaleString(), icon: '🤖', color: 'var(--color-accent-violet)' },
    { label: 'Commands', value: (globalStats?.total_commands ?? 0).toLocaleString(), icon: '⌨️', color: 'var(--color-accent-emerald)' },
    { label: 'Error Rate', value: `${globalStats?.error_rate ?? 0}%`, icon: '⚠️', color: 'var(--color-accent-rose)' },
    { label: 'Avg Response', value: `${globalStats?.avg_response_ms ?? 0}ms`, icon: '⚡', color: 'var(--color-accent-amber)' },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
        <h1 style={{ fontSize: '1.75rem', fontWeight: 700 }}>📈 Statistics</h1>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          {['7d', '30d', '90d'].map((p) => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              style={{
                padding: '0.5rem 1rem',
                borderRadius: 'var(--radius-sm)',
                border: '1px solid',
                borderColor: period === p ? 'var(--color-accent-blue)' : 'var(--color-border)',
                background: period === p ? 'rgba(59,130,246,0.15)' : 'transparent',
                color: period === p ? 'var(--color-accent-blue)' : 'var(--color-text-secondary)',
                cursor: 'pointer',
                fontSize: '0.8125rem',
                fontWeight: 500,
              }}
            >
              {p}
            </button>
          ))}
        </div>
      </div>

      {/* Summary Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: '1rem', marginBottom: '2rem' }}>
        {summaryCards.map((card, i) => (
          <motion.div
            key={card.label}
            className="glass-card"
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.08 }}
            style={{ padding: '1.25rem' }}
          >
            <div style={{ color: 'var(--color-text-muted)', fontSize: '0.75rem', marginBottom: '0.5rem' }}>
              {card.icon} {card.label}
            </div>
            <div style={{ fontSize: '1.5rem', fontWeight: 700 }}>{card.value}</div>
          </motion.div>
        ))}
      </div>

      {/* Message Trend Chart */}
      <motion.div
        className="glass-card"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3 }}
        style={{ padding: '1.5rem', marginBottom: '1.5rem' }}
      >
        <h2 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '1rem' }}>Message Trend</h2>
        <ResponsiveContainer width="100%" height={300}>
          <AreaChart data={globalStats?.daily_messages || []}>
            <defs>
              <linearGradient id="colorMessages" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.1)" />
            <XAxis dataKey="date" stroke="#64748b" fontSize={12} tickLine={false} />
            <YAxis stroke="#64748b" fontSize={12} tickLine={false} />
            <Tooltip
              contentStyle={{
                background: '#1e293b',
                border: '1px solid rgba(148,163,184,0.2)',
                borderRadius: '0.5rem',
                color: '#f1f5f9',
              }}
            />
            <Area type="monotone" dataKey="count" stroke="#3b82f6" strokeWidth={2} fill="url(#colorMessages)" />
          </AreaChart>
        </ResponsiveContainer>
      </motion.div>

      {/* Model Usage */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
        <motion.div
          className="glass-card"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4 }}
          style={{ padding: '1.5rem' }}
        >
          <h2 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '1rem' }}>Model Usage</h2>
          <ResponsiveContainer width="100%" height={250}>
            <PieChart>
              <Pie
                data={(modelStats?.models || []).map((m: any) => ({ name: m.model, value: m.calls }))}
                innerRadius={60}
                outerRadius={90}
                paddingAngle={3}
                dataKey="value"
              >
                {(modelStats?.models || []).map((_: any, i: number) => (
                  <Cell key={i} fill={COLORS[i % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid rgba(148,163,184,0.2)', borderRadius: '0.5rem', color: '#f1f5f9' }} />
              <Legend wrapperStyle={{ color: '#94a3b8', fontSize: '0.75rem' }} />
            </PieChart>
          </ResponsiveContainer>
        </motion.div>

        <motion.div
          className="glass-card"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.5 }}
          style={{ padding: '1.5rem' }}
        >
          <h2 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '1rem' }}>Response Time by Model</h2>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={modelStats?.models || []} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.1)" />
              <XAxis type="number" stroke="#64748b" fontSize={12} />
              <YAxis type="category" dataKey="model" stroke="#64748b" fontSize={11} width={120} />
              <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid rgba(148,163,184,0.2)', borderRadius: '0.5rem', color: '#f1f5f9' }} />
              <Bar dataKey="avg_response_ms" fill="#8b5cf6" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </motion.div>
      </div>
    </div>
  );
}
