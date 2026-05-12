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
      // Proxy only specific auth endpoints — NOT /auth/discord/callback
      // (that URL is handled by React Router /callback page)
      '/auth/discord/login': 'http://127.0.0.1:8005',
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

