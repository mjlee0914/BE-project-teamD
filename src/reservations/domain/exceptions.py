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


# 기존 예매와 신규 예매를 합산 시 인당 최대 구매 가능 수량의 범위를 벗어남 (규칙 9)
class OverReservationQuantity(UnprocessableException):
    def __init__(
        self, message: str = "신규 예매로 인해 총 예매 가능 수량을 벗어납니다"
    ):
        super().__init__(message=message, error_code="OVER_RESERVATION_QUANTITY")


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


# 지금은 예매할 수 없는 상태 : 축제가 취소·종료됨, 회차가 오픈 전·매진·예매 기간 밖 (409)
class ReservationNotAvailable(ConflictException):
    def __init__(self, message: str = "현재 예매할 수 없습니다."):
        super().__init__(message=message, error_code="RESERVATION_NOT_AVAILABLE")


# 취소 마감 위반 : 입금 완료(CONFIRMED) 예매를 회차의 취소 마감(cancel_deadline_at) 이후에 취소하려 함 (409)
# - 입금 전(PENDING) 예매는 마감과 상관없이 취소 가능하므로 이 예외가 나지 않음
# - ConflictException(409)을 상속 : 요청 형식은 맞지만 "지금 상태"와 충돌하기 때문
class CancelDeadlineViolation(ConflictException):
    def __init__(self, message: str = "예매 취소 기간을 벗어났습니다."):
        super().__init__(message=message, error_code="CANCEL_DEADLINE_VIOLATION")


