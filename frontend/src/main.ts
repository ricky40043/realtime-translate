import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import './style.css'
import App from './App.vue'

// 導入頁面組件
import Room from './views/Room.vue'
import Settings from './views/Settings.vue'
import HostBoard from './views/HostBoard.vue'
import UserView from './views/UserView.vue'
import Translator from './views/Translator.vue'
import Home from './views/Home.vue'

// 建立路由
const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: Home, name: 'home' },
    { path: '/translator', component: Translator, name: 'translator' },
    { path: '/room/:roomId?', component: Room, name: 'room' },
    { path: '/host/:roomId', component: HostBoard, name: 'host' },
    { path: '/user', component: UserView, name: 'user' },
    { path: '/settings', component: Settings, name: 'settings' }
  ]
})

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)
app.mount('#app')
