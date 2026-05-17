import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import { useMeme } from '../hooks/useMeme';

function MemeSkeleton() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
      <motion.div
        animate={{ opacity: [0.3, 0.7, 0.3] }}
        transition={{ duration: 1.2, repeat: Infinity }}
        style={{ height: 220, borderRadius: 'var(--radius-md)', background: 'rgba(244,63,94,0.08)' }}
      />
      <motion.div
        animate={{ opacity: [0.3, 0.7, 0.3] }}
        transition={{ duration: 1.2, repeat: Infinity, delay: 0.2 }}
        style={{ height: 16, width: '70%', borderRadius: 'var(--radius-sm)', background: 'rgba(148,163,184,0.1)' }}
      />
      <motion.div
        animate={{ opacity: [0.3, 0.7, 0.3] }}
        transition={{ duration: 1.2, repeat: Infinity, delay: 0.4 }}
        style={{ height: 13, width: '40%', borderRadius: 'var(--radius-sm)', background: 'rgba(148,163,184,0.07)' }}
      />
    </div>
  );
}

export default function Forbidden() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const { meme, loading, error, refresh } = useMeme(['mildlyinfuriating', 'dankmemes']);

  return (
    <div style={{
      minHeight: 'calc(100vh - 4rem)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '2rem',
      position: 'relative',
      overflow: 'hidden',
    }}>
      {/* Rose ambient glow */}
      <div style={{
        position: 'absolute',
        width: 480,
        height: 480,
        borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(244,63,94,0.06) 0%, transparent 65%)',
        top: '50%',
        left: '50%',
        transform: 'translate(-50%, -50%)',
        pointerEvents: 'none',
      }} />

      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
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
        {/* Left: 403 info */}
        <div style={{ flex: '1 1 280px', maxWidth: 400, textAlign: 'center' }}>
          {/* Lock + bounced pig animation */}
          <div style={{ fontSize: '4rem', lineHeight: 1, marginBottom: '0.25rem' }}>
            <motion.span
              animate={{ rotate: [-8, 8, -8, 0] }}
              transition={{ duration: 0.5, repeat: Infinity, repeatDelay: 2.5 }}
              style={{ display: 'inline-block' }}
            >
              🔒
            </motion.span>
          </div>

          <motion.div
            initial={{ x: -30, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            transition={{ delay: 0.25, duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
            style={{ fontSize: '2.5rem', marginBottom: '0.75rem' }}
          >
            🐷💨
          </motion.div>

          <motion.h1
            initial={{ scale: 0.6, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ duration: 0.55, delay: 0.15, ease: [0.16, 1, 0.3, 1] }}
            style={{
              fontSize: 'clamp(5rem, 16vw, 9rem)',
              fontWeight: 900,
              lineHeight: 1,
              letterSpacing: '-0.05em',
              marginBottom: '0.25rem',
              background: 'linear-gradient(135deg, #f43f5e, #fb923c)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              backgroundClip: 'text',
            }}
          >
            403
          </motion.h1>

          <motion.h2
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.35 }}
            style={{ fontSize: '1.4rem', fontWeight: 700, color: 'var(--color-text-primary)', marginBottom: '0.625rem' }}
          >
            {t('forbidden.title')}
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
            {t('forbidden.subtitle')}
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.65 }}
            style={{ display: 'flex', gap: '0.75rem', justifyContent: 'center', flexWrap: 'wrap' }}
          >
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.96 }}
              onClick={() => navigate(-1)}
              style={{
                background: 'rgba(148,163,184,0.1)',
                color: 'var(--color-text-secondary)',
                border: '1px solid var(--color-border)',
                padding: '0.8125rem 1.5rem',
                borderRadius: 'var(--radius-lg)',
                fontSize: '0.9375rem',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              ← {t('forbidden.goBack')}
            </motion.button>

            <motion.button
              whileHover={{ scale: 1.05, boxShadow: '0 0 24px rgba(59,130,246,0.35)' }}
              whileTap={{ scale: 0.96 }}
              onClick={() => navigate('/admin')}
              style={{
                background: 'linear-gradient(135deg, var(--color-gradient-start), var(--color-gradient-end))',
                color: 'white',
                border: 'none',
                padding: '0.8125rem 1.5rem',
                borderRadius: 'var(--radius-lg)',
                fontSize: '0.9375rem',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              🏠 {t('forbidden.goHome')}
            </motion.button>
          </motion.div>
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
            border: '1px solid rgba(244,63,94,0.2)',
            borderRadius: 'var(--radius-xl)',
            padding: '1.25rem',
            backdropFilter: 'blur(12px)',
          }}
        >
          <p style={{
            fontSize: '0.75rem',
            color: 'rgba(244,63,94,0.8)',
            background: 'rgba(244,63,94,0.08)',
            padding: '0.2rem 0.6rem',
            borderRadius: 'var(--radius-sm)',
            display: 'inline-block',
            fontWeight: 600,
            textTransform: 'uppercase',
            letterSpacing: '0.08em',
            marginBottom: '0.875rem',
          }}>
            {t('forbidden.memeTitle')}
          </p>

          {loading && <MemeSkeleton />}

          {!loading && error && (
            <div style={{
              height: 180,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '0.5rem',
              color: 'var(--color-text-muted)',
              fontSize: '0.875rem',
            }}>
              <span style={{ fontSize: '2.5rem' }}>🚫</span>
              {t('forbidden.memeError')}
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
                  maxHeight: 280,
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
                  color: 'rgba(244,63,94,0.9)',
                  background: 'rgba(244,63,94,0.1)',
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
                background: 'rgba(244,63,94,0.08)',
                border: '1px solid rgba(244,63,94,0.2)',
                borderRadius: 'var(--radius-sm)',
                color: 'rgba(244,63,94,0.9)',
                fontSize: '0.75rem',
                fontWeight: 600,
                padding: '0.3rem 0.75rem',
                cursor: loading ? 'not-allowed' : 'pointer',
                opacity: loading ? 0.5 : 1,
              }}
            >
              {t('forbidden.refresh')}
            </motion.button>
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}
