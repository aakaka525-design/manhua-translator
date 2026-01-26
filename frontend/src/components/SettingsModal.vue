<script setup>
import { useSettingsStore } from '@/stores/settings'

const settingsStore = useSettingsStore()
</script>

<template>
  <!-- Settings Modal -->
  <Teleport to="body">
    <div v-if="settingsStore.showModal" class="fixed inset-0 z-[100] flex items-center justify-center p-4">
      <div class="absolute inset-0 bg-black/60 backdrop-blur-sm" @click="settingsStore.showModal = false"></div>
      <div class="bg-surface border border-slate-700 w-full max-w-lg rounded-2xl p-6 relative z-10 shadow-2xl">
        <div class="flex items-center justify-between mb-6">
          <h3 class="text-xl font-bold flex items-center gap-2">
            <i class="fas fa-sliders-h text-accent-1"></i> 设置
          </h3>
          <button @click="settingsStore.showModal = false" class="p-2 hover:bg-white/10 rounded-full transition">
            <i class="fas fa-times"></i>
          </button>
        </div>

        <div class="space-y-6 max-h-[70vh] overflow-y-auto pr-2">
          <!-- Appearance -->
          <div>
            <h4 class="text-sm font-semibold text-slate-400 mb-3 uppercase tracking-wider">外观</h4>
            <button @click="settingsStore.toggleTheme()"
              class="w-full px-4 py-3 rounded-xl text-left transition flex items-center justify-between group border border-transparent bg-slate-800/50 hover:bg-slate-800">
              <div class="flex items-center gap-3">
                <div class="w-8 h-8 rounded-lg flex items-center justify-center transition-colors"
                  :class="settingsStore.settings.theme === 'pop' ? 'bg-accent-1 text-white' : 'bg-slate-700 text-slate-400'">
                  <i class="fas" :class="settingsStore.settings.theme === 'pop' ? 'fa-bolt' : 'fa-moon'"></i>
                </div>
                <div>
                  <span class="font-medium block text-slate-200">
                    {{ settingsStore.settings.theme === 'pop' ? 'High-Voltage Pop' : 'Dark Glass' }}
                  </span>
                  <span class="text-xs text-slate-500">
                    {{ settingsStore.settings.theme === 'pop' ? '高亮波普风格' : '沉浸式暗黑风格' }}
                  </span>
                </div>
              </div>
              <div class="relative w-11 h-6 bg-slate-700 rounded-full transition-colors duration-200"
                :class="settingsStore.settings.theme === 'pop' ? 'bg-accent-1' : 'bg-slate-700'">
                <div class="absolute top-1 left-1 bg-white w-4 h-4 rounded-full transition-transform duration-200"
                  :class="settingsStore.settings.theme === 'pop' ? 'translate-x-5' : ''"></div>
              </div>
            </button>
          </div>

          <!-- AI Model -->
          <div>
            <h4 class="text-sm font-semibold text-slate-400 mb-3 uppercase tracking-wider">AI 模型</h4>
            <div class="space-y-2">
              <button v-for="model in settingsStore.availableModels" :key="model.id"
                @click="settingsStore.selectModel(model)"
                class="w-full px-4 py-3 rounded-xl text-left transition flex items-center justify-between group border"
                :class="settingsStore.settings.aiModel === model.id ? 'bg-accent-1/20 border-accent-1/30' : 'bg-slate-800/50 border-transparent hover:bg-slate-800'">
                <div class="flex items-center gap-3">
                  <div class="w-8 h-8 rounded-lg flex items-center justify-center"
                    :class="settingsStore.settings.aiModel === model.id ? 'bg-accent-1 text-white' : 'bg-slate-700 text-slate-400'">
                    <i class="fas fa-robot"></i>
                  </div>
                  <div>
                    <span class="font-medium block"
                      :class="settingsStore.settings.aiModel === model.id ? 'text-accent-1' : 'text-slate-200'">
                      {{ model.name }}
                    </span>
                    <span class="text-xs text-slate-500">{{ model.desc }}</span>
                  </div>
                </div>
                <div class="w-5 h-5 rounded-full border border-slate-600 flex items-center justify-center">
                  <div class="w-2.5 h-2.5 rounded-full bg-accent-1 transition-transform"
                    :class="settingsStore.settings.aiModel === model.id ? 'scale-100' : 'scale-0'"></div>
                </div>
              </button>
            </div>
          </div>

          <!-- Language -->
          <div>
            <h4 class="text-sm font-semibold text-slate-400 mb-3 uppercase tracking-wider">翻译偏好</h4>
            <div class="grid grid-cols-2 gap-4">
              <div>
                <label class="text-xs text-slate-500 mb-1 block">源语言</label>
                <select v-model="settingsStore.settings.sourceLang" @change="settingsStore.saveSettings()"
                  class="w-full bg-slate-800 border border-slate-700 text-slate-200 rounded-lg px-3 py-2 text-sm focus:border-accent-1 focus:outline-none">
                  <option value="en">English (英语)</option>
                  <option value="ja">Japanese (日语)</option>
                  <option value="ko">Korean (韩语)</option>
                  <option value="zh">Chinese (中文)</option>
                </select>
              </div>
              <div>
                <label class="text-xs text-slate-500 mb-1 block">目标语言</label>
                <select v-model="settingsStore.settings.targetLang" @change="settingsStore.saveSettings()"
                  class="w-full bg-slate-800 border border-slate-700 text-slate-200 rounded-lg px-3 py-2 text-sm focus:border-accent-1 focus:outline-none">
                  <option value="zh">Chinese (中文)</option>
                  <option value="en">English (英语)</option>
                  <option value="ja">Japanese (日语)</option>
                </select>
              </div>
            </div>
          </div>

          <!-- System -->
          <div>
            <h4 class="text-sm font-semibold text-slate-400 mb-3 uppercase tracking-wider">系统</h4>
            <button @click="settingsStore.openLogs()"
              class="w-full px-4 py-3 rounded-xl bg-slate-800/50 hover:bg-slate-800 border border-transparent hover:border-slate-700 text-left transition flex items-center justify-between">
              <div class="flex items-center gap-3">
                <div class="w-8 h-8 rounded-lg bg-slate-700 text-slate-400 flex items-center justify-center">
                  <i class="fas fa-terminal"></i>
                </div>
                <div>
                  <span class="font-medium block text-slate-200">系统日志</span>
                  <span class="text-xs text-slate-500">查看最近的运行日志</span>
                </div>
              </div>
              <i class="fas fa-chevron-right text-slate-600"></i>
            </button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>

  <!-- Logs Modal -->
  <Teleport to="body">
    <div v-if="settingsStore.showLogsModal" class="fixed inset-0 z-[100] flex items-center justify-center p-4">
      <div class="absolute inset-0 bg-black/60 backdrop-blur-sm" @click="settingsStore.showLogsModal = false"></div>
      <div class="bg-surface border border-slate-700 w-full max-w-4xl rounded-2xl p-6 relative z-10 shadow-2xl">
        <div class="flex items-center justify-between mb-4">
          <h3 class="text-xl font-bold flex items-center gap-2">
            <i class="fas fa-terminal text-accent-2"></i> 系统日志
          </h3>
          <button @click="settingsStore.showLogsModal = false" class="p-2 hover:bg-white/10 rounded-full transition">
            <i class="fas fa-times"></i>
          </button>
        </div>
        <pre class="bg-black/50 rounded-xl p-4 text-xs text-green-400 font-mono overflow-auto h-[60vh] whitespace-pre-wrap">{{ settingsStore.logsContent || 'Loading...' }}</pre>
        <div class="mt-4 flex justify-end">
          <button @click="settingsStore.fetchLogs()" :disabled="settingsStore.loading"
            class="px-4 py-2 rounded-lg bg-slate-800 text-sm hover:bg-slate-700 transition">
            <i class="fas fa-sync-alt mr-2" :class="{ 'animate-spin': settingsStore.loading }"></i> 刷新
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
