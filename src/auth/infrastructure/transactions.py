from sqlalchemy.ext.asyncio import AsyncSession

from auth.domain.service import TransactionManager


class SqlAlchemyTransactionManager(TransactionManager):
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def commit(self) -> None:
        await self.db.commit()

    async def rollback(self) -> None:
        await self.db.rollback()
