# 파일 역할: 인증 결과를 전달하는 데이터 객체다. DB 조회나 JWT 검증은 다른 계층에서 수행한다.

"""인증(auth) 과정에서 주고받을 정보를 ONLY 파이선 객체로 정의"""

""" ※로그인 처리나 JWT 검증 자체를 수행하는 코드는 아님"""

# dataclasses -> 파이썬 기본 제공 모듈
# dataclass는 객체를 만들 때 필요한 초기화 메서드를 자동으로 만들어줌

from dataclasses import dataclass


# 토큰 검증 후 사용할 회원 ID와 jti만 보관한다. frozen=True이므로 생성 후 필드를 바꾸지 못한다.
@dataclass(frozen=True)  # 수정을 불가하게 해줌
class TokenPayload:
    """검증된 토큰에서 추출한 회원 ID와 토큰 식별자."""

    user_id: int
    # 회원 ID와 달리 로그인할 때마다 새로 만드는 토큰 식별자다. 특정 토큰의 로그아웃에 사용한다.
    jti: str
