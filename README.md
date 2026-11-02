# BE-project-teamD

## 👥 팀원

|                         리더                          |                          부리더                           |                           서기                           |                           부서기                           |                         팀원                         |
| :---------------------------------------------------: | :-------------------------------------------------------: | :------------------------------------------------------: | :--------------------------------------------------------: | :--------------------------------------------------: |
| <img src="https://github.com/tuski0.png" width="100"> | <img src="https://github.com/justinweon.png" width="100"> | <img src="https://github.com/mjlee0914.png" width="100"> | <img src="https://github.com/aiagentohms.png" width="100"> | <img src="https://github.com/jsa00.png" width="100"> |
|                        선병철                         |                          원정린                           |                          이명지                          |                           오명석                           |                        조성아                        |
|         [@tuski0](https://github.com/tuski0)          |       [@justinweon](https://github.com/justinweon)        |        [@mjlee0914](https://github.com/mjlee0914)        |       [@aiagentohms](https://github.com/aiagentohms)       |          [@jsa00](https://github.com/jsa00)          |

<br>

## 🛠 기술 스택

| 분류          | 기술                                       |
| ------------- | ------------------------------------------ |
| 언어          | Python 3.13                                |
| 프레임워크    | FastAPI, Uvicorn, Pydantic, Jinja2         |
| DB · ORM      | PostgreSQL, SQLAlchemy (asyncpg, greenlet) |
| 인증          | PyJWT, passlib[bcrypt]                     |
| 패키지 관리   | uv                                         |
| 인프라 · 협업 | Docker, GitHub                             |

<br>

## 목차

- [시작하기](#-시작하기)
- [작업 흐름](#-작업-흐름)
- [python & uv 규칙](#-python--uv-규칙)
- [Docker 명령어](#-docker-명령어)

<br>

## 🚀 시작하기

1. 저장소를 받고 패키지를 설치해요.

```bash
git clone https://github.com/mjlee0914/BE-project-teamD.git
cd BE-project-teamD
uv sync
```

2. 환경 변수 파일을 만들어요. 값은 그대로 써도 돼요.

```bash
cp .env.example .env
```

3. DB(PostgreSQL) 컨테이너를 띄워요. Docker Desktop이 켜져 있어야 해요.

```bash
docker compose up -d   # 컨테이너 생성 및 실행
docker compose ps      # STATUS가 Up이면 정상
```

4. 서버를 실행해요. (프로젝트 루트에서)

```bash
uv run uvicorn main:app --app-dir src --reload
```

<br>

## 🔄 작업 흐름

**이슈 만들기 → 브랜치 만들기 → 작업·커밋 → PR 올리기 → 리뷰·머지**

> ⚠️ `dev`에 바로 push하지 마세요. 항상 브랜치를 만들어 PR로 올려주세요.

### 1. ISSUE 생성하기

상단 ISSUE 탭에서 양식에 맞춰 생성하고 이슈 번호 부여 받기

### 2. 브랜치 만들기

`dev`를 최신으로 받은 다음, 이슈 종류와 번호로 브랜치를 만들어요.

```bash
git switch dev
git pull origin dev
uv sync                # 다른 팀원이 추가한 패키지까지 설치
git switch -c feat/12-email-login
```

| 종류 | 브랜치 이름 예시      |
| ---- | --------------------- |
| 기능 | `feat/12-email-login` |
| 수정 | `fix/15-login-error`  |
| 기타 | `chore/18-uv-setup`   |

### 3. 작업하고 push 하기

```bash
git add .
git commit -m "feat: 이메일 로그인 API 연동"
git push -u origin feat/12-email-login
```

> 💡 커밋 메시지는 `.`처럼 비워두지 말고 무엇을 했는지 적어주세요. 나중에 기록을 볼 때 훨씬 편해요.

### 4. PR 올리기

1. push 직후 GitHub 저장소에 들어가면 노란 배너의 **Compare & pull request** 버튼이 보여요. 클릭하세요.
   - 버튼이 없으면 **Pull requests** 탭 → **New pull request** → `base: dev` ← `compare: 내 브랜치` 선택
   - `base: dev` ← `compare: dev`이면 비교할 게 없어서 PR을 만들 수 없어요. compare를 꼭 내 브랜치로 바꾸세요.
2. 본문에 자동으로 채워진 PR 템플릿을 항목별로 작성하세요.
3. 오른쪽 사이드바에서 **Assignees(본인)**, **Reviewers(팀원)**를 지정하고 **Create pull request** 클릭

#### PR 템플릿 작성 요령

| 항목                              | 작성 방법                                                                                                |
| --------------------------------- | -------------------------------------------------------------------------------------------------------- |
| 🔗 관련 이슈                      | `close #12`처럼 이슈 번호를 적어요. `dev`에 머지되면 이슈가 자동으로 닫혀요. 여러 개면 줄을 나눠 적어요. |
| 📝 작업 내용                      | 무엇을 했는지 적어요. 예: 로그인 API 연동 / 입력값 검증 추가                                             |
| 💡 고민한 점 / 리뷰 포인트 (선택) | 왜 이렇게 만들었는지, 리뷰어가 특히 봐줬으면 하는 부분을 적어요.                                         |
| 🧪 확인 방법                      | 리뷰어가 따라 할 수 있게 적어요. 예: Swagger(`/docs`)에서 틀린 비밀번호로 로그인 → 401 응답 확인         |
| 📷 스크린샷 (선택)                | Swagger 응답이나 터미널 로그를 드래그해서 붙여넣어요.                                                    |
| ✔️ 체크리스트                     | 올리기 전에 하나씩 확인하고 `[ ]`를 `[x]`로 바꿔요.                                                      |

#### 체크리스트

- [ ] Assignees에 본인 지정
- [ ] Reviewers에 팀원 지정
- [ ] `uv run uvicorn main:app --app-dir src --reload`로 실행해서 동작 확인
- [ ] 패키지를 추가했다면 `pyproject.toml`, `uv.lock` 함께 커밋
- [ ] `.venv`, `__pycache__`, `.env`가 커밋에 없는지 확인
- [ ] 디버깅용 `print()`, 불필요한 주석 삭제

### 5. 리뷰와 머지

1. 리뷰어가 코멘트를 남기면 같은 브랜치에서 수정하고 다시 push하세요. PR에 자동으로 반영돼요.
2. 승인(Approve)을 받으면 **Merge pull request**로 `dev`에 합쳐요.
3. 머지 후 `close #번호`로 연결한 이슈가 자동으로 닫혔는지 확인해요.
4. 다 쓴 브랜치는 정리해요.

```bash
git switch dev
git pull origin dev
git branch -d feat/12-email-login # 로컬 브랜치 삭제
```

<br>

## 🐍 Python · uv 규칙

| 상황                              | 할 일                                                                            |
| --------------------------------- | -------------------------------------------------------------------------------- |
| 처음 clone 했을 때 / pull 받은 후 | `uv sync`로 패키지 설치                                                          |
| 패키지를 새로 추가할 때           | `uv add 패키지명` → `pyproject.toml`, `uv.lock` 둘 다 커밋 (`chore` 이슈로 등록) |
| 서버 실행                         | 프로젝트 루트에서 `uv run uvicorn main:app --app-dir src --reload`               |
| 커밋하면 안 되는 것               | `.venv/`, `__pycache__/`, `.env` (`.gitignore`에 등록)                           |
| 새 폴더를 만들 때                 | 빈 `__init__.py` 함께 만들기 (`ModuleNotFoundError` 방지)                        |

> ⚠️ `pip install`로 설치하지 마세요. `uv.lock`에 기록되지 않아서 다른 팀원 환경에서는 패키지가 없어요.

<br>

## 🐳 Docker 명령어

DB는 `docker-compose.yaml`로 각자 PC에 똑같이 띄워요. 접속 정보는 `.env.example`에 있어요.

| 상황                       | 명령어                                             | 설명                                                    |
| -------------------------- | -------------------------------------------------- | ------------------------------------------------------- |
| DB 켜기                    | `docker compose up -d`                             | 컨테이너가 없으면 만들고, 있으면 다시 켜요              |
| 상태 확인                  | `docker compose ps`                                | STATUS가 `Up`이면 정상                                  |
| 로그 보기                  | `docker compose logs -f db`                        | DB가 안 뜰 때 원인 확인 (`Ctrl + C`로 종료)             |
| 잠깐 끄기                  | `docker compose stop`                              | 컨테이너만 멈춰요. `docker compose start`로 다시 켜요   |
| 컨테이너 삭제              | `docker compose down`                              | 컨테이너는 지우지만 **데이터는 남아요**                 |
| DB 초기화                  | `docker compose down -v`                           | 컨테이너와 **데이터까지 전부 삭제**해요                 |
| DB 직접 접속               | `docker compose exec db psql -U admin -d karakpe`  | SQL로 테이블 확인 (`\dt` 테이블 목록, `\q` 종료)        |

> 💡 데이터는 `pgdata` 볼륨에 저장돼서 컨테이너를 껐다 켜거나 `down` 해도 그대로 남아요.
>
> ⚠️ `down -v`는 DB 데이터가 전부 지워져요. `docker-compose.yaml`의 유저·비밀번호·DB 이름을 바꿨을 때처럼 DB를 처음부터 다시 만들어야 할 때만 쓰세요.
>
> 💡 테이블은 Docker가 아니라 서버 코드(SQLAlchemy)가 만들어요. 컨테이너가 처음 뜨면 빈 `karakpe` DB만 있어요.
