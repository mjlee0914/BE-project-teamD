import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock

from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from payments.domain.entities import Payment, PaymentStatus
from payments.infrastructure.models import PaymentModel
from payments.infrastructure.repositories import PaymentRepository


class PaymentRepositoryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 11, 3, tzinfo=UTC)
        self.db = AsyncMock(spec=AsyncSession)
        self.repository = PaymentRepository(self.db)

    def model(self, status=PaymentStatus.READY, payment_id=10) -> PaymentModel:
        approved = status in (PaymentStatus.PAID, PaymentStatus.CANCELED)
        return PaymentModel(
            id=payment_id,
            reservation_id=1,
            method="CARD",
            amount=50000,
            status=status,
            payment_key=f"mock-key-{payment_id}" if approved else None,
            paid_at=self.now if approved else None,
            canceled_at=self.now + timedelta(minutes=1)
            if status == PaymentStatus.CANCELED
            else None,
            fail_reason="승인 실패" if status == PaymentStatus.FAILED else None,
            created_at=self.now,
            updated_at=None,
            payment_log={"event": "preserve-this-log"},
        )

    async def test_find_restores_each_status_and_identifiers(self) -> None:
        for status in PaymentStatus:
            with self.subTest(status=status):
                model = self.model(status)
                self.db.scalar.return_value = model
                payment = await self.repository.find_by_id(10)
                self.assertIs(type(payment), Payment)
                self.assertEqual(payment.id, 10)
                self.assertEqual(payment.status, status)
                self.assertEqual(payment.created_at, self.now)
                self.assertEqual(payment.payment_key, model.payment_key)
                self.assertEqual(payment.paid_at, model.paid_at)
                self.assertEqual(payment.canceled_at, model.canceled_at)
                self.assertEqual(payment.fail_reason, model.fail_reason)

    async def test_restored_paid_payment_can_be_canceled(self) -> None:
        self.db.scalar.return_value = self.model(PaymentStatus.PAID)
        payment = await self.repository.find_by_id(10)
        payment.cancel(now=self.now + timedelta(minutes=2))
        self.assertEqual(payment.status, PaymentStatus.CANCELED)

    async def test_missing_payment_returns_none(self) -> None:
        self.db.scalar.return_value = None
        self.assertIsNone(await self.repository.find_by_id(999))

    async def test_optional_lock_and_lookup_id_are_in_generated_sql(self) -> None:
        self.db.scalar.return_value = None
        for locked in (False, True):
            with self.subTest(locked=locked):
                await self.repository.find_by_id(10, for_update=locked)
                statement = self.db.scalar.call_args.args[0]
                compiled = statement.compile(dialect=postgresql.dialect())
                self.assertEqual("FOR UPDATE" in str(compiled), locked)
                self.assertIn(10, compiled.params.values())

    async def test_reservation_lookup_keeps_failed_and_successful_attempts(
        self,
    ) -> None:
        self.db.scalars.return_value = Mock(
            all=Mock(
                return_value=[
                    self.model(PaymentStatus.FAILED, 10),
                    self.model(PaymentStatus.PAID, 11),
                ]
            )
        )
        payments = await self.repository.find_by_reservation_id(1)
        self.assertEqual([payment.id for payment in payments], [10, 11])
        self.assertEqual(
            [payment.status for payment in payments],
            [PaymentStatus.FAILED, PaymentStatus.PAID],
        )
        statement = self.db.scalars.call_args.args[0]
        compiled = statement.compile(dialect=postgresql.dialect())
        self.assertIn(1, compiled.params.values())
        self.assertIn("ORDER BY payments.id", str(compiled))

    async def test_empty_reservation_lookup_returns_empty_list(self) -> None:
        self.db.scalars.return_value = Mock(all=Mock(return_value=[]))
        self.assertEqual(await self.repository.find_by_reservation_id(1), [])

    async def test_new_payment_receives_database_id_without_commit(self) -> None:
        payment = Payment(reservation_id=1, method="CARD", amount=50000)

        async def refresh(model):
            model.id = 10
            model.created_at = self.now
            model.updated_at = None

        self.db.refresh.side_effect = refresh
        saved = await self.repository.save(payment)
        self.assertIs(saved, payment)
        self.assertEqual(payment.id, 10)
        self.assertEqual(payment.created_at, self.now)
        self.assertEqual(
            [call[0] for call in self.db.mock_calls], ["add", "flush", "refresh"]
        )
        model = self.db.add.call_args.args[0]
        self.assertEqual(model.reservation_id, 1)
        self.assertEqual(model.amount, 50000)
        self.assertEqual(model.status, PaymentStatus.READY)
        self.db.commit.assert_not_awaited()

    async def test_existing_payment_is_updated_without_overwriting_log(self) -> None:
        model = self.model(PaymentStatus.PAID)
        self.db.scalar.return_value = model
        payment = await self.repository.find_by_id(10)
        payment.cancel(now=self.now + timedelta(minutes=2))
        self.db.get.return_value = model
        await self.repository.save(payment)
        self.assertEqual(model.status, PaymentStatus.CANCELED)
        self.assertEqual(model.canceled_at, payment.canceled_at)
        self.assertEqual(model.payment_log, {"event": "preserve-this-log"})
        self.db.add.assert_not_called()
        self.db.commit.assert_not_awaited()

    async def test_missing_update_is_not_recreated_as_new_payment(self) -> None:
        payment = Payment.restore(
            id=10,
            reservation_id=1,
            method="CARD",
            amount=50000,
            status=PaymentStatus.READY,
        )
        self.db.get.return_value = None
        with self.assertRaises(LookupError):
            await self.repository.save(payment)
        self.db.add.assert_not_called()
        self.db.flush.assert_not_awaited()

    async def test_existing_identity_and_amount_cannot_be_overwritten(self) -> None:
        for name, value in [
            ("reservation_id", 2),
            ("method", "TRANSFER"),
            ("amount", 1),
        ]:
            with self.subTest(name=name):
                self.db.scalar.return_value = self.model()
                payment = await self.repository.find_by_id(10)
                setattr(payment, name, value)
                self.db.get.return_value = self.model()
                with self.assertRaises(ValueError):
                    await self.repository.save(payment)
        self.db.flush.assert_not_awaited()

    async def test_flush_failure_is_propagated_without_committing(self) -> None:
        error = RuntimeError("flush failed")
        self.db.flush.side_effect = error
        payment = Payment(reservation_id=1, method="CARD", amount=50000)
        with self.assertRaises(RuntimeError) as caught:
            await self.repository.save(payment)
        self.assertIs(caught.exception, error)
        self.assertIsNone(payment.id)
        self.db.refresh.assert_not_awaited()
        self.db.commit.assert_not_awaited()

    async def test_inconsistent_stored_state_is_rejected(self) -> None:
        for status, overrides in [
            (PaymentStatus.PAID, {"paid_at": None}),
            (PaymentStatus.PAID, {"payment_key": None}),
            (PaymentStatus.READY, {"paid_at": self.now}),
            (PaymentStatus.FAILED, {"fail_reason": None}),
            (
                PaymentStatus.CANCELED,
                {"canceled_at": self.now - timedelta(seconds=1)},
            ),
        ]:
            with self.subTest(status=status, overrides=overrides):
                model = self.model(status)
                for name, value in overrides.items():
                    setattr(model, name, value)
                self.db.scalar.return_value = model
                with self.assertRaises(ValueError):
                    await self.repository.find_by_id(10)
