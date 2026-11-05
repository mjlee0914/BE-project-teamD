"""
# exceptions.py
모든 도메인이 공통으로 상속해서 쓰는 예외 모음
여기 정의된 예외를 raise하면 exception_handlers.py가 잡아서 APIResponse.fail() 형식으로 응답함

# 상태 코드 기준
- 401 UnauthorizedException  : 누구인지 모름 (로그인 안 됨)
- 403 ForbiddenException     : 누구인지는 아는데 권한이 없음
- 404 NotFoundException      : 찾는 게 없음
- 409 ConflictException      : 이미 있거나, 현재 데이터 상태와 충돌
- 422 UnprocessableException : 비즈니스 규칙 위반 (SharedException 기본값도 422)
- 500                        : 처리되지 않은 예외 → exception_handlers.py가 자동 처리 (클래스 없음)

# 400을 쓰지 않는 이유
FastAPI는 JSON 문법 오류, 타입 오류, 필수값 누락 같은 요청 오류를 이미 422로 응답함
비즈니스 규칙 위반도 "형식은 맞지만 내용 때문에 처리할 수 없음"이라 422로 통일함
→ 클라이언트는 "422 = 내 요청 내용에 문제가 있다" 하나의 기준으로 처리하면 됨

# 409 vs 422 구분
"다른 시점에 보냈으면 성공했을까?"
- 그렇다 → 409 (예: 이미 취소된 예매 취소, 이미 가입된 이메일)
- 언제 보내도 실패 → 422 (예: 수량 3장, 음수 금액)

# 사용법
raise NotFoundException()                          # 기본 메시지로 응답
raise NotFoundException("3번 예매가 없습니다.")      # 메시지를 직접 지정
raise UnprocessableException(errors={"quantity": ["2장 이하로 선택해주세요."]})  # 상세 에러 포함

# 도메인 예외 만드는 법 (각 도메인의 domain/exceptions.py)
도메인마다 기본 예외 1개를 두고, 상황에 맞는 공통 예외를 상속해서 세부 예외를 만듦
    class ReservationNotFound(NotFoundException):
        def __init__(self, message: str = "예매를 찾을 수 없습니다."):
            super().__init__(message=message, error_code="RESERVATION_NOT_FOUND")
"""

# 파이썬 표준 라이브러리
from typing import Generic, TypeVar

# 외부 라이브러리
from fastapi import status

# 타입 변수: errors에 들어갈 타입을 "아직 정하지 않은 자리"로 비워둠
# 하위 예외나 사용하는 쪽에서 dict, list 등으로 정할 수 있음
# 예) SharedException[dict[str, list[str]]] → errors에 필드별 에러 목록이 들어감
# 실행에는 영향이 없고, 에디터 자동완성·타입 검사를 위한 힌트임
T = TypeVar("T")


# Generic[T]: 이 클래스가 타입 T를 매개변수처럼 받는다는 표시
# (함수가 값을 매개변수로 받듯이, 클래스가 타입을 매개변수로 받음)
class SharedException(Exception, Generic[T]):
    """모든 애플리케이션 예외의 공통 부모 클래스"""

    # 각 값이 응답의 어디로 가는지
    # - message     → 응답의 message: 사용자에게 보여줄 한 줄 설명
    # - status_code → HTTP 상태 코드 (기본 422)
    # - error_code  → 응답의 code: 대문자 스네이크 (예: RESERVATION_NOT_FOUND)
    # - errors      → 응답의 errors: 상세 에러 내용, 없으면 None (응답에서는 null)
    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_422_UNPROCESSABLE_CONTENT,
        error_code: str = "UNPROCESSABLE_CONTENT",
        errors: T | None = None,
    ):
        # 받은 값을 객체에 저장 → exception_handlers.py에서 exc.message처럼 꺼내서 응답을 만듦
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.errors: T | None = errors
        # 부모 Exception에도 메시지를 전달 → 로그나 print(e)에 메시지가 보임
        super().__init__(message)


# 아래 하위 예외들은 상태 코드만 고정하고 나머지(message, error_code, errors)는 그대로 부모에게 넘김
# message 기본값은 def __init__(...)에서 정하고, super().__init__(...)에서는 받은 값을 전달만 함


class UnauthorizedException(SharedException[T]):
    """
    401: 누구인지 모름 ( 로그인 안 된 상태 )
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
    403: 누구인지는 아는데 권한이 없음 ( 로그인해도 해결 안 됨 )
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
    404: 찾는 게 없음
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
    409: 이미 있거나, 현재 데이터 상태와 충돌
    다른 시점에 보냈으면 성공했을 요청 ( 422와 구분 )
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
    422: 비즈니스 규칙 위반 ( 형식은 맞지만 내용 때문에 처리 불가 )
    언제 보내도 실패하는 요청 ( 409와 구분 )
    ex ) 티켓 수량 3장 선택, 할인 금액이 총 금액 보다 큼
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