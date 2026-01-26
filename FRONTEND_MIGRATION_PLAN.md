# Vue3 前端迁移计划

基于 **Neo-Comic Realism** 设计规范，将现有 Vanilla JS + Jinja2 前端迁移至 Vue3。

---

> [!IMPORTANT]
> **迁移期间保持后端 API 不变**  
> 前端完全重构，后端 FastAPI 保持现有接口，确保平滑过渡。

> [!WARNING]
> **关键风险点**
> - SSE (Server-Sent Events) 翻译进度需要在 Vue 中正确处理
> - 图片路径需要适配 Vite 的静态资源处理
> - 阅读器的横向滚动需要特别测试移动端兼容性

> [!CAUTION]
> **项目核心功能迁移注意**
> 1. **漫画爬取器** - 需要保持 WebSocket/轮询状态更新、站点配置切换
> 2. **翻译进度 SSE** - `EventSource` 需要在组件销毁时正确关闭，避免内存泄漏
> 3. **阅读器** - 分页加载、无限滚动、对比模式、阅读进度记忆
> 4. **设置面板** - AI 模型切换、语言选择需要持久化到 localStorage
> 5. **右键菜单/长按菜单** - 需要适配 Vue 的事件处理方式
> 6. **Toast 通知** - 需要全局状态管理或 provide/inject
> 7. **键盘快捷键** - 需要在 Vue 中正确绑定和解绑

> [!NOTE]
> **可选优化**
> - 考虑 PWA 支持（离线阅读）
> - 虚拟滚动优化长列表性能
> - 图片懒加载 + 预加载策略

---

## 项目概览

| 项目 | 当前 | 迁移后 |
|------|------|--------|
| 框架 | **Alpine.js 3.x** | Vue 3 (Composition API) |
| 构建 | ES Modules (unpkg CDN) | Vite |
| 样式 | Vanilla CSS | Tailwind CSS + GSAP |
| 状态管理 | Alpine.data() 单例 | Pinia |
| 路由 | 自实现 (view 变量切换) | Vue Router |

> [!TIP]
> **Alpine.js → Vue3 语法映射**
> | Alpine.js | Vue 3 |
> |-----------|-------|
> | `x-data` | `<script setup>` + `ref()`/`reactive()` |
> | `x-show` / `x-if` | `v-show` / `v-if` |
> | `x-for` | `v-for` |
> | `x-bind:` / `:` | `v-bind:` / `:` |
> | `x-on:` / `@` | `v-on:` / `@` |
> | `x-model` | `v-model` |
> | `x-text` / `x-html` | `{{ }}` / `v-html` |
> | `$refs` | `ref` + `useTemplateRef()` |
> | `$watch` | `watch()` / `watchEffect()` |
> | `Alpine.store()` | Pinia store |

---

## 技术栈

```
Frontend/
├── Vue 3 (Composition API + <script setup>)
├── Vite (构建工具)
├── Tailwind CSS (原子化样式)
├── Pinia (状态管理)
├── Vue Router (SPA 路由)
├── GSAP (滚动视差、时间轴动画)
├── VueUse (工具函数)
└── Axios (API 请求)
```

---

## 阶段规划

### Phase 1: 项目初始化 (0.5天)

- [ ] 创建 Vite + Vue3 项目
- [ ] 配置 Tailwind CSS + 设计系统
- [ ] 设置代理到 FastAPI 后端
- [ ] 创建基础目录结构

```
frontend/
├── src/
│   ├── assets/          # 静态资源
│   │   ├── fonts/       # 字体文件
│   │   └── textures/    # 网点纹理
│   ├── components/      # 可复用组件
│   │   ├── ui/          # 基础 UI
│   │   └── layout/      # 布局组件
│   ├── views/           # 页面视图
│   ├── composables/     # 组合式函数
│   ├── stores/          # Pinia Store
│   ├── api/             # API 封装
│   └── styles/          # 全局样式
├── tailwind.config.js
└── vite.config.js
```

---

### Phase 2: 设计系统实现 (1天)

#### 2.1 Tailwind 主题配置

```javascript
// tailwind.config.js
export default {
  theme: {
    extend: {
      colors: {
        'bg-primary': '#0F0F11',
        'surface': '#1A1A1E',
        'accent-1': '#FF0055',  // 霓虹玫红
        'accent-2': '#00F0FF',  // 赛博青
        'text-main': '#F0F0F0',
      },
      fontFamily: {
        'heading': ['Bebas Neue', 'sans-serif'],
        'body': ['Inter', 'sans-serif'],
        'comic': ['Bangers', 'cursive'],
      },
      boxShadow: {
        'comic': '5px 5px 0px 0px #FF0055',
        'comic-hover': '7px 7px 0px 0px #00F0FF',
      }
    }
  }
}
```

#### 2.2 核心样式组件

- [ ] `ComicBackground.vue` - 半色调网点背景
- [ ] `ComicCard.vue` - 手绘边框卡片 + 3D Tilt
- [ ] `GlassNav.vue` - 毛玻璃导航栏
- [ ] `ComicCursor.vue` - 自定义光标

---

### Phase 3: 组件迁移 (1.5天)

#### 现有组件 → Vue 组件映射

| 现有 HTML/JS | Vue 组件 | 说明 |
|--------------|----------|------|
| `index.html` | `App.vue` | 根组件 |
| `partials/views/home.html` | `views/HomeView.vue` | Bento Grid 首页 |
| `partials/views/manga.html` | `views/MangaView.vue` | 漫画详情 |
| `partials/views/reader.html` | `views/ReaderView.vue` | 阅读器 |
| `partials/ui/sidebar.html` | `components/layout/Sidebar.vue` | 侧边导航 |
| `partials/ui/loading.html` | `components/ui/ComicLoading.vue` | 漫画骨架屏 |
| `modules/api.js` | `api/index.js` | API 封装 |
| `modules/scraper.js` | `composables/useScraper.js` | 爬取功能 |

---

### Phase 4: 状态管理 (0.5天)

#### Pinia Store 结构

```javascript
// stores/manga.js
export const useMangaStore = defineStore('manga', () => {
  const mangas = ref([])
  const selectedManga = ref(null)
  const chapters = ref([])
  
  async function fetchMangas() { ... }
  async function selectManga(id) { ... }
  
  return { mangas, selectedManga, chapters, fetchMangas, selectManga }
})

// stores/translate.js
export const useTranslateStore = defineStore('translate', () => {
  const progress = ref({})
  const translating = ref(false)
  
  async function startTranslation(chapterId) { ... }
  function updateProgress(data) { ... }
  
  return { progress, translating, startTranslation, updateProgress }
})
```

---

### Phase 5: 动效实现 (0.5天)

#### GSAP 集成

```javascript
// composables/useParallax.js
export function useParallax() {
  onMounted(() => {
    gsap.registerPlugin(ScrollTrigger)
    
    // 视差滚动
    gsap.to('.parallax-bg', {
      y: '30%',
      scrollTrigger: {
        trigger: '.parallax-container',
        scrub: true
      }
    })
  })
}
```

#### 核心动效

- [ ] 卡片 3D Tilt (VanillaTilt.js)
- [ ] Glitch 效果 (CSS + JS)
- [ ] 撕纸转场 (GSAP)
- [ ] 墨水加载动画

---

### Phase 6: API 集成 (0.5天)

```javascript
// api/index.js
import axios from 'axios'

const api = axios.create({
  baseURL: '/api/v1'
})

export const mangaApi = {
  list: () => api.get('/manga/list'),
  chapters: (id) => api.get(`/manga/${id}/chapters`),
  images: (mangaId, chapterId) => api.get(`/manga/${mangaId}/chapter/${chapterId}/images`)
}

export const translateApi = {
  start: (data) => api.post('/translate/chapter', data),
  events: () => new EventSource('/api/v1/translate/events')
}
```

---

### Phase 7: 测试与集成 (0.5天)

- [ ] 开发环境联调
- [ ] 生产构建配置
- [ ] FastAPI 静态文件服务集成
- [ ] 部署测试

---

## 与 FastAPI 集成

### 开发模式

```javascript
// vite.config.js
export default defineConfig({
  server: {
    proxy: {
      '/api': 'http://localhost:8000'
    }
  }
})
```

### 生产模式

构建后的文件放入 `app/static/dist/`，FastAPI 直接服务：

```python
# app/main.py
app.mount("/", StaticFiles(directory="app/static/dist", html=True))
```

---

## 时间估算

| 阶段 | 时间 |
|------|------|
| Phase 1: 项目初始化 | 0.5 天 |
| Phase 2: 设计系统 | 1 天 |
| Phase 3: 组件迁移 | 1.5 天 |
| Phase 4: 状态管理 | 0.5 天 |
| Phase 5: 动效实现 | 0.5 天 |
| Phase 6: API 集成 | 0.5 天 |
| Phase 7: 测试集成 | 0.5 天 |
| **总计** | **~5 天** |

---

## 关键设计元素实现

### 半色调网点背景

```vue
<template>
  <div class="halftone-bg" />
</template>

<style>
.halftone-bg {
  @apply fixed inset-0 -z-10;
  background-color: #0F0F11;
  background-image: radial-gradient(#333 1px, transparent 1px);
  background-size: 20px 20px;
}
</style>
```

### 漫画卡片组件

```vue
<template>
  <div 
    class="comic-card group cursor-pointer"
    @mouseenter="onHover"
  >
    <img :src="cover" class="transition-transform group-hover:scale-110" />
    <div class="p-4">
      <h3 class="font-comic text-xl">{{ title }}</h3>
    </div>
  </div>
</template>

<style>
.comic-card {
  @apply bg-surface rounded-lg overflow-hidden;
  border: 3px solid #000;
  box-shadow: 5px 5px 0px 0px theme('colors.accent-1');
  transition: all 0.2s ease;
}

.comic-card:hover {
  transform: translate(-2px, -2px);
  box-shadow: 7px 7px 0px 0px theme('colors.accent-2');
}
</style>
```

### Bento Grid 布局

```vue
<template>
  <div class="bento-grid">
    <ComicCard size="large" />  <!-- 2x2 -->
    <ComicCard size="wide" />   <!-- 2x1 -->
    <ComicCard />               <!-- 1x1 -->
  </div>
</template>

<style>
.bento-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1rem;
}

.bento-grid .large { grid-area: span 2 / span 2; }
.bento-grid .wide { grid-area: span 1 / span 2; }
</style>
```

---

## 下一步

1. 确认技术栈选择
2. 创建 frontend 目录并初始化项目
3. 逐步迁移组件

---

## ⚠️ 特别说明

### 字体授权
- **Bebas Neue**: 免费商用 (SIL Open Font License)
- **Inter**: 免费商用 (SIL Open Font License)
- **Bangers**: Google Fonts 免费
- 如需其他漫画字体，注意检查授权

### 移动端适配
- Bento Grid 在移动端需改为单列布局
- 3D Tilt 效果在触屏设备上需禁用或改为点击触发
- 自定义光标在移动端无效，需检测设备类型

### 浏览器兼容性
- 目标：Chrome 90+, Firefox 88+, Safari 14+, Edge 90+
- CSS backdrop-filter (毛玻璃) 在部分浏览器需前缀
- GSAP ScrollTrigger 需要 Intersection Observer 支持

### 回滚策略
- 保留现有 `app/static/` 和 `app/templates/` 目录不删除
- 迁移期间可通过环境变量切换新/旧前端
- 建议在独立分支开发，合并前完成完整测试

### 性能考量
- 漫画封面图片建议使用 WebP 格式 + 缩略图
- 首页 Bento Grid 建议首屏 6-8 张卡片，其余懒加载
- GSAP 动画在低端设备上可能需要降级

### 国际化 (i18n)
- 当前项目为中文，如需多语言支持建议使用 vue-i18n
- 漫画标题来自源站，保持原样不翻译

