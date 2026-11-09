# 파일 역할: 인증 도메인의 충돌 상황을 공통 예외 형식으로 표현한다.

from shared.core.exceptions import ConflictException


# 같은 토큰 식별자가 다른 회원의 것으로 저장된 충돌을 409로 표현한다.
class TokenBlacklistConflict(ConflictException):
    # 예외 메시지와 오류 코드를 공통 예외에 전달한다. HTTP 응답은 전역 핸들러가 생성한다.
    def __init__(self):
        super().__init__(
            message="이미 다른 회원의 토큰으로 등록된 식별자입니다.",
            error_code="TOKEN_BLACKLIST_CONFLICT",
        )
