"""Write the PRAI projects v01..v11 (foreman clips V01–V11, captions 1–29) and scenemap19.json.
Captions are the confirmed wording, read from the caption file and never changed. One caption and one mark at a time.
Result captions start half a beat after the first mark on the real result; preview captions (7, 8, 10, 19) come before the action.
2026-11-02 15h conti (21 clips / 57 captions): V05–V11 continue from the typo answer (take B); take A is used only in V03
(and V04 for the comparison with the earlier answer).
usage: python build_specs19.py   (after assemble19.py)
"""
import json
import re
from pathlib import Path

W = Path(__file__).parent
C = json.loads((W.parent.parent / "work" / "common.json").read_text(encoding="utf-8"))
SUBS = W.parent / "croScan_최종자막_57개_수정반영본_2026-11-02.md"
URL = "위험작업 허가서 사전검토 · 스테이징 화면"
SAY = {k: re.search(k + r': "([^"]+)"', (W / "foreman19.mjs").read_text(encoding="utf-8")).group(1) for k in ("A", "B")}
R = json.loads((W / "allrects.json").read_text(encoding="utf-8"))
LOG = {k: {e["k"]: e["v"] for e in json.loads((W / f"cap{k}" / f"log_{k}.json").read_text(encoding="utf-8"))["events"]} for k in "AB"}
BPM = C["music"]["bpm"]

# the confirmed captions (main, sub), word for word from the 57-caption file; "—" = no sub
CAP = {}
for line in SUBS.read_text(encoding="utf-8").splitlines():
    m = re.match(r"\|\s*(\d+)\s*\|\s*V\d+B?-\d+\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*$", line)
    if m:
        CAP[int(m.group(1))] = (m.group(2), None if m.group(3) == "—" else m.group(3))
assert len(CAP) == 57, len(CAP)
# the facts the result captions claim, checked against the real logs before anything is written
A, Bl = LOG["A"], LOG["B"]
assert "13:00~15:00" in A["card"] and "13:00~15:00" in Bl["card"]                    # 9, 11 (sub 13:00~15:00)
assert Bl["fixed"] is True                                                           # 13: a value was really fixed (take B)
assert "사례집" in Bl["why_case_line"]                                                # 23: a real, sourced case
assert "KOSHA" in Bl["refs_question"]                                                # 24/25: real searched passages
assert "안전팀에 제출했습니다" in Bl["sent"]                                             # 27
SUBMISSION = Bl["submission"]["id"]
TAIL_B = re.search(r"상부(\S)\s*$", Bl["fix_before"]).group(1)                         # the spoken ending left in the place (구)
AI_OK = isinstance(Bl.get("cand_pick"), dict) and Bl["cand_pick"].get("mark")
V08 = "B" if AI_OK else "A"                                                          # take B's checklist AI failed → V08 from take A (labelled)
CP = LOG[V08]["cand_pick"]["text"]
QM = re.search(r"같은 근거 「(.+?)」\((.+?)\)", CP)
QUOTE, QSRC = (QM.group(1), QM.group(2)) if QM else ("", "")
SPECS, SCENEMAP = {}, {}


def B(x, y, w, h):
    return {"box": [x, y, w, h]}


def D(proj, cap, id, shot, camera=None, marks=None, clicks=None, swaps=None, typing=None, cues=None, beats=0, hat=None, note=None):
    """one scene. cap = caption number (None: no caption). The caption starts half a beat after the first mark unless hat is given,
    and stays at least 5 beats (3 s at 100 BPM); scenes are an even number of beats."""
    marks = marks or []
    first = min(m["at"] for m in marks) if marks else 1
    if cap is not None and hat is None:
        hat = first + 0.5
    last = max([m.get("until", m["at"] + 2) for m in marks] + [c["at"] + 1.5 for c in camera or []] + [k["at"] + 1.5 for k in clicks or []]
               + [t["until"] for t in typing or []] + [s["at"] + 1.5 for s in swaps or []] + [4])
    need = last
    if cap is not None:
        need = max(need, hat + 5)
    b = max(beats, need)
    b = int(-(-b // 2) * 2)
    d = {"id": id, "type": "demo", "shot": shot, "url": URL, "camera": camera or [], "marks": marks, "clicks": clicks or [], "swaps": swaps or [],
         "typing": typing or [], "cues": cues or [], "beats": b}
    if cap is not None:
        main, sub = CAP[cap]
        d["headline"] = {"text": main, **({"sub": sub} if sub else {}), "at": hat}
    SCENEMAP.setdefault(proj, []).append({"scene": id, "caption": cap, "hat": hat if cap is not None else None, "beats": b,
                                          "headline": CAP[cap][0] if cap else None, "sub": CAP[cap][1] if cap else None,
                                          "shots": [shot] + [s["shot"] for s in swaps or []],
                                          "marks": [m.get("label") for m in marks if m.get("label")], "note": note})
    return d


def spec(title, scenes):
    s = {"$schema": "C:/Users/seoco/OneDrive/Desktop/PRAI/schema/prai.schema.json", **json.loads(json.dumps(C))}
    s["theme"].pop("logo", None)
    s["video"] = {**C["video"], "title": title}
    s["scenes"] = scenes
    return s


SEND = B(1796, 1022, 106, 46)   # 「보내기」 under the input box

# ---- V01 기존 작업계획서로 시작 ----
SPECS["v01"] = spec("croScan V01 · 기존 작업계획서로 시작", [
    D("v01", None, "login", "B_s01_login", camera=[{"at": 0.5, "to": ["roles", "go"], "pad": 80}],
      marks=[{"at": 1, "on": "foreman", "label": "현장 작업반장"}], clicks=[{"at": 2.5, "on": "go"}], beats=4),
    D("v01", 1, "pick", "B_s02_pick", camera=[{"at": 0.5, "to": ["drop", "list"], "pad": 50}],
      marks=[{"at": 1.5, "until": 5.5, "on": "list", "label": "협력사·본청 계획서 2건"}, {"at": 5.5, "on": "start", "label": "작업계획서 읽기"}],
      clicks=[{"at": 6.5, "on": "start"}], beats=8),
    D("v01", 2, "read", "B_s03_read", camera=[{"at": 0.5, "to": "full"}, {"at": 6, "to": B(60, 790, 1300, 90), "pad": 40}, {"at": 9, "to": "plan1", "pad": 60}],
      marks=[{"at": 1, "until": 3.5, "on": B(90, 250, 1220, 170), "label": "협력사 계획서 원본 양식"},
             {"at": 3.5, "until": 6, "on": "list", "label": "읽힌 작업 목록 2건"},
             {"at": 7, "until": 9, "on": B(104, 806, 1192, 66), "label": "대표 작업: 시작 13:30 · 종료 15:00"},
             {"at": 10, "on": "plan1", "label": "13:30~15:00 · 3BAY 08-10 E42P"}], hat=4, beats=14),
    D("v01", 3, "checked", "B_s05_checked", camera=[{"at": 0, "to": B(1401, 140, 519, 150), "pad": 30}],
      marks=[{"at": 0.5, "on": "checks", "label": "확인함 · 나머지 1건도 확인(축약)"}], beats=8),
    D("v01", None, "next", "B_s05_checked", camera=[{"at": 0, "to": "next", "pad": 100}],
      marks=[{"at": 0.5, "on": "next", "label": "다음: 허가서 올리기"}], clicks=[{"at": 2.5, "on": "next"}], beats=4),
])

# ---- V02 허가서 종류 소개 후 화기 선택 ----
SPECS["v02"] = spec("croScan V02 · 허가서 종류와 화기 선택", [
    D("v02", 4, "kinds", "B_s06_kinds", camera=[{"at": 0.5, "to": "kinds", "pad": 60}],
      marks=[{"at": 1, "on": "kinds", "label": "위험작업 허가서 종류 5가지"}], beats=8),
    D("v02", 5, "hot", "B_s07_ready", camera=[{"at": 0.5, "to": ["kinds", "start"], "pad": 50}],
      marks=[{"at": 1, "until": 4, "on": "hot", "label": "화기"}, {"at": 4, "on": "drop", "label": "0731 화기 허가서"}],
      clicks=[{"at": 6.5, "on": "start"}], beats=8),
    D("v02", 6, "orig", "B_s08_review", camera=[{"at": 0.5, "to": "time", "pad": 140}, {"at": 4.5, "to": "location", "pad": 140}],
      marks=[{"at": 1.5, "until": 4.5, "on": "time", "label": "08:00~16:59 · 하루 신청 시간"},
             {"at": 5.5, "on": "location", "label": "대조립3부 용접2팀 · 팀 이름"}], beats=10),
    D("v02", 7, "ask", "B_s08_review", camera=[{"at": 0.5, "to": "question", "pad": 40}],
      marks=[{"at": 1, "on": "question", "label": "첫 질문: 실제 작업시간"}], beats=8),
])

# ---- V03 시간·위치·공법이 섞인 긴 답변 (테이크 A) ----
SPECS["v03"] = spec("croScan V03 · 시간·위치·공법이 섞인 긴 답변", [
    D("v03", 8, "q", "A_s08_review", camera=[{"at": 0.5, "to": "question", "pad": 40}],
      marks=[{"at": 1, "on": "question", "label": "실제 작업시간 질문"}], beats=8, note="예고 자막: 입력 직전"),
    D("v03", None, "typed", "A_s09_typed", camera=[{"at": 0, "to": "full"}],
      typing=[{"at": 0.5, "until": 9, "title": "입력 내용 재현 · 기본 입력 (실제로 입력한 문장)", "text": SAY["A"], "done": 7}],
      marks=[{"at": 9, "until": 11, "on": "input", "label": "실제 입력칸"}], clicks=[{"at": 10.5, "on": SEND}], beats=12),
    D("v03", 9, "card", "A_s10_card", camera=[{"at": 0, "to": "card", "pad": 30}, {"at": 4, "to": ["loc"], "pad": 40}],
      marks=[{"at": 0.5, "until": 4, "on": "head", "label": f"약 {A['ai_wait_s']}초 뒤 실제 해석 결과 · 기다린 구간 줄임"},
             {"at": 4, "until": 7, "on": "time", "label": "읽은 작업시간 13:00~15:00"},
             {"at": 7, "on": B(1446, 338, 376, 78), "label": "읽은 장소 ↔ 답변 원문"}], hat=4.5, beats=12),
])

# ---- V04 같은 내용에 오타를 넣어 비교 (테이크 B, V05부터 이어짐) ----
SPECS["v04"] = spec("croScan V04 · 같은 내용에 오타를 넣어 비교", [
    D("v04", 10, "q", "B_s08_review", camera=[{"at": 0.5, "to": "question", "pad": 40}],
      marks=[{"at": 1, "on": "question", "label": "같은 질문 · 처음부터 다시 시작한 별도 촬영"}], beats=8, note="예고 자막: 입력 직전"),
    D("v04", None, "typed", "B_s09_typed", camera=[{"at": 0, "to": "full"}],
      typing=[{"at": 0.5, "until": 9, "title": "입력 내용 재현 · 오타 3곳: 자겁 · 상부구요 · 예정임니다", "text": SAY["B"], "done": 7}],
      marks=[{"at": 9, "until": 11, "on": "input", "label": "실제 입력칸"}], clicks=[{"at": 10.5, "on": SEND}], beats=12),
    D("v04", 11, "card", "B_s10_card", camera=[{"at": 0, "to": "card", "pad": 30}],
      marks=[{"at": 0.5, "until": 3, "on": "head", "label": f"약 {Bl['ai_wait_s']}초 뒤 실제 해석 결과 · 기다린 구간 줄임"},
             {"at": 3, "until": 6.5, "on": "time", "label": "오타 입력: 13:00~15:00"},
             {"at": 7, "until": 9.5, "on": "A_s10_card.time", "label": "앞의 기본 입력: 13:00~15:00"},
             {"at": 10.5, "on": "time", "label": "오타 입력 결과로 이어서 진행"}],
      swaps=[{"at": 6.5, "shot": "A_s10_card"}, {"at": 10, "shot": "B_s10_card"}], hat=3.5, beats=14),
])

# ---- V05 어떻게 읽었는지 보고 반영 (테이크 B) ----
SPECS["v05"] = spec("croScan V05 · 어떻게 읽었는지 보고 반영", [
    D("v05", 12, "compare", "B_s10_card", camera=[{"at": 0, "to": "loc", "pad": 40}],
      marks=[{"at": 0.5, "until": 3, "on": B(1446, 338, 376, 50), "label": f"읽은 값 · 끝에 「{TAIL_B}」가 붙음"},
             {"at": 3, "until": 5.5, "on": "quote", "label": "오타 답변 원문"},
             {"at": 5.5, "on": "dest", "label": "들어갈 칸: 작업장소"}], beats=12),
    D("v05", 13, "fix", "B_s11_fix", camera=[{"at": 0, "to": ["loc", "fixrow"], "pad": 30}, {"at": 5, "to": "B_s13_applied.card", "pad": 30}],
      marks=[{"at": 0.5, "until": 3.5, "on": "fixrow", "label": f"항목 고치기: 「상부{TAIL_B}」 → 「상부」"},
             {"at": 3.5, "until": 5, "on": "save", "label": "이 값으로 답하기"},
             {"at": 5.5, "on": B(1438, 240, 388, 120), "label": "반장이 확인한 우리 작업 정보"}],
      clicks=[{"at": 4.5, "on": "save"}], swaps=[{"at": 5, "shot": "B_s13_applied"}], beats=12),
    D("v05", 14, "applied", "B_s13_applied", camera=[{"at": 0, "to": "full"}, {"at": 2, "to": "detail", "pad": 90}],
      marks=[{"at": 3, "on": "detail", "label": "② 실제 작업 예정 13:00~15:00, CO2 (파란 글씨)"}], beats=10),
])

# ---- V06 다음 단계 전에 핵심정보 재확인 ----
SPECS["v06"] = spec("croScan V06 · 다음 단계 전에 핵심정보 재확인", [
    D("v06", None, "next", "B_s14_done", camera=[{"at": 0.5, "to": "next", "pad": 120}],
      marks=[{"at": 1, "on": "next", "label": "다음: 위험 체크리스트"}], clicks=[{"at": 2.5, "on": "next"}], beats=4),
    D("v06", 15, "popup", "B_s15_popup", camera=[{"at": 0, "to": "dialog", "pad": 20}],
      marks=[{"at": 0.5, "until": 3, "on": B(664, 507, 592, 36), "label": "작업시간 10/29 13:00~15:00"},
             {"at": 3, "until": 5.5, "on": B(664, 543, 592, 36), "label": "작업 위치 3BAY 08~10칼럼 E42P 블록 상부"},
             {"at": 5.5, "on": B(664, 578, 592, 58), "label": "작업 내용"}], beats=12),
    D("v06", 16, "unknown", "B_s15_popup", camera=[{"at": 0, "to": "dialog", "pad": 20}],
      marks=[{"at": 0.5, "until": 4, "on": "open", "label": "모름 2건 · 안전팀 확인으로 넘어감"},
             {"at": 4, "until": 6, "on": "ok", "label": "확인하고 체크리스트로"},
             {"at": 7, "on": "B_s16_check.bar", "label": "4단계 위험 체크리스트"}],
      clicks=[{"at": 5.5, "on": "ok"}], swaps=[{"at": 6.5, "shot": "B_s16_check"}], beats=12),
])

# ---- V07 대표 위험과 준비할 조치 ----
SPECS["v07"] = spec("croScan V07 · 대표 위험과 준비할 조치", [
    D("v07", None, "list", "B_s16_check", camera=[{"at": 0.5, "to": "bar", "pad": 60}],
      marks=[{"at": 1, "on": "bar", "label": "28개 항목 · 해당 12 · 안전팀 확인 16"}], beats=4),
    D("v07", 17, "fire", "B_s17_fire", camera=[{"at": 0, "to": B(610, 174, 700, 220), "pad": 20}],
      marks=[{"at": 0.5, "until": 3, "on": "head", "label": "01 불티가 아래·틈새로 번져 화상·화재"},
             {"at": 3, "on": "reason", "label": "제안 「해당」 · 근거: 허가서 「용접·용단」 칸 (서류)"}], hat=3.5, beats=12),
    D("v07", 18, "controls", "B_s17_fire", camera=[{"at": 0, "to": B(610, 390, 700, 440), "pad": 20}],
      marks=[{"at": 0.5, "until": 4, "on": "ctl1", "label": "준비할 안전조치"},
             {"at": 5.5, "on": "B_s18_fire_done.ctlok", "label": "준비할 안전조치 확인함"}],
      clicks=[{"at": 4, "on": "ok"}, {"at": 4.5, "on": "ctlok"}], swaps=[{"at": 5, "shot": "B_s18_fire_done"}], beats=12),
])

# ---- V08 AI의 보완 제안 ----
c19, c20 = f"{V08}_s19_cand", f"{V08}_s20_adopted"
seg = R[c19]["seg"]
OKBOX = B(seg["x"], seg["y"] + 58, seg["w"], 60)
KV08 = [{"block": "kicker", "text": "이 장면만 앞의 기본 입력 촬영 · 오타 입력 촬영에서는 AI 결과를 준비하지 못함", "tone": "brand", "at": 0, "y": 58,
         "enter": "cut"}] if V08 == "A" else []
SPECS["v08"] = spec("croScan V08 · AI의 보완 제안", [
    D("v08", 19, "ai", c19, camera=[{"at": 0, "to": B(610, R[c19]["head"]["y"] - 25, 700, 230), "pad": 20}],
      marks=[{"at": 0.5, "on": "chip", "label": "AI 제안"}], cues=KV08, hat=1, beats=8, note="실제 AI 제안 줄이 보일 때"),
    D("v08", 20, "quote", c19, camera=[{"at": 0, "to": "reason", "pad": 60}],
      marks=[{"at": 0.5, "on": "reason", "label": f"근거: 「{QUOTE}」({QSRC})"}], cues=KV08, beats=10),
    D("v08", 21, "choose", c19, camera=[{"at": 0, "to": B(610, seg["y"] - 12, 700, 140), "pad": 30}],
      marks=[{"at": 0.5, "until": 3.5, "on": "seg", "label": "해당 · 해당 없음 · 안전팀 확인"},
             {"at": 4.5, "on": OKBOX, "label": "반장이 「해당」으로 확인"}],
      clicks=[{"at": 3.5, "on": OKBOX}], swaps=[{"at": 4, "shot": c20}], cues=KV08, beats=10),
])

# ---- V09 이 위험을 확인하는 이유 ----
SPECS["v09"] = spec("croScan V09 · 이 위험을 확인하는 이유", [
    D("v09", 22, "why", "B_s18_fire_done", camera=[{"at": 0, "to": B(610, 174, 700, 160), "pad": 30}, {"at": 2.5, "to": "B_s21_why.out", "pad": 20}],
      marks=[{"at": 0.5, "until": 2, "on": "xwhy", "label": "위험한 이유 보기"},
             {"at": 3, "until": 5.5, "on": "B_s21_why.facts", "label": "이번 작업에서 사용한 사실"},
             {"at": 5.5, "until": 8.5, "on": B(623, 494, 677, 26), "label": "적용한 기준: 체크리스트 명세"},
             {"at": 8.5, "on": "B_s21_why.left", "label": "아직 확인할 것: 조치 이행은 현장에서 따로 확인"}],
      clicks=[{"at": 1.5, "on": "xwhy"}], swaps=[{"at": 2, "shot": "B_s21_why"}], hat=3.5, beats=14),
    D("v09", 23, "case", "B_s21_why", camera=[{"at": 0, "to": "case", "pad": 60}],
      marks=[{"at": 0.5, "until": 5, "on": "case", "label": "출처: 조선업 중대재해 사례집 86쪽"},
             {"at": 5, "on": B(637, 528, 667, 66), "label": "연결된 참고 사고 사례 3건"}], beats=10),
])

# ---- V10 관련 자료와 출처 확인 ----
SPECS["v10"] = spec("croScan V10 · 관련 자료와 출처 확인", [
    D("v10", None, "back", "B_s22_back", camera=[{"at": 0, "to": "stepper", "pad": 40}, {"at": 3, "to": "B_s23_refs.q", "pad": 30}],
      marks=[{"at": 0.5, "until": 2.5, "on": "stepper", "label": "허가서 검토 화면으로 돌아옴"},
             {"at": 3.5, "on": "B_s23_refs.need", "label": "작업시간 질문의 「왜 묻나요?」 자료"}],
      swaps=[{"at": 2.5, "shot": "B_s23_refs"}], beats=6),
    D("v10", 24, "refs", "B_s23_refs", camera=[{"at": 0, "to": "box", "pad": 30}],
      marks=[{"at": 0.5, "on": B(1448, 474, 368, 260), "label": "관련 자료 · 검색 후보 2건(근거 확정 아님)"}], beats=8),
    D("v10", 25, "source", "B_s23_refs", camera=[{"at": 0, "to": "ref1", "pad": 40}],
      marks=[{"at": 0.5, "until": 3.5, "on": "src", "label": "출처: KOSHA A-G-14-2026 6쪽 · 검수 전"},
             {"at": 3.5, "on": "text", "label": "원문 구절"}], beats=10),
    D("v10", None, "closed", "B_s24_refs_closed", camera=[{"at": 0, "to": "q", "pad": 40}],
      marks=[{"at": 0.5, "on": "q", "label": "자료를 닫고 검토 화면으로"}], beats=4),
])

# ---- V11 확인 마침 → 제출 → 반영본과 추가검토서 → 0731의 확인된 시간·위치 ----
P1, P2 = R["PDF_p1"], R["PDF_p2"]
P2LINES = [t for t, _ in json.loads((W / "pdfshots" / "pdfinfo.json").read_text(encoding="utf-8"))["PDF_p2"]["boxes"]["lines"]]


def U(*boxes):
    xs = [b["x"] for b in boxes]; ys = [b["y"] for b in boxes]
    x2 = [b["x"] + b["w"] for b in boxes]; y2 = [b["y"] + b["h"] for b in boxes]
    return B(min(xs) - 4, min(ys) - 3, max(x2) - min(xs) + 8, max(y2) - min(ys) + 6)


def li(prefix, after=0):
    return next(j for j, t in enumerate(P2LINES) if j >= after and t.startswith(prefix))


L = lambda a, b: U(*[P2[f"l{i}"] for i in range(a, b + 1)])
s2, s3, s4 = li("2. 양식 밖"), li("3. 확인된"), li("4. 안전팀")
iAI = li("AI 분석", s4)
iTime, iLoc, iCmp = li("위험시간대", s3), li("위치", s3), li("대상·설비", s3)
TIMEB = U(P1["t0800"], P1["t1659"])
SPECS["v11"] = spec("croScan V11 · 확인 마침, 제출, 반영본과 추가검토서", [
    D("v11", 26, "finish", "B_s25_mid", camera=[{"at": 0, "to": "bar", "pad": 40}, {"at": 3.5, "to": "full"}],
      marks=[{"at": 0.5, "until": 3, "on": "next", "label": "다음 미완료로 이동 · 반복 확인 구간 줄임"},
             {"at": 4, "until": 6.5, "on": "B_s26_done.bar", "label": "28 / 28 확인 완료"},
             {"at": 6.5, "on": "B_s26_done.next", "label": "다음: 제출 확인"}],
      swaps=[{"at": 3.5, "shot": "B_s26_done"}], hat=4.5, beats=10),
    D("v11", None, "summary", "B_s27_submit", camera=[{"at": 0, "to": B(641, 590, 638, 270), "pad": 30}],
      marks=[{"at": 0.5, "on": B(641, 585, 638, 280), "label": "제출 전 요약 · 모름 2건 · AI 미완료 1건도 함께"}], beats=6),
    D("v11", 27, "sent", "B_s28_sent", camera=[{"at": 0, "to": B(641, 630, 638, 440), "pad": 20}],
      marks=[{"at": 0.5, "until": 2.5, "on": B(850, 642, 428, 62), "label": "안전팀에 제출"},
             {"at": 3, "on": "id", "label": f"실제 제출 완료 · 제출본 {SUBMISSION[:6]} (전산·결재로 보내지 않음)"}],
      clicks=[{"at": 2, "on": B(850, 642, 428, 62)}], hat=3.5, beats=10),
    D("v11", 28, "permit", "PDF_p1", camera=[{"at": 0, "to": "page", "pad": 10}, {"at": 2, "to": U(P1["blue1"], P1["blue3"]), "pad": 60}],
      marks=[{"at": 3, "until": 6, "on": U(P1["blue1"], P1["blue2"]), "label": "① 작업장소: 반장 답"},
             {"at": 6, "on": U(P1["blue3"], P1["blue4"]), "label": "② 작업내용(상세): 실제 작업시간·CO2"}], beats=10),
    D("v11", 29, "extra", "PDF_p2", camera=[{"at": 0, "to": "page", "pad": 10}, {"at": 2, "to": L(s2, iAI), "pad": 40}],
      marks=[{"at": 3, "until": 6, "on": L(s2, s3 - 1), "label": "양식 밖 보충: 반장 답"},
             {"at": 6, "on": L(s4, iAI), "label": "안전팀 확인 필요: 모름 2건 · AI 미완료 1건"}], beats=12),
    D("v11", None, "range", "PDF_p1", camera=[{"at": 0, "to": TIMEB, "pad": 120}, {"at": 3, "to": L(0, 6), "pad": 40}, {"at": 6, "to": L(s3, iCmp + 2), "pad": 40}],
      marks=[{"at": 0.5, "until": 2.5, "on": TIMEB, "label": "원래 신청시간 08:00~16:59 (원본 칸 그대로)"},
             {"at": 3.5, "until": 6, "on": L(1, 2), "label": "같은 작업 0731"},
             {"at": 6.5, "until": 9.5, "on": L(iTime, iTime + 2), "label": "반장이 확인한 실제 작업시간 13:00~15:00"},
             {"at": 9.5, "on": L(iLoc, iCmp + 2), "label": "확인된 위치 3BAY 08~10칼럼 · E42P"}],
      swaps=[{"at": 3, "shot": "PDF_p2"}], beats=14, note="역할 전환 직전: 0731 · 원래 신청시간과 확인된 실제 시간 구분"),
])

for name, s in SPECS.items():
    d = W / name
    d.mkdir(exist_ok=True)
    (d / "prai.json").write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")
# seconds: every scene is `beats` long at BPM; a caption runs from its start to the end of its scene
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
meta = {"submission": SUBMISSION, "v08_take": V08, "v08_quote": [QUOTE, QSRC], "tail_b": TAIL_B}
(W / "scenemap19.json").write_text(json.dumps({"meta": meta, **SCENEMAP}, ensure_ascii=False, indent=1), encoding="utf-8")
print("specs:", ", ".join(f"{k} {v[-1]['total_s']}s" for k, v in SCENEMAP.items()), meta)
