import unittest
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

from sqlalchemy import create_engine, event, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateTable

from payments.domain.entities import Payment, PaymentLog, ReservationInfo
from payments.domain.enums import PaymentStatus
from payments.domain.exceptions import (
    PaymentConcurrentUpdate,
    PaymentDuplicateIdentifier,
    PaymentIdentityConflict,
    PaymentNotFoundException,
    PaymentReservationNotFound,
)
from payments.infrastructure.access_checker import SQLAlchemyPaymentAccessChecker
from payments.infrastructure.models import PaymentModel
from payments.infrastructure.sqlalchemy_repository import SQLAlchemyPaymentRepository
from shared.core.exceptions import ForbiddenException


class PaymentRepositoryTests(unittest.IsolatedAsyncioTestCase):
    """SQLite로 실제 SQL과 제약을 검사한다. 비동기 드라이버 대신 세션 어댑터를 사용한다."""

    async def asyncSetUp(self):
        self.engine = create_engine("sqlite://")

        @event.listens_for(self.engine, "connect")
        def enable_foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

        # 예매 테이블은 저장소에서 참조하는 컬럼만 격리한다. 기존 프로젝트 DB는 사용하지 않는다.
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE reservations (id BIGINT PRIMARY KEY, festival_name TEXT NOT NULL, user_id BIGINT NOT NULL DEFAULT 10)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO reservations (id, festival_name) VALUES (1, 'Snapshot Festival'), (2, 'Another Festival')"
                )
            )
        PaymentModel.__table__.create(self.engine)
        self.sync = Session(self.engine)
        self.session = AsyncMock(spec=AsyncSession)
        self.session.execute.side_effect = self.sync.execute
        self.session.get.side_effect = self.sync.get
        self.session.flush.side_effect = self.sync.flush
        self.session.refresh.side_effect = self.sync.refresh
        self.session.add = Mock(side_effect=self.sync.add)
        self.repo = SQLAlchemyPaymentRepository(self.session)

    async def asyncTearDown(self):
        self.sync.close()
        self.engine.dispose()

    async def create(self, reservation_id=1):
        return await self.repo.save(
            Payment.create(reservation_id, "Ignored client name", 1000)
        )

    async def test_insert_and_retrieve_preserve_identity_and_reservation_snapshot(self):
        saved = await self.create()
        self.assertIsNotNone(saved.payment_id)
        self.assertEqual(saved.reservation.festival_name, "Snapshot Festival")
        self.sync.expire_all()
        loaded = await self.repo.find_by_id(saved.payment_id)
        self.assertEqual(loaded.order_id, saved.order_id)
        self.assertEqual(loaded.amount, 1000)
        self.assertEqual(loaded.status, PaymentStatus.READY)
        self.assertIsNone(loaded.paid_at)
        self.session.commit.assert_not_awaited()

    async def test_multiple_attempts_per_reservation_are_filtered_and_ordered(self):
        first = await self.create()
        second = await self.create()
        await self.create(2)
        rows = await self.repo.find_by_reservation_id(1)
        self.assertEqual(
            [row.payment_id for row in rows], [first.payment_id, second.payment_id]
        )
        self.assertNotEqual(rows[0].order_id, rows[1].order_id)
        self.assertEqual(await self.repo.find_by_reservation_id(999), [])

    async def test_updated_at_is_null_until_first_change(self):
        saved = await self.create()
        self.assertIsNone(saved.updated_at)
        self.sync.expire_all()
        loaded = await self.repo.find_by_id(saved.payment_id)
        self.assertIsNone(loaded.updated_at)

        loaded.fail("declined")
        changed = await self.repo.save(loaded)
        self.assertIsNotNone(changed.updated_at)

    async def test_status_constraint_rejects_unknown_value(self):
        # ORM 타입 검사와 별개로 DB 자체도 Enum 밖의 상태를 거절해야 한다.
        with self.assertRaises(IntegrityError):
            self.sync.execute(
                text(
                    "INSERT INTO payments (reservation_id, amount, status, payment_log) "
                    "VALUES (1, 1000, 'UNKNOWN', '[]')"
                )
            )

    async def test_approval_and_cancellation_round_trip(self):
        payment = await self.create()
        now = datetime.now(UTC)
        payment.approve(
            "payment-key",
            1000,
            PaymentStatus.DONE,
            now,
            PaymentLog({"nested": {"amount": 1000}}),
            "가상계좌",
        )
        await self.repo.save(payment)
        self.sync.expire_all()
        loaded = await self.repo.find_by_id(payment.payment_id)
        self.assertEqual(loaded.method, "가상계좌")
        self.assertEqual(loaded.payment_key, "payment-key")
        self.assertEqual(loaded.payment_log[0].value, {"nested": {"amount": 1000}})
        loaded.cancel(now, PaymentLog({"status": "CANCELED"}))
        await self.repo.save(loaded)
        self.sync.expire_all()
        canceled = await self.repo.find_by_id(payment.payment_id)
        self.assertEqual(canceled.status, PaymentStatus.CANCELED)
        self.assertIsNotNone(canceled.canceled_at)
        self.assertEqual(len(canceled.payment_log), 2)
        self.assertEqual(
            self.sync.scalar(
                select(PaymentModel).where(PaymentModel.id == payment.payment_id)
            ).status,
            "CANCELED",
        )

    async def test_fail_reason_uses_erd_column(self):
        payment = await self.create()
        payment.fail("declined")
        await self.repo.save(payment)
        self.assertEqual(
            self.sync.get(PaymentModel, payment.payment_id).fail_reason, "declined"
        )
        loaded = await self.repo.find_by_id(payment.payment_id)
        self.assertEqual(loaded.failed_reason, "declined")

    async def test_domain_log_does_not_mutate_orm_without_save(self):
        payment = await self.create()
        payment.add_payment_log(PaymentLog({"nested": {"value": 1}}))
        await self.repo.save(payment)
        loaded = await self.repo.find_by_id(payment.payment_id)
        loaded.payment_log[0].value["nested"]["value"] = 2
        model = self.sync.get(PaymentModel, payment.payment_id)
        self.assertEqual(model.payment_log[1]["nested"]["value"], 1)

    async def test_missing_payment(self):
        self.assertIsNone(await self.repo.find_by_id(999))
        payment = Payment.create(1, "Festival", 1000)
        payment.payment_id = 999
        with self.assertRaises(PaymentNotFoundException):
            await self.repo.save(payment)

    async def test_webhook_metadata_and_memory_token_round_trip(self):
        payment = await self.create()
        self.assertIsNotNone(payment.persistence_token)
        payment.webhook_secret_hash = "a" * 64
        payment.processed_deposit_events = ["event-1"]
        saved = await self.repo.save(payment)
        loaded = await self.repo.find_by_order_id(saved.order_id)
        self.assertNotEqual(loaded.persistence_token, payment.persistence_token)
        self.assertEqual(loaded.webhook_secret_hash, "a" * 64)
        self.assertEqual(loaded.processed_deposit_events, ["event-1"])
        self.assertIsNone(await self.repo.find_by_order_id("missing-order"))

    async def test_stale_domain_update_is_rejected(self):
        payment = await self.create()
        stale = await self.repo.find_by_id(payment.payment_id)
        payment.fail("declined")
        await self.repo.save(payment)
        stale.method = "가상계좌"
        with self.assertRaises(PaymentConcurrentUpdate):
            await self.repo.save(stale)

    async def test_locked_refresh_prevents_overwrite_from_other_session(self):
        payment = await self.create()
        self.sync.commit()
        with Session(self.engine) as other:
            session = AsyncMock(spec=AsyncSession)
            session.execute.side_effect = other.execute
            session.get.side_effect = other.get
            session.flush.side_effect = other.flush
            session.refresh.side_effect = other.refresh
            repo = SQLAlchemyPaymentRepository(session)
            stale = await repo.find_by_id(payment.payment_id)
            # ORM identity map은 약한 참조이므로 객체를 유지해 실제 낡은 버전을 검사한다.
            stale_model = other.get(PaymentModel, payment.payment_id)
            payment.fail("declined")
            await self.repo.save(payment)
            self.sync.commit()
            self.assertEqual(stale_model.status, "READY")
            stale.method = "가상계좌"
            with self.assertRaises(PaymentConcurrentUpdate):
                await repo.save(stale)
            other.rollback()
        self.assertEqual(
            (await self.repo.find_by_id(payment.payment_id)).status,
            PaymentStatus.ABORTED,
        )

    async def test_missing_reservation(self):
        with self.assertRaises(PaymentReservationNotFound):
            await self.create(999)
        self.session.add.assert_not_called()

    async def test_owner_check_rejects_other_user_and_missing_reservation(self):
        checker = SQLAlchemyPaymentAccessChecker(self.session)
        await checker.ensure_owner(1, 10)
        with self.assertRaises(ForbiddenException):
            await checker.ensure_owner(1, 99)
        with self.assertRaises(ForbiddenException):
            await checker.ensure_owner(999, 10)

    async def test_existing_identity_cannot_be_replaced(self):
        for field, value in (
            ("order_id", "changed-order"),
            ("amount", 2000),
            ("reservation", ReservationInfo(2, "Another Festival")),
        ):
            with self.subTest(field=field):
                saved = await self.create()
                setattr(saved, field, value)
                with self.assertRaises(PaymentIdentityConflict):
                    await self.repo.save(saved)

    async def test_duplicate_order_id_is_rejected(self):
        saved = await self.create()
        duplicate = Payment.create(1, "Festival", 1000)
        duplicate.order_id = saved.order_id
        with self.assertRaises(PaymentDuplicateIdentifier):
            await self.repo.save(duplicate)

    async def test_duplicate_payment_key_is_rejected(self):
        first = await self.create()
        first.payment_key = "same-key"
        await self.repo.save(first)
        second = Payment.create(1, "Festival", 1000)
        second.payment_key = "same-key"
        with self.assertRaises(PaymentDuplicateIdentifier):
            await self.repo.save(second)

    async def test_positive_amount_constraint(self):
        payment = Payment.create(1, "Festival", 1000)
        payment.amount = 0
        with self.assertRaises(IntegrityError):
            await self.repo.save(payment)

    async def test_rollback_removes_flushed_payment(self):
        saved = await self.create()
        self.sync.rollback()
        self.assertIsNone(await self.repo.find_by_id(saved.payment_id))

    def test_postgresql_schema_has_jsonb_timestamps_and_foreign_key(self):
        ddl = str(
            CreateTable(PaymentModel.__table__).compile(dialect=postgresql.dialect())
        )
        self.assertIn("JSONB", ddl)
        self.assertIn("TIMESTAMP WITH TIME ZONE", ddl)
        self.assertIn("FOREIGN KEY(reservation_id) REFERENCES reservations (id)", ddl)
        self.assertEqual(
            set(PaymentModel.__table__.columns.keys()),
            {
                "id",
                "reservation_id",
                "status",
                "method",
                "amount",
                "payment_key",
                "fail_reason",
                "paid_at",
                "canceled_at",
                "created_at",
                "updated_at",
                "payment_log",
            },
        )
        self.assertIn("UNIQUE (payment_key)", ddl)
