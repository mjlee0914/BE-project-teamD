"""
# dependencies.py
- 회원 라우터가 사용할 의존성(UserService)을 꺼내 주는 자리
- router는 UserService를 직접 만들지 않고 Depends(get_user_service)로 받기만 함

# 의존성
- 이 함수는 자리표시자(placeholder)일 뿐, 실제 service는 wiring(src/wiring/user.py)이 만들어줌
- 앱 시작 시 dependency_overrides[get_user_service] = build_user_service로 바꿔 끼움
- presentation은 저장소, 해셔, DB 세션을 몰라도 됨 (계층 분리)

# 주의할 점
- 이 함수 본문이 실행됐다 = wiring 등록을 빠뜨렸다는 뜻 -> 바로 에러를 내서 알아채게 함
"""

# users/application/service.py
from users.application.service import UserService


# [UserService 의존성]
# wiring이 정상 등록되면 이 함수는 실행되지 않음
# 등록이 빠졌을 때만 실행 -> None을 조용히 반환하지 않고 즉시 에러 (fail-fast)
def get_user_service() -> UserService:
    raise NotImplementedError("wiring/user.py에서 연결되지 않았습니다.")
