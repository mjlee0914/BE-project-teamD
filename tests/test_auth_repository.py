import subprocess
import sys
import unittest
from unittest.mock import AsyncMock, Mock

from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.schema import CreateTable

from auth.domain.exceptions import TokenBlacklistConflict
from auth.infrastructure.models import TokenBlacklistModel
from auth.infrastructure.repositories import SqlAlchemyTokenBlacklistRepository
from users.infrastructure.models import UserModel


class TokenBlacklistRepositoryTests(unittest.IsolatedAsyncioTestCase):
    def test_init_models_registers_blacklist_in_fresh_process(self):
        # 다른 테스트의 auth import로 우연히 등록되지 않도록 새 프로세스에서 초기화 함수만 검사한다.
        subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "from shared.core.models import Base, init_models; "
                    "init_models(); "
                    "assert 'auth' in Base.metadata.tables; "
                    "assert 'users' in Base.metadata.tables"
                ),
            ],
            check=True,
            capture_output=True,
            text=True,
        )

    async def asyncSetUp(self):
        self.session = AsyncMock(spec=AsyncSession)
        self.repo = SqlAlchemyTokenBlacklistRepository(self.session)

    async def test_insert_is_idempotent_sql_without_commit(self):
        result = Mock()
        result.scalar_one_or_none.return_value = 10
        self.session.execute.return_value = result
        await self.repo.add("test-jti", 10)
        statement = self.session.execute.call_args.args[0]
        sql = str(statement.compile(dialect=postgresql.dialect()))
        self.assertIn("ON CONFLICT (jti) DO NOTHING", sql)
        self.assertIn("RETURNING auth.user_id", sql)
        self.session.flush.assert_awaited_once()
        self.session.commit.assert_not_awaited()

    async def test_duplicate_for_same_owner_succeeds(self):
        result, existing = Mock(), Mock()
        result.scalar_one_or_none.return_value = None
        existing.scalar_one_or_none.return_value = 10
        self.session.execute.side_effect = [result, existing]
        await self.repo.add("test-jti", 10)
        self.session.flush.assert_awaited_once()

    async def test_duplicate_cannot_replace_owner(self):
        result, existing = Mock(), Mock()
        result.scalar_one_or_none.return_value = None
        existing.scalar_one_or_none.return_value = 20
        self.session.execute.side_effect = [result, existing]
        with self.assertRaises(TokenBlacklistConflict):
            await self.repo.add("test-jti", 10)
        self.session.flush.assert_not_awaited()

    async def test_invalid_input_never_calls_database(self):
        for jti, user_id in (
            ("", 10),
            (" ", 10),
            ("jti", 0),
            ("jti", True),
            ("jti", 2**63),
        ):
            with self.subTest(jti=jti, user_id=user_id), self.assertRaises(ValueError):
                await self.repo.add(jti, user_id)
        self.session.execute.assert_not_awaited()

    async def test_existence_query_returns_boolean(self):
        result = Mock()
        self.session.execute.return_value = result
        for found in (True, False):
            result.scalar_one.return_value = found
            self.assertIs(await self.repo.is_blacklisted("test-jti"), found)

    def test_schema_matches_erd_and_allows_multiple_tokens_per_user(self):
        self.assertEqual(
            set(TokenBlacklistModel.__table__.columns.keys()), {"jti", "user_id"}
        )
        self.assertEqual(
            list(TokenBlacklistModel.__table__.primary_key.columns.keys()), ["jti"]
        )
        self.assertEqual(UserModel.__tablename__, "users")
        ddl = str(
            CreateTable(TokenBlacklistModel.__table__).compile(
                dialect=postgresql.dialect()
            )
        )
        self.assertIn("FOREIGN KEY(user_id) REFERENCES users (id)", ddl)
        self.assertNotIn("UNIQUE (user_id)", ddl)
