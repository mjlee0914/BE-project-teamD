from enum import StrEnum


class TicketType(StrEnum):
    SAT = "SAT"  # 토요일권
    SUN = "SUN"  # 일요일권
    BOTH = "BOTH"  # 양일권