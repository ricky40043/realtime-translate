import { computed, onBeforeUnmount, ref, shallowRef } from 'vue'

// 雙向翻譯機的多裝置同步：同一個房間代碼的裝置，畫面上的對話即時一致。
// 手機當麥克風、電腦只看；或兩邊都能講，對話依時間合併顯示。

export interface SyncPiece { transcript: string; translation: string; final: boolean }
export interface SyncEntry {
  key: string          // `${分頁代號}:${句子編號}`，不同裝置不會撞號
  t: number            // 句子開始的時間（伺服器時間，ms），排序用
  sourceLang: string
  targetLang: string
  ended: boolean
  pieces: SyncPiece[]
}
// 本機的句子（有數字 id）；key 由這裡加上
export type LocalEntry = Omit<SyncEntry, 'key'> & { id: number | string }

const ROOM_RE = /^[A-Za-z0-9_-]{4,64}$/
const ROOM_STORAGE_KEY = 'translatorRoom'
const FLUSH_MS = 100
const PING_MS = 25_000
const MAX_BACKOFF_MS = 10_000
// 去掉容易看錯的字（0/O、1/I/L）
const ROOM_ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'

function newRoomId(): string {
  const bytes = new Uint8Array(8)
  crypto.getRandomValues(bytes)
  return Array.from(bytes, b => ROOM_ALPHABET[b % ROOM_ALPHABET.length]).join('')
}

function readStoredRoom(): string {
  try { return localStorage.getItem(ROOM_STORAGE_KEY) || '' } catch { return '' }
}

function storeRoom(id: string) {
  try { localStorage.setItem(ROOM_STORAGE_KEY, id) } catch { /* 存不了也沒關係 */ }
}

function writeUrlRoom(id: string) {
  const url = new URL(location.href)
  url.searchParams.set('room', id)
  history.replaceState(history.state, '', url)
}

export function useTranslatorSync(options: {
  getToken: () => string | null
  refreshToken: () => Promise<boolean>
  getLocal: () => LocalEntry[]
  getLangs: () => { langA: string[]; langB: string[] }
  onRemoteLangs: (langA: string[], langB: string[]) => void
  onRemoteChange: () => void
}) {
  const cid = Math.random().toString(36).slice(2, 10)
  const urlRoom = new URLSearchParams(location.search).get('room') || ''
  const fromUrl = ROOM_RE.test(urlRoom)
  const stored = readStoredRoom()
  const roomId = ref(fromUrl ? urlRoom : ROOM_RE.test(stored) ? stored : newRoomId())
  // 掃 QR 進來的裝置（網址帶房間）→ true；自己開的新房間 → false
  const joinedViaLink = fromUrl
  const status = ref<'connecting' | 'online' | 'offline' | 'error'>('connecting')
  const peers = ref(1)
  const remoteEntries = shallowRef<SyncEntry[]>([])
  const shareUrl = computed(() => {
    const url = new URL(location.origin + '/translator')
    url.searchParams.set('room', roomId.value)
    return url.toString()
  })

  const remote = new Map<string, SyncEntry>()
  let sent = new Map<string, string>()   // key → 已送出的內容（JSON），只送有變的
  let ws: WebSocket | null = null
  let started = false
  let reconnectTimer: number | null = null
  let flushTimer: number | null = null
  let pingTimer: number | null = null
  let backoff = 1000
  let clockOffset = 0
  let synced = false                     // 收到快照後才開始送，避免把舊畫面蓋掉

  const keyOf = (id: number | string) => `${cid}:${id}`
  const now = () => Date.now() + clockOffset

  function publishRemote() {
    remoteEntries.value = [...remote.values()].sort((a, b) => a.t - b.t)
    options.onRemoteChange()
  }

  function send(message: object) {
    if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify(message))
  }

  function connect() {
    const token = options.getToken()
    if (!started || !token) return
    clearTimers()
    status.value = 'connecting'
    synced = false
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const socket = new WebSocket(
      `${proto}://${location.host}/ws/translator-sync/${roomId.value}?token=${encodeURIComponent(token)}&cid=${cid}`,
    )
    ws = socket
    socket.onmessage = event => {
      if (ws !== socket) return
      try { onMessage(JSON.parse(event.data)) } catch { /* 壞訊息直接略過 */ }
    }
    socket.onopen = () => {
      pingTimer = window.setInterval(() => send({ type: 'ping' }), PING_MS)
    }
    socket.onclose = async event => {
      if (ws !== socket) return
      ws = null
      synced = false
      if (pingTimer !== null) { window.clearInterval(pingTimer); pingTimer = null }
      if (!started) return
      if (event.code === 4400 || event.code === 4429) { status.value = 'error'; return }
      status.value = 'offline'
      // 登入憑證過期（7 天）：換一張再連
      if (event.code === 4001 && !(await options.refreshToken())) { status.value = 'error'; return }
      reconnectTimer = window.setTimeout(connect, backoff)
      backoff = Math.min(MAX_BACKOFF_MS, backoff * 2)
    }
    socket.onerror = () => { /* 交給 onclose 處理重連 */ }
  }

  function onMessage(message: any) {
    switch (message.type) {
      case 'snapshot': {
        backoff = 1000
        status.value = 'online'
        peers.value = message.peers ?? 1
        if (typeof message.now === 'number') clockOffset = message.now - Date.now()
        remote.clear()
        sent = new Map()
        for (const entry of message.entries as SyncEntry[]) {
          // 這個分頁自己以前送過的句子（斷線重連）：記起來，之後比對要不要更新或刪除
          if (entry.key.startsWith(`${cid}:`)) sent.set(entry.key, '')
          else remote.set(entry.key, entry)
        }
        publishRemote()
        synced = true
        if (message.langs) options.onRemoteLangs(message.langs.langA, message.langs.langB)
        else pushLangs()
        flush()
        break
      }
      case 'entries':
        for (const entry of message.upserts as SyncEntry[]) remote.set(entry.key, entry)
        for (const key of message.removed as string[]) remote.delete(key)
        publishRemote()
        break
      case 'langs':
        options.onRemoteLangs(message.langA, message.langB)
        break
      case 'reset':
        remote.clear()
        publishRemote()
        break
      case 'peers':
        peers.value = message.peers
        break
    }
  }

  // 把本機句子和上次送出的比對，只送有變的（講話中每秒更新很多次，不能每次都整包送）
  function flush() {
    flushTimer = null
    if (!synced) return
    const upserts: SyncEntry[] = []
    const seen = new Set<string>()
    for (const entry of options.getLocal()) {
      const key = keyOf(entry.id)
      seen.add(key)
      const payload: SyncEntry = {
        key, t: entry.t, sourceLang: entry.sourceLang, targetLang: entry.targetLang, ended: entry.ended,
        pieces: entry.pieces.map(p => ({ transcript: p.transcript, translation: p.translation, final: p.final })),
      }
      const json = JSON.stringify(payload)
      if (sent.get(key) !== json) {
        sent.set(key, json)
        upserts.push(payload)
      }
    }
    const removed = [...sent.keys()].filter(key => !seen.has(key))
    removed.forEach(key => sent.delete(key))
    if (upserts.length || removed.length) send({ type: 'entries', upserts, removed })
  }

  function schedulePush() {
    if (flushTimer === null) flushTimer = window.setTimeout(flush, FLUSH_MS)
  }

  function pushLangs() {
    if (!synced) return
    const { langA, langB } = options.getLangs()
    send({ type: 'langs', langA, langB })
  }

  function clearTimers() {
    if (reconnectTimer !== null) { window.clearTimeout(reconnectTimer); reconnectTimer = null }
    if (pingTimer !== null) { window.clearInterval(pingTimer); pingTimer = null }
  }

  function close() {
    const socket = ws
    ws = null
    synced = false
    clearTimers()
    socket?.close()
  }

  // 手機鎖屏回來、網路切換後連線多半已經死了：回到畫面就馬上重連，不用等退避時間
  function onVisible() {
    if (document.visibilityState === 'visible' && started && !ws) {
      backoff = 1000
      connect()
    }
  }

  function start() {
    if (started) return
    started = true
    storeRoom(roomId.value)
    writeUrlRoom(roomId.value)
    document.addEventListener('visibilitychange', onVisible)
    window.addEventListener('online', onVisible)
    connect()
  }

  function stop() {
    started = false
    close()
    if (flushTimer !== null) { window.clearTimeout(flushTimer); flushTimer = null }
    document.removeEventListener('visibilitychange', onVisible)
    window.removeEventListener('online', onVisible)
  }

  // 新對話：換一個新房間代碼（舊裝置不會再收到）
  function newRoom() {
    close()
    remote.clear()
    sent = new Map()
    publishRemote()
    roomId.value = newRoomId()
    storeRoom(roomId.value)
    writeUrlRoom(roomId.value)
    backoff = 1000
    connect()
  }

  onBeforeUnmount(stop)

  return {
    cid, roomId, status, peers, remoteEntries, shareUrl, joinedViaLink,
    now, start, stop, newRoom, schedulePush, pushLangs,
  }
}
