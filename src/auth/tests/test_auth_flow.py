import unittest
from typing import Annotated
from unittest.mock import AsyncMock

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from auth.domain.entities import TokenPayload
from auth.infrastructure.security import JwtTokenProvider
from auth.presentation.dependencies import (
    get_current_token,
    provide_auth_service,
)
from auth.presentation.routers.v1.router import router
from auth.wiring import build_auth_service


class AuthFlowTests(unittest.TestCase):
    """실제 JWT와 HTTP 라우터를 사용하되, DB 세션은 메모리로 모의합니다."""

    def setUp(self) -> None:
        self.committed = set()
        self.pending = set()
        self.db = AsyncMock(spec=AsyncSession)

        async def execute(statement):
            self.pending.add(statement.compile().params["jti"])

        async def scalar(statement):
            jti = next(iter(statement.compile().params.values()))
            return jti in self.committed

        async def commit():
            self.committed.update(self.pending)
            self.pending.clear()

        async def rollback():
            self.pending.clear()

        self.db.execute.side_effect = execute
        self.db.scalar.side_effect = scalar
        self.db.commit.side_effect = commit
        self.db.rollback.side_effect = rollback
        self.tokens = JwtTokenProvider(
            "test-only-key-0123456789-abcdefghijklmnopqrstuvwxyz"
        )
        self.service = build_auth_service(self.db, self.tokens)
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[provide_auth_service] = lambda: self.service

        @app.get("/protected")
        async def protected(
            claims: Annotated[TokenPayload, Depends(get_current_token)],
        ):
            return {"user_id": claims.user_id}

        self.client = TestClient(app, raise_server_exceptions=False)
        self.access = self.tokens.create_access_token(1)
        self.refresh = self.tokens.create_refresh_token(1)
        self.headers = {"Authorization": f"Bearer {self.access}"}

    def tearDown(self) -> None:
        self.client.close()

    def logout(self, refresh_token=None):
        return self.client.post(
            "/v1/auth/logout",
            headers=self.headers,
            json={"refresh_token": refresh_token or self.refresh},
        )

    def test_logout_blocks_access_and_refresh_immediately(self) -> None:
        self.assertEqual(
            self.client.get("/protected", headers=self.headers).status_code, 200
        )
        self.assertEqual(self.logout().status_code, 200)
        self.assertEqual(len(self.committed), 2)
        self.db.commit.assert_awaited_once()
        response = self.client.get("/protected", headers=self.headers)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.headers["WWW-Authenticate"], "Bearer")
        response = self.client.post(
            "/v1/auth/refresh", json={"refresh_token": self.refresh}
        )
        self.assertEqual(response.status_code, 401)

    def test_repeated_logout_keeps_two_records(self) -> None:
        self.assertEqual(self.logout().status_code, 200)
        self.assertEqual(self.logout().status_code, 200)
        self.assertEqual(len(self.committed), 2)

    def test_refresh_issues_a_new_access_token(self) -> None:
        response = self.client.post(
            "/v1/auth/refresh", json={"refresh_token": self.refresh}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["token_type"], "bearer")
        claims = self.tokens.decode_token(response.json()["access_token"])
        self.assertEqual(claims.user_id, 1)
        self.assertNotEqual(claims.jti, self.tokens.decode_token(self.access).jti)

    def test_different_members_tokens_are_rejected_before_saving(self) -> None:
        response = self.logout(self.tokens.create_refresh_token(2))
        self.assertEqual(response.status_code, 401)
        self.db.execute.assert_not_awaited()
        self.db.commit.assert_not_awaited()

    def test_invalid_refresh_is_rejected_before_saving(self) -> None:
        self.assertEqual(self.logout("not-a-token").status_code, 401)
        self.db.execute.assert_not_awaited()

    def test_missing_bearer_token_is_rejected(self) -> None:
        self.assertEqual(self.client.get("/protected").status_code, 401)
        response = self.client.post(
            "/v1/auth/logout", json={"refresh_token": self.refresh}
        )
        self.assertEqual(response.status_code, 401)
        self.db.execute.assert_not_awaited()

    def test_refresh_cannot_be_used_as_access(self) -> None:
        response = self.client.get(
            "/protected", headers={"Authorization": f"Bearer {self.refresh}"}
        )
        self.assertEqual(response.status_code, 401)

    def test_access_cannot_be_used_for_refresh(self) -> None:
        response = self.client.post(
            "/v1/auth/refresh", json={"refresh_token": self.access}
        )
        self.assertEqual(response.status_code, 401)

    def test_second_save_failure_rolls_back_both_records(self) -> None:
        save = self.db.execute.side_effect
        calls = 0

        async def fail_second_save(statement):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("save failed")
            await save(statement)

        self.db.execute.side_effect = fail_second_save
        self.assertEqual(self.logout().status_code, 500)
        self.assertEqual(self.committed, set())
        self.assertEqual(self.pending, set())
        self.db.commit.assert_not_awaited()
        self.db.rollback.assert_awaited_once()

    def test_commit_failure_does_not_return_logout_success(self) -> None:
        self.db.commit.side_effect = RuntimeError("commit failed")
        self.assertEqual(self.logout().status_code, 500)
        self.assertEqual(self.committed, set())
        self.assertEqual(self.pending, set())
        self.db.rollback.assert_awaited_once()

    def test_lookup_failure_does_not_allow_access_or_refresh(self) -> None:
        self.db.scalar.side_effect = RuntimeError("lookup failed")
        self.assertEqual(
            self.client.get("/protected", headers=self.headers).status_code, 500
        )
        response = self.client.post(
            "/v1/auth/refresh", json={"refresh_token": self.refresh}
        )
        self.assertEqual(response.status_code, 500)
