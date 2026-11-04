import unittest
from datetime import UTC, datetime
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
        now = datetime(2026, 11, 4, tzinfo=UTC)
        self.access = TokenPayload(user_id=1, jti="access-jti", exp=now)
        self.refresh = TokenPayload(
            user_id=1, jti="refresh-jti", exp=now, token_type="refresh"
        )
        self.tokens.decode_token.side_effect = lambda token, **kwargs: (
            self.refresh if kwargs.get("expected_type") == "refresh" else self.access
        )

    async def test_logout_uses_injected_repository_and_transaction(self) -> None:
        await self.service.logout("access", "refresh")
        self.assertEqual(
            self.repository.add.await_args_list[0].kwargs,
            {"jti": "access-jti", "user_id": 1},
        )
        self.assertEqual(
            self.repository.add.await_args_list[1].kwargs,
            {"jti": "refresh-jti", "user_id": 1},
        )
        self.transaction.commit.assert_awaited_once()
        self.transaction.rollback.assert_not_awaited()

    async def test_injected_provider_failure_prevents_storage(self) -> None:
        self.tokens.decode_token.side_effect = UnauthorizedException("expired")
        with self.assertRaises(UnauthorizedException):
            await self.service.logout("access", "refresh")
        self.repository.add.assert_not_awaited()
        self.transaction.commit.assert_not_awaited()

    async def test_injected_blacklist_controls_authentication(self) -> None:
        self.repository.is_blacklisted.return_value = True
        with self.assertRaises(UnauthorizedException):
            await self.service.authenticate_token("access")
        self.repository.is_blacklisted.assert_awaited_once_with("access-jti")

    async def test_different_users_are_rejected_without_writes(self) -> None:
        self.refresh = TokenPayload(
            user_id=2, jti="other-jti", exp=self.access.exp, token_type="refresh"
        )
        with self.assertRaises(UnauthorizedException):
            await self.service.logout("access", "refresh")
        self.repository.add.assert_not_awaited()
        self.transaction.commit.assert_not_awaited()
