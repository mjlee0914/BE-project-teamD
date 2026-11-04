import unittest
from datetime import UTC, datetime, timedelta

from payments.domain.entities import Payment, PaymentStatus


class PaymentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 11, 3, tzinfo=UTC)
        self.payment = Payment(reservation_id=1, method="CARD", amount=50000)

    def approve(self) -> None:
        self.payment.approve(
            requested_amount=50000, payment_key="mock-payment-key", now=self.now
        )

    def test_new_payment_is_ready(self) -> None:
        self.assertEqual(self.payment.status, PaymentStatus.READY)
        self.assertIsNone(self.payment.payment_key)
        self.assertIsNone(self.payment.paid_at)

    def test_approval_sets_key_time_and_paid_status(self) -> None:
        self.approve()
        self.assertEqual(self.payment.status, PaymentStatus.PAID)
        self.assertEqual(self.payment.payment_key, "mock-payment-key")
        self.assertEqual(self.payment.paid_at, self.now)

    def test_amount_mismatch_leaves_payment_unchanged(self) -> None:
        with self.assertRaises(ValueError):
            self.payment.approve(
                requested_amount=1, payment_key="mock-key", now=self.now
            )
        self.assertEqual(self.payment.status, PaymentStatus.READY)
        self.assertIsNone(self.payment.payment_key)
        self.assertIsNone(self.payment.paid_at)

    def test_failure_records_reason_and_blocks_approval(self) -> None:
        self.payment.fail("가상 결제 승인 실패")
        self.assertEqual(self.payment.status, PaymentStatus.FAILED)
        self.assertEqual(self.payment.fail_reason, "가상 결제 승인 실패")
        with self.assertRaises(ValueError):
            self.approve()

    def test_retry_uses_new_payment(self) -> None:
        self.payment.fail("가상 결제 승인 실패")
        retry = Payment(reservation_id=1, method="CARD", amount=50000)
        retry.approve(requested_amount=50000, payment_key="retry-key", now=self.now)
        self.assertEqual(self.payment.status, PaymentStatus.FAILED)
        self.assertEqual(retry.status, PaymentStatus.PAID)

    def test_cancellation_preserves_approval_and_sets_cancel_time(self) -> None:
        self.approve()
        later = self.now + timedelta(minutes=1)
        self.payment.cancel(now=later)
        self.assertEqual(self.payment.status, PaymentStatus.CANCELED)
        self.assertEqual(self.payment.canceled_at, later)
        self.assertEqual(self.payment.paid_at, self.now)
        self.assertEqual(self.payment.payment_key, "mock-payment-key")

    def test_ready_and_failed_payments_cannot_be_canceled(self) -> None:
        with self.assertRaises(ValueError):
            self.payment.cancel(now=self.now)
        self.payment.fail("승인 실패")
        with self.assertRaises(ValueError):
            self.payment.cancel(now=self.now)

    def test_paid_and_canceled_payments_cannot_be_approved_or_failed(self) -> None:
        self.approve()
        for canceled in (False, True):
            if canceled:
                self.payment.cancel(now=self.now)
            with self.subTest(canceled=canceled):
                with self.assertRaises(ValueError):
                    self.approve()
                with self.assertRaises(ValueError):
                    self.payment.fail("중복 처리")

    def test_repeated_cancellation_is_rejected(self) -> None:
        self.approve()
        self.payment.cancel(now=self.now)
        with self.assertRaises(ValueError):
            self.payment.cancel(now=self.now)

    def test_cancellation_before_approval_is_rejected(self) -> None:
        self.approve()
        with self.assertRaises(ValueError):
            self.payment.cancel(now=self.now - timedelta(seconds=1))
        self.assertEqual(self.payment.status, PaymentStatus.PAID)
        self.assertIsNone(self.payment.canceled_at)

    def test_zero_amount_payment_is_supported(self) -> None:
        payment = Payment(reservation_id=1, method="CARD", amount=0)
        payment.approve(requested_amount=0, payment_key="zero-key", now=self.now)
        self.assertEqual(payment.status, PaymentStatus.PAID)

    def test_invalid_creation_values_are_rejected(self) -> None:
        for reservation_id, method, amount in [
            (0, "CARD", 1),
            (True, "CARD", 1),
            (1, " ", 1),
            (1, "CARD", -1),
            (1, "CARD", True),
            (1, "CARD", 1.5),
        ]:
            with (
                self.subTest(
                    reservation_id=reservation_id, method=method, amount=amount
                ),
                self.assertRaises(ValueError),
            ):
                Payment(reservation_id=reservation_id, method=method, amount=amount)

    def test_invalid_approval_values_leave_payment_ready(self) -> None:
        for amount, key, now in [
            (True, "key", self.now),
            (50000, " ", self.now),
            (50000, "key", self.now.replace(tzinfo=None)),
        ]:
            with self.subTest(amount=amount, key=key, now=now):
                with self.assertRaises(ValueError):
                    self.payment.approve(
                        requested_amount=amount, payment_key=key, now=now
                    )
                self.assertEqual(self.payment.status, PaymentStatus.READY)
                self.assertIsNone(self.payment.payment_key)

    def test_empty_failure_reason_leaves_payment_ready(self) -> None:
        with self.assertRaises(ValueError):
            self.payment.fail(" ")
        self.assertEqual(self.payment.status, PaymentStatus.READY)
        self.assertIsNone(self.payment.fail_reason)
