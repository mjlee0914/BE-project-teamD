import unittest
from unittest.mock import AsyncMock, Mock

from sqlalchemy.ext.asyncio import AsyncSession

from auth.application.service import AuthService
from auth.domain.entities import TokenPayload, UnauthorizedException
from auth.domain.service import TokenProvider
from auth.infrastructure.repositories import SqlAlchemyTokenBlacklistRepository
from auth.infrastructure.transactions import SqlAlchemyTransactionManager


class AuthServiceTransactionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.db = AsyncMock(spec=AsyncSession)
        self.tokens = Mock(spec=TokenProvider)
        self.access = TokenPayload(user_id=1, jti="token-A")
        self.tokens.decode_token.return_value = self.access
        self.service = AuthService(
            SqlAlchemyTokenBlacklistRepository(self.db),
            self.tokens,
            SqlAlchemyTransactionManager(self.db),
        )

    async def test_logout_commits_after_save(self) -> None:
        await self.service.logout("access")
        self.assertEqual(
            [call[0] for call in self.db.mock_calls], ["execute", "commit"]
        )
        statement = self.db.execute.call_args_list[0].args[0]
        self.assertEqual(statement.compile().params, {"jti": "token-A", "user_id": 1})
        self.db.rollback.assert_not_awaited()

    async def test_save_failure_rolls_back_and_propagates(self) -> None:
        error = RuntimeError("save failed")
        self.db.execute.side_effect = error
        with self.assertRaises(RuntimeError) as caught:
            await self.service.logout("access")
        self.assertIs(caught.exception, error)
        self.db.commit.assert_not_awaited()
        self.db.rollback.assert_awaited_once()

    async def test_commit_failure_rolls_back_and_propagates(self) -> None:
        error = RuntimeError("commit failed")
        self.db.commit.side_effect = error
        with self.assertRaises(RuntimeError) as caught:
            await self.service.logout("access")
        self.assertIs(caught.exception, error)
        self.assertEqual(
            [call[0] for call in self.db.mock_calls],
            ["execute", "commit", "rollback"],
        )

    async def test_invalid_token_does_not_touch_database(self) -> None:
        self.tokens.decode_token.side_effect = UnauthorizedException("invalid token")
        with self.assertRaises(UnauthorizedException):
            await self.service.logout("invalid")
        self.assertEqual(self.db.mock_calls, [])

    async def test_authentication_uses_blacklist_result(self) -> None:
        self.db.scalar.return_value = False
        self.assertIs(await self.service.authenticate_token("access"), self.access)
        self.db.scalar.return_value = True
        with self.assertRaises(UnauthorizedException):
            await self.service.authenticate_token("access")
        self.db.commit.assert_not_awaited()

    async def test_lookup_failure_is_not_treated_as_unblocked(self) -> None:
        error = RuntimeError("lookup failed")
        self.db.scalar.side_effect = error
        with self.assertRaises(RuntimeError) as caught:
            await self.service.authenticate_token("access")
        self.assertIs(caught.exception, error)
