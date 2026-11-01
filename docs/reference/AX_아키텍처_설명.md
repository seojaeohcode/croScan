# croScan AX 아키텍처 설명서

작성일: 2026-10-31

이 문서는 발표용 설명서다. **용어는 업계 문서나 논문에서 실제로 쓰는 말만 쓰고, 출처를 함께 적는다.** 각 용어는 croScan 코드 안에 대응하는 부분이 있다. 하지 않은 것(파인튜닝, 자율 에이전트, 자동 승인)은 쓰지 않는다. 수치는 서버 실측과 평가 결과만 쓴다.

---

## 1. 한 문장 요약

> **croScan은 뉴로-심볼릭(Neuro-Symbolic) 구조다. 생성형 AI(LLM)가 작업반장의 자유로운 말을 구조화하고, 규칙 기반 시스템이 위험을 판정한다.** AI의 출력은 가드레일(출력 검증)을 거쳐 제안으로만 나간다. 가드레일은 인용 구절, 숫자·ID, 일부 질문의 주제어를 검사한다. 의미가 맞는지는 사람이 확인해야 확정된다(인간 감독, Human Oversight).

이 결합은 흔히 「LLM이 제안하고, 규칙이 승인한다」는 말로 설명된다. 다만 표준 기법명이 아니라 설명 문구다. 안전이 중요한 분야에서 기호적(규칙) 계층이 가드레일과 추적 가능한 결정을 맡는 방식이다. [출처 1, 2]

```
반장의 말·서류
   │
   ▼
① 구조화 출력 기반 정보 추출 (Structured Outputs / Information Extraction)
   │   LLM이 JSON 스키마에 맞춰 「질문·보기·값·주체·시점·근거 인용」만 내놓는다
   ▼
② 출력 가드레일 · 근거성 검증 (Output Guardrails / Groundedness Check)
   │   인용 구절이 반장의 말에 있는지, 숫자·ID가 일치하는지 대조한다. 정정·추측·불분명한 말은 제안하지 않는다(기권, abstention)
   ▼
③ 검증 호출 (Verification, CRITIQUE)
   │   부정·관계 판독을 별도 호출로 다시 본다
   ▼
④ 인간 감독 (Human Oversight / Human-in-the-Loop)
   │   「이렇게 읽었는데 맞나요?」 카드. 반장이 확인·수정·제외한다
   ▼
⑤ 규칙 기반 판정 (Rule-based System)
   │   확정된 사실로 작업쌍 위험을 판정한다. 서류·확인 답변·제출본·규칙 판이 같으면 결과가 같다
   │   페일세이프(fail-safe): 모델이 실패하면 규칙만으로 진행하고, 통합 판정은 서류 기준 경보 하한을 유지한다
   ▼
⑥ 설명 가능성 (XAI)
       판정에 쓴 사실과 규칙을 보여 준다. 조문·사례는 확보·검수 상태(확인된 조문 / 인용만 / 검색 후보 / 예시)를 구분해 보여 준다
```

---

## 2. 왜 이 구조인가 (설계 근거)

| 질문 | 답 | 근거 |
|---|---|---|
| 왜 판정을 LLM에 맡기지 않나 | 안전 판정은 재현돼야 하고, 놓쳤을 때 책임 소재가 분명해야 한다. | 현장 사실: 승인은 생산부서 권한자, 안전은 검토·현장 확인 담당(현장 정정 D01). 기호적 계층은 추적 가능한 결정을 제공한다. [출처 1] |
| 왜 AI의 자기 검증만 믿지 않나 | 같은 모델이 자기 답을 검증하면 오히려 나빠지는 경우가 있다. 외부의 확실한 검증기를 둘 때 성능이 좋아진다는 연구가 있다. | Stechly 외(2024), 「On the Self-Verification Limitations of LLMs on Reasoning and Planning Tasks」. [출처 7] croScan은 결정적 검증기(가드레일)를 별도로 둔다. |
| 그럼 AI는 왜 필요한가 | 반장은 묻는 것만 답하지 않고 여러 정보를 섞어 말한다. 규칙만으로는 그 말을 다 읽지 못한다. | 자연어 1,200건(기대 정보 1,000개, 2026-10-31 코드): 규칙만 쓰면 285건, AI를 더하면 794건을 읽었다. |
| 왜 사람이 확인하나 | 고위험 AI는 사람이 출력을 무시하거나 뒤집을 수 있어야 하고, 자동화 편향(automation bias)을 알아챌 수 있어야 한다. | EU AI Act 제14조(Human oversight). [출처 9] NIST AI RMF도 감독과 개입을 위험 관리의 일부로 둔다. [출처 10] |

---

## 3. 구성 요소별 용어와 실제 구현

| 실제로 쓰는 용어 | croScan에서 하는 일 | 구현 위치 | 출처 |
|---|---|---|---|
| **뉴로-심볼릭 AI (Neuro-Symbolic AI)** | LLM(이해)과 규칙 기반 판정(안전)을 결합한다. | 전체 구조 | [1][2] |
| **구조화 출력 (Structured Outputs) · 제약 디코딩 (Constrained Decoding)** | LLM 응답을 JSON 스키마로 강제한다(`response_format: json_schema`). 보기 id·질문 번호 같은 정해진 값만 고를 수 있다. 받은 값은 검증한다. 글로 쓴 「없음」은 답을 그대로 두고, 5개 항목(CF2·H2·LI2·HT1·B3)에서만 답 전체가 조건 없는 부정일 때 「없음」 보기처럼 계산한다(`augment.negated`). | `server/llm.py`, `understand.check()` | [3] |
| **정보 추출 · 슬롯 채우기 (Information Extraction / Slot Filling)** | 반장의 한 답에서 다른 열린 질문(슬롯)의 값을 채운다. | `server/understand.py` (TURN) | [3][11] |
| **출력 가드레일 · 출력 검증 (Output Guardrails / Validators)** | LLM 출력을 서버 검증기가 통과시키거나 버린다. 보기가 맞는지, 같은 질문을 두 번 답하지 않는지, 질문에 필요한 말이 문장에 있는지 확인한다. | `understand.check()` | [4][5] |
| **근거성 검증 (Groundedness Detection)** | 인용 구절이 반장 원문에 있는지, 제안한 값의 숫자·ID가 원문과 일치하는지, 일부 질문(회수·차단·병행 등)은 그 주제어가 문장에 있는지 본다. 주제어가 없으면 버리지 않고 「질문 내용이 문장에 직접 보이지 않음」 표시와 함께 기본 해제로 보여 반장이 정한다. 숫자·ID가 원문과 다르면 원문 구절이 그대로 있을 때만 그 말로 바꾼다. 의미 전체가 맞는지는 사람이 확인한다. | `understand.check()`, `_supported()`, `ITEM_NEEDS` | [6] |
| **출처 귀속 검증 (Citation / Attribution Verification)** | AI가 근거로 짚은 구절이 반장 원문의 한 문장 안에 있어야 하고, 아니면 버린다. 숫자·ID가 원문과 다르면 원문 구절이 그대로 있을 때만 그 말로 바꾼다(값의 의미가 다른 모든 경우를 잡는 것은 아니다). 법령·지침 인용은 저장된 출처·개정·구간과 일치하는지 검사한다. | `understand.check()`, `retrieval.check_cite` | [12] |
| **기권 · 선택적 예측 (Abstention / Selective Prediction)** | 「아마」, 「~일 수도」, 정정이 섞인 말, 누구 일인지 불분명한 말은 제안하지 않고 따로 남긴다. | `augment.HEDGE`, apart 처리 | [8] |
| **명확화 질문 (Clarifying Questions, 다중 턴)** | 비거나 모호한 정보는 질문 한도(검토당 12회, 명확화 3회) 안에서 다시 묻는다. 규칙 질문을 먼저, AI가 찾은 애매함을 그 뒤에 묻고, 같은 것은 두 번 묻지 않는다. | `need_catalog`, `store.issue` | [11] |
| **자기 수정 발화 처리 (Self-repair / Disfluency Correction)** | 「아까 4개라고 했는데 잘못 말했고 6개」처럼 말하다 고친 부분(reparandum → repair)을 나눠, 지금 맞는 부분만 다시 읽는다. | `understand.normalize()` (NORMALIZE) | [13] |
| **검증 단계 (Verification step, 자기 비평 계열)** | 첫 판독 뒤 별도 호출이 부정·관계 판독을 다시 본다. 시간 안에 못 하면 보류한다. 자기 검증의 한계 때문에, 결정적 가드레일과 사람 확인이 따로 있다. | `server/critique.py` | [7][14] |
| **인간 감독 · 사람 참여 (Human Oversight / Human-in-the-Loop)** | AI 판독은 확인 카드로만 나오고, 확인·항목 고치기·빼기 중 반장이 고른 것만 서류에 들어간다. 누가·언제·무엇을 확인했는지 기록한다. | 확인 카드, `store.decide()` | [9][10] |
| **규칙 기반 시스템 (Rule-based System)** | 작업쌍 위험을 강도 × 노출 점수와 1~3순위로 판정한다. 서류·확인 답변·제출본·규칙 판이 같으면 결과가 같다. | `server/pairs.py`, `pair_rules.json` | [1] |
| **페일세이프 설계 (Fail-safe Design)** | 모델이 실패·시간 초과하면 규칙 질문만으로 진행한다. 반장의 답이나 제출본이 서류 기준 경보를 낮추거나 없앨 수 없다(새 정보는 경보를 더하기만). 보장 범위는 서류 기준 경보의 하한이며, 모든 오판을 막는다는 뜻은 아니다. | `pairs.floor()`, 규칙 질문 우선 | 안전공학 일반 용어 |
| **BM25 검색 · 검색 증강 생성 (RAG)** | 법령(현행 조문 원문)·KOSHA 지침·팀 조사 자료에서 BM25(한글 2~3글자 조각)로 관련 구절을 찾아 「참고 자료(판단 근거 아님)」로 보여 준다. 업로드 분석에서는 검색 구절을 LLM의 참고 문맥으로 넣는다. RAG에 해당하는 것은 이 부분이다. | `server/retrieval.py`, `server/analyze.py` | — |
| **설명 가능 AI (XAI) · 추적 가능성 (Traceability)** | 위험 쌍마다 쓴 서류 값·반장 답·조문·사례를 보여 준다. 근거 지도는 규칙 적합성을 검수한 조문만 「확인된 근거」로 센다. | `explain.py`, `/static/evidence.html` | [1][10] |
| **프리픽스 캐싱 · KV 캐시 재사용 (Prefix Caching / KV Cache Reuse)** | 반장이 질문을 읽는 동안 그 질문 목록을 모델 캐시에 미리 넣는다. 같은 앞부분의 캐시가 남아 있으면 답을 읽을 때 그 계산을 건너뛴다. 실측: 프롬프트 처리 9초 → 1.8초(운영 CPU 서버, 2026-10-31). | `understand.warm`, llama.cpp `cache_prompt` | [15] |
| **요청 우선순위 스케줄링 (Priority Scheduling, 선점)** | 반장이 기다리는 답 읽기를 먼저 하고, 미리 계산은 그 뒤에 한다. 급한 요청이 오면 미리 계산이 자리를 내준다. | `llm._Slot` | — |
| **패러프레이즈 강건성 평가 · 제거 실험 (Paraphrase Robustness / Ablation)** | 합성 평가 사례: 기본 시나리오 30개 × 값 변형 5가지 × 표현 8가지 = 1,200개 답. 같은 뜻을 다르게 말해도 같은 결과가 나오는지 잰다. 규칙만 / 통합 비교와, 비평·캐시 같은 구성요소를 끄는 제거 실험(ablation) 옵션이 있다. | `tools/eval_phase1.py`, `eval_nl_variants.py` | [16] |

「—」로 표시한 줄은 용어 자체가 일반적인 공학 용어라 특정 출처를 달지 않았다.

---

## 4. 발표에서 「규칙」을 부르는 말

| 코드에서 부르는 말 | 발표 용어 | 비고 |
|---|---|---|
| 쌍 판정 규칙 | 규칙 기반 판정(뉴로-심볼릭의 기호적 계층) | 재현성·추적 가능성 |
| 서버 검사 | 출력 가드레일 / 근거성 검증 | AI 출력의 사실성 확인 |
| 근거 문장 확인·재연결 | 출처 귀속(attribution) 검증 | 인용이 값을 실제로 담는지 |
| 규칙 질문 | 명확화 질문(다중 턴) | 무엇을 먼저 물을지 |
| 하한(floor) | 페일세이프 설계 | AI가 경보를 줄이지 못함 |
| 미리 읽기 | 프리픽스 캐싱(KV 캐시 재사용) | llama.cpp 기능 사용 |

**주의.** 가드레일은 AI 대신 말을 이해하는 규칙이 아니라, AI가 이해한 것을 검증하는 장치다. 일부 질문(회수·차단·병행·시간 차이)에는 그 질문의 주제어가 문장에 있는지 보는 검사가 있다. 이 검사는 말을 대신 읽는 것이 아니라, 답이 될 근거가 있는지만 본다. 이 검사는 판독을 버리지 않고 표시만 한다(반장이 정함). 하류 계산에는 글로 쓴 「없음」을 5개 항목(CF2·H2·LI2·HT1·B3)에서 조건 없는 부정일 때만 「없음」 보기처럼 계산하는 규칙이 있다. 2026-10-31 평가 중 넣었던 「가스 안 씀」 단어 규칙은 이 원칙에 맞지 않아 되돌렸다. 이런 판독 차이는 사람 확인 카드에서 반장이 고친다.

---

## 5. 발표에서 쓸 수 있는 수치와 쓰면 안 되는 수치

**쓸 수 있는 것 (실측: 운영 CPU 서버 s8-g3, Raon-1-mini Q4, 2026-10-31. 원자료 `/data/tmp/evals/`와 설계서 부록)**
- 답을 보내고 다음 질문이 뜨기까지 0.2~0.3초(선계산·비차단 구조).
- 미리 읽기(프리픽스 캐싱)로 프롬프트 처리 9초 → 1.8초.
- 전체 대화 30개: 모두 6분 안. 대화당 p50 111초, p95 240초(질문당 읽기·입력 20초 가정).
- 동시 사용자 4명: 1인 중앙값 32.2초, 실패 0.
- 자연어 1,200건 평가(150가지 상황 × 8가지 말투, 2026-10-31 코드). 맞힌 판독은 규칙만 285건 → 통합 794건이었다. 금지 0건(하지 않은 말·남의 작업을 본인 사실로 적은 경우 없음), 틀림 53건, 놓침 206건이었다. 원자료상 값·주체·시점 틀림은 0이다(53건이 모두 글로 쓴 「없음」이라는 분류는 수작업 검토 결과). 이 평가 뒤 자료 보강으로 질문·판독이 바뀌었으므로, 바뀐 부분은 시험 묶음(질문 179·질문 자료 244·대화 API 46 등)으로만 확인했다고 함께 말한다.
- 원본양식 무손상: 제출본과 원본의 픽셀 비교에서 양식 칸 밖 변화 0(상단 24pt와 각 칸 둘레 2pt를 뺀 영역 기준, 2026-11-01 스테이징 제출본으로 다시 확인).
- 조사자료 반영 범위(2026-11-01): 412쪽 조사본과 사례집 81건 등 자료 전부를 한 줄씩 대조했다. 쌍 판정 규칙은 16 → 36개, 위험 체크리스트는 53 → 86항목이 됐다(11-01 최종 전수 검토 포함). 규칙 추가는 경보를 더하기만 하며, 기존 경보가 줄지 않음을 시험으로 확인한다(의도한 예외 둘: 「용접봉 불출」만, 「관찰·모니터링」만 적힌 작업은 그 행위로 보지 않음).
- 시연일 쌍 판정: 26쌍(11-01 최종 검토로 옆 BAY 불티 판정보류 2쌍 추가). 정답 쌍 10/10을 찾았고(순위까지 맞은 것 8/10), 근접 5쌍 중 확정 경보는 0이다(3쌍은 판정보류로 표시, 시연 자료 기준이며 현장 실측 정확도가 아니다).

**쓰면 안 되는 것**
- 시간 절감률, 사고 감소율. 측정한 적이 없다(현장 정정 D24·D28).
- 회사 공개실적(재해율 등)을 croScan 효과처럼 쓰는 것.
- HiSEs·HI-SIGHT에 이미 있는 기능(체크리스트, 도장·화기 필터 등)을 croScan이 처음 만든 것처럼 쓰는 것(D17~D21). 「보완·연동」으로 설명한다.
- 「AI가 판단」, 「AI가 승인」. croScan은 승인하지 않는다.

---

## 6. 30초 설명 (발표 대본용)

> "croScan은 생성형 AI와 규칙 기반 판정을 결합한 뉴로-심볼릭 구조입니다. LLM은 작업반장이 자유롭게 한 말을 구조화된 데이터로 추출합니다. 출력 가드레일은 인용과 숫자가 반장의 실제 말과 맞는지 검증합니다. 불확실한 판독은 제안하지 않고 질문 한도 안에서 다시 묻습니다. 원본 서류의 사실과, AI 해석 가운데 반장이 확인한 것만 규칙 기반 판정에 들어갑니다. 같은 입력에는 같은 판정이 나옵니다. 모델이 실패하면 규칙만으로 진행하고, 서류 기준 경보는 줄어들지 않습니다. 판정에는 쓴 사실과 규칙이 붙고, 조문과 사례는 검수 상태를 구분해 보여 줍니다."

---

## 출처

1. Neuro-symbolic AI의 안전 분야 적용(기호적 계층의 가드레일·추적 가능한 결정): [preprints.org 202511.1342](https://www.preprints.org/manuscript/202511.1342/v1). 「LLM proposes, rules authorize」 패턴: [synapsesocial.com 요약(XPS 2)](https://synapsesocial.com/pt/papers/69e320cc40886becb653fef8). 참고로 대부분 프리프린트·업체 글이다.
2. [PYMNTS — Neurosymbolic AI Aims to Make AI Safe](https://www.pymnts.com/?p=3367054)
3. 구조화 출력·제약 디코딩: [Together AI Docs — Structured Outputs](https://docs.together.ai/learn/structured-outputs), [ZeroEntropy — Structured Output](https://www.zeroentropy.dev/concepts/structured-output/), [EMNLP 2025 Industry — SLOT](https://aclanthology.org/anthology-files/pdf/emnlp/2025.emnlp-industry.32.pdf)
4. [Guardrails AI × NeMo Guardrails](https://guardrailsai.com/blog/nemoguardrails-integration)
5. [NVIDIA NeMo Guardrails — Guardrail Catalog](https://docs.nvidia.com/nemo/guardrails/configure-guardrails/guardrail-catalog)
6. [Microsoft Learn — Groundedness detection (Azure AI Content Safety)](https://learn.microsoft.com/en-gb/azure/ai-services/content-safety/concepts/groundedness)
7. [Stechly 외 — On the Self-Verification Limitations of LLMs on Reasoning and Planning Tasks (arXiv 2402.08115)](https://arxiv.org/pdf/2402.08115)
8. 기권: [AbstentionBench (arXiv 2506.09038)](https://arxiv.org/abs/2506.09038v1), [Selectively Answering Ambiguous Questions (arXiv 2305.14613)](https://arxiv.org/pdf/2305.14613.pdf)
9. [EU AI Act Service Desk — Article 14 Human oversight](https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-14)
10. NIST AI RMF의 감독·개입: [Obsidian Security 정리](https://www.obsidiansecurity.com/academy/ai-regulations-requiring-agent-oversight) (원문은 NIST AI RMF 1.0)
11. 명확화 질문·슬롯 채우기: [ClarifyMT-Bench (arXiv 2512.21120)](https://arxiv.org/pdf/2512.21120)
12. 출처 귀속 검증: [VeriCite (arXiv 2510.11394)](https://arxiv.org/pdf/2510.11394), [TruLens — RAG feedback](https://www.trulens.org/reference/trulens/feedback/templates/rag/), [FullCite (arXiv 2606.07130)](https://arxiv.org/pdf/2606.07130)
13. 자기 수정 발화(reparandum·repair, Shriberg 1994 구조): [Disfluency Detection using a Bidirectional LSTM (arXiv 1604.03209)](https://arxiv.org/pdf/1604.03209), [Noisy Channel + Neural LM (arXiv 1808.09091)](https://arxiv.org/pdf/1808.09091)
14. 검증 계열 기법: [Chain-of-Verification 요약(DAIR.AI)](https://academy.dair.ai/papers/chain-of-verification-cove), [The Prompt Report (arXiv 2406.06608)](https://arxiv.org/pdf/2406.06608)
15. llama.cpp 프리픽스 캐싱·슬롯: [llama.cpp Discussion #13606 — KV cache reuse with llama-server](https://github.com/ggml-org/llama.cpp/discussions/13606), [Serving parallel requests with llama.cpp server slots](https://dev.to/multigrid/serving-parallel-requests-with-llamacpps-server-slots-c90)
16. 패러프레이즈 강건성: [Lunardi 외 — On Robustness and Reliability of Benchmark-Based Evaluation of LLMs (arXiv 2509.04013, ECAI 2025)](https://arxiv.org/abs/2509.04013)
