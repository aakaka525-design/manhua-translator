<script setup>
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useMangaStore } from '@/stores/manga'
import ComicBackground from '@/components/ui/ComicBackground.vue'
import ComicCard from '@/components/ui/ComicCard.vue'
import ComicLoading from '@/components/ui/ComicLoading.vue'
import GlassNav from '@/components/layout/GlassNav.vue'
import { useParallax } from '@/composables/useParallax'

const router = useRouter()
const mangaStore = useMangaStore()

useParallax()

onMounted(() => {
  mangaStore.fetchMangas()
})

function openManga(id) {
  router.push({ name: 'manga', params: { id } })
}

// Removed Bento size variation for consistent layout
</script>

<template>
  <div class="min-h-screen relative pb-10">
    <ComicBackground />
    <GlassNav />

    <main class="container mx-auto px-4 py-6">
      <!-- Loading State -->
      <ComicLoading v-if="mangaStore.loading" />

      <!-- Empty State -->
      <div v-else-if="!mangaStore.hasMangas" class="text-center py-20">
        <h2 class="text-2xl text-slate-500 font-comic">No Mangas Found</h2>
        <p class="text-slate-600">Place your manga folders in the /data directory.</p>
      </div>

      <!-- Bento Grid -->
      <div v-else class="bento-grid">
        <ComicCard 
          v-for="(manga, index) in mangaStore.mangas" 
          :key="manga.id"
          :title="manga.name"
          :cover="manga.cover_url"
          :chapter-count="manga.chapter_count"
          @click="openManga(manga.id)"
          class="animate-fade-in"
          :style="{ animationDelay: `${index * 30}ms` }"
        />
      </div>
    </main>
  </div>
</template>

<style scoped>
.bento-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 1rem;
}

@media (min-width: 640px) {
  .bento-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}

@media (min-width: 1024px) {
  .bento-grid {
    grid-template-columns: repeat(4, 1fr);
  }
}

@media (min-width: 1280px) {
  .bento-grid {
    grid-template-columns: repeat(5, 1fr);
  }
}

.animate-fade-in {
  animation: fadeIn 0.5s ease-out backwards;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
