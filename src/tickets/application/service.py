# DB와web을 모르는 중간 단계 담당자
# usecase 는 설계도만 지키고, 어떤 저장소가 들어오는지는 wiring이 정함


from tickets.domain.exceptions import TicketNotFound
from tickets.domain.repository import TicketRepository  # 설계도 가져오기
from tickets.domain.ticket import Ticket  # 반환타입


# 티켓과 관련된 업무를 모아두는 상자
class TicketService:
    def __init__(
        self, ticket_repo: TicketRepository
    ) -> None:  # 저장소 받기. 밖에서 저장소를 하나 받고, 타입은 설계도. 이 함수는 돌려주는 값이 없음.
        self._ticket_repo = ticket_repo

    async def get_my_ticket(self, ticket_id: int, user_id: int) -> Ticket:
        ticket = await self._ticket_repo.find_by_id_for_user(ticket_id, user_id)
        if ticket is None:
            raise TicketNotFound()
        return ticket
