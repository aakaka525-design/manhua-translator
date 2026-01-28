<script setup>
import { onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMangaStore } from '@/stores/manga'
import { useTranslateStore } from '@/stores/translate'
import { useToastStore } from '@/stores/toast'
import { translateApi } from '@/api'
import ComicBackground from '@/components/ui/ComicBackground.vue'
import ComicLoading from '@/components/ui/ComicLoading.vue'
import GlassNav from '@/components/layout/GlassNav.vue'

const route = useRoute()
const router = useRouter()
const mangaStore = useMangaStore()
const translateStore = useTranslateStore()
const toast = useToastStore()

onMounted(() => {
  const id = route.params.id
  if (id) {
    mangaStore.openManga(id)
    translateStore.initSSE()
  }
})

onUnmounted(() => {
  translateStore.closeSSE()
})

function goBack() {
  router.push({ name: 'home' })
}

function openChapter(chapter) {
  router.push({ 
    name: 'reader', 
    params: { 
      mangaId: mangaStore.currentManga.id, 
      chapterId: chapter.id 
    } 
  })
}

async function translateChapter(chapter, event) {
  event.stopPropagation() // Don't trigger card click
  
  if (chapter.isTranslating) {
    toast.show('该章节正在翻译中', 'warning')
    return
  }
  
  toast.show(`开始翻译: ${chapter.name}`, 'info')
  chapter.isTranslating = true
  
  try {
    await translateApi.translateChapter({
      manga_id: mangaStore.currentManga.id,
      chapter_id: chapter.id
    })
    toast.show('翻译任务已启动', 'success')
  } catch (e) {
    console.error('Translate failed:', e)
    toast.show('翻译启动失败: ' + e.message, 'error')
    chapter.isTranslating = false
  }
}
</script>

<template>
  <div class="min-h-screen relative pb-10">
    <ComicBackground />
    <GlassNav :title="mangaStore.currentManga?.name || 'Loading...'">
      <template #actions>
        <button @click="goBack" class="text-text-secondary hover:text-text-main transition flex items-center gap-2">
          <i class="fas fa-arrow-left"></i> 返回
        </button>
      </template>
    </GlassNav>

    <main class="container mx-auto px-4 py-6">
      <ComicLoading v-if="mangaStore.loading" />

      <div v-else-if="mangaStore.currentManga" class="space-y-3">
        <!-- Chapter List -->
        <div 
          v-for="chapter in mangaStore.chapters" 
          :key="chapter.id"
          class="bg-surface border border-border-main rounded-xl p-4 flex items-center justify-between hover:bg-white/5 transition cursor-pointer group"
          @click="openChapter(chapter)"
        >
          <div class="flex items-center gap-4">
            <div class="w-10 h-10 rounded-lg bg-bg-secondary flex items-center justify-center text-accent-2 group-hover:scale-110 transition-transform">
              <i class="fas fa-book-open"></i>
            </div>
            <div>
              <h3 class="font-semibold text-text-main">{{ chapter.name }}</h3>
              <p class="text-xs text-text-secondary opacity-70">{{ chapter.page_count }} 页</p>
            </div>
          </div>
          
          <div class="flex items-center gap-3">
            <!-- Status Badges -->
            <span v-if="chapter.isComplete" class="px-2 py-0.5 bg-state-success/20 text-state-success text-xs rounded border border-state-success/30 font-bold">已完成</span>
            <span v-else-if="chapter.has_translated" class="px-2 py-0.5 bg-state-warning/20 text-state-warning text-xs rounded border border-state-warning/30 font-bold">
              {{ chapter.translated_count }}/{{ chapter.page_count }}
            </span>
            <span v-if="chapter.isTranslating" class="text-xs text-accent-1 animate-pulse">翻译中...</span>
            
            <!-- Translate Button -->
            <button 
              v-if="!chapter.isComplete"
              @click="translateChapter(chapter, $event)"
              :disabled="chapter.isTranslating"
              class="px-3 py-1.5 text-xs font-semibold rounded-lg transition flex items-center gap-1.5"
              :class="chapter.isTranslating 
                ? 'bg-bg-secondary text-text-secondary opacity-50 cursor-not-allowed' 
                : 'bg-accent-1/20 text-accent-1 hover:bg-accent-1 hover:text-white'"
            >
              <i class="fas" :class="chapter.isTranslating ? 'fa-spinner animate-spin' : 'fa-language'"></i>
              {{ chapter.isTranslating ? '翻译中' : '翻译' }}
            </button>
            
            <i class="fas fa-chevron-right text-text-secondary opacity-50"></i>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>
