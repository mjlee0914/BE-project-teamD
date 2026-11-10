# 예매 데모 프론트 (코드 흐름 시각화)

왼쪽에서 실제 예매 서비스를 조작하면, 오른쪽에서 그 요청이 지나가는 **실제 백엔드 코드**가
라우터 → 서비스 → 도메인 → 저장소 순서로 강조된다. 설계는 [`docs/frontend-demo-plan.md`](../docs/frontend-demo-plan.md) 참고.

## 실행 (레포 루트에서)

```bash
# 1. DB
docker compose up -d db

# 2. 테이블 생성 + 데모 데이터 (회원 3명, 축제 1개, 토·일 회차)
uv run python frontend/demo_backend/seed.py

# 3. 데모 백엔드 (팀 앱 + 데모용 로그인 대체·보조 API) → :8000
uv run uvicorn server:app --app-dir frontend/demo_backend --port 8000

# 4. 프론트 → http://localhost:5173
cd frontend && npm install && npm run dev
```

## 구조

| 경로 | 역할 |
|---|---|
| `demo_backend/seed.py` | 테이블 생성 + 데모 데이터 초기화 |
| `demo_backend/server.py` | 팀 앱(`src/main.py`)을 그대로 import하고 데모 기능만 덧붙임 (팀 코드 수정 없음) |
| `src/api/client.js` | 모든 API 호출이 지나가는 함수 → 오른쪽 패널에 요청·응답 이벤트 전달 |
| `src/trace/flows.js` | API별 코드 흐름 정의 (파일 + 함수 이름 + 강조할 줄 문자열) |
| `src/trace/sourceLoader.js` | 레포의 `src/**/*.py`를 그대로 읽어 함수 위치를 찾음 |
| `src/trace/TracePanel.jsx` | 오른쪽 패널 (재생·일시정지·단계 이동·동시 요청 2열) |
| `src/pages/*` | 왼쪽 화면 (예매하기, 내 예매, 내 티켓, 관리자) |

## 데모 전용으로 대신하는 것 (실제 연동 전까지)

| 데모 | 실제 | 상태 |
|---|---|---|
| 상단 회원 선택 → `X-Demo-User` 헤더 | JWT 로그인 | auth wiring PR #138 |
| "입금 완료 (시뮬레이션)" → `/demo/reservations/{id}/confirm` | 결제 웹훅 DONE → `confirm_reservation` | 결제 담당 |
| "입금 기한 지나게 하기" → `/demo/reservations/{id}/expire` | 서버 만료 작업이 1분마다 실행 | 구현됨 (#134) |
| "↺ 초기화" → `/demo/reset` | — | 데모 전용 |

## 흐름을 추가하려면

`src/trace/flows.js`에 `"메서드 경로템플릿"` 키로 step 목록을 추가한다. 경로의 숫자는 `{id}`로 쓴다.
함수 이름과 anchor 문자열이 실제 코드에 있어야 하며, 없으면 브라우저 콘솔에 `[trace]` 경고가 뜬다.
