<script setup>
import { onUnmounted, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useScraperStore } from '@/stores/scraper'
import ComicBackground from '@/components/ui/ComicBackground.vue'
import GlassNav from '@/components/layout/GlassNav.vue'

const router = useRouter()
const scraper = useScraperStore()
const mobileTab = ref('browse')
const mobileConfigOpen = ref(true)

onMounted(() => {
    scraper.ensureUserAgent()
})

onUnmounted(() => {
    scraper.stopPolling()
})
</script>

<template>
  <div class="min-h-screen relative pb-24 xl:pb-10">
    <ComicBackground />
    <GlassNav title="资源爬取">
      <template #actions>
        <button @click="router.push({ name: 'home' })" class="text-text-secondary hover:text-text-main transition flex items-center gap-2">
          <i class="fas fa-arrow-left"></i> 返回
        </button>
      </template>
    </GlassNav>

    <main class="container mx-auto px-4 py-6">
      <div class="flex flex-wrap gap-2 mb-4" :class="mobileTab !== 'browse' ? 'hidden xl:flex' : ''">
        <button @click="scraper.setView('search')"
          class="px-3 py-1 text-xs font-semibold rounded-full border transition"
          :class="scraper.state.view === 'search'
            ? 'bg-accent-1/20 text-accent-1 border-accent-1/50'
            : 'bg-bg-secondary text-text-secondary border border-border-subtle hover:border-accent-1 hover:text-text-main'">
          搜索漫画
        </button>
        <button @click="scraper.setView('catalog')"
          class="px-3 py-1 text-xs font-semibold rounded-full border transition"
          :class="scraper.state.view === 'catalog'
            ? 'bg-accent-1/20 text-accent-1 border-accent-1/50'
            : 'bg-bg-secondary text-text-secondary border border-border-subtle hover:border-accent-1 hover:text-text-main'">
          站点目录
        </button>
        <button @click="scraper.setView('auth')"
          class="px-3 py-1 text-xs font-semibold rounded-full border transition"
          :class="scraper.state.view === 'auth'
            ? 'bg-accent-1/20 text-accent-1 border-accent-1/50'
            : 'bg-bg-secondary text-text-secondary border border-border-subtle hover:border-accent-1 hover:text-text-main'">
          认证
        </button>
      </div>
      <div class="flex flex-wrap gap-2 mb-4 xl:hidden">
        <button @click="mobileTab = 'browse'"
          class="px-3 py-1 text-xs font-semibold rounded-full border transition"
          :class="mobileTab === 'browse'
            ? 'bg-accent-1/20 text-accent-1 border-accent-1/50'
            : 'bg-bg-secondary text-text-secondary border border-border-subtle hover:border-accent-1 hover:text-text-main'">
          浏览
        </button>
        <button @click="mobileTab = 'chapters'"
          class="px-3 py-1 text-xs font-semibold rounded-full border transition"
          :class="mobileTab === 'chapters'
            ? 'bg-accent-1/20 text-accent-1 border-accent-1/50'
            : 'bg-bg-secondary text-text-secondary border border-border-subtle hover:border-accent-1 hover:text-text-main'">
          章节
        </button>
        <button @click="mobileTab = 'settings'"
          class="px-3 py-1 text-xs font-semibold rounded-full border transition"
          :class="mobileTab === 'settings'
            ? 'bg-accent-1/20 text-accent-1 border-accent-1/50'
            : 'bg-bg-secondary text-text-secondary border border-border-subtle hover:border-accent-1 hover:text-text-main'">
          设置
        </button>
      </div>
      <div class="grid gap-6 xl:grid-cols-12">
        <!-- Config Panel -->
        <div class="space-y-4 xl:col-span-3" :class="mobileTab === 'settings' ? 'block' : 'hidden xl:block'">
          <div class="bg-surface border border-main rounded-xl p-4">
            <div class="flex items-center justify-between">
              <h3 class="font-semibold text-text-main">站点设置</h3>
              <button class="text-xs text-text-secondary xl:hidden" @click="mobileConfigOpen = !mobileConfigOpen">
                <span>{{ mobileConfigOpen ? '收起' : '展开' }}</span>
                <i class="fas fa-chevron-down ml-1 transition"
                  :class="mobileConfigOpen ? 'rotate-180' : ''"></i>
              </button>
            </div>
            <div class="mt-3 space-y-5" :class="mobileConfigOpen ? 'block' : 'hidden xl:block'">
              <p class="text-[10px] uppercase tracking-widest text-text-secondary opacity-70">基础设置</p>
              <div class="space-y-4">
                <div>
                  <label class="text-xs text-text-secondary">站点</label>
                  <select v-model="scraper.state.site" @change="scraper.setSite(scraper.state.site)"
                    class="mt-1 w-full bg-bg-secondary border border-border-subtle text-text-main rounded-lg px-3 py-2 text-sm focus:border-accent-1 focus:outline-none">
                    <option value="toongod">ToonGod</option>
                    <option value="mangaforfree">MangaForFree</option>
                    <option value="custom">自定义</option>
                  </select>
                </div>
                <div>
                  <label class="text-xs text-text-secondary">基础地址</label>
                  <input v-model="scraper.state.baseUrl" placeholder="https://toongod.org"
                    class="mt-1 w-full bg-bg-secondary border border-border-subtle text-text-main rounded-lg px-3 py-2 text-sm focus:border-accent-1 focus:outline-none" />
                </div>
                <div>
                  <label class="text-xs text-text-secondary">抓取模式</label>
                  <select v-model="scraper.state.mode" @change="scraper.setMode(scraper.state.mode)"
                    class="mt-1 w-full bg-bg-secondary border border-border-subtle text-text-main rounded-lg px-3 py-2 text-sm focus:border-accent-1 focus:outline-none">
                    <option value="http">HTTP</option>
                    <option value="headless">无头浏览器</option>
                    <option value="headed">有头浏览器</option>
                  </select>
                  <p class="text-[10px] text-text-secondary mt-1 opacity-70" v-if="scraper.state.mode === 'headed'">
                    有头模式会打开浏览器并需在终端回车继续
                  </p>
                  <p class="text-[10px] text-text-secondary mt-1 opacity-70" v-else-if="scraper.state.mode === 'headless'">
                    无头模式不会弹窗，但需要有效状态文件
                  </p>
                </div>
              </div>

              <p class="text-[10px] uppercase tracking-widest text-text-secondary opacity-70">认证与状态</p>
              <div class="space-y-3 rounded-xl border border-border-subtle bg-bg-secondary/40 p-3">
                <div>
                  <label class="text-xs text-text-secondary">状态文件（可选）</label>
                  <div class="mt-1 flex gap-2">
                    <input v-model="scraper.state.storageStatePath" placeholder="data/toongod_state.json"
                      class="flex-1 bg-bg-secondary border border-border-subtle text-text-main rounded-lg px-3 py-2 text-sm focus:border-accent-1 focus:outline-none" />
                    <button @click="scraper.checkStateInfo()"
                      class="px-3 py-2 text-xs font-semibold rounded-lg bg-bg-secondary border border-border-subtle text-text-secondary hover:border-accent-1 transition">
                      检测
                    </button>
                  </div>
                  <div class="mt-2 flex items-center gap-2">
                    <label
                      class="px-3 py-2 text-xs font-semibold rounded-lg bg-bg-secondary border border-border-subtle text-text-secondary hover:border-accent-1 transition cursor-pointer">
                      上传状态文件
                      <input type="file" accept=".json" class="hidden"
                        @change="scraper.uploadStateFile($event.target.files[0])" />
                    </label>
                    <span v-if="scraper.uploadInfo.status !== 'idle'" class="text-[10px]"
                      :class="scraper.uploadInfo.status === 'success' ? 'text-green-300' : (scraper.uploadInfo.status === 'error' ? 'text-red-300' : 'text-slate-300')">
                      {{ scraper.uploadInfo.message }}
                    </span>
                  </div>
                  <p class="text-[10px] text-text-secondary mt-1 opacity-70">无界面服务器可复用本地 bootstrap 文件</p>
                  <p v-if="scraper.stateInfo.status !== 'idle'" class="text-[10px] mt-1"
                    :class="scraper.stateInfoClass()">
                    {{ scraper.stateInfoLabel() }}
                  </p>
                  <div class="mt-2 flex items-center gap-2">
                    <button @click="scraper.checkAccess()"
                      class="px-3 py-2 text-xs font-semibold rounded-lg bg-bg-secondary border border-border-subtle text-text-secondary hover:border-accent-1 transition">
                      站点检测
                    </button>
                    <span v-if="scraper.accessInfo.status !== 'idle'" class="text-[10px]"
                      :class="scraper.accessInfoClass()">
                      {{ scraper.accessInfoLabel() }}
                    </span>
                  </div>
                </div>
                <div class="grid gap-2 sm:grid-cols-2">
                  <button @click="scraper.setView('auth')"
                    class="w-full bg-bg-secondary border border-border-subtle text-text-secondary text-sm font-semibold py-2 rounded-lg hover:border-accent-1 hover:text-text-main transition">
                    去认证
                  </button>
                  <a :href="scraper.authInfo.url || '/auth'" target="_blank"
                    class="w-full inline-flex items-center justify-center gap-2 bg-accent-1/20 text-accent-1 text-sm font-semibold py-2 rounded-lg hover:bg-accent-1 hover:text-white transition">
                    打开认证页
                    <i class="fas fa-external-link-alt text-[10px]"></i>
                  </a>
                </div>
                <p class="text-[10px] text-text-secondary opacity-70">认证页在新标签打开，完成挑战后回到此处检测</p>
              </div>

              <details class="group rounded-xl border border-border-subtle bg-bg-secondary/40 p-3">
                <summary class="cursor-pointer list-none text-xs font-semibold text-text-main">
                  高级设置
                  <span class="text-[10px] text-text-secondary opacity-70 ml-2">UA / 通道 / 并发</span>
                </summary>
                <div class="mt-3 space-y-4">
                  <div>
                    <label class="text-xs text-text-secondary">持久化配置（推荐）</label>
                    <div class="mt-1 flex items-center gap-2">
                      <input type="checkbox" v-model="scraper.state.useProfile" class="accent-accent-1" />
                      <span class="text-[10px] text-text-secondary opacity-70">开启可减少重复挑战</span>
                    </div>
                    <input v-if="scraper.state.useProfile" v-model="scraper.state.userDataDir" placeholder="data/toongod_profile"
                      class="mt-2 w-full bg-bg-secondary border border-border-subtle text-text-main rounded-lg px-3 py-2 text-sm focus:border-accent-1 focus:outline-none" />
                  </div>
                  <div>
                    <label class="text-xs text-text-secondary">固定 UA（推荐）</label>
                    <div class="mt-1 flex items-center gap-2">
                      <input type="checkbox" v-model="scraper.state.lockUserAgent" class="accent-accent-1"
                        @change="scraper.ensureUserAgent()" />
                      <span class="text-[10px] text-text-secondary opacity-70">避免 UA 变化触发挑战</span>
                    </div>
                    <div v-if="scraper.state.lockUserAgent" class="mt-2 flex gap-2">
                      <input v-model="scraper.state.userAgent" placeholder="浏览器 UA"
                        class="flex-1 bg-bg-secondary border border-border-subtle text-text-main rounded-lg px-3 py-2 text-sm focus:border-accent-1 focus:outline-none" />
                      <button @click="scraper.syncUserAgent()"
                        class="px-3 py-2 text-xs font-semibold rounded-lg bg-bg-secondary border border-border-subtle text-text-secondary hover:border-accent-1 transition">
                        使用当前浏览器 UA
                      </button>
                    </div>
                  </div>
                  <div>
                    <label class="text-xs text-text-secondary">浏览器通道（推荐）</label>
                    <div class="mt-1 flex items-center gap-2">
                      <input type="checkbox" v-model="scraper.state.useChromeChannel" class="accent-accent-1"
                        :disabled="scraper.state.httpMode" />
                      <span class="text-[10px] text-text-secondary opacity-70">仅有头模式生效，需已安装 Chrome</span>
                    </div>
                  </div>
                  <div>
                    <label class="text-xs text-text-secondary">并发</label>
                    <input type="number" min="1" max="12" v-model.number="scraper.state.concurrency"
                      class="mt-1 w-full bg-bg-secondary border border-border-subtle text-text-main rounded-lg px-3 py-2 text-sm focus:border-accent-1 focus:outline-none" />
                  </div>
                </div>
              </details>

              <p class="text-[10px] uppercase tracking-widest text-text-secondary opacity-70">搜索与目录</p>
              <div class="space-y-3">
                <div v-if="scraper.state.view === 'search'">
                  <label class="text-xs text-text-secondary">关键词 / 网址</label>
                  <input v-model="scraper.state.keyword" placeholder="输入漫画关键词或完整网址"
                    class="mt-1 w-full bg-bg-secondary border border-border-subtle text-text-main rounded-lg px-3 py-2 text-sm focus:border-accent-1 focus:outline-none"
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
              </div>

              <p v-if="scraper.error" class="text-xs text-red-400">{{ scraper.error }}</p>

              <details class="group rounded-xl border border-border-subtle bg-bg-secondary/40 p-3">
                <summary class="cursor-pointer list-none text-xs font-semibold text-text-main">
                  Cloudflare 指引
                  <span class="text-[10px] text-text-secondary opacity-70 ml-2">点此查看</span>
                </summary>
                <div class="mt-3 text-[10px] text-text-secondary space-y-1">
                  <p>1) 有界面电脑运行 bootstrap 生成状态文件</p>
                  <p>2) 拷贝到服务器后填写上方路径</p>
                  <p>3) 建议开启“持久化配置”减少重复挑战</p>
                  <p class="mt-2 font-mono text-[10px] text-text-secondary opacity-70">python scripts/scraper_cli.py bootstrap --base-url https://mangaforfree.com</p>
                </div>
              </details>
            </div>
          </div>

        </div>

        <!-- Results -->
        <div class="space-y-4 xl:col-span-5" :class="mobileTab === 'browse' ? 'block' : 'hidden xl:block'">
          <!-- Search Results -->
          <div v-if="scraper.state.view === 'search'" class="bg-surface border border-main rounded-xl p-4">
            <div class="flex items-start justify-between gap-4">
              <div>
                <h3 class="font-semibold text-text-main">搜索结果</h3>
                <p class="text-xs text-text-secondary opacity-70 mt-1">输入关键词或 URL 搜索漫画</p>
              </div>
              <span v-if="scraper.loading" class="text-xs text-text-secondary animate-pulse">加载中...</span>
            </div>
            <div class="mt-4 space-y-3">
              <p v-if="!scraper.loading && scraper.results.length === 0" class="text-xs text-text-secondary opacity-70">暂无结果</p>
              <div v-for="manga in scraper.results" :key="manga.id"
                class="flex items-center justify-between rounded-xl px-4 py-3 border transition"
                :class="manga.id === scraper.selectedManga?.id ? 'bg-accent-1/10 border-accent-1/60' : 'bg-bg-secondary/50 border-border-subtle hover:border-accent-1/40'">
                <div class="flex items-center gap-4">
                  <div class="w-16 h-24 sm:w-20 sm:h-28 rounded-lg bg-bg-secondary border border-border-subtle overflow-hidden">
                    <img v-if="manga.cover_url" :src="scraper.proxyImageUrl(manga.cover_url)" alt="cover"
                      class="w-full h-full object-cover" loading="lazy" />
                  </div>
                  <div>
                    <p class="text-sm font-semibold text-text-main">{{ manga.title || manga.id }}</p>
                    <p class="text-[11px] text-text-secondary truncate">{{ manga.url }}</p>
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
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 class="font-semibold text-text-main">站点目录</h3>
                <p class="text-xs text-text-secondary opacity-70 mt-1">按站点排序浏览全部漫画</p>
              </div>
              <div class="flex items-center gap-2 text-xs text-text-secondary">
                <span>目录</span>
                <select v-model="scraper.catalog.mode" @change="scraper.setCatalogMode(scraper.catalog.mode)"
                  class="bg-bg-secondary border border-border-subtle text-text-main rounded-lg px-2 py-1 text-xs">
                  <option value="all">全部</option>
                  <option value="views">浏览量</option>
                  <option value="new">最新</option>
                  <option value="genre-manga">分类: Manga</option>
                  <option value="genre-webtoon">分类: Webtoon</option>
                </select>
              </div>
            </div>
            <div class="mt-4 space-y-3">
              <p v-if="!scraper.catalog.loading && scraper.catalog.items.length === 0" class="text-xs text-text-secondary opacity-70">暂无目录数据</p>
              <div v-for="manga in scraper.catalog.items" :key="manga.id"
                class="flex items-center justify-between rounded-xl px-4 py-3 border transition"
                :class="manga.id === scraper.selectedManga?.id ? 'bg-accent-1/10 border-accent-1/60' : 'bg-bg-secondary/50 border-border-subtle hover:border-accent-1/40'">
                <div class="flex items-center gap-4">
                  <div class="w-16 h-24 sm:w-20 sm:h-28 rounded-lg bg-bg-secondary border border-border-subtle overflow-hidden">
                    <img v-if="manga.cover_url" :src="scraper.proxyImageUrl(manga.cover_url)" alt="cover"
                      class="w-full h-full object-cover" loading="lazy" />
                  </div>
                  <div>
                    <p class="text-sm font-semibold text-text-main">{{ manga.title || manga.id }}</p>
                    <p class="text-[11px] text-text-secondary truncate">{{ manga.url }}</p>
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
              <span class="text-xs text-text-secondary opacity-70">第 {{ scraper.catalog.page }} 页</span>
              <button @click="scraper.loadMoreCatalog()" :disabled="!scraper.catalog.hasMore || scraper.catalog.loading"
                class="px-3 py-1 text-xs font-semibold rounded-full bg-bg-secondary text-text-secondary border border-border-subtle hover:border-accent-1 hover:text-text-main transition"
                :class="(!scraper.catalog.hasMore || scraper.catalog.loading) ? 'opacity-60 cursor-not-allowed' : ''">
                {{ scraper.catalog.loading ? '加载中...' : (scraper.catalog.hasMore ? '加载更多' : '没有更多') }}
              </button>
            </div>
          </div>

          <!-- Auth -->
          <div v-if="scraper.state.view === 'auth'" class="bg-surface border border-main rounded-xl p-4">
            <div class="flex items-start justify-between gap-3">
              <div>
                <h3 class="font-semibold text-text-main">站点认证</h3>
                <p class="text-xs text-text-secondary opacity-70 mt-1">在服务器浏览器中完成 Cloudflare 验证</p>
              </div>
            </div>
            <div class="mt-4 space-y-3 text-sm">
              <div>
                <p class="text-xs text-text-secondary opacity-70">认证地址</p>
                <p class="text-sm text-text-main break-all">
                  {{ scraper.authInfo.url || '加载中...' }}
                </p>
              </div>
              <a :href="scraper.authInfo.url || '/auth'" target="_blank"
                class="inline-flex items-center gap-2 px-3 py-2 text-xs font-semibold rounded-lg bg-accent-1/20 text-accent-1 hover:bg-accent-1 hover:text-white transition">
                打开认证页
                <i class="fas fa-external-link-alt text-[10px]"></i>
              </a>
              <div class="text-xs text-text-secondary space-y-1">
                <p>1) 打开认证页完成验证</p>
                <p>2) 回到此页点击“检测 / 上传状态文件”</p>
              </div>
              <div class="flex items-center gap-2">
                <button @click="scraper.checkStateInfo()"
                  class="px-3 py-2 text-xs font-semibold rounded-lg bg-bg-secondary border border-border-subtle text-text-secondary hover:border-accent-1 hover:text-text-main transition">
                  检测状态
                </button>
                <button @click="scraper.checkAccess()"
                  class="px-3 py-2 text-xs font-semibold rounded-lg bg-bg-secondary border border-border-subtle text-text-secondary hover:border-accent-1 hover:text-text-main transition">
                  站点检测
                </button>
              </div>
            </div>
          </div>

        </div>

        <!-- Chapters -->
        <div class="space-y-4 xl:col-span-4" :class="mobileTab === 'chapters' ? 'block' : 'hidden xl:block'">
          <div class="bg-surface border border-main rounded-xl p-4">
            <div class="flex items-start justify-between gap-3">
              <div>
                <h3 class="font-semibold text-text-main">下载状态</h3>
                <p class="text-xs text-text-secondary opacity-70 mt-1">当前任务与队列摘要</p>
              </div>
              <span v-if="scraper.task.status" class="text-[10px] font-semibold px-2 py-1 rounded-full"
                :class="scraper.statusClass(scraper.task.status)">
                {{ scraper.statusLabel(scraper.task.status) }}
              </span>
            </div>
            <div class="mt-3 space-y-2 text-xs">
              <p class="text-text-secondary">{{ scraper.task.message || '暂无任务' }}</p>
              <div class="flex items-center gap-2">
                <span class="text-[10px] text-text-secondary opacity-70">队列中 {{ scraper.queue.length }} 项</span>
              </div>
              <div v-if="scraper.task.report" class="text-text-secondary space-y-1">
                <p>成功 {{ scraper.task.report.success_count }} / 失败 {{ scraper.task.report.failed_count }}</p>
                <p class="break-all">输出目录: {{ scraper.task.report.output_dir }}</p>
              </div>
            </div>
          </div>
          <div class="bg-surface border border-main rounded-xl p-4">
            <div class="flex items-start justify-between gap-4">
              <div>
                <h3 class="font-semibold text-text-main">章节下载</h3>
                <p class="text-xs text-text-secondary opacity-70 mt-1">选择章节加入队列，支持批量下载</p>
              </div>
              <div class="flex flex-col items-end gap-2">
                <span v-if="scraper.loading" class="text-xs text-text-secondary animate-pulse">加载中...</span>
                <div v-if="scraper.selectedManga" class="text-xs text-text-secondary flex items-center gap-2">
                  <span>{{ scraper.selectedManga.title || scraper.selectedManga.id }}</span>
                  <span v-if="scraper.downloadSummary.total > 0"
                    class="px-2 py-1 text-[10px] rounded-full bg-bg-secondary border border-border-subtle text-text-secondary">
                    已下载 {{ scraper.downloadSummary.done }}/{{ scraper.downloadSummary.total }} 章
                  </span>
                </div>
              </div>
            </div>
            <div class="mt-3 flex flex-wrap gap-2 hidden xl:flex">
              <button @click="scraper.selectAll()"
                class="px-3 py-1 text-xs font-semibold rounded-full bg-bg-secondary text-text-secondary border border-border-subtle hover:border-accent-1 hover:text-text-main transition">
                全选
              </button>
              <button @click="scraper.clearSelection()"
                class="px-3 py-1 text-xs font-semibold rounded-full bg-bg-secondary text-text-secondary border border-border-subtle hover:border-accent-1 hover:text-text-main transition">
                清空
              </button>
              <button @click="scraper.downloadSelected()" :disabled="scraper.selectedIds.length === 0"
                class="px-3 py-1 text-xs font-semibold rounded-full bg-accent-1/20 text-accent-1 hover:bg-accent-1 hover:text-white transition"
                :class="scraper.selectedIds.length === 0 ? 'opacity-60 cursor-not-allowed' : ''">
                批量下载 ({{ scraper.selectedIds.length }})
              </button>
            </div>
            <div class="mt-4 space-y-3 max-h-[64vh] xl:max-h-[520px] overflow-y-auto custom-scrollbar">
              <p v-if="scraper.chapters.length === 0" class="text-xs text-text-secondary opacity-70">请选择漫画查看章节</p>
              <div v-for="chapter in scraper.chapters" :key="chapter.id"
                class="flex items-start justify-between bg-bg-secondary/50 border border-border-subtle rounded-xl px-4 py-3">
                <div class="flex items-center gap-3">
                  <input type="checkbox" :checked="scraper.selectedIds.includes(chapter.id)"
                    @change="scraper.toggleSelection(chapter.id)" class="accent-accent-1" />
                  <div>
                    <p class="text-sm font-semibold text-text-main">{{ chapter.title || chapter.id }}</p>
                    <p class="text-[11px] text-text-secondary truncate">{{ chapter.url }}</p>
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
      <div v-if="mobileTab === 'chapters'" class="fixed bottom-4 left-4 right-4 z-30 xl:hidden">
        <div class="bg-surface/95 border border-main rounded-full px-3 py-2 flex items-center justify-between gap-2">
          <button @click="scraper.selectAll()"
            class="px-3 py-1 text-xs font-semibold rounded-full bg-bg-secondary text-text-secondary border border-border-subtle">
            全选
          </button>
          <button @click="scraper.clearSelection()"
            class="px-3 py-1 text-xs font-semibold rounded-full bg-bg-secondary text-text-secondary border border-border-subtle">
            清空
          </button>
          <button @click="scraper.downloadSelected()" :disabled="scraper.selectedIds.length === 0"
            class="px-3 py-1 text-xs font-semibold rounded-full bg-accent-1/20 text-accent-1 border border-accent-1/30"
            :class="scraper.selectedIds.length === 0 ? 'opacity-60 cursor-not-allowed' : ''">
            下载 {{ scraper.selectedIds.length }}
          </button>
        </div>
      </div>
    </main>
  </div>
</template>
