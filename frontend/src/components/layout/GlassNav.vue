<script setup>
import { useRouter } from 'vue-router'
import { useSettingsStore } from '@/stores/settings'

defineProps({
  title: {
    type: String,
    default: 'Neo-Comic Reader'
  }
})

const router = useRouter()
const settingsStore = useSettingsStore()

function goHome() {
  router.push({ name: 'home' })
}
</script>

<template>
  <nav class="fixed top-0 left-0 right-0 h-16 glass-nav z-50 flex items-center justify-between px-6">
    <div class="flex items-center gap-3 cursor-pointer" @click="goHome">
      <div class="w-8 h-8 bg-accent-1 rounded-lg rotate-3 flex items-center justify-center font-comic text-black text-xl font-bold">
        N
      </div>
      <h1 class="font-heading text-2xl tracking-wide text-white">{{ title }}</h1>
    </div>

    <div class="flex items-center gap-2">
      <slot name="actions"></slot>
      <router-link :to="{ name: 'scraper' }" 
        class="p-2 hover:bg-white/10 rounded-full transition" 
        title="资源爬取">
        <i class="fas fa-spider text-lg"></i>
      </router-link>
      <button @click="settingsStore.showModal = true" class="p-2 hover:bg-white/10 rounded-full transition" title="设置">
        <i class="fas fa-cog text-lg"></i>
      </button>
    </div>
  </nav>
  <!-- Spacer -->
  <div class="h-16"></div>
</template>

<style scoped>
.glass-nav {
  background: var(--nav-bg);
  backdrop-filter: blur(var(--nav-backdrop-blur));
  -webkit-backdrop-filter: blur(var(--nav-backdrop-blur));
  border-bottom: 1px solid var(--nav-border);
}
</style>
