"""사전검토 반영본 (QA #37): what the 작업반장 said goes into the form field it belongs to, the rest to the 별지.

The uploaded file is never changed. The submitted PDF is a derived copy: the original pages with the values that fit
written into their fields (blue, with a change number), then the 별지 (addendum.py). One plan, computed here from the
fields and the answers, is used by the web preview, the PDF and the 별지, so the three always agree.

How an answer is placed is decided by what the question asked (item·choice: its meaning) and what the field is for,
never by the button's status word or by the question's keys (those only mark where the question points):
- fields croScan never writes: the day-of-work boxes (작업당일 체크·현장 안전조치·추가정보 수치), signatures, approvals,
  허가구분·2중점검, check boxes and images (also when edited on screen: then it is listed as not reflected);
- three kinds of information: what an empty field lacks (it fills that field — an answer about the work itself fills an
  empty 작업내용, about the place an empty or team-name 작업장소), what adds to a filled field (the 상세 row below it,
  after what is there, the repeated part left out), and what has no field (the 별지);
- the 신청 작업일시 changes only on a 「잘못 적음」 correction of that row (T5) or when it was empty (T0); an actual or
  stage working window is a supplement in 작업내용(상세) ('실제 작업 예정 …'), the 신청 time stays;
- what contradicts the permit (러그 없음 ↔ 러그 절단, 반전 없음 ↔ 반전) is not added: it is listed to be checked;
- 「모름」 is written nowhere: it is listed as what is to be checked, and a value that only says 「모름/미정」 is not one;
- another team's work (병행작업 details, work inside a block to be lifted) is never put in this permit's own fields;
- if it does not fit at the form's size it goes to the next field for it (작업내용 → 상세) or the 별지.
"""
import re

import pymupdf

from . import augment as A

FONT_FILES = [("/usr/share/fonts/truetype/nanum/NanumGothic.ttf"), ("C:/Windows/Fonts/malgun.ttf")]
BLUE = (0.05, 0.27, 0.78)
MIN_SIZE = 7.0            # the form prints at 8–8.5pt: smaller than this goes to the 별지 rather than into the field
MARKS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
# never written by croScan, whatever the source
NEVER = set(A.DAY_OF_VALUES) | set(A.NOT_FOREMAN) | {"req_sign", "app_name", "app_date", "app_sign", "face_name",
                                                     "face_date", "face_sign", "extra_measures"}
NOT_A_VALUE = A.NOT_A_VALUE
# a 「추가로 적은 내용이 맞음」 answer (C5.X free) replaces the earlier 'none' answer of X with its positive choice
POSITIVE = {"B3": "yes", "LI2": "text", "CF2": "text", "LO4": "text"}
# what a 「모름」 leaves to be checked, per question (said as the thing to check, not as 「모름」)
CHECK = {"T0": "작업 날짜·시작·종료 시각", "T1": "실제 작업 시간", "T2": "날짜별 작업 시간", "T5": "종료 시각", "T6": "작업시간의 범위(전체/특정 단계)",
         "L1": "실제 작업장소", "L3": "작업 높이·상하 위치", "L5": "출발·경유·도착 위치", "L7": "실제 작업 위치", "D1": "작업 대상(블록·배관)",
         "H1": "보수 범위·개수", "H2": "절단·용접 방법과 사용 가스", "H3": "분리물 지지·회수 계획", "CF1": "내부 작업 목적·횟수",
         "CF2": "가스·공기 연결 계통과 차단 계획", "HT1": "러그 제거 여부·수량·절단 방법", "HT2": "러그 회수 방법·내릴 곳·하부 통제",
         "LI1": "사용 크레인·인양 방법", "LI2": "블록 안·위 작업과 부착물", "LO1": "작업 범위(점검/교체/수리/증설)",
         "LO3": "차단·복구·시험운전 시각과 함께 멈추는 설비", "LO4": "접근 위치(제어반 앞/거더·상부)", "B3": "같은 시간·장소의 병행작업",
         "C4": "인양물 중량·크레인 정격하중", "A1": "시간의 오전·오후", "A2": "시간의 날짜", "A3": "추가 전달의 시간", "U1": "추가 전달의 뜻"}
# answers that say something is NOT there, and what in the permit would contradict them (then: checked, not added)
NOT_THERE = {("HT1", "na"): r"러그|인양\s*고리", ("H2", "na"): r"가스\s*절단|산소|LPG|아세틸렌|프로판",
             ("CF2", "none"): r"아르곤|질소|퍼지|가스\s*(?:공급|라인|배관|호스)", ("LI2", "none"): r"블록\s*(?:안|내부)\s*(?:작업|취부|용접)"}
BLOCK = re.compile(r"(?<![A-Za-z0-9-])[A-Z]\d{2,3}[A-Z]?(?:\([A-Z]\))?(?![A-Za-z0-9]|-\d|\s*(?:축|칼럼|밸브|번\s*밸브|열|라인|펌프))|(?<![A-Za-z0-9-])[A-Z]-\d{2}(?=\s*블록)")  # a block number (E41P, B11, E170(A)) — the same as pairs.BLOCK_ID
NEG = re.compile(r"([가-힣A-Za-z0-9]{2,})\s*(?:없음|없이|안\s*함|안\s*하|하지\s*않|미실시)")
_font = None


def font():
    global _font
    if _font is None:
        f = next((x for x in FONT_FILES if __import__("os").path.exists(x)), None)
        _font = pymupdf.Font(fontfile=f) if f else pymupdf.Font("korea")
    return _font


def _clean(v):
    return re.sub(r"\s+", " ", (v or "")).strip()


def _base(item):
    """The question an item belongs to: 'U1.F1' and 'A1.T1.0' are asked-back U1 / A1; B1.x, B2.x, C5.x keep their part."""
    return item.split(".")[0] if not item.startswith(("B1.", "B2.", "C5.")) else item       # T0.2 → T0


# ---------------------------------------------------------------- what each answer means (item, choice) -> facts
# a fact: ("field", purpose, text) to put in a field, ("extra", label, text) for the 별지, ("pending", label, text) to check
def _actual(head, v, P, item):
    """The actual / stage time on the form: the times augment.effective read from this answer (said_windows: the 오전·
    오후 and date check answers applied, the requested window said again left out), the day written unless the permit
    has that one day only; a long answer that also explains is kept word for word on the 별지 (QA #106). An answer
    whose times were not read, or are still unclear, is written as said (Codex final #2·#3)."""
    got = (P.get("said_windows") or {}).get(item)
    rest = re.sub(r"\d{1,2}\s*[:시]\s*\d{0,2}\s*분?|[~\-–,./\s]|오전|오후|부터|까지|에|는|은|및|그리고", "", v)
    if not got or len(rest) <= 6:
        return [("field", "job_detail", f"{head} {v}".strip())]
    days = set(A._windows(P["p"]) if P.get("p") else ())
    bare = len(days) == 1 and set(got) == days
    when = ", ".join(f"{'' if bare else d[5:7] + '/' + d[8:] + ' '}{A.hm(x)}~{A.hm(y)}" for d, ws in sorted(got.items()) for x, y in ws)
    return [("field", "job_detail", f"{head} {when}"), ("extra", f"{head.replace(' 예정', '')}시간(신청자 원문)", v)]


def _facts(a, P):
    # a long answer that also answered other questions (QA #39): its own part ('read'), the rest went to those questions
    item, ch, v = _base(a["qid"].split(":")[0]), a.get("choice") or "", _clean(a.get("read") or a.get("value"))
    q = a.get("q") or {}
    label = next((c.get("label", "") for c in q.get("choices", []) if c.get("id") == ch), ch)
    name = A_ITEM.get(item.split(".")[0], item)
    lift = P["kind"] == "lifting"
    why = f" · 근거: {q['signal']}" if q.get("signal") else ""
    what = CHECK.get(item.split(".")[0])
    if re.fullmatch(r"AI\d+", item):             # a question the AI found in the documents: on the 별지 only, as said
        quote = f"「{q.get('original')}」 " if q.get("original") else ""
        if ch == "unknown":
            return [("pending", "추가 확인 질문", f"{quote}확인 필요 (반장 「모름」)")]
        return [("extra", "추가 확인 질문", f"{quote}→ {label}" + (f": {v}" if v and ch not in ("first", "second") else ""))]
    if item.startswith(("B1.", "B2.")):
        key = item.split(".", 1)[1]
        fname = P["p"].get(key, {}).get("name", key)
        if ch == "value" and v and not NOT_A_VALUE.match(v):
            return [("field", key, v)]
        if ch == "na":
            return [("pending", fname, f"{fname} 확인 필요 (신청자는 「해당 없음」이라고 답함)")]
        return [("pending", fname, f"{fname} 확인 필요" + (f" (입력 '{v}')" if v else ""))]
    if ch == "unknown":                           # what is to be checked; the words typed before it was kept stay
        return [("pending", name, f"{what or name} 확인 필요" + (f" (입력 원문 '{v}')" if v else "") + why)]
    if v and NOT_A_VALUE.match(v):
        return [("pending", name, f"{what or name} 확인 필요 (입력 '{v}')" + why)]
    with_v = lambda text: f"{text} {v}".strip() if v else text
    if item == "C5.concurrent":
        return [("field", "concurrent", "Y"), ("extra", "병행작업", v)] if ch == "free" else []
    if item.startswith("C5."):
        if ch != "free":
            return []
        x = item[3:]
        note = [("extra", f"상충 확인: {A_ITEM.get(x, x)}", "추가로 적은 내용이 맞음 (앞 답 철회)" + (f": {v}" if v else ""))]
        if x in POSITIVE:                          # what the earlier 'none' said is replaced by what is now said
            pid = a["qid"].split(":")[1]
            return note + _facts({"qid": f"{x}:{pid}", "choice": POSITIVE[x], "value": v, "q": {}}, P)
        return note
    T = {
        ("T0", "value"): [("t0", None, v)],
        ("T1", "yes"): [],
        # times: the 신청 작업일시 stays; the actual / stage window is a supplement to the work, in 작업내용(상세)
        ("T1", "partial"): _actual(f"{'블록 이동' if lift else '실제 작업'} 예정", v, P, "T1"),
        ("T2", "partial"): [("field", "job_detail", f"날짜별 작업 예정 {v}")],
        ("T5", "overnight"): [("field", "job_detail", "다음 날 아침 종료(신청자 확인)")],
        ("T5", "fix"): [("time_row", None, v)],
        # T7: the row asked about is corrected (that row only); the 주간·야간 check box is never written by croScan, so a
        # tick to change is listed to be checked with the row it was asked about
        ("T7", "check"): [("time_row", None, v)],
        ("T7", "time"): [("pending", "주간·야간 체크", f"체크 정정 필요 — 신청자 답: 적힌 시간이 맞고 체크를 고쳐야 함 "
                                                   f"({(a.get('q') or {}).get('original', '')}) · 체크 칸은 croScan이 고치지 않음")],
        ("T7", "both"): [("extra", "주간·야간 체크와 시간", f"둘 다 맞음(현장 분류) — {(a.get('q') or {}).get('original', '')}")],
        ("T6", "yes"): [],
        ("T6", "text"): [("field", "job_detail", f"작업시간에 포함: {v}")],
        ("T6", "retime"): _actual("실제 작업 예정", v, P, "T6"),
        ("T6", "stage"): [("field", "job_detail", f"전체 작업 예정 {v}")],
        ("A3", "time"): [("field", "job_detail", f"실제 작업 예정 {v}")],
        ("U1", "time"): [("field", "job_detail", f"실제 작업 예정 {v}")],
        ("U1", "place"): [("place", None, v)],
        ("U1", "other"): [("extra", "다른 팀 작업(추가 전달)", v)],
        ("U1", "note"): [("extra", "안전팀 참고(추가 전달)", (a.get("q") or {}).get("original", ""))],
        ("L1", "whole"): [("whole", None, "")],
        ("D1", "text"): [("field", "job_detail", f"대상 {v}")],
        ("D1", "na"): [("field", "job_detail", "특정 대상 블록·배관 없음")],
        ("L3", "text"): [("field", "location_detail", v)],
        ("L5", "text"): [("route", None, v)],
        ("L7", "place"): [("field", "location_detail", f"실제 작업 위치 {v}")],
        # what the work is: fills an empty 작업내용, else adds to 작업내용(상세)
        ("H1", "local"): [("job", None, with_v("용접부 국부 보수"))],
        ("H1", "replace"): [("job", None, f"{v} 분리·교체" if v else "부재 분리·교체")],
        ("H2", "text"): [("field", "job_detail", v)],
        ("H2", "na"): [("field", "job_detail", "용접용 가스 사용 없음")],
        ("H3", "text"): [("field", "job_detail", f"분리물 지지·회수 계획: {v}")],
        ("CF1", "inspect"): [("job", None, with_v("내부 검사·점검"))],
        ("CF1", "clean"): [("job", None, with_v("내부 청소·잔재 정리"))],
        ("CF1", "repair"): [("job", None, with_v("내부 보수·용접"))],
        ("CF1", "text"): [("job", None, f"내부 작업 {v}")],
        ("CF2", "text"): [("field", "hazards", f"연결 계통·차단 계획: {v}")],
        ("CF2", "none"): [("field", "hazards", "가스·공기 공급 연결 없음(신청자 확인)")],
        ("HT1", "na"): [("field", "job_detail", "떼어 낼 러그 없음")],
        ("HT2", "text"): [("field", "job_detail", f"러그 회수 계획: {v}")],
        ("HT2", "na"): [("pending", "러그 회수·하부", "러그 제거 여부와 제거물 처리 방법 확인 필요 (신청자는 「해당 없음」이라고 답함)")],
        ("LI1", "text"): [("job", None, v)],
        # what is in or on the block to be lifted is another work: the 별지; 'nothing there' is a 전달사항 of this permit
        ("LI2", "none"): [("field", "hazards", "블록 안·위 작업·부착물 없음(신청 시점)")],
        ("LI2", "text"): [("extra", "블록 안·위 다른 작업·부착물 (인양 전 철수·해제 확인 필요)", v)],
        ("LO1", "diag"): [("job", None, "고장 원인 진단·점검")],
        ("LO1", "module"): [("job", None, (v if re.search(r"교체", v) else f"{v} 교체") if v else "부품 교체")],
        ("LO1", "repair"): [("job", None, (v if re.search(r"수리|교체|보수", v) else f"{v} 수리") if v else "수리")],
        ("LO1", "install"): [("job", None, v or "설치·증설")],
        ("LO3", "text"): [("field", "job_detail", f"차단·복구·시험 예정 {v}")],
        ("LO4", "front"): [("field", "location_detail", "제어반 앞에서만 작업")],
        ("LO4", "text"): [("field", "location_detail", v if re.search(r"거더|상부|트롤리", v) else f"거더·상부 접근 {v}")],
        ("B3", "yes"): [("field", "concurrent", "Y")] + ([("extra", "알고 있는 병행작업", v)] if v else []),
        ("B3", "no"): [("field", "concurrent", "N")],
        ("C4", "text"): [("extra", "중량·정격하중 (신청자 정정)", v)],
        ("L2", "text"): [("field", "location_detail", f"실제 작업점 {v}")],
        ("L6", "text"): [("field", "location_detail", f"통제 예정 범위 {v}")],
        ("D2", "text"): [("field", "job_detail", f"사용 크레인 {v}")],
        ("X1", "text"): [("field", "job_detail", f"사용 크레인 {v}")],
        ("D3", "text"): [("field", "job_detail", v)],
        ("D4", "text"): [("field", "job_detail", f"함께 멈추는 설비·복구 {v}")],
        ("D5", "text"): [("field", "hazards", f"연결 계통 확인 계획: {v}")],
        ("C1", "text"): [("field", "hazards", v)],
        ("B4", "value"): [("field", "hull_no", v)],
    }
    if (item, ch) in T:
        out = [f for f in T[(item, ch)] if f[2] or f[0] in ("time_row", "t0", "whole")]
        # a 「없음」 typed in words ('가스·공기 배관 연결 없음', '전기 용접만') is checked against the permit like the
        # 「없음」 choice (augment.negated, Codex trace 2026-10-31 §B); his words are quoted as given
        neg = A.negated(item, a)
        rx = NOT_THERE.get((item, neg or ch))
        if rx and re.search(rx, P["orig_text"]):         # says it is not there, the permit says it is
            said_ = v if neg and neg != ch else label
            return [("pending", name, f"{what or name} 확인 필요 — 답 '{said_}'이 허가서 내용과 다름(문서와 다름)")]
        return out
    if item == "L1" and ch == "place":
        if "job" in [k.split(".", 1)[1] for k in q.get("keys", [])]:          # the LO-TO 크레인·제어반 number question
            pl = A.parse_place(v)                                          # with a BAY it says where; else what
            return [("field", "location_detail" if pl["bays"] or pl["cols"] else "job_detail", v)]
        return [("place", None, v)]
    if item == "HT1":                                                    # gas / plasma / mech (+ the count) or a count
        n = v + ("개" if v.isdigit() else "")
        how = {"gas": "가스절단", "plasma": "플라즈마 절단", "mech": "그라인더·기계절단"}.get(ch, "")
        return [("job", None, _clean(f"러그 {n} {how}" if n else f"러그 {how}"))]
    if item in ("A1", "A2"):                # these complete another answer's reading; nothing of their own to write
        return []
    # anything else (manager questions, pair questions): its meaning in words, on the 별지
    text = v or label
    return [("extra", name, text)] if text else []


A_ITEM = None    # filled from addendum.ITEM on first use (avoids an import cycle)


# ---------------------------------------------------------------- fitting text into a field box
def _lines_for(text, width, size):
    """Wrap on spaces (and inside a long word if needed) at this size; [] if a single glyph does not fit."""
    f, out, cur = font(), [], ""
    for word in text.split(" "):
        tryc = (cur + " " + word).strip()
        if f.text_length(tryc, fontsize=size) <= width:
            cur = tryc
            continue
        if cur:
            out.append(cur)
        cur = ""
        for chx in word:
            if f.text_length(cur + chx, fontsize=size) <= width:
                cur += chx
            else:
                if not cur:
                    return []
                out.append(cur)
                cur = chx
    if cur:
        out.append(cur)
    return out


def _place_text(f, text, after):
    """Where the text goes in field f: {"size", "lines": [(x, baseline, str)]} or None if it does not fit.
    after = the original value that stays (the text is added after it: same line if room, else the next lines)."""
    L = f.get("layout") or {}
    b = L.get("box")
    if not b:
        return None
    x0, y0, x1, y1 = b
    pad = float(L.get("pad") or 1.0)
    size0 = float(L.get("size") or 8.0)
    fnt = font()
    multi = bool(L.get("multi")) or (y1 - y0) > 2.4 * size0
    if f.get("type") == "yn" or (L.get("align") == "center" and not after):      # Y/N and centred cells: in the middle
        w = fnt.text_length(text, fontsize=size0)
        if w <= x1 - x0 - 2:
            return {"size": size0, "lines": [((x0 + x1 - w) / 2, (y0 + y1) / 2 + size0 * 0.36, text)]}
        return None
    for size in (size0, max(MIN_SIZE, size0 - 0.5), MIN_SIZE):
        lh = float(L.get("lh") or size * 1.3)
        if not multi:
            start = x0 + pad
            if after:
                start += fnt.text_length(after, fontsize=size0) + size * 0.6
            if start + fnt.text_length(text, fontsize=size) <= x1 - 1:
                base = (y0 + y1) / 2 + size * 0.36
                return {"size": size, "lines": [(start, base, text)]}
            continue
        top = y0 + float(L.get("top") or 1.0)
        used = 0
        if after:                       # lines the original value already takes
            used = len(_lines_for(after, x1 - x0 - 2 * pad, size0)) or 1
        rows = _lines_for(text, x1 - x0 - 2 * pad, size)
        if rows and top + (used + len(rows)) * lh <= y1 + 0.5:
            return {"size": size, "lines": [(x0 + pad, top + (used + i) * lh + size * 0.92, r) for i, r in enumerate(rows)]}
    return None


# ---------------------------------------------------------------- the plan
def plan(fields, answers, perms=None):
    """{permit_no: {"fills": [...], "extra": [(label, text)], "pending": [(label, text)], "kept": [...]}}.
    A fill: {"no", "base", "name", "keys": [page keys], "mode": fill|append|replace, "original", "text", "final", "src",
    "draw": {page key: {"size", "lines"}}, "redact": bool}. A fill that does not fit is moved to extra (status noted)."""
    global A_ITEM
    if A_ITEM is None:
        from .addendum import ITEM
        A_ITEM = ITEM
    answers = A.live_answers(answers)              # C6 「서류가 맞음」: the earlier answer is taken back, not written
    perms = perms or A.effective(fields, answers)
    pages = A._pages(fields)
    out = {}
    answers = A.drop_stale(perms, answers)          # a T7 answer about another row than the one asked now: not written
    for P in perms:
        pid, kind = P["permit_no"], P["kind"]
        same = [no for no, p in pages.items() if (A._v(p, "permit_no").upper() or f"#{no}") == pid]     # copies of this permit
        rep = pages[P["no"]]                        # the fields as sent (effective's P["p"] has answers laid over them)
        P["orig_text"] = " ".join(str(rep[k].get("original") or "") for k in ("job", "job_detail", "location", "location_detail", "hazards") if k in rep)
        ids_perm = set(BLOCK.findall(P["orig_text"] + " " + str((rep.get("hull_no") or {}).get("original") or "")))
        ans = {a["qid"]: a for a in answers or []}
        get = lambda item: ans.get(f"{item}:{pid}")
        # C5.X 「추가로 적은 내용이 맞음」: the earlier answer to X is withdrawn (its facts are not written)
        withdrawn = {a["qid"].split(":")[0][3:] for a in answers or [] if a["qid"].startswith("C5.") and a.get("choice") == "free"
                     and a["qid"].split(":")[1].split(">")[0] == pid}
        want = {}                                   # base key -> {"mode", "parts": [(text, src)], "replace": value}
        extra, pending = [], []
        fixed = set()                               # time fields a correction replaced: nothing else is added to them

        def put(base, text, src, mode=None):
            if base in NEVER or base not in rep or rep[base].get("type") in ("check", "image"):
                extra.append((rep.get(base, {}).get("name", base), f"{text} ({src})"))
                return
            w = want.setdefault(base, {"parts": [], "replace": None, "src": []})
            if mode == "replace":
                w["replace"], w["src"] = text, w["src"] + [src]
            elif text not in [t for t, _ in w["parts"]]:
                w["parts"].append((text, src))
                w["src"].append(src)

        # 1. what was typed on screen, on any copy: the value of that field, unless croScan never writes it
        seen_edit = set()
        for base, f in [(b, f) for no in same for b, f in pages[no].items()]:
            if f.get("type") == "image" or str(f.get("value")) == str(f.get("original")) or base in seen_edit:
                continue
            seen_edit.add(base)
            if base in NEVER or f.get("type") == "check":
                pending.append((f["name"], f"화면에서 고친 값 '{f.get('value')}'은 이 칸이 당일·서명·승인 칸이라 반영본에 넣지 않음"))
                continue
            put(base, str(f.get("value")), "화면 수정", "replace")
        edited = set(want)
        job_given = any(a["qid"].startswith(f"B1.job:{pid}") and a.get("choice") == "value" for a in answers or [])
        empty = lambda k: k in rep and not str(rep[k].get("value") or "").strip() and k not in edited

        def place_into(text, src):
            """A place of this work: an empty or team-name 작업장소 gets it, else the 상세 row without repeating it."""
            if not text:
                return
            org = A.parse_place(A._v(rep, "location"))
            if (org.get("org") or not A._v(rep, "location")) and "location" not in edited:
                put("location", text, src, "replace")
            else:
                main = _clean(A._v(rep, "location"))
                rest = _clean(text[len(main):]) if main and _clean(text).startswith(main) else text
                if rest:
                    put("location_detail", rest, src)

        def checked(text, src, name):
            """An answer that does not contradict the permit is written; one that does, in any of its parts, is listed to
            be checked whole and not written: the rest of a sentence cut at a comma has lost what it was about (the
            「통제 예정 범위 …E41P 블록 내부와 출입구, 작업 지점 바로 아래 통로를…」 of QA #106 kept only its tail)."""
            why = []
            for cl in [c.strip() for c in re.split(r"[,，;]", text) if c.strip()]:
                bad = [m.group(1) for m in NEG.finditer(cl) if m.group(1) in P["orig_text"]
                       and not re.search(re.escape(m.group(1)) + r"\s*(?:없|안\s*함|하지)", P["orig_text"])]
                other = set(BLOCK.findall(cl)) - ids_perm if ids_perm else set()
                if bad:
                    why.append(f"허가서에는 '{bad[0]}'이(가) 있음 → 어느 쪽이 맞는지 확인 필요 ({src})")
                elif other:                              # another block than the permit's: held, not written
                    why.append(f"블록 번호가 허가서와 다름 (허가서 {', '.join(sorted(ids_perm))} / 답 {', '.join(sorted(other))}) → 확인 필요")
            if why:
                pending.append((name, f"'{text}' — {' · '.join(dict.fromkeys(why))}"))
                return ""
            return text
        # 2. answers, in the order given; a later answer about the same thing is added, never silently dropped
        for a in answers or []:
            qid = a["qid"]
            if qid.startswith("FREE:"):
                t = _clean(a.get("value"))
                if len(perms) == 1 and t:                  # kept word for word; what it says for a field is proposed
                    extra.append(("추가 전달(신청자 원문)", t))    # and written once confirmed (design §2)
                continue
            q = a.get("q") or {}
            if q.get("permit_no") not in (None, pid) or qid.split(":")[1].split(">")[0] != pid:
                continue
            it = qid.split(":")[0]
            if it in withdrawn:
                continue
            src = "빈칸 답변" if it.startswith(("B1.", "B2.")) else f"답변 {A_ITEM.get(it.split('.')[0], it)}"
            if a.get("by"):                           # read from a longer answer to another question (QA #39)
                src += f" · 「{_clean(a.get('quote'))[:24]}」"
            for kind_, purpose, text in _facts(a, P):
                if kind_ == "field" and purpose == "job_detail" and re.search(r"예정 ", text) and A._windows(rep):
                    per = A._windows(rep)
                    got = A._parse_windows(text.split("예정 ", 1)[1], sorted(per), {}, [])
                    out_ = [f"{d} {A.hm(x)}~{A.hm(y)}" for d, ws in got.items() for x, y in ws
                            if not any(a0 <= x and y <= b0 for a0, b0 in per.get(d, []))]
                    if out_:
                        pending.append(("작업시간", f"답한 시간 중 신청 작업일시 밖이 있음 ({', '.join(out_)}) → 날짜·범위 확인 필요 (신청 시간은 그대로)"))
                    if text.startswith("전체 작업 예정") and got and not any(
                            a0 <= x and y <= b0 for d, ws in per.items() for x, y in ws for a0, b0 in got.get(d, [])):
                        pending.append(("작업시간", "전체 예정 시간이 적힌 작업시간을 포함하지 않음 → 정정인지 별도 일정인지 확인 필요"))
                if kind_ in ("field", "job", "place", "route") and text:
                    text = checked(text, src, purpose and rep.get(purpose, {}).get("name") or A_ITEM.get(it.split(".")[0], it))
                    if not text:
                        continue
                if kind_ == "job":                       # what the work is: an empty 작업내용 gets it, else the 상세 row
                    put("job" if empty("job") and not job_given else "job_detail", text, src)
                elif kind_ == "route":                   # a lift's route: an empty 작업장소 gets it, else the 상세 row
                    put("location", text, src) if empty("location") else put("location_detail", f"이동 경로: {text}", src)
                elif kind_ == "whole":
                    org = A.parse_place(A._v(rep, "location"))
                    if org.get("org") or not A._v(rep, "location"):
                        pending.append(("작업장소", "어느 공장인지 확인 필요 (신청자는 공장 전체를 오가며 작업한다고 답함)"))
                    else:
                        lab = next((c.get("label", "") for c in q.get("choices", []) if c.get("id") == a.get("choice")), "")
                        put("location_detail", "BAY 전체를 오가며 작업" if "BAY" in lab else "공장 안 여러 곳을 오가며 작업", src)
                elif kind_ == "extra":
                    extra.append((purpose, text))
                elif kind_ == "pending":
                    pending.append((purpose, text))
                elif kind_ == "place":
                    place_into(text, src)
                elif kind_ == "t0":                      # the empty 작업일시 rows: one row per day, as the form has them
                    ks = [k.split(".", 1)[1] for k in q.get("keys", [])]
                    first = int(ks[0].split("_")[1]) if ks and ks[0].split("_")[1].isdigit() else 1
                    t0 = (P.get("t0") or {}).get(first) or {}
                    w = {d: [tuple(x) for x in ws] for d, ws in (t0.get("w") or {}).items()}
                    days = sorted(w)
                    rows = [i for i in range(first, 8) if f"date_{i}" in rep and (i == first or not any(A._v(rep, f"{k}_{i}") for k in ("date", "from", "to")))]
                    if t0.get("amb") or not w:
                        pending.append(("작업일시", f"작업 날짜·시작·종료 시각 확인 필요 ('{text}'에서 하나로 정해지지 않아 칸은 비워 둠)"))
                    elif not t0.get("dated"):
                        pending.append(("작업일시", f"작업 날짜 확인 필요 (답 '{text}'에 날짜가 없어 칸은 비워 둠 · 쌍작업 검토는 승인번호 날짜 {days[0]}로 계산)"))
                    elif any(len(w[d]) > 1 for d in days) or len(days) > len(rows):
                        extra.append(("작업일시 (신청자 답변)", text))
                        pending.append(("작업일시", "하루에 시간대가 여러 개라 날짜 행(하루 한 줄)에 넣지 않음 → 위 보충 참고"))
                    else:
                        for i, d in zip(rows, days):
                            (a0, b0), = w[d]
                            vals = ((f"date_{i}", d), (f"from_{i}", A.hm(a0)), (f"to_{i}", A.hm(b0 % (24 * 60))))
                            clash = [(k, v2) for k, v2 in vals if A._v(rep, k) and _clean(A._v(rep, k)) != v2]
                            if clash:                    # a row is filled as a whole or not at all
                                pending.append((f"작업일시 {i}행", "작업일시 확인 필요 — 답이 원본과 다름 ("
                                                + ", ".join(f"{rep[k]['name']} 원본 '{A._v(rep, k)}' / 답 '{v2}'" for k, v2 in clash) + ") → 이 행은 원본 그대로"))
                                continue
                            for k, val in vals:
                                if not A._v(rep, k):
                                    put(k, val, src)
                elif kind_ == "time_row":                # read as the cross-check reads it, with its 오전·오후/날짜 answers
                    t7 = a["qid"].split(":")[0] == "T7" and P.get("t7")
                    if t7:                                # T7: the row asked about now, on its day (also one T0 filled)
                        row, day = str(P["t7"][0]), P["t7"][1]
                        keys = [f"from_{row}", f"to_{row}"]
                    else:
                        keys = [k.split(".", 1)[1] for k in q.get("keys", []) if re.fullmatch(r"p\d+\.(?:from|to)_\d", k)]
                        row = keys[0].split("_")[1] if keys else "1"
                        day = A._v(rep, f"date_{row}")
                    amb = []
                    w = A._parse_windows(text, [day] if day else [], A._force(get, q.get("item") or "T5"), amb)     # T5 per row: T5, T5.2 …
                    rng = (w.get(day) or []) if t7 and set(w) == {day} else [] if t7 else w.get(day) or (next(iter(w.values())) if len(w) == 1 else [])
                    if not amb and len(rng) == 1 and len(keys) == 2:
                        put(keys[0], A.hm(rng[0][0]), src, "replace")
                        put(keys[1], A.hm(rng[0][1] % (24 * 60)), src, "replace")
                        fixed.update(keys)
                    else:
                        pending.append(("작업시간 정정", f"'{text}' → 한 구간으로 정해지지 않아 시간 칸은 그대로"))
                elif kind_ == "field":
                    base = purpose
                    if base in edited:               # the 작업반장 typed this field themself: their value stands
                        extra.append((rep.get(base, {}).get("name", base), f"{text} ({src})"))
                    elif base in ("concurrent",) or (purpose in rep and rep[purpose].get("type") != "text"):
                        put(base, text, src, "replace" if A._v(rep, base) else None)
                    else:
                        put(base, text, src)
        for b in fixed:                             # a T0 value of the same field (T7 after T0) is replaced, not kept
            if b in want:
                want[b]["parts"] = []
        # 3. a value per field, placed and measured on every copy of the permit
        fills = []
        for base, w in want.items():
            f0 = rep[base]
            orig = str(f0.get("original") or "")
            if w["replace"] is not None:
                text, mode, after = w["replace"], ("replace" if orig.strip() else "fill"), ""
                if w["parts"]:
                    text = text + " " + " · ".join(t for t, _ in w["parts"])
            else:
                # a part that repeats the original and adds to it ('4BAY 10칼럼 배전반' → '4BAY 10칼럼 배전반 MCC-4'):
                # only what is new is added after the original
                adds = []
                for t, _ in w["parts"]:
                    t = _clean(t)
                    if orig.strip() and _clean(orig) in t:
                        t = _clean(t.replace(_clean(orig), "", 1)).strip(" ,·:")
                    if t and t not in _clean(orig) and t not in adds:
                        adds.append(t)
                if not adds:
                    continue
                text = ", ".join(adds)
                mode, after = ("append" if orig.strip() else "fill"), orig
            if f0.get("type") not in ("text", "name") and not A.valid(f0.get("type"), text):
                pending.append((f0["name"], f"'{text}'은 칸 형식({f0.get('type')})에 맞지 않아 넣지 않음"))
                continue
            if mode == "replace" and _clean(text) == _clean(orig):
                continue
            draw = {}
            for no in same:
                k = f"p{no}.{base}"
                if k not in fields:
                    continue
                fk = fields[k]
                if _clean(str(fk.get("original") or "")) != _clean(orig):       # a copy that reads otherwise: not unified
                    pending.append((f0["name"], f"{no}쪽 사본의 원본 값이 다름 ('{fk.get('original')}') → 그 쪽에는 반영하지 않음"))
                    continue
                if mode == "replace" and not (fk.get("layout") or {}).get("glyphs"):   # where the old value is, not known
                    continue
                spot = _place_text(fk, text, after if mode == "append" else "")
                if spot:
                    draw[k] = spot
            if not draw:
                extra.append((f0["name"], f"{text} (칸이 좁거나 원본 글자 위치를 몰라 반영본에 넣지 못함 · {', '.join(dict.fromkeys(w['src']))})"))
                continue
            for no in same:                          # a copy where it did not fit: said, not silent
                k = f"p{no}.{base}"
                if k in fields and k not in draw and _clean(str(fields[k].get("original") or "")) == _clean(orig):
                    pending.append((f0["name"], f"{no}쪽 사본에는 칸이 좁아 넣지 못함"))
            final = (orig + " " + text).strip() if mode == "append" else text
            fills.append({"base": base, "name": f0["name"], "keys": sorted(draw), "mode": mode, "original": orig, "text": text,
                          "final": final, "src": list(dict.fromkeys(w["src"])), "draw": draw})
        order = {k: i for i, k in enumerate(rep)}
        fills.sort(key=lambda x: order.get(x["base"], 999))
        for i, x in enumerate(fills):
            x["no"] = i + 1
            x["mark"] = MARKS[i] if i < len(MARKS) else f"({i + 1})"
        out[pid] = {"fills": fills, "extra": _uniq(extra), "pending": _uniq(pending)}
    return out


def destination(fields, answers, prop, before=None):
    """where a proposal would go once confirmed (design §4.3·§19.2 「들어갈 곳(전→후)」): the same plan made with and
    without it -> [{kind: field|sheet|pending, where, before, after}] — a form field with its value before and after,
    the 별지 with what is added, or what is left to be checked. [] when it changes nothing written (the answer is kept
    as said, for the calculation only). before: the plan without it, when already made."""
    pid = ((prop.get("q") or {}).get("permit_no") or prop["qid"].split(":")[1].split(">")[0]) if ":" in prop["qid"] else None
    base = [a for a in answers or [] if a["qid"] != prop["qid"]]
    p0 = (before if before is not None else plan(fields, base)).get(pid) or {"fills": [], "extra": [], "pending": []}
    p1 = plan(fields, base + [{**prop, "pid": prop.get("pid") or "proposal"}]).get(pid) or {"fills": [], "extra": [], "pending": []}
    was = {f["base"]: f for f in p0["fills"]}
    out = []
    for f in p1["fills"]:
        b = was.get(f["base"])
        if not b or b["final"] != f["final"]:
            out.append({"kind": "field", "where": f["name"], "before": (b["final"] if b else f["original"]) or "", "after": f["final"]})
    for lab, text in p1["extra"]:
        if (lab, text) not in p0["extra"]:
            out.append({"kind": "sheet", "where": f"별지 · {lab}", "before": "", "after": text})
    for lab, text in p1["pending"]:
        if (lab, text) not in p0["pending"]:
            out.append({"kind": "pending", "where": f"확인 필요 · {lab}", "before": "", "after": text})
    return out


def _uniq(rows):
    seen, out = set(), []
    for r in rows:
        if r not in seen and r[1]:
            seen.add(r)
            out.append(r)
    return out


# ---------------------------------------------------------------- drawing: the derived PDF
def apply(doc, fields, rplan, stamp=True):
    """Write the planned values onto the pages of doc (a pymupdf Document of the original): the old value's glyphs are
    removed only where a value is replaced; nothing else on the page is touched. Returns the number of fields written."""
    fnt = font()
    by_page = {}
    for pid, R in rplan.items():
        for x in R["fills"]:
            for k, spot in x["draw"].items():
                by_page.setdefault(int(k.split(".")[0][1:]), []).append((k, x, spot))
    n = 0
    for no in range(1, doc.page_count + 1):
        items = by_page.get(no, [])
        pg = doc[no - 1]
        # remove the replaced values' own glyphs (text only: lines, logo and labels stay)
        hits = 0
        for k, x, _ in items:
            if x["mode"] != "replace":
                continue
            for g in (fields[k].get("layout") or {}).get("glyphs") or []:      # only the old value's own glyphs
                pg.add_redact_annot(pymupdf.Rect(g) + (0.3, 0.3, -0.3, -0.3), fill=False)
                hits += 1
        if hits:
            pg.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                                text=pymupdf.PDF_REDACT_TEXT_REMOVE)
        pg.insert_font(fontname="crs", fontbuffer=fnt.buffer)
        for k, x, spot in items:
            for (lx, by, t) in spot["lines"]:
                pg.insert_text((lx, by), t, fontsize=spot["size"], fontname="crs", color=BLUE)
            lx, by, t = spot["lines"][-1]
            pg.insert_text((lx + fnt.text_length(t, fontsize=spot["size"]) + 1, by - spot["size"] * 0.45), x["mark"],
                           fontsize=max(5.0, spot["size"] * 0.7), fontname="crs", color=BLUE)
            n += 1
        if stamp and by_page:                     # every page of the 반영본 says what it is
            W = pg.rect.width
            s = "croScan 사전검토 반영본 · 파란 글씨(①…)는 신청자 답변·화면 수정 반영 · 원본 대비 변경은 별지 참조 · 업로드한 원본 파일은 그대로 보존"
            size = 6.5
            while fnt.text_length(s, fontsize=size) > W - 60 and size > 5:
                size -= 0.25
            pg.insert_text((W - 30 - fnt.text_length(s, fontsize=size), 22), s, fontsize=size, fontname="crs", color=BLUE)
    return n
