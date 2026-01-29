import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'
import '@fontsource/bangers'
import '@fontsource/bebas-neue'
import '@fontsource/inter'
import '@fontsource/space-grotesk'
import '@fortawesome/fontawesome-free/css/all.css'
import './styles/main.css'

const app = createApp(App)

app.use(createPinia())
app.use(router)

app.mount('#app')
