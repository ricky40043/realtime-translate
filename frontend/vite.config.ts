import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    hmr: {
      clientPort: 5173
    },
    // 允許外部 host 訪問
    cors: true,
    // 允許的 host
    allowedHosts: ['localhost', '04537c7e118f.ngrok-free.app', '.ngrok-free.app']
  }
})
