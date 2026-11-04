from auth.domain.entities import BlacklistToken, TokenPayload, UnauthorizedException
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

    async def refresh_access_token(self, refresh_token: str) -> str:
        payload = self._token_provider.decode_token(
            refresh_token, expected_type="refresh"
        )
        await self._check_blacklist(payload)
        return self._token_provider.create_access_token(payload.user_id)

    async def logout(self, token: str, refresh_token: str) -> None:
        """유효한 두 토큰을 검증한 뒤 한 트랜잭션으로 즉시 차단합니다."""
        payload = self._token_provider.decode_token(token)
        refresh = self._token_provider.decode_token(
            refresh_token, expected_type="refresh"
        )
        if payload.user_id != refresh.user_id:
            raise UnauthorizedException(
                "서로 다른 회원의 토큰으로 로그아웃할 수 없습니다."
            )
        entries = [
            BlacklistToken(jti=payload.jti, user_id=payload.user_id),
            BlacklistToken(jti=refresh.jti, user_id=refresh.user_id),
        ]
        try:
            for entry in entries:
                await self._blacklist_repo.add(jti=entry.jti, user_id=entry.user_id)
            await self._transaction.commit()
        except Exception:
            await self._transaction.rollback()
            raise

    async def _check_blacklist(self, payload: TokenPayload) -> None:
        if await self._blacklist_repo.is_blacklisted(payload.jti):
            raise UnauthorizedException("로그아웃 처리되어 사용할 수 없는 토큰입니다.")
