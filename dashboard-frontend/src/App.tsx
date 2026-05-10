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
import UserPortal from './pages/admin/UserPortal';
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

            {/* Server Admin routes — guild sub-pages */}
            <Route path="/guild/:guildId/*" element={<GuildLayout />} />

            {/* General User routes */}
            <Route path="/me/*" element={<UserPortalWrapper />} />
          </Route>

          {/* Catch-all redirect */}
          <Route path="*" element={<Navigate to="/admin" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
