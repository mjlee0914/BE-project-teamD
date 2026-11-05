"""
# exception_handlers.py
API 처리 중 발생한 예외를 잡아서 공통 응답 형식(APIResponse.fail)으로 바꿔 응답하는 전역 예외 핸들러 모음
main.py에서 register_exception_handlers(app)를 한 번 호출하면 모든 API에 적용됨

# 처리 흐름
router/service/domain에서 raise NotFoundException("3번 예매가 없습니다.")
→ FastAPI가 예외 종류에 맞는 핸들러를 찾아 실행
→ 핸들러가 로그를 남기고 APIResponse.fail(...) 형식의 JSON으로 응답

# 핸들러 4종
1. SharedException (+ 하위 예외)  → 예외에 지정된 상태 코드 (401, 403, 404, 409, 422)
2. RequestValidationError        → 422 (Pydantic 스키마 검증 실패, FastAPI가 자동으로 발생시킴)
3. HTTPException (Starlette)    → 404, 405, 401 등 (없는 URL, 허용 안 된 메서드, 토큰 누락)
4. Exception (그 외 모든 예외)     → 500 (예상하지 못한 서버 오류)

# 응답 예시
{"success": false, "code": "NOT_FOUND", "message": "3번 예매가 없습니다.", "errors": null, "data": null, "responded_at": "..."}
"""

# 외부 라이브러리
from fastapi import FastAPI, Request, status
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

# 프로젝트 코드
from shared.core.exceptions import SharedException
from shared.core.logger import get_logger
from shared.core.schemas import APIResponse

logger = get_logger(__name__)


# app에 예외 핸들러 3개를 등록하는 함수 (main.py에서 호출)
# @app.exception_handler(예외 클래스): 해당 예외(와 그 하위 예외)가 발생하면 아래 함수를 실행하도록 등록
def register_exception_handlers(app: FastAPI) -> None:
    # 1. 비즈니스 예외 (SharedException 및 하위 예외)
    # NotFoundException, ConflictException, 각 도메인 예외 등 SharedException을 상속한 예외가 모두 여기로 옴
    @app.exception_handler(SharedException)
    async def shared_exception_handler(request: Request, exc: SharedException):
        # 500 이상은 서버 문제라 error, 그 외(4xx)는 클라이언트 요청 문제라 warning으로 로그를 남김
        if exc.status_code >= 500:
            logger.error("비즈니스 서버 오류 [%s]: %s", exc.error_code, exc.message)
        else:
            logger.warning(
                "클라이언트 요청 예외 [%s] %s (path: %s, method: %s)",
                exc.error_code,
                exc.message,
                request.url.path,
                request.method,
            )

        # 예외에 저장해둔 값(exceptions.py의 self.~)을 꺼내서 공통 실패 응답을 만듦
        response_dto = APIResponse.fail(
            code=exc.error_code, message=exc.message, errors=exc.errors
        )

        # model_dump(mode="json"): 응답 객체를 JSON으로 보낼 수 있는 dict로 변환 (datetime → 문자열 등)
        return JSONResponse(
            status_code=exc.status_code, content=response_dto.model_dump(mode="json")
        )

    # 2. Pydantic 스키마 검증 실패 (422)
    # 타입 오류, 필수값 누락, JSON 문법 오류 등 요청 형식이 스키마와 맞지 않을 때 FastAPI가 자동으로 발생시킴
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ):
        # 필드별 에러 목록으로 정리 → {"quantity": ["Input should be a valid integer"]}
        errors_map: dict[str, list[str]] = {}
        for err in exc.errors():
            # err["loc"]: 에러 위치 ("body", "quantity") → 앞의 "body"는 빼고 필드 이름만 "."으로 연결
            loc = ".".join(str(item) for item in err["loc"] if item != "body")
            # 특정 필드가 아닌 요청 전체 오류(JSON 문법 오류 등)는 "non_field_errors"로 모음
            field_name = loc if loc else "non_field_errors"
            # setdefault: 키가 없으면 빈 리스트를 만들고, 있으면 기존 리스트에 메시지를 추가
            errors_map.setdefault(field_name, []).append(err["msg"])

        logger.warning(
            "요청 파라미터 유효성 검증 실패 (path: %s, method: %s): %s",
            request.url.path,
            request.method,
            errors_map,
        )

        response_dto = APIResponse.fail(
            code="REQUEST_VALIDATION_ERROR",
            message="요청 입력값 검증에 실패했습니다.",
            errors=errors_map,
        )
        # ⚠️ 422는 HTTP_422_UNPROCESSABLE_CONTENT 사용 (HTTP_422_UNPROCESSABLE_ENTITY는 deprecated 경고가 남)
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=response_dto.model_dump(mode="json"),
        )

    # 3. 프레임워크가 직접 발생시키는 HTTP 예외 (404, 405, 401 등)
    # 없는 URL(404), 허용하지 않는 메서드(405), 토큰 누락(HTTPBearer) 등 우리 코드를 거치지 않고 Starlette/FastAPI가 발생시킴
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        logger.warning(
            "HTTP 예외 [%s] %s (path: %s, method: %s)",
            exc.status_code,
            exc.detail,
            request.url.path,
            request.method,
        )

        response_dto = APIResponse.fail(
            code="HTTP_ERROR",
            message=str(exc.detail),
            errors=None,
        )

        # headers: 401 응답의 WWW-Authenticate 같은 헤더를 그대로 유지하기 위해 넘김
        return JSONResponse(
            status_code=exc.status_code,
            content=response_dto.model_dump(mode="json"),
            headers=exc.headers,
        )

    # 4. 처리되지 않은 시스템 내부 오류 (500)
    # 위 핸들러들에 걸리지 않은 모든 예외 (DB 연결 실패, 코드 버그 등)
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        # logger.exception: 에러 내용과 함께 어디서 났는지(traceback)까지 로그로 남김
        logger.warning(
            "처리되지 않은 치명적 시스템 오류 발생 (path: %s, method: %s): %s",
            request.url.path,
            request.method,
            exc,
        )

        # 내부 오류 내용은 보안상 클라이언트에게 보여주지 않고 고정 메시지로 응답 (자세한 내용은 로그로 확인)
        response_dto = APIResponse.fail(
            code="INTERNAL_SERVER_ERROR",
            message="서버 내부 오류가 발생했습니다. 관리자에게 문의해주세요.",
            errors=None,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_dto.model_dump(mode="json"),
        )
