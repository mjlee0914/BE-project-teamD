import base64
import json
import unittest
from datetime import datetime
from unittest.mock import patch

import httpx

from payments.domain.enums import PaymentStatus
from payments.domain.exceptions import PaymentProcessingError
from payments.domain.service import RefundAccount
from payments.infrastructure.toss_service import TossPaymentProcessor


class TossPaymentProcessorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.requests = []
        self.response_status = 200
        self.response_body = {
            "paymentKey": "test-payment-key",
            "orderId": "order-test-001",
            "totalAmount": 1000,
            "status": "DONE",
            "approvedAt": "2026-11-09T12:00:00+09:00",
            "method": "가상계좌",
            "secret": "webhook-secret-must-not-be-logged",
            "card": {"number": "sensitive-card-data"},
        }
        self.network_error = None
        self.client = httpx.AsyncClient(transport=httpx.MockTransport(self.handle))
        self.processor = TossPaymentProcessor("test_sk_dummy", client=self.client)

    async def asyncTearDown(self):
        await self.client.aclose()

    def handle(self, request):
        self.requests.append(request)
        if self.network_error:
            raise self.network_error("mock transport error", request=request)
        if isinstance(self.response_body, bytes):
            return httpx.Response(self.response_status, content=self.response_body)
        return httpx.Response(self.response_status, json=self.response_body)

    async def approve(self):
        return await self.processor.approve("test-payment-key", "order-test-001", 1000)

    def cancellation_response(self):
        self.response_body.update(
            status="CANCELED",
            balanceAmount=0,
            cancels=[
                {
                    "cancelStatus": "DONE",
                    "cancelAmount": 1000,
                    "canceledAt": "2026-11-09T13:00:00+09:00",
                    "cancelReason": "private reason",
                }
            ],
        )

    async def test_confirm_request_auth_body_timeout_and_result(self):
        result = await self.approve()
        request = self.requests[0]
        expected_auth = base64.b64encode(b"test_sk_dummy:").decode()
        self.assertEqual(request.headers["Authorization"], f"Basic {expected_auth}")
        self.assertEqual(request.method, "POST")
        self.assertEqual(
            str(request.url), "https://api.tosspayments.com/v1/payments/confirm"
        )
        self.assertEqual(
            json.loads(request.content),
            {
                "paymentKey": "test-payment-key",
                "orderId": "order-test-001",
                "amount": 1000,
            },
        )
        self.assertEqual(request.extensions["timeout"]["read"], 15.0)
        self.assertEqual(result.status, PaymentStatus.DONE)
        self.assertEqual(result.method, "가상계좌")
        self.assertIsNotNone(result.paid_at.tzinfo)
        self.assertNotIn("secret", result.log.value)
        self.assertNotIn("card", result.log.value)
        self.assertFalse(self.client.is_closed)

    async def test_same_approval_uses_same_idempotency_key(self):
        await self.approve()
        await self.approve()
        keys = [request.headers["Idempotency-Key"] for request in self.requests]
        self.assertEqual(keys[0], keys[1])
        self.assertEqual(len(keys[0]), 64)

    async def test_virtual_account_approval_is_not_marked_paid(self):
        self.response_body.update(status="WAITING_FOR_DEPOSIT", approvedAt=None)
        self.response_body["virtualAccount"] = {"dueDate": "2027-01-02T15:05:00+09:00"}
        result = await self.approve()
        self.assertEqual(result.status, PaymentStatus.WAITING_FOR_DEPOSIT)
        self.assertIsNone(result.paid_at)
        self.assertIsNotNone(result.webhook_secret_hash)
        self.assertEqual(
            result.virtual_account_due_at,
            datetime.fromisoformat("2027-01-02T15:05:00+09:00"),
        )
        self.assertNotIn("webhook-secret", str(result))

    async def test_retrieve_uses_authenticated_get_and_parses_snapshot(self):
        result = await self.processor.retrieve("test-payment-key")
        self.assertEqual(self.requests[0].method, "GET")
        self.assertTrue(str(self.requests[0].url).endswith("/test-payment-key"))
        self.assertEqual(self.requests[0].content, b"")
        self.assertIn("Authorization", self.requests[0].headers)
        self.assertNotIn("Idempotency-Key", self.requests[0].headers)
        self.assertEqual(result.order_id, "order-test-001")
        self.assertEqual(result.amount, 1000)
        self.assertEqual(result.status, PaymentStatus.DONE)

    async def test_virtual_account_approval_requires_verification_secret(self):
        self.response_body.update(status="WAITING_FOR_DEPOSIT", approvedAt=None)
        self.response_body.pop("secret")
        with self.assertRaises(PaymentProcessingError):
            await self.approve()

    async def test_retrieve_cancelled_payment(self):
        self.cancellation_response()
        snapshot = await self.processor.retrieve("test-payment-key")
        self.assertEqual(snapshot.status, PaymentStatus.CANCELED)
        self.assertEqual(snapshot.canceled_at.hour, 13)

    async def test_mismatched_payment_identity_and_amount_are_rejected(self):
        for field, value in (
            ("paymentKey", "another-key"),
            ("orderId", "another-order"),
            ("totalAmount", 999),
            ("totalAmount", True),
        ):
            with self.subTest(field=field, value=value):
                original = self.response_body[field]
                self.response_body[field] = value
                with self.assertRaises(PaymentProcessingError) as caught:
                    await self.approve()
                self.assertTrue(caught.exception.outcome_unknown)
                self.response_body[field] = original

    async def test_invalid_status_or_timestamp_is_rejected(self):
        for field, value in (
            ("status", "ABORTED"),
            ("status", "UNKNOWN"),
            ("approvedAt", None),
            ("approvedAt", "not-a-date"),
            ("approvedAt", "2026-11-09T12:00:00"),
        ):
            with self.subTest(field=field, value=value):
                original = self.response_body[field]
                self.response_body[field] = value
                with self.assertRaises(PaymentProcessingError):
                    await self.approve()
                self.response_body[field] = original

    async def test_invalid_input_does_not_send_request(self):
        for key, order, amount in (
            ("", "order-test-001", 1000),
            ("has space", "order-test-001", 1000),
            ("key", "1", 1000),
            ("key", "order-test-001", 0),
            ("key", "order-test-001", True),
        ):
            with (
                self.subTest(key=key, order=order, amount=amount),
                self.assertRaises(ValueError),
            ):
                await self.processor.approve(key, order, amount)
        self.assertEqual(self.requests, [])

    async def test_provider_rejection_retains_code_without_raw_message(self):
        self.response_status = 400
        self.response_body = {"code": "INVALID_REQUEST", "message": "sensitive detail"}
        with self.assertRaises(PaymentProcessingError) as caught:
            await self.approve()
        self.assertEqual(caught.exception.code, "INVALID_REQUEST")
        self.assertEqual(caught.exception.http_status, 400)
        self.assertFalse(caught.exception.outcome_unknown)
        self.assertNotIn("sensitive detail", str(caught.exception))

    async def test_server_error_is_uncertain(self):
        self.response_status = 500
        self.response_body = {"code": "PROVIDER_ERROR"}
        with self.assertRaises(PaymentProcessingError) as caught:
            await self.approve()
        self.assertTrue(caught.exception.outcome_unknown)

    async def test_network_errors_are_not_retried_or_treated_as_definite_failure(self):
        for error in (httpx.ReadTimeout, httpx.ConnectError):
            with self.subTest(error=error):
                self.requests.clear()
                self.network_error = error
                with self.assertRaises(PaymentProcessingError) as caught:
                    await self.approve()
                self.assertEqual(caught.exception.code, "TOSS_NETWORK_ERROR")
                self.assertTrue(caught.exception.outcome_unknown)
                self.assertEqual(len(self.requests), 1)

    async def test_non_json_or_non_object_response_is_rejected(self):
        for body in (b"<html>error</html>", [1, 2]):
            with self.subTest(body=body):
                self.response_body = body
                with self.assertRaises(PaymentProcessingError):
                    await self.approve()

    async def test_full_cancellation_with_refund_account(self):
        self.cancellation_response()
        account = RefundAccount("088", "1234567890", "Test Holder")
        result = await self.processor.cancel(
            "test-payment-key", reason="Customer request", refund_account=account
        )
        body = json.loads(self.requests[0].content)
        self.assertTrue(str(self.requests[0].url).endswith("/test-payment-key/cancel"))
        self.assertEqual(body["cancelReason"], "Customer request")
        self.assertEqual(body["refundReceiveAccount"]["accountNumber"], "1234567890")
        self.assertNotIn("cancelAmount", body)
        self.assertEqual(result.canceled_at.hour, 13)
        self.assertNotIn("cancelReason", result.log.value["cancels"][0])
        self.assertNotIn("1234567890", json.dumps(result.log.value))

    async def test_partial_or_pending_cancellation_is_not_completed(self):
        self.cancellation_response()
        self.response_body["status"] = "PARTIAL_CANCELED"
        with self.assertRaises(PaymentProcessingError):
            await self.processor.cancel("test-payment-key")
        self.response_body["status"] = "CANCELED"
        self.response_body["cancels"][0]["cancelStatus"] = "IN_PROGRESS"
        with self.assertRaises(PaymentProcessingError):
            await self.processor.cancel("test-payment-key")

    async def test_invalid_refund_account_does_not_send_request(self):
        with self.assertRaises(ValueError):
            await self.processor.cancel(
                "test-payment-key",
                refund_account=RefundAccount("088", "123-45", "Test"),
            )
        self.assertEqual(self.requests, [])

    async def test_environment_configuration_and_missing_key(self):
        with (
            patch("payments.infrastructure.toss_service.load_dotenv"),
            patch.dict(
                "os.environ",
                {"TOSS_SECRET_KEY": "test_sk_dummy", "TOSS_TIMEOUT_SECONDS": "7"},
            ),
        ):
            processor = TossPaymentProcessor.from_env(client=self.client)
            await processor.approve("test-payment-key", "order-test-001", 1000)
        self.assertEqual(self.requests[0].extensions["timeout"]["read"], 7)
        with self.assertRaises(ValueError):
            TossPaymentProcessor("")
