# croScan을 사내 로그인 뒤에 두기 (OIDC 프록시 예시)

회사 로그인 뒤에 croScan을 두는 예시 구성입니다. IdP는 사용자를 확인하는 회사 로그인 시스템입니다. OIDC는 IdP가 로그인 결과를 다른 프로그램에 전달하는 표준입니다. 실제 회사 IdP와 연결해 본 적은 없습니다.

**이 문서에서 알 수 있는 것**

- 프록시 구성과 역할별 접근 범위
- 이 예시를 띄우기 전에 준비할 것(앱 이미지, 모델 연결)
- 회사가 정해 줄 설정과 인증서
- 설정 검사와 실제 연결 시험

**목차**

[어떻게 막나](#어떻게-막나) · [구성](#구성) · [띄우기 전에](#띄우기-전에) · [회사가 정해 줄 것](#회사가-정해-줄-것-이-저장소에서-할-수-없는-것) · [확인](#확인)

## 어떻게 막나

croScan은 계정을 갖지 않습니다. 회사의 로그인 시스템(IdP)이 사용자를 확인합니다. 그 앞에 놓인 프록시(요청을 대신 받아 넘겨 주는 서버)가 두 헤더만 croScan에 넘깁니다. 하나는 누구인지(`X-Croscan-User`), 다른 하나는 역할(`X-Croscan-Role`: `manager` 또는 `foreman`)입니다.

croScan은 `CROSCAN_AUTH=proxy`로 실행합니다. 그러면 역할과 사용자에 따라 다음처럼 막습니다(`server/app.py` `_gate`).

| 요청 | 반장(foreman) | 안전관리자(manager) | 로그인 없음 |
|---|---|---|---|
| 반장 검토(`/api/augment`, `/api/dialogues/*` 등) | 자기 세션만(아래 예외) | 모두 | 401 |
| 안전관리자 화면(`/api/safety/*`), 근거 지도(`/api/knowledge/*`) | 403 | 열림 | 401 |
| 제출 문서(`/api/submissions/{id}/*.pdf`) | 자기 제출본만 | 모두 | 401 |
| `/api/health` | 열림 | 열림 | 열림 |

- 소유자가 기록된 검토 세션은 그 반장만 열 수 있습니다. 안전관리자는 모두 열 수 있습니다.
- 소유자가 없는 기존 세션(시연 모드에서 만든 것 등)에는 이 소유권 제한이 없습니다. 작업계획서 토큰(올린 계획서마다 주는 임의 번호)에도 없습니다. 로그인한 사용자라면 토큰을 아는 사람이 열 수 있습니다.

## 구성
- `docker-compose.yml`: 서비스는 셋입니다. croScan은 바깥에 열지 않습니다(`expose`만).
  - `croscan`: 앱
  - `oauth2-proxy`: 로그인 처리
  - `nginx`: 443 포트만 바깥에 엽니다.
- `nginx.conf`: 요청마다 `auth_request`로 로그인을 확인합니다. 그리고 IdP 그룹을 역할로 바꿔 헤더에 넣습니다.
  - 그룹 이름은 `croscan-manager`·`croscan-foreman`입니다.
  - 브라우저가 같은 이름의 헤더를 보내도 nginx가 덮어씁니다. 그래서 사용자가 스스로 안전관리자 역할을 가질 수 없습니다.
  - 요청 본문은 64MiB로 제한합니다(`client_max_body_size 64m`). 이보다 큰 업로드는 프록시에서 거절됩니다.
- `oauth2-proxy.env.example`: IdP 값의 틀입니다. 실제 값(클라이언트 비밀, 쿠키 비밀)은 이 저장소에 두지 않습니다.

## 띄우기 전에
- 이 구성은 인증 프록시 예시입니다. 앱 이미지는 빌드하지 않습니다. 그러니 먼저 저장소 루트에서 `docker compose build web`으로 `croscan:latest` 이미지를 만듭니다.
- 이 구성에는 언어 모델 서비스(`llm`)가 없습니다. 모델을 쓰려면 앱이 닿을 수 있는 주소를 `LLM_URL`에 적습니다. 필요한 네트워크도 연결합니다. 모델이 없어도 규칙 질문과 판정은 돕니다.
- 데이터는 `CROSCAN_DATA_DIR`로 지정한 폴더에 남습니다. 지정하지 않으면 `croscan_data` 볼륨에 남습니다.

## 회사가 정해 줄 것 (이 저장소에서 할 수 없는 것)
- IdP 주소, 클라이언트 등록, 그룹 이름과 소속 관리
- 호스트 이름과 TLS 인증서
- 사용자 식별자로 `preferred_username` 말고 다른 값(사번 등)을 쓸 때: `OAUTH2_PROXY_USER_ID_CLAIM`을 바꿉니다. nginx는 그 값을 늘 같은 이름 `X-Croscan-User`로 넘깁니다. 그래서 앱 설정은 바꾸지 않아도 됩니다.
- 앱으로 보내는 헤더 이름까지 바꿀 때만: nginx의 `proxy_set_header`와 앱의 `CROSCAN_USER_HEADER`(역할은 `CROSCAN_ROLE_HEADER`)를 함께 바꿉니다.

## 확인
붙인 뒤 `python tools/check_proxy_headers.py --conf deploy/oidc-proxy/nginx.conf`로 설정을 검사합니다. 이어서 `--url https://croscan.example.internal --app http://<서버>:8765`로 실제 연결을 시험합니다.

실제 연결 시험에서 확인하는 것:
- 로그인 없이 열리지 않음
- 헤더를 위조해도 열리지 않음
- 앱 포트가 바깥에서 닿지 않음
