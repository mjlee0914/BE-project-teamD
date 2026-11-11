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

// 추가 도메인 경로 (#167)
const PERF_ROUTER = "src/performances/presentation/routers/v1/router.py";
const PERF_SERVICE = "src/performances/application/service.py";
const PERF_REPO = "src/performances/infrastructure/repositories.py";
const FEST_ROUTER = `${FEST}/presentation/routers/v1/router.py`;
const FEST_SERVICE = `${FEST}/application/service.py`;
const FEST_ENTITY = `${FEST}/domain/festival.py`;
const FEST_REPO = `${FEST}/infrastructure/repositories.py`;
const TK = "src/tickets";
const TK_ROUTER = `${TK}/presentation/routers/v1/router.py`;
const TK_SERVICE = `${TK}/application/service.py`;
const TK_ENTITY = `${TK}/domain/ticket.py`;
const TK_REPO = `${TK}/infrastructure/repositories.py`;

// 결제 단건 API가 공통으로 지나는 소유권 검사 (OwnedPayment)
const ownedPaymentSteps = [
  { id: "owned", layer: "router", file: PAY_ROUTER, symbol: "get_owned_payment", anchor: "service.get_payment(payment_id)", note: "결제를 먼저 읽고 (없으면 404)" },
  { id: "owner", layer: "repository", file: PAY_ACCESS, symbol: "SQLAlchemyPaymentAccessChecker.ensure_owner", anchor: "raise ForbiddenException", note: "결제가 연결된 예매의 주인이 나인지 확인 (아니면 403)" },
];
// 관리자 검사 (도메인마다 라우터에 _require_admin이 있음)
const adminStep = (file) => ({ id: "admin", layer: "router", file, symbol: "_require_admin", anchor: "if not actor.is_admin", note: "관리자 전용 API는 라우터에서 먼저 막아요 (일반 회원이면 403)" });
const adminOutcome = { 403: { stopAt: "admin", note: "관리자만 이용할 수 있어요" } };

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
      { id: "tickets", layer: "service", file: TK_SERVICE, symbol: "TicketService.cancel_all_by_reservation", anchor: "ticket.force_cancel(now)", note: "발급된 티켓도 함께 취소하고 회차 잔여 수량을 복구" },
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
  // ─────────────────────────────── 비밀번호 변경 · 회원 탈퇴
  "PATCH /v1/users/me/password": {
    title: "비밀번호 변경",
    steps: [
      { id: "router", layer: "router", file: USER_ROUTER, symbol: "change_password", anchor: "service.change_password(", note: "대상은 항상 토큰 주인 본인" },
      ...tokenSteps,
      { id: "verify", layer: "domain", file: USER_ENTITY, symbol: "User.change_password", anchor: "hasher.verify(old_password", note: "기존 비밀번호를 저장된 해시와 비교 (본인 확인)" },
      { id: "reuse", layer: "domain", file: USER_ENTITY, symbol: "User.change_password", anchor: "old_password == new_password", note: "같은 비밀번호로 바꾸는 건 막아요" },
      { id: "hash", layer: "domain", file: USER_ENTITY, symbol: "User.change_password", anchor: "self.password_hash = hasher.hash(new_password)", note: "형식 검사 통과 후 새 비밀번호를 해시" },
      { id: "save", layer: "repository", file: USER_REPO, symbol: "SqlAlchemyUserRepository.save", anchor: "flush()", note: "저장" },
    ],
    outcomes: {
      200: { note: "비밀번호 변경 완료" },
      422: { stopAt: "verify", anchor: "raise InvalidPassword(", note: "기존 비밀번호가 틀렸거나, 새 비밀번호가 같거나 형식이 맞지 않아요" },
      403: { stopAt: "verify", anchor: "raise InactiveUser(", note: "탈퇴한 회원이에요" },
      401: { stopAt: "decode", note: "토큰이 없거나 유효하지 않아요" },
    },
  },
  "DELETE /v1/users/me": {
    title: "회원 탈퇴",
    steps: [
      { id: "router", layer: "router", file: USER_ROUTER, symbol: "delete_user", anchor: "service.withdraw(", note: "탈퇴 대상과 요청자가 모두 토큰 주인" },
      ...tokenSteps,
      { id: "domain", layer: "domain", file: USER_ENTITY, symbol: "User.withdraw", anchor: "self.status = UserStatus.WITHDRAWN", note: "행을 지우지 않고 상태만 WITHDRAWN으로 (소프트 삭제)" },
      { id: "active", layer: "service", file: USER_SERVICE, symbol: "UserService.withdraw", anchor: "has_active_reservation(", note: "진행 중인 예매가 있으면 탈퇴할 수 없어요" },
      { id: "save", layer: "repository", file: USER_REPO, symbol: "SqlAlchemyUserRepository.save", anchor: "flush()", note: "저장 → 이후 이 계정으로는 로그인할 수 없어요" },
    ],
    outcomes: {
      200: { note: "탈퇴 완료" },
      409: { stopAt: "active", anchor: "raise ActiveReservationExists", note: "진행 중인 예매가 있거나 이미 탈퇴한 회원이에요" },
      401: { stopAt: "decode", note: "토큰이 없거나 유효하지 않아요" },
    },
  },

  // ─────────────────────────────── 축제 (관리자)
  "POST /v1/festivals": {
    title: "축제 생성 (관리자)",
    steps: [
      { id: "router", layer: "router", file: FEST_ROUTER, symbol: "create_festival", anchor: "_require_admin(actor)", note: "관리자만 만들 수 있어요" },
      authStep,
      adminStep(FEST_ROUTER),
      { id: "overlap", layer: "service", file: FEST_SERVICE, symbol: "FestivalService.create_festival", anchor: "exists_overlapping(", note: "기간이 겹치는 축제가 있는지 확인" },
      { id: "save", layer: "repository", file: FEST_REPO, symbol: "SqlAlchemyFestivalRepository.save", note: "저장" },
    ],
    outcomes: {
      201: { note: "축제 생성 완료" },
      ...adminOutcome,
      409: { stopAt: "overlap", anchor: "raise FestivalPeriodOverlap", note: "기간이 겹치는 축제가 있어요" },
      422: { stopAt: "router", note: "이름·장소·기간 형식이 맞지 않아요" },
    },
  },
  "PATCH /v1/festivals/{id}": {
    title: "축제 수정 (관리자)",
    steps: [
      { id: "router", layer: "router", file: FEST_ROUTER, symbol: "update_festival", anchor: "_require_admin(actor)", note: "보낸 필드만 바뀌어요" },
      authStep,
      adminStep(FEST_ROUTER),
      { id: "domain", layer: "service", file: FEST_SERVICE, symbol: "FestivalService.update_festival", anchor: "festival.change_period(", note: "기존 값 + 바뀐 값을 합쳐서 검증" },
      { id: "overlap", layer: "service", file: FEST_SERVICE, symbol: "FestivalService.update_festival", anchor: "exists_overlapping(", note: "바뀐 기간이 다른 축제와 겹치는지 확인" },
      { id: "save", layer: "repository", file: FEST_REPO, symbol: "SqlAlchemyFestivalRepository.save", note: "저장" },
    ],
    outcomes: {
      200: { note: "축제 수정 완료" },
      ...adminOutcome,
      404: { stopAt: "domain", anchor: "self.get_festival(festival_id)", note: "없는 축제예요" },
      409: { stopAt: "overlap", anchor: "raise FestivalPeriodOverlap", note: "기간이 겹치거나 취소된 축제예요" },
      422: { stopAt: "domain", note: "기간 형식이 맞지 않아요" },
    },
  },
  "PATCH /v1/festivals/{id}/cancel": {
    title: "축제 취소 (관리자)",
    steps: [
      { id: "router", layer: "router", file: FEST_ROUTER, symbol: "cancel_festival", anchor: "_require_admin(actor)", note: "관리자만 취소할 수 있어요" },
      authStep,
      adminStep(FEST_ROUTER),
      { id: "perf", layer: "service", file: FEST_SERVICE, symbol: "FestivalService.cancel_festival", anchor: "exists_uncanceled_by_festival(", note: "아직 취소되지 않은 회차가 있으면 축제를 먼저 취소할 수 없어요" },
      { id: "domain", layer: "domain", file: FEST_ENTITY, symbol: "Festival.cancel", anchor: "self.canceled_at = now", note: "취소 시각 기록" },
      { id: "save", layer: "repository", file: FEST_REPO, symbol: "SqlAlchemyFestivalRepository.save", note: "저장" },
    ],
    outcomes: {
      200: { note: "축제 취소 완료" },
      ...adminOutcome,
      409: { stopAt: "perf", anchor: "raise FestivalHasUncanceledPerformances", note: "취소되지 않은 회차가 있거나 이미 취소된 축제예요" },
    },
  },

  // ─────────────────────────────── 공연(회차)
  "GET /v1/performances/{id}": {
    title: "회차 상세",
    steps: [
      { id: "router", layer: "router", file: PERF_ROUTER, symbol: "get_performance", anchor: "service.get_performance(", note: "로그인 없이 조회할 수 있어요" },
      { id: "service", layer: "service", file: PERF_SERVICE, symbol: "PerformanceService.get_performance", anchor: "find_by_id(", note: "id로 회차 조회" },
    ],
    outcomes: { 200: { note: "회차 정보 (예매 기간·취소 마감 포함)" }, 404: { stopAt: "service", anchor: "raise PerformanceNotFound", note: "없는 회차예요" } },
  },
  "GET /v1/performances/{id}/availability": {
    title: "회차 예매 가능 여부",
    steps: [
      { id: "router", layer: "router", file: PERF_ROUTER, symbol: "get_availability", anchor: "service.get_availability(", note: "잔여 수량과 예매 가능 여부를 함께 돌려줘요" },
      { id: "service", layer: "service", file: PERF_SERVICE, symbol: "PerformanceService.get_availability", anchor: "is_bookable(now_utc())", note: "지금 시각 기준으로 판단" },
      { id: "domain", layer: "domain", file: PERF, symbol: "Performance.is_bookable", note: "상태가 OPEN이고, 예매 기간 안이고, 잔여가 있어야 예매 가능" },
    ],
    outcomes: { 200: { note: "is_bookable + remaining_count" }, 404: { stopAt: "service", note: "없는 회차예요" } },
  },
  "POST /v1/festivals/{id}/performances": {
    title: "회차 생성 (관리자)",
    steps: [
      { id: "router", layer: "router", file: PERF_ROUTER, symbol: "create_performance", anchor: "_require_admin(actor)", note: "관리자만 만들 수 있어요" },
      authStep,
      adminStep(PERF_ROUTER),
      { id: "festival", layer: "service", file: PERF_SERVICE, symbol: "PerformanceService.create_performance", anchor: "festival.ensure_not_canceled()", note: "축제가 있고 취소되지 않았는지 확인" },
      { id: "dup", layer: "service", file: PERF_SERVICE, symbol: "PerformanceService.create_performance", anchor: "exists_duplicated_title(", note: "같은 축제 안에 같은 제목의 회차가 있는지 확인" },
      { id: "save", layer: "repository", file: PERF_REPO, symbol: "SqlAlchemyPerformanceRepository.save", note: "저장 (잔여 수량 = 수용 인원)" },
    ],
    outcomes: {
      201: { note: "회차 생성 완료 (상태 SCHEDULED)" },
      ...adminOutcome,
      404: { stopAt: "festival", anchor: "raise FestivalNotFound", note: "없는 축제예요" },
      409: { stopAt: "dup", anchor: "raise PerformanceTitleDuplicated", note: "같은 제목의 회차가 있거나 취소된 축제예요" },
      422: { stopAt: "router", note: "시각 순서나 수용 인원·가격이 맞지 않아요" },
    },
  },
  "PATCH /v1/performances/{id}": {
    title: "회차 수정 (관리자)",
    steps: [
      { id: "router", layer: "router", file: PERF_ROUTER, symbol: "update_performance", anchor: "_require_admin(actor)", note: "시각 4개와 수용 인원만 바꿀 수 있어요" },
      authStep,
      adminStep(PERF_ROUTER),
      { id: "schedule", layer: "domain", file: PERF, symbol: "Performance.change_schedule", note: "기존 값 + 바뀐 값을 합쳐 시각 순서 검증" },
      { id: "capacity", layer: "domain", file: PERF, symbol: "Performance.change_capacity", note: "이미 팔린 수보다 적게 줄일 수 없어요" },
      { id: "save", layer: "repository", file: PERF_REPO, symbol: "SqlAlchemyPerformanceRepository.save", note: "저장" },
    ],
    outcomes: {
      200: { note: "회차 수정 완료" },
      ...adminOutcome,
      404: { stopAt: "router", note: "없는 회차예요" },
      409: { stopAt: "schedule", note: "지금 상태에서는 수정할 수 없어요" },
      422: { stopAt: "schedule", note: "시각 순서나 수용 인원이 맞지 않아요" },
    },
  },
  "PATCH /v1/performances/{id}/open": {
    title: "회차 예매 오픈 (관리자)",
    steps: [
      { id: "router", layer: "router", file: PERF_ROUTER, symbol: "open_performance", anchor: "_require_admin(actor)", note: "관리자만 오픈할 수 있어요" },
      authStep,
      adminStep(PERF_ROUTER),
      { id: "domain", layer: "domain", file: PERF, symbol: "Performance.open", anchor: "self.status = PerformanceStatus.OPEN", note: "SCHEDULED → OPEN" },
      { id: "save", layer: "repository", file: PERF_REPO, symbol: "SqlAlchemyPerformanceRepository.save", note: "저장 → 이제 예매할 수 있어요" },
    ],
    outcomes: { 200: { note: "예매 오픈" }, ...adminOutcome, 409: { stopAt: "domain", anchor: "raise InvalidPerformanceStatus", note: "예매 시작 전(SCHEDULED) 회차만 오픈할 수 있어요" } },
  },
  "PATCH /v1/performances/{id}/complete": {
    title: "회차 종료 처리 (관리자)",
    steps: [
      { id: "router", layer: "router", file: PERF_ROUTER, symbol: "complete_performance", anchor: "_require_admin(actor)", note: "관리자만 종료 처리할 수 있어요" },
      authStep,
      adminStep(PERF_ROUTER),
      { id: "domain", layer: "domain", file: PERF, symbol: "Performance.complete", anchor: "if now < self.ends_at", note: "OPEN·SOLD_OUT이고 공연 종료 시각이 지났을 때만 COMPLETED" },
      { id: "save", layer: "repository", file: PERF_REPO, symbol: "SqlAlchemyPerformanceRepository.save", note: "저장" },
    ],
    outcomes: { 200: { note: "종료 처리 완료" }, ...adminOutcome, 409: { stopAt: "domain", anchor: "raise InvalidPerformanceStatus", note: "아직 공연이 끝나지 않았거나 종료할 수 없는 상태예요" } },
  },
  "PATCH /v1/performances/{id}/cancel": {
    title: "회차 취소 (관리자)",
    steps: [
      { id: "router", layer: "router", file: PERF_ROUTER, symbol: "cancel_performance", anchor: "_require_admin(actor)", note: "관리자만 취소할 수 있어요" },
      authStep,
      adminStep(PERF_ROUTER),
      { id: "domain", layer: "domain", file: PERF, symbol: "Performance.cancel", anchor: "self.status = PerformanceStatus.CANCELED", note: "이미 취소·종료된 회차는 취소할 수 없어요" },
      { id: "cascade", layer: "service", file: PERF_SERVICE, symbol: "PerformanceService.cancel_performance", anchor: "cancel_by_performance(", note: "이 회차의 예매와 티켓도 함께 취소" },
      { id: "res", layer: "service", file: SERVICE, symbol: "ReservationService.cancel_by_performance", note: "예매를 취소하고 티켓 서비스가 티켓을 함께 취소" },
    ],
    outcomes: { 200: { note: "회차 취소 → 관련 예매·티켓도 취소됐어요" }, ...adminOutcome, 409: { stopAt: "domain", anchor: "raise InvalidPerformanceStatus", note: "이미 취소됐거나 종료된 회차예요" } },
  },

  // ─────────────────────────────── 예매 상세
  "GET /v1/reservations/{id}": {
    title: "예매 상세",
    steps: [
      { id: "router", layer: "router", file: ROUTER, symbol: "get_reservation", anchor: "service.get_reservation(", note: "user_id와 관리자 여부를 함께 넘겨요" },
      authStep,
      { id: "service", layer: "service", file: SERVICE, symbol: "ReservationService.get_reservation", anchor: "if not is_admin and reservation.user_id != user_id", note: "본인 예매이거나 관리자일 때만 → 남의 예매는 404로 존재를 숨겨요" },
      { id: "repo", layer: "repository", file: REPO, symbol: "SqlalchemyReservationRepository.find_by_id", note: "id로 예매 조회" },
    ],
    outcomes: { 200: { note: "예매 상세 (금액·할인·처리 시각)" }, 404: { stopAt: "service", anchor: "raise ReservationNotFound", note: "없거나 남의 예매예요" } },
  },

  // ─────────────────────────────── 결제
  "POST /v1/payments": {
    title: "결제 건 생성",
    steps: [
      { id: "router", layer: "router", file: PAY_ROUTER, symbol: "create_payment", anchor: "service.create(", note: "금액·주문번호는 서버가 예매에서 정해요 (클라이언트 값을 믿지 않음)" },
      ...tokenSteps,
      { id: "lock", layer: "service", file: PAY_SERVICE, symbol: "PaymentService.create", anchor: "lock_reservation(reservation_id)", note: "같은 예매의 결제 요청을 줄 세워요" },
      { id: "payable", layer: "service", file: PAY_SERVICE, symbol: "PaymentService.create", anchor: "_validate_reservation_payable(context)", note: "입금 대기 중인 내 예매인지 확인" },
      { id: "attempt", layer: "service", file: PAY_SERVICE, symbol: "PaymentService.create", anchor: "raise PaymentAttemptConflict", note: "진행 중인 결제가 있으면 새로 만들지 않아요" },
      { id: "save", layer: "repository", file: PAY_REPO, symbol: "SQLAlchemyPaymentRepository.save", note: "READY 상태로 저장 → 이 값으로 토스 결제창을 열어요" },
    ],
    outcomes: {
      201: { note: "결제 건 생성 → 토스 결제창으로 이동" },
      409: { stopAt: "attempt", note: "이미 진행 중인 결제가 있거나 결제할 수 없는 예매예요" },
      403: { stopAt: "payable", note: "내 예매가 아니에요" },
      404: { stopAt: "payable", note: "없는 예매예요" },
    },
  },
  "GET /v1/payments/{id}": {
    title: "결제 단건 조회",
    steps: [
      { id: "router", layer: "router", file: PAY_ROUTER, symbol: "get_payment", note: "결제 정보를 응답 모양으로 바꿔요" },
      ...tokenSteps,
      ...ownedPaymentSteps,
      { id: "repo", layer: "repository", file: PAY_REPO, symbol: "SQLAlchemyPaymentRepository.find_by_id", note: "id로 결제 조회" },
    ],
    outcomes: { 200: { note: "결제 상세" }, 403: { stopAt: "owner", note: "내 예매의 결제가 아니에요" }, 404: { stopAt: "owned", note: "없는 결제예요" } },
  },
  "POST /v1/payments/{id}/reconcile": {
    title: "결제 상태 재확인",
    steps: [
      { id: "router", layer: "router", file: PAY_ROUTER, symbol: "reconcile_payment", anchor: "service.reconcile(", note: "토스 서버에 이 결제의 최신 상태를 다시 물어봐요" },
      ...tokenSteps,
      ...ownedPaymentSteps,
      { id: "lock", layer: "service", file: PAY_SERVICE, symbol: "PaymentService.reconcile", anchor: "lock_reservation(", note: "같은 예매의 결제 요청을 줄 세워요" },
      { id: "toss", layer: "service", file: TOSS, symbol: "TossPaymentProcessor.retrieve", note: "토스 결제 조회 API 호출" },
      { id: "settle", layer: "service", file: PAY_SERVICE, symbol: "PaymentService.reconcile", anchor: "return await self.settle(payment)", note: "토스 결과로 결제 상태를 맞추고, 완료됐으면 예매도 확정" },
    ],
    outcomes: {
      200: { note: "토스와 상태를 맞췄어요" },
      404: { stopAt: "lock", anchor: "raise PaymentKeyNotFoundException", note: "결제창을 완료하지 않아 토스에 조회할 결제 키가 없어요" },
      409: { stopAt: "toss", note: "토스 결제 정보가 이 결제와 맞지 않아요" },
      502: { stopAt: "toss", note: "토스 서버와 통신하지 못했어요" },
      403: { stopAt: "owner", note: "내 예매의 결제가 아니에요" },
    },
  },
  "POST /v1/payments/{id}/cancel": {
    title: "결제 취소 (환불)",
    steps: [
      { id: "router", layer: "router", file: PAY_ROUTER, symbol: "cancel_payment", anchor: "service.cancel(", note: "취소 사유와 (가상계좌면) 환불 계좌를 받아요" },
      ...tokenSteps,
      ...ownedPaymentSteps,
      { id: "lock", layer: "service", file: PAY_SERVICE, symbol: "PaymentService.cancel", anchor: "lock_reservation(", note: "같은 예매의 결제 요청을 줄 세워요" },
      { id: "reservation", layer: "service", file: PAY_SERVICE, symbol: "PaymentService.cancel", anchor: "_cancel_reservation(payment)", note: "토스 호출 전에 예매·티켓 취소와 잔여 수량 복구를 먼저 확정" },
      { id: "toss", layer: "service", file: TOSS, symbol: "TossPaymentProcessor.cancel", note: "토스 결제 취소 API 호출 (환불)" },
    ],
    outcomes: {
      200: { note: "결제 취소 → 예매·티켓도 취소됐어요" },
      409: { stopAt: "reservation", note: "취소 마감이 지났거나 취소할 수 없는 결제예요" },
      422: { stopAt: "router", note: "가상계좌 환불에는 환불 계좌가 필요해요" },
      502: { stopAt: "toss", note: "토스 서버와 통신하지 못했어요" },
      403: { stopAt: "owner", note: "내 예매의 결제가 아니에요" },
    },
  },

  // ─────────────────────────────── 티켓
  "GET /v1/tickets/{id}": {
    title: "티켓 상세",
    steps: [
      { id: "router", layer: "router", file: TK_ROUTER, symbol: "get_my_ticket", anchor: "service.get_my_ticket(", note: "토큰의 user_id로 내 티켓만 조회" },
      authStep,
      { id: "repo", layer: "repository", file: TK_REPO, symbol: "SqlAlchemyTicketRepository.find_by_id_for_user", anchor: "ReservationModel.user_id == user_id", note: "티켓 ↔ 예매를 JOIN해서 내 예매의 티켓인지 확인" },
      { id: "service", layer: "service", file: TK_SERVICE, symbol: "TicketService.get_my_ticket", anchor: "raise TicketNotFound", note: "없거나 남의 티켓이면 404 (존재를 숨김)" },
    ],
    outcomes: { 200: { note: "티켓 상세 (입장 코드 포함)" }, 404: { stopAt: "service", anchor: "raise TicketNotFound", note: "없거나 남의 티켓이에요" } },
  },
  "PATCH /v1/tickets/{id}/cancel": {
    title: "티켓 단일 취소",
    steps: [
      { id: "router", layer: "router", file: TK_ROUTER, symbol: "cancel_ticket", anchor: "service.cancel_ticket(", note: "응답에 함께 취소된 티켓 id가 모두 담겨요" },
      authStep,
      { id: "mine", layer: "service", file: TK_SERVICE, symbol: "TicketService.cancel_ticket", anchor: "self.get_my_ticket(ticket_id, user_id)", note: "내 티켓인지 확인 (아니면 404)" },
      { id: "lock", layer: "service", file: TK_SERVICE, symbol: "TicketService.cancel_ticket", anchor: "_reservation_repo.lock(", note: "같은 예매를 다루는 요청을 줄 세워요" },
      { id: "pick", layer: "service", file: TK_SERVICE, symbol: "TicketService._pick_cancel_targets", note: "토·일권은 누른 1장, 양일권은 토·일 한 쌍" },
      { id: "domain", layer: "domain", file: TK_ENTITY, symbol: "Ticket.cancel", anchor: "if now > self.cancel_deadline_at", note: "끝난 티켓이거나 취소 마감이 지났으면 409" },
      { id: "restore", layer: "service", file: TK_SERVICE, symbol: "TicketService._cancel_targets", anchor: "_restore_seats(", note: "취소한 장마다 그 회차 잔여 수량 +1" },
      { id: "reservation", layer: "service", file: TK_SERVICE, symbol: "TicketService._cancel_reservation_if_all_canceled", note: "티켓이 전부 취소되면 예매도 CANCELED" },
    ],
    outcomes: {
      200: { note: "티켓 취소 완료" },
      404: { stopAt: "mine", note: "없거나 남의 티켓이에요" },
      409: { stopAt: "domain", anchor: "raise TicketNotCancelable(", note: "이미 끝난 티켓이거나 취소 마감이 지났어요" },
    },
  },
  "POST /v1/tickets/enter": {
    title: "입장 처리 (관리자)",
    steps: [
      { id: "router", layer: "router", file: TK_ROUTER, symbol: "enter_ticket", anchor: "_require_admin(actor)", note: "현장 스태프(관리자)만 입장 처리" },
      authStep,
      adminStep(TK_ROUTER),
      { id: "find", layer: "service", file: TK_SERVICE, symbol: "TicketService.enter_ticket", anchor: "find_by_code(ticket_code)", note: "입장 코드(UUID)로 티켓 조회" },
      { id: "domain", layer: "domain", file: TK_ENTITY, symbol: "Ticket.enter", anchor: "self.status = TicketStatus.USED", note: "발급된 티켓이고, 공연 당일이고, 공연이 끝나기 전이어야 해요" },
      { id: "save", layer: "repository", file: TK_REPO, symbol: "SqlAlchemyTicketRepository.save", note: "USED로 저장" },
    ],
    outcomes: {
      200: { note: "입장 완료 (USED)" },
      ...adminOutcome,
      404: { stopAt: "find", anchor: "raise TicketNotFound", note: "없는 입장 코드예요" },
      409: { stopAt: "domain", anchor: "raise TicketNotEnterable(", note: "발급된 티켓이 아니거나 공연 당일이 아니에요" },
    },
  },
  "GET /v1/tickets/entry-status": {
    title: "회차별 입장 현황 (관리자)",
    steps: [
      { id: "router", layer: "router", file: TK_ROUTER, symbol: "get_entry_status", anchor: "_require_admin(actor)", note: "관리자만 볼 수 있어요" },
      authStep,
      adminStep(TK_ROUTER),
      { id: "repo", layer: "repository", file: TK_REPO, symbol: "SqlAlchemyTicketRepository.count_by_status", note: "회차의 티켓을 상태별로 GROUP BY 해서 개수를 세요" },
    ],
    outcomes: { 200: { note: "상태별 티켓 수 (없는 상태는 0)" }, ...adminOutcome },
  },
};

export function findFlow(method, template) {
  return FLOWS[`${method} ${template}`] || null;
}

export function pickOutcome(flow, status, code) {
  if (!flow?.outcomes) return null;
  return flow.outcomes[`${status}:${code}`] || flow.outcomes[status] || null;
}
