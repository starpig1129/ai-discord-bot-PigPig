import { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../lib/api';

export default function AuthCallback() {
  const navigate = useNavigate();
  const handled = useRef(false);

  useEffect(() => {
    if (handled.current) return;
    handled.current = true;

    const params = new URLSearchParams(window.location.search);
    const code = params.get('code');
    const accessToken = params.get('access_token');

    if (code) {
      // New SPA flow: Discord redirected here with ?code=
      // POST the code to backend to exchange for JWT
      const redirectUri = `${window.location.origin}/callback`;
      api
        .post('/auth/discord/exchange', { code, redirect_uri: redirectUri })
        .then(({ data }) => {
          localStorage.setItem('access_token', data.access_token);
          localStorage.setItem('user', JSON.stringify(data.user));
          navigate('/admin', { replace: true });
        })
        .catch(() => {
          navigate('/login', { replace: true });
        });
    } else if (accessToken) {
      // Legacy flow fallback: token passed directly in URL
      localStorage.setItem('access_token', accessToken);
      navigate('/admin', { replace: true });
    } else {
      const stored = localStorage.getItem('access_token');
      navigate(stored ? '/admin' : '/login', { replace: true });
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
