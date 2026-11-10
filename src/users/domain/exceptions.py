"""
# exceptions.py
- 회원 도메인 예외
- 회원 규칙을 어겼을 때 raise 하는 예외 모음
- shared/core/exceptions.py의 공통 예외를 상속해서 HTTP 상태 코드를 정함

# 상태 코드 기준
- 404 NotFound      : 찾는 회원이 없음
- 409 Conflict      : 현재 데이터 상태와 충돌 (이미 가입된 이메일, 이미 탈퇴한 회원)
- 422 Unprocessable : 입력이 회원 규칙을 위반 (형식 오류, 길이 위반)
- 403 Forbidden     : 누구인지는 아는데 권한이 없음 (남의 계정 탈퇴, 탈퇴 회원의 이용 요청)
"""

# shared/core/exceptions.py
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


# 이미 가입된 전화번호 (규칙 9, service에서 대응)
class DuplicatePhone(ConflictException):
    def __init__(self, message: str = "이미 사용 중인 전화번호입니다."):
        super().__init__(message=message, error_code="PHONE_ALREADY_EXISTS")


# 이메일 형식 위반 (규칙 1)
class InvalidEmail(UnprocessableException):
    def __init__(self, message: str = "올바른 이메일 형식이 아닙니다."):
        super().__init__(message=message, error_code="INVALID_EMAIL")


# 이름 길이 위반 : 1자, 21자 이상, 공백 포함 (규칙 4, 5)
class InvalidName(UnprocessableException):
    def __init__(self, message: str = "이름은 2자 이상 20자 이하여야 합니다."):
        super().__init__(message=message, error_code="INVALID_NAME")


# 비밀번호 규칙 위반, 기존 비밀번호 불일치, 같은 비밀번호로 변경 (규칙 6, 13, 14)
class InvalidPassword(UnprocessableException):
    def __init__(self, message: str = "비밀번호 규칙을 만족하지 않습니다."):
        super().__init__(message=message, error_code="INVALID_PASSWORD")


# 전화번호 형식 위반 (규칙 8)
class InvalidPhone(UnprocessableException):
    def __init__(self, message: str = "올바른 전화번호 형식이 아닙니다."):
        super().__init__(message=message, error_code="INVALID_PHONE")


# 현재 상태와 충돌 : 이미 탈퇴한 회원의 중복 탈퇴 요청 (규칙 16)
class InvalidUserStatus(ConflictException):
    def __init__(self, message: str = "현재 회원 상태에서 처리할 수 없는 요청입니다."):
        super().__init__(message=message, error_code="INVALID_USER_STATUS")


# 본인 또는 관리자가 아닌 사용자의 탈퇴 요청 (규칙 15)
class WithdrawPermissionDenied(ForbiddenException):
    def __init__(self, message: str = "탈퇴는 본인 또는 관리자만 가능합니다."):
        super().__init__(message=message, error_code="WITHDRAW_PERMISSION_DENIED")


# ACTIVE가 아닌 회원의 로그인, 예매, 정보 수정, 비밀번호 변경, 관리자 기능 요청 (규칙 12, 21, 22, 23, 26)
class InactiveUser(ForbiddenException):
    def __init__(self, message: str = "이용할 수 없는 회원 상태입니다."):
        super().__init__(message=message, error_code="INACTIVE_USER")


# 관리자가 아닌 회원의 관리자 전용 기능 요청 (규칙 25)
class AdminPermissionDenied(ForbiddenException):
    def __init__(self, message: str = "관리자만 이용할 수 있습니다."):
        super().__init__(message=message, error_code="ADMIN_PERMISSION_DENIED")