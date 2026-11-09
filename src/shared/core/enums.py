from enum import StrEnum


class TicketType(StrEnum):
    SAT = "SAT"  # 토요일권
    SUN = "SUN"  # 일요일권
    BOTH = "BOTH"  # 양일권

    @property
    def weekdays(self) -> list[int]:
        """필요한 회차의 요일 (datetime.weekday() 기준: 월=0 … 토=5, 일=6)
        양일권(BOTH)은 토·일 두 회차를 포함한다"""
        return _WEEKDAYS[self]


_WEEKDAYS = {
    TicketType.SAT: [5],
    TicketType.SUN: [6],
    TicketType.BOTH: [5, 6],
}
