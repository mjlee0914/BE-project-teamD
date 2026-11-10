from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from payments.domain.service import PaymentTransaction


class SQLAlchemyPaymentTransaction(PaymentTransaction):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def checkpoint(self) -> None:
        await self._session.commit()

    @asynccontextmanager
    async def savepoint(self) -> AsyncIterator[None]:
        async with self._session.begin_nested():
            yield
