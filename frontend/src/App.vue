<template>
  <div id="app">
    <!-- 로그인 폼 -->
    <div v-if="!isConnected" class="login-form">
      <h1>SSH Client</h1>
      <form @submit.prevent="connect">
        <div class="form-group">
          <label for="hostname">Hostname:</label>
          <input
            id="hostname"
            v-model="connectionForm.hostname"
            type="text"
            placeholder="192.168.10.100"
            required
          />
        </div>
        <div class="form-group">
          <label for="port">Port:</label>
          <input
            id="port"
            v-model="connectionForm.port"
            type="number"
            placeholder="22"
            required
          />
        </div>
        <div class="form-group">
          <label for="username">Username:</label>
          <input
            id="username"
            v-model="connectionForm.username"
            type="text"
            placeholder="jrpark"
            required
          />
        </div>
        <div class="form-group">
          <label for="password">Password:</label>
          <input
            id="password"
            v-model="connectionForm.password"
            type="password"
            required
          />
        </div>
        <button type="submit" class="connect-btn" :disabled="isConnecting">
          {{ isConnecting ? 'Connecting...' : 'Connect' }}
        </button>
        <div v-if="errorMessage" class="error-message">
          {{ errorMessage }}
        </div>
      </form>
    </div>

    <!-- 터미널 영역 -->
    <div v-else>
      <!-- 탭 영역 -->
      <div class="tabs">
        <button
          v-for="(tab, index) in tabs"
          :key="tab.id"
          class="tab"
          :class="{ active: activeTabId === tab.id }"
          @click="switchTab(tab.id)"
        >
          Session {{ index + 1 }}
        </button>
        <button class="new-tab-btn" @click="createNewTab">+</button>
      </div>

      <!-- 터미널 컨테이너 -->
      <div class="terminal-container">
        <div
          v-for="tab in tabs"
          :key="tab.id"
          :ref="el => setTerminalRef(tab.id, el)"
          class="terminal"
          :style="{ display: activeTabId === tab.id ? 'block' : 'none' }"
        ></div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
import { Terminal } from 'xterm'
import { FitAddon } from 'xterm-addon-fit'

interface ConnectionForm {
  hostname: string
  port: number
  username: string
  password: string
}

interface Tab {
  id: string
  terminal: Terminal | null
  websocket: WebSocket | null
  fitAddon: FitAddon | null
}

const isConnected = ref(false)
const isConnecting = ref(false)
const errorMessage = ref('')
const activeTabId = ref('')
const tabs = ref<Tab[]>([])
const terminalRefs = ref<{ [key: string]: HTMLElement }>({})

const connectionForm = ref<ConnectionForm>({
  hostname: '192.168.10.100',
  port: 22,
  username: 'jrpark',
  password: ''
})

const setTerminalRef = (tabId: string, el: HTMLElement | null) => {
  if (el) {
    terminalRefs.value[tabId] = el
  }
}

const createNewTab = async () => {
  const tabId = `tab-${Date.now()}`
  const newTab: Tab = {
    id: tabId,
    terminal: null,
    websocket: null,
    fitAddon: null
  }
  
  tabs.value.push(newTab)
  activeTabId.value = tabId
  
  await nextTick()
  await initializeTerminal(newTab)
}

const switchTab = (tabId: string) => {
  activeTabId.value = tabId
  const tab = tabs.value.find(t => t.id === tabId)
  if (tab && tab.fitAddon) {
    setTimeout(() => {
      tab.fitAddon!.fit()
    }, 100)
  }
}

const initializeTerminal = async (tab: Tab) => {
  const terminalElement = terminalRefs.value[tab.id]
  if (!terminalElement) return

  // xterm.js 터미널 생성
  const terminal = new Terminal({
    cursorBlink: true,
    fontSize: 14,
    fontFamily: 'Courier New, monospace',
    theme: {
      background: '#000000',
      foreground: '#ffffff',
      cursor: '#ffffff'
    }
  })

  const fitAddon = new FitAddon()
  terminal.loadAddon(fitAddon)
  terminal.open(terminalElement)
  fitAddon.fit()

  tab.terminal = terminal
  tab.fitAddon = fitAddon

  // WebSocket 연결 - 현재 호스트에 맞게 동적으로 설정
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = window.location.hostname
  const wsUrl = `${protocol}//${host}:8000/ws/${tab.id}`
  const ws = new WebSocket(wsUrl)
  tab.websocket = ws

  ws.onopen = () => {
    // SSH 연결 요청
    ws.send(JSON.stringify({
      type: 'connect',
      hostname: connectionForm.value.hostname,
      username: connectionForm.value.username,
      password: connectionForm.value.password,
      port: connectionForm.value.port
    }))
  }

  ws.onmessage = (event) => {
    const message = JSON.parse(event.data)
    
    if (message.type === 'connection_result') {
      if (!message.success) {
        terminal.write('\r\n\x1b[31mSSH 연결 실패\x1b[0m\r\n')
      }
    } else if (message.type === 'output') {
      terminal.write(message.data)
    }
  }

  ws.onerror = (error) => {
    console.error('WebSocket 오류:', error)
    terminal.write('\r\n\x1b[31mWebSocket 연결 오류\x1b[0m\r\n')
  }

  ws.onclose = () => {
    terminal.write('\r\n\x1b[33m연결이 종료되었습니다.\x1b[0m\r\n')
  }

  // 터미널 입력 처리
  terminal.onData((data) => {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: 'command',
        data: data
      }))
    }
  })

  // 윈도우 리사이즈 처리
  window.addEventListener('resize', () => {
    fitAddon.fit()
  })
}

const connect = async () => {
  isConnecting.value = true
  errorMessage.value = ''

  try {
    // 첫 번째 탭 생성
    await createNewTab()
    isConnected.value = true
  } catch (error) {
    errorMessage.value = '연결에 실패했습니다.'
    console.error('연결 오류:', error)
  } finally {
    isConnecting.value = false
  }
}

onMounted(() => {
  // CSS 로드 확인
  const link = document.createElement('link')
  link.rel = 'stylesheet'
  link.href = 'https://cdn.jsdelivr.net/npm/xterm@5.3.0/css/xterm.css'
  document.head.appendChild(link)
})
</script>
