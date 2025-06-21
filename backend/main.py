from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import paramiko
import asyncio
import json
import threading
import queue
import time
import os
import stat
from typing import List, Dict, Optional
from pathlib import Path
import io

app = FastAPI()

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 개발 환경에서는 모든 origin 허용
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class SSHSession:
    def __init__(self):
        self.client = None
        self.channel = None
        self.connected = False
        self.output_queue = queue.Queue()
        self.terminal_width = 80  # 기본 터미널 너비
        self.terminal_height = 24  # 기본 터미널 높이
        
    def connect(self, hostname, username, password, port=22):
        try:
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.client.connect(hostname, port=port, username=username, password=password)
            
            # PTY 크기와 함께 쉘 호출 - 기본 터미널 타입으로 설정
            self.channel = self.client.invoke_shell(
                term='xterm',  # 기본 터미널 타입으로 변경 (색상 자동 적용 방지)
                width=self.terminal_width,
                height=self.terminal_height,
                width_pixels=0,
                height_pixels=0
            )
            self.channel.settimeout(0.1)
            self.connected = True
            
            print(f"SSH 연결 성공 - 터미널 크기: {self.terminal_width}x{self.terminal_height}")
            
            # 출력 읽기 스레드 시작
            self.output_thread = threading.Thread(target=self._read_output)
            self.output_thread.daemon = True
            self.output_thread.start()
            
            return True
        except Exception as e:
            print(f"SSH 연결 실패: {e}")
            return False
    
    def _read_output(self):
        while self.connected and self.channel:
            try:
                if self.channel.recv_ready():
                    data = self.channel.recv(1024).decode('utf-8', errors='ignore')
                    self.output_queue.put(data)
                time.sleep(0.01)
            except Exception as e:
                if self.connected:
                    print(f"출력 읽기 오류: {e}")
                break
    
    def send_command(self, command):
        if self.channel and self.connected:
            try:
                self.channel.send(command)
                return True
            except Exception as e:
                print(f"명령어 전송 실패: {e}")
                return False
        return False
    
    def resize_terminal(self, cols, rows):
        """터미널 크기 조정"""
        if self.channel and self.connected:
            try:
                # 터미널 크기 업데이트
                self.terminal_width = cols
                self.terminal_height = rows
                
                # PTY 크기 조정
                self.channel.resize_pty(width=cols, height=rows, width_pixels=0, height_pixels=0)
                print(f"터미널 크기 조정 완료: {cols}x{rows}")
                return True
            except Exception as e:
                print(f"터미널 크기 조정 실패: {e}")
                return False
        return False
    
    def get_output(self):
        output = ""
        while not self.output_queue.empty():
            try:
                output += self.output_queue.get_nowait()
            except queue.Empty:
                break
        return output
    
    def disconnect(self):
        self.connected = False
        if self.channel:
            self.channel.close()
        if self.client:
            self.client.close()

class SFTPSession:
    def __init__(self):
        self.client = None
        self.sftp = None
        self.connected = False
        self.home_dir = None
        
    def connect(self, hostname, username, password, port=22):
        try:
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.client.connect(hostname, port=port, username=username, password=password)
            
            self.sftp = self.client.open_sftp()
            self.connected = True
            
            # Get home directory - use pwd command to get actual home directory
            try:
                # Execute pwd command to get current directory
                stdin, stdout, stderr = self.client.exec_command('pwd')
                self.home_dir = stdout.read().decode().strip()
                print(f"Home directory set to: {self.home_dir}")
            except Exception as e:
                print(f"Failed to get home directory: {e}")
                self.home_dir = f'/home/{username}'
            
            return True
        except Exception as e:
            print(f"SFTP 연결 실패: {e}")
            return False
    
    def list_files(self, path='.'):
        if not self.connected or not self.sftp:
            return []
        
        try:
            # Prevent going above home directory
            full_path = self.sftp.normalize(path)
            if not full_path.startswith(self.home_dir):
                full_path = self.home_dir
            
            files = []
            file_list = self.sftp.listdir_attr(full_path)
            
            for file_attr in file_list:
                if file_attr.filename.startswith('.') and file_attr.filename != '..':
                    continue  # Skip hidden files except parent directory
                
                file_info = {
                    'name': file_attr.filename,
                    'type': 'directory' if stat.S_ISDIR(file_attr.st_mode) else 'file',
                    'size': file_attr.st_size if file_attr.st_size else 0,
                    'modified': file_attr.st_mtime if file_attr.st_mtime else 0,
                    'permissions': oct(file_attr.st_mode)[-3:] if file_attr.st_mode else '000'
                }
                files.append(file_info)
            
            return {'files': files, 'path': full_path}
        except Exception as e:
            print(f"파일 목록 조회 실패: {e}")
            return {'files': [], 'path': self.home_dir}
    
    def upload_file(self, local_file, remote_path):
        if not self.connected or not self.sftp:
            return False
        
        try:
            # Prevent going above home directory
            full_remote_path = self.sftp.normalize(remote_path)
            if not full_remote_path.startswith(self.home_dir):
                full_remote_path = self.home_dir
            
            # Create full file path
            remote_file_path = os.path.join(full_remote_path, local_file.filename)
            
            # Upload file
            file_content = local_file.file.read()
            with self.sftp.open(remote_file_path, 'wb') as remote_file:
                remote_file.write(file_content)
            
            return True
        except Exception as e:
            print(f"파일 업로드 실패: {e}")
            return False
    
    def download_file(self, remote_path):
        if not self.connected or not self.sftp:
            return None
        
        try:
            # Prevent going above home directory
            full_remote_path = self.sftp.normalize(remote_path)
            if not full_remote_path.startswith(self.home_dir):
                return None
            
            file_data = io.BytesIO()
            with self.sftp.open(full_remote_path, 'rb') as remote_file:
                file_data.write(remote_file.read())
            
            file_data.seek(0)
            return file_data
        except Exception as e:
            print(f"파일 다운로드 실패: {e}")
            return None
    
    def delete_file(self, remote_path, is_directory=False):
        if not self.connected or not self.sftp:
            return False
        
        try:
            # Prevent going above home directory
            full_remote_path = self.sftp.normalize(remote_path)
            if not full_remote_path.startswith(self.home_dir):
                return False
            
            if is_directory:
                self.sftp.rmdir(full_remote_path)
            else:
                self.sftp.remove(full_remote_path)
            
            return True
        except Exception as e:
            print(f"파일 삭제 실패: {e}")
            return False
    
    def create_directory(self, remote_path):
        if not self.connected or not self.sftp:
            return False
        
        try:
            # Prevent going above home directory
            full_remote_path = self.sftp.normalize(remote_path)
            if not full_remote_path.startswith(self.home_dir):
                return False
            
            self.sftp.mkdir(full_remote_path)
            return True
        except Exception as e:
            print(f"디렉토리 생성 실패: {e}")
            return False
    
    def disconnect(self):
        self.connected = False
        if self.sftp:
            self.sftp.close()
        if self.client:
            self.client.close()

# 세션 관리
sessions = {}
sftp_sessions = {}

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    
    # 새 SSH 세션 생성
    ssh_session = SSHSession()
    sessions[session_id] = ssh_session
    
    try:
        while True:
            # 클라이언트로부터 메시지 받기
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message["type"] == "connect":
                # SSH 연결
                success = ssh_session.connect(
                    hostname=message["hostname"],
                    username=message["username"],
                    password=message["password"],
                    port=message.get("port", 22)
                )
                
                await websocket.send_text(json.dumps({
                    "type": "connection_result",
                    "success": success
                }))
                
                if success:
                    # 연결 성공 시 출력 모니터링 시작
                    asyncio.create_task(monitor_output(websocket, ssh_session))
            
            elif message["type"] == "command":
                # 명령어 전송
                ssh_session.send_command(message["data"])
            
            elif message["type"] == "resize":
                # 터미널 크기 조정
                cols = message.get("cols", 80)
                rows = message.get("rows", 24)
                success = ssh_session.resize_terminal(cols, rows)
                
                await websocket.send_text(json.dumps({
                    "type": "resize_result",
                    "success": success,
                    "cols": cols,
                    "rows": rows
                }))
            
            elif message["type"] == "disconnect":
                # 연결 종료 요청
                print(f"클라이언트 요청으로 세션 종료: {session_id}")
                ssh_session.disconnect()
                break
    
    except WebSocketDisconnect:
        print(f"WebSocket 연결 종료: {session_id}")
    except Exception as e:
        print(f"WebSocket 오류: {e}")
    finally:
        # 세션 정리
        if session_id in sessions:
            sessions[session_id].disconnect()
            del sessions[session_id]

async def monitor_output(websocket: WebSocket, ssh_session: SSHSession):
    """SSH 출력을 모니터링하고 WebSocket으로 전송"""
    while ssh_session.connected:
        try:
            output = ssh_session.get_output()
            if output:
                await websocket.send_text(json.dumps({
                    "type": "output",
                    "data": output
                }))
            await asyncio.sleep(0.01)
        except Exception as e:
            print(f"출력 모니터링 오류: {e}")
            break

# SFTP API 엔드포인트들
@app.post("/api/sftp/{session_id}/connect")
async def connect_sftp(session_id: str, connection_data: dict):
    """SFTP 연결 생성"""
    try:
        sftp_session = SFTPSession()
        success = sftp_session.connect(
            hostname=connection_data["hostname"],
            username=connection_data["username"],
            password=connection_data["password"],
            port=connection_data.get("port", 22)
        )
        
        if success:
            sftp_sessions[session_id] = sftp_session
            return {"success": True, "message": "SFTP 연결 성공"}
        else:
            return {"success": False, "message": "SFTP 연결 실패"}
    except Exception as e:
        return {"success": False, "message": f"SFTP 연결 오류: {str(e)}"}

@app.get("/api/sftp/{session_id}/remote/files")
async def list_remote_files(session_id: str, path: str = "/"):
    """원격 파일 목록 조회"""
    if session_id not in sftp_sessions:
        # SSH 세션에서 SFTP 세션 생성 시도
        if session_id in sessions:
            ssh_session = sessions[session_id]
            if ssh_session.connected:
                try:
                    sftp_session = SFTPSession()
                    sftp_session.client = ssh_session.client
                    sftp_session.sftp = ssh_session.client.open_sftp()
                    sftp_session.connected = True
                    
                    # Get home directory using pwd command
                    try:
                        stdin, stdout, stderr = ssh_session.client.exec_command('pwd')
                        sftp_session.home_dir = stdout.read().decode().strip()
                        print(f"SFTP Home directory set to: {sftp_session.home_dir}")
                    except Exception as e:
                        print(f"Failed to get home directory via pwd: {e}")
                        # Fallback to sftp normalize
                        try:
                            sftp_session.home_dir = sftp_session.sftp.normalize('.')
                        except:
                            sftp_session.home_dir = '/home'
                    
                    sftp_sessions[session_id] = sftp_session
                    print(f"SFTP 세션 생성 성공: {session_id}")
                except Exception as e:
                    print(f"SFTP 세션 생성 실패: {e}")
                    raise HTTPException(status_code=500, detail=f"SFTP 세션 생성 실패: {str(e)}")
            else:
                raise HTTPException(status_code=404, detail="SSH 연결이 필요합니다")
        else:
            raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")
    
    sftp_session = sftp_sessions[session_id]
    
    # If path is "/" use home directory
    if path == "/":
        path = sftp_session.home_dir
    
    result = sftp_session.list_files(path)
    print(f"파일 목록 조회 결과: {result}")
    return result

@app.post("/api/sftp/{session_id}/upload")
async def upload_file(session_id: str, file: UploadFile = File(...), remote_path: str = Form("/")):
    """파일 업로드"""
    if session_id not in sftp_sessions:
        raise HTTPException(status_code=404, detail="SFTP 세션을 찾을 수 없습니다")
    
    sftp_session = sftp_sessions[session_id]
    success = sftp_session.upload_file(file, remote_path)
    
    if success:
        return {"success": True, "message": "파일 업로드 성공"}
    else:
        raise HTTPException(status_code=500, detail="파일 업로드 실패")

@app.get("/api/sftp/{session_id}/download")
async def download_file(session_id: str, remote_path: str):
    """파일 다운로드"""
    if session_id not in sftp_sessions:
        raise HTTPException(status_code=404, detail="SFTP 세션을 찾을 수 없습니다")
    
    sftp_session = sftp_sessions[session_id]
    file_data = sftp_session.download_file(remote_path)
    
    if file_data:
        filename = os.path.basename(remote_path)
        return StreamingResponse(
            io.BytesIO(file_data.read()),
            media_type='application/octet-stream',
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    else:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")

@app.delete("/api/sftp/{session_id}/delete")
async def delete_file(session_id: str, path: str, is_directory: bool = False):
    """파일/디렉토리 삭제"""
    if session_id not in sftp_sessions:
        raise HTTPException(status_code=404, detail="SFTP 세션을 찾을 수 없습니다")
    
    sftp_session = sftp_sessions[session_id]
    success = sftp_session.delete_file(path, is_directory)
    
    if success:
        return {"success": True, "message": "삭제 성공"}
    else:
        raise HTTPException(status_code=500, detail="삭제 실패")

@app.post("/api/sftp/{session_id}/mkdir")
async def create_directory(session_id: str, path: str):
    """디렉토리 생성"""
    if session_id not in sftp_sessions:
        raise HTTPException(status_code=404, detail="SFTP 세션을 찾을 수 없습니다")
    
    sftp_session = sftp_sessions[session_id]
    success = sftp_session.create_directory(path)
    
    if success:
        return {"success": True, "message": "디렉토리 생성 성공"}
    else:
        raise HTTPException(status_code=500, detail="디렉토리 생성 실패")

# 로컬 파일 시스템 API (브라우저에서는 제한적)
@app.get("/api/sftp/local/files")
async def list_local_files(path: str = "."):
    """로컬 파일 목록 조회 (서버 측 파일시스템)"""
    try:
        # 보안상 특정 디렉토리로 제한
        safe_path = os.path.abspath(path)
        server_root = os.path.abspath(".")
        
        if not safe_path.startswith(server_root):
            safe_path = server_root
        
        files = []
        if os.path.exists(safe_path):
            for item in os.listdir(safe_path):
                item_path = os.path.join(safe_path, item)
                if os.path.isfile(item_path):
                    stat_info = os.stat(item_path)
                    files.append({
                        'name': item,
                        'type': 'file',
                        'size': stat_info.st_size,
                        'modified': stat_info.st_mtime
                    })
                elif os.path.isdir(item_path):
                    stat_info = os.stat(item_path)
                    files.append({
                        'name': item,
                        'type': 'directory',
                        'size': 0,
                        'modified': stat_info.st_mtime
                    })
        
        return {'files': files, 'path': safe_path}
    except Exception as e:
        return {'files': [], 'path': path, 'error': str(e)}

@app.get("/")
async def root():
    return {"message": "SSH Client Backend Server"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
