"""RUN_AUTH_POSTGRES_TESTS=1에서만 실제 PostgreSQL을 검사하고 전체 테스트 스키마를 롤백한다."""

import os
import unittest
from pathlib import Path
from typing import Annotated
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from dotenv import load_dotenv
from sqlalchemy import delete, func, insert, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from auth.application.service import AuthService
from auth.domain.entities import TokenPayload
from auth.domain.exceptions import TokenBlacklistConflict
from auth.domain.service import UserCredentialVerifier
from auth.infrastructure.credentials_verifier import RepositoryUserCredentialVerifier
from auth.infrastructure.factory import create_auth_service
from auth.infrastructure.models import TokenBlacklistModel
from auth.infrastructure.password_hasher import BcryptPasswordHasher
from auth.infrastructure.repositories import SqlAlchemyTokenBlacklistRepository
from auth.infrastructure.security import JwtTokenProvider
from auth.infrastructure.user_status_checker import RepositoryUserStatusChecker
from shared.core.exceptions import UnauthorizedException
from shared.core.models import Base
from users.domain.enums import UserStatus
from users.domain.exceptions import InactiveUser
from users.domain.service import PasswordHasher
from users.domain.user import User
from users.infrastructure.models import UserModel
from users.infrastructure.repositories import SqlAlchemyUserRepository


@unittest.skipUnless(
    os.getenv("RUN_AUTH_POSTGRES_TESTS") == "1",
    "auth PostgreSQL 검증은 명시적으로 실행",
)
class TokenBlacklistPostgresTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        load_dotenv(Path(__file__).resolve().parents[1] / ".env")
        raw = os.getenv("AUTH_TEST_DATABASE_URL") or os.getenv("DATABASE_URL")
        if not raw:
            self.fail("PostgreSQL 테스트 연결 설정이 필요합니다.")
        self.engine = create_async_engine(
            make_url(raw).set(drivername="postgresql+asyncpg"),
            poolclass=NullPool,
            connect_args={
                "timeout": 5,
                "server_settings": {
                    "statement_timeout": "10000",
                    "lock_timeout": "3000",
                },
            },
        )
        self.addAsyncCleanup(self.engine.dispose)
        self.connection = await self.engine.connect()
        self.addAsyncCleanup(self.connection.close)
        self.transaction = await self.connection.begin()
        self.schema = "auth_test_" + uuid4().hex

        async def rollback_and_verify():
            if self.transaction.is_active:
                await self.transaction.rollback()
            exists = await self.connection.scalar(
                text("SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname=:name)"),
                {"name": self.schema},
            )
            self.assertFalse(exists, "auth 테스트 스키마가 남아 있습니다.")
            await self.connection.rollback()

        self.addAsyncCleanup(rollback_and_verify)
        await self.connection.execute(text(f'CREATE SCHEMA "{self.schema}"'))
        await self.connection.execution_options(
            schema_translate_map={None: self.schema}
        )
        await self.connection.run_sync(
            lambda connection: Base.metadata.create_all(
                connection, tables=[UserModel.__table__, TokenBlacklistModel.__table__]
            )
        )
        self.user_id = await self.connection.scalar(
            insert(UserModel)
            .values(
                email="auth-test@example.com",
                name="Auth Test",
                password_hash="test-only-hash",
            )
            .returning(UserModel.id)
        )
        self.session = AsyncSession(
            bind=self.connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        self.addAsyncCleanup(self.session.close)
        self.repo = SqlAlchemyTokenBlacklistRepository(self.session)

    async def test_add_and_lookup(self):
        self.assertFalse(await self.repo.is_blacklisted("test-jti"))
        await self.repo.add("test-jti", self.user_id)
        self.assertTrue(await self.repo.is_blacklisted("test-jti"))
        self.assertFalse(await self.repo.is_blacklisted("another-jti"))

    async def test_duplicate_logout_does_not_insert_duplicate_row(self):
        await self.repo.add("test-jti", self.user_id)
        await self.repo.add("test-jti", self.user_id)
        count = await self.session.scalar(
            select(func.count()).select_from(TokenBlacklistModel)
        )
        self.assertEqual(count, 1)

    async def test_multiple_tokens_for_one_user_are_allowed(self):
        await self.repo.add("first-jti", self.user_id)
        await self.repo.add("second-jti", self.user_id)
        count = await self.session.scalar(
            select(func.count()).select_from(TokenBlacklistModel)
        )
        self.assertEqual(count, 2)

    async def test_existing_owner_is_not_overwritten(self):
        other_id = await self.session.scalar(
            insert(UserModel)
            .values(
                email="other@example.com",
                name="Other User",
                password_hash="test-only-hash",
            )
            .returning(UserModel.id)
        )
        await self.repo.add("same-jti", self.user_id)
        with self.assertRaises(TokenBlacklistConflict):
            await self.repo.add("same-jti", other_id)
        owner = await self.session.scalar(
            select(TokenBlacklistModel.user_id).where(
                TokenBlacklistModel.jti == "same-jti"
            )
        )
        self.assertEqual(owner, self.user_id)

    async def test_foreign_key_rejects_nonexistent_user(self):
        with self.assertRaises(IntegrityError):
            await self.repo.add("test-jti", 2**63 - 1)
        await self.session.rollback()

    async def test_caller_rollback_removes_blacklist_entry(self):
        await self.repo.add("test-jti", self.user_id)
        await self.session.rollback()
        self.assertFalse(await self.repo.is_blacklisted("test-jti"))

    async def test_real_jwt_and_repository_reject_token_after_logout(self):
        verifier = AsyncMock(spec=UserCredentialVerifier)
        verifier.verify_credentials.return_value = self.user_id
        service = AuthService(
            verifier,
            self.repo,
            JwtTokenProvider("test-only-auth-key-" * 4),
            RepositoryUserStatusChecker(SqlAlchemyUserRepository(self.session)),
        )
        first = (await service.login("auth-test@example.com", "test-password"))[0]
        second = (await service.login("auth-test@example.com", "test-password"))[0]
        self.assertEqual(
            (await service.authenticate_token(first)).user_id, self.user_id
        )
        await service.logout(first)
        await service.logout(first)
        await self.session.commit()
        with self.assertRaises(UnauthorizedException):
            await service.authenticate_token(first)
        self.assertEqual(
            (await service.authenticate_token(second)).user_id, self.user_id
        )

    async def test_credential_verifier_with_real_user_repository(self):
        hasher = Mock(spec=PasswordHasher)
        hasher.verify.side_effect = lambda plain, hashed: (
            plain == "correct-password" and hashed == "test-only-hash"
        )
        verifier = RepositoryUserCredentialVerifier(
            SqlAlchemyUserRepository(self.session), hasher
        )
        self.assertEqual(
            await verifier.verify_credentials(
                " AUTH-TEST@EXAMPLE.COM ", "correct-password"
            ),
            self.user_id,
        )
        self.assertIsNone(
            await verifier.verify_credentials("auth-test@example.com", "wrong-password")
        )
        model = await self.session.get(UserModel, self.user_id)
        model.status = UserStatus.WITHDRAWN
        await self.session.flush()
        with self.assertRaises(InactiveUser):
            await verifier.verify_credentials(
                "auth-test@example.com", "correct-password"
            )

    async def test_token_is_rejected_after_user_withdrawal_in_database(self):
        provider = JwtTokenProvider("test-only-status-key-" * 4)
        token = provider.create_access_token(self.user_id)[0]
        verifier = AsyncMock(spec=UserCredentialVerifier)
        checker = RepositoryUserStatusChecker(SqlAlchemyUserRepository(self.session))
        service = AuthService(verifier, self.repo, provider, checker)
        await service.authenticate_token(token)
        await self.session.execute(
            update(UserModel)
            .where(UserModel.id == self.user_id)
            .values(status=UserStatus.WITHDRAWN)
        )
        await self.session.flush()
        # 다음 요청처럼 새 세션을 사용해 이전 ORM 객체 캐시와 분리한다.
        async with AsyncSession(
            bind=self.connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        ) as next_session:
            guarded = AuthService(
                verifier,
                SqlAlchemyTokenBlacklistRepository(next_session),
                provider,
                RepositoryUserStatusChecker(SqlAlchemyUserRepository(next_session)),
            )
            with self.assertRaises(InactiveUser):
                await guarded.authenticate_token(token)

    async def test_token_is_rejected_when_user_no_longer_exists(self):
        provider = JwtTokenProvider("test-only-status-key-" * 4)
        token = provider.create_access_token(self.user_id)[0]
        await self.session.execute(
            delete(UserModel).where(UserModel.id == self.user_id)
        )
        service = AuthService(
            AsyncMock(spec=UserCredentialVerifier),
            self.repo,
            provider,
            RepositoryUserStatusChecker(SqlAlchemyUserRepository(self.session)),
        )
        with self.assertRaises(UnauthorizedException):
            await service.authenticate_token(token)

    async def test_real_hash_factory_and_http_authentication_flow(self):
        import httpx
        from fastapi import Depends, FastAPI

        from auth.presentation.dependencies import (
            get_current_user,
            provide_auth_service,
        )
        from auth.presentation.routers.v1.router import router
        from shared.core.exception_handlers import register_exception_handlers

        hasher = BcryptPasswordHasher(rounds=4)
        users = SqlAlchemyUserRepository(self.session)
        saved = await users.save(
            User.create("real-hash@example.com", "Real Hash", "Password1!", hasher)
        )
        provider = JwtTokenProvider("real-hash-integration-test-key-" * 4)
        service = create_auth_service(self.session, provider, password_hasher=hasher)
        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(router)
        app.dependency_overrides[provide_auth_service] = lambda: service

        @app.get("/protected")
        async def protected(user: Annotated[TokenPayload, Depends(get_current_user)]):
            return {"user_id": user.user_id}

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            payload = {"email": " REAL-HASH@EXAMPLE.COM ", "password": "Password1!"}
            wrong = await client.post(
                "/v1/auth/login", json=payload | {"password": "WrongPassword1!"}
            )
            self.assertEqual(wrong.status_code, 401)
            response = await client.post("/v1/auth/login", json=payload)
            self.assertEqual(response.status_code, 200)
            headers = {
                "Authorization": "Bearer " + response.json()["data"]["access_token"]
            }
            self.assertEqual(
                (await client.get("/protected", headers=headers)).json(),
                {"user_id": saved.id},
            )
            for _ in range(2):
                self.assertEqual(
                    (await client.post("/v1/auth/logout", headers=headers)).status_code,
                    204,
                )
            self.assertEqual(
                (await client.get("/protected", headers=headers)).status_code, 401
            )
            second = await client.post("/v1/auth/login", json=payload)
            second_headers = {
                "Authorization": "Bearer " + second.json()["data"]["access_token"]
            }
            await self.session.execute(
                update(UserModel)
                .where(UserModel.id == saved.id)
                .values(status=UserStatus.WITHDRAWN)
            )
            await self.session.flush()
            self.assertEqual(
                (await client.get("/protected", headers=second_headers)).status_code,
                403,
            )
            self.assertEqual(
                (await client.post("/v1/auth/login", json=payload)).status_code, 403
            )

    async def test_password_change_uses_same_implementation_as_login(self):
        hasher = BcryptPasswordHasher(rounds=4)
        users = SqlAlchemyUserRepository(self.session)
        user = await users.save(
            User.create(
                "password-change@example.com", "Password Change", "Password1!", hasher
            )
        )
        service = create_auth_service(
            self.session,
            JwtTokenProvider("password-change-test-key-" * 4),
            password_hasher=hasher,
        )
        await service.login(user.email, "Password1!")
        user.change_password("Password1!", "NewPassword2!", hasher)
        await users.save(user)
        with self.assertRaises(UnauthorizedException):
            await service.login(user.email, "Password1!")
        self.assertEqual(
            (await service.login(user.email, "NewPassword2!"))[1], "bearer"
        )
