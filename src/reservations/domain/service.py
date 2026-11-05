from reservations.domain.enums import TicketType

MAX_PER_DAY = 2

TICEKT_DAYS = {
    "SAT" : TicketType.SAT,
    "SUN" : TicketType.SUN,
    "BOTH" : TicketType.BOTH,
}

def check_daily_limit(existing, ticket_type, quantity):
    """
    existing : 기존 예매 존재 여부
    ticket_type : 티켓 종류 'SAT', 'SUN', 'BOTH'
    quantity : 수량
    """

    pass
