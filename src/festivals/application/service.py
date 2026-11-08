# app/service 는 조회 -> 검증 -> 저장의 순서를 정한다.

# 저장소를 생성자로 받고, 없으면 NotFound raise
# 요청이 끝날 때 get_db가 commit한다.

from datetime import UTC, date, datetime  # UTC, datetime -> cancel에서 사용

from festivals.domain.exceptions import FestivalNotFound, FestivalPeriodOverlap
from festivals.domain.festival import Festival
from festivals.domain.repository import FestivalRepository


class FestivalService:
    def __init__(
            self,
            festival_repo: FestivalRepository
    ) -> None:
        self._festival_repo = festival_repo

    # 페스티벌 꺼내기
    async def get_festival(self, festival_id: int) -> Festival:
        festival = await self._festival_repo.find_by_id(festival_id)
        if festival is None:
            raise FestivalNotFound()
        return festival

    # 페스티벌 생성하기
    async def create_festival(
            self, 
            name: str,
            venue: str,
            starts_on: date,
            ends_on: date,
            description: str | None = None
            ) -> Festival:

        # Domain entity(Festival) 검사
        festival = Festival( 
            name=name,
            venue=venue,
            starts_on=starts_on,
            ends_on=ends_on,
            description=description
        )

        # infrastructure 저장소
        if await self._festival_repo.exists_overlapping(  
            festival.venue,
            festival.starts_on,
            festival.ends_on
        ):
            raise FestivalPeriodOverlap()

        return await self._festival_repo.save(festival)

    # 몇 페이지를 보여줄지
    async def list_festivals(self, page: int, size: int) -> tuple[list[Festival], int]:
        # page: 페이지 수, size: 한 페이지에 보여줄 축제 개수
        # 1페이지: 1~10번째 : 앞에서 0개 건너뛰고 10개
        # 2페이지: 11~20번째: 앞에서 10개 건너뛰고 10개
        # 3페이지: 21~25번째: 앞에서 20개 건너뛰고 10개 (5개만 있을 시 5개)
        offset = (page - 1) * size 

        festivals = await self._festival_repo.find_all(offset=offset, limit=size) # 계층마다 부르는 이름이 다르다.
        total = await self._festival_repo.count() # 전체 개수 계산 -> ex) 전체 total개 중 1 페이지
        return festivals, total

    # 수정: 꺼내기 -> 고치기 -> 겹침 검사 -> 저장
    async def update_festival(
            self,
            festival_id: int,
            name: str | None = None,
            venue: str | None = None,
            description: str | None = None,
            starts_on: date | None = None,
            ends_on: date | None = None
    ) -> Festival:
        # 엔티티 꺼내기
        festival = await self.get_festival(festival_id)

        # 고치기 (엔티티에게 시킨다)
        festival.change_info(name=name, venue=venue, description=description)
        festival.change_period(starts_on=starts_on, ends_on=ends_on)

        # 겹침 검사
        if await self._festival_repo.exists_overlapping(  
            festival.venue,
            festival.starts_on,
            festival.ends_on,
            exclude_id=festival_id
        ):
            raise FestivalPeriodOverlap()
        # TODO: 줄어든 기간 밖에 공연이 있는지 검사

        # 저장
        return await self._festival_repo.save(festival)
    
    # 취소: 꺼내기 -> 취소 -> 저장
    async def cancel_festival(
            self,
            festival_id: int
    ) -> Festival:
        # 꺼내기
        festival = await self.get_festival(festival_id)

        # 지금 시각을 만들어서 엔티티에 넘긴다.
        festival.cancel(datetime.now(UTC))
        # TODO: 축제취소 시 소속 공연 처리(팀 결정 필요)
        return await self._festival_repo.save(festival)