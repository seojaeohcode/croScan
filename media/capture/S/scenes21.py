# scene definitions for build21.py (exec'd there: B, D, M, K, spec, SPECS, CAPT are in scope). Beats: 1 beat = 0.6 s.

# ---- V12 같은 구역의 화기와 도장 (30–33) ----
TL = B(1079, 505, 796, 112)                       # 「겹치는 시간 13:30–15:00 · 90분」 + the two bars
SPECS["v12"] = spec("croScan V12 · 같은 구역의 화기와 도장", [
    D("v12", 30, "login_docs", "V12_login", clicks=[{"at": 2, "on": "go"}], swaps=[{"at": 3, "shot": "V12_docs"}],
      camera=[{"at": 4, "to": ["V12_docs.row", "V12_docs.sum"], "pad": 30}],
      marks=[{"at": 5, "until": 8, "on": "V12_docs.row", "label": "0731 화기 작업"},
             {"at": 8, "until": 11.5, "on": "V12_docs.locTime", "label": "반장이 확인한 위치·시간 (0731 제출본)"},
             {"at": 11.5, "on": "V12_docs.sans", "label": "반장 추가 답변 3건"}], hat=8.5, beats=16),
    D("v12", 31, "home_p1", "V12_home", camera=[{"at": 1, "to": ["nav", "res"], "pad": 20}],
      marks=[{"at": 2, "until": 5, "on": "pri", "label": "순위별 위험 쌍"}, {"at": 5, "until": 7, "on": "p1tab", "label": "1순위 · 즉시 조정"},
             {"at": 8, "on": "V12_p1.pair", "label": "P02 · 0731 × WP-01"}],
      clicks=[{"at": 6.5, "on": "p1tab"}, {"at": 10.5, "on": "V12_p1.pair"}], swaps=[{"at": 7, "shot": "V12_p1"}], hat=5, beats=12),
    D("v12", 32, "pair_time", "V12_pair", camera=[{"at": 1, "to": B(1079, 430, 796, 240), "pad": 30}, {"at": 11.5, "to": "V12_hy.hy", "pad": 20}],
      marks=[{"at": 2, "until": 4.5, "on": "where", "label": "3BAY 08–10 · 같은 블록 E42P"},
             {"at": 4.5, "until": 8, "on": "tlver", "label": "0731 반장 확인 13:00–15:00 · WP-01 계획 13:30–15:00"},
             {"at": 8, "until": 11.5, "on": TL, "label": "13:30–15:00 · 90분 겹침"},
             {"at": 13, "on": "V12_hy.row", "label": "반장 답 반영 전후 같은 1순위 9점"}],
      swaps=[{"at": 11.5, "shot": "V12_hy"}], hat=8.5, beats=18),
    D("v12", 33, "pair_why", "V12_pair", camera=[{"at": 1, "to": "why", "pad": 30}],
      marks=[{"at": 2, "until": 5, "on": "flow", "label": "주는 작업 → 받는 작업"}, {"at": 5, "on": "acc", "label": "예상 사고 경로"}], beats=12),
])

# ---- V13 판정에 사용한 서류로 돌아가기 (34–35) ----
SPECS["v13"] = spec("croScan V13 · 판정에 사용한 서류로 돌아가기", [
    D("v13", 34, "jd", "V13_jd", camera=[{"at": 1, "to": B(1079, 262, 796, 455), "pad": 20}],
      marks=[{"at": 2, "until": 5, "on": "time", "label": "판정 근거·원문"}, {"at": 5, "on": "evs", "label": "판정에 쓴 시간·위치"}], beats=10),
    D("v13", 35, "docs", "V13_docWP", camera=[{"at": 1, "to": "panel", "pad": 10}, {"at": 3, "to": "both", "pad": 60}, {"at": 8, "to": B(1105, 710, 791, 114), "pad": 60}],
      marks=[{"at": 4, "until": 7, "on": "both", "label": "WP-01 계획서: 13:30~15:00 · 3BAY 08-10 E42P"},
             {"at": 9, "until": 11.5, "on": B(1105, 710, 791, 38), "label": "0731 허가서 원본 장소: 팀 이름"},
             {"at": 11.5, "on": B(1105, 748, 791, 76), "label": "0731 반장 답 반영: 위치 · 13:00–15:00"}],
      swaps=[{"at": 7, "shot": "V13_doc0731"}], beats=18),
])

# ---- V14 필요한 설명을 직접 질문 (36–37) ----
Q = "왜 1순위인가요?"
SPECS["v14"] = spec("croScan V14 · 필요한 설명을 직접 질문", [
    D("v14", 36, "ask", "V14_ask0", camera=[{"at": 1, "to": "why", "pad": 60}],
      marks=[{"at": 2, "until": 7, "on": "form", "label": "이 판정에 대해 묻기"}, {"at": 7, "on": "V14_typed.ask", "label": "묻기"}],
      typing=[{"at": 3, "until": 6.5, "title": "입력 내용 재현 · 실제 입력한 질문", "text": Q, "done": 5}],
      swaps=[{"at": 6.5, "shot": "V14_typed"}], clicks=[{"at": 8.5, "on": "V14_typed.ask"}], hat=2.5, beats=10),
    D("v14", 37, "answer", "V14_wait", camera=[{"at": 0, "to": B(1079, 700, 796, 180), "pad": 40}, {"at": 3, "to": B(1079, 318, 796, 460), "pad": 20}],
      marks=[{"at": 0.5, "until": 2.5, "on": "out", "label": "AI가 판정 근거에서 답을 고르는 중"},
             {"at": 4, "until": 7, "on": "V14_done.judge", "label": "AI가 질문을 이 설명으로 읽음"},
             {"at": 7, "until": 10, "on": "V14_done.facts", "label": "사용한 사실"}, {"at": 10, "on": "V14_done.left", "label": "아직 확인할 것"}],
      swaps=[{"at": 2.5, "shot": "V14_done"}], hat=4.5, beats=16),
])

exec((S / "scenes21b.py").read_text(encoding="utf-8")) if (S / "scenes21b.py").exists() else None
