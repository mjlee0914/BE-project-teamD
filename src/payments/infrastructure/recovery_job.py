"""취소·만료 예매와 중단된 결제를 기존 DB 기록으로 찾아 재조회·취소한다."""

import asyncio

from payments.domain.exceptions import PaymentProcessingError
from payments.infrastructure.sqlalchemy_repository import SQLAlchemyPaymentRepository
from shared.core.database import AsyncSessionLocal
from shared.core.logger import get_logger
from shared.core.time import now_utc
from wiring.payment import build_payment_service

logger = get_logger(__name__)


async def run_recovery_once() -> int:
    async with AsyncSessionLocal() as session:
        ids = await SQLAlchemyPaymentRepository(session).find_recovery_candidates(
            now_utc()
        )
    completed = 0
    # 한 건의 오류로 나머지 결제 처리가 밀리지 않도록 별도 세션에서 처리한다.
    for payment_id in ids:
        async with AsyncSessionLocal() as session:
            try:
                payment = await build_payment_service(session).recover(payment_id)
                await session.commit()
                if payment.recovery_status is None:
                    completed += 1
            except PaymentProcessingError:
                # 서비스가 남긴 재시도 상태를 보존한다. 실제 상태는 다음 주기에 다시 조회한다.
                await session.commit()
                logger.warning("결제 복구 재시도 필요: payment_id=%s", payment_id)
            except Exception:
                await session.rollback()
                logger.exception("결제 복구 실패: payment_id=%s", payment_id)
    return completed


async def _loop() -> None:
    while True:
        try:
            await run_recovery_once()
        except Exception:
            logger.exception("결제 복구 조회 실패 (다음 주기에 재시도)")
        await asyncio.sleep(30)


def start_payment_recovery_job() -> asyncio.Task:
    return asyncio.create_task(_loop())
