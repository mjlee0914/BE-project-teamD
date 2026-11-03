import os
import logging
from dotenv import load_dotenv

# .env 파일의 값을 환경 변수로 불러옴
load_dotenv()

# 로그 레벨 결정: LOGGING_MODE=debug면 DEBUG까지, 아니면 INFO 이상만 출력
log_mode = os.getenv("LOGGING_MODE", "info").lower()
log_level = logging.DEBUG if log_mode == "debug" else logging.INFO


# 로그 출력 형식
# 예) 2026-11-02 14:20:20 [INFO] shared.database (database.py:51) - 메시지
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d) - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# 프로젝트 전체에 적용되는 기본 로깅 설정
# force=True: 다른 라이브러리가 먼저 설정했더라도 이 설정으로 덮어씀
logging.basicConfig(
    level=log_level,
    format=LOG_FORMAT,
    datefmt=DATE_FORMAT,
    force=True,
)

# 모듈별 로거를 꺼내 쓰는 함수
# 사용법: logger = get_logger(__name__) → 로그에 어느 모듈에서 찍혔는지 표시됨
# name을 안 넘기면 LOGGER_NAME 환경 변수(기본값 "app")를 이름으로 사용
def get_logger(name: str | None = None) -> logging.Logger:

    logger_name = name or os.getenv("LOGGER_NAME", "app")
    return logging.getLogger(logger_name)

logger = get_logger(__name__)
