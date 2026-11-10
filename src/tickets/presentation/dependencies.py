# presentation/dependencies.py
# 라우터가 Depends()로 받아 쓰는 "자리표시자" 의존성 모음
# - 요청한 사람(CurrentActor, get_current_actor)은 모든 도메인이 공통으로 쓰는
#   shared/core/actor.py를 사용한다 (실제 구현은 wiring/actor.py)

from tickets.application.service import TicketService


def get_ticket_service() -> TicketService:
    raise NotImplementedError("wiring/ticket.py에서 연결되지 않았습니다.")