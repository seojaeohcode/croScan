"""Follow-up questions to the 작업반장 and the 추가검토서 (page 2) they fill.

The uploaded permit file is never changed (QA #37, 2026-10-30: the submitted copy is a 사전검토 반영본, server/reflect.py,
with the answers that fit written into their fields; the rest on the 별지). Rules look at the read values and raise a
question wherever a value may be true, mistaken or left blank on purpose (a whole-day
time, a place that is a team name, an empty 병행여부 ...). Each answer becomes a record
with its source ("신청자 답변"); the values the cross-permit check uses are the permit
values overlaid with those records. Design: croScan_멀티턴_추가검토_설계.md.

Answer (from the client): {"qid", "choice", "value"}; choice is one of the question's
choice ids. Statuses: 확인됨 / 정정 / 해당없음 / 미확인 / 보강.
"""
import hashlib
import json
import re

from . import need_catalog
from . import permit_kinds as PK
from .review import _num, _pages, legal_night_only, plain_day, valid

N_OF = {"hot": "N1", "confined": "N2", "height": "N3", "lifting": "N4", "loto": "N5"}
WORK = {"hot": "절단·용접을", "confined": "내부 진입을", "height": "고소 작업을", "lifting": "인양·운반을", "loto": "정전 수리를"}
# 대조립 비일상 × 비일상 15 combinations (team research, section 8): link and the action drafted in section 9
PAIR = {
    ("hot", "hot"): ("최종 연결부 절단(같은 지지구조)", "낙하·전도", "C", "절단 순서·지지 확인, 한 팀 절단 중 상대 팀 하부 대피"),
    ("confined", "hot"): ("용접가스 공급 → 진입 배관, 같은 구획 절단", "가스·산소결핍, 화재·불티", "C", "내부 인원 전원 퇴실 후 절단·용접, 재진입 전 공기 재측정"),
    ("height", "hot"): ("지지부 절단 ↔ 상부 발판, 러그 낙하", "낙하·전도, 공통지지", "C", "절단 부재 지지 확인, 낙하 반경 하부 통제"),
    ("hot", "lifting"): ("절단 후 약해진 부재에 반출 블록 접촉", "낙하·전도, 이동·충돌", "C", "보수 완료·지지 검토·인계 후 반출"),
    ("hot", "loto"): ("절단물·불티 → 열린 제어반", "화재·불티, 낙하", "C", "제어반 방향 불티 차단(방화포), 절단물 낙하 경로 통제"),
    ("confined", "confined"): ("공급·환기·격리 변경이 다른 진입팀에 영향", "가스·산소결핍", "C", "공급·환기·격리 변경 전 다른 진입팀에 통보, 공동 감시"),
    ("confined", "height"): ("러그 낙하 → 감시인·덕트·출입구", "낙하, 접근·구조 방해", "C", "낙하 반경에서 감시인·덕트·출입구 이격"),
    ("confined", "lifting"): ("사람이 들어간 배관·블록째 반출", "이동·충돌, 접근·구조 방해", "C", "내부 인원표 대조·전원 퇴실 확인 후 인양, 해치 인계 전 이동 금지"),
    ("confined", "loto"): ("공유전원 차단 → 환기 중단", "공유전원", "H", "차단 전원에 환기팬 연결 여부 확인 전 보류, 연결 시 독립전원"),
    ("height", "height"): ("두 러그팀의 상하 낙하·작업대 간섭", "낙하", "C", "상하 동시작업 금지 또는 낙하방지망, 작업대 간섭 확인"),
    ("height", "lifting"): ("운반물·줄걸이가 발판 충격", "이동·충돌", "C", "고소작업과 운반물 통과 시간 분리, 통과 중 발판 위 작업 중지"),
    ("height", "loto"): ("복구·시험운전이 고소팀을 침", "공유전원·기계가동", "C", "복구·시험운전 전 고소팀 철수 확인"),
    ("lifting", "lifting"): ("두 인양의 경로 교차·동시주행", "이동·충돌", "C", "두 인양 경로·시간 분리, 동시 주행 금지"),
    ("lifting", "loto"): ("수리 중 크레인 사용, 조기 복구", "공유전원·기계가동, 이동·충돌", "C", "LOTO 중 해당 크레인 운행 금지, 복구·시험운전·인계 후 인양"),
    ("loto", "loto"): ("한 팀 완료 후 공통전원 복구", "공유전원", "C", "공통전원 복구는 모든 팀 잠금 해제 확인 후"),
}
# words that show the kind's main hazard is written in 유해위험요소 (form context, not sample values)
HAZ_WORDS = {
    "confined": r"질식|산소|가스|환기|아르곤|유해",
    "hot": r"화재|불티|불꽃|화상|폭발|발화|스패터",       # fire and spark; 흄 (fume) is a health hazard, not this one
    "height": r"추락|낙하|떨어",
    "lifting": r"낙하|협착|충돌|끼임|전도|깔림",
    "loto": r"감전|아크|재가동|재기동|전기|충전",
}
MOMENT_Q = {
    "hot": "마지막 연결부를 끊는(절단 완료) 예정 시각은 언제인가요?",
    "confined": "진입·퇴실 시각은 언제인가요? 중간에 나왔다 다시 들어가나요?",
    "height": "러그가 떨어지는 절단 완료 시각과, 회수 전 하부 통제가 끝나는 시각은요?",
    "lifting": "시험인양·주행·안착·줄걸이 해제는 각각 몇 시인가요?",
    "loto": "복구(전원 투입)·시험운전은 몇 시인가요?",
}
NOTE_ITEMS = [("L5", "이동 경로"), ("L6", "작업 중 통제 범위"), ("D2", "크레인"), ("D3", "가스·공급 방식"),
              ("D4", "함께 멈추는 설비·복구 시각"), ("D5", "진입 구획 공급 계통"), ("T3", "인양 단계 시각"),
              ("H1", "보수 범위·개수"), ("H2", "공법·가스"), ("H3", "분리물 지지·회수"), ("CF1", "내부 작업·진입 방식"),
              ("CF2", "연결 계통·차단"), ("HT1", "러그 수량·절단 방법"), ("HT2", "러그 회수·하부"), ("LI1", "크레인·인양 방법"),
              ("LI2", "블록 안·위 작업, 붙은 것"), ("LO1", "작업 범위"), ("LO3", "차단·복구·시험"), ("LO4", "접근 위치"),
              ("L7", "칼럼 범위의 뜻"), ("T6", "시간 차이 설명"), ("B3", "알고 있는 병행작업")]
# a block or equipment ID: 'E41P', 'OH-21-03', 'B-01', and the real form's 'E170(A)' (the part letter kept: E170(A) and
# E170(B) are two blocks)
TARGET = re.compile(r"(?<![A-Za-z0-9])[A-Z]{1,3}-?\d{1,3}[A-Z]?(?:-\d{1,3})*(?:\([A-Z]\))?(?![A-Za-z0-9])")
# look like an ID but are a gas or a steel grade ('CO2 용접', 'AH36 판재 교체'): never a block or equipment
NOT_ID = re.compile(r"CO2|O2|N2|H2S?|SF6|CH4|NO2|SO2|(?:AH|DH|EH|FH)(?:32|36|40)|SUS\d{3}L?|SS\d{3}|SM\d{3}[A-C]?|(?:C|M|K)?M[23]", re.I)
CRANE = re.compile(r"(?<![A-Za-z0-9])(?:OH|MC|GC|JC|TC|CR)-?\d{1,3}[A-Z]?(?:-\d{1,3})*(?![A-Za-z0-9])")
NEAR_COLS = 2          # provisional: columns within 2 of each other count as near (no measured column spacing yet)
DAY_START, DAY_END = 9 * 60, 16 * 60        # a day row that starts before 09 and ends after 16 covers the shift
# The site's confirmed day shift ('08:00-18:00'), set by the site (CROSCAN_SITE_SHIFT) — none is known today. The
# research's 08~18 / 18~익일 08 split is an author's scenario: 「야간 자체/08~18 가정만으로 질문·오류 금지」 (N4-MT15
# p315; N2~N5 MT14 p247·275·355 ask only against confirmed operating information). Without a confirmed shift the
# permit's 주간·야간 tick is compared with its time only by the statutory night line (review.LEGAL_NIGHT, 근로기준법
# 제56조 제3항): a 주간 row wholly inside it, a 야간 permit plainly daytime; asked as a check of what the tick means,
# with 「둘 다 맞음」 among the answers. Night is known only from what the permit or the foreman says (the 야간 tick, a
# confirmed next-morning end, a T7 answer).
def _site_shift(v=None):
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})\s*", v if v is not None else __import__("os").environ.get("CROSCAN_SITE_SHIFT", ""))
    return (int(m.group(1)) * 60 + int(m.group(2)), int(m.group(3)) * 60 + int(m.group(4))) if m else None


SITE_SHIFT = _site_shift()


def night_part(a, b, shift=None):
    """a window (minutes; b may pass midnight) reaches outside the confirmed day shift at all (06:00~10:00 does with
    08~18); False when no shift is confirmed"""
    shift = shift or SITE_SHIFT
    if not shift:
        return False
    ds, de = shift
    return a < ds or b > de


def day_only(a, b, shift=None):
    """a window wholly inside the confirmed day shift; False when none is confirmed"""
    shift = shift or SITE_SHIFT
    return bool(shift) and a >= shift[0] and b <= shift[1]



# ---------------------------------------------------------------- reading a permit
def _v(p, k):
    return str(p.get(k, {}).get("value", "") or "").strip()


def _m(t):
    m = re.fullmatch(r"\s*(\d{1,2}):?(\d{2})?\s*", t or "")
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2) or 0)
    return h * 60 + mi if (0 <= h < 24 and 0 <= mi < 60) or (h == 24 and mi == 0) else None


def hm(x):
    return f"익일 {hm(x - 1440)}" if x >= 1440 else f"{x // 60:02d}:{x % 60:02d}"


def permit_day(p):
    """The work day a permit's number carries (AC00-IH-YYYYMMDD-NNNN), else its first date row: the default day of T0."""
    m = re.search(r"-(20\d{2})(\d{2})(\d{2})-\d{3,4}\b", _v(p, "permit_no"))
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    d = _v(p, "date_1")
    return d if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) else ""


def t0_dates(p, text, row=1):
    """The ISO dates a T0 answer can be about: those written in it (10/29, 2026-10-29), else the row's own date, else the
    permit number's day (used to place the work in the day; not written on the form unless the answer gives it)."""
    own = _v(p, f"date_{row}")
    day = own if re.fullmatch(r"\d{4}-\d{2}-\d{2}", own) else permit_day(p)
    year = day[:4] if day else ""
    out = []
    for m in DATE_MD.finditer(text or ""):
        if m.group(1):
            out.append(f"{m.group(1)}-{m.group(2)}-{m.group(3)}")
        elif year and 1 <= int(m.group(4)) <= 12 and 1 <= int(m.group(5)) <= 31:
            out.append(f"{year}-{int(m.group(4)):02d}-{int(m.group(5)):02d}")
    return sorted(set(out)) or ([day] if day else [])


def t5_item(i):
    """the item of the reversed-row question T5 for row i: 'T5' for row 1 (as before), 'T5.<i>' for the others"""
    return "T5" if int(i) == 1 else f"T5.{i}"


def time_gap(p, done=()):
    """The 작업일시 row to ask about (T0.<row>): (row, missing parts) — row 1 when no row is used at all, else the first
    used row with an empty date, start or end that has not been answered (done); None when there is none left."""
    if not ("date_1" in p and "from_1" in p and "to_1" in p):
        return None
    parts = (("날짜", "date"), ("시작", "from"), ("종료", "to"))
    used = [i for i in range(1, 8) if any(_v(p, f"{k}_{i}") for _, k in parts)]
    if not used:
        return (1, [n for n, _ in parts]) if 1 not in done else None
    for i in used:
        miss = [n for n, k in parts if not _v(p, f"{k}_{i}")]
        if miss and i not in done:
            return i, miss
    return None


def t0_row(p, ws, row):
    """A T0 answer's days placed on the form's rows, as the 반영본 writes them: {row: (date, start, end)}, or None
    when a row's written values say otherwise (the row is then kept as it is, and so is the cross-check's time)."""
    days = sorted(ws)
    rows = [i for i in range(row, 8) if f"date_{i}" in p and (i == row or not any(_v(p, f"{k}_{i}") for k in ("date", "from", "to")))]
    if any(len(ws[d]) > 1 for d in days) or len(days) > len(rows):
        return None
    out = {}
    for i, d in zip(rows, days):
        (a0, b0), = ws[d]
        vals = (d, hm(a0), hm(b0 % (24 * 60)))
        if any(_v(p, f"{k}_{i}") and _v(p, f"{k}_{i}").strip() != v for k, v in zip(("date", "from", "to"), vals)):
            return None
        out[i] = vals
    return out


def _windows(p):
    out = {}
    for i in range(1, 8):
        d, a, b = _v(p, f"date_{i}"), _m(_v(p, f"from_{i}")), _m(_v(p, f"to_{i}"))
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) and a is not None and b is not None and b > a:
            out.setdefault(d, []).append((a, b))
    return out


def _hull_add(wins, more):
    """wins with the windows of more added, each day apart: a window already inside one of that day's windows adds
    nothing; any other is kept as said (never cut to the requested window, never moved to another day)"""
    out = {d: list(ws) for d, ws in wins.items()}
    for d, ws in more.items():
        out[d] = _union(out.get(d, []) + list(ws))           # a union: overlapping parts are not counted twice
    return out


def parse_place(text):
    """Place detail level L0..L4 with factory, bays, columns (design 3-2)."""
    t = re.sub(r"[–—～∼〜]", lambda m: "~" if m.group(0) in "～∼〜" else "-", text or "")
    fac = re.search(r"([A-Za-z]*\d+)\s*공장", t)
    # '3BAY', and the axis notation of the 대조립 layout model (F01): '2B', '2B-08', '2B / 08~12축'
    bays = {b.upper() for b in re.findall(r"(\d+)\s*BAY", t, re.I)} | set(re.findall(r"(?<![A-Za-z0-9])(\d{1,2})B(?![A-Za-z0-9])", t))
    # a number range right after the BAY is its columns ('3BAY 12-14', QA #39), not a time
    cols = (re.search(r"(\d+)\s*[-~]\s*(\d+)\s*(?:칼럼|축)", t) or re.search(r"(?<![A-Za-z0-9])\d{1,2}B-(\d{1,2})(?![0-9])", t)
            or re.search(r"BAY\s*(\d{1,2})\s*[-~]\s*(\d{1,2})(?!\s*(?:시|:|분|\d))", t, re.I) or re.search(r"(\d+)\s*(?:칼럼|축)", t))
    layer = "상부" if re.search(r"상부|위\b|상단|거더", t) else "내부" if re.search(r"내부|안\b|진입", t) else \
        "하부" if re.search(r"하부|아래|지상", t) else ""
    org = not bays and bool(re.search(r"[가-힣A-Za-z0-9]+(팀|과|부|반)(?=\s|$|,)", t))
    level = 0 if (org or not t.strip()) else 1 if not bays else 3 if cols else 2
    if level >= 3 and (TARGET.search(t) or layer):
        level = 4
    colrange = None
    if cols:
        nums = [int(x) for x in cols.groups() if x]
        colrange = (min(nums), max(nums))
    return {"text": t.strip(), "factory": fac.group(1).upper() if fac else None, "bays": bays,
            "cols": cols.group(0) if cols else "", "colrange": colrange, "layer": layer, "level": level, "org": org}


def _permits(fields):
    """One entry per permit (the first page of each 승인번호), in page order."""
    pages, seen, out = _pages(fields), set(), []
    for no, p in sorted(pages.items()):
        pno = _v(p, "permit_no").upper() or f"#{no}"
        if pno in seen:
            continue
        seen.add(pno)
        kind = next((f.get("kind") for f in p.values() if f.get("kind")), None)
        out.append({"no": no, "permit_no": pno, "kind": kind, "label": PK.KINDS[kind]["label"] if kind in PK.KINDS else "?", "p": p})
    return out


def _who(P):
    return f"{P['no']}쪽 {P['label']}({P['permit_no'][-4:]})"


_ID_ANY_CASE = re.compile(TARGET.pattern, re.I)


def norm_ids(text):
    """IDs a foreman typed in lower case ('oh-21-01', 'e41p') in capitals, the rest of the answer as typed."""
    return _ID_ANY_CASE.sub(lambda m: m.group(0) if re.fullmatch(r"[ckm]?m[23]", m.group(0)) else m.group(0).upper(), text or "")   # 'm3' stays a unit


def confirmed(text, rx):
    """the clause of text that says rx as settled ('' if none): not undecided, not unable, not uncertain
    ('DB-2인지 확인 필요', '차단 담당 미정', '가능한지 미정', '여부 미정', '차단 불가' say nothing settled)"""
    from .need_catalog import UNSURE
    for cl in re.split(r"[,;\n/]|(?<!\d)\.(?!\d)|그리고|지만", text or ""):
        if re.search(rx, cl) and not UNSURE.search(cl) and not HEDGE.search(cl):
            return cl.strip()
    return ""


def blocks_in(text):
    """block IDs only ('E41P', 'B11', 'E170(A)', 'B-01'): not a crane, a panel ('DB-2'), a pipe ('P-01') or a valve ('V-12')"""
    return {x for x in ids(text) if not CRANE.fullmatch(x) and (re.fullmatch(r"[A-Z]\d{2,3}[A-Z]?(?:\([A-Z]\))?", x)
                                                                 or (re.fullmatch(r"[A-Z]-\d{2,3}", x) and x[0] not in "PV"))}


def ids(text):
    """Block / equipment IDs in a text ('E41P', 'OH-21-03', 'CP-01'), without gases and steel grades."""
    return {t for t in TARGET.findall(text or "") if not re.fullmatch(r"\d+", t) and not NOT_ID.fullmatch(t)}


# ---------------------------------------------------------------- effective values: permit + answers
ISO = re.compile(r"\d{4}-\d{2}-\d{2}")
# one clock time: '14:30', '9시', '9시 30분', '9시 반', '오후 2시'; and a range of two ('오후 2시~4시', '09:00～11:00')
_T = r"(?:(오전|아침|새벽|오후|저녁|밤)\s*)?(\d{1,2})(?:\s*:\s*(\d{2})|\s*시(?:\s*(\d{1,2})\s*분|\s*(반))?)?"
TIME_RANGE = re.compile(rf"(?<![\d.:A-Za-z-]){_T}\s*(?:[~\-–—～∼〜]|부터)+\s*{_T}"
                        r"(?!\d|[.:]\d|\s*(?:칼럼|축|BAY|번|m(?![a-z])|미터|개|명|톤|t(?![a-z])|일|%|kg|mm|cm))", re.I)
# a BAY and the column range after it ('3BAY 12-14', QA #39): a place, never read as a time
PLACE_SPAN = re.compile(r"(?:\d+\s*공장\s*)?\d+\s*BAY(?:\s*\d{1,2}\s*[-~–]\s*\d{1,2}(?!\d)(?!\s*(?:시|:|분))(?:\s*(?:칼럼|축))?)?", re.I)
DATE_MD = re.compile(r"(\d{4})-(\d{2})-(\d{2})|(?<![\d.])(\d{1,2})\s*[/.월]\s*(\d{1,2})(?!\d|\s*(?:m(?![a-z])|미터|시|:))", re.I)


AM, PM = ("오전", "아침", "새벽"), ("오후", "저녁", "밤")
# a day word that names no date by itself: on a permit of several days croScan asks which date it is
REL_DAY = re.compile(r"오늘|내일|모레|글피|다음\s*날|이튿날|첫\s*날|둘째\s*날|셋째\s*날|마지막\s*날|하루\s*뒤|이틀\s*뒤")


def _clocks(mark, h, mi, half, raw):
    """The clock times (minutes) a written time can be. With 오전·오후 or in 24-hour form ('14시', '09:00') one;
    a bare '7시'…'12시' is the day shift's; a bare '1시'…'6시' can be 새벽 or 오후, so both."""
    h, mi = int(h), int(mi or 0) + (30 if half else 0)
    if h > 24 or mi >= 60:
        return []
    if mark in PM:
        return [(h + 12 if h < 12 else h) * 60 + mi]
    if mark in AM or raw.startswith("0") or h == 0 or h >= 7:
        return [h * 60 + mi]
    return [h * 60 + mi, (h + 12) * 60 + mi]


def _readings(m):
    """Every (start, end) a range can mean: the end is the first of its clock times after the start."""
    m1, h1, i1, j1, half1, m2, h2, i2, j2, half2 = m.groups()
    morning = m1 if m1 in AM and int(h2) > int(h1) else None            # '새벽 2시~4시', not '오전 9시~1시'
    ends = _clocks(m2 or morning, h2, i2 or j2, half2, h2)
    if not (m2 or morning) and not h2.startswith("0") and int(h2) < 12:
        ends = sorted(set(ends) | {(int(h2) + 12) * 60 + int(i2 or j2 or 0) + (30 if half2 else 0)})   # '11시~1시' ends 13:00
    out = []
    for a in _clocks(m1, h1, i1 or j1, half1, h1):
        b = next((e for e in sorted(ends) if e > a), None)
        if b is not None and b <= 24 * 60 and (a, b) not in out:
            out.append((a, b))
    return out


def time_ranges(text, ampm=None, amb=None, seen=None):
    """[(a, b)] minutes for every time range in the text. A range that can mean two things ('2시~4시': 02:00~04:00 or
    14:00~16:00) is not guessed. ampm is the 작업반장's answer: 'am' / 'pm' for every such range, or {k: 'am'|'pm'} for
    the k-th one (each is asked on its own); a range with no answer is left out and added to amb as (k, words).
    seen counts those ranges across calls ([0])."""
    out, seen = [], seen if seen is not None else [0]
    for m in TIME_RANGE.finditer(PLACE_SPAN.sub(" ", text or "")):
        rs = _readings(m)
        if len(rs) > 1:
            k = seen[0]
            seen[0] += 1
            pick = ampm.get(k) if isinstance(ampm, dict) else ampm
            if pick in ("am", "pm"):
                rs = [rs[0] if pick == "am" else rs[-1]]
            else:
                if amb is not None:
                    amb.append((k, m.group(0).strip()))
                continue
        out += rs
    return out


def dated(text):
    """every time range in the text is said with its date ('10/27 09~11; 10/28 14~16'): it says nothing of other days"""
    segs = [s for s in re.split(r"[,;\n]|그리고|및", text or "") if TIME_RANGE.search(PLACE_SPAN.sub(" ", s))]
    return bool(segs) and all(DATE_MD.search(s) for s in segs)


NEXT_DAY = re.compile(r"다음\s*날|익일|이튿날")


def next_iso(d):
    import datetime
    return (datetime.date.fromisoformat(d) + datetime.timedelta(days=1)).isoformat()


def _parse_windows(text, dates, force=None, amb=None, count=None):
    """'09:00~11:00, 14~16' or '10/27 09~11; 10/28 14:00-16:00' -> {date: [(a, b)]}; dates are the permit's ISO dates.
    force: the 작업반장's answers to croScan's check questions, one per unclear part in the order they appear:
    {"ampm": {k: "am"|"pm"}, "date": {k: ISO date | "all"}}.
    What cannot be read without guessing goes to amb as {"kind": "ampm"|"date", "k": k, "raw": the words} and is not used."""
    dates = [d for d in dates if ISO.fullmatch(d)]           # a date typed on screen as '10/27' cannot be matched
    force = force or {}
    out = {}
    count = count if count is not None else {"ampm": [0], "date": [0]}      # shared by every sentence of one answer
    seen, nday = count["ampm"], count["date"]
    for seg in re.split(r"[,;\n]|그리고|및", text or ""):
        md = DATE_MD.search(seg)
        targets = list(dates)
        if md:
            mm, dd = (md.group(2), md.group(3)) if md.group(1) else (md.group(4), md.group(5))
            if 1 <= int(mm) <= 12 and 1 <= int(dd) <= 31:
                targets = [d for d in dates if int(d[5:7]) == int(mm) and int(d[8:10]) == int(dd)]
                seg = seg[md.end():]
                if not targets and dates and TIME_RANGE.search(seg):
                    # a date the permit does not have: asked once whether the work is on it, never dropped or moved
                    new = md.group(0) if md.group(1) else f"{dates[0][:4]}-{int(mm):02d}-{int(dd):02d}"
                    pick = (force.get("date") or {}).get(nday[0])
                    nday[0] += 1
                    if pick == new or pick in dates:
                        targets = [pick]
                    else:
                        if amb is not None:
                            amb.append({"kind": "date", "k": nday[0] - 1, "raw": md.group(0) + seg, "new": new})
                        continue
        elif len(dates) > 1 and REL_DAY.search(seg) and TIME_RANGE.search(seg):
            day = (force.get("date") or {}).get(nday[0])      # '내일 2시~4시' on a permit of several days
            nday[0] += 1
            if day == "all" or day in dates:
                targets = list(dates) if day == "all" else [day]
            else:
                if amb is not None:
                    amb.append({"kind": "date", "k": nday[0] - 1, "raw": seg.strip()})
                continue
        elif len(dates) == 1 and NEXT_DAY.search(seg) and TIME_RANGE.search(seg):
            targets = [next_iso(dates[0])]                     # '다음 날 00:00~02:00' on a one-day permit: the next date
        found = []
        rs = time_ranges(seg, force.get("ampm") or {}, found, seen)
        if amb is not None:
            amb += [{"kind": "ampm", "k": k, "raw": x} for k, x in found]
        for a, b in rs:
            for d in targets:
                out.setdefault(d, []).append((a, b))
    return out


# ---------------------------------------------------------------- what the text says (permit + answers)
COUNT = re.compile(r"(\d{1,3})\s*(?:개소|개|EA|ea|군데|곳|부위|장)(?!월|년|소|씩|면|님)")
HEIGHT = re.compile(r"(\d+(?:\.\d+)?)\s*(?:m|M|미터)(?![A-Za-z가-힣])")
NEG = re.compile(r"안\s*(?:씀|써|쓰|씁|함|합|해|했|하|할|들어)|없|미사용|사용\s*안|않|아님|아니")
PRENEG = re.compile(r"(?:안|못)\s*(?:쓰는|쓸|하는|할|들어가는)\s*$|(?:없는|않는|않을)\s*$")     # '안 쓰는 가스'
WORKTIME = re.compile(r"작업\s*시간|실제|시간대|작업은|작업할|일하는|하는\s*시간|진입|움직이는|들어가는\s*시간")
COND = re.compile(r"면(?:\s|$)|경우|때(?:는|에)?(?:\s|$)")
CLAUSE = re.compile(r"[,;\n/·]|(?<!\d)\.(?!\d)|그리고|지만")        # '4.8m' is not split


# not sure: '아마 없을 거예요', '있는 것 같아요', '잘 모르겠지만'. Such a clause is never taken as a fact (약·대략·쯤 are
# only rough numbers and stay)
HEDGE = re.compile(r"아마|[가-힣]\s*수도\s*있|것\s*같|듯\s*(?:해|합|하|요|싶)|글쎄|모르겠|확실(?:하지|치)\s*않|확실히\s*모르|(?:있|없)을\s*(?:걸|거(?:예요|에요|야|같))|짐작|추정|미확인"
                   # '다른 작업 여부는 확인 중' (not known yet), not '용접 상태 확인 중' (the work itself)
                   # ('러그가 6개인지 담당자에게 확인 중', '없는지 반장님께 물어보고 있습니다' too)
                   r"|(?:여부|는지|인지|할지|될지)[^,.;\n]{0,20}?(?:확인|파악|알아보|문의|물어보)\S*\s*(?:중|있)")


# a time said without numbers ('오후에', '점심 먹고', '하루 종일'): croScan asks for the clock times
VAGUE_TIME = re.compile(r"오전|오후|아침|점심|저녁|밤\s*(?:에|부터|까지|중)|새벽|퇴근|출근|종일|반나절")
# a time when there is no work at all: '오전 작업은 안 합니다', '오후에는 안 했습니다' (not '오전에는 가스 안 쓰고 용접합니다')
# ('오전에는 작업하지 않습니다', '오전 작업은 하지 않습니다', '오전에는 작업이 없습니다', '저녁엔 안 할 겁니다')
NO_WORK_TIME = re.compile(r"(?:오전|오후|아침|점심|저녁|밤|새벽)\s*(?:에는|엔|에|은|는)?\s*(?:(?:작업|일)\s*(?:은|는|을|이|가)?\s*)?"
                          r"(?:(?:안|못)\s*(?:합|해|했|할|함|하)|하지\s*(?:않|못)|없)")
# an answer that decides nothing ('상황 봐서', '알아서', '그때그때', '나중에 정함') or is not words ('ㅇㅇ', '?')
UNDECIDED = re.compile(r"상황\s*(?:봐서|보고|에\s*따라)|그때\s*그때|알아서|적당히|대충|나중에\s*(?:정|알려|말)|미정|봐서\s*(?:할|정)|현장\s*(?:에서|보고)\s*(?:정|판단)")


# a clause that leaves the thing open ('가우징 가스 미정', '지지 여부 확인 필요', '올라갈지 미정'): not said either way
# (최종 검토 2026-11-01: H2·H3·L5·LI2·LO4·LO5 closed on such words — Codex final #4 fixed only the items it named)
OPEN = re.compile(r"미정|확인\s*필요(?!\s*(?:없|X))|확인\s*예정|모름|모르겠|협의\s*중|정해지지\s*않|정하지\s*않")


def said(text, rx, hedged=False):
    """How the text speaks of rx, clause by clause: True (it is so), False (it is not: '가스는 안 씀'),
    None (not said, or only in a condition: '다른 작업 없으면', or not sure: '아마 없을 거예요', or left open: '가스 미정').
    Any plain 'it is so' wins. hedged=True counts a not-sure mention as said (to notice a possible contradiction, never
    to fill a value)."""
    out = None
    for cl in CLAUSE.split(text or ""):
        if HEDGE.search(cl):
            if hedged and re.search(rx, cl):
                out = True
            continue
        for m in re.finditer(rx, cl):
            after = cl[m.end():m.end() + 12]
            nxt = re.search(rx, after)
            after = after[:nxt.start()] if nxt else after
            if COND.search(after) or COND.search(cl[:m.start()]):
                continue
            if OPEN.search(cl[m.end():m.end() + 20]):    # 「가스 사용 여부 미정」: that thing is left open (not said)
                continue
            v = not (NEG.search(after) or PRENEG.search(cl[max(0, m.start() - 10):m.start()]))
            out = v if out is None else (out or v)
    return out


# two candidate numbers: '2~3개', '2개~3개', '3m~4m', '3개 또는 4개', '3개나 4개'
# (both numbers are counts or heights: '3BAY에서 6개', '12-14칼럼', 'OH-21-03' are not two values)
_UNIT = r"(?:개소|개|EA|ea|군데|곳|부위|장|m|M|미터)"
TWO_VALUES = re.compile(rf"(?<![\d.A-Za-z-])\d+(?:\.\d+)?\s*{_UNIT}?\s*(?:[~\-–～]|또는|아니면|혹은|이나|나\s)\s*\d+(?:\.\d+)?\s*{_UNIT}")


def _plain_number(text, rx, cast, not_after=None):
    """The last number rx finds in a plain clause: not in a condition ('6개 있으면'), not denied ('6개 아님'),
    not right after not_after ('반경 5m' is a distance, not a height)."""
    got = None
    for cl in CLAUSE.split(text or ""):
        if COND.search(cl) or HEDGE.search(cl):
            continue
        two = [x.span() for x in TWO_VALUES.finditer(cl)]
        for m in rx.finditer(cl):
            if any(a <= m.start() < b for a, b in two):
                continue
            if (NEG.search(cl[m.end():m.end() + 6]) or (not_after and re.search(not_after, cl[max(0, m.start() - 8):m.start()]))
                    or re.search(r"\d\s*(?:[~\-–～]|에서)\s*$", cl[:m.start()])):          # '2~3개', '3~4m': two values
                continue
            got = cast(m.group(1))
    return got


def count_in(text):
    return _plain_number(text, COUNT, int)


DISTANCE = r"반경|거리|이격|떨어|간격|폭|길이|범위|주변|둘레|통로"


def height_in(text):
    return _plain_number(text, HEIGHT, float, DISTANCE)


CONC = r"다른\s*(?:작업|팀)|병행|동시\s*작업|옆\s*(?:\d*\s*BAY|칼럼|블록|팀)|타\s*(?:팀|부서|업체)"
# answers that describe another team's work (LI3·LO6: another crane's run or maintenance on the same rail)
ABOUT_OTHERS = {"B3", "C3", "C5.B3", "C5.concurrent", "LI3", "LO6"}
# work words of each kind; a sentence that names work of another kind is about another job
OWN = {"hot": r"용접|절단|가우징|보수|취부|검사|사상|그라인딩", "confined": r"진입|검사|청소|회수|보수|용접|점검",
       "height": r"러그|절단|회수|사상|그라인딩", "lifting": r"인양|반출|이동|운반|옮|반전", "loto": r"정전|차단|복구|수리|교체|점검|시험|검사"}
WORKS = r"도장|족장|비계|사상|그라인딩|청소|취부|인양|반출|용접|절단|가우징|정전|진입|검사|러그"


def other_work(text, kind=None):
    """Work of another kind the text names in a plain clause ('도장 작업 시간은 14~16시' on a hot-work permit)."""
    out = set()
    for cl in CLAUSE.split(text or ""):
        if COND.search(cl):
            continue
        for m in re.finditer(WORKS, cl):
            w = m.group(0)
            # the denial that belongs to this word: up to the next linking ending ('…14~16시이며 가스 사용은 없음')
            rest = re.split(r"(?:이며|이고|하며|하고|며|고|지만|는데)\s", cl[m.end():], maxsplit=1)[0]
            if not (kind and re.fullmatch(OWN[kind], w)) and not NEG.search(rest):
                out.add(w)
    return out


def own_text(text, kind=None):
    """The clauses of a free answer about this work: a clause about another team or another kind of work
    ('옆 5BAY에서 도장 작업 있음') says nothing about this permit's place, IDs, count or height."""
    return " ".join(cl for cl in CLAUSE.split(text or "")
                    if not re.search(CONC, cl) and not other_work(cl, kind) and not HEDGE.search(cl))


def work_windows(text, dates, kind=None, force=None, amb=None):
    """Time windows a free answer gives for this work: only plain sentences that speak of the work time
    ('실제 작업 시간은 09:00~13:00'). Not taken: a condition, a denied time ('…이 아닙니다'), another job
    ('옆 BAY 도장 작업 시간은 14~16시': another team or work of another kind), a step ('14:30 복구')."""
    out, count = {}, {"ampm": [0], "date": [0]}
    for sent in re.split(r"[;\n]|(?<!\d)\.|\.(?!\d)", text or ""):          # '10.27 09~11' stays one sentence
        if (not WORKTIME.search(sent) or COND.search(sent) or HEDGE.search(sent) or re.search(r"아닙|아님|아니|않", sent)
                or re.search(CONC, sent)):
            continue
        if other_work(sent, kind):
            continue
        for d, ws in _parse_windows(sent, dates, force, amb, count).items():
            out.setdefault(d, []).extend(ws)
    return out


def ask_item(kind, src, k):
    """The item of a check question: A1 (오전·오후) or A2 (날짜) about the k-th unclear part of one answer
    ('A1.T1', then 'A1.T1.2', 'A1.T1.3' …)."""
    return f"{'A1' if kind == 'ampm' else 'A2'}.{src}" + (f".{k + 1}" if k else "")


def _force(get, src):
    """The 작업반장's answers to the check questions about one source of times, per unclear part."""
    return {kind: {k: a.get("choice") for k in range(9) if (a := get(ask_item(kind, src, k)))} for kind in ("ampm", "date")}


# a typed value that only says it is not known yet: never a field's value (반영본, effective)
NOT_A_VALUE = re.compile(r"^\s*(?:모름|몰라요?|미정|미상|확인\s*중|나중에|-|—|\?+)\s*$")


# ---------------------------------------------------------------- reading a permit
# the questions whose answers say what the work is (target, equipment, method, count, height): their words are read
# for the permit's targets, cranes, count and height. Time, place, 병행 and asking-back answers are read only for
# their own value; a free answer is not read into the calculation at all.
SAID_SCOPE = {"D1", "D2", "D3", "D4", "D5", "X1", "X2", "X3", "X4", "X5", "H1", "H2", "H3", "CF1", "CF2", "HT1", "HT2",
              "LI1", "LI2", "LO1", "LO3", "LO4", "L2", "L3", "L5", "L6", "C1", "C2", "C4", "B4", "W1"}
# answers kept as named facts of this work for the checklist and the pair rules (P["facts"]), never read as its
# targets, count or place (CF3's panel is a power source, not a block; a count in it is not inspection points)
FACT_ITEMS = ("CF3", "CF4", "CF5", "D6", "D7", "LO5", "LO6", "LI3", "T8", "T9", "T4")


def withdrawn(answers):
    """the answers the foreman took back: X when he said of C6.X (the document now says otherwise) 「서류가 맞음」"""
    out = set()
    for a in answers or []:
        q = a.get("qid", "")
        if q.startswith("C6.") and a.get("choice") == "doc" and ":" in q:
            out.add(f"{q.split(':')[0][3:].split('~')[0]}:{q.split(':', 1)[1]}")
    return out


# C5.X 「추가로 적은 내용이 맞음」: X's earlier 「없음」 is replaced by the corrected sentence with X's positive choice
C5_POSITIVE = {"B3": "yes", "LI2": "text", "CF2": "text", "LO4": "text"}


def live_answers(answers):
    """THE answers to compute with (stable name; checklist.standing(), pairs.confirmed_facts, understand's callers and
    every reader but the history display use it): without the ones taken back (C6 「서류가 맞음」), and with an earlier
    「없음」 that a C5 「추가로 적은 내용이 맞음」 corrected replaced by that sentence as X's own answer ('아르곤 퍼지 라인
    V-12 연결 있음' becomes CF2's answer). The history (records) keeps every answer as given."""
    gone = withdrawn(answers)
    out = [a for a in answers or [] if a.get("qid") not in gone]
    fixed = {}
    for c in out:
        q = c.get("qid", "")
        if q.startswith("C5.") and c.get("choice") == "free" and ":" in q and q.split(":")[0][3:] in C5_POSITIVE:
            fixed[f"{q.split(':')[0][3:]}:{q.split(':', 1)[1]}"] = c
    res = []
    for a in out:
        c = fixed.get(a.get("qid"))
        if c and (c.get("value") or "").strip():
            x = a["qid"].split(":")[0]
            a = {k: v for k, v in a.items() if k != "read"}
            a.update(choice=C5_POSITIVE[x], value=c["value"], by=c["qid"], corrected=True)
        res.append(a)
    return res


def _said_scope(item):
    base = item.split(".")[0]
    return base in SAID_SCOPE or item.startswith(("B1.", "B2."))


def effective(fields, answers):
    """Permits with the values the cross-permit check uses (permit values overlaid by answers)."""
    live0 = live_answers(answers)
    stale = stale_answers(fields, live0)
    answers = [a for a in live0 if a["qid"] not in stale]
    ans = {a["qid"]: a for a in answers or []}
    perms = _permits(fields)
    frees = [(a["qid"].split(":")[1], a.get("value", "")) for a in answers or [] if a["qid"].startswith("FREE:")]
    free = [t for _, t in frees]
    for P in perms:
        p, pid = P["p"], P["permit_no"]
        P["form"] = {k: str(v.get("value") or "") for k, v in p.items() if isinstance(v, dict)}     # as written now
        P["stale"] = {a["qid"] for a in live0 if a["qid"] in stale and owner(a) == pid}
        get = lambda item: ans.get(f"{item}:{pid}")
        # a blank required field answered with its value (B1/B2) counts as that field's value, as on the 반영본 (QA #37);
        # the field objects are the client's: a copy is changed, never them
        for q, a in ans.items():
            it = q.split(":")[0]
            av = (a.get("read") or a.get("value") or "").strip()
            if (it.startswith(("B1.", "B2.")) and q.split(":")[1:2] == [pid] and a.get("choice") == "value" and av
                    and not NOT_A_VALUE.match(av)):
                k = it.split(".", 1)[1]
                if k in p and not _v(p, k):
                    p = P["p"] = {**p, k: {**p[k], "value": av}}
        P["windows"] = _windows(p)
        P["windows_src"] = "원본"
        # what the 작업반장 said about this permit: every answer value, and the closing free answers when the file
        # holds one permit (with several, a free answer cannot be put on one of them and is only kept as it is)
        # answers that describe another team's work (병행작업) and other-work clauses of a free answer are left out:
        # their place, block numbers and counts are not this permit's
        # a value kept only as typed (「모름」 after a second unreadable try) is never read as a value; a bare '6' given
        # for a count is that count
        mine = [a["value"] + ("개" if q.split(".")[0].split(":")[0] in ("HT1", "H1") and a["value"].strip().isdigit() else "")
                for q, a in ans.items() if q.split(":")[1:2] == [pid] and a.get("value") and a.get("choice") != "unknown"
                and q.split(":")[0] not in ABOUT_OTHERS and not (q.startswith("U1.") and a.get("choice") == "other")
                and _said_scope(q.split(":")[0])]
        P["said"] = " ".join(mine)
        P["text"] = " / ".join(_v(p, k) for k in ("hull_no", "location", "location_detail", "job", "job_detail", "hazards")) + " / " + P["said"]
        P["t5"] = {}                                        # row -> the T5 answer's choice (that row only, #12)
        # times in answers: what can mean two things ('2시~4시', '내일 …' on a permit of several days) is not used
        # until the 작업반장 answers croScan's check question about it (A1 오전·오후, A2 날짜): P["amb"]
        P["amb"] = []
        days_of = lambda: sorted(P["windows"]) or sorted({_v(p, f"date_{i}") for i in range(1, 8)} - {""})
        # the empty 작업일시 rows (T0.<row>): one reading for the cross-check and the 반영본; a row whose written values
        # say otherwise is kept as written in both (reflect.py lists it to be checked)
        P["t0"] = {}
        for q, a in sorted(ans.items()):
            if not (q.startswith("T0.") and q.split(":")[1:2] == [pid] and a.get("choice") == "value"):
                continue
            item = q.split(":")[0]
            row = int(item.split(".")[1]) if item.split(".")[1].isdigit() else 1
            amb = []
            av = a.get("read") or a.get("value", "")          # QA #39: the part of a long answer that is its value
            w = _parse_windows(av, t0_dates(p, av, row), _force(get, item), amb)
            placed = None if amb or not w else t0_row(p, w, row)
            P["t0"][row] = {"w": {d: list(x) for d, x in w.items()}, "amb": bool(amb), "row": row, "placed": placed,
                            "dated": bool(DATE_MD.search(av)) or bool(_v(p, f"date_{row}"))}
            if amb:
                P["amb"] += [dict(x, src=item) for x in amb]
            elif placed or (w and not any(_v(p, f"{k}_{row}") for k in ("date", "from", "to"))):
                P["windows"] = {**P["windows"], **w}
                P["windows_src"] = "신청자 답변"
        # T5 per row (#12): 「다음 날 끝남」 makes that row end the next morning; 「잘못 적음」 replaces that row's day; the
        # other reversed rows stay without a window until asked
        for i in range(1, 8):
            a = get(t5_item(i))
            d, x, y = _v(p, f"date_{i}"), _m(_v(p, f"from_{i}")), _m(_v(p, f"to_{i}"))
            if not a or x is None or y is None or y > x:
                continue
            P["t5"][i] = a.get("choice")
            if a.get("choice") == "overnight" and ISO.fullmatch(d):
                P["windows"].setdefault(d, []).append((x, 24 * 60 + y))
            elif a.get("choice") == "fix":
                amb = []
                w = _parse_windows(a.get("read") or a.get("value", ""), [d] if ISO.fullmatch(d) else days_of(), _force(get, t5_item(i)), amb)
                if amb:
                    P["amb"] += [dict(x_, src=t5_item(i)) for x_ in amb]
                elif w:
                    P["windows"] = {**P["windows"], **w}
                    P["windows_src"] = "신청자 답변"
        P["t7"] = t7_target(P)
        P["t7_stale"] = t7_stale(P, ans)
        if P["t7_stale"]:
            ans = {k: v for k, v in ans.items() if k != f"T7:{pid}"}
        # the requested windows as written and as the 작업일시 answers T0·T5 correct them: kept apart from what a later
        # answer narrows or widens, so the matching can use either (research N4-MT03, N5 2.5 「원문 시간창 보존」)
        P["windows_req"] = {d: _union(ws) for d, ws in P["windows"].items()}
        # stages of the work, each kind apart (never overwritten by another): "move" a lift's moving part (T1, N4-MT03),
        # "written" the part the permit's time was when a T6 「특정 단계만」 answer gave the whole work
        P["windows_stage"] = {}
        P["full_end"] = {}                        # {date: the whole work's end} when the time written was a stage (T6)
        for item, choice in (("T1", "partial"), ("T2", "partial"), ("T6", "retime"), ("T7", "check"), ("T6", "stage")):
            a = get(item)
            if a and a.get("choice") == choice:
                amb = []
                dates = days_of()
                if item == "T7":                     # a correction of the row asked about (t7_target): its day only
                    dates = [P["t7"][1]] if P["t7"] else dates
                w = _parse_windows(a.get("read") or a.get("value", ""), dates, _force(get, item), amb)
                if amb:
                    P["amb"] += [dict(x, src=item) for x in amb]
                elif w and item == "T1" and P["kind"] == "lifting":
                    # a lift's T1 answer is the moving part only (N4-MT03): kept as a stage; the whole window stays,
                    # and a stage outside it is added to it, never cut (it is asked once, C6.T1)
                    P["windows_stage"]["move"] = {d: _union(ws) for d, ws in w.items()}
                    P["windows"] = _hull_add(P["windows"], w)
                elif w and choice == "stage":
                    # 「특정 단계만 적음」: what is written is a stage; the answer is the whole work, start to the end of
                    # recovery·inspection·hand-over (N1 MT13, N3 MT12, N5 MT12). The window grows to it, never shrinks.
                    P["windows_stage"]["written"] = {d: _union(ws) for d, ws in P["windows"].items()}
                    P["windows"] = _hull_add(P["windows"], w)
                    P["full_end"] = {d: max(b for _, b in ws) for d, ws in w.items()}
                    P["windows_src"] = "신청자 답변(전체 작업 시간)"
                elif item == "T7" and P["t7"]:
                    # the row asked about is replaced, that one window (another row of the day keeps its time, also an
                    # equal one); an answer of another day or of several windows is not this row's time: not placed,
                    # the 반영본 lists it to be checked
                    _, d7, a7, b7, _ = P["t7"]
                    if w and set(w) == {d7} and len(w[d7]) == 1:
                        keep = [tuple(x) for x in P["windows"].get(d7, [])]
                        if (a7, b7) in keep:
                            keep.pop(keep.index((a7, b7)))
                        P["windows"] = {**P["windows"], d7: _union(keep + [tuple(x) for x in w[d7]])}
                        P["windows_src"] = "신청자 답변"
                        P["t7_fixed"] = True
                elif w:
                    # a time given with its day ('10/29 09~11', a plan's time) is that day's only: the other days keep
                    # the times written for them; T6 「실제 시간 다시 입력」 replaces the window (it is a correction)
                    P["windows"] = {**P["windows"], **w} if item == "T7" or dated(a.get("read") or a.get("value", "")) else w
                    P["windows_src"] = "신청자 답변"
        a = get("T1")
        # for a lift the T1 answer is the moving part only (N4-MT03): a stage, not the whole job
        P["time_meaning"] = None if not a or a.get("choice") not in ("yes", "partial") else             "stage" if P["kind"] == "lifting" and a["choice"] == "partial" else "actual"
        if P["full_end"]:
            P["time_meaning"] = "full"                # the windows hold the whole work, windows_stage the part written
        # a free answer is kept as said and asked about (U1·A3·C5) but not read into the calculation: what it says
        # for a question is proposed (interpret) and counts once the foreman confirms it (design §2·§4.2)
        P["free"] = " ".join(free) if len(perms) == 1 else ""
        P["frees"] = frees if len(perms) == 1 else []
        # an unclear time in a free answer ('2시~4시') is asked back (A1·A2, as for any answer); once the foreman has
        # answered that check, the time he made clear is his own confirmed answer and is used. A clear time in a free
        # answer is not used here: it is proposed (interpret) and counts once confirmed.
        for n, t in P["frees"]:
            amb, force = [], _force(get, f"F{n}")
            w = work_windows(t, days_of(), P["kind"], force, amb)
            if amb:
                P["amb"] += [dict(x, src=f"F{n}") for x in amb]
            elif w and any(force.values()):
                if P["kind"] == "lifting" and "움직" in t:          # the moving part: a stage, kept apart (N4-MT03)
                    P["windows_stage"]["move"], P["windows"] = {d: _union(ws) for d, ws in w.items()}, _hull_add(P["windows"], w)
                    P["time_meaning"] = "stage"
                else:
                    P["windows"], P["windows_src"] = w, "신청자 답변(추가 전달, 시간 확인함)"
                    P["time_meaning"] = "actual"
        # a free answer croScan did not understand, or a time without numbers in it ('오후에'), was asked back (U1, A3):
        # a time given in that answer is used like any time answer
        for n, _ in P["frees"]:
            for src in (f"A3.F{n}", f"U1.F{n}"):
                a = get(src)
                if a and a.get("choice") == "time" and a.get("value", "").strip():
                    amb = []
                    w = _parse_windows(a["value"], days_of(), _force(get, src), amb)
                    if amb:
                        P["amb"] += [dict(x, src=src) for x in amb]
                    elif w:
                        P["windows"], P["windows_src"] = w, "신청자 답변(추가 전달)"
                        P["time_meaning"] = P["time_meaning"] or "actual"
        # each day's windows as a union (a time is never counted twice; the requested ones kept as written)
        P["windows"] = {d: _union(ws) for d, ws in P["windows"].items()}
        # the ember check's end (T4): read with its day and its 오전·오후 (one parser, clock_read). It stretches the
        # windows for the matching (_span) and is never evidence that the residual hazard is gone.
        # {work date: minutes from that date's 00:00} — the end applies to its own date only (#13); a day relation
        # that is not clear (a time before the work's end, a date that is no work day) is asked once (A5.T4)
        P["residual"], P["residual_ask"] = {}, None
        a = get("T4")
        if a and a.get("choice") == "time":
            v = a.get("read") or a.get("value", "")
            m, ambig, nextday = clock_read(PLACE_SPAN.sub(" ", DATE_MD.sub(" ", v)))
            days = sorted(d for d, ws in P["windows"].items() if ws)
            md = DATE_MD.search(v)
            day, plus, sure = (days[-1] if days else None), (24 * 60 if nextday else 0), not md
            if md and days:
                iso = md.group(0) if md.group(1) else f"{days[-1][:4]}-{int(md.group(4)):02d}-{int(md.group(5)):02d}"
                prev = next((d for d in days if next_iso(d) == iso), None)
                day, plus, sure = (iso, 0, True) if iso in days else (prev, 24 * 60, True) if prev else (days[-1], 0, False)
            # an end given without a date is each work day's (a daily hot work's watch ends every day, as before the
            # per-date reading); with a date, that date only
            on = [day] if md else days
            back = get("A5.T4")
            if back and back.get("choice") == "next" and m is not None and day:
                for d in on:
                    P["residual"][d] = m + 24 * 60
            elif back and back.get("choice") == "fix" and day:
                m2, ambig2, next2 = clock_read(back.get("value", ""))
                if m2 is not None and not ambig2:
                    for d in on:
                        P["residual"][d] = m2 + (24 * 60 if next2 else 0)
            elif m is not None and not ambig and day:
                ends = {d: max(b for _, b in P["windows"][d]) for d in on if P["windows"].get(d)}
                if not sure or (not md and not nextday and any(m < e for e in ends.values())):
                    P["residual_ask"] = (day, m)                 # the next day, or a slip? asked, not guessed
                else:
                    for d in ends:
                        P["residual"][d] = m + plus
        P["moments"] = []
        a = get("T3")
        if a and a.get("choice") == "time":
            P["moments"] = [int(h) * 60 + int(mi or 0) for h, mi in re.findall(r"(\d{1,2})(?::(\d{2}))", a.get("value", ""))]
        a1, a2 = _v(p, "location"), _v(p, "location_detail")
        loc = a1 if a2 and re.sub(r"\s", "", a2) in re.sub(r"\s", "", a1) else " ".join(x for x in (a1, a2) if x)
        a = get("L1")
        if a and a.get("choice") == "place" and a.get("value", "").strip():
            loc = a.get("read") or a["value"]
        for item in ("A4.cols", "L7"):                          # A4: a column range written backwards, asked once
            a7 = get(item)
            if a7 and a7.get("choice") == "place" and a7.get("value", "").strip():
                loc = _replace_cols(loc, a7.get("read") or a7["value"])
        for n, _ in P["frees"]:                               # a place given when a free answer was asked back (U1)
            u = get(f"U1.F{n}")
            if u and u.get("choice") == "place" and u.get("value", "").strip():
                loc = u["value"] if parse_place(u["value"])["bays"] else f"{loc} {u['value']}"
        P["place"] = parse_place(loc)
        P["place"]["whole"] = bool(a and a.get("choice") == "whole" and P["place"]["level"] <= 1)
        for item in ("L2", "L3", "L5"):
            a = get(item)
            if a and a.get("value", "").strip() and a.get("choice") != "unknown":     # a value kept as 「모름」 adds nothing
                extra = parse_place(a["value"])
                P["place"]["bays"] |= extra["bays"]
                P["place"]["layer"] = extra["layer"] or P["place"]["layer"]
                if item == "L3" and extra["layer"]:
                    P["place"]["level"] = max(P["place"]["level"], 4)
        if not P["place"]["layer"] and P["kind"] != "lifting":   # 'E42P 블록 상부' in the job text says where too
            P["place"]["layer"] = parse_place(" ".join(_v(p, k) for k in ("job", "job_detail")) + " " + P["said"])["layer"]
        text = " ".join(_v(p, k) for k in ("hull_no", "location", "location_detail", "job", "job_detail")) + " " + P["said"]
        P["targets"] = ids(text)
        P["cranes"] = set(CRANE.findall(text))
        P["count"] = count_in(" ".join(_v(p, k) for k in ("job", "job_detail")) + " " + P["said"])
        P["height"] = _num(_v(p, "work_height")) or height_in(" ".join(_v(p, k) for k in ("location_detail", "job", "job_detail")) + " " + P["said"])
        P["links"] = {(q.split(":")[0], q.split(">")[1]): a.get("choice") for q, a in ans.items()
                      if q.split(":")[0] in ("X2", "X4", "X5") and q.split(":")[1].split(">")[0] == pid and ">" in q}
        P["concurrent"] = _v(p, "concurrent").upper()
        b3, c5 = get("B3"), get("C5.concurrent")              # what the 반영본 writes in 병행여부 (QA #37)
        if not P["concurrent"] and b3 and b3.get("choice") in ("yes", "no"):
            P["concurrent"] = "Y" if b3["choice"] == "yes" else "N"
        if (c5 and c5.get("choice") == "free") or ((get("C5.B3") or {}).get("choice") == "free"):
            P["concurrent"] = "Y"
        # extra values for the later pair check, shown on page 2 (section 2)
        P["notes"] = {lab: (ans.get(f"{i}:{pid}") or {}).get("value", "") for i, lab in NOTE_ITEMS
                      if (ans.get(f"{i}:{pid}") or {}).get("value", "").strip() and (ans.get(f"{i}:{pid}") or {}).get("choice") != "unknown"}
        # this work's answered facts by name, for the checklist and the pair rules (contract in impl/multiturn.md):
        # {item: {choice, value}}; CF3 also its power sources (panel IDs of his own clauses, not another team's)
        P["facts"] = {}
        for i in FACT_ITEMS:
            a = get(i)
            if a and a.get("choice") not in (None, "unknown"):
                P["facts"][i] = {"choice": a["choice"], "value": (a.get("read") or a.get("value") or "").strip(), "src": "answer"}
        P["facts"].update({k: v for k, v in doc_facts(P).items() if k not in P["facts"] and not get(k)})
        if "CF3" in P["facts"]:
            P["facts"]["CF3"]["sources"] = sorted(ids(own_text(P["facts"]["CF3"]["value"], P["kind"])))
    return perms


def doc_facts(P):
    """the facts the document itself settles, so their questions were not asked (for the pre-submit card):
    {item: {"choice": "doc", "value": the clauses, "src": "doc"}} — each only when every atom is in a settled clause"""
    from . import need_catalog as N
    kind, dt = P["kind"], doc_text(P)
    want = {"confined": {"CF3": [POWER_SRC], "D6": [LIVE_NONE + "|" + LIVE_WHO], "D7": [TEST_MEDIUM, TEST_START, TEST_END],
                         "CF2": [a[2] for a in N.ATOMS["CF2"]]},
            "hot": {"T4": [EMBER_SAID], "T8": [NIGHT_SUPPORT, NIGHT_HANDOVER], "L6": [CONTROL_RANGE]},
            "height": {"T4": [EMBER_SAID], "L6": [CONTROL_RANGE], "HT2": [a[2] for a in N.ATOMS["HT2"]]},
            "lifting": {"L6": [CONTROL_RANGE], "LI3": [RAIL_SAID]},
            "loto": {"LO6": [RAIL_SAID], "LO3": [a[2] for a in N.ATOMS["LO3"] if a[3]]}}.get(kind, {})
    out = {}
    for item, rxs in want.items():
        if item == "D6" and not P["p"].get("commissioning", {}).get("value") or item == "D7" and not P["p"].get("pressure_use", {}).get("value"):
            continue
        cls = [confirmed(dt, rx) for rx in rxs]
        if all(cls):
            out[item] = {"choice": "doc", "value": " / ".join(dict.fromkeys(cls)), "src": "doc"}
    return out


def _row_of(a):
    """the 작업일시 row a time question was about (its keys 'p1.from_2' …), else 1"""
    for k in ((a.get("q") or {}).get("keys") or []):
        m = re.search(r"(?:date|from|to)_(\d)$", k)
        if m:
            return m.group(1)
    return "1"


def _union(ws):
    """the windows of one day as a union: overlapping or touching ones merged (a time is never counted twice)"""
    out = []
    for a, b in sorted(ws):
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


COLS_RX = re.compile(r"\d{1,2}\s*[-~]\s*\d{1,2}\s*(?:칼럼|축)|\d{1,2}\s*(?:칼럼|축)")


def _replace_cols(loc, said_):
    """the place with an answer's place in it, structurally: an answer with a BAY is the whole place; one with columns
    replaces the columns written (never appended after them: the first range would be read again); else it is added"""
    pl = parse_place(said_)
    if pl["bays"]:
        return said_
    m = COLS_RX.search(said_)
    if m and COLS_RX.search(loc):
        rest = COLS_RX.sub(" ", said_).strip()                  # 'E41P 동측' said with the columns stays
        return (COLS_RX.sub(m.group(0), loc, count=1) + (f" {rest}" if rest else "")).strip()
    return f"{loc} {said_}".strip()


def _span(P, d):
    """Windows on date d, the last one stretched to the residual-hazard end (design T4, D4)."""
    ws = sorted(P["windows"].get(d, []))
    r = (P.get("residual") or {}).get(d)                   # that date's own ember-check end only (never a release)
    if ws and r and r > ws[-1][1]:
        ws[-1] = (ws[-1][0], r)
    return ws


def overlap(P, Q):
    for d in sorted(set(P["windows"]) & set(Q["windows"])):
        for a1, b1 in _span(P, d):
            for a2, b2 in _span(Q, d):
                if max(a1, a2) < min(b1, b2):
                    return d, max(a1, a2), min(b1, b2)
    return None


def _key(a, b):
    return tuple(sorted((a, b)))


def pairs(perms):
    """Every pair of permits with its priority (design 5): 1 즉시 조정, 2 확인 후 판단, 3 정보 부족, 9 기록만."""
    out = []
    for i, P in enumerate(perms):
        for Q in perms[i + 1:]:
            ov = overlap(P, Q)
            info = PAIR.get(_key(P["kind"], Q["kind"]), ("", "", "U", ""))
            shared = sorted(P["targets"] & Q["targets"])
            cranes = sorted(P["cranes"] & Q["cranes"])
            linked = [lab for k, lab in (("X2", "가스계통 연결"), ("X4", "공통지지"), ("X5", "공유전원"))
                      if "yes" in (P["links"].get((k, Q["permit_no"])), Q["links"].get((k, P["permit_no"])))]
            pp, qp = P["place"], Q["place"]
            fac_ok = not (pp["factory"] and qp["factory"] and pp["factory"] != qp["factory"])
            whole = (pp.get("whole") or qp.get("whole")) and pp["factory"] and pp["factory"] == qp["factory"]
            same_bay = fac_ok and (bool(pp["bays"] & qp["bays"]) or bool(whole))
            unknown = (pp["level"] <= 1 and not pp.get("whole")) or (qp["level"] <= 1 and not qp.get("whole"))
            reasons = []
            if shared:
                reasons.append("같은 대상 " + ", ".join(shared))
            if cranes and not set(cranes) <= set(shared):
                reasons.append("같은 설비 " + ", ".join(cranes))
            reasons += linked
            if not ov:
                if shared or cranes or same_bay:
                    out.append(_pair(P, Q, 9, None, info, reasons or ["같은 BAY"], "위험시간대가 겹치지 않음"))
                continue
            if reasons:
                level, why = 1, "연결 확인됨: " + ", ".join(reasons)
            elif same_bay:
                # a BAY is long (no fixed size: F01 p389 is a synthetic layout): being in the same BAY is not yet a pair risk. With both column
                # ranges known, only overlapping or near columns stay; a lift moves along its route, so it is not
                # judged by its start columns.
                ra, rb = pp.get("colrange"), qp.get("colrange")
                gap = None
                if ra and rb and "lifting" not in (P["kind"], Q["kind"]) and not whole:
                    gap = max(ra[0], rb[0]) - min(ra[1], rb[1])
                    if gap > NEAR_COLS:
                        x = _pair(P, Q, 9, ov, info, [], f"같은 BAY지만 칼럼 {gap}칸 떨어짐 ({pp['cols']} / {qp['cols']})")
                        x["gap"] = gap
                        out.append(x)
                        continue
                where = (f"같은 {pp['factory']}공장 (공장 전체 작업)" if whole and not (pp["bays"] & qp["bays"]) else
                         f"같은 {pp['factory'] or ''}공장 {'/'.join(sorted(pp['bays'] & qp['bays']))}BAY")
                near = "" if gap is None else (", 칼럼 겹침" if gap <= 0 else f", 칼럼 {gap}칸 차이")
                route = ", 인양 경로가 이 BAY를 지남" if "lifting" in (P["kind"], Q["kind"]) else ""
                level, why = 2, where + near + route + ", 연결 미확인"
            elif unknown or not (pp["bays"] and qp["bays"]):
                level, why = 3, "장소가 넓거나 BAY가 없어 비교 불가"
            else:
                out.append(_pair(P, Q, 9, ov, info, [], ("다른 공장" if not fac_ok else "다른 BAY") + ", 공유 대상 없음"))
                continue
            x = _pair(P, Q, level, ov, info, reasons, why)
            x["gap"] = gap if level == 2 else None
            out.append(x)
    hit = lambda x: any(x["overlap"] and x["overlap"][1] <= m <= x["overlap"][2] for m in x["moments"])
    near = lambda x: 50 if x.get("gap") is None else max(x["gap"], 0)     # closer columns first, unknown after known
    out.sort(key=lambda x: (x["level"], not hit(x), near(x), -(x["minutes"]), x["status"] != "C"))
    return out


def _pair(P, Q, level, ov, info, reasons, why):
    link, modes, status, action = info
    return {"a": P["no"], "b": Q["no"], "a_no": P["permit_no"], "b_no": Q["permit_no"], "a_who": _who(P), "b_who": _who(Q),
            "kinds": f"{N_OF.get(P['kind'], '?')}×{N_OF.get(Q['kind'], '?')}", "level": level,
            "overlap": ov, "when": f"{ov[0]} {hm(ov[1])}~{hm(ov[2])}" if ov else "", "minutes": (ov[2] - ov[1]) if ov else 0,
            "reasons": reasons, "why": why, "link": link, "modes": modes, "status": status, "action": action,
            "moments": P["moments"] + Q["moments"]}


# ---------------------------------------------------------------- questions
# Why the 작업반장 is asked at all: the 안전관리자 will later look for pair risks across the day's
# permits, and that needs time, place, target and shared-resource values precise enough to compare.
# Two tiers keep it bearable:
#   core   needed to compare at all (time, place/target, required blanks, the kind's hazard, category)
#   extra  makes the comparison sharper (shared crane / gas / power, control zone, residual hazard ...);
#          offered once after the core ones, and the 작업반장 may stop there ("여기까지")
# A value that is very likely right because of the kind of work is not asked: it is written to
# page 2 as a rule estimate ("규칙 추정") instead (e.g. no 호선 for a crane repair).
EQUIP = re.compile(r"크레인|설비|제어반|배전|분전|공용|전기|변전|컴프레서|펌프")


def _fp(values):
    """a short hash of the form values a question was asked about"""
    return hashlib.sha256(json.dumps([str(v or "").strip() for v in values], ensure_ascii=False).encode()).hexdigest()[:10]


# what a question's answer depends on, beyond the fields it points at (Codex batch-2 #7): a time question reads every
# 작업일시 row and the 주간·야간 tick; a place question the place; a question about the work the work's own words. A
# checking question (A·C5·C6·U1) and a blank-field fill (B1·B2) depend on their own fields only.
DEP_TIME = tuple(f"{k}_{i}" for i in range(1, 8) for k in ("date", "from", "to")) + ("day", "night")
DEP_PLACE = ("location", "location_detail")
DEP_WORK = ("job", "job_detail", "hazards", "location_detail")


def _deps(item, keys):
    if item.startswith(("A1.", "A2.", "A3.", "A4.", "A5.", "U1.", "C5.", "C6.", "B1.", "B2.")):
        return sorted(set(keys))
    head = item.split(".")[0]
    extra = DEP_TIME if head.startswith("T") else DEP_PLACE if head.startswith("L") and head not in ("LI1", "LI2", "LI3", "LO1",
                                                                                                    "LO3", "LO4", "LO5", "LO6") else DEP_WORK
    return sorted(set(keys) | set(extra))


def _q(item, P, keys, signal, text, choices, prio, other=None, original="", tier="core"):
    keys = [re.sub(r"^p\d+\.", "", k) for k in keys]            # a key handed on already with its page (C5): once only
    form = P.get("form") or {}
    deps = _deps(item, keys)
    return {"qid": f"{item}:{P['permit_no']}" + (f">{other['permit_no']}" if other and item != "X1" else ""), "item": item, "page": P["no"], "permit_no": P["permit_no"], "who": _who(P),
            "keys": [f"p{P['no']}.{k}" for k in keys], "signal": signal, "text": text, "choices": choices,
            "prio": ((0 if tier == "core" else 10) + prio[0], prio[1]), "tier": tier,
            "other": other["no"] if other else None, "original": original,
            # the form values it depends on, as they were when asked: an answer given before the foreman changed them
            # is asked again (stale_answers)
            "fp_keys": [f"p{P['no']}.{k}" for k in deps], "fp": _fp([form.get(k, "") for k in deps])}


def stale_answers(fields, answers):
    """the answers given about form values the foreman has changed since (최종 검토 2026-11-01: only T7 was asked again;
    「관련값이 바뀌면 다시 묻기」): its question's fields now differ from when it was asked. A blank-field answer (B1·B2)
    is that field's value itself; an answer without the mark (older) stands."""
    out = set()
    for a in answers or []:
        q = a.get("q") or {}
        if not q.get("fp") or not q.get("fp_keys") or str(a.get("qid", "")).startswith(("B1.", "B2.")):
            continue
        now = _fp([(fields.get(k) or {}).get("value", "") if isinstance(fields.get(k), dict) else "" for k in q["fp_keys"]])
        if now != q["fp"]:
            out.add(a["qid"])
    return out


def owner(a):
    """the permit an answer is about: its question's permit, else the qid's (an X·C5 question 「A>B」 is A's)"""
    q = a.get("q") or {}
    return q.get("permit_no") or str(a.get("qid", "")).split(":", 1)[-1].split(">")[0]


def answers_now(fields, answers):
    """the answers every reader calculates with: live (C6 withdrawals out) and not stale (asked on values changed since)"""
    live = live_answers(answers)
    stale = stale_answers(fields, live)
    return [a for a in live if a["qid"] not in stale]


C = lambda cid, label, status, ask=None: {"id": cid, "label": label, "status": status, **({"ask": ask} if ask else {})}
UNKNOWN = C("unknown", "모름", "미확인")

# ---------------------------------------------------------------- 작업반장 view (one permit as filed)
# The research for the five 대조립 non-routine works (hot/confined/height/heavy/loto 2.5~2.8) gives the rule:
# ask only for what is needed now and missing, unclear, contradictory, or an unexplained gap to a reference model
# whose conditions match; reuse what the permit and earlier answers already say; never ask for day-of-work boxes
# (현장 안전조치, 추가정보: "작업당일 작업시작 전 체크"), precise values (좌표·질량·풍량), or proof of steps not due yet.
# Every item is asked at most once per permit; 「모름」 closes it (page 2 「안전팀 확인」). When nothing is left the
# chat always ends with CLOSING; a free answer is read for values and may open only items not asked before.
CLOSING = "추가로 말씀하실 것이 있나요? 없으면 「없음 · 검토 마치기」를 눌러 주세요."
ASK_BACK = 3        # at most this many asking-back questions per permit (unclear time, date or words): no endless loop
DAY_OF_VALUES = {v[0] for k in PK.KINDS for v in PK.KINDS[k]["c"][2]} | {PK.KINDS[k]["d"][2][0] for k in PK.KINDS}
NOT_FOREMAN = {"permit_type", "double_check"}       # 허가구분·2중점검: who decides is not known (research process p16)
VERB = {"hot": "절단·용접을", "confined": "안에 들어가 작업을", "height": "러그 절단·회수를", "loto": "전원을 끊고 수리를"}
RX = {
    "hot_local": r"가우징|파내|국부|균열|기공|크랙|용접부\s*보수",
    "hot_replace": r"교체|떼어|완전\s*분리|판재|부재\s*분리",
    "hot_reweld": r"재용접만|용접만",
    "hot_remove": r"제거만|파내기만",
    "hot_deep": r"깊은|심한",
    "hot_method": r"가우징|가스\s*절단|산소\s*절단|플라즈마|그라인더|그라인딩|기계\s*절단|아크|CO2|피복|TIG|MIG|FCAW|SMAW|LPG|아세틸렌|프로판",
    "support": r"받침|지지|회수|내려|내리|크레인|슬링|체인블록|호이스트|안착",
    "cf_inspect": r"검사|점검|확인|측정|조사", "cf_clean": r"청소|잔재|이물", "cf_recover": r"회수|꺼내",
    "cf_repair": r"용접|보수|취부|그라인|사상|절단", "cf_partial": r"머리|상체|들여다",
    "cf_entry": r"진입|들어가|들어감|이동|머리|상체|들여다", "cf_repeat": r"반복|교대|재진입|여러\s*번|\d+\s*(?:회|번)\s*진입",
    "cf_link": r"아르곤|질소|퍼지|배관|파이프|가스\s*(?:공급|라인|배관|호스|사용)", "cf_isolated": r"차단|격리|블라인드|맹판|밸브\s*잠|공급\s*중지",
    "ht_gas": r"가스\s*절단|산소|LPG|아세틸렌|프로판|가스로", "ht_plasma": r"플라즈마", "ht_mech": r"그라인더|기계\s*절단|커터|톱",
    "ht_recover": r"내려|내리|안착|적치|슬링|로프|호이스트|바구니|크레인|받아",
    "route": r"→|->|경유|통로|에서[^,.;\n]{1,24}?로\s*(?:옮|이동|반출|운반|내리|간)",
    "li_tandem": r"공동\s*인양|탠덤|크레인\s*2대|두\s*대", "li_turn": r"반전|뒤집|턴오버", "li_rotate": r"회전|방향\s*전환",
    "li_vehicle": r"차량|트레일러|트랜스포터", "li_inside": r"(?:블록|내부)\s*안(?:에|에서)?[^,.;]{0,12}(?:작업|사람|인원|명)|내부\s*(?:인원|작업)|잔류\s*인원|인원\s*확인|안(?:에서)?\s*(?:작업|사람)|미고정|부착물|붙어|연결선",
    "lo_diag": r"점검|진단|원인|고장\s*확인|이상\s*확인", "lo_module": r"교체|인버터|모듈|부품", "lo_repair": r"수리|정비|보수", "lo_install": r"증설|신설|설치|이설",
    "lo_access": r"거더|상부|트롤리|운전실|발판|사다리|제어반\s*앞|지상반|전기실",
    "lo_restore_time": r"(?:복구|시험|재투입|투입)[^,.;\n]{0,12}\d{1,2}\s*(?::\d{2}|시)|\d{1,2}\s*(?::\d{2}|시)[^,.;\n]{0,6}(?:복구|시험|재투입|투입)",
}
# a gas said (or said to be none) for hot work; a support relation said (not a recovery word)
HOT_GAS = (r"가스|산소|LPG|프로판|아세틸렌|CO2|탄산|아르곤|질소|불활성|압축\s*공기|에어|피복\s*아크|SMAW|전기\s*용접만|"
           r"가스\s*(?:없|안)")
HOLDS = r"받치|지지|받침|하중|받는\s*(?:것|구조)"
HOT_INSIDE = r"화기|용접(?!\s*(?:상태|부|선|비드|검사|품질))|용단|절단|가우징|그라인딩|그라인더"   # '용접 상태 점검' is not hot work
CF_KEPT = r"유지|복구|진입\s*(?:중|동안)|퇴실\s*(?:후|까지)|작업\s*(?:중|동안|내내)"
# CF3 is closed by a named source (a panel·generator ID, or no powered fan·light), not by the word 「전원」
POWER_SRC = (r"(?:분전반|배전반|MCC|DB|PNL|패널|판넬)\s*-?\s*[A-Z]?\d|DB-?\d|발전기|자연\s*환기|"
             r"(?:환기|조명|팬|송기)[^,.;\n]{0,10}(?:전원\s*(?:없|안)|안\s*씀|없음)")
# how one goes in (N2 MT04): a head·upper body or a whole body, said as a way of entering ('진입 전 측정' is not)
CF_MODE = (r"머리|상체|들여다|부분\s*진입|전신|몸\s*전체|(?:안|내부)(?:으로|에)?\s*들어가|들어가\s*(?:이동|작업)|"
           r"진입\s*\d+\s*명|\d+\s*명\s*(?:이\s*)?진입|전신\s*진입")
# D6 closed by the live·test-run equipment said none, or said with who checks its isolation; D7 by the medium and the
# pressurising times; L6 by a range (a radius, or a place said with the control); LI3·LO6 by the rail·maintenance said
LIVE_NONE = r"(?:통전|시운전|수전)\s*(?:중인\s*)?(?:설비|장비)?\s*(?:은|는|이)?\s*없"
LIVE_WHO = r"(?:통전|시운전)[^,.;\n]{0,20}(?:차단|잠금)[^,.;\n]{0,20}(?:확인자|담당|팀|반장|확인)"
TEST_MEDIUM = r"공기|질소|N2|수압|물로|에어"
TEST_START = r"\d{1,2}\s*(?::\d{2}|시)[^,.;\n]{0,8}가압|가압[^,.;\n]{0,8}(?:시작\s*)?\d{1,2}\s*(?::\d{2}|시)"
TEST_END = r"\d{1,2}\s*(?::\d{2}|시)[^,.;\n]{0,8}감압|감압[^,.;\n]{0,10}(?:완료\s*)?\d{1,2}\s*(?::\d{2}|시)"
TEST_TIMES = (r"\d{1,2}\s*(?::\d{2}|시)[^,.;\n]{0,12}(?:가압|감압)|(?:가압|감압)[^,.;\n]{0,12}\d{1,2}\s*(?::\d{2}|시)")
CONTROL_RANGE = (r"(?:반경|주변)\s*\d+(?:\.\d+)?\s*m|\d+(?:\.\d+)?\s*m\s*(?:이내|반경)|"
                 r"(?:하부|아래|통로|BAY|칼럼|구역)[^,.;\n]{0,10}(?:통제|출입\s*금지|접근\s*금지)|(?:통제|출입\s*금지)[^,.;\n]{0,6}(?:하부|BAY|칼럼|통로)")
RAIL_SAID = r"(?:같은\s*)?(?:레일|주행로)[^,.;\n]{0,15}(?:없|운행|정비)|(?:다른|옆)\s*크레인[^,.;\n]{0,15}(?:없|운행|정비)|크레인\s*정비[^,.;\n]{0,8}(?:없|있|중)"
LIVE = r"활선|통전\s*상태|전원\s*(?:넣고|넣은|투입\s*상태|들어간)|무전압\s*상태로만|정전\s*상태로만"
# reference durations, minutes (research 2.6: author estimates, not site averages; used only to ask once about
# an unexplained gap when the model's conditions match, never as an error or a risk)
MODEL_SRC = {"hot": "hot.txt 2.6 T01~T06", "confined": "confined.txt 2.6 R-I~R-P", "height": "height.txt 2.6 R-G1~R-M1",
             "lifting": "heavy.txt 2.6 N4-EST", "loto": "loto.txt 2.6 EST-A~C"}
# (item, choice, what the free answer must not say, name): an earlier 'none' answer that a free answer contradicts
CONFLICT = [("LI2", "none", RX["li_inside"], "블록 안·위 작업이나 붙어 있는 것"), ("CF2", "none", RX["cf_link"], "가스·배관 연결"),
            ("B3", "no", CONC, "다른 작업"), ("LO4", "front", r"거더|트롤리|상부에\s*올라", "거더·상부 접근")]
# ---- a 「없음」 said in words (Codex trace 2026-10-31 §B): an answer typed as text ('가스·공기 배관 연결 없음', '전기 용접만')
# that plainly and unconditionally denies its item means the item's no-choice, for the checks that need it (C5
# contradiction, reflect's 문서와 다름). The answer, its words and quote stay as given; a condition, a hedge or
# another team's work in it is never taken (understand's guards, read here, not changed there).
NEG_CHOICE = {"CF2": "none", "H2": "na", "LI2": "none", "HT1": "na", "B3": "no"}
NEG_SUBJECT = {"CF2": RX["cf_link"] + r"|연결|계통|공기|배관|라인",
               "H2": r"가스|산소|LPG|아세틸렌|프로판|CO2|아르곤|질소",
               "LI2": RX["li_inside"] + r"|작업|붙|배관|발판|전선|부착",
               "HT1": r"러그|인양\s*고리|떼",
               "B3": CONC + r"|작업"}
ELECTRIC_ONLY = re.compile(r"전기\s*용접만|피복\s*아크\s*용접만|SMAW\s*만|(?:용접|가스)[^,.;\n]{0,6}(?:가스\s*(?:는\s*)?)?(?:안\s*씀|안\s*써|미사용|쓰지\s*않)")
BARE_NO = re.compile(r"\s*(?:없(?:음|습니다|어요|다)?|해당\s*없(?:음|습니다)|아니(?:요|오)|안\s*(?:함|합니다|해요))\s*[.!]?\s*")
# never a plain denial: a correction ('없는 줄 알았는데'), a double negation ('없지 않아요'), a necessity ('없이는 못 해요'),
# or anything affirmed anywhere in the answer ('…있음', '질소 퍼지') — such an answer stays as typed, unconfirmed
NEG_NOT_PLAIN = re.compile(r"줄\s*알았|알고\s*보니|사실은|아니라|아니고|정정|잘못|대신|그런데|는데|"
                           r"없지\s*않|않지\s*않|아니지\s*않|없는\s*(?:게|것은?|건)\s*아니|없이는|없으면|없어서는|없어도|필요|해야")
NEG_AFFIRM = re.compile(r"(?<!안\s)(?<!안)(?<!못\s)(?<!못)(?:있|씀|써요|씁니다|쓰고|쓰는|사용함|사용합|사용하고|사용해|"
                        r"퍼지|공급(?:함|합|하고|해)|연결(?:함|됨|돼|되어))")
# a planned or reported statement is not a denial of what is there ('질소 투입 예정', '없다고 들었어요')
NEG_PLANNED = re.compile(r"예정|계획|할\s*(?:거|것|게)|하겠|투입|넣을|들었|한대|했대|라고|래요|대요|다고")
NEG_WORD = re.compile(r"없|않|아니|말고|무관|안\s*(?:함|합|해|하|씀|써|쓰|들어|나)|못\s*(?:함|합|해|하)|미사용")


def negated(item, a):
    """the no-choice id an answer's typed words mean (see NEG_CHOICE), or None. Already that choice: it. Only a single,
    unconditional denial of the item with nothing about it affirmed anywhere: every clause plain (no condition, hedge,
    undecided word, other team), no correction, double negation or necessity, one negation in all, the item's subject
    before it; or a bare 「없음」; for H2 the electric-only welding the method reading already knows, with no gas said."""
    item = (item or "").split(":")[0].split(".")[0]
    want = NEG_CHOICE.get(item)
    ch, v = (a or {}).get("choice"), ((a or {}).get("read") or (a or {}).get("value") or "").strip()
    if not want or ch == want:
        return want if ch == want else None
    if ch in (None, "unknown") or ch in ("yes", "free") or not v:
        return None
    from . import understand as U                                  # lazy: understand imports this module
    for cl in [c for c in CLAUSE.split(v) if c.strip()]:
        if COND.search(cl) or U._conditional(cl) or HEDGE.search(cl) or UNDECIDED.search(cl) or U.UNDECIDED.search(cl) or U._other(cl):
            return None
    if BARE_NO.fullmatch(v):
        return want
    if NEG_NOT_PLAIN.search(v) or NEG_AFFIRM.search(v) or NEG_PLANNED.search(v):
        return None
    if item == "H2" and re.search(r"산소|LPG|아세틸렌|프로판|CO2|아르곤|질소|퍼지|가스\s*절단", v) and not re.search(NEG_SUBJECT["H2"] + r"[^,.;\n]{0,8}(?:없|않|안\s*(?:씀|써|쓰)|미사용)", v):
        return None
    # every part of the answer is the item denied (once, its subject before the denial) — or, for H2, the
    # electric-only welding; a part that says anything else ('질소 투입 예정', '공기 호스는 있음') keeps it text
    parts = [x.strip() for x in re.split(r"[,;\n/]|(?<!\d)\.(?!\d)|그리고|지만|(?<=[가-힣])(?:고|며|는데)\s", v) if x.strip(" .!")]
    for x in parts:
        if item == "H2" and ELECTRIC_ONLY.search(x):
            continue
        m, n = re.search(NEG_SUBJECT[item], x), NEG_WORD.search(x)
        if not (m and n and m.start() < n.start() and len(NEG_WORD.findall(x)) == 1):
            return None
    return want if parts else None


def eff_choice(item, a):
    """the answer's choice, or its no-choice when its words plainly deny the item (negated)"""
    return negated(item, a) or (a or {}).get("choice")


SCOPE_Q = {"hot": "H1", "confined": "CF1", "height": "HT1", "loto": "LO1"}
SCOPE_WORD = {"local": "용접부 국부 보수", "replace": "부재 교체", "reweld": "재용접만", "remove": "제거만", "inspect": "검사·점검",
              "clean": "청소", "recover": "회수", "repair": "보수·수리", "partial": "머리·상체만 진입", "gas": "가스절단",
              "plasma": "플라즈마", "mech": "기계절단", "diag": "원인 찾는 점검", "module": "부품 교체", "install": "설치·증설"}
STAGE = {"hot": "절단·용접", "confined": "내부 작업", "height": "절단", "lifting": "블록이 움직이는 구간", "loto": "수리"}
# T6 「짧다」: what the end written can mean, in the book's words (N1 MT13, N2 MT12, N3 MT12, N4-MT13, N5 MT12)
END_Q = {"hot": "용접·절단만 적었나요, 검사·정리·잔불 확인까지 끝나는 시간인가요?",
         "confined": "내부 작업만 적었나요, 모든 인원 퇴장·정리·복구 인계까지 끝나는 시간인가요?",
         "height": "절단만 적었나요, 회수·사상·철수까지 끝나는 시간인가요?",
         "lifting": "블록이 움직이는 구간만 적었나요, 안착·줄걸이 해제·철수까지 끝나는 시간인가요?",
         "loto": "수리만 적었나요, 시험·철수·운전 인계까지 끝나는 시간인가요?"}
END_Q_ALL = {"hot": "잔불 확인", "confined": "퇴장·복구 인계", "height": "회수·철수", "lifting": "줄걸이 해제·철수", "loto": "운전 인계"}
# T6 「길다」: what can be in it (N3 MT08 p274: moving the platform or the access; N5 MT08 p355: parts, outside repair)
LONG_Q = {"height": "대기·반복, 작업대·접근장비를 옮기는 일이나 다른 블록 이동",
          "loto": "진단·대기·반복·시험이나 부품 대기·외부 수리·재방문"}


def _scope(P, ans):
    """The kind's work scope from the permit text and the answers (None = not said)."""
    t, kind, pid = P["text"], P["kind"], P["permit_no"]
    item = SCOPE_Q.get(kind, "-")
    a = ans.get(f"{item}:{pid}")
    # an answer taken back (C6 「서류가 맞음」) is not in ans (live_answers). CF1 「몸 전체 진입」 says how, not what:
    # the purpose is read on.
    if a and a.get("choice") not in (None, "unknown", "text", "full"):
        return "partial" if a["choice"] == "head" else a["choice"]
    if kind == "hot":
        for name in ("reweld", "remove", "replace", "local"):
            if said(t, RX[f"hot_{name}"]):
                return name
    if kind == "confined":
        for name in ("partial", "inspect", "clean", "recover", "repair"):
            if said(t, RX[f"cf_{name}"]):
                return name
    if kind == "height":
        for name in ("plasma", "mech", "gas"):
            if said(t, RX[f"ht_{name}"]):
                return name
    if kind == "loto":
        for name in ("module", "diag", "repair", "install"):
            if said(t, RX[f"lo_{name}"]):
                return name
    return None


def doc_text(P):
    """the permit's own words (no answer in them)"""
    return " ".join(_v(P["p"], k) for k in ("hull_no", "location", "location_detail", "job", "job_detail", "hazards"))


# what makes a reference model's conditions known (research 2.6; a single word never picks a model or skips a question:
# the model needs the count, the scope and the conditions the book names, else the comparison waits — DEFER)
SAME_AGAIN = r"(?:같은|동일)\s*(?:불량|부위|곳|자리)[^,.;\n]{0,12}(?:재작업|재보수|다시)|재작업\s*1\s*회|(?:두|2)\s*번\s*(?:보수|작업)"
REPEAT_N = re.compile(r"(\d)\s*(?:회|번)\s*(?:진입|들어|반복|시험|교체)|(?<![가-힣])(두|세|네)\s*번\s*(?:진입|들어|반복|시험|교체)")
THICK = re.compile(r"(?:두께|t)\s*(\d{2,3})\s*mm|(\d{2,3})\s*mm\s*(?:두께|판|러그)", re.I)
CUTLEN = re.compile(r"절단\s*(?:선|길이)\s*(?:총\s*)?(\d+(?:\.\d+)?)\s*m(?![a-z])")
WAIT_OPEN = r"대기|기다리|검사\s*대기|장비\s*대기"          # a wait said with no length: the whole elapsed time is not known


def _repeats(t):
    """a stated number of entries / repeats ('2회 진입', '세 번 반복'), else None"""
    m = REPEAT_N.search(t or "")
    if not m:
        return None
    return int(m.group(1)) if m.group(1) else {"두": 2, "세": 3, "네": 4}[m.group(2)]


def time_model(P, ans):
    """(model id, lo, hi) of the reference model whose conditions the permit meets, or (None, reason)."""
    kind, t, n = P["kind"], P["text"], P["count"]
    sc = _scope(P, ans)
    job_ids = blocks_in(_v(P["p"], "job") + " " + _v(P["p"], "job_detail"))
    if kind == "hot":
        if sc == "local":
            if said(t, SAME_AGAIN) and n in (None, 1):          # T07: the same defect done twice (stated, never assumed)
                return ("T07 같은 불량 재작업 1회 추가", 200, 400)
            if n is None:
                return None, "보수 개수 미상"
            if said(t, RX["hot_deep"]):
                # T02 needs the actual removal depth·length·WPS; the word 「깊은」 alone does not pick it (p203, p214 A07)
                return None, "깊은 불량: 제거 범위 조건 미확인"
            if n > 1 and len(job_ids) > 1:                      # T04: other blocks do not share one preparation
                return None, "여러 블록: 공통 준비 공유 미확인"
            return ("T01 국부 보수 1개", 115, 230) if n == 1 else (f"T04 국부 보수 {n}개", 40 + 75 * n, 80 + 150 * n)
        if sc == "replace":
            return ("T03 판재 분리·교체 1개", 230, 460) if n == 1 else (None, "교체 개수 미상" if n is None else "여러 개 교체 모델 없음")
        # T05·T06 are for one defect: a count not known is not taken as 1 (p215 A11 「미정 개수는 1로 대입하지 않음」)
        if sc == "reweld":
            return ("T06 재용접·검사만", 85, 170) if n == 1 else (None, "개수 미상" if n is None else "여러 개 모델 없음")
        if sc == "remove":
            return ("T05 제거·정리만", 70, 140) if n == 1 else (None, "개수 미상" if n is None else "여러 개 모델 없음")
        return None, "보수 범위 미상"
    if kind == "confined":
        reps = _repeats(t)
        if said(t, RX["cf_repeat"]) or (reps or 1) > 1:
            # R-N (p245, p259 B12): the entries counted and an inspection of known points; else the comparison waits
            if sc == "inspect" and n and reps and 2 <= reps <= 4:
                lo = 65 + reps * (10 + 5 * n + 10 + 10) + (reps - 1) * 10
                hi = 130 + reps * (20 + 10 * n + 20 + 20) + (reps - 1) * 20
                return (f"R-N 내부 검사 {n}곳 {reps}회 진입", lo, hi)
            return None, "반복 진입·교대 횟수 미상"
        if sc == "inspect":
            # R-I is for the points inspected: [95+5p, 190+10p] (p244, p258 B06); points not known are not 2
            return (f"R-I 내부 검사 {n}곳 1회 진입", 95 + 5 * n, 190 + 10 * n) if n else (None, "검사 지점 수 미상")
        return {"clean": ("R-C 국부 청소 1회 진입", 125, 250),
                "recover": ("R-R 물품 회수 1회 진입", 100, 200), "repair": ("R-W 국부 보수 1회 진입", 145, 290),
                "partial": ("R-P 머리·상체 부분 진입", 85, 170)}.get(sc, (None, "내부 작업 목적 미상"))
    if kind == "height":
        if n is None:
            return None, "러그 개수 미상"
        if len(job_ids) > 1:                                    # R-MULTIBLOCK (p273): each block's preparation apart
            return None, "여러 블록: 블록별 준비 공유 미확인"
        mt, cl = THICK.search(t or ""), CUTLEN.search(t or "")
        th = int(mt.group(1) or mt.group(2)) if mt else None
        if (th is not None and not 20 <= th <= 30) or (cl and not 0.3 <= float(cl.group(1)) <= 0.5):
            # the base models are for 20~30mm and 0.3~0.5m of cut per lug; R-G2 (45~55mm, 0.8~1.2m) also needs the
            # recovered piece and its recovery to match, so it is not applied by the numbers alone (p272~273)
            return None, "참고 조건(두께·절단 길이)과 다름"
        if sc == "gas":
            return (f"R-G 가스절단 러그 {n}개", 40 + 50 * n, 80 + 100 * n)
        if sc == "plasma":                                      # the cutting step of each lug replaced (p272~273)
            return ("R-P1 플라즈마 1개", 85, 175) if n == 1 else (f"플라즈마 러그 {n}개", 40 + 45 * n, 80 + 95 * n)
        if sc == "mech":
            return ("R-M1 기계절단 1개", 100, 200) if n == 1 else (f"기계절단 러그 {n}개", 40 + 60 * n, 80 + 120 * n)
        return None, "절단 방법 미상" if sc is None else "여러 개 모델 없음"
    if kind == "lifting":
        blocks = n or len(job_ids) or None
        flags = [k for k in ("tandem", "turn", "rotate", "vehicle") if said(t, RX[f"li_{k}"]) or (k == "tandem" and P["p"].get("tandem", {}).get("value"))]
        if blocks is None:
            return None, "블록 수 미상"
        if len(flags) > 1:
            return None, "복합 방법(단계별로 나눠 봐야 함)"
        if blocks == 1:
            route = " ".join(x for x in (_v(P["p"], "location"), _v(P["p"], "location_detail"), (ans.get(f"L5:{P['permit_no']}") or {}).get("value", "")) if x)
            if not flags and (len(parse_place(route)["bays"]) > 1 or said(route + " " + t, r"우회|통행\s*조정")):
                return ("N4-EST-B 긴 경로·통행 조정", 180, 390)     # p312~313, p336: a route through another BAY
            return {None: ("N4-EST-A 단일 크레인 1블록", 120, 240), "tandem": ("N4-EST-C 공동인양", 180, 360),
                    "rotate": ("N4-EST-D 수평 회전", 150, 300), "turn": ("N4-EST-E 반전", 240, 480),
                    "vehicle": ("N4-EST-F 차량 인계", 240, 480)}[flags[0] if flags else None]
        if not flags and blocks in (2, 3):
            return (f"같은 계획 블록 {blocks}개", 15 + 105 * blocks, 30 + 210 * blocks)
        return None, "여러 블록·방법 모델 없음"
    if kind == "loto":
        reps = _repeats(t)
        if said(t, r"반복|재시험|여러\s*대") or (reps or 1) > 1:
            # EST-D (p353, p376): the repair·test bundle 2~3 times, recomputed by the count; else it waits
            return (f"EST-D 수리·시험 {reps}회 반복", 150 * reps, 360 * reps) if reps in (2, 3) else (None, "반복 횟수 미상")
        return {"module": ("EST-C 모듈·부품 교체", 150, 360), "diag": ("EST-B 진단 후 국소 수리", 180, 480),
                "repair": ("EST-A 원인 확인된 국소 수리", 120, 240)}.get(sc, (None, "작업 범위 미상"))
    return None, "모델 없음"


def time_fit(P, ans, whole_asked):
    """Reported minutes against the matching model: {"state": "fit"|"long"|"short"|"defer", ...} (research MT05)."""
    if P.get("amb"):
        return {"state": "defer", "why": "작업 시간을 다시 확인하는 중 (오전·오후 또는 날짜)"}
    days = {d: ws for d, ws in P["windows"].items() if ws}
    if len(days) != 1:
        return {"state": "defer", "why": "여러 날 작업이라 하루 단위 참고와 비교하지 않음" if days else "작업 시간 없음"}
    if P.get("time_meaning") == "stage":
        return {"state": "defer", "why": "블록이 움직이는 구간만 받음: 전체 작업 참고와 비교하지 않음"}
    if whole_asked and not P.get("time_meaning"):
        return {"state": "defer", "why": "시간의 의미(신청 시간/실제 작업 시간) 확인 전"}
    mins = sum(b - a for ws in days.values() for a, b in _union(ws))     # a union: a time is counted once
    if said(P["text"], WAIT_OPEN) and not re.search(r"대기[^,.;\n]{0,8}\d|\d\s*(?:분|시간)[^,.;\n]{0,6}대기", P["text"]):
        # a wait whose length is not known: the elapsed whole cannot be estimated (p203 T08, p215 A13); the wait itself
        # is asked about (T9), the comparison waits
        return {"state": "defer", "why": "대기 시간 미정: 전체 시간 비교 보류", "minutes": mins}
    m = time_model(P, ans)
    if m[0] is None:
        return {"state": "defer", "why": m[1], "minutes": mins}
    model, lo, hi = m
    state = "fit" if lo <= mins <= hi else "long" if mins > hi else "short"
    return {"state": state, "minutes": mins, "model": model, "lo": lo, "hi": hi, "src": MODEL_SRC[P["kind"]]}


# T8 is closed only when both the support and the hand-over are said; T4 only when the ember check's end (or that the
# end written includes it) is said; T9 only when the state kept and the restart are said (atoms, not one word)
NIGHT_SUPPORT = r"투광|조명\s*(?:설치|확보|\d)|화재\s*감시[^,.;\n]{0,10}(?:\d|까지|명)|구조\s*(?:대기|인원|팀)"
NIGHT_HANDOVER = r"인계|같은\s*조가?\s*(?:끝까지|마무리)|교대\s*(?:없|안\s*함)"
WAIT_RX = (r"대기|중단|휴식|쉬는\s*동안|쉬었다|교대|재개|이어서|재진입|재절단|나눠서|나누어|"
           r"다시\s*(?:들어|진입|자르|절단|시작)")
WAIT_STATE = r"유지|차단|잠금|잠그|받친|받침|통제"
WAIT_RESUME = (r"(?:재개|다시\s*시작|재진입|재절단|다시\s*(?:들어|자르))[^,.;\n]{0,10}\d{1,2}\s*(?::\d{2}|시)|"
               r"\d{1,2}\s*(?::\d{2}|시)[^,.;\n]{0,8}(?:재개|다시\s*시작|재진입|재절단|다시\s*(?:들어|자르))")
# the ember check's end said ('화재감시 16시까지', '잔불 확인 30분', '잔불 확인 후 종료'); '잔불' alone or '화재감시자 1명' is not
EMBER_SAID = (r"(?:잔불|불씨|화재\s*감시)[^,.;\n]{0,15}(?:\d{1,2}\s*(?::\d{2}|시)|\d+\s*분)|"
              r"\d{1,2}\s*(?::\d{2}|시)[^,.;\n]{0,8}까지\s*(?:잔불|불씨|화재\s*감시)|잔불\s*확인\s*(?:후|까지)\s*(?:종료|끝)")


CLOCK = re.compile(r"(오전|아침|새벽|오후|저녁|밤)?\s*(\d{1,2})\s*(?::\s*(\d{2})|시(?:\s*(\d{1,2})\s*분|\s*(반))?)")


def clock_read(v):
    """one clock time an answer gives, read like every time croScan reads (_clocks): (minutes or None, ambiguous,
    next day). '16:00', '오후 4시 30분' are one time; a bare '4시 반' (새벽 or 오후) and '오전 12시 30분' (자정 or 정오)
    are ambiguous and asked back, never guessed; '다음날 01:00' is on the next day."""
    v = v or ""
    m = CLOCK.search(v)
    if not m:
        x = _m(v)
        return x, False, bool(NEXT_DAY.search(v))
    mark, h, mi, mi2, half = m.groups()
    cands = _clocks(mark, h, mi or mi2, half, h if not mi else h)
    ambig = len(cands) != 1 or (mark in AM and int(h) == 12)
    return (cands[0] if len(cands) == 1 else None), ambig, bool(NEXT_DAY.search(v) or re.search(r"내일\s*(?:새벽|아침)", v))


def _clock(v):
    """one clear clock time in minutes, or None (ambiguous ones are None)"""
    m, ambig, nextday = clock_read(v)
    return None if ambig else m


def t7_rows(P):
    """the 작업일시 rows T7 compares, [(row, date, start, end)] in minutes (end past 24:00 for a next-morning end), and
    whether a used row is not settled yet: a part missing or unreadable, or its end not after its start without T5
    「다음 날 끝남」 (T0·T5 ask those first). An empty row is read as its T0 answer placed it."""
    p, out, hold = P["p"], [], False
    t0 = {}
    for x in (P.get("t0") or {}).values():
        for i, (d, _, _) in (x.get("placed") or {}).items():
            ws = (x.get("w") or {}).get(d) or []
            if len(ws) == 1:
                t0[i] = (d, *ws[0])
    for i in range(1, 8):
        if i in t0:
            out.append((i, *t0[i]))
            continue
        d, x, y = _v(p, f"date_{i}"), _v(p, f"from_{i}"), _v(p, f"to_{i}")
        if not (d or x or y):
            continue
        a, b = _m(x), _m(y)
        if not ISO.fullmatch(d) or a is None or b is None:
            hold = True
            continue
        if b <= a:
            if P.get("t5", {}).get(i) != "overnight":
                hold = True
                continue
            b += 24 * 60
        if b <= a:                                     # 24:00~00:00: no time at all
            hold = True
            continue
        out.append((i, d, a, b))
    return out, hold


def t7_target(P):
    """the row T7 asks about, (row, date, start, end, tick), or None: against a confirmed site shift when there is one,
    else by the statutory night only — 「주간」 with a row wholly inside it, 「야간」 with every row plainly daytime (all of
    them settled: a row not settled is not taken as daytime)"""
    p = P["p"]
    day_t, night_t = bool(p.get("day", {}).get("value")), bool(p.get("night", {}).get("value"))
    rows, hold = t7_rows(P)
    if not rows or day_t == night_t:
        return None
    if day_t:
        hit = next((r for r in rows if (night_part(r[2], r[3]) if SITE_SHIFT else legal_night_only(r[2], r[3]))), None)
    else:
        hit = rows[0] if not hold and all(day_only(a, b) if SITE_SHIFT else plain_day(a, b) for _, _, a, b in rows) else None
    return (*hit, "주간" if day_t else "야간") if hit else None


def t7_original(t):
    i, d, a, b, tick = t
    return f"{tick} / {d} {hm(a)}~{hm(b)}"


def t7_stale(P, ans):
    """a T7 answer given about another row or tick than the one asked now (the permit edited, a T0·T5 answer moved
    it): it is not used anywhere, and T7 is asked again (Codex T7 #1)"""
    a = ans.get(f"T7:{P['permit_no']}")
    if not a:
        return False
    t = P.get("t7")
    was = (a.get("q") or {}).get("original")
    row = _row_of(a) if (a.get("q") or {}).get("keys") else None
    return not t or (was is not None and was != t7_original(t)) or (row is not None and row != str(t[0]))


def drop_stale(perms, answers):
    """the answers without a stale one of any permit: a T7 answer about another row, an answer about form values
    changed since (stale_answers)"""
    gone = {f"T7:{P['permit_no']}" for P in perms if P.get("t7_stale")} | {q for P in perms for q in P.get("stale", ())}
    return [a for a in answers or [] if a["qid"] not in gone] if gone else answers


def _open(get, item):
    """a time question asked and not settled: not answered, or answered 「모름」 (the meaning stays unknown)"""
    a = get(item)
    return not a or a.get("choice") == "unknown"


def _time_of_day(P, ans, add, qs=()):
    """T7·T8: what the book asks of the time of day, and only that (research 2.6 S07, 2.7 MT12·MT14, N4-MT15).
    T7 — the 주간·야간 the permit ticks and the time of one row (t7_target): asked what they mean together, about that
    row (its date and keys); a corrected time replaces that row only. A row not settled (T0, T5) waits for them.
    T8 — hot work at night or into the next morning as the permit or the foreman says it (the 야간 tick, T5 「다음 날
    끝남」, a 주간 row in the statutory night that T7 says is really worked then, or a confirmed shift): who supports it
    and whether it is handed over (N1 MT12) — asked only when a shift change, a hand-over or a night support is written
    and left unclear (MT12 p205); night by itself is no question (MT14 p247, N4-MT15 p315).
    It waits while T7 or T5 is not settled. Night by itself is never called wrong; the answers are recorded."""
    p, kind, pid = P["p"], P["kind"], P["permit_no"]
    get = lambda item: ans.get(f"{item}:{pid}")
    day_t, night_t = bool(p.get("day", {}).get("value")), bool(p.get("night", {}).get("value"))
    t7 = P.get("t7")
    if t7:
        i, d, a, b, tick = t7
        if SITE_SHIFT:
            ds, de = SITE_SHIFT
            where = f"확인된 주간 근무({hm(ds)}~{hm(de)}) " + ("밖에 걸칩니다" if day_t else "안에 있습니다")
        else:
            law = "22:00~다음 날 06:00(근로기준법 제56조 제3항이 야간근로로 정한 시간)"
            where = (f"모두 {law} 사이입니다" if day_t else
                     f"낮 12시를 지나고 {law}에는 걸치지 않습니다" + (" (다른 날 시간도 모두 그렇습니다)" if len(t7_rows(P)[0]) > 1 else ""))
        add("T7", P, ["day", "night", f"date_{i}", f"from_{i}", f"to_{i}"], f"「{tick}」 체크 ↔ {d} {hm(a)}~{hm(b)}",
            f"작업일시에 「{tick}」을 체크했는데, {d} 적힌 시간 {hm(a)}~{hm(b)}은 {where}. 체크와 적힌 시간이 서로 맞나요?",
            [C("time", "적힌 시간이 맞음(체크를 고쳐야 함)", "정정"),
             C("check", f"「{tick}」 체크가 맞음(이 날 시간을 고침)", "정정", "맞는 시간대 예: " + ("09:00~11:00" if day_t else "20:00~23:00")),
             C("both", f"둘 다 맞음(현장에서 이 시간을 {tick}으로 봄)", "확인됨"), UNKNOWN], (1, 1), original=t7_original(t7))
    if kind != "hot" or (t7 and _open(get, "T7")) or any(q["item"].split(".")[0] == "T5" and q["permit_no"] == pid and _open(get, q["item"]) for q in qs) \
            or "unknown" in P.get("t5", {}).values():
        return                                                # the time of day is not settled yet: T8 waits
    said7 = (get("T7") or {}).get("choice") if t7 else None
    dark = None                                                # a 주간 row in the statutory night, really worked then
    if said7 in ("time", "both") and day_t:
        dark = t7[1:4]
        if said7 == "time":
            day_t, night_t = False, True
    elif said7 == "time":                                      # 「야간」 but the daytime written is right
        day_t, night_t = True, False
    eff = [(d, a, b) for d, ws in sorted(P["windows"].items()) for a, b in ws]
    redone = t7[0] if said7 == "check" and P.get("t7_fixed") else None          # that row's T5 end is replaced
    over = any(v == "overnight" for i, v in P.get("t5", {}).items() if i != redone)
    night = dark or next(((d, a, b) for d, a, b in eff if b > 24 * 60 or (SITE_SHIFT and night_part(a, b))), None)
    if not (night or over or (night_t and not day_t)):
        return
    if confirmed(P["text"], NIGHT_SUPPORT) and confirmed(P["text"], NIGHT_HANDOVER):      # both atoms said: nothing to ask
        return
    if not re.search(r"교대|인계|야간조|다음\s*조|넘겨|이어서\s*(?:작업|함)|화재\s*감시|조명|투광등|작업등|지원", P["text"]):
        return                                                # night by itself is no question: nothing about shifts or support is written
    d, a, b = night or (eff[0] if eff else (None, None, None))
    win = f"{hm(a)}~{hm(b)}" if a is not None else "야간"
    row = t7[0] if dark else 1
    add("T8", P, ["night", f"from_{row}", f"to_{row}"], f"야간·교대 시간 작업: {win}",
        f"적으신 작업 시간 {win}은 야간·교대 시간에 걸칩니다(서류의 야간 체크, 다음 날 종료 또는 앞의 확인 답). 야간 작업 자체를 문제로 "
        "보지 않습니다. 그 시간의 조명·접근·화재감시·구조 지원은 어떻게 되고, 다음 조로 넘기는 인계가 있나요?",
        [C("same", "같은 조가 끝까지 하고 지원 갖춤", "확인됨"),
         C("text", "지원·인계 입력", "보강", "예: 투광등 2대, 화재감시 1명 23시까지, 22시에 야간조 반장에게 인계"), UNKNOWN],
        (5, 2), original=win)


# (kind) -> (text, choices) of T9: the state kept while the work waits, stops or changes shift (research 2.7
# N1 MT07, N2 MT09, N3 MT11, N5 MT07). Recorded only.
WAIT_Q = {
    "hot": ("기다리거나 멈추는 동안(검사·장비 대기 등) 작업자리·받침·가스·전원은 어떤 상태로 두나요? 다시 시작(재개·검사)은 언제인가요?",
            [C("kept", "차단·통제 그대로 유지", "확인됨"), C("text", "상태·재개 시각 입력", "보강", "예: 검사 대기 중 가스 밸브 잠금·용접기 전원 차단, 14:00 재개")]),
    "confined": ("중간에 나왔다가 다시 들어가나요? 쉬거나 교대하는 동안 가스 공급 차단·환기는 유지하나요? 다시 들어가기 전 공기 측정을 다시 하나요?",
                 [C("once", "한 번 들어가 끝까지 함", "확인됨"),
                  C("text", "재진입·유지 계획 입력", "보강", "예: 2번 진입, 점심 동안 환기·차단 유지, 재진입 전 산소·가스 재측정")]),
    "height": ("쉬거나 교대하는 동안 반쯤 자른 러그의 받침과 아래 출입 통제는 어떻게 두나요? 다시 자르거나 장비를 다시 설치하나요?",
               [C("kept", "받침·하부 통제 그대로 유지", "확인됨"), C("notcut", "멈출 때는 자르기 전 상태로 둠", "확인됨"),
                C("text", "상태·재설치 입력", "보강", "예: 점심 동안 체인블록으로 받친 채 하부 통제 유지, 13시 재절단")]),
    "loto": ("작업을 멈춘 동안(대기·휴식·교대)에도 전원 차단·잠금은 유지하나요? 그동안 그 크레인(설비)을 쓰는 계획이 있나요?",
             [C("kept", "계속 차단·쓰는 계획 없음", "확인됨"), C("text", "중간 사용·복구 입력", "보강", "예: 12~13시 점심 동안 차단 유지, 사용 없음")]),
}


def _wait_state(P, ans, add):
    """T9 when the permit or an answer says the work waits, stops, is split or changes shift (words, or two windows in
    a day): what is kept meanwhile. Not asked when the state kept and the restart are both said already (confined:
    the re-measuring and the supply·ventilation kept); a work running past midnight without a stop is no wait."""
    kind, pid, t = P["kind"], P["permit_no"], P["text"]
    if kind not in WAIT_Q:
        return
    get = lambda item: ans.get(f"{item}:{pid}")
    t6 = get("T6") or {}
    said_ = t + " " + (t6.get("value", "") if t6.get("choice") == "text" else "")
    split = any(len(_union(ws)) > 1 for ws in P["windows"].values())
    why = "대기·중단·교대가 적혀 있음" if said(said_, WAIT_RX) else "작업 시간이 나뉘어 있음" if split else ""
    if not why:
        return
    if kind == "confined":
        done = confirmed(said_, r"재측정|다시\s*측정|재평가") and confirmed(said_, r"(?:환기|차단|격리|공급)[^,.;\n]{0,10}유지")
    else:
        done = confirmed(said_, WAIT_STATE) and confirmed(said_, WAIT_RESUME)
    if done:
        return
    text, choices = WAIT_Q[kind]
    add("T9", P, ["job_detail"], why, text, choices + [UNKNOWN], (6, 1))



def _foreman(P, ans, qs, assumed, deferred):
    p, kind, pid = P["p"], P["kind"], P["permit_no"]
    t, pl = P["text"], P["place"]
    get = lambda item: ans.get(f"{item}:{pid}")
    add = lambda *a, **k: qs.append(_q(*a, **k))
    jt = " ".join(_v(p, k) for k in ("job", "job_detail", "location_detail"))
    equip = bool(EQUIP.search(jt + " " + _v(p, "location"))) or kind == "loto"
    blocks = {x for x in P["targets"] if not CRANE.fullmatch(x)}
    # ---- time: a date row whose end is before its start (MT04), the meaning of a whole-shift or copied time (MT01)
    bad = [(i, _v(p, f"date_{i}"), _v(p, f"from_{i}"), _v(p, f"to_{i}")) for i in range(1, 8)]
    bad = [(i, d, a, b) for i, d, a, b in bad if _m(a) is not None and _m(b) is not None and _m(b) <= _m(a)
           and not get(t5_item(i))]                            # one question per reversed row, each on its own (#12)
    if bad:
        i, d, a, b = bad[0]
        add(t5_item(i), P, [f"from_{i}", f"to_{i}"], f"{i}일차 종료 {b} ≤ 시작 {a}",
            f"{d or f'{i}일차'} 종료({b})가 시작({a})" + ("과 같습니다. " if _m(a) == _m(b) else "보다 빠릅니다. ") + "다음 날 아침에 끝나는 작업인가요, 시각을 잘못 적었나요?",
            [C("overnight", "다음 날 끝남", "확인됨"), C("fix", "잘못 적음", "정정", "맞는 시간대 예: 13:00~15:30"), UNKNOWN], (0, 0), original=f"{a}~{b}")
    gap = time_gap(p, {int(q.split(":")[0].split(".")[1]) for q in ans if q.startswith("T0.") and q.split(":")[1:2] == [pid]
                       and q.split(":")[0].split(".")[1].isdigit()})
    if gap:
        i, miss = gap
        day = _v(p, f"date_{i}") or permit_day(p)
        whole_row = len(miss) == 3
        add(f"T0.{i}", P, [f"date_{i}", f"from_{i}", f"to_{i}"], f"작업일시 {i}행 빈칸({'·'.join(miss)})",
            ("허가 신청에 적을 작업일시(날짜·시작·종료)가 비어 있습니다. 작업 날짜와 시작~종료 시각을 알려 주세요."
             if whole_row and i == 1 else
             f"작업일시 {i}행의 {'·'.join(miss)}이(가) 비어 있습니다"
             + (f" (적힌 값: {', '.join(f'{n} {_v(p, k)}' for n, k in (('날짜', f'date_{i}'), ('시작', f'from_{i}'), ('종료', f'to_{i}')) if _v(p, k))})" if not whole_row else "")
             + ". 이 날의 날짜와 시작~종료 시각을 알려 주세요."),
            [C("value", "날짜·시간 입력", "정정",
               f"예: {day or '2026-10-29'} {_v(p, f'from_{i}') or '13:00'}~{_v(p, f'to_{i}') or '15:00'}"
               + (" / 여러 날이면 날마다 날짜를 적어 10/29 09~11; 10/30 13~15" if whole_row else "")), UNKNOWN], (0, 0))
    rows = [(d, a, b) for d, ws in sorted(_windows(p).items()) for a, b in ws]
    whole = [(d, a, b) for d, a, b in rows if a <= DAY_START and b >= DAY_END]
    copied = len(rows) >= 3 and len({(a, b) for _, a, b in rows}) == 1
    if whole or copied:
        d0, a0, b0 = (whole or rows)[0]
        ds = f"{rows[0][0]}~{rows[-1][0][5:]}" if len(rows) > 1 else d0
        if kind == "lifting":
            text = (f"작업일시가 {ds} {hm(a0)}~{hm(b0)}로 적혀 있습니다. 준비부터 안착·줄걸이 해제까지 이 시간 내내 하나요? "
                    "블록이 실제로 움직이는 시간대를 알려 주세요.")
        elif whole:
            text = (f"작업일시가 {ds} {hm(a0)}~{hm(b0)}로 적혀 있습니다. 하루 신청 시간인가요, 실제로 {VERB.get(kind, '작업을')} 하는 시간인가요? "
                    "나눠서 하거나 기다리는 시간이 있으면 실제 시간대를 알려 주세요.")
        else:
            text = f"{len(rows)}일 동안 매일 {hm(a0)}~{hm(b0)}로 같습니다. 날마다 같은 작업을 이 시간에 하나요?"
        add("T1", P, ["from_1", "to_1"], f"{len(rows)}일, {hm(a0)}~{hm(b0)}" + (" (근무시간 거의 전체)" if whole else " (같은 시간 반복)"), text,
            [C("yes", "이 시간 내내 함" if whole else "매일 같음", "확인됨"),
             C("partial", "실제 시간대 입력", "정정", "예: 09:00~11:00, 14:00~16:00 / 날마다 다르면 10/27 09~11; 10/28 14~16"), UNKNOWN],
            (1, 0), original=f"{hm(a0)}~{hm(b0)}")
    _time_of_day(P, ans, add, qs)
    # ---- asking back (A1 오전·오후, A2 날짜, A3 숫자 없는 시간, U1 알아듣지 못한 말) never loops: each is asked once (its
    # qid), a check question is answered by buttons or by a value that is itself checked once, and at most ASK_BACK of
    # them per permit; past that the words go to page 2 「안전팀 확인」 without a question
    left = [ASK_BACK - sum(1 for q in ans if q.split(":")[1:2] == [pid] and q.split(".")[0] in ("A1", "A2", "A3", "A4", "A5", "U1"))]

    def ask_back(item, raw, *a, **k):
        if f"{item}:{pid}" in ans:
            return
        if left[0] <= 0:
            deferred.append({"permit_no": pid, "name": "확인 못 한 말", "text": f"'{raw}' (다시 묻기는 {ASK_BACK}번까지라 묻지 않음)"})
            return
        left[0] -= 1
        add(item, P, *a, **k)
    # ---- a time that can mean two things is asked back, never guessed (A1 오전·오후, A2 which date)
    where = lambda src: "추가로 적으신 내용의" if src.startswith("F") else "앞에서 답하신"
    for x in {(x["kind"], x["src"], x["k"]): x for x in P["amb"]}.values():
        if x["kind"] == "ampm":
            am, pm = time_ranges(x["raw"], "am"), time_ranges(x["raw"], "pm")
            if not (am and pm):
                continue
            ask_back(ask_item("ampm", x["src"], x["k"]), x["raw"], ["from_1", "to_1"], f"오전·오후 표시 없음: '{x['raw']}'",
                f"{where(x['src'])} 「{x['raw']}」는 오후인가요, 새벽(오전)인가요?",
                [C("pm", f"오후 {hm(pm[0][0])}~{hm(pm[0][1])}", "확인됨"), C("am", f"새벽·오전 {hm(am[0][0])}~{hm(am[0][1])}", "확인됨"), UNKNOWN],
                (0, 1), original=x["raw"])
        else:
            days = sorted(d for d in {_v(p, f"date_{i}") for i in range(1, 8)} if ISO.fullmatch(d))
            if x.get("new"):                                    # a date the permit does not have (#5): confirm it
                nd = x["new"]
                ask_back(ask_item("date", x["src"], x["k"]), x["raw"], ["date_1"], f"허가서에 없는 날짜: {nd}",
                    f"{where(x['src'])} 「{x['raw']}」의 {int(nd[5:7])}월 {int(nd[8:10])}일은 허가서 작업일에 없습니다. 그날 작업이 맞나요?",
                    [C(nd, f"{int(nd[5:7])}월 {int(nd[8:10])}일에 함(새 날짜)", "확인됨")]
                    + [C(d, f"{int(d[5:7])}월 {int(d[8:10])}일(허가서 날짜)", "정정") for d in days] + [UNKNOWN],
                    (0, 1), original=x["raw"])
                continue
            word = (REL_DAY.search(x["raw"]) or [""])[0]
            ask_back(ask_item("date", x["src"], x["k"]), x["raw"], ["date_1"], f"날짜를 알 수 없는 말: '{word}'",
                f"{where(x['src'])} 「{x['raw']}」에서 「{word}」는 며칠인가요?",
                [C(d, f"{int(d[5:7])}월 {int(d[8:10])}일", "확인됨") for d in days] + [C("all", "날마다 같음", "확인됨"), UNKNOWN],
                (0, 1), original=x["raw"])
    # ---- a free answer croScan cannot read is not just filed: a time without numbers is asked as a time (A3), anything
    # else not understood is asked what it is about (U1). Once per free answer.
    dates = sorted(P["windows"]) or sorted(d for d in {_v(p, f"date_{i}") for i in range(1, 8)} if ISO.fullmatch(d))
    for n, ft in P.get("frees", []):           # ft, not t: t is the permit text used below
        vague = next((cl.strip() for cl in CLAUSE.split(ft) if VAGUE_TIME.search(cl) and not NO_WORK_TIME.search(cl)
                      and not COND.search(cl) and not re.search(r"\d", cl) and not re.search(CONC, cl)
                      and not other_work(cl, kind)), None)
        got = [x for x in found_in(ft, dates, kind) if not x.startswith("'아마")]
        if vague and not any(x.startswith("시간") for x in got):
            ask_back(f"A3.F{n}", vague, ["from_1", "to_1"], f"숫자 없는 시간: '{vague}'",
                f"추가로 적으신 「{vague}」는 몇 시부터 몇 시까지인가요?",
                [C("time", "시간 입력", "정정", "시작~끝 예: 13:00~16:00"), C("same", "신청한 시간 그대로", "확인됨"), UNKNOWN],
                (0, 2), original=vague)
        elif not got:
            ask_back(f"U1.F{n}", ft[:40], [], "알아듣지 못한 추가 전달",
                f"추가로 적으신 「{ft[:40]}{'…' if len(ft) > 40 else ''}」는 croScan이 어느 내용인지 알아듣지 못했습니다. 무엇에 대한 말인가요?",
                [C("time", "작업 시간", "정정", "시작~끝 예: 13:00~15:00"), C("place", "작업 장소", "정정", "BAY·칼럼·블록 번호 예: 3BAY 12-14 칼럼 E41P"),
                 C("other", "다른 팀 작업", "보강", "어떤 작업을 언제·어디서? 예: 같은 BAY 도장, 14~16시"),
                 C("note", "안전팀 참고로만 남김", "확인됨"), UNKNOWN],
                (0, 3), original=ft[:60])
    # ---- place and target (MT03): the work has to be found again later; BAY + a block number is enough
    crane_pins = kind == "loto" and P["cranes"]
    # an empty 작업장소 is asked for any kind (a lift's route or a crane number does not fill it)
    blank_place = not (_v(p, "location") or _v(p, "location_detail"))
    need_place = blank_place or (kind != "lifting" and not pl.get("whole") and not crane_pins and (pl["level"] <= 1 or (pl["level"] == 2 and not blocks)))
    if need_place:
        if kind == "loto":
            text = (f"작업장소에 '{pl['text'] or '(빈칸)'}'만 적혀 있습니다. 어느 설비(크레인 제어반·배전반 등)에서 하나요? "
                    "설비 번호와 위치(BAY)를 알려 주세요.")
            hint = "예: 21공장 3BAY 천장크레인 OH-21-03 제어반 CP-01 / 4BAY 10칼럼 배전반 MCC-4"
        elif pl["level"] == 2:
            text = f"작업장소에 '{pl['text']}'처럼 BAY까지만 적혀 있습니다. 칼럼 범위(기둥 번호)나 블록 번호를 알려 주시겠어요?"
            hint = "예: 3BAY 12-14 칼럼 E41P 블록"
        else:
            text = (f"작업장소에 '{pl['text'] or '(빈칸)'}'만 적혀 있습니다. 실제 작업 위치를 BAY·칼럼까지 알려 주시겠어요?"
                    + ("" if blocks else " 블록 번호도 함께 알려 주세요."))
            hint = "예: 대조립21공장 3BAY 12-14 칼럼 E41P 블록 / 여러 곳이면 쉼표로 / 공정번호가 있으면 함께"
        sig = "장소가 팀·부서 이름처럼 보임" if pl["org"] else "장소가 BAY까지만 있음" if pl["level"] == 2 else "장소에 BAY·칼럼이 없음"
        add("L1", P, ["location", "location_detail"], f"{sig}: '{pl['text']}'", text,
            [C("place", "위치 입력", "정정", hint), C("whole", "정말 공장 전체를 오가며 함", "확인됨"), UNKNOWN], (2, 0), original=pl["text"])
    elif kind in ("hot", "confined", "height") and not blocks:
        add("D1", P, ["job", "location_detail"], "블록·배관 번호가 없음", "어느 블록(또는 배관·구획)에서 하는 작업인가요? 번호를 알려 주세요.",
            [C("text", "번호 입력", "보강", "예: E41P 블록 / P-07 배관"), C("na", "특정 대상 없음", "해당없음"), UNKNOWN], (2, 1))
    if kind == "loto" and not P["cranes"] and not P["targets"] and not need_place:     # no equipment number at all
        add("L1", P, ["job"], "설비 번호 없음", "어느 설비(크레인 제어반·배전반 등)인가요? 번호를 알려 주세요.",
            [C("place", "번호 입력", "보강", "예: OH-21-03 제어반 CP-01 / 배전반 MCC-4"), UNKNOWN], (2, 0))
    # ---- kind: scope, method, and the facts that decide where the hazard goes (research thoughts p381: target,
    # action/method/gas, work·recovery range, the key steps, related support/system)
    sc = _scope(P, ans)
    if kind == "hot":
        if sc is None:
            add("H1", P, ["job"], "보수 범위(국부 보수/부재 교체)가 없음",
                "불량부는 용접부만 파내는 보수인가요, 부재를 떼어 교체하나요? 몇 군데인가요?",
                [C("local", "용접부만 보수", "보강", "몇 군데인가요? 예: 3군데"), C("replace", "부재를 떼어 교체", "보강", "몇 개인가요? 예: 판재 1장"),
                 UNKNOWN], (3, 1))
        if said(t, RX["hot_method"]) is not True and not p.get("gouging", {}).get("value"):    # '가스절단은 안 함' alone: still unknown
            add("H2", P, ["job"], "절단·용접 방법과 가스가 없음",
                "절단·가우징·용접은 어떤 방법으로 하고, 어떤 가스(산소·LPG·CO2·아르곤 등)를 쓰나요?",
                [C("text", "방법·가스 입력", "보강", "예: 아크 가우징, CO2 용접 / 산소·LPG 절단"), C("na", "가스 안 씀(전기 용접만)", "해당없음"), UNKNOWN], (4, 0))
        elif said(t, HOT_GAS) is None:
            # the method is known but not the gas (MT10, p205: method·gas·power are kept apart; one known does not
            # close the other): only the gas is asked
            add("H2", P, ["job"], "방법은 있으나 쓰는 가스가 없음",
                "적으신 방법에 쓰는 가스(산소·LPG·CO2·아르곤·압축공기 등)는 무엇인가요? 가스를 쓰지 않으면 「가스 안 씀」을 눌러 주세요.",
                [C("text", "가스 입력", "보강", "예: CO2 용접, 가우징은 압축공기"), C("na", "가스 안 씀(전기 용접만)", "해당없음"), UNKNOWN], (4, 0))
            qs[-1]["m"] = 0.5                                        # the method is known (design §3.2 M)
        # what the removed part holds up (MT08, p205): asked for a replacement and for a deep local removal (p200 「국부
        # 파내기: 완전 분리 없어도 지지 영향 가능」); a recovery word ('내려', '크레인') does not answer whether it holds
        # anything up
        deep = sc == "local" and said(t, RX["hot_deep"])
        if (sc == "replace" or deep) and said(t, HOLDS) is None:
            add("H3", P, ["job"], "부재 분리: 지지·회수 계획 없음" if sc == "replace" else "깊은 파내기: 받치는 구조 언급 없음",
                ("떼어내는 부재가 다른 구조나 발판을 받치고 있나요? 떼어낸 부재는 무엇으로 받쳐 어디로 내리나요?" if sc == "replace" else
                 "깊게 파내는 부재가 다른 구조나 발판을 받치고 있나요? 파내는 동안 따로 받쳐 두나요?"),
                [C("text", "지지·회수 입력", "보강", "예: 받치는 것 없음, 체인블록으로 받아 하부 적치장에"), UNKNOWN] if sc == "replace" else
                [C("none", "받치는 것 없음", "확인됨"), C("text", "받치고 있음(받침 계획)", "보강", "예: 상부 발판 지지재, 파내기 전 임시 받침"), UNKNOWN],
                (5, 0))
        at_height = bool(height_in(jt)) or p.get("hot_at_height", {}).get("value")
        if at_height and not pl["layer"]:
            h = height_in(jt)
            add("L3", P, ["location_detail"], "높이 작업인데 상하·내부 표시 없음",
                (f"작업내용에 높이 {h:g}m가 있습니다. " if h else "") + "블록 위(상부)·옆·아래(하부)·안(내부) 중 어디서 하나요?",
                [C("text", "위치 입력", "보강", "예: 블록 상부 발판 위 2.5m"), UNKNOWN], (4, 1))
    if kind == "confined":
        if sc is None:
            entry = "" if said(t, CF_MODE) else " 머리·상체만 넣는지, 몸 전체가 들어가 이동하는지도 알려 주세요."
            add("CF1", P, ["job"], "내부 작업 목적이 없음", "안에 들어가서 무엇을 하나요? (검사·청소·회수·보수 등) 몇 곳, 몇 번 들어가나요?" + entry,
                [C("inspect", "검사·점검", "보강", "몇 곳·몇 번? 예: 2곳, 1번 진입"), C("clean", "청소·잔재 정리", "보강", "범위 예: 1m² 안팎, 1번 진입"),
                 C("repair", "보수·용접", "보강", "무엇을? 예: 국부 용접 1곳"), C("text", "기타 입력", "보강", "하는 일·횟수"), UNKNOWN], (3, 1))
        elif said(" ".join(_v(p, k) for k in ("job", "job_detail", "location_detail")) + " " + P["said"], CF_MODE) is None and not get("CF1"):
            # the purpose is written ('검사') but not how one goes in (N2 MT04, p246): a written purpose does not skip it
            add("CF1", P, ["job"], "진입 방식(머리·상체/전신)이 없음", "머리·상체만 넣나요, 몸 전체가 들어가 안에서 이동하나요?",
                [C("head", "머리·상체만 넣음", "보강"), C("full", "몸 전체가 들어가 이동함", "보강", "들어가는 곳·대략 깊이 예: 맨홀 M-2, 안쪽 10m (배관이면 직경·굽은 곳도)"), UNKNOWN], (3, 1))
            qs[-1]["m"] = 0.5
        if (said(t, RX["cf_link"]) or p.get("argon", {}).get("value")) and need_catalog.atoms("CF2", "text", doc_text(P))["missing"]:
            # N2 MT07 (p246): the supply cut, kept while inside and restored when; one 「밸브 잠금」 does not say all of it,
            # nor another team's supply·pressure test·restore planned for the entry time
            add("CF2", P, ["hazards"], "연결 계통(가스·배관)과 차단·유지 계획이 없음",
                "들어가는 배관·구획에 가스(아르곤 등)나 공기를 넣는 연결 계통이 있나요? 있으면 진입 중에는 차단해 두나요? "
                "다른 팀의 가스 공급·압력시험·복구가 진입 시간에 예정돼 있나요?",
                [C("none", "연결 계통 없음", "확인됨"), C("text", "있음(계통·차단·다른 팀 예정)", "보강", "예: 아르곤 퍼지 라인 V-12, 진입 전 차단·진입 중 유지, 배관팀 시험 없음"), UNKNOWN], (5, 0))
        if (said(t, HOT_INSIDE) or (get("CF1") or {}).get("choice") == "repair") and said(t, RX["hot_method"]) is not True:
            # the real form (위험작업신고서 실물 p2): hot work inside a confined-space permit, written only in 유해위험요소
            # ('화기작업시 …, 병행 작업 금지'): whether it is done inside, how, and under which hot-work permit
            add("CF4", P, ["hazards", "job"], "밀폐 허가서에 화기 언급, 방법·허가서 없음",
                "안에서 용접·절단·그라인딩 같은 화기를 하나요? 하면 어떤 방법·가스로 하고, 별도 화기작업 허가서가 있나요(번호)?",
                [C("yes", "함: 방법·가스·허가서 입력", "보강", "예: CO2 용접 1곳, 화기작업 허가서 0712"), C("no", "안에서 화기 없음", "확인됨"), UNKNOWN],
                (4, 1))
        if said(_v(p, "job") + " " + _v(p, "job_detail") + " " + P["said"], r"도장|스프레이|세정|세척|페인트|코팅") and said(t, r"화기\s*(?:완료|종료|끝)") is None:
            # interview p33 「화기가 남은 탱크에 도장」: what he heard of hot work left in the space he goes in to paint
            add("CF5", P, ["job"], "도장·세정 진입: 그 구획의 화기 완료 여부 언급 없음",
                "들어가 도장·세정할 구획에서 용접·절단 같은 화기가 모두 끝났다고 들었나요?",
                [C("done", "끝났다고 들음", "확인됨", "누구에게 들었나요? 예: 용접2팀 반장"), C("left", "남은 화기 있음", "보강", "언제·무엇? 예: 14시까지 보강 용접"),
                 UNKNOWN], (5, 2))
        if p.get("commissioning", {}).get("value") and not (confirmed(t, LIVE_NONE) or confirmed(t, LIVE_WHO)):
            # the form's 수전구역(COMMISSIONING AREA) tick (신고서양식 p1·2): which live or test-run equipment is there
            add("D6", P, ["commissioning"], "수전구역 체크, 통전·시운전 설비 언급 없음",
                "작업 구간에 통전·시운전 중인 설비가 있나요? 있으면 차단·잠금은 누가 확인하나요?",
                [C("text", "있음(설비·확인자)", "보강", "예: 펌프 P-3 시운전 중, 전기팀 김XX 차단 확인"), C("none", "없음", "확인됨"), UNKNOWN], (5, 2))
        if p.get("pressure_use", {}).get("value") and not (confirmed(t, TEST_MEDIUM) and confirmed(t, TEST_START) and confirmed(t, TEST_END)):
            # the form's 압력사용(PRESSURE) tick: the test medium decides the hazard (nitrogen: air loss), and when it is
            # under pressure (the pressure value itself is the day's: 테스트압력 is not asked)
            add("D7", P, ["pressure_use"], "압력사용 체크, 시험 매체·가압 시각 없음",
                "압력(기밀)시험의 매체는 무엇(공기·질소·물)이고, 가압 시작·감압 완료는 몇 시인가요?",
                [C("text", "매체·시각 입력", "보강", "예: 질소, 10:00 가압 ~ 11:30 감압 완료"), UNKNOWN], (5, 2))
        if not confirmed(t, POWER_SRC):
            # N2 MT08 (p247): the air, light and fan inside depend on a power source another work may cut; which one
            add("CF3", P, ["job_detail"], "환기·송기·조명의 전원 언급 없음",
                "안에서 쓰는 환기팬·송기·조명은 어느 전원(분전반·발전기)에 물려 있나요? 진입 중 그 전원을 끊는 다른 작업이 있다고 들었나요?",
                [C("text", "전원 입력", "보강", "예: 3BAY 분전반 DB-2에서 환기팬·조명, 끊는 작업 들은 것 없음"),
                 C("na", "전원 쓰는 환기·조명 없음(자연환기)", "해당없음"), UNKNOWN], (5, 1))
    if kind == "height":
        n, need_m = P["count"], sc is None
        if n is None or need_m:
            lugless = said(t, r"러그|인양\s*고리|피스|절단|제거") is None     # the permit does not say anything is taken down
            what = ("떼어 낼 러그(임시 인양고리)가 있나요? 있으면 몇 개를 어떤 방법(가스절단·플라즈마·그라인더)으로 떼나요?" if lugless and n is None and need_m else
                    "어느 블록의 러그 몇 개를 어떤 방법(가스절단·플라즈마·그라인더)으로 떼나요?" if n is None and need_m else
                    f"러그 {n}개는 어떤 방법(가스절단·플라즈마·그라인더)으로 떼나요?" if need_m else "러그는 몇 개를 떼나요?")
            add("HT1", P, ["job", "job_detail"], "러그 수량·절단 방법이 없음" if n is None and need_m else "절단 방법이 없음" if need_m else "러그 수량이 없음", what,
                ([C("gas", "가스절단", "보강", "러그 개수 예: 6개") if n is None else C("gas", "가스절단", "보강"),
                  C("plasma", "플라즈마", "보강", "러그 개수 예: 1개") if n is None else C("plasma", "플라즈마", "보강"),
                  C("mech", "그라인더·기계절단", "보강", "러그 개수 예: 1개") if n is None else C("mech", "그라인더·기계절단", "보강")] if need_m else
                 [C("text", "개수 입력", "보강", "예: 6개")]) + ([] if lugless else [C("na", "떼는 러그 없음", "해당없음")]) + [UNKNOWN], (3, 1))
            if lugless:                                              # 「없음」 first: the likely answer for such a permit
                qs[-1]["choices"].insert(0, C("na", "떼는 러그 없음", "해당없음"))
            if not (n is None and need_m):
                qs[-1]["m"] = 0.5                                    # one of count·method is known (design §3.2 M)
        if not pl["layer"] or P["height"] is None:
            text = ("블록 위(상부)에서 하시나요? 바닥에서 대략 몇 m 높이인가요?" if not pl["layer"] else "바닥에서 대략 몇 m 높이에서 작업하나요?")
            add("L3", P, ["location_detail", "work_height"], "작업 높이·상하 표시 없음", text,
                [C("text", "높이 입력", "보강", "예: 블록 상부 4.8m"), UNKNOWN], (4, 1))
        ht1 = get("HT1")
        no_lug = (ht1 and ht1.get("choice") == "na") or said(t, r"러그") is False
        # N3 MT09 (p274): by what means and to where; one word ('로프') does not say both
        jt_said = " ".join(_v(p, k) for k in ("job", "job_detail")) + " " + P["said"]     # not the work's own place
        if not no_lug and need_catalog.atoms("HT2", "text", jt_said)["missing"]:
            add("HT2", P, ["job_detail"], "떼어낸 러그의 회수 방법·내릴 곳이 없음",
                "떼어낸 러그는 무엇으로 받아 어디에 내리나요? 그 아래나 옮기는 길에 다른 작업·통행이 있나요? 러그 1개 무게와, 지금 러그에 하중이 걸려 있지 않은지도 알려 주세요.",
                [C("text", "회수 방법 입력", "보강", "예: 로프로 내려 하부 적치함, 하부는 통행 통제"), C("na", "해당 없음", "해당없음"), UNKNOWN], (5, 0))
    if kind == "lifting":
        nblocks = P["count"] or len(blocks)
        if not P["cranes"]:
            add("LI1", P, ["job"], "크레인 번호가 없음",
                "어느 크레인(번호)으로 옮기나요? 공동인양·뒤집기(반전)·차량 인계도 하나요?" + ("" if nblocks else " 옮기는 블록 번호(또는 개수)도 알려 주세요."),
                [C("text", "크레인·방법 입력", "보강", "예: OH-21-01 한 대, 반전 없음" + ("" if nblocks else ", E21P 블록 1개") + " (매다는 무게는 줄걸이·빔 포함)"), UNKNOWN], (2, 2))
        elif not nblocks:
            # N4-MT01·MT02 (p314): the crane is known but not which block or how many, nor the method
            add("LI1", P, ["job"], "옮기는 블록 번호·개수가 없음",
                "몇 개 블록(번호)을 옮기나요? 공동인양·회전·반전·차량 인계가 있나요?",
                [C("blocks", "블록·방법 입력", "보강", "예: E21P 블록 1개, 단일 인양·반전 없음"), UNKNOWN], (2, 2))
        if said(t, RX["route"]) is None:
            # N4-MT05·MT07·MT14 (p314): with the route, the meaning of a wide column range, where it turns, where a
            # vehicle takes it — each only when the permit says it (one bubble, no further question)
            cr_ = pl.get("colrange")
            more = ((f" 적힌 '{pl['cols']}'는 출발 위치인가요, 지나가는 길인가요?" if cr_ and cr_[1] - cr_[0] >= 3 else "")
                    + (" 회전·반전하는 위치(칼럼)도 알려 주세요." if said(t, RX["li_turn"]) or said(t, RX["li_rotate"]) else "")
                    + (" 차량에 싣는 곳·내리는 곳도 알려 주세요." if said(t, RX["li_vehicle"]) else ""))
            add("L5", P, ["location"], "이동 경로 없음", "블록을 어디에서 어디로 옮기나요? 지나가는 BAY·통로도 알려 주세요." + more,
                [C("text", "경로 입력", "보강", "예: 3BAY 12-16 칼럼 → 3BAY 동측 통로 → 1BAY 반출장 (공장 대형문 통과 여부도)"), UNKNOWN], (3, 0))
        if P["cranes"] and not confirmed(t + " , " + ((get("B3") or {}).get("value") or ""), RAIL_SAID):
            # N4-MT11 (p314): the same crane under maintenance, or another crane on the same rail — what he heard
            add("LI3", P, ["job"], "같은 크레인 정비·같은 주행로 운행 관계 미정",
                f"옮기는 동안 그 크레인({', '.join(sorted(P['cranes']))})의 정비나, 같은 주행로(레일)에서 다른 크레인 운행·정비가 있다고 들었나요?",
                [C("none", "들은 것 없음", "확인됨"), C("text", "있음(크레인·시각)", "보강", "예: OH-21-02 10시 정비, 같은 레일"), UNKNOWN], (7, 1))
        if said(t, RX["li_inside"]) is None:
            add("LI2", P, ["job"], "블록 안·위 작업, 붙어 있는 것 언급 없음",
                "옮기기 전에 그 블록 안이나 위에서 하는 작업, 붙어 있는 배관·발판·전선이 있나요?",
                [C("none", "없음", "확인됨"), C("text", "있음", "보강", "무엇이 있는지 예: 블록 내부 취부 2명, 10시 철수"), UNKNOWN], (5, 0))
        lw, swl = _num(_v(p, "load_weight")), _num(_v(p, "crane_swl"))
        if lw is not None and swl is not None and lw > swl:
            add("C4", P, ["load_weight", "crane_swl"], f"중량 {lw:g}t > 정격 {swl:g}t",
                f"인양물 중량 {lw:g}톤이 크레인 정격하중 {swl:g}톤보다 큽니다. 어느 값이 맞나요?",
                [C("text", "맞는 값 입력", "정정", "예: 중량 12톤(줄걸이·빔 포함), 정격 20톤"), UNKNOWN], (6, 0), original=f"{lw:g}t / {swl:g}t")
    if kind == "loto":
        if sc is None:
            add("LO1", P, ["job"], "작업 범위(점검/수리·교체)가 없음", "원인을 찾는 점검인가요, 원인이 확인된 수리·부품 교체인가요?",
                [C("diag", "원인 찾는 점검", "보강"), C("module", "부품 교체", "보강", "무엇을? 예: 인버터 1대"), C("repair", "정해진 수리", "보강", "무엇을? 예: 접점 교체"),
                 C("install", "설치·증설", "보강", "무엇을? 예: 용접기 전원 분기 1회로 증설"), UNKNOWN], (3, 1))
        if need_catalog.atoms("LO3", "text", t)["required_missing"]:          # both 차단 and 복구 said, not one of them
            # N5 MT05·MT06·MT12 (p355): a restore midway and re-cut, the test run and its stretch, and whether the end
            # written is the repair's or the test·hand-over's are kept apart (atoms; only 차단·복구 are required)
            add("LO3", P, ["job_detail"], "차단·복구·시험운전 시각 없음",
                "전원은 언제 끊고 언제 복구하나요? 중간에 복구했다 다시 끊으면 그 시각도, 복구 뒤 시험운전(주행·권상)이 있으면 그 시각·구간과, "
                "함께 멈추는 설비(환기팬·조명 등)와 같은 전원에 다른 팀 잠금이 있는지도 알려 주세요. 적으신 종료는 수리 완료인가요, 시험·운전 인계까지인가요?",
                [C("text", "시각·설비 입력", "보강", "예: 13:00 차단, 14:30 복구, 14:45 시험운전(08~12 칼럼 주행), 3BAY 조명 일부 꺼짐, 다른 팀 잠금 없음, 15:00 운전팀 인계"),
                 UNKNOWN], (5, 0))
            if need_catalog.atoms("LO3", "text", t)["have"]:
                qs[-1]["m"] = 0.5                                    # a part of 차단·복구·시험운전 is written
        if said(t, RX["lo_access"]) is None and (P["cranes"] or not P["targets"]):   # 거더·상부 is a crane's: known other equipment is not asked
            add("LO4", P, ["location_detail"], "제어반 앞/거더·상부 접근 언급 없음", "제어반 앞에서만 작업하나요, 크레인 거더·상부에도 올라가나요?",
                [C("front", "제어반 앞에서만", "확인됨"), C("text", "거더·상부에도 올라감", "보강", "어디 예: 거더 상부 주행로, 트롤리 위"), UNKNOWN], (5, 0))
        if sc == "diag" and said(t, LIVE) is None:
            # ACC-E14 (p372), 유의점 4-5 (p378): looking for the cause can include measuring with the power on; asked once
            add("LO5", P, ["job_detail"], "원인 찾는 점검: 통전 상태 측정 여부 없음",
                "원인을 찾는 동안 전원이 들어간 상태로 측정·확인하는 단계가 있나요?",
                [C("dead", "정전 상태로만 함", "확인됨"), C("live", "있음: 무엇을·몇 시", "보강", "예: 인버터 출력 전압 측정 13:20"), UNKNOWN], (4, 2))
        if P["cranes"] and not confirmed(t + " , " + ((get("B3") or {}).get("value") or ""), RAIL_SAID):
            # N5 MT11 (p355): another crane on the same rail, or another team's work to check before the restore
            add("LO6", P, ["job"], "같은 주행로·다른 팀 작업 관계 미정",
                "수리하는 동안 같은 주행로(레일)에서 다른 크레인 운행이나 이 크레인을 쓰려는 작업이 있다고 들었나요? 복구 전에 확인할 다른 팀 작업이 있나요?",
                [C("none", "들은 것 없음", "확인됨"), C("text", "있음(크레인·팀·시각)", "보강", "예: OH-21-02 같은 레일 운행, 도장팀 거더 하부 14시까지"), UNKNOWN], (7, 1))
    _wait_state(P, ans, add)
    # ---- several blocks over several days (실물 0400: 블록 9개·4일): which block on which day (L4, so far the 안전관리자
    # view's only); and, for work that throws sparks, drops or lifts, the range kept closed while working (L6, interview
    # p41 「오늘 여기서 여기까지」) — L6 extra, after the core questions
    many_ids = blocks_in(_v(p, "job") + " " + _v(p, "job_detail"))
    ndays = len({d for d, ws in P["windows"].items() if ws})
    if len(many_ids) > 1 and ndays > 1:
        add("L4", P, ["job"], f"블록 {len(many_ids)}개·{ndays}일", "여러 블록을 동시에 하나요, 순서대로 하나요? 블록별 작업 날짜를 알려 주세요.",
            [C("text", "순서·날짜 입력", "보강", "예: 10/27 B11·F31, 10/28 E11"), C("same", "날마다 모든 블록을 함께 함", "확인됨"), UNKNOWN], (6, 2))
    if kind in ("hot", "height", "lifting") and not confirmed(t, CONTROL_RANGE):
        add("L6", P, ["location_detail"], "작업 중 통제 범위 언급 없음",
            "작업하는 동안 출입을 막는 범위(불티·낙하물·인양 반경)는 어디까지인가요?",
            [C("text", "범위 입력", "보강", "예: 하부 반경 5m, 3BAY 동측 통로 통제"), UNKNOWN], (8, 2), tier="extra")
    # ---- space fit (MT09/MT07/MT06): a column range wider than a local work, for one target
    cr = pl.get("colrange")
    listed = {x for x in ids(_v(p, "job") + " " + _v(p, "job_detail")) if not CRANE.fullmatch(x)}
    many = len(listed) > 1 or (P["count"] or 0) > 1          # counted, not the bare word 「여러」 (a word decides nothing)
    local = kind in ("height", "loto", "confined") or (kind == "hot" and sc != "replace")
    if cr and cr[1] - cr[0] >= 3 and local and (not many or kind == "height"):
        if kind == "height" and many:
            # N3 MT07 (p274): several lugs can explain a wide range, or it takes in the access and recovery path
            text = f"작업장소의 '{pl['cols']}'는 여러 러그의 위치인가요, 접근·회수 경로까지 포함한 범위인가요?"
            yes = C("yes", "러그 위치들의 범위임", "확인됨")
        else:
            text = f"작업장소의 '{pl['cols']}'는 실제로 작업하는 위치인가요, 이동·회수·접근 경로까지 포함한 범위인가요?"
            yes = C("yes", "그 범위에서 작업함", "확인됨")
        # a crane repair's range may be its test run or the cable checked (N5 MT14, p355)
        extra = [C("test", "주행·권상 시험 구간 포함", "보강", "시험 구간 예: 08~12 칼럼 주행"), C("cable", "케이블 점검 구간 포함", "보강", "점검 구간 예: 10~14 칼럼")] \
            if kind == "loto" else []
        add("L7", P, ["location"], f"칼럼 범위 {pl['cols']} ({cr[1] - cr[0]}구간): " + ("러그 여러 개" if kind == "height" and many else "국부 작업 하나보다 넓음"),
            text, [yes, C("place", "실제 작업 위치는 좁음", "정정", "실제 위치 예: 14-15 칼럼 E41P 동측")] + extra + [UNKNOWN], (4, 2),
            original=pl["cols"])
    # ---- a column range written backwards ('14-12 칼럼', F01 p392: an input error is not silently read as 12~14)
    rev = re.search(r"(\d{1,2})\s*[-~]\s*(\d{1,2})\s*(?:칼럼|축)", pl["text"])
    if rev and int(rev.group(1)) > int(rev.group(2)):
        lo_, hi_ = int(rev.group(2)), int(rev.group(1))
        ask_back("A4.cols", rev.group(0), ["location"], f"칼럼 범위가 거꾸로 적힘: '{rev.group(0)}'",
                 f"작업장소의 「{rev.group(0)}」은 {lo_}~{hi_} 칼럼인가요?",
                 [C("yes", f"{lo_}~{hi_} 칼럼이 맞음", "확인됨"), C("place", "다른 위치", "정정", f"예: 3BAY {lo_}-{hi_} 칼럼"), UNKNOWN],
                 (0, 2), original=rev.group(0))
    # ---- required header blanks (B1); day-of boxes, 허가구분·2중점검 and the place are not asked
    for k, f in p.items():
        if (not f["required"] or f["type"] in ("check", "image") or _v(p, k) or k in ("location", "location_detail")
                or k in DAY_OF_VALUES or k in NOT_FOREMAN or k.startswith(("date_", "from_", "to_")) or k.endswith("_sign")):
            continue
        add(f"B1.{k}", P, [k], f"'{f['name']}' 빈칸", f"'{f['name']}' 칸이 비어 있습니다. 값을 알려 주세요.",
            [C("value", "값 입력", "정정", f["name"] + (" (숫자)" if f["type"] in ("number", "count") else "")), C("na", "해당 없음", "해당없음"), UNKNOWN], (6, 1))
    # ---- 병행여부 empty: what the 작업반장 knows of other work (filing item 4, research process p4)
    if not P["concurrent"]:                                   # another answer's 'none' is a proposal to confirm, not this answer
        add("B3", P, ["concurrent"], "병행여부 빈칸", "병행여부가 비어 있습니다. 같은 시간·장소에 알고 있는 다른 작업이 있나요?",
            [C("yes", "있음", "보강", "어떤 작업을 언제·어디서? 예: 같은 BAY 14-16 칼럼 도장, 오후"), C("no", "없음", "확인됨"), UNKNOWN], (7, 0))
    # ---- a closing free answer that says the opposite of an earlier answer (research: ask on 내부 상충, once)
    for item, choice, rx, what in CONFLICT:
        a = get(item)
        # a 「없음」 typed as words counts as the 「없음」 choice (negated: plain, unconditional denials only)
        if a and eff_choice(item, a) == choice and P["free"] and said(P["free"], rx, hedged=True):     # '아마 있을걸요' too
            q0 = a.get("q") if isinstance(a.get("q"), dict) else {}
            said0 = (a.get("value") or "").strip()[:40] if a.get("choice") != choice else                 next((c["label"] for c in q0.get("choices", []) if c["id"] == choice), choice)      # his own words when typed
            add(f"C5.{item}", P, q0.get("keys", []), f"앞 답 「{said0}」 ≠ 추가 전달 내용",
                f"앞에서 {what}에 대해 「{said0}」이라고 답하셨는데, "
                f"추가로 적으신 내용에는 {what}이 있습니다. 어느 쪽이 맞나요?",
                [C("free", "추가로 적은 내용이 맞음", "정정", "자세히 예: 블록 안 취부 2명, 10:00 철수 후 인양"), C("before", "앞의 답이 맞음", "확인됨"), UNKNOWN],
                (6, 0), original=said0)
    # a clause that forbids concurrent work ('병행 작업 금지', research p18 Q6) names no other work
    free_ = re.sub(r"(?:병행|동시|혼재)\s*(?:작업)?\s*(?:금지|하지\s*않도록|없도록)", " ", P["free"] or "")
    if P["concurrent"] == "N" and free_.strip() and (said(free_, CONC, hedged=True) or other_work(free_, kind)):
        add("C5.concurrent", P, ["concurrent"], "병행여부 N인데 추가 전달에 다른 작업 언급",
            "병행여부를 N(없음)으로 적으셨는데, 추가로 적으신 내용에 다른 작업이 있습니다. 같은 시간·같은 장소에서 하는 작업인가요?",
            [C("free", "같은 시간·장소임", "정정", "무엇을 언제·어디서? 예: 같은 BAY 14-16 칼럼 도장, 14~16시"), C("before", "시간이나 장소가 다름", "확인됨"), UNKNOWN],
            (6, 0), original="N")
    # ---- an answer that says other than the document (design §3.5 「문서와 답이 상충」): both are kept and it is asked
    # once whether the answer corrects the document (C6; the ask-back budget is shared)
    # the question carries a fingerprint of the facts compared: the same disagreement is asked once, a new one again
    for item, keys, doc, said_ in doc_conflicts(P, ans):
        fp = __import__("hashlib").sha1(f"{doc}|{said_}".encode("utf-8")).hexdigest()[:6]
        ask_back(f"C6.{item}~{fp}", said_, keys, f"서류 「{doc}」 ≠ 답 「{said_}」",
                 f"서류에는 「{doc}」로 적혀 있는데, 답은 「{said_}」입니다. 답이 맞아 서류를 고치는 것(정정)인가요?",
                 [C("answer", "답이 맞음(서류 정정)", "정정"), C("doc", "서류가 맞음", "확인됨"), UNKNOWN], (6, 0), original=doc)
        if qs and qs[-1]["qid"] == f"C6.{item}~{fp}:{pid}":
            qs[-1]["item"] = f"C6.{item}"                  # the item stays C6.X; the qid carries the fingerprint
    # ---- time fit (MT05) last: it needs the scope, count and the meaning of the time
    fit = time_fit(P, ans, bool(whole or copied))
    P["fit"] = fit
    if fit["state"] in ("long", "short"):
        ref = f"참고 작업시간 {fit['lo']}~{fit['hi']}분"          # QA #19: no model code in the question; 2쪽 says what it is
        if fit["state"] == "long":
            add("T6", P, ["from_1", "to_1"], f"작업시간 {fit['minutes']}분 > {ref}",
                f"적힌 작업시간 {fit['minutes']}분은 {ref}보다 깁니다. {LONG_Q.get(kind, '대기·검사·반복이나 추가 범위')}가 포함됐나요?",
                [C("text", "포함된 것 입력", "확인됨", "예: 검사 대기 1시간, 2군데 추가"), C("retime", "실제 시간 다시 입력", "정정", "예: 13:00~15:00"), UNKNOWN],
                (8, 0), original=f"{fit['minutes']}분")
        else:
            # the meaning of the end written (N1 MT13, N2 MT12, N3 MT12, N4-MT13, N5 MT12): the part, or up to the end
            # of recovery·exit·hand-over. 「특정 단계만」 takes the whole work's time, which the window grows to.
            add("T6", P, ["from_1", "to_1"], f"작업시간 {fit['minutes']}분 < {ref}",
                f"적힌 작업시간 {fit['minutes']}분은 {ref}보다 짧습니다. {END_Q[kind]}",
                [C("yes", f"{END_Q_ALL[kind]}까지 전체 시간이 맞음", "확인됨"),
                 C("stage", "특정 단계만 적음", "보강", "끝까지 걸리는 전체 시간 예: 09:00~13:00"), UNKNOWN],
                (8, 0), original=f"{fit['minutes']}분")
    # ---- the end of the work (N1 MT13 p205, N3 MT12 p275, LU15-FIRE p266): for hot work, and for a lug cut with gas or
    # plasma, whether the end written is the cut's or the ember check's, and until when (extra, last; asked once, the
    # same item as the 안전관리자 view's T4). Not while the meaning of the time itself is open (T1·T6 asked, not
    # answered: DEFER). The pair rules keep the residual whatever the answer.
    open_time = (any(q["item"].split(".")[0] in ("T1", "T5", "T6", "T7") and q["permit_no"] == pid and _open(get, q["item"]) for q in qs)
                 or "unknown" in P.get("t5", {}).values())
    t6_all = kind == "hot" and (get("T6") or {}).get("choice") == "yes"        # 「잔불 확인까지 전체 시간이 맞음」
    if ((kind == "hot" or (kind == "height" and sc in ("gas", "plasma"))) and P["windows"] and not open_time
            and not t6_all and not confirmed(t, EMBER_SAID)):
        end = max(b for ws in P["windows"].values() for _, b in ws)
        what = "용접·절단" if kind == "hot" else "러그 절단"
        add("T4", P, ["to_1"], f"종료 {hm(end)}의 뜻(잔불 확인 포함 여부) 미정",
            f"적으신 종료 {hm(end)}은 {what}이 끝나는 시각인가요, 잔불 확인·정리까지 끝나는 시각인가요? 잔불 확인이 그 뒤에 끝나면 그 시각을 알려 주세요.",
            [C("incl", "잔불 확인·정리까지 포함", "확인됨"), C("time", "그 뒤 잔불 확인 끝: 시각 입력", "보강", "예: 16:00"), UNKNOWN],
            (8, 1), original=hm(end), tier="extra")
    # a T4 end before the work's own end with no day said ('01:00' after 20:00~23:00): the next day, or a slip? asked once
    r = P.get("residual_ask")
    if r is not None and P["windows"].get(r[0]):
        end = max(b for _, b in P["windows"][r[0]])
        r = r[1]
        ask_back("A5.T4", hm(r), ["to_1"], f"잔불 확인 끝 {hm(r)} < 작업 끝 {hm(end)}",
                 f"잔불 확인 끝을 {hm(r)}로 적으셨는데 작업 끝({hm(end)})보다 이릅니다. 다음 날 {hm(r)}인가요?",
                 [C("next", f"다음 날 {hm(r)}", "확인됨"), C("fix", "시각을 다시 입력", "정정", "예: 23:30, 다음날 01:00"), UNKNOWN],
                 (0, 1), original=hm(r))
    # ---- not asked, written on page 2 for the safety team
    if not _v(p, "hull_no"):
        if equip:
            assumed.append({"permit_no": pid, "item": "B4", "name": "호선/공사", "original": "",
                            "value": "호선 무관으로 추정 (설비·공용 작업)", "why": "작업내용·장소가 설비 작업이라 호선이 없는 것이 보통임"})
        else:
            deferred.append({"permit_no": pid, "name": "호선/공사", "text": "빈칸 (반장에게 묻지 않음, 필요하면 안전팀 확인)"})
    haz, need = _v(p, "hazards"), HAZ_WORDS.get(kind, "")
    if need and not re.search(need, haz):
        what = {"confined": "질식·산소결핍·가스", "hot": "화재·불티", "height": "추락·낙하", "lifting": "낙하·협착·충돌", "loto": "감전·재가동"}[kind]
        deferred.append({"permit_no": pid, "name": "유해위험요소", "text": f"'{haz[:30] or '(빈칸)'}'에 {what} 언급 없음 → 규칙 보강 제안: {what}"})


def questions(fields, answers, manager=False):
    """Every open question, core first (design 4). No cap: the conversation goes on while any is open.
    manager=False is the 작업반장 view (one permit as filed): no question comes from another permit.
    The pair questions (T3/T4 by overlap, L2, X1-X6, C3) are for the 안전관리자 view, comparing a day's permits.
    Returns (open questions, permits, pairs, rule estimates)."""
    perms = effective(fields, answers)
    answers = drop_stale(perms, answers)                      # a T7 answer about another row is asked again
    done = {a["qid"] for a in answers or []}                  # a question answered stays answered (taken back too)
    if not manager:
        ans = {a["qid"]: a for a in live_answers(answers)}
        qs, assumed, deferred = [], [], []
        for P in perms:
            _foreman(P, ans, qs, assumed, deferred)
        uniq = {}
        for q in qs:
            uniq.setdefault(q["qid"], q)
        open_ = sorted((q for q in uniq.values() if q["qid"] not in done), key=lambda q: (q["prio"], q["page"]))
        return open_, perms, [], assumed + [dict(d, item="DEFER") for d in deferred]
    prs = pairs(perms)
    by_no = {P["no"]: P for P in perms}
    involved = {}                                  # page -> pairs of level 1-3 it is in
    for x in (prs if manager else []):
        if x["level"] <= 3:
            for n in (x["a"], x["b"]):
                involved.setdefault(n, []).append(x)
    qs, assumed = [], []
    for P in perms:
        p, kind, n = P["p"], P["kind"], P["no"]
        mine = involved.get(n, [])
        others = lambda: ", ".join(sorted({(x["b_who"] if x["a"] == n else x["a_who"]) for x in mine}))
        work = WORK.get(kind, "작업을")
        jt = " ".join(_v(p, k) for k in ("job", "job_detail", "location_detail"))
        alltext = jt + " " + _v(p, "location")
        equip = bool(EQUIP.search(alltext)) or kind == "loto"
        pl = P["place"]
        # ---- time: T1 whole shift / T2 the same hours copied over days (core: every pair check starts from time)
        rows = [(d, a, b) for d, ws in sorted(_windows(p).items()) for a, b in ws]
        whole = [(d, a, b) for d, a, b in rows if a <= DAY_START and b >= DAY_END]
        if whole:
            ds = f"{whole[0][0]}~{whole[-1][0][5:]}" if len(whole) > 1 else whole[0][0]
            qs.append(_q("T1", P, ["from_1", "to_1"], f"{len(whole)}일 모두 {hm(whole[0][1])}~{hm(whole[0][2])} (근무시간 거의 전체)",
                         f"{ds} {hm(whole[0][1])}~{hm(whole[0][2])}로 적혀 있습니다. 이 시간 내내 {work} 하시나요?",
                         [C("yes", "내내 함", "확인됨"), C("partial", "일부 시간만", "정정", "실제로 하는 시간대를 적어 주세요. 예: 09:00~11:00, 14:00~16:00 / 날마다 다르면 10/27 09~11; 10/28 14~16"), UNKNOWN],
                         (1, -len(mine)), original=f"{hm(whole[0][1])}~{hm(whole[0][2])}"))
        elif len(rows) >= 3 and len({(a, b) for _, a, b in rows}) == 1:
            qs.append(_q("T2", P, ["date_1"], f"{len(rows)}일 같은 시간 {hm(rows[0][1])}~{hm(rows[0][2])}",
                         f"{len(rows)}일 동안 매일 같은 시간({hm(rows[0][1])}~{hm(rows[0][2])})입니다. 날마다 같은 작업인가요?",
                         [C("yes", "매일 같음", "확인됨"), C("partial", "날마다 다름", "정정", "날짜별 시간대를 적어 주세요. 예: 10/27 09~11; 10/28 14~16"), UNKNOWN], (3, 0)))
        # ---- place and target: L1 (asked together with the block / equipment number when none is written)
        no_target = not P["targets"]
        moving = kind == "lifting"                     # a lift moves: its route (L5) says more than one place
        if pl["level"] <= 2 and not pl.get("whole") and not moving:
            ask_t = " 블록·설비 번호도 함께 알려 주세요." if no_target else ""
            tier = "extra" if (P["targets"] and equip) else "core"   # an equipment number already pins the place
            if pl["level"] == 2:
                sig = "장소가 BAY까지만 있음 (BAY 하나가 수백 m 길이)"         # F01 p389: no fixed size is claimed
                text = f"작업장소가 '{pl['text']}'로 BAY까지만 적혀 있습니다. BAY 안의 칼럼 범위(기둥 번호)를 알려 주시겠어요?{ask_t}"
                whole_c = C("whole", "BAY 전체를 오가며 함", "확인됨")
            else:
                sig = ("장소가 팀·부서 이름처럼 보임" if pl["org"] else "장소에 BAY·칼럼이 없음")
                text = f"작업장소가 '{pl['text'] or '(빈칸)'}'로 적혀 있습니다. 실제 작업 위치를 BAY·칼럼까지 알려 주시겠어요?{ask_t}"
                whole_c = C("whole", "정말 공장 전체", "확인됨")
            qs.append(_q("L1", P, ["location", "location_detail"], f"{sig}: '{pl['text']}'", text,
                         [C("place", "위치 입력", "정정", "예: 대조립21공장 3BAY 12-16 칼럼 E41P 블록 / 여러 곳이면 쉼표로"), whole_c, UNKNOWN],
                         (1, -len(mine)), original=pl["text"], tier=tier))
        elif no_target:
            qs.append(_q("D1", P, ["job", "location_detail"], "블록·설비 번호가 없음",
                         "어느 블록·설비에서 하는 작업인가요? 번호를 알려 주세요.",
                         [C("text", "번호 입력", "보강", "예: E41P 블록 / OH-21-03 크레인 / P-07 배관"), C("na", "특정 대상 없음", "해당없음"), UNKNOWN], (2, 0)))
        if moving and not re.search(r"→|경유|통로|->", pl["text"]):
            qs.append(_q("L5", P, ["location"], "이동 경로 없음", "블록이 출발해서 지나가는 BAY·통로와 도착 위치, 통과 예정 시각을 알려 주세요.",
                         [C("text", "경로 입력", "보강", "예: 3BAY 12-16 칼럼 → 3BAY 동측 통로 → 1BAY 반출장, 10:50 통과"), UNKNOWN], (1, 0)))
        if not pl["layer"] and (kind == "height" or (kind == "hot" and (re.search(r"(\d+(?:\.\d+)?)\s*m\b", jt) or p.get("hot_at_height", {}).get("value")))):
            qs.append(_q("L3", P, ["location_detail"], "높이·상하·내부 표시 없음", "블록 위(상부) / 옆·지상 / 아래(하부) / 안(내부) 중 어디서 하나요? 높이도 알려 주세요.",
                         [C("text", "위치 입력", "보강", "예: 상부 4.8m"), UNKNOWN], (2, 0)))
        # ---- required blanks (approver and day-of-work boxes are never asked: design 3-3, D1)
        for k, name, t, req in [(k, f["name"], f["type"], f["required"]) for k, f in p.items()]:
            if not req or t in ("check", "image") or _v(p, k) or k in ("location", "location_detail"):
                continue
            item = "B2" if k in PK.KINDS.get(kind, {}).get("required", []) else "B1"
            qs.append(_q(f"{item}.{k}", P, [k], f"'{name}' 빈칸", f"'{name}' 칸이 비어 있습니다. 값을 알려 주세요.",
                         [C("value", "값 입력", "정정", f"{name}" + (" (숫자)" if t in ("number", "count") else "")), C("na", "해당 없음", "해당없음"), UNKNOWN],
                         (2, 0)))
        if kind == "confined" and p.get("height_work", {}).get("value") and not _v(p, "work_height"):
            qs.append(_q("B2.work_height", P, ["height_work", "work_height"], "고소작업 체크, 작업높이 빈칸",
                         "고소작업에 체크했는데 작업높이가 없습니다. 몇 m인가요?", [C("value", "높이 입력", "정정", "m 단위 숫자"), UNKNOWN], (2, 0)))
        # ---- 병행여부 (C3 needs the other permits: 안전관리자 view)
        cv = P["concurrent"]
        if not cv:
            cand = f" croScan이 찾은 같은 시간 작업: {others()}." if mine else ""
            qs.append(_q("B3", P, ["concurrent"], "병행여부 빈칸",
                         f"병행여부가 비어 있습니다. 알고 있는 같은 시간·장소의 다른 작업이 있나요?{cand}",
                         [C("yes", "있음", "보강", "어떤 작업인지 적어 주세요"), C("no", "없음", "확인됨"), UNKNOWN], (3, -len(mine))))
        elif cv == "N" and any(x["level"] <= 2 for x in mine):
            qs.append(_q("C3", P, ["concurrent"], "병행여부 N, 겹치는 작업 있음",
                         f"병행작업 없음(N)으로 적었는데 같은 시간에 {others()} 작업이 있습니다. 알고 계셨나요?",
                         [C("unaware", "몰랐음", "보강"), C("aware", "알고 있음(조정됨)", "확인됨", "어떻게 조정했는지 적어 주세요"), C("na", "해당 없음(다른 장소·설비)", "해당없음", "다른 점을 적어 주세요")],
                         (3, 0), original="N"))
        # ---- 호선: empty is normal for plant equipment work -> rule estimate, not a question
        if not _v(p, "hull_no"):
            if equip:
                assumed.append({"permit_no": P["permit_no"], "item": "B4", "name": "호선/공사", "original": "",
                                "value": "호선 무관으로 추정 (설비·공용 작업)", "why": "작업내용·장소가 설비 작업이라 호선이 없는 것이 보통임"})
            else:
                qs.append(_q("B4", P, ["hull_no"], "호선/공사 빈칸", "호선/공사가 비어 있습니다. 특정 호선 작업이 아닌가요?",
                             [C("na", "호선 무관", "해당없음"), C("value", "입력 누락", "정정", "호선/공사 번호"), UNKNOWN], (4, 0), tier="extra"))
        # ---- the kind's main hazard and category (safety content of the permit itself)
        haz = _v(p, "hazards")
        need = HAZ_WORDS.get(kind, "")
        argon = kind == "confined" and p.get("argon", {}).get("value") and not re.search(r"아르곤|가스|산소", haz)
        if haz and need and (not re.search(need, haz) or argon):
            what = "아르곤(가스)·산소" if argon else {"confined": "질식·산소·가스", "hot": "화재·불티", "height": "추락·낙하",
                                                   "lifting": "낙하·협착·충돌", "loto": "감전·재가동"}[kind]
            qs.append(_q("C1", P, ["hazards"], f"유해위험요소에 {what} 언급 없음 ('{haz[:30]}')",
                         f"유해위험요소에 {what} 관련 내용이 없습니다. 이 위험은 어떻게 관리하나요?",
                         [C("text", "설명 입력", "보강", "예: 진입 전 아르곤 공급 차단, 산소측정 1시간마다"), C("na", "해당 없음", "해당없음"), UNKNOWN],
                         (4, 0), original=haz))
        hm_ = re.search(r"(\d+(?:\.\d+)?)\s*m\b", jt)
        tall = hm_ and float(hm_.group(1)) >= 2
        head = {"hot": "hot_at_height", "confined": "height_work"}.get(kind)
        if tall and head and not p.get(head, {}).get("value"):
            nm = p.get(head, {}).get("name", "고소")
            qs.append(_q("C2", P, [head], f"작업내용에 높이 {hm_.group(1)}m, '{nm}' 체크 없음",
                         f"작업내용에 높이 {hm_.group(1)}m가 있는데 '{nm}'에 체크가 없습니다. 높은 곳에서 하는 작업인가요?",
                         [C("yes", "예, 체크 필요", "보강"), C("na", "아니오(지상 작업)", "해당없음"), UNKNOWN], (4, 0), original=f"'{nm}' 체크 없음"))
        heads = [k for k, _ in PK.KINDS.get(kind, {}).get("heads", [])]
        if heads and not any(p.get(k, {}).get("value") for k in heads):
            qs.append(_q("C2h", P, heads, "추가정보 분류 체크가 하나도 없음",
                         "추가정보의 작업 분류(" + ", ".join(PK.ko(l) for _, l in PK.KINDS[kind]["heads"]) + ") 중 체크된 것이 없습니다. 어떤 작업인가요?",
                         [C("text", "분류 입력", "보강", "해당 분류를 적어 주세요"), UNKNOWN], (4, 0), original="분류 체크 없음"))
        # ---- shared resources: what links two permits later (research: transfer paths)
        crane_work = kind == "lifting" or (kind == "loto" and (p.get("crane_power", {}).get("value") or "크레인" in alltext))
        if crane_work and not P["cranes"] and not (no_target and pl["level"] <= 1):    # else L1 asks for the number already
            qs.append(_q("D2", P, ["job"], "크레인 번호 없음",
                         "인양에 쓰는 크레인 번호는 무엇인가요?" if kind == "lifting" else "수리하는 크레인 번호는 무엇인가요?",
                         [C("text", "크레인 번호", "보강", "예: OH-21-03"), UNKNOWN], (2, 0)))
        if kind == "loto":
            qs.append(_q("D4", P, ["job"], "정전 범위", "이 전원을 끊으면 함께 멈추는 설비(크레인·환기팬·조명 등)가 있나요? 복구·시험운전 예정 시각도 알려 주세요.",
                         [C("text", "설비·시각 입력", "보강", "예: 3BAY 조명 일부, 복구 14:30 시험운전 14:45"), C("none", "함께 멈추는 것 없음", "확인됨"), UNKNOWN], (1, 0), tier="extra"))
        if kind == "hot":
            qs.append(_q("D3", P, ["job"], "가스 사용", "용접·절단에 쓰는 가스(산소·LPG·아르곤 등)와 공급 방식(용기/배관)은요?",
                         [C("text", "가스·방식 입력", "보강", "예: 산소·LPG 용기, 아르곤 배관"), C("na", "가스 안 씀(전기 용접만)", "해당없음"), UNKNOWN], (1, 0), tier="extra"))
        # the ember check also after a lug cut with gas or plasma (LU15-FIRE p266: a hidden ember lights later)
        if kind == "hot" or (kind == "height" and _scope(P, {a["qid"]: a for a in answers or []}) in ("gas", "plasma")):
            qs.append(_q("T4", P, ["to_1"], "종료 후 잔불 (D4)", "작업 후 잔불 확인·화재감시는 몇 시까지 하나요?",
                         [C("time", "시각 입력", "보강", "HH:MM"), C("none", "바로 끝남", "확인됨"), UNKNOWN], (2, 0), tier="extra"))
        if kind == "confined":
            qs.append(_q("D5", P, ["job"], "진입 구획의 공급 계통", "들어가는 배관·구획에 가스나 공기를 넣는 계통은 무엇이고, 차단은 누가 확인하나요?",
                         [C("text", "계통·담당 입력", "보강", "예: 아르곤 퍼지 라인 V-12 차단, 배관2팀 반장 확인"), C("na", "공급 계통 없음", "해당없음"), UNKNOWN], (1, 0), tier="extra"))
        if kind in ("hot", "height", "lifting"):
            qs.append(_q("L6", P, ["location_detail"], "작업 중 통제 범위", "작업하는 동안 출입을 막는 범위는 어디까지인가요? (불티·낙하·인양 반경)",
                         [C("text", "범위 입력", "보강", "예: 하부 반경 5m, 3BAY 동측 통로"), UNKNOWN], (3, 0)))
        if kind == "lifting":
            qs.append(_q("T3", P, ["from_1", "to_1"], "인양 단계 시각", MOMENT_Q["lifting"],
                         [C("time", "시각 입력", "보강", "예: 시험인양 10:35, 주행 10:40, 안착 11:10"), UNKNOWN], (2, 0), tier="extra"))
        if re.search(r"(?:[A-Z]\d{2}[A-Z]?\s*,\s*){1,}[A-Z]\d{2}", jt):
            qs.append(_q("L4", P, ["job"], "작업내용에 블록 여러 개", "여러 블록을 동시에 하나요, 순서대로 하나요? 날짜별로 나눠 알려 주세요.",
                         [C("text", "순서·날짜 입력", "보강", "예: 10/14 B11·F31, 10/15 E11·E18"), UNKNOWN], (4, 0), tier="extra"))
        # ---- 안전관리자 view only: questions that exist because another permit overlaps this one
        top = min((x["level"] for x in mine), default=9)
        if top <= 2 and kind != "lifting":
            qs.append(_q("T3", P, ["from_1", "to_1"], f"{others()} 작업과 시간 겹침", MOMENT_Q.get(kind, "위험이 가장 큰 순간은 언제인가요?"),
                         [C("time", "시각 입력", "보강", "예: 10:40 / 여러 개면 쉼표로"), UNKNOWN], (1, -len(mine))))
        if pl["level"] == 3 and top == 2:
            qs.append(_q("L2", P, ["location"], f"칼럼 범위 '{pl['cols']}' 안의 실제 작업점", f"{pl['cols']} 중 실제로 작업하는 블록·위치는 어디인가요?",
                         [C("text", "작업점 입력", "보강", "예: E41P 블록 동측 측판"), UNKNOWN], (2, 0)))
        for x in mine:
            o = by_no[x["b"] if x["a"] == n else x["a"]]
            ks = {kind, o["kind"]}
            if ks == {"lifting", "loto"} and kind == "lifting" and not (P["cranes"] & o["cranes"]):
                qs.append(_q("X1", P, ["job"], f"{_who(o)} 크레인 수리와 시간 겹침",
                             f"인양에 쓰는 크레인 번호는 무엇인가요? 같은 시간에 {_who(o)}에서 크레인 정비가 있습니다.",
                             [C("text", "크레인 번호", "보강", "예: OH-21-03"), UNKNOWN], (1, 0), other=o))
            if ks == {"hot", "confined"} and kind == "hot":
                qs.append(_q("X2", P, ["job"], f"{_who(o)} 내부 진입과 시간 겹침",
                             f"용접·절단에 쓰는 가스(아르곤 등) 공급이 {_who(o)}의 진입 배관·구획과 이어져 있나요?",
                             [C("yes", "예, 이어져 있음", "보강"), C("no", "아니오", "확인됨"), UNKNOWN], (1, 0), other=o))
            if ks == {"confined", "lifting"} and kind == "lifting":
                qs.append(_q("X3", P, ["job"], f"{_who(o)} 내부 진입과 같은 시간",
                             f"인양 전에 블록 안 인원이 모두 나왔는지는 누가 확인하나요? ({_who(o)}에 내부 진입이 있습니다)",
                             [C("text", "확인자 입력", "보강", "이름·직책"), UNKNOWN], (2, 0), other=o))
            if kind == "hot" and o["kind"] in ("height", "lifting", "hot"):
                qs.append(_q("X4", P, ["job"], f"{_who(o)} 작업과 같은 시간",
                             f"절단하는 부재가 다른 발판·부재를 받치고 있나요? ({_who(o)} 작업과 시간이 겹칩니다)",
                             [C("yes", "예, 받치고 있음", "보강"), C("no", "아니오", "확인됨"), UNKNOWN], (1, 0), other=o))
            if ks == {"loto", "confined"} and kind == "loto":
                qs.append(_q("X5", P, ["job"], f"{_who(o)} 내부 진입과 같은 시간",
                             "차단하는 전원에 환기팬·조명이 물려 있나요?", [C("yes", "예", "보강"), C("no", "아니오", "확인됨"), UNKNOWN], (1, 0), other=o))
        firsts = [x for x in mine if x["level"] == 1]
        if firsts:
            who = ", ".join(f"{x['b_who'] if x['a'] == n else x['a_who']}({x['when'][11:]})" for x in firsts)
            qs.append(_q("X6", P, ["from_1", "to_1"], "즉시 조정 대상과 시간 겹침",
                         f"{who} 작업과 시간이 겹칩니다. 해당 반장과 협의한 변경 가능 시간대가 있나요?",
                         [C("text", "협의한 시간대 입력", "보강", "예: 13:30 이후 (상대 반장과 협의한 것)"), C("no", "협의한 시간대 없음", "확인됨"), UNKNOWN], (2, 0)))
    uniq = {}
    for q in qs:
        uniq.setdefault(q["qid"], q)
    open_ = [q for q in uniq.values() if q["qid"] not in done]
    open_.sort(key=lambda q: (q["prio"], q["page"]))
    return open_, perms, prs, assumed


# ---------------------------------------------------------------- records for page 2
CHECKING_LATER = re.compile(r"확인\s*(?:중|예정|후)|(?:물어|알아)\s*보(?:고|는)|문의\s*중|담당자?(?:에게|한테)")


def unknown_kind(v):
    """what a 「모름」 kept with words says (research 2.5 미확인 상태: not one blank): 미정 (not decided: '상황 봐서'),
    확인 예정 (being checked: '담당자에게 확인 중'), 불확실 ('아마 …'), else 모름. Its status stays 미확인."""
    v = v or ""
    if UNDECIDED.search(v):
        return "미정"
    if CHECKING_LATER.search(v):
        return "확인 예정"
    if HEDGE.search(v):
        return "불확실"
    return "모름"


def records(fields, answers, one=None):
    """One line per answered question, in the order answered. A closing free answer (qid FREE:n) is kept word for word;
    one = the permit number when the file holds one permit (a free answer then belongs to it). An answer taken back
    (C6 「서류가 맞음」) stays, marked 「철회」."""
    out, gone = [], withdrawn(answers)
    for a in answers or []:
        if a["qid"].startswith("FREE:"):
            out.append({"qid": a["qid"], "item": "FREE", "page": None, "permit_no": one, "who": "", "signal": "마지막 추가 전달",
                        "original": "", "question": CLOSING, "answer": "추가 전달", "value": a.get("value", ""), "status": "보강",
                        "source": "신청자 답변", "keys": []})
            continue
        q = a.get("q") or {}
        ch = next((c for c in q.get("choices", []) if c["id"] == a.get("choice")), {})
        extra = {"unknown_kind": unknown_kind(a.get("value", ""))} if a.get("choice") == "unknown" else {}
        if a["qid"] in gone:                         # taken back: the document is right (C6), kept on page 2 as such
            extra = {**extra, "withdrawn": True}
        out.append({**extra, "qid": a["qid"], "item": q.get("item", a["qid"].split(":")[0]), "page": q.get("page"), "permit_no": q.get("permit_no"),
                    "who": q.get("who", ""), "signal": q.get("signal", ""), "original": q.get("original", ""), "question": q.get("text", ""),
                    "answer": ch.get("label", a.get("choice", "")), "value": a.get("value", ""),
                    "status": "철회(서류가 맞음)" if a["qid"] in gone else ch.get("status", "미확인"),
                    "source": "신청자 답변" + (" (다른 질문에 함께 적은 말)" if a.get("by") else ""), "keys": q.get("keys", []),
                    "by": a.get("by", ""), "quote": a.get("quote", "")})
    return out


# typed answers that must carry a value croScan can read: (item, choice or None for any) -> what
READABLE = {("T0", "value"): "time", ("T1", "partial"): "time", ("T2", "partial"): "time", ("T5", "fix"): "time", ("T6", "retime"): "time",
            ("T6", "stage"): "time", ("L1", "place"): "place", ("L7", "place"): "place", ("D1", "text"): "id",
            ("LI1", "text"): "crane", ("HT1", None): "count", ("H1", None): "count", ("L3", "text"): "where",
            ("A3", "time"): "time", ("U1", "time"): "time", ("U1", "place"): "place",
            ("T7", "check"): "time", ("T4", "time"): "clock", ("LI1", "blocks"): "block", ("A4", "place"): "place",
            ("A5", "fix"): "clock"}
RANGE_COUNT = TWO_VALUES


def readable(what, v):
    """'' when croScan can read the value, otherwise what to ask again (one retry; the second time it is kept as typed
    and goes to the safety team as 미확인)."""
    if HEDGE.search(v):
        return "「아마」「것 같아요」처럼 확실하지 않은 말이 있습니다. 확실한 값을 적어 주시고, 모르면 「모름」을 눌러 주세요"
    if UNDECIDED.search(v):
        return "「상황 봐서」「알아서」처럼 정해지지 않은 말은 받을 수 없습니다. 정해진 내용을 적어 주시고, 아직 모르면 「모름」을 눌러 주세요"
    if not re.search(r"[가-힣]{2,}|\d|[A-Za-z]{2,}", v):
        return "무슨 뜻인지 알아듣지 못했습니다. 조금 더 적어 주세요 (모르면 「모름」)"
    if what == "time" and not time_ranges(v, amb=(found := [])) and not found:
        return "시간을 읽지 못했습니다. 시작~끝으로 적어 주세요 (예: 13:00~15:00, 오후 1시~3시)"
    if what == "place":
        pl = parse_place(v)
        if not (pl["bays"] or pl["cols"] or ids(v)):
            return "위치를 읽지 못했습니다. BAY·칼럼이나 블록·설비 번호로 적어 주세요 (예: 3BAY 12-14 칼럼 E41P)"
    if what == "id" and not ids(v):
        return "번호를 읽지 못했습니다 (예: E41P 블록, P-07 배관). 번호가 없으면 「특정 대상 없음」을 눌러 주세요"
    if what == "crane" and not (CRANE.search(v) or ids(v)):
        return "크레인 번호를 읽지 못했습니다 (예: OH-21-01)"
    if what == "clock":
        m, ambig, _ = clock_read(v)
        if ambig:
            return "오전·오후(또는 다음 날)를 알 수 없는 시각입니다. 함께 적어 주세요 (예: 오후 4시 30분, 16:30, 다음날 01:00)"
        if m is None:
            return "시각을 읽지 못했습니다 (예: 16:00, 오후 4시)"
    if what == "block" and not ({x for x in ids(v) if not CRANE.fullmatch(x)} or count_in(v) is not None):
        return "블록 번호나 개수를 읽지 못했습니다 (예: E21P 블록 1개)"
    if what == "count":
        if RANGE_COUNT.search(v):
            return "개수가 두 값입니다. 하나로 적어 주세요 (예: 3개). 모르면 「모름」을 눌러 주세요"
        if count_in(v) is None and not re.fullmatch(r"\s*\d{1,3}\s*", v):
            return "개수를 읽지 못했습니다 (예: 3개)"
    if what == "where" and not (height_in(v) is not None or parse_place(v)["layer"] or re.search(r"옆|지상|바닥", v)):
        return "위치나 높이를 읽지 못했습니다 (예: 블록 상부 4.8m)"
    return ""


def doc_conflicts(P, ans):
    """the answers that say other than the document of the same permit -> [(item, keys, document's words, answer's
    words)]: a time outside the window written, a BAY not the one written, a height more than 1m from the one written"""
    p, pid, out = P["p"], P["permit_no"], []
    a = ans.get(f"T1:{pid}")
    req = P.get("windows_req") or _windows(p)
    if a and a.get("choice") == "partial" and req:
        # each day against that day's own requested window (N2 MT15, N5 MT13: dates are compared one by one, the
        # first start and last end of all days are not merged); a part outside is kept and asked once, never cut
        get = lambda item: ans.get(f"{item}:{pid}")
        said_ = _parse_windows(a.get("read") or a.get("value") or "", sorted(req), _force(get, "T1"), [])     # as A1·A2 settled it
        off = [(d, x, y) for d, ws in said_.items() for x, y in ws
               if not any(lo <= x and y <= hi for lo, hi in req.get(d, []))]
        if off:
            d = off[0][0]
            doc = ", ".join(f"{hm(x)}~{hm(y)}" for x, y in req.get(d, [])) or "이 날 시간 없음"
            out.append(("T1", ["from_1", "to_1"], f"{d[5:]} {doc}", (a.get("value") or "").strip()[:30]))
    # an earlier answer about the work's scope that the document now says otherwise of (the document was edited after
    # the answer; MT17 「확인 후 관련 조건 변경」, p247): asked once which is right, both kept
    item = SCOPE_Q.get(P["kind"])
    a = ans.get(f"{item}:{pid}") if item else None
    if a and a.get("choice") not in (None, "unknown", "text", "full", "head", "na"):
        doc = _scope({**P, "text": doc_text(P)}, {})
        if doc and doc != a["choice"] and not (P["kind"] == "confined" and doc == "partial" and a["choice"] == "inspect"):
            lab = lambda c: next((x["label"] for x in ((a.get("q") or {}).get("choices") or []) if x["id"] == c), c)
            out.append((item, ["job"], f"작업내용: {SCOPE_WORD.get(doc, doc)}", lab(a["choice"])))
    a = ans.get(f"L1:{pid}")
    if a and a.get("choice") == "place":
        doc_b = parse_place(" ".join(_v(p, k) for k in ("location", "location_detail")))["bays"]
        said_b = parse_place(a.get("value") or "")["bays"]
        if doc_b and said_b and not (doc_b & said_b):
            out.append(("L1", ["location"], _v(p, "location")[:30], (a.get("value") or "").strip()[:30]))
    a = ans.get(f"L3:{pid}")
    if a and a.get("choice") == "text":
        doc_h, said_h = _num(_v(p, "work_height")), height_in(a.get("value") or "")
        if doc_h is not None and said_h is not None and abs(doc_h - said_h) >= 1:
            out.append(("L3", ["work_height"], f"{doc_h:g}m", f"{said_h:g}m"))
    return out


def check_value(fields, answer):
    """Check a typed answer before it is used: a form field's type (B1/B2), or a value croScan must be able to read
    (a time, a place, a number) without guessing. Returns what to ask again, or ''."""
    item, choice, v = answer["qid"].split(":")[0], answer.get("choice"), (answer.get("read") or answer.get("value") or "").strip()
    if item.startswith(("B1.", "B2.")) and choice == "value":
        key = item.split(".", 1)[1]
        f0 = next((f for f in fields.values() if f.get("key") == key), {})
        t = f0.get("type", "text")
        if re.sub(r"\s", "", v) == re.sub(r"\s", "", f0.get("name", "")):        # the field's own name is not its value
            return f"칸 이름이 아니라 실제 {f0.get('name', '값')}을(를) 적어 주세요"
        return "" if valid(t, v) else f"형식이 맞지 않습니다 ({t})"
    if not v or choice == "unknown" or item.startswith(("C5.", "C6.", "A1.", "A2.", "FREE")):
        return ""
    if item == "LO3" and choice == "text":                 # 원자 슬롯: 차단·복구 are two facts and both are needed
        miss = need_catalog.atoms(item, choice, v)["required_missing"]
        if miss:
            return f"{'과 '.join(miss)}을 함께 알려 주세요"
    base = item.split(".")[0] if item.startswith(("A3.", "A4.", "A5.", "U1.", "T0.")) else item
    # every typed answer must say something decided; the ones that fill a time, place or number must be readable
    return readable(READABLE.get((base, choice)) or READABLE.get((base, None)), v)


def summary(fields, answers, manager=False):
    """Everything the chat and page 2 need, recomputed from the permit and all answers so far."""
    open_, perms, prs, assumed = questions(fields, answers, manager)
    deferred = [x for x in assumed if x.get("item") == "DEFER"]
    assumed = [x for x in assumed if x.get("item") != "DEFER"]
    prs = prs if manager else []
    stale_now = sorted({q for P in perms for q in P.get("stale", ())} | {f"T7:{P['permit_no']}" for P in perms if P.get("t7_stale")})
    answers = drop_stale(perms, answers)
    recs = records(fields, answers, perms[0]["permit_no"] if len(perms) == 1 else None)
    pending = [r for r in recs if r["status"] == "미확인"]
    eff = []
    for P in perms:
        pl = P["place"]
        eff.append({"no": P["no"], "permit_no": P["permit_no"], "who": _who(P), "label": P["label"],
                    "windows": {d: [f"{hm(a)}~{hm(b)}" for a, b in _span(P, d)] for d, _ in sorted(P["windows"].items())},
                    # the work's own windows, not stretched to the residual end (the pre-submit card shows that end apart)
                    "windows_work": {d: [f"{hm(a)}~{hm(b)}" for a, b in sorted(ws)] for d, ws in sorted(P["windows"].items())},
                    "windows_src": P["windows_src"],
                    "residual": hm(P["residual"][max(P["residual"])]) if P.get("residual") else "",
                    "residual_at": {d: hm(x) for d, x in sorted((P.get("residual") or {}).items())},
                    "moments": [hm(m) for m in P["moments"]],
                    "place": {"text": pl["text"], "level": f"L{pl['level']}", "factory": pl["factory"] or "", "bays": sorted(pl["bays"]),
                              "cols": pl["cols"], "layer": pl["layer"], "whole": pl.get("whole", False)},
                    "targets": sorted(P["targets"]), "cranes": sorted(P["cranes"]), "notes": P["notes"], "fit": P.get("fit"),
                    "count": P.get("count"), "height": P.get("height"),
                    # for the matching (2026-10-31): the requested windows as written, a stage kept apart (a lift's
                    # moving part, the part a T6 「특정 단계만」 answer named), the whole work's end, the meaning
                    "windows_req": {d: [f"{hm(a)}~{hm(b)}" for a, b in sorted(ws)] for d, ws in sorted(P.get("windows_req", {}).items())},
                    "windows_stage": {k: {d: [f"{hm(a)}~{hm(b)}" for a, b in ws] for d, ws in sorted(st.items())}
                                      for k, st in sorted(P.get("windows_stage", {}).items())},
                    "full_end": {d: hm(x) for d, x in sorted((P.get("full_end") or {}).items())}, "time_meaning": P.get("time_meaning"),
                    "facts": P.get("facts", {}),
                    # field values whose proof is due on the day of work (현장 안전조치 etc.): never asked before
                    # (NOT_YET_DUE, research 2.5·MT14), listed so the day's check knows they are still open
                    "not_yet_due": sorted(k for k in P["p"] if k in DAY_OF_VALUES and not _v(P["p"], k))})
    dates = sorted({d for P in perms for d in P["windows"]})
    kind = perms[0]["kind"] if len(perms) == 1 else None
    found = {a["qid"]: found_in(a.get("value", ""), dates, kind) for a in answers or [] if a["qid"].startswith("FREE:")}
    return {"stale_answers": stale_now, "questions": open_, "records": recs, "effective": eff, "pairs": prs, "pending": pending, "manager": manager, "assumed": assumed,
            "deferred": deferred, "closing": CLOSING, "free_found": found,
            # 현장 정정 D02: only the Y/N is known to be set at the PTW scan; when and by whom 허가구분 is set is not
            # known, and 허가구분 alone does not say whether there is a morning 대면허가 (one text: addendum labels it by prefix)
            "fixed_pending": ["허가구분(전산허가/안전현장허가): 언제·누가 정하는지 미확인 · "
                              "2중점검 Y/N: PTW 스캔 때 정해짐(판정 기준·스캔 주체는 미확인). Y면 실제 작업일마다 아침 대면허가, N이면 아침 대면허가 대상 아님 · "
                              "croScan은 둘 다 판정하지 않고 적힌 값만 옮김"]}


def found_in(text, dates=(), kind=None):
    """What croScan read from a free answer, as short lines for the chat ('반영했습니다: …'). Only plain statements;
    a condition ('다른 작업 없으면') or an unclear phrase is not turned into a value."""
    out, amb = [], []
    w = work_windows(text, dates, kind, None, amb) if dates else {}
    if amb:
        out.append("시간 " + ", ".join(f"'{x['raw']}'" for x in amb) + "은 뜻이 두 가지라 다시 여쭙니다")
    elif w:
        out.append("시간 " + ", ".join(f"{hm(a)}~{hm(b)}" for a, b in sorted({x for ws in w.values() for x in ws})))
    for cl in CLAUSE.split(text or ""):                 # '오전 작업은 안 합니다': understood, kept as it is
        if NO_WORK_TIME.search(cl) and not re.search(r"\d", cl):
            out.append(f"'{cl.strip()}'은 일하지 않는 시간으로 그대로 적어 둠")
    if HEDGE.search(text or ""):
        out.append("'아마·것 같아요'처럼 확실하지 않은 말은 확정하지 않았습니다")
    own = own_text(text, kind)                 # place, IDs, count and height only from clauses about this work
    pl = parse_place(own)
    if pl["bays"] or pl["cols"]:
        out.append("위치 " + " ".join(x for x in (pl["factory"] and f"{pl['factory']}공장", pl["bays"] and "/".join(sorted(pl["bays"])) + "BAY", pl["cols"]) if x))
    if got := sorted(ids(own)):
        out.append("번호 " + ", ".join(got))
    if (n := count_in(own)) is not None:
        out.append(f"개수 {n}")
    if (h := height_in(own)) is not None:
        out.append(f"높이 {h:g}m")
    g = said(text, r"가스|산소|LPG|프로판|아세틸렌|아르곤|질소|CO2")
    if g is not None:
        out.append("가스 " + ("·".join(dict.fromkeys(re.findall(r"산소|LPG|프로판|아세틸렌|아르곤|질소|CO2", text))) or "사용") if g else "가스 안 씀")
    c = said(text, CONC)
    if c is not None:
        out.append("알고 있는 병행작업 있음" if c else "병행작업 없음")
    if (ow := other_work(text, kind)) and not c:
        out.append("다른 작업 언급 " + "·".join(sorted(ow)))
    i = said(text, RX["li_inside"])
    if i is not None:
        out.append("블록 안·위 작업 있음" if i else "블록 안·위 작업 없음")
    for rx, name in ((RX["li_tandem"], "공동인양"), (RX["li_turn"], "반전"), (RX["lo_access"], "거더·상부 접근")):
        v = said(text, rx)
        if v is not None:
            out.append(name + ("" if v else " 없음"))
    return out


# ---------------------------------------------------------------- one long answer, several questions (QA #39)
# A typed answer often says more than its question asked ('장소는 3BAY 12-14입니다. 실제 작업은 기존 9시가 아니라 13시부터
# 15시까지이고 … 작업자 4명과 감시인 1명이 들어갑니다'). What it plainly says about a few things croScan can read without
# guessing is taken as the answer to the open question about it, with the clause it came from: the place (L1·L7), the
# working time (T0 empty row, T1 actual window), the number of workers (B1.workers) and a watcher count, which has no field
# (별지). Not taken: a condition, a hedge, another team's work, a denied value ('9시가 아니라' keeps only what follows).
SPILL_SPLIT = re.compile(r"(?<!\d)[.。!?\n;]|\.(?!\d)|,|\s(?:그리고|또)\s|(?<=[이하])(?:고|며)\s|지만\s")
WORKERS = re.compile(r"(?:작업자|작업\s*인원|인원|근로자|작업원)\s*(?:은|는|이|가|도)?\s*(?:총\s*)?(\d{1,3})\s*명")
WATCHER = re.compile(r"((?:화재\s*)?감시(?:인|자|원)|신호수|입회자)\s*(?:은|는|이|가|도)?\s*(\d{1,2})\s*명")


SENTENCE = re.compile(r"(?<!\d)[.。!?\n;]|\.(?!\d)")
# what a clause asserts: 'X가 아니라 Y' → Y; a clause that denies ('…작업하지 않습니다', '4명이 아닙니다') asserts nothing
SAID_NOT = re.compile(r"아닙|아님|아니에|아니야|않|안\s*(?:함|합|해|하)|없(?:음|습|어|다)")


def _asserted(cl):
    part = re.split(r"아니라|아니고|대신", cl)[-1]
    return "" if SAID_NOT.search(part) else part


def _plain(cl, kind):
    return cl.strip() and not (COND.search(cl) or HEDGE.search(cl) or re.search(CONC, cl) or other_work(cl, kind))


def _clauses(v, kind):
    """The plain clauses of an answer: a sentence with a condition or a hedge anywhere in it ('비가 오면, 작업자 4명 …') is
    left out whole (the condition holds over its commas); another team's or another kind of work is left out per clause."""
    out = []
    for sent in SENTENCE.split(v or ""):
        if not sent.strip() or COND.search(sent) or re.search(r"면\s*[,，]", sent) or HEDGE.search(sent):     # '오면,' too
            continue
        out += [c.strip() for c in SPILL_SPLIT.split(sent) if c and _plain(c, kind)]
    return out


def workers_in(cl):
    """'작업자 4명' → 4; '작업자 4명이 아니라 6명' → 6; '작업자는 4명이 아닙니다' → None."""
    m = WORKERS.search(cl or "")
    if not m:
        return None
    tail = cl[m.end():]
    if re.search(r"아니라|아니고", tail):
        n = re.search(r"(\d{1,3})\s*명", re.split(r"아니라|아니고", tail)[-1])
        return int(n.group(1)) if n and not SAID_NOT.search(re.split(r"아니라|아니고", tail)[-1]) else None
    return None if SAID_NOT.search(tail[:14]) else int(m.group(1))


# a time said in the same clause as the place ('오후 1시부터 3시까지 3BAY 12~14칼럼'): it needs 시 · a colon · 오전/오후, so
# a column span (12-14) is never taken for one
_HM = r"(?:오전|오후)?\s*\d{1,2}(?:\s*:\s*\d{2}|\s*시(?:\s*\d{1,2}\s*분|\s*반)?)"
TIME_IN_PLACE = re.compile(rf"(?:{_HM}|(?:오전|오후)\s*\d{{1,2}}|\d{{1,2}})\s*(?:부터|~|-|–|에서)\s*{_HM}\s*(?:까지|사이)?(?:\s*(?:에|동안))?|{_HM}\s*(?:부터|까지|에)")


def _place_value(cl):
    """'장소는 3BAY 12–14입니다' → '3BAY 12-14 칼럼': the place words without the sentence around them (nor a time said
    in the same clause, nor a 「…요」 ending)."""
    cl = re.sub(r"\s+", " ", TIME_IN_PLACE.sub(" ", cl)).strip(" ,")
    cl = re.sub(r"^(?:(?:네|음|아|어|그러니까|말씀드리면|그게|저기)(?=[\s,.]|$)\s*[,.]?\s*)+", "", cl)       # a spoken lead-in
    pl = parse_place(cl)
    t = re.sub(r"^\s*(?:작업\s*)?(?:장소|위치)\s*(?:는|은|가|이)?\s*", "", pl["text"])
    t = re.sub(r"\s*(?:입니다|이에요|예요|이요|이고|이며|에서\s*(?:합니다|해요|작업|함).*|임)\s*$", "", t).strip(" .")
    t = re.sub(r"(?<=[가-힣A-Za-z0-9])요$", "", t).strip(" .")
    # 「…블록 내부에서 용접해」: the work said after the place is not the place (NL eval 2026-10-31)
    t = re.sub(r"\s*에서\s+[가-힣]+(?:해|해요|합니다|함|한다|하고|할|했|하는)\S*.*$", "", t).strip(" .,")
    if re.search(r"BAY\s*\d{1,2}\s*-\s*\d{1,2}\s*$", t, re.I):
        t += " 칼럼"
    return t


def _time_value(cl):
    """The window a clause gives as hh:mm~hh:mm ('기존 9시가 아니라 13시부터 15시까지' → '13:00~15:00'), or ''."""
    day = (DATE_MD.search(PLACE_SPAN.sub(" ", cl)) or [""])[0]
    cl = _asserted(cl)                                        # 'X가 아니라 Y': Y is meant; a denied time is none
    cl = PLACE_SPAN.sub(" ", cl)                              # '3BAY 12-14' is a place, never a time
    if not re.search(r"\d\s*시|\d:\d", cl):
        return ""
    rs = time_ranges(cl, amb=(amb := []))
    if amb or len(rs) != 1:
        return ""
    a, b = rs[0]
    rel = "" if day else (REL_DAY.search(cl) or [""])[0]     # '다음 날 00:00~02:00' keeps its day through the reading
    return f"{day or rel} {hm(a)}~{hm(b % (24 * 60))}".strip()


LUG, LUG_NONE = re.compile(r"러그"), re.compile(r"없|않|안\s*(?:떼|자르|잘라|절단|해|합|함)")
LUG_METHOD = (("mech", re.compile(r"그라인더|그라인딩|기계\s*절단|톱")), ("plasma", re.compile(r"플라즈마")),
              ("gas", re.compile(r"가스\s*절단|산소|LPG|용단|토치")))
LUG_DOWN = re.compile(r"로프|체인\s*블록|달아\s*내|내려|내리|크레인으로\s*내")


def interpret(fields, answers, src):
    """(answers to other open questions that the typed answer src also gives: [{qid, choice, value, q, by, quote}],
    src's own value read from it, or ''). Each derived answer is checked like a typed answer (check_value); a question
    already answered is never answered again. 'read' is given only when the answer said more than its own question."""
    v = (src.get("value") or "").strip()
    item = src["qid"].split(":")[0]
    # an answer about another team's work (병행작업, work inside a block to be lifted) says nothing of this work's own
    if (not v or src.get("choice") == "unknown" or src["qid"].startswith(("C5.", "A1.", "A2.")) or len(v) < 8
            or item in ABOUT_OTHERS or item == "LI2" or (item.startswith("U1.") and src.get("choice") == "other")):
        return [], ""
    before = [a for a in answers or [] if a["qid"] != src["qid"]]
    open_, perms, _, _ = questions(fields, before)
    if src["qid"].startswith("FREE:"):                       # a free answer: read for the one permit of the file
        if len(perms) != 1:
            return [], ""
        pid = perms[0]["permit_no"]
    else:
        pid = src["qid"].split(":")[1].split(">")[0]
    P = next((x for x in perms if x["permit_no"] == pid), None)
    if not P:
        return [], ""
    kind = P["kind"]
    done = {a["qid"] for a in answers or []}
    clauses = _clauses(v, kind)
    places = [c for c in clauses if (a := _asserted(c)) and parse_place(a)["bays"] and (parse_place(a)["cols"] or ids(a))]
    out, used = [], set()

    def give(q, choice, value, quote):
        a = {"qid": q["qid"], "choice": choice, "value": value, "q": q, "by": src["qid"], "quote": quote}
        if not check_value(fields, a):
            out.append(a)
            used.add(q["item"].split(".")[0])
    for q in open_:
        if q["permit_no"] != pid or q["qid"] in done or q["qid"] == src["qid"]:
            continue
        it, ids_ = q["item"], {c["id"] for c in q["choices"]}
        if it in ("L1", "L7") and "place" in ids_ and "job" not in [k.split(".", 1)[1] for k in q["keys"]]:
            if places:
                give(q, "place", _place_value(_asserted(places[0])), places[0])
        elif (it.startswith("T0.") and "value" in ids_) or (it == "T1" and "partial" in ids_):
            got = [(c, t) for c in clauses if (t := _time_value(c))]
            if len(got) == 1:                                    # two windows in one answer: not split here, asked
                give(q, "value" if it.startswith("T0.") else "partial", got[0][1], got[0][0])
        elif it in ("B1.workers", "B2.workers") and "value" in ids_:
            m = next(((c, n) for c in clauses if (n := workers_in(c)) is not None), None)
            if m:
                give(q, "value", str(m[1]), m[0])
        elif it == "HT1":
            no = next((c for c in clauses if LUG.search(c) and LUG_NONE.search(c)), None)
            if no and "na" in ids_:
                give(q, "na", "", no)
            elif not no:
                m = next(((c, ch) for c in clauses if LUG.search(c) or re.search(r"절단|자르|떼", c)
                          for ch, rx in LUG_METHOD if ch in ids_ and rx.search(c)), None)
                if m:
                    n = count_in(m[0])
                    ask = next(x for x in q["choices"] if x["id"] == m[1]).get("ask")
                    if n is not None or not ask:                 # a count asked for and not said: the question stays
                        give(q, m[1], f"{n}개" if n is not None else "", m[0])
        elif it == "HT2" and "text" in ids_:
            m = next((c for c in clauses if LUG_DOWN.search(c) and (LUG.search(c) or re.search(r"자른|떼어\s*낸|절단한", c))), None)
            if m:
                give(q, "text", (_asserted(m) or m).strip(), m)
    # a watcher has no field of its own: kept for the 별지 with the clause it came from (never added to 작업인원)
    if f"W1:{pid}" not in done:
        m = next(((c, x) for c in clauses if (x := WATCHER.search(c)) and not SAID_NOT.search(c[x.end():x.end() + 14])), None)
        if m:
            name = re.sub(r"\s", "", m[1].group(1))
            q = {"qid": f"W1:{pid}", "item": "W1", "page": P["no"], "permit_no": pid, "who": _who(P), "keys": [],
                 "signal": "답변에 함께 적은 인원", "text": "(답변에서 함께 읽음) 감시·입회 인원",
                 "choices": [C("text", "인원", "보강")], "original": ""}
            out.append({"qid": q["qid"], "choice": "text", "value": f"{name} {m[1].group(2)}명", "q": q, "by": src["qid"], "quote": m[0]})
    # the source's own question: what of the long answer is its value ('read'; the words stay as typed on page 2)
    it, read = src["qid"].split(":")[0], ""
    if (it in ("L1", "L7") or it.startswith("U1.")) and src.get("choice") == "place":
        read = _place_value(_asserted(places[0])) if places else ""
    elif (it.startswith("T0.") and src.get("choice") == "value") or (it in ("T1", "T6") and src.get("choice") in ("partial", "retime", "stage")):
        got = [t for c in clauses if (t := _time_value(c))]
        read = got[0] if len(got) == 1 else ""
    elif it in ("B1.workers", "B2.workers"):
        read = own_count(v, kind)
    return out, (read if read and read != v else "")


def own_count(v, kind=None):
    """작업인원 read from a typed answer to its own question ('작업자 4명입니다. 장소는 …' → '4'), or ''."""
    n = next((n for c in _clauses(v, kind) if (n := workers_in(c)) is not None), None)
    return str(n) if n is not None else ""
