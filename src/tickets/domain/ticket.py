# 규칙, 예외, 티켓 엔티티 정리

"""
요구사항 정리

[생성]
1. 티켓은 예매(reservation_id)와 공연 회차(performance_id)에 속한다.
2. 새 티켓의 상태는 PENDING이다.
3. 공연 제목, 시작·종료 시각, 취소 마감 시각, 가격은 생성 시점의 값을 저장한다 (스냅샷).
4. 티켓 코드(ticket_code)는 입장 확인용 고유값이다.

[검증]
5. 가격은 0원보다 커야 한다.
6. 공연 종료 시각은 시작 시각보다 뒤여야 한다.

[상태 변경]
7. 예매가 확정되면 PENDING → ISSUED, issued_at을 기록한다.
8. 취소하면 ISSUED → CANCELED, canceled_at을 기록한다. (PENDING 취소 허용 여부는 팀 확인 필요)
9. 입장하면 ISSUED → USED, used_at을 기록한다.
10. 공연 종료 후 미사용이면 ISSUED → EXPIRED.
11. CANCELED, USED, EXPIRED는 끝난 상태라 다른 상태로 바꿀 수 없다.
"""

from dataclasses import dataclass  # 엔티티 반복 코드 줄여주는 도구
from datetime import datetime
from uuid import UUID

from tickets.domain.enums import TicketStatus


# 에러 클래스
class TicketError(ValueError):
    """티켓 규칙을 어겼을 때의 공통 예외"""


class NotCancelable(TicketError):
    """취소할 수 없는 티켓"""


class NotEnterable(TicketError):
    """입장할 수 없는 티켓"""


# 티켓양식
@dataclass
class Ticket:
    # 기본값이 없는 필드 반드시 먼저 정의
    reservation_id: int
    performance_id: int
    ticket_code: UUID
    price: int
    performance_title: str
    performance_start_at: datetime
    performance_end_at: datetime
    cancel_deadline_at: datetime

    # 기본값이 있는 필드 나중에 정의
    id: int | None = None
    status: TicketStatus = TicketStatus.PENDING  # 기본 값 pending
    issued_at: datetime | None = None
    canceled_at: datetime | None = None
    used_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    # 잘못된 티켓이 발행되지 않게 검증
    def __post_init__(self) -> None:
        if self.price <= 0:
            raise TicketError("가격은 0원 보다 커야 합니다")
        if self.performance_end_at <= self.performance_start_at:
            raise TicketError("공연 종료 시각은 시작 시각보다 뒤여야 합니다")
