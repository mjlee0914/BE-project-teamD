"""
# application/service.py
예매 유스케이스(사용자가 하려는 일 하나)를 처리하는 파일
    - 저장소에서 필요한 데이터를 모으고, domain의 규칙에 넘기고, 결과를 저장한다
    - "어떻게 판단하는가"(규칙)는 domain이 알고, 여기는 "어떤 순서로 하는가"만 안다

# 유스케이스 목록
[사용자]
- create_reservation          예매 생성
- get_reservation             예매 단건 조회 (본인 또는 관리자)
- get_my_reservations         내 예매 목록
- cancel_reservation          예매 취소 (본인: 취소 마감까지 / 관리자: 공연 시작 전까지)
[관리자] #117
- list_festival_reservations  축제별 예매 목록 (티켓 종류·상태 필터 + 페이지)

# commit은 여기서 하지 않는다
- 저장소는 flush까지만 하고, commit은 요청 단위 세션(get_db)에서 처리
- 중간에 예외가 나면 세션이 rollback 되므로 잔여 수량 변경도 함께 취소됨
"""

# 축제 도메인
from festivals.domain.enums import FestivalStatus
from festivals.domain.exceptions import FestivalNotFound
from festivals.domain.repository import FestivalRepository

# 공연 도메인
from performances.domain.enums import PerformanceStatus
from performances.domain.exceptions import PerformanceNotFound
from performances.domain.performance import Performance
from performances.domain.repository import PerformanceRepository

# 예매 도메인
from reservations.domain.enums import DiscountType, ReservationStatus
from reservations.domain.exceptions import (
    CancelDeadlineViolation,
    ReservationNotAvailable,
    ReservationNotFound,
)
from reservations.domain.repository import ReservationRepository
from reservations.domain.reservation import Reservation
from reservations.domain.service import check_daily_limit

# 공통
from shared.core.enums import TicketType
from shared.core.time import KST, now_utc, today_kst
from users.domain.exceptions import AdminPermissionDenied

# 잔여 수량을 되돌릴 수 있는 공연 상태
# - 취소·종료된 공연은 공연 엔티티가 복구를 거부(409)하므로 미리 걸러서 건너뛴다
RESTORABLE_STATUSES = (PerformanceStatus.OPEN, PerformanceStatus.SOLD_OUT)


class ReservationService:
    # 생성자 : 저장소 3개를 추상 타입으로 받아 보관 (실제 구현체는 wiring이 넣어 줌)
    def __init__(
        self,
        reservation_repo: ReservationRepository,
        festival_repo: FestivalRepository,
        performance_repo: PerformanceRepository,
    ) -> None:
        self._reservation_repo = reservation_repo
        self._festival_repo = festival_repo
        self._performance_repo = performance_repo

    # ------------------------------------------------------------------
    # 내부 도우미
    # ------------------------------------------------------------------

    # 티켓 종류에 맞는 회차 고르기 (토요일권 → 토 회차 1개, 양일권 → 토·일 2개)
    # - 예매에는 회차 id가 없고 festival_id + ticket_type만 있으므로 요일로 골라낸다 (#79)
    async def _find_target_performance(
        self, festival_id: int, ticket_type: TicketType
    ) -> list[Performance]:
        performance_count = await self._performance_repo.count_by_festival(festival_id)
        performances = await self._performance_repo.find_all_by_festival(
            festival_id, offset=0, limit=performance_count
        )

        performance_day = ticket_type.weekdays  # ex) SAT → [5], BOTH → [5, 6]
        select_performance = []
        for performance in performances:
            # 요일은 한국 시간 기준으로 판단 (UTC로 보면 토요일 새벽이 금요일이 됨)
            day = performance.starts_at.astimezone(KST).weekday()
            if day in performance_day:
                select_performance.append(performance)

        # 필요한 요일 수만큼 회차가 없으면 예매할 수 없음 → 404
        if len(performance_day) != len(select_performance):
            raise PerformanceNotFound()
        return select_performance

    # 잔여 수량 복구 (취소·만료·일괄 취소가 함께 사용)
    # - 취소·종료된 회차는 건너뜀 : 공연 취소로 예매를 일괄 취소할 때
    #   취소된 요일은 되돌릴 필요가 없고, 남은 요일만 되돌리면 되기 때문 (#131)
    async def _restore_remaining(self, reservation: Reservation) -> None:
        performances = await self._find_target_performance(
            reservation.festival_id, reservation.ticket_type
        )
        for performance in performances:
            if performance.status not in RESTORABLE_STATUSES:
                continue
            performance.increase_remaining(reservation.quantity)
            await self._performance_repo.save(performance)

    # ------------------------------------------------------------------
    # 사용자 유스케이스
    # ------------------------------------------------------------------

    # 예매 생성 (기존 로직 그대로)
    async def create_reservation(
        self,
        festival_id: int,
        user_id: int,
        ticket_type: TicketType,
        quantity: int,
        discount_type: DiscountType = DiscountType.NONE,
    ) -> Reservation:
        now = now_utc()
        today = today_kst()

        # ① 축제 조회 → 없으면 404
        festival = await self._festival_repo.find_by_id(festival_id)
        if festival is None:
            raise FestivalNotFound()

        # ② 취소·종료된 축제는 예매 불가 → 409
        if festival.status(today) in (
            FestivalStatus.CANCELED,
            FestivalStatus.COMPLETED,
        ):
            raise ReservationNotAvailable()

        # ③ 회차 고르기
        select_performance = await self._find_target_performance(
            festival_id, ticket_type
        )

        # ④ 고른 회차가 모두 예매 가능해야 함 → 아니면 409
        for performance in select_performance:
            if not performance.is_bookable(now):
                raise ReservationNotAvailable()

        # ⑤ 같은 축제 기존 예매 + 신규 예매가 날짜별 2장을 넘는지 검사 → 넘으면 422
        user_reservation = await self._reservation_repo.find_by_user_id(user_id)
        same_festival = [r for r in user_reservation if r.festival_id == festival_id]
        check_daily_limit(same_festival, ticket_type, quantity)

        # ⑥ 1장 가격 = 고른 회차 가격의 합 (양일권 = 토 + 일)
        price = sum(performance.price for performance in select_performance)

        # ⑦ 잔여 수량 차감
        for performance in select_performance:
            performance.decrease_remaining(quantity)
            await self._performance_repo.save(performance)

        # ⑧ 예매 생성·저장
        reservation = Reservation.create(
            festival_id=festival_id,
            user_id=user_id,
            ticket_type=ticket_type,
            quantity=quantity,
            unit_price=price,
            festival_name=festival.name,
            venue=festival.venue,
            discount_type=discount_type,
            now=now,
        )
        return await self._reservation_repo.save(reservation)

    # 예매 단건 조회 (#117 : 본인 확인 → "본인 또는 관리자" 확인으로 변경)
    # - 일반 회원이 남의 예매를 보면 403이 아니라 404 (예매가 있다는 사실 자체를 숨김)
    async def get_reservation(
        self, reservation_id: int, user_id: int, is_admin: bool
    ) -> Reservation:
        reservation = await self._reservation_repo.find_by_id(reservation_id)
        if reservation is None:
            raise ReservationNotFound()
        if not is_admin and reservation.user_id != user_id:
            raise ReservationNotFound()
        return reservation

    # 내 예매 목록 (없으면 빈 리스트)
    async def get_my_reservations(self, user_id: int) -> list[Reservation]:
        return await self._reservation_repo.find_by_user_id(user_id)

    # 예매 취소
    # - 일반 회원 : 입금 완료(CONFIRMED) 예매는 회차의 취소 마감(cancel_deadline_at)까지
    # - 관리자    : 예매 상태와 상관없이 공연 시작(starts_at) 전까지 (#117)
    #               양일권은 "첫 회차" 시작 시각 기준
    async def cancel_reservation(
        self, reservation_id: int, user_id: int, is_admin: bool
    ) -> Reservation:
        # ① 예매 조회 (본인 또는 관리자 확인 포함)
        await self._reservation_repo.lock(reservation_id)
        reservation = await self.get_reservation(reservation_id, user_id, is_admin)

        # ② 회차 조회
        performances = await self._find_target_performance(
            reservation.festival_id, reservation.ticket_type
        )
        # 종료된 공연의 예매는 취소 불가 (관리자·일반 회원 공통)
        if any(p.status == PerformanceStatus.COMPLETED for p in performances):
            raise CancelDeadlineViolation("종료된 공연의 예매는 취소할 수 없습니다.")
        now = now_utc()

        # ③ 마감 확인
        if is_admin:
            first_start = min(performance.starts_at for performance in performances)
            if now >= first_start:
                raise CancelDeadlineViolation("공연이 시작되어 취소할 수 없습니다.")
        elif reservation.status == ReservationStatus.CONFIRMED:
            for performance in performances:
                if now > performance.cancel_deadline_at:
                    raise CancelDeadlineViolation()

        # ④ 상태 변경 (이미 끝난 예매면 엔티티가 409)
        reservation.cancel(now)

        # ⑤ 잔여 수량 복구 → ⑥ 저장
        await self._restore_remaining(reservation)
        return await self._reservation_repo.save(reservation)

    # ------------------------------------------------------------------
    # 관리자 유스케이스 (#117)
    # ------------------------------------------------------------------

    # 축제별 예매 목록
    # - day : "SAT" 또는 "SUN" (회차별 보기). 토요일 회차 = SAT + BOTH 예매
    # - statuses : 상태 필터 (없으면 전체)
    # - 반환 : (현재 페이지 항목, 전체 개수) → 라우터가 PageResponse로 감쌈
    async def list_festival_reservations(
        self,
        festival_id: int,
        is_admin: bool,
        day: TicketType | None,
        statuses: list[ReservationStatus] | None,
        page: int,
        size: int,
    ) -> tuple[list[Reservation], int]:
        if not is_admin:
            raise AdminPermissionDenied()

        festival = await self._festival_repo.find_by_id(festival_id)
        if festival is None:
            raise FestivalNotFound()

        # 회차(요일) → 해당 요일이 포함된 티켓 종류 목록으로 바꾸기
        ticket_types = None
        if day is not None:
            ticket_types = [day, TicketType.BOTH] if day != TicketType.BOTH else [day]

        offset = (page - 1) * size  # 1페이지 → 0번째부터
        items = await self._reservation_repo.find_festival_reservation(
            festival_id, ticket_types, statuses, offset, size
        )
        total = await self._reservation_repo.count_festival_reservation(
            festival_id, ticket_types, statuses
        )
        return items, total
