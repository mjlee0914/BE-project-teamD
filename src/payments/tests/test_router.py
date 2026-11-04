import unittest
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import jwt
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from auth.infrastructure.security import JwtTokenProvider
from auth.presentation.dependencies import provide_auth_service
from auth.wiring import build_auth_service
from payments.application.service import PaymentService
from payments.domain.entities import Payment, PaymentStatus
from payments.presentation.dependencies import get_payment_service
from payments.presentation.router import router


class PaymentRouterTests(unittest.TestCase):
    """실제 JWT 인증과 라우터를 검사합니다. 결제 서비스와 DB는 모의 객체입니다."""

    def setUp(self) -> None:
        self.now = datetime(2026, 11, 3, tzinfo=UTC)
        self.key = "test-only-key-0123456789-abcdefghijklmnopqrstuvwxyz"
        self.tokens = JwtTokenProvider(self.key)
        self.auth_db = AsyncMock(spec=AsyncSession)
        self.auth_db.scalar.return_value = False
        auth = build_auth_service(self.auth_db, self.tokens)
        self.service = AsyncMock(spec=PaymentService)
        self.payment = Payment.restore(
            id=42,
            reservation_id=1,
            method="CARD",
            amount=50000,
            status=PaymentStatus.PAID,
            payment_key="mock-approved",
            paid_at=self.now,
            created_at=self.now,
        )
        self.service.pay.return_value = self.payment
        self.service.get_payment.return_value = self.payment
        self.service.cancel.return_value = Payment.restore(
            id=42,
            reservation_id=1,
            method="CARD",
            amount=50000,
            status=PaymentStatus.CANCELED,
            payment_key="mock-approved",
            paid_at=self.now,
            canceled_at=self.now,
            created_at=self.now,
        )
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_payment_service] = lambda: self.service
        app.dependency_overrides[provide_auth_service] = lambda: auth
        self.app = app
        self.client = TestClient(app, raise_server_exceptions=False)
        self.access = self.tokens.create_access_token(7)
        self.headers = {"Authorization": f"Bearer {self.access}"}
        self.payload = {
            "reservation_id": 1,
            "method": "CARD",
            "requested_amount": 50000,
        }

    def tearDown(self) -> None:
        self.client.close()

    def test_create_returns_serialized_payment_and_uses_authenticated_member(
        self,
    ) -> None:
        response = self.client.post(
            "/payments", headers=self.headers, json=self.payload
        )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["id"], 42)
        self.assertEqual(body["status"], "PAID")
        self.assertEqual(body["amount"], 50000)
        self.assertIsInstance(body["paid_at"], str)
        self.assertNotIn("payment_log", body)
        self.service.pay.assert_awaited_once_with(
            reservation_id=1,
            user_id=7,
            method="CARD",
            requested_amount=50000,
            simulate_failure=False,
        )

    def test_failed_attempt_is_created_with_failed_status(self) -> None:
        payment = Payment(reservation_id=1, method="CARD", amount=50000)
        payment.id = 43
        payment.fail("가상 결제 승인 실패")
        self.service.pay.return_value = payment
        response = self.client.post(
            "/payments",
            headers=self.headers,
            json={**self.payload, "simulate_failure": True},
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["status"], "FAILED")
        self.assertEqual(response.json()["fail_reason"], "가상 결제 승인 실패")
        self.assertTrue(self.service.pay.call_args.kwargs["simulate_failure"])

    def test_get_and_cancel_pass_member_identity(self) -> None:
        response = self.client.get("/payments/42", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.service.get_payment.assert_awaited_once_with(payment_id=42, user_id=7)
        response = self.client.patch("/payments/42/cancel", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "CANCELED")
        self.service.cancel.assert_awaited_once_with(payment_id=42, user_id=7)

    def test_all_routes_require_authentication(self) -> None:
        for method, path, kwargs in [
            ("post", "/payments", {"json": self.payload}),
            ("get", "/payments/42", {}),
            ("patch", "/payments/42/cancel", {}),
        ]:
            with self.subTest(path=path):
                response = getattr(self.client, method)(path, **kwargs)
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.headers["WWW-Authenticate"], "Bearer")
        self.service.pay.assert_not_awaited()
        self.service.get_payment.assert_not_awaited()
        self.service.cancel.assert_not_awaited()

    def test_blacklisted_access_is_rejected_before_payment_service(self) -> None:
        self.auth_db.scalar.return_value = True
        response = self.client.post(
            "/payments", headers=self.headers, json=self.payload
        )
        self.assertEqual(response.status_code, 401)
        self.service.pay.assert_not_awaited()

    def test_non_access_token_cannot_access_payment_api(self) -> None:
        payload = jwt.decode(self.access, self.key, algorithms=["HS256"])
        payload["token_type"] = "refresh"
        token = jwt.encode(payload, self.key, algorithm="HS256")
        response = self.client.post(
            "/payments", headers={"Authorization": f"Bearer {token}"}, json=self.payload
        )
        self.assertEqual(response.status_code, 401)
        self.service.pay.assert_not_awaited()

    def test_expired_token_is_rejected(self) -> None:
        payload = jwt.decode(self.access, self.key, algorithms=["HS256"])
        payload["exp"] = int(datetime.now(UTC).timestamp()) - 60
        token = jwt.encode(payload, self.key, algorithm="HS256")
        response = self.client.get(
            "/payments/42", headers={"Authorization": f"Bearer {token}"}
        )
        self.assertEqual(response.status_code, 401)
        self.service.get_payment.assert_not_awaited()

    def test_member_id_cannot_be_injected_in_request_body(self) -> None:
        response = self.client.post(
            "/payments",
            headers=self.headers,
            json={**self.payload, "user_id": 999},
        )
        self.assertEqual(response.status_code, 422)
        self.service.pay.assert_not_awaited()

    def test_invalid_input_is_rejected_before_service(self) -> None:
        for name, value in [
            ("reservation_id", 0),
            ("reservation_id", True),
            ("method", "   "),
            ("requested_amount", -1),
            ("requested_amount", True),
            ("requested_amount", 1.5),
            ("requested_amount", "50000"),
            ("simulate_failure", "true"),
        ]:
            with self.subTest(name=name, value=value):
                response = self.client.post(
                    "/payments",
                    headers=self.headers,
                    json={**self.payload, name: value},
                )
                self.assertEqual(response.status_code, 422)
        self.service.pay.assert_not_awaited()

    def test_zero_amount_is_accepted_by_request_schema(self) -> None:
        self.payment.amount = 0
        response = self.client.post(
            "/payments",
            headers=self.headers,
            json={**self.payload, "requested_amount": 0},
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.service.pay.call_args.kwargs["requested_amount"], 0)

    def test_invalid_path_id_is_rejected(self) -> None:
        for path in (
            "/payments/0",
            "/payments/-1",
            "/payments/abc",
            "/payments/0/cancel",
        ):
            with self.subTest(path=path):
                method = (
                    self.client.patch if path.endswith("/cancel") else self.client.get
                )
                self.assertEqual(method(path, headers=self.headers).status_code, 422)
        self.service.get_payment.assert_not_awaited()
        self.service.cancel.assert_not_awaited()

    def test_service_errors_are_mapped_for_each_route(self) -> None:
        for method, path, target, kwargs in [
            ("post", "/payments", self.service.pay, {"json": self.payload}),
            ("get", "/payments/42", self.service.get_payment, {}),
            ("patch", "/payments/42/cancel", self.service.cancel, {}),
        ]:
            for error, expected in [
                (PermissionError("권한 없음"), 403),
                (LookupError("기록 없음"), 404),
                (ValueError("조건 위반"), 400),
            ]:
                with self.subTest(path=path, status=expected):
                    target.side_effect = error
                    response = getattr(self.client, method)(
                        path, headers=self.headers, **kwargs
                    )
                    self.assertEqual(response.status_code, expected)
                    self.assertEqual(response.json()["detail"], str(error))
            target.side_effect = None

    def test_database_error_does_not_return_success_or_expose_details(self) -> None:
        self.service.pay.side_effect = RuntimeError("private-db-error")
        response = self.client.post(
            "/payments", headers=self.headers, json=self.payload
        )
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("private-db-error", response.text)

    def test_auth_lookup_failure_does_not_allow_payment(self) -> None:
        self.auth_db.scalar.side_effect = RuntimeError("lookup failed")
        response = self.client.post(
            "/payments", headers=self.headers, json=self.payload
        )
        self.assertEqual(response.status_code, 500)
        self.service.pay.assert_not_awaited()

    def test_openapi_documents_bearer_authentication_and_payment_status(self) -> None:
        schema = self.app.openapi()
        create = schema["paths"]["/payments"]["post"]
        self.assertIn("201", create["responses"])
        self.assertTrue(create["security"])
        self.assertEqual(
            schema["components"]["securitySchemes"]["HTTPBearer"]["scheme"], "bearer"
        )
        self.assertIn(
            "FAILED", schema["components"]["schemas"]["PaymentStatus"]["enum"]
        )
