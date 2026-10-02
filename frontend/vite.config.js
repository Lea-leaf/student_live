import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// Vite 配置
// - @ 指向 src
// - /api 代理到 Flask 后端，开发时不需要处理跨域
// - 移动端自适应：PC 优先，样式使用 rem/百分比 + Element Plus 响应式栅格
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
    open: false,
    proxy: {
      '/api': {
        // 后端地址：可用 .env.development 里的 VITE_API_TARGET 覆盖
        target: process.env.VITE_API_TARGET || 'http://127.0.0.1:5000',
        changeOrigin: true
      }
    }
  },
  build: {
    outDir: 'dist',
    chunkSizeWarningLimit: 1500,
    rollupOptions: {
      output: {
        // 拆分体积较大的依赖，便于浏览器缓存
        manualChunks: {
          vue: ['vue', 'vue-router', 'pinia'],
          element: ['element-plus', '@element-plus/icons-vue']
        }
      }
    }
  }
})
