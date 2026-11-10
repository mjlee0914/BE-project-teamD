"""
# main.py
FastAPI 앱의 시작점
실행: 프로젝트 루트에서 uv run uvicorn main:app --app-dir src --reload

# 하는 일
1. app 생성
2. 전역 예외 핸들러 등록 (shared/core/exception_handlers.py)
3. 의존성 연결 (wiring/)
4. 도메인별 라우터 등록
"""

# 표준 라이브러리
import asyncio
from contextlib import asynccontextmanager, suppress

# 외부 라이브러리
from fastapi import FastAPI

from auth.presentation.routers.v1.router import router as auth_router
from festivals.presentation.routers.v1.router import router as festival_router
from payments.infrastructure.recovery_job import start_payment_recovery_job
from payments.presentation.routers.v1.router import router as payment_router
from payments.presentation.routers.v1.webhook_router import (
    router as payment_webhook_router,
)
from performances.presentation.routers.v1.router import router as performance_router

# 프로젝트 코드
from reservations.infrastructure.expire_job import start_expire_job
from reservations.presentation.routers.v1.router import (
    admin_router as reservation_admin_router,
)
from reservations.presentation.routers.v1.router import router as reservation_router
from shared.core.exception_handlers import register_exception_handlers
from tickets.presentation.routers.v1.router import router as ticket_router
from users.presentation.routers.v1.router import router as user_router
from wiring import wire_dependencies


# 서버 시작·종료 시 할 일
# - 시작 : 입금 기한 지난 예매를 만료시키는 주기 작업 실행 (#134)
# - 종료 : 주기 작업 멈추기
@asynccontextmanager
async def lifespan(app: FastAPI):
    expire_task = start_expire_job()
    payment_task = start_payment_recovery_job()
    yield
    expire_task.cancel()
    payment_task.cancel()
    with suppress(asyncio.CancelledError):
        await expire_task
    with suppress(asyncio.CancelledError):
        await payment_task


app = FastAPI(lifespan=lifespan)

# 전역 예외 핸들러 등록
# 이후 모든 API에서 발생한 예외가 APIResponse.fail() 형식으로 응답됨
# app이 만들어진 직후에 등록해야 함
register_exception_handlers(app)

# 의존성 연결 (FastAPI Dependency Overrides)
# 각 도메인의 추상 의존성(인터페이스)에 실제 구현체를 연결함 → 도메인별 설정은 wiring/ 폴더 참고
wire_dependencies(app)

# 도메인별 라우터 등록
# 새 도메인 라우터를 만들면 위에서 import하고 여기에 include_router를 추가
app.include_router(reservation_router)
app.include_router(reservation_admin_router)  # 축제별 예매 목록 (관리자, #117)
app.include_router(user_router)
app.include_router(performance_router)
app.include_router(festival_router)
app.include_router(ticket_router)
app.include_router(auth_router)
app.include_router(payment_router)
app.include_router(payment_webhook_router)


# 서버 동작 확인용 (헬스 체크)
@app.get("/")
async def root():
    return {"message": "OK"}
