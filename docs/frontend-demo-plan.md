# 프론트엔드 데모 설계 (코드 흐름 시각화)

> 이 문서는 구현 지시서다. 이 문서만 보고 `frontend/` 폴더에 데모 앱을 만들 수 있도록 작성했다.
> 백엔드(`src/`)는 수정하지 않는 것을 원칙으로 한다.

## 1. 목표

- 발표에서 **실제 서비스를 조작하면서, 그 순간 백엔드에서 어떤 코드가 실행되는지 함께 보여준다.**
- 화면을 좌우로 나눈다.
  - **왼쪽 (서비스 화면):** 실제로 동작하는 예매 서비스. 버튼을 누르면 진짜 API를 호출한다.
  - **오른쪽 (코드 패널):** 왼쪽에서 API 요청이 나가는 순간 자동으로 반응해, 라우터 → 서비스 → 도메인 → 저장소 순서로 코드를 한 단계씩 강조한다.
- 발표자는 **왼쪽만 조작**한다. 오른쪽을 위한 별도 버튼은 없다.

## 2. 기술 스택

| 항목 | 선택 | 이유 |
|---|---|---|
| 프레임워크 | React + Vite + TypeScript | 빠른 개발 서버, 프록시 설정이 쉬움 |
| 라우팅 | react-router | 화면 6~8개 |
| 서버 상태 | 직접 fetch 래퍼 (라이브러리 최소화) | 모든 요청을 한 곳에서 가로채야 함 (4장) |
| 코드 하이라이트 | Shiki | 파이썬 하이라이트 품질, 줄 단위 강조 지원 |
| 스타일 | CSS Modules 또는 Tailwind | 팀 합의에 따름 |
| 결제 | 토스페이먼츠 결제위젯 JS SDK (테스트 키) | 가상계좌 발급은 브라우저에서 결제창을 띄워야 함 |

## 3. 폴더 구조

```
frontend/
├── package.json
├── vite.config.ts            # /v1 → http://localhost:8000 프록시
├── index.html
└── src/
    ├── main.tsx
    ├── App.tsx               # 좌우 분할 레이아웃
    ├── api/
    │   ├── client.ts         # 공통 요청 함수 (모든 API 호출이 여기를 지남) ★
    │   └── endpoints.ts      # API별 함수 (login, createReservation, ...)
    ├── pages/                # 왼쪽 서비스 화면
    │   ├── LoginPage.tsx
    │   ├── FestivalListPage.tsx
    │   ├── FestivalDetailPage.tsx   # 회차·잔여 수량 + 예매 폼
    │   ├── PaymentPage.tsx          # 토스 가상계좌
    │   ├── MyReservationsPage.tsx   # 내 예매 목록·취소
    │   ├── MyTicketsPage.tsx
    │   └── admin/
    │       ├── FestivalReservationsPage.tsx  # 축제별 예매 목록
    │       └── PerformanceAdminPage.tsx      # 공연 취소
    ├── trace/                # 오른쪽 코드 패널
    │   ├── TracePanel.tsx    # 패널 UI (재생·일시정지·속도)
    │   ├── traceBus.ts       # client.ts → TracePanel 이벤트 전달
    │   ├── flows.ts          # API별 코드 흐름 정의 ★
    │   └── sourceLoader.ts   # 백엔드 소스 파일 읽기 + 함수 위치 찾기
    └── styles/
```

## 4. 핵심 구조: API 호출에 코드 흐름을 연결

### 4-1. 버튼이 아니라 "API 호출"에 연결한다

```
[왼쪽 버튼 클릭] → endpoints.createReservation() → client.ts request()
                                                       │
                       ┌───────────────────────────────┤
                       ▼                               ▼
               traceBus.emit("request")         fetch("/v1/reservations")
                       │                               │
                       ▼                               ▼
               TracePanel: 흐름 재생 시작        응답 도착 (201 / 422 ...)
                       │                               │
                       └──────── traceBus.emit("response", status, body)
                                       │
                                       ▼
                       TracePanel: 성공 경로 / 실패 경로로 마무리
```

- `client.ts`의 `request(method, path, body)` 하나만 fetch를 호출한다.
- 요청 직전에 `{ method, pathTemplate, body }`를, 응답 후 `{ status, json }`을 `traceBus`로 보낸다.
- 경로의 숫자 부분은 템플릿으로 바꿔 매칭한다. 예: `/v1/reservations/12/cancel` → `/v1/reservations/{reservation_id}/cancel`
- 화면이 늘어나도 API가 같으면 흐름은 자동으로 재사용된다.

### 4-2. 흐름 정의 형식 (`flows.ts`)

줄 번호는 코드가 바뀌면 틀어지므로 **파일 + 함수 이름(+ 함수 안의 기준 문자열)** 으로 위치를 지정한다.
`sourceLoader`가 소스를 읽어 함수 시작 위치를 찾고, `anchor` 문자열이 있는 줄을 강조한다.

```ts
type Step = {
  file: string;          // 예: "reservations/application/service.py"
  symbol: string;        // 함수/메서드 이름. 예: "ReservationService.create_reservation"
  anchor?: string;       // 강조할 줄에 들어 있는 문자열. 예: "check_daily_limit("
  note: string;          // 코드 옆에 띄울 한 줄 설명
  layer: "router" | "service" | "domain" | "repository" | "db";
};

type Flow = {
  method: string;
  path: string;          // FastAPI 경로 템플릿
  title: string;         // 패널 상단 제목
  steps: Step[];         // 공통 경로
  onStatus?: Record<number, { stopAt?: string; steps?: Step[]; note: string }>;
  // 실패 응답이면 stopAt(anchor)에서 빨갛게 멈추고 note 표시
};
```

### 4-3. 소스 읽기 (`sourceLoader.ts`)

- Vite의 `import.meta.glob("../../src/**/*.py", { query: "?raw", eager: false })`로 백엔드 소스를 **빌드 시점에 그대로** 가져온다.
  - 항상 실제 코드가 보이고, 백엔드를 수정하면 데모도 자동으로 따라간다.
- `symbol`로 위치 찾기: `def 이름(` / `async def 이름(` 줄을 찾고, 들여쓰기가 끝나는 곳까지를 함수 범위로 본다.
- 함수를 찾지 못하면 콘솔 경고 + 파일 맨 위를 보여준다 (데모가 멈추지 않게).

## 5. 오른쪽 패널 UI

```
┌───────────────────────────────────────┐
│ POST /v1/reservations   예매 생성      │  ← 요청 표시
│ ● router  ● service  ○ domain  ○ repo │  ← 계층 진행 표시
├───────────────────────────────────────┤
│ reservations/application/service.py   │
│  205 │   # ⑤ 날짜별 2장 검사            │
│  206 │▶  check_daily_limit(...)        │  ← 현재 단계 강조
│  207 │                                 │
│  💬 같은 축제 기존 예매 + 신규가        │  ← note
│     하루 2장을 넘는지 검사해요           │
├───────────────────────────────────────┤
│ ⏮ ⏯ ⏭   속도 [1x ▾]   [패널 접기]     │
├───────────────────────────────────────┤
│ 응답 422 OVER_RESERVATION_QUANTITY    │  ← 실제 응답 JSON (접기 가능)
└───────────────────────────────────────┘
```

- 기본은 자동 재생(단계당 약 1.2초). 발표 중에는 ⏯로 멈추고 ⏭로 한 단계씩 넘긴다.
- 응답이 흐름 재생보다 먼저 오면, 마지막 단계까지 재생한 뒤 결과를 표시한다.
- 실패 응답이면 `onStatus[status].stopAt` 줄에서 빨간색으로 멈추고 에러 코드를 보여준다.
- 요청이 연달아 오면 큐에 쌓아 순서대로 재생한다. 동시 요청(7-6)은 2열로 나란히 재생한다.
- [패널 접기]를 누르면 왼쪽 서비스 화면만 전체 폭으로 보인다.

## 6. 백엔드 API 정리 (데모에 쓰는 것)

공통 응답 형식: `{ success, code, message, errors, data, responded_at }` (`shared/core/schemas.py`의 `APIResponse`)
인증: `Authorization: Bearer <access_token>` (로그인 응답의 `data.access_token`)

| 화면 | 메서드 | 경로 | 비고 |
|---|---|---|---|
| 회원가입 | POST | `/v1/users` | `{ email, name, password }` |
| 로그인 | POST | `/v1/auth/login` | `{ email, password }` → `access_token` |
| 로그아웃 | POST | `/v1/auth/logout` | 204 |
| 축제 목록 | GET | `/v1/festivals` | |
| 축제 상세 | GET | `/v1/festivals/{festival_id}` | |
| 회차 목록 | GET | `/v1/festivals/{festival_id}/performances` | 잔여 수량 표시 |
| 예매 생성 | POST | `/v1/reservations` | `{ festival_id, quantity(1~2), ticket_type(SAT/SUN/BOTH), discount_type }` |
| 내 예매 | GET | `/v1/reservations/me` | |
| 예매 상세 | GET | `/v1/reservations/{reservation_id}` | |
| 예매 취소 | PATCH | `/v1/reservations/{reservation_id}/cancel` | |
| 결제 조회 | GET | `/v1/payments?reservation_id=` | 결제 담당 API 확인 필요 |
| 결제 승인 | POST | `/v1/payments/{payment_id}/approve` | 토스 결제창 성공 후 |
| 입금 웹훅 | POST | `/v1/payments/webhooks/deposit` | 토스가 호출 (데모에서는 시뮬레이션, 9장) |
| 내 티켓 | GET | `/v1/tickets` | |
| 티켓 상세 | GET | `/v1/tickets/{ticket_id}` | |
| [관리자] 축제별 예매 | GET | `/v1/festivals/{festival_id}/reservations?day=&statuses=&page=&size=` | |
| [관리자] 공연 취소 | PATCH | `/v1/performances/{performance_id}/cancel` | 예매·티켓 일괄 취소 (#131) |
| [관리자] 입장 처리 | POST | `/v1/tickets/enter` | |

선택 값
- `ticket_type`: `SAT`(토요일권) / `SUN`(일요일권) / `BOTH`(양일권 = 토+일 가격)
- `discount_type`: `NONE` / `DISABLED` / `VETERAN` / `SENIOR` / `KANT`

## 7. 시나리오별 코드 흐름 (flows.ts에 옮길 내용)

파일 경로는 `src/` 기준. `symbol`은 클래스명.메서드명.

### 7-1. 예매 생성 `POST /v1/reservations`

| # | layer | file | symbol | anchor | note |
|---|---|---|---|---|---|
| 1 | router | reservations/presentation/routers/v1/router.py | create_reservation | `service.create_reservation(` | body에서 값을 꺼내고, user_id는 토큰에서 가져와요 |
| 2 | router | wiring/reservation.py | build_current_actor | `find_by_id(token.user_id)` | 토큰 검증 → 회원 조회 → 관리자 여부 확인 |
| 3 | service | reservations/application/service.py | ReservationService.create_reservation | `find_by_id(festival_id)` | 축제가 있는지, 취소·종료되지 않았는지 확인 |
| 4 | service | 〃 | ReservationService._find_target_performance | `astimezone(KST).weekday()` | 티켓 종류에 맞는 요일 회차를 골라요 (한국 시간 기준) |
| 5 | service | 〃 | ReservationService.create_reservation | `is_bookable(now)` | 회차가 예매 가능한지 (오픈, 잔여, 예매 기간) |
| 6 | domain | reservations/domain/service.py | check_daily_limit | — | 같은 축제에서 하루 2장 넘는지 검사 |
| 7 | domain | performances/domain/performance.py | Performance.decrease_remaining | — | 회차 잔여 수량 차감 (0이면 매진) |
| 8 | domain | reservations/domain/reservation.py | Reservation.create | `expires_at = now +` | 금액·할인 계산, 상태 PENDING, 입금 기한 설정 |
| 9 | repository | reservations/infrastructure/repositories.py | SqlalchemyReservationRepository.save | — | DB에 저장 (commit은 요청 끝에서 한 번) |

응답별 마무리
- `201`: "예매가 생성되었어요. 입금 기한 안에 결제해야 해요."
- `422 OVER_RESERVATION_QUANTITY`: 6번에서 멈춤 → "하루 2장 한도를 넘었어요. 차감했던 수량도 함께 rollback돼요."
- `409 RESERVATION_NOT_AVAILABLE`: 3번 또는 5번에서 멈춤 → "취소된 축제거나 예매 기간이 아니에요."
- `404 PERFORMANCE_NOT_FOUND`: 4번에서 멈춤 → "해당 요일 회차가 없어요."
- `401 UNAUTHORIZED`: 2번에서 멈춤 → "로그인이 필요해요."

### 7-2. 결제 확정 → 티켓 발급 (입금 완료)

> 현재 결제 쪽에서 `confirm_reservation`을 호출하는 연결이 **아직 없다** (결제 담당 작업).
> 연결되기 전까지 이 흐름은 데모 시뮬레이션(9장)으로 보여준다.

| # | layer | file | symbol | anchor | note |
|---|---|---|---|---|---|
| 1 | router | payments/presentation/webhook_router.py | (웹훅 엔드포인트) | — | 토스가 입금 완료를 알려줘요 |
| 2 | service | payments/application/webhook_service.py | DepositWebhookService.process | `retrieve(` | 알림을 믿지 않고 토스에 최신 상태를 다시 물어봐요 |
| 3 | service | reservations/application/service.py | ReservationService.confirm_reservation | `lock(reservation_id)` | 예매 행을 잠가요 (만료 작업·취소와 동시에 처리되지 않게) |
| 4 | service | 〃 | 〃 | `ReservationStatus.CONFIRMED` | 이미 확정이면 그대로 성공 (웹훅이 두 번 와도 안전) |
| 5 | domain | reservations/domain/reservation.py | Reservation.confirm | — | PENDING → CONFIRMED |
| 6 | service | reservations/application/service.py | ReservationService._issue_tickets | `ticket.confirm(now)` | 회차 × 수량만큼 티켓 발급 (양일권 2장 = 4장) |

### 7-3. 예매 취소 `PATCH /v1/reservations/{reservation_id}/cancel`

| # | layer | file | symbol | anchor | note |
|---|---|---|---|---|---|
| 1 | router | reservations/presentation/routers/v1/router.py | cancel_reservation | — | 본인 또는 관리자 |
| 2 | service | reservations/application/service.py | ReservationService.cancel_reservation | `lock(reservation_id)` | 예매 행 잠금 (비관적 락) |
| 3 | repository | reservations/infrastructure/repositories.py | SqlalchemyReservationRepository.lock | `with_for_update()` | SELECT … FOR UPDATE |
| 4 | service | reservations/application/service.py | ReservationService.cancel_reservation | `PerformanceStatus.COMPLETED` | 종료된 공연이면 취소 불가 |
| 5 | service | 〃 | 〃 | `cancel_deadline_at` | 일반 회원: 취소 마감 / 관리자: 공연 시작 전까지 |
| 6 | domain | reservations/domain/reservation.py | Reservation.cancel | — | CANCELED + 취소 시각 기록 |
| 7 | service | reservations/application/service.py | ReservationService._cancel_tickets | `force_cancel` | 발급된 티켓도 함께 취소 |
| 8 | service | 〃 | ReservationService._restore_remaining | `increase_remaining` | 잔여 수량 복구 (취소된 회차는 건너뜀) |

응답별 마무리
- `409 CANCEL_DEADLINE_VIOLATION`: 4번 또는 5번에서 멈춤
- `409 INVALID_RESERVATION_STATUS`: 6번에서 멈춤 → "이미 취소·만료된 예매예요."
- `404 RESERVATION_NOT_FOUND`: 2번에서 멈춤 → "남의 예매는 존재 자체를 숨겨요 (403이 아니라 404)."

### 7-4. [관리자] 공연 취소 → 예매 일괄 취소 `PATCH /v1/performances/{performance_id}/cancel`

> PR #141 (공연 담당) 머지 후 기준. 공연 서비스가 예매 서비스를 같은 세션으로 호출한다.

| # | layer | file | symbol | anchor | note |
|---|---|---|---|---|---|
| 1 | router | performances/presentation/routers/v1/router.py | cancel_performance | — | 관리자 |
| 2 | service | performances/application/service.py | PerformanceService.cancel_performance | `performance.cancel(` | 회차를 CANCELED로 |
| 3 | service | 〃 | 〃 | `_performance_repo.save(` | 먼저 저장 → 예매 쪽이 이 회차를 CANCELED로 읽음 |
| 4 | service | reservations/application/service.py | ReservationService.cancel_by_performance | `weekday == 5` | 토요일 회차 → SAT + BOTH 예매가 대상 |
| 5 | repository | reservations/infrastructure/repositories.py | SqlalchemyReservationRepository.find_active_by_festival_for_update | `with_for_update()` | 진행 중 예매를 잠그면서 조회 |
| 6 | service | reservations/application/service.py | ReservationService.cancel_by_performance | `_cancel_tickets(` | 예매·티켓 취소 |
| 7 | service | 〃 | ReservationService._restore_remaining | `RESTORABLE_STATUSES` | 양일권의 남은 요일(일요일) 좌석만 복구 |

### 7-5. 입금 기한 만료 (백그라운드 작업)

> API 요청이 아니라 서버 안에서 1분마다 돈다. 왼쪽 화면에서는 "내 예매" 상태가 PENDING → EXPIRED로 바뀌는 것으로 보여준다.
> 오른쪽 패널에는 "⏱ 백그라운드" 배지로 표시한다. (트리거 방법은 9장)

| # | layer | file | symbol | anchor | note |
|---|---|---|---|---|---|
| 1 | — | main.py | lifespan | `start_expire_job()` | 서버가 켜질 때 만료 작업 시작 |
| 2 | — | reservations/infrastructure/expire_job.py | _loop | `asyncio.sleep(` | 1분마다 반복 |
| 3 | repository | reservations/infrastructure/repositories.py | SqlalchemyReservationRepository.find_overdue_pending | `skip_locked=True` | 기한 지난 PENDING만, 결제 처리 중인 예매는 건너뜀 |
| 4 | domain | reservations/domain/reservation.py | Reservation.expire | — | PENDING → EXPIRED |
| 5 | service | reservations/application/service.py | ReservationService._restore_remaining | — | 좌석 반납 |

### 7-6. 동시 취소 (락 시연)

- 왼쪽 "내 예매" 화면에 데모 전용 버튼 **[동시에 2번 취소]** 를 둔다 (`?demo=1`일 때만 표시).
- 같은 예매에 취소 요청 2개를 `Promise.all`로 동시에 보낸다.
- 오른쪽 패널은 2열로 나란히 재생한다.
  - 요청 A: 7-3 흐름 전체 → `200`
  - 요청 B: 3번(`with_for_update`)에서 **"⏳ 대기 중"** 표시 → A가 끝난 뒤 6번에서 `409 INVALID_RESERVATION_STATUS`로 멈춤
- 마지막에 "잔여 수량은 1번만 복구됐어요"를 표시한다 (회차 잔여 수량 재조회로 확인).

## 8. 화면 흐름 (데모 진행 순서 예시)

1. 로그인 (일반 회원) → 7-1 이전에 인증 흐름이 짧게 재생됨
2. 축제 목록 → 축제 상세 (회차·잔여 수량)
3. 토요일권 2장 예매 → **7-1 성공**
4. 같은 축제 양일권 1장 예매 시도 → **7-1 실패 (422 하루 2장 초과)**
5. 결제 화면 → 가상계좌 발급 → 입금 시뮬레이션 → **7-2** → 예매 CONFIRMED, 내 티켓 2장
6. 예매 취소 → **7-3** → 티켓 CANCELED, 잔여 수량 복구
7. 새 예매 → [동시에 2번 취소] → **7-6**
8. 관리자 로그인 → 축제별 예매 목록 → 공연 취소 → **7-4**
9. (선택) 입금하지 않은 예매가 만료되는 모습 → **7-5**

## 9. 데모 전용 보조 기능

- **입금 시뮬레이션:** 토스 테스트 환경의 가상계좌 입금은 실제 입금이 어렵다.
  - 1안: 토스 개발자센터의 테스트 웹훅 발송 기능을 사용한다.
  - 2안: 데모 화면에서 웹훅 엔드포인트로 테스트 payload를 보낸다 (결제 담당과 방식 확인 필요).
  - 결제 → `confirm_reservation` 연결이 아직 없으면, 이 단계는 오른쪽 패널만 7-2 흐름을 재생하고 "결제 담당 연동 예정"으로 표시한다.
- **만료 시연:** 예매 대기 시간이 길면 기다릴 수 없다. 데모용 DB에서 해당 예매의 `expires_at`을 과거로 바꾸는 방식은 쓰지 않는다 (백엔드 수정 금지 원칙). 대기 시간을 짧게 설정한 환경(예: 10분)에서 미리 만든 예매로 보여준다.
- **데모 데이터:** 축제 1개(토·일), 회차 2개(정원 100), 일반 회원 2명, 관리자 1명을 미리 넣는 시드 스크립트를 `frontend/` 안이 아닌 별도 위치에 둔다 (팀 합의).

## 10. 개발 환경

```bash
# 백엔드 (레포 루트)
docker compose up -d db
uv run uvicorn main:app --app-dir src --reload   # http://localhost:8000

# 프론트
cd frontend
npm install
npm run dev                                       # http://localhost:5173
```

`vite.config.ts` 프록시

```ts
server: { proxy: { "/v1": "http://localhost:8000" } }
```

- 프록시를 쓰면 백엔드에 CORS 설정을 추가하지 않아도 된다.
- 토스 클라이언트 키는 `frontend/.env.local`의 `VITE_TOSS_CLIENT_KEY`에 넣는다 (커밋 금지, `.gitignore`에 추가).

## 11. 선행 조건 (데모 전에 끝나 있어야 하는 것)

| 항목 | 상태 | 담당 |
|---|---|---|
| dev 서버 실행 (`main.py` import 오류) | PR #140 | 예매 |
| auth·payments wiring | PR #138 (`.env.example`에 JWT 항목 필요) | auth·payments |
| auth·payments 라우터 `main.py` 등록 | 미정 | auth·payments |
| 공연 취소 → 예매 일괄 취소 | PR #141 | 공연 |
| 결제 DONE → `confirm_reservation` 호출 | 미구현 | 결제 |
| 가상계좌 입금 마감 = 예매 `expires_at` − 5분 | 미구현 (예매 쪽 `deposit_due_at`은 로컬 보류 중) | 결제 + 예매 |
| 로컬 DB에 `token_blacklist`, `payments` 테이블 | 각자 생성 필요 | 전원 |

## 12. 구현 순서 (권장)

1. Vite 프로젝트 생성, 좌우 분할 레이아웃, 프록시 설정
2. `client.ts` + `traceBus.ts` + 빈 `TracePanel` (요청·응답만 표시)
3. `sourceLoader.ts` (소스 읽기, 함수 위치 찾기) + Shiki 하이라이트
4. `flows.ts`에 7-1 하나만 넣고 재생·강조·실패 멈춤까지 완성
5. 로그인·축제·예매 화면 → 7-1 실제 연결 확인
6. 7-3 취소, 7-6 동시 취소
7. 관리자 화면 + 7-4
8. 결제 화면 + 7-2 (선행 조건 상태에 맞춰 실제 연동 또는 시뮬레이션)
9. 재생 컨트롤(일시정지·속도·접기), 다듬기

## 13. 하지 않을 것

- 백엔드(`src/`) 코드 수정 (데모를 위해 API를 추가하지 않는다)
- 실제 실행 경로 추적(백엔드 계측) — 미리 정의한 흐름 재생 방식으로 충분하다
- 회원가입 화면 디자인 다듬기 등 발표와 무관한 화면 완성도
