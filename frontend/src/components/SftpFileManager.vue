<template>
  <div class="sftp-container">
    <div class="sftp-header">
      <h3>파일 관리</h3>
      <div class="connection-status" :class="{ connected: isConnected }">
        {{ isConnected ? 'Connected' : 'Disconnected' }}
      </div>
    </div>
    
    <div class="sftp-content">
      <!-- 파일 탐색기 영역 (drag & drop 지원) -->
      <div 
        class="file-panel remote-panel full-width"
        :class="{ 'drag-over': isDragOver }"
        @drop="handleFileDrop"
        @dragover.prevent="handleDragOver"
        @dragenter.prevent="handleDragEnter"
        @dragleave.prevent="handleDragLeave"
      >
        <!-- 숨겨진 파일 입력 -->
        <input 
          ref="fileInput" 
          type="file" 
          @change="handleFileSelect" 
          style="display: none"
          multiple
        >
        <div class="panel-header">
          <div class="header-left">
            <h4>Remote Files - {{ currentPath }}</h4>
            <div class="upload-hint" v-if="isConnected">
              <small>📤 Drag & drop files here to upload to current directory</small>
            </div>
          </div>
          <div class="header-right">
            <button @click="selectFiles" :disabled="!isConnected" class="action-btn" title="Browse files">
              📁 Browse
            </button>
            <button @click="refreshRemoteFiles" :disabled="!isConnected" class="refresh-btn">↻</button>
          </div>
        </div>
        
        <!-- 드래그 오버레이 -->
        <div v-if="isDragOver" class="drag-overlay">
          <div class="drag-message">
            <div class="drag-icon">📤</div>
            <div class="drag-text">
              <p><strong>Drop files to upload</strong></p>
              <p>Files will be uploaded to: {{ currentPath }}</p>
            </div>
          </div>
        </div>
        
        <div class="file-list-container" v-if="isConnected">
          <div class="file-list">
            <!-- Parent directory -->
            <div v-if="currentPath !== '/'" class="file-item" @dblclick="navigateToParent">
              <span class="file-icon">📁</span>
              <span class="file-name">..</span>
              <span class="file-type">DIR</span>
              <span class="file-actions"></span>
            </div>
            
            <!-- Files and directories -->
            <div 
              v-for="file in remoteFiles" 
              :key="file.name"
              class="file-item"
              :class="{ selected: selectedFile === file.name }"
              @click="selectFile(file)"
              @dblclick="handleItemDoubleClick(file)"
              @contextmenu.prevent="showContextMenu($event, file)"
            >
              <span class="file-icon">{{ file.type === 'directory' ? '📁' : getFileIcon(file.name) }}</span>
              <span class="file-name">{{ file.name }}</span>
              <span class="file-size">{{ file.type === 'file' ? formatFileSize(file.size) : '' }}</span>
              <div class="file-actions">
                <button 
                  v-if="file.type === 'file'" 
                  @click.stop="downloadFile(file)"
                  class="action-btn-small"
                  title="Download"
                >
                  ⬇
                </button>
                <button 
                  @click.stop="deleteFile(file)"
                  class="action-btn-small danger"
                  title="Delete"
                >
                  🗑
                </button>
              </div>
            </div>
          </div>
          
          <div class="file-panel-footer">
            <button @click="createFolder" :disabled="!isConnected" class="action-btn">
              New Folder
            </button>
            <button @click="refreshRemoteFiles" :disabled="!isConnected" class="action-btn">
              Refresh
            </button>
            <div class="footer-spacer"></div>
            <div v-if="uploadQueue.length > 0" class="upload-summary">
              <span>{{ uploadQueue.length }} files queued</span>
              <button 
                @click="startUpload" 
                :disabled="!isConnected || isUploading"
                class="action-btn primary"
              >
                {{ isUploading ? 'Uploading...' : 'Upload All' }}
              </button>
            </div>
          </div>
        </div>
        
        <div v-else class="connection-required">
          <p>SSH connection required to browse remote files</p>
        </div>
      </div>
    </div>
    
    <!-- 업로드 큐 표시 (축약된 형태) -->
    <div v-if="uploadQueue.length > 0" class="upload-queue-compact">
      <div class="queue-header-compact">
        <div class="queue-info">
          <span class="queue-count">{{ uploadQueue.length }} files in queue</span>
          <span class="queue-status">
            {{ uploadQueue.filter(i => i.completed).length }} completed, 
            {{ uploadQueue.filter(i => i.error).length }} failed
          </span>
        </div>
        <div class="queue-actions-compact">
          <button 
            @click="startUpload" 
            :disabled="!isConnected || isUploading"
            class="action-btn primary"
            v-if="uploadQueue.some(i => !i.completed && !i.error)"
          >
            {{ isUploading ? 'Uploading...' : 'Upload All' }}
          </button>
          <button @click="clearQueue" class="action-btn secondary">
            Clear
          </button>
        </div>
      </div>
      
      <!-- 진행 중인 업로드만 표시 -->
      <div v-if="uploadQueue.some(i => i.uploading)" class="active-uploads">
        <div 
          v-for="(item, index) in uploadQueue.filter(i => i.uploading)" 
          :key="index"
          class="upload-item-compact"
        >
          <span class="upload-filename">{{ item.file.name }}</span>
          <div class="upload-progress">
            <div class="progress-bar-compact">
              <div class="progress-fill" :style="{ width: item.progress + '%' }"></div>
            </div>
            <span class="progress-text">{{ item.progress }}%</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 전송 상태 표시 -->
    <div v-if="globalTransferStatus.active" class="transfer-status">
      <div class="transfer-info">
        <span>{{ globalTransferStatus.type }}: {{ globalTransferStatus.filename }}</span>
        <span>{{ globalTransferStatus.progress }}%</span>
      </div>
      <div class="progress-bar">
        <div class="progress-fill" :style="{ width: globalTransferStatus.progress + '%' }"></div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, computed } from 'vue'
import axios from 'axios'

interface UploadQueueItem {
  file: File
  uploading: boolean
  completed: boolean
  error: boolean
  progress: number
}

interface FileInfo {
  name: string
  type: 'file' | 'directory'
  size: number
  modified: number
  permissions?: string
}

interface TransferStatus {
  active: boolean
  type: 'Upload' | 'Download'
  filename: string
  progress: number
}

// Props
const props = defineProps<{
  sessionId: string
  connected: boolean
}>()

// Reactive data
const isConnected = ref(false)
const fileInput = ref<HTMLInputElement>()
const isDragOver = ref(false)
const uploadQueue = ref<UploadQueueItem[]>([])
const isUploading = ref(false)
const currentPath = ref('/')
const remoteFiles = ref<FileInfo[]>([])
const selectedFile = ref('')

const globalTransferStatus = ref<TransferStatus>({
  active: false,
  type: 'Upload',
  filename: '',
  progress: 0
})

// API base URL  
const API_BASE = `http://${window.location.hostname}:8000`

// VueFinder adapter configuration (simplified version)
const adapterConfig = computed(() => ({
  name: 'sftp',
  url: `${API_BASE}/api/sftp/${props.sessionId}/remote/files`,
  method: 'get'
}))

// Watch for connection changes
watch(() => props.connected, (newVal) => {
  isConnected.value = newVal
  if (newVal) {
    // Reset to root path when connecting
    currentPath.value = '/'
    refreshRemoteFiles()
  }
})

// File selection and upload functions
const selectFiles = () => {
  fileInput.value?.click()
}

const handleFileSelect = async (event: Event) => {
  const target = event.target as HTMLInputElement
  const files = target.files
  if (!files) return
  
  addFilesToQueue(Array.from(files))
  // Reset input to allow selecting same files again
  target.value = ''
}

const addFilesToQueue = (files: File[]) => {
  const newItems: UploadQueueItem[] = files.map(file => ({
    file,
    uploading: false,
    completed: false,
    error: false,
    progress: 0
  }))
  
  uploadQueue.value.push(...newItems)
}

// Drag and drop handlers
const handleDragEnter = (event: DragEvent) => {
  event.preventDefault()
  isDragOver.value = true
}

const handleDragOver = (event: DragEvent) => {
  event.preventDefault()
  isDragOver.value = true
}

const handleDragLeave = (event: DragEvent) => {
  event.preventDefault()
  // Only set to false if leaving the drop zone entirely
  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect()
  if (
    event.clientX < rect.left ||
    event.clientX > rect.right ||
    event.clientY < rect.top ||
    event.clientY > rect.bottom
  ) {
    isDragOver.value = false
  }
}

const handleFileDrop = (event: DragEvent) => {
  event.preventDefault()
  isDragOver.value = false
  
  const files = event.dataTransfer?.files
  if (files) {
    addFilesToQueue(Array.from(files))
  }
}

// Queue management
const clearQueue = () => {
  uploadQueue.value = uploadQueue.value.filter(item => item.uploading)
}

const removeFromQueue = (index: number) => {
  if (!uploadQueue.value[index].uploading) {
    uploadQueue.value.splice(index, 1)
  }
}

// Upload functions
const startUpload = async () => {
  if (!isConnected.value || isUploading.value) return
  
  isUploading.value = true
  
  for (const item of uploadQueue.value) {
    if (!item.completed && !item.error) {
      await uploadSingleFile(item)
    }
  }
  
  isUploading.value = false
  
  // Refresh remote files after upload
  refreshRemoteFiles()
}

const uploadSingleFile = async (item: UploadQueueItem) => {
  item.uploading = true
  item.progress = 0
  
  const formData = new FormData()
  formData.append('file', item.file)
  formData.append('remote_path', currentPath.value)
  
  globalTransferStatus.value = {
    active: true,
    type: 'Upload',
    filename: item.file.name,
    progress: 0
  }
  
  try {
    await axios.post(`${API_BASE}/api/sftp/${props.sessionId}/upload`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      },
      onUploadProgress: (progressEvent: any) => {
        if (progressEvent.total) {
          const progress = Math.round((progressEvent.loaded * 100) / progressEvent.total)
          item.progress = progress
          globalTransferStatus.value.progress = progress
        }
      }
    })
    
    item.completed = true
    item.uploading = false
  } catch (error) {
    console.error('Upload failed:', error)
    item.error = true
    item.uploading = false
  } finally {
    globalTransferStatus.value.active = false
  }
}

// Remote file operations
const refreshRemoteFiles = async () => {
  if (!isConnected.value) return
  
  try {
    const response = await axios.get(`${API_BASE}/api/sftp/${props.sessionId}/remote/files`, {
      params: { path: currentPath.value }
    })
    remoteFiles.value = response.data.files
    currentPath.value = response.data.path || currentPath.value
  } catch (error: any) {
    console.error('Failed to load remote files:', error)
    // 연결 후 잠시 기다린 후 재시도
    if (error.response?.status === 404) {
      setTimeout(() => {
        refreshRemoteFiles()
      }, 1000)
    }
  }
}

// File list navigation functions
const navigateToParent = () => {
  const parentPath = currentPath.value.split('/').slice(0, -1).join('/') || '/'
  currentPath.value = parentPath
  refreshRemoteFiles()
}

const selectFile = (file: FileInfo) => {
  selectedFile.value = file.name
}

const handleItemDoubleClick = (file: FileInfo) => {
  if (file.type === 'directory') {
    currentPath.value = `${currentPath.value}/${file.name}`.replace('//', '/')
    refreshRemoteFiles()
  }
}

const showContextMenu = (event: MouseEvent, file: FileInfo) => {
  // Context menu functionality can be implemented later
  console.log('Context menu for:', file.name)
}

const getFileIcon = (filename: string) => {
  const ext = filename.split('.').pop()?.toLowerCase()
  switch (ext) {
    case 'txt':
    case 'md':
      return '📄'
    case 'jpg':
    case 'jpeg':
    case 'png':
    case 'gif':
      return '🖼️'
    case 'zip':
    case 'tar':
    case 'gz':
      return '📦'
    case 'js':
    case 'ts':
      return '📜'
    case 'html':
    case 'css':
      return '🌐'
    default:
      return '📄'
  }
}

const downloadFile = async (file: FileInfo) => {
  const filePath = `${currentPath.value}/${file.name}`.replace('//', '/')
  
  globalTransferStatus.value = {
    active: true,
    type: 'Download',
    filename: file.name,
    progress: 0
  }
  
  try {
    const response = await axios.get(
      `${API_BASE}/api/sftp/${props.sessionId}/download`,
      {
        params: { remote_path: filePath },
        responseType: 'blob',
        onDownloadProgress: (progressEvent: any) => {
          if (progressEvent.total) {
            globalTransferStatus.value.progress = Math.round(
              (progressEvent.loaded * 100) / progressEvent.total
            )
          }
        }
      }
    )
    
    // Download file to user's computer
    const url = window.URL.createObjectURL(new Blob([response.data]))
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', file.name)
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)
    
  } catch (error) {
    console.error('Download failed:', error)
    alert('Download failed: ' + error)
  } finally {
    globalTransferStatus.value.active = false
  }
}

const deleteFile = async (file: FileInfo) => {
  const confirmed = confirm(`Are you sure you want to delete ${file.name}?`)
  if (!confirmed) return
  
  const filePath = `${currentPath.value}/${file.name}`.replace('//', '/')
  
  try {
    await axios.delete(`${API_BASE}/api/sftp/${props.sessionId}/delete`, {
      params: { 
        path: filePath,
        is_directory: file.type === 'directory'
      }
    })
    
    // Refresh file list after deletion
    await refreshRemoteFiles()
    selectedFile.value = ''
  } catch (error) {
    console.error('Delete failed:', error)
    alert('Delete failed: ' + error)
  }
}

const createFolder = async () => {
  const folderName = prompt('Enter folder name:')
  if (!folderName) return
  
  const newFolderPath = `${currentPath.value}/${folderName}`.replace('//', '/')
  
  try {
    await axios.post(`${API_BASE}/api/sftp/${props.sessionId}/mkdir`, null, {
      params: { path: newFolderPath }
    })
    
    // Refresh file list after creation
    await refreshRemoteFiles()
  } catch (error) {
    console.error('Create folder failed:', error)
    alert('Create folder failed: ' + error)
  }
}

const onItemSelect = (item: any) => {
  console.log('Item selected:', item)
}

const onItemDoubleClick = (item: any) => {
  console.log('Item double clicked:', item) 
}

const onDirChange = (path: string) => {
  currentPath.value = path
}

const onFileDownload = async (item: any) => {
  const filePath = item.path
  
  globalTransferStatus.value = {
    active: true,
    type: 'Download',
    filename: item.name,
    progress: 0
  }
  
  try {
    const response = await axios.get(
      `${API_BASE}/api/sftp/${props.sessionId}/download`,
      {
        params: { remote_path: filePath },
        responseType: 'blob',
        onDownloadProgress: (progressEvent: any) => {
          if (progressEvent.total) {
            globalTransferStatus.value.progress = Math.round(
              (progressEvent.loaded * 100) / progressEvent.total
            )
          }
        }
      }
    )
    
    // Download file to user's computer
    const url = window.URL.createObjectURL(new Blob([response.data]))
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', item.name)
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)
    
  } catch (error) {
    console.error('Download failed:', error)
    alert('Download failed: ' + error)
  } finally {
    globalTransferStatus.value.active = false
  }
}

const onFileDelete = async (item: any) => {
  const confirmed = confirm(`Are you sure you want to delete ${item.name}?`)
  if (!confirmed) return
  
  try {
    await axios.delete(`${API_BASE}/api/sftp/${props.sessionId}/delete`, {
      params: { 
        path: item.path,
        is_directory: item.type === 'directory'
      }
    })
    
    refreshRemoteFiles()
  } catch (error) {
    console.error('Delete failed:', error)
    alert('Delete failed: ' + error)
  }
}

const onFolderCreate = async (path: string, name: string) => {
  const newDirPath = `${path}/${name}`.replace('//', '/')
  
  try {
    await axios.post(`${API_BASE}/api/sftp/${props.sessionId}/mkdir`, null, {
      params: { path: newDirPath }
    })
    
    refreshRemoteFiles()
  } catch (error) {
    console.error('Create directory failed:', error)
    alert('Create directory failed: ' + error)
  }
}

// Utility functions
const formatFileSize = (bytes: number) => {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

// Initialize
onMounted(() => {
  if (props.connected) {
    isConnected.value = true
    refreshRemoteFiles()
  }
})
</script>

<style scoped>
.sftp-container {
  background: #f5f5f5;
  border: 1px solid #ddd;
  border-radius: 4px;
  overflow: hidden;
}

.sftp-header {
  background: #333;
  color: white;
  padding: 10px 15px;
  display: flex;
  justify-content: between;
  align-items: center;
}

.sftp-header h3 {
  margin: 0;
  font-size: 16px;
}

.connection-status {
  font-size: 12px;
  padding: 4px 8px;
  border-radius: 4px;
  background: #666;
}

.connection-status.connected {
  background: #4CAF50;
}

.sftp-content {
  display: flex;
  height: 400px;
}

.file-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  border-right: 1px solid #ddd;
}

.file-panel:last-child {
  border-right: none;
}

.panel-header {
  background: #e9e9e9;
  padding: 10px;
  border-bottom: 1px solid #ddd;
}

.panel-header h4 {
  margin: 0 0 10px 0;
  font-size: 14px;
  color: #333;
  font-weight: 600;
}

.path-bar {
  display: flex;
  gap: 5px;
}

.path-input {
  flex: 1;
  padding: 5px;
  border: 1px solid #ccc;
  border-radius: 3px;
  font-size: 12px;
}

.refresh-btn {
  padding: 5px 10px;
  border: 1px solid #ccc;
  background: white;
  border-radius: 3px;
  cursor: pointer;
}

.refresh-btn:hover {
  background: #f0f0f0;
}

.file-list {
  flex: 1;
  overflow-y: auto;
  background: white;
}

.file-item {
  display: grid;
  grid-template-columns: 30px 1fr 80px 100px;
  align-items: center;
  padding: 5px 10px;
  border-bottom: 1px solid #eee;
  cursor: pointer;
  font-size: 12px;
  color: #333;
}

.file-item:hover {
  background: #f0f0f0;
}

.file-item.selected {
  background: #e3f2fd;
}

.file-icon {
  text-align: center;
}

.file-name {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.file-size, .file-date {
  text-align: right;
  color: #666;
  font-size: 11px;
}

.panel-footer {
  padding: 10px;
  background: #f9f9f9;
  border-top: 1px solid #ddd;
  display: flex;
  gap: 5px;
}

.action-btn {
  padding: 6px 12px;
  border: 1px solid #ccc;
  background: white;
  border-radius: 3px;
  cursor: pointer;
  font-size: 12px;
}

.action-btn:hover {
  background: #f0f0f0;
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.action-btn.danger {
  background: #ff6b6b;
  color: white;
  border-color: #ff5252;
}

.action-btn.danger:hover {
  background: #ff5252;
}

.transfer-status {
  padding: 10px;
  background: #fff3cd;
  border-top: 1px solid #ffeaa7;
}

.transfer-info {
  display: flex;
  justify-content: space-between;
  margin-bottom: 5px;
  font-size: 12px;
}

.progress-bar {
  height: 4px;
  background: #e0e0e0;
  border-radius: 2px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: #4CAF50;
  transition: width 0.3s ease;
}

/* Upload zone styles */
.upload-info {
  font-size: 12px;
  color: #666;
  margin-top: 5px;
}

.upload-zone {
  flex: 1;
  border: 2px dashed #ccc;
  border-radius: 8px;
  padding: 40px 20px;
  text-align: center;
  cursor: pointer;
  transition: all 0.3s ease;
  background: white;
  margin: 10px;
}

.upload-zone:hover {
  border-color: #007acc;
  background: #f8f9fa;
}

.upload-zone.drag-over {
  border-color: #007acc;
  background: #e3f2fd;
  border-style: solid;
}

.upload-icon {
  font-size: 48px;
  margin-bottom: 15px;
}

.upload-text p {
  margin: 5px 0;
  color: #666;
}

.upload-text p:first-child {
  color: #333;
  font-size: 16px;
}

/* Upload queue styles */
.upload-queue {
  margin: 10px;
  background: white;
  border-radius: 4px;
  border: 1px solid #ddd;
}

.queue-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 15px;
  background: #f8f9fa;
  border-bottom: 1px solid #ddd;
  font-size: 14px;
  font-weight: bold;
}

.clear-btn {
  padding: 4px 8px;
  background: #dc3545;
  color: white;
  border: none;
  border-radius: 3px;
  cursor: pointer;
  font-size: 12px;
}

.clear-btn:hover {
  background: #c82333;
}

.queue-items {
  max-height: 150px;
  overflow-y: auto;
}

.queue-item {
  display: grid;
  grid-template-columns: 1fr auto auto auto;
  gap: 10px;
  align-items: center;
  padding: 8px 15px;
  border-bottom: 1px solid #eee;
  font-size: 12px;
}

.queue-item:last-child {
  border-bottom: none;
}

.queue-item.uploading {
  background: #fff3cd;
}

.queue-item.completed {
  background: #d4edda;
}

.queue-item.error {
  background: #f8d7da;
}

.queue-item .file-name {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 200px;
}

.queue-item .progress {
  display: flex;
  align-items: center;
  gap: 5px;
  min-width: 80px;
}

.queue-item .progress .progress-bar {
  width: 50px;
  height: 4px;
  background: #e0e0e0;
  border-radius: 2px;
  overflow: hidden;
}

.queue-item .progress .progress-text {
  font-size: 10px;
  color: #666;
}

.queue-item .status {
  font-size: 14px;
  font-weight: bold;
}

.queue-item .status.completed {
  color: #28a745;
}

.queue-item .status.error {
  color: #dc3545;
}

.remove-btn {
  padding: 2px 6px;
  background: #6c757d;
  color: white;
  border: none;
  border-radius: 2px;
  cursor: pointer;
  font-size: 12px;
  line-height: 1;
}

.remove-btn:hover {
  background: #5a6268;
}

.queue-actions {
  padding: 10px 15px;
  background: #f8f9fa;
  border-top: 1px solid #ddd;
}

.action-btn.primary {
  background: #007acc;
  color: white;
  border-color: #007acc;
}

.action-btn.primary:hover:not(:disabled) {
  background: #005a9e;
  border-color: #005a9e;
}

/* Remote panel styles */
.current-path {
  flex: 1;
  padding: 5px;
  background: #f8f9fa;
  border: 1px solid #ddd;
  border-radius: 3px;
  font-size: 12px;
  font-family: monospace;
  color: #666;
}

.vuefinder-container {
  flex: 1;
  background: white;
  overflow: hidden;
}

.connection-required {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: white;
  color: #666;
  font-style: italic;
}

/* File list container and actions */
.file-list-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: white;
  overflow: hidden;
}

.file-actions {
  display: flex;
  gap: 2px;
  opacity: 0;
  transition: opacity 0.2s;
}

.file-item:hover .file-actions {
  opacity: 1;
}

.action-btn-small {
  padding: 2px 4px;
  border: 1px solid #ccc;
  background: white;
  border-radius: 2px;
  cursor: pointer;
  font-size: 10px;
  line-height: 1;
}

.action-btn-small:hover {
  background: #f0f0f0;
}

.action-btn-small.danger {
  background: #ff6b6b;
  color: white;
  border-color: #ff5252;
}

.action-btn-small.danger:hover {
  background: #ff5252;
}

.file-panel-footer {
  padding: 10px;
  background: #f9f9f9;
  border-top: 1px solid #ddd;
  display: flex;
  gap: 5px;
  align-items: center;
}

/* New styles for full-width drag & drop layout */
.file-panel.full-width {
  position: relative;
}

.file-panel.full-width.drag-over {
  background: rgba(0, 122, 204, 0.05);
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.header-left {
  flex: 1;
}

.header-right {
  display: flex;
  gap: 5px;
  align-items: center;
}

.upload-hint {
  margin-top: 5px;
}

.upload-hint small {
  color: #007acc;
  font-weight: 500;
}

/* Drag overlay styles */
.drag-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 122, 204, 0.1);
  border: 3px dashed #007acc;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  backdrop-filter: blur(2px);
}

.drag-message {
  text-align: center;
  padding: 20px;
  background: white;
  border-radius: 12px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  border: 2px solid #007acc;
}

.drag-icon {
  font-size: 64px;
  margin-bottom: 15px;
  animation: bounce 1s infinite;
}

@keyframes bounce {
  0%, 20%, 50%, 80%, 100% {
    transform: translateY(0);
  }
  40% {
    transform: translateY(-10px);
  }
  60% {
    transform: translateY(-5px);
  }
}

.drag-text p {
  margin: 5px 0;
  color: #333;
}

.drag-text p:first-child {
  font-size: 18px;
  font-weight: bold;
  color: #007acc;
}

.drag-text p:last-child {
  font-size: 14px;
  color: #666;
  font-family: monospace;
}

/* Footer enhancements */
.footer-spacer {
  flex: 1;
}

.upload-summary {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
  color: #666;
}

.upload-summary span {
  padding: 4px 8px;
  background: #e3f2fd;
  border-radius: 4px;
  color: #007acc;
  font-weight: 500;
}

/* Compact upload queue styles */
.upload-queue-compact {
  background: #f8f9fa;
  border-top: 1px solid #ddd;
  border-bottom: 1px solid #ddd;
}

.queue-header-compact {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 15px;
  background: #e9ecef;
}

.queue-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.queue-count {
  font-size: 13px;
  font-weight: 600;
  color: #333;
}

.queue-status {
  font-size: 11px;
  color: #666;
}

.queue-actions-compact {
  display: flex;
  gap: 5px;
}

.action-btn.secondary {
  background: #6c757d;
  color: white;
  border-color: #6c757d;
}

.action-btn.secondary:hover:not(:disabled) {
  background: #5a6268;
  border-color: #5a6268;
}

.active-uploads {
  padding: 5px 15px 10px 15px;
}

.upload-item-compact {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 0;
  font-size: 12px;
}

.upload-filename {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-right: 10px;
  color: #333;
}

.upload-progress {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 120px;
}

.progress-bar-compact {
  width: 80px;
  height: 6px;
  background: #e0e0e0;
  border-radius: 3px;
  overflow: hidden;
}

.progress-bar-compact .progress-fill {
  height: 100%;
  background: #007acc;
  transition: width 0.3s ease;
}

.upload-progress .progress-text {
  font-size: 10px;
  color: #666;
  min-width: 30px;
  text-align: right;
}
</style>
