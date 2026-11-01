"""허가 검토 신호 (design §6.5·§19.2): a 작업계획서 says it does a step that a permit covers (용접·절단, 밀폐 진입, 고소,
인양, 정전), and among the day's permits that croScan looked at none of that kind is at the same place or block at an
overlapping time. Then the safety manager is asked to check — never told 「허가서가 없다」 or 「허가 대상」:

    대응 허가서를 확인해 주세요 → 계획서 "구절" → 조회 범위 → 이 범위에서 찾지 못함

The rules read the plan's own action lines (작업명·작업범위·작업사양·단계·장비), one clause at a time, and tell apart
doing a hot work from inspecting a weld, checking a welder, a 「화기 금지」 sign, UT/RT. A step of a kind croScan does
not support (도장·유기용제, 방사선 투과검사, 압력·기밀시험) is a 「지원 범위 밖」 signal of its own. Lines the rules
cannot place may be offered to the model (suggest_ai), which only picks a kind per line; such a signal says
「AI 제안」. A signal changes no pair, no priority and no document: it is a line to check.
"""
import re

from . import augment, llm

KIND_KO = {"hot": "화기", "confined": "밀폐", "height": "고소", "lifting": "중량물인양", "loto": "정전·LOTO"}
RULES = [
    ("hot", re.compile(r"가용접|용접|용단|절단|가우징|그라인딩|토치|예열|가열|브레이징")),
    ("confined", re.compile(r"밀폐|탱크\s*내부|이중저|맨홀\s*진입|내부\s*진입|보이드\s*(?:스페이스|내부)")),
    ("height", re.compile(r"고소\s*작업|비계|족장|고소작업대|안전대\s*체결|상부\s*(?:작업|이동)")),
    ("lifting", re.compile(r"인양|양중|블록\s*반출|탑재|턴\s*오버|반전|크레인으로")),
    ("loto", re.compile(r"정전|LOTO|잠금\s*장치|전원\s*(?:차단|분리)|차단기\s*(?:내림|개방)")),
]
# the same words that are not doing that work (design §6.5: 용접 실시·용접부 검사·용접기 점검·화기 금지·UT/RT)
NOT_DOING = re.compile(r"검사|점검|확인|금지|여부|측정|UT|RT|PT|MT|비파괴|도면|대기|준비물|표지|용접기|완료|끝난|된\s*면")
OUT_OF_SCOPE = [("도장·유기용제", re.compile(r"도장|도료|유기용제|시너|희석제|스프레이")),
                ("방사선 투과검사", re.compile(r"방사선|\bRT\b|투과\s*검사")),
                ("압력·기밀시험", re.compile(r"압력\s*시험|기밀\s*시험|에어\s*테스트|수압\s*시험"))]
FIELDS = ("작업명", "작업범위", "작업사양", "작업장비")
CLAUSE = re.compile(r"[,·/;\n]|(?<!\d)\.(?!\d)")
_AI = {}


def _lines(plan):
    """the plan's action lines: (label, text)"""
    out = []
    for it in plan.get("_items") or plan.get("items") or []:
        lab = it.get("label") or ""
        if (lab in FIELDS or re.fullmatch(r"\d+\s*단계", lab)) and it.get("value"):
            out.append((lab, it["value"]))
    return out


def _m(hm):
    h, m = hm.split(":")
    return int(h) * 60 + int(m)


def _overlap(a, b):
    """two works' windows overlap (a work without a time is taken as the whole day: not ruled out)"""
    if not a.get("windows") or not b.get("windows"):
        return True
    for x in a["windows"]:
        for y in b["windows"]:
            x0, x1, y0, y1 = _m(x["start"]), _m(x["end"]), _m(y["start"]), _m(y["end"])
            x1, y1 = x1 + (1440 if x1 <= x0 else 0), y1 + (1440 if y1 <= y0 else 0)
            if x0 < y1 and y0 < x1:
                return True
    return False


def _near(plan, permit):
    """the same block/equipment number, or the same BAY with overlapping columns (or columns unknown)"""
    pt = " ".join([plan.get("title") or "", plan.get("place") or "", plan.get("target") or ""])
    qt = " ".join([permit.get("title") or "", permit.get("detail") or "", permit.get("place") or ""])
    if augment.ids(pt) & augment.ids(qt):
        return True
    for s in plan.get("spans") or []:
        for t in permit.get("spans") or []:
            if s["bay"] == t["bay"] and (s["c0"] is None or t["c0"] is None or (s["c0"] <= t["c1"] and t["c0"] <= s["c1"])):
                return True
    return False


def phrases(plan):
    """[(kind or None, scope-out name or None, label, clause)]: what the plan says it does, by the rules"""
    out, seen = [], set()
    for lab, text in _lines(plan):
        for cl in (c.strip() for c in CLAUSE.split(text)):
            if len(cl) < 2 or cl in seen:
                continue
            for name, rx in OUT_OF_SCOPE:
                if rx.search(cl) and not re.search(r"금지|여부|회수|보관|확인|완료|끝난|된\s*면", cl):
                    out.append((None, name, lab, cl)); seen.add(cl)
                    break
            else:
                for kind, rx in RULES:
                    if rx.search(cl) and not NOT_DOING.search(cl):
                        out.append((kind, None, lab, cl)); seen.add(cl)
                        break
    return out


def _signal(plan, kind, scope, lab, cl, D, ai=False):
    same = [p for p in D["permits"] if p.get("kind") == kind] if kind else []
    hit = [p for p in same if _near(plan, p) and _overlap(plan, p)]
    if kind and hit:
        return None
    if kind:
        rng = (f"{D.get('date', '')} 이 화면의 허가서 {len(D['permits'])}건 중 {KIND_KO[kind]} 허가서 {len(same)}건 · "
               "같은 블록·설비 번호 또는 같은 BAY·칼럼 · 시간 겹침")
        return {"plan": plan["id"], "kind": kind, "kind_ko": KIND_KO[kind], "title": "대응 허가서를 확인해 주세요", "quote": cl, "label": lab,
                "scope": rng, "found": "이 범위에서 찾지 못함", "ai": ai}
    return {"plan": plan["id"], "kind": None, "kind_ko": scope, "title": "지원 범위 밖 작업을 확인해 주세요", "quote": cl, "label": lab,
            "scope": "croScan이 다루는 허가 5종(화기·밀폐·고소·중량물인양·정전·LOTO) 밖의 작업",
            "found": "필요한 허가·절차는 기존 방식으로 확인", "ai": ai}


def signals(D, ai_kinds=None):
    """the day's signals, plan by plan: [{plan, kind, kind_ko, title, quote, label, scope, found, ai}].
    ai_kinds: {(plan id, clause): kind} picked by the model for clauses the rules did not place (suggest_ai)."""
    out = []
    for plan in D["plans"]:
        seen = set()
        for kind, scope, lab, cl in phrases(plan):
            if (kind, scope) in seen:
                continue                                      # one signal per kind and plan (its first phrase)
            s = _signal(plan, kind, scope, lab, cl, D)
            seen.add((kind, scope))
            if s:
                out.append(s)
        for (pid, cl), kind in (ai_kinds or {}).items():
            if pid == plan["id"] and kind in KIND_KO and (kind, None) not in seen:
                s = _signal(plan, kind, None, "AI 제안", cl, D, ai=True)
                seen.add((kind, None))
                if s:
                    out.append(s)
    return out


def _schema(cids):
    return {"type": "object", "additionalProperties": False, "required": ["k"], "properties": {"k": {
        "type": "array", "maxItems": len(cids), "items": {"type": "object", "additionalProperties": False, "required": ["c", "t"],
            "properties": {"c": {"type": "string", "enum": cids}, "t": {"type": "string", "enum": list(KIND_KO) + ["none"]}}}}}}


SYSTEM = ("너는 작업계획서의 작업 단계를 읽는 도우미다. 각 구절이 실제로 그 작업을 '하는' 단계인지 보고 종류를 고른다: "
          "hot(용접·절단 등 화기 작업), confined(밀폐공간 진입), height(높은 곳 작업), lifting(크레인 인양), loto(정전·전원 차단), "
          "none(그런 작업을 하지 않음 · 검사 · 점검 · 확인 · 금지 표지 · 모름). 애매하면 none.")


async def suggest_ai(plan, pri=None):
    """the clauses of a plan the rules placed in no kind (a verb of work in them), each given to the model to pick a
    kind or none -> {(plan id, clause): kind}; cached per plan revision; a failure gives nothing"""
    done = {cl for _, _, _, cl in phrases(plan)}
    rest = []
    for lab, text in _lines(plan):
        for cl in (c.strip() for c in CLAUSE.split(text)):
            if len(cl) >= 4 and cl not in done and cl not in rest and re.search(r"작업|설치|해체|제거|교체|이동|진입|조립|취부", cl):
                rest.append(cl)
    rest = rest[:8]
    if not rest:
        return {}
    k = (plan["id"], plan.get("rev"), tuple(rest))
    if k in _AI:
        return _AI[k]
    cids = [f"C{i}" for i in range(1, len(rest) + 1)]
    user = "\n".join(f"C{i} {cl}" for i, cl in enumerate(rest, 1))
    try:
        data, _ = await llm.call_json("PERMIT_SIGNAL", [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
                                      _schema(cids), think=0, out_tokens=20 * len(cids) + 16, deadline=60.0,
                                      pri=llm.WARM if pri is None else pri)
    except llm.LlmFail:
        return {}
    got = data.get("k") if isinstance(data, dict) else None
    out = {}
    for x in got if isinstance(got, list) else []:
        if isinstance(x, dict) and x.get("c") in cids and x.get("t") in KIND_KO:
            cl = rest[int(x["c"][1:]) - 1]
            if not NOT_DOING.search(cl):                     # an inspection or a sign stays out even if picked
                out[(plan["id"], cl)] = x["t"]
    _AI[k] = out
    if len(_AI) > 500:
        _AI.clear()
    return out
