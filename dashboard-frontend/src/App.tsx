import { type ReactNode } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import Layout from './components/Layout';
import Login from './pages/Login';
import AuthCallback from './pages/AuthCallback';
import Dashboard from './pages/admin/Dashboard';
import Stats from './pages/admin/Stats';
import Config from './pages/admin/Config';
import Guilds from './pages/admin/Guilds';
import Logs from './pages/admin/Logs';
import Update from './pages/admin/Update';
import Users from './pages/admin/Users';
import NotFound from './pages/NotFound';
import Forbidden from './pages/Forbidden';

import GuildLayout from './pages/admin/GuildLayout';
import GuildOverview from './pages/admin/guild/Overview';
import GuildChannels from './pages/admin/guild/Channels';
import GuildPrompt from './pages/admin/guild/Prompt';
import GuildStats from './pages/admin/guild/GuildStats';
import UserPortal from './pages/admin/UserPortal';
import UserProfile from './pages/admin/user/Profile';
import UserMemory from './pages/admin/user/Memory';
import UserStatsPage from './pages/admin/user/UserStats';
import DeleteData from './pages/admin/user/DeleteData';
import { useAuth } from './hooks/useAuth';
import { getStoredUser } from './lib/auth';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
    },
  },
});

function UserPortalWrapper() {
  const { user } = useAuth();
  if (!user) return null;
  return <UserPortal user={user} />;
}

function RequireOwner({ children }: { children: ReactNode }) {
  const stored = getStoredUser();
  if (!stored || stored.role !== 'owner') return <Forbidden />;
  return <>{children}</>;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/callback" element={<AuthCallback />} />

          {/* Protected routes inside Layout */}
          <Route element={<Layout />}>
            {/* Admin (Bot Owner) routes */}
            <Route path="/admin" element={<Dashboard />} />
            <Route path="/admin/stats" element={<Stats />} />
            <Route path="/admin/config" element={<RequireOwner><Config /></RequireOwner>} />
            <Route path="/admin/guilds" element={<Guilds />} />
            <Route path="/admin/logs" element={<RequireOwner><Logs /></RequireOwner>} />
            <Route path="/admin/update" element={<RequireOwner><Update /></RequireOwner>} />
            <Route path="/admin/users" element={<RequireOwner><Users /></RequireOwner>} />


            {/* Server Admin routes — GuildLayout uses Outlet */}
            <Route path="/guild/:guildId" element={<GuildLayout />}>
              <Route index element={<GuildOverview />} />
              <Route path="channels" element={<GuildChannels />} />
              <Route path="prompt" element={<GuildPrompt />} />
              <Route path="stats" element={<GuildStats />} />
            </Route>

            {/* General User routes — UserPortal uses Outlet */}
            <Route path="/me" element={<UserPortalWrapper />}>
              <Route index element={<UserProfile />} />
              <Route path="stats" element={<UserStatsPage />} />
              <Route path="memory" element={<UserMemory />} />
              <Route path="delete" element={<DeleteData />} />
            </Route>
          </Route>

          {/* Catch-all: show 404 page */}
          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
