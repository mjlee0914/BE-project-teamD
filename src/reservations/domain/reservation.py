# 표준 라이브러리
from dataclasses import dataclass
from datetime import datetime

# 프로젝트 코드
from reservations.domain.enums import ReservationStatus, TicketType


@dataclass
class Reservation:
    
    performances_id: int # 회차 아이디
    user_id: int # 사용자 아이디
    quantity: int # 티켓 수량
    ticket_type: TicketType # 티켓 타입
    total_price: int  # 총 금액
    final_price: int  # 최종 결제 금액
    festival_name: str # 축제 이름
    venue: str         # 축제 장소

    # 기본값이 존재
    id: int | None = None                 # 예매 아이디
    discount_amount: int = 0    # 할인 금액
    status: ReservationStatus = ReservationStatus.PENDING # 예매 상태
    created_at: datetime | None = None    # 예매 생성 시간
    expires_at: datetime | None = None    # 예매 대기 만료 시간
    confirmed_at: datetime | None = None  # 예매 승인 시간
    canceled_at: datetime | None = None   # 예매 취소 시간
    updated_at: datetime | None = None    # 예매 수정 시간
