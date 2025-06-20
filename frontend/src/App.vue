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
    <div v-else class="main-container">
      <!-- 탭 영역 -->
      <div class="tabs">
        <div
          v-for="(tab, index) in tabs"
          :key="tab.id"
          class="tab-container"
          :class="{ active: activeTabId === tab.id }"
        >
          <button
            class="tab"
            @click="switchTab(tab.id)"
          >
            Session {{ index + 1 }}
          </button>
          <button
            v-if="tabs.length > 1"
            class="tab-close-btn"
            @click="closeTab(tab.id)"
            title="세션 닫기"
          >
            ×
          </button>
        </div>
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
          @contextmenu="handleContextMenu($event, tab.id)"
        ></div>
      </div>
      
      <!-- 컨텍스트 메뉴 -->
      <div
        v-if="contextMenu.show"
        class="context-menu"
        :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }"
        @click.stop
      >
        <div class="context-menu-item" @click="copySelection">
          복사 (Ctrl+C)
        </div>
        <div class="context-menu-item" @click="pasteFromClipboard">
          붙여넣기 (Ctrl+V)
        </div>
        <div class="context-menu-separator"></div>
        <div class="context-menu-item" @click="selectAll">
          모두 선택 (Ctrl+A)
        </div>
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

// 컨텍스트 메뉴 관련 변수
const contextMenu = ref({
  show: false,
  x: 0,
  y: 0,
  tabId: ''
})

const setTerminalRef = (tabId: string, el: any) => {
  if (el && el instanceof HTMLElement) {
    terminalRefs.value[tabId] = el
  }
}

// 컨텍스트 메뉴 관련 함수들
const handleContextMenu = (event: MouseEvent, tabId: string) => {
  event.preventDefault()
  contextMenu.value = {
    show: true,
    x: event.clientX,
    y: event.clientY,
    tabId: tabId
  }
}

const copySelection = async () => {
  const tab = tabs.value.find(t => t.id === contextMenu.value.tabId)
  if (tab && tab.terminal) {
    const selection = tab.terminal.getSelection()
    if (selection) {
      try {
        await navigator.clipboard.writeText(selection)
      } catch (err) {
        console.error('클립보드 복사 실패:', err)
      }
    }
  }
  contextMenu.value.show = false
}

const pasteFromClipboard = async () => {
  const tab = tabs.value.find(t => t.id === contextMenu.value.tabId)
  if (tab && tab.terminal && tab.websocket) {
    try {
      const text = await navigator.clipboard.readText()
      if (text && tab.websocket.readyState === WebSocket.OPEN) {
        // 컨텍스트 메뉴를 통한 붙여넣기는 직접 WebSocket으로 전송
        // onData 이벤트를 거치지 않으므로 중복 문제가 없음
        tab.websocket.send(JSON.stringify({
          type: 'command',
          data: text
        }))
      }
    } catch (err) {
      console.error('클립보드 붙여넣기 실패:', err)
    }
  }
  contextMenu.value.show = false
}

const selectAll = () => {
  const tab = tabs.value.find(t => t.id === contextMenu.value.tabId)
  if (tab && tab.terminal) {
    tab.terminal.selectAll()
  }
  contextMenu.value.show = false
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

const closeTab = (tabId: string) => {
  const tabIndex = tabs.value.findIndex(t => t.id === tabId)
  if (tabIndex === -1) return
  
  const tab = tabs.value[tabIndex]
  
  // WebSocket 연결 정상 종료
  if (tab.websocket) {
    if (tab.websocket.readyState === WebSocket.OPEN) {
      // 서버에 연결 종료 신호 전송
      tab.websocket.send(JSON.stringify({
        type: 'disconnect'
      }))
    }
    tab.websocket.close()
  }
  
  // 터미널 정리
  if (tab.terminal) {
    tab.terminal.dispose()
  }
  
  // terminalRefs에서 제거
  delete terminalRefs.value[tabId]
  
  // tabs 배열에서 제거
  tabs.value.splice(tabIndex, 1)
  
  // 활성 탭이 닫힌 경우 다른 탭으로 전환
  if (activeTabId.value === tabId && tabs.value.length > 0) {
    // 닫힌 탭의 이전 탭으로 전환, 없으면 첫 번째 탭으로
    const newActiveIndex = Math.max(0, tabIndex - 1)
    activeTabId.value = tabs.value[newActiveIndex].id
    
    // 새로운 활성 탭의 크기 조정
    const newActiveTab = tabs.value[newActiveIndex]
    if (newActiveTab && newActiveTab.fitAddon) {
      setTimeout(() => {
        newActiveTab.fitAddon!.fit()
      }, 100)
    }
  }
  
  // 모든 탭이 닫힌 경우 연결 해제
  if (tabs.value.length === 0) {
    isConnected.value = false
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
    allowTransparency: false,
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

  // 키보드 단축키 처리 - 모든 키 이벤트를 가로채서 처리
  terminal.attachCustomKeyEventHandler((event) => {
    // Ctrl+C: 복사
    if (event.ctrlKey && event.key === 'c' && terminal.hasSelection()) {
      event.preventDefault()
      const selection = terminal.getSelection()
      if (selection) {
        navigator.clipboard.writeText(selection).catch(err => {
          console.error('클립보드 복사 실패:', err)
        })
      }
      return false
    }
    
    // Ctrl+V: 붙여넣기 - 완전히 커스텀 처리
    if (event.ctrlKey && event.key === 'v') {
      event.preventDefault()
      event.stopPropagation()
      
      navigator.clipboard.readText().then(text => {
        if (text && ws.readyState === WebSocket.OPEN) {
          // 직접 WebSocket으로 전송 (onData 이벤트를 거치지 않음)
          ws.send(JSON.stringify({
            type: 'command',
            data: text
          }))
        }
      }).catch(err => {
        console.error('클립보드 붙여넣기 실패:', err)
      })
      return false
    }
    
    // Ctrl+A: 모두 선택
    if (event.ctrlKey && event.key === 'a') {
      event.preventDefault()
      terminal.selectAll()
      return false
    }
    
    return true
  })

  // 모든 붙여넣기 관련 이벤트 차단
  terminalElement.addEventListener('paste', (event) => {
    event.preventDefault()
    event.stopPropagation()
    event.stopImmediatePropagation()
  }, true)

  // keydown 이벤트에서도 Ctrl+V 차단
  terminalElement.addEventListener('keydown', (event) => {
    if (event.ctrlKey && event.key === 'v') {
      event.preventDefault()
      event.stopPropagation()
      event.stopImmediatePropagation()
    }
  }, true)

  // input 이벤트에서도 붙여넣기 차단
  terminalElement.addEventListener('input', (event: Event) => {
    const inputEvent = event as InputEvent
    if (inputEvent.inputType === 'insertFromPaste') {
      event.preventDefault()
      event.stopPropagation()
      event.stopImmediatePropagation()
    }
  }, true)

  // 윈도우 리사이즈 처리
  window.addEventListener('resize', () => {
    fitAddon.fit()
  })
}

const connect = async () => {
  isConnecting.value = true
  errorMessage.value = ''

  try {
    // 연결 상태를 먼저 true로 설정하여 터미널 영역이 렌더링되도록 함
    isConnected.value = true
    
    // DOM 렌더링을 기다린 후 첫 번째 탭 생성
    await nextTick()
    await createNewTab()
  } catch (error) {
    errorMessage.value = '연결에 실패했습니다.'
    console.error('연결 오류:', error)
    isConnected.value = false
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
  
  // 컨텍스트 메뉴 닫기 이벤트 리스너
  document.addEventListener('click', () => {
    contextMenu.value.show = false
  })
  
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      contextMenu.value.show = false
    }
  })
})
</script>

<style scoped>
/* 기본 스타일 */
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

#app {
  font-family: Avenir, Helvetica, Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  height: 100vh;
  width: 100vw;
  background-color: #f0f0f0;
}

.login-form {
  max-width: 400px;
  margin: 100px auto;
  padding: 2rem;
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
}

.login-form h1 {
  text-align: center;
  margin-bottom: 2rem;
  color: #333;
}

.form-group {
  margin-bottom: 1rem;
}

.form-group label {
  display: block;
  margin-bottom: 0.5rem;
  font-weight: bold;
  color: #555;
}

.form-group input {
  width: 100%;
  padding: 0.75rem;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 1rem;
  box-sizing: border-box;
}

.form-group input:focus {
  outline: none;
  border-color: #007acc;
  box-shadow: 0 0 0 2px rgba(0, 122, 204, 0.2);
}

.connect-btn {
  width: 100%;
  padding: 0.75rem;
  background: #007acc;
  color: white;
  border: none;
  border-radius: 4px;
  font-size: 1rem;
  cursor: pointer;
  transition: background-color 0.2s;
}

.connect-btn:hover:not(:disabled) {
  background: #005a9e;
}

.connect-btn:disabled {
  background: #ccc;
  cursor: not-allowed;
}

.error-message {
  margin-top: 1rem;
  padding: 0.75rem;
  background: #ffe6e6;
  color: #d00;
  border: 1px solid #ffcccc;
  border-radius: 4px;
  text-align: center;
}

/* 터미널 관련 스타일 */
.main-container {
  display: flex;
  flex-direction: column;
  height: 100vh;
  width: 100vw;
  background-color: #2d2d2d;
}

.tabs {
  display: flex;
  background: #2d2d2d;
  border-bottom: 1px solid #444;
  overflow-x: auto;
  flex-shrink: 0;
}

.tab-container {
  display: flex;
  align-items: center;
  background: #3c3c3c;
  border-right: 1px solid #555;
  min-width: fit-content;
}

.tab-container.active {
  background: #1e1e1e;
}

.tab {
  padding: 8px 16px;
  background: none;
  border: none;
  color: #ccc;
  font-size: 13px;
  cursor: pointer;
  white-space: nowrap;
  transition: color 0.2s;
}

.tab:hover {
  color: #fff;
}

.tab-container.active .tab {
  color: #fff;
}

.tab-close-btn {
  padding: 4px 8px;
  background: none;
  border: none;
  color: #999;
  font-size: 16px;
  cursor: pointer;
  line-height: 1;
  transition: color 0.2s;
}

.tab-close-btn:hover {
  color: #ff6b6b;
}

.new-tab-btn {
  padding: 8px 12px;
  background: none;
  border: none;
  color: #ccc;
  font-size: 16px;
  cursor: pointer;
  transition: color 0.2s;
}

.new-tab-btn:hover {
  color: #fff;
  background: #404040;
}

.terminal-container {
  flex: 1;
  background: #000000;
  overflow: hidden;
  position: relative;
}

.terminal {
  width: 100%;
  height: 100%;
  padding: 10px;
  box-sizing: border-box;
}

.context-menu {
  position: fixed;
  background: #2d2d2d;
  border: 1px solid #555;
  border-radius: 4px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.3);
  z-index: 1000;
  min-width: 150px;
}

.context-menu-item {
  padding: 8px 12px;
  color: #ccc;
  cursor: pointer;
  font-size: 12px;
  transition: background-color 0.2s;
}

.context-menu-item:hover {
  background: #404040;
  color: #fff;
}

.context-menu-separator {
  height: 1px;
  background: #555;
  margin: 4px 0;
}
</style>
