# SSH Client 배포 가이드

## 프로젝트 개요
PuTTY와 같은 웹 기반 SSH 클라이언트가 성공적으로 구현되었습니다.

## 기술 스택
- **Backend**: FastAPI + Python + paramiko + WebSocket
- **Frontend**: Vue.js + TypeScript + xterm.js + Vite
- **통신**: WebSocket을 통한 실시간 SSH 세션

## 서버 실행 방법

### 1. 백엔드 서버 실행
```bash
cd backend
python main.py
```
- 포트: 8000
- 엔드포인트: http://localhost:8000

### 2. 프론트엔드 서버 실행
```bash
cd frontend
npm run dev
```
- 포트: 3000
- 엔드포인트: http://localhost:3000

## 접속 방법

1. 브라우저에서 `http://localhost:3000` 또는 `http://192.168.10.100:3000` 접속
2. SSH 연결 정보 입력:
   - **Hostname**: 192.168.10.100
   - **Port**: 22
   - **Username**: jrpark
   - **Password**: [실제 비밀번호 입력]
3. "Connect" 버튼 클릭
4. 터미널에서 명령어 실행

## 주요 기능

✅ **웹 기반 SSH 터미널**
- xterm.js를 사용한 실제 터미널 UI
- ANSI 색상 코드 지원
- 커서 깜빡임 및 실시간 입출력

✅ **다중 세션 지원**
- 탭 기반 인터페이스
- "+" 버튼으로 새 세션 추가
- 세션 간 독립적 동작

✅ **실시간 통신**
- WebSocket을 통한 양방향 통신
- 명령어 실행 결과 실시간 스트리밍
- 세션 상태 관리

✅ **보안 기능**
- SSH 키 자동 수락 (개발용)
- 세션별 독립적 연결 관리
- WebSocket 연결 종료 시 SSH 세션 자동 정리

## 테스트 결과

### WebSocket 연결 테스트
```bash
python test_websocket.py
```
- ✅ WebSocket 연결 성공
- ✅ SSH 연결 성공 (192.168.10.100:22)
- ✅ 명령어 실행 성공 (`whoami` → `jrpark`)

### 서버 상태 확인
```bash
curl http://localhost:8000
# 응답: {"message":"SSH Client Backend Server"}

curl http://localhost:3000
# 응답: HTML 페이지 정상 로드
```

## 프로젝트 구조

```
term/
├── backend/                    # FastAPI 백엔드
│   ├── main.py                # 메인 서버 (SSH + WebSocket)
│   └── requirements.txt       # Python 의존성
├── frontend/                  # Vue.js 프론트엔드
│   ├── src/
│   │   ├── App.vue           # 메인 Vue 컴포넌트
│   │   ├── main.ts           # 엔트리 포인트
│   │   └── style.css         # 스타일시트
│   ├── package.json          # Node.js 의존성
│   ├── vite.config.ts        # Vite 설정
│   ├── tsconfig.json         # TypeScript 설정
│   └── index.html            # HTML 템플릿
├── test_websocket.py         # WebSocket 테스트 스크립트
├── test.html                 # 테스트 결과 페이지
└── README.md                 # 프로젝트 설명
```

## 네트워크 설정

### CORS 설정 (backend/main.py)
```python
allow_origins=[
    "http://localhost:3000",
    "http://192.168.10.100:3000",
    "https://code.ai-hpc.io",
    "http://code.ai-hpc.io"
]
```

### WebSocket 연결 (frontend)
- 동적 호스트 감지
- HTTP/HTTPS 프로토콜에 따른 WS/WSS 자동 선택
- 포트 8000으로 백엔드 연결

## 문제 해결

### 1. CORS 오류
- 백엔드의 `allow_origins`에 도메인 추가
- 프론트엔드 Vite 설정에서 CORS 활성화

### 2. WebSocket 연결 실패
- 백엔드 서버 실행 상태 확인
- 방화벽 설정 확인 (포트 8000)
- 브라우저 개발자 도구에서 네트워크 탭 확인

### 3. SSH 연결 실패
- 대상 서버 SSH 서비스 상태 확인
- 사용자 계정 및 비밀번호 확인
- 네트워크 연결 상태 확인

## 성능 최적화

- 터미널 출력 버퍼링 (1024 바이트 단위)
- 비동기 I/O 처리
- 세션별 독립적 스레드 관리
- 자동 리사이즈 지원

## 보안 고려사항

⚠️ **개발 환경용 설정**
- SSH 키 자동 수락 활성화
- HTTPS 미적용
- 인증 없는 웹 접근

🔒 **프로덕션 환경 권장사항**
- HTTPS 적용
- 웹 애플리케이션 인증 추가
- SSH 키 검증 강화
- 접근 IP 제한
- 로그 모니터링

## 확장 가능성

- 파일 전송 기능 (SCP/SFTP)
- 세션 저장 및 복원
- 사용자 관리 시스템
- 터미널 테마 커스터마이징
- 명령어 히스토리 저장
