# DB와web을 모르는 중간 단계 담당자
# usecase 는 설계도만 지키고, 어떤 저장소가 들어오는지는 wiring이 정함

from datetime import UTC, datetime
from uuid import UUID

from performances.domain.exceptions import PerformanceNotFound
from performances.domain.performance import Performance
from performances.domain.repository import PerformanceRepository
from reservations.domain.enums import ReservationStatus
from reservations.domain.exceptions import ReservationNotFound
from reservations.domain.repository import ReservationRepository
from shared.core.enums import TicketType
from shared.core.time import KST
from tickets.domain.exceptions import (
    TicketAlreadyIssued,
    TicketNotFound,
    TicketNotIssuable,
)
from tickets.domain.repository import TicketRepository  # 설계도 가져오기
from tickets.domain.ticket import (
    Ticket,  # 반환타입
    TicketStatus,
)


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
    async def create_tickets(self, reservation_id: int, user_id: int) -> list[Ticket]:
        # ① 예매 행 잠금: 같은 예매의 발급 요청이 동시에 오면 한 줄로 세운다
        # 잠음은 예매조회보다 먼저 작성.
        await self._ticket_repo.lock_reservation(reservation_id, user_id)

        # ② 예매 조회: 없거나 남의 예매면 똑같이 404 (존재 여부를 숨김)
        reservation = await self._reservation_repo.find_by_id(reservation_id)
        if reservation is None or reservation.user_id != user_id:
            raise ReservationNotFound()

        # ③ 승인된 예매만 티켓을 발급한다
        if reservation.status != ReservationStatus.CONFIRMED:
            raise TicketNotIssuable()

        # ④ 중복 발급 검사: 티켓은 한 번에 전부 만들어지므로 하나라도 있으면 이미 발급됨
        #    (취소된 티켓도 세므로 취소 후 재발급은 불가)
        if await self._ticket_repo.count_by_reservation_id(reservation_id) > 0:
            raise TicketAlreadyIssued()

        # ⑤ 티켓 종류에 맞는 회차 조회 (SAT·SUN은 1개, BOTH는 2개)
        performances = await self._find_target_performances(
            reservation.festival_id, reservation.ticket_type
        )

        # ⑥ 회차마다 수량만큼 티켓 생성 → 확정(ISSUED) → 저장
        now = datetime.now(UTC)
        tickets: list[Ticket] = []
        for performance in performances:
            for _ in range(reservation.quantity):
                ticket = Ticket(
                    reservation_id=reservation_id,
                    performance_id=performance.id,
                    price=performance.price,  # 정가 스냅샷 (할인은 예매에서 계산)
                    performance_title=performance.title,
                    performance_start_at=performance.starts_at,
                    performance_end_at=performance.ends_at,
                    cancel_deadline_at=performance.cancel_deadline_at,
                )
                ticket.confirm(now)
                # save의 반환값을 써야 DB가 채운 id가 들어 있다
                tickets.append(await self._ticket_repo.save(ticket))
        return tickets

    # --- 상태 변경 ---

    # 내 티켓 취소 (마감·상태 규칙은 Ticket.cancel이 판단)
    async def cancel_ticket(self, ticket_id: int, user_id: int) -> Ticket:
        ticket = await self.get_my_ticket(ticket_id, user_id)
        ticket.cancel(datetime.now(UTC))
        return await self._ticket_repo.save(ticket)

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
