import { defineStore } from 'pinia'
import { ref } from 'vue'
import { translateApi } from '@/api'
import { useMangaStore } from './manga'

export const useTranslateStore = defineStore('translate', () => {
    const isConnected = ref(false)
    const eventSource = ref(null)
    const retryCount = ref(0)

    const mangaStore = useMangaStore()

    function initSSE() {
        if (eventSource.value) return

        const url = translateApi.getEventsUrl()
        eventSource.value = new EventSource(url)

        eventSource.value.onopen = () => {
            console.log('SSE Connected')
            isConnected.value = true
            retryCount.value = 0
        }

        eventSource.value.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data)
                handleEvent(data)
            } catch (e) {
                console.error('SSE Parse Error:', e)
            }
        }

        eventSource.value.onerror = (err) => {
            console.error('SSE Error:', err)
            closeSSE()
            // Simple retry logic
            if (retryCount.value < 5) {
                retryCount.value++
                setTimeout(initSSE, 1000 * retryCount.value)
            }
        }
    }

    function closeSSE() {
        if (eventSource.value) {
            eventSource.value.close()
            eventSource.value = null
            isConnected.value = false
        }
    }

    function handleEvent(data) {
        if (data.type === 'chapter_start') {
            const chapter = findChapter(data.manga_id, data.chapter_id)
            if (chapter) {
                chapter.isTranslating = true
                chapter.progress = 0
                chapter.totalPages = data.total_pages
                chapter.completedPages = 0
            }
        } else if (data.type === 'progress') {
            // Update logic if needed
        } else if (data.type === 'chapter_complete') {
            const chapter = findChapter(data.manga_id, data.chapter_id)
            if (chapter) {
                const successCount = data.success_count !== undefined ? data.success_count : chapter.page_count;
                const totalCount = data.total_count !== undefined ? data.total_count : chapter.page_count;
                const isFullSuccess = successCount === totalCount;

                chapter.isTranslating = false
                chapter.has_translated = successCount > 0
                chapter.isComplete = isFullSuccess
                chapter.translated_count = successCount
                chapter.statusText = isFullSuccess ? '已完成' : `已完成 (${successCount}/${totalCount})`
                chapter.progress = 100
            }
        } else if (data.type === 'page_complete') {
            const chapter = findChapter(data.manga_id, data.chapter_id)
            if (chapter) {
                // Update page logic would go here if we had page store accessible
                console.log('Page translated:', data.image_name)
            }
        }
    }

    function findChapter(mangaId, chapterId) {
        // Only update if we are looking at the relevant manga
        if (mangaStore.currentManga && mangaStore.currentManga.id === mangaId) {
            return mangaStore.chapters.find(c => c.id === chapterId)
        }
        return null
    }

    return {
        isConnected,
        initSSE,
        closeSSE
    }
})
