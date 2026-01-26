<script setup>
import { onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useScraperStore } from '@/stores/scraper'
import ComicBackground from '@/components/ui/ComicBackground.vue'
import ComicLoading from '@/components/ui/ComicLoading.vue'
import GlassNav from '@/components/layout/GlassNav.vue'

const router = useRouter()
const scraper = useScraperStore()

onUnmounted(() => {
    scraper.stopPolling()
})
</script>

<template>
  <div class="min-h-screen relative pb-10">
    <ComicBackground />
    <GlassNav title="资源爬取">
      <template #actions>
        <button @click="router.push({ name: 'home' })" class="text-slate-300 hover:text-white transition flex items-center gap-2">
          <i class="fas fa-arrow-left"></i> 返回
        </button>
      </template>
    </GlassNav>

    <main class="container mx-auto px-4 py-6">
      <div class="flex flex-wrap gap-2 mb-4">
        <button @click="scraper.setView('search')"
          class="px-3 py-1 text-xs font-semibold rounded-full border transition"
          :class="scraper.state.view === 'search'
            ? 'bg-accent-1/20 text-accent-1 border-accent-1/50'
            : 'bg-bg-primary/70 text-slate-200 border border-main/50 hover:border-accent-1'">
          搜索漫画
        </button>
        <button @click="scraper.setView('catalog')"
          class="px-3 py-1 text-xs font-semibold rounded-full border transition"
          :class="scraper.state.view === 'catalog'
            ? 'bg-accent-1/20 text-accent-1 border-accent-1/50'
            : 'bg-bg-primary/70 text-slate-200 border border-main/50 hover:border-accent-1'">
          站点目录
        </button>
      </div>
      <div class="grid gap-6 xl:grid-cols-12">
        <!-- Config Panel -->
        <div class="space-y-4 xl:col-span-3">
          <div class="bg-surface border border-main rounded-xl p-4 space-y-4">
            <div>
              <label class="text-xs text-slate-400">站点</label>
              <select v-model="scraper.state.site" @change="scraper.setSite(scraper.state.site)"
                class="mt-1 w-full bg-bg-primary border border-main text-text-main rounded-lg px-3 py-2 text-sm focus:border-accent-1 focus:outline-none">
                <option value="toongod">ToonGod</option>
                <option value="mangaforfree">MangaForFree</option>
                <option value="custom">自定义</option>
              </select>
            </div>
            <div>
              <label class="text-xs text-slate-400">基础地址</label>
              <input v-model="scraper.state.baseUrl" placeholder="https://toongod.org"
                class="mt-1 w-full bg-bg-primary border border-main text-text-main rounded-lg px-3 py-2 text-sm focus:border-accent-1 focus:outline-none" />
            </div>
            <div>
              <label class="text-xs text-slate-400">抓取模式</label>
              <select v-model="scraper.state.mode" @change="scraper.setMode(scraper.state.mode)"
                class="mt-1 w-full bg-bg-primary border border-main text-text-main rounded-lg px-3 py-2 text-sm focus:border-accent-1 focus:outline-none">
                <option value="http">HTTP</option>
                <option value="headed">有头浏览器</option>
              </select>
              <p class="text-[10px] text-slate-500 mt-1">有头模式会打开浏览器并需在终端回车继续</p>
            </div>
            <div>
              <label class="text-xs text-slate-400">并发</label>
              <input type="number" min="1" max="12" v-model.number="scraper.state.concurrency"
                class="mt-1 w-full bg-bg-primary border border-main text-text-main rounded-lg px-3 py-2 text-sm focus:border-accent-1 focus:outline-none" />
            </div>
            <div v-if="scraper.state.view === 'search'">
              <label class="text-xs text-slate-400">关键词 / 网址</label>
              <input v-model="scraper.state.keyword" placeholder="输入漫画关键词或完整网址"
                class="mt-1 w-full bg-bg-primary border border-main text-text-main rounded-lg px-3 py-2 text-sm focus:border-accent-1 focus:outline-none"
                @keydown.enter="scraper.search()" />
            </div>
            <button v-if="scraper.state.view === 'search'" @click="scraper.search()" :disabled="scraper.loading"
              class="w-full bg-accent-1/80 hover:bg-accent-1 text-white text-sm font-semibold py-2 rounded-lg transition"
              :class="scraper.loading ? 'opacity-60 cursor-not-allowed' : ''">
              {{ scraper.loading ? '搜索中...' : '搜索' }}
            </button>
            <button v-if="scraper.state.view === 'catalog'" @click="scraper.loadCatalog(true)"
              :disabled="scraper.catalog.loading"
              class="w-full bg-accent-1/80 hover:bg-accent-1 text-white text-sm font-semibold py-2 rounded-lg transition"
              :class="scraper.catalog.loading ? 'opacity-60 cursor-not-allowed' : ''">
              {{ scraper.catalog.loading ? '加载中...' : '加载目录' }}
            </button>
            <p v-if="scraper.error" class="text-xs text-red-400">{{ scraper.error }}</p>
          </div>

          <!-- Task Status -->
          <div class="bg-surface border border-main rounded-xl p-4">
            <div class="flex items-center justify-between">
              <h3 class="font-semibold">下载状态</h3>
              <span v-if="scraper.task.status" class="text-[10px] font-semibold px-2 py-1 rounded-full"
                :class="scraper.statusClass(scraper.task.status)">
                {{ scraper.statusLabel(scraper.task.status) }}
              </span>
            </div>
            <p class="mt-2 text-xs text-slate-400">{{ scraper.task.message || '暂无任务' }}</p>
            <p class="mt-1 text-[10px] text-slate-500">队列中 {{ scraper.queue.length }} 项</p>
            <div v-if="scraper.task.report" class="mt-2 text-xs text-slate-500 space-y-1">
              <p>成功 {{ scraper.task.report.success_count }} / 失败 {{ scraper.task.report.failed_count }}</p>
              <p class="break-all">输出目录: {{ scraper.task.report.output_dir }}</p>
            </div>
          </div>
        </div>

        <!-- Results -->
        <div class="space-y-4 xl:col-span-5">
          <!-- Search Results -->
          <div v-if="scraper.state.view === 'search'" class="bg-surface border border-main rounded-xl p-4">
            <div class="flex items-center justify-between">
              <h3 class="font-semibold">搜索结果</h3>
              <span v-if="scraper.loading" class="text-xs text-slate-400 animate-pulse">加载中...</span>
            </div>
            <div class="mt-3 space-y-2">
              <p v-if="!scraper.loading && scraper.results.length === 0" class="text-xs text-slate-500">暂无结果</p>
              <div v-for="manga in scraper.results" :key="manga.id"
                class="flex items-center justify-between bg-bg-primary/50 border border-main/50 rounded-lg px-3 py-2">
                <div class="flex items-center gap-3">
                  <div class="w-12 h-16 rounded-lg bg-bg-primary/80 border border-main/50 overflow-hidden">
                    <img v-if="manga.cover_url" :src="manga.cover_url" alt="cover"
                      class="w-full h-full object-cover" loading="lazy" />
                  </div>
                  <div>
                    <p class="text-sm font-semibold">{{ manga.title || manga.id }}</p>
                    <p class="text-[10px] text-slate-500 truncate">{{ manga.url }}</p>
                  </div>
                </div>
                <button @click="scraper.selectManga(manga)" :disabled="scraper.loading"
                  class="px-3 py-1 text-xs font-semibold rounded-full bg-accent-1/20 text-accent-1 hover:bg-accent-1 hover:text-white transition"
                  :class="scraper.loading ? 'opacity-60 cursor-not-allowed' : ''">
                  查看章节
                </button>
              </div>
            </div>
          </div>

          <!-- Catalog List -->
          <div v-if="scraper.state.view === 'catalog'" class="bg-surface border border-main rounded-xl p-4">
            <div class="flex flex-wrap items-center justify-between gap-3">
              <h3 class="font-semibold">站点目录</h3>
              <div class="flex items-center gap-2 text-xs text-slate-400">
                <span>目录</span>
                <select v-model="scraper.catalog.mode" @change="scraper.setCatalogMode(scraper.catalog.mode)"
                  class="bg-bg-primary border border-main rounded-lg px-2 py-1 text-xs">
                  <option value="all">全部</option>
                  <option value="views">浏览量</option>
                  <option value="new">最新</option>
                  <option value="genre-manga">分类: Manga</option>
                  <option value="genre-webtoon">分类: Webtoon</option>
                </select>
              </div>
            </div>
            <div class="mt-3 space-y-2">
              <p v-if="!scraper.catalog.loading && scraper.catalog.items.length === 0" class="text-xs text-slate-500">暂无目录数据</p>
              <div v-for="manga in scraper.catalog.items" :key="manga.id"
                class="flex items-center justify-between bg-bg-primary/50 border border-main/50 rounded-lg px-3 py-2">
                <div class="flex items-center gap-3">
                  <div class="w-12 h-16 rounded-lg bg-bg-primary/80 border border-main/50 overflow-hidden">
                    <img v-if="manga.cover_url" :src="manga.cover_url" alt="cover"
                      class="w-full h-full object-cover" loading="lazy" />
                  </div>
                  <div>
                    <p class="text-sm font-semibold">{{ manga.title || manga.id }}</p>
                    <p class="text-[10px] text-slate-500 truncate">{{ manga.url }}</p>
                  </div>
                </div>
                <button @click="scraper.selectManga(manga)" :disabled="scraper.catalog.loading || scraper.loading"
                  class="px-3 py-1 text-xs font-semibold rounded-full bg-accent-1/20 text-accent-1 hover:bg-accent-1 hover:text-white transition"
                  :class="(scraper.catalog.loading || scraper.loading) ? 'opacity-60 cursor-not-allowed' : ''">
                  查看章节
                </button>
              </div>
            </div>
            <div class="mt-3 flex items-center justify-between">
              <span class="text-xs text-slate-500">第 {{ scraper.catalog.page }} 页</span>
              <button @click="scraper.loadMoreCatalog()" :disabled="!scraper.catalog.hasMore || scraper.catalog.loading"
                class="px-3 py-1 text-xs font-semibold rounded-full bg-bg-primary/70 text-slate-200 border border-main/50 hover:border-accent-1 transition"
                :class="(!scraper.catalog.hasMore || scraper.catalog.loading) ? 'opacity-60 cursor-not-allowed' : ''">
                {{ scraper.catalog.loading ? '加载中...' : (scraper.catalog.hasMore ? '加载更多' : '没有更多') }}
              </button>
            </div>
          </div>

        </div>

        <!-- Chapters -->
        <div class="space-y-4 xl:col-span-4">
          <div class="bg-surface border border-main rounded-xl p-4">
            <div class="flex items-center justify-between">
              <h3 class="font-semibold">章节列表</h3>
              <span v-if="scraper.loading" class="text-xs text-slate-400 animate-pulse">加载中...</span>
              <div v-if="scraper.selectedManga" class="text-xs text-slate-400 flex items-center gap-2">
                <span>{{ scraper.selectedManga.title || scraper.selectedManga.id }}</span>
                <span v-if="scraper.downloadSummary.total > 0">
                  已下载 {{ scraper.downloadSummary.done }}/{{ scraper.downloadSummary.total }} 章
                </span>
              </div>
            </div>
            <div class="mt-3 flex flex-wrap gap-2">
              <button @click="scraper.selectAll()"
                class="px-3 py-1 text-xs font-semibold rounded-full bg-bg-primary/70 text-slate-200 border border-main/50 hover:border-accent-1 transition">
                全选
              </button>
              <button @click="scraper.clearSelection()"
                class="px-3 py-1 text-xs font-semibold rounded-full bg-bg-primary/70 text-slate-200 border border-main/50 hover:border-accent-1 transition">
                清空
              </button>
              <button @click="scraper.downloadSelected()" :disabled="scraper.selectedIds.length === 0"
                class="px-3 py-1 text-xs font-semibold rounded-full bg-accent-1/20 text-accent-1 hover:bg-accent-1 hover:text-white transition"
                :class="scraper.selectedIds.length === 0 ? 'opacity-60 cursor-not-allowed' : ''">
                批量下载 ({{ scraper.selectedIds.length }})
              </button>
            </div>
            <div class="mt-3 space-y-2 max-h-[480px] overflow-y-auto custom-scrollbar">
              <p v-if="scraper.chapters.length === 0" class="text-xs text-slate-500">请选择漫画查看章节</p>
              <div v-for="chapter in scraper.chapters" :key="chapter.id"
                class="flex items-center justify-between bg-bg-primary/50 border border-main/50 rounded-lg px-3 py-2">
                <div class="flex items-center gap-3">
                  <input type="checkbox" :checked="scraper.selectedIds.includes(chapter.id)"
                    @change="scraper.toggleSelection(chapter.id)" class="accent-accent-1" />
                  <div>
                    <p class="text-sm font-semibold">{{ chapter.title || chapter.id }}</p>
                    <p class="text-[10px] text-slate-500 truncate">{{ chapter.url }}</p>
                  </div>
                </div>
                <div class="flex items-center gap-2">
                  <span v-if="chapter.downloaded_count"
                    class="text-[10px] font-semibold px-2 py-1 rounded-full"
                    :class="scraper.downloadedClass(chapter)">
                    {{ scraper.downloadedLabel(chapter) }}
                  </span>
                  <span v-if="scraper.chapterStatus(chapter.id)"
                    class="text-[10px] font-semibold px-2 py-1 rounded-full"
                    :class="scraper.statusClass(scraper.chapterStatus(chapter.id))">
                    {{ scraper.statusLabel(scraper.chapterStatus(chapter.id)) }}
                  </span>
                  <button @click="scraper.download(chapter)"
                    :disabled="scraper.loading || scraper.isChapterBusy(chapter.id)"
                    class="px-3 py-1 text-xs font-semibold rounded-full bg-accent-1/20 text-accent-1 hover:bg-accent-1 hover:text-white transition"
                    :class="(scraper.loading || scraper.isChapterBusy(chapter.id)) ? 'opacity-60 cursor-not-allowed' : ''">
                    加入队列
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>
