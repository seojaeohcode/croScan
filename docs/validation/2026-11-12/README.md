# 2026-11-12 공개본 검증

- **34 / 34 스크립트 통과.** 서로 다른 평가/회귀 도구의 종료 코드를 확인한 집계입니다. 실제 사용자·현장 사례 34개를 뜻하지 않습니다.
- 환경: Windows, Python 3.12.14, OpenJDK 21.0.12.1, 저장소 requirements.txt, Node.js.
- LLM 주소는 응답하지 않는 로컬 포트로 설정했습니다. 모델을 대체한 단위 시험과 규칙·PDF·상태 시험이며, 실모델 추론은 하지 않았습니다.
- 데이터는 별도 임시 폴더로 분리했습니다. 제출 보관 시험은 `CROSCAN_KEEP_SUBMISSIONS=1`, 기본 시연 제출 시험은 `0`을 사용했습니다.
- 최초 실행의 PDF 시험 3개는 180초 제한을 초과했습니다. 별도 재실행에서 체크리스트 222.91초, 반영본 200.47초, 출력 113.34초로 완료했습니다. 최종 로그를 첨부합니다.
- 프록시 검사는 `--conf deploy/oidc-proxy/nginx.conf`를 지정한 오프라인 검사입니다. 실제 SSO 접속 시험은 아닙니다.
- 앱 `/api/health`, 관리자 시연 진입, 50개 작업·26개 위험쌍 표시, 브라우저 JavaScript 오류 없음 확인.
- PDF: 체크리스트 2,794/2,794 항목 · 반영본 146/146 항목 · 출력 11/11 항목 통과. 항목 수는 검사 단언의 수이며 독립적인 현장 사례 수가 아닙니다.
- Docker 엔진·실제 LLM 서버·현장 결재 시스템은 검증 환경에 없었습니다.
- 로그의 검증용 로컬 경로와 줄 끝 공백만 정리했습니다. Starlette의 httpx 테스트 클라이언트 사용 중단 예고 경고가 있으며, 시험 실패는 아닙니다.

재현: `python tools/check_release.py --pdf`. PDF 시험은 환경에 따라 수 분 걸릴 수 있습니다. 원본/출력 PDF 두 개를 인자로 받는 `check_form_intact.py`와 전체 판독 채점 `check_extract.py`, 별도 시나리오 `check_interpret.py`는 이번 묶음에 포함하지 않았습니다.

| 스크립트 | 결과 | 기록 |
|---|---|---|
| `check_access.py` | 통과 | [로그](check_access.py.txt) |
| `check_analyze.py` | 통과 | [로그](check_analyze.py.txt) |
| `check_cases.py` | 통과 | [로그](check_cases.py.txt) |
| `check_checkai.py` | 통과 | [로그](check_checkai.py.txt) |
| `check_checklist.py` | 통과 | [로그](check_checklist.py.txt) |
| `check_checklist_material.py` | 통과 | [로그](check_checklist_material.py.txt) |
| `check_ckmerge.py` | 통과 | [로그](check_ckmerge.py.txt) |
| `check_coordnote.py` | 통과 | [로그](check_coordnote.py.txt) |
| `check_critique_link.py` | 통과 | [로그](check_critique_link.py.txt) |
| `check_delta_api.py` | 통과 | [로그](check_delta_api.py.txt) |
| `check_dialogue_api.py` | 통과 | [로그](check_dialogue_api.py.txt) |
| `check_docs_ai.py` | 통과 | [로그](check_docs_ai.py.txt) |
| `check_eval_tools.py` | 통과 | [로그](check_eval_tools.py.txt) |
| `check_explain.py` | 통과 | [로그](check_explain.py.txt) |
| `check_hybrid.py` | 통과 | [로그](check_hybrid.py.txt) |
| `check_pairreview.py` | 통과 | [로그](check_pairreview.py.txt) |
| `check_pairs.py` | 통과 | [로그](check_pairs.py.txt) |
| `check_pairs_cases.py` | 통과 | [로그](check_pairs_cases.py.txt) |
| `check_pairs_final.py` | 통과 | [로그](check_pairs_final.py.txt) |
| `check_pairs_material.py` | 통과 | [로그](check_pairs_material.py.txt) |
| `check_proxy_headers.py` | 통과 | [로그](check_proxy_headers.py.txt) |
| `check_qa_board.py` | 통과 | [로그](check_qa_board.py.txt) |
| `check_questions.py` | 통과 | [로그](check_questions.py.txt) |
| `check_questions_material.py` | 통과 | [로그](check_questions_material.py.txt) |
| `check_reflect.py` | 통과 | [로그](check_reflect.py.txt) |
| `check_render.py` | 통과 | [로그](check_render.py.txt) |
| `check_retrieval.py` | 통과 | [로그](check_retrieval.py.txt) |
| `check_store.py` | 통과 | [로그](check_store.py.txt) |
| `check_submissions.py` | 통과 | [로그](check_submissions.py.txt) |
| `check_submit_link.py` | 통과 | [로그](check_submit_link.py.txt) |
| `check_ui_state.py` | 통과 | [로그](check_ui_state.py.txt) |
| `check_understand.py` | 통과 | [로그](check_understand.py.txt) |
| `eval_retrieval.py` | 통과 | [로그](eval_retrieval.py.txt) |
| `check_demo_submissions.py` | 통과 | [로그](check_demo_submissions.py.txt) |
