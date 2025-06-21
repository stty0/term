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
        <button 
          class="new-tab-btn" 
          @click="createNewTab"
          :disabled="tabs.length >= 5"
          :title="tabs.length >= 5 ? '최대 5개 세션까지 생성 가능합니다' : '새 세션 추가'"
        >
          +
        </button>
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
        <div class="context-menu-item" @click="pasteFromClipboardMenu">
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

const copySelection = () => {
  const tab = tabs.value.find(t => t.id === contextMenu.value.tabId)
  if (tab && tab.terminal) {
    const selection = tab.terminal.getSelection()
    if (selection) {
      // 간단한 fallback 방식으로 복사
      const textArea = document.createElement('textarea')
      textArea.value = selection
      textArea.style.position = 'fixed'
      textArea.style.left = '-9999px'
      document.body.appendChild(textArea)
      textArea.select()
      try {
        document.execCommand('copy')
        console.log('복사 완료:', selection.substring(0, 50) + '...')
      } catch (err) {
        console.error('복사 실패:', err)
      }
      document.body.removeChild(textArea)
    }
  }
  contextMenu.value.show = false
}

const pasteFromClipboardMenu = async () => {
  const tab = tabs.value.find(t => t.id === contextMenu.value.tabId)
  if (tab && tab.terminal && tab.websocket) {
    const terminalElement = terminalRefs.value[tab.id]
    if (terminalElement) {
      // 터미널에 포커스 주기
      terminalElement.focus()
      
      // 1차: navigator.clipboard API 시도
      try {
        const text = await navigator.clipboard.readText()
        if (text && tab.websocket.readyState === WebSocket.OPEN) {
          console.log('우클릭 붙여넣기 성공:', text.substring(0, 50) + '...')
          tab.websocket.send(JSON.stringify({
            type: 'command',
            data: text
          }))
          contextMenu.value.show = false
          return
        }
      } catch (err) {
        // Clipboard API 실패 시 계속 진행
      }
      
      // 2차: 키보드 이벤트 시뮬레이션으로 Ctrl+V 발생
      const keydownEvent = new KeyboardEvent('keydown', {
        key: 'v',
        code: 'KeyV',
        ctrlKey: true,
        bubbles: true,
        cancelable: true
      })
      
      const keyupEvent = new KeyboardEvent('keyup', {
        key: 'v',
        code: 'KeyV',
        ctrlKey: true,
        bubbles: true,
        cancelable: true
      })
      
      // 터미널 요소에 키 이벤트 발생
      terminalElement.dispatchEvent(keydownEvent)
      terminalElement.dispatchEvent(keyupEvent)
      
      console.log('키보드 이벤트 시뮬레이션 시도')
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
  // 최대 5개 세션 제한
  if (tabs.value.length >= 5) {
    console.warn('최대 5개 세션까지만 생성 가능합니다.')
    return
  }
  
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
      // 탭 전환 시 터미널 포커스 보장
      const terminalElement = terminalRefs.value[tabId]
      if (terminalElement && tab.terminal) {
        terminalElement.focus()
        tab.terminal.focus()
        console.log('탭 전환 시 포커스 설정:', tabId)
      }
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
  
  // ResizeObserver 정리
  if ((tab as any).resizeObserver) {
    (tab as any).resizeObserver.disconnect()
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
    scrollback: 1000,  // 스크롤백 버퍼 크기
    wordSeparator: ' ()[]{}",\':;',  // 단어 구분자 설정
    theme: {
      background: '#000000',
      foreground: '#ffffff',
      cursor: '#ffffff'
    },
    // 자동 줄바꿈 관련 설정
    convertEol: true,  // 줄바꿈 문자 변환
    disableStdin: false  // 표준 입력 활성화
  })

  const fitAddon = new FitAddon()
  terminal.loadAddon(fitAddon)
  terminal.open(terminalElement)
  
  // 터미널 크기 조정 및 줄바꿈 처리
  setTimeout(() => {
    fitAddon.fit()
    
    // 터미널 크기 정보 출력 (디버깅용)
    const dims = fitAddon.proposeDimensions()
    if (dims) {
      // 한 라인당 문자수를 4개 줄임
      const adjustedCols = Math.max(1, dims.cols - 4)
      console.log(`터미널 크기: ${adjustedCols}x${dims.rows} (원본: ${dims.cols}x${dims.rows})`)
      
      // 터미널 크기를 조정된 값으로 설정
      terminal.resize(adjustedCols, dims.rows)
      
      // 서버에 터미널 크기 전송 (PTY 크기 조정용)
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
          type: 'resize',
          cols: adjustedCols,
          rows: dims.rows
        }))
      }
    }
  }, 100)

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

  // 터미널이 포커스를 받을 수 있도록 설정
  terminalElement.setAttribute('tabindex', '0')
  
  // 중복 방지를 위한 변수들
  let lastPasteTime = 0
  let lastPasteText = ''
  let isPasting = false
  
  // 안전한 붙여넣기 함수
  const safePaste = (text: string, source: string) => {
    const currentTime = Date.now()
    
    // 중복 방지: 같은 텍스트를 200ms 이내에 붙여넣으려 하면 무시
    if (text === lastPasteText && (currentTime - lastPasteTime) < 200) {
      console.log(`중복 붙여넣기 방지됨 (${source})`)
      return
    }
    
    // 현재 붙여넣기 중이면 무시
    if (isPasting) {
      console.log(`붙여넣기 진행 중, 무시됨 (${source})`)
      return
    }
    
    if (text && ws.readyState === WebSocket.OPEN) {
      isPasting = true
      console.log(`붙여넣기 실행 (${source}):`, text.substring(0, 50) + '...')
      ws.send(JSON.stringify({
        type: 'command',
        data: text
      }))
      
      lastPasteTime = currentTime
      lastPasteText = text
      
      // 200ms 후 플래그 해제
      setTimeout(() => {
        isPasting = false
      }, 200)
    }
  }

  // 키보드 이벤트 처리: Ctrl+C, Ctrl+V, Ctrl+A 직접 처리
  terminal.attachCustomKeyEventHandler((event) => {
    // Ctrl+C: 선택된 텍스트가 있으면 복사, 없으면 break 신호
    if (event.ctrlKey && event.key === 'c') {
      if (terminal.hasSelection()) {
        // 선택된 텍스트가 있으면 복사 처리
        event.preventDefault()
        const selection = terminal.getSelection()
        if (selection) {
          // execCommand 방식으로 복사
          const textArea = document.createElement('textarea')
          textArea.value = selection
          textArea.style.position = 'fixed'
          textArea.style.left = '-9999px'
          document.body.appendChild(textArea)
          textArea.select()
          try {
            document.execCommand('copy')
            console.log('복사 완료 (Ctrl+C):', selection.substring(0, 50) + '...')
          } catch (err) {
            console.error('복사 실패:', err)
          }
          document.body.removeChild(textArea)
        }
        return false // 이벤트 중단 (SSH 서버로 전송하지 않음)
      }
      // 선택된 텍스트가 없으면 break 신호로 SSH 서버에 전송
      return true
    }
    
    // Ctrl+V: 붙여넣기 (직접 처리)
    if (event.ctrlKey && event.key === 'v') {
      event.preventDefault()
      
      // navigator.clipboard API 시도
      if (navigator.clipboard && navigator.clipboard.readText) {
        navigator.clipboard.readText().then(text => {
          safePaste(text, 'Ctrl+V clipboard')
        }).catch(err => {
          console.error('Ctrl+V 붙여넣기 실패:', err)
          // fallback: 임시 textarea 생성하여 붙여넣기 시도
          const tempTextarea = document.createElement('textarea')
          tempTextarea.style.position = 'fixed'
          tempTextarea.style.left = '-9999px'
          tempTextarea.style.opacity = '0'
          document.body.appendChild(tempTextarea)
          tempTextarea.focus()
          
          // execCommand paste 시도
          setTimeout(() => {
            if (document.execCommand('paste')) {
              const pastedText = tempTextarea.value
              safePaste(pastedText, 'Ctrl+V fallback')
            }
            document.body.removeChild(tempTextarea)
            terminalElement.focus()
          }, 10)
        })
      } else {
        // clipboard API가 없는 경우 fallback
        console.log('Clipboard API 없음, fallback 시도')
        const tempTextarea = document.createElement('textarea')
        tempTextarea.style.position = 'fixed'
        tempTextarea.style.left = '-9999px'
        tempTextarea.style.opacity = '0'
        document.body.appendChild(tempTextarea)
        tempTextarea.focus()
        
        setTimeout(() => {
          if (document.execCommand('paste')) {
            const pastedText = tempTextarea.value
            safePaste(pastedText, 'Ctrl+V no-API fallback')
          }
          document.body.removeChild(tempTextarea)
          terminalElement.focus()
        }, 10)
      }
      
      return false
    }
    
    // Ctrl+A: 모두 선택
    if (event.ctrlKey && event.key === 'a') {
      event.preventDefault()
      terminal.selectAll()
      return false
    }
    
    // 나머지는 xterm.js 기본 동작 허용
    return true
  })

  // paste 이벤트도 중복 방지 처리
  terminalElement.addEventListener('paste', (event) => {
    const text = (event.clipboardData || (window as any).clipboardData)?.getData('text')
    if (text) {
      event.preventDefault() // 기본 xterm 붙여넣기 방지
      safePaste(text, 'paste event')
    }
  })

  // 터미널 클릭 시 포커스 보장 (강화)
  const ensureTerminalFocus = () => {
    // 터미널 요소에 포커스
    terminalElement.focus()
    // xterm 터미널 자체에도 포커스
    terminal.focus()
    console.log('터미널 포커스 설정됨')
  }
  
  terminalElement.addEventListener('click', ensureTerminalFocus)
  terminalElement.addEventListener('mousedown', ensureTerminalFocus)
  
  // 터미널 컨테이너에도 클릭 이벤트 추가
  const terminalContainer = terminalElement.parentElement
  if (terminalContainer) {
    terminalContainer.addEventListener('click', (e) => {
      // 터미널 영역 클릭 시에만 포커스 설정
      if (e.target === terminalElement || terminalElement.contains(e.target as Node)) {
        ensureTerminalFocus()
      }
    })
  }

  // 윈도우 리사이즈 처리 (개선된 버전)
  const handleResize = () => {
    if (tab.fitAddon && tab.terminal) {
      setTimeout(() => {
        tab.fitAddon!.fit()
        
        // 리사이즈 후 터미널 크기를 서버에 전송
        const dims = tab.fitAddon!.proposeDimensions()
        if (dims && tab.websocket && tab.websocket.readyState === WebSocket.OPEN) {
          // 한 라인당 문자수를 4개 줄임
          const adjustedCols = Math.max(1, dims.cols - 4)
          
          // 터미널 크기를 조정된 값으로 설정
          if (tab.terminal) {
            tab.terminal.resize(adjustedCols, dims.rows)
          }
          
          tab.websocket.send(JSON.stringify({
            type: 'resize',
            cols: adjustedCols,
            rows: dims.rows
          }))
          console.log(`터미널 리사이즈: ${adjustedCols}x${dims.rows} (원본: ${dims.cols}x${dims.rows})`)
        }
      }, 100)
    }
  }
  
  window.addEventListener('resize', handleResize)
  
  // 터미널 컨테이너 크기 변경 감지 (ResizeObserver 사용)
  if (window.ResizeObserver) {
    const resizeObserver = new ResizeObserver(handleResize)
    resizeObserver.observe(terminalElement)
    
    // 탭이 닫힐 때 옵저버 정리를 위해 참조 저장
    ;(tab as any).resizeObserver = resizeObserver
  }
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

.new-tab-btn:hover:not(:disabled) {
  color: #fff;
  background: #404040;
}

.new-tab-btn:disabled {
  color: #666;
  cursor: not-allowed;
  opacity: 0.5;
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
  outline: none;
}

.terminal:focus {
  outline: none;
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
