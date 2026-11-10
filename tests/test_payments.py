import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

from payments.application.service import PaymentService
from payments.domain.entities import Payment, PaymentLog
from payments.domain.enums import PaymentRecoveryStatus, PaymentStatus
from payments.domain.exceptions import (
    InvalidAmountException,
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
    PaymentSnapshot,
    PaymentTransaction,
)
from reservations.application.service import ReservationService
from reservations.domain.enums import ReservationStatus
from reservations.domain.exceptions import DepositDeadlineViolation
from shared.core.exceptions import ForbiddenException, SharedException


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
        self.processor.retrieve.side_effect = lambda key: PaymentSnapshot(
            key,
            self.payment.order_id,
            self.payment.amount,
            self.payment.status,
            (self.payment.paid_at or datetime.now(UTC))
            if self.payment.status == PaymentStatus.DONE
            else None,
            self.payment.canceled_at,
            PaymentLog({}),
            self.payment.method,
        )
        self.reservation_service = AsyncMock(spec=ReservationService)
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
        self.transaction = AsyncMock(spec=PaymentTransaction)
        self.service = PaymentService(
            self.processor,
            self.repo,
            self.creation_context_provider,
            self.reservation_service,
            self.transaction,
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
        self.reservation_service.confirm_reservation.assert_awaited_once_with(1)

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
            PaymentStatus.WAITING_FOR_DEPOSIT,
            None,
            PaymentLog({"status": "waiting"}),
            virtual_account_due_at=datetime.now(UTC) + timedelta(minutes=30),
        )
        result = await self.service.approve(7, "key", 1000)
        self.processor.approve.assert_awaited_once_with(
            "key", self.payment.order_id, 1000
        )
        self.assertEqual(result.status, PaymentStatus.WAITING_FOR_DEPOSIT)
        self.assertIsNone(result.paid_at)
        self.reservation_service.confirm_reservation.assert_not_awaited()
        self.assertEqual(self.repo.save.await_count, 2)

    async def test_successful_approval_and_cancellation_are_saved(self):
        now = datetime.now(UTC)
        self.processor.approve.return_value = PaymentApprovalResult(
            PaymentStatus.DONE, now, PaymentLog({"status": "done"})
        )
        await self.service.approve(7, "key", 1000)
        self.reservation_service.confirm_reservation.assert_awaited_once_with(1)
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
        self.assertEqual(self.repo.save.await_count, 4)

    async def test_duplicate_approval_does_not_call_processor(self):
        self.payment.status = PaymentStatus.DONE
        with self.assertRaises(PaymentStatusException):
            await self.service.approve(7, "key", 1000)
        self.processor.approve.assert_not_awaited()

    async def test_ready_payment_cancellation_does_not_call_processor(self):
        result = await self.service.cancel(7)
        self.assertEqual(result.status, PaymentStatus.ABORTED)
        self.processor.cancel.assert_not_awaited()
        self.reservation_service.cancel_reservation.assert_awaited_once_with(
            1, 10, False
        )

    async def test_approval_error_propagates_without_assuming_payment_failed(self):
        self.processor.approve.side_effect = PaymentProcessingError(
            "timeout", outcome_unknown=True
        )
        with self.assertRaises(PaymentProcessingError):
            await self.service.approve(7, "key", 1000)
        self.assertEqual(self.payment.status, PaymentStatus.IN_PROGRESS)
        self.assertEqual(self.payment.payment_key, "key")
        self.repo.save.assert_awaited_once()
        self.reservation_service.confirm_reservation.assert_not_awaited()
        self.repo.find_by_reservation_id.return_value = [self.payment]
        with self.assertRaises(PaymentAttemptConflict):
            await self.service.create(1, 10)

    async def test_definite_rejection_allows_new_payment_and_successful_approval(self):
        rejection = PaymentProcessingError(
            "private provider message",
            code="UNAUTHORIZED_KEY",
            outcome_unknown=False,
        )
        self.processor.approve.side_effect = rejection
        with self.assertRaises(PaymentProcessingError) as caught:
            await self.service.approve(7, "rejected-key", 1000)

        self.assertIs(caught.exception, rejection)
        self.assertEqual(self.payment.status, PaymentStatus.ABORTED)
        self.assertEqual(self.payment.failed_reason, "UNAUTHORIZED_KEY")
        self.assertEqual(self.repo.save.await_count, 2)
        self.reservation_service.confirm_reservation.assert_not_awaited()

        self.repo.find_by_reservation_id.return_value = [self.payment]
        retry = await self.service.create(1, 10)
        self.assertEqual(retry.status, PaymentStatus.READY)
        self.assertNotEqual(retry.order_id, self.payment.order_id)

        retry.payment_id = 8
        self.repo.find_by_id.return_value = retry
        self.processor.approve.side_effect = None
        self.processor.approve.return_value = PaymentApprovalResult(
            PaymentStatus.DONE, datetime.now(UTC), PaymentLog({})
        )
        result = await self.service.approve(8, "new-key", 1000)
        self.assertEqual(result.status, PaymentStatus.DONE)
        self.reservation_service.confirm_reservation.assert_awaited_once_with(1)

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

    async def test_rejected_retry_does_not_erase_previous_uncertain_approval(self):
        self.payment.start_approval("key", 1000)
        self.processor.approve.side_effect = PaymentProcessingError(
            "rejected retry", code="UNAUTHORIZED_KEY", outcome_unknown=False
        )
        with self.assertRaises(PaymentProcessingError) as caught:
            await self.service.approve(7, "key", 1000)
        self.assertTrue(caught.exception.outcome_unknown)
        self.assertEqual(self.payment.status, PaymentStatus.IN_PROGRESS)

    async def test_provider_still_processing_does_not_become_failed_on_recovery(self):
        self.payment.start_approval("key", 1000)
        self.processor.retrieve.side_effect = None
        self.processor.retrieve.return_value = PaymentSnapshot(
            "key",
            self.payment.order_id,
            1000,
            PaymentStatus.IN_PROGRESS,
            None,
            None,
            PaymentLog({}),
            None,
        )
        result = await self.service.recover(7)
        self.assertEqual(result.status, PaymentStatus.IN_PROGRESS)
        self.reservation_service.confirm_reservation.assert_not_awaited()

    async def test_repeated_successful_approval_returns_existing_result(self):
        self.payment.status = PaymentStatus.DONE
        self.payment.payment_key = "key"
        result = await self.service.approve(7, "key", 1000)
        self.assertIs(result, self.payment)
        self.processor.approve.assert_not_awaited()
        self.repo.save.assert_not_awaited()
        self.reservation_service.confirm_reservation.assert_awaited_once_with(1)

    async def test_confirmation_failure_propagates_for_transaction_rollback(self):
        self.processor.approve.return_value = PaymentApprovalResult(
            PaymentStatus.DONE, datetime.now(UTC), PaymentLog({})
        )
        self.reservation_service.confirm_reservation.side_effect = RuntimeError(
            "ticket issuance failed"
        )

        with self.assertRaisesRegex(RuntimeError, "ticket issuance failed"):
            await self.service.approve(7, "key", 1000)

        self.assertEqual(self.payment.status, PaymentStatus.DONE)
        self.repo.save.assert_awaited()
        self.transaction.checkpoint.assert_awaited_once()

    async def test_confirmation_conflict_is_retried_without_losing_done_result(self):
        self.processor.approve.return_value = PaymentApprovalResult(
            PaymentStatus.DONE, datetime.now(UTC), PaymentLog({})
        )
        self.reservation_service.confirm_reservation.side_effect = SharedException(
            "ticket conflict", error_code="TICKET_CONFLICT"
        )
        result = await self.service.approve(7, "key", 1000)
        self.assertEqual(result.status, PaymentStatus.DONE)
        self.assertEqual(
            result.recovery_status, PaymentRecoveryStatus.CONFIRMATION_PENDING
        )
        self.reservation_service.confirm_reservation.side_effect = None
        recovered = await self.service.recover(7)
        self.assertIsNone(recovered.recovery_status)
        self.assertEqual(self.processor.approve.await_count, 1)

    async def test_expiration_during_approval_releases_reservation_and_refunds(self):
        now = datetime.now(UTC)
        self.processor.approve.return_value = PaymentApprovalResult(
            PaymentStatus.DONE, now, PaymentLog({}), "카드"
        )
        self.processor.cancel.return_value = PaymentCancellationResult(
            now, PaymentLog({})
        )
        self.reservation_service.confirm_reservation.side_effect = (
            DepositDeadlineViolation()
        )
        result = await self.service.approve(7, "key", 1000)
        self.assertEqual(result.status, PaymentStatus.CANCELED)
        self.reservation_service.release_for_payment_failure.assert_awaited_once_with(1)
        self.transaction.checkpoint.assert_has_awaits(
            [unittest.mock.call(), unittest.mock.call()]
        )

    async def test_cancel_timeout_preserves_intent_and_recovery_reuses_reason(self):
        self.payment.status = PaymentStatus.DONE
        self.payment.payment_key = "key"
        self.processor.cancel.side_effect = PaymentProcessingError(
            "timeout", outcome_unknown=True
        )
        with self.assertRaises(PaymentProcessingError):
            await self.service.cancel(7, reason="사용자 요청")
        self.assertEqual(
            self.payment.recovery_status, PaymentRecoveryStatus.CANCELLATION_PENDING
        )
        self.transaction.checkpoint.assert_awaited_once()
        self.processor.cancel.side_effect = None
        self.processor.cancel.return_value = PaymentCancellationResult(
            datetime.now(UTC), PaymentLog({})
        )
        result = await self.service.recover(7)
        self.assertEqual(result.status, PaymentStatus.CANCELED)
        self.assertIsNone(result.recovery_status)
        self.assertEqual(
            [call.kwargs["reason"] for call in self.processor.cancel.await_args_list],
            ["사용자 요청", "사용자 요청"],
        )

    async def test_virtual_account_with_extended_due_date_is_returned(self):
        self.processor.approve.return_value = PaymentApprovalResult(
            PaymentStatus.WAITING_FOR_DEPOSIT,
            None,
            PaymentLog({}),
            "가상계좌",
            virtual_account_due_at=datetime.now(UTC) + timedelta(hours=2),
        )
        self.processor.cancel.return_value = PaymentCancellationResult(
            datetime.now(UTC), PaymentLog({})
        )
        result = await self.service.approve(7, "key", 1000)
        self.assertEqual(result.status, PaymentStatus.CANCELED)
        self.reservation_service.confirm_reservation.assert_not_awaited()

    async def test_already_refunded_provider_result_does_not_send_another_refund(self):
        self.payment.status = PaymentStatus.DONE
        self.payment.payment_key = "key"
        self.processor.retrieve.side_effect = None
        self.processor.retrieve.return_value = PaymentSnapshot(
            "key",
            self.payment.order_id,
            1000,
            PaymentStatus.CANCELED,
            datetime.now(UTC),
            datetime.now(UTC),
            PaymentLog({}),
            "카드",
        )
        result = await self.service.cancel(7)
        self.assertEqual(result.status, PaymentStatus.CANCELED)
        self.processor.cancel.assert_not_awaited()

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
        result = await self.service.cancel(7)
        self.assertEqual(
            result.recovery_status, PaymentRecoveryStatus.REFUND_ACCOUNT_REQUIRED
        )
        self.processor.cancel.assert_not_awaited()

    async def test_cancel_error_keeps_paid_state(self):
        self.payment.status = PaymentStatus.DONE
        self.payment.payment_key = "key"
        self.processor.cancel.side_effect = PaymentProcessingError("timeout")
        with self.assertRaises(PaymentProcessingError):
            await self.service.cancel(7)
        self.assertEqual(self.payment.status, PaymentStatus.DONE)
        self.assertIsNone(self.payment.canceled_at)
        self.assertEqual(
            self.payment.recovery_status, PaymentRecoveryStatus.CANCELLATION_PENDING
        )

    async def test_missing_payment(self):
        self.repo.find_by_id.return_value = None
        with self.assertRaises(PaymentNotFoundException):
            await self.service.approve(7, "key", 1000)
        self.processor.approve.assert_not_awaited()
