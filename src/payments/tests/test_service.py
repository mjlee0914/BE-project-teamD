import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from payments.application.service import PaymentService
from payments.domain.entities import Payment, PaymentStatus
from payments.domain.reservation import ReservationPaymentInfo
from payments.infrastructure.repositories import PaymentRepository
from payments.infrastructure.reservation_repository import ReservationPaymentRepository


class PaymentServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 11, 3, tzinfo=UTC)
        self.db = AsyncMock(spec=AsyncSession)
        self.service = PaymentService(self.db, clock=lambda: self.now)
        self.service.payments = AsyncMock(spec=PaymentRepository)
        self.service.reservations = AsyncMock(spec=ReservationPaymentRepository)
        self.reservation = ReservationPaymentInfo(
            id=1,
            user_id=7,
            status="PENDING",
            final_price=50000,
            expires_at=self.now + timedelta(minutes=10),
        )
        self.service.reservations.find_by_id.return_value = self.reservation
        self.service.payments.find_by_reservation_id.return_value = []

        async def save(payment):
            if payment.id is None:
                payment.id = 42
            return payment

        self.service.payments.save.side_effect = save

    async def pay(self, **overrides):
        args = {
            "reservation_id": 1,
            "user_id": 7,
            "method": "CARD",
            "requested_amount": 50000,
        }
        args.update(overrides)
        return await self.service.pay(**args)

    def paid_payment(self) -> Payment:
        return Payment.restore(
            id=42,
            reservation_id=1,
            method="CARD",
            amount=50000,
            status=PaymentStatus.PAID,
            payment_key="mock-test-key",
            paid_at=self.now,
        )

    async def test_approval_uses_reservation_amount_and_commits_after_save(
        self,
    ) -> None:
        events = []

        async def lock(*args, **kwargs):
            events.append("lock")
            return self.reservation

        async def attempts(*args):
            events.append("check_attempts")
            return []

        async def save(payment):
            events.append("save")
            payment.id = 42

        async def commit():
            events.append("commit")

        self.service.reservations.find_by_id.side_effect = lock
        self.service.payments.find_by_reservation_id.side_effect = attempts
        self.service.payments.save.side_effect = save
        self.db.commit.side_effect = commit
        payment = await self.pay()
        self.assertEqual(events, ["lock", "check_attempts", "save", "commit"])
        self.assertEqual(payment.id, 42)
        self.assertEqual(payment.status, PaymentStatus.PAID)
        self.assertEqual(payment.amount, self.reservation.final_price)
        self.assertTrue(payment.payment_key.startswith("mock-"))
        self.service.reservations.find_by_id.assert_awaited_once_with(
            1, for_update=True
        )
        self.db.rollback.assert_not_awaited()

    async def test_amount_mismatch_is_committed_as_failed_attempt(self) -> None:
        payment = await self.pay(requested_amount=1)
        self.assertEqual(payment.amount, 50000)
        self.assertEqual(payment.status, PaymentStatus.FAILED)
        self.assertIn("금액", payment.fail_reason)
        self.assertIsNone(payment.payment_key)
        self.db.commit.assert_awaited_once()

    async def test_mock_decline_is_committed_as_failed_attempt(self) -> None:
        payment = await self.pay(simulate_failure=True)
        self.assertEqual(payment.status, PaymentStatus.FAILED)
        self.assertEqual(payment.fail_reason, "가상 결제 승인 실패")
        self.db.commit.assert_awaited_once()

    async def test_failed_attempt_allows_new_attempt(self) -> None:
        previous = Payment(reservation_id=1, method="CARD", amount=50000)
        previous.fail("이전 실패")
        self.service.payments.find_by_reservation_id.return_value = [previous]
        payment = await self.pay()
        self.assertEqual(payment.status, PaymentStatus.PAID)
        self.assertEqual(previous.status, PaymentStatus.FAILED)

    async def test_already_paid_reservation_is_rejected(self) -> None:
        self.service.payments.find_by_reservation_id.return_value = [
            self.paid_payment()
        ]
        with self.assertRaises(ValueError):
            await self.pay()
        self.service.payments.save.assert_not_awaited()
        self.db.commit.assert_not_awaited()
        self.db.rollback.assert_awaited_once()

    async def test_other_members_reservation_is_rejected_before_payment_lookup(
        self,
    ) -> None:
        with self.assertRaises(PermissionError):
            await self.pay(user_id=8)
        self.service.payments.find_by_reservation_id.assert_not_awaited()
        self.service.payments.save.assert_not_awaited()
        self.db.commit.assert_not_awaited()

    async def test_nonpending_reservations_are_rejected(self) -> None:
        for status in ("CONFIRMED", "CANCELED", "EXPIRED"):
            with self.subTest(status=status):
                self.service.reservations.find_by_id.return_value = replace(
                    self.reservation, status=status
                )
                with self.assertRaises(ValueError):
                    await self.pay()
        self.service.payments.save.assert_not_awaited()

    async def test_expiration_boundary_and_missing_expiration_are_rejected(
        self,
    ) -> None:
        for expires_at in (self.now, self.now - timedelta(seconds=1), None):
            with self.subTest(expires_at=expires_at):
                self.service.reservations.find_by_id.return_value = replace(
                    self.reservation, expires_at=expires_at
                )
                with self.assertRaises(ValueError):
                    await self.pay()
        self.service.payments.save.assert_not_awaited()

    async def test_expiration_is_checked_after_waiting_for_lock(self) -> None:
        async def lock(*args, **kwargs):
            self.now += timedelta(minutes=11)
            return self.reservation

        self.service.reservations.find_by_id.side_effect = lock
        with self.assertRaises(ValueError):
            await self.pay()
        self.service.payments.save.assert_not_awaited()

    async def test_missing_reservation_is_rejected(self) -> None:
        self.service.reservations.find_by_id.return_value = None
        with self.assertRaises(LookupError):
            await self.pay()
        self.service.payments.save.assert_not_awaited()

    async def test_zero_final_price_is_supported(self) -> None:
        self.service.reservations.find_by_id.return_value = replace(
            self.reservation, final_price=0
        )
        payment = await self.pay(requested_amount=0)
        self.assertEqual(payment.status, PaymentStatus.PAID)
        self.assertEqual(payment.amount, 0)

    async def test_save_failure_rolls_back_without_commit(self) -> None:
        error = RuntimeError("save failed")
        self.service.payments.save.side_effect = error
        with self.assertRaises(RuntimeError) as caught:
            await self.pay()
        self.assertIs(caught.exception, error)
        self.db.commit.assert_not_awaited()
        self.db.rollback.assert_awaited_once()

    async def test_commit_failure_rolls_back_and_propagates(self) -> None:
        error = RuntimeError("commit failed")
        self.db.commit.side_effect = error
        with self.assertRaises(RuntimeError) as caught:
            await self.pay()
        self.assertIs(caught.exception, error)
        self.db.rollback.assert_awaited_once()

    async def test_get_payment_checks_ownership(self) -> None:
        self.service.payments.find_by_id.return_value = self.paid_payment()
        payment = await self.service.get_payment(payment_id=42, user_id=7)
        self.assertEqual(payment.id, 42)
        with self.assertRaises(PermissionError):
            await self.service.get_payment(payment_id=42, user_id=8)
        self.db.commit.assert_not_awaited()

    async def test_get_missing_payment_is_rejected(self) -> None:
        self.service.payments.find_by_id.return_value = None
        with self.assertRaises(LookupError):
            await self.service.get_payment(payment_id=999, user_id=7)

    async def test_cancellation_requires_canceled_reservation(self) -> None:
        self.service.payments.find_by_id.return_value = self.paid_payment()
        with self.assertRaises(ValueError):
            await self.service.cancel(payment_id=42, user_id=7)
        self.service.payments.save.assert_not_awaited()
        self.db.commit.assert_not_awaited()

    async def test_cancellation_locks_payment_and_commits(self) -> None:
        self.service.reservations.find_by_id.return_value = replace(
            self.reservation, status="CANCELED"
        )
        self.service.payments.find_by_id.return_value = self.paid_payment()
        payment = await self.service.cancel(payment_id=42, user_id=7)
        self.assertEqual(payment.status, PaymentStatus.CANCELED)
        self.service.reservations.find_by_id.assert_awaited_once_with(
            1, for_update=True
        )
        self.service.payments.find_by_id.assert_any_await(42, for_update=True)
        self.db.commit.assert_awaited_once()

    async def test_other_member_cannot_cancel(self) -> None:
        self.service.reservations.find_by_id.return_value = replace(
            self.reservation, status="CANCELED"
        )
        self.service.payments.find_by_id.return_value = self.paid_payment()
        with self.assertRaises(PermissionError):
            await self.service.cancel(payment_id=42, user_id=8)
        self.service.payments.save.assert_not_awaited()

    async def test_cancellation_commit_failure_is_propagated(self) -> None:
        self.service.reservations.find_by_id.return_value = replace(
            self.reservation, status="CANCELED"
        )
        self.service.payments.find_by_id.return_value = self.paid_payment()
        self.db.commit.side_effect = RuntimeError("commit failed")
        with self.assertRaises(RuntimeError):
            await self.service.cancel(payment_id=42, user_id=7)
        self.db.rollback.assert_awaited_once()


class ReservationPaymentRepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_adapter_returns_pure_domain_information_and_lock_sql(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        expiry = datetime(2026, 11, 3, tzinfo=UTC)
        db.scalar.return_value = SimpleNamespace(
            id=1,
            user_id=7,
            status="PENDING",
            final_price=50000,
            expires_at=expiry,
        )
        repository = ReservationPaymentRepository(db)
        result = await repository.find_by_id(1, for_update=True)
        self.assertIs(type(result), ReservationPaymentInfo)
        self.assertEqual(result.final_price, 50000)
        statement = db.scalar.call_args.args[0]
        self.assertIn(
            "FOR UPDATE", str(statement.compile(dialect=postgresql.dialect()))
        )
        self.assertTrue(statement.get_execution_options()["populate_existing"])

    async def test_missing_reservation_returns_none(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        db.scalar.return_value = None
        self.assertIsNone(await ReservationPaymentRepository(db).find_by_id(999))
