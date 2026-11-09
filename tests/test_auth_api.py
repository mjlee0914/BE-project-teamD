import unittest
from typing import Annotated
from unittest.mock import AsyncMock

import httpx
from fastapi import Depends, FastAPI

from auth.application.service import AuthService
from auth.domain.entities import TokenPayload
from auth.domain.repository import TokenBlacklistRepository
from auth.domain.service import UserCredentialVerifier, UserStatusChecker
from auth.infrastructure.security import JwtTokenProvider
from auth.presentation.dependencies import get_current_user, provide_auth_service
from auth.presentation.router import router
from auth.presentation.schemas import LoginRequest
from shared.core.exception_handlers import register_exception_handlers
from shared.core.exceptions import UnauthorizedException
from users.domain.exceptions import InactiveUser


class AuthAPITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = FastAPI()
        register_exception_handlers(self.app)
        self.app.include_router(router)

        @self.app.get("/protected")
        async def protected(user: Annotated[TokenPayload, Depends(get_current_user)]):
            return {"user_id": user.user_id}

        self.blocked = set()
        self.blacklist = AsyncMock(spec=TokenBlacklistRepository)
        self.blacklist.is_blacklisted.side_effect = lambda jti: jti in self.blocked

        async def add(jti, user_id):
            self.blocked.add(jti)

        self.blacklist.add.side_effect = add
        self.credentials = AsyncMock(spec=UserCredentialVerifier)
        self.credentials.verify_credentials.return_value = 10
        self.status_checker = AsyncMock(spec=UserStatusChecker)
        self.provider = JwtTokenProvider("auth-api-test-only-secret-" * 4)
        self.service = AuthService(
            self.credentials, self.blacklist, self.provider, self.status_checker
        )
        self.app.dependency_overrides[provide_auth_service] = lambda: self.service
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app), base_url="http://test"
        )

    async def asyncTearDown(self):
        await self.client.aclose()

    async def login(self):
        return await self.client.post(
            "/v1/auth/login",
            json={"email": "user@example.com", "password": "Password1!"},
        )

    async def token_headers(self):
        response = await self.login()
        return {"Authorization": "Bearer " + response.json()["data"]["access_token"]}

    async def test_login_returns_token_in_common_envelope_without_caching(self):
        response = await self.login()
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["token_type"], "bearer")
        self.assertEqual(data["data"]["expires_in"], 3600)
        self.assertEqual(
            self.provider.decode_token(data["data"]["access_token"]).user_id, 10
        )
        self.assertNotIn("Password1!", response.text)
        self.assertEqual(response.headers["cache-control"], "no-store")

    async def test_login_normalizes_email_without_changing_password(self):
        response = await self.client.post(
            "/v1/auth/login",
            json={"email": " USER@EXAMPLE.COM ", "password": " password "},
        )
        self.assertEqual(response.status_code, 200)
        self.credentials.verify_credentials.assert_awaited_once_with(
            "user@example.com", " password "
        )

    async def test_wrong_credentials_return_401(self):
        self.credentials.verify_credentials.return_value = None
        response = await self.login()
        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.json()["success"])
        self.assertNotIn("access_token", response.text)

    async def test_withdrawn_login_returns_403(self):
        self.credentials.verify_credentials.side_effect = InactiveUser()
        self.assertEqual((await self.login()).status_code, 403)

    async def test_invalid_login_body_is_rejected_without_echoing_password(self):
        for body in (
            {"email": "invalid", "password": "SensitivePassword1!"},
            {"email": "user@example.com", "password": ""},
            {"email": "user@example.com", "password": 12345},
            {
                "email": "user@example.com",
                "password": "SensitivePassword1!",
                "role": "ADMIN",
            },
        ):
            with self.subTest(fields=list(body)):
                response = await self.client.post("/v1/auth/login", json=body)
                self.assertEqual(response.status_code, 422)
                self.assertNotIn("SensitivePassword1!", response.text)
        self.credentials.verify_credentials.assert_not_awaited()

    async def test_password_is_hidden_from_request_repr(self):
        request = LoginRequest(email="user@example.com", password="SensitivePassword1!")
        self.assertNotIn("SensitivePassword1!", repr(request))

    async def test_protected_route_checks_current_user(self):
        response = await self.client.get(
            "/protected", headers=await self.token_headers()
        )
        self.assertEqual(response.json(), {"user_id": 10})
        self.status_checker.ensure_active.assert_awaited_once_with(10)

    async def test_missing_or_wrong_scheme_is_401(self):
        for headers in (
            {},
            {"Authorization": "Basic credentials"},
            {"Authorization": "Bearer"},
        ):
            for path in ("/protected", "/v1/auth/logout"):
                with self.subTest(path=path, has_header=bool(headers)):
                    response = await self.client.request(
                        "GET" if path == "/protected" else "POST", path, headers=headers
                    )
                    self.assertEqual(response.status_code, 401)
                    self.assertEqual(response.headers.get("www-authenticate"), "Bearer")

    async def test_invalid_token_is_401(self):
        response = await self.client.get(
            "/protected", headers={"Authorization": "Bearer invalid-token"}
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.headers.get("www-authenticate"), "Bearer")
        self.status_checker.ensure_active.assert_not_awaited()

    async def test_logout_rejects_invalid_token_without_adding_blacklist(self):
        response = await self.client.post(
            "/v1/auth/logout", headers={"Authorization": "Bearer invalid-token"}
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.headers.get("www-authenticate"), "Bearer")
        self.blacklist.add.assert_not_awaited()

    async def test_logout_revokes_token_and_duplicate_logout_has_empty_response(self):
        headers = await self.token_headers()
        for _ in range(2):
            response = await self.client.post("/v1/auth/logout", headers=headers)
            self.assertEqual(response.status_code, 204)
            self.assertEqual(response.content, b"")
        self.assertEqual(
            (await self.client.get("/protected", headers=headers)).status_code, 401
        )
        self.blacklist.add.assert_awaited_once()

    async def test_withdrawn_user_is_blocked_but_can_logout(self):
        headers = await self.token_headers()
        self.status_checker.ensure_active.side_effect = InactiveUser()
        self.assertEqual(
            (await self.client.get("/protected", headers=headers)).status_code, 403
        )
        self.assertEqual(
            (await self.client.post("/v1/auth/logout", headers=headers)).status_code,
            204,
        )

    async def test_deleted_user_is_401(self):
        headers = await self.token_headers()
        self.status_checker.ensure_active.side_effect = UnauthorizedException()
        self.assertEqual(
            (await self.client.get("/protected", headers=headers)).status_code, 401
        )

    async def test_unwired_service_returns_503(self):
        headers = await self.token_headers()
        self.app.dependency_overrides.clear()
        self.assertEqual((await self.login()).status_code, 503)
        self.assertEqual(
            (await self.client.get("/protected", headers=headers)).status_code, 503
        )
