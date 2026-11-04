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
        self.headers = {"Authorization": f"Bearer {self.access}"}

    def tearDown(self) -> None:
        self.client.close()

    def logout(self):
        return self.client.post("/v1/auth/logout", headers=self.headers)

    def test_logout_blocks_access_immediately(self) -> None:
        self.assertEqual(
            self.client.get("/protected", headers=self.headers).status_code, 200
        )
        self.assertEqual(self.logout().status_code, 200)
        self.assertEqual(len(self.committed), 1)
        self.db.commit.assert_awaited_once()
        response = self.client.get("/protected", headers=self.headers)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.headers["WWW-Authenticate"], "Bearer")

    def test_repeated_logout_keeps_one_record(self) -> None:
        self.assertEqual(self.logout().status_code, 200)
        self.assertEqual(self.logout().status_code, 200)
        self.assertEqual(len(self.committed), 1)

    def test_refresh_endpoint_is_not_available(self) -> None:
        response = self.client.post("/v1/auth/refresh")
        self.assertEqual(response.status_code, 404)
        self.assertNotIn(
            "/v1/auth/refresh", self.client.get("/openapi.json").json()["paths"]
        )
        self.db.execute.assert_not_awaited()

    def test_invalid_access_is_rejected_before_saving(self) -> None:
        response = self.client.post(
            "/v1/auth/logout", headers={"Authorization": "Bearer not-a-token"}
        )
        self.assertEqual(response.status_code, 401)
        self.db.execute.assert_not_awaited()
        self.db.commit.assert_not_awaited()

    def test_missing_bearer_token_is_rejected(self) -> None:
        self.assertEqual(self.client.get("/protected").status_code, 401)
        response = self.client.post("/v1/auth/logout")
        self.assertEqual(response.status_code, 401)
        self.db.execute.assert_not_awaited()

    def test_save_failure_rolls_back(self) -> None:
        self.db.execute.side_effect = RuntimeError("save failed")
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

    def test_lookup_failure_does_not_allow_access(self) -> None:
        self.db.scalar.side_effect = RuntimeError("lookup failed")
        self.assertEqual(
            self.client.get("/protected", headers=self.headers).status_code, 500
        )
