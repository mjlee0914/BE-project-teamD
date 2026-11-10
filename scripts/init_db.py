"""현재 모델의 테이블 준비 여부 확인. --create를 지정한 경우에만 없는 테이블을 생성한다."""

import argparse
import asyncio

from sqlalchemy import inspect

from shared.core.database import engine
from shared.core.models import Base, init_models


async def main(create: bool) -> None:
    init_models()
    try:
        async with engine.begin() as connection:
            if create:
                await connection.run_sync(Base.metadata.create_all)
            existing = await connection.run_sync(
                lambda sync: inspect(sync).get_table_names()
            )
            missing = sorted(set(Base.metadata.tables) - set(existing))
            print("Missing tables:", ", ".join(missing) if missing else "none")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--create", action="store_true", help="현재 DB에 없는 모델 테이블 생성"
    )
    asyncio.run(main(parser.parse_args().create))
