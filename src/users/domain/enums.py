from enum import StrEnum  # StrEnum : 출력 시 값 그대로 나와서 안전


# 회원 권한
class UserRole(StrEnum):
    USER = "USER"  # 일반 회원
    ADMIN = "ADMIN"  # 관리자


# 회원 상태 (탈퇴 여부는 WITHDRAWN으로 판단)
class UserStatus(StrEnum):
    ACTIVE = "ACTIVE"  # 정상
    SUSPENDED = "SUSPENDED"  # 정지
    WITHDRAWN = "WITHDRAWN"  # 탈퇴
