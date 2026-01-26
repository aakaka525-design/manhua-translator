import { defineStore } from 'pinia'
import { ref, reactive, computed } from 'vue'

const api = {
    async search(payload) {
        const res = await fetch('/api/v1/scraper/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        })
        if (!res.ok) throw new Error((await res.json()).detail || 'Search failed')
        return res.json()
    },
    async chapters(payload) {
        const res = await fetch('/api/v1/scraper/chapters', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        })
        if (!res.ok) throw new Error((await res.json()).detail || 'Chapters failed')
        return res.json()
    },
    async catalog(payload) {
        const res = await fetch('/api/v1/scraper/catalog', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        })
        if (!res.ok) throw new Error((await res.json()).detail || 'Catalog failed')
        return res.json()
    },
    async download(payload) {
        const res = await fetch('/api/v1/scraper/download', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        })
        if (!res.ok) throw new Error((await res.json()).detail || 'Download failed')
        return res.json()
    },
    async taskStatus(taskId) {
        const res = await fetch(`/api/v1/scraper/task/${taskId}`)
        if (!res.ok) throw new Error('Task not found')
        return res.json()
    }
}

export const useScraperStore = defineStore('scraper', () => {
    const state = reactive({
        site: 'toongod',
        baseUrl: 'https://toongod.org',
        mode: 'http',
        httpMode: true,
        headless: true,
        manualChallenge: false,
        storageStatePath: 'data/toongod_state.json',
        concurrency: 6,
        keyword: '',
        view: 'search'
    })

    const loading = ref(false)
    const error = ref('')
    const results = ref([])
    const selectedManga = ref(null)
    const chapters = ref([])
    const selectedIds = ref([])
    const queue = ref([])
    const tasks = reactive({})
    const catalog = reactive({
        items: [],
        page: 1,
        hasMore: false,
        loading: false,
        orderby: null,
        path: null,
        mode: 'all'
    })
    const downloadSummary = computed(() => {
        const total = chapters.value.length
        const done = chapters.value.filter(chapter => chapter.downloaded_count > 0).length
        return { total, done }
    })

    const task = reactive({
        id: null,
        chapterId: null,
        status: null,
        message: '',
        report: null
    })
    let pollTimer = null

    function setSite(site) {
        state.site = site
        if (site === 'mangaforfree') {
            state.baseUrl = 'https://mangaforfree.com'
            state.storageStatePath = 'data/mangaforfree_state.json'
        } else if (site === 'toongod') {
            state.baseUrl = 'https://toongod.org'
            state.storageStatePath = 'data/toongod_state.json'
        }
        applyCatalogMode()
    }

    function setMode(mode) {
        state.mode = mode
        if (mode === 'headed') {
            state.httpMode = false
            state.headless = false
            state.manualChallenge = true
        } else {
            state.httpMode = true
            state.headless = true
            state.manualChallenge = false
        }
    }

    function getCatalogBasePath() {
        if (state.site === 'toongod') return '/webtoon/'
        return '/manga/'
    }

    function applyCatalogMode() {
        const basePath = getCatalogBasePath()
        if (catalog.mode === 'views') {
            catalog.path = basePath
            catalog.orderby = 'views'
        } else if (catalog.mode === 'new') {
            catalog.path = basePath
            catalog.orderby = 'new-manga'
        } else if (catalog.mode === 'genre-manga') {
            catalog.path = '/manga-genre/manga/'
            catalog.orderby = null
        } else if (catalog.mode === 'genre-webtoon') {
            catalog.path = '/manga-genre/webtoon/'
            catalog.orderby = null
        } else {
            catalog.path = basePath
            catalog.orderby = null
        }
    }

    function setView(view) {
        state.view = view
        if (view === 'catalog' && catalog.items.length === 0) {
            loadCatalog(true)
        }
    }

    function setCatalogMode(mode) {
        catalog.mode = mode
        applyCatalogMode()
        loadCatalog(true)
    }

    function getPayload() {
        return {
            base_url: state.baseUrl,
            http_mode: state.httpMode,
            headless: state.headless,
            manual_challenge: state.manualChallenge,
            storage_state_path: state.storageStatePath || null,
            concurrency: state.concurrency
        }
    }

    async function search() {
        if (state.view !== 'search') {
            state.view = 'search'
        }
        const kw = state.keyword.trim()
        if (!kw) { error.value = '请输入关键词'; return }
        loading.value = true
        error.value = ''
        results.value = []
        chapters.value = []
        selectedManga.value = null
        try {
            if (kw.startsWith('http')) {
                const url = new URL(kw)
                state.baseUrl = url.origin
                const id = url.pathname.split('/').filter(Boolean).pop() || url.hostname
                const manga = { id, title: id, url: kw }
                results.value = [manga]
                await selectManga(manga)
            } else {
                results.value = await api.search({ ...getPayload(), keyword: kw })
            }
        } catch (e) {
            error.value = e.message
        } finally {
            loading.value = false
        }
    }

    async function selectManga(manga) {
        selectedManga.value = manga
        loading.value = true
        error.value = ''
        chapters.value = []
        selectedIds.value = []
        try {
            chapters.value = await api.chapters({ ...getPayload(), manga })
            chapters.value = chapters.value.map(chapter => ({
                ...chapter,
                downloaded: !!chapter.downloaded,
                downloaded_count: chapter.downloaded_count || 0,
                downloaded_total: chapter.downloaded_total || 0
            }))
        } catch (e) {
            error.value = e.message
        } finally {
            loading.value = false
        }
    }

    async function loadCatalog(reset = false) {
        if (catalog.loading) return
        catalog.loading = true
        error.value = ''
        try {
            if (reset) {
                catalog.page = 1
                catalog.items = []
            }
            const orderby = catalog.orderby || null
            const data = await api.catalog({
                ...getPayload(),
                page: catalog.page,
                orderby,
                path: catalog.path || null
            })
            if (reset) {
                catalog.items = data.items
            } else {
                catalog.items = [...catalog.items, ...data.items]
            }
            catalog.page = data.page
            catalog.hasMore = data.has_more
        } catch (e) {
            error.value = e.message
        } finally {
            catalog.loading = false
        }
    }

    function loadMoreCatalog() {
        if (catalog.loading || !catalog.hasMore) return
        catalog.page += 1
        loadCatalog(false)
    }

    function isQueued(chapterId) {
        return queue.value.some(item => item.id === chapterId)
    }

    function isChapterBusy(chapterId) {
        const status = tasks[chapterId]?.status
        if (status && ['queued', 'pending', 'running'].includes(status)) return true
        return task.chapterId === chapterId && ['pending', 'running'].includes(task.status)
    }

    function updateTask(chapterId, payload) {
        tasks[chapterId] = { ...(tasks[chapterId] || {}), ...payload }
    }

    function enqueue(chapter) {
        if (isQueued(chapter.id) || isChapterBusy(chapter.id)) return
        queue.value.push(chapter)
        updateTask(chapter.id, { status: 'queued', message: '排队中', report: null })
        processQueue()
    }

    function enqueueMany(items) {
        items.forEach(item => enqueue(item))
    }

    async function startDownload(chapter) {
        if (!selectedManga.value) { error.value = '请先选择漫画'; return }
        stopPolling()
        task.status = 'pending'
        task.message = '提交下载任务中...'
        task.report = null
        task.chapterId = chapter.id
        error.value = ''
        updateTask(chapter.id, { status: 'pending', message: '提交下载任务中...', report: null })
        try {
            const data = await api.download({ ...getPayload(), manga: selectedManga.value, chapter })
            task.id = data.task_id
            task.status = data.status
            task.message = data.message || '已提交下载任务'
            updateTask(chapter.id, { status: data.status, message: task.message, report: data.report || null })
            schedulePoll()
        } catch (e) {
            error.value = e.message
            task.message = '下载任务提交失败'
            task.status = 'error'
            updateTask(chapter.id, { status: 'error', message: task.message })
        }
    }

    function processQueue() {
        if (task.status === 'running' || task.status === 'pending') return
        if (queue.value.length === 0) return
        const next = queue.value.shift()
        if (!next) return
        startDownload(next)
    }

    function download(chapter) {
        enqueue(chapter)
    }

    function downloadSelected() {
        const targets = chapters.value.filter(chapter => selectedIds.value.includes(chapter.id))
        enqueueMany(targets)
    }

    function schedulePoll(delay = 2000) {
        stopPolling()
        pollTimer = setTimeout(poll, delay)
    }

    function stopPolling() {
        if (pollTimer) { clearTimeout(pollTimer); pollTimer = null }
    }

    async function poll() {
        if (!task.id) return
        try {
            const data = await api.taskStatus(task.id)
            task.status = data.status
            task.message = data.message || ''
            task.report = data.report || null
            if (task.chapterId) {
                updateTask(task.chapterId, {
                    status: data.status,
                    message: task.message,
                    report: data.report || null
                })
                if (data.report) {
                    const target = chapters.value.find(ch => ch.id === task.chapterId)
                    if (target) {
                        const success = data.report.success_count || 0
                        const failed = data.report.failed_count || 0
                        target.downloaded_count = success
                        target.downloaded_total = success + failed
                        target.downloaded = success > 0
                    }
                }
            }
            if (data.status === 'running' || data.status === 'pending') {
                schedulePoll()
            } else {
                stopPolling()
                processQueue()
            }
        } catch (e) {
            task.message = '任务状态获取失败'
        }
    }

    function statusLabel(s) {
        const map = { queued: '排队中', pending: '排队中', running: '下载中', success: '已完成', partial: '部分成功', error: '失败' }
        return map[s] || s || '暂无任务'
    }

    function statusClass(s) {
        const map = {
            success: 'bg-green-500/20 text-green-300 border border-green-500/30',
            partial: 'bg-amber-500/20 text-amber-300 border border-amber-500/30',
            error: 'bg-red-500/20 text-red-300 border border-red-500/30',
            running: 'bg-blue-500/20 text-blue-300 border border-blue-500/30'
        }
        return map[s] || 'bg-slate-700/40 text-slate-300 border border-slate-500/30'
    }

    function toggleSelection(chapterId) {
        if (selectedIds.value.includes(chapterId)) {
            selectedIds.value = selectedIds.value.filter(id => id !== chapterId)
        } else {
            selectedIds.value = [...selectedIds.value, chapterId]
        }
    }

    function selectAll() {
        selectedIds.value = chapters.value.map(chapter => chapter.id)
    }

    function clearSelection() {
        selectedIds.value = []
    }

    function chapterStatus(chapterId) {
        return tasks[chapterId]?.status || null
    }

    function downloadedLabel(chapter) {
        if (!chapter.downloaded_count) return ''
        if (chapter.downloaded_total > 0 && chapter.downloaded_count < chapter.downloaded_total) {
            return `已下载 ${chapter.downloaded_count}/${chapter.downloaded_total}`
        }
        return '已下载'
    }

    function downloadedClass(chapter) {
        if (!chapter.downloaded_count) return ''
        if (chapter.downloaded_total > 0 && chapter.downloaded_count < chapter.downloaded_total) {
            return 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
        }
        return 'bg-green-500/20 text-green-300 border border-green-500/30'
    }

    return {
        state,
        loading,
        error,
        results,
        selectedManga,
        chapters,
        selectedIds,
        queue,
        tasks,
        catalog,
        downloadSummary,
        task,
        setSite,
        setMode,
        setView,
        setCatalogMode,
        search,
        selectManga,
        loadCatalog,
        loadMoreCatalog,
        download,
        downloadSelected,
        toggleSelection,
        selectAll,
        clearSelection,
        chapterStatus,
        isChapterBusy,
        downloadedLabel,
        downloadedClass,
        statusLabel,
        statusClass,
        stopPolling
    }
})
