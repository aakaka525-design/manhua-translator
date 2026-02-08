<script setup>
import { onMounted, onUnmounted, computed } from 'vue'
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

const activeTranslatingChapters = computed(() =>
  mangaStore.chapters.filter((chapter) => chapter.isTranslating)
)

const translationSummary = computed(() => {
  const totalPages = activeTranslatingChapters.value.reduce((sum, chapter) => {
    return sum + chapterTotalPages(chapter)
  }, 0)
  const completedPages = activeTranslatingChapters.value.reduce((sum, chapter) => {
    return sum + chapterDonePages(chapter)
  }, 0)
  const failedPages = activeTranslatingChapters.value.reduce((sum, chapter) => {
    return sum + Number(chapter.failedPages || 0)
  }, 0)
  const progress = totalPages > 0 ? Math.round((completedPages / totalPages) * 100) : 0
  return { totalPages, completedPages, failedPages, progress }
})

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

function chapterTotalPages(chapter) {
  const total = Number(chapter.totalPages)
  if (total > 0) return total
  return Number(chapter.page_count) || 0
}

function chapterDonePages(chapter) {
  const done = Number(chapter.completedPages)
  if (done >= 0) return done
  return 0
}

function chapterProgress(chapter) {
  const explicit = Number(chapter.progress)
  if (explicit > 0) return Math.min(100, explicit)
  const total = chapterTotalPages(chapter)
  if (total <= 0) return 0
  return Math.min(99, Math.round((chapterDonePages(chapter) / total) * 100))
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
        <div v-if="activeTranslatingChapters.length > 0" class="rounded-xl border border-accent-1/30 bg-accent-1/5 px-4 py-3">
          <div class="flex items-center justify-between gap-3">
            <div class="text-sm font-semibold text-text-main">
              正在翻译 {{ activeTranslatingChapters.length }} 章
            </div>
            <div class="text-xs" :class="translateStore.isConnected ? 'text-state-success' : 'text-state-warning'">
              <i class="fas mr-1" :class="translateStore.isConnected ? 'fa-circle' : 'fa-triangle-exclamation'"></i>
              {{ translateStore.isConnected ? '实时连接正常' : '实时连接重连中' }}
            </div>
          </div>
          <div class="mt-2 text-xs text-text-secondary">
            {{ translationSummary.completedPages }}/{{ translationSummary.totalPages }} 页
            <span v-if="translationSummary.failedPages > 0"> · 失败 {{ translationSummary.failedPages }}</span>
          </div>
          <div class="mt-2 h-1.5 w-full rounded-full bg-bg-secondary overflow-hidden">
            <div class="h-full bg-accent-1 transition-all duration-300" :style="{ width: translationSummary.progress + '%' }"></div>
          </div>
        </div>

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
              <p v-if="chapter.isTranslating || chapter.statusText" class="text-[11px] text-text-secondary mt-1">
                {{ chapter.statusText || '进行中' }}
              </p>
              <div v-if="chapter.isTranslating" class="mt-1.5 h-1.5 w-40 rounded-full bg-bg-secondary overflow-hidden">
                <div class="h-full bg-accent-1 transition-all duration-300" :style="{ width: chapterProgress(chapter) + '%' }"></div>
              </div>
            </div>
          </div>
          
          <div class="flex items-center gap-3">
            <!-- Status Badges -->
            <span v-if="chapter.isComplete" class="px-2 py-0.5 bg-state-success/20 text-state-success text-xs rounded border border-state-success/30 font-bold">已完成</span>
            <span v-else-if="chapter.has_translated" class="px-2 py-0.5 bg-state-warning/20 text-state-warning text-xs rounded border border-state-warning/30 font-bold">
              {{ chapter.translated_count }}/{{ chapter.page_count }}
            </span>
            <span v-if="chapter.isTranslating" class="text-xs text-accent-1 animate-pulse">
              翻译中 {{ chapterDonePages(chapter) }}/{{ chapterTotalPages(chapter) }}
            </span>
            
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
