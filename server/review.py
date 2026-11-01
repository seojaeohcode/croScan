"""Rule checks on the (edited) form values. The rules decide; the chat model only
explains them and asks the questions. Each finding:
  {"page", "keys": [...], "kind": blank|format|logic|question, "msg"}
"""
import re
from datetime import date, datetime

from . import permit_kinds as PK

FORMATS = {
    "code": r"[A-Z0-9]+(?:-[A-Z0-9]+)*",
    "phone": r"0\d{1,2}-[\dX]{3,4}-[\dX]{4}",     # X = masked digit in the sample file
    "count": r"\d{1,3}",
    "number": r"\d+(?:\.\d+)?",
    "date": r"\d{4}-\d{2}-\d{2}",
    "time": r"\d{2}:\d{2}",
    "yn": r"[YN]",
    "name": r"[가-힣A-Za-z]{1,10}",
}
# a location precise enough to place the work on the yard map: bay / column / grid
PRECISE_PLACE = re.compile(r"(?i)\bBAY\b|\d+\s*BAY|칼럼|COL|\d+\s*[-~]\s*\d+|구역|번지|열\b|도크|정반")


def valid(ftype, v):
    if ftype in ("check", "image", "text") or v in ("", None):
        return True
    rx = FORMATS.get(ftype)
    if not rx or not re.fullmatch(rx, str(v).strip()):
        return False
    if ftype == "date":
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            return False
    if ftype == "time":
        h, m = map(int, v.split(":"))
        return 0 <= h < 24 and 0 <= m < 60
    return True


def _pages(fields):
    out = {}
    for fk, f in fields.items():
        out.setdefault(f["page"], {})[f["key"]] = f
    return out


def _d(v):
    try:
        return datetime.strptime(v, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _t(v):
    try:
        h, m = map(int, v.split(":"))
        return h * 60 + m
    except (AttributeError, ValueError):
        return None


# 근로기준법 제56조 제3항 야간근로 「오후 10시부터 다음 날 오전 6시 사이」, in minutes from a row's day (a row may end
# the next day). It is the law's line for the night premium, not what a permit's 주간·야간 tick means: a tick on the
# other side of it is asked about (T7, the 논리 note below), never called wrong.
LEGAL_NIGHT = ((0, 6 * 60), (22 * 60, 30 * 60), (46 * 60, 54 * 60))
NOONS = (12 * 60, 36 * 60)


def legal_night_only(a, b):
    """a window (minutes, a < b; b may pass midnight) wholly inside the statutory night: 01:00~04:00, 23:00~익일 05:00"""
    return any(s <= a and b <= e for s, e in LEGAL_NIGHT)


def plain_day(a, b):
    """a window with no minute in the statutory night that runs across noon: 10:00~15:00, not 12:00~15:00. An evening a
    site may call 야간 (18:00~21:00) never runs across noon, so it is never this."""
    return not any(a < e and s < b for s, e in LEGAL_NIGHT) and any(a < n < b for n in NOONS)


def work_days(p):
    rows = []
    for i in range(1, 8):                     # the form has 7 date rows
        d, a, b = (p.get(f"{k}_{i}", {}).get("value", "") for k in ("date", "from", "to"))
        if d or a or b:
            rows.append((i, d, a, b))
    return rows


def _num(v):
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def _kind_label(p):
    kind = next((f.get("kind") for f in p.values() if f.get("kind")), None)
    return PK.KINDS[kind]["label"] if kind in PK.KINDS else "?"


def check(fields, cross=False):
    """cross=True adds permit-against-permit findings (안전관리자 view); the 작업반장 view checks each permit alone."""
    out = []
    pages = _pages(fields)
    for no, p in sorted(pages.items()):
        def add(keys, kind, msg):
            out.append({"page": no, "keys": [f"p{no}.{k}" for k in keys], "kind": kind, "msg": msg})

        # the picked kind's 추가정보 items were not found on this page: most likely the wrong kind was picked
        picked = _kind_label(p)
        if not any(f.get("group") == "추가정보" for f in p.values()):
            out.append({"page": no, "keys": [f"p{no}.permit_no"], "kind": "question", "level": "high",
                        "msg": f"고른 종류({picked})의 추가정보 항목을 이 쪽에서 찾지 못함 → 허가서 종류를 다시 확인하세요"})
        for k, f in p.items():
            if f["type"] in ("check", "image") or k.startswith(("date_", "from_", "to_")):
                continue
            v = f.get("value", "")
            if f["required"] and not str(v).strip():
                add([k], "blank", f"'{f['name']}' 칸이 비어 있음")
            elif not valid(f["type"], v):
                add([k], "format", f"'{f['name']}' 값 '{v}'이(가) 형식({f['type']})에 맞지 않음")
        rows = work_days(p)
        if not rows:
            add(["date_1"], "blank", "작업 일시(날짜·시간)가 하나도 없음")
        days = []
        for i, d, a, b in rows:
            if not (d and a and b):
                add([f"date_{i}", f"from_{i}", f"to_{i}"], "blank", f"{i}일차 작업일/시작/종료 중 빈칸이 있음")
            for k, v, t in ((f"date_{i}", d, "date"), (f"from_{i}", a, "time"), (f"to_{i}", b, "time")):
                if v and not valid(t, v):
                    add([k], "format", f"{i}일차 '{v}' 형식 오류")
            if _t(a) is not None and _t(b) is not None and _t(b) <= _t(a):
                add([f"from_{i}", f"to_{i}"], "logic", f"{i}일차 종료({b})가 시작({a})보다 늦지 않음")
            if _d(d):
                days.append((i, _d(d)))
        for (i, d1), (j, d2) in zip(days, days[1:]):
            if d2 <= d1:
                add([f"date_{i}", f"date_{j}"], "logic", f"{j}일차 날짜({d2})가 {i}일차({d1})보다 앞이거나 같음")
        first = min((d for _, d in days), default=None)
        rq, ap = _d(p.get("req_date", {}).get("value")), _d(p.get("app_date", {}).get("value"))
        if first and rq and rq > first:
            add(["req_date"], "logic", f"허가신청일({rq})이 첫 작업일({first})보다 늦음")
        if first and ap and ap > first:
            add(["app_date"], "logic", f"전산승인일({ap})이 첫 작업일({first})보다 늦음")
        if rq and ap and ap < rq:
            add(["app_date"], "logic", f"전산승인일({ap})이 신청일({rq})보다 빠름")
        day, night = p.get("day", {}).get("value"), p.get("night", {}).get("value")
        if day and night:
            add(["day", "night"], "logic", "주간과 야간이 둘 다 체크됨")
        if not day and not night:
            add(["day", "night"], "blank", "주간/야간 중 아무것도 체크되지 않음")
        # the tick against the time, by the statutory night only (the same line as T7): a 주간 row wholly in it, or a
        # 야간 permit whose every row is plainly daytime; an evening extension is not noted (no site shift is assumed)
        # only readable times, end after start: a reversed row (its next-morning end not confirmed here) is not read
        span = [(i, _t(a), _t(b)) for i, d, a, b in rows if a and b and valid("time", a) and valid("time", b) and _t(b) > _t(a)]
        dark = [i for i, a, b in span if legal_night_only(a, b)]
        if day and not night and dark:
            add([f"from_{i}" for i in dark] + [f"to_{i}" for i in dark], "logic",
                f"주간 체크인데 {', '.join(f'{i}일차' for i in dark)} 시간이 모두 22:00~다음 날 06:00 사이 → 체크와 시간 확인")
        if night and not day and span and len(span) == len(rows) and all(plain_day(a, b) for _, a, b in span):
            add(["night"] + [f"from_{i}" for i, _, _ in span], "logic", "야간 체크인데 모든 날 시간이 낮(정오를 지나고 22:00~06:00에 걸치지 않음) → 체크와 시간 확인")
        if p.get("height_work", {}).get("value") and not p.get("work_height", {}).get("value"):
            add(["height_work", "work_height"], "blank", "고소작업이 체크됐는데 작업높이가 없음")
        if p.get("pressure_use", {}).get("value") and not (p.get("test_pressure", {}).get("value") and p.get("pipe_diameter", {}).get("value")):
            add(["pressure_use", "test_pressure", "pipe_diameter"], "blank", "압력사용이 체크됐는데 테스트압력/파이프직경이 없음")
        lw, swl = _num(p.get("load_weight", {}).get("value")), _num(p.get("crane_swl", {}).get("value"))
        if lw is not None and swl is not None and lw > swl:
            add(["load_weight", "crane_swl"], "logic", f"인양물 중량 {lw:g}톤이 크레인 정격하중 {swl:g}톤을 넘음")
        loc = " ".join(str(p.get(k, {}).get("value", "")) for k in ("location", "location_detail"))
        if loc.strip() and not PRECISE_PLACE.search(loc):
            add(["location", "location_detail"], "question",
                f"작업장소 '{loc.strip()}'에 BAY·칼럼 같은 세부 위치가 없어 같은 공장 안 다른 작업과 겹치는지 판단할 수 없음")
        if not str(p.get("concurrent", {}).get("value", "")).strip():
            add(["concurrent"], "question", "병행여부(같은 시간·공간의 다른 작업 유무)가 비어 있음")
    # pages with one 승인번호 are copies (제출용 / 게시용) of one permit: they must agree;
    # pages with different numbers are different permits: check them against each other
    by_no = {}
    for no, p in sorted(pages.items()):
        by_no.setdefault(str(p.get("permit_no", {}).get("value", "")).strip().upper() or f"#{no}", []).append(no)
    for pno, nos in by_no.items():
        for a, b in zip(nos, nos[1:]):
            pa, pb = pages[a], pages[b]
            for k in sorted(set(pa) & set(pb)):
                fa, fb = pa[k], pb[k]
                if fa["type"] == "image" or str(fa["value"]) == str(fb["value"]):
                    continue
                show = lambda f: ("체크" if f["value"] else "빈칸") if f["type"] == "check" else (f["value"] or "(빈칸)")
                out.append({"page": 0, "keys": [f"p{a}.{k}", f"p{b}.{k}"], "kind": "logic",
                            "msg": f"같은 허가서({pno})의 {a}쪽·{b}쪽 사본에서 '{fa['name']}' 값이 다름: '{show(fa)}' / '{show(fb)}'"})
    # permits against each other: the same pair logic the 추가검토서 uses (server/augment.py), on the permit values
    from . import augment
    clash = {}
    for x in (augment.pairs(augment.effective(fields, [])) if cross else []):
        if x["level"] > 3:
            continue
        keys = [f"p{x['a']}.location", f"p{x['b']}.location"]
        head = f"{x['a']}쪽({x['a_who'].split(' ')[1].split('(')[0]}) × {x['b']}쪽({x['b_who'].split(' ')[1].split('(')[0]})"
        if x["level"] == 1:
            out.append({"page": 0, "keys": keys, "kind": "logic", "level": "high",
                        "msg": f"{head}: {x['why']}, 같은 시간({x['when']}) → 함께 할 수 있는지, 순서·중지 조건 확인 필요"})
        elif x["level"] == 2:
            out.append({"page": 0, "keys": keys, "kind": "question", "level": "normal",
                        "msg": f"{head}: {x['why']}, 시간 겹침({x['when']}) → 낙하·이동·불티·가스 경로가 서로 닿는지 확인 필요"})
        else:
            out.append({"page": 0, "keys": keys, "kind": "question", "level": "normal",
                        "msg": f"{head}: 시간 겹침({x['when']}), {x['why']}"})
            continue
        clash.setdefault(x["a"], set()).add(x["b"])
        clash.setdefault(x["b"], set()).add(x["a"])
    return out
