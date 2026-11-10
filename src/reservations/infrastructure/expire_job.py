"""
# infrastructure/expire_job.py
[작업 3] 입금 기한이 지난 예매를 주기적으로 만료시키는 백그라운드 작업

# 동작
- 서버가 켜질 때 main.py의 lifespan이 start_expire_job()으로 시작
- EXPIRE_INTERVAL_SECONDS마다 ReservationService.expire_overdue() 실행
- 요청이 아니라서 get_db를 못 씀 → 세션을 직접 열고 commit/rollback도 직접 함
- 한 번 실패해도 로그만 남기고 다음 주기에 다시 시도 (서버가 죽지 않게)
"""

# 표준 라이브러리
import asyncio

# 프로젝트 코드
from festivals.infrastructure.repositories import SqlAlchemyFestivalRepository
from performances.infrastructure.repositories import SqlAlchemyPerformanceRepository
from reservations.application.service import ReservationService
from reservations.infrastructure.repositories import SqlalchemyReservationRepository
from shared.core.database import AsyncSessionLocal
from shared.core.logger import get_logger
from tickets.infrastructure.repositories import SqlAlchemyTicketRepository

logger = get_logger(__file__)

EXPIRE_INTERVAL_SECONDS = 60  # 1분마다 검사


async def run_expire_once() -> int:
    async with AsyncSessionLocal() as session:
        try:
            service = ReservationService(
                reservation_repo=SqlalchemyReservationRepository(session),
                festival_repo=SqlAlchemyFestivalRepository(session),
                performance_repo=SqlAlchemyPerformanceRepository(session),
                ticket_repo=SqlAlchemyTicketRepository(session),
            )
            count = await service.expire_overdue()
            await session.commit()
            return count
        except Exception:
            await session.rollback()
            raise


async def _loop() -> None:
    while True:
        try:
            count = await run_expire_once()
            if count:
                logger.info(f"입금 기한 지난 예매 {count}건을 만료했습니다.")
        except Exception:
            logger.exception("예매 만료 작업 실패 (다음 주기에 재시도)")
        await asyncio.sleep(EXPIRE_INTERVAL_SECONDS)


# 시작 : 반환된 task를 lifespan이 들고 있다가 종료 시 cancel()
def start_expire_job() -> asyncio.Task:
    return asyncio.create_task(_loop())
