# V14B, V15–V19, V17B (captions 38–57). exec'd from scenes21.py.
SAY_F = LF.get("typed_first") or "작업시간 14:00~16:00. 장소 1BAY 14-16 칼럼 B21S 블록 상부. 러그 3개 절단·회수만, 3명이 2시간."
V15_RESULT = B(1090, 870, 774, 52)
V15_LABEL = {"held": "근거 부족으로 보류", "ok": "AI 추가 제안", "none": "관계 미발견"}.get(rv.get("status"), "검토 미완료")
V17_MSGVIEW, V17_MSG, V17_NONOTE = B(1105, 600, 791, 360), B(1105, 642, 791, 243), B(1105, 892, 791, 66)
V17_NOTE, V17_PUTVIEW = B(1105, 828, 791, 60), B(1105, 614, 791, 360)
V17_ADDVIEW, V17_ADDED = B(1105, 505, 791, 250), B(1113, 655, 775, 56)
V18_SRC_LABEL = "근거: 규칙 문구 2건 · 시간·위치는 0731 제출본"

# ---- V14B 부족한 정보는 담당 반장에게 확인하고 재제출 (38–40) ----
KX = "추가 확인 예시 · P21 (0732 × 0735)"
SPECS["v14b"] = spec("croScan V14B · 부족한 정보는 담당 반장에게 확인하고 재제출", [
    D("v14b", 38, "ask", "V14B_pair", camera=[{"at": 1, "to": ["head", "ask"], "pad": 30}, {"at": 8.5, "to": "V14B_hq.doc", "pad": 50}],
      marks=[{"at": 2, "until": 5, "on": "head", "label": "P21 · 3순위 확인 필요 · 정보 부족"}, {"at": 5, "until": 8, "on": "ask", "label": "확인 필요"},
             {"at": 9.5, "until": 12, "on": "V14B_hq.who", "label": "담당별 확인 · 0735 작업반장"},
             {"at": 12, "on": "V14B_hq.ask", "label": "본인 작업 질문: 작업 위치·시간과 인원 배치"}],
      swaps=[{"at": 8, "shot": "V14B_hq"}], cues=K(KX), hat=12.5, beats=18),
    D("v14b", 39, "copy", "V14B_hq", camera=[{"at": 0, "to": "doc", "pad": 50}],
      marks=[{"at": 1, "until": 3, "on": "copy", "label": "질문 복사"}, {"at": 4, "until": 9, "on": "V14B_copied.copy", "label": "실제 복사 결과 · 보내지는 않음"},
             {"at": 9, "on": "V14B_copied.foot", "label": "croScan은 메시지를 보내지 않습니다"}],
      clicks=[{"at": 2.5, "on": "copy"}], swaps=[{"at": 3, "shot": "V14B_copied"}], cues=K(KX), hat=4.5, beats=14),
    D("v14b", None, "foreman", "F_review", camera=[{"at": 0.5, "to": "msgs", "pad": 20}, {"at": 7.5, "to": "F_card.card", "pad": 30}],
      marks=[{"at": 1, "until": 3, "on": "question", "label": "0735 반장 화면 · 실제 작업시간 질문"},
             {"at": 8.5, "until": 12.5, "on": "F_card.card", "label": "AI가 읽은 시간·장소만 반장이 확인 (나머지 줄은 「이것 빼기」)"},
             {"at": 13.5, "on": "F_sent.docs", "label": "확인 후 다시 제출 · 0735 새 제출본"}],
      typing=[{"at": 2.5, "until": 7, "title": "입력 내용 재현 · 실제 입력한 답 (준비 자료의 시간·장소)", "text": SAY_F, "done": 5.5}],
      swaps=[{"at": 7, "shot": "F_card"}, {"at": 12.5, "shot": "F_sent"}], cues=K("반장 화면 · 0735 작업반장 · " + KX), beats=18),
    D("v14b", 40, "review", "V14B_after", camera=[{"at": 0.5, "to": "tlver", "pad": 40}, {"at": 6, "to": "V14B_hy.hy", "pad": 20}],
      marks=[{"at": 1.5, "until": 5.5, "on": "ver", "label": "판정 자료: 0735 제출본 반영 (위치·시간)"},
             {"at": 7, "on": "V14B_hy.row", "label": "확인 사실로 다시 판정 · 순위는 3순위 그대로"}],
      swaps=[{"at": 5.5, "shot": "V14B_hy"}], cues=K("안전관리자 화면 · " + KX), hat=2, beats=14),
    D("v14b", None, "back", "V14B_back", camera=[{"at": 0.5, "to": "head", "pad": 40}],
      marks=[{"at": 1.5, "on": "head", "label": "0731 × WP-01 (P02) 주 사례로 돌아옴"}], beats=8),
])

# ---- V15 선택적 AI 추가 검토 (41–42) ----
NEAR = (L2.get("pair_review_before") or {}).get("chosen", "0738|WP-1029-22")
KV15 = K("추가 검토 예시 · 별도 작업쌍 " + NEAR.replace("|WP-1029-", " × WP-"))
SPECS["v15"] = spec("croScan V15 · 선택적 AI 추가 검토", [
    D("v15", 41, "request", "V15_near", camera=[{"at": 1, "to": "row", "pad": 80}, {"at": 4.5, "to": B(1079, 410, 796, 470), "pad": 20}],
      marks=[{"at": 1.5, "until": 3.5, "on": "row", "label": "검토 통과 인접 작업"}, {"at": 5.5, "until": 8, "on": "V15_pair.why", "label": "규칙 경보 없음 · 검토 통과 근거"},
             {"at": 8, "on": "V15_pair.btn", "label": "AI 검토 요청"}],
      clicks=[{"at": 3.5, "on": "row"}, {"at": 11, "on": "V15_pair.btn"}], swaps=[{"at": 4, "shot": "V15_pair"}], cues=KV15, hat=8.5, beats=12),
    D("v15", 42, "result", "V15_wait", camera=[{"at": 0, "to": "rv", "pad": 40}, {"at": 3.5, "to": "V15_done.rv", "pad": 30}],
      marks=[{"at": 0.5, "until": 3, "on": "out", "label": f"실제 약 {round((L2.get('pair_review_seconds') or {}).get('secs', 30))}초 걸림 · 기다린 구간 줄임"},
             {"at": 4.5, "until": 7.5, "on": V15_RESULT, "label": V15_LABEL}, {"at": 7.5, "on": "V15_done.ev", "label": "AI가 대조한 두 서류의 행"}],
      swaps=[{"at": 3, "shot": "V15_done"}], cues=KV15, hat=5, beats=14),
])

# ---- V16 같은 시각의 배치 (43–44) ----
TIMEBOX = B(324, 196, 214, 74)
SPECS["v16"] = spec("croScan V16 · 조율 전에 같은 시각의 배치 확인", [
    D("v16", 43, "tomap", "V16_pair", camera=[{"at": 1, "to": "where", "pad": 60}, {"at": 4.5, "to": B(324, 160, 1530, 180), "pad": 20}],
      marks=[{"at": 2, "until": 4, "on": "tomap", "label": "배치도에서 보기"}, {"at": 5.5, "on": TIMEBOX, "label": "선택 시각 13:30"}],
      clicks=[{"at": 3.5, "on": "tomap"}], swaps=[{"at": 4, "shot": "V16_map"}], hat=6, beats=12),
    D("v16", 44, "map", "V16_map", camera=[{"at": 0.5, "to": "grid", "pad": 20}, {"at": 3, "to": "pair", "pad": 150}],
      marks=[{"at": 1.5, "until": 3.5, "on": B(309, 590, 1562, 82), "label": "3BAY"}, {"at": 4, "on": "pair", "label": "0731 화기 · WP-01 도장 · 08–10칼럼"}], hat=4.5, beats=14),
])

# ---- V17 협조 문자 (45–48) ----
KV17 = K("다른 작업쌍 예시 · P22 (0735 × WP-08)")
SPECS["v17"] = spec("croScan V17 · 작업 조율 협조 문자 작성과 복사", [
    D("v17", 45, "p02", "V17_filled", camera=[{"at": 1, "to": "who", "pad": 30}, {"at": 5, "to": V17_MSGVIEW, "pad": 30}],
      marks=[{"at": 2, "until": 5, "on": "who", "label": "받는 사람 · 협의 상대 (이름·번호 가림)"}, {"at": 6, "until": 9, "on": V17_MSG, "label": "겹치는 시간·위치·요청"},
             {"at": 9, "on": V17_NONOTE, "label": "P02: 확인된 반장 답이 없어 협의할 점 제안 없음"}], beats=14),
    D("v17", 46, "note", "V17_ex_note", camera=[{"at": 1, "to": "note", "pad": 40}],
      marks=[{"at": 2, "until": 5, "on": V17_NOTE, "label": "협의할 점 (제안) · AI 초안"}, {"at": 5, "on": "src", "label": "출처: 0735 반장 확인 답"}], cues=KV17, beats=10),
    D("v17", 47, "put", "V17_ex_note", camera=[{"at": 0.5, "to": V17_PUTVIEW, "pad": 20}, {"at": 3.5, "to": V17_ADDVIEW, "pad": 30}],
      marks=[{"at": 1, "until": 2.5, "on": "put", "label": "문자에 넣기"}, {"at": 4.5, "on": V17_ADDED, "label": "추가된 문장"}],
      clicks=[{"at": 2.5, "on": "put"}], swaps=[{"at": 3, "shot": "V17_ex_added"}], cues=KV17, hat=5, beats=10),
    D("v17", 48, "copy", "V17_ex_added", camera=[{"at": 0.5, "to": "copy", "pad": 120}, {"at": 3.5, "to": "V17_ex_copied.toast", "pad": 80}],
      marks=[{"at": 1, "until": 3, "on": "copy", "label": "문자 복사"}, {"at": 4.5, "on": "V17_ex_copied.toast", "label": "실제 복사 결과 · 보내지는 않음"}],
      clicks=[{"at": 2.5, "on": "copy"}], swaps=[{"at": 3, "shot": "V17_ex_copied"}], cues=KV17, hat=5, beats=12),
])

# ---- V17B 문자 전달 후 일정 조율·기존 승인 완료를 연결 (49–50): PRAI motion blocks, no app screen ----
KB = [{"block": "kicker", "text": "앱 외부 진행 · 협의·승인 완료를 가정", "tone": "brand", "at": 0, "y": 330, "enter": "cut"}]
STEPS = ["1. 문자 전달", "2. 반장 간 일정 조율", "3. 생산부서 전산승인"]
SPECS["v17b"] = spec("croScan V17B · 문자 전달 후 일정 조율·기존 승인 완료를 연결", [
    D("v17b", None, "from_copy", "V17_ex_copied", camera=[{"at": 0, "to": "toast", "pad": 80}],
      marks=[{"at": 0.5, "on": "toast", "label": "V17 복사 결과 · 전달은 기존 연락 수단"}], beats=6),
    M("v17b", 49, "coord", KB + [{"block": "chips", "items": STEPS[:2], "step": 2, "at": 1, "y": 560, "enter": "rise"}], beats=10, hat=3.5),
    M("v17b", 50, "approved", KB + [{"block": "chips", "items": STEPS, "at": 0, "y": 560, "enter": "cut"},
                                    {"block": "title", "text": "협의·승인 후 현장 전달 자료 준비", "size": 58, "at": 3, "y": 740, "enter": "rise"}], beats=12, hat=4),
])

# ---- V18 AI 게시 문안과 별지 반영 (51–53) ----
ROWS = B(1106, 141, 789, 108)
KV18 = K("가정: 반장 간 협의·생산부서 전산승인을 마친 뒤")
SPECS["v18"] = spec("croScan V18 · AI의 현장 게시 문안 제안과 별지 반영", [
    D("v18", None, "open", "V18_issue", camera=[{"at": 1, "to": "card", "pad": 30}, {"at": 4.5, "to": B(1106, 105, 789, 370), "pad": 20}],
      marks=[{"at": 2, "until": 4, "on": "prev", "label": "0731 미발행 별지 · 미리 보기·편집"}, {"at": 5.5, "on": "V18_sheet.aigo", "label": "AI 문안 보충 보기"}],
      clicks=[{"at": 3.5, "on": "prev"}, {"at": 7, "on": "V18_sheet.aigo"}], swaps=[{"at": 4, "shot": "V18_sheet"}], cues=KV18, beats=10),
    D("v18", 51, "draft", "V18_wait", camera=[{"at": 0, "to": B(1106, 380, 789, 330), "pad": 20}],
      marks=[{"at": 0.5, "until": 1.5, "on": B(1106, 419, 789, 40), "label": "AI 문안 준비 중"}, {"at": 2.5, "on": "V18_draft.lines", "label": "AI 초안"}],
      swaps=[{"at": 1.5, "shot": "V18_draft"}], hat=3, beats=10),
    D("v18", 52, "source", "V18_draft", camera=[{"at": 0.5, "to": "src", "pad": 50}],
      marks=[{"at": 1.5, "on": "src", "label": V18_SRC_LABEL}], beats=8),
    D("v18", 53, "take", "V18_draft", camera=[{"at": 0.5, "to": B(1106, 105, 789, 600), "pad": 20}, {"at": 3.5, "to": ROWS, "pad": 50}],
      marks=[{"at": 1, "until": 2.5, "on": "take", "label": "문안 채택"}, {"at": 4.5, "on": ROWS, "label": "바뀐 칸: 우리 반이 할 일 · 착수조건"}],
      clicks=[{"at": 2.5, "on": "take"}], swaps=[{"at": 3, "shot": "V18_taken"}], hat=5, beats=12),
])

# ---- V19 발행 → 할 일 · 착수조건 · 중지조건 → 전체 별지 (54–57) ----
SPECS["v19"] = spec("croScan V19 · 우리 반의 할 일·착수조건·중지조건 확인", [
    D("v19", 54, "publish", "V19_before", camera=[{"at": 1, "to": "card", "pad": 30}],
      marks=[{"at": 2, "until": 3.5, "on": "pub", "label": "발행"}, {"at": 5, "on": "V19_issued.issued", "label": "S-0731/R1 발행"}],
      clicks=[{"at": 3, "on": "pub"}], swaps=[{"at": 3.5, "shot": "V19_issued"}], hat=5.5, beats=12),
    D("v19", 55, "todo", "V19_view", camera=[{"at": 0.5, "to": B(1106, 60, 789, 340), "pad": 10}, {"at": 3, "to": ROWS, "pad": 50}],
      marks=[{"at": 1.5, "until": 3, "on": B(1090, 60, 500, 40), "label": "발행본 S-0731/R1"},
             {"at": 4, "until": 7, "on": "todo", "label": "우리 반이 할 일"}, {"at": 7, "on": "start", "label": "착수조건"}], hat=4.5, beats=12),
    D("v19", 56, "stop", "V19_view", camera=[{"at": 0.5, "to": ["stop", "who"], "pad": 70}],
      marks=[{"at": 1.5, "until": 5, "on": "stop", "label": "중지·해제 조건"}, {"at": 5, "on": "who", "label": "연락할 상대 반장"}], hat=2, beats=10),
    D("v19", 57, "whole", "V19_full", camera=[{"at": 0.5, "to": "sheet", "pad": 10}],
      marks=[{"at": 1.5, "on": "three", "label": "할 일 · 착수조건 · 중지·해제 조건"}], hat=2.5, beats=12),
])
