# DB와web을 모르는 중간 단계 담당자
# usecase 는 설계도만 지키고, 어떤 저장소가 들어오는지는 wiring이 정함

from datetime import UTC, datetime
from uuid import UUID

from performances.domain.enums import PerformanceStatus
from performances.domain.repository import PerformanceRepository
from reservations.domain.enums import ReservationStatus
from reservations.domain.repository import ReservationRepository
from reservations.domain.reservation import Reservation
from shared.core.enums import TicketType
from tickets.domain.exceptions import TicketNotCancelable, TicketNotFound
from tickets.domain.repository import TicketRepository  # 설계도 가져오기
from tickets.domain.ticket import (
    FINAL_STATUSES,
    Ticket,  # 반환타입
    TicketStatus,
)

# 잔여 수량을 되돌릴 수 있는 공연 상태 (취소·종료된 공연은 공연 엔티티가 복구를 거부하므로 건너뜀)
RESTORABLE_STATUSES = (PerformanceStatus.OPEN, PerformanceStatus.SOLD_OUT)


# 티켓과 관련된 업무를 모아두는 상자
class TicketService:
    def __init__(
        self,
        ticket_repo: TicketRepository,
        reservation_repo: ReservationRepository,
        performance_repo: PerformanceRepository,
    ) -> None:  # 저장소 받기. 밖에서 저장소를 하나 받고, 타입은 설계도. 이 함수는 돌려주는 값이 없음.
        self._ticket_repo = ticket_repo
        self._reservation_repo = reservation_repo  # 에매 조회
        self._performance_repo = performance_repo  # 공연 정보 스냅샷

    # --------조회---------
    async def get_my_ticket(self, ticket_id: int, user_id: int) -> Ticket:
        ticket = await self._ticket_repo.find_by_id_for_user(ticket_id, user_id)
        if ticket is None:
            raise TicketNotFound()
        return ticket

    # 내 전체 티켓 목록
    async def get_my_tickets(
        self, user_id, status: TicketStatus | None, page: int, size: int
    ) -> tuple[list[Ticket], int]:
        offset = (page - 1) * size
        tickets = await self._ticket_repo.find_all_by_user(
            user_id, status, offset, size
        )
        total = await self._ticket_repo.count_by_user(user_id, status)
        return tickets, total

    # --- 생성 ---

    # 승인된 예매의 티켓을 모두 만든다 (회차 수 × 수량)
    # async def create_tickets(self, reservation_id: int, user_id: int) -> list[Ticket]:
    #     # ① 예매 행 잠금: 같은 예매의 발급 요청이 동시에 오면 한 줄로 세운다
    #     # 잠음은 예매조회보다 먼저 작성.
    #     await self._ticket_repo.lock_reservation(reservation_id, user_id)

    #     # ② 예매 조회: 없거나 남의 예매면 똑같이 404 (존재 여부를 숨김)
    #     reservation = await self._reservation_repo.find_by_id(reservation_id)
    #     if reservation is None or reservation.user_id != user_id:
    #         raise ReservationNotFound()

    #     # ③ 승인된 예매만 티켓을 발급한다
    #     if reservation.status != ReservationStatus.CONFIRMED:
    #         raise TicketNotIssuable()

    #     # ④ 중복 발급 검사: 티켓은 한 번에 전부 만들어지므로 하나라도 있으면 이미 발급됨
    #     #    (취소된 티켓도 세므로 취소 후 재발급은 불가)
    #     if await self._ticket_repo.count_by_reservation_id(reservation_id) > 0:
    #         raise TicketAlreadyIssued()

    #     # ⑤ 티켓 종류에 맞는 회차 조회 (SAT·SUN은 1개, BOTH는 2개)
    #     performances = await self._find_target_performances(
    #         reservation.festival_id, reservation.ticket_type
    #     )

    #     # ⑥ 회차마다 수량만큼 티켓 생성 → 확정(ISSUED) → 저장
    #     now = datetime.now(UTC)
    #     tickets: list[Ticket] = []
    #     for performance in performances:
    #         for _ in range(reservation.quantity):
    #             ticket = Ticket(
    #                 reservation_id=reservation_id,
    #                 performance_id=performance.id,
    #                 price=performance.price,  # 정가 스냅샷 (할인은 예매에서 계산)
    #                 performance_title=performance.title,
    #                 performance_start_at=performance.starts_at,
    #                 performance_end_at=performance.ends_at,
    #                 cancel_deadline_at=performance.cancel_deadline_at,
    #             )
    #             ticket.confirm(now)
    #             # save의 반환값을 써야 DB가 채운 id가 들어 있다
    #             tickets.append(await self._ticket_repo.save(ticket))
    #     return tickets

    # --- 상태 변경 ---

    # 내 티켓 취소 (규칙 여섯 개는 아래 도우미 메서드에 나눠 놓았다)
    # - 토요일권·일요일권: 누른 1장 / 양일권: 토·일 한 쌍을 함께 취소
    # - 취소한 장마다 그 회차 잔여 수량 +1, 티켓이 전부 취소되면 예매도 CANCELED
    async def cancel_ticket(self, ticket_id: int, user_id: int) -> Ticket:
        ticket = await self.get_my_ticket(
            ticket_id, user_id
        )  # ① 내 티켓인지 (아니면 404)
        await self._reservation_repo.lock(
            ticket.reservation_id
        )  # ② 같은 예매 요청을 줄 세움

        # 티켓 종류(SAT/SUN/BOTH)는 예매에 있으므로 예매와 예매의 티켓 전체를 조회
        reservation = await self._reservation_repo.find_by_id(ticket.reservation_id)
        if reservation is None:
            raise TicketNotFound()
        siblings = await self._ticket_repo.find_all_by_reservation(
            ticket.reservation_id
        )

        targets = self._pick_cancel_targets(  # ③ 함께 취소할 티켓 (양일권이면 쌍)
            reservation.ticket_type, ticket_id, siblings
        )
        now = datetime.now(UTC)
        saved = await self._cancel_targets(
            targets, now
        )  # ④ 검사 → 저장, ⑤ 잔여 수량 복구
        await self._cancel_reservation_if_all_canceled(  # ⑥ 전부 취소됐으면 예매도
            reservation, siblings, now
        )
        return saved[ticket_id]

    # 티켓 코드로 입장 처리 (당일·상태 규칙은 Ticket.enter가 판단)
    async def enter_ticket(self, ticket_code: UUID) -> Ticket:
        ticket = await self._ticket_repo.find_by_code(ticket_code)
        if ticket is None:
            raise TicketNotFound()
        ticket.enter(datetime.now(UTC))
        return await self._ticket_repo.save(ticket)

    # --- 관리자 ---

    # 관리자 검색: (목록, 전체 개수)
    async def search_tickets(
        self,
        performance_id: int | None,
        status: TicketStatus | None,
        page: int,
        size: int,
    ) -> tuple[list[Ticket], int]:
        offset = (page - 1) * size
        tickets = await self._ticket_repo.find_all(performance_id, status, offset, size)
        total = await self._ticket_repo.count(performance_id, status)
        return tickets, total

    # 회차별 입장 현황: 상태별 티켓 수 (없는 상태는 0)
    async def get_entry_status(self, performance_id: int) -> dict[TicketStatus, int]:
        return await self._ticket_repo.count_by_status(performance_id)

    # --- 내부 도우미 ---

    # 축제의 회차 중 티켓 종류의 요일에 해당하는 회차를 고른다 (예매 서비스와 같은 기준)
    """
    async def _find_target_performances(
        self, festival_id: int, ticket_type: TicketType
    ) -> list[Performance]:
        count = await self._performance_repo.count_by_festival(festival_id)
        performances = await self._performance_repo.find_all_by_festival(
            festival_id, offset=0, limit=count
        )
        weekdays = ticket_type.weekdays
        selected = [
            performance
            for performance in performances
            if performance.starts_at.astimezone(KST).weekday() in weekdays
        ]
        # 필요한 요일 수와 고른 회차 수가 다르면 발급할 수 없다 (하루에 회차 1개 가정)
        if len(selected) != len(weekdays):
            raise PerformanceNotFound()
        return selected
        """

    # 예매에 속한 티켓 전부 취소 + 잔여 수량 복구 (예매 서비스가 호출)
    # - 예매 상태 변경은 호출한 쪽(예매)이 한다. 여기서는 티켓과 잔여 수량만 다룬다
    # - force_cancel : 취소 마감은 보지 않음 (마감 판단은 예매가 이미 했음)
    # - 이미 끝난 티켓(CANCELED·USED·EXPIRED)은 건너뛰고,
    #   이번에 취소한 티켓 수만큼만 회차별로 복구 → 단건 취소분을 또 복구하지 않는다
    async def cancel_all_by_reservation(
        self, reservation_id: int, now: datetime
    ) -> None:
        tickets = await self._ticket_repo.find_all_by_reservation(reservation_id)
        cancelled: dict[int, int] = {}  # {회차 id: 이번에 취소한 장수}
        for ticket in tickets:
            if ticket.status in FINAL_STATUSES:
                continue
            ticket.force_cancel(now)
            await self._ticket_repo.save(ticket)
            cancelled[ticket.performance_id] = (
                cancelled.get(ticket.performance_id, 0) + 1
            )
        for performance_id, count in cancelled.items():
            await self._restore_seats(performance_id, count)

    # 공연 잔여 수량 복구 (취소·종료된 공연은 건너뜀)
    async def _restore_seats(self, performance_id: int, count: int) -> None:
        performance = await self._performance_repo.find_by_id(performance_id)
        if performance is not None and performance.status in RESTORABLE_STATUSES:
            performance.increase_remaining(count)
            await self._performance_repo.save(performance)

    # 함께 취소할 티켓 고르기
    # - 토요일권·일요일권: 누른 티켓 한 장
    # - 양일권(BOTH): 토·일 한 쌍. 발급 순서가 "회차 → 수량"이라서 (예매의 _issue_tickets)
    #   같은 회차 안에서 k번째 티켓끼리 한 쌍이다 (수량 2: 토1-일1, 토2-일2)
    #   siblings는 id 순서(= 발급 순서)이고 이미 취소된 티켓도 포함하므로 쌍이 바뀌지 않는다
    @staticmethod
    def _pick_cancel_targets(
        ticket_type: TicketType, ticket_id: int, siblings: list[Ticket]
    ) -> list[Ticket]:
        clicked = next(t for t in siblings if t.id == ticket_id)
        if ticket_type != TicketType.BOTH:
            return [clicked]

        # 회차별 티켓 묶음: {회차 id: [티켓, ...]} (발급 순서 유지)
        by_performance: dict[int, list[Ticket]] = {}
        for t in siblings:
            by_performance.setdefault(t.performance_id, []).append(t)

        # 누른 티켓이 자기 회차 안에서 몇 번째인지
        position = next(
            i
            for i, t in enumerate(by_performance[clicked.performance_id])
            if t.id == ticket_id
        )

        # 다른 회차에서 같은 번째 티켓이 짝
        targets = [clicked]
        for performance_id, group in by_performance.items():
            if performance_id == clicked.performance_id:
                continue
            if position >= len(group):
                raise TicketNotCancelable("양일권의 짝이 되는 티켓을 찾을 수 없습니다.")
            targets.append(group[position])
        return targets

    # 대상 티켓을 전부 검사한 뒤 저장하고, 티켓 1장마다 그 회차 잔여 수량을 복구한다
    # - 먼저 전부 cancel(검사): 하나라도 못 취소하면(끝난 티켓, 마감 지남) 여기서 409
    #   → 아직 아무것도 저장하지 않았으므로 쌍의 한쪽만 취소되는 일이 없다
    async def _cancel_targets(
        self, targets: list[Ticket], now: datetime
    ) -> dict[int, Ticket]:
        for target in targets:
            target.cancel(now)

        saved: dict[int, Ticket] = {}
        for target in targets:
            saved[target.id] = await self._ticket_repo.save(target)
            await self._restore_seats(target.performance_id, 1)
        return saved

    # 예매의 티켓이 전부 CANCELED면 예매도 CANCELED로 바꾼다 (일부만 취소면 CONFIRMED 유지)
    # - siblings 안의 티켓 객체는 위에서 cancel로 이미 상태가 바뀌어 있다 (같은 객체)
    async def _cancel_reservation_if_all_canceled(
        self, reservation: Reservation, siblings: list[Ticket], now: datetime
    ) -> None:
        all_canceled = all(t.status == TicketStatus.CANCELED for t in siblings)
        if all_canceled and reservation.status == ReservationStatus.CONFIRMED:
            reservation.cancel(now)
            await self._reservation_repo.save(reservation)
