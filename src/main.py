from fastapi import FastAPI

from reservations.presentation.router import router as reservation_router
from users.presentation.router import router as user_router

app = FastAPI()

app.include_router(reservation_router)
app.include_router(user_router)


@app.get("/")
async def root():
    return {"message": "OK"}