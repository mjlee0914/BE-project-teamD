"""
# wiring/reservation.py
예매 도메인의 "자리표시자 의존성"에 실제 구현체를 연결하는 파일

# 왜 이런 파일이 필요한가
- 라우터는 Depends(provide_reservation_service)라는 "이름"만 알고, 서비스를 어떻게 만드는지는 모른다
- 서비스는 저장소의 추상 클래스(ReservationRepository 등)만 알고, SQLAlchemy는 모른다
- 실제로 무엇을 끼울지는 여기서 한 번에 정한다 → 다른 계층은 구현체를 몰라도 됨
  ex) 테스트에서는 이 연결만 가짜 저장소로 바꿔 끼우면 됨

# 동작 순서 (요청 1번마다)
① 라우터가 Depends(provide_reservation_service)를 요청
② dependency_overrides에 등록된 build_reservation_service가 대신 호출됨
③ build_reservation_service가 Depends(get_db)로 세션을 받음
④ 그 세션으로 저장소 3개 → 서비스 1개를 만들어 라우터에 넘김

# main.py에서 wire_dependencies(app)가 호출하므로 따로 등록할 필요 없음
"""

# 외부 라이브러리
from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

# 프로젝트 코드 : 저장소 구현체 3개, 서비스, 교체할 자리표시자, 세션 의존성
from festivals.infrastructure.repositories import SqlAlchemyFestivalRepository
from performances.infrastructure.repositories import SqlAlchemyPerformanceRepository
from reservations.application.service import ReservationService
from reservations.infrastructure.repositories import SqlalchemyReservationRepository
from reservations.presentation.dependencies import provide_reservation_service
from shared.core.database import get_db


# 예매 서비스 조립
# - session : get_db가 요청마다 새 세션을 만들어 넣어 줌 (요청이 끝나면 commit / 예외 시 rollback)
# - 저장소 3개에 "같은 세션"을 넣는 것이 핵심
#   → 예매 저장과 공연 잔여 수량 변경이 한 트랜잭션으로 묶임
#   → 중간에 실패하면 둘 다 함께 rollback (수량만 줄고 예매는 없는 상황 방지)
# - 키워드 인자로 넘기는 이유 : 위치 인자로 넘기면 순서가 바뀌었을 때
#   축제 저장소 자리에 공연 저장소가 들어가도 에러 없이 조용히 잘못 동작함
def build_reservation_service(
    session: AsyncSession = Depends(get_db),
) -> ReservationService:
    return ReservationService(
        reservation_repo=SqlalchemyReservationRepository(session),
        festival_repo=SqlAlchemyFestivalRepository(session),
        performance_repo=SqlAlchemyPerformanceRepository(session),
    )


# 의존성 교체 등록
# - 키 : 원래 함수(자리표시자), 값 : 대신 실행할 함수
# - 둘 다 괄호 없이 "함수 자체"를 넘긴다
#   → 괄호를 붙이면 등록하는 순간 실행돼 버림
#     (자리표시자는 바로 NotImplementedError, build 함수는 세션 없이 호출되어 에러)
# - get_current_user_id는 auth 구현 전이라 아직 등록하지 않음
def wire_reservation_dependencies(app: FastAPI) -> None:
    app.dependency_overrides.update(
        {
            # 추상 의존성: 구현체 팩토리
            provide_reservation_service: build_reservation_service
        }
    )
