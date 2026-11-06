from shared.core.exceptions import SharedException, NotFoundException

class PaymentStatusException(SharedException):
    def __init__(self, message: str = "결제 상태를 변경할 수 없습니다."):
        super().__init__(message=message, error_code="PAYMENT_STATUS_NOT_CHANGEABLE")


class InvalidAmountException(SharedException):
    def __init__(self, message: str = "유효한 금액이 아닙니다."):
        super().__init__(message=message, error_code="INVALID_PAYMENT_AMOUNT")

class PaymentKeyNotFoundException(NotFoundException):
    def __init__(self, message: str =  "Payment Key가 누락되었습니다."):
            super().__init__(message=message, error_code="PAYMENT_KEY_NOT_FOUND")

class PaymentNotFoundException(NotFoundException):
    def __init__(self, message: str =  "결제정보를 찾을 수 없습니다."):
        super().__init__(message=message, error_code="PAYMENT_NOT_FOUND")