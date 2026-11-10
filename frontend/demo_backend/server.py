"""
데모 전용 백엔드 실행 파일 (팀 코드 src/ 는 수정하지 않음)

팀의 FastAPI 앱(src/main.py의 app)을 그대로 가져와서, 데모에 필요한 것만 덧붙인다.

1) 로그인 대체
   - auth 연결(PR #138)이 끝나기 전이라 토큰 로그인이 안 된다
   - 요청 헤더 X-Demo-User(회원 id)로 "누가 요청했는지"를 정한다
   - 예매·티켓의 get_current_actor 자리표시자를 이 함수로 교체
2) 데모 보조 API (/demo/...)
   - GET  /demo/users                         : 화면 상단 회원 선택용 목록
   - POST /demo/reservations/{id}/confirm     : 입금 완료 시뮬레이션 (결제 → confirm_reservation)
   - POST /demo/reservations/{id}/expire      : 입금 기한을 지난 것으로 만들고 만료 작업 1회 실행
   - POST /demo/reset                         : 데모 데이터 초기화

실행 (레포 루트에서)
    uv run uvicorn server:app --app-dir frontend/demo_backend --port 8000
"""

import sys
from datetime import timedelta
from pathlib import Path
from typing import Annotated

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import Depends, Header  # noqa: E402
from sqlalchemy import select, update  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

import seed as demo_seed  # noqa: E402
from main import app  # noqa: E402  ← 팀 앱 그대로
from reservations.infrastructure.models import Reservation as ReservationModel  # noqa: E402
from reservations.presentation.dependencies import (  # noqa: E402
    CurrentActor as ReservationActor,
    get_current_actor as reservation_actor_placeholder,
    provide_reservation_service,
)
from reservations.presentation.schemas import ReservationResponse  # noqa: E402
from shared.core.database import get_db  # noqa: E402
from shared.core.exceptions import UnauthorizedException  # noqa: E402
from shared.core.schemas import APIResponse  # noqa: E402
from shared.core.time import now_utc  # noqa: E402
from tickets.presentation.dependencies import (  # noqa: E402
    CurrentActor as TicketActor,
    get_current_actor as ticket_actor_placeholder,
)
from users.infrastructure.models import UserModel  # noqa: E402


async def _load_demo_user(user_id: int | None, session: AsyncSession) -> UserModel:
    if user_id is None:
        raise UnauthorizedException("데모 회원을 선택해 주세요. (X-Demo-User 헤더)")
    user = await session.get(UserModel, user_id)
    if user is None:
        raise UnauthorizedException("존재하지 않는 데모 회원입니다.")
    return user


async def demo_reservation_actor(
    session: Annotated[AsyncSession, Depends(get_db)],
    x_demo_user: Annotated[int | None, Header()] = None,
) -> ReservationActor:
    user = await _load_demo_user(x_demo_user, session)
    return ReservationActor(user_id=user.id, is_admin=user.role == "ADMIN")


async def demo_ticket_actor(
    session: Annotated[AsyncSession, Depends(get_db)],
    x_demo_user: Annotated[int | None, Header()] = None,
) -> TicketActor:
    user = await _load_demo_user(x_demo_user, session)
    return TicketActor(user_id=user.id, is_admin=user.role == "ADMIN")


app.dependency_overrides[reservation_actor_placeholder] = demo_reservation_actor
app.dependency_overrides[ticket_actor_placeholder] = demo_ticket_actor


@app.get("/demo/users", tags=["demo"])
async def demo_users(session: Annotated[AsyncSession, Depends(get_db)]):
    rows = (await session.scalars(select(UserModel).order_by(UserModel.id))).all()
    return APIResponse.ok(
        data=[{"user_id": u.id, "name": u.name, "role": str(u.role)} for u in rows]
    )


# 입금 완료 시뮬레이션
# - 실제로는 결제 웹훅이 DONE을 받은 뒤 confirm_reservation을 호출해야 한다 (결제 담당 작업)
@app.post("/demo/reservations/{reservation_id}/confirm", tags=["demo"])
async def demo_confirm(
    reservation_id: int,
    service=Depends(provide_reservation_service),
):
    reservation = await service.confirm_reservation(reservation_id)
    return APIResponse.ok(
        data=ReservationResponse.model_validate(reservation),
        message="입금 완료(시뮬레이션) → 예매가 확정되었습니다.",
    )


# 만료 시뮬레이션
# - 입금 기한(expires_at)을 1초 전으로 바꾼 뒤, 서버의 만료 작업과 같은 expire_overdue를 1번 실행
@app.post("/demo/reservations/{reservation_id}/expire", tags=["demo"])
async def demo_expire(
    reservation_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    service=Depends(provide_reservation_service),
):
    await session.execute(
        update(ReservationModel)
        .where(ReservationModel.id == reservation_id)
        .values(expires_at=now_utc() - timedelta(seconds=1))
    )
    count = await service.expire_overdue()
    return APIResponse.ok(data={"expired": count}, message=f"{count}건이 만료되었습니다.")


@app.post("/demo/reset", tags=["demo"])
async def demo_reset():
    result = await demo_seed.seed()
    return APIResponse.ok(data=result, message="데모 데이터를 초기화했습니다.")
