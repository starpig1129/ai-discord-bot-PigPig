import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import { useMeme } from '../hooks/useMeme';

// Deterministic star positions (avoid Math.random on every render)
const STARS = Array.from({ length: 30 }, (_, i) => ({
  id: i,
  x: (i * 37 + 11) % 100,
  y: (i * 53 + 7) % 100,
  size: (i % 3) + 1.5,
  duration: (i % 4) + 2.5,
  delay: (i % 5) * 0.4,
  color: i % 3 === 0 ? 'var(--color-accent-violet)' : i % 3 === 1 ? 'var(--color-accent-blue)' : '#e2e8f0',
}));

function MemeSkeleton() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
      <motion.div
        animate={{ opacity: [0.3, 0.7, 0.3] }}
        transition={{ duration: 1.2, repeat: Infinity }}
        style={{ height: 240, borderRadius: 'var(--radius-md)', background: 'rgba(148,163,184,0.12)' }}
      />
      <motion.div
        animate={{ opacity: [0.3, 0.7, 0.3] }}
        transition={{ duration: 1.2, repeat: Infinity, delay: 0.2 }}
        style={{ height: 18, width: '75%', borderRadius: 'var(--radius-sm)', background: 'rgba(148,163,184,0.1)' }}
      />
      <motion.div
        animate={{ opacity: [0.3, 0.7, 0.3] }}
        transition={{ duration: 1.2, repeat: Infinity, delay: 0.4 }}
        style={{ height: 14, width: '45%', borderRadius: 'var(--radius-sm)', background: 'rgba(148,163,184,0.08)' }}
      />
    </div>
  );
}

export default function NotFound() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const { meme, loading, error, refresh } = useMeme(['me_irl', 'dankmemes']);

  return (
    <div style={{
      minHeight: '100vh',
      background: 'var(--color-bg-primary)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      position: 'relative',
      overflow: 'hidden',
      padding: '2rem',
    }}>
      {/* Floating star particles */}
      {STARS.map((star) => (
        <motion.div
          key={star.id}
          animate={{ opacity: [0.1, 0.8, 0.1], scale: [0.7, 1.3, 0.7] }}
          transition={{ duration: star.duration, delay: star.delay, repeat: Infinity, ease: 'easeInOut' }}
          style={{
            position: 'absolute',
            left: `${star.x}%`,
            top: `${star.y}%`,
            width: star.size,
            height: star.size,
            borderRadius: '50%',
            background: star.color,
            pointerEvents: 'none',
          }}
        />
      ))}

      {/* Ambient glow orbs */}
      <div style={{
        position: 'absolute', width: 500, height: 500, borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(59,130,246,0.07) 0%, transparent 70%)',
        top: '10%', left: '0%', pointerEvents: 'none',
      }} />
      <div style={{
        position: 'absolute', width: 400, height: 400, borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(139,92,246,0.07) 0%, transparent 70%)',
        bottom: '10%', right: '0%', pointerEvents: 'none',
      }} />

      {/* Main content */}
      <motion.div
        initial={{ opacity: 0, y: 40 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
        style={{
          position: 'relative',
          zIndex: 1,
          display: 'flex',
          gap: '3rem',
          alignItems: 'center',
          flexWrap: 'wrap',
          justifyContent: 'center',
          maxWidth: 920,
          width: '100%',
        }}
      >
        {/* Left: 404 info */}
        <div style={{ flex: '1 1 280px', maxWidth: 400, textAlign: 'center' }}>
          <motion.div
            animate={{ y: [-10, 10, -10], rotate: [-4, 4, -4] }}
            transition={{ duration: 3.5, repeat: Infinity, ease: 'easeInOut' }}
            style={{ fontSize: '5rem', lineHeight: 1, marginBottom: '0.25rem' }}
          >
            🐷
          </motion.div>

          <motion.div
            animate={{ opacity: [0, 1, 0] }}
            transition={{ duration: 1.8, repeat: Infinity, delay: 0.5 }}
            style={{ fontSize: '1.1rem', letterSpacing: '0.6rem', marginBottom: '0.75rem', color: 'var(--color-text-muted)' }}
          >
            ✨ ❓ ✨
          </motion.div>

          <motion.h1
            initial={{ scale: 0.6, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ duration: 0.6, delay: 0.15, ease: [0.16, 1, 0.3, 1] }}
            className="gradient-text"
            style={{
              fontSize: 'clamp(5rem, 16vw, 9rem)',
              fontWeight: 900,
              lineHeight: 1,
              letterSpacing: '-0.05em',
              marginBottom: '0.25rem',
            }}
          >
            404
          </motion.h1>

          <motion.h2
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.35 }}
            style={{ fontSize: '1.4rem', fontWeight: 700, color: 'var(--color-text-primary)', marginBottom: '0.625rem' }}
          >
            {t('notFound.title')}
          </motion.h2>

          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.5 }}
            style={{
              fontSize: '0.9375rem',
              color: 'var(--color-text-secondary)',
              lineHeight: 1.65,
              marginBottom: '1.75rem',
            }}
          >
            {t('notFound.subtitle')}
          </motion.p>

          <motion.button
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.65 }}
            whileHover={{ scale: 1.06, boxShadow: '0 0 28px rgba(59,130,246,0.4)' }}
            whileTap={{ scale: 0.96 }}
            onClick={() => navigate('/admin')}
            style={{
              background: 'linear-gradient(135deg, var(--color-gradient-start), var(--color-gradient-end))',
              color: 'white',
              border: 'none',
              padding: '0.8125rem 2rem',
              borderRadius: 'var(--radius-lg)',
              fontSize: '0.9375rem',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            🏠 {t('notFound.goHome')}
          </motion.button>
        </div>

        {/* Right: Meme card */}
        <motion.div
          initial={{ opacity: 0, x: 30 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.7, delay: 0.3, ease: [0.16, 1, 0.3, 1] }}
          style={{
            flex: '1 1 300px',
            maxWidth: 420,
            background: 'var(--color-bg-card)',
            border: '1px solid var(--color-border)',
            borderRadius: 'var(--radius-xl)',
            padding: '1.25rem',
            backdropFilter: 'blur(12px)',
          }}
        >
          <p style={{
            fontSize: '0.75rem',
            color: 'var(--color-text-muted)',
            fontWeight: 600,
            textTransform: 'uppercase',
            letterSpacing: '0.08em',
            marginBottom: '0.875rem',
          }}>
            {t('notFound.memeTitle')}
          </p>

          {loading && <MemeSkeleton />}

          {!loading && error && (
            <div style={{
              height: 200,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '0.5rem',
              color: 'var(--color-text-muted)',
              fontSize: '0.875rem',
            }}>
              <span style={{ fontSize: '2.5rem' }}>😿</span>
              {t('notFound.memeError')}
            </div>
          )}

          {!loading && !error && meme && (
            <>
              <img
                src={meme.url}
                alt={meme.title}
                onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                style={{
                  width: '100%',
                  maxHeight: 300,
                  objectFit: 'contain',
                  borderRadius: 'var(--radius-md)',
                  display: 'block',
                  background: 'rgba(0,0,0,0.2)',
                }}
              />
              <p style={{
                fontSize: '0.8125rem',
                color: 'var(--color-text-primary)',
                marginTop: '0.75rem',
                marginBottom: '0.625rem',
                lineHeight: 1.4,
                fontWeight: 500,
              }}>
                {meme.title}
              </p>
            </>
          )}

          {/* Footer: subreddit + upvotes + refresh */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            marginTop: loading ? '0.75rem' : '0',
            flexWrap: 'wrap',
          }}>
            {!loading && !error && meme && (
              <>
                <span style={{
                  fontSize: '0.7rem',
                  color: 'var(--color-accent-blue)',
                  background: 'rgba(59,130,246,0.1)',
                  padding: '0.2rem 0.5rem',
                  borderRadius: 'var(--radius-sm)',
                  fontWeight: 600,
                }}>
                  r/{meme.subreddit}
                </span>
                <span style={{ fontSize: '0.7rem', color: 'var(--color-text-muted)' }}>
                  👍 {meme.ups.toLocaleString()}
                </span>
              </>
            )}
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.94 }}
              onClick={refresh}
              disabled={loading}
              style={{
                marginLeft: 'auto',
                background: 'rgba(148,163,184,0.1)',
                border: '1px solid var(--color-border)',
                borderRadius: 'var(--radius-sm)',
                color: 'var(--color-text-secondary)',
                fontSize: '0.75rem',
                fontWeight: 600,
                padding: '0.3rem 0.75rem',
                cursor: loading ? 'not-allowed' : 'pointer',
                opacity: loading ? 0.5 : 1,
              }}
            >
              {t('notFound.refresh')}
            </motion.button>
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}
