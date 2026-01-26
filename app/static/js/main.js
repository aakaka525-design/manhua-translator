/**
 * Main Application Function
 */
import Alpine from 'https://unpkg.com/alpinejs@3.13.3/dist/module.esm.js';
import { getSSEDelay } from './modules/utils.js';
import { createApiSlice } from './modules/api.js';
import { createReaderSlice } from './modules/reader.js';
import { createScraperSlice } from './modules/scraper.js';

window.Alpine = Alpine;

Alpine.data('mangaApp', () => ({
    view: 'dashboard',
    loading: false,
    mangas: [],
    currentManga: null,
    chapters: [],
    currentChapter: null,
    nextChapterId: null,
    pages: [],
    compareMode: false,
    renderCount: 0,
    pageBatchSize: 6,
    scrollListener: null,
    eventSource: null,
    sseRetry: 0,
    sseRetryTimer: null,
    visibilityHandler: null,
    toasts: [],
    showBackToTop: false,
    readProgress: 0,
    hideToolbar: false,
    lastScrollY: 0,
    readingHistory: {},

    showSettings: false,
    showLogsModal: false,
    logsContent: '',
    contextMenu: { visible: false, x: 0, y: 0, item: null, type: null },
    touchTimer: null,

    scraper: {
        site: 'toongod',
        mode: 'http',
        baseUrl: 'https://toongod.org',
        keyword: '',
        results: [],
        chapters: [],
        selectedManga: null,
        loading: false,
        error: '',
        httpMode: true,
        headless: true,
        manualChallenge: false,
        userDataDir: '',
        browserChannel: '',
        storageStatePath: 'data/toongod_state.json',
        concurrency: 6,
        taskId: null,
        taskStatus: null,
        taskMessage: '',
        taskReport: null,
    },
    scraperTaskTimer: null,

    // AI Model Settings
    settings: {
        aiModel: 'glm-4-flash-250414',
        aiModelName: 'GLM-4 Flash',
        sourceLang: 'en',
        targetLang: 'zh'
    },
    availableModels: [
        { id: 'glm-4-flash-250414', name: 'GLM-4 Flash', desc: '快速响应，适合大批量翻译' },
        { id: 'deepseek-v3-250324', name: 'DeepSeek V3', desc: '高质量翻译，速度适中' },
        { id: 'qwen3-30b-a3b', name: 'Qwen3 30B', desc: '阿里通义千问，均衡性能' },
        { id: 'gemini-2.0-flash', name: 'Gemini 2.0 Flash', desc: 'Google Gemini，需配置 GEMINI_API_KEY' },
        { id: 'gpt-4o-mini', name: 'GPT-4o Mini', desc: 'OpenAI 兼容模型' },
    ],

    // Merge logic modules
    ...createApiSlice(),
    ...createReaderSlice(),
    ...createScraperSlice(),

    async init() {
        this.loadSettings();
        this.loadHistory();
        await this.refreshData();
        this.setupVisibilityListener();
        this.setupKeyboardListener();
        this.initSSE();
        this.setScraperMode();
    },

    loadSettings() {
        const saved = localStorage.getItem('manhua_settings');
        if (saved) {
            try {
                const parsed = JSON.parse(saved);
                this.settings = { ...this.settings, ...parsed };
            } catch (e) {
                console.error('Failed to load settings:', e);
            }
        }
    },

    saveSettings() {
        localStorage.setItem('manhua_settings', JSON.stringify(this.settings));
    },

    loadHistory() {
        const saved = localStorage.getItem('manhua_history');
        if (saved) {
            try {
                this.readingHistory = JSON.parse(saved);
            } catch (e) {
                console.error('Failed to load history:', e);
            }
        }
    },

    saveHistory(mangaId, chapterId, chapterName) {
        this.readingHistory[mangaId] = {
            chapterId,
            chapterName,
            timestamp: Date.now()
        };
        localStorage.setItem('manhua_history', JSON.stringify(this.readingHistory));
    },

    setupVisibilityListener() {
        if (this.visibilityHandler) {
            return;
        }
        this.visibilityHandler = () => {
            if (document.hidden) {
                this.closeSSE();
            } else {
                this.initSSE();
            }
        };
        document.addEventListener('visibilitychange', this.visibilityHandler);
    },

    setView(nextView) {
        if (this.view === 'reader' && nextView !== 'reader') {
            this.teardownReaderScroll();
            this.compareMode = false;
        }
        if (this.view === 'scraper' && nextView !== 'scraper') {
            this.stopScraperPolling();
        }
        this.view = nextView;
    },

    setupKeyboardListener() {
        document.addEventListener('keydown', (e) => {
            if (this.view === 'reader') {
                if (e.key === 'ArrowRight' || e.key === 'l') {
                    this.nextChapter();
                } else if (e.key === 'ArrowLeft' || e.key === 'h') {
                    this.prevChapter();
                } else if (e.key === 'Escape') {
                    this.setView('chapters');
                } else if (e.key === 'c') {
                    this.toggleCompare();
                }
            } else if (this.view === 'chapters') {
                if (e.key === 'Escape') {
                    this.setView('dashboard');
                }
            }
        });
    },

    initSSE() {
        if (document.hidden || this.eventSource) {
            return;
        }
        this.connectSSE();
    },

    connectSSE() {
        if (this.eventSource) {
            this.eventSource.close();
        }
        const eventSource = new EventSource('/api/v1/translate/events');
        this.eventSource = eventSource;

        eventSource.onopen = () => {
            this.sseRetry = 0;
        };

        eventSource.onmessage = (event) => {
            let data;
            try {
                data = JSON.parse(event.data);
            } catch (error) {
                return;
            }

            if (data.type === 'progress') {
                this.handleProgress(data);
            } else if (data.type === 'chapter_start') {
                this.handleChapterStart(data);
            } else if (data.type === 'chapter_complete') {
                this.handleChapterComplete(data);
            } else if (data.type === 'page_complete') {
                this.handlePageComplete(data);
            }
        };

        eventSource.onerror = () => {
            this.handleSSEError(eventSource);
        };
    },

    handleSSEError(eventSource) {
        if (this.eventSource !== eventSource) {
            return;
        }
        eventSource.close();
        this.eventSource = null;
        clearTimeout(this.sseRetryTimer);
        const delay = getSSEDelay(this.sseRetry);
        this.sseRetry += 1;
        this.sseRetryTimer = setTimeout(() => this.connectSSE(), delay);
    },

    closeSSE() {
        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
        }
        clearTimeout(this.sseRetryTimer);
    },

    handleChapterStart(data) {
        if (this.currentManga && this.currentManga.id === data.manga_id) {
            const chapter = this.chapters.find(c => c.id === data.chapter_id);
            if (chapter) {
                chapter.isTranslating = true;
                chapter.progress = 0;
                chapter.totalPages = data.total_pages;
                chapter.completedPages = 0;
                chapter.isComplete = false;
            }
        }
        const manga = this.mangas.find(m => m.id === data.manga_id);
        if (manga) {
            manga.isTranslating = true;
            manga.progress = 0;
        }
    },

    handleProgress(data) {
        // Implementation specific logic can go here
    },

    handleChapterComplete(data) {
        const totalCount = typeof data.total_count === 'number' ? data.total_count : 0;
        const savedCount = typeof data.saved_count === 'number'
            ? data.saved_count
            : (typeof data.success_count === 'number' ? data.success_count : 0);
        const isFullSuccess = totalCount > 0 && savedCount === totalCount;
        const statusText = isFullSuccess ? '已完成' : `已完成 (${savedCount}/${totalCount})`;

        if (!isFullSuccess) {
            this.showToast(`翻译完成，成功 ${savedCount}/${totalCount}`, 'warning');
        } else {
            this.showToast('翻译任务已全部完成', 'success');
        }

        if (this.currentManga && this.currentManga.id === data.manga_id) {
            const chapter = this.chapters.find(c => c.id === data.chapter_id);
            if (chapter) {
                chapter.isTranslating = false;
                chapter.has_translated = savedCount > 0;
                chapter.isComplete = isFullSuccess;
                chapter.progress = 100;
                chapter.statusText = statusText;
            }
        }
        const manga = this.mangas.find(m => m.id === data.manga_id);
        if (manga) {
            manga.isTranslating = false;
        }

        // Always refresh the current view if we are looking at this chapter
        // This ensures file paths are re-verified with backend
        if (this.currentManga && this.currentManga.id === data.manga_id &&
            this.currentChapter && this.currentChapter.id === data.chapter_id) {
            this.openChapter(this.currentChapter);
        }
    },

    handlePageComplete(data) {
        if (this.currentManga && this.currentManga.id === data.manga_id &&
            this.currentChapter && this.currentChapter.id === data.chapter_id) {

            // Update local pages array to force refresh
            const pageIndex = this.pages.findIndex(p => p.name === data.image_name);
            if (pageIndex !== -1) {
                // Update URL with timestamp to bust cache
                this.pages[pageIndex].translated_url = data.url;
                this.showToast(`单页 ${data.image_name} 翻译完成`, 'success');
            }
        }
    },

    showToast(message, type = 'success') {
        const id = Date.now();
        this.toasts.push({ id, message, type, visible: true });
        setTimeout(() => {
            const idx = this.toasts.findIndex(t => t.id === id);
            if (idx !== -1) this.toasts[idx].visible = false;
            setTimeout(() => {
                this.toasts = this.toasts.filter(t => t.id !== id);
            }, 300);
        }, 3000);
    },

    get currentIndex() {
        if (!this.currentChapter || !this.chapters) return -1;
        return this.chapters.findIndex(c => c.id === this.currentChapter.id);
    },

    get hasPrevChapter() {
        const idx = this.currentIndex;
        return idx > 0;
    },

    get hasNextChapter() {
        const idx = this.currentIndex;
        return idx !== -1 && idx < this.chapters.length - 1;
    },

    prevChapter() {
        if (this.hasPrevChapter) {
            this.openChapter(this.chapters[this.currentIndex - 1]);
        }
    },

    nextChapter() {
        if (this.hasNextChapter) {
            this.openChapter(this.chapters[this.currentIndex + 1]);
        } else {
            this.showToast('已经是最后一章了', 'info');
        }
    },

    showContextMenu(event, item, type) {
        this.contextMenu = {
            visible: true,
            x: event.clientX,
            y: event.clientY,
            item,
            type
        };
    },

    handleTouchStart(event, item, type) {
        this.touchTimer = setTimeout(() => {
            const touch = event.touches[0];
            this.showContextMenu({ clientX: touch.clientX, clientY: touch.clientY }, item, type);
        }, 800);
    },

    handleTouchEnd() {
        if (this.touchTimer) {
            clearTimeout(this.touchTimer);
            this.touchTimer = null;
        }
    }
}));

Alpine.data('compareSlider', () => ({
    sliderVal: 50,
    isDragging: false,
    pendingX: null,
    rect: null,
    frame: null,

    startDrag(event, compareMode) {
        if (!compareMode) {
            return;
        }
        this.isDragging = true;
        this.rect = this.$el.getBoundingClientRect();
        if (event.currentTarget && event.currentTarget.setPointerCapture && event.pointerId !== undefined) {
            event.currentTarget.setPointerCapture(event.pointerId);
        }
        this.queueUpdate(event);
    },

    stopDrag() {
        this.isDragging = false;
        this.pendingX = null;
        this.rect = null;
    },

    handleMove(event, compareMode) {
        if (!this.isDragging || !compareMode) {
            return;
        }
        this.queueUpdate(event);
    },

    queueUpdate(event) {
        const clientX = event.touches ? event.touches[0].clientX : event.clientX;
        this.pendingX = clientX;
        if (this.frame) {
            return;
        }
        this.frame = requestAnimationFrame(() => {
            this.frame = null;
            if (!this.rect || this.pendingX === null) {
                return;
            }
            const relative = (this.pendingX - this.rect.left) / this.rect.width;
            this.sliderVal = Math.max(0, Math.min(100, relative * 100));
        });
    }
}));

// Alpine Directive for Double Tap
Alpine.directive('double-tap', (el, { expression }, { evaluate }) => {
    let lastTap = 0;
    let scale = 1;

    el.addEventListener('touchend', (e) => {
        const currentTime = new Date().getTime();
        const tapLength = currentTime - lastTap;

        if (tapLength < 300 && tapLength > 0) {
            // Double tap detected
            e.preventDefault();
            if (scale === 1) {
                scale = 2;
                el.style.transform = `scale(2)`;
                el.style.zIndex = 100;
            } else {
                scale = 1;
                el.style.transform = `scale(1)`;
                el.style.zIndex = 'auto';
            }
            el.style.transition = 'transform 0.3s ease';
        }
        lastTap = currentTime;
    });
});

Alpine.start();
