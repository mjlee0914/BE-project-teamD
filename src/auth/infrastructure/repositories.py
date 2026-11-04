from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from auth.domain.entities import BlacklistToken
from auth.domain.repository import TokenBlacklistRepository
from auth.infrastructure.models import TokenBlacklistModel


class SqlAlchemyTokenBlacklistRepository(TokenBlacklistRepository):
    """차단 토큰의 DB 저장과 조회를 담당합니다. 커밋은 서비스가 수행합니다."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def add(self, jti: str, user_id: int) -> None:
        """같은 jti가 이미 저장되어 있으면 기존 차단 기록을 유지합니다."""
        entry = BlacklistToken(jti=jti, user_id=user_id)
        statement = (
            insert(TokenBlacklistModel)
            .values(jti=entry.jti, user_id=entry.user_id)
            .on_conflict_do_nothing(index_elements=[TokenBlacklistModel.jti])
        )
        await self.db.execute(statement)

    async def find_by_jti(self, jti: str) -> BlacklistToken | None:
        """DB 조회 결과를 순수 도메인 객체로 변환합니다."""
        statement = select(TokenBlacklistModel).where(TokenBlacklistModel.jti == jti)
        model = await self.db.scalar(statement)
        if model is None:
            return None
        return BlacklistToken(jti=model.jti, user_id=model.user_id)

    async def is_blacklisted(self, jti: str) -> bool:
        """인증 처리에서 사용할 차단 여부만 조회합니다."""
        statement = select(
            select(TokenBlacklistModel.jti)
            .where(TokenBlacklistModel.jti == jti)
            .exists()
        )
        return bool(await self.db.scalar(statement))
