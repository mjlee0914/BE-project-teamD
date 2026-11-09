# 파일 역할: 개발용 DDL 도구다. 기본 실행은 SQL 출력만 하고, --apply를 명시했을 때만 설정된 DB에 payments 테이블을 생성한다.

"""결제 테이블 DDL 미리보기. --apply를 지정할 때만 설정된 DB에 테이블을 생성한다."""

import argparse
import asyncio

from sqlalchemy import Connection, inspect
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from payments.infrastructure.models import PaymentModel
from shared.core.models import init_models


# 이미 있는 테이블을 덮어쓰지 않고 신규 payments 테이블만 만든다. 참조하는 예매 테이블은 미리 존재해야 한다.
def _create_table(connection: Connection) -> None:
    if inspect(connection).has_table("payments"):
        raise RuntimeError(
            "payments 테이블이 이미 있습니다. 기존 스키마와 비교 후 마이그레이션하세요."
        )
    PaymentModel.__table__.create(connection)


# 실제 DB 생성은 트랜잭션 안에서 실행하고, 성공·실패와 무관하게 엔진의 연결 자원을 정리한다.
async def _apply() -> None:
    # DDL 미리보기에는 DB 환경변수나 접속이 필요 없다.
    from shared.core.database import engine

    try:
        async with engine.begin() as connection:
            await connection.run_sync(_create_table)
    finally:
        await engine.dispose()


# 명령행 옵션을 읽는다. 기본은 PostgreSQL DDL 출력, --apply는 실제 DB 변경이라는 차이가 있다.
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="설정된 DB에 payments 테이블 생성"
    )
    args = parser.parse_args()
    init_models()
    if args.apply:
        asyncio.run(_apply())
    else:
        dialect = postgresql.dialect()
        print(CreateTable(PaymentModel.__table__).compile(dialect=dialect))
        for index in sorted(PaymentModel.__table__.indexes, key=lambda item: item.name):
            print(CreateIndex(index).compile(dialect=dialect))


if __name__ == "__main__":
    main()
