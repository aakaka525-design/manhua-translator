import { defineStore } from 'pinia'
import { ref, reactive, onMounted } from 'vue'

const STORAGE_KEY = 'manhua_settings'

const availableModels = [
    // Gemini 3.x 系列 (最新)
    { id: 'gemini-3-pro-preview', name: 'Gemini 3 Pro', desc: '最新旗舰，高质量翻译' },
    { id: 'gemini-3-flash-preview', name: 'Gemini 3 Flash', desc: '最新快速模型' },
    // Gemini 2.5 系列
    { id: 'gemini-2.5-flash', name: 'Gemini 2.5 Flash', desc: '平衡速度与质量' },
    { id: 'gemini-2.5-flash-lite', name: 'Gemini 2.5 Flash-Lite', desc: '轻量级快速' },
    { id: 'gemini-2.5-pro-exp', name: 'Gemini 2.5 Pro Exp', desc: '实验版高质量' },
    // PPIO 模型
    { id: 'zai-org/glm-4.7-flash', name: 'GLM-4.7 Flash', desc: 'PPIO 快速翻译' },
    { id: 'deepseek/deepseek-r1-distill-llama-70b', name: 'DeepSeek R1 70B', desc: 'PPIO 高质量' },
    { id: 'deepseek/deepseek-v3', name: 'DeepSeek V3', desc: 'PPIO 通用模型' },
    // 其他
    { id: 'gpt-4o', name: 'GPT-4o', desc: 'OpenAI 模型' }
]

const availableUpscaleModels = [
    { id: 'realesrgan-x4plus-anime', name: 'RealESRGAN Anime x4', desc: '动漫风格优化' },
    { id: 'realesrgan-x4plus', name: 'RealESRGAN x4plus', desc: '通用高清放大' },
    { id: 'realesr-animevideov3-x4', name: 'AnimeVideo v3 x4', desc: '视频动漫优化' }
]

const availableUpscaleScales = [2, 4]

export const useSettingsStore = defineStore('settings', () => {
    const showModal = ref(false)
    const showLogsModal = ref(false)
    const logsContent = ref('')
    const loading = ref(false)

    const settings = reactive({
        aiModel: 'zai-org/glm-4.7-flash',
        aiModelName: 'GLM-4.7 Flash',
        sourceLang: 'en',
        targetLang: 'zh',
        theme: 'default', // default (dark) or pop (light)
        upscaleModel: 'realesrgan-x4plus-anime',
        upscaleScale: 2,
        upscaleEnabled: true
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

    async function selectUpscaleModel(model) {
        settings.upscaleModel = model.id
        saveSettings()
        try {
            await fetch('/api/v1/settings/upscale', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    model: settings.upscaleModel,
                    scale: settings.upscaleScale,
                    enabled: settings.upscaleEnabled
                })
            })
        } catch (e) {
            console.error('Failed to update upscale model:', e)
        }
    }

    async function selectUpscaleScale(scale) {
        settings.upscaleScale = scale
        saveSettings()
        try {
            await fetch('/api/v1/settings/upscale', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    model: settings.upscaleModel,
                    scale: settings.upscaleScale,
                    enabled: settings.upscaleEnabled
                })
            })
        } catch (e) {
            console.error('Failed to update upscale scale:', e)
        }
    }

    async function setUpscaleEnabled(enabled) {
        settings.upscaleEnabled = enabled
        saveSettings()
        try {
            await fetch('/api/v1/settings/upscale', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    model: settings.upscaleModel,
                    scale: settings.upscaleScale,
                    enabled: settings.upscaleEnabled
                })
            })
        } catch (e) {
            console.error('Failed to update upscale enabled:', e)
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
        availableUpscaleModels,
        availableUpscaleScales,
        saveSettings,
        selectModel,
        selectUpscaleModel,
        selectUpscaleScale,
        setUpscaleEnabled,
        openLogs,
        fetchLogs,
        toggleTheme
    }
})
