import { defineStore } from 'pinia'
import { ref, reactive, onMounted } from 'vue'

const STORAGE_KEY = 'manhua_settings'

const availableModels = [
    { id: 'gemini-2.0-flash', name: 'Gemini 2.0 Flash', desc: '快速响应' },
    { id: 'gemini-2.5-pro-exp', name: 'Gemini 2.5 Pro Exp', desc: '高质量翻译' },
    { id: 'gemini-2.0-flash-thinking-exp-01-21', name: 'Gemini Thinking', desc: '思考模式' },
    { id: 'gpt-4o', name: 'GPT-4o', desc: 'OpenAI 模型' }
]

export const useSettingsStore = defineStore('settings', () => {
    const showModal = ref(false)
    const showLogsModal = ref(false)
    const logsContent = ref('')
    const loading = ref(false)

    const settings = reactive({
        aiModel: 'gemini-2.0-flash',
        aiModelName: 'Gemini 2.0 Flash',
        sourceLang: 'en',
        targetLang: 'zh',
        theme: 'default' // default (dark) or pop (light)
    })

    function applyTheme() {
        if (settings.theme === 'pop') {
            document.documentElement.setAttribute('data-theme', 'pop')
        } else {
            document.documentElement.removeAttribute('data-theme')
        }
    }

    function toggleTheme() {
        settings.theme = settings.theme === 'default' ? 'pop' : 'default'
        applyTheme()
        saveSettings()
    }

    function loadSettings() {
        try {
            const saved = localStorage.getItem(STORAGE_KEY)
            if (saved) {
                const parsed = JSON.parse(saved)
                Object.assign(settings, parsed)
            }
            applyTheme()
        } catch (e) {
            console.error('Failed to load settings:', e)
        }
    }

    function saveSettings() {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(settings))
        } catch (e) {
            console.error('Failed to save settings:', e)
        }
    }

    async function selectModel(model) {
        settings.aiModel = model.id
        settings.aiModelName = model.name
        saveSettings()
        try {
            await fetch('/api/v1/settings/model', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ model: model.id })
            })
        } catch (e) {
            console.error('Failed to update model:', e)
        }
    }

    async function fetchLogs() {
        loading.value = true
        try {
            const res = await fetch('/api/v1/system/logs?lines=200')
            if (res.ok) {
                const lines = await res.json()
                logsContent.value = lines.join('')
            } else {
                logsContent.value = '获取日志失败'
            }
        } catch (e) {
            logsContent.value = '网络错误: ' + e.message
        } finally {
            loading.value = false
        }
    }

    function openLogs() {
        showModal.value = false
        showLogsModal.value = true
        fetchLogs()
    }

    // Load on init
    loadSettings()

    return {
        showModal,
        showLogsModal,
        logsContent,
        loading,
        settings,
        availableModels,
        saveSettings,
        selectModel,
        openLogs,
        fetchLogs,
        toggleTheme
    }
})
