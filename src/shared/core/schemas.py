# 표준 라이브러리 ( Python 내장 )
from datetime import UTC, datetime
from typing import Any, Generic, Self, TypeVar

# 외부 패키지 ( uv add )
from pydantic import BaseModel, ConfigDict, Field

# 타입 변수: "아직 정해지지 않은 어떤 타입"을 뜻하는 자리표시자
# APIResponse[FestivalResponse]처럼 쓰면 T 자리에 FestivalResponse가 들어감
T = TypeVar("T")


# ORM 객체 → 응답 스키마 변환용 베이스
# 응답 스키마가 이 클래스를 상속하면 SQLAlchemy 모델 객체를 바로 넘겨서 만들 수 있음
# 사용법: class FestivalResponse(ORMSchema): ...
#         FestivalResponse.model_validate(festival)  # festival은 DB에서 조회한 모델 객체
class ORMSchema(BaseModel):
    """SQLAlchemy 모델 객체를 바로 응답 스키마로 변환할 때 상속하는 베이스"""

    # from_attributes=True: dict가 아닌 객체에서도 festival.name처럼 속성으로 값을 읽어옴
    # 이 설정이 없으면 모델 객체를 넘겼을 때 검증 에러가 남
    model_config = ConfigDict(from_attributes=True)


# 목록 조회 응답 (페이지네이션)
# 페이지네이션: 데이터를 한 번에 다 주지 않고 10개, 20개씩 나눠서 주는 방식
# Generic[T]: items 안에 들어갈 항목 타입을 쓸 때 정함 → PageResponse[FestivalResponse]
class PageResponse(BaseModel, Generic[T]):
    """목록 조회 응답 (축제/공연 리스트 등)"""

    items: list[T] = Field(description="현재 페이지의 항목 목록")
    total: int = Field(description="전체 항목 수")
    page: int = Field(description="현재 페이지 번호 (1부터 시작)")
    size: int = Field(description="페이지당 항목 수")

    # 객체를 만드는 단축 함수
    # @classmethod: 객체 없이 클래스 이름으로 바로 부르는 함수 (cls = 클래스 자신)
    # -> Self: 이 함수를 부른 클래스 자신의 타입을 돌려준다는 뜻
    # 사용법: PageResponse.create(items=festivals, total=35, page=1, size=10)
    @classmethod
    def create(cls, items: list[T], total: int, page: int, size: int) -> Self:
        return cls(items=items, total=total, page=page, size=size)


# 모든 API 응답의 공통 형식
# 성공이든 실패든 항상 같은 모양으로 응답해서, 프론트엔드가 한 가지 방식으로 처리할 수 있게 함
# 응답 예) {"success": true, "code": "OK", "message": "...", "errors": null, "data": {...}, "responded_at": "..."}
# Generic[T]: data에 들어갈 타입을 쓸 때 정함 → APIResponse[FestivalResponse]
class APIResponse(BaseModel, Generic[T]):
    """모든 API 응답을 감싸는 공통 응답 형식"""

    # Field(기본값, description=...): description은 Swagger(/docs) 문서에 설명으로 표시됨
    success: bool = Field(description="처리 성공/실패 여부")
    code: str | None = Field(
        None, description="비즈니스 식별 코드 (성공 시 OK, 실패 시 에러 코드)"
    )
    message: str | None = Field(None, description="성공 또는 실패시 설명")
    # Any: 어떤 타입이든 허용 (dict, list, 문자열 등 에러 내용 형태가 다양해서)
    errors: Any | None = Field(None, description="실패 시 세부 오류 내용")
    data: T | None = Field(None, description="성공시 응답 데이터")
    # default_factory: 응답 객체를 만들 때마다 함수를 실행해서 기본값을 새로 만듦
    # default=datetime.now(UTC)로 쓰면 서버 시작 시 한 번만 계산돼서 모든 응답 시각이 같아짐
    # UTC: 시간대 정보가 붙은 시각 (DB의 DateTime(timezone=True) 값과 비교할 때 에러 방지)
    responded_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="응답 날짜시간(UTC)",
    )

    # 성공 응답 만들기
    # 사용법: return APIResponse.ok(data=festival_response)
    #         return APIResponse.ok(data=page, message="축제 목록 조회 성공")
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

    # 실패 응답 만들기
    # code 기본값이 UNPROCESSABLE_ENTITY인 이유: 팀 규칙상 검증 실패·비즈니스 규칙 위반은 422로 응답함
    # 사용법: return APIResponse.fail(message="잔여 수량이 부족합니다.", code="SOLD_OUT")
    # ⚠️ 이 함수는 응답 내용만 만듦. HTTP 상태 코드(422 등)는 따로 지정해야 함
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
