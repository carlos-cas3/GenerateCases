import { fileURLToPath, URL } from 'node:url'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    // «@/features/history» en vez de «../../../features/history»: los límites entre slices se ven en cada import.
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
})
