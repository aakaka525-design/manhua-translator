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
  <nav class="glass-nav fixed left-0 right-0 top-0 z-50 flex h-16 items-center justify-between px-3 sm:px-6">
    <div class="flex min-w-0 cursor-pointer items-center gap-2 sm:gap-3" @click="goHome">
      <div class="flex h-8 w-8 shrink-0 rotate-3 items-center justify-center rounded-lg bg-accent-1 font-comic text-xl font-bold text-black">
        N
      </div>
      <h1 class="max-w-[36vw] truncate font-heading text-base tracking-wide text-white sm:max-w-[52vw] sm:text-2xl">
        {{ title }}
      </h1>
    </div>

    <div class="flex shrink-0 items-center gap-1 sm:gap-2">
      <slot name="actions"></slot>
      <router-link :to="{ name: 'scraper' }" 
        class="rounded-full p-1.5 transition hover:bg-white/10 sm:p-2" 
        title="资源爬取">
        <i class="fas fa-spider text-lg"></i>
      </router-link>
      <button @click="settingsStore.showModal = true" class="rounded-full p-1.5 transition hover:bg-white/10 sm:p-2" title="设置">
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
