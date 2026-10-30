from fastapi import APIRouter

router = APIRouter(prefix="/reservations", tags=["reservations"])


# 예매하기
@router.post("")
async def create_reservation():
    return {"message": "예매 생성"}


# 예매 조회
@router.get("/{reservation_id}")
async def get_reservation(reservation_id: int):
    return {"message": f"{reservation_id}번 예매 조회"}


# 예매 취소
@router.patch("/{reservation_id}/cancel")
async def cancel_reservation(reservation_id: int):
    return {"message": f"{reservation_id}번 예매 취소"}
