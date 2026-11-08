"""
요구 사항 정의

[생성]
1. 예매는 축제(festival_id), 사용자(user_id), 수량, 티켓 종류, 금액, 축제 이름·장소를 받아 생성한다.
2. 새 예매의 상태는 항상 PENDING(입금 대기)이다.
3. 결제는 토스 가상계좌(무통장입금) 기준이며, 입금 기한(expires_at)은 생성 시각 + 24시간이다.
4. 축제 이름·장소·금액은 예매 시점의 값을 그대로 저장한다(스냅샷). 이후 축제 정보가 바뀌어도 예매 내역은 바뀌지 않는다.

[금액]
5. 수량은 1장 이상이어야 한다.
6. 총 금액은 0원보다 커야 한다. (무료 공연 없음)
7. 할인 금액은 할인 타입에 의해 결정된다.
8. 할인 금액은 0원 이상이고 총 금액을 넘을 수 없다. 할인이 없으면 0원이다.
9. 최종 결제 금액은 총 금액 - 할인 금액이다.

[구매 수량 제한]
10. 사용자 1명은 날짜(회차)별로 최대 2장까지 예매할 수 있다.
11. 양일권(BOTH) 1장은 토요일 1장 + 일요일 1장으로 계산한다.
    - 양일권 2장을 예매하면 토요일 2장, 일요일 2장이 되어 두 날짜 모두 한도에 도달한다.
    - 티켓은 날짜별로 발급하므로 양일권 1장당 티켓 2장(토 1, 일 1)이 발급된다.
12. 한 번의 예매 수량도 위 한도를 넘을 수 없다. (토요일권·일요일권·양일권 각각 최대 2장)
13. 이미 예매한 수량과 합산한 한도 검사는 domain(service.py)에서 판단하고, 기존 예매 조회는 application(service)에서 한다.
    - CANCELED, EXPIRED 예매는 합산에서 제외한다.

[상태 변경]
14. 입금이 완료되면 PENDING → CONFIRMED로 바뀌고 confirmed_at을 기록한다. 입금 기한이 지났으면 승인할 수 없다.
15. 입금 기한이 지나도록 입금하지 않으면 PENDING → EXPIRED로 바뀐다. 입금 기한 전에는 만료할 수 없다.
16. 예매를 취소하면 CANCELED로 바뀌고 canceled_at을 기록한다.
    - PENDING 상태에서는 취소할 수 있다.
    - CONFIRMED 상태(입금 완료)도 취소할 수 있다. 부분 취소 없이 전체 취소만 가능하다.
17. CANCELED, EXPIRED는 끝난 상태이므로 다른 상태로 바꿀 수 없다.
18. 허용되지 않은 상태 변경을 시도하면 도메인 오류가 발생한다.
"""

# 표준 라이브러리
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

# 프로젝트 코드
from reservations.domain.enums import DiscountType, ReservationStatus, TicketType
from reservations.domain.exceptions import (
    DepositDeadlineViolation,
    InvalidReservationPrice,
    InvalidReservationQuantity,
    InvalidReservationStatus,
)

DEPOSIT_EXPIRE_HOURS = 24  # 예매 대기 시간
MAX_QUANTITY_PER_RESERVATION = 2  # 티켓 최대 수량
DISCOUNT_RATE = {
    DiscountType.NONE: 0,
    DiscountType.DISABLED: 60,
    DiscountType.VETERAN: 70,
    DiscountType.SENIOR: 80,
    DiscountType.KANT: 90,
}


@dataclass
class Reservation:
    festival_id: int  # 축제 ID
    user_id: int  # 사용자 아이디
    quantity: int  # 티켓 수량
    ticket_type: TicketType  # 티켓 타입
    total_price: int  # 총 금액
    final_price: int  # 최종 결제 금액
    festival_name: str  # 축제 이름
    venue: str  # 축제 장소

    # 기본값이 존재
    id: int | None = None  # 예매 아이디
    discount_type: DiscountType = DiscountType.NONE
    discount_amount: int = 0  # 할인 금액
    status: ReservationStatus = ReservationStatus.PENDING  # 예매 상태
    created_at: datetime | None = None  # 예매 생성 시간
    expires_at: datetime | None = None  # 예매 대기 만료 시간
    confirmed_at: datetime | None = None  # 예매 승인 시간
    canceled_at: datetime | None = None  # 예매 취소 시간
    updated_at: datetime | None = None  # 예매 수정 시간

    def __post_init__(self) -> None:  # 데이터 검증
        # 티켓 수량은 1장 이상이어야 한다.
        if not 1 <= self.quantity:
            raise InvalidReservationQuantity(
                f"티켓 수량은 1장 이상이어야 합니다. [입력 : {self.quantity}]"
            )
        # 티켓 수량은 MAX_QUANTITY_PER_RESERVATION 이하여야 한다.
        if not MAX_QUANTITY_PER_RESERVATION >= self.quantity:
            raise InvalidReservationQuantity(
                f"티켓 수량은 2장 이하여야 합니다. [입력 : {self.quantity}, 최대 수량 : {MAX_QUANTITY_PER_RESERVATION}]"
            )
        # 총 금액은 0원보다 커야 한다. (무료 공연 없음)
        if not 0 < self.total_price:
            raise InvalidReservationPrice(
                f"총 금액은 0원보다 커야 합니다. (총 금액 : {self.total_price})"
            )
        # 할인 금액은 음수 일 수 없다.
        if not 0 <= self.discount_amount:
            raise InvalidReservationPrice(
                f"할인 금액은 음수 일 수 없습니다. (할인 금액 : {self.discount_amount})"
            )
        # 할인 금액은 총 금액보다 클 수 없다.
        if not self.discount_amount <= self.total_price:
            raise InvalidReservationPrice(
                f"할인 금액은 총 금액보다 클 수 없습니다. (총 금액 : {self.total_price}, 할인 금액 : {self.discount_amount})"
            )
        # 최종 결제 금액은 총 금액 - 할인 금액 이어야 한다.
        if self.final_price != (self.total_price - self.discount_amount):
            raise InvalidReservationPrice(
                f"최종 결제 금액은 총 금액 - 할인 금액과 같아야 합니다. (최종 결제 금액 : {self.final_price}, 총 금액 - 할인 금액 : {self.total_price - self.discount_amount})"
            )

    @classmethod
    def create(
        cls,
        festival_id: int,
        user_id: int,
        ticket_type: TicketType,
        quantity: int,
        unit_price: int,  # 티켓 1장 가격
        festival_name: str,  # 스냅샷
        venue: str,  # 스냅샷
        discount_type: DiscountType = DiscountType.NONE,
    ) -> "Reservation":

        now = datetime.now(UTC)
        created_at = now
        expires_at = now + timedelta(hours=DEPOSIT_EXPIRE_HOURS)
        total_price = unit_price * quantity
        discount_amount = total_price * DISCOUNT_RATE[discount_type] // 100
        final_price = total_price - discount_amount

        return cls(
            festival_id=festival_id,
            user_id=user_id,
            ticket_type=ticket_type,
            quantity=quantity,
            festival_name=festival_name,
            venue=venue,
            discount_type=discount_type,
            discount_amount=discount_amount,
            created_at=created_at,
            expires_at=expires_at,
            total_price=total_price,
            final_price=final_price,
        )

    def confirm(self) -> None:  # 예매 승인 상태로 변경, 예매 승인 시간 추가
        if self.status != ReservationStatus.PENDING:
            raise InvalidReservationStatus(
                f"예매 승인 시 상태는 PENDING 상태여야 합니다. [현재 상태 : {self.status}]"
            )
        now = datetime.now(UTC)
        # 입금 기한이 지난 예매는 승인할 수 없다.
        if self.expires_at is not None and now > self.expires_at:
            raise DepositDeadlineViolation(
                f"입금 기한이 지나 예매를 승인할 수 없습니다. [입금 기한 : {self.expires_at}]"
            )

        self.status = ReservationStatus.CONFIRMED
        self.confirmed_at = now

    def expire(self) -> None:  # 예매 만료 상태로 변경
        if self.status != ReservationStatus.PENDING:
            raise InvalidReservationStatus(
                f"예매 만료 시 상태는 PENDING 상태여야 합니다. [현재 상태 : {self.status}]"
            )
        # 입금 기한이 지나지 않은 예매는 만료할 수 없다.
        if self.expires_at is not None and datetime.now(UTC) <= self.expires_at:
            raise DepositDeadlineViolation(
                f"입금 기한이 지나지 않아 예매를 만료할 수 없습니다. [입금 기한 : {self.expires_at}]"
            )

        self.status = ReservationStatus.EXPIRED

    def cancel(self) -> None:  # 예매 취소 상태로 변경, 예매 취소 시간 추가
        if self.status not in (ReservationStatus.PENDING, ReservationStatus.CONFIRMED):
            raise InvalidReservationStatus(
                f"예매 취소 시 상태는 PENDING or CONFIRMED 상태여야 합니다. [현재 상태 : {self.status}]"
            )

        self.status = ReservationStatus.CANCELED
        self.canceled_at = datetime.now(UTC)
