import unittest
from unittest.mock import AsyncMock, Mock

from auth.application.service import AuthService
from auth.domain.entities import TokenPayload, UnauthorizedException
from auth.domain.repository import TokenBlacklistRepository
from auth.domain.service import TokenProvider, TransactionManager


class AuthServicePortTests(unittest.IsolatedAsyncioTestCase):
    """DB·JWT 구체 구현체 없이 주입된 인터페이스로 서비스를 검사합니다."""

    def setUp(self) -> None:
        self.repository = AsyncMock(spec=TokenBlacklistRepository)
        self.repository.is_blacklisted.return_value = False
        self.tokens = Mock(spec=TokenProvider)
        self.transaction = AsyncMock(spec=TransactionManager)
        self.service = AuthService(self.repository, self.tokens, self.transaction)
        self.access = TokenPayload(user_id=1, jti="access-jti")
        self.tokens.decode_token.return_value = self.access

    async def test_logout_uses_injected_repository_and_transaction(self) -> None:
        await self.service.logout("access")
        self.assertEqual(
            self.repository.add.await_args_list[0].kwargs,
            {"jti": "access-jti", "user_id": 1},
        )
        self.repository.add.assert_awaited_once_with(jti="access-jti", user_id=1)
        self.transaction.commit.assert_awaited_once()
        self.transaction.rollback.assert_not_awaited()

    async def test_injected_provider_failure_prevents_storage(self) -> None:
        self.tokens.decode_token.side_effect = UnauthorizedException("expired")
        with self.assertRaises(UnauthorizedException):
            await self.service.logout("access")
        self.repository.add.assert_not_awaited()
        self.transaction.commit.assert_not_awaited()

    async def test_injected_blacklist_controls_authentication(self) -> None:
        self.repository.is_blacklisted.return_value = True
        with self.assertRaises(UnauthorizedException):
            await self.service.authenticate_token("access")
        self.repository.is_blacklisted.assert_awaited_once_with("access-jti")

    async def test_authenticated_payload_is_returned(self) -> None:
        self.assertIs(await self.service.authenticate_token("access"), self.access)
        self.tokens.decode_token.assert_called_once_with("access")
