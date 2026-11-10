import unittest
from unittest.mock import AsyncMock

import httpx
from fastapi import FastAPI

from auth.application.service import AuthService
from auth.domain.entities import TokenPayload
from payments.application.service import PaymentService
from payments.domain.entities import Payment
from payments.domain.exceptions import PaymentNotFoundException, PaymentProcessingError
from payments.domain.service import PaymentAccessChecker, RefundAccount
from payments.presentation.dependencies import (
    provide_auth_service,
    provide_payment_access_checker,
    provide_payment_service,
)
from payments.presentation.routers.v1.router import router
from shared.core.exception_handlers import register_exception_handlers
from shared.core.exceptions import (
    ForbiddenException,
    UnauthorizedException,
)


class PaymentAPITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = FastAPI()
        register_exception_handlers(self.app)
        self.app.include_router(router)

        self.payment = Payment.create(1, "Festival", 1000)
        self.payment.payment_id = 7
        self.service = AsyncMock(spec=PaymentService)
        self.service.get_payment.return_value = self.payment
        self.service.get_payments.return_value = [self.payment]
        self.service.approve.return_value = self.payment
        self.service.cancel.return_value = self.payment
        self.service.reconcile.return_value = self.payment
        self.access = AsyncMock(spec=PaymentAccessChecker)
        self.auth = AsyncMock(spec=AuthService)
        self.auth.authenticate_token.return_value = TokenPayload(
            user_id=10, jti="test-jti"
        )
        self.app.dependency_overrides.update(
            {
                provide_auth_service: lambda: self.auth,
                provide_payment_service: lambda: self.service,
                provide_payment_access_checker: lambda: self.access,
            }
        )
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app), base_url="http://test"
        )
        self.headers = {"Authorization": "Bearer verified-token"}

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_get_verifies_token_and_owner_and_filters_sensitive_fields(self):
        self.payment.payment_key = "private-key"
        self.payment.failed_reason = "private-message"
        response = await self.client.get("/v1/payments/7", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.auth.authenticate_token.assert_awaited_once_with("verified-token")
        self.access.ensure_owner.assert_awaited_once_with(1, 10)
        data = response.json()["data"]
        self.assertEqual(data["payment_id"], 7)
        self.assertIsNone(data["updated_at"])
        self.assertIn("canceled_at", data)
        self.assertNotIn("cancelled_at", data)
        self.assertNotIn("payment_key", data)
        self.assertNotIn("failed_reason", data)
        self.assertNotIn("payment_log", data)

    async def test_missing_token_is_rejected(self):
        response = await self.client.get("/v1/payments/7")
        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.json()["success"])
        self.assertEqual(response.json()["code"], "UNAUTHORIZED")
        self.assertEqual(response.headers.get("www-authenticate"), "Bearer")
        self.service.get_payment.assert_not_awaited()

    async def test_invalid_token_is_rejected(self):
        self.auth.authenticate_token.side_effect = UnauthorizedException()
        response = await self.client.get("/v1/payments/7", headers=self.headers)
        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.json()["success"])
        self.assertEqual(response.json()["code"], "UNAUTHORIZED")
        self.assertEqual(response.headers.get("www-authenticate"), "Bearer")
        self.service.get_payment.assert_not_awaited()

    async def test_unconfigured_dependencies_do_not_allow_payment(self):
        self.app.dependency_overrides.clear()
        response = await self.client.get("/v1/payments/7", headers=self.headers)
        self.assertEqual(response.status_code, 503)
        self.service.get_payment.assert_not_awaited()

    async def test_non_owner_cannot_approve_or_cancel(self):
        self.access.ensure_owner.side_effect = ForbiddenException()
        for action, body in (
            ("approve", {"payment_key": "key", "amount": 1000}),
            ("cancel", {"reason": "customer request"}),
        ):
            with self.subTest(action=action):
                response = await self.client.post(
                    f"/v1/payments/7/{action}", json=body, headers=self.headers
                )
                self.assertEqual(response.status_code, 403)
        self.service.approve.assert_not_awaited()
        self.service.cancel.assert_not_awaited()

    async def test_list_checks_reservation_owner(self):
        response = await self.client.get(
            "/v1/payments?reservation_id=1", headers=self.headers
        )
        self.assertEqual(response.status_code, 200)
        self.access.ensure_owner.assert_awaited_once_with(1, 10)
        self.assertEqual(len(response.json()["data"]), 1)

    async def test_non_owner_cannot_list(self):
        self.access.ensure_owner.side_effect = ForbiddenException()
        response = await self.client.get(
            "/v1/payments?reservation_id=1", headers=self.headers
        )
        self.assertEqual(response.status_code, 403)
        self.service.get_payments.assert_not_awaited()

    async def test_approval_delegates_after_owner_check(self):
        response = await self.client.post(
            "/v1/payments/7/approve",
            json={"payment_key": "key", "amount": 1000},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        self.service.approve.assert_awaited_once_with(7, "key", 1000)

    async def test_cancellation_converts_refund_account(self):
        response = await self.client.post(
            "/v1/payments/7/cancel",
            headers=self.headers,
            json={
                "reason": "customer request",
                "refund_account": {
                    "bank": "088",
                    "account_number": "12345",
                    "holder_name": "Test",
                },
            },
        )
        self.assertEqual(response.status_code, 200)
        self.service.cancel.assert_awaited_once_with(
            7,
            reason="customer request",
            refund_account=RefundAccount("088", "12345", "Test"),
        )

    async def test_invalid_approval_body_never_calls_processor(self):
        for body in (
            {"payment_key": "key", "amount": 0},
            {"payment_key": "key", "amount": True},
            {"payment_key": "key", "amount": "1000"},
            {"payment_key": "has space", "amount": 1000},
            {"payment_key": "key", "amount": 1000, "user_id": 99},
        ):
            with self.subTest(body=body):
                response = await self.client.post(
                    "/v1/payments/7/approve", json=body, headers=self.headers
                )
                self.assertEqual(response.status_code, 422)
        self.service.approve.assert_not_awaited()

    async def test_provider_error_returns_uncertain_result_without_raw_message(self):
        self.service.approve.side_effect = PaymentProcessingError(
            "sensitive message", code="TOSS_NETWORK_ERROR", outcome_unknown=True
        )
        response = await self.client.post(
            "/v1/payments/7/approve",
            json={"payment_key": "key", "amount": 1000},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 502)
        self.assertTrue(response.json()["errors"]["outcome_unknown"])
        self.assertNotIn("sensitive message", response.text)

    async def test_missing_payment_returns_not_found(self):
        self.service.get_payment.side_effect = PaymentNotFoundException()
        response = await self.client.get("/v1/payments/7", headers=self.headers)
        self.assertEqual(response.status_code, 404)
        self.access.ensure_owner.assert_not_awaited()

    async def test_owner_can_request_reconciliation(self):
        response = await self.client.post(
            "/v1/payments/7/reconcile",
            headers=self.headers,
            json={"payment_key": "key"},
        )
        self.assertEqual(response.status_code, 200)
        self.service.reconcile.assert_awaited_once_with(7, "key")

    async def test_non_owner_cannot_reconcile(self):
        self.access.ensure_owner.side_effect = ForbiddenException()
        response = await self.client.post(
            "/v1/payments/7/reconcile", headers=self.headers, json={}
        )
        self.assertEqual(response.status_code, 403)
        self.service.reconcile.assert_not_awaited()
