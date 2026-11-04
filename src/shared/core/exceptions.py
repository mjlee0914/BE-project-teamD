# 파이썬 표준 라이브러리
from typing import Generic, TypeVar

# 외부 라이브러리
from fastapi import status

T = TypeVar("T")


class SharedException(Exception, Generic[T]):
    """모든 애플리케이션 예외의 공통 부모 클래스"""

    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_422_UNPROCESSABLE_CONTENT,
        error_code: str = "UNPROCESSABLE_CONTENT",
        errors: T | None = None,
    ):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.errors: T | None = errors
        super().__init__(message)


class UnauthorizedException(SharedException[T]):
    """
    누구인지 모름 ( 로그인 안 된 상태 )
    ex ) 토큰 없음, 만료된 토큰, 로그아웃된 토큰 ...
    """

    def __init__(
        self,
        message: str = "로그인 상태가 아닙니다.",
        error_code: str = "UNAUTHORIZED",
        errors: T | None = None,
    ):
        super().__init__(
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code=error_code,
            errors=errors,
        )


class ForbiddenException(SharedException[T]):
    """
    누구인지는 아는데 권한이 없음
    ex ) 남의 예매를 취소하려 함, 일반 회원이 축제 등록 시도 ...
    """

    def __init__(
        self,
        message: str = "권한이 존재하지 않습니다.",
        error_code: str = "FORBIDDEN",
        errors: T | None = None,
    ):
        super().__init__(
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
            error_code=error_code,
            errors=errors,
        )


class NotFoundException(SharedException[T]):
    """
    찾는 게 없음
    ex ) 없는 예매 번호, 없는 축제, 없는 공연 회차
    """

    def __init__(
        self,
        message: str = "찾는 리소스가 존재하지 않습니다.",
        error_code: str = "NOT_FOUND",
        errors: T | None = None,
    ):
        super().__init__(
            message=message,
            status_code=status.HTTP_404_NOT_FOUND,
            error_code=error_code,
            errors=errors,
        )


class ConflictException(SharedException[T]):
    """
    이미 있거나, 현재 상태와 충돌
    ex ) 이메일 중복 가입, 이미 취소된 예매를 취소 ...
    """

    def __init__(
        self,
        message: str = "이미 존재하는 데이터거나, 현재 상태와 데이터가 충돌합니다",
        error_code: str = "CONFLICT",
        errors: T | None = None,
    ):
        super().__init__(
            message=message,
            status_code=status.HTTP_409_CONFLICT,
            error_code=error_code,
            errors=errors,
        )


class UnprocessableException(SharedException[T]):
    """
    규칙 위반 ( 내용 때문에 처리 불가 )
    ex ) 티켓 수량 3장 선택, 할인 금액이 총 금액 보다 큼,
    """

    def __init__(
        self,
        message: str = "비즈니스 규칙을 위반합니다.",
        error_code: str = "UNPROCESSABLE_CONTENT",
        errors: T | None = None,
    ):
        super().__init__(
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            error_code=error_code,
            errors=errors,
        )
