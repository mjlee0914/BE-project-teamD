from typing import Annotated

from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from payments.application.service import PaymentService
from payments.application.webhook_service import DepositWebhookService
from payments.domain.service import PaymentAccessChecker, PaymentProcessor
from payments.infrastructure.access_checker import SQLAlchemyPaymentAccessChecker
from payments.infrastructure.sqlalchemy_repository import SQLAlchemyPaymentRepository
from payments.infrastructure.toss_service import TossPaymentProcessor
from payments.presentation.dependencies import (
    provide_payment_access_checker,
    provide_payment_service,
)
from payments.presentation.webhook_router import provide_deposit_webhook_service
from shared.core.database import get_db


# 결제 API 요청에 사용할 서비스를 조립한다.
# TossPaymentProcessor는 토스 API 통신을 맡고, 저장소는 같은 요청 세션으로 결제 정보를 조회·저장한다.
def build_payment_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PaymentService:
    processor: PaymentProcessor = TossPaymentProcessor.from_env()
    repository = SQLAlchemyPaymentRepository(session)
    return PaymentService(processor=processor, payment_repo=repository)


# 결제 소유권 확인기를 조립한다.
# 인증된 회원이 해당 예매에 연결된 결제에 접근할 권한이 있는지 DB에서 확인한다.
def build_payment_access_checker(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PaymentAccessChecker:
    return SQLAlchemyPaymentAccessChecker(session)


# 가상계좌 입금 웹훅 처리 서비스를 조립한다.
# 웹훅 자체의 내용만 믿지 않고 토스 결제 조회와 결제 저장소를 통해 최신 상태를 확인한다.
def build_deposit_webhook_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> DepositWebhookService:
    processor: PaymentProcessor = TossPaymentProcessor.from_env()
    repository = SQLAlchemyPaymentRepository(session)
    return DepositWebhookService(processor=processor, repository=repository)


# 결제 API, 소유권 검사, 입금 웹훅의 placeholder 의존성을 실제 구현체로 바꾼다.
# main.py에서 wire_dependencies(app)이 실행될 때 등록되어 각 요청에 맞는 서비스를 제공한다.
def wire_payment_dependencies(app: FastAPI) -> None:
    app.dependency_overrides.update(
        {
            provide_payment_service: build_payment_service,
            provide_payment_access_checker: build_payment_access_checker,
            provide_deposit_webhook_service: build_deposit_webhook_service,
        }
    )
