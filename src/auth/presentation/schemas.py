# 파일 역할: 로그인 요청과 토큰 응답의 형식이다. Pydantic 검증을 통과한 입력만 서비스에 전달한다.

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from users.domain.user import EMAIL_REGEX, normalize_email


# 예상하지 않은 필드를 거절하고 이메일 형식·비밀번호의 최소 입력 여부를 검증한다.
class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=255)
    # 비밀번호에는 strip/소문자 변환을 적용하지 않는다.
    password: SecretStr = Field(min_length=1)

    # users와 같은 정규화 함수를 사용해 이메일의 공백·대소문자 처리 규칙을 맞춘다.
    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = normalize_email(value)
        if EMAIL_REGEX.fullmatch(normalized) is None:
            raise ValueError("올바른 이메일 형식이 아닙니다.")
        return normalized


# 클라이언트가 인증 헤더를 만들 수 있도록 토큰·bearer 방식·유효 기간(초)만 응답한다.
class TokenResponse(BaseModel):
    # repr=False는 객체 출력에서만 감춘다. 로그인 JSON 응답에는 토큰을 전달한다.
    access_token: str = Field(min_length=1, repr=False)
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(gt=0)
