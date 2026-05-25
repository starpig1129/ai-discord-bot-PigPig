/** Discord OAuth2 helpers */

const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '';

export function loginWithDiscord(): void {
  window.location.href = `${API_BASE}/auth/discord/login`;
}

export function logout(): void {
  fetch(`${API_BASE}/auth/logout`, { method: 'POST', credentials: 'include' }).catch(() => {});
  localStorage.removeItem('access_token');
  localStorage.removeItem('user');
  window.location.href = '/login';
}

export interface User {
  id: string;
  username: string;
  avatar: string;
  role: 'owner' | 'admin' | 'user';
  guild_ids: string[];
  admin_guild_ids?: string[];
}

export function getStoredUser(): User | null {
  const raw = localStorage.getItem('user');
  if (!raw) return null;
  try {
    return JSON.parse(raw) as User;
  } catch {
    return null;
  }
}

export function getAvatarUrl(user: User): string {
  if (!user.avatar) return `https://cdn.discordapp.com/embed/avatars/${parseInt(user.id) % 5}.png`;
  return `https://cdn.discordapp.com/avatars/${user.id}/${user.avatar}.png`;
}
