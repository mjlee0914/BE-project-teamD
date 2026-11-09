"""
# domain/repository.py
반드시 가져야 할 메서드 목록을 정의하는 추상 클래스
메서드 이름, 인자 타입, 반환 타입만 존재하며 구현은 없음
service.py는 이 클래스 타입만 보고 코드를 작성

# abc
Abstract Base Classes ( 추상 기본 클래스 )
추상 클래스
  - 직접 객체를 만드는 것이 아닌, 상속받아서 쓰라고 만든 클래스
  - 자식 클래스가 모든 @abstractmethod를 구현해야 객체를 만들 수 있음
"""

# 파이썬 기본 라이브러리
from abc import ABC, abstractmethod

from reservations.domain.enums import ReservationStatus

# 프로젝트 코드
from reservations.domain.reservation import Reservation
from shared.core.enums import TicketType


class ReservationRepository(ABC):
    @abstractmethod
    async def find_by_id(self, reservation_id: int) -> Reservation | None:
        """예매 ID기준 단건 조회"""

    @abstractmethod
    async def save(self, reservation: Reservation) -> Reservation:
        """예매 저장"""

    @abstractmethod
    async def find_by_user_id(
        self, user_id: int
    ) -> list[Reservation]:  # 사용자 한 명은 여러 개의 예매를 가질 수 있음
        """로그인한 사용자의 모든 예매 조회"""

    @abstractmethod
    async def find_festival_reservation(
        self,
        festival_id: int,
        ticket_types: list[TicketType] | None,
        statuses: list[ReservationStatus] | None,
        offset: int,
        limit: int,
    ) -> list[Reservation]:
        """축제별 예매 목록 ( 페이지 하나 분량 )"""

    @abstractmethod
    async def count_festival_reservation(
        self,
        festival_id: int,
        ticket_types: list[TicketType] | None,
        statuses: list[ReservationStatus] | None,
    ) -> int:
        """축제별 예매 전체 개수"""
