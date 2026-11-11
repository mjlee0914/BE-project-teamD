"""
# infrastructure/expire_job.py
공연이 끝난 티켓(취소된 티켓 제외)을 주기적으로 만료(EXPIRED)시키는 백그라운드 작업

# 동작
- 서버가 켜질 때 main.py의 lifespan이 start_ticket_expire_job()으로 시작
- EXPIRE_INTERVAL_SECONDS마다 TicketService.expire_overdue() 실행
- 요청이 아니라서 get_db를 못 씀 → 세션을 직접 열고 commit/rollback도 직접 함
- 한 번 실패해도 로그만 남기고 다음 주기에 다시 시도 (서버가 죽지 않게)
"""

# 표준 라이브러리
import asyncio

# 프로젝트 코드
from performances.infrastructure.repositories import SqlAlchemyPerformanceRepository
from reservations.infrastructure.repositories import SqlalchemyReservationRepository
from shared.core.database import AsyncSessionLocal
from shared.core.logger import get_logger
from tickets.application.service import TicketService
from tickets.infrastructure.repositories import SqlAlchemyTicketRepository

logger = get_logger(__file__)

EXPIRE_INTERVAL_SECONDS = 600  # 10분마다 검사 (공연 종료 후 만료라 촘촘할 필요 없음)


async def run_ticket_expire_once() -> int:
    async with AsyncSessionLocal() as session:
        try:
            service = TicketService(
                ticket_repo=SqlAlchemyTicketRepository(session),
                reservation_repo=SqlalchemyReservationRepository(session),
                performance_repo=SqlAlchemyPerformanceRepository(session),
            )
            count = await service.expire_overdue()
            await session.commit()  # 요청이 아니라서 get_db 대신 직접 commit
            return count
        except Exception:
            await session.rollback()
            raise


async def _loop() -> None:
    while True:
        try:
            count = await run_ticket_expire_once()
            if count:
                logger.info(f"공연이 끝난 티켓 {count}건을 만료했습니다.")
        except Exception:
            logger.exception("티켓 만료 작업 실패 (다음 주기에 재시도)")
        await asyncio.sleep(EXPIRE_INTERVAL_SECONDS)


# 시작: 반환된 task를 lifespan이 들고 있다가 종료 시 cancel()
def start_ticket_expire_job() -> asyncio.Task:
    return asyncio.create_task(_loop())
