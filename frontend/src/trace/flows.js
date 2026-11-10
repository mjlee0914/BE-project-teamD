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

const AUTH = "src/auth";
const AUTH_ROUTER = `${AUTH}/presentation/routers/v1/router.py`;
const AUTH_DEPS = `${AUTH}/presentation/dependencies.py`;
const AUTH_SERVICE = `${AUTH}/application/service.py`;
const AUTH_VERIFIER = `${AUTH}/infrastructure/credentials_verifier.py`;
const AUTH_JWT = `${AUTH}/infrastructure/security.py`;
const AUTH_REPO = `${AUTH}/infrastructure/repositories.py`;
const USER_ROUTER = "src/users/presentation/routers/v1/router.py";
const USER_SERVICE = "src/users/application/service.py";
const USER_ENTITY = "src/users/domain/user.py";
const USER_REPO = "src/users/infrastructure/repositories.py";
const FEST = "src/festivals";
const PAY = "src/payments";
const PAY_ROUTER = `${PAY}/presentation/routers/v1/router.py`;
const PAY_SERVICE = `${PAY}/application/service.py`;
const PAY_ENTITY = `${PAY}/domain/entities.py`;
const PAY_REPO = `${PAY}/infrastructure/sqlalchemy_repository.py`;
const PAY_ACCESS = `${PAY}/infrastructure/access_checker.py`;
const TOSS = `${PAY}/infrastructure/toss_service.py`;

// 로그인한 요청이 공통으로 지나는 곳 : Authorization 헤더의 JWT → 회원 조회 → 요청한 사람
const authStep = {
  id: "auth",
  layer: "auth",
  file: "src/wiring/actor.py",
  symbol: "build_current_actor",
  anchor: "is_admin=user.is_admin",
  note: "Authorization 헤더의 JWT를 검증해 user_id를 꺼내고, 회원을 조회해 관리자 여부를 채워요",
};
// 토큰 검증 3단계 (회원·결제 API가 쓰는 get_current_user)
const tokenSteps = [
  { id: "token", layer: "auth", file: AUTH_DEPS, symbol: "get_current_user", anchor: "authenticate_token(token)", note: "Authorization: Bearer 헤더에서 토큰을 꺼내 검증을 맡겨요 (없으면 401)" },
  { id: "decode", layer: "auth", file: AUTH_JWT, symbol: "JwtTokenProvider.decode_token", anchor: "jwt.decode(", note: "서명·만료·발급자·대상을 확인 → 위조되거나 만료된 토큰은 401" },
  { id: "blacklist", layer: "auth", file: AUTH_SERVICE, symbol: "AuthService.authenticate_token", anchor: "is_blacklisted(payload.jti)", note: "로그아웃된 토큰인지, 지금도 활성 회원인지 확인" },
];

export const FLOWS = {
  // ─────────────────────────────── 회원가입
  "POST /v1/users": {
    title: "회원가입",
    steps: [
      { id: "router", layer: "router", file: USER_ROUTER, symbol: "create_user", anchor: "service.signup(", note: "로그인 없이 호출할 수 있어요. 본문 모양이 다르면 여기 오기 전에 422" },
      { id: "validate", layer: "domain", file: USER_ENTITY, symbol: "User.create", anchor: "_validate_password(raw_password)", note: "비밀번호 형식 검사 (영문·숫자·특수문자 포함 8자 이상) → 해시하기 전에 먼저" },
      { id: "hash", layer: "domain", file: USER_ENTITY, symbol: "User.create", anchor: "hasher.hash(raw_password)", note: "비밀번호를 bcrypt로 해시 → DB에는 원문을 저장하지 않아요" },
      { id: "dup", layer: "service", file: USER_SERVICE, symbol: "UserService.signup", anchor: "find_by_email(user.email)", note: "정규화된 이메일·전화번호로 중복 확인" },
      { id: "save", layer: "repository", file: USER_REPO, symbol: "SqlAlchemyUserRepository.save", anchor: "flush()", note: "저장 → 동시에 같은 이메일로 가입해도 unique 제약이 막아요" },
    ],
    outcomes: {
      201: { note: "가입 완료 → 응답에는 password_hash가 빠져 있어요" },
      "409:EMAIL_ALREADY_EXISTS": { stopAt: "dup", anchor: "raise DuplicateEmail", note: "이미 가입된 이메일이에요" },
      "409:PHONE_ALREADY_EXISTS": { stopAt: "dup", anchor: "raise DuplicatePhone", note: "이미 등록된 전화번호예요" },
      "422:INVALID_PASSWORD": { stopAt: "validate", note: "비밀번호 형식이 맞지 않아요" },
      422: { stopAt: "validate", anchor: "return cls(", note: "이메일·이름·전화번호 형식이 맞지 않아요 (__post_init__에서 검증)" },
    },
  },

  // ─────────────────────────────── 로그인
  "POST /v1/auth/login": {
    title: "로그인 (JWT 발급)",
    steps: [
      { id: "router", layer: "router", file: AUTH_ROUTER, symbol: "login", anchor: "service.login(", note: "이메일과 비밀번호 원문을 서비스에 넘겨요 (비밀번호는 로그에 남기지 않음)" },
      { id: "service", layer: "service", file: AUTH_SERVICE, symbol: "AuthService.login", anchor: "verify_credentials(", note: "회원 확인을 먼저 하고, 통과하면 토큰을 만들어요" },
      { id: "find", layer: "auth", file: AUTH_VERIFIER, symbol: "RepositoryUserCredentialVerifier.verify_credentials", anchor: "find_by_email(", note: "이메일로 회원 조회" },
      { id: "hash", layer: "auth", file: AUTH_VERIFIER, symbol: "RepositoryUserCredentialVerifier.verify_credentials", anchor: "self._password_hasher.verify", note: "입력한 비밀번호와 저장된 bcrypt 해시 비교" },
      { id: "active", layer: "auth", file: AUTH_VERIFIER, symbol: "RepositoryUserCredentialVerifier.verify_credentials", anchor: "user.ensure_active()", note: "탈퇴한 회원이 아닌지 확인 (비밀번호가 맞은 뒤에만 상태를 알려 줌)" },
      { id: "jwt", layer: "auth", file: AUTH_JWT, symbol: "JwtTokenProvider.create_access_token", anchor: "token = jwt.encode(", note: "회원 ID(sub)·토큰 식별자(jti)·만료 시각을 넣어 서명한 JWT 발급" },
    ],
    outcomes: {
      200: { note: "토큰 발급 완료 → 이제 모든 요청의 Authorization 헤더에 이 토큰이 실려요" },
      401: { stopAt: "hash", anchor: "if not matched", note: "이메일 또는 비밀번호가 틀렸어요 (어느 쪽이 틀렸는지는 알려 주지 않음)" },
      403: { stopAt: "active", note: "탈퇴한 회원이에요" },
      422: { stopAt: "router", note: "이메일 형식이 맞지 않아요" },
    },
  },

  // ─────────────────────────────── 로그아웃
  "POST /v1/auth/logout": {
    title: "로그아웃 (토큰 차단)",
    steps: [
      { id: "router", layer: "router", file: AUTH_ROUTER, symbol: "logout", anchor: "service.logout(token)", note: "헤더의 토큰을 서비스에 넘겨요" },
      { id: "service", layer: "service", file: AUTH_SERVICE, symbol: "AuthService.logout", anchor: "_blacklist_repo.add(", note: "JWT는 서버가 지울 수 없어서, 토큰 식별자(jti)를 차단 목록에 올려요" },
      { id: "save", layer: "repository", file: AUTH_REPO, symbol: "SqlAlchemyTokenBlacklistRepository.add", anchor: "flush()", note: "차단 목록에 저장 → 이후 이 토큰으로 온 요청은 401" },
    ],
    outcomes: { 204: { note: "로그아웃 완료 → 같은 토큰은 더 이상 쓸 수 없어요" }, 401: { stopAt: "router", note: "이미 만료된 토큰이에요" } },
  },

  // ─────────────────────────────── 내 정보
  "GET /v1/users/me": {
    title: "내 정보 조회",
    steps: [
      { id: "router", layer: "router", file: USER_ROUTER, symbol: "get_user", anchor: "service.get_me(current.user_id)", note: "URL에 id가 없어요 → 토큰의 user_id만 쓰므로 남의 정보는 조회할 수 없어요" },
      ...tokenSteps,
      { id: "service", layer: "service", file: USER_SERVICE, symbol: "UserService.get_me", anchor: "user.ensure_active()", note: "회원 조회 후 탈퇴 여부 확인" },
    ],
    outcomes: { 200: { note: "내 정보 (password_hash는 응답에 없음)" }, 401: { stopAt: "decode", note: "토큰이 없거나 유효하지 않아요" } },
  },
  "PATCH /v1/users/me": {
    title: "내 정보 수정",
    steps: [
      { id: "router", layer: "router", file: USER_ROUTER, symbol: "patch_user", anchor: "service.update_profile(", note: "수정 대상은 항상 토큰 주인 본인 (이메일·권한은 못 바꿈)" },
      ...tokenSteps,
      { id: "domain", layer: "domain", file: USER_ENTITY, symbol: "User.update_profile", anchor: "self._validate_name(new_name)", note: "이름·전화번호 정규화 후 형식 검증 → 통과해야 반영" },
      { id: "dup", layer: "service", file: USER_SERVICE, symbol: "UserService.update_profile", anchor: "owner.id != user.id", note: "다른 회원이 쓰는 전화번호인지 확인 (내 번호 그대로면 통과)" },
      { id: "save", layer: "repository", file: USER_REPO, symbol: "SqlAlchemyUserRepository.save", anchor: "flush()", note: "저장" },
    ],
    outcomes: {
      200: { note: "수정 완료" },
      409: { stopAt: "dup", anchor: "raise DuplicatePhone", note: "이미 등록된 전화번호예요" },
      422: { stopAt: "domain", note: "이름 또는 전화번호 형식이 맞지 않아요" },
      401: { stopAt: "decode", note: "토큰이 없거나 유효하지 않아요" },
    },
  },

  // ─────────────────────────────── 축제 목록
  "GET /v1/festivals": {
    title: "축제 목록",
    steps: [
      { id: "router", layer: "router", file: `${FEST}/presentation/routers/v1/router.py`, symbol: "list_festivals", anchor: "service.list_festivals(page, size)", note: "page·size를 받아요 (로그인 없이 조회 가능)" },
      { id: "service", layer: "service", file: `${FEST}/application/service.py`, symbol: "FestivalService.list_festivals", anchor: "offset = (page - 1) * size", note: "몇 개를 건너뛸지 계산" },
      { id: "repo", layer: "repository", file: `${FEST}/infrastructure/repositories.py`, symbol: "SqlAlchemyFestivalRepository.find_all", anchor: ".offset(offset)", note: "SELECT ... OFFSET / LIMIT" },
    ],
    outcomes: { 200: { note: "축제 목록 + 전체 개수 → PageResponse로 응답" } },
  },


  // ─────────────────────────────── 결제 승인 (토스 서버 호출)
  "POST /v1/payments/{id}/approve": {
    title: "결제 승인 (토스페이먼츠)",
    steps: [
      { id: "router", layer: "router", file: PAY_ROUTER, symbol: "approve_payment", anchor: "service.approve(", note: "결제창에서 받은 paymentKey와 금액을 서비스에 넘겨요" },
      { id: "owner", layer: "auth", file: PAY_ROUTER, symbol: "get_owned_payment", anchor: "access.ensure_owner(", note: "토큰의 회원이 이 결제의 예매 주인인지 먼저 확인" },
      { id: "access", layer: "repository", file: PAY_ACCESS, symbol: "SQLAlchemyPaymentAccessChecker.ensure_owner", anchor: "owner_id != user_id", note: "예매의 user_id와 비교 → 남의 결제면 403" },
      { id: "lock", layer: "service", file: PAY_SERVICE, symbol: "PaymentService.approve", anchor: "lock_reservation(", note: "예매 행을 잠가요 → 같은 예매의 결제 요청이 동시에 와도 하나씩 처리" },
      { id: "for_update", layer: "repository", file: PAY_REPO, symbol: "SQLAlchemyPaymentRepository.lock_reservation", anchor: "with_for_update()", note: "SELECT ... FOR UPDATE" },
      { id: "check", layer: "domain", file: PAY_ENTITY, symbol: "Payment.ensure_approvable", anchor: "amount != self.amount", note: "브라우저가 보낸 금액이 서버에 저장된 금액과 같은지 확인 (금액 조작 방지)" },
      { id: "start", layer: "domain", file: PAY_ENTITY, symbol: "Payment.start_approval", anchor: "PaymentStatus.IN_PROGRESS", note: "승인 진행 중(IN_PROGRESS)으로 먼저 기록 → 결과가 불분명해도 흔적이 남아요" },
      { id: "call", layer: "service", file: PAY_SERVICE, symbol: "PaymentService.approve", anchor: "self.processor.approve(", note: "여기서 토스 서버로 HTTP 요청이 나가요" },
      { id: "toss", layer: "external", file: TOSS, symbol: "TossPaymentProcessor.approve", anchor: '"/confirm"', note: "POST https://api.tosspayments.com/v1/payments/confirm (paymentKey + 서버가 보관한 주문번호·금액)" },
      { id: "verify", layer: "external", file: TOSS, symbol: "TossPaymentProcessor.approve", anchor: 'data.get("paymentKey") != payment_key', note: "토스 응답의 결제 키·주문번호·금액이 보낸 값과 같은지 다시 확인" },
      { id: "apply", layer: "domain", file: PAY_ENTITY, symbol: "Payment.approve", anchor: "self.status = status", note: "가상계좌 = 입금 대기(WAITING_FOR_DEPOSIT), 카드 = 결제 완료(DONE)" },
      { id: "save", layer: "repository", file: PAY_REPO, symbol: "SQLAlchemyPaymentRepository.save", anchor: "_apply_changes(model, payment)", note: "승인 결과 저장" },
    ],
    outcomes: {
      200: { note: "승인 완료 → 가상계좌는 입금을 기다리고, 카드는 바로 결제 완료예요" },
      502: { stopAt: "toss", note: "토스 서버가 승인을 거절했거나 응답을 확인하지 못했어요 (진행 기록은 남김)" },
      403: { stopAt: "access", anchor: "raise ForbiddenException", note: "본인의 예매에 연결된 결제만 승인할 수 있어요" },
      404: { stopAt: "owner", note: "결제를 찾을 수 없어요" },
      409: { stopAt: "start", note: "같은 예매에 이미 진행 중이거나 완료된 결제가 있어요" },
      422: { stopAt: "check", anchor: "raise InvalidAmountException", note: "금액이 서버에 저장된 값과 다르거나 승인할 수 없는 상태예요" },
      401: { stopAt: "owner", note: "로그인이 필요해요" },
    },
  },

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
