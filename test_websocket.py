#!/usr/bin/env python3
import asyncio
import websockets
import json

async def test_websocket():
    uri = "ws://localhost:8000/ws/test-session"
    
    try:
        async with websockets.connect(uri) as websocket:
            print("WebSocket 연결 성공!")
            
            # SSH 연결 테스트
            connect_message = {
                "type": "connect",
                "hostname": "192.168.10.100",
                "username": "jrpark",
                "password": "Qkrwjdfuf$00",
                "port": 22
            }
            
            await websocket.send(json.dumps(connect_message))
            print("SSH 연결 요청 전송됨")
            
            # 응답 대기
            response = await websocket.recv()
            message = json.loads(response)
            print(f"응답 받음: {message}")
            
            if message.get("type") == "connection_result" and message.get("success"):
                print("SSH 연결 성공!")
                
                # 간단한 명령어 테스트
                command_message = {
                    "type": "command",
                    "data": "whoami\n"
                }
                await websocket.send(json.dumps(command_message))
                print("명령어 전송: whoami")
                
                # 출력 대기
                for i in range(5):  # 최대 5번 응답 대기
                    try:
                        response = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                        message = json.loads(response)
                        if message.get("type") == "output":
                            print(f"출력: {repr(message.get('data'))}")
                    except asyncio.TimeoutError:
                        print("응답 대기 시간 초과")
                        break
            else:
                print("SSH 연결 실패")
                
    except Exception as e:
        print(f"오류 발생: {e}")

if __name__ == "__main__":
    asyncio.run(test_websocket())
