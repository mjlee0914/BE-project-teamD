# SharedException 팀원 사용 가이드

> 이 문서는 공통 예외 처리기를 프로젝트에 도입할 때 사용할 안내서입니다.
> 문서 작성 시점에는 공통 처리기 파일 복사와 `main.py` 등록이 아직 완료되지 않았습니다.
> 아래 예외 이름·상태 코드·메시지는 제안 예시입니다. 실제 적용 시 팀 API 명세에 맞춰 확정하세요.

## 1. 무엇을 공유하나요?

각 도메인에서 문제가 발생했을 때 같은 모양의 오류 응답을 보내기 위한 기능입니다. DB에 설치하는 기능이 아니라 **FastAPI 앱에 등록하는 처리기**입니다.

예를 들어 없는 예매를 조회하면 다음과 같이 응답합니다.

HTTP 상태 코드: `404`

```json
{
  "success": false,
  "message": "예매 정보를 찾을 수 없습니다."
}
```

각 도메인 담당자는 **문제가 생기는 조건을 확인하고 예외를 발생시키는 코드**를 작성합니다. 공통 처리기는 그 예외를 받아 HTTP 상태 코드와 JSON 응답을 만듭니다. 예외 클래스만 만들면 자동으로 문제를 찾아주는 것은 아닙니다.

```text
요청 → 라우터 → 서비스에서 업무 처리 또는 DB 조회
                         ↓ 문제 발견
                  도메인 예외를 raise
                         ↓
                  공통 예외 처리기
                         ↓
                 HTTP 상태 코드 + JSON
```

## 2. 공통 기능 담당자가 한 번 할 일

### 파일 추가

기존 예제 프로젝트 `shared_exception_reconstructed`의 `src/shared/core`에서 아래 세 파일을 가져옵니다. 대상 프로젝트의 기존 `database.py`, `logger.py`는 유지합니다.

```text
src/shared/
├─ __init__.py
├─ database.py
├─ logger.py
└─ core/
   ├─ __init__.py     # 빈 파일 추가
   ├─ exception.py   # SharedException
   ├─ handlers.py    # error_handler, register_exception_handlers
   └─ schemas.py     # APIResponse
```

예제의 `.venv`, `main.py`, `requirements.txt`, `demo.py`를 팀 프로젝트에 덮어쓰지 않습니다. 대상 프로젝트는 자체 `pyproject.toml`과 `uv.lock`으로 의존성을 관리합니다.

### 앱에 등록

`src/main.py`에서 앱을 생성한 다음 처리기를 한 번 등록합니다.

```python
from fastapi import FastAPI

from reservations.presentation.router import router as reservation_router
from shared.core.handlers import register_exception_handlers

app = FastAPI()
register_exception_handlers(app)

app.include_router(reservation_router)


@app.get("/")
async def root():
    return {"message": "OK"}
```

이 코드는 현재 `main.py` 구조를 기준으로 한 예시입니다. 다른 라우터나 lifespan이 추가되었다면 그 설정을 유지하고 import와 등록 코드만 추가합니다. 일반 오류도 공통 JSON으로 응답하도록 앱의 `debug=True` 설정은 사용하지 않습니다.

**등록한 동일 앱에 연결된 라우터들이 공통 처리기를 사용합니다.** 각 팀원이 자기 라우터에서 처리기를 다시 등록할 필요는 없습니다. 도메인 라우터 자체를 앱에 연결하는 작업은 별도로 필요합니다.

## 3. 각 도메인 담당자가 할 일

### ① 자기 도메인에 예외 클래스 만들기

권장 파일 위치는 다음과 같습니다.

```text
src/reservations/domain/exceptions.py
src/tickets/domain/exceptions.py
src/users/domain/exceptions.py
```

예매 담당자 예시:

```python
# src/reservations/domain/exceptions.py
from shared.core.exception import SharedException


class ReservationNotFoundException(SharedException):
    def __init__(self):
        super().__init__(
            status_code=404,
            message="예매 정보를 찾을 수 없습니다.",
        )
```

티켓 담당자 예시:

```python
# src/tickets/domain/exceptions.py
from shared.core.exception import SharedException


class TicketAlreadyUsedException(SharedException):
    def __init__(self):
        super().__init__(
            status_code=409,
            message="이미 사용된 티켓입니다.",
        )
```

회원 담당자 예시:

```python
# src/users/domain/exceptions.py
from shared.core.exception import SharedException


class UserNotFoundException(SharedException):
    def __init__(self):
        super().__init__(
            status_code=404,
            message="사용자를 찾을 수 없습니다.",
        )
```

`(SharedException)`은 공통 예외를 상속한다는 뜻입니다. 상태 코드와 메시지를 예외 클래스에 정해 두면 사용하는 곳마다 같은 문구를 다시 쓸 필요가 없습니다. 메시지는 그대로 사용자에게 전달되므로 비밀번호, 토큰, DB 접속 정보 등 내부 정보를 넣지 않습니다.

### ② 문제가 발견되는 곳에서 raise 하기

서비스가 구현되어 있다면 서비스에서 업무 규칙을 확인하고 예외를 발생시키는 방식을 권장합니다.

다음은 **흐름 설명용 코드**입니다. `repository.find_by_id`는 현재 프로젝트에 구현된 메서드가 아니며, 실제 저장소 메서드에 맞춰 작성해야 합니다.

```python
from reservations.domain.exceptions import ReservationNotFoundException


async def get_reservation(reservation_id: int, repository):
    reservation = await repository.find_by_id(reservation_id)

    if reservation is None:
        raise ReservationNotFoundException()

    return reservation
```

다른 도메인도 같은 방식으로 사용합니다. 아래 변수와 속성은 설명용이며 실제 모델에 맞춰야 합니다.

```python
# 티켓을 조회한 뒤 사용 여부를 확인하는 위치
if ticket.is_used:
    raise TicketAlreadyUsedException()

# 회원을 조회한 뒤 결과를 확인하는 위치
if user is None:
    raise UserNotFoundException()
```

`raise`를 만나면 정상 처리가 중단되고 예외가 상위 호출로 전달됩니다. 공통 처리기가 처리할 수 있도록 도중에 예외를 숨기지 않습니다.

### ③ 오류 응답을 직접 만들지 않기

공통 처리 대상인 업무 오류는 다음처럼 사용합니다.

```python
raise ReservationNotFoundException()
```

다음처럼 예외 객체를 `return`하지 않습니다.

```python
# 잘못된 사용: 예외가 발생하지 않습니다.
return ReservationNotFoundException()
```

또한 `return {"success": False, ...}`만 사용하면 별도로 상태 코드를 지정하지 않는 한 정상 상태 코드인 200이 반환될 수 있습니다. 공통 처리기에 맡길 오류는 `raise`로 전달하세요.

다음과 같이 모든 오류를 잡아 정상 반환값으로 바꾸면 공통 처리기까지 전달되지 않습니다.

```python
# 피할 패턴
try:
    ...
except Exception:
    return {"message": "오류 발생"}
```

정리 작업을 위해 잡아야 한다면 필요한 작업 후 `raise`로 다시 전달합니다. 실제 트랜잭션 처리는 프로젝트의 DB 세션 정책을 따릅니다.

## 4. 어떤 오류가 공통 처리되나요?

| 발생한 예외 | 현재 예제 처리기의 응답 |
|---|---|
| SharedException 및 이를 상속한 도메인 예외 | 지정한 상태 코드 + `success/message` |
| 별도 처리되지 않은 일반 예외 | 500 + `success: false`, `서버 내부 오류가 발생했습니다.` |
| FastAPI HTTPException | FastAPI 기본 `detail` 형식, 지정한 상태 코드와 헤더 유지 |
| 요청 입력 검증 오류 | FastAPI 기본 422 + `detail` 형식 |

예상하지 못한 일반 예외의 상세 내용은 서버 로그에 남습니다. 모든 오류를 “찾을 수 없음” 예외로 바꾸지 마세요. 예를 들어 **조회 결과 없음**과 **DB 연결 실패**는 다른 문제입니다.

공통 응답 모델 `APIResponse`는 여기서 오류 응답의 형태를 정합니다. 도입만으로 기존 성공 응답 형태가 바뀌지는 않습니다. HTTPException과 입력 검증 오류까지 통일하려면 팀 합의 후 별도 처리기를 추가해야 합니다.

## 5. DB와는 어떻게 연결되나요?

DB 조회 결과를 확인하는 서비스 코드에서 필요한 도메인 예외를 발생시키면 됩니다. 공통 처리기가 DB를 직접 조회하거나 연결 설정을 바꾸지는 않습니다.

현재 `src/shared/database.py`의 `get_db()`에는 세션 사용 중 예외가 전달되면 `rollback()`하고 다시 `raise`하는 코드가 있습니다. 해당 의존성을 사용하는 요청에서 예외가 세션 사용 범위 밖으로 전달되어야 이 경로가 실행됩니다.

**SharedException 자체는 롤백, 커밋, 인증 검사, 중복 예매 방지를 수행하지 않습니다.** 이미 커밋된 변경을 예외 발생만으로 되돌릴 수도 없습니다. 트랜잭션 경계와 동시 요청에 대한 제약은 각 기능에서 별도로 설계해야 합니다.

## 6. DB 없이 연결을 먼저 확인하는 방법

공통 파일과 처리기 등록을 완료한 뒤, `src/main.py` 아래쪽에 다음 임시 확인용 API를 추가할 수 있습니다.

```python
from shared.core.exception import SharedException


@app.get("/_check/shared-exception", include_in_schema=False)
async def check_shared_exception():
    raise SharedException(409, "공통 예외 처리 연결 확인")
```

프로젝트 루트에서 실행합니다.

```powershell
uv sync
uv run uvicorn main:app --app-dir src --reload
```

브라우저로 `http://127.0.0.1:8000/_check/shared-exception`에 접속하면 다음 JSON이 보여야 합니다.

```json
{
  "success": false,
  "message": "공통 예외 처리 연결 확인"
}
```

HTTP 상태 코드까지 확인하려면 PowerShell에서 실행하세요.

```powershell
curl.exe -i http://127.0.0.1:8000/_check/shared-exception
```

상단에 `409 Conflict`가 표시되면 됩니다. 확인 후 임시 API와 그 용도로만 추가한 import는 제거합니다. 이 검사는 공통 연결 확인용이며 실제 DB나 각 도메인 기능의 동작을 보장하지 않습니다.

현재 앱은 DB를 불러오지 않아 이 확인에 DB가 필요하지 않습니다. 이후 앱 시작 시 DB를 초기화하도록 변경되면 해당 실행 환경도 준비해야 합니다. 기존 실습 서버가 8000번 포트를 사용 중이면 먼저 종료하세요.

## 7. 각 도메인의 작업 완료 전 확인

- 예외 클래스가 `SharedException`을 상속하는가?
- 실제 업무 조건을 확인한 위치에서 `raise`하는가?
- 상태 코드와 공개 메시지가 팀 API 명세와 일치하는가?
- 정상 요청은 기존 정상 응답을 유지하는가?
- 오류 요청은 예상한 상태 코드와 `success/message`를 반환하는가?
- 오류를 중간에서 잡아 200 응답으로 바꾸고 있지 않은가?
- DB를 사용하는 기능은 실패 시 트랜잭션 처리도 별도로 검증했는가?

## 팀 공유용 짧은 안내

> 공통 예외 처리기는 FastAPI 앱에 한 번 등록합니다. 각 도메인에서는 `from shared.core.exception import SharedException`으로 가져와 자기 도메인의 예외를 상속해 만들고, 문제가 발견되면 `raise 도메인예외()`로 발생시키면 됩니다. 상태 코드와 메시지는 팀 API 명세에 맞춰 예외 클래스에서 정의하세요. 오류 JSON은 공통 처리기가 생성하므로 각 API에서 따로 만들 필요가 없습니다. FastAPI HTTPException과 입력 검증 오류는 현재 기본 형식을 유지합니다. 공통 파일 복사와 앱 등록이 완료된 뒤 사용 가능합니다.
