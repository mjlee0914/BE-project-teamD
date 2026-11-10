# actor.py
# 모든 도메인이 공통으로 쓰는 "요청한 사람" 의존성
# 실제 구현 위치: wiring/actor.py의 build_current_actor
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# Swagger 자물쇠 표시용 (실제 검증은 wiring의 build_current_actor가 담당)
bearer = HTTPBearer(auto_error=False)


# 요청한 사람 (누구인지 + 관리자인지)
# - 예매·티켓·축제·공연이 공통으로 사용
# - frozen=True : 만든 뒤 값 변경 불가 → 처리 도중 실수로 is_admin을 바꾸는 사고 방지
@dataclass(frozen=True)
class CurrentActor:
    user_id: int
    is_admin: bool


# 요청한 사람 제공 (자리표시자)
# - 실제로는 wiring/actor.py의 build_current_actor로 교체됨
#   토큰 검증(auth) → 회원 조회(users) → 탈퇴 회원 차단 → is_admin 채우기
# - 이 본문이 실행됐다 = wiring 등록을 빠뜨렸다는 뜻 → 바로 에러
# - credentials 파라미터: Swagger 문서에 Bearer(자물쇠)를 표시하기 위한 것
#   (dependency_overrides는 실행에만 반영되고 문서는 이 시그니처 기준으로 생성됨)
async def get_current_actor(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> CurrentActor:
    raise NotImplementedError("wiring/actor.py에서 연결되지 않았습니다.")
