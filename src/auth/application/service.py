from auth.domain.entities import TokenPayload, UnauthorizedException
from auth.domain.repository import TokenBlacklistRepository
from auth.domain.service import TokenProvider, TransactionManager


class AuthService:
    def __init__(
        self,
        token_blacklist_repo: TokenBlacklistRepository,
        token_provider: TokenProvider,
        transaction: TransactionManager,
    ) -> None:
        self._blacklist_repo = token_blacklist_repo
        self._token_provider = token_provider
        self._transaction = transaction

    async def authenticate_token(self, token: str) -> TokenPayload:
        payload = self._token_provider.decode_token(token)
        await self._check_blacklist(payload)
        return payload

    async def logout(self, token: str) -> None:
        """액세스 토큰을 검증하고 차단 기록 저장을 확정합니다."""
        payload = self._token_provider.decode_token(token)
        try:
            await self._blacklist_repo.add(jti=payload.jti, user_id=payload.user_id)
            await self._transaction.commit()
        except Exception:
            await self._transaction.rollback()
            raise

    async def _check_blacklist(self, payload: TokenPayload) -> None:
        if await self._blacklist_repo.is_blacklisted(payload.jti):
            raise UnauthorizedException("로그아웃 처리되어 사용할 수 없는 토큰입니다.")
