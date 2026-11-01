import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The API runs on :8000 (`drishti serve`); in production FastAPI serves web/dist itself.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
  build: { chunkSizeWarningLimit: 2000 },
})
