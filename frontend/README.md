# 예매 데모 프론트 (코드 흐름 시각화)

왼쪽에서 실제 예매 서비스를 조작하면, 오른쪽에서 그 요청이 지나가는 **실제 백엔드 코드**가
라우터 → 서비스 → 도메인 → 저장소 순서로 강조된다. 설계는 [`docs/frontend-demo-plan.md`](../docs/frontend-demo-plan.md) 참고.

## 실행 (레포 루트에서)

```bash
# 1. DB
docker compose up -d db

# 2. 테이블 생성 + 데모 데이터 (⚠ 기존 데이터를 모두 지움)
uv run python scripts/seed_demo.py

# 3. 팀 백엔드 → :8000
uv run uvicorn main:app --app-dir src --port 8000

# 4. 프론트 → http://localhost:5173
cd frontend && npm install && npm run dev
```

백엔드가 다른 주소에 있으면 `VITE_API_TARGET=http://<주소>:8000 npm run dev` 처럼 지정한다.

### EC2에서 빌드본으로 띄우기

```bash
cd frontend && npm ci && npm run build
VITE_API_TARGET=http://localhost:8000 npm run preview   # → :4173 (/v1 은 백엔드로 프록시)
```

## 구조

| 경로 | 역할 |
|---|---|
| `../scripts/seed_demo.py` | 테이블 생성 + 데모 데이터 초기화 (계정 비밀번호는 파일 안 `DEMO_PASSWORD`) |
| `src/api/client.js` | 모든 API 호출이 지나가는 함수 → 오른쪽 패널에 요청·응답 이벤트 전달 |
| `src/trace/flows.js` | API별 코드 흐름 정의 (파일 + 함수 이름 + 강조할 줄 문자열) |
| `src/trace/sourceLoader.js` | 레포의 `src/**/*.py`를 그대로 읽어 함수 위치를 찾음 |
| `src/trace/TracePanel.jsx` | 오른쪽 패널 (재생·일시정지·단계 이동·동시 요청 2열) |
| `src/api/toss.js` | 토스 결제창 열기, 결제창에서 돌아온 값 읽기 |
| `src/pages/*` | 왼쪽 화면 (로그인·회원가입, 축제, 예매, 내 예매·결제, 내 티켓, 내 정보, 관리자) |

## 왼쪽 화면의 흐름 (실제 API)

회원가입·로그인(JWT) → 축제 목록 → 예매 → 결제(토스 결제창 → 승인) → 입금 확인 → 티켓

- 로그인하면 받은 토큰을 `Authorization: Bearer` 헤더로 모든 요청에 싣는다 (`src/api/client.js`).

## 토스 결제창을 쓰려면

토스 개발자센터의 **같은 상점** 테스트 키 두 개가 필요하다. 없으면 결제 건 생성까지만 되고 결제창은 뜨지 않는다.

| 위치 | 변수 | 값 |
|---|---|---|
| 레포 루트 `.env` | `TOSS_SECRET_KEY` | 테스트 시크릿 키 (`test_sk_...`) |
| `frontend/.env.local` (`.env.example` 복사) | `VITE_TOSS_CLIENT_KEY` | 테스트 클라이언트 키 (`test_ck_...`) |

## 알아둘 점

- 예매 확정·티켓 발급은 토스 입금 웹훅(`/v1/payments/webhooks/deposit`)이 백엔드에 도착해야 진행된다. 웹훅이 예매 확정까지 연결되어 있는지는 백엔드 쪽에서 확인해야 한다.
- 입금 기한 만료는 서버의 만료 작업(1분 주기)이 자동 처리한다.

## 흐름을 추가하려면

`src/trace/flows.js`에 `"메서드 경로템플릿"` 키로 step 목록을 추가한다. 경로의 숫자는 `{id}`로 쓴다.
함수 이름과 anchor 문자열이 실제 코드에 있어야 하며, 없으면 브라우저 콘솔에 `[trace]` 경고가 뜬다.
