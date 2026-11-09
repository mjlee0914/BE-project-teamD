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
from shared.core.time import now_utc


class PerformanceService:
    def __init__(
            self,
            performance_repo: PerformanceRepository,
            festival_repo: FestivalRepository # 공연 생성 및 수정시 축제기간 안에 있는지 검사해야 하므로 축제 꺼냄

    ) -> None:
        self._performance_repo = performance_repo
        self._festival_repo = festival_repo

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
        performance.cancel()
        # TODO: 예매 일괄 취소 (회의 11/9)
        return await self._performance_repo.save(performance)

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