from enum import StrEnum


class ReservationStatus(StrEnum):
    PENDING = "PENDING"     # 예매 대기
    CONFIRMED = "CONFIRMED" # 예매 승인
    CANCELED = "CANCELED"   # 예매 취소
    EXPIRED = "EXPIRED"     # 예매 만료

class TicketType(StrEnum):
    SAT = "SAT"   # 토요일권
    SUN = "SUN"   # 일요일권
    BOTH = "BOTH" # 양일권
