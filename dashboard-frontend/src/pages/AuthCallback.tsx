import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

/**
 * OAuth callback handler — extracts access_token from the URL query parameters
 * (provided by backend redirect) and redirects to admin dashboard.
 */
export default function AuthCallback() {
  const navigate = useNavigate();

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const accessToken = params.get('access_token');

    if (accessToken) {
      // First invocation: token is in URL — store it and navigate
      localStorage.setItem('access_token', accessToken);
      console.log('[AuthCallback] Token stored, navigating to /admin');
      navigate('/admin', { replace: true });
    } else {
      // Second invocation (React StrictMode double-invoke) or direct visit:
      // check if token was already stored by the first invocation
      const stored = localStorage.getItem('access_token');
      if (stored) {
        console.log('[AuthCallback] Token already in storage, navigating to /admin');
        navigate('/admin', { replace: true });
      } else {
        console.warn('[AuthCallback] No token found — redirecting to /login');
        navigate('/login', { replace: true });
      }
    }
  }, [navigate]);

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'var(--color-bg-primary)',
      flexDirection: 'column',
      gap: '1rem',
      color: 'white',
    }}>
      <div className="animate-pulse-glow" style={{ fontSize: '3rem' }}>🐷</div>
      <p style={{ opacity: 0.5, fontSize: '0.875rem' }}>Processing login…</p>
    </div>
  );
}

