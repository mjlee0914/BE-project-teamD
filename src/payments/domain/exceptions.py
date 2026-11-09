# 파일 역할: 금액·상태·접근·저장 충돌·결제사 오류를 구분한다. 공통 예외는 전역 핸들러가, 연동 오류는 라우터가 응답으로 바꾼다.

from shared.core.exceptions import (
    ConflictException,
    ForbiddenException,
    NotFoundException,
    SharedException,
)


# 현재 상태에서 불가능한 작업을 422와 도메인 오류 코드로 알린다.
class PaymentStatusException(SharedException):
    # 예외 메시지와 오류 코드를 공통 예외에 전달한다. HTTP 응답은 전역 핸들러가 생성한다.
    def __init__(self, message: str = "결제 상태를 변경할 수 없습니다."):
        super().__init__(message=message, error_code="PAYMENT_STATUS_NOT_CHANGEABLE")


# 금액이 양의 정수가 아니거나 저장값과 다르면 422로 거절한다.
class InvalidAmountException(SharedException):
    # 예외 메시지와 오류 코드를 공통 예외에 전달한다. HTTP 응답은 전역 핸들러가 생성한다.
    def __init__(self, message: str = "유효한 금액이 아닙니다."):
        super().__init__(message=message, error_code="INVALID_PAYMENT_AMOUNT")


# 요청 처리에 필요한 결제 키가 없을 때 404 형식으로 알린다.
class PaymentKeyNotFoundException(NotFoundException):
    # 예외 메시지와 오류 코드를 공통 예외에 전달한다. HTTP 응답은 전역 핸들러가 생성한다.
    def __init__(self, message: str = "Payment Key가 누락되었습니다."):
        super().__init__(message=message, error_code="PAYMENT_KEY_NOT_FOUND")


# 내부 결제 ID에 해당하는 데이터가 없을 때 404로 알린다.
class PaymentNotFoundException(NotFoundException):
    # 예외 메시지와 오류 코드를 공통 예외에 전달한다. HTTP 응답은 전역 핸들러가 생성한다.
    def __init__(self, message: str = "결제정보를 찾을 수 없습니다."):
        super().__init__(message=message, error_code="PAYMENT_NOT_FOUND")


# 결제의 참조 대상 예매가 없어서 저장·잠금을 할 수 없을 때 404로 알린다.
class PaymentReservationNotFound(NotFoundException):
    # 예외 메시지와 오류 코드를 공통 예외에 전달한다. HTTP 응답은 전역 핸들러가 생성한다.
    def __init__(self):
        super().__init__(
            message="결제에 연결할 예매가 없습니다.",
            error_code="PAYMENT_RESERVATION_NOT_FOUND",
        )


# 이미 저장된 결제의 예매·주문번호·금액 변경을 409로 거절한다.
class PaymentIdentityConflict(ConflictException):
    # 예외 메시지와 오류 코드를 공통 예외에 전달한다. HTTP 응답은 전역 핸들러가 생성한다.
    def __init__(self):
        super().__init__(
            message="저장된 결제의 예매·주문번호·금액은 변경할 수 없습니다.",
            error_code="PAYMENT_IDENTITY_CONFLICT",
        )


# 결제사 통신·응답 오류를 보관한다. 결과 불명 여부를 함께 전달해 실패 확정과 구분한다.
class PaymentProcessingError(Exception):
    """결제 연동 실패. 통신 오류는 실제 처리 결과가 불명확하므로 재조회가 필요하다."""

    # 외부 오류 코드·HTTP 상태·결과 불명 여부를 보관한다. HTTP 응답 생성은 라우터에 맡긴다.
    def __init__(
        self,
        message: str,
        *,
        code: str = "PAYMENT_PROCESSING_ERROR",
        http_status: int | None = None,
        outcome_unknown: bool = False,
    ):
        super().__init__(message)
        self.code = code
        self.http_status = http_status
        self.outcome_unknown = outcome_unknown


# 웹훅의 비밀값 등을 검증하지 못한 요청을 403으로 거절한다.
class InvalidPaymentWebhook(ForbiddenException):
    # 예외 메시지와 오류 코드를 공통 예외에 전달한다. HTTP 응답은 전역 핸들러가 생성한다.
    def __init__(self):
        super().__init__(
            message="결제 웹훅을 검증할 수 없습니다.",
            error_code="INVALID_PAYMENT_WEBHOOK",
        )


# 조회 뒤 다른 요청이 먼저 상태를 바꾼 경우 409로 재조회를 요구한다.
class PaymentConcurrentUpdate(ConflictException):
    # 예외 메시지와 오류 코드를 공통 예외에 전달한다. HTTP 응답은 전역 핸들러가 생성한다.
    def __init__(self):
        super().__init__(
            message="결제 상태가 변경됐습니다. 다시 조회해주세요.",
            error_code="PAYMENT_CONCURRENT_UPDATE",
        )


# 같은 예매에 다른 진행 중·입금 대기·완료 결제가 있으면 409로 새 승인을 막는다.
class PaymentAttemptConflict(ConflictException):
    # 예외 메시지와 오류 코드를 공통 예외에 전달한다. HTTP 응답은 전역 핸들러가 생성한다.
    def __init__(self):
        super().__init__(
            message="같은 예매에 진행 중이거나 완료된 다른 결제가 있습니다.",
            error_code="PAYMENT_ATTEMPT_CONFLICT",
        )


# 입금된 가상계좌 취소에 환불 계좌가 없으면 422로 알린다.
class InvalidRefundAccount(SharedException):
    # 예외 메시지와 오류 코드를 공통 예외에 전달한다. HTTP 응답은 전역 핸들러가 생성한다.
    def __init__(self):
        super().__init__(
            message="입금된 가상계좌를 취소하려면 환불 계좌가 필요합니다.",
            error_code="INVALID_REFUND_ACCOUNT",
        )


# 주문번호 또는 결제 키의 DB 중복 제약 위반을 409로 바꿔 전달한다.
class PaymentDuplicateIdentifier(ConflictException):
    # 예외 메시지와 오류 코드를 공통 예외에 전달한다. HTTP 응답은 전역 핸들러가 생성한다.
    def __init__(self):
        super().__init__(
            message="이미 저장된 주문번호 또는 결제 키입니다.",
            error_code="PAYMENT_DUPLICATE_IDENTIFIER",
        )
