from shared.core.exceptions import (
    ConflictException,
    NotFoundException,
    UnprocessableException,
)


# 존재하지 않는 예매 조회 시 ( service에서 대응 )
class ReservationNotFound(NotFoundException):
    def __init__(self, message: str = "예매를 찾을 수 없습니다."):

        # message는 상황에 따라 바꿀 수 있으므로 매개변수로 받음
        super().__init__(message=message, error_code="RESERVATION_NOT_FOUND")


# 예매 수량이 범위를 벗어남 : 0장, 3장 이상 (규칙 5, 11)
class InvalidReservationQuantity(UnprocessableException):
    def __init__(self, message: str = "예매 수량이 올바르지 않습니다."):
        super().__init__(message=message, error_code="INVALID_RESERVATION_QUANTITY")


# 처리 할 수 없는 금액 : 총 결제 금액이 음수, 할인 금액이 음수 (규칙 6, 7, 8)
class InvalidReservationPrice(UnprocessableException):
    def __init__(self, message: str = "금액이 올바르지 않습니다."):
        super().__init__(message=message, error_code="INVALID_RESERVATION_PRICE")


# 현재 상태에서 처리 불가능한 요청 : 취소 상태 -> 취소 상태 (규칙 13~17)
class InvalidReservationStatus(ConflictException):
    def __init__(self, message: str = "현재 상태에서는 처리할 수 없는 요청입니다."):
        super().__init__(message=message, error_code="INVALID_RESERVATION_STATUS")


# 입금 기한 위반: 기한이 지나 승인 불가, 기한 전이라 만료 불가 (규칙 13, 14)
class DepositDeadlineViolation(ConflictException):
    def __init__(self, message: str = "입금 기한 조건을 만족하지 않습니다."):
        super().__init__(message=message, error_code="DEPOSIT_DEADLINE_VIOLATION")
