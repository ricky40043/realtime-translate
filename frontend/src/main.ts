import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import './style.css'
import App from './App.vue'

// 導入頁面組件
import Room from './views/Room.vue'
import Settings from './views/Settings.vue'

// 建立路由
const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/room' },
    { path: '/room/:roomId?', component: Room, name: 'room' },
    { path: '/settings', component: Settings, name: 'settings' }
  ]
})

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)
app.mount('#app')
