<script setup>
/**
 * 公开页布局：登录 / 注册。
 * 左侧品牌介绍 + 右侧表单卡片，PC 双栏、移动端单栏。
 */
import { computed } from 'vue'

import { useAppStore } from '@/stores/app'

const appStore = useAppStore()
const siteName = computed(() => appStore.siteName)
</script>

<template>
  <div class="public-layout">
    <div class="public-layout__brand">
      <h1 class="public-layout__title">{{ siteName }}</h1>
      <p class="public-layout__slogan">同学之间的校园生活互助平台</p>
      <ul class="public-layout__list">
        <li>失物招领：丢了东西、捡到东西，一句话发出来</li>
        <li>校园互助：二手交易、拼单、跑腿（模块可后台启停）</li>
        <li>安全提示：请勿上传身份证、银行卡等敏感信息</li>
      </ul>
    </div>
    <div class="public-layout__panel">
      <router-view />
    </div>
  </div>
</template>

<style scoped>
.public-layout {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 60px;
  padding: 40px 20px;
  background: linear-gradient(135deg, #eef4ff 0%, #f7fbff 40%, #f5f7fa 100%);
}

.public-layout__brand {
  max-width: 420px;
}

.public-layout__title {
  font-size: 34px;
  margin: 0 0 12px;
  color: #1f2d3d;
}

.public-layout__slogan {
  font-size: 16px;
  color: #5a6b7f;
  margin-bottom: 24px;
}

.public-layout__list {
  padding-left: 18px;
  color: #6b7c93;
  line-height: 2;
  font-size: 14px;
}

.public-layout__panel {
  width: 400px;
  background: #fff;
  border-radius: 12px;
  padding: 28px;
  box-shadow: 0 8px 30px rgba(31, 45, 61, 0.1);
}

@media (max-width: 900px) {
  .public-layout {
    flex-direction: column;
    gap: 24px;
    padding: 24px 12px;
  }

  .public-layout__brand {
    text-align: center;
  }

  .public-layout__list {
    display: none;
  }

  .public-layout__panel {
    width: 100%;
    max-width: 420px;
  }
}
</style>
