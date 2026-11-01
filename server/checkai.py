"""체크리스트 AI 추가 위험요인 (design §7): after the server's checklist (checklist.draft), the model may propose a few
more hazards — only items of the checklist catalog (checklist_spec.json) of another kind of work, never a hazard of
its own wording — each with the words of this work that show it. Nothing is added until the foreman puts it in
(「넣기」); then it is an item like the others, to be confirmed (해당 / 해당 없음 / 안전팀 확인).

What the model may do: pick up to MAX_PICKS candidates by short id, each with one run of words of the work facts.
What the server checks: the id is a candidate (another kind's item not already in this permit's list); the words are
in the work facts; the clause they stand in does not say no and is not about another team; the words speak of that
kind of work (KIND_WORDS). A failed or late call gives nothing; the base checklist is never changed, and a hazard the
model did not mention is never 「해당 없음」 because of it.

The same call (CHECKLIST, design §1.4·§7) also reads the base items: for an item it may say the work's words show
the hazard (support) or say it is not done (conflict), with those words and, for support, the item's own measures
(control ids) that fit. These readings never change an item's state or its basis; the server shows them by the
design's table: rule 해당 + support → the same basis shown; rule 확인 필요 + support → 「해당이면 골라 주세요」; rule
해당 없음 + support → 상충, chosen again (a 「해당 없음」 he chose stands only when chosen after the words were shown:
submissions.confirm_checklist); conflict → 「누구의 어떤 작업인지 확인해 판단」, 해당 stays the default. An item the
model does not mention is never 「해당 없음」 because of it.

A suggestion is kept per review, work facts, spec version and kind of permit (store.job, kind 「checkai:<hash>」): the
same facts give the same suggestion without calling the model again, each item and reading checked again against the
work as it is now before it is shown (_now: with its basis now, or left out). An item the foreman put in is never taken out by a
later result: it is checked again against the work as it is now (validate: the same checks as a pick), and when the
work changed or its words are gone it is 「재확인 필요」 until he confirms it again or takes it out (Codex final review #5).
"""
import asyncio
import hashlib
import json
import re

from . import addendum, augment, checklist, llm, store

SPEC = checklist.SPEC
CATALOG = hashlib.sha256(json.dumps([SPEC.get("kinds"), SPEC.get("common"), SPEC.get("cross")], ensure_ascii=False,
                                    sort_keys=True).encode()).hexdigest()[:12]
MAX_PICKS, MAX_QUOTE, MAX_CANDIDATES, MAX_MARKS = 3, 60, 24, 6
# two-letter pieces too common to show that words speak of an item
GENERIC = {"작업", "위험", "확인", "예정", "준비", "안전", "사람", "장소", "시간", "있을", "때문", "하는", "하여", "정할", "나누"}
FACT_FIELDS = (("job", "작업명"), ("job_detail", "작업 상세"), ("location", "작업장소"), ("location_detail", "상세 위치"),
               ("hazards", "유해위험요소"), ("notes", "추가정보"))
# the words that speak of each kind of work: a pick's quote must have one of its kind (a guard on relevance; the
# foreman still decides)
KIND_WORDS = {
    "hot": re.compile(r"용접|용단|절단|가우징|그라인|불티|화기|토치|산소|플라즈마|가열"),
    "confined": re.compile(r"탱크|밀폐|이중저|맨홀|보이드|코퍼댐|내부\s*진입|구획\s*내부"),
    "height": re.compile(r"고소|상부|추락|비계|사다리|고소작업대|갑판|높이|\d+(?:\.\d+)?\s*m|\d+\s*미터"),
    "lifting": re.compile(r"인양|크레인|호이스트|리깅|중량물|턴오버|반전|탑재|체인\s*블록"),
    "loto": re.compile(r"정전|전원|차단|LOTO|잠금|배전|패널|MCC|분전"),
}
SAYS_NO = re.compile(r"없|않|아니|말고|무관|안\s*(?:함|합|해|하|씀|써|쓰|들어|나)|못\s*(?:함|합|해|하)|미사용|제외")
OTHER_TEAM = re.compile(r"(?:옆|다른|타|상대|저쪽)\s*(?:팀|업체|반|작업|회사)|[가-힣]{1,6}팀(?:은|이|도|의|에서|이랑|하고|\s)|들었")
MIXED = {"common_mixed"}                                    # the item about other teams' work beside ours
CLAUSE = re.compile(r"[,.;·/\n]|\s(?:그리고|또는|및)\s")
SYSTEM = ("너는 조선소 위험작업허가서의 위험 체크리스트를 돕는다. '작업 사실'을 읽고 두 가지를 한다.\n"
          "(1) picks: '후보 위험요인'(C1, C2…) 가운데 이 작업에 실제로 해당할 수 있는 것만 고른다. 최대 3개.\n"
          "(2) marks: '기본 항목'(B1, B2…) 가운데 작업 사실에 그 위험이 있다는 말이 있으면 m=support, 그 일을 하지 않는다는 말이 "
          "있으면 m=conflict로 표시한다. support이면 그 항목의 조치 id 중 맞는 것을 k에 고른다. 최대 6개. 언급이 없으면 표시하지 않는다.\n"
          "규칙:\n"
          "1. id는 주어진 것만 쓴다. 새 위험요인·조치를 만들지 않는다.\n"
          "2. 근거로 작업 사실에서 이어진 한 구절을 그대로 quote에 붙인다. 구절이 없으면 고르지 않는다.\n"
          "3. 다른 팀 이야기는 근거가 아니다. 애매하면 고르지 않는다.")


class Stale(Exception):
    """a put-in AI item no longer holds for the work facts as they are (its words gone, or its basis changed)"""


def _norm(s):
    return re.sub(r"[\s\"'“”‘’「」『』.,·…]", "", s or "")


def _all_items():
    """every catalog item with its kind: [(kind, item)] (common items have kind None)"""
    out = [(k, it) for k, v in SPEC["kinds"].items() for it in v["items"]]
    return out + [(None, it) for it in SPEC["common"]]


def spec_item(iid):
    """(kind, catalog item) for an id, or (None, None)"""
    return next(((k, it) for k, it in _all_items() if it["id"] == iid), (None, None))


# the way candidates are chosen: part of the kept suggestion's key, so a kept result of an older choice is not reused
POLICY = "relevance-then-kinds/2026-11-01"


def _item_words(it):
    return _bigrams(" ".join([it.get("title", ""), it.get("why", "")] + [k.get("text", "") for k in it.get("controls", [])]))


def candidates(kind, base_items, lines=None):
    """the catalog items of the other kinds of work not already in this permit's list (by id or title): [(kind, item)].
    Relevance first (Codex review 2026-11-01 #4): the items whose words share a two-letter piece with the work facts
    (lines), most shared first, taken in turn from each kind; then the others in turn from each kind (catalog order),
    so every kind is offered and an item the work speaks of (잔불, 아크, 소음, 온열 …) is not cut by the limit."""
    have_ids = {it["id"] for it in base_items}
    have_titles = {_norm(it["title"]) for it in base_items}
    fw = _bigrams(" ".join(ln.split(": ", 1)[-1] for ln in lines or []))
    per, seen = {}, set()
    for k, it in _all_items():
        if k in (None, kind) or it["id"] in have_ids or _norm(it["title"]) in have_titles or _norm(it["title"]) in seen:
            continue
        seen.add(_norm(it["title"]))
        per.setdefault(k, []).append((len(fw & _item_words(it)), (k, it)))

    def turns(lists):
        out = []
        for i in range(max((len(x) for x in lists), default=0)):
            out += [x[i] for x in lists if i < len(x)]
        return out
    hit = [[c for n, c in sorted((x for x in v if x[0] > 0), key=lambda x: -x[0])] for v in per.values()]
    rest = [[c for n, c in v if n == 0] for v in per.values()]
    return (turns(hit) + turns(rest))[:MAX_CANDIDATES]


def facts(P, answers):
    """the work facts of this permit as lines: its own values, then the foreman's answers about his own work (not
    another team's, not 「모름」, not a checking answer)"""
    lines = []
    for key, name in FACT_FIELDS:
        v = re.sub(r"\s+", " ", augment._v(P["p"], key) or "").strip()
        if v:
            lines.append(f"{name}: {v}")
    pid = P["permit_no"]
    for a in checklist.standing(answers):                  # withdrawn (C6) and corrected (C5); a stale one is not a fact
        if a.get("qid") in P.get("stale", ()):
            continue
        q, item = a.get("qid", ""), a.get("qid", "").split(":")[0]
        if q.startswith("FREE:") or q.split(":")[1:2] != [pid] or a.get("choice") in ("unknown", None):
            continue
        if item in augment.ABOUT_OTHERS or item.split(".")[0] in augment.ABOUT_OTHERS or item.startswith(("A1.", "A2.", "A3.", "U1.", "C5.", "C6.")):
            continue
        if a.get("pid") and a.get("who") not in (None, "self"):
            continue
        label = next((c.get("label") for c in (a.get("q") or {}).get("choices", []) if c.get("id") == a.get("choice")), "")
        said = re.sub(r"\s+", " ", " ".join(x for x in (label, a.get("value") or "") if x)).strip()
        if said:
            slot = addendum.ITEM.get(item) or addendum.ITEM.get(item.split(".")[0]) or item
            lines.append(f"반장 답({slot}): {said}")
    return lines


def digest(lines):
    return hashlib.sha256(json.dumps(lines, ensure_ascii=False).encode()).hexdigest()[:12]


def _words(quote, lines):
    """-> (the quoted words, the lines to look in): a quote that carries the name of its line (「유해위험요소: 용접흄,
    소음」, 「반장 답(추가정보): 사다리는 쓰지 않음」) is the words without it, looked up in the lines of that name
    first. Every match of a quote goes through it — the clause, its source, the kind's words, the item's words
    (Codex persona A10: the clause was found without the name but its source with it, so 「반장 답」 showed as 「서류」)."""
    quote = str(quote or "").strip()
    head, _, rest = quote.partition(": ")
    named = [ln for ln in lines if head.strip() in ln.split(": ", 1)[0]] if rest.strip() and head.strip() else []
    if named:
        return rest.strip(), named + [ln for ln in lines if ln not in named]
    return quote, lines


def _find(quote, lines):
    """-> (the line, the clause of it) the quoted words stand in, or ('', '')"""
    quote, lines = _words(quote, lines)
    q = _norm(quote)
    for ln in lines if q else []:
        body = ln.split(": ", 1)[-1]
        for c in CLAUSE.split(body):
            if q in _norm(c):
                return ln, c
        if q in _norm(body):
            return ln, body
    return "", ""


def _clause(quote, lines):
    """the clause of the facts the quoted words stand in, or ''"""
    return _find(quote, lines)[1]


def source(quote, lines):
    """where the quoted words are: 「서류」 (a value of the permit) or 「반장 답」 (an answer)"""
    return "반장 답" if _find(quote, lines)[0].startswith("반장 답") else "서류"


def _bigrams(s):
    w = re.sub(r"[^가-힣A-Za-z0-9]", "", s or "")
    return {w[i:i + 2] for i in range(len(w) - 1)} - GENERIC


def relevant(quote, it):
    """the words speak of the item: a two-letter piece of its title, reason or measures is in them"""
    return bool(_bigrams(quote) & _bigrams(" ".join([it.get("title", ""), it.get("why", "")] + [k.get("text", "") for k in it.get("controls", [])])))


def why_not(kind, quote, lines):
    """why these words cannot stand for an item of that kind of work in these facts, or None"""
    cl = _clause(quote, lines) if quote else ""
    if not cl:
        return "구절이 작업 사실에 없음"
    if SAYS_NO.search(cl):
        return "하지 않는다는 문장"
    if OTHER_TEAM.search(cl):
        return "다른 팀 이야기"
    if not KIND_WORDS[kind].search(_words(quote, lines)[0]):          # the words, not the name of their line
        return "그 작업 종류의 말이 구절에 없음"
    return None


def method_digest(P):
    """the work's method and equipment as written (작업명·상세·유해위험요소): what an AI item's measures stand on"""
    return digest([P["kind"]] + [augment._v(P["p"], k) for k in checklist.METHOD_FIELDS])


def check_marks(marks, base_items, lines):
    """the model's readings of the base items -> ({item id: {m, quote, src, controls, id}}, dropped [b, why]): the
    item is one of this list; the words are in the facts and not another team's; they speak of the item; support is
    not a sentence that says no, conflict is one; the measures are the item's own"""
    bmap = {f"B{i}": it for i, it in enumerate(base_items, 1)}
    out, dropped = {}, []
    for x in marks[:MAX_MARKS] if isinstance(marks, list) else []:
        it, m = bmap.get(str(x.get("b", ""))), x.get("m")
        quote = str(x.get("quote") or "").strip()[:MAX_QUOTE]
        if not it or m not in ("support", "conflict"):
            dropped.append([x.get("b"), "항목이 아님"]); continue
        if it["id"] in out:
            dropped.append([it["id"], "같은 항목 두 번"]); continue
        cl = _clause(quote, lines) if quote else ""
        if not cl:
            dropped.append([it["id"], "구절이 작업 사실에 없음", quote]); continue
        if OTHER_TEAM.search(cl) and it["id"] not in MIXED:             # another team's work is what 병행·혼재 is about
            dropped.append([it["id"], "다른 팀 이야기", quote]); continue
        if bool(SAYS_NO.search(cl)) != (m == "conflict"):
            dropped.append([it["id"], "하지 않는다는 말이 아님" if m == "conflict" else "하지 않는다는 문장", quote]); continue
        if not relevant(_words(quote, lines)[0], it) and not (it["id"] in MIXED and OTHER_TEAM.search(cl)):
            dropped.append([it["id"], "그 항목의 말이 구절에 없음", quote]); continue
        own = {f"{x2['id']}" for x2 in it.get("controls", [])}
        ks = [k for k in (x.get("k") if isinstance(x.get("k"), list) else []) if k in own][:3] if m == "support" else []
        out[it["id"]] = {"m": m, "quote": quote, "src": source(quote, lines), "controls": ks,
                         "id": digest([it["id"], m, quote])}
    return out, dropped


def check(picks, cands, lines, wd="", md=""):
    """the model's picks -> (items, dropped [id, why]); every rule of the module's docstring"""
    cmap = {f"C{i}": c for i, c in enumerate(cands, 1)}
    out, dropped, seen = [], [], set()
    for p in picks[:MAX_PICKS] if isinstance(picks, list) else []:
        c = cmap.get(str(p.get("c", "")))
        quote = str(p.get("quote") or "").strip()
        if not c:
            dropped.append([p.get("c"), "후보가 아님"]); continue
        kind, it = c
        if it["id"] in seen:
            dropped.append([it["id"], "같은 항목 두 번"]); continue
        why = why_not(kind, quote, lines)
        if why:
            dropped.append([it["id"], why, quote]); continue
        seen.add(it["id"])
        out.append(item_of(kind, it, quote, wd, source(quote, lines), md))
    return out, dropped


def item_of(kind, it, quote, wd="", src="서류", md=""):
    """a suggestion as a checklist item: put in, it is confirmed like the others (auto 「안전팀 확인」, untouched); its
    해당 여부 stands on the work facts (wd), its measures on the work's method and equipment (md, design §7)"""
    label = SPEC["kinds"][kind]["label"]
    reasons = [f"AI 추가 후보({label} 작업 위험요인) · 근거 「{quote}」"]
    controls = [{**k, "permit_key": None, "on": False, "pre": k["id"] in it.get("preselect", [])} for k in it.get("controls", [])]
    basis = hashlib.sha256(json.dumps(["A", SPEC.get("version", 1), it["id"], it["title"], it.get("why", ""), quote,
                                       [(k["id"], k.get("text")) for k in it.get("controls", [])], wd], ensure_ascii=False).encode()).hexdigest()[:12]
    basis_ctl = hashlib.sha256(json.dumps(["A", SPEC.get("version", 1), it["id"], [(k["id"], k.get("text")) for k in it.get("controls", [])], md],
                                          ensure_ascii=False).encode()).hexdigest()[:12]
    return {"id": "A:" + it["id"], "spec": it["id"], "kind": kind, "basis": basis, "basis_ctl": basis_ctl, "ref": it.get("ref", ""), "title": it["title"],
            "why": it.get("why", ""), "common": False, "state": "check", "auto": "check", "reasons": reasons, "sources": [src], "controls": controls,
            "memo": "", "origin": "ai", "quote": quote, "quote_src": src}


def _schema(cids, bids=None, kids=None):
    props = {"picks": {
        "type": "array", "maxItems": MAX_PICKS, "items": {"type": "object", "additionalProperties": False, "required": ["c", "quote"],
            "properties": {"c": {"type": "string", "enum": cids}, "quote": {"type": "string", "maxLength": MAX_QUOTE}}}}}
    if bids:
        props["marks"] = {"type": "array", "maxItems": MAX_MARKS, "items": {"type": "object", "additionalProperties": False,
            "required": ["b", "m", "quote"], "properties": {"b": {"type": "string", "enum": bids}, "m": {"type": "string", "enum": ["support", "conflict"]},
                "quote": {"type": "string", "maxLength": MAX_QUOTE}, "k": {"type": "array", "maxItems": 3, "items": {"type": "string", "enum": kids or ["-"]}}}}}
    return {"type": "object", "additionalProperties": False, "required": ["picks"] + (["marks"] if bids else []), "properties": props}


def _one(fields, answers):
    """the one permit of the file with its base checklist, or (None, None)"""
    perms = [P for P in augment.effective(fields, answers) if P["kind"] in SPEC["kinds"]]
    if len(perms) != 1:
        return None, None
    d = checklist.draft(fields, answers)
    base = next((x for x in d["permits"] if x["permit_no"] == perms[0]["permit_no"]), None)
    return perms[0], base


def validate(P, base, lines, iid, quote, answers):
    """a put-in AI item, as it is for the work now -> (item, None) or (None, why): the same checks as a pick (another
    kind's catalog item not in this permit's list; the words in the facts, not said no, not another team's, of that
    kind of work), its basis on the work as it is now"""
    kind, it = spec_item(str(iid or "")[2:]) if str(iid or "").startswith("A:") else (None, None)
    if not it or kind is None:
        return None, "카탈로그 항목이 아님"
    if kind == P["kind"] or any(x["id"] == it["id"] or _norm(x["title"]) == _norm(it["title"]) for x in base["items"]):
        return None, "이 허가서 목록에 이미 있음"
    why = why_not(kind, str(quote or "").strip()[:MAX_QUOTE], lines)
    if why:
        return None, why
    q = str(quote).strip()[:MAX_QUOTE]
    return item_of(kind, it, q, checklist.work_digest(P, answers), source(q, lines), method_digest(P)), None


def _key(P, lines):
    """the kept suggestion's key: the facts, the spec's version, the catalog itself and the way candidates are chosen
    (Codex review #8: the spec's version alone kept an older result after the catalog grew), and the kind of permit"""
    return "checkai:" + digest([SPEC.get("version", 1), CATALOG, POLICY, P["kind"]] + lines)


STATE_KO = {"yes": "해당", "no": "해당 없음", "check": "확인 필요"}


async def _run(P, base, lines, sid, wd=""):
    cands = candidates(P["kind"], base["items"], lines)
    bitems = [it for it in base["items"] if not str(it["id"]).startswith(("A:", "U"))]
    if not lines or (not cands and not bitems):
        return {"status": "none", "items": [], "marks": {}, "why": "후보나 작업 사실이 없음"}
    cl = "\n".join(f"C{i} [{SPEC['kinds'][k]['label']}] {it['title']} — {it.get('why', '')}" for i, (k, it) in enumerate(cands, 1)) or "(없음)"
    bl = "\n".join(f"B{i} [{STATE_KO.get(it['auto'], '')}] {it['title']} · 조치 " + ", ".join(f"{k['id']}={k.get('text', '')[:24]}" for k in it.get("controls", []))
                   for i, it in enumerate(bitems, 1))
    user = f"작업 종류: {SPEC['kinds'][P['kind']]['label']}\n작업 사실:\n" + "\n".join(lines) + f"\n후보 위험요인:\n{cl}\n기본 항목:\n{bl}"
    kids = sorted({k["id"] for it in bitems for k in it.get("controls", [])})
    try:
        data, meta = await llm.call_json("CHECKLIST", [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
                                         _schema([f"C{i}" for i in range(1, len(cands) + 1)] or ["C0"], [f"B{i}" for i in range(1, len(bitems) + 1)] or None, kids),
                                         think=0, out_tokens=360, deadline=120.0, sid=sid, pri=llm.PREPARED)
    except llm.LlmFail as e:
        return {"status": "fail", "items": [], "marks": {}, "why": e.code}
    if not isinstance(data.get("picks"), list):
        return {"status": "fail", "items": [], "marks": {}, "why": "schema"}
    items, dropped = check(data["picks"], cands, lines, wd, method_digest(P))
    marks, mdropped = check_marks(data.get("marks") or [], bitems, lines)
    return {"status": "ok" if items or marks else "none", "items": items, "marks": marks, "dropped": dropped + mdropped, "ms": meta.get("ms")}


_TASKS = {}


def recheck(P, base, lines, answers, keep):
    """the items he put in, each as it is for the work now: {id: {ok, item | why}} (keep: [{id, quote}]). Never
    a removal: an item that no longer holds is reported, and stays until he takes it out or keeps it as his own."""
    out = {}
    for k in (keep or [])[:12]:
        if not isinstance(k, dict) or not str(k.get("id", "")).startswith("A:"):
            continue
        item, why = validate(P, base, lines, k.get("id"), k.get("quote"), answers)
        out[str(k["id"])] = {"ok": True, "item": item} if item else {"ok": False, "why": why}
    return out


def _now(out, P, base, lines, answers):
    """a kept (or shared) result as it is for the work now (Codex persona A5: a suggestion kept under the same words
    carried the basis of the work before 작업인원 3→5, so putting it in was refused at the submission): each item
    checked again and given its basis now (validate; one that no longer holds is dropped), each reading of a base item
    checked again against this list and these facts (check_marks; one that no longer holds is dropped)"""
    items = [x for x, _ in (validate(P, base, lines, it.get("id"), it.get("quote"), answers) for it in out.get("items") or []
                            if isinstance(it, dict)) if x]
    bitems = [it for it in base["items"] if not str(it["id"]).startswith(("A:", "U"))]
    pos = {it["id"]: f"B{i}" for i, it in enumerate(bitems, 1)}
    marks, _ = check_marks([{"b": pos.get(k, ""), "m": m.get("m"), "quote": m.get("quote"), "k": m.get("controls") or []}
                            for k, m in (out.get("marks") or {}).items() if isinstance(m, dict)], bitems, lines)
    status = ("ok" if items or marks else "none") if out.get("status") in ("ok", "none") else out.get("status")
    return {**out, "status": status, "items": items, "marks": marks}


async def suggest(fields, answers, sid, keep=None):
    """-> {status: ok|none|fail, items, facts, kept}: the suggestion for the work facts as they are, made once per
    review, facts, spec version and kind (asked again, the kept one; while it is being made, the same run is awaited);
    kept: the items he put in (keep: [{id, quote}]) checked against the work as it is now (recheck), whatever the
    model says this time. answers: the review's normalized answers (the same as the checklist's)."""
    P, base = _one(fields, answers)
    if not P or not base:
        return {"status": "none", "items": [], "why": "허가서 한 건이 아님", "kept": {}}
    lines = facts(P, answers)
    kind, wd = _key(P, lines), checklist.work_digest(P, answers)
    h = kind.split(":", 1)[1]
    kept_items = recheck(P, base, lines, answers, keep)
    kept = store.job(sid, kind) if sid else None
    if kept and kept.get("status") in ("ok", "none"):
        return {**_now(kept, P, base, lines, answers), "facts": h, "kept": kept_items}
    key = (sid, h)
    task = _TASKS.get(key)
    if not task or task.done() and task.cancelled():
        task = asyncio.ensure_future(_run(P, base, lines, sid, wd))
        _TASKS[key] = task
    try:
        out = await asyncio.shield(task)
    except asyncio.CancelledError:
        if task.cancelled():                              # taken from the slot by a more urgent call: not done
            _TASKS.pop(key, None)
            return {"status": "fail", "items": [], "why": "preempted", "facts": h, "kept": kept_items}
        raise
    _TASKS.pop(key, None)
    if sid and out["status"] in ("ok", "none"):
        if store.start_job(sid, kind):
            store.finish_job(sid, kind, out["status"], {"items": out["items"], "marks": out.get("marks") or {}})
    return {**_now(out, P, base, lines, answers), "facts": h, "kept": kept_items}       # a shared run may be of an older basis


def marks_cached(sid, fields, answers):
    """the readings of the base items kept for the work facts as they are now ({item id: mark}), each checked again
    against them (_now), or {} — never a model call (the submission checks a 「해당 없음」 against what was shown)"""
    if not sid:
        return {}
    P, base = _one(fields, answers)
    if not P or not base:
        return {}
    lines = facts(P, answers)
    kept = store.job(sid, _key(P, lines))
    return _now(kept, P, base, lines, answers)["marks"] if kept and kept.get("status") in ("ok", "none") else {}


def attach(draft, sid, fields, answers, sent):
    """the server's draft with the AI items the foreman put in (sent with id 「A:…」 and their words, quote), each
    checked against the work facts as they are now (validate — not against a kept suggestion: a new model result
    never takes one out), as draft items with their basis now (submissions.confirm_checklist then refuses one he
    confirmed on an older basis, like the other items). Raises Stale when one no longer holds (its words gone from the
    work, said no, another team's): he takes it out or keeps it as his own item (U…)."""
    put = [(str(P.get("permit_no")), it) for P in (sent or {}).get("permits", []) if isinstance(P, dict) and isinstance(P.get("items"), list)
           for it in P["items"] if isinstance(it, dict) and str(it.get("id", "")).startswith("A:")]
    if not put:
        return draft
    P, base = _one(fields, answers)
    if not P or not base:
        raise Stale(str(put[0][1].get("id")))
    lines = facts(P, answers)
    out = {**draft, "permits": [dict(x, items=list(x["items"])) for x in draft["permits"]]}
    for pno, it in put:
        x, why = validate(P, base, lines, it.get("id"), it.get("quote"), answers)
        if not x or pno != P["permit_no"]:
            raise Stale(f"{it.get('id')}: {why or '다른 허가서'}")
        tgt = next(q for q in out["permits"] if q["permit_no"] == pno)
        if not any(y["id"] == x["id"] for y in tgt["items"]):
            tgt["items"].append({k: v for k, v in x.items() if k not in ("spec", "kind", "origin")})
    return out
