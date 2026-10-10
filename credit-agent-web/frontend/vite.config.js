import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue2'

// Vite 配置：
// - dev 默认端口 5173；外部可通过 npm run dev -- --host 0.0.0.0 --port 7100 透传
// - /api 代理到 SSM 后端（Tomcat 8080，上下文 /credit-web）
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  server: {
    host: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8080/credit-web',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, '')
      }
    }
  },
  build: {
    outDir: 'dist',
    chunkSizeWarningLimit: 1200
  }
})
