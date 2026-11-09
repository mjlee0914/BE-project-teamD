from enum import StrEnum


class ReservationStatus(StrEnum):
    PENDING = "PENDING"  # 예매 대기
    CONFIRMED = "CONFIRMED"  # 예매 승인
    CANCELED = "CANCELED"  # 예매 취소
    EXPIRED = "EXPIRED"  # 예매 만료


class DiscountType(StrEnum):
    NONE = "NONE"
    DISABLED = "DISABLED"
    VETERAN = "VETERAN"
    SENIOR = "SENIOR"
    KANT = "KANT"
