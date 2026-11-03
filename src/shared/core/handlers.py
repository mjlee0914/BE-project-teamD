import logging

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from shared.core.exception import SharedException
from shared.core.schemas import APIResponse

logger = logging.getLogger(__name__)


async def error_handler(request: Request, exc: Exception) -> JSONResponse:
    status_code = (
        exc.status_code
        if isinstance(exc, SharedException)
        else status.HTTP_500_INTERNAL_SERVER_ERROR
    )
    if isinstance(exc, SharedException):
        message = str(exc)
    else:
        # 영상은 모든 예외에 str(exc)를 사용. 이 분기는 실행용 보완.
        logger.error("Unhandled request error", exc_info=(type(exc), exc, exc.__traceback__))
        message = "서버 내부 오류가 발생했습니다."

    return JSONResponse(
        status_code=status_code,
        content=APIResponse(success=False, message=message).model_dump(mode="json"),
    )


def register_exception_handlers(app: FastAPI) -> None:
    # 영상은 Exception만 등록. 예상된 도메인 예외를 별도로 등록하도록 보완.
    app.add_exception_handler(SharedException, error_handler)
    app.add_exception_handler(Exception, error_handler)
