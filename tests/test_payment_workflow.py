import json
import os
import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

import httpx
from sqlalchemy import insert, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from festivals.infrastructure.models import Festival
from main import app
from payments.infrastructure import recovery_job
from payments.infrastructure.models import PaymentModel
from payments.infrastructure.toss_service import TossPaymentProcessor
from performances.infrastructure.models import Performance
from reservations.application.service import ReservationService
from reservations.infrastructure.models import Reservation
from shared.core.database import engine, get_db
from shared.core.models import Base, init_models
from tickets.infrastructure.models import Ticket
from wiring.reservation import build_reservation_service

provider = {}
deadlines = {}
steps = []


def transport(request):
    body = json.loads(request.content) if request.content else {}
    path = request.url.path
    if path.endswith("/confirm"):
        key = body["paymentKey"]
        if key.startswith("reject"):
            return httpx.Response(400, json={"code": "UNAUTHORIZED_KEY"})
        virtual = key.startswith("virtual")
        data = {
            "paymentKey": key,
            "orderId": body["orderId"],
            "totalAmount": body["amount"],
            "balanceAmount": body["amount"],
            "status": "WAITING_FOR_DEPOSIT" if virtual else "DONE",
            "method": "가상계좌" if virtual else "카드",
            "approvedAt": None if virtual else datetime.now(UTC).isoformat(),
        }
        if virtual:
            data["secret"] = "isolated-deposit-secret"
            data["virtualAccount"] = {"dueDate": deadlines[body["orderId"]]}
        provider[key] = data
        if key.startswith("uncertain"):
            return httpx.Response(500, json={"code": "PROVIDER_TIMEOUT"})
        return httpx.Response(200, json=data)
    key = path.split("/")[-2] if path.endswith("/cancel") else path.split("/")[-1]
    data = provider[key]
    if path.endswith("/cancel"):
        data.update(
            status="CANCELED",
            balanceAmount=0,
            cancels=[
                {
                    "cancelStatus": "DONE",
                    "canceledAt": datetime.now(UTC).isoformat(),
                }
            ],
        )
        if data.pop("simulate_lost_cancel_response", False):
            return httpx.Response(500, json={"code": "PROVIDER_TIMEOUT"})
    return httpx.Response(200, json=data)


async def run_workflow():
    init_models()
    schema = "scenario_160_" + uuid4().hex
    original_overrides = app.dependency_overrides.copy()
    original_factory = recovery_job.AsyncSessionLocal
    provider.clear()
    deadlines.clear()
    steps.clear()
    try:
        async with engine.connect() as connection:
            names = (
                (
                    await connection.execute(
                        text(
                            "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
                        )
                    )
                )
                .scalars()
                .all()
            )
            print("PUBLIC_TABLES", ",".join(sorted(names)), flush=True)
            print(
                "CURRENT_SCHEMA",
                await connection.scalar(text("SELECT current_schema()")),
                flush=True,
            )
            await connection.rollback()
            outer = await connection.begin()
            try:
                await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
                await connection.execution_options(schema_translate_map={None: schema})
                await connection.run_sync(Base.metadata.create_all)

                async def isolated_db():
                    async with AsyncSession(
                        bind=connection,
                        expire_on_commit=False,
                        join_transaction_mode="create_savepoint",
                    ) as session:
                        try:
                            yield session
                            await session.commit()
                        except Exception:
                            await session.rollback()
                            raise

                app.dependency_overrides[get_db] = isolated_db
                recovery_job.AsyncSessionLocal = lambda: AsyncSession(
                    bind=connection,
                    expire_on_commit=False,
                    join_transaction_mode="create_savepoint",
                )

                async def make_festival():
                    now = datetime.now(UTC)
                    saturday = now.date() + timedelta(days=14)
                    saturday += timedelta(days=(5 - saturday.weekday()) % 7)
                    festival_id = await connection.scalar(
                        insert(Festival)
                        .values(
                            name="Isolated Scenario",
                            venue="Test Venue",
                            starts_on=saturday,
                            ends_on=saturday + timedelta(days=1),
                        )
                        .returning(Festival.id)
                    )
                    for day in (0, 1):
                        start = datetime.combine(
                            saturday + timedelta(days=day), datetime.min.time(), UTC
                        ) + timedelta(hours=5)
                        await connection.execute(
                            insert(Performance).values(
                                festival_id=festival_id,
                                title=f"DAY {day + 1}",
                                starts_at=start,
                                ends_at=start + timedelta(hours=3),
                                booking_open_at=now - timedelta(days=1),
                                booking_close_at=start - timedelta(days=1),
                                cancel_deadline_at=start - timedelta(hours=2),
                                capacity=20,
                                remaining_count=20,
                                price=1000,
                                status="OPEN",
                                version=1,
                            )
                        )
                    return festival_id

                async with httpx.AsyncClient(
                    transport=httpx.MockTransport(transport)
                ) as toss:
                    with patch.object(
                        TossPaymentProcessor,
                        "from_env",
                        side_effect=lambda: TossPaymentProcessor(
                            "test_sk_isolated", client=toss
                        ),
                    ):
                        async with httpx.AsyncClient(
                            transport=httpx.ASGITransport(
                                app=app, raise_app_exceptions=False
                            ),
                            base_url="http://scenario",
                        ) as api:

                            async def call(
                                label,
                                method,
                                path,
                                expected=200,
                                body=None,
                                headers=None,
                            ):
                                response = await api.request(
                                    method, path, json=body, headers=headers
                                )
                                payload = response.json() if response.content else {}
                                print(
                                    label,
                                    response.status_code,
                                    payload.get("code", ""),
                                    flush=True,
                                )
                                steps.append((label, response.status_code))
                                assert response.status_code == expected, (
                                    label,
                                    payload,
                                )
                                return payload.get("data")

                            credentials = {
                                "email": "scenario160@example.com",
                                "password": "ScenarioTest123!",
                            }
                            await call(
                                "signup",
                                "POST",
                                "/v1/users",
                                201,
                                {**credentials, "name": "Scenario User"},
                            )
                            token = (
                                await call(
                                    "login", "POST", "/v1/auth/login", body=credentials
                                )
                            )["access_token"]
                            auth = {"Authorization": "Bearer " + token}
                            await call("me", "GET", "/v1/users/me", headers=auth)
                            await call(
                                "missing-token",
                                "POST",
                                "/v1/reservations",
                                401,
                                {"festival_id": 1, "ticket_type": "SAT", "quantity": 1},
                            )

                            async def create_case(label, ticket_type="SAT", quantity=1):
                                festival_id = await make_festival()
                                reservation = await call(
                                    label + "-reservation",
                                    "POST",
                                    "/v1/reservations",
                                    201,
                                    {
                                        "festival_id": festival_id,
                                        "ticket_type": ticket_type,
                                        "quantity": quantity,
                                    },
                                    auth,
                                )
                                payment = await call(
                                    label + "-payment",
                                    "POST",
                                    "/v1/payments",
                                    201,
                                    {"reservation_id": reservation["reservation_id"]},
                                    auth,
                                )
                                deadlines[payment["order_id"]] = reservation[
                                    "deposit_due_at"
                                ]
                                return (
                                    festival_id,
                                    reservation["reservation_id"],
                                    payment,
                                )

                            async def counts(rid):
                                rows = (
                                    (
                                        await connection.execute(
                                            select(Ticket.status).where(
                                                Ticket.reservation_id == rid
                                            )
                                        )
                                    )
                                    .scalars()
                                    .all()
                                )
                                return [str(row) for row in rows]

                            for label, kind, quantity in [
                                ("card", "SAT", 1),
                                ("both", "BOTH", 2),
                            ]:
                                fid, rid, payment = await create_case(
                                    label, kind, quantity
                                )
                                pid = payment["payment_id"]
                                with patch.dict(
                                    os.environ, {"TOSS_CLIENT_KEY": "test_ck_isolated"}
                                ):
                                    config = await call(
                                        label + "-checkout-config",
                                        "GET",
                                        f"/v1/payments/{pid}/checkout",
                                        headers=auth,
                                    )
                                from shared.core.time import KST

                                due = (
                                    datetime.fromisoformat(
                                        config["virtual_account_due_date"]
                                    )
                                    .replace(tzinfo=KST)
                                    .astimezone(UTC)
                                )
                                assert due.replace(
                                    microsecond=0
                                ) == datetime.fromisoformat(
                                    deadlines[payment["order_id"]]
                                ).replace(microsecond=0)
                                assert "secret" not in config
                                approval = {
                                    "payment_key": label + "-key",
                                    "amount": payment["amount"],
                                }
                                approved = await call(
                                    label + "-approve",
                                    "POST",
                                    f"/v1/payments/{pid}/approve",
                                    body=approval,
                                    headers=auth,
                                )
                                assert approved["status"] == "DONE"
                                reservation = await call(
                                    label + "-confirmed",
                                    "GET",
                                    f"/v1/reservations/{rid}",
                                    headers=auth,
                                )
                                assert reservation["status"] == "CONFIRMED"
                                expected_tickets = quantity * (
                                    2 if kind == "BOTH" else 1
                                )
                                assert (
                                    await counts(rid) == ["ISSUED"] * expected_tickets
                                )
                                await call(
                                    label + "-duplicate-approval",
                                    "POST",
                                    f"/v1/payments/{pid}/approve",
                                    body=approval,
                                    headers=auth,
                                )
                                assert len(await counts(rid)) == expected_tickets
                                await call(
                                    label + "-ticket-list",
                                    "GET",
                                    "/v1/tickets",
                                    headers=auth,
                                )
                                canceled = await call(
                                    label + "-cancel-payment",
                                    "POST",
                                    f"/v1/payments/{pid}/cancel",
                                    body={"reason": "scenario refund"},
                                    headers=auth,
                                )
                                assert canceled["status"] == "CANCELED"
                                current = await connection.scalar(
                                    select(Reservation.status).where(
                                        Reservation.id == rid
                                    )
                                )
                                print(
                                    label + "-after-refund",
                                    "reservation=" + str(current),
                                    "tickets=" + ",".join(await counts(rid)),
                                    flush=True,
                                )
                                await call(
                                    label + "-duplicate-cancel",
                                    "POST",
                                    f"/v1/payments/{pid}/cancel",
                                    body={"reason": "scenario refund"},
                                    headers=auth,
                                )
                                await call(
                                    label + "-cancel-reservation",
                                    "PATCH",
                                    f"/v1/reservations/{rid}/cancel",
                                    409,
                                    headers=auth,
                                )
                                assert (
                                    await counts(rid) == ["CANCELED"] * expected_tickets
                                )
                                remaining = (
                                    (
                                        await connection.execute(
                                            select(Performance.remaining_count).where(
                                                Performance.festival_id == fid
                                            )
                                        )
                                    )
                                    .scalars()
                                    .all()
                                )
                                assert all(value == 20 for value in remaining), (
                                    remaining
                                )

                            _, rid, payment = await create_case("rejection")
                            pid = payment["payment_id"]
                            await call(
                                "rejection-approve",
                                "POST",
                                f"/v1/payments/{pid}/approve",
                                502,
                                {"payment_key": "reject-key", "amount": 1000},
                                auth,
                            )
                            state = await call(
                                "rejection-state",
                                "GET",
                                f"/v1/payments/{pid}",
                                headers=auth,
                            )
                            assert state["status"] == "ABORTED"
                            retry = await call(
                                "rejection-new-payment",
                                "POST",
                                "/v1/payments",
                                201,
                                {"reservation_id": rid},
                                auth,
                            )
                            await call(
                                "rejection-retry-approve",
                                "POST",
                                f"/v1/payments/{retry['payment_id']}/approve",
                                body={"payment_key": "retry-key", "amount": 1000},
                                headers=auth,
                            )

                            _, rid, payment = await create_case("uncertain")
                            pid = payment["payment_id"]
                            await call(
                                "uncertain-approve",
                                "POST",
                                f"/v1/payments/{pid}/approve",
                                502,
                                {"payment_key": "uncertain-key", "amount": 1000},
                                auth,
                            )
                            await call(
                                "uncertain-block-duplicate",
                                "POST",
                                "/v1/payments",
                                409,
                                {"reservation_id": rid},
                                auth,
                            )
                            reconciled = await call(
                                "uncertain-reconcile",
                                "POST",
                                f"/v1/payments/{pid}/reconcile",
                                body={},
                                headers=auth,
                            )
                            assert reconciled["status"] == "DONE"
                            assert await counts(rid) == ["ISSUED"]

                            _, rid, payment = await create_case("virtual")
                            pid = payment["payment_id"]
                            waiting = await call(
                                "virtual-approve",
                                "POST",
                                f"/v1/payments/{pid}/approve",
                                body={"payment_key": "virtual-key", "amount": 1000},
                                headers=auth,
                            )
                            assert waiting["status"] == "WAITING_FOR_DEPOSIT"
                            assert await counts(rid) == []
                            provider["virtual-key"].update(
                                status="DONE", approvedAt=datetime.now(UTC).isoformat()
                            )
                            event = {
                                "orderId": payment["order_id"],
                                "secret": "isolated-deposit-secret",
                                "transactionKey": "deposit-event",
                                "status": "DONE",
                            }
                            await call(
                                "virtual-webhook",
                                "POST",
                                "/v1/payments/webhooks/deposit",
                                204,
                                event,
                            )
                            await call(
                                "virtual-duplicate-webhook",
                                "POST",
                                "/v1/payments/webhooks/deposit",
                                204,
                                event,
                            )
                            assert await counts(rid) == ["ISSUED"]

                            pending = await call(
                                "virtual-refund-needs-account",
                                "POST",
                                f"/v1/payments/{pid}/cancel",
                                202,
                                {"reason": "refund"},
                                auth,
                            )
                            assert (
                                pending["recovery_status"] == "REFUND_ACCOUNT_REQUIRED"
                            )
                            refunded = await call(
                                "virtual-refund-with-account",
                                "POST",
                                f"/v1/payments/{pid}/cancel",
                                body={
                                    "reason": "refund",
                                    "refund_account": {
                                        "bank": "88",
                                        "account_number": "1234567890",
                                        "holder_name": "Test User",
                                    },
                                },
                                headers=auth,
                            )
                            assert refunded["status"] == "CANCELED"

                            _, rid, payment = await create_case("reservation-first")
                            pid = payment["payment_id"]
                            await call(
                                "reservation-first-approve",
                                "POST",
                                f"/v1/payments/{pid}/approve",
                                body={
                                    "payment_key": "reservation-first-key",
                                    "amount": 1000,
                                },
                                headers=auth,
                            )
                            await call(
                                "reservation-first-cancel",
                                "PATCH",
                                f"/v1/reservations/{rid}/cancel",
                                headers=auth,
                            )
                            payment_state = await connection.scalar(
                                select(PaymentModel.status).where(
                                    PaymentModel.id == pid
                                )
                            )
                            print(
                                "RESERVATION_CANCEL_PAYMENT_STATE",
                                str(payment_state),
                                flush=True,
                            )
                            await recovery_job.run_recovery_once()
                            payment_state = await connection.scalar(
                                select(PaymentModel.status).where(
                                    PaymentModel.id == pid
                                )
                            )
                            assert str(payment_state) == "CANCELED", payment_state
                            print(
                                "RESERVATION_CANCEL_AFTER_WORKER",
                                str(payment_state),
                                flush=True,
                            )

                            _, rid, payment = await create_case(
                                "deadline-during-provider"
                            )
                            pid = payment["payment_id"]
                            expiry = await connection.scalar(
                                select(Reservation.expires_at).where(
                                    Reservation.id == rid
                                )
                            )
                            with patch(
                                "reservations.application.service.now_utc",
                                return_value=expiry + timedelta(seconds=1),
                            ):
                                await call(
                                    "deadline-during-provider-approve",
                                    "POST",
                                    f"/v1/payments/{pid}/approve",
                                    200,
                                    {"payment_key": "late-key", "amount": 1000},
                                    auth,
                                )
                            payment_state = await connection.scalar(
                                select(PaymentModel.status).where(
                                    PaymentModel.id == pid
                                )
                            )
                            reservation_state = await connection.scalar(
                                select(Reservation.status).where(Reservation.id == rid)
                            )
                            print(
                                "APPROVAL_DEADLINE_STATE",
                                "provider=" + provider["late-key"]["status"],
                                "db_payment=" + str(payment_state),
                                "reservation=" + str(reservation_state),
                                flush=True,
                            )
                            assert str(payment_state) == "CANCELED"

                            _, rid, payment = await create_case("ticket-failure")
                            pid = payment["payment_id"]
                            original_issue = ReservationService._issue_tickets

                            async def issue_then_fail(
                                service, reservation, performances
                            ):
                                await original_issue(service, reservation, performances)
                                raise RuntimeError(
                                    "simulated crash after ticket insert"
                                )

                            with patch.object(
                                ReservationService, "_issue_tickets", issue_then_fail
                            ):
                                await call(
                                    "ticket-failure-approve",
                                    "POST",
                                    f"/v1/payments/{pid}/approve",
                                    500,
                                    {
                                        "payment_key": "ticket-failure-key",
                                        "amount": 1000,
                                    },
                                    auth,
                                )
                            state = await connection.scalar(
                                select(PaymentModel.status).where(
                                    PaymentModel.id == pid
                                )
                            )
                            assert str(state) == "IN_PROGRESS"
                            assert await counts(rid) == []
                            # 승인 중인 요청과 경합하지 않도록 복구 작업은 30초 지난 건만 조회한다.
                            await connection.execute(
                                update(PaymentModel)
                                .where(PaymentModel.id == pid)
                                .values(
                                    updated_at=datetime.now(UTC) - timedelta(seconds=31)
                                )
                            )
                            await recovery_job.run_recovery_once()
                            assert await counts(rid) == ["ISSUED"]

                            provider["ticket-failure-key"][
                                "simulate_lost_cancel_response"
                            ] = True
                            await call(
                                "lost-cancel-response",
                                "POST",
                                f"/v1/payments/{pid}/cancel",
                                502,
                                {"reason": "customer refund"},
                                auth,
                            )
                            await recovery_job.run_recovery_once()
                            state = await connection.scalar(
                                select(PaymentModel.status).where(
                                    PaymentModel.id == pid
                                )
                            )
                            assert str(state) == "CANCELED"
                            assert await counts(rid) == ["CANCELED"]

                            fid, rid, payment = await create_case("waiting-expiry")
                            pid = payment["payment_id"]
                            await call(
                                "waiting-expiry-approve",
                                "POST",
                                f"/v1/payments/{pid}/approve",
                                body={
                                    "payment_key": "virtual-expiry-key",
                                    "amount": 1000,
                                },
                                headers=auth,
                            )
                            async with recovery_job.AsyncSessionLocal() as session:
                                await build_reservation_service(session).expire_overdue(
                                    datetime.now(UTC) + timedelta(minutes=11)
                                )
                                await session.commit()
                            await recovery_job.run_recovery_once()
                            state = await connection.scalar(
                                select(PaymentModel.status).where(
                                    PaymentModel.id == pid
                                )
                            )
                            assert str(state) == "CANCELED"
                            assert await counts(rid) == []

                            await call(
                                "logout", "POST", "/v1/auth/logout", 204, headers=auth
                            )
                            await call(
                                "revoked-token",
                                "GET",
                                f"/v1/payments/{pid}",
                                401,
                                headers=auth,
                            )
                            print(
                                "SCENARIO_PASS", len(steps), "HTTP requests", flush=True
                            )
            finally:
                if outer.is_active:
                    await outer.rollback()
                exists = await connection.scalar(
                    text(
                        "SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname=:name)"
                    ),
                    {"name": schema},
                )
                print("TEMP_SCHEMA_REMOVED", not exists, flush=True)
                await connection.rollback()
    finally:
        recovery_job.AsyncSessionLocal = original_factory
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original_overrides)
        await engine.dispose()


@unittest.skipUnless(
    os.getenv("RUN_PAYMENT_POSTGRES_TESTS") == "1", "?? DB ????? ????? ??"
)
class PaymentWorkflowPostgresTests(unittest.IsolatedAsyncioTestCase):
    async def test_login_reservation_approval_refund_and_recovery(self):
        with patch.dict(
            os.environ, {"JWT_SECRET_KEY": "isolated-workflow-secret-" * 4}
        ):
            await run_workflow()
