# 라우터가 요청할 추상 의존성 선언

from tickets.application.service import TicketService


def get_ticket_service() -> TicketService:
    raise NotImplementedError("wiring/ticket.py에서 연결되지 않았습니다.")
