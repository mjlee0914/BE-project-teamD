"""
router.py
- 회원 API 엔드포인트 (HTTP <-> service 연결)
- 요청 하나를 처리하는 순서: 바디 검증(schema) -> 토큰 확인 -> service 호출 -> 공통 응답으로 감싸기
- 비즈니스 규칙, DB 작업은 하지 않음 -> service, domain에 맡김

# 의존성
- UserServiceDep: get_user_service -> wiring이 바꿔 끼운 진짜 UserService가 들어옴
- CurrentUser: get_current_user가 토큰을 검증한 결과(user_id, jti), 실패하면 401

# /me 방식
- URL에 id를 받지 않고 토큰의 user_id만 사용
- /users/3처럼 남의 id를 넣어 조회, 수정하는 공격(IDOR)이 구조적으로 불가능

# 응답
- 모든 응답을 APIResponse.ok(data, message)로 감쌈 -> {success, code, message, data}
"""

from typing import Annotated

from fastapi import APIRouter, Depends

# auth/domain/entities.py
from auth.domain.entities import TokenPayload

# auth/presentation/dependencies.py
from auth.presentation.dependencies import get_current_user

# shared/core/schemas.py
from shared.core.schemas import APIResponse

# users/application/service.py
from users.application.service import UserService

# users/presentation/dependencies.py
from users.presentation.dependencies import get_user_service

# users/presentation/schemas.py
from users.presentation.schemas import (
    PasswordChange,
    UserCreate,
    UserResponse,
    UserUpdate,
)

# 모든 경로 앞에 /v1/users가 붙음, Swagger에서 "users" 그룹으로 표시
router = APIRouter(prefix="/v1/users", tags=["users"])

# FastAPI가 wiring 등록부를 보고 진짜 service를 넣어줌
# 매 함수 마다 Depends(...)를 반복하지 않도록 타입 별칭으로 묶음
UserServiceDep = Annotated[UserService, Depends(get_user_service)]
# 이 매개변수가 있는 API = 로그인 필수, 토큰이 없거나 잘못되면 함수 본문까지 오지 않고 401
# 토큰을 검증한 결과 (user_id, jti)
CurrentUser = Annotated[TokenPayload, Depends(get_current_user)]


# [회원가입] POST /v1/users -> 201
# CurrentUser 없음 -> 로그인 없이 호출 가능
@router.post("", status_code=201, response_model=APIResponse[UserResponse])
async def create_user(body: UserCreate, service: UserServiceDep):
    # [1] 바디 검증: UserCreate 모양이 아니면 FastAPI가 자동으로 422
    # [2] service 실행: 형식 검증 422, 이메일, 전화번호 중복 409 (규칙 3, 9)
    # password가 아닌 raw_password(평문)라는 걸 키워드 인자로 명시
    user = await service.signup(
        email=body.email,
        name=body.name,
        raw_password=body.password,
        phone=body.phone,
    )
    # [3] 응답: User 엔티티 -> UserResponse(password_hash 제외) -> 공통 응답
    return APIResponse.ok(
        data=UserResponse.model_validate(user), message="회원가입 완료"
    )


# [내 정보 조회] GET /v1/users/me -> 200
@router.get("/me", response_model=APIResponse[UserResponse])
async def get_user(current: CurrentUser, service: UserServiceDep):
    # [1] 토큰 확인: 없거나 잘못되면 401
    # [2] service 실행: 회원 없음 404, 탈퇴 회원 403 (규칙 23)
    user = await service.get_me(current.user_id)
    # [3] 응답
    return APIResponse.ok(data=UserResponse.model_validate(user))


# [내 정보 수정] PATCH /v1/users/me -> 200
# 수정 대상은 항상 토큰 주인 본인, email, role은 바꿀 수 없음
@router.patch("/me", response_model=APIResponse[UserResponse])
async def patch_user(body: UserUpdate, current: CurrentUser, service: UserServiceDep):
    # [1] 토큰 확인: 401
    # [2] service 실행: 회원 없음 404, 탈퇴 회원 403, 형식 위반 422, 전화번호 중복 409 (규칙 9, 18~21)
    user = await service.update_profile(
        current.user_id, name=body.name, phone=body.phone
    )
    # [3] 응답: 수정된 회원 정보
    return APIResponse.ok(
        data=UserResponse.model_validate(user), message="회원 정보 수정 완료"
    )


# [비밀번호 변경] PATCH /v1/users/me/password -> 200
# 변경 대상은 항상 토큰 주인 본인
@router.patch("/me/password", response_model=APIResponse[None])
async def change_password(
    body: PasswordChange, current: CurrentUser, service: UserServiceDep
):
    # [1] 토큰 확인: 401
    # [2] service 실행: 회원 없음 404, 탈퇴 회원 403, 기존 비밀번호 불일치·재사용·형식 위반 422 (규칙 12~14)
    await service.change_password(current.user_id, body.old_password, body.new_password)
    # [3] 응답: 메시지만
    return APIResponse.ok(message="비밀번호 변경 완료")


# [회원 탈퇴] DELETE /v1/users/me -> 200
# 본인 탈퇴: 대상(target)과 요청자(requester)가 모두 토큰 주인
@router.delete("/me", response_model=APIResponse[None])
async def delete_user(current: CurrentUser, service: UserServiceDep):
    # [1] 토큰 확인: 401
    # [2] service 실행: 회원 없음 404, 이미 탈퇴 409, 본인·ADMIN이 아니면 403 (규칙 15, 16)
    # 행은 남기고 status=WITHDRAWN, deleted_at만 기록 (규칙 17)
    await service.withdraw(target_user_id=current.user_id, requester_id=current.user_id)
    # [3] 응답: 메시지만
    return APIResponse.ok(message="회원 탈퇴 완료")
