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

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/callback" element={<AuthCallback />} />

          {/* Protected admin routes */}
          <Route element={<Layout />}>
            <Route path="/admin" element={<Dashboard />} />
            <Route path="/admin/stats" element={<Stats />} />
            <Route path="/admin/config" element={<Config />} />
            <Route path="/admin/guilds" element={<Guilds />} />
            <Route path="/admin/logs" element={<Logs />} />
            <Route path="/admin/update" element={<Update />} />
          </Route>

          {/* Catch-all redirect */}
          <Route path="*" element={<Navigate to="/admin" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
