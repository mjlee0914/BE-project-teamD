import os
from typing import AsyncGenerator
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from shared.core.logger import get_logger

# .env 파일의 값을 환경 변수로 불러옴
load_dotenv()
logger = get_logger(__name__)

# 데이터베이스 접속 정보
# 형식: postgresql+asyncpg://유저:비밀번호@호스트:포트/DB이름
# 코드에 직접 적지 않고 .env에서만 읽어옴 (없으면 바로 에러)
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL 환경 변수가 설정되지 않았습니다. .env 파일을 확인하세요.")

# 커넥션 풀 설정 및 비동기 엔진 생성
# 커넥션 풀: DB 연결을 미리 만들어두고 재사용해서, 요청마다 새로 연결하는 비용을 줄임
POOL_SIZE = int(os.getenv("POOL_SIZE", "10"))        # 평소에 유지하는 연결 개수
MAX_OVERFLOW = int(os.getenv("MAX_OVERFLOW", "20"))  # 바쁠 때 추가로 더 만들 수 있는 연결 개수 (최대 POOL_SIZE + MAX_OVERFLOW)
engine = create_async_engine(
    DATABASE_URL,
    pool_size=POOL_SIZE,
    max_overflow=MAX_OVERFLOW,
    pool_timeout=30.0,    # 남는 연결이 없을 때 최대 30초 기다리고, 넘으면 에러
    pool_recycle=1800,    # 30분 지난 연결은 새로 만듦 (DB가 오래된 연결을 끊는 문제 방지)
    pool_pre_ping=True,   # 연결을 꺼내 쓰기 전에 살아있는지 확인
    echo=os.getenv("SQL_ECHO", "False").lower() == "true"  # SQL_ECHO=true면 실행되는 SQL을 로그로 출력
)

# 비동기 데이터베이스 세션 생성
# 세션: DB 작업(조회/저장 등)을 묶어서 처리하는 단위. AsyncSessionLocal()로 하나씩 만들어 씀
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autoflush=False,          # 쿼리 전에 변경사항을 자동으로 DB에 보내지 않음 (직접 제어)
    expire_on_commit=False,   # commit 후에도 객체 값을 그대로 읽을 수 있게 함 (비동기에서 필요)
)

# FastAPI에 데이터베이스 세션 제공 함수 정의
# 사용법: async def api(db: AsyncSession = Depends(get_db))
# 요청마다 세션을 하나 열고, 요청이 끝나면 자동으로 닫음
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback() # 오류 발생하면 작업 모두 취소
            raise

# 서버 종료 시 커넥션 풀을 안전하게 반환하는 함수
async def close_db() -> None:
    logger.info("데이터베이스 엔진 연결 풀을 종료합니다.")
    await engine.dispose()
