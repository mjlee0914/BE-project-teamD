"""티켓 상세 조회·단일 취소 + 예매 상세 조회 테스트 (본인 또는 관리자)."""

import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import httpx
from fastapi import FastAPI

from performances.domain.repository import PerformanceRepository
from reservations.application.service import ReservationService
from reservations.domain.enums import ReservationStatus
from reservations.domain.exceptions import ReservationNotFound
from reservations.domain.repository import ReservationRepository
from reservations.domain.reservation import Reservation
from reservations.presentation.dependencies import provide_reservation_service
from reservations.presentation.routers.v1.router import router as reservation_router
from shared.core.actor import CurrentActor, get_current_actor
from shared.core.enums import TicketType
from shared.core.exception_handlers import register_exception_handlers
from tickets.application.service import TicketCancelResult, TicketService
from tickets.domain.enums import TicketStatus
from tickets.domain.exceptions import TicketNotCancelable, TicketNotFound
from tickets.domain.repository import TicketRepository
from tickets.domain.ticket import Ticket
from tickets.presentation.dependencies import get_ticket_service
from tickets.presentation.routers.v1.router import router as ticket_router

OWNER, OTHER, ADMIN = 1, 2, 99


def make_ticket(ticket_id=10, deadline_delta=timedelta(days=1)) -> Ticket:
    now = datetime.now(UTC)
    t = Ticket(
        reservation_id=5,
        performance_id=3,
        price=10000,
        performance_title="토요일 공연",
        performance_start_at=now + timedelta(days=2),
        performance_end_at=now + timedelta(days=2, hours=3),
        cancel_deadline_at=now + deadline_delta,
        id=ticket_id,
        created_at=now,
    )
    t.confirm(now)
    return t


def make_reservation(user_id=OWNER) -> Reservation:
    now = datetime.now(UTC)
    return Reservation(
        festival_id=1,
        user_id=user_id,
        quantity=1,
        ticket_type=TicketType.SAT,
        total_price=10000,
        final_price=10000,
        festival_name="축제",
        venue="장소",
        id=5,
        status=ReservationStatus.CONFIRMED,
        created_at=now,
        expires_at=now + timedelta(minutes=30),
    )


# ---------------- 서비스 ----------------
class TicketServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.ticket = make_ticket()
        self.reservation = make_reservation()
        self.ticket_repo = AsyncMock(spec=TicketRepository)
        self.reservation_repo = AsyncMock(spec=ReservationRepository)
        self.performance_repo = AsyncMock(spec=PerformanceRepository)
        self.performance_repo.find_by_id.return_value = None

        # 저장소 흉내: 본인 조회는 소유자일 때만 반환
        async def for_user(ticket_id, user_id):
            return self.ticket if user_id == OWNER and ticket_id == 10 else None

        self.ticket_repo.find_by_id_for_user.side_effect = for_user
        self.ticket_repo.find_by_id.side_effect = lambda tid: (
            self.ticket if tid == 10 else None
        )
        self.ticket_repo.find_all_by_reservation.side_effect = lambda rid: [self.ticket]
        self.ticket_repo.save.side_effect = lambda t: t
        self.reservation_repo.find_by_id.return_value = self.reservation
        self.reservation_repo.save.side_effect = lambda r: r
        self.service = TicketService(
            self.ticket_repo, self.reservation_repo, self.performance_repo
        )

    async def test_owner_gets_ticket(self):
        got = await self.service.get_ticket(10, OWNER)
        self.assertEqual(got.id, 10)

    async def test_other_user_gets_404(self):
        with self.assertRaises(TicketNotFound):
            await self.service.get_ticket(10, OTHER)

    async def test_admin_gets_any_ticket(self):
        got = await self.service.get_ticket(10, ADMIN, is_admin=True)
        self.assertEqual(got.id, 10)
        self.ticket_repo.find_by_id.assert_awaited_once_with(10)

    async def test_admin_missing_ticket_404(self):
        with self.assertRaises(TicketNotFound):
            await self.service.get_ticket(999, ADMIN, is_admin=True)

    async def test_owner_cancels_ticket_and_reservation_follows(self):
        got = await self.service.cancel_ticket(10, OWNER)
        self.assertEqual(got.ticket.status, TicketStatus.CANCELED)
        self.assertEqual(got.canceled_ticket_ids, [10])
        # 예매의 티켓이 전부 취소됐으므로 예매도 취소
        self.assertEqual(self.reservation.status, ReservationStatus.CANCELED)

    async def test_other_user_cannot_cancel(self):
        with self.assertRaises(TicketNotFound):
            await self.service.cancel_ticket(10, OTHER)
        self.ticket_repo.save.assert_not_awaited()

    async def test_admin_cancels_other_users_ticket(self):
        got = await self.service.cancel_ticket(10, ADMIN, is_admin=True)
        self.assertEqual(got.ticket.status, TicketStatus.CANCELED)

    async def test_cancel_after_deadline_conflict(self):
        self.ticket = make_ticket(deadline_delta=timedelta(days=-1))
        with self.assertRaises(TicketNotCancelable):
            await self.service.cancel_ticket(10, OWNER)


class ReservationDetailServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.repo = AsyncMock(spec=ReservationRepository)
        self.repo.find_by_id.return_value = make_reservation()
        self.service = ReservationService.__new__(ReservationService)
        self.service._reservation_repo = self.repo

    async def test_owner_and_admin_can_read(self):
        self.assertEqual((await self.service.get_reservation(5, OWNER, False)).id, 5)
        self.assertEqual((await self.service.get_reservation(5, ADMIN, True)).id, 5)

    async def test_other_user_404(self):
        with self.assertRaises(ReservationNotFound):
            await self.service.get_reservation(5, OTHER, False)

    async def test_missing_404(self):
        self.repo.find_by_id.return_value = None
        with self.assertRaises(ReservationNotFound):
            await self.service.get_reservation(5, ADMIN, True)


# ---------------- API ----------------
class DetailCancelAPITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = FastAPI()
        register_exception_handlers(self.app)
        self.app.include_router(ticket_router)
        self.app.include_router(reservation_router)
        self.ticket_service = AsyncMock(spec=TicketService)
        self.reservation_service = AsyncMock(spec=ReservationService)
        self.actor = CurrentActor(user_id=OWNER, is_admin=False)
        self.app.dependency_overrides.update(
            {
                get_ticket_service: lambda: self.ticket_service,
                provide_reservation_service: lambda: self.reservation_service,
                get_current_actor: lambda: self.actor,
            }
        )
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app), base_url="http://test"
        )

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_ticket_detail(self):
        self.ticket_service.get_ticket.return_value = make_ticket()
        res = await self.client.get("/v1/tickets/10")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["data"]["ticket_id"], 10)
        self.ticket_service.get_ticket.assert_awaited_once_with(10, OWNER, False)

    async def test_ticket_detail_admin_flag_passed(self):
        self.actor = CurrentActor(user_id=ADMIN, is_admin=True)
        self.ticket_service.get_ticket.return_value = make_ticket()
        res = await self.client.get("/v1/tickets/10")
        self.assertEqual(res.status_code, 200)
        self.ticket_service.get_ticket.assert_awaited_once_with(10, ADMIN, True)

    async def test_ticket_detail_not_found(self):
        self.ticket_service.get_ticket.side_effect = TicketNotFound()
        res = await self.client.get("/v1/tickets/10")
        self.assertEqual(res.status_code, 404)

    async def test_ticket_cancel(self):
        ticket = make_ticket()
        ticket.cancel(datetime.now(UTC))
        self.ticket_service.cancel_ticket.return_value = TicketCancelResult(
            ticket=ticket, canceled_ticket_ids=[10]
        )
        res = await self.client.patch("/v1/tickets/10/cancel")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["data"]["status"], "CANCELED")
        self.assertEqual(res.json()["data"]["canceled_ticket_ids"], [10])
        self.ticket_service.cancel_ticket.assert_awaited_once_with(10, OWNER, False)

    async def test_ticket_cancel_conflict(self):
        self.ticket_service.cancel_ticket.side_effect = TicketNotCancelable()
        res = await self.client.patch("/v1/tickets/10/cancel")
        self.assertEqual(res.status_code, 409)

    async def test_reservation_detail(self):
        self.reservation_service.get_reservation.return_value = make_reservation()
        res = await self.client.get("/v1/reservations/5")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["data"]["reservation_id"], 5)
        self.reservation_service.get_reservation.assert_awaited_once_with(
            5, OWNER, False
        )

    async def test_reservation_detail_not_found(self):
        self.reservation_service.get_reservation.side_effect = ReservationNotFound()
        res = await self.client.get("/v1/reservations/5")
        self.assertEqual(res.status_code, 404)
