from fastapi import FastAPI

def wire_ticket_dependencies(app: FastAPI) -> None:
    app.dependency_overrides.update(
        {
            # 추상 의존성: 구현체 팩토리
        }
    )