import { motion } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import { loginWithDiscord } from '../lib/auth';


export default function Login() {
  const { t } = useTranslation();
  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #0f172a 100%)',
      position: 'relative',
      overflow: 'hidden',
    }}>
      {/* Animated background orbs */}
      <div style={{
        position: 'absolute',
        width: 400,
        height: 400,
        borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(59,130,246,0.15), transparent 70%)',
        top: '-10%',
        right: '-5%',
        filter: 'blur(40px)',
      }} />
      <div style={{
        position: 'absolute',
        width: 300,
        height: 300,
        borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(139,92,246,0.12), transparent 70%)',
        bottom: '-5%',
        left: '-5%',
        filter: 'blur(40px)',
      }} />

      <motion.div
        initial={{ opacity: 0, y: 30, scale: 0.95 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
        className="glass-card"
        style={{
          padding: '3rem',
          width: '100%',
          maxWidth: 420,
          textAlign: 'center',
          position: 'relative',
        }}
      >
        {/* Logo */}
        <motion.div
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
          transition={{ delay: 0.2, type: 'spring', stiffness: 200 }}
          style={{ fontSize: '4rem', marginBottom: '1rem' }}
        >
          🐷
        </motion.div>

        <h1
          className="gradient-text"
          style={{ fontSize: '2rem', fontWeight: 700, marginBottom: '0.5rem' }}
        >
          {t('login.title')}
        </h1>
        <p style={{
          color: 'var(--color-text-secondary)',
          fontSize: '0.875rem',
          marginBottom: '2.5rem',
          lineHeight: 1.6,
        }}>
          {t('login.subtitle')}
        </p>

        {/* Discord Login Button */}
        <motion.button
          whileHover={{ scale: 1.02, y: -2 }}
          whileTap={{ scale: 0.98 }}
          onClick={loginWithDiscord}
          style={{
            width: '100%',
            padding: '0.875rem 1.5rem',
            borderRadius: 'var(--radius-md)',
            border: 'none',
            background: '#5865F2',
            color: 'white',
            fontSize: '1rem',
            fontWeight: 600,
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '0.75rem',
            transition: 'all var(--transition-fast)',
            boxShadow: '0 4px 20px rgba(88, 101, 242, 0.3)',
          }}
        >
          <svg width="24" height="24" viewBox="0 0 127.14 96.36" fill="currentColor">
            <path d="M107.7,8.07A105.15,105.15,0,0,0,81.47,0a72.06,72.06,0,0,0-3.36,6.83A97.68,97.68,0,0,0,49,6.83,72.37,72.37,0,0,0,45.64,0,105.89,105.89,0,0,0,19.39,8.09C2.79,32.65-1.71,56.6.54,80.21h0A105.73,105.73,0,0,0,32.71,96.36,77.7,77.7,0,0,0,39.6,85.25a68.42,68.42,0,0,1-10.85-5.18c.91-.66,1.8-1.34,2.66-2a75.57,75.57,0,0,0,64.32,0c.87.71,1.76,1.39,2.66,2a68.68,68.68,0,0,1-10.87,5.19,77,77,0,0,0,6.89,11.1,105.25,105.25,0,0,0,32.19-16.14c0,0,.04-.06.09-.09A71.1,71.1,0,0,0,107.7,8.07ZM42.45,65.69C36.18,65.69,31,60,31,53s5-12.74,11.43-12.74S54,46,53.89,53,48.84,65.69,42.45,65.69Zm42.24,0C78.41,65.69,73.31,60,73.31,53s5-12.74,11.43-12.74S96,46,95.89,53,91.08,65.69,84.69,65.69Z"/>
          </svg>
          {t('login.button')}
        </motion.button>

        <p style={{
          color: 'var(--color-text-muted)',
          fontSize: '0.75rem',
          marginTop: '1.5rem',
        }}>
          {t('login.hint')}
        </p>
      </motion.div>
    </div>
  );
}
