# 파일 역할: 결제 API의 의존성 주입 지점이다. 인증은 auth의 함수를 재사용하고 결제 서비스·소유권 구현체는 wiring에서 연결한다.

from fastapi import HTTPException

from auth.presentation.dependencies import get_current_user as provide_current_user
from auth.presentation.dependencies import provide_auth_service
from payments.application.service import PaymentService
from payments.domain.service import PaymentAccessChecker

# auth 함수의 동일 객체를 재노출한다. auth 서비스 override 하나가 결제 인증에도 적용된다.
__all__ = [
    "provide_auth_service",
    "provide_current_user",
    "provide_payment_access_checker",
    "provide_payment_service",
]


# 결제 서비스의 교체 지점이다. 실제 wiring이 없으면 503을 반환해 미연결 상태를 명시한다.
def provide_payment_service() -> PaymentService:
    raise HTTPException(status_code=503, detail="결제 서비스 연결이 필요합니다.")


# 소유권 검사 구현체의 주입 지점이다. 연결 전에는 권한 검사를 우회하지 않고 503으로 차단한다.
def provide_payment_access_checker() -> PaymentAccessChecker:
    raise HTTPException(status_code=503, detail="결제 소유자 검사 연결이 필요합니다.")
