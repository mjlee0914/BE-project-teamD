"""실제 PostgreSQL 검증. RUN_PAYMENT_POSTGRES_TESTS=1일 때만 격리 스키마를 생성하고 롤백한다."""

import importlib
import os
import unittest
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

from dotenv import load_dotenv
from sqlalchemy import insert, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from payments.application.service import PaymentService
from payments.application.webhook_service import DepositWebhookService
from payments.domain.entities import Payment, PaymentLog
from payments.domain.enums import PaymentStatus
from payments.domain.exceptions import (
    PaymentAttemptConflict,
    PaymentConcurrentUpdate,
    PaymentDuplicateIdentifier,
    PaymentProcessingError,
)
from payments.domain.service import (
    PaymentApprovalResult,
    PaymentCancellationResult,
    PaymentProcessor,
    PaymentSnapshot,
    RefundAccount,
)
from payments.infrastructure.models import PaymentModel
from payments.infrastructure.sqlalchemy_repository import SQLAlchemyPaymentRepository
from reservations.infrastructure.models import Reservation as ReservationModel
from shared.core.models import Base


@unittest.skipUnless(
    os.getenv("RUN_PAYMENT_POSTGRES_TESTS") == "1",
    "PostgreSQL 통합 검증은 명시적으로 실행",
)
class PaymentPostgresTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        load_dotenv(Path(__file__).resolve().parents[1] / ".env")
        raw = os.getenv("PAYMENTS_TEST_DATABASE_URL") or os.getenv("DATABASE_URL")
        if not raw:
            self.fail("테스트용 PostgreSQL 연결 설정이 필요합니다.")
        url = make_url(raw).set(drivername="postgresql+asyncpg")
        self.engine = create_async_engine(
            url,
            poolclass=NullPool,
            connect_args={
                "timeout": 5,
                "server_settings": {
                    "statement_timeout": "10000",
                    "lock_timeout": "3000",
                },
            },
        )
        self.addAsyncCleanup(self.engine.dispose)
        self.connection = await self.engine.connect()
        self.addAsyncCleanup(self.connection.close)
        self.transaction = await self.connection.begin()
        self.schema = "payment_test_" + uuid4().hex

        async def rollback_and_verify():
            if self.transaction.is_active:
                await self.transaction.rollback()
            exists = await self.connection.scalar(
                text("SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname=:name)"),
                {"name": self.schema},
            )
            self.assertFalse(exists, "테스트용 스키마가 남아 있습니다.")
            await self.connection.rollback()

        self.addAsyncCleanup(rollback_and_verify)
        await self.connection.execute(text(f'CREATE SCHEMA "{self.schema}"'))
        await self.connection.execution_options(
            schema_translate_map={None: self.schema}
        )
        for module in ("users", "festivals", "reservations", "payments"):
            importlib.import_module(module + ".infrastructure.models")
        tables = [
            Base.metadata.tables[name]
            for name in ("users", "festivals", "reservations", "payments")
        ]
        await self.connection.run_sync(
            lambda connection: Base.metadata.create_all(connection, tables=tables)
        )
        user_id = await self.connection.scalar(
            insert(Base.metadata.tables["users"])
            .values(
                email="test@example.com",
                name="Test User",
                password_hash="not-a-real-password",
            )
            .returning(Base.metadata.tables["users"].c.id)
        )
        festival_id = await self.connection.scalar(
            insert(Base.metadata.tables["festivals"])
            .values(
                name="Test Festival",
                venue="Test Venue",
                starts_on=date(2027, 1, 1),
                ends_on=date(2027, 1, 3),
            )
            .returning(Base.metadata.tables["festivals"].c.id)
        )
        self.reservation_id = await self.connection.scalar(
            insert(ReservationModel)
            .values(
                quantity=1,
                total_price=1000,
                discount_amount=0,
                final_price=1000,
                ticket_type="SAT",
                expires_at=datetime.now(UTC) + timedelta(hours=1),
                festival_name="Test Festival",
                venue="Test Venue",
                user_id=user_id,
                festival_id=festival_id,
            )
            .returning(ReservationModel.id)
        )
        self.session = AsyncSession(
            bind=self.connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        self.addAsyncCleanup(self.session.close)
        self.repository = SQLAlchemyPaymentRepository(self.session)

    async def create(self):
        return await self.repository.save(
            Payment.create(self.reservation_id, "Test Festival", 1000)
        )

    async def test_updated_at_is_null_until_first_change(self):
        saved = await self.create()
        self.assertIsNone(saved.updated_at)
        loaded = await self.repository.find_by_id(saved.payment_id)
        self.assertIsNone(loaded.updated_at)
        loaded.fail("declined")
        changed = await self.repository.save(loaded)
        self.assertIsNotNone(changed.updated_at)
        self.assertIsNotNone(changed.updated_at.utcoffset())

    async def test_status_constraint_rejects_unknown_value(self):
        # ORM의 입력 검사와 별개로 PostgreSQL CHECK가 허용되지 않은 상태를 막는지 확인한다.
        with self.assertRaises(IntegrityError):
            await self.session.execute(
                text(
                    "INSERT INTO payments (reservation_id, amount, status, payment_log) "
                    "VALUES (:reservation_id, 1000, 'UNKNOWN', '[]'::jsonb)"
                ),
                {"reservation_id": self.reservation_id},
            )

    async def test_jsonb_identity_metadata_and_timezone_round_trip(self):
        payment = await self.create()
        payment.webhook_secret_hash = "a" * 64
        payment.processed_deposit_events = ["event-1"]
        await self.repository.save(payment)
        loaded = await self.repository.find_by_order_id(payment.order_id)
        self.assertEqual(loaded.webhook_secret_hash, "a" * 64)
        self.assertEqual(loaded.processed_deposit_events, ["event-1"])
        self.assertIsNotNone(loaded.created_at.tzinfo)
        self.assertEqual(loaded.reservation.reservation_id, self.reservation_id)
        self.assertEqual(len(PaymentModel.__table__.columns), 12)

    async def test_paid_and_canceled_state_round_trip(self):
        payment = await self.create()
        now = datetime.now(UTC)
        payment.approve(
            "test-key",
            1000,
            PaymentStatus.DONE,
            now,
            PaymentLog({"status": "DONE"}),
            "가상계좌",
        )
        paid = await self.repository.save(payment)
        paid.cancel(now, PaymentLog({"status": "CANCELED"}))
        await self.repository.save(paid)
        loaded = await self.repository.find_by_id(payment.payment_id)
        self.assertEqual(loaded.status, PaymentStatus.CANCELED)
        self.assertEqual(loaded.paid_at, now)
        self.assertEqual(loaded.cancelled_at, now)

    async def test_stale_write_is_rejected(self):
        first = await self.create()
        stale = await self.repository.find_by_id(first.payment_id)
        first.fail("declined")
        await self.repository.save(first)
        with self.assertRaises(PaymentConcurrentUpdate):
            await self.repository.save(stale)

    async def test_expression_index_prevents_duplicate_order(self):
        first = await self.create()
        duplicate = Payment.create(self.reservation_id, "Test Festival", 1000)
        duplicate.order_id = first.order_id
        with self.assertRaises(PaymentDuplicateIdentifier):
            await self.repository.save(duplicate)
        await self.session.rollback()

    async def test_reservation_lock_and_attempt_list(self):
        await self.repository.lock_reservation(self.reservation_id)
        first = await self.create()
        second = await self.create()
        attempts = await self.repository.find_by_reservation_id(self.reservation_id)
        self.assertEqual(
            [payment.payment_id for payment in attempts],
            [first.payment_id, second.payment_id],
        )

    async def test_uncertain_approval_keeps_recovery_key_when_request_commits(self):
        processor = AsyncMock(spec=PaymentProcessor)
        processor.approve.side_effect = PaymentProcessingError(
            "timeout", outcome_unknown=True
        )
        service = PaymentService(processor, self.repository)
        payment = await service.create(self.reservation_id, "Test Festival", 1000)
        with self.assertRaises(PaymentProcessingError):
            await service.approve(payment.payment_id, "uncertain-key", 1000)
        # 실제 API가 502 응답을 반환할 때 요청 세션에서 수행할 commit을 모사한다.
        # 이 테스트의 최상위 트랜잭션은 끝까지 rollback된다.
        await self.session.commit()
        pending = await self.repository.find_by_id(payment.payment_id)
        self.assertEqual(pending.status, PaymentStatus.IN_PROGRESS)
        self.assertEqual(pending.payment_key, "uncertain-key")

    async def test_service_approval_webhook_and_refund_with_real_repository(self):
        import hashlib

        processor = AsyncMock(spec=PaymentProcessor)
        service = PaymentService(processor, self.repository)
        payment = await service.create(self.reservation_id, "Test Festival", 1000)
        processor.approve.return_value = PaymentApprovalResult(
            PaymentStatus.WAITING_FOR_DEPOSIT,
            None,
            PaymentLog({"status": "WAITING_FOR_DEPOSIT"}),
            "가상계좌",
            hashlib.sha256(b"test-secret").hexdigest(),
        )
        waiting = await service.approve(payment.payment_id, "test-key", 1000)
        self.assertEqual(waiting.status, PaymentStatus.WAITING_FOR_DEPOSIT)
        second = await service.create(self.reservation_id, "Test Festival", 1000)
        with self.assertRaises(PaymentAttemptConflict):
            await service.approve(second.payment_id, "another-key", 1000)
        now = datetime.now(UTC)
        processor.retrieve.return_value = PaymentSnapshot(
            "test-key",
            payment.order_id,
            1000,
            PaymentStatus.DONE,
            now,
            None,
            PaymentLog({"status": "DONE"}),
            "가상계좌",
        )
        webhook = DepositWebhookService(processor, self.repository)
        for _ in range(2):
            await webhook.process(
                order_id=payment.order_id,
                secret="test-secret",
                transaction_key="deposit-1",
                status=PaymentStatus.DONE,
            )
        processor.retrieve.assert_awaited_once()
        loaded = await service.get_payment(payment.payment_id)
        self.assertEqual(loaded.status, PaymentStatus.DONE)
        processor.cancel.return_value = PaymentCancellationResult(
            now, PaymentLog({"status": "CANCELED"})
        )
        canceled = await service.cancel(
            payment.payment_id, refund_account=RefundAccount("088", "12345", "Test")
        )
        self.assertEqual(canceled.status, PaymentStatus.CANCELED)
