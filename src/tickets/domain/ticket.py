# 규칙, 예외, 티켓 엔티티 정리

"""
요구사항 정리

[생성]
1. 티켓은 예매(reservation_id)와 공연 회차(performance_id)에 속한다.
2. 새 티켓의 상태는 PENDING이다.
3. 공연 제목, 시작·종료 시각, 취소 마감 시각, 가격은 생성 시점의 값을 저장한다 (스냅샷).
4. 티켓 코드(ticket_code)는 입장 확인용 고유값이다.
5. 한 예매에는 티켓이 여러장 있을 수 있다.

[가격]
- 티켓 가격(price)은 공연의 정가를 생성 시점에 복사한 값이다.
- 할인은 예매(reservations)에서 계산하며 티켓 가격에는 반영하지 않는다. (팀 확인 필요)

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

from dataclasses import dataclass, field  # 엔티티 반복 코드 줄여주는 도구
from datetime import datetime
from uuid import UUID, uuid4

from tickets.domain.enums import TicketStatus
from tickets.domain.exceptions import InvalidTicketPerformanceTime, InvalidTicketPrice


# 티켓양식
@dataclass
class Ticket:
    # 기본값이 없는 필드 반드시 먼저 정의

    reservation_id: int
    performance_id: int
    price: int
    performance_title: str
    performance_start_at: (
        datetime  # 관례적으로 3인칭 단수 동사형을 따르는게 맞으나 db컬럼명이라 유지
    )
    performance_end_at: datetime
    cancel_deadline_at: datetime

    # 기본값이 있는 필드 나중에 정의
    # None은 "아직 DB에 저장되지 않음"을 뜻함. 저장 후 repository가 채워서 돌려준다
    id: int | None = None
    status: TicketStatus = TicketStatus.PENDING  # 기본 값 pending
    issued_at: datetime | None = None
    canceled_at: datetime | None = None
    used_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    ticket_code: UUID = field(default_factory=uuid4)

    # 잘못된 티켓이 발행되지 않게 검증
    # self의 price, 공연 시각을 읽어야 해서 staticmethod가 아닌 인스턴스 메서드로 작성
    def __post_init__(self) -> None:
        if self.price <= 0:
            raise InvalidTicketPrice("가격은 0원보다 커야 합니다")
        if self.performance_end_at <= self.performance_start_at:
            raise InvalidTicketPerformanceTime(
                "공연 종료 시각은 시작 시각보다 뒤여야 합니다"
            )
