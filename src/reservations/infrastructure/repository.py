"""
# infrastructure/repository.py
domain/repository.py에서 정의한 추상 클래스를 실제 DB로 구현하는 파일
    - SQLAlchemy 세션으로 DB에 저장 / 조회
    - DB의 ORM 모델 <-> domain 엔티티를 서로 변환

# ORM 모델 ( Object Relational Mapping )
- DB 테이블을 파이썬 클래스로 표현 한 것
- ORM 모델을 사용 안하고 SQL문으로 직접 조회하면 tuple 한 줄로 결과값이 온다
- ORM 모델 사용하면 객체로 오기 때문에 데이터 보기 편하고, 컬럼을 속성으로 꺼낼 수 있음

## _to_entity
# DB에서 꺼낸 ORM 모델을 domain 엔티티로 바꿈
- DB를 조회하면 SQLAlchemy가 ReservationModel 객체(DB 테이블 한 줄을 그대로 담은)를 돌려줌
- application, domain은 Reservation 엔티티만 앎, cancel(), confirm() 같은 규칙 메서드도 엔티티에 존재
- 저장소가 돌려주기 전에 엔티티로 바꿔줘야 application, domain이 정보를 알 수 있음

## _to_model
# 파이썬의 엔티티를 DB에 보낼 수 있는 ORM 모델로 변환

## 함수 앞 _
- 이 클래스 내부에서만 사용하니 외부에서 호출 금지 -> 실제로 막는 것이 아닌 관례

## session.get(모델, id)
- 기본 키로 행 하나를 가져옴
- SELECT * FROM reservations WHERE id = 3  -> 존재하면 ORM 객체, 없으면 None
- 다른 조건이 필요하다면 SELECT().WHERE()

## session.flush()
- 지금까지 세션에 쌓인 변경을 DB에 보내고, 확정(commit)은 하지 않음
- add나 값 변경은 세션에만 있다. flush를 해야 실제 INSERT/UPDATE SQL이 DB로 감
- commit 전이기 때문에 rollback 가능

## session.refresh(객체)
- DB에서 그 행을 다시 읽어서 객체의 값을 최신으로 채움

## session.scalar(stmt) / scalars(stmt)
- select 문장 실행해서 결과를 ORM 객체로 받음
- scalar는 결과 중 첫 번째 하나 / scalars는 결과 여러개, all()은 리스트로 반환
"""

# 외부 라이브러리
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# 프로젝트 코드
from reservations.domain.repository import ReservationRepository
from reservations.domain.reservation import Reservation
from reservations.infrastructure.models import Reservation as ReservationModel


class SqlalchemyReservationRepository(ReservationRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _to_entity(model: ReservationModel) -> Reservation:
        return Reservation(
            festival_id=model.festival_id,
            user_id=model.user_id,
            quantity=model.quantity,
            ticket_type=model.ticket_type,
            total_price=model.total_price,
            final_price=model.final_price,
            festival_name=model.festival_name,
            venue=model.venue,
            id=model.id,
            discount_amount=model.discount_amount,
            status=model.status,
            created_at=model.created_at,
            expires_at=model.expires_at,
            confirmed_at=model.confirmed_at,
            canceled_at=model.canceled_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def _to_model(entity: Reservation) -> ReservationModel:
        return ReservationModel(
            festival_id=entity.festival_id,
            user_id=entity.user_id,
            quantity=entity.quantity,
            ticket_type=entity.ticket_type,
            total_price=entity.total_price,
            final_price=entity.final_price,
            festival_name=entity.festival_name,
            venue=entity.venue,
            id=entity.id,
            discount_amount=entity.discount_amount,
            status=entity.status,
            created_at=entity.created_at,
            expires_at=entity.expires_at,
            confirmed_at=entity.confirmed_at,
            canceled_at=entity.canceled_at,
            updated_at=entity.updated_at,
        )

    # reservation ID 기준 단건 조회
    async def find_by_id(self, reservation_id: int) -> Reservation | None:
        model = await self.session.get(ReservationModel, reservation_id)
        return self._to_entity(model) if model else None

    # 예매 저장
    async def save(self, reservation: Reservation) -> Reservation:
        if reservation.id is not None:  # 예매가 존재하면 수정
            _Reservation = await self.session.get(ReservationModel, reservation.id)

            _Reservation.status = reservation.status
            _Reservation.confirmed_at = reservation.confirmed_at
            _Reservation.canceled_at = reservation.canceled_at

            await self.session.flush()
            await self.session.refresh(_Reservation)
            return self._to_entity(_Reservation)
        else:  # 예매 등록
            new_reservation = self._to_model(reservation)
            self.session.add(new_reservation)

            await self.session.flush()
            await self.session.refresh(new_reservation)
            return self._to_entity(new_reservation)

    # 로그인한 사용자의 모든 예매 조회
    async def find_by_user_id(self, user_id: int) -> list[Reservation]:
        stmt = select(ReservationModel).where(ReservationModel.user_id == user_id)

        models = (await self.session.scalars(stmt)).all()
        # 사용자의 모든 예매를 조회하기 때문에 scalars

        result = []

        for model in models:
            result.append(self._to_entity(model))

        return result
