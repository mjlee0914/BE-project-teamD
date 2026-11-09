import hashlib
import unittest
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from payments.application.service import PaymentService
from payments.application.webhook_service import DepositWebhookService
from payments.domain.entities import Payment, PaymentLog
from payments.domain.enums import PaymentStatus
from payments.domain.exceptions import (
    InvalidPaymentWebhook,
    PaymentConcurrentUpdate,
    PaymentIdentityConflict,
    PaymentProcessingError,
    PaymentStatusException,
)
from payments.domain.repository import PaymentRepository
from payments.domain.service import PaymentProcessor, PaymentSnapshot
from payments.presentation.webhook_router import provide_deposit_webhook_service, router
from shared.core.exceptions import SharedException


class DepositWebhookTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.secret = "known-provider-secret"
        self.saved = Payment.create(1, "Festival", 1000)
        self.saved.payment_id = 7
        self.saved.approve(
            "payment-key",
            1000,
            PaymentStatus.WAITING_FOR_DEPOSIT,
            None,
            PaymentLog({}),
            "가상계좌",
            hashlib.sha256(self.secret.encode()).hexdigest(),
        )
        self.repo = AsyncMock(spec=PaymentRepository)
        self.repo.find_by_order_id.side_effect = lambda _: deepcopy(self.saved)
        self.repo.find_by_id.side_effect = lambda _: deepcopy(self.saved)

        async def save(payment):
            self.saved = deepcopy(payment)
            return payment

        self.repo.save.side_effect = save
        self.processor = AsyncMock(spec=PaymentProcessor)
        self.snapshot = PaymentSnapshot(
            "payment-key",
            self.saved.order_id,
            1000,
            PaymentStatus.DONE,
            datetime.now(UTC),
            None,
            PaymentLog({"status": "DONE"}),
            "가상계좌",
        )
        self.processor.retrieve.return_value = self.snapshot
        self.service = DepositWebhookService(self.processor, self.repo)

    async def process(self, **overrides):
        body = {
            "order_id": self.saved.order_id,
            "secret": self.secret,
            "transaction_key": "txn-001",
            "status": PaymentStatus.DONE,
        }
        body.update(overrides)
        await self.service.process(**body)

    async def test_verified_deposit_requeries_and_records_paid_state(self):
        await self.process()
        self.processor.retrieve.assert_awaited_once_with("payment-key")
        self.assertEqual(self.saved.status, PaymentStatus.DONE)
        self.assertEqual(self.saved.paid_at, self.snapshot.paid_at)
        self.assertEqual(len(self.saved.processed_deposit_events), 1)
        self.assertNotIn(self.secret, repr(self.saved))
        self.assertNotIn(self.secret, str(self.saved.payment_log))

    async def test_duplicate_delivery_does_not_repeat_update_or_query(self):
        await self.process()
        await self.process()
        self.repo.save.assert_awaited_once()
        self.processor.retrieve.assert_awaited_once()

    async def test_invalid_or_missing_secret_is_rejected_before_provider_call(self):
        with self.assertRaises(InvalidPaymentWebhook):
            await self.process(secret="forged")
        self.saved.webhook_secret_hash = None
        with self.assertRaises(InvalidPaymentWebhook):
            await self.process()
        self.processor.retrieve.assert_not_awaited()
        self.repo.save.assert_not_awaited()

    async def test_query_failure_does_not_consume_event(self):
        self.processor.retrieve.side_effect = PaymentProcessingError("timeout")
        with self.assertRaises(PaymentProcessingError):
            await self.process()
        self.assertEqual(self.saved.processed_deposit_events, [])
        self.assertEqual(self.saved.status, PaymentStatus.WAITING_FOR_DEPOSIT)
        self.repo.save.assert_not_awaited()

    async def test_save_conflict_can_be_retried_without_losing_event(self):
        save = self.repo.save.side_effect
        self.repo.save.side_effect = PaymentConcurrentUpdate()
        with self.assertRaises(PaymentConcurrentUpdate):
            await self.process()
        self.assertEqual(self.saved.processed_deposit_events, [])
        self.repo.save.side_effect = save
        await self.process()
        self.assertEqual(self.saved.status, PaymentStatus.DONE)

    async def test_mismatched_snapshot_is_rejected_without_saving(self):
        for changes in (
            {"order_id": "another-order"},
            {"amount": 2000},
            {"payment_key": "another-key"},
        ):
            with self.subTest(changes=changes):
                self.processor.retrieve.return_value = replace(self.snapshot, **changes)
                with self.assertRaises(PaymentIdentityConflict):
                    await self.process()
        self.repo.save.assert_not_awaited()

    async def test_old_event_uses_latest_provider_state_instead_of_body(self):
        self.processor.retrieve.return_value = replace(
            self.snapshot, status=PaymentStatus.WAITING_FOR_DEPOSIT, paid_at=None
        )
        await self.process(status=PaymentStatus.DONE)
        self.assertEqual(self.saved.status, PaymentStatus.WAITING_FOR_DEPOSIT)
        self.assertIsNone(self.saved.paid_at)

    async def test_deposit_reversal_clears_paid_state(self):
        await self.process()
        self.processor.retrieve.return_value = replace(
            self.snapshot, status=PaymentStatus.WAITING_FOR_DEPOSIT, paid_at=None
        )
        await self.process(
            transaction_key="reversal-002", status=PaymentStatus.WAITING_FOR_DEPOSIT
        )
        self.assertEqual(self.saved.status, PaymentStatus.WAITING_FOR_DEPOSIT)
        self.assertIsNone(self.saved.paid_at)

    async def test_terminal_state_cannot_be_reopened(self):
        self.saved.status = PaymentStatus.CANCELED
        self.saved.canceled_at = datetime.now(UTC)
        with self.assertRaises(PaymentStatusException):
            await self.process()
        self.repo.save.assert_not_awaited()

    async def test_reconcile_recovers_lost_approval_response(self):
        self.saved.status = PaymentStatus.READY
        self.saved.payment_key = None
        service = PaymentService(self.processor, self.repo)
        result = await service.reconcile(7, "payment-key")
        self.assertEqual(result.status, PaymentStatus.DONE)
        self.assertEqual(result.payment_key, "payment-key")

    async def test_webhook_http_uses_provider_shape_and_returns_no_content(self):
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[provide_deposit_webhook_service] = lambda: self.service

        @app.exception_handler(SharedException)
        async def domain_error(_: Request, exc: SharedException):
            return JSONResponse(
                status_code=exc.status_code, content={"code": exc.error_code}
            )

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            body = {
                "orderId": self.saved.order_id,
                "secret": self.secret,
                "transactionKey": "txn-http",
                "status": "DONE",
                "createdAt": "2026-11-09T12:00:00",
            }
            response = await client.post("/v1/payments/webhooks/deposit", json=body)
            self.assertEqual(response.status_code, 204)
            self.assertEqual(response.content, b"")
            body["secret"] = "forged"
            self.assertEqual(
                (
                    await client.post("/v1/payments/webhooks/deposit", json=body)
                ).status_code,
                403,
            )
            body["secret"] = self.secret
            body["transactionKey"] = "txn-new"
            self.processor.retrieve.side_effect = PaymentProcessingError("timeout")
            self.assertEqual(
                (
                    await client.post("/v1/payments/webhooks/deposit", json=body)
                ).status_code,
                503,
            )
