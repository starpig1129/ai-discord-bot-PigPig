import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8005',
      // Proxy all auth endpoints to the backend. The backend handles the Discord
      // callback and exchanges the code, then redirects to the frontend /callback
      '/auth/discord/login': 'http://127.0.0.1:8005',
      '/auth/discord/callback': 'http://127.0.0.1:8005',
      '/auth/refresh': 'http://127.0.0.1:8005',
      '/auth/logout': 'http://127.0.0.1:8005',
      '/auth/me': 'http://127.0.0.1:8005',
      '/ws': {
        target: 'ws://127.0.0.1:8005',
        ws: true,
      },
    },
  },
})

