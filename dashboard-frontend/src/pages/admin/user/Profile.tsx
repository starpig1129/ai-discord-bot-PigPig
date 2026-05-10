import { motion } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import { useOutletContext } from 'react-router-dom';
import { type User, getAvatarUrl } from '../../../lib/auth';

interface UserContext {
  user: User;
}

export default function UserProfile() {
  const { user } = useOutletContext<UserContext>();
  const { t } = useTranslation();

  const infoRows = [
    { label: t('user.discordId'), value: user.id || '—' },
    { label: t('user.role'), value: user.role },
    { label: t('user.guildsCount'), value: (user.guild_ids?.length ?? 0).toString() },
  ];

  return (
    <div>
      <motion.div
        className="glass-card"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        style={{ padding: '2rem', maxWidth: 560 }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '1.25rem', marginBottom: '1.5rem' }}>
          <img
            src={getAvatarUrl(user)}
            alt="avatar"
            style={{ width: 72, height: 72, borderRadius: '50%', border: '3px solid var(--color-accent-blue)' }}
          />
          <div>
            <h2 style={{ fontSize: '1.25rem', fontWeight: 700 }}>{user.username}</h2>
            <p style={{ fontSize: '0.8125rem', color: 'var(--color-accent-blue)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              {user.role}
            </p>
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          {infoRows.map(({ label, value }) => (
            <div key={label} style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              padding: '0.625rem 0', borderBottom: '1px solid var(--color-border)',
            }}>
              <span style={{ color: 'var(--color-text-muted)', fontSize: '0.875rem' }}>{label}</span>
              <span style={{ fontWeight: 500, fontSize: '0.875rem', fontFamily: 'monospace' }}>{value}</span>
            </div>
          ))}
        </div>
      </motion.div>
    </div>
  );
}
