import axios from 'axios'

const api = axios.create({
    baseURL: '/api/v1',
    timeout: 10000
})

function extractApiError(err) {
    const status = err?.response?.status
    const body = err?.response?.data || {}
    const headers = err?.response?.headers || {}

    let message = '请求失败'
    if (typeof body.detail === 'string' && body.detail.trim()) {
        message = body.detail
    } else if (typeof body.error?.message === 'string' && body.error.message.trim()) {
        message = body.error.message
    } else if (typeof err?.message === 'string' && err.message.trim()) {
        message = err.message
    }

    const error = new Error(message)
    error.status = status
    error.code = body.error?.code || err?.code || 'API_ERROR'
    error.requestId = body.error?.request_id || headers['x-request-id'] || null
    error.raw = body
    return error
}

api.interceptors.response.use(
    (response) => response,
    (err) => Promise.reject(extractApiError(err))
)

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
