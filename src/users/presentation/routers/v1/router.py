from fastapi import APIRouter

router = APIRouter(prefix="/v1/users", tags=["users"])


# 회원가입
@router.post("")
async def create_user():
    return {"message": "회원가입 완료"}


# 회원조회
@router.get("/me")
async def get_user():
    return {"message": "회원조회 완료"}


# 회원수정
@router.patch("/me")
async def patch_user():
    return {"message": "회원수정 완료"}


# 회원탈퇴
@router.delete("/me")
async def delete_user():
    return {"message": "회원탈퇴 완료"}
