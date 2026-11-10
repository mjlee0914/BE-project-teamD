# 실제로 쓰는 유스케이스가 있으면 작성
# 추상 클래스, abstractmethod <- 자식클래스가 구현해야한다는 뜻

from abc import ABC, abstractmethod
from uuid import UUID

from tickets.domain.enums import TicketStatus
from tickets.domain.ticket import Ticket


class TicketRepository(ABC):
    # 저장
    @abstractmethod
    async def save(self, ticket: Ticket) -> Ticket:
        """티켓을 저장한다. id가 None이면 새로 만들고, 있으면 기존 티켓을 갱신한다.
        DB가 채운 id, created_at 등이 반영된 티켓을 반환한다."""

    # 입장처리
    @abstractmethod
    async def find_by_code(self, ticket_code: UUID) -> Ticket | None:
        """ticket_code로 조회한다."""

    # 티켓 조회
    @abstractmethod
    async def find_by_id_for_user(self, ticket_id: int, user_id: int) -> Ticket | None:
        """본인 티켓만 조회한다. 없거나 남의 티켓이면 None."""

    # 중복발급 검사
    # 개수는 여기서 세고, 수량과 비교하는 판단은 유스케이스가 한다
    @abstractmethod
    async def count_by_reservation_id(self, reservation_id: int) -> int:
        """예매에 이미 발급된 티켓 수를 반환한다. 취소된 티켓도 포함해서 센다."""

    # 중복 발급 동시성 방지
    # "개수 세기 → 0이면 생성"은 두 요청이 동시에 오면 둘 다 0을 보고 통과한다.
    # 그래서 검사 전에 예매 행을 잠가서, 같은 예매의 발급 요청이 한 줄로 서게 한다.
    @abstractmethod
    async def lock_reservation(self, reservation_id: int, user_id: int) -> None:
        """본인 예매 행을 잠근다 (요청이 commit/rollback될 때까지 유지).
        없거나 남의 예매면 아무것도 잠그지 않는다."""

    # ----목록/집계--------

    # 내 티켓 목록 (최신순). 전체 개수는 count_by_user가 따로 센다
    @abstractmethod
    async def find_all_by_user(
        self,
        user_id: int,
        status: TicketStatus | None,
        offset: int,
        limit: int,
    ) -> list[Ticket]:
        """사용자의 티켓 목록. 최신순(created_at, id 내림차순). status가 None이면 전체."""

    # 내 티켓 전체 개수 (PageResponse.total 용)
    @abstractmethod
    async def count_by_user(self, user_id: int, status: TicketStatus | None) -> int:
        """사용자의 티켓 개수. status가 None이면 전체."""

    # 관리자 검색
    @abstractmethod
    async def find_all(
        self,
        performance_id: int | None,
        status: TicketStatus | None,
        offset: int,
        limit: int,
    ) -> list[Ticket]:
        """관리자 검색 목록. 최신순. 조건이 None이면 그 조건은 걸지 않는다."""

    # 관리자 검색 전체 개수 (PageResponse.total 용)
    @abstractmethod
    async def count(
        self, performance_id: int | None, status: TicketStatus | None
    ) -> int:
        """관리자 검색 조건에 맞는 티켓 개수."""

    # 입장 현황
    @abstractmethod
    async def count_by_status(self, performance_id: int) -> dict[TicketStatus, int]:
        """회차별 상태별 티켓 수. 없는 상태는 0으로 채워 모든 상태를 돌려준다."""
