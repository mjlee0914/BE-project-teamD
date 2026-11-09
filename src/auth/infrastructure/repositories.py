# 파일 역할: 블랙리스트 계약을 PostgreSQL로 구현한다. SQL 반영은 flush까지이며 최종 commit은 요청 쪽 책임이다.

from sqlalchemy import exists, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from auth.domain.exceptions import TokenBlacklistConflict
from auth.domain.repository import TokenBlacklistRepository
from auth.infrastructure.models import TokenBlacklistModel


# 주입된 요청 세션으로만 SQL을 실행한다. 같은 세션을 공유해야 요청 전체를 함께 commit/rollback할 수 있다.
class SqlAlchemyTokenBlacklistRepository(TokenBlacklistRepository):
    """PostgreSQL 저장소. commit/rollback은 호출자의 요청 트랜잭션이 담당한다."""

    # 외부에서 전달받은 의존성을 보관한다. 여기서 DB 연결이나 업무 처리를 새로 시작하지 않는다.
    def __init__(self, session: AsyncSession):
        self._session = session

    # 충돌을 허용하는 INSERT로 동시 로그아웃을 처리하고, 기존 jti라면 소유자가 같은지 추가 확인한다.
    async def add(self, jti: str, user_id: int) -> None:
        if not isinstance(jti, str) or not jti.strip():
            raise ValueError("토큰 식별자가 필요합니다.")
        if type(user_id) is not int or not 1 <= user_id <= 2**63 - 1:
            raise ValueError("회원 ID는 양의 BIGINT 정수여야 합니다.")
        # 조회 후 INSERT 방식의 경쟁 조건을 피한다. 같은 토큰의 재등록은 성공으로 취급한다.
        result = await self._session.execute(
            insert(TokenBlacklistModel)
            .values(jti=jti, user_id=user_id)
            .on_conflict_do_nothing(index_elements=[TokenBlacklistModel.jti])
            .returning(TokenBlacklistModel.user_id)
        )
        # INSERT가 생략됐다면 기존 소유자를 읽는다. 동일 회원의 반복 등록만 정상으로 취급한다.
        inserted_user_id = result.scalar_one_or_none()
        if inserted_user_id is None:
            existing = await self._session.execute(
                select(TokenBlacklistModel.user_id).where(
                    TokenBlacklistModel.jti == jti
                )
            )
            if existing.scalar_one_or_none() != user_id:
                raise TokenBlacklistConflict
        # flush는 SQL 반영이지 최종 확정이 아니다. 로그아웃 응답 전 commit을 보장해야 한다.
        await self._session.flush()

    # 행 전체 대신 EXISTS 결과를 읽어 차단 여부를 True/False로 반환한다.
    async def is_blacklisted(self, jti: str) -> bool:
        result = await self._session.execute(
            select(exists().where(TokenBlacklistModel.jti == jti))
        )
        return bool(result.scalar_one())
