import { fileURLToPath, URL } from 'node:url'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

/**
 * Solo desarrollo: `/api` se reenvía al backend local (same-origin, sin CORS). No existe en producción.
 * 127.0.0.1 y no «localhost»: Node resuelve «localhost» a ::1 y uvicorn escucha en IPv4 por defecto.
 */
const DEV_API_PROXY = { '/api': 'http://127.0.0.1:8000' }

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    // «@/features/history» en vez de «../../../features/history»: los límites entre slices se ven en cada import.
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: { proxy: DEV_API_PROXY },
})
