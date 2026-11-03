# 표준 라이브러리
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

# 프로젝트 코드
from reservations.domain.enums import ReservationStatus, TicketType

"""
[생성]
1. 예매는 회차(performances_id), 사용자(user_id), 수량, 티켓 종류, 금액, 축제 이름·장소를 받아 생성한다.
2. 새 예매의 상태는 항상 PENDING(입금 대기)이다.
3. 결제는 토스 가상계좌(무통장입금) 기준이며, 입금 기한(expires_at)은 생성 시각 + 24시간이다.
4. 축제 이름·장소·금액은 예매 시점의 값을 그대로 저장한다(스냅샷). 이후 축제 정보가 바뀌어도 예매 내역은 바뀌지 않는다.

[금액]
5. 수량은 1장 이상이어야 한다.
6. 총 금액은 0원 이상이어야 한다.
7. 할인 금액은 0원 이상이고 총 금액을 넘을 수 없다. 할인이 없으면 0원이다.
8. 최종 결제 금액은 총 금액 - 할인 금액이다.

[구매 수량 제한]
9. 사용자 1명은 토요일권 최대 2장, 일요일권 최대 2장, 합계 최대 4장까지 예매할 수 있다.
10. 양일권(BOTH) 1장은 토요일 1장 + 일요일 1장으로 계산한다. (팀 확인 필요)
11. 한 번의 예매 수량도 위 한도를 넘을 수 없다. (토요일권·일요일권·양일권 각각 최대 2장)
12. 이미 예매한 수량과 합산한 한도 검사는 기존 예매 조회가 필요하므로 application(service)에서 처리한다.
    - CANCELED, EXPIRED 예매는 합산에서 제외한다.

[상태 변경]
13. 입금이 완료되면 PENDING → CONFIRMED로 바뀌고 confirmed_at을 기록한다.
14. 입금 기한이 지나도록 입금하지 않으면 PENDING → EXPIRED로 바뀐다.
15. 예매를 취소하면 CANCELED로 바뀌고 canceled_at을 기록한다.
    - PENDING 상태에서는 취소할 수 있다.
    - CONFIRMED 상태(입금 완료)의 취소 가능 여부와 환불 처리는 팀 확인 필요.
16. CANCELED, EXPIRED는 끝난 상태이므로 다른 상태로 바꿀 수 없다.
17. 허용되지 않은 상태 변경을 시도하면 도메인 오류가 발생한다.
"""

DEPOSIT_EXPIRE_HOURS = 24


@dataclass
class Reservation:
    performances_id: int  # 회차 아이디
    user_id: int  # 사용자 아이디
    quantity: int  # 티켓 수량
    ticket_type: TicketType  # 티켓 타입
    total_price: int  # 총 금액
    final_price: int  # 최종 결제 금액
    festival_name: str  # 축제 이름
    venue: str  # 축제 장소

    # 기본값이 존재
    id: int | None = None  # 예매 아이디
    discount_amount: int = 0  # 할인 금액
    status: ReservationStatus = ReservationStatus.PENDING  # 예매 상태
    created_at: datetime | None = None  # 예매 생성 시간
    expires_at: datetime | None = None  # 예매 대기 만료 시간
    confirmed_at: datetime | None = None  # 예매 승인 시간
    canceled_at: datetime | None = None  # 예매 취소 시간
    updated_at: datetime | None = None  # 예매 수정 시간

    @classmethod
    def create(
        cls,
        performances_id: int,
        user_id: int,
        ticket_type: TicketType,
        quantity: int,
        unit_price: int,  # 티켓 1장 가격
        festival_name: str,  # 스냅샷
        venue: str,  # 스냅샷
        discount_amount: int = 0,
    ) -> "Reservation":
        now = datetime.now(UTC)
        created_at = now
        expires_at = now + timedelta(hours=DEPOSIT_EXPIRE_HOURS)
        total_price = unit_price * quantity
        final_price = total_price - discount_amount
        return cls(
            performances_id=performances_id,
            user_id=user_id,
            ticket_type=ticket_type,
            quantity=quantity,
            festival_name=festival_name,
            venue=venue,
            discount_amount=discount_amount,
            created_at=created_at,
            expires_at=expires_at,
            total_price=total_price,
            final_price=final_price,
        )
