from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import paramiko
import asyncio
import json
import threading
import queue
import time

app = FastAPI()

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://192.168.10.100:3000",
        "https://code.ai-hpc.io",
        "http://code.ai-hpc.io"
    ],
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
        
    def connect(self, hostname, username, password, port=22):
        try:
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.client.connect(hostname, port=port, username=username, password=password)
            
            self.channel = self.client.invoke_shell()
            self.channel.settimeout(0.1)
            self.connected = True
            
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

# 세션 관리
sessions = {}

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

@app.get("/")
async def root():
    return {"message": "SSH Client Backend Server"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
