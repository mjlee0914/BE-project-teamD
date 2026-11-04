from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from payments.application.service import PaymentService
from shared.core.database import get_db


def get_payment_service(db: Annotated[AsyncSession, Depends(get_db)]) -> PaymentService:
    return PaymentService(db)
