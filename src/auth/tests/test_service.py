import unittest
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

from sqlalchemy.ext.asyncio import AsyncSession

from auth.application.service import AuthService
from auth.domain.entities import TokenPayload
from auth.domain.service import TokenProvider
from auth.infrastructure.repositories import SqlAlchemyTokenBlacklistRepository
from auth.infrastructure.transactions import SqlAlchemyTransactionManager


class AuthServiceTransactionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.db = AsyncMock(spec=AsyncSession)
        self.tokens = Mock(spec=TokenProvider)
        now = datetime(2026, 11, 4, tzinfo=UTC)
        self.access = TokenPayload(user_id=1, jti="token-A", exp=now)
        self.refresh = TokenPayload(
            user_id=1, jti="token-R", exp=now, token_type="refresh"
        )
        self.tokens.decode_token.side_effect = lambda token, **kwargs: (
            self.refresh if kwargs.get("expected_type") == "refresh" else self.access
        )
        self.service = AuthService(
            SqlAlchemyTokenBlacklistRepository(self.db),
            self.tokens,
            SqlAlchemyTransactionManager(self.db),
        )

    async def test_registration_commits_after_both_saves(self) -> None:
        await self.service.logout("access", "refresh")
        self.assertEqual(
            [call[0] for call in self.db.mock_calls], ["execute", "execute", "commit"]
        )
        statement = self.db.execute.call_args_list[0].args[0]
        self.assertEqual(statement.compile().params, {"jti": "token-A", "user_id": 1})
        self.db.rollback.assert_not_awaited()

    async def test_save_failure_rolls_back_and_propagates(self) -> None:
        error = RuntimeError("save failed")
        self.db.execute.side_effect = error
        with self.assertRaises(RuntimeError) as caught:
            await self.service.logout("access", "refresh")
        self.assertIs(caught.exception, error)
        self.db.commit.assert_not_awaited()
        self.db.rollback.assert_awaited_once()

    async def test_commit_failure_rolls_back_and_propagates(self) -> None:
        error = RuntimeError("commit failed")
        self.db.commit.side_effect = error
        with self.assertRaises(RuntimeError) as caught:
            await self.service.logout("access", "refresh")
        self.assertIs(caught.exception, error)
        self.assertEqual(
            [call[0] for call in self.db.mock_calls],
            ["execute", "execute", "commit", "rollback"],
        )

    async def test_invalid_entry_does_not_touch_database(self) -> None:
        for jti, user_id in [("", 1), ("token-A", 0)]:
            with self.subTest(jti=jti, user_id=user_id):
                self.access = TokenPayload(
                    user_id=user_id, jti=jti, exp=self.access.exp
                )
                self.refresh = TokenPayload(
                    user_id=user_id,
                    jti="token-R",
                    exp=self.access.exp,
                    token_type="refresh",
                )
                with self.assertRaises(ValueError):
                    await self.service.logout("access", "refresh")
        self.assertEqual(self.db.mock_calls, [])

    async def test_authentication_uses_blacklist_result(self) -> None:
        self.db.scalar.return_value = False
        self.assertIs(await self.service.authenticate_token("access"), self.access)
        self.db.scalar.return_value = True
        with self.assertRaises(ValueError):
            await self.service.authenticate_token("access")
        self.db.commit.assert_not_awaited()

    async def test_lookup_failure_is_not_treated_as_unblocked(self) -> None:
        error = RuntimeError("lookup failed")
        self.db.scalar.side_effect = error
        with self.assertRaises(RuntimeError) as caught:
            await self.service.authenticate_token("access")
        self.assertIs(caught.exception, error)
