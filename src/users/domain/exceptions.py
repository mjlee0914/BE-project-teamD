"""
상태 코드 기준

- 404 NotFound      : 찾는 회원이 없음
- 409 Conflict      : 현재 데이터 상태와 충돌 (이미 가입된 이메일, 이미 탈퇴한 회원)
- 422 Unprocessable : 입력이 회원 규칙을 위반 (형식 오류, 길이 위반)
- 403 Forbidden     : 누구인지는 아는데 권한이 없음 (남의 계정 탈퇴)
"""

from shared.core.exceptions import (
    ConflictException,
    ForbiddenException,
    NotFoundException,
    UnprocessableException,
)


# 존재하지 않는 회원 조회 시 (service에서 대응)
class UserNotFound(NotFoundException):
    def __init__(self, message: str = "회원을 찾을 수 없습니다."):
        # message는 상황에 따라 바꿀 수 있으므로 매개변수로 받음
        super().__init__(message=message, error_code="USER_NOT_FOUND")


# 이미 가입된 이메일 (규칙 3, service에서 대응)
class DuplicateEmail(ConflictException):
    def __init__(self, message: str = "이미 사용 중인 이메일입니다."):
        super().__init__(message=message, error_code="EMAIL_ALREADY_EXISTS")


# 이미 가입된 전화번호 (규칙 8, service에서 대응)
class DuplicatePhone(ConflictException):
    def __init__(self, message: str = "이미 사용 중인 전화번호입니다."):
        super().__init__(message=message, error_code="PHONE_ALREADY_EXISTS")


# 이메일 형식 위반 (규칙 1)
class InvalidEmail(UnprocessableException):
    def __init__(self, message: str = "올바른 이메일 형식이 아닙니다."):
        super().__init__(message=message, error_code="INVALID_EMAIL")


# 이름 길이 위반 : 1자, 21자 이상 (규칙 4)
class InvalidName(UnprocessableException):
    def __init__(self, message: str = "이름은 2자 이상 20자 이하여야 합니다."):
        super().__init__(message=message, error_code="INVALID_NAME")


# 비밀번호 규칙 위반, 기존 비밀번호 불일치, 같은 비밀번호로 변경 (규칙 5, 12, 13)
class InvalidPassword(UnprocessableException):
    def __init__(self, message: str = "비밀번호 규칙을 만족하지 않습니다."):
        super().__init__(message=message, error_code="INVALID_PASSWORD")


# 전화번호 형식 위반 (규칙 7)
class InvalidPhone(UnprocessableException):
    def __init__(self, message: str = "올바른 전화번호 형식이 아닙니다."):
        super().__init__(message=message, error_code="INVALID_PHONE")


# 현재 상태에서 처리 불가 : 탈퇴 회원 -> 탈퇴 회원의 비밀번호 변경 (규칙 11, 15)
class InvalidUserStatus(ConflictException):
    def __init__(self, message: str = "현재 회원 상태에서 처리할 수 없는 요청입니다."):
        super().__init__(message=message, error_code="INVALID_USER_STATUS")


# 본인 또는 관리자가 아닌 사용자의 탈퇴 요청 (규칙 14)
class WithdrawPermissionDenied(ForbiddenException):
    def __init__(self, message: str = "탈퇴는 본인 또는 관리자만 가능합니다."):
        super().__init__(message=message, error_code="WITHDRAW_PERMISSION_DENIED")
