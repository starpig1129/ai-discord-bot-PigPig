import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../lib/api';

export default function AuthCallback() {
  const navigate = useNavigate();
  const handled = useRef(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (handled.current) return;
    handled.current = true;

    const params = new URLSearchParams(window.location.search);
    const code = params.get('code');
    const accessToken = params.get('access_token');

    if (code) {
      const redirectUri = `${window.location.origin}/callback`;
      api
        .post('/auth/discord/exchange', { code, redirect_uri: redirectUri })
        .then(({ data }) => {
          localStorage.setItem('access_token', data.access_token);
          localStorage.setItem('user', JSON.stringify(data.user));
          navigate('/admin', { replace: true });
        })
        .catch((err) => {
          const detail = err?.response?.data?.detail ?? err?.message ?? 'Unknown error';
          const status = err?.response?.status ?? 'Network error';
          console.error('[AuthCallback] exchange failed', status, detail);
          setError(`Login failed (${status}): ${detail}`);
          setTimeout(() => navigate('/login', { replace: true }), 4000);
        });
    } else if (accessToken) {
      localStorage.setItem('access_token', accessToken);
      navigate('/admin', { replace: true });
    } else {
      const stored = localStorage.getItem('access_token');
      navigate(stored ? '/admin' : '/login', { replace: true });
    }
  }, [navigate]);

  if (error) {
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
        padding: '2rem',
        textAlign: 'center',
      }}>
        <div style={{ fontSize: '3rem' }}>⚠️</div>
        <p style={{ color: '#f87171', fontWeight: 600 }}>{error}</p>
        <p style={{ opacity: 0.5, fontSize: '0.875rem' }}>Redirecting to login…</p>
      </div>
    );
  }

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
