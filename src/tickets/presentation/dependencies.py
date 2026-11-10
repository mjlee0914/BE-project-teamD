# presentation/dependencies.py
# 라우터가 Depends()로 받아 쓰는 "자리표시자" 의존성 모음

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials

from shared.core.actor import bearer
from tickets.application.service import TicketService


def get_ticket_service() -> TicketService:
    raise NotImplementedError("wiring/ticket.py에서 연결되지 않았습니다.")


# 2. 요청한 사람 (누구인지 + 관리자인지)
# 라우터가 "이 요청을 보낸 사람이 누구인지" 알기 위해 받는 값
# frozen=True: 만든 뒤에는 값을 바꿀 수 없다 → 요청 처리 도중에 실수로 is_admin을 True로 바꾸는 사고를 막는다
@dataclass(frozen=True)
class CurrentActor:
    user_id: int
    is_admin: bool


# 요청한 사람 정보를 달라는 자리표시자
# 실제 구현은 wiring/ticket.py의 build_current_actor가 담당한다
#   - 토큰 검증(auth) → user_id 추출
#   - (TODO) 관리자·활성 회원 확인(users) → is_admin 채우기
# 로그인이 안 된 요청은 이 단계에서 걸러져 라우터까지 오지 않는다 (401)
# credentials 파라미터: Swagger 자물쇠 표시용 (shared/core/actor.py 참고)
async def get_current_actor(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> CurrentActor:
    raise NotImplementedError("get_current_actor 의존성이 주입되지 않았습니다.")
