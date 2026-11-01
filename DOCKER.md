# croScan 도커 실행 안내

도커로 croScan을 띄우고 운영하는 방법을 적습니다. 날짜가 붙은 측정값은 그때의 기록입니다. 설정의 기준은 `Dockerfile`과 `docker-compose.yml`입니다.

**이 문서에서 알 수 있는 것**

- 이미지가 어떻게 짜여 있고 어떤 명령으로 띄우는지
- 언어 모델 파일을 어디에 두고 어떤 환경 변수로 지정하는지
- 데이터가 어디에 남고, 첫 실행 때 무엇을 확인하는지
- QA 보고를 받고 읽는 법
- 지금 서버 기록과 서버 사양

**목차**

[구성](#구성) · [실행](#실행-도커가-있는-서버에서) · [AI 모델](#ai-모델-라온-1-미니-프리뷰) · [환경변수](#환경변수) · [첫 실행 확인](#첫-실행-때-확인할-것) · [QA 보고](#qa-보고-화면-오른쪽-위-qa-버튼) · [서버 기록](#지금-서버-2026-10-27) · [서버 사양](#서버-사양-참고)

> 검증 기록 (2026-10-25): Ncloud 서버(Ubuntu 24.04, c2-g3: 2 vCPU·4GB, Docker 29.1 / Compose 2.40)에서 빌드하고 실행했습니다.
> - 빌드 시간: 1분 18초. 이미지 크기: 971MB.
> - 헬스체크(컨테이너가 살아 있는지 스스로 보는 검사): healthy.
> - 시연 PDF 5종(각 14.3MB)의 결과가 개발 PC와 같았습니다(값·지적 차이 0). 처리 시간은 한 건에 약 6초입니다.
> - 화면에서 업로드, 칸 배치, 수정까지 확인했습니다.
> - 이때 `docker-compose.yml`에서 `platform` 위치 오류(build 아래 → 서비스 아래)를 고쳤습니다.

## 구성

| 파일 | 역할 |
|---|---|
| `Dockerfile` | Python 3.12 + Java 17(JRE) 이미지. OpenDataLoader가 `java`로 jar를 실행하므로 Java가 있어야 합니다. 일반 사용자(uid 10001)로 실행하고, 헬스체크가 있습니다. |
| `docker-compose.yml` | `web`(croScan), 선택으로 `llm`(로컬 모델 라온-1 미니 프리뷰, llama.cpp, `--profile ai`) |
| `llm/Dockerfile` | 크래프톤 llama.cpp 브랜치(고정 커밋)로 만든 llama-server. 모델 파일은 이미지에 넣지 않습니다 |
| `requirements.txt` | 개발 환경과 같은 패키지 버전 고정 |
| `.dockerignore` | `.env`, 생성 도구(`tools/`), 캐시는 이미지에 넣지 않습니다 |

이미지에는 `server/`와 `web/`만 들어갑니다. 샘플 PDF(`samples/`)는 넣지 않습니다. 허가서는 웹 화면에서 올립니다.

## 실행 (도커가 있는 서버에서)

```bash
docker compose up -d --build
```
→ `http://<서버주소>:8765`

- 바깥 포트를 바꾸려면 `CROSCAN_PORT=80 docker compose up -d --build`처럼 실행합니다.
- AI 모델(라온-1 미니 프리뷰, Apache 2.0)까지 띄우려면 먼저 아래 「AI 모델」 절을 따라 모델 파일을 둡니다. 그다음 `docker compose --profile ai up -d --build`를 실행합니다.
- 서버의 시스템 디스크는 10GB입니다. 다시 빌드할 때마다 빌드 캐시가 쌓여 디스크가 금방 찹니다. 다시 빌드한 뒤에는 `docker builder prune -f`로 캐시를 비웁니다(실행 중인 이미지는 지우지 않음).
- 서버에서 시험하려면 `sh tools/cloud_test.sh`를 씁니다(임시 파일은 /data에 씁니다).

## AI 모델 (라온-1 미니 프리뷰)

- 모델 파일(GGUF: llama.cpp가 읽는 양자화 모델 파일)은 저장소와 이미지에 없습니다. 파일 이름, 받는 곳, 시험한 판(revision), 체크섬은 **팀 배포 자료에서 확인**합니다.
- 받은 파일은 서버의 `LLM_MODELS` 폴더(기본 `./models`)에 둡니다. 파일 이름은 `LLM_GGUF`로 지정합니다. 기본값과 다르면 compose 파일 옆 `.env`에 적습니다.
- 받은 뒤에는 `sha256sum`으로 팀 배포 자료의 체크섬과 맞는지 확인합니다. 프리뷰 모델이라 원래 저장소의 최신판이 바뀔 수 있습니다. 그러니 시험한 판을 받습니다.
- llama.cpp 이미지(`llm/Dockerfile`)는 크래프톤 브랜치 고정 커밋(`fb89566`)을 `GGML_NATIVE=OFF`·`GGML_CPU_ALL_VARIANTS=ON`으로 빌드합니다. CPU마다 가장 빠른 코드를 실행할 때 고릅니다. 그래서 다른 CPU 서버로 옮겨도 다시 빌드하지 않아도 됩니다(다시 빌드: `docker compose --profile ai build llm`).
- 메모리: 모델만 약 20GB. 실행 서버는 32GB 이상.
- 2026-10-27 Ncloud s8-g3(8 vCPU, 32GB, CPU만)에서 잰 속도: 프롬프트 초당 32토큰, 답 초당 6.7토큰, 짧은 과제 한 번에 40~60초(생각하기 포함). 서비스에 쓰기에는 느려서 GPU(L4 24GB, `gp1l8-g3`)로 옮기기로 했습니다. 그때 `llm/Dockerfile`을 CUDA 빌드로 바꿉니다.
- DFlash2 투기적 디코딩(작은 모델이 먼저 쓰고 큰 모델이 검사하는 가속법)은 CPU에서 오히려 느렸습니다(초당 4.3토큰). 그래서 끄고 씁니다.
- 속도 재기: 서버에서 `python3 bench_models.py http://127.0.0.1:8000`.

## 환경변수

compose 파일 옆 `.env`에 적습니다. 값(특히 `QA_TOKEN`)은 저장소에 적지 않습니다.

| 변수 | 기본값 | 뜻 |
|---|---|---|
| `CROSCAN_PORT` | 8765 | 서버 바깥 포트 |
| `CROSCAN_DATA_DIR` | 없으면 Compose 프로젝트의 `qa` 볼륨 | 웹 데이터를 둘 서버 폴더 |
| `CROSCAN_AUTH` | `demo` | `demo`(시연 모드) 또는 `proxy`(사내 로그인 뒤) |
| `QA_TOKEN` | 비어 있음(아무도 못 읽음) | QA 보고 읽기 열쇠 |
| `LLM_MODELS` | `./models` | 모델 파일 폴더 |
| `LLM_GGUF` | 팀 배포 자료에서 확인 | 모델 파일 이름 |
| `LLM_CTX` | 16384 | 문맥 길이(토큰) |
| `LLM_PARALLEL` | 1 | 모델 서버의 동시 처리 수 |
| `LLM_THINK_BUDGET` | -1(무제한) | 모델 서버의 생각 길이 상한 |

- `LLM_THREADS`는 읽지 않습니다. 스레드 수는 llama.cpp가 서버의 물리 코어 수로 정합니다.
- 웹 컨테이너의 `PORT`(8765), `LLM_URL`(`http://llm:8000/v1/chat/completions`), `LLM_MODEL`(`Raon-1-mini-preview`)은 compose 파일에 값이 고정돼 있습니다. `.env`만 바꿔서는 바뀌지 않습니다.
- 앱이 읽는 다른 변수(`CROSCAN_DISK_FLOOR_GB`, `CROSCAN_SITE_SHIFT` 등)는 compose의 `environment`에 항목을 더해야 컨테이너에 전달됩니다. 전체 목록은 [12 배포와 운영 §9](docs/12_배포와_운영.md#9-환경-변수)에 있습니다.

## 첫 실행 때 확인할 것

1. `docker compose ps`에서 `web`이 `healthy`인지 봅니다(헬스체크 주소 `/api/health`).
2. 첫 화면에서 허가서 종류를 고르고 PDF(예: 이 PC의 `samples/시연/0614_중량물인양.pdf`)를 넣습니다. 「검토 시작」을 눌러 5단계가 모두 완료되는지 봅니다.
3. 로그(`docker compose logs web`)에 java 관련 오류가 없는지 봅니다.

## QA 보고 (화면 오른쪽 위 「QA」 버튼)

- 누구나 파일을 넣고 설명과 함께 보낼 수 있습니다. 파일은 캡처·이미지·PDF·워드·엑셀 등 모든 형식이 됩니다. Ctrl+V 붙여넣기, 끌어 놓기, 선택으로 넣습니다. 보낼 때 지금 화면 상태(파일 이름, 허가서 종류, 보기, 입력값, 답변, 남은 질문)도 같이 저장됩니다.
- 앱 자체에는 첨부 크기·개수 제한이 없습니다. 대신 남은 디스크가 `CROSCAN_DISK_FLOOR_GB`(기본 2GB)보다 적으면 저장을 멈춥니다. 이 하한 검사는 QA 첨부와 작업계획서를 저장할 때만 합니다. 사내 로그인 예시 프록시(`deploy/oidc-proxy/`)는 요청 본문을 64MiB로 제한합니다.
- 저장 위치: 컨테이너 `/app/data/qa.sqlite3`(보고 내용), `/app/data/qa_files/`(첨부 파일). `/app/data`는 `CROSCAN_DATA_DIR`로 지정한 서버 폴더입니다. 지정하지 않으면 Compose 프로젝트의 `qa` 볼륨입니다. 어느 쪽이든 다시 빌드해도 남습니다.
- 보고를 읽으려면 서버 환경 변수 `QA_TOKEN`과 같은 값을 `X-QA-Token` 요청 헤더로 보내야 합니다. 시연 모드(`demo`)에서도 같습니다. 서버에서는 `docker-compose.yml` 옆 `.env`에, 개발 PC에서는 저장소 루트의 `.env`에 같은 값을 둡니다.
- 가져오기: [`tools/qa_pull.py`](tools/qa_pull.py)는 저장소 루트의 `.env` 또는 환경 변수에서 `CROSCAN_URL`(서버 주소)과 `QA_TOKEN`을 읽습니다. `python tools/qa_pull.py`를 실행하면 `qa_inbox/<번호>/`에 `report.md`·첨부 파일·`context.json`이 생깁니다. 기본으로는 처리 안 된 것(`handled = false`)만 받습니다. 고친 뒤에는 `python tools/qa_pull.py --handled 번호 "메모"`로 처리 표시를 합니다.

## 지금 서버 (2026-10-27)

- Ncloud s8-g3(8 vCPU, 32GB, CPU만). 서버 주소는 팀 안에서만 나눕니다(저장소에 적지 않음). 80번 포트는 모두에게 열었습니다. 22번은 배포한 PC에만 열었습니다.
- 데이터 디스크 `croscan-data` 50GB(`/data`, 반납 보호 켬): `/data/app` = 웹앱 데이터(QA DB·첨부·작업계획서), `/data/models` = 모델 파일.
  서버를 지울 때는 이 디스크를 먼저 떼고 서버만 지웁니다. 새 서버에 붙이면 QA와 모델이 그대로 따라옵니다.
- 서버 `.env`: `QA_TOKEN`(값은 팀 배포 자료에서 확인), `CROSCAN_PORT=80`, `CROSCAN_DATA_DIR=/data/app`, `LLM_MODELS=/data/models`.
- 라온(CPU): 짧은 과제 약 44초, 허가서 첫 검토 채팅 약 66초. 생각 길이 제한(`LLM_THINK_BUDGET`)을 256으로 걸어도 빨라지지 않았습니다. 그래서 무제한(-1)으로 둡니다.

## 서버 사양 참고

- 메모리: 최소 2GB(웹만). AI 모델까지 켜면 32GB 이상.
- 디스크: 이미지 약 1GB. 모델 파일 약 20GB는 따로 둡니다(추가 디스크 40GB를 썼습니다).
- CPU: x86_64(amd64) 기준으로 빌드합니다.
