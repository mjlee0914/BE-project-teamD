import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

from payments.application.service import PaymentService
from payments.domain.entities import Payment, PaymentLog
from payments.domain.enums import PaymentStatus
from payments.domain.exceptions import (
    InvalidAmountException,
    InvalidRefundAccount,
    PaymentAttemptConflict,
    PaymentNotFoundException,
    PaymentProcessingError,
    PaymentStatusException,
)
from payments.domain.repository import PaymentRepository
from payments.domain.service import (
    PaymentApprovalResult,
    PaymentCancellationResult,
    PaymentCreationContext,
    PaymentCreationContextProvider,
    PaymentProcessor,
)
from reservations.domain.enums import ReservationStatus
from shared.core.exceptions import ForbiddenException


class PaymentDomainTests(unittest.TestCase):
    def test_create_defaults_and_independent_logs(self):
        first = Payment.create(1, "Festival", 1000)
        second = Payment.create(2, "Festival", 1000)
        first.add_payment_log(PaymentLog({"event": "test"}))
        self.assertEqual(first.status, PaymentStatus.READY)
        self.assertIsNone(first.payment_id)
        self.assertIsNone(first.paid_at)
        self.assertIsNone(first.updated_at)
        self.assertEqual(second.payment_log, [])
        self.assertNotEqual(first.order_id, second.order_id)

    def test_nonpositive_amount_rejected(self):
        for amount in (0, -1, True, 1.5):
            with self.subTest(amount=amount), self.assertRaises(InvalidAmountException):
                Payment.create(1, "Festival", amount)

    def test_invalid_approval_result_keeps_payment_unchanged(self):
        payment = Payment.create(1, "Festival", 1000)
        with self.assertRaises(PaymentStatusException):
            payment.approve("key", 1000, PaymentStatus.DONE, None, PaymentLog({}))
        self.assertEqual(payment.status, PaymentStatus.READY)
        self.assertIsNone(payment.payment_key)
        self.assertEqual(payment.payment_log, [])

    def test_state_change_does_not_change_other_payments_or_enum(self):
        first = Payment.create(1, "Festival", 1000)
        second = Payment.create(2, "Festival", 1000)
        first.fail("declined")
        self.assertEqual(first.status, PaymentStatus.ABORTED)
        self.assertEqual(second.status, PaymentStatus.READY)
        self.assertEqual(PaymentStatus.READY.value, "READY")


class PaymentServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.payment = Payment.create(1, "Festival", 1000)
        self.payment.payment_id = 7
        self.repo = AsyncMock(spec=PaymentRepository)
        self.repo.find_by_id.return_value = self.payment
        self.repo.find_by_reservation_id.return_value = []
        self.repo.save.side_effect = lambda payment: payment
        self.processor = AsyncMock(spec=PaymentProcessor)
        self.creation_context_provider = AsyncMock(spec=PaymentCreationContextProvider)
        self.creation_context_provider.get_context.return_value = (
            PaymentCreationContext(
                reservation_id=1,
                user_id=10,
                festival_name="Festival",
                amount=1000,
                reservation_status=ReservationStatus.PENDING,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
        self.service = PaymentService(
            self.processor, self.repo, self.creation_context_provider
        )

    async def test_create_saves_payment(self):
        result = await self.service.create(1, 10)
        self.assertEqual(result.reservation.reservation_id, 1)
        self.assertEqual(result.reservation.festival_name, "Festival")
        self.assertEqual(result.amount, 1000)
        self.assertEqual(result.status, PaymentStatus.READY)
        self.repo.lock_reservation.assert_awaited_once_with(1)
        self.assertEqual(self.creation_context_provider.get_context.await_count, 2)
        self.repo.save.assert_awaited_once_with(result)
        self.processor.approve.assert_not_awaited()

    async def test_create_then_approve_uses_created_order(self):
        payment = await self.service.create(1, 10)
        self.repo.find_by_id.return_value = payment
        self.processor.approve.return_value = PaymentApprovalResult(
            PaymentStatus.DONE,
            datetime.now(UTC),
            PaymentLog({"status": "done"}),
            method="카드",
        )

        result = await self.service.approve(payment.payment_id or 7, "toss-key", 1000)

        self.processor.approve.assert_awaited_once_with(
            "toss-key", payment.order_id, payment.amount
        )
        self.assertEqual(result.status, PaymentStatus.DONE)
        self.assertEqual(result.payment_key, "toss-key")

    async def test_create_rejects_reservation_owned_by_another_user(self):
        self.creation_context_provider.get_context.return_value = (
            PaymentCreationContext(
                reservation_id=1,
                user_id=11,
                festival_name="Festival",
                amount=1000,
                reservation_status=ReservationStatus.PENDING,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
        with self.assertRaises(ForbiddenException):
            await self.service.create(1, 10)
        self.repo.save.assert_not_awaited()

    async def test_create_rejects_non_pending_or_expired_reservation(self):
        future = datetime.now(UTC) + timedelta(hours=1)
        contexts = (
            PaymentCreationContext(
                1, 10, "Festival", 1000, ReservationStatus.CONFIRMED, future
            ),
            PaymentCreationContext(
                1,
                10,
                "Festival",
                1000,
                ReservationStatus.PENDING,
                datetime.now(UTC),
            ),
        )
        for context in contexts:
            with self.subTest(context=context):
                self.creation_context_provider.get_context.return_value = context
                with self.assertRaises(PaymentStatusException):
                    await self.service.create(1, 10)
        self.repo.save.assert_not_awaited()

    async def test_create_rejects_duplicate_payment_attempt(self):
        existing = Payment.create(1, "Festival", 1000)
        existing.status = PaymentStatus.DONE
        self.repo.find_by_reservation_id.return_value = [existing]
        with self.assertRaises(PaymentAttemptConflict):
            await self.service.create(1, 10)
        self.repo.save.assert_not_awaited()

    async def test_create_reuses_ready_attempt(self):
        existing = Payment.create(1, "Festival", 1000)
        existing.payment_id = 11
        self.repo.find_by_reservation_id.return_value = [existing]

        result = await self.service.create(1, 10)

        self.assertIs(result, existing)
        self.repo.save.assert_not_awaited()

    async def test_create_accepts_naive_utc_expiration(self):
        self.creation_context_provider.get_context.return_value = (
            PaymentCreationContext(
                reservation_id=1,
                user_id=10,
                festival_name="Festival",
                amount=1000,
                reservation_status=ReservationStatus.PENDING,
                expires_at=(datetime.now(UTC) + timedelta(hours=1)).replace(
                    tzinfo=None
                ),
            )
        )

        result = await self.service.create(1, 10)

        self.assertEqual(result.status, PaymentStatus.READY)

    async def test_create_rejects_zero_amount(self):
        self.creation_context_provider.get_context.return_value = (
            PaymentCreationContext(
                reservation_id=1,
                user_id=10,
                festival_name="Festival",
                amount=0,
                reservation_status=ReservationStatus.PENDING,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
        with self.assertRaises(InvalidAmountException):
            await self.service.create(1, 10)
        self.repo.save.assert_not_awaited()

    async def test_approval_rejects_expired_reservation_before_provider_call(self):
        self.creation_context_provider.get_context.return_value = (
            PaymentCreationContext(
                reservation_id=1,
                user_id=10,
                festival_name="Festival",
                amount=1000,
                reservation_status=ReservationStatus.PENDING,
                expires_at=datetime.now(UTC) - timedelta(seconds=1),
            )
        )
        with self.assertRaises(PaymentStatusException):
            await self.service.approve(7, "key", 1000)
        self.processor.approve.assert_not_awaited()

    async def test_amount_mismatch_does_not_call_processor_or_mutate(self):
        with self.assertRaises(InvalidAmountException):
            await self.service.approve(7, "key", 2000)
        self.processor.approve.assert_not_awaited()
        self.repo.save.assert_not_awaited()
        self.assertIsNone(self.payment.payment_key)

    async def test_waiting_for_deposit_is_not_paid(self):
        self.processor.approve.return_value = PaymentApprovalResult(
            PaymentStatus.WAITING_FOR_DEPOSIT, None, PaymentLog({"status": "waiting"})
        )
        result = await self.service.approve(7, "key", 1000)
        self.processor.approve.assert_awaited_once_with(
            "key", self.payment.order_id, 1000
        )
        self.assertEqual(result.status, PaymentStatus.WAITING_FOR_DEPOSIT)
        self.assertIsNone(result.paid_at)
        self.assertEqual(self.repo.save.await_count, 2)

    async def test_successful_approval_and_cancellation_are_saved(self):
        now = datetime.now(UTC)
        self.processor.approve.return_value = PaymentApprovalResult(
            PaymentStatus.DONE, now, PaymentLog({"status": "done"})
        )
        await self.service.approve(7, "key", 1000)
        self.assertEqual(self.payment.paid_at, now)
        self.processor.cancel.return_value = PaymentCancellationResult(
            now, PaymentLog({"status": "canceled"})
        )
        result = await self.service.cancel(7)
        self.processor.cancel.assert_awaited_once_with(
            "key", reason="고객 요청", refund_account=None
        )
        self.assertEqual(result.status, PaymentStatus.CANCELED)
        self.assertEqual(result.canceled_at, now)
        self.assertEqual(self.repo.save.await_count, 3)

    async def test_duplicate_approval_does_not_call_processor(self):
        self.payment.status = PaymentStatus.DONE
        with self.assertRaises(PaymentStatusException):
            await self.service.approve(7, "key", 1000)
        self.processor.approve.assert_not_awaited()

    async def test_invalid_cancellation_does_not_call_processor(self):
        with self.assertRaises(PaymentStatusException):
            await self.service.cancel(7)
        self.processor.cancel.assert_not_awaited()

    async def test_approval_error_propagates_without_assuming_payment_failed(self):
        self.processor.approve.side_effect = PaymentProcessingError("timeout")
        with self.assertRaises(PaymentProcessingError):
            await self.service.approve(7, "key", 1000)
        self.assertEqual(self.payment.status, PaymentStatus.IN_PROGRESS)
        self.assertEqual(self.payment.payment_key, "key")
        self.repo.save.assert_awaited_once()

    async def test_other_active_attempt_prevents_provider_request(self):
        other = Payment.create(1, "Festival", 1000)
        other.payment_id = 8
        for status in (
            PaymentStatus.IN_PROGRESS,
            PaymentStatus.WAITING_FOR_DEPOSIT,
            PaymentStatus.DONE,
        ):
            with self.subTest(status=status):
                other.status = status
                self.repo.find_by_reservation_id.return_value = [other]
                with self.assertRaises(PaymentAttemptConflict):
                    await self.service.approve(7, "key", 1000)
        self.processor.approve.assert_not_awaited()

    async def test_repeated_successful_approval_returns_existing_result(self):
        self.payment.status = PaymentStatus.DONE
        self.payment.payment_key = "key"
        result = await self.service.approve(7, "key", 1000)
        self.assertIs(result, self.payment)
        self.processor.approve.assert_not_awaited()
        self.repo.save.assert_not_awaited()

    async def test_repeated_cancellation_does_not_call_provider(self):
        self.payment.status = PaymentStatus.CANCELED
        self.payment.canceled_at = datetime.now(UTC)
        result = await self.service.cancel(7)
        self.assertIs(result, self.payment)
        self.processor.cancel.assert_not_awaited()

    async def test_pending_attempt_does_not_accept_another_payment_key(self):
        self.payment.start_approval("first-key", 1000)
        with self.assertRaises(PaymentStatusException):
            await self.service.approve(7, "second-key", 1000)
        self.processor.approve.assert_not_awaited()

    async def test_unpaid_virtual_account_can_be_canceled_without_refund_account(self):
        self.payment.status = PaymentStatus.WAITING_FOR_DEPOSIT
        self.payment.payment_key = "key"
        self.payment.method = "가상계좌"
        self.processor.cancel.return_value = PaymentCancellationResult(
            datetime.now(UTC), PaymentLog({})
        )
        result = await self.service.cancel(7)
        self.assertEqual(result.status, PaymentStatus.CANCELED)
        self.assertIsNone(result.paid_at)

    async def test_paid_virtual_account_requires_refund_account_before_external_call(
        self,
    ):
        self.payment.status = PaymentStatus.DONE
        self.payment.payment_key = "key"
        self.payment.method = "가상계좌"
        with self.assertRaises(InvalidRefundAccount):
            await self.service.cancel(7)
        self.processor.cancel.assert_not_awaited()

    async def test_cancel_error_keeps_paid_state(self):
        self.payment.status = PaymentStatus.DONE
        self.payment.payment_key = "key"
        self.processor.cancel.side_effect = PaymentProcessingError("timeout")
        with self.assertRaises(PaymentProcessingError):
            await self.service.cancel(7)
        self.assertEqual(self.payment.status, PaymentStatus.DONE)
        self.assertIsNone(self.payment.canceled_at)
        self.repo.save.assert_not_awaited()

    async def test_missing_payment(self):
        self.repo.find_by_id.return_value = None
        with self.assertRaises(PaymentNotFoundException):
            await self.service.approve(7, "key", 1000)
        self.processor.approve.assert_not_awaited()
