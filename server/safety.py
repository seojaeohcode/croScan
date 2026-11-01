"""안전관리자 시점: what the 생산부서 and the 협력사 sent in for one day, read from the demo DB (read-only).

The demo DB (tools/make_demo_day.py) holds the permits as croScan read them, the foreman's answers, the 위험 체크리스트
he confirmed and the 추가검토서, and the 작업계획서 as read. Its answer key (clashes, near_misses, truth) is never served:
the pair detection comes later and must find them itself.
"""
import json
import re
import sqlite3
from functools import lru_cache
from pathlib import Path

from . import addendum, checklist
from . import permit_kinds as PK
from .qa import DATA

ROOT = Path(__file__).resolve().parent.parent
# on the server the DB and its PDFs sit on the data disk; on a development PC the samples folder is used
_HOMES = [(DATA / "demo_day.sqlite3", DATA / "demo_day"), (ROOT / "samples/시연_하루/demo_day.sqlite3", ROOT / "samples/시연_하루")]
# 대조립21공장: the DEMO layout (4BAY · 20 columns), a variant made for the demo day — not the research book's canonical
# F01 (자료 388~404쪽: 3BAY × 폭 36m, 길이 240m, 12m 축 20구간, 합성 계획값). Neither is a site's real grid; a column number
# is an address for finding candidates, never a distance (pairs.py). Do not overwrite one with the other (Codex B 518~525).
BAYS, COLS = 4, 20

_POS = re.compile(r"(?<!\d)(\d+)\s*BAY|(?<!\d)(\d+)\s*[-~]\s*(\d+)\s*칼럼|(?<!\d)(\d+)\s*칼럼")


def _home():
    for db, files in _HOMES:
        if db.exists():
            return db, files
    raise FileNotFoundError("시연 DB(demo_day.sqlite3)가 없습니다")


def spans(text):
    """Where a work is, as BAY + column ranges: [{bay, c0, c1}] (c0/c1 None: somewhere in that BAY).
    '3BAY 06칼럼에서 16칼럼' gives two spans (a route's ends); a BAY named again without columns adds nothing.
    A BAY or a column outside the factory is never moved into it: it is left out (where unknown)."""
    out, bay, named = [], None, []
    for m in _POS.finditer(text or ""):
        if m.group(1):
            bay = int(m.group(1)) if 1 <= int(m.group(1)) <= BAYS else None
            if bay:
                named.append(bay)
            continue
        if bay is None:
            continue
        a, b = (int(m.group(2)), int(m.group(3))) if m.group(2) else (int(m.group(4)),) * 2
        if 1 <= a <= COLS and 1 <= b <= COLS:
            # '14-12' is read as the range 12~14 (conservative) and marked, so it is asked whether it is a typo (자료 4-8·p392)
            out.append({"bay": bay, "c0": min(a, b), "c1": max(a, b), **({"rev": True} if a > b else {})})
    for b in dict.fromkeys(named):
        if not any(s["bay"] == b for s in out):
            out.append({"bay": b, "c0": None, "c1": None})
    return out


def _hm(s):
    m = re.search(r"(\d{1,2}):(\d{2})", s or "")
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else None


def _win(s, said_next=False):
    """'HH:MM~HH:MM' -> {start, end, next_day?}. An end before its start is read as the next day (the conservative,
    longer window) — marked assumed_next_day unless the foreman said so, so the pair asks 「익일인지 오기인지」 (자료 MT04)."""
    a, _, b = (s or "").partition("~")
    a, b = _hm(a), _hm(b)
    if not (a and b) or a == b:
        return None
    if a < b:
        return {"start": a, "end": b}
    return {"start": a, "end": b, "next_day": True, **({} if said_next else {"assumed_next_day": True})}   # 23:00~01:00


NEXT_SAID = re.compile(r"다음\s*날|익일|야간|자정\s*넘")


def _dated_win(start, end, day):
    """a plan's ISO start/end -> the part of it on `day`, the dates kept (Codex B 41·P1-4): minutes from `day`'s 00:00,
    an end on a later date runs on (next_day, and `days` past midnight — a two-day work is not cut at 23:59), a work
    that began on an earlier date is going at 00:00, one that is over before `day` is not on it (None). Without dates
    the times are read as before."""
    a, b = (start or "").partition("T"), (end or "").partition("T")
    if not (a[1] and b[1]) or not (ISO_DAY.fullmatch(a[0]) and ISO_DAY.fullmatch(b[0]) and ISO_DAY.fullmatch(day or "")):
        return _win(a[2] + "~" + b[2])
    from datetime import date
    ha, hb = _hm(a[2]), _hm(b[2])
    if not (ha and hb):
        return None
    d0 = date.fromisoformat(day)
    s = (date.fromisoformat(a[0]) - d0).days * 1440 + int(ha[:2]) * 60 + int(ha[3:])
    e = (date.fromisoformat(b[0]) - d0).days * 1440 + int(hb[:2]) * 60 + int(hb[3:])
    if e <= s or e <= 0 or s >= 1440:
        return None if e > s else _win(a[2] + "~" + b[2])    # not on this day / an end before its start: as written
    s = max(s, 0)
    w = {"start": f"{s // 60:02d}:{s % 60:02d}", "end": f"{(e % 1440) // 60:02d}:{e % 60:02d}"}
    if e > 1440 or (e == 1440):
        w.update(next_day=True, **({"days": e // 1440} if e // 1440 > 1 or e % 1440 == 0 else {}))
    return w


def _day_wins(allw, day, said_next=False):
    """a permit's windows on `day` from its dated rows ({date: ['HH:MM~HH:MM']}): that day's, and the part of the day
    before's window that runs past midnight, from 00:00 (Codex final #7)"""
    wins = [w for w in (_win(x, said_next) for x in allw.get(day) or []) if w]
    wins += [{"start": "00:00", "end": w["end"], "from_prev": True, **({"assumed_next_day": True} if w.get("assumed_next_day") else {})}
             for w in (_win(x, said_next) for x in allw.get(_prev_day(day)) or []) if w and w.get("next_day") and w["end"] != "00:00"]
    return wins


def _prev_day(day):
    from datetime import date, timedelta
    try:
        return (date.fromisoformat(day) - timedelta(days=1)).isoformat()
    except (TypeError, ValueError):
        return ""


def spanned_dates(windows):
    """the dates a set of dated windows ({date: ['HH:MM~HH:MM' | '…~익일 HH:MM']}) is on, the next date included when a
    window runs past midnight (the submission date index, Codex final #7)"""
    from datetime import date, timedelta
    out = set()
    for d, ws in (windows or {}).items():
        out.add(d)
        for w in ws or []:
            m = re.search(r"~\s*익일\s*(\d{1,2}:\d{2})|~\s*(\d{1,2}:\d{2})\s*$", str(w))
            a = re.match(r"\s*(\d{1,2}:\d{2})", str(w))
            nxt = "익일" in str(w) or (m and a and m.group(2) and m.group(2) < a.group(1).zfill(5))
            if nxt:
                try:
                    out.add((date.fromisoformat(d) + timedelta(days=1)).isoformat())
                except ValueError:
                    pass
    return sorted(out)


ISO_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")


def _num(s):
    m = re.search(r"\d+", str(s or ""))
    return int(m.group()) if m else None


def _rev(*texts):
    """What a document holds (values, answers, checklist), short: a 자료 확인 mark is for this content only."""
    import hashlib
    return hashlib.sha1("\x00".join(texts).encode()).hexdigest()[:12]


@lru_cache(maxsize=2)
def _load(path, stamp):
    db, files = Path(path), next(f for d, f in _HOMES if str(d) == path)
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    meta = {r["key"]: r["value"] for r in c.execute("SELECT key, value FROM meta")}
    day = meta.get("date", "")
    permits, plans = [], []
    for r in c.execute("SELECT * FROM permits ORDER BY permit_no"):
        fields = json.loads(r["fields"])
        val = {}
        for f in fields.values():
            val.setdefault(f["key"], f["value"])        # a value printed on two pages: the first one
        records = json.loads(r["records"])
        ck = json.loads(r["checklist"])
        items = [it for P in ck["permits"] for it in P["items"]]
        route = next((x["value"] for x in records if x.get("item") == "L5" and x.get("value")), "")
        # T6 'the block only moves 15:40~16:10': the move inside the permit's hours, kept apart from them
        move = next((m.groups() for x in records if x.get("item") == "T6"
                     for m in [re.search(r"(\d{1,2}:\d{2})\s*[~-]\s*(\d{1,2}:\d{2})", x.get("value") or "")] if m), None)
        allw = json.loads(r["windows"])
        said_next = any(x.get("item") == "T5" and NEXT_SAID.search(x.get("value") or "") for x in records)
        wins = _day_wins(allw, day, said_next)
        # 7일 단위 신청: a permit filed earlier for several work days is still running today (not in this day's 접수)
        days = sorted(d for d, ws in allw.items() if ws)
        status = {}
        for x in records:
            status[x["status"]] = status.get(x["status"], 0) + 1
        permits.append({
            "type": "permit", "id": r["permit_no"][-4:], "permit_no": r["permit_no"], "kind": r["kind"], "label": r["label"],
            "title": val.get("job", ""), "detail": val.get("job_detail", ""), "dept": val.get("department", ""),
            "place": r["place"], "route": route, "spans": spans(r["place"] + " " + route), "is_route": bool(route) or "→" in r["place"],
            "windows": wins, "start": wins[0]["start"] if wins else None, "end": wins[-1]["end"] if wins else None, "move": {"start": _hm(move[0]), "end": _hm(move[1])} if move else None,
            "rev": _rev(r["fields"], r["records"], r["checklist"]),
            # 정전·LOTO: the foreman's own plan of when the power goes off and comes back (LO3), as he said it
            "isolation": next((x["value"] for x in records if x.get("item") == "LO3" and x.get("value")), "") if r["kind"] == "loto" else "",
            "workers": _num(val.get("workers")), "hazards": val.get("hazards", ""),
            "concurrent": val.get("concurrent", ""), "permit_type": val.get("permit_type", "").strip("[]"),
            "double_check": val.get("double_check", ""), "applicant": val.get("req_name", ""), "applied": val.get("req_date", ""),
            "days": days, "works_today": bool(wins), "running": bool(days) and days[0] < day,
            "supervisor": val.get("supervisor", ""), "phone": val.get("supervisor_phone", ""),
            "answers": len(records), "answer_status": status, "unconfirmed": status.get("미확인", 0),
            "open_questions": len(json.loads(r["open_questions"])),
            "checklist": {s: sum(it["state"] == s for it in items) for s in checklist.STATES},
            "checklist_confirmed": all(it.get("touched") for it in items),
            "_file": files / r["file"], "_fields": fields, "_records": records, "_checklist": ck, "_sheets": json.loads(r["addendum"]),
        })
    for r in c.execute("SELECT * FROM workplans ORDER BY doc_no"):
        rec = json.loads(r["record"])
        it = {i["label"]: i["value"] for i in rec["items"]}
        plans.append({
            "type": "plan", "id": r["doc_no"], "doc_no": r["doc_no"], "company": r["company"], "title": r["title"],
            "place": r["location"], "spans": spans(r["location"]), "is_route": False,
            "windows": [w for w in [_dated_win(r["start"], r["end_"], day)] if w],
            "start": _hm(r["start"].partition("T")[2]), "end": _hm(r["end_"].partition("T")[2]),
            "workers": _num(it.get("작업인원")), "equipment": it.get("작업장비", ""), "materials": it.get("사용물질", ""),
            "height": it.get("작업높이", ""), "target": it.get("대상ID", ""), "rev": _rev(r["record"]), "boss": it.get("책임자", ""),
            "_file": files / r["file"], "_items": rec["items"],
        })
    c.close()
    return {"date": day, "factory": meta.get("factory", ""), "bays": BAYS, "cols": COLS, "permits": permits, "plans": plans}


def data():
    db, _ = _home()
    return _load(str(db), db.stat().st_mtime_ns)


def _public(d):
    return {k: (str(v) if isinstance(v, Path) else v) for k, v in d.items() if not k.startswith("_")}


def overview():
    d = data()
    return {**{k: d[k] for k in ("date", "factory", "bays", "cols")},
            "permits": [_public(p) for p in d["permits"]], "plans": [_public(p) for p in d["plans"]]}


def find(doc_id):
    d = data()
    for x in d["permits"] + d["plans"]:
        if x["id"] == doc_id or x.get("permit_no") == doc_id:
            return x
    raise KeyError(doc_id)


def detail(doc_id):
    x = find(doc_id)
    out = _public(x)
    if x["type"] == "permit":
        kind = PK.KINDS.get(x["kind"], {})
        out["form"] = [{"name": f["name"], "value": f["value"], "type": f["type"], "page": f.get("page")}
                       for f in x["_fields"].values() if f["type"] not in ("image",) and (f["type"] != "check" or f["value"])]
        out["records"] = [{k: r.get(k) for k in ("item", "question", "original", "answer", "value", "status", "source")}
                          for r in x["_records"]]
        out["checklist_items"] = [{k: it.get(k) for k in ("id", "title", "why", "state", "memo", "reasons")}
                                  | {"controls": [c["text"] for c in it.get("controls", []) if c.get("on")]}
                                  for P in x["_checklist"]["permits"] for it in P["items"]]
        out["kind_title"] = kind.get("title", "")
    else:
        out["items"] = [{"section": i.get("section"), "label": i["label"], "value": i["value"], "page": i.get("page")}
                        for i in x["_items"]]
    return out


def pdf(doc_id, part):
    """original: the PDF as it came in; full: permit + 추가검토서; checklist: the 위험 체크리스트 as the foreman confirmed it."""
    x = find(doc_id)
    if part == "original":
        return x["_file"].read_bytes()
    if x["type"] != "permit":
        raise KeyError(part)
    if part == "full":
        rplan = {L["pno"]: L["reflect"] for L in x["_sheets"] if L.get("reflect")}       # QA #37: the 반영본 as submitted
        return addendum.pdf(x["_file"].read_bytes(), [(None, None, L) for L in x["_sheets"]], x["_fields"], rplan)
    if part == "checklist":
        return checklist.pdf(x["_checklist"], x["_fields"])
    raise KeyError(part)

# ---------------------------------------------------------------- 제출본 → 관리자 입력 (design §6·§8.1, Codex A6)
# The foreman's latest submission of the day is the manager's input for that work: the facts his answers confirm,
# and the place and times his answers changed (his corrected 작업계획서 too). A submission whose number is not in the
# day's list is listed apart (「이 날 작업 목록에 없는 제출」), never dropped. Each document says which version its
# judgement uses: 서류 기준 (the documents as collected) or 제출본 반영.
VERSION_DOC, VERSION_SUB = "서류 기준", "제출본 반영"
OUTSIDE = "이 날 작업 목록에 없는 제출"
OTHER_DAY = "이 허가번호의 다른 작업일 제출"
NO_DAY = "작업일을 알 수 없는 제출(이 날 판정에 넣지 않음)"


def _hm_of(m):
    return f"{(m // 60) % 24:02d}:{m % 60:02d}"


def _day_windows(ws):
    """[(a, b)] minutes of one day -> [{start, end, next_day?, days?}] (an end past midnight runs into the next day; one
    two or more days on keeps how many, never cut at 23:59)"""
    return [{"start": _hm_of(a), "end": _hm_of(b), **({"next_day": True} if b >= 1440 else {}),
             **({"days": b // 1440} if b >= 2880 or (b >= 1440 and b % 1440 == 0) else {})} for a, b in sorted(ws)]


def submitted_values(payload, day, permit_no=None):
    """the place and this day's times a submission's answers set for its permit, where they differ from what the
    permit itself says -> {place?, windows?}; {} when the answers changed neither (or the payload cannot be read).
    The answers as read at 제출 (answers_read) when kept, else the answers as given."""
    from . import augment
    fields, answers = payload.get("fields") or {}, payload.get("answers_read") or payload.get("answers") or []
    # the base is the permit as uploaded (each field's original), so a value he corrected in the field itself counts too
    first = {k: {**f, "value": f.get("original", f.get("value"))} if isinstance(f, dict) else f for k, f in fields.items()}
    try:
        now, was = augment.effective(fields, answers), augment.effective(first, [])
    except (KeyError, TypeError, AttributeError, ValueError, IndexError):
        return {}
    P = next((x for x in now if x["permit_no"] == permit_no), None) or (now[0] if len(now) == 1 else None)
    P0 = P and next((x for x in was if x["permit_no"] == P["permit_no"]), None)
    if not P or not P0:
        return {}
    out = {}
    if P["place"]["text"] and P["place"]["text"] != P0["place"]["text"]:
        out["place"] = P["place"]["text"]
    on_day = lambda W: sorted((W.get(day) or []) + [(0, b - 1440) for a, b in W.get(_prev_day(day)) or [] if b > 1440])  # noqa: E731
    ws = on_day(P["windows"])                       # the day's windows and the part of the day before's that runs into it
    if ws and ws != on_day(P0["windows"]):
        out["windows"] = _day_windows(ws)          # the work's own window (windows_work: not stretched to the ember check)
    # the field contract of augment.effective (impl/multiturn.md): the ember-check end T4 goes in as a residual-only
    # extension — shown with a residual, never as its release; the stage written for T6/T1 is kept apart; full_end is
    # the whole work's end (already in the windows)
    per_day = lambda v: v.get(day) if isinstance(v, dict) else v          # noqa: E731  (a value per date, or one)
    res = per_day(P.get("residual"))
    if res is not None and ws:
        out["residual_end"] = _hm_of(res)          # a residual note only: never the release (multiturn 계약)
        if res >= 1440:
            out["residual_next_day"] = True
    stg = P.get("windows_stage") or {}
    mv = sorted((stg.get("move") or {}).get(day) or [])
    if mv and mv != ws:
        out["stage"] = _day_windows(mv)            # a lift's moving part (T1·확인된 추가 전달)
    wr = sorted((stg.get("written") or {}).get(day) or [])
    if wr and wr != ws:
        out["stage_written"] = _day_windows(wr)    # the stage the document had (T6 「특정 단계만」): kept, shown apart
    if per_day(P.get("full_end")) is not None and ws:
        out["full_end"] = _hm_of(per_day(P["full_end"]))
    return out


def plan_values(token, edits, checked):
    """at 제출: the confirmed plans' place and times with the foreman's edits in (kept in the snapshot, since the
    upload and its edits do not last) -> [{doc_no, title, place, start, end, changed: [location|start|end]}]"""
    from . import workplan
    recs = workplan.load_plans(token) if token else None
    out = []
    for i in checked or []:
        if not recs or not isinstance(i, int) or not 0 <= i < len(recs):
            continue
        rec, ed = recs[i], (edits or {}).get(str(i)) or {}
        by = {x.get("key"): x for x in rec.get("items") or [] if x.get("key")}
        vals, changed = {}, []
        for k in ("location", "start", "end"):
            x = by.get(k)
            if not x:
                continue
            v = str((ed.get(x["fk"], x.get("value")) if x.get("fk") else x.get("value")) or "").strip()
            if v != (x.get("value") or "").strip():
                changed.append(k)
            vals[k] = v
        out.append({"doc_no": rec.get("doc_no") or "", "title": rec.get("title") or "",
                    "place": vals.get("location", rec.get("location") or ""),
                    "start": workplan._iso(vals["start"]) if "start" in vals else rec.get("start") or "",
                    "end": workplan._iso(vals["end"]) if "end" in vals else rec.get("end") or "", "changed": changed})
    return out


def _plan_sub(pv, day):
    """a plan the foreman corrected in his submission -> {place?, windows?} for that plan's document of the day"""
    out = {}
    if "location" in (pv.get("changed") or []) and pv.get("place"):
        out["place"] = pv["place"]
    a, b = pv.get("start") or "", pv.get("end") or ""
    if {"start", "end"} & set(pv.get("changed") or []) and "T" in a and "T" in b:
        w = _dated_win(a, b, day)                   # the dated interval cut by the review day: a 10/31→11/2 change is on 11/1 too
        if w:
            out["windows"] = [w]
    return out


def _ver(summ, used, vals, by=None):
    return {"version": VERSION_SUB if used else VERSION_DOC, "sub": summ["id"], "created": summ.get("created"), "used": used,
            "values": {k: v for k, v in (("위치", vals.get("place")),
                                         ("시간", ", ".join(f"{w['start']}~{w['end']}" for w in vals.get("windows") or []))) if v},
            **({"by": by} if by else {})}


def hybrid_inputs(D, latest, get):
    """the day's latest submissions as rule input -> (confirmed {permit_no: facts}, submitted {doc_id: {place?,
    windows?}}, versions {doc_id: {version, sub, created, used: [what went in], values}}). A submission whose
    number is not in the day's list adds nothing here: submission_view lists it apart."""
    from . import pairs
    by_no = {p["permit_no"]: p for p in D["permits"]}
    plans = {p["id"]: p for p in D["plans"]}
    confirmed, submitted, versions = {}, {}, {}
    for pno, summ in sorted(latest.items(), key=lambda kv: kv[1].get("created") or 0):   # a later submission wins
        d = by_no.get(pno)
        if not d:
            continue
        got = get(summ["id"])
        payload = (got[0] if got else None) or {}
        from . import augment                             # lazy: the answers that stood against the submitted fields
        ans_ = augment.answers_now(payload["fields"], payload.get("answers")) if isinstance(payload.get("fields"), dict) else payload.get("answers")
        facts = pairs.confirmed_facts(ans_)
        vals = submitted_values(payload, D["date"], pno)
        if facts:
            confirmed[pno] = facts
        if vals:
            submitted[d["id"]] = vals
        used = (["위치"] if "place" in vals else []) + (["시간"] if "windows" in vals else []) + ([f"확인한 답 {len(facts)}건"] if facts else [])
        versions[d["id"]] = _ver(summ, used, vals)
        for pv in payload.get("plan_values") or []:
            P = plans.get(pv.get("doc_no"))
            ps = _plan_sub(pv, D["date"]) if P else {}
            if ps:
                submitted[P["id"]] = ps
                versions[P["id"]] = _ver(summ, [n for k, n in (("place", "위치"), ("windows", "시간")) if k in ps], ps, by=d["id"])
    return confirmed, submitted, versions


def submission_view(D, latest_day, latest_all, get):
    """the manager's view of the submissions -> {permit_no: the day's latest, with the version its judgement uses;
    "_outside": the submissions not in the day's list or of another work day; "_versions": {doc_id: version}; "_day"}"""
    _, _, versions = hybrid_inputs(D, latest_day, get)
    by_no = {p["permit_no"]: p for p in D["permits"]}
    out, outside = {}, []
    for pno, s in latest_day.items():
        if pno in by_no:
            out[pno] = {**s, "used": versions.get(by_no[pno]["id"])}
    for pno in dict.fromkeys(list(latest_day) + list(latest_all)):
        if pno not in by_no:
            outside.append({**(latest_all.get(pno) or latest_day[pno]), "why": OUTSIDE})
        elif pno in latest_all and latest_all[pno]["id"] != (out.get(pno) or {}).get("id"):
            outside.append({**latest_all[pno], "why": OTHER_DAY if latest_all[pno].get("dates") else NO_DAY})
    outside.sort(key=lambda s: -(s.get("created") or 0))
    return {**out, "_outside": outside, "_versions": versions, "_day": D["date"]}


def placement(permit_no, dates):
    """for the foreman's 제출 message: whether the manager's day list has this work -> {day, listed} or None"""
    try:
        D = data()
    except FileNotFoundError:
        return None
    return {"day": D["date"], "listed": any(p["permit_no"] == permit_no for p in D["permits"]) and D["date"] in (dates or [])}
