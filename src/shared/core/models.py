from sqlalchemy.orm import DeclarativeBase

# 데이터베이스 테이블의 기준(베이스 클래스) 정의
class Base(DeclarativeBase):
    pass


# 모델 초기화
def init_models():
    """SQLAlchemy 모델 메타데이터 등록"""
    # import user.infrastructure.models