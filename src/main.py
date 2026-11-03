from fastapi import FastAPI

from reservations.presentation.router import router as reservation_router

app = FastAPI()

# 이 앱에서 발생하는 공통 예외를 처리하도록 등록합니다.
register_exception_handlers(app)

app.include_router(reservation_router)


@app.get("/")
async def root():
    return {"message": "OK"}