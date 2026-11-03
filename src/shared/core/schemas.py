# 표준 라이브러리 ( Python 내장 )
from datetime import UTC, datetime
from typing import Any, Generic, Self, TypeVar

# 외부 패키지 ( uv add )
from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ORMSchema(BaseModel):
    """SQLAlchemy 모델 객체를 바로 응답 스키마로 변환할 때 상속하는 베이스"""

    model_config = ConfigDict(from_attributes=True)


class PageResponse(BaseModel, Generic[T]):
    """목록 조회 응답 (축제/공연 리스트 등)"""

    items: list[T] = Field(description="현재 페이지의 항목 목록")
    total: int = Field(description="전체 항목 수")
    page: int = Field(description="현재 페이지 번호 (1부터 시작)")
    size: int = Field(description="페이지당 항목 수")

    @classmethod
    def create(cls, items: list[T], total: int, page: int, size: int) -> Self:
        return cls(items=items, total=total, page=page, size=size)


class APIResponse(BaseModel, Generic[T]):
    """모든 API 응답을 감싸는 공통 응답 형식"""

    success: bool = Field(description="처리 성공/실패 여부")
    code: str | None = Field(
        None, description="비즈니스 식별 코드 (성공 시 OK, 실패 시 에러 코드)"
    )
    message: str | None = Field(None, description="성공 또는 실패시 설명")
    errors: Any | None = Field(None, description="실패 시 세부 오류 내용")
    data: T | None = Field(None, description="성공시 응답 데이터")
    responded_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="응답 날짜시간(UTC)",
    )

    @classmethod
    def ok(
        cls,
        data: T | None = None,
        message: str = "요청이 성공적으로 처리되었습니다.",
        code: str = "OK",
    ) -> Self:
        return cls(
            success=True,
            code=code,
            message=message,
            errors=None,
            data=data,
        )

    @classmethod
    def fail(
        cls,
        message: str,
        code: str = "UNPROCESSABLE_ENTITY",
        errors: Any | None = None,
    ) -> Self:
        return cls(
            success=False,
            code=code,
            message=message,
            errors=errors,
            data=None,
        )
