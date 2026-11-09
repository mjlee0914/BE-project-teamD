from reservations.domain.enums import ReservationStatus
from reservations.domain.exceptions import OverReservationQuantity
from shared.core.enums import TicketType

MAX_PER_DAY = 2

TICKET_DAYS = {
    TicketType.SAT: [TicketType.SAT],
    TicketType.SUN: [TicketType.SUN],
    TicketType.BOTH: [TicketType.SAT, TicketType.SUN],
}


def check_daily_limit(existing, ticket_type, quantity):
    """
    existing : 기존 예매 목록
    ticket_type : 티켓 종류 'SAT', 'SUN', 'BOTH'
    quantity : 수량
    """

    # 토요일, 일요일 날짜별 티켓 수량 초기화
    counts = {TicketType.SAT: 0, TicketType.SUN: 0}

    for i in existing:
        if i.status in (ReservationStatus.CANCELED, ReservationStatus.EXPIRED):
            # 예매의 상태가 취소, 만료 상태이면 티켓 수량이 0이기 때문에 넘어감
            continue

        for day in TICKET_DAYS[i.ticket_type]:
            # 티켓 타입별로 count에 기존 예매의 티켓 수량 더하기
            counts[day] += i.quantity

    for day in TICKET_DAYS[ticket_type]:
        if (counts[day] + quantity) > MAX_PER_DAY:
            # 만약 기존 예매 수량 + 신규 예매 수량이 최대 예매 가능 수량보다 크면 오류 발생
            raise OverReservationQuantity(
                f"신규 예매로 인해 {MAX_PER_DAY}의 범위를 벗어납니다 , 날짜 : {day}, 기존 예매 수량 : {counts[day]}, 신규 예매 수량 : {quantity}"
            )
