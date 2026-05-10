import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
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
            <Route path="/admin/config" element={<Config />} />
            <Route path="/admin/guilds" element={<Guilds />} />
            <Route path="/admin/logs" element={<Logs />} />
            <Route path="/admin/update" element={<Update />} />

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

          {/* Catch-all redirect */}
          <Route path="*" element={<Navigate to="/admin" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
