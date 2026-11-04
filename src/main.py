from fastapi import FastAPI

from reservations.presentation.router import router as reservation_router
from users.presentation.routers.v1.router import router as user_router
from wiring import wire_dependencies

app = FastAPI()
wire_dependencies(app)

app.include_router(reservation_router)
app.include_router(user_router)


@app.get("/")
async def root():
    return {"message": "OK"}