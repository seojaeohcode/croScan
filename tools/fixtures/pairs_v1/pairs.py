"""쌍작업 위험탐지: every pair of one work day's documents (일상×비일상, 비일상×비일상), judged by rules only.

The researcher's six steps (조사자료 6절) are followed as they are:
  1. two different works            → one row per document, a document never pairs with itself
  2. time overlap or residual risk  → the windows of the risky phase (the move of a lift, a scheduled crane step);
                                      after a work ends its residual risk (embers, vapour, gas, people still inside)
                                      lasts until someone confirms it is gone, so any later work the same day is
                                      kept as 「확인 필요」 — there is no time after which it is assumed gone
  3. the path that joins them       → a rule (pair_rules.json): fire, falling, load path, shared crane/power, gas …
  4. people / functions exposed     → the rule's cause side and exposed side, from what each document says
  5. cause → exposure → accident    → the rule's chain, filled with the two works, worded as what *can* happen
  6. unknown stays unknown          → no time, no place, no head count: 노출 1 (확인 필요), never 'safe'
Being in the same BAY, or even the same column address, is not a confirmed path: a path is confirmed by the same
block, a stated route, the same equipment, or a stated above/below relation; a shared address alone is 노출 2.

Priority: a forbidden combination (법·멘토: 도장×화기, 상하 동시, 인양물 아래, 정비 중 사용 …) confirmed by the
documents (노출 3) is 1순위; otherwise 강도 S × 노출 E: 6 and more 2순위, 3 to 5 3순위, below 3 not raised.
"""
import json
import re
from functools import lru_cache
from pathlib import Path

from . import safety

RULES_PATH = Path(__file__).with_name("pair_rules.json")
FIRE_REACH_M = 11          # 안전보건규칙 제241조의2: 화재감시자 반경 11m


@lru_cache(maxsize=1)
def rules():
    R = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    R["by_id"] = {r["id"]: r for r in R["rules"]}
    return R


HM = re.compile(r"([01]\d|2[0-3]):[0-5]\d")


def _m(hm):
    h, m = map(int, hm.split(":"))
    return h * 60 + m


def _hm(m):
    return f"{(m // 60) % 24:02d}:{m % 60:02d}" + ("(+1)" if m >= 1440 else "")


def _win_m(w):
    a, b = _m(w["start"]), _m(w["end"])
    return (a, b + 1440) if w.get("next_day") or b <= a else (a, b)


# ---------------------------------------------------------------- what each work is (from what its document says)
DASH = str.maketrans({"‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "－": "-"})
SPARK = re.compile(r"용접|용단|가우징|절단|그라인더|그라인딩|사상|토치|브레이징")
SPARK_TOOL = re.compile(r"용접기|그라인더|토치|절단기|가우징|플라즈마")
NOT_ACTION = re.compile(r"확인|여부|점검|검사|탐상|측정|판독|금지|표지|준비|계획|없음|미사용|제외|보고|기록")
SOLVENT = re.compile(r"유기용제|희석제|시너|신너|세정제|솔벤트|용제형|인화성")
PAINT_JOB = re.compile(r"도장|세정|탈지|프라이머|코팅")
NOT_FLAM = re.compile(r"수성|불연|무용제|비인화")
NEGATED = re.compile(r"미사용|사용 안|사용하지|없음|제외|금지")
UPKEEP = re.compile(r"점검|정비|정리|보관|수리|교체|판독")
SYSTEM_ID = re.compile(r"\b[A-Z]{1,3}-\d{1,3}\b(?![-\d])")
CRANE_ID = re.compile(r"OH-\d+-\d+")
PANEL_ID = re.compile(r"(?:MCC|DB|PNL|LP|PP)-\d+")
BLOCK_ID = re.compile(r"\b[A-Z]\d{2}[A-Z]\b")
SEPARATE = re.compile(r"절단|해체|제거|분리|러그")
PRESSURE = re.compile(r"압력시험|압력 시험|가압|수압|기밀시험|에어 ?테스트|리크 ?테스트")
RADIATION = re.compile(r"방사선|선원|이리듐|감마선|RT 촬영")
VEHICLE = re.compile(r"지게차|운반차|트럭|카고")
MEWP = re.compile(r"고소작업대|MEWP|시저리프트|붐리프트")
OFF_FLOOR = re.compile(r"사무동|사무실|검사실|회의실|공장 밖")


def _tokens(value):
    """A field cut into short phrases: '크레인·체인블록으로 부재 취부 / 가용접·치수 확인' → each part on its own."""
    return [t.strip() for t in re.split(r"[/,;·]|\s및\s", value or "") if t.strip()]


# one phrase cut into its acts (Codex A8): a check or a no qualifies the act it is written with, not the whole phrase.
# '가용접 후 치수 확인' → '가용접' | '치수 확인'; '절단 없이 볼트 해체' → '절단 없이' | '볼트 해체' (the no stays with its act)
ACT_SPLIT = re.compile(r"\s*(?:→|->|=>|\+|&)\s*|(?<=[가-힣])\s*(?:하고|한\s*(?:후|뒤|다음)|후|뒤|다음|이후)\s+|\s+(?:그리고|또는|이후)\s+"
                       r"|(?<=없이|않고|말고|대신)\s+")


ACT_NO = re.compile(r"없이|않고|말고|대신|않음|안\s*함|하지\s*않")      # a no written with the act itself


def _acts(t):
    return [a.strip() for a in ACT_SPLIT.split(t) if a and a.strip()]


def _heights(text):
    """(lowest, highest) m from '지상 ~ 블록 상부 3.0m', '최고 4.8m', '4.5m', or (None, None)."""
    hs = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)\s*m\b", text or "")]
    if not hs:
        return None, None
    low = 0.0 if re.search(r"지상|최고|~", text) else min(hs)
    return low, max(hs)


def profile(d):
    """Tags with the field and words they come from: {tag: [(field, value), …]}, plus ids, heights, place and time."""
    tags, ids = {}, {"crane_use": set(), "crane_loto": set(), "power_use": set(), "power_loto": set(), "blocks": set(), "systems": set()}

    def tag(t, field, value):
        if (field, value) not in tags.setdefault(t, []):
            tags[t].append((field, value))

    if d["type"] == "permit":
        checks = [v["name"] for v in d["_fields"].values() if v["type"] == "check" and v["value"]]
        rec = {r["item"]: r.get("value") or "" for r in d["_records"]}
        fields = [("작업명", d["title"]), ("작업 상세", d["detail"]), ("유해위험요소", d["hazards"]), ("위치(답변 반영)", d["place"]),
                  ("이동 경로(답변)", d["route"])] + [(f"답변 {k}", v) for k, v in rec.items() if v]

        if d["kind"] == "hot":
            tag("SPARK", "허가서 종류", "화기작업 허가서")
        for c in checks:
            if re.search(r"용접|용단|가우징", c):
                tag("SPARK", "체크 항목", c)
        if d["kind"] == "confined" or "밀폐구역출입" in checks:
            tag("CONFINED", "허가서 종류" if d["kind"] == "confined" else "체크 항목", "밀폐공간 허가서" if d["kind"] == "confined" else "밀폐구역출입")
        if d["kind"] == "lifting":
            tag("LIFT", "허가서 종류", "중량물인양 허가서")
        if "고소작업대" in checks:
            tag("MEWP", "체크 항목", "고소작업대")
        if "아르곤가스 사용" in checks:
            tag("INERT", "체크 항목", "아르곤가스 사용")
        lows, highs = _heights(" ".join([rec.get("L3", ""), d["hazards"], d["detail"]]))
        title = d["title"]
    else:
        it = {i["label"]: i["value"] for i in d["_items"]}
        steps = [(k, v) for k, v in it.items() if re.fullmatch(r"\d+단계", k)]
        fields = [("작업명", it.get("작업명", "")), ("작업장비", it.get("작업장비", "")), ("사용물질", it.get("사용물질", ""))] + steps
        upkeep = UPKEEP.search(it.get("작업명", "")) and not SPARK.search(re.sub(r"용접기|용접부", "", it.get("작업명", "")))
        if not upkeep and any(SPARK_TOOL.search(t) and not NEGATED.search(t) for t in _tokens(it.get("작업장비", ""))):
            tag("SPARK", "작업장비", it.get("작업장비", ""))
        lows, highs = _heights(it.get("작업높이", ""))
        hv = it.get("작업높이", "")
        title = it.get("작업명", "") or d["title"]
    fields = [(f, (v or "").translate(DASH)) for f, v in fields if v]
    # one extractor for both kinds of document: an action phrase, not a check ('화기작업 여부 확인', '용접부 검사')
    for f, v in fields:
        for t in _tokens(v):
            # each act on its own: '가용접 후 치수 확인' keeps 가용접 (화기); '용접부 검사만 실시', '절단 없음' are no act
            for a in _acts(t):
                act = not NOT_ACTION.search(a) and not NEGATED.search(a) and not ACT_NO.search(a)
                # '용접부'·'용접기' name a thing, not the act: '용접부 그라인딩' is still grinding
                if act and SPARK.search(re.sub(r"용접부|용접기", "", a)) and f not in ("유해위험요소", "위치(답변 반영)", "이동 경로(답변)"):
                    tag("SPARK", f, v)
                # flammability is judged per phrase: '수성 도료, 유기용제 세정제' still has a solvent
                if act and (SOLVENT.search(a) or (PAINT_JOB.search(a) and f in ("작업명", "작업 상세"))) and not NOT_FLAM.search(a):
                    tag("SOLVENT", f, v)
                if act and SEPARATE.search(a) and f in ("작업명", "작업 상세") + tuple(k for k, _ in fields if k.endswith("단계")):
                    tag("SEP", f, v)
                if act and PRESSURE.search(a):
                    tag("PRESSURE", f, v)
                if act and RADIATION.search(a):
                    tag("RADIATION", f, v)
                if act and VEHICLE.search(a) and f in ("작업명", "작업장비") + tuple(k for k, _ in fields if k.endswith("단계")):
                    tag("VEHICLE", f, v)
            if MEWP.search(t) and f != "유해위험요소":
                tag("MEWP", f, v)
            if re.search(r"아르곤|TIG|퍼지|질소 치환", t) and not NEGATED.search(t):
                tag("INERT", f, v)
            if re.search(r"배관|계통|라인|퍼지", t):
                for sid in SYSTEM_ID.findall(t):
                    if not CRANE_ID.fullmatch(sid) and not PANEL_ID.fullmatch(sid):
                        ids["systems"].add(sid)
            if f in ("작업명", "작업 상세", "위치(답변 반영)") and re.search(r"이중저|탱크 내부|밀폐|맨홀 진입", t) and d["type"] == "plan":
                tag("CONFINED", f, v)
            # equipment: per phrase, so 'OH-21-03 사용, OH-21-02 미사용' keeps only the one in use
            for c in CRANE_ID.findall(t):
                if re.search(r"미사용|사용 안|제외", t) or f in ("유해위험요소",):
                    continue
                if d["type"] == "permit" and d["kind"] == "loto":
                    ids["crane_loto"].add(c); tag("CRANE_LOTO", f, v)
                elif d["type"] == "plan" and f == "작업명":
                    continue
                else:
                    ids["crane_use"].add(c); tag("CRANE_USE", f, v)
            for p in PANEL_ID.findall(t):
                if d["type"] == "permit" and d["kind"] == "loto":
                    ids["power_loto"].add(p); tag("POWER_LOTO", f, v)
                elif "전원" in t and not NEGATED.search(t):
                    ids["power_use"].add(p); tag("POWER_USE", f, v)
    # 쌍 하이브리드: the facts the foreman confirmed in his submission (an explicit table, see confirmed_facts)
    from_answer = {}
    for x in d.get("_confirmed", []):
        f = f"{CONFIRMED} {x['item']}"
        if x.get("tag"):
            tag(x["tag"], f, x["value"])
        if x.get("ids"):
            kind, i = x["ids"]
            ids[kind].add(i)
            from_answer[i] = (f, x["value"])
            tag({"crane_use": "CRANE_USE", "power_use": "POWER_USE"}[kind], f, x["value"])
    if ids["crane_use"]:
        tag("LIFT", "크레인 사용", ", ".join(sorted(ids["crane_use"])))
        for i in sorted(ids["crane_use"] & set(from_answer)):        # a lift known from a confirmed answer says so
            tag("LIFT", *from_answer[i])
    place = d["place"].translate(DASH)
    if lows is None and re.search(r"상부|갑판", place + title):
        lows = highs = None
    up = (highs or 0) >= 2 or re.search(r"상부|갑판", place) is not None
    if SEPARATE.search(title + " " + (d.get("detail") or "")) and up:
        tag("DROP", "작업명", title)
    level = "inside" if re.search(r"내부|이중저|탱크|배관", place) and "외판" not in place else "top" if up else "ground"
    ids["blocks"] = set(BLOCK_ID.findall(" ".join([title, place, d.get("target") or ""])))
    wins = [_win_m(w) for w in d["windows"]]
    move = _win_m(d["move"]) if d.get("move") else None
    move_off = bool(move and wins and not any(a <= move[0] and move[1] <= b for a, b in wins))
    # the moving part of a lift: its planned move, plus any re-entry window the safety team added (완료 후 재진입:
    # the block may be lifted again then, so the whole added window counts, not only the old move)
    moves = ([move] if move else []) + [_win_m(w) for w in d.get("extra_windows") or []]
    # a crane step with a stated start: '(10:30)'. Its end is not stated, so it runs to the end of the plan's window
    lift_at = []
    if d["type"] == "plan":
        for _, s in fields:
            if CRANE_ID.search(s) and (m := re.search(r"\((\d{1,2}:\d{2})\)", s)) and wins:
                t0 = _m(m.group(1))
                # the step runs from its stated start to the end of the window it falls in; a step whose time is no
                # longer inside the work's hours (stopped or moved) is not done at that time
                lift_at += [(t0, b) for a, b in wins if a <= t0 < b]
    where = "known" if d["spans"] else "off" if OFF_FLOOR.search(place) else "unknown"
    # an answer that says another work is below this one (B3 '하부에서 족장 해체 13:00~15:30 (삼녹)')
    below = [v for f, v in fields if f.startswith("답변") and re.search(r"하부|아래|밑", v)]
    return {"d": d, "tags": tags, "ids": ids, "level": level, "low": lows, "high": highs, "wins": wins, "move": move, "moves": moves, "move_off": move_off,
            "lift_at": lift_at, "fields": fields, "where": where, "below": below,
            "people": d.get("workers")}           # None = 미상, 0 = nobody


# ---------------------------------------------------------------- where and when two works meet
def _spans(P, path=False):
    """BAY + column ranges; a route as one range from its first to its last column (the load passes over all of it)."""
    sp = P["d"]["spans"]
    if path and P["d"]["is_route"]:
        out = []
        for b in sorted({s["bay"] for s in sp}):
            cs = [s for s in sp if s["bay"] == b and s["c0"]]
            out.append({"bay": b, "c0": min(s["c0"] for s in cs), "c1": max(s["c1"] for s in cs)} if cs else {"bay": b, "c0": None, "c1": None})
        return out
    return sp


def place_rel(A, B, path_a=False, path_b=False):
    """same (shared column range) · near (next column) · unknown (a side without columns or place) · far · none · off."""
    if A["where"] == "off" or B["where"] == "off":
        return {"kind": "off", "bay": None, "gap": None}
    if A["where"] == "unknown" or B["where"] == "unknown":
        return {"kind": "unknown", "bay": None, "gap": None}
    order = {"same": 0, "near": 1, "unknown": 2, "far": 3, "none": 4}
    best = {"kind": "none", "bay": None, "gap": None}
    for a in _spans(A, path_a):
        for b in _spans(B, path_b):
            if a["bay"] != b["bay"]:
                continue
            if a["c0"] is None or b["c0"] is None:
                r = {"kind": "unknown", "bay": a["bay"], "gap": None}
            else:
                gap = max(a["c0"], b["c0"]) - min(a["c1"], b["c1"])
                r = {"kind": "same" if gap <= 0 else "near" if gap == 1 else "far", "bay": a["bay"], "gap": max(gap, 0)}
            if order[r["kind"]] < order[best["kind"]] or (r["kind"] == best["kind"] == "far" and r["gap"] < best["gap"]):
                best = r
    return best


def overlaps(wa, wb):
    """The overlap of two window lists as separate pieces, merged: [(start, end)] (no minute counted twice)."""
    out = []
    for a0, a1 in wa:
        for b0, b1 in wb:
            s, e = max(a0, b0), min(a1, b1)
            if e > s:
                out.append((s, e))
    merged = []
    for s_, e_ in sorted(out):
        if merged and s_ <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e_))
        else:
            merged.append((s_, e_))
    return merged


def gap_after(first, then):
    """Minutes from the end of `first` to the start of `then` (`then` starting after `first` ended), smallest; None if never."""
    g = [b0 - a1 for a0, a1 in first for b0, b1 in then if b0 >= a1]
    return min(g) if g else None


# ---------------------------------------------------------------- the rules: does the path exist? (A = cause, B = exposed)
def _people(B):
    return B["people"] != 0


def _path(rule, A, B):
    """→ (windows of A, windows of B, place-mode) or None. place-mode: which place evidence the rule needs."""
    t, a, b = rule["id"], A["tags"], B["tags"]
    wa, wb = A["wins"], B["wins"]
    if t == "FIRE":
        return (wa, wb, "reach") if "SPARK" in a and "SOLVENT" in b and _people(B) else None
    if t == "CONF_HOT":
        return (wa, wb, "block") if "SPARK" in a and "CONFINED" in b and _people(B) else None
    if t == "CONF_GAS":
        return (wa, wb, "system") if "INERT" in a and "CONFINED" in b and _people(B) else None
    if t == "LOAD_OVER":
        if "LIFT" not in a or not _people(B) or A["ids"]["crane_use"] & B["ids"]["crane_loto"]:
            return None                              # a crane over its own repair is CRANE_LOTO
        return (A["moves"] if A["moves"] else A["lift_at"] or wa, wb, "path")
    if t == "TARGET_OCCUPIED":
        if A["d"]["type"] != "permit" or A["d"]["kind"] != "lifting" or B["level"] not in ("inside", "top") or not _people(B):
            return None
        return (A["moves"] if A["moves"] else wa, wb, "same_block")
    if t == "CRANE_LOTO":
        if not (A["ids"]["crane_loto"] & B["ids"]["crane_use"]):
            return None
        return (wa, B["moves"] if B["moves"] else B["lift_at"] or wb, "link")
    if t == "POWER_LOTO":
        return (wa, wb, "link") if A["ids"]["power_loto"] & B["ids"]["power_use"] else None
    if t == "DROP_BELOW":
        return (wa, wb, "below") if "DROP" in a and _people(B) else None
    if t == "PRESSURE":
        return (wa, wb, "reach") if "PRESSURE" in a and _people(B) else None
    if t == "RADIATION":
        return (wa, wb, "reach") if "RADIATION" in a and _people(B) else None
    if t == "VEHICLE":
        if "VEHICLE" not in a or not _people(B) or (B["level"] != "ground" and "MEWP" not in b):
            return None
        return (wa, wb, "covered")
    if t == "CRANE_SHARE":
        if not (A["ids"]["crane_use"] & B["ids"]["crane_use"]) or A["d"]["id"] > B["d"]["id"]:
            return None
        pick = lambda P: P["moves"] if P["moves"] else P["lift_at"] or P["wins"]  # noqa: E731
        return (pick(A), pick(B), "link")
    if t == "CRANE_CROSS":
        if "LIFT" not in a or "LIFT" not in b or A["d"]["id"] > B["d"]["id"] or A["ids"]["crane_use"] & B["ids"]["crane_use"] \
                or not A["ids"]["crane_use"] or not B["ids"]["crane_use"]:
            return None
        pick = lambda P: P["moves"] if P["moves"] else P["lift_at"] or P["wins"]  # noqa: E731
        return (pick(A), pick(B), "bay")
    if t == "SUPPORT":
        if "SEP" not in a and "DROP" not in a:
            return None
        return (wa, wb, "same_block") if B["level"] == "top" and _people(B) else None
    if t == "ACCESS":
        if not ({"LIFT", "VEHICLE", "DROP"} & set(a)) or "CONFINED" not in b:
            return None
        return (A["moves"] if A["moves"] else A["lift_at"] or wa, wb, "path") if _people(B) else None
    if t == "HOT_PERSON":
        return (wa, wb, "same_only") if "SPARK" in a and _people(B) and "SOLVENT" not in b and "CONFINED" not in b else None
    return None


def _place(mode, A, B):
    """How sure the place link is: (E cap 3/2/1 or None = no path, words)."""
    common = sorted(A["ids"]["blocks"] & B["ids"]["blocks"])
    if mode == "system":
        shared = sorted(A["ids"]["systems"] & B["ids"]["systems"])
        if shared:
            return 3, f"같은 배관·계통 {', '.join(shared)}"
        common_b = sorted(A["ids"]["blocks"] & B["ids"]["blocks"])
        return (1, f"같은 블록 {', '.join(common_b)}이지만 가스 계통 연결은 서류에 없음") if common_b else (None, "")
    if mode == "link":
        ids = sorted((A["ids"]["crane_loto"] | A["ids"]["power_loto"] | A["ids"]["crane_use"]) & (B["ids"]["crane_use"] | B["ids"]["power_use"]))
        return 3, f"같은 설비 {', '.join(ids)}"
    rel = place_rel(A, B, path_a=mode == "path")
    if rel["kind"] in ("off", "none"):
        return None, ""
    if rel["kind"] == "unknown":
        return 1, "위치(칼럼)를 알 수 없어 같은 곳인지 확인 못 함"
    if mode == "same_block":
        return (3, f"같은 블록 {', '.join(common)}") if common else (None, "")
    if mode == "bay":
        return (2, f"같은 {rel['bay']}BAY(주행 구간 미확인)") if rel["kind"] in ("same", "near", "far") else (None, "")
    if mode == "path":
        if rel["kind"] != "same":
            return None, ""
        return (3, f"명시된 이동 경로가 {rel['bay']}BAY 그 칼럼 위를 지남") if A["d"]["is_route"] else \
            (3, f"같은 블록 {', '.join(common)}") if common else (2, f"{rel['bay']}BAY 같은 칼럼 주소(실제 위치 미확인)")
    if mode == "covered":
        if rel["kind"] != "same":
            return None, ""
        return (3, f"운반 구간 안 · 같은 블록 {', '.join(common)}") if common else (2, f"{rel['bay']}BAY 운반 구간과 같은 칼럼 주소")
    if mode == "below":
        if rel["kind"] != "same":
            return None, ""
        stated = [v for v in A["below"] if (B["d"].get("company") and B["d"]["company"] in v) or (B["d"]["type"] == "permit" and B["d"]["id"] in v)]
        if stated:
            return 3, f"작업반장이 아래 작업이라고 답함: '{stated[0]}'"
        if B["low"] is not None and A["high"] is not None and B["low"] > A["high"]:
            return None, ""                          # the other work is clearly above: nothing falls on it
        if B["level"] in ("ground", "inside") or (B["high"] is not None and A["low"] is not None and B["high"] < A["low"]):
            return (3 if common else 2), (f"같은 블록 {', '.join(common)} · 아래 높이" if common else "같은 칼럼 주소 · 아래 높이")
        return 2, "같은 칼럼이지만 위아래 높이를 확정할 수 없음"
    if mode == "block":
        if common:
            return 3, f"같은 블록 {', '.join(common)}"
        return (2, f"{rel['bay']}BAY 같은 칼럼 주소(다른 블록)") if rel["kind"] == "same" else (None, "")
    if mode == "same_only":
        if rel["kind"] != "same":
            return None, ""
        return (3, f"같은 블록 {', '.join(common)}") if common else (2, f"{rel['bay']}BAY 같은 칼럼 주소(실제 거리 미확인)")
    # reach: fire, pressure, radiation — same block / same columns; anywhere else in the BAY the real distance and
    # shielding are not known (the column spacing is an estimate, and 11m is the fire-watch radius of 제241조의2, not the
    # edge of every hazard), so a farther column is not left out: it stays 「거리 미확인」 to be checked (Codex A7)
    if rel["kind"] == "same":
        return (3, f"같은 블록 {', '.join(common)}") if common else (2, f"{rel['bay']}BAY 같은 칼럼 주소(실제 거리 미확인)")
    if rel["kind"] == "near":
        return 1, f"{rel['bay']}BAY 바로 옆 칼럼: 거리 미확인(실제 거리·차폐 확인 필요)"
    if rel["kind"] == "far":
        return 1, f"{rel['bay']}BAY 칼럼 {rel['gap']}칸 떨어짐: 거리 미확인(실제 거리·차폐 확인 필요)"
    return None, ""


# 쌍 하이브리드 (design §8.1): a submission's answers the foreman confirmed, about his own work, go into the
# profile of that permit like its other answers — marked, so the evidence says where they came from. Only these
# items (what the work does, where, with what); not another team's work (B3·C3·C5), not a free remark, not a
# checking answer, not 「모름」 or 「해당 없음」 (an answer adds what it says; it never takes away what the documents say).
CONFIRMED = "작업반장 답변 · 반장 답변 확인"
# (question, choice) -> the tag the confirmed choice says of this work (the choice itself, whatever number came with it)
HYBRID_CHOICE = {("HT1", "gas"): "SPARK", ("HT1", "plasma"): "SPARK", ("HT1", "mech"): "SPARK"}
# a typed answer naming the equipment this work uses: the IDs it names, clause by clause, not in a clause that says no
HYBRID_IDS = {"D2": "crane_use", "LI1": "crane_use", "D4": "power_use"}
# a typed answer naming the gas or line: argon·nitrogen in a clause that does not say no
HYBRID_INERT = ("H2", "D3", "CF2")
SAYS_NO = re.compile(r"안\s*(?:씀|써|쓰|함|해|하|합|들)|않|없|미사용|사용\s*안|제외|아님|아니|말고|금지|빼고")
OTHERS = re.compile(r"(?:옆|다른|타|상대|저쪽)\s*(?:팀|업체|반|작업|회사)|[가-힣]{1,6}팀(?:은|는|이|가|도|의|에서|이랑|하고)|들었")
CLAUSE = re.compile(r"[,·/;.]|\s(?:그리고|또는|및)\s")


def confirmed_facts(answers):
    """the answers of a submission the foreman confirmed — his own typed answers and the readings of his own work he
    confirmed on the card — as facts of his work: [{item, value, tag | ids}]. Nothing from another team's work, a
    free remark, a checking question, an AI question, a blank-field fill, 「모름」 or a no; a typed sentence is read
    only for what the table above names."""
    out = []
    for a in answers or []:
        item, ch, v = str(a.get("qid", "")).split(":")[0], a.get("choice"), (a.get("value") or "").strip()
        if ch in ("unknown", "na", "none", "no") or (a.get("pid") and a.get("who") not in (None, "self")):
            continue
        q = a.get("q") or {}
        label = next((c.get("label") for c in q.get("choices", []) if c.get("id") == ch), ch)
        if (item, ch) in HYBRID_CHOICE:                      # the choice, and the count typed with it (nothing else said)
            n = re.search(r"(?<!\d)(\d{1,3})\s*개", v) or re.fullmatch(r"\s*(\d{1,3})\s*", v)
            out.append({"item": item, "value": f"{label} {n.group(1)}개" if n else str(label), "tag": HYBRID_CHOICE[(item, ch)]})
        for cl in CLAUSE.split(v) if v and (item in HYBRID_IDS or item in HYBRID_INERT) else []:
            if SAYS_NO.search(cl) or OTHERS.search(cl):    # a no, or another team's work: nothing of this one
                continue
            if item in HYBRID_IDS:
                for i in (CRANE_ID if HYBRID_IDS[item] == "crane_use" else PANEL_ID).findall(cl):
                    out.append({"item": item, "value": f"{i} 사용", "ids": (HYBRID_IDS[item], i)})
            elif re.search(r"아르곤|질소|TIG|퍼지", cl) and not any(x.get("tag") == "INERT" and x["item"] == item for x in out):
                out.append({"item": item, "value": cl.strip()[:40], "tag": "INERT"})
    return out


def compare(before, after, facts=None):
    """the alarms before and after the confirmed answers went in (design §8.1): new; kept (the same alarm — changed
    when its priority, E or score moved, or it stands on a confirmed answer now); gone. Every row of a pair one of
    whose works has confirmed facts carries those facts (what made the change, or what was weighed)."""
    facts = facts or {}
    k = lambda p, r: (p["key"], r["rule"], r["cause"], r["exposed"])
    B = {k(p, r): (p, r) for p in before["pairs"] for r in p["reasons"]}
    A = {k(p, r): (p, r) for p in after["pairs"] for r in p["reasons"]}
    num = lambda r: {x: r[x] for x in ("priority", "S", "E", "score")}

    def row(key, was, now):
        p, r = now or was
        src = [{"doc": d, "item": x["item"], "value": x["value"]} for d in (key[2], key[3]) for x in facts.get(d, [])]
        return {"key": key[0], "pair": p.get("id"), "rule": r["rule"], "name": r["name"], "cause": key[2], "exposed": key[3],
                "before": was and num(was[1]), "after": now and num(now[1]), "from": src,
                "moved": bool(was and now and num(was[1]) != num(now[1]))}
    new = [row(x, None, A[x]) for x in A if x not in B]
    gone = [row(x, B[x], None) for x in B if x not in A]
    kept = [row(x, B[x], A[x]) for x in A if x in B and (num(A[x][1]) != num(B[x][1])
            or any(e.get("confirmed") or e.get("submitted") for e in A[x][1].get("evidence", [])) or facts.get(x[2]) or facts.get(x[3]))]
    return {"new": new, "kept": kept, "gone": gone}


def floor(before, after):
    """the day's judgement with the confirmed answers in, never below the documents' own: a reason the documents
    raised and the answers took away stays (marked 「문서 기준 유지」), a reason the answers made weaker keeps the
    documents' priority and score, and the pair keeps its place. Only a person lifts an alarm; a reading never does.
    -> a new judgement (after is not changed)."""
    k = lambda p, r: (p["key"], r["rule"], r["cause"], r["exposed"])
    rank = lambda r: (r["priority"], -r["score"])
    A = {p["key"]: p for p in after["pairs"]}
    pairs = []
    for p in after["pairs"]:
        pairs.append({**p, "reasons": list(p["reasons"])})
    by = {p["key"]: p for p in pairs}
    for p in before["pairs"]:
        if p["key"] not in A:
            by[p["key"]] = {**p, "reasons": [{**r, "floor": "gone"} for r in p["reasons"]]}
            pairs.append(by[p["key"]])
            continue
        q = by[p["key"]]
        now = {k(q, r): i for i, r in enumerate(q["reasons"])}
        for r in p["reasons"]:
            i = now.get(k(p, r))
            if i is None:
                q["reasons"].append({**r, "floor": "gone"})
            elif rank(r) < rank(q["reasons"][i]):          # the answers made it weaker: the documents' numbers stay
                q["reasons"][i] = {**q["reasons"][i], **{x: r[x] for x in ("priority", "S", "E", "score")}, "floor": "lowered"}
    for p in pairs:
        p["reasons"].sort(key=lambda h: (h["priority"], -h["score"], -h["when"]["min"]))
        top = p["reasons"][0]
        p.update(priority=top["priority"], score=top["score"], S=top["S"], E=top["E"], title=top["name"], forbidden=top["forbidden"],
                 judgement="확인위험" if top["E"] == 3 else "보수위험" if top["E"] == 2 else "판정보류")
    pairs.sort(key=lambda p: (p["priority"], -p["score"], -p["reasons"][0]["when"]["min"], -p["people"], p["a"], p["b"]))
    for i, p in enumerate(pairs, 1):
        p["id"] = f"P{i:02d}"
    stats = {**after["stats"], "pairs": len(pairs), "by_priority": {str(n): sum(p["priority"] == n for p in pairs) for n in (1, 2, 3)}}
    near = [n for n in after["near"] if not any(n["a"] in (p["a"], p["b"]) and n["b"] in (p["a"], p["b"]) for p in pairs)]
    return {**after, "pairs": pairs, "stats": stats, "near": near}


def _judge(rule, A, B):
    """One rule, A as its cause and B exposed → the reason (with S, E, words) or None."""
    p = _path(rule, A, B)
    if not p:
        return None
    wa, wb, mode = p
    cap, place_txt = _place(mode, A, B)
    if cap is None:
        return None
    why = []
    e = 3 if rule["trigger"] == "direct" else 2
    if rule["trigger"] != "direct":
        why.append("경로가 생기려면 사건이 하나 더 있어야 함(재통전·같은 시각 배차·주행 구간 겹침 등)")
    if cap < 3:
        why.append(place_txt)
    e = min(e, cap)
    # time
    ovs = overlaps(wa, wb) if wa and wb else []
    seq = None
    if ovs:
        when = {"start": _hm(ovs[0][0]), "end": _hm(ovs[0][1]), "min": sum(b - a for a, b in ovs), "kind": "overlap",
                "segments": [[_hm(a), _hm(b)] for a, b in ovs]}
    elif not wa or not wb:
        when = {"start": "", "end": "", "min": 0, "kind": "unknown"}
        e = 1; why.append("한쪽의 작업 시간이 없어 겹치는지 확인 못 함")
    elif rule.get("sequence"):
        # the closest end -> start between the two works' own windows (with several windows the last end is not it)
        cands = [(b0 - a1, "A", a1, b0) for a0, a1 in wa for b0, b1 in wb if b0 >= a1]
        cands += [(a0 - b1, "B", b1, a0) for a0, a1 in wa for b0, b1 in wb if a0 >= b1]
        if not cands:
            return None
        g, first, end, start = min(cands)
        seq = {"gap": g, "first": first}
        when = {"start": _hm(end), "end": _hm(start), "min": 0, "kind": "sequence", "gap": g}
        e = 1; why.append(f"작업 시간은 겹치지 않지만, 앞 작업이 끝나고 {g}분 뒤 시작: 잔류위험(잔불·증기·가스·잔압·잔류 인원)이 없어졌다는 확인 기록이 없음")
    else:
        return None
    if B["people"] is None and rule["id"] not in ("CRANE_LOTO", "POWER_LOTO", "CRANE_SHARE", "CRANE_CROSS"):
        e = min(e, 2); why.append("위험을 받는 작업의 인원 수가 적혀 있지 않음")
    for P in (A, B):
        if P["move_off"] and mode in ("path", "same_block", "link"):
            e = min(e, 2); why.append(f"{P['d']['id']}의 실제 이동 시각이 허가 시간 밖: 일정 불일치 확인")
    info_gap = e == 1 and (when["kind"] in ("unknown", "sequence") or cap == 1)
    gaps = list(why)                                   # every one of these is a thing not known or not confirmed
    if not why:
        why.append("같은 시간에 " + place_txt + " — 두 작업이 이어지는 것이 서류로 확인됨")
    S = rule["S"]
    # a missing fact or an unconfirmed residual risk is asked about whatever the score (3순위 확인 필요)
    pri = 1 if rule.get("forbidden") and e == 3 else 2 if S * e >= 6 else 3 if S * e >= 3 or info_gap else 0
    return {"rule": rule["id"], "name": rule["name"], "mode": rule["mode"], "S": S, "E": e, "score": S * e, "priority": pri,
            "forbidden": bool(rule.get("forbidden")), "cause": A["d"]["id"], "exposed": B["d"]["id"], "why_E": why, "gaps": gaps,
            "when": when, "sequence": seq, "relation": place_txt, "chain": [_fill(s, A, B, cap) for s in rule["chain"]],
            "measures": rule["measures"], "cases": rule["cases"], "law": rule["law"], "ask": rule["ask"],
            **{k: rule.get(k) for k in ("headline", "accident", "story", "mechanism", "roles", "roles_short")},
            "evidence": _evidence(rule, A, B), "estimated": bool(B["lift_at"] and mode == "link") or bool(A["lift_at"] and not A["move"] and mode == "path")}


_BATCHIM_DIGIT = set("013678")


def _josa(word, pair):
    """은/는-style particle after a name: '0737 중량물인양이', 'WP-02가', 'OH-21-03을', 'MCC-4를'."""
    c = word.rstrip()[-1:]
    if "가" <= c <= "힣":
        has = (ord(c) - 0xAC00) % 28 != 0
    else:
        has = c in _BATCHIM_DIGIT or c in "LMNRlmnr"
    return word + (pair[0] if has else pair[1])


def _who(P):
    d = P["d"]
    return f"{d['id']} {d['label']}" if d["type"] == "permit" else f"WP-{d['id'][-2:]}"


def _fill(s, A, B, cap):
    a, b = _who(A), _who(B)
    crane = ", ".join(sorted(A["ids"]["crane_loto"] | A["ids"]["crane_use"])) or "크레인"
    panel = ", ".join(sorted(A["ids"]["power_loto"])) or "전원"
    hi = A["high"]
    return s.format(a=a, b=b, a_ga=_josa(a, "이가"), b_ga=_josa(b, "이가"), a_ui=a + "의", b_ui=b + "의", a_wa=_josa(a, "과와"),
                    crane_eul=_josa(crane, "을를"), panel_eul=_josa(panel, "을를"), where=B["d"]["place"].replace("대조립21공장 ", ""),
                    block=", ".join(sorted(A["ids"]["blocks"] & B["ids"]["blocks"])) or "같은",
                    height=f"{hi:g}m" if hi else "높은 곳",
                    reach=f"화재감시자 반경 {FIRE_REACH_M}m 기준" if cap == 3 else "실제 거리·차폐 미확인")


_WANT = {"FIRE": ("SPARK", "SOLVENT"), "CONF_HOT": ("SPARK", "CONFINED"), "CONF_GAS": ("INERT", "CONFINED"), "LOAD_OVER": ("LIFT", None),
         "TARGET_OCCUPIED": ("LIFT", "CONFINED"), "CRANE_LOTO": ("CRANE_LOTO", "CRANE_USE"), "POWER_LOTO": ("POWER_LOTO", "POWER_USE"),
         "DROP_BELOW": ("DROP", None), "PRESSURE": ("PRESSURE", None), "RADIATION": ("RADIATION", None), "VEHICLE": ("VEHICLE", "MEWP"),
         "CRANE_SHARE": ("CRANE_USE", "CRANE_USE"), "CRANE_CROSS": ("CRANE_USE", "CRANE_USE"), "SUPPORT": ("SEP", None),
         "ACCESS": ("LIFT", "CONFINED"), "HOT_PERSON": ("SPARK", None)}


def _evidence(rule, A, B):
    """The facts the judgement stands on: which document says what (what it is, when, where)."""
    out = []
    for P, t in zip((A, B), _WANT[rule["id"]]):
        got = P["tags"].get(t) or []
        for field, value in got[:2] + [x for x in got[2:] if x[0].startswith(CONFIRMED)]:      # a confirmed answer is always shown
            out.append({"doc": P["d"]["id"], "field": field, "value": value, **({"confirmed": True} if field.startswith(CONFIRMED) else {})})
    for P in (A, B):
        t = ", ".join(f"{_hm(a)}–{_hm(b)}" for a, b in P["wins"]) or "시간 없음"
        if P["move"]:
            t += f" (실제 이동 {_hm(P['move'][0])}–{_hm(P['move'][1])})"
        if P["lift_at"]:
            t += f" (크레인 인양 {', '.join(_hm(a) for a, _ in P['lift_at'])} 시작, 끝 시각 없음)"
        sub = P["d"].get("_sub") or {}               # a value from the foreman's submission says so (Codex A6)
        out.append({"doc": P["d"]["id"], "field": "시간" + (f"({SUBMITTED})" if sub.get("time") else ""), "value": t,
                    **({"submitted": True} if sub.get("time") else {})})
        out.append({"doc": P["d"]["id"], "field": "위치" + (f"({SUBMITTED})" if sub.get("place") else ""),
                    "value": P["d"]["place"].replace("대조립21공장 ", "") + (f" / 경로: {P['d']['route']}" if P["d"].get("route") else ""),
                    **({"submitted": True} if sub.get("place") else {})})
        if P["below"] and rule["id"] == "DROP_BELOW" and P is A:
            said = [v for v in A["below"] if (B["d"].get("company") and B["d"]["company"] in v) or (B["d"]["type"] == "permit" and B["d"]["id"] in v)]
            out.append({"doc": P["d"]["id"], "field": "답변(아래 작업)", "value": (said or P["below"])[0], "quote": True})
    return out


TAG_KO = {"SEP": "절단·해체", "SPARK": "화기", "SOLVENT": "유기용제", "CONFINED": "밀폐 진입", "INERT": "불활성가스", "LIFT": "크레인 인양", "DROP": "높은 곳 절단·해체",
          "PRESSURE": "압력시험", "RADIATION": "방사선", "VEHICLE": "차량 운반", "MEWP": "고소작업대", "CRANE_USE": "크레인 사용",
          "CRANE_LOTO": "크레인 정전", "POWER_LOTO": "전원 정전", "POWER_USE": "전원 사용"}


def _override(d, wins):
    """A work with the time the safety team set (일정 변경 / 한쪽 중지): its windows replaced; a lift's move shifted
    with its start, or dropped when it no longer fits."""
    if not wins:
        return d
    extra = [w for w in wins if w.get("extra")]
    wins = [{k: v for k, v in w.items() if k != "extra"} for w in wins]
    nd = {**d, "windows": wins, "start": wins[0]["start"], "end": wins[-1]["end"], "extra_windows": [{k: v for k, v in w.items() if k != "extra"} for w in extra]}
    if d.get("move") and d.get("windows"):
        base = [w for w in wins if w not in nd["extra_windows"]] or wins
        delta = _m(base[0]["start"]) - _m(d["windows"][0]["start"])
        a, b = _win_m(d["move"])
        a, b = a + delta, b + delta
        fits = any(_win_m(w)[0] <= a and b <= _win_m(w)[1] for w in wins)
        nd["move"] = {"start": _hm(a), "end": _hm(b)} if fits else None
    return nd


SUBMITTED = "제출본 반영"


def _windows_ok(ws):
    return isinstance(ws, list) and all(isinstance(w, dict) and HM.fullmatch(str(w.get("start"))) and HM.fullmatch(str(w.get("end"))) for w in ws)


def _submitted(d, s):
    """a document with the place and this day's times the foreman's latest submission confirms (Codex A6, design §8.1):
    the same hybrid path as the confirmed answers, so it can add an alarm; the documents' own alarms are kept by floor().
    s: {place?, windows?}; a value equal to the document's, or not readable, changes nothing."""
    if not s:
        return d
    nd, sub = dict(d), {}
    place = str(s.get("place") or "").strip()
    if place and place != d["place"]:
        route = d.get("route") or ""
        nd.update(place=place, spans=safety.spans(place + " " + route), is_route=bool(route) or "→" in place)
        sub["place"] = d["place"]
    ws = s.get("windows")
    if ws and _windows_ok(ws) and [{k: w[k] for k in ("start", "end")} for w in ws] != [{k: w[k] for k in ("start", "end")} for w in d["windows"]]:
        ws = [{"start": w["start"], "end": w["end"], **({"next_day": True} if w.get("next_day") or w["end"] <= w["start"] else {})} for w in ws]
        nd.update(windows=ws, start=ws[0]["start"], end=ws[-1]["end"])
        sub["time"] = [f"{w['start']}~{w['end']}" for w in d["windows"]]
    if sub:
        nd["_sub"] = sub
    return nd


def detect(overrides=None, confirmed=None, submitted=None):
    """overrides: {doc_id: [{"start": "HH:MM", "end": "HH:MM"}, …]} — tests only (a schedule tried).
    confirmed: {permit_no: [records]} — the foremen's confirmed answers from their submissions (쌍 하이브리드).
    submitted: {doc_id: {place?, windows?}} — the place and times the latest submission confirms (Codex A6)."""
    D = safety.data()
    if confirmed:
        D = {**D, "permits": [{**p, "_confirmed": confirmed[p["permit_no"]]} if confirmed.get(p.get("permit_no")) else p for p in D["permits"]]}
    if submitted:
        D = {**D, **{k: [_submitted(p, submitted.get(p["id"])) for p in D[k]] for k in ("permits", "plans")}}
    R = rules()
    ov = {}
    for k, ws in (overrides or {}).items():
        if not isinstance(ws, list) or not all(isinstance(w, dict) and HM.fullmatch(str(w.get("start"))) and HM.fullmatch(str(w.get("end"))) for w in ws):
            raise ValueError(f"{k}: 시각은 00:00~23:59 형식이어야 합니다")    # refused, not read as a stop
        good = ws
        ov[k] = [{**({"start": w["start"], "end": w["end"]}), **({"next_day": True} if w["end"] <= w["start"] else {}),
                  **({"extra": True} if w.get("extra") is True else {})} for w in good]
    # a work stopped for the whole day (no window left) is not done that day: it meets nobody
    off = {k for k, v in ov.items() if not v}
    permits = [profile(_override(p, ov.get(p["id"]))) for p in D["permits"] if p["id"] not in off]
    plans = [profile(_override(p, ov.get(p["id"]))) for p in D["plans"] if p["id"] not in off]
    cand = [(a, b) for i, a in enumerate(permits) for b in permits[i + 1:]] + [(a, b) for a in permits for b in plans]
    pairs, near = [], []
    stats = {"candidates": len(cand), "nn": len(permits) * (len(permits) - 1) // 2, "rn": len(permits) * len(plans),
             "time": 0, "time_bay": 0, "path": 0, "sequence": 0, "unknown_time": 0, "unknown_place": 0}
    for X, Y in cand:
        both_t = bool(X["wins"] and Y["wins"])
        ov = both_t and bool(overlaps(X["wins"], Y["wins"]))
        rel = place_rel(X, Y, True, True)
        stats["time"] += ov
        stats["time_bay"] += ov and rel["kind"] in ("same", "near", "far")
        stats["unknown_place"] += ov and rel["kind"] == "unknown"
        stats["unknown_time"] += not both_t
        hits, seen = [], set()
        for rule in R["rules"]:
            for A, B in ((X, Y), (Y, X)):
                h = _judge(rule, A, B)
                if h and h["priority"] and (h["rule"], h["cause"], h["exposed"]) not in seen:
                    seen.add((h["rule"], h["cause"], h["exposed"]))
                    hits.append(h)
        hits.sort(key=lambda h: (h["priority"], -h["score"], -h["when"]["min"]))
        if hits:
            top = hits[0]
            confirmed = top["when"]["kind"] == "overlap" and top["E"] > 1     # E1 = a missing fact or a residual risk to ask about
            stats["path"] += confirmed
            stats["sequence"] += not confirmed
            a, b = X["d"], Y["d"]
            pairs.append({"a": a["id"], "b": b["id"], "key": f"{a['id']}|{b['id']}", "kind": "NN" if b["type"] == "permit" else "RN", "priority": top["priority"],
                          "score": top["score"], "S": top["S"], "E": top["E"], "title": top["name"], "forbidden": top["forbidden"],
                          "reasons": hits, "judgement": "확인위험" if top["E"] == 3 else "보수위험" if top["E"] == 2 else "판정보류",
                          "people": sum(x for x in (a.get("workers"), b.get("workers")) if x)})
        else:
            why = _quiet(X, Y, rel)
            if why:
                near.append({"a": X["d"]["id"], "b": Y["d"]["id"], "why": why})
    pairs.sort(key=lambda p: (p["priority"], -p["score"], -p["reasons"][0]["when"]["min"], -p["people"], p["a"], p["b"]))
    for i, p in enumerate(pairs, 1):
        p["id"] = f"P{i:02d}"
    stats["pairs"] = len(pairs)
    stats["by_priority"] = {str(k): sum(p["priority"] == k for p in pairs) for k in (1, 2, 3)}
    near.sort(key=lambda n: (n["why"]["rank"], n["a"], n["b"]))
    return {"date": D["date"], "stats": stats, "pairs": pairs, "near": near, "overrides": ov,
            "rules": [{k: r.get(k) for k in ("id", "name", "mode", "S", "trigger", "forbidden", "post", "measures", "residual")} for r in R["rules"]],
            "levels": {k: R[k] for k in ("severity", "exposure", "priority")}}


def _quiet(X, Y, rel):
    """A pair that looks close but is not raised, and why — the closest reason first (researcher's step 6)."""
    if rel["kind"] in ("none", "off"):
        return None
    tx, ty = set(X["tags"]), set(Y["tags"])
    # a shared kind of equipment, but not the same one
    for kind, loto, use in (("전원", "power_loto", "power_use"), ("크레인", "crane_loto", "crane_use")):
        for P, Q in ((X, Y), (Y, X)):
            if P["ids"][loto] and Q["ids"][use] and not P["ids"][loto] & Q["ids"][use]:
                return {"rank": 0, "text": f"{kind}이 달라 이어지지 않음({', '.join(sorted(P['ids'][loto]))} 정전 · {', '.join(sorted(Q['ids'][use]))} 사용)", "kind": "link"}
    ov = overlaps(X["wins"], Y["wins"]) if X["wins"] and Y["wins"] else []
    if rel["kind"] in ("same", "near") and not ov:
        g = [x for x in (gap_after(X["wins"], Y["wins"]), gap_after(Y["wins"], X["wins"])) if x is not None]
        if g and min(g) <= 180:
            return {"rank": 1, "text": (f"같은 곳이지만 시간이 떨어짐({min(g)}분 간격)" if min(g) else "같은 곳이지만 한 작업이 끝난 뒤 이어서 시작")
                    + " · 앞 작업에 잔류위험 규칙이 없음", "kind": "time"}
        return None
    if ov and rel["kind"] == "far":
        # no distance is claimed (the column spacing is not measured): what is said is which rules were looked at
        return {"rank": 2, "text": f"같은 시간·같은 {rel['bay']}BAY, 칼럼 {rel['gap']}칸 떨어짐(실제 거리 미확인): 떨어져도 닿을 수 있는 "
                "화기×유기용제·압력시험·방사선 작업이 아니고, 낙하·인양 경로·운반·불티 규칙은 같은 칼럼·블록일 때 봄", "kind": "far"}
    if ov:
        kx = "·".join(TAG_KO[t] for t in sorted(tx) if t in TAG_KO) or "일반 작업"
        ky = "·".join(TAG_KO[t] for t in sorted(ty) if t in TAG_KO) or "일반 작업"
        return {"rank": 3, "text": f"같은 시간·가까운 곳이지만 두 작업 성질({kx} × {ky}) 사이에 위험 전달 규칙이 없음", "kind": "path"}
    return None


# 서류상 선후 계획 · 남은 확인 (design §8.4·§19.1): display only — a pair whose documents plan one work after the other
# (a rule's sequence reason, or a document that says 「…완료 후」) shows the plan as written and what is not confirmed.
# It never lifts an alarm, lowers a priority or ticks anything done; a new or corrected document is judged again.
SEQ_TITLE = "서류상 선후 계획 · 남은 확인"
SEQ_TEXT = "문서에 선후 계획이 있으나 실제 완료·잔류위험 해제·상대 반장 합의는 확인되지 않았습니다."
SEQ_SAID = re.compile(r"[^.。\n]{0,24}(?:완료\s*(?:후|뒤|이후)|끝난\s*(?:뒤|후)|끝나면|종료\s*(?:후|뒤|이후)|마친\s*(?:뒤|후)|선행\s*작업|후행\s*작업|"
                      r"이후\s*(?:시작|진행|착수|작업))[^.。\n]{0,24}")


def _said_seq(d):
    """the first sentence of a document that plans an order (「도장 완료 후 진입」), or None"""
    for t in [d.get("title"), d.get("detail"), d.get("place"), d.get("route")] + [v for _, v in (d.get("fields") or []) if isinstance(v, str)]:
        m = SEQ_SAID.search(str(t or ""))
        if m:
            return m.group(0).strip()
    return None


def sequence_plan(p, docs, rules_=None):
    """-> {title, text, plan: [{first, later, end, start, gap, rule}], said: [{doc, text}], left: [...]} or None"""
    seqs = [r for r in p["reasons"] if (r.get("when") or {}).get("kind") == "sequence"]
    said = [{"doc": i, "text": t} for i in (p["a"], p["b"]) if (t := _said_seq(docs.get(i) or {}))]
    if not seqs and not said:
        return None
    R = {r["id"]: r for r in (rules_ or rules())["rules"]}
    plan, seen = [], set()
    for r in seqs:
        first, later = (r["cause"], r["exposed"]) if (r.get("sequence") or {}).get("first", "A") == "A" else (r["exposed"], r["cause"])
        if (first, later) in seen:
            continue
        seen.add((first, later))
        plan.append({"first": first, "later": later, "end": r["when"]["start"], "start": r["when"]["end"], "gap": r["when"].get("gap"), "rule": r["name"]})
    residual = list(dict.fromkeys(R[r["rule"]]["residual"] for r in seqs if R.get(r["rule"], {}).get("residual")))
    left = ["앞 작업의 실제 완료(현장 확인 기록 없음)"] + [f"잔류위험 해제: {x}" for x in residual] + ["두 작업반장의 순서 합의"]
    return {"title": SEQ_TITLE, "text": SEQ_TEXT, "plan": plan, "said": said, "left": left}


def annotate(det, docs):
    """display data added to a judgement (nothing it decides changes): the sequence plan of each pair"""
    R = rules()
    for p in det["pairs"]:
        p["seq_plan"] = sequence_plan(p, docs, R)
    return det

