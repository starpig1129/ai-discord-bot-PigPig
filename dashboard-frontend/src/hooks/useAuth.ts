import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../lib/api';
import { type User, getStoredUser, logout as doLogout } from '../lib/auth';

export function useAuth() {
  const [user, setUser] = useState<User | null>(getStoredUser);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    // Verify current token with backend
    const token = localStorage.getItem('access_token');
    if (!token) {
      setLoading(false);
      return;
    }

    api.get('/auth/me')
      .then(({ data }) => {
        localStorage.setItem('user', JSON.stringify(data));
        setUser(data);
      })
      .catch((err) => {
        const status = err?.response?.status;
        const detail = err?.response?.data?.detail || err?.message;
        console.error(`[useAuth] /auth/me failed — HTTP ${status}: ${detail}`);
        // Only clear token on actual auth failures (401/403)
        // For network errors (no status), keep the token and don't redirect
        if (status === 401 || status === 403) {
          localStorage.removeItem('access_token');
          localStorage.removeItem('user');
          setUser(null);
        } else if (!status) {
          // Network/proxy error — keep token, set user from cached data if available
          const cached = getStoredUser();
          if (cached) setUser(cached);
        }
      })
      .finally(() => setLoading(false));
  }, []);

  const logout = useCallback(() => {
    doLogout();
    setUser(null);
    navigate('/login');
  }, [navigate]);

  return { user, loading, logout, isOwner: user?.role === 'owner' };
}
