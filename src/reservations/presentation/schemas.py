"""
# presentation/schemas.py
API 요청·응답의 모양을 정하는 Pydantic 스키마 파일

# 엔티티(domain/reservation.py)와 따로 두는 이유
- 엔티티는 비즈니스 규칙을 담고, 스키마는 "밖으로 주고받는 데이터 모양"만 담는다
- 엔티티를 그대로 내보내면 user_id, updated_at처럼 응답에 필요 없는 값까지 노출됨
- 요청 스키마는 형식 검증(타입, 수량 범위)을 FastAPI가 서비스 호출 전에 대신 해 준다 → 실패 시 422

# 요청 스키마에 넣지 않는 값
- 가격, 할인 금액, 축제 이름·장소 : 서버가 직접 조회·계산 (클라이언트 값을 믿으면 가격 조작 가능)
- user_id : 로그인 정보에서 꺼냄 (dependencies.py 참고)
"""

# 표준 라이브러리
from datetime import datetime

# 외부 라이브러리
from pydantic import BaseModel, ConfigDict, Field

# 프로젝트 코드
from reservations.domain.enums import DiscountType
from shared.core.enums import TicketType


# 예매 생성 요청 body (POST /v1/reservations)
class ReservationCreate(BaseModel):
    festival_id: int  # 예매할 축제 ID
    quantity: int = Field(ge=1, le=2)  # 수량 : 1~2장 (범위를 벗어나면 422)
    ticket_type: TicketType  # 티켓 종류 : SAT / SUN / BOTH
    discount_type: DiscountType = DiscountType.NONE  # 할인 종류 : 안 보내면 할인 없음


# 예매 응답 (생성·목록·단건·취소 공통)
class ReservationResponse(BaseModel):
    # 엔티티의 id를 읽어서 응답에는 reservation_id라는 이름으로 내보냄
    # - validation_alias : 값을 "읽을 때" 쓰는 이름 → 엔티티의 id 속성을 찾아 옴
    reservation_id: int = Field(validation_alias="id")
    festival_id: int  # 축제 ID
    festival_name: str  # 축제 이름 (예매 시점 스냅샷)
    venue: str  # 축제 장소 (예매 시점 스냅샷)
    ticket_type: str  # 티켓 종류 (StrEnum이라 str 필드에 그대로 들어감)
    quantity: int  # 수량
    total_price: int  # 총 금액 (1장 가격 × 수량)
    discount_type: str  # 할인 종류
    discount_amount: int  # 할인 금액
    final_price: int  # 최종 결제 금액 (총 금액 - 할인 금액)
    status: str  # 예매 상태 : PENDING / CONFIRMED / EXPIRED / CANCELED
    expires_at: datetime  # 입금 기한
    created_at: datetime  # 예매 생성 시각
    confirmed_at: datetime | None = None  # 입금 확인 시각 (확인 전이면 None)
    canceled_at: datetime | None = None  # 취소 시각 (취소 전이면 None)

    # from_attributes=True : dict가 아닌 객체의 "속성"에서 값을 읽을 수 있게 함
    # → ReservationResponse.model_validate(엔티티) 한 줄로 변환 가능
    model_config = ConfigDict(from_attributes=True)
