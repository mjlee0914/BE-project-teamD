"""
# schemas.py
- 회원 API의 요청 바디, 응답 모양을 정하는 파일 (Pydantic)
- 요청 JSON -> 파이썬 객체로 바꾸면서 타입, 길이 같은 "모양"만 검사

# 역할 분담
- 스키마: JSON 모양, 최소 길이 -> 위반 시 FastAPI가 자동으로 422
- 도메인(User): 이메일 형식, 이름 2~20자, 비밀번호 규칙 같은 회원 규칙 -> 422
- 서비스(UserService): 이메일, 전화번호 중복처럼 DB가 필요한 검사 -> 409

# 보안
- 요청 스키마에 role/status가 없음 -> 클라이언트가 ADMIN을 보내도 무시됨
- 응답 스키마에 password_hash가 없음 -> 해시가 밖으로 나가지 않음
"""

from datetime import datetime

from pydantic import BaseModel, Field

# shared/core/schemas.py
from shared.core.schemas import ORMSchema

# users/domain/user.py
from users.domain.user import UserRole, UserStatus


# [회원가입 요청] POST /v1/users
# 형식 검증(이메일, 비밀번호 규칙 등)은 domain(User)이 하므로 여기서는 최소 길이만 확인
class UserCreate(BaseModel):
    # DB 컬럼 길이(255)를 넘는 값은 미리 차단, 형식 검사는 도메인에서 (규칙 1)
    email: str = Field(max_length=255)
    # 빈 문자열만 막음, 실제 2~20자 검사는 도메인에서 (규칙 2)
    name: str = Field(min_length=1, max_length=50)
    # 평문으로 받음 -> service에서 검증, 해시 후 버림, 평문은 저장하지 않음
    password: str = Field(min_length=1)
    # 선택 입력, 보내지 않으면 None
    phone: str | None = None  # 선택 입력


# [회원 정보 수정 요청] PATCH /v1/users/me
# 이름과 전화번호를 함께 받아야 수정 가능 (규칙 19)
# email, role 필드가 없음 -> 수정 API로 바꿀 수 없음
class UserUpdate(BaseModel):
    name: str
    phone: str


# [비밀번호 변경 요청] PATCH /v1/users/me/password
class PasswordChange(BaseModel):
    # 본인 확인용: 저장된 해시와 비교 (규칙 12)
    old_password: str
    # 새 비밀번호: 재사용, 형식 검사 후 해시 (규칙 13, 14)
    new_password: str


# [회원 응답] 모든 회원 API 응답의 data 부분
# ORMSchema(from_attributes=True) 상속 -> User 엔티티를 model_validate(user)로 바로 변환
# password_hash, updated_at, deleted_at -> 응답에 절대 포함 안함 (보안 + 불필요)
class UserResponse(ORMSchema):
    id: int  # 저장된 회원만 응답 -> None 불가
    email: str
    name: str
    phone: str | None  # 선택 입력이라 null 가능
    role: UserRole  # JSON에서는 "USER" / "ADMIN" 문자열
    status: UserStatus  # JSON에서는 "ACTIVE" / "WITHDRAWN" 등
    created_at: datetime  # ISO 8601 문자열로 응답
