import { motion } from 'framer-motion';
import { loginWithDiscord } from '../lib/auth';

export default function Login() {
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
          PigPig Dashboard
        </h1>
        <p style={{
          color: 'var(--color-text-secondary)',
          fontSize: '0.875rem',
          marginBottom: '2.5rem',
          lineHeight: 1.6,
        }}>
          Sign in with your Discord account to manage your bot.
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
          <svg width="24" height="24" viewBox="0 0 71 55" fill="none">
            <path d="M60.1045 4.8978C55.5792 2.8214 50.7265 1.2916 45.6527 0.41542C45.5603 0.39851 45.468 0.440769 45.4204 0.525289C44.7963 1.6353 44.105 3.0834 43.6209 4.2216C38.1637 3.4046 32.7345 3.4046 27.3892 4.2216C26.905 3.0581 26.1886 1.6353 25.5617 0.525289C25.5141 0.443589 25.4218 0.40133 25.3294 0.41542C20.2584 1.2888 15.4057 2.8186 10.8776 4.8978C10.8384 4.9147 10.8048 4.9429 10.7825 4.9795C1.57795 18.7309 -0.943561 32.1443 0.293408 45.3914C0.299005 45.4562 0.335386 45.5182 0.385761 45.5576C6.45866 50.0174 12.3413 52.7249 18.1147 54.5195C18.2071 54.5477 18.305 54.5139 18.3638 54.4378C19.7295 52.5728 20.9469 50.6063 21.9907 48.5383C22.0523 48.4172 21.9935 48.2735 21.8676 48.2256C19.9366 47.4931 18.0979 46.6 16.3292 45.5858C16.1893 45.5041 16.1781 45.304 16.3068 45.2082C16.679 44.9293 17.0513 44.6391 17.4067 44.3461C17.471 44.2926 17.5606 44.2813 17.6362 44.3151C29.2558 49.6202 41.8354 49.6202 53.3179 44.3151C53.3## 44.2785 53.4eli 44.2898 53.4g 44.3461C53.8680 44.6391 54.2402 44.9293 54.6152 45.2082C54.7440 45.304 54.7355 45.5041 54.5765 45.5858C52.8077 46.6197 50.9722 47.4931 49.0260 48.2228C48.9001 48.2707 48.8441 48.4172 48.9057 48.5383C49.9781 50.6034 51.1955 52.5699 52.5765 54.4350C52.6324 54.5139 52.7331 54.5477 52.8255 54.5195C58.6241 52.7249 64.5068 50.0174 70.5797 45.5576C70.6329 45.5182 70.6665 45.459 70.6721 45.3942C72.1527 30.0791 68.1731 16.7757 60.1968 4.9823C60.1772 4.9429 60.1437 4.9147 60.1045 4.8978ZM23.7259 37.3253C20.2276 37.3253 17.3451 34.1136 17.3451 30.1693C17.3451 26.2250 20.1717 23.0133 23.7259 23.0133C27.308 23.0133 30.1627 26.2532 30.1066 30.1693C30.1066 34.1136 27.2801 37.3253 23.7259 37.3253ZM47.3178 37.3253C43.8196 37.3253 40.9370 34.1136 40.9370 30.1693C40.9370 26.2250 43.7636 23.0133 47.3178 23.0133C50.8999 23.0133 53.7546 26.2532 53.6985 30.1693C53.6985 34.1136 50.8999 37.3253 47.3178 37.3253Z" fill="currentColor"/>
          </svg>
          Continue with Discord
        </motion.button>

        <p style={{
          color: 'var(--color-text-muted)',
          fontSize: '0.75rem',
          marginTop: '1.5rem',
        }}>
          Requires Discord account · Bot Owner access
        </p>
      </motion.div>
    </div>
  );
}
