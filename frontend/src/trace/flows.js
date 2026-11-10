// API별 "백엔드에서 실행되는 코드 순서" 정의
//
// 줄 번호 대신 (파일 + 함수 이름 + anchor 문자열)로 위치를 지정한다
// → 백엔드 코드가 바뀌어도 함수 이름만 같으면 데모가 깨지지 않음
//
// step
//   id     : 실패 시 멈출 위치를 가리킬 때 쓰는 이름
//   layer  : router | auth | service | domain | repository | demo
//   file   : 레포 루트 기준 경로
//   symbol : "함수" 또는 "클래스.메서드"
//   anchor : 강조할 줄에 들어 있는 문자열 (없으면 def 줄)
//   note   : 코드 옆 설명
//
// outcomes : 응답 코드별 마무리
//   key "201" | "409" | "422:OVER_RESERVATION_QUANTITY" (상태:에러코드가 더 우선)
//   stopAt : 이 step에서 빨갛게 멈춤 (없으면 끝까지 재생)
//   waitAt : 이 step에서 "⏳ 잠금 대기"를 보여줌 (동시 요청 시연)
//   anchor : 실패해서 멈출 때 강조할 줄 (보통 raise 줄)

const R = "src/reservations";
const ROUTER = `${R}/presentation/routers/v1/router.py`;
const SERVICE = `${R}/application/service.py`;
const ENTITY = `${R}/domain/reservation.py`;
const RULE = `${R}/domain/service.py`;
const REPO = `${R}/infrastructure/repositories.py`;
const PERF = "src/performances/domain/performance.py";
const DEMO = "frontend/demo_backend/server.py";

const authStep = {
  id: "auth",
  layer: "auth",
  file: DEMO,
  symbol: "demo_reservation_actor",
  anchor: "is_admin=",
  note: "요청한 사람 확인 (데모: 선택한 회원 / 실제: JWT 토큰 → 회원 조회)",
};

export const FLOWS = {
  // ─────────────────────────────── 예매 생성
  "POST /v1/reservations": {
    title: "예매 생성",
    steps: [
      { id: "router", layer: "router", file: ROUTER, symbol: "create_reservation", anchor: "service.create_reservation(", note: "body에서 값을 꺼내고, user_id는 body가 아니라 로그인 정보에서 가져와요" },
      authStep,
      { id: "festival", layer: "service", file: SERVICE, symbol: "ReservationService.create_reservation", anchor: "festival.status(today)", note: "축제가 있는지, 취소·종료되지 않았는지 확인" },
      { id: "pick", layer: "service", file: SERVICE, symbol: "ReservationService._find_target_performance", anchor: "astimezone(KST).weekday()", note: "티켓 종류에 맞는 요일 회차를 골라요 (한국 시간 기준 요일)" },
      { id: "bookable", layer: "domain", file: PERF, symbol: "Performance.is_bookable", anchor: "booking_open_at <= now", note: "회차가 OPEN이고, 잔여가 있고, 예매 기간인지" },
      { id: "limit", layer: "domain", file: RULE, symbol: "check_daily_limit", anchor: "raise OverReservationQuantity", note: "같은 축제 기존 예매 + 이번 예매가 하루 2장을 넘는지 (양일권 = 토1 + 일1)" },
      { id: "decrease", layer: "domain", file: PERF, symbol: "Performance.decrease_remaining", anchor: "remaining_count -=", note: "회차 잔여 수량 차감 (0이 되면 SOLD_OUT)" },
      { id: "create", layer: "domain", file: ENTITY, symbol: "Reservation.create", anchor: "expires_at = now +", note: "금액·할인 계산, 상태 PENDING, 입금 기한 설정" },
      { id: "save", layer: "repository", file: REPO, symbol: "SqlalchemyReservationRepository.save", anchor: "flush()", note: "DB에 저장 (commit은 요청이 끝날 때 한 번)" },
    ],
    outcomes: {
      201: { note: "예매 생성 완료 → 입금 기한 안에 결제해야 해요" },
      "422:OVER_RESERVATION_QUANTITY": { stopAt: "limit", note: "하루 2장 한도 초과 → 예외가 나면 요청 전체가 rollback 돼요" },
      "409:RESERVATION_NOT_AVAILABLE": { stopAt: "festival", anchor: "raise ReservationNotAvailable", note: "예매할 수 없는 회차예요 (매진·기간 아님·취소된 축제)" },
      "409:INVALID_PERFORMANCE_STATUS": { stopAt: "decrease", note: "회차 상태 때문에 차감할 수 없어요" },
      "404:PERFORMANCE_NOT_FOUND": { stopAt: "pick", note: "해당 요일 회차가 없어요" },
      "404:FESTIVAL_NOT_FOUND": { stopAt: "festival", note: "축제가 없어요" },
      401: { stopAt: "auth", note: "로그인이 필요해요" },
    },
  },

  // ─────────────────────────────── 내 예매 목록
  "GET /v1/reservations/me": {
    title: "내 예매 목록",
    steps: [
      { id: "router", layer: "router", file: ROUTER, symbol: "get_my_reservations", anchor: "get_my_reservations(actor.user_id)", note: "토큰의 user_id로만 조회 → 남의 예매는 볼 수 없어요" },
      authStep,
      { id: "repo", layer: "repository", file: REPO, symbol: "SqlalchemyReservationRepository.find_by_user_id", anchor: "where(", note: "SELECT ... WHERE user_id = ?" },
    ],
    outcomes: { 200: { note: "예매가 없으면 404가 아니라 빈 목록(200)" } },
  },

  // ─────────────────────────────── 예매 취소
  "PATCH /v1/reservations/{id}/cancel": {
    title: "예매 취소",
    steps: [
      { id: "router", layer: "router", file: ROUTER, symbol: "cancel_reservation", anchor: "service.cancel_reservation(", note: "본인 또는 관리자만 취소 가능" },
      authStep,
      { id: "lock", layer: "service", file: SERVICE, symbol: "ReservationService.cancel_reservation", anchor: "_reservation_repo.lock(", note: "예매 행을 먼저 잠가요 (비관적 락)" },
      { id: "for_update", layer: "repository", file: REPO, symbol: "SqlalchemyReservationRepository.lock", anchor: "with_for_update()", note: "SELECT ... FOR UPDATE → 같은 예매의 다른 요청은 여기서 기다려요" },
      { id: "owner", layer: "service", file: SERVICE, symbol: "ReservationService.get_reservation", anchor: "reservation.user_id != user_id", note: "남의 예매면 403이 아니라 404 (존재 자체를 숨김)" },
      { id: "deadline", layer: "service", file: SERVICE, symbol: "ReservationService.cancel_reservation", anchor: "cancel_deadline_at", note: "종료된 공연 / 취소 마감 확인 (관리자는 공연 시작 전까지)" },
      { id: "cancel", layer: "domain", file: ENTITY, symbol: "Reservation.cancel", anchor: "ReservationStatus.CANCELED", note: "PENDING·CONFIRMED만 취소 가능 → CANCELED + 취소 시각 기록" },
      { id: "tickets", layer: "service", file: SERVICE, symbol: "ReservationService._cancel_tickets", anchor: "force_cancel", note: "발급된 티켓도 함께 취소" },
      { id: "restore", layer: "service", file: SERVICE, symbol: "ReservationService._restore_remaining", anchor: "increase_remaining", note: "회차 잔여 수량 복구 (취소·종료된 회차는 건너뜀)" },
      { id: "save", layer: "repository", file: REPO, symbol: "SqlalchemyReservationRepository.save", anchor: "flush()", note: "저장 → 요청이 끝나면 commit, 잠금 해제" },
    ],
    outcomes: {
      200: { note: "취소 완료 → 잔여 수량과 티켓까지 함께 정리됐어요" },
      "409:INVALID_RESERVATION_STATUS": { waitAt: "for_update", stopAt: "cancel", anchor: "raise InvalidReservationStatus", note: "이미 취소·만료된 예매예요 (동시 요청이었다면: 먼저 온 요청이 끝날 때까지 기다린 뒤 최신 상태를 읽고 409)" },
      "409:CANCEL_DEADLINE_VIOLATION": { stopAt: "deadline", anchor: "raise CancelDeadlineViolation", note: "취소 가능 기간이 지났어요" },
      404: { stopAt: "owner", anchor: "raise ReservationNotFound", note: "예매가 없거나 남의 예매예요" },
    },
  },

  // ─────────────────────────────── 입금 완료 시뮬레이션 → 확정 + 티켓 발급
  "POST /demo/reservations/{id}/confirm": {
    title: "입금 완료 → 예매 확정 (결제 웹훅 시뮬레이션)",
    steps: [
      { id: "demo", layer: "demo", file: DEMO, symbol: "demo_confirm", anchor: "confirm_reservation(", note: "실제로는 결제 웹훅이 DONE을 받은 뒤 이 메서드를 호출해야 해요 (결제 담당 연동 예정)" },
      { id: "lock", layer: "service", file: SERVICE, symbol: "ReservationService.confirm_reservation", anchor: "_reservation_repo.lock(", note: "예매 행 잠금 → 만료 작업(skip_locked)이 이 예매를 건너뛰어요" },
      { id: "idempotent", layer: "service", file: SERVICE, symbol: "ReservationService.confirm_reservation", anchor: "return reservation", note: "이미 확정이면 그대로 성공 (웹훅이 두 번 와도 안전)" },
      { id: "confirm", layer: "domain", file: ENTITY, symbol: "Reservation.confirm", anchor: "ReservationStatus.CONFIRMED", note: "PENDING이고 입금 기한 안이어야 CONFIRMED" },
      { id: "issue", layer: "service", file: SERVICE, symbol: "ReservationService._issue_tickets", anchor: "ticket.confirm(now)", note: "회차 × 수량만큼 티켓 발급 (양일권 2장 = 4장)" },
    ],
    outcomes: {
      200: { note: "확정 + 티켓 발급 → 같은 트랜잭션이라 발급이 실패하면 확정도 취소돼요" },
      409: { stopAt: "confirm", anchor: "raise", note: "PENDING이 아니거나 입금 기한이 지난 예매는 확정할 수 없어요" },
    },
  },

  // ─────────────────────────────── 만료 작업
  "POST /demo/reservations/{id}/expire": {
    title: "입금 기한 만료 (백그라운드 작업 1회 실행)",
    badge: "⏱ 서버에서는 1분마다 자동 실행",
    steps: [
      { id: "job", layer: "demo", file: "src/reservations/infrastructure/expire_job.py", symbol: "_loop", anchor: "run_expire_once()", note: "서버가 켜져 있는 동안 1분마다 돌아요 (데모에서는 버튼으로 1회 실행)" },
      { id: "find", layer: "repository", file: REPO, symbol: "SqlalchemyReservationRepository.find_overdue_pending", anchor: "skip_locked=True", note: "기한 지난 PENDING만 조회, 결제 확정 중(잠긴) 예매는 건너뜀" },
      { id: "expire", layer: "domain", file: ENTITY, symbol: "Reservation.expire", anchor: "ReservationStatus.EXPIRED", note: "PENDING → EXPIRED" },
      { id: "restore", layer: "service", file: SERVICE, symbol: "ReservationService._restore_remaining", anchor: "increase_remaining", note: "묶여 있던 좌석 반납" },
    ],
    outcomes: { 200: { note: "만료 처리 완료 → 좌석이 다시 예매 가능해져요" } },
  },

  // ─────────────────────────────── 관리자 목록
  "GET /v1/festivals/{id}/reservations": {
    title: "축제별 예매 목록 (관리자)",
    steps: [
      { id: "router", layer: "router", file: ROUTER, symbol: "list_festival_reservations", anchor: "_require_admin(actor)", note: "관리자 전용 API는 라우터에서 먼저 막아요" },
      { id: "admin", layer: "router", file: ROUTER, symbol: "_require_admin", anchor: "raise AdminPermissionDenied", note: "일반 회원이면 403" },
      { id: "filter", layer: "service", file: SERVICE, symbol: "ReservationService.list_festival_reservations", anchor: "TicketType.BOTH]", note: "토요일 보기 = SAT + 양일권(BOTH) 예매" },
      { id: "query", layer: "repository", file: REPO, symbol: "SqlalchemyReservationRepository.find_festival_reservation", anchor: "offset(", note: "필터 + 페이지네이션 (offset / limit)" },
    ],
    outcomes: {
      200: { note: "목록 + 전체 개수 → PageResponse로 응답" },
      403: { stopAt: "admin", anchor: "raise AdminPermissionDenied", note: "관리자만 볼 수 있어요" },
    },
  },

  // ─────────────────────────────── 내 티켓
  "GET /v1/tickets": {
    title: "내 티켓 목록",
    steps: [
      { id: "router", layer: "router", file: "src/tickets/presentation/routers/v1/router.py", symbol: "list_tickets", note: "일반 회원은 내 티켓만, 관리자는 전체 검색" },
      { id: "repo", layer: "repository", file: "src/tickets/infrastructure/repositories.py", symbol: "SqlAlchemyTicketRepository.find_all_by_user", anchor: "join(", note: "티켓 ↔ 예매를 JOIN해서 내 예매의 티켓만" },
    ],
    outcomes: { 200: { note: "확정된 예매의 티켓이 보여요" } },
  },

  // ─────────────────────────────── 회차 목록 (잔여 수량)
  "GET /v1/festivals/{id}/performances": {
    title: "회차 목록 (잔여 수량)",
    steps: [
      { id: "router", layer: "router", file: "src/performances/presentation/routers/v1/router.py", symbol: "list_performances", note: "축제의 회차와 잔여 수량 조회" },
    ],
    outcomes: { 200: { note: "잔여 수량이 실시간으로 반영돼요" } },
  },
};

export function findFlow(method, template) {
  return FLOWS[`${method} ${template}`] || null;
}

export function pickOutcome(flow, status, code) {
  if (!flow?.outcomes) return null;
  return flow.outcomes[`${status}:${code}`] || flow.outcomes[status] || null;
}
