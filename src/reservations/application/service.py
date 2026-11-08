"""
# application/service.py
예매 유스케이스(사용자가 하려는 일 하나)를 처리하는 파일
    - 저장소에서 필요한 데이터를 모으고, domain의 규칙에 넘기고, 결과를 저장한다
    - "어떻게 판단하는가"(규칙)는 domain이 알고, 여기는 "어떤 순서로 하는가"만 안다
      ex) 금액 계산·상태·만료 시각 → Reservation.create() / 날짜별 한도 → check_daily_limit()

# 왜 축제·공연 저장소를 직접 import 하나
- 예매에 필요한 축제 정보(존재 여부, 상태, 이름·장소)와 공연 정보(회차, 가격, 잔여 수량)는
  각자의 도메인이 관리하는 데이터
- 예매 저장소에 같은 조회 메서드를 또 만들면 같은 테이블을 읽는 코드가 두 군데 생김
  → 팀 결정: 따로 만들지 않고 각 도메인의 저장소를 그대로 가져와 사용

# 예매 생성 흐름 (create_reservation)
① 축제 조회        → 없으면 404
② 축제 상태 확인   → 취소·종료면 409
③ 회차 조회·선택   → 티켓 종류(SAT/SUN/BOTH)에 맞는 요일의 회차만 고름
④ 회차 예매 가능   → 오픈 전, 매진, 예매 기간이 아니면 409
⑤ 날짜별 한도 검사 → 같은 축제의 기존 예매 + 신규 예매가 하루 2장을 넘으면 422
⑥ 1장 가격 계산    → 고른 회차 가격의 합 (양일권 = 토 + 일)
⑦ 잔여 수량 차감   → 고른 회차마다 quantity만큼 줄이고 저장
⑧ 예매 생성·저장   → Reservation.create()로 만들고 저장한 결과를 반환

# commit은 여기서 하지 않는다
- 저장소는 flush까지만 하고, commit은 요청 단위 세션에서 처리
- 중간에 예외가 나면 세션이 rollback 되므로 ⑦에서 줄인 잔여 수량도 함께 취소됨

# 공연 도메인에 의존하는 부분 (PR #95, #93)
- PerformanceRepository.count_by_festival / find_all_by_festival / save : 추상 메서드 정의됨, 구현체는 공연 담당 작업 예정
- Performance.decrease_remaining : 구현됨 (OPEN이 아니거나 잔여보다 많으면 예외, 0이 되면 SOLD_OUT)
- PR #95가 dev에 머지되기 전에는 이 파일을 import하면 PerformanceRepository가 없어 ImportError가 남
"""

# 표준 라이브러리 : 현재 시각(UTC)과 한국 시간대 변환
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

# 축제 도메인 : 축제 조회, 축제 상태 Enum, 축제가 없을 때 예외
from festivals.domain.enums import FestivalStatus
from festivals.domain.exceptions import FestivalNotFound
from festivals.domain.repository import FestivalRepository

# 공연 도메인 : 회차 조회·잔여 수량 저장, 회차가 없을 때 예외
from performances.domain.exceptions import PerformanceNotFound
from performances.domain.repository import PerformanceRepository

# 예매 도메인 : 저장소 추상 클래스, 엔티티, Enum, 예외, 한도 검사 규칙
from reservations.domain.enums import DiscountType, TicketType
from reservations.domain.exceptions import ReservationNotAvailable
from reservations.domain.repository import ReservationRepository
from reservations.domain.reservation import Reservation
from reservations.domain.service import check_daily_limit

# 한국 시간대
# - 시각 저장·비교는 UTC로 하고, "몇 월 며칠 / 무슨 요일"을 판단할 때만 KST로 바꾼다
# - UTC 기준으로 요일을 보면 한국 토요일 새벽 공연이 금요일로 잘못 계산될 수 있음
#   ex) 2026-11-06 15:30 UTC → 2026-11-07 00:30 KST (금요일 X, 토요일 O)
KST = ZoneInfo("Asia/Seoul")

# 티켓 종류별로 필요한 회차의 요일 (datetime.weekday() 기준 : 월=0 … 토=5, 일=6)
# - 값을 전부 리스트로 둔 이유
#   ① "회차 요일 in 목록"으로 검사할 수 있음 (숫자 하나면 in을 쓸 수 없어 TypeError)
#   ② len(목록)으로 "필요한 회차 수"를 알 수 있음 (양일권 = 2개)
WEEKDAY = {
    TicketType.SAT: [5],
    TicketType.SUN: [6],
    TicketType.BOTH: [5, 6],
}


class ReservationService:
    # 생성자 : 서비스가 쓸 저장소 3개를 받아서 보관만 한다
    # - 구현체(SQLAlchemy 저장소)가 아니라 추상 클래스 타입으로 받음
    #   → 서비스는 DB를 몰라도 되고, 테스트할 때 가짜 저장소로 바꿔 끼울 수 있음
    # - 실제 구현체는 wiring에서 연결해 줌
    def __init__(
        self,
        reservation_repo: ReservationRepository,
        festival_repo: FestivalRepository,
        performance_repo: PerformanceRepository,
    ) -> None:
        self._reservation_repo = (
            reservation_repo  # 예매 : 기존 예매 조회, 신규 예매 저장
        )
        self._festival_repo = festival_repo  # 축제 : 존재 여부, 상태, 이름·장소(스냅샷)
        self._performance_repo = performance_repo  # 공연 : 회차 목록, 가격, 잔여 수량

    # 예매 생성
    # - 인자는 사용자가 선택한 값 (라우터가 요청 body와 로그인 정보에서 꺼내 넘겨줌)
    #   festival_id, ticket_type, quantity, discount_type : 요청 body (사용자가 고른 값)
    #   user_id : 로그인 토큰 (인증을 통과했으므로 따로 조회하지 않음)
    # - 가격·할인 금액·축제 이름은 인자로 받지 않는다
    #   → 클라이언트가 보낸 값을 믿으면 가격을 조작할 수 있으므로 서버가 직접 조회·계산
    # - 반환 타입 Reservation : 저장 후 id가 채워진 예매를 돌려준다는 뜻
    async def create_reservation(
        self,
        festival_id: int,
        user_id: int,
        ticket_type: TicketType,
        quantity: int,
        discount_type: DiscountType = DiscountType.NONE,  # 할인을 고르지 않으면 할인 없음
    ) -> Reservation:

        # 현재 시각 준비
        # - now : UTC 시각. 예매 기간처럼 "시각끼리 비교"할 때 그대로 사용 (④)
        # - today : 한국 날짜. 축제 상태처럼 "날짜"로 판단할 때 사용 (②)
        now = datetime.now(UTC)
        now_kst = now.astimezone(KST)
        today = now_kst.date()

        # ① 축제 조회
        # - 사용자가 보낸 festival_id가 실제로 있는 축제인지 확인
        # - DB의 FK 제약에만 맡기면 저장 시점에 DB 에러(500)가 나므로,
        #   먼저 조회해서 "축제를 찾을 수 없습니다"(404)로 응답한다
        festival = await self._festival_repo.find_by_id(festival_id)

        if festival is None:
            raise FestivalNotFound()

        # ② 축제 상태 확인
        # - status(today)는 오늘(한국 날짜) 기준으로 SCHEDULED / OPEN / COMPLETED / CANCELED 를 계산
        # - 취소됐거나 이미 끝난 축제는 예매할 수 없음 → 409
        if festival.status(today) in (
            FestivalStatus.CANCELED,
            FestivalStatus.COMPLETED,
        ):
            raise ReservationNotAvailable()

        # ③ 회차 조회
        # - 예매는 축제(festival_id)를 가리키고, 어느 회차인지는 티켓 종류로 정해진다
        #   (양일권은 예매 1건이 토·일 두 회차를 포함하기 때문, #79)
        # - 그래서 축제의 회차를 전부 가져온 뒤 요일로 골라낸다
        # - 공연 저장소(#93)에는 페이지네이션이 있는 목록 조회(find_all_by_festival)만 있음
        #   → 축제의 회차 개수를 먼저 세고(count_by_festival), 그 개수만큼 한 번에 가져온다
        #     (offset=0 : 처음부터, limit=회차 개수 : 전부)
        performance_count = await self._performance_repo.count_by_festival(festival_id)
        performances = await self._performance_repo.find_all_by_festival(
            festival_id, offset=0, limit=performance_count
        )

        # 티켓 종류에 필요한 요일 목록 ex) SAT → [5], BOTH → [5, 6]
        performance_day = WEEKDAY[ticket_type]
        select_performance = []  # 고른 회차를 담을 리스트

        # 회차를 하나씩 꺼내서, 시작 시각의 "한국 요일"이 필요한 요일 목록에 있으면 담는다
        # - performances는 회차 여러 개의 리스트라 starts_at이 없음 → 하나씩 꺼내서 확인
        for performance in performances:
            day = performance.starts_at.astimezone(KST).weekday()
            if day in performance_day:
                select_performance.append(performance)

        # 필요한 요일 수와 고른 회차 수가 다르면 예매할 수 없음 → 404
        # ex) 양일권인데 일요일 회차가 없음 (필요 2개, 고름 1개)
        # - 하루에 회차가 1개라는 가정 (하루에 여러 회차면 정책을 다시 정해야 함)
        if len(performance_day) != len(select_performance):
            raise PerformanceNotFound()

        # ④ 회차 예매 가능 여부 확인
        # - is_bookable(now) : 상태가 OPEN이고, 잔여 수량이 1 이상이고, 지금이 예매 기간 안이면 True
        # - 양일권이면 토·일 회차 둘 다 예매 가능해야 함 → 하나라도 안 되면 409
        # - now는 UTC 그대로 넣음 (시각끼리 비교는 시간대가 달라도 파이썬이 맞춰서 비교)
        for performance in select_performance:
            if not performance.is_bookable(now):
                raise ReservationNotAvailable()

        # ⑤ 날짜별 한도 검사 (사용자 1명은 날짜별 최대 2장)
        # 1. 로그인한 사용자의 모든 예매 조회
        user_reservation = await self._reservation_repo.find_by_user_id(user_id)

        # 2. 같은 축제의 예매만 남기기
        # - 조회 결과에는 다른 축제 예매도 섞여 있음
        #   → 다른 축제의 토요일 예매가 이 축제 한도에 합산되면 안 되므로 걸러낸다
        same_festival = []
        for reservation in user_reservation:
            if reservation.festival_id == festival_id:
                same_festival.append(reservation)

        # 3. 기존 예매 + 신규 예매가 날짜별 2장을 넘는지 검사 (domain/service.py)
        # - 취소·만료된 예매는 함수 안에서 제외하고 계산
        # - 양일권 1장은 토 1장 + 일 1장으로 계산
        # - 넘으면 함수 안에서 OverReservationQuantity(422)를 던지므로 여기서는 호출만 한다
        check_daily_limit(same_festival, ticket_type, quantity)

        # ⑥ 티켓 1장 가격 계산
        # - 고른 회차의 가격을 더한 값 (토요일권 = 토 회차 가격 / 양일권 = 토 + 일)
        # - 수량은 곱하지 않음 → Reservation.create()가 unit_price × quantity로 총 금액을 계산
        price = sum(performance.price for performance in select_performance)

        # ⑦ 회차 잔여 수량 차감
        # - 고른 회차마다 quantity만큼 줄임 (양일권이면 토·일 둘 다)
        # - 엔티티 값만 바꾸면 DB에 반영되지 않으므로 공연 저장소로 저장까지 해야 함
        # - 이후 단계에서 예외가 나면 세션 rollback으로 차감도 함께 취소됨
        for performance in select_performance:
            performance.decrease_remaining(quantity)
            await self._performance_repo.save(performance)

        # ⑧ 예매 생성
        # - 서비스는 재료만 모아서 넘기고, 만드는 규칙은 엔티티(domain/reservation.py)가 담당
        #   create()가 하는 일 : 총 금액·할인 금액·최종 금액 계산, 상태 PENDING,
        #                         입금 기한(생성 + 24시간), 수량·금액 규칙 검증
        # - festival_name, venue : 예매 시점의 축제 이름·장소를 복사해 둠 (스냅샷)
        #   → 나중에 축제 정보가 바뀌어도 예매 내역은 그대로 유지
        reservation = Reservation.create(
            festival_id=festival_id,
            user_id=user_id,
            ticket_type=ticket_type,
            quantity=quantity,
            unit_price=price,
            festival_name=festival.name,
            venue=festival.venue,
            discount_type=discount_type,
        )

        # 저장 후 반환
        # - create() 결과에는 아직 id가 없음 → DB가 id를 만들어 준 save() 결과를 반환해야 함
        return await self._reservation_repo.save(reservation)
