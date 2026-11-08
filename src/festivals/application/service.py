# 저장소를 생성자로 받고, 없으면 NotFound raise
# 요청이 끝날 때 get_db가 commit한다.

from datetime import date

from festivals.domain.exceptions import FestivalNotFound, FestivalPeriodOverlap
from festivals.domain.festival import Festival
from festivals.domain.repository import FestivalRepository


class FestivalService:
    def __init__(
            self,
            festival_repo: FestivalRepository
    ) -> None:
        self._festival_repo = festival_repo

    async def get_festival(self, festival_id: int) -> Festival:
        festival = await self._festival_repo.find_by_id(festival_id)
        if festival is None:
            raise FestivalNotFound()
        return festival

    async def create_festival(
            self, 
            name: str,
            venue: str,
            starts_on: date,
            ends_on: date,
            description: str | None = None
            ) -> Festival:
        
        festival = Festival(
            name=name,
            venue=venue,
            starts_on=starts_on,
            ends_on=ends_on,
            description=description
        )
        if await self._festival_repo.exists_overlapping(
            festival.venue,
            festival.starts_on,
            festival.ends_on
        ):
            raise FestivalPeriodOverlap()

        return await self._festival_repo.save(festival)