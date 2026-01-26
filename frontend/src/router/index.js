import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
    history: createWebHistory(import.meta.env.BASE_URL),
    routes: [
        {
            path: '/',
            name: 'home',
            component: () => import('../views/HomeView.vue')
        },
        {
            path: '/manga/:id',
            name: 'manga',
            component: () => import('../views/MangaView.vue')
        },
        {
            path: '/read/:mangaId/:chapterId',
            name: 'reader',
            component: () => import('../views/ReaderView.vue')
        },
        {
            path: '/scraper',
            name: 'scraper',
            component: () => import('../views/ScraperView.vue')
        }
    ]
})

export default router
