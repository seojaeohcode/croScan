"""V12–V19 PRAI projects (safety manager, captions 30–51) from the shots in cap/. Captions are read verbatim from the confirmed
51-caption file; 39 is the conti's 「근거 부족으로 보류」 line (the real pair-review result was status=held).
Writes v12..v19/prai.json, copies shots + music, and scenemap19.json (scene → caption number, start/end in seconds).
usage: python build19.py
"""
import json
import re
import shutil
from pathlib import Path

S = Path(__file__).parent
WORK = S.parent.parent / "work"
CAP = S / "cap" / "public" / "shots"
C = json.loads((WORK / "common.json").read_text(encoding="utf-8"))
SUBS = Path("C:/Users/seoco/.claude/uploads/6b9e37ba-819f-4f0d-b20b-5274c2f4e819/b452c8e0-croScan______51__2026-11-02.md")
URL = "위험작업 허가서 사전검토 · 스테이징 화면"
CAPT = {}
for line in SUBS.read_text(encoding="utf-8").splitlines():
    m = re.match(r"\|\s*(\d+)\s*\|\s*V\d+-\d+\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*$", line)
    if m:
        CAPT[int(m.group(1))] = (m.group(2), None if m.group(3) == "—" else m.group(3))
assert len(CAPT) == 51, len(CAPT)
C39 = "근거가 부족한 내용은 보류로 남깁니다."          # conti table row 「근거 부족으로 보류」
CAPT[39] = (C39, CAPT[39][1])
BPM = C["music"]["bpm"]
SPECS, SCENEMAP = {}, {}


def B(x, y, w, h):
    return {"box": [x, y, w, h]}


def D(proj, cap, id, shot, camera=None, marks=None, clicks=None, swaps=None, typing=None, cues=None, beats="auto", hat=None):
    """one scene; caption `cap` (number or None) starts half a beat after the first mark unless `hat` is given"""
    first = min(m["at"] for m in marks) if marks else 2
    hat = hat if hat is not None else first + 0.5
    last = max([m.get("until", m["at"] + 2) for m in marks or []] + [c["at"] + 1.5 for c in camera or []] + [s["at"] + 2 for s in swaps or []] + [0])
    need = max(8, -(-(hat + 5) // 2) * 2 if cap else 0, -(-last // 2) * 2)
    beats = max(beats, need) if isinstance(beats, int) else int(need)
    d = {"id": id, "type": "demo", "shot": shot, "url": URL, "camera": camera or [], "marks": marks or [], "clicks": clicks or [], "swaps": swaps or [],
         "typing": typing or [], "cues": cues or [], "beats": beats}
    if cap:
        head, sub = CAPT[cap]
        d["headline"] = {"text": head, **({"sub": sub} if sub else {}), "at": hat}
    SCENEMAP.setdefault(proj, []).append({"scene": id, "caption": cap, "hat": hat if cap else None, "beats": beats,
                                          "headline": CAPT[cap][0] if cap else None, "sub": CAPT[cap][1] if cap else None, "shots": [shot] + [s["shot"] for s in swaps or []]})
    return d


def spec(title, scenes):
    s = {"$schema": "C:/Users/seoco/OneDrive/Desktop/PRAI/schema/prai.schema.json", **json.loads(json.dumps(C))}
    s["theme"].pop("logo", None)
    s["video"] = {**C["video"], "title": title}
    s["scenes"] = scenes
    return s


def K(text):
    return [{"block": "kicker", "text": text, "tone": "brand", "at": 0, "y": 58, "enter": "cut"}]


# ---- V12 같은 구역의 화기와 도장 ----
TL = B(1079, 510, 796, 112)                       # 「겹치는 시간 13:30–15:00 · 90분」 + the two bars
SPECS["v12"] = spec("croScan V12 · 같은 구역의 화기와 도장", [
    D("v12", 30, "login_docs", "V12_login", clicks=[{"at": 2, "on": "go"}], swaps=[{"at": 3, "shot": "V12_docs"}],
      camera=[{"at": 4, "to": ["V12_docs.counts", "V12_docs.row"], "pad": 30}],
      marks=[{"at": 5, "until": 8, "on": "V12_docs.counts", "label": "비일상 10건 · 일상 40건"}, {"at": 8, "on": "V12_docs.row", "label": "0731 화기 작업"}], beats=14),
    D("v12", 31, "home_p1", "V12_home", camera=[{"at": 1, "to": ["nav", "res"], "pad": 20}],
      marks=[{"at": 2, "until": 5, "on": "pri", "label": "순위별 위험 쌍"}, {"at": 5, "until": 7, "on": "p1tab", "label": "1순위 · 즉시 조정"},
             {"at": 8, "on": "V12_p1.pair", "label": "P02 · 0731 × WP-01"}],
      clicks=[{"at": 6.5, "on": "p1tab"}, {"at": 10.5, "on": "V12_p1.pair"}], swaps=[{"at": 7, "shot": "V12_p1"}], hat=5, beats=12),
    D("v12", 32, "pair_time", "V12_pair", camera=[{"at": 1, "to": B(1079, 430, 796, 196), "pad": 30}],
      marks=[{"at": 2, "until": 5, "on": "where", "label": "3BAY 08–10 · 같은 블록 E42P"}, {"at": 5, "on": TL, "label": "13:30–15:00 · 90분 겹침"}], beats=12),
    D("v12", 33, "pair_why", "V12_pair", camera=[{"at": 1, "to": "why", "pad": 30}],
      marks=[{"at": 2, "until": 5, "on": "flow", "label": "주는 작업 → 받는 작업"}, {"at": 5, "on": "acc", "label": "예상 사고 경로"}], beats=12),
])

# ---- V13 판정에 사용한 서류로 돌아가기 ----
SPECS["v13"] = spec("croScan V13 · 판정에 사용한 서류로 돌아가기", [
    D("v13", 34, "jd", "V13_jd", camera=[{"at": 1, "to": B(1079, 262, 796, 455), "pad": 20}],
      marks=[{"at": 2, "until": 5, "on": "time", "label": "판정 근거·원문"}, {"at": 5, "on": "evs", "label": "판정에 쓴 시간·위치"}], beats=10),
    D("v13", 35, "docs", "V13_docWP", camera=[{"at": 1, "to": "panel", "pad": 10}, {"at": 3, "to": "both", "pad": 60}, {"at": 8, "to": B(1105, 712, 791, 114), "pad": 60}],
      marks=[{"at": 4, "until": 7, "on": "both", "label": "WP-01 계획서: 13:30~15:00 · 3BAY 08-10 E42P"},
             {"at": 9, "until": 11.5, "on": B(1105, 712, 791, 36), "label": "0731 허가서 원본 장소: 팀 이름"},
             {"at": 11.5, "on": B(1105, 749, 791, 77), "label": "0731 반장 답 반영: 위치 · 13:00–15:00"}],
      swaps=[{"at": 7, "shot": "V13_doc0731"}], beats=18),
])

# ---- V14 필요한 설명을 직접 질문 ----
Q = "왜 1순위인가요?"
SPECS["v14"] = spec("croScan V14 · 필요한 설명을 직접 질문", [
    D("v14", 36, "ask", "V14_ask0", camera=[{"at": 1, "to": "why", "pad": 60}],
      marks=[{"at": 2, "until": 7, "on": "form", "label": "이 판정에 대해 묻기"}, {"at": 7, "on": "V14_typed.ask", "label": "묻기"}],
      typing=[{"at": 3, "until": 6.5, "title": "입력 내용 재현 · 실제 입력한 질문", "text": Q, "done": 5}],
      swaps=[{"at": 6.5, "shot": "V14_typed"}], clicks=[{"at": 8.5, "on": "V14_typed.ask"}], hat=2.5, beats=10),
    D("v14", 37, "answer", "V14_wait", camera=[{"at": 0, "to": B(1079, 700, 796, 180), "pad": 40}, {"at": 3, "to": B(1079, 318, 796, 460), "pad": 20}],
      marks=[{"at": 0.5, "until": 2.5, "on": B(1097, 828, 778, 26), "label": "AI가 판정 근거에서 답을 고르는 중"},
             {"at": 4, "until": 7, "on": "V14_done.judge", "label": "AI가 질문을 이 설명으로 읽음"},
             {"at": 7, "until": 10, "on": "V14_done.facts", "label": "사용한 사실"}, {"at": 10, "on": "V14_done.left", "label": "아직 확인할 것"}],
      swaps=[{"at": 2.5, "shot": "V14_done"}], hat=4.5, beats=16),
])

# ---- V15 선택적 AI 추가 검토 (별도 작업쌍) ----
KV15 = K("추가 검토 예시 · 별도 작업쌍 0738 × WP-22")
SPECS["v15"] = spec("croScan V15 · 선택적 AI 추가 검토", [
    D("v15", 38, "request", "V15_near", camera=[{"at": 1, "to": "row", "pad": 80}, {"at": 4.5, "to": B(1079, 440, 796, 490), "pad": 20}],
      marks=[{"at": 1.5, "until": 3.5, "on": "row", "label": "검토 통과 인접 작업"}, {"at": 5.5, "until": 8, "on": "V15_pair.why", "label": "경보 없음 · 검토 통과 근거"},
             {"at": 8, "on": "V15_pair.btn", "label": "AI 검토 요청"}],
      clicks=[{"at": 3.5, "on": "row"}, {"at": 11, "on": "V15_pair.btn"}], swaps=[{"at": 4, "shot": "V15_pair"}], cues=KV15, hat=8.5, beats=12),
    D("v15", 39, "result", "V15_wait", camera=[{"at": 0, "to": "rv", "pad": 40}, {"at": 3.5, "to": "V15_done.rv", "pad": 30}],
      marks=[{"at": 0.5, "until": 3, "on": "out", "label": "실제 약 30초 걸림 · 기다린 구간 줄임"},
             {"at": 4.5, "until": 7.5, "on": B(1090, 912, 774, 48), "label": "근거 부족으로 보류"}, {"at": 7.5, "on": "V15_done.ev", "label": "AI가 대조한 두 서류의 행"}],
      swaps=[{"at": 3, "shot": "V15_done"}], cues=KV15, hat=5, beats=14),
])

# ---- V16 같은 시각의 배치 ----
TIMEBOX = B(324, 196, 214, 74)
SPECS["v16"] = spec("croScan V16 · 조율 전에 같은 시각의 배치 확인", [
    D("v16", 40, "tomap", "V16_pair", camera=[{"at": 1, "to": "where", "pad": 60}, {"at": 4.5, "to": B(324, 160, 1530, 180), "pad": 20}],
      marks=[{"at": 2, "until": 4, "on": "tomap", "label": "배치도에서 보기"}, {"at": 5.5, "on": TIMEBOX, "label": "선택 시각 13:30"}],
      clicks=[{"at": 3.5, "on": "tomap"}], swaps=[{"at": 4, "shot": "V16_map"}], hat=6, beats=12),
    D("v16", 41, "map", "V16_map", camera=[{"at": 0.5, "to": "grid", "pad": 20}, {"at": 3, "to": "pair", "pad": 150}],
      marks=[{"at": 1.5, "until": 3.5, "on": B(309, 590, 1562, 82), "label": "3BAY"}, {"at": 4, "on": "pair", "label": "0731 화기 · WP-01 도장 · 08–10칼럼"}], hat=4.5, beats=14),
])

# ---- V17 협조 문자 ----
KV17 = K("다른 작업쌍 예시 · P22 (0735 × WP-08)")
MSG02 = B(1105, 643, 791, 240)
SPECS["v17"] = spec("croScan V17 · 작업 조율 협조 문자 작성과 복사", [
    D("v17", 42, "p02", "V17_filled", camera=[{"at": 1, "to": "who", "pad": 30}, {"at": 5, "to": B(1105, 620, 791, 320), "pad": 30}],
      marks=[{"at": 2, "until": 5, "on": "who", "label": "받는 사람 · 협의 상대 (이름·번호 가림)"}, {"at": 6, "until": 9, "on": MSG02, "label": "겹치는 시간·위치·요청"},
             {"at": 9, "on": B(1105, 892, 791, 40), "label": "P02: 확인된 반장 답이 없어 협의할 점 제안 없음"}], beats=14),
    D("v17", 43, "note", "V17_ex_note", camera=[{"at": 1, "to": "note", "pad": 40}],
      marks=[{"at": 2, "until": 5, "on": B(1105, 828, 791, 56), "label": "협의할 점 (제안) · AI 초안"}, {"at": 5, "on": "src", "label": "출처: 0735 반장 확인 답"}], cues=KV17, beats=10),
    D("v17", 44, "put", "V17_ex_note", camera=[{"at": 0.5, "to": B(1105, 614, 791, 360), "pad": 20}, {"at": 3.5, "to": B(1105, 505, 791, 250), "pad": 30}],
      marks=[{"at": 1, "until": 2.5, "on": "put", "label": "문자에 넣기"}, {"at": 4.5, "on": B(1113, 660, 775, 56), "label": "추가된 문장"}],
      clicks=[{"at": 2.5, "on": "put"}], swaps=[{"at": 3, "shot": "V17_ex_added"}], cues=KV17, hat=5, beats=10),
    D("v17", 45, "copy", "V17_ex_added", camera=[{"at": 0.5, "to": B(1105, 950, 791, 120), "pad": 30}, {"at": 3.5, "to": "V17_ex_copied.toast", "pad": 80}],
      marks=[{"at": 1, "until": 3, "on": "copy", "label": "문자 복사"}, {"at": 4.5, "on": "V17_ex_copied.toast", "label": "실제 복사 결과 · 보내지는 않음"}],
      clicks=[{"at": 2.5, "on": "copy"}], swaps=[{"at": 3, "shot": "V17_ex_copied"}], cues=KV17, hat=5, beats=12),
])

# ---- V18 AI 게시 문안과 별지 반영 ----
ROWS = B(1106, 141, 789, 107)
SPECS["v18"] = spec("croScan V18 · AI의 현장 게시 내용 작성과 별지 반영", [
    D("v18", None, "open", "V18_issue", camera=[{"at": 1, "to": "card", "pad": 30}, {"at": 4.5, "to": B(1106, 105, 789, 370), "pad": 20}],
      marks=[{"at": 2, "until": 4, "on": "prev", "label": "0731 미발행 별지 · 미리 보기·편집"}, {"at": 5.5, "on": "V18_sheet.aigo", "label": "AI 문안 보충 보기"}],
      clicks=[{"at": 3.5, "on": "prev"}, {"at": 7, "on": "V18_sheet.aigo"}], swaps=[{"at": 4, "shot": "V18_sheet"}], beats=10),
    D("v18", 46, "draft", "V18_wait", camera=[{"at": 0, "to": B(1106, 380, 789, 330), "pad": 20}],
      marks=[{"at": 0.5, "until": 1.5, "on": B(1106, 419, 789, 40), "label": "AI 문안 준비 중"}, {"at": 2.5, "on": "V18_draft.lines", "label": "AI 초안"}],
      swaps=[{"at": 1.5, "shot": "V18_draft"}], hat=3, beats=10),
    D("v18", 47, "source", "V18_draft", camera=[{"at": 0.5, "to": "src", "pad": 50}],
      marks=[{"at": 1.5, "on": "src", "label": "근거: 규칙 문구 2건"}], beats=8),
    D("v18", 48, "take", "V18_draft", camera=[{"at": 0.5, "to": B(1106, 105, 789, 600), "pad": 20}, {"at": 3.5, "to": ROWS, "pad": 50}],
      marks=[{"at": 1, "until": 2.5, "on": "take", "label": "문안 채택"}, {"at": 4.5, "on": ROWS, "label": "바뀐 칸: 우리 반이 할 일 · 착수조건"}],
      clicks=[{"at": 2.5, "on": "take"}], swaps=[{"at": 3, "shot": "V18_taken"}], hat=5, beats=12),
])

# ---- V19 발행 → 할 일 · 착수조건 · 중지조건 ----
SPECS["v19"] = spec("croScan V19 · 우리 반의 할 일·착수조건·중지조건 확인", [
    D("v19", 49, "publish", "V19_before", camera=[{"at": 1, "to": "card", "pad": 30}],
      marks=[{"at": 2, "until": 3.5, "on": "pub", "label": "발행"}, {"at": 5, "on": "V19_issued.issued", "label": "S-0731/R1 발행"}],
      clicks=[{"at": 3, "on": "pub"}], swaps=[{"at": 3.5, "shot": "V19_issued"}], hat=5.5, beats=12),
    D("v19", 50, "todo", "V19_view", camera=[{"at": 0.5, "to": "sheet", "pad": 10}, {"at": 3, "to": ROWS, "pad": 50}],
      marks=[{"at": 1.5, "until": 3, "on": B(1105, 74, 300, 22), "label": "발행본 S-0731/R1"},
             {"at": 4, "until": 7, "on": B(1106, 141, 789, 53), "label": "우리 반이 할 일"}, {"at": 7, "on": B(1106, 194, 789, 54), "label": "착수조건"}], hat=4.5, beats=12),
    D("v19", 51, "stop", "V19_view", camera=[{"at": 0.5, "to": B(1106, 355, 789, 50), "pad": 70}, {"at": 6, "to": "sheet", "pad": 10}],
      marks=[{"at": 1.5, "until": 6, "on": B(1106, 365, 789, 30), "label": "중지·해제 조건"}, {"at": 7, "on": B(1106, 141, 789, 254), "label": "할 일 · 착수조건 · 중지·해제 조건"}], hat=2, beats=12),
])

NEED = {}
for name, s in SPECS.items():
    d = S / name
    (d / "public" / "shots").mkdir(parents=True, exist_ok=True)
    (d / "public" / "music").mkdir(parents=True, exist_ok=True)
    shutil.copy(WORK / "groove.mp3", d / "public" / "music" / "groove.mp3")
    used = set()
    for sc in s["scenes"]:
        used.add(sc["shot"]); used.update(x["shot"] for x in sc["swaps"])
        for k in ("camera", "marks", "clicks"):
            for x in sc[k]:
                refs = x.get("to", x.get("on"))
                for r in refs if isinstance(refs, list) else [refs]:
                    if isinstance(r, str) and "." in r:
                        used.add(r.split(".")[0])
    for f in used:
        shutil.copy(CAP / f"{f}.png", d / "public" / "shots" / f"{f}.png")
    shutil.copy(CAP / "rects.json", d / "public" / "shots" / "rects.json")
    (d / "prai.json").write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")
# seconds: every scene is `beats` long at BPM (no gaps in a demo-only spec)
sec = 60 / BPM
for proj, rows in SCENEMAP.items():
    t = 0
    for r in rows:
        r["start_s"] = round(t * sec, 2)
        if r["caption"]:
            r["cap_start_s"] = round((t + r["hat"]) * sec, 2)
            r["cap_end_s"] = round((t + r["beats"]) * sec, 2)
        t += r["beats"]
    rows.append({"total_s": round(t * sec, 2)})
(S / "scenemap19.json").write_text(json.dumps(SCENEMAP, ensure_ascii=False, indent=1), encoding="utf-8")
print("specs:", ", ".join(SPECS), {p: r[-1]["total_s"] for p, r in SCENEMAP.items()})
