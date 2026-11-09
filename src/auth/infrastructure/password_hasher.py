# 파일 역할: users의 PasswordHasher 계약을 bcrypt로 구현한다. 비밀번호 해시 생성과 기존 해시 비교를 제공한다.

import re

from users.domain.exceptions import InvalidPassword
from users.domain.service import PasswordHasher


# 원문을 복원하는 암호화가 아니라 단방향 해시를 사용한다. 비교할 때는 bcrypt.checkpw를 호출한다.
class BcryptPasswordHasher(PasswordHasher):
    """users의 해시 계약 구현. bcrypt 원본 형식을 사용하고 비밀번호를 자르지 않는다."""

    # bcrypt 연산 비용을 설정한다. 값이 클수록 계산량이 늘어나며 기본값은 12다.
    def __init__(self, rounds: int = 12):
        if type(rounds) is not int or not 4 <= rounds <= 31:
            raise ValueError("bcrypt 비용은 4~31 사이의 정수여야 합니다.")
        self._rounds = rounds

    # UTF-8 바이트 길이를 검사하고 새 salt를 생성해 해시한다. 같은 비밀번호여도 salt에 따라 결과가 달라진다.
    def hash(self, raw_password: str) -> str:
        if not isinstance(raw_password, str):
            raise InvalidPassword("비밀번호는 문자열이어야 합니다.")
        try:
            encoded = raw_password.encode("utf-8")
        except UnicodeEncodeError:
            raise InvalidPassword("비밀번호 문자열을 처리할 수 없습니다.") from None
        # bcrypt의 입력 한도는 글자 수가 아닌 바이트 수다. 초과분을 잘라 인증하지 않는다.
        if not 1 <= len(encoded) <= 72:
            raise InvalidPassword("비밀번호는 UTF-8 기준 1~72바이트여야 합니다.")
        bcrypt = self._backend()
        return bcrypt.hashpw(encoded, bcrypt.gensalt(rounds=self._rounds)).decode(
            "ascii"
        )

    # 형식·길이가 유효한 입력만 bcrypt에 전달한다. 잘못된 입력이나 해시이면 인증 성공 대신 False를 반환한다.
    def verify(self, raw_password: str, hashed_password: str) -> bool:
        if not isinstance(raw_password, str) or not isinstance(hashed_password, str):
            return False
        if (
            re.fullmatch(
                r"\$2[aby]\$(?:0[4-9]|[12][0-9]|3[01])\$[./A-Za-z0-9]{53}",
                hashed_password,
            )
            is None
        ):
            return False
        try:
            encoded = raw_password.encode("utf-8")
        except UnicodeEncodeError:
            return False
        if not 1 <= len(encoded) <= 72:
            return False
        bcrypt = self._backend()
        try:
            return bcrypt.checkpw(encoded, hashed_password.encode("ascii"))
        except ValueError:
            return False

    # bcrypt 모듈을 필요할 때 읽는다. 설치가 빠져 있으면 설정 오류를 내고 인증을 우회하지 않는다.
    @staticmethod
    def _backend():
        try:
            import bcrypt
        except ImportError:
            raise RuntimeError(
                "bcrypt 의존성이 준비되지 않았습니다. 해시 구현체 설정을 확인하세요."
            ) from None
        return bcrypt
