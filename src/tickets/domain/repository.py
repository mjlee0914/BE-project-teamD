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

    # ----목록/집계

    # 내 티켓 목록/ 전체 개수 반환
    @abstractmethod
    async def get_all_by_user(
        self,
        user_id: int,
        status: TicketStatus | None,
        page: int,
        size: int,
    ) -> tuple[list[Ticket], int]:
        """사용자 검색 결과와 전체개수를 반환한다. page는 1부터, 최신 발급순"""

    # 관리자 검색결과 전체 개수 반환
    @abstractmethod
    async def search(
        self,
        performance_id: int | None,
        status: TicketStatus | None,
        page: int,
        size: int,
    ) -> tuple[list[Ticket], int]:
        """관리자 검색 결과와 전체 개수를 반환한다. page는 1부터, 최신 발급순."""

    # 입장 현황
    @abstractmethod
    async def count_by_status(self, performance_id: int) -> dict[TicketStatus, int]:
        """회차별 상태별 티켓 수. (입장 현황)"""
