# 순서: 꺼내기 → 처리 → 저장
# 요청이 끝날 때 get_db가 commit
from datetime import datetime

from festivals.domain.exceptions import FestivalNotFound
from festivals.domain.repository import FestivalRepository
from performances.domain.exceptions import (
    PerformanceNotFound,
    PerformanceTitleDuplicated,
)
from performances.domain.performance import Performance
from performances.domain.repository import PerformanceRepository
from reservations.application.service import ReservationService
from shared.core.time import now_utc


class PerformanceService:
    def __init__(
            self,
            performance_repo: PerformanceRepository,
            festival_repo: FestivalRepository, # 공연 생성 및 수정시 축제기간 안에 있는지 검사해야 하므로 축제 꺼냄
            reservation_service: ReservationService,
    ) -> None:
        self._performance_repo = performance_repo
        self._festival_repo = festival_repo
        self._reservation_service = reservation_service

    # 개별 조회
    async def get_performance(self, performance_id: int) -> Performance:
        performance = await self._performance_repo.find_by_id(performance_id)
        if performance is None:
            raise PerformanceNotFound()
        return performance

    # 생성
    async def create_performance(
            self,
            festival_id: int,
            title: str,
            starts_at: datetime,
            ends_at: datetime,
            booking_open_at: datetime,
            booking_close_at: datetime,
            capacity: int,
            price: int,
            ) -> Performance:
        # festival 가져오기
        festival = await self._festival_repo.find_by_id(festival_id)

        if festival is None:
            raise FestivalNotFound()

        festival.ensure_not_canceled()

        if await self._performance_repo.exists_duplicated_title(
            festival_id=festival_id,
            title=title,
            ):
            raise PerformanceTitleDuplicated()

        performance = Performance.create(
            festival_id=festival_id,
            title=title,
            starts_at=starts_at,
            ends_at=ends_at,
            booking_open_at=booking_open_at,
            booking_close_at=booking_close_at,
            capacity=capacity,
            price=price,
            festival_starts_on=festival.starts_on,
            festival_ends_on=festival.ends_on
        )

        return await self._performance_repo.save(performance)

    # 목록 조회
    async def list_performances(self, festival_id: int, page: int, size: int) -> tuple[list[Performance], int]:
        festival = await self._festival_repo.find_by_id(festival_id)
        if festival is None:
            raise FestivalNotFound()

        offset = (page - 1) * size

        performances = await self._performance_repo.find_all_by_festival(festival_id=festival_id, offset=offset, limit=size)
        total = await self._performance_repo.count_by_festival(festival_id)

        return performances, total

    # 수정
    async def update_performance(
            self,
            performance_id: int,
            starts_at: datetime | None = None,
            ends_at: datetime | None = None,
            booking_open_at: datetime | None = None,
            booking_close_at: datetime | None = None,
            capacity: int | None = None
            ) -> Performance:
        # 공연 꺼내기
        performance = await self.get_performance(performance_id)
        # 공연 id로 페스티벌 꺼내기
        festival = await self._festival_repo.find_by_id(performance.festival_id)
        if festival is None:
            raise FestivalNotFound()

        performance.change_schedule(
            festival_starts_on=festival.starts_on,
            festival_ends_on=festival.ends_on,
            starts_at=starts_at,
            ends_at=ends_at,
            booking_open_at=booking_open_at,
            booking_close_at=booking_close_at
            )
        if capacity is not None:
            performance.change_capacity(capacity)

        return await self._performance_repo.save(performance)

    # 오픈 (꺼내기 -> 엔티티 메서드 -> 저장)
    async def open_performance(self, performance_id: int) -> Performance:
        performance = await self.get_performance(performance_id)
        performance.open()
        return await self._performance_repo.save(performance)

    # 취소 (꺼내기 -> 엔티티 메서드 -> 저장)
    async def cancel_performance(self, performance_id: int) -> Performance:
        performance = await self.get_performance(performance_id)
        performance.cancel(now_utc())
        # 공연 취소 → 관련 예매 일괄 취소 기능 추가
        # 저장을 먼저 하는 이유:
        # 예매 쪽이 이 회차를 CANCELED로 읽어야 수량 복구에서 건너뛴다 (취소된 회차는 복구x 이므로)
        # 양일권은 전체 취소
        # 남은 요일 회차의 좌석만 복구됨(예매에서 처리)
        saved_canceled = await self._performance_repo.save(performance)
        # 예매의 cancel_by_performance 실행하기
        # 공연 취소 -> 예매도 정리 -> 취소된 공연 돌려준다.
        await self._reservation_service.cancel_by_performance(saved_canceled)
        # 취소된 공연을 돌려줌.
        # -> (이 함수를 부른)라우터가 return 된 "취소된 공연 정보"로 응답을 만든다.
        return saved_canceled

    # 완료 (꺼내기 -> 엔티티 메서드 -> 저장). performance.complete(now_utc())
    async def complete_performance(self, performance_id: int) -> Performance:
        performance = await self.get_performance(performance_id)
        performance.complete(now_utc())
        return await self._performance_repo.save(performance)

    # bookable 조회
    async def get_availability(self, performance_id: int) -> tuple[Performance, bool]:
        performance = await self.get_performance(performance_id)
        result = performance.is_bookable(now_utc())
        return performance, result