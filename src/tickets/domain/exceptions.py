# global exception import

from shared.core.exceptions import (
    ConflictException,
    NotFoundException,
    UnprocessableException,
)

# 조회되지 않는 티켓


class TicketNotFound(NotFoundException):
    def __init__(
        self, message="조회되지 않는 티켓입니다"
    ):  # ticketntfound의 매개변수 두개 채움
        super().__init__(
            message=message, error_code="TICKET_NOT_FOUND"
        )  # super()로 error_code상속받아 채움


# 처리할 수 없는 가격
class InvalidTicketPrice(UnprocessableException):
    def __init__(self, message="티켓 가격이 올바르지 않습니다"):
        super().__init__(message=message, error_code="INVALID_TICKET_PRICE")


# 공연 시간이 올바르지 않음
class InvalidTicketPerformanceTime(UnprocessableException):
    def __init__(self, message: str = "공연 시간이 올바르지 않습니다."):
        super().__init__(message=message, error_code="INVALID_TICKET_PERFORMANCE_TIME")


# 현재 상태에서 허용되지 않은 상태변경
class InvalidTicketStatus(ConflictException):
    def __init__(self, message: str = "현재 상태에서는 처리할 수 없는 요청입니다."):
        super().__init__(message=message, error_code="INVALID_TICKET_STATUS")


# 취소할 수 없는 티켓
class TicketNotCancelable(ConflictException):
    def __init__(self, message: str = "취소할 수 없는 티켓입니다."):
        super().__init__(message=message, error_code="TICKET_NOT_CANCELABLE")


# 입장할 수 없는 티켓
class TicketNotEnterable(ConflictException):
    def __init__(self, message: str = "입장할 수 없는 티켓입니다."):
        super().__init__(message=message, error_code="TICKET_NOT_ENTERABLE")


# 승인되지 않은 예매로 티켓 발급을 시도함
class TicketNotIssuable(ConflictException):
    def __init__(self, message: str = "승인된 예매만 티켓을 발급할 수 있습니다."):
        super().__init__(message=message, error_code="TICKET_NOT_ISSUABLE")


# 이미 티켓이 발급된 예매
class TicketAlreadyIssued(ConflictException):
    def __init__(self, message: str = "이미 티켓이 발급된 예매입니다."):
        super().__init__(message=message, error_code="TICKET_ALREADY_ISSUED")


# 낙관적 락: 조회한 뒤 저장하기 전에 다른 요청이 먼저 티켓을 변경함 (version 불일치)
class TicketVersionConflict(ConflictException):
    def __init__(
        self, message: str = "다른 요청이 먼저 티켓을 변경했습니다. 다시 시도해 주세요."
    ):
        super().__init__(message=message, error_code="TICKET_VERSION_CONFLICT")
