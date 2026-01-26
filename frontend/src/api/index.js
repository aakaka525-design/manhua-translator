import axios from 'axios'

const api = axios.create({
    baseURL: '/api/v1',
    timeout: 10000
})

export const mangaApi = {
    // Get all mangas
    list: async () => {
        const { data } = await api.get('/manga')
        return data
    },

    // Get chapters for a manga
    getChapters: async (mangaId) => {
        const { data } = await api.get(`/manga/${mangaId}/chapters`)
        return data
    },

    // Get chapter details (pages)
    getChapter: async (mangaId, chapterId) => {
        const { data } = await api.get(`/manga/${mangaId}/chapter/${chapterId}`)
        return data
    },

    // Delete manga
    deleteManga: async (mangaId) => {
        const { data } = await api.delete(`/manga/${mangaId}`)
        return data
    },

    // Delete chapter
    deleteChapter: async (mangaId, chapterId) => {
        const { data } = await api.delete(`/manga/${mangaId}/chapter/${chapterId}`)
        return data
    }
}

export const translateApi = {
    // Translate a chapter
    translateChapter: async (payload) => {
        const { data } = await api.post('/translate/chapter', payload)
        return data
    },

    // Re-translate a single page
    retranslatePage: async (payload) => {
        const { data } = await api.post('/translate/page', payload)
        return data
    },

    // Get SSE event source URL
    getEventsUrl: () => '/api/v1/translate/events'
}

export const systemApi = {
    getLogs: async (lines = 100) => {
        const { data } = await api.get(`/system/logs?lines=${lines}`)
        return data
    }
}

export default api
