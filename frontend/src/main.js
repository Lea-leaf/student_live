import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'

import 'element-plus/dist/index.css'
import '@/styles/main.css'

import App from '@/App.vue'
import router from '@/router'
import { useAppStore } from '@/stores/app'

const app = createApp(App)
const pinia = createPinia()

// 全局注册 Element Plus 图标（PC 端常用，一次性注册便于模板里直接用 <el-icon><Search /></el-icon>）
Object.entries(ElementPlusIconsVue).forEach(([key, component]) => {
  app.component(key, component)
})

app.use(pinia)
app.use(router)
app.use(ElementPlus, { locale: zhCn, size: 'default' })

// 启动时拉取公开配置（站点名、审核开关、上传限制等）
const appStore = useAppStore(pinia)
appStore.loadPublicConfig().finally(() => {
  app.mount('#app')
})
