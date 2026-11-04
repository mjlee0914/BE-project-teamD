import os
import unittest
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from auth.infrastructure.security import JwtTokenProvider
from auth.presentation.dependencies import provide_auth_service
from auth.presentation.routers.v1.router import router
from auth.wiring import build_auth_service, get_token_provider, wire_auth_dependencies
from payments.application.service import PaymentService
from payments.domain.entities import Payment, PaymentStatus
from payments.presentation.dependencies import get_payment_service
from payments.presentation.router import router as payment_router
from shared.core.database import get_db


class AuthWiringTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = AsyncMock(spec=AsyncSession)
        self.db.scalar.return_value = False
        self.tokens = JwtTokenProvider(
            "test-only-key-0123456789-abcdefghijklmnopqrstuvwxyz"
        )
        self.app = FastAPI()
        self.app.include_router(router)
        wire_auth_dependencies(self.app)

        async def session():
            yield self.db

        self.app.dependency_overrides[get_db] = session
        self.app.dependency_overrides[get_token_provider] = lambda: self.tokens
        self.client = TestClient(self.app, raise_server_exceptions=False)

    def tearDown(self) -> None:
        self.client.close()

    def test_repository_and_transaction_share_injected_session(self) -> None:
        service = build_auth_service(self.db, self.tokens)
        self.assertIs(service._token_provider, self.tokens)
        self.assertIs(service._blacklist_repo.db, self.db)
        self.assertIs(service._transaction.db, self.db)

    def test_logout_resolves_placeholder_through_wiring(self) -> None:
        response = self.client.post(
            "/v1/auth/logout",
            headers={"Authorization": f"Bearer {self.tokens.create_access_token(1)}"},
            json={"refresh_token": self.tokens.create_refresh_token(1)},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.db.execute.await_count, 2)
        self.db.commit.assert_awaited_once()

    def test_payments_share_auth_wiring_and_blocklist_guard(self) -> None:
        self.app.include_router(payment_router)
        service = AsyncMock(spec=PaymentService)
        now = datetime(2026, 11, 4, tzinfo=UTC)
        service.get_payment.return_value = Payment.restore(
            id=42,
            reservation_id=1,
            method="CARD",
            amount=50000,
            status=PaymentStatus.PAID,
            payment_key="mock-key",
            paid_at=now,
        )
        self.app.dependency_overrides[get_payment_service] = lambda: service
        headers = {"Authorization": f"Bearer {self.tokens.create_access_token(7)}"}
        self.assertEqual(
            self.client.get("/payments/42", headers=headers).status_code, 200
        )
        service.get_payment.assert_awaited_once_with(payment_id=42, user_id=7)
        service.get_payment.reset_mock()
        self.db.scalar.return_value = True
        self.assertEqual(
            self.client.get("/payments/42", headers=headers).status_code, 401
        )
        service.get_payment.assert_not_awaited()

    def test_unwired_placeholder_does_not_silently_create_service(self) -> None:
        app = FastAPI()
        app.include_router(router)
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post("/v1/auth/refresh", json={"refresh_token": "token"})
        self.assertEqual(response.status_code, 500)
        self.db.commit.assert_not_awaited()

    def test_secret_is_required_without_a_fallback_key(self) -> None:
        with (
            patch.dict(os.environ, {"JWT_SECRET_KEY": ""}),
            self.assertRaises(RuntimeError),
        ):
            get_token_provider()

    def test_wiring_is_safe_to_apply_twice(self) -> None:
        wire_auth_dependencies(self.app)
        self.assertIn(provide_auth_service, self.app.dependency_overrides)
        response = self.client.post(
            "/v1/auth/refresh",
            json={"refresh_token": self.tokens.create_refresh_token(1)},
        )
        self.assertEqual(response.status_code, 200)
