# router는 service가 필요하다.
# 하지만 router는 service를 직접 만들 수 없다. (그러러면 DB 세션과 SQLAlchemy 저장소까지 알아야 한다.)
# 그래서 router는 다리를 만들어서 service를 받는다
# 그 다리가 바로 dependencies.py!
# 이 다리에서는 앱이 시작될 때 wiring이 진짜 service를 만드는 함수를 끼워 넣는다.
# 요청이 오면 FastAPI가 등록부(app.dependency_overrides)를 보고
# get_festival_service 대신 build_festival_service를 부른다. (등록은 wiring이 app 시작 때 해 둠.)
# 그래서 이 파일의 함수는 영원히 NotImplementedError로 남고, 실제로는 한 번도 실행되지 않는다.
# wiring을 빠뜨렸을 때만 실행되서 에러를 낸다.


from festivals.application.service import FestivalService


def get_festival_service() -> FestivalService:
    # wiring에서 빠뜨리면 바로 알아채기 위해 에러 던짐
    # 조용히 None을 돌려주면 원인을 찾기 어려움
    raise NotImplementedError("wiring/festival.py에서 연결되지 않았습니다.")
