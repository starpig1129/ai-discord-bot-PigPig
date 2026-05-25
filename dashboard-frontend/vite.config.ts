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
      // Proxy all auth endpoints (including exchange, login, refresh, logout, me) to the backend.
      '/auth': 'http://127.0.0.1:8005',
      '/ws': {
        target: 'ws://127.0.0.1:8005',
        ws: true,
      },
    },
  },
})

