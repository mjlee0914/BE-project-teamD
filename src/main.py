from fastapi import FastAPI

from reservations.presentation.router import router as reservation_router

app = FastAPI()

app.include_router(reservation_router)


@app.get("/")
async def root():
    return {"message": "OK"}
