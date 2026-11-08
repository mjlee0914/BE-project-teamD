from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from performances.domain.exceptions import (
    PerformanceNotFound,
    PerformanceVersionConflict,
)
from performances.domain.performance import Performance
from performances.domain.repository import PerformanceRepository
from performances.infrastructure.models import Performance as PerformanceModel


def _to_domain(model:PerformanceModel) -> Performance:
    return Performance(
        id=model.id,
        festival_id=model.festival_id,
        title=model.title,
        starts_at=model.starts_at,
        ends_at=model.ends_at,
        booking_open_at=model.booking_open_at,
        booking_close_at=model.booking_close_at,
        cancel_deadline_at=model.cancel_deadline_at,
        capacity=model.capacity,
        remaining_count=model.remaining_count,
        price=model.price,
        version=model.version,
        status=model.status,
        created_at=model.created_at,
        updated_at=model.updated_at
    )


def _to_model(performance: Performance) -> PerformanceModel:
    # version은 return 하지 않는다
    # why ?
    # version은 기본키가 아니라 None을 넣으면 NULL로 insert 됨
    # -> default=1이 무시됨 = NOT NULL 위반
    return PerformanceModel(
        remaining_count=performance.remaining_count,
        cancel_deadline_at=performance.cancel_deadline_at,
        status=performance.status,
        festival_id=performance.festival_id,
        title=performance.title,
        starts_at=performance.starts_at,
        ends_at=performance.ends_at,
        booking_open_at=performance.booking_open_at,
        booking_close_at=performance.booking_close_at,
        capacity=performance.capacity,
        price=performance.price
    )

class SqlAlchemyPerformanceRepository(PerformanceRepository):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def find_by_id(self, performance_id: int) -> Performance | None:
        stmt = (
            select(PerformanceModel)
            .where(PerformanceModel.id == performance_id)
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return None if model is None else _to_domain(model)

    async def find_all(self, offset: int, limit: int) -> list[Performance]:
        stmt = (
            select(PerformanceModel)
            .order_by(PerformanceModel.starts_at, PerformanceModel.id)
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return [_to_domain(model) for model in models]

    async def find_all_by_festival(self, festival_id: int, offset: int, limit: int) -> list[Performance]:
        stmt = (
            select(PerformanceModel)
            .where(
                PerformanceModel.festival_id == festival_id
            )
            .order_by(PerformanceModel.starts_at, PerformanceModel.id)
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return [_to_domain(model) for model in models]        

    async def count(self) -> int:
        stmt = (
            select(
                func.count()
            )
            .select_from(PerformanceModel)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    # 예매가 가장 먼저 부르는 메서드
    async def count_by_festival(self, festival_id: int) -> int:
        stmt = (
            select(func.count())
            .select_from(PerformanceModel)
            .where(PerformanceModel.festival_id == festival_id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def save(self, performance: Performance) -> Performance:
        if performance.id is None: # 새 공연일 때
            model = _to_model(performance)
            self._session.add(model)
        else:
            model = await self._session.get(PerformanceModel, performance.id)
            # 조회 없이 save를 부른 경우를 위한 방어 코드
            if model is None:
                raise PerformanceNotFound()
            
            # 밑의 조건 추가 안하면?
            # save의 session.get()이 DB를 다시 읽어서 최신 버전을 가져옴
            # -> 이러면 최신끼리 비교하게 되어서 충돌 못잡음
            # 밑의 조건 의미:
            # model.version=현재 버전
            # performance.version=아까 버전(엔티티의 버전)
            # 아까 버전이랑 현재 버전이 다르면 예외발생시키고 멈춘다.
            if model.version != performance.version:
                raise PerformanceVersionConflict()
            
            model.remaining_count=performance.remaining_count
            model.cancel_deadline_at=performance.cancel_deadline_at
            model.status=performance.status
            model.title=performance.title
            model.starts_at=performance.starts_at
            model.ends_at=performance.ends_at
            model.booking_open_at=performance.booking_open_at
            model.booking_close_at=performance.booking_close_at
            model.capacity=performance.capacity
            model.price=performance.price

        # flush() 실행 도중 생기는 에러 잡기
        # 우리 예외로 바꿔서 던지면,
        # get_db가 rollback
        try: 
            await self._session.flush()
        except StaleDataError: # version이 stale 되었을 때 (version 1 이 2로 바뀌었을 때)
            raise PerformanceVersionConflict() # StaleDataError는 SQLAlchemy 에러 -> 우리 예외로 잡지 않으면 500뜸
        
        await self._session.refresh(model)
        return _to_domain(model)

    async def exists_duplicated_title(self, festival_id: int, title: str, exclude_id: int | None = None) -> bool:
        inner = select(PerformanceModel.id).where(
            PerformanceModel.festival_id == festival_id,
            PerformanceModel.title == title
            )
        if exclude_id is not None:
            # 수정할 때는 자기 자신을 중복으로 착각하지 않도록,
            # 안쪽 쿼리 (같은 축제, 같은 제목) 조건에 "id != exclude_id"을 AND로 덧붙인다.
            # (EXISTS로 감싸기 전에 붙여야 함, 바깥에 붙이면 자기 자신이 빠지지 않음)
            inner = inner.where(PerformanceModel.id != exclude_id)
        stmt = select(inner.exists())
        result = await self._session.execute(stmt)
        return result.scalar()
    