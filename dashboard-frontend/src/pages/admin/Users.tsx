import { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import api from '../../lib/api';


interface UserSummary {
  discord_id: string;
  discord_name: string;
  display_names: string[];
  created_at: string | null;
  has_memory: boolean;
}

interface UserDetail {
  discord_id: string;
  discord_name: string;
  display_names: string[];
  procedural_memory: string | null;
  user_background: string | null;
  created_at: string | null;
  guild_stats: {
    guild_id: string;
    guild_name?: string;
    total_messages: number;
    streak_days: number;
    last_active_at: string | null;
    first_message_at: string | null;
    channel_memories: Record<string, string>;
  }[];
}

export default function Users() {
  const { t } = useTranslation();
  const [search, setSearch] = useState('');

  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [page, setPage] = useState(0);
  const [selectedUser, setSelectedUser] = useState<UserDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);
  const [deleteMsg, setDeleteMsg] = useState('');
  const [isDeleting, setIsDeleting] = useState(false);
  const LIMIT = 50;

   const timerRef = useRef<number | null>(null);
   const msgTimerRef = useRef<number | null>(null);

   useEffect(() => {
     return () => {
       if (timerRef.current) clearTimeout(timerRef.current);
       if (msgTimerRef.current) clearTimeout(msgTimerRef.current);
     };
   }, []);
  
  // Debounce search input
  const handleSearchChange = (val: string) => {
    setSearch(val);
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      setDebouncedSearch(val);
      setPage(0);
    }, 400);
  };

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['admin-users', debouncedSearch, page],
    queryFn: () =>
      api
        .get(`/api/admin/users?limit=${LIMIT}&offset=${page * LIMIT}&search=${encodeURIComponent(debouncedSearch)}`)
        .then((r) => r.data as { users: UserSummary[]; total: number }),
  });

  const openDetail = async (userId: string) => {
    setDetailLoading(true);
    try {
      const res = await api.get(`/api/admin/users/${userId}`);
      setSelectedUser(res.data as UserDetail);
    } catch (err: unknown) {
      console.error('Failed to fetch user:', err);
      setSelectedUser(null);
    } finally {
      setDetailLoading(false);
    }
  };

  const handleDelete = async (userId: string) => {
    setIsDeleting(true);
    try {
      await api.delete(`/api/admin/users/${userId}/memory`, { data: { confirm: true } });
      setDeleteMsg(t('admin.deleteSuccess', { id: userId }));
      if (msgTimerRef.current) clearTimeout(msgTimerRef.current);
      msgTimerRef.current = setTimeout(() => setDeleteMsg(''), 5000);
      setDeleteConfirm(null);
      setSelectedUser(null);
      refetch();
    } catch {
      setDeleteMsg(t('admin.deleteFailed'));
      if (msgTimerRef.current) clearTimeout(msgTimerRef.current);
      msgTimerRef.current = setTimeout(() => setDeleteMsg(''), 5000);
    } finally {
      setIsDeleting(false);
    }
  };

  const totalPages = data ? Math.ceil(data.total / LIMIT) : 0;

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
        <h1 style={{ fontSize: '1.75rem', fontWeight: 700 }}>👥 {t('admin.usersTitle')}</h1>
        <span style={{ color: 'var(--color-text-muted)', fontSize: '0.875rem' }}>
          {data?.total ?? 0} {t('admin.usersWithMemory')}
        </span>
      </div>

      {/* Search */}
      <input
        type="text"
        placeholder={t('admin.searchPlaceholder')}
        value={search}

        onChange={(e) => handleSearchChange(e.target.value)}
        style={{
          width: '100%',
          padding: '0.625rem 1rem',
          borderRadius: 'var(--radius-md)',
          border: '1px solid var(--color-border)',
          background: 'var(--color-bg-secondary)',
          color: 'var(--color-text-primary)',
          fontSize: '0.875rem',
          marginBottom: '1.5rem',
          outline: 'none',
        }}
      />

      {deleteMsg && (
        <div style={{ padding: '0.75rem 1rem', borderRadius: 'var(--radius-md)', background: 'rgba(16,185,129,0.1)',
          border: '1px solid rgba(16,185,129,0.3)', color: '#10b981', fontSize: '0.875rem', marginBottom: '1rem' }}>
          {deleteMsg}
        </div>
      )}

      {/* User Table */}
      <div className="glass-card" style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem', minWidth: 600 }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
              {[t('user.discordId'), t('user.discordName'), t('user.nicknames'), t('dashboard.lastUpdated'), t('user.memory'), ''].map((h) => (
                <th key={h} style={{ padding: '0.875rem 1rem', textAlign: 'left',
                  color: 'var(--color-text-muted)', fontWeight: 500, fontSize: '0.75rem', textTransform: 'uppercase' }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>

          <tbody>
            {isLoading ? (
              <tr><td colSpan={6} style={{ padding: '2rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>{t('common.loading')}</td></tr>
            ) : (data?.users ?? []).map((u, i) => (
              <motion.tr
                key={u.discord_id}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: i * 0.03 }}
                style={{ borderBottom: '1px solid rgba(148,163,184,0.06)', cursor: 'pointer' }}
                onClick={() => openDetail(u.discord_id)}
                onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(148,163,184,0.05)')}
                onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
              >
                <td style={{ padding: '0.875rem 1rem', fontFamily: 'monospace', fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
                  {u.discord_id}
                </td>
                <td style={{ padding: '0.875rem 1rem', fontWeight: 500 }}>{u.discord_name || '—'}</td>
                <td style={{ padding: '0.875rem 1rem', color: 'var(--color-text-muted)', fontSize: '0.8125rem' }}>
                  {u.display_names.slice(0, 2).join(', ')}{u.display_names.length > 2 ? ` +${u.display_names.length - 2}` : ''}
                </td>
                <td style={{ padding: '0.875rem 1rem', color: 'var(--color-text-muted)', fontSize: '0.8125rem' }}>
                  {u.created_at ? new Date(u.created_at).toLocaleDateString() : '—'}
                </td>
                <td style={{ padding: '0.875rem 1rem' }}>
                  <span style={{
                    padding: '0.2rem 0.5rem', borderRadius: '9999px', fontSize: '0.7rem', fontWeight: 600,
                    background: u.has_memory ? 'rgba(16,185,129,0.15)' : 'rgba(148,163,184,0.1)',
                    color: u.has_memory ? '#10b981' : 'var(--color-text-muted)',
                  }}>
                    {u.has_memory ? t('common.yes') : t('common.no')}
                  </span>
                </td>
                <td style={{ padding: '0.875rem 1rem' }}>
                  <button
                    onClick={(e) => { e.stopPropagation(); setDeleteConfirm(u.discord_id); }}
                    style={{
                      padding: '0.3rem 0.75rem', borderRadius: 'var(--radius-sm)', fontSize: '0.75rem',
                      background: 'rgba(244,63,94,0.1)', border: '1px solid rgba(244,63,94,0.3)',
                      color: '#f43f5e', cursor: 'pointer',
                    }}
                  >
                    {t('admin.deleteUserMemory')}
                  </button>
                </td>

              </motion.tr>
            ))}
          </tbody>
        </table>
        </div>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div style={{ display: 'flex', justifyContent: 'center', gap: '0.5rem', marginTop: '1rem' }}>
          <button onClick={() => setPage(Math.max(0, page - 1))} disabled={page === 0}
            style={{ padding: '0.4rem 0.875rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--color-border)',
              background: 'transparent', color: page === 0 ? 'var(--color-text-muted)' : 'var(--color-text-primary)', cursor: page === 0 ? 'default' : 'pointer' }}>
            ←
          </button>
          <span style={{ padding: '0.4rem 0.875rem', color: 'var(--color-text-muted)', fontSize: '0.875rem' }}>
            {page + 1} / {totalPages}
          </span>
          <button onClick={() => setPage(Math.min(totalPages - 1, page + 1))} disabled={page >= totalPages - 1}
            style={{ padding: '0.4rem 0.875rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--color-border)',
              background: 'transparent', color: page >= totalPages - 1 ? 'var(--color-text-muted)' : 'var(--color-text-primary)', cursor: page >= totalPages - 1 ? 'default' : 'pointer' }}>
            →
          </button>
        </div>
      )}

      {/* Delete Confirm Modal */}
      <AnimatePresence>
        {deleteConfirm && (
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', display: 'flex',
              alignItems: 'center', justifyContent: 'center', zIndex: 100 }}
            onClick={() => setDeleteConfirm(null)}
          >
            <motion.div
              initial={{ scale: 0.9, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.9, opacity: 0 }}
              className="glass-card"
              style={{ padding: '2rem', width: 380, maxWidth: '90vw' }}
              onClick={(e) => e.stopPropagation()}
            >
              <h3 style={{ fontSize: '1.125rem', fontWeight: 700, marginBottom: '0.5rem', color: '#f43f5e' }}>
                ⚠️ {t('admin.deleteUserMemory')}
              </h3>
              <p style={{ color: 'var(--color-text-muted)', fontSize: '0.875rem', marginBottom: '1.5rem' }}>
                {t('admin.deleteUserMemoryDesc', { id: deleteConfirm })}
              </p>
              <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}>
                <button onClick={() => setDeleteConfirm(null)}
                  style={{ padding: '0.5rem 1rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--color-border)',
                    background: 'transparent', color: 'var(--color-text-secondary)', cursor: 'pointer' }}>
                  {t('common.cancel')}
                </button>
                <button
                  onClick={() => handleDelete(deleteConfirm)}
                  disabled={isDeleting}
                  style={{
                    padding: '0.5rem 1rem',
                    borderRadius: 'var(--radius-sm)',
                    border: 'none',
                    background: isDeleting ? 'rgba(244,63,94,0.5)' : '#f43f5e',
                    color: 'white',
                    cursor: isDeleting ? 'not-allowed' : 'pointer',
                    fontWeight: 600,
                    opacity: isDeleting ? 0.7 : 1,
                  }}>
                  {isDeleting ? '...' : t('admin.deleteUserMemory')}
                </button>
              </div>

            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* User Detail Side Panel */}
      <AnimatePresence>
        {(selectedUser || detailLoading) && (
          <motion.div
            initial={{ x: '100%' }} animate={{ x: 0 }} exit={{ x: '100%' }}
            transition={{ type: 'spring', stiffness: 300, damping: 30 }}
            style={{
              position: 'fixed', top: 0, right: 0, bottom: 0, width: 480, maxWidth: '90vw',
              background: 'var(--color-bg-secondary)', borderLeft: '1px solid var(--color-border)',
              zIndex: 50, overflowY: 'auto', padding: '1.5rem',
            }}
          >
            <button onClick={() => setSelectedUser(null)}
              style={{ background: 'none', border: 'none', color: 'var(--color-text-muted)', cursor: 'pointer',
                fontSize: '1.25rem', marginBottom: '1rem' }}>
              ✕
            </button>
            {detailLoading ? (
              <div style={{ textAlign: 'center', color: 'var(--color-text-muted)', paddingTop: '4rem' }}>Loading...</div>
            ) : selectedUser && (
              <>
                <h2 style={{ fontSize: '1.25rem', fontWeight: 700, marginBottom: '0.25rem' }}>
                  {selectedUser.discord_name || selectedUser.discord_id}
                </h2>
                <p style={{ color: 'var(--color-text-muted)', fontSize: '0.8125rem', marginBottom: '1.5rem', fontFamily: 'monospace' }}>
                  ID: {selectedUser.discord_id}
                </p>

                {selectedUser.display_names.length > 0 && (
                  <div style={{ marginBottom: '1.5rem' }}>
                    <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', textTransform: 'uppercase',
                      letterSpacing: '0.05em', marginBottom: '0.5rem' }}>{t('user.nicknames')}</div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.375rem' }}>

                      {selectedUser.display_names.map((n) => (
                        <span key={n} style={{ padding: '0.2rem 0.5rem', borderRadius: '9999px', fontSize: '0.8125rem',
                          background: 'rgba(59,130,246,0.1)', color: 'var(--color-accent-blue)' }}>{n}</span>
                      ))}
                    </div>
                  </div>
                )}

                {selectedUser.procedural_memory && (
                  <div style={{ marginBottom: '1.5rem' }}>
                    <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', textTransform: 'uppercase',
                      letterSpacing: '0.05em', marginBottom: '0.5rem' }}>{t('user.proceduralMemory')}</div>
                    <div style={{ padding: '0.875rem', background: 'rgba(0,0,0,0.2)', borderRadius: 'var(--radius-md)',

                      fontSize: '0.8125rem', lineHeight: 1.6, whiteSpace: 'pre-wrap', maxHeight: 200, overflowY: 'auto' }}>
                      {selectedUser.procedural_memory}
                    </div>
                  </div>
                )}

                {selectedUser.user_background && (
                  <div style={{ marginBottom: '1.5rem' }}>
                    <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', textTransform: 'uppercase',
                      letterSpacing: '0.05em', marginBottom: '0.5rem' }}>{t('user.background')}</div>
                    <div style={{ padding: '0.875rem', background: 'rgba(0,0,0,0.2)', borderRadius: 'var(--radius-md)',

                      fontSize: '0.8125rem', lineHeight: 1.6, whiteSpace: 'pre-wrap', maxHeight: 200, overflowY: 'auto' }}>
                      {selectedUser.user_background}
                    </div>
                  </div>
                )}

                {selectedUser.guild_stats.length > 0 && (
                  <div style={{ marginBottom: '1.5rem' }}>
                    <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', textTransform: 'uppercase',
                      letterSpacing: '0.05em', marginBottom: '0.75rem' }}>{t('admin.guildActivity')} ({selectedUser.guild_stats.length})</div>
                    {selectedUser.guild_stats.map((gs) => (
                      <div key={gs.guild_id} style={{ padding: '0.75rem', background: 'rgba(0,0,0,0.15)',
                        borderRadius: 'var(--radius-md)', marginBottom: '0.5rem', fontSize: '0.8125rem' }}>
                        <div style={{ fontWeight: 600, marginBottom: '0.25rem' }}>{gs.guild_name || gs.guild_id}</div>
                        <div style={{ fontFamily: 'monospace', color: 'var(--color-text-muted)', fontSize: '0.75rem' }}>{gs.guild_id}</div>
                        <div style={{ display: 'flex', gap: '1rem', marginTop: '0.375rem', flexWrap: 'wrap' }}>
                          <span>💬 {gs.total_messages} {t('admin.messages')}</span>
                          <span>🔥 {gs.streak_days}{t('admin.streak')}</span>
                          {gs.last_active_at && (
                            <span style={{ color: 'var(--color-text-muted)' }}>
                              {t('admin.lastActive')}: {new Date(gs.last_active_at).toLocaleDateString()}
                            </span>
                          )}
                        </div>
                        {Object.entries(gs.channel_memories).length > 0 && (
                          <div style={{ marginTop: '0.75rem', borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '0.5rem' }}>
                            {Object.entries(gs.channel_memories).map(([cid, mem]) => (
                              <div key={cid} style={{ marginBottom: '0.5rem' }}>
                                <div style={{ fontSize: '0.65rem', color: 'var(--color-accent-blue)', opacity: 0.8 }}>#{cid}</div>
                                <div style={{ fontSize: '0.75rem', color: 'var(--color-text-secondary)', lineHeight: 1.4,
                                  background: 'rgba(0,0,0,0.1)', padding: '0.4rem', borderRadius: '4px' }}>{mem}</div>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                <button
                  onClick={() => setDeleteConfirm(selectedUser.discord_id)}
                  style={{ width: '100%', padding: '0.625rem', borderRadius: 'var(--radius-md)',
                    background: 'rgba(244,63,94,0.1)', border: '1px solid rgba(244,63,94,0.3)',
                    color: '#f43f5e', cursor: 'pointer', fontWeight: 600, fontSize: '0.875rem' }}>
                  🗑️ {t('admin.deleteUserMemory')}
                </button>

              </>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
