# app/service 는 조회 -> 검증 -> 저장의 순서를 정한다.

# 저장소를 생성자로 받고, 없으면 NotFound raise
# 요청이 끝날 때 get_db가 commit한다.

from datetime import UTC, date, datetime, time, timedelta

from festivals.domain.exceptions import (
    FestivalAlreadyCanceled,
    FestivalHasPerformanceOutsidePeriod,
    FestivalHasUncanceledPerformances,
    FestivalNotFound,
    FestivalPeriodOverlap,
)
from festivals.domain.festival import Festival
from festivals.domain.repository import FestivalRepository

# TODO: KST 상수 통일 회의 후 shared로 교체 (#110 리뷰)
from performances.domain.performance import KST
from performances.domain.repository import PerformanceRepository


class FestivalService:
    def __init__(
            self,
            festival_repo: FestivalRepository,
            performance_repo: PerformanceRepository,
    ) -> None:
        self._festival_repo = festival_repo
        self._performance_repo = performance_repo

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

        # 같은 장소, 기간 겹치는지 검사
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

    # 수정: 꺼내기 -> 고치기 -> 겹침 검사 -> (기간 변경시) 기간 밖 공연 검사 -> 저장
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

        # 고치기(새로운 정보 적기) (엔티티에게 시킨다)
        festival.change_info(name=name, venue=venue, description=description)
        festival.change_period(starts_on=starts_on, ends_on=ends_on)

        # 겹침 검사 (현재는 이름이나 설명만 바꿔도 검사를 한다. 중대 이슈는 아님.)
        if await self._festival_repo.exists_overlapping(
            festival.venue,
            festival.starts_on,
            festival.ends_on,
            exclude_id=festival_id
        ):
            raise FestivalPeriodOverlap()

        # 기간(starts_on, ends_on)이 요청에 들어올 때만 줄어든 기간 밖에 공연이 있는지 검사
        # refactor 작업: 축제별 공연 개수를 전부 "세서" 전부 "가져오기" 에서 -> exists_outside_period 한번으로 바꾸기
        # 장점:
        # 1. DB왕복 2번에서 1번으로 줄임.
        # 2. 옮기는 데이터도 공연 전체에서 boolean 값 하나로 바뀜
        # 3. EXISTS는 조건에 맞는 공연을 찾으면 바로 멈춤
        # --> 공연이 많아져도 찾는 비용이 그대로 + 코드가 짧아짐 + 다른 검사들과 같은 패턴(exists_duplicated_title, exists_uncanceled_by_festival)
        if starts_on is not None or ends_on is not None:
            # 축제 첫날 00:00 KST
            # combine(날짜, 시각, tzinfo) = 날짜 + 시각 + 시간대 합쳐 datetime 하나로 만듦.
            # 날짜에는 요청값이 아닌 엔티티 값을 씀: 기존 시작일
            period_start = datetime.combine(festival.starts_on, time.min, tzinfo=KST)

            # 축제 마지막 날(다음 날) 00:00 KST
            # timedelta(days=1)= 하루, 날짜 + 하루 = 다음날
            # 다음날 자정 = 마지막 날이 끝나는 순간
            period_end = datetime.combine(festival.ends_on + timedelta(days=1), time.min, tzinfo=KST)

            # 공연 저장소에 "기간 밖의 취소 안된 공연 있는지" 확인
            # DB 접근 - await 사용
            # KST가 붙은 시각이라 DB가 UTC 값과 알아서 맞춰서 비교한다.
            if await self._performance_repo.exists_outside_period(
                festival_id=festival_id,
                period_start=period_start,
                period_end=period_end,
            ):
                # True일 때 (밖에 공연이 하나라도 있을 때) -> 409
                # 여기서 raise하면 save까지 안가고 get_db가 rollback
                raise FestivalHasPerformanceOutsidePeriod()

        # 모든 검사를 통과하면 저장
        # flush, UPDATE
        # commit은 요청이 끝날 때 get_db가 한다.
        return await self._festival_repo.save(festival)

    # 취소: 꺼내기 -> 취소 -> 저장
    async def cancel_festival(
            self,
            festival_id: int
    ) -> Festival:
        # 꺼내기
        festival = await self.get_festival(festival_id)

        # 이미 취소된 축제를 또 취소하면 에러
        if festival.canceled_at is not None:
            raise FestivalAlreadyCanceled()
        
        # 공연상태가 CANCELED가 아닌 공연이 존재하면 축제 취소 x
        if await self._performance_repo.exists_uncanceled_by_festival(festival_id):
            raise FestivalHasUncanceledPerformances()

        # 지금 시각을 만들어서 엔티티에 넘긴다.
        festival.cancel(datetime.now(UTC))

        return await self._festival_repo.save(festival)