from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from festivals.domain.exceptions import FestivalNotFound
from festivals.domain.festival import Festival
from festivals.domain.repository import FestivalRepository
from festivals.infrastructure.models import Festival as FestivalModel


# DB에서 꺼낼 때 사용: model의 9개 필드를 엔티티에 옮긴다.
# 축제는 상태를 저장하지 않고 status(today)로 계산하므로 enum 변환이 필요 없음
def _to_domain(model: FestivalModel) -> Festival:
    return Festival(
        id= model.id,
        name=model.name,
        venue=model.venue,
        description=model.description,
        starts_on=model.starts_on,
        ends_on=model.ends_on,
        canceled_at=model.canceled_at,
        created_at=model.created_at,
        updated_at=model.updated_at
    )

# DB에 넣을 때 사용: 새 축제를 DB 모델(ORM 객체)로 만든다.
# 새 축제 생성(save의 id=None 갈래)에서만 사용
# created_at, updated_at은 DB가 채우므로 넣지 않는다.
def _to_model(festival: Festival) -> FestivalModel:
    return FestivalModel(
        id=festival.id, # 새 축제의 id는 None이라 DB가 번호를 채운다.
        name=festival.name,
        venue=festival.venue,
        description=festival.description,
        starts_on=festival.starts_on,
        ends_on=festival.ends_on,
        canceled_at=festival.canceled_at
    )

# domain/repository.py의 FestivalRepository를 상속해서, 각 메서드를 실제 SQL로 채운다.
class SqlAlchemyFestivalRepository(FestivalRepository):
    # session을 받아 self._session에 저장한다.
    # session을 통해 모든 메서드가 DB와 이야기함.
    def __init__(self, session: AsyncSession):
        self._session = session

    # festival_id 기준 축제 단건 조회
    async def find_by_id(self, festival_id: int) -> Festival | None:
        stmt = (
            select(FestivalModel)
            .where(FestivalModel.id == festival_id)
            )
        # 비동기로 stmt 실행해서 result에 저장
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()

        # 조건 표현식으로 return
        return None if model is None else _to_domain(model)

    # 모든 축제 조회
    async def find_all(self, offset: int, limit: int) -> list[Festival]:
        stmt = (
            select(FestivalModel)
            # 축제 시작일 오름차순, 같으면 id 오름차순 
            .order_by(FestivalModel.starts_on, FestivalModel.id) 
            .offset(offset) # 건너뛰기
            .limit(limit) # 가져오기
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()

        # [리스트 컴프리헨션]
        # models에서 model을 하나씩 꺼내고, _to_domain(model)의 결과를 모아 리스트로 만든다.
        # 적용 안할 경우:
        # result = []
        # for model in models:
        #     result.append(_to_domain(model))
        # return result
        return [_to_domain(model) for model in models]

    # PageResponse.total 값으로 넣는 용도
    async def count(self) -> int:
        stmt = (
            select(
                func.count()
            )
            .select_from(FestivalModel)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    # 축제 저장
    # 엔티티를 받아서 DB에 반영 -> DB가 채운 값(id, created_at)이 들어간 엔티티를 돌려줌.
    async def save(self, festival: Festival) -> Festival:
        if festival.id is None: # 새 축제일 때
            
            model = _to_model(festival) # 엔티티 -> DB모델로 번역
            # DB에 넣은 새로 만든 모델은 add()로 등록해야 함.(session이 알아야 함)
            # 메모리에서 처리하는 일이므로 await가 없다
            self._session.add(model) # session.add()는 None 반환 -> 결과 받지 않고 호출만
        
        else: # 기존 축제 수정할 때
            # session.get()으로 DB에서 모델을 꺼낸다.
            # 꺼낸 객체는 자동으로 관리 대장에 올라간다.
            # DB에 다녀오므로 await를 쓴다.
            model = await self._session.get(FestivalModel, festival.id) # FestivalModel에서 이 id의 행을 줘

            # service가 조회하고 저장하기 전, 그 사이 행이 사라지면 여기서 404 
            if model is None:
                raise FestivalNotFound() # A안: 예외는 여기서 잡지 않고 raise만. 전역 핸들러가 404로 바꿔주고 get_db가 rollback 함.
            
            # dirty tracking: 엔티티에서 바뀐 값을 DB모델에 옮겨 적는다.
            model.name = festival.name
            model.venue = festival.venue
            model.description = festival.description
            model.starts_on = festival.starts_on
            model.ends_on = festival.ends_on
            model.canceled_at = festival.canceled_at

        # flush()로 바뀐 값만 session이 SQL로 보냄.
        # 새로 등록: INSERT, 값이 바뀜: UPDATE
        # flush()는 commit 전: 다른 요청에서 이 변경이 보이지 않음
        # commit은 요청이 정상적으로 끝날 때 get_db가 한다.
        await self._session.flush()
        # DB가 채운 값을 다시 model로 읽어온다 (refresh 안하면 엔티티 created_at이 비어있을 수 있음)
        await self._session.refresh(model)
        # DB모델을 다시 엔티티로 번역해서 service에 돌려준다.
        return _to_domain(model)

    async def exists_overlapping(self, venue: str, starts_on: date, ends_on: date, exclude_id: int | None = None)-> bool:
        stmt = select(func.count()).select_from(FestivalModel).where( # func.count() = COUNT(*)
                FestivalModel.venue == venue, # 같은 장소
                FestivalModel.canceled_at.is_(None), # 취소된 축제 제외 (canceled_At IS NULL)
                FestivalModel.starts_on <= ends_on, # 하루 겹침도 막기
                FestivalModel.ends_on >= starts_on
            )

        # 수정 중인 축제의 DB에 저장된 원래 버전(수정 전 기간)과 비교하면 안됨.
        # 자기 자신은 비교 대상에서 빠져야 함.
        # 다른 축제와 겹칠 때만 True
        # exclude_id가 None일 때면 DB에 없는 상태이므로 계산하면 안됨. not None일 때만 체크
        if exclude_id is not None:
            stmt = stmt.where(
                FestivalModel.id != exclude_id
            )
        result = await self._session.execute(stmt)
        return result.scalar_one() > 0
        
