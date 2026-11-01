# 04b API

이 문서는 croScan 서버([`server/app.py`](../server/app.py))의 HTTP 끝점(서버가 요청을 받는 주소)을 모두 적습니다. 직접 정의한 HTTP 끝점은 총 61개입니다. `/api/…`가 60개이고 첫 화면 `/`가 1개입니다. `/static` 마운트는 이 수에 넣지 않았습니다. 끝점은 영역별로 묶었습니다. 끝점마다 하는 일, 주요 입력·출력, 부르는 화면 코드, 권한을 적었습니다.

**이 문서에서 알 수 있는 것**
- 끝점마다 무엇을 하고 무엇을 주고받는지
- [`web/app.js`](../web/app.js)의 어느 함수가 그 끝점을 부르는지
- `CROSCAN_AUTH=proxy`일 때 누가 어떤 끝점을 쓸 수 있는지
- 개정 번호(revision)와 오류 코드를 어떻게 다루는지

## 목차
1. [공통 규칙](#1-공통-규칙)
2. [문서 업로드·판독](#2-문서-업로드판독)
3. [반장 대화](#3-반장-대화)
4. [체크리스트](#4-체크리스트)
5. [제출](#5-제출)
6. [안전관리자](#6-안전관리자)
7. [근거·설명](#7-근거설명)
8. [QA·운영](#8-qa운영)
9. [시험](#9-시험)
10. [한계와 주의](#10-한계와-주의)

---

## 1. 공통 규칙

### 1.1 권한 (`CROSCAN_AUTH`)
- 기본값은 `demo`입니다. `demo`는 로그인 프록시 검사를 하지 않습니다. 다만 QA 목록·첨부 조회·처리 표시는 `demo`에서도 따로 `X-QA-Token`이 필요합니다(아래 「QA 목록」). 안전관리자 화면에는 「시연 모드 · 인증 없음」이 뜹니다(화면이 `/api/health`의 `auth` 값을 보고 판단).
- `proxy`이면 서버가 두 헤더를 보고 요청을 막습니다. 두 헤더는 회사 로그인 프록시가 넣습니다. 사용자 헤더는 `x-croscan-user`, 역할 헤더는 `x-croscan-role`입니다(환경 변수 `CROSCAN_USER_HEADER`·`CROSCAN_ROLE_HEADER`로 바꿀 수 있음). 검사하는 미들웨어는 `_gate()`이고, 규칙은 `_needs()`에 있습니다.
- `demo`·`proxy`가 아닌 값이면 서버가 시작하지 않습니다.

| 경로 | proxy일 때 필요한 것 | 거절 |
|---|---|---|
| `/api/safety/…`, `/api/knowledge/…` | 역할 `manager` (「안전관리자」) | 역할 없음 401, 다른 역할 403 |
| 그 밖의 `/api/…` (`/api/health` 제외) | 역할 `manager` 또는 `foreman`, 그리고 사용자 헤더 | 역할 없음·사용자 헤더 없음 401, `manager`·`foreman` 밖의 역할 403 |
| `/api/health`, `/`, `/static/…` | 없음 | — |

서버는 안에서 세 가지를 더 확인합니다.
- **세션 주인**: 세션은 만든 사용자의 것입니다. 다른 반장의 세션은 「없는 세션」(404 `session_missing`)으로 보입니다. 안전관리자는 모든 세션을 봅니다([`store.py`](../server/store.py) `_session()`).
- **제출 PDF**: 반장은 자기 제출본만 받습니다. 아니면 404입니다(`submitted_file()`).
- **QA 목록**: `X-QA-Token` 헤더가 환경 변수 `QA_TOKEN`과 같아야 합니다(`_qa_auth()`). 이 검사는 proxy 권한 검사와 따로 합니다.

### 1.2 개정 번호와 오류 모양
- 검토 세션을 바꾸는 요청은 브라우저가 마지막으로 본 `expected_revision`을 함께 보냅니다.
- 개정 번호가 없으면 428 `revision_required`, 낡았으면 409 `stale_revision`입니다([`store.py`](../server/store.py) `_sync()`·`current()`).
- 세션 오류는 `{"detail": {"code", "message", …}}` 모양입니다(`_store_error()`).
- 화면의 `sessionRead()`가 개정 번호 때문에 409·428(`stale_revision`·`revision_required`)을 받을 때가 있습니다. 그러면 `serverState()`로 세션을 다시 읽고 한 번 더 보냅니다.
- `sessionPost()`는 세션 없음(404 `session_missing`)이나 낡은 개정(409 `stale_revision`)이면 최대 두 번 다시 보냅니다. 428은 자동으로 다시 보내지 않습니다.
- 질문 횟수 관련 409 코드: `budget`(12회), `clarify`(다시 묻기 3회), `close_once`, `closed`, `reserved`([`store.py`](../server/store.py) `issue()`).

### 1.3 공통 입력 모양
- `fields`: `/api/parse`가 돌려준 양식 칸. `{"p1.permit_no": {name, type, value, page, …}}`.
- `answers`: `[{qid, choice, value, q}]`. `q`는 물은 질문 그대로입니다. 서버는 질문·보기·값·시각만 받습니다. 브라우저가 「읽었다」고 하는 값은 받지 않습니다(`_answers()`, `_calc_answers()`).
- `session_id`: `/api/dialogues`가 준 세션 id.

---

## 2. 문서 업로드·판독

| 메서드 · 경로 | 하는 일 | 주요 입력 → 출력 | 부르는 곳 |
|---|---|---|---|
| `GET /api/kinds` | 허가서 5종 목록 | → `[{id, label, title}]` | `web/app.js` 초기화 코드의 `fetch("/api/kinds")`(함수 밖) |
| `POST /api/parse` | 허가서 PDF 판독 | multipart `file`, `kind`(종류 id) → NDJSON 줄(한 줄에 JSON 하나): `{step: open·odl·map·review·done·error, msg, t}`, 마지막 `done`에 `doc`(쪽·칸·`fields`·`findings`) | `parseRequest()` |
| `POST /api/review` | 칸 값 규칙 검사 | `{fields}` → `[{page, keys, kind, msg}]` | `scheduleReview()` |
| `POST /api/workplans` | 작업계획서 PDF 여러 개 판독 | multipart `files` → NDJSON 진행 줄, 그다음 계획서 기록. 디스크 부족 507 | `planRequest()` |
| `POST /api/workplans/{token}/prepare` | 계획서를 미리 읽어 모르는 칸 이름의 연결 제안을 만듦(모델, 미리 하는 일) | `{idx, session_id}` → `{plans}`, 밀리면 `why: "preempted"` | `wpPrepare()` |
| `POST /api/workplans/{token}/maps` | 「이 칸은 그 항목이다/아니다」 확인 저장 | `{plan, label, key, accept}` → `{maps, plan}` | `wpMapBox()` |
| `POST /api/workplans/{token}/edits` | 화면에서 고친 계획서 값 저장 | `{edits: {계획서 번호: {칸: 값}}}` → `{saved}` | `saveNow()` |
| `GET /api/workplans/{token}/edits` | 저장한 고친 값 읽기 | → 고친 값 | 화면은 부르지 않음 |
| `GET /api/workplans/{token}/plan/{i}.pdf` | 고친 계획서 하나를 PDF로 | → PDF(내려받기) | `downloadPlans()` |
| `GET /api/workplans/{token}/all.pdf` | 고친 계획서 전체를 PDF 하나로 | → PDF | `downloadPlans("all.pdf")` |
| `GET /api/workplans/{token}/{fi}/{page}.png` | 계획서 쪽 그림. `?bg=1`이면 값을 지운 바탕 | → PNG | 계획서 기록의 `image`·`background` 주소([`workplan.py`](../server/workplan.py)) |

- 계획서는 마지막 서버 접근 뒤 7일 동안 쓰지 않으면 정리 대상이 됩니다. 정리는 새 계획서를 올릴 때 합니다. 접근할 때마다 보관 기준 시간이 새로 잡힙니다([`workplan.py`](../server/workplan.py) `_touch()`·`_clean_cache()`).
- 정리된 계획서를 부르면 404 「작업계획서가 만료됐습니다」가 옵니다. 다만 `GET …/edits`는 404 대신 빈 객체를 돌려줍니다.
- 허가서에 글자 층이 없으면 `step: "error"`를 보냅니다.
- 계획서의 파일별 판독 오류는 `wp_file.error`와 마지막 `wp_done.files[].error`에 담습니다.

---

## 3. 반장 대화

### 3.1 세션과 질문

| 메서드 · 경로 | 하는 일 | 주요 입력 → 출력 | 부르는 곳 |
|---|---|---|---|
| `POST /api/dialogues` | 검토 세션 만들기 | → `{session_id, revision: 0}` | `ensureSession()` |
| `POST /api/dialogues/{sid}/state` | 세션의 답·제안·개정 번호 | `{fields}` → `store.state()` 결과 | `serverState()` |
| `POST /api/augment` | 질문·제안·반영 계획·별지를 다시 계산. 친 답을 세션에 기록 | `{fields, answers, session_id, expected_revision}` → `questions`, `proposals`, `effective`, `records`, `errors`, `revision`, `dropped`, `reflect`, `sheets`, `budget`, `unresolved`, `expired`, `protected` 등 | `refreshAug()` (`sessionPost`) |
| `POST /api/dialogues/{sid}/ask` | 질문을 지금 보여 준다고 알림. 횟수를 셈 | `{what: question·retry·card·link·close, qid, q, fields}` → `{key, used, max, again}`. 한도 넘으면 409 | `issueAsk()` |

- `what`이 `retry`·`card`·`link`이거나 AI 질문이면, 서버는 아직 묻지 않은 규칙 질문 몫을 남겨 둡니다(`_reserve()`). 횟수가 모자라면 409 `reserved`를 돌려줍니다.

### 3.2 AI 분석과 AI 읽기

| 메서드 · 경로 | 하는 일 | 주요 입력 → 출력 | 부르는 곳 |
|---|---|---|---|
| `POST /api/analyze` | 업로드 분석. 검토마다 한 번, 배경에서 | `{fields, answers, session_id, expected_revision, plans: {token, idx}}` → `{status: ok·none·fail·stale·late·done_before, found, why, plan, …}` | `startAnalyze()` |
| `POST /api/analyze/delta` | 허가서를 고친 뒤 바뀐 칸만 다시 분석 | `{fields, session_id, plans}` → `{status, found, changed, why}` | `scheduleDelta()` |
| `POST /api/understand` | 8자 이상 자유 답을 모델이 읽고 다른 열린 질문의 답을 제안 | `{fields, answers, qid, session_id, expected_revision}` → `{status, props, apart, revision, why}` | `readCard()` 안 `sessionPost` |
| `POST /api/understand/phrase` | 다음 질문 1~2개의 말투를 미리 고름 | `{fields, session_id, qids}` → `{status, phrased}` | `phraseAhead()` |
| `POST /api/understand/warm` | 보이는 질문을 모델 캐시에 미리 넣음(세션당 16회) | `{fields, qid, session_id}` → `{status}` | `warmAsk()` |
| `GET /api/dialogues/{sid}/stage?qid=` | 그 답의 읽기 단계: 대기 중·답 해석 중·결과 검사 중·끝 | → `{qid, stage}` | `aiTick()` |

- `/api/understand`는 브라우저 연결이 끊기면 모델 호출을 취소합니다. 마감은 60초입니다(`CROSCAN_MEASURE=1`일 때만 바꿀 수 있음).
- 「없음·안 함」처럼 위험 신호를 낮추는 제안은 [`critique.py`](../server/critique.py)가 검사합니다. 통과하지 못하면 `apart`로 갑니다.

### 3.3 제안 확인

| 메서드 · 경로 | 하는 일 | 주요 입력 → 출력 | 부르는 곳 |
|---|---|---|---|
| `POST /api/dialogues/{sid}/confirm` | 「AI 읽음」 카드 확인. 카드가 그 뒤 바뀌었으면 409 | `{action_id, adopt, reject, withdraw, fields, displayed_digest, expected_revision}`. 해시·개정 번호가 없으면 422 | `readCard()` 안 `decide()` |
| `POST /api/dialogues/{sid}/decide` | 같은 처리. 해시·개정 번호를 꼭 요구하지 않음 | 위와 같음 | `decide()` (보인 카드가 없을 때) |

- 확인·거절된 읽기는 사례 후보로도 기록됩니다([`cases.py`](../server/cases.py) `record()`). 이 기록이 실패해도 확인은 그대로입니다.

### 3.4 작업계획서 연결

| 메서드 · 경로 | 하는 일 | 주요 입력 → 출력 | 부르는 곳 |
|---|---|---|---|
| `POST /api/dialogues/{sid}/link` | 확정한 계획서 가운데 같은 작업 후보 제안(모델) | `{fields, plans: {token, idx}}` → `{status, links, why}` | `suggestLinks()` |
| `POST /api/dialogues/{sid}/link/confirm` | 반장의 「같은 작업으로 연결」·「아님」 저장 | `{plan, token, title, rel, accept, evidence, digest, imports}` → `{ok, links}` | `suggestLinks()`, `checkLinks()` |
| `POST /api/dialogues/{sid}/links/check` | 연결한 뒤 계획서가 고쳐졌는지 | → `{links: [{…, digest_now, expired, gone}]}` | `checkLinks()` |

### 3.5 기록 보기 (화면은 부르지 않음)

| 메서드 · 경로 | 하는 일 | 부르는 곳 |
|---|---|---|
| `GET /api/dialogues/{sid}` | 서버가 가진 검토 전체: 답·읽기·사실·횟수·작업·이벤트·확인 기록 | [`tools/check_dialogue_api.py`](../tools/check_dialogue_api.py) |
| `POST /api/dialogues/{sid}/events` | 정정·철회·메모 이벤트 기록. 같은 `action_id`는 한 번만 | 같은 시험 |
| `GET /api/jobs/{sid}~{kind}` | 검토의 작업 하나(상태·시각·모델 호출 수) | 같은 시험 |

---

## 4. 체크리스트

| 메서드 · 경로 | 하는 일 | 주요 입력 → 출력 | 부르는 곳 |
|---|---|---|---|
| `POST /api/checklist` | 허가서와 답만으로 위험 체크리스트 초안 | `{fields, answers, session_id, expected_revision}` → `checklist.draft()` 결과(`permits[].items[]`) | `openChecklist()` |
| `POST /api/checklist/ai-suggest` | 다른 종류의 카탈로그 항목을 「넣기」 후보로 제안하고, 기본 항목마다 근거·상충 표시(`marks`)를 붙임(모델). 세션 없으면 `none` | 위 + `keep`(넣은 AI 항목) → `{status, items, …}` | `ckAiAhead()`, `ckAiLoad()` |
| `POST /api/checklist/pdf` | 반장이 확인한 체크리스트의 미리 보기 PDF | `{fields, checklist, answers, session_id, expected_revision}` → PDF | `#ck-pdf` 단추 |

- 세 끝점은 저장된 답을 읽기만 합니다(`write=False`). 답을 새로 기록하지 않습니다.
- 다만 `ai-suggest`는 모델 호출 횟수를 늘리고, 작업 결과를 세션에 저장합니다([`checkai.py`](../server/checkai.py)).
- 체크리스트 AI는 추가 항목 후보와 기존 항목의 근거·상충 표시를 제안만 합니다. 반장의 선택값은 바꾸지 않습니다.
- 「해당 없음」으로 고른 항목에 해당 근거 표시가 나오면, 화면이 그 항목을 다시 확인하라고 돌려놓습니다(`ckTakeAi()`). 제출 때 서버도 같은 것을 검사합니다.
- PDF는 서버의 기본 목록에 반장의 선택을 넣어 만듭니다. 그래서 기본 항목이 빠질 수 없습니다(`checklist.merge()`).

---

## 5. 제출

| 메서드 · 경로 | 하는 일 | 주요 입력 → 출력 | 부르는 곳 |
|---|---|---|---|
| `POST /api/reflect/preview` | 제출 전 확인 창. 반영본 쪽을 PNG로 | multipart `file`(원본 PDF), `payload`(JSON: fields·answers·session_id·expected_revision) → `{pages, reflect}` | `reflectPreview()` (`sessionRead`) |
| `POST /api/submissions` | 제출 스냅숏을 한 번 만듦 | multipart `file`, `payload`(fields·session_id·expected_revision·checklist·plans) → `{id, created, digest, again, manager, summary}` | `sendFinalOnce()` |
| `GET /api/submissions/{id}/{name}.pdf` | 제출 때 그린 문서. `name`은 `permit`·`checklist`·`plans` | → PDF. 제출 기록이 없으면 404(보관 정리로 기록까지 지워진 경우도 404). 기록은 있는데 PDF 파일이 없으면 410 | `permitPdf()`, `checklistPdf()`, `sendFinalOnce()`, `sfOutside()`, `sfSubHtml()`, `outFiles()` |
| `POST /api/submit` | 옛 방식: 원본 + 추가검토서 PDF를 바로 돌려줌. 저장하지 않음 | multipart `file`, `payload` → PDF | 화면은 부르지 않음. [`tools/check_checklist.py`](../tools/check_checklist.py) |

제출하려면 체크리스트의 모든 기본 항목에서 해당 여부를 확인해야 합니다. 「해당」인 항목은 준비할 안전조치도 따로 확인해야 합니다([`submissions.py`](../server/submissions.py) `confirm_checklist()`).

`/api/submissions`에서 생기는 409:
- 해당 여부나 안전조치를 확인하지 않은 항목이 있음(`checklist_left`)
- 반장이 고른 뒤 근거가 바뀐 항목, 또는 해당 근거가 있는데 「해당 없음」으로 고른 항목(`checklist_changed`)
- 넣은 AI 항목의 작업 내용이 바뀜(`checklist_changed`)
- 낡은 개정 번호(`stale_revision`)

허가서가 두 건 이상이면 400 「허가서 한 건씩 제출합니다」를 돌려줍니다.

---

## 6. 안전관리자

이 영역의 끝점은 모두 `/api/safety/…`입니다. proxy일 때는 역할 `manager`만 씁니다. 시연 DB를 읽어야 하는 끝점은 DB가 없으면 404를 돌려줍니다. `/api/safety/submissions`는 예외입니다. 시연 DB가 없어도 저장된 제출 목록을 돌려줍니다.

| 메서드 · 경로 | 하는 일 | 주요 입력 → 출력 | 부르는 곳 |
|---|---|---|---|
| `GET /api/safety/overview` | 그날 서류 목록(허가서·계획서). 정답 자료는 내보내지 않음 | → `{date, factory, bays, cols, permits, plans}` | `sfLoad()` |
| `GET /api/safety/submissions` | 허가번호별 최신 제출본. 그날 목록에 없는 제출은 따로 | → `{허가번호: 요약, _outside, _versions, …}` | `sfSubs()`, `outNow()` |
| `POST /api/safety/detect` | 쌍작업 위험탐지. 서류 판정 + 제출본 판정 + `floor` | → `{date, stats, pairs, near, rules, levels, hybrid}` | `sfDetect()` |
| `GET /api/safety/doc/{id}` | 서류 하나(허가서: 양식·답·체크리스트, 계획서: 항목) | → 서류 상세 | `sfOpen()`, `outNow()` |
| `GET /api/safety/pdf/{id}/{part}.pdf` | `original`·`full`(허가서+추가검토서)·`checklist` | → PDF | `sfPdf`, `outFiles()` |
| `GET /api/safety/doc-summaries` | 문서별 관리자 요약과 허가 검토 신호 | → `docsum.build()` 결과 | `sfSumLoad()` |
| `GET /api/safety/hold-questions` | 판정보류 쌍의 담당별 질문 문안 | → `{date, docs: [{…, questions, message}], count}` | `sfHoldLoad()` |
| `POST /api/safety/hold-questions/mark` | 질문 표시: 미전달 → 전달함 → 응답 받음 | `{key, state}` → 지금의 질문 | `sfHoldMark()` |
| `POST /api/safety/pair-review` | 규칙이 아무것도 띄우지 않은 쌍의 「AI 검토 권장」(규칙 판정 아님) | `{a, b}` → 검토 결과. 가깝지 않은 쌍은 422 | `sfReview()` |
| `GET /api/safety/pair-reviews` | AI 검토 권장 목록과 상태 | → `pairreview.listing()` 결과 | `sfRvLoad()` |
| `POST /api/safety/coord-note` | 협조 문자의 「협의할 점」 한 문장(모델이 고르고 서버가 씀) | `{key}` → `{status, …}` | `mgNote()` |
| `POST /api/safety/post-draft` | 게시 서류 「우리 반이 할 일」 문안 초안 | `{key, doc}` → 초안 | `postAiGo()` |
| `POST /api/safety/sheet.pdf` | 현장 게시용(`post`) 또는 일상작업반 전달문(`notice`) PDF | `{doc_id, kind, sheet}` → PDF | `postPdf()`, `outFiles()` |

- 판정 결과는 메모리에 둡니다. 시연 DB나 그날 제출본이 바뀔 때만 다시 계산합니다(`_detect()`).
- 「전달함」 표시는 그 허가서 검토의 질문 횟수에 들어갑니다. 횟수가 없으면 표시는 그대로 남기고, 횟수가 없었다는 사실을 적습니다([`holdq.py`](../server/holdq.py) `_charge()`).
- croScan은 문자나 질문을 보내지 않습니다. 문안만 만듭니다.

---

## 7. 근거·설명

| 메서드 · 경로 | 하는 일 | 주요 입력 → 출력 | 부르는 곳 | 권한(proxy) |
|---|---|---|---|---|
| `POST /api/safety/explain` | 쌍 판정의 「왜?」. 정해진 질문 3개(`seq`·`used`·`defer`)는 바로 답함. 자기 말 질문(200자 안)은 모델을 거쳐 답함 | `{key, which}` 또는 `{key, question}` → `{status, question, frame, questions, verify}` | `sfWhyAsk()` | manager |
| `POST /api/explanations/query` | 여러 설명을 받는 하나의 입구: 쌍·질문·체크리스트 항목·반영본 변경·개정 | `{target: {kind: pair·question·checklist·change·revision, …}, fields, session_id, which, question}` → `{status, kind, frame, verify}` | `xWhy()` | `kind: pair`는 manager만(아니면 403). 나머지 `kind`는 manager 또는 foreman과 사용자 헤더 |
| `GET /api/knowledge/map` | 근거 지도: 체크리스트 항목·쌍 규칙의 근거 | → `evidencemap.build()` 결과 | `sfEvidence()`, [`web/evidence.js`](../web/evidence.js) | manager |
| `GET /api/knowledge/search` | 근거 자료 검색 | `?q=&k=(1~12)&authority=` → `{query, hits}` | 화면은 부르지 않음. [`tools/check_access.py`](../tools/check_access.py) | manager |

croScan은 서버가 만든 주장으로만 설명을 짭니다(판단 → 사용한 사실 → 적용한 규칙 → 아직 확인할 것 → 근거 보기). 일정을 옮기면 어떻게 되느냐는 질문은 계산하지 않습니다([`explain.py`](../server/explain.py)).

---

## 8. QA·운영

| 메서드 · 경로 | 하는 일 | 주요 입력 → 출력 | 부르는 곳 | 권한 |
|---|---|---|---|---|
| `POST /api/qa` | QA 신고(첨부·설명·화면 상태) | multipart `text`, `author`, `context`(JSON 객체), `files` → `{id}`. 디스크 부족 507 | `#qa-form` 보내기 | proxy일 때 user |
| `GET /api/qa` | 신고 목록. `?handled=false`는 남은 것만 | → 목록 | [`tools/qa_pull.py`](../tools/qa_pull.py) | `X-QA-Token` |
| `GET /api/qa/{id}/file/{n}` | 신고 첨부 파일 | → 파일 | `qa_pull.py` | `X-QA-Token` |
| `POST /api/qa/{id}/handled` | 처리 표시 | `{handled, note}` → `{ok}` | `qa_pull.py` | `X-QA-Token` |
| `GET /api/health` | 살아 있는지. Docker HEALTHCHECK가 부름 | → `{ok, auth}` | 화면 끝(시연 모드 표시), [`Dockerfile`](../Dockerfile) | 열림 |
| `GET /api/llm` | 모델 서버가 떠 있는지 | → `{ok, model, status, served}` | 화면은 부르지 않음 | user |
| `POST /api/chat` | 옛 자유 대화. 기본으로 꺼져 410 | `CROSCAN_LEGACY_CHAT=1`일 때만 스트림 | 화면은 부르지 않음 | user |
| `GET /` | 첫 화면 `web/index.html` | → HTML | 브라우저 | 열림 |
| `/static/…` | `web/` 폴더의 파일 | → 파일 | 브라우저 | 열림 |

서버가 시작할 때 `store.recover()`가 끝나지 않은 작업을 정리합니다(`@app.on_event("startup")`).

---

## 9. 시험

| 무엇 | 시험 |
|---|---|
| 세션·개정 번호·질문 횟수·작업 끝점 | [`tools/check_dialogue_api.py`](../tools/check_dialogue_api.py), [`tools/check_store.py`](../tools/check_store.py), [`tools/check_delta_api.py`](../tools/check_delta_api.py) |
| proxy 권한과 프록시 설정 | [`tools/check_access.py`](../tools/check_access.py), [`tools/check_proxy_headers.py`](../tools/check_proxy_headers.py) |
| 제출 | [`tools/check_submissions.py`](../tools/check_submissions.py), [`tools/check_submit_link.py`](../tools/check_submit_link.py) |
| 설명 | [`tools/check_explain.py`](../tools/check_explain.py) |

---

## 10. 한계와 주의

- **화면이 부르지 않는 끝점**이 있습니다: `GET /api/dialogues/{sid}`, `/events`, `/api/jobs/…`, `GET /api/workplans/{token}/edits`, `/api/submit`, `/api/llm`, `/api/chat`, `/api/knowledge/search`. 시험·도구용이거나 옛 기능입니다.
- **계획서 `token`은 사용자에 묶이지 않습니다.** proxy일 때도 로그인한 사용자가 `token`을 알면 그 계획서를 읽을 수 있습니다. 고친 값(`/edits`)과 칸 연결(`/maps`)도 저장할 수 있습니다. 서버는 주인을 검사하지 않습니다.
- **`/api/explanations/query`의 `kind: "pair"`.** 이 경로는 `/api/safety/`로 시작하지 않습니다. 그래서 `_gate`가 막지 못했습니다. 2026-11-01에 끝점 안을 고쳤습니다. 이제 proxy일 때 안전관리자가 아니면 403을 돌려줍니다. `tools/check_access.py`에 시험도 더했습니다.
- croScan은 승인·일정·작업 차단을 하지 않습니다. 이 API의 어떤 끝점도 전산·결재로 보내지 않습니다.
