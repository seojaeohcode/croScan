# 구조와 설계 판단

```mermaid
flowchart LR
  A[계획서·허가서 PDF] --> B[판독·원문 보존]
  B --> C[누락 조건 질문]
  C --> D[AI 해석 제안]
  D --> E[작업반장 확인]
  E --> F[규칙 기반 위험 판정]
  F --> G[근거·미확인 조건]
  G --> H[사람의 협의·승인]
  H --> I[검토 서류·현장 게시물]
```

## 읽어볼 코드

| 설계 판단 | 구현 | 확인 방법 |
|---|---|---|
| AI 응답을 사실로 바로 채택하지 않음 | [`understand.py`](../server/understand.py), [`analyze.py`](../server/analyze.py) | 원문에 없는 인용·다른 팀 발언·잘못된 값 거절 |
| 늦은 응답이 최신 답을 덮어쓰지 않음 | [`store.py`](../server/store.py), [`web/app.js`](../web/app.js) | revision 누락·불일치, 중복 확인, 화면 상태 병합 검사 |
| 위험 근거와 미확인 조건을 분리 | [`pairs.py`](../server/pairs.py), [`pair_rules.json`](../server/pair_rules.json) | 합성 정답 위험쌍·근접 사례·보류 조건 대조 |
| 서류 생성 시 판단을 다시 바꾸지 않음 | [`submissions.py`](../server/submissions.py), [`addendum.py`](../server/addendum.py) | 확인한 버전·체크리스트 기준 검증, PDF 출력 검사 |
| 의견 수집부터 처리 결과까지 연결 | [`qa.py`](../server/qa.py), [`check_qa_board.py`](../tools/check_qa_board.py) | QA 토큰·중복 실행 요청·처리 상태 검사 |

## 실행 환경

- Python / FastAPI / SQLite / JavaScript / OpenDataLoader PDF / PyMuPDF.
- LLM: OpenAI 호환 API를 사용하는 별도 서버. 기본 설정은 Raon-1-mini-preview + llama.cpp입니다.
- 근거 검색·규칙 판정·AI 해석·사람 확인을 서로 다른 책임으로 나눴습니다.
- `LLM_URL`은 변경 가능합니다. 사내 배치는 가능한 구성이지, 모든 실행 환경에서 외부 전송이 불가능하다는 뜻은 아닙니다.

## 현재 시연판의 동작

- 인증 기본값 `demo`: 로컬에서 합성 자료로 사용합니다.
- `proxy`: 신뢰할 수 있는 게이트웨이가 설정한 사용자·역할 헤더를 검사합니다. 외부에서 앱으로 직접 접근하지 못하게 구성해야 합니다.
- 기본 제출본은 메모리에서 최근 6건만 유지합니다. 서버 재시작 시 사라지며 관리자 시연 자료에 합치지 않습니다.
- `CROSCAN_KEEP_SUBMISSIONS=1`: 제출본을 저장하고 관리자 목록에 연결하는 시험 모드입니다.
- QA·세션·업로드 자료는 `CROSCAN_DATA` 경로에 저장됩니다. 기본 제출본의 일시 보관과 구분합니다.
- QA 시작 요청은 작업을 기록하는 API입니다. 외부 자동 처리 도구가 없으면 요청만 생성되며, 자동 수정이 실행되지는 않습니다.
- [`qa_watch.py`](../tools/qa_watch.py)는 대기 중인 요청을 감지해 알리는 도구이고, [`qa_pull.py`](../tools/qa_pull.py)는 의견 조회·처리 상태 갱신 도구입니다. `qa_prompt.txt`는 당시 작업 지침을 보관한 데이터이며, 앱이 직접 실행하는 명령은 아닙니다.

## 운영 전 남은 일

- 실제 사내 SSO·결재·작업 데이터 연동과 역할별 접근 검증.
- 실자료의 개인정보·보관 정책, 파일 업로드 크기·요청 제한, 백업·관측 설정.
- 현장 담당자와 오경보·누락·판정 보류의 비용을 정하고 검증.

[전체 아키텍처](04_아키텍처.md) · [API](04b_API.md) · [배포](../DOCKER.md) · [평가](EVALUATION.md)
