"""위험 체크리스트 (작업반장 시점, 작업 전날): croScan drafts it from the permit alone (its values and the
작업반장's answers to the multi-turn questions about it, the 추가정보); the 작업계획서 are not used (a decision of the
team: the overlap with other work is the safety team's check). The 작업반장 confirms or changes every item; it goes
to the safety team with the permit and the plans.

What it is and is not
  - A day-before plan: for each hazard, 해당 여부 and the safety measures that will be prepared. It never says a
    day-of check was done: the 「현장 안전조치 및 추가정보」 block of the permit stays empty until the day (사전 작성 금지).
  - The items per kind and their rules are in checklist_spec.json (drafted from the research PDF, sections 1.4/2.3/2.5
    of each kind, and the legal articles in permit_kinds.py). A hazard starts as 확인 필요 unless a rule says
    otherwise; 해당 없음 is only set when the permit and the answers clearly say so (croScan never guesses it).

Two confirmations per item (design §7): applicability (해당 여부, `touched`) and the safety measures to prepare
(`ctl_touched`, needed when it is 해당). Each stands on its own basis: `basis` — the item, croScan's proposal and its
reasons, and the facts its rules read plus the work (work_digest: every work fact but the times and the people);
`basis_ctl` — the measures and the work's method and equipment (작업명·상세·유해위험요소) plus the answers its rules
read and the work's size (작업인원, height). A change of those facts expires only the
confirmation that stands on them. Every reason says where it comes from: (서류) the permit, (반장 답) an answer.

Rules (evaluable, see the spec's "rule" format):
  {"any"|"all": [rule…]}, {"not": rule}, {"head": key}, {"text": regex, "fields": [field keys]},
  {"denied": regex, "fields": [field keys]} (true only when the permit plainly says it is not so: 「산소 안 씀」 — never
  for silence), {"answer": qid prefix, "choice"?: id or [ids], "value"?: regex}, {"eff": name, "op": "…", "value": x};
  every rule may carry "reason" (shown to the 작업반장).
A 해당 없음 rule needs the permit's own words and a confirmed answer of the same permit (all), so silence, a blank or
「모름」 stays 확인 필요 (Codex review 2026-11-01 #2). A list denied at its end (「용접·절단 없음」) is denied as a whole;
an undecided word (미정·모름·여부) makes its clause not known (#6). The spec's "cross" adds another kind's items when
the work of this permit includes that kind of work (hot work inside a confined space, #4).
"""
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import addendum, augment
from . import permit_kinds as PK

MAX_PERMITS, MAX_ITEMS = 10, 40                     # a page never sends more (up to 24 items + what was added by hand)
SPEC = json.loads((Path(__file__).with_name("checklist_spec.json")).read_text(encoding="utf-8"))
STATES = {"yes": "해당", "no": "해당 없음", "check": "안전팀 확인"}
TEXT_FIELDS = ("hazards", "notes", "job", "job_detail", "location", "location_detail")
TICK = {"true", "1", "y", "yes", "■", "v", "✓", "o"}
OPS = {">=": lambda a, b: a >= b, ">": lambda a, b: a > b, "<=": lambda a, b: a <= b, "<": lambda a, b: a < b,
       "==": lambda a, b: a == b, "!=": lambda a, b: a != b}


def items_for(kind):
    """The kind's own items, then the common ones."""
    return list(SPEC["kinds"].get(kind, {}).get("items", [])) + list(SPEC["common"])


def _by_id(iid):
    return next((x for v in SPEC["kinds"].values() for x in v["items"] if x["id"] == iid), None)


def cross_for(kind):
    """the other kinds' items this kind's permit may carry (spec "cross"): [(rule, [items])]"""
    return [(c["when"], [_by_id(i) for i in c["items"] if _by_id(i)]) for c in SPEC.get("cross", {}).get(kind, [])]


def known_for(kind):
    """every item a permit of this kind can have: its own, the cross ones, the common ones (by id)"""
    out = {it["id"]: it for it in items_for(kind)}
    for _, its in cross_for(kind):
        out.update({it["id"]: it for it in its})
    return out


class _Ctx:
    """What the rules look at, for one permit."""

    def __init__(self, P, answers, one=True):
        self.P, self.p = P, P["p"]
        self.src = {}                                   # reason -> the sources it came from ({"서류", "반장 답"})
        pid = P["permit_no"]
        # this permit's answers by item ('T1', 'H2', 'A1.T1'), and the closing free answers (FREE:n) only when the file
        # has this one permit: a free answer is not tied to a permit, so with several it moves none of them (as
        # augment.effective: P["free"]; Codex review #7)
        self.ans = {}
        for a in standing(answers):                     # withdrawn (C6) out, C5 folded in, then a stale one out (one reading)
            if a.get("qid") in P.get("stale", ()):
                continue
            q = a["qid"]
            if (q.startswith("FREE:") and one) or q.split(":")[1:2] == [pid]:
                self.ans.setdefault(q.split(":")[0] if not q.startswith("FREE:") else "FREE", []).append(a)

    def head(self, key):
        return str(self.p.get(key, {}).get("value", "")).strip().lower() in TICK

    def text(self, keys):
        return "\n".join(augment._v(self.p, k) for k in keys)       # one field per line: its words stay its own (#10)

    def eff(self, name):
        P = self.P
        if name == "kind":
            return P["kind"]
        if name in ("layer", "place.layer"):
            return P["place"].get("layer", "")
        if name == "height":
            return P.get("height")
        if name == "concurrent":
            return P.get("concurrent", "")
        if name == "layer":
            return P["place"].get("layer", "")
        if name == "workers":
            return augment._num(augment._v(self.p, "workers"))
        if name.startswith("notes."):
            return P.get("notes", {}).get(name[6:], "")
        if name.startswith("facts."):                   # effective.facts: {item: {choice, value}} of the answers that stand
            item, _, part = name[6:].partition(".")
            return (P.get("facts") or {}).get(item, {}).get(part or "choice", "")
        if name == "said":
            return P.get("said", "")
        return None


# where a rule's fact comes from: the permit as written (서류) or the foreman's answers (반장 답)
EFF_SRC = {"kind": "서류", "layer": "서류", "place.layer": "서류", "height": "서류", "workers": "서류", "said": "반장 답",
           "concurrent": "서류·반장 답"}


def _leaf_src(rule):
    """the sources of the facts a rule reads (all its leaves)"""
    if "any" in rule or "all" in rule:
        return set().union(*[_leaf_src(r) for r in rule.get("any") or rule.get("all") or []]) if (rule.get("any") or rule.get("all")) else set()
    if "not" in rule:
        return _leaf_src(rule["not"])
    if "answer" in rule:
        return {"반장 답"}
    if "denied" in rule:
        return {"서류"}
    if "eff" in rule:
        e = rule["eff"]
        return set(("반장 답" if e.startswith(("notes.", "facts.")) else EFF_SRC.get(e, "서류")).split("·"))
    return {"서류"}                                     # head, text: the permit's own fields


# an undecided word (미정·모름·여부 …) that speaks of the fact itself: right after it, through only words about doing it
# (「산소 사용 미정」, 「가스 사용 여부 모름」) — not another fact beside it (「CO2 용접 감시자 미정」: the welding stands;
# final Codex review #10)
UNSURE_WORDS = augment.UNDECIDED.pattern + r"|모름|모르|미상|불확실|정해지지|확인\s*(?:중|필요)"
ABOUT = (r"(?:\s*(?:은|는|이|가|을|를|도|의))?(?:\s*(?:사용|공급|여부|작업|방법|투입|주입|시행|실시|계획|일정|진행|유무|할지|할\s*지))*"
         r"(?:\s*(?:은|는|이|가|을|를|도))?")
UNSURE_AFTER = re.compile(r"^" + ABOUT + r"\s*(?:" + UNSURE_WORDS + ")")
SEG = re.compile(r"[,;\n/]|그리고|지만|(?<!\d)\.(?!\d)")         # '·' joins a list: it stays in one segment
GAP = re.compile(r"[\s·와과및,]*")


def says(t, rx):
    """augment.said with two more readings (Codex review #6): a list denied at its end is denied as a whole (「용접·절단
    없음」), and a fact an undecided word speaks of is not known (「산소 사용 미정」). Fields come joined by line breaks,
    so one field's words never reach another's. True / False / None."""
    t = t or ""
    if not re.search(rx, t):
        return False
    out, unsure, seen = [], False, False
    for seg in SEG.split(t):
        ms = list(re.finditer(rx, seg))
        if not ms:
            continue
        seen = True
        keep, i = seg, len(ms) - 1
        while i >= 0:                                   # runs of matches joined by 「·」「와」, the last one's tail
            j = i
            while j > 0 and GAP.fullmatch(seg[ms[j - 1].end():ms[j].start()]):
                j -= 1
            tail = seg[ms[i].end():]
            if UNSURE_AFTER.match(tail):
                unsure = True
            elif j < i and augment.NEG.search(tail[:8]):
                out.append(False)
            else:
                i = j - 1
                continue
            keep = keep[:ms[j].start()] + " " * (ms[i].end() - ms[j].start()) + keep[ms[i].end():]
            i = j - 1
        if re.search(rx, keep):
            out.append(augment.said(keep.replace("·", " "), rx))     # a word joined by 「·」 is read with its neighbour
    if not seen:                                        # a rule whose words span fields or clauses: read as before
        return augment.said(t.replace("\n", " "), rx)
    if True in out:
        return True
    if None in out or unsure:
        return None
    return False if out else None


def standing(answers):
    """the answers that stand: augment.live_answers (C6 「서류가 맞음」 took the earlier answer back), and an answer X
    the foreman corrected with C5.X 「추가로 적은 내용이 맞음」 is read as what he wrote there (typed words), not as the
    earlier choice — a withdrawn or corrected answer never moves an item"""
    live = augment.live_answers(answers)               # when augment folds C5 in too, the loop below changes nothing
    fixed = {}
    for a in live:
        q = str(a.get("qid", ""))
        if q.startswith("C5.") and a.get("choice") == "free" and ":" in q and not q.startswith("C5.concurrent:"):
            fixed[q.split(":")[0][3:] + ":" + q.split(":", 1)[1]] = (a.get("read") or a.get("value") or "").strip()
    out = []
    for a in live:
        if a.get("qid") in fixed:
            out.append({**a, "choice": "text", "value": fixed[a["qid"]], "read": fixed[a["qid"]]})
        else:
            out.append(a)
    have = {a.get("qid") for a in out}
    out += [{"qid": q, "choice": "text", "value": v, "read": v, "q": {}} for q, v in fixed.items() if q not in have]
    return out


def _tag(c, rule, ok):
    if ok is True and rule.get("reason"):
        c.src.setdefault(rule["reason"], set()).update(_leaf_src(rule))


def source_of(src):
    """{"서류", "반장 답"} -> 「서류」 / 「반장 답」 / 「서류·반장 답」"""
    return "·".join(x for x in ("서류", "반장 답") if x in src) or "서류"


def _match(rule, c):
    """-> (True / False / None, [reasons that made it true]). None is 'not known': a hedged or conditional mention
    ('아마 연결돼 있음', '없으면'), a 「모름」 answer, an empty value. It never makes a rule true, and 'not' of it
    stays None, so an unsure opposite never turns an item into 해당 없음 (Kleene logic)."""
    def R(ok):
        _tag(c, rule, ok)
        return ok, [rule["reason"]] if ok is True and rule.get("reason") else []
    if "any" in rule:
        got = None if rule["any"] else False
        unknown = False
        for r in rule["any"]:
            ok, why = _match(r, c)
            if ok is True:                            # the plain reason that matched, else the group's
                if not why:
                    _tag(c, rule, True)
                return True, why or ([rule["reason"]] if rule.get("reason") else [])
            unknown |= ok is None
        return (None if unknown else False), []
    if "all" in rule:
        whys, unknown = [], False
        for r in rule["all"]:
            ok, why = _match(r, c)
            if ok is False:
                return False, []
            unknown |= ok is None
            whys += why
        if not unknown and rule.get("reason"):
            _tag(c, rule, True)
        return (None, []) if unknown else (True, [rule["reason"]] if rule.get("reason") else whys)
    if "not" in rule:
        ok, _ = _match(rule["not"], c)
        return R(None if ok is None else not ok)
    if "head" in rule:
        f = c.p.get(rule["head"])
        return R(None if f is None else str(f.get("value", "")).strip().lower() in TICK)
    if "text" in rule:
        # says(): '가스 안 씀' is False, '다른 작업 없으면' / '아마' / '미정' are None; not mentioned at all is False
        t, rx = c.text(rule.get("fields") or TEXT_FIELDS), "(?i)" + rule["text"]
        return R(says(t, rx))
    if "denied" in rule:
        # the permit plainly says it is not so; not mentioned is False (silence is not absence), hedged is None
        t, rx = c.text(rule.get("fields") or TEXT_FIELDS), "(?i)" + rule["denied"]
        v = says(t, rx)
        return R(None if v is None else (re.search(rx, t) is not None and v is False))
    if "answer" in rule:
        pre, choice, value = rule["answer"], rule.get("choice"), rule.get("value")
        choices = [choice] if isinstance(choice, str) else choice
        got = None                                    # not asked or not answered: not known
        for item, lst in c.ans.items():
            if item != pre and not item.startswith(pre + "."):
                continue
            for a in lst:
                if a.get("choice") == "unknown" and choices != ["unknown"]:
                    continue                          # 「모름」 stays not known
                # a plain typed 「없음」 is read as the no-choice (augment.eff_choice: one unconditional denial only;
                # 「없는 줄 알았는데 있어요」, conditions, corrections stay typed words)
                if choices and augment.eff_choice(item, a) not in choices:
                    got = False if got is None else got
                    continue
                v = True if not value else says(a.get("value", "") or "", "(?i)" + value)
                if v is True:
                    return R(True)
                got = v if got is None else got
        if got is None and rule.get("missing") is False:     # a guard: no answer (or 「모름」) says nothing against it
            return R(False)
        return R(got)
    if "eff" in rule:
        v, want, op = c.eff(rule["eff"]), rule.get("value"), rule.get("op", "==")
        if op == "present":
            return R(bool(v))
        if v in (None, ""):                           # unknown is never a match (and never 0)
            return R(None)
        if op == "in":
            return R(str(v).upper() in {str(x).upper() for x in (want or [])})
        if op == "re":                                  # the words of an answered fact, read as a text rule
            return R(says(str(v), "(?i)" + str(want)))
        if op in OPS:
            try:
                return R(OPS[op](float(v), float(want)) if isinstance(want, (int, float)) else OPS[op](str(v).upper(), str(want).upper()))
            except (TypeError, ValueError):
                return R(None)
        return R(None)
    return R(None)


def evaluate(item, c):
    """-> state, reasons, preselected control ids. 해당 and 해당 없음 both true (the permit and an answer disagree)
    is 확인 필요, with both reasons shown."""
    pre = item.get("prefill", {})
    yes, no = [], []
    for side, out in (("yes", yes), ("no", no)):
        for r in pre.get(side, []):
            ok, why = _match(r, c)
            if ok is True:
                out += why or [r.get("reason", "")]
    yes, no = list(dict.fromkeys(x for x in yes if x)), list(dict.fromkeys(x for x in no if x))
    if yes and no:
        return "check", [f"근거가 엇갈림 — 해당: {'; '.join(yes)} / 해당 없음: {'; '.join(no)}"], []
    if yes:
        return "yes", yes, item.get("preselect", [])
    if no:
        return "no", no, []
    return "check", [], []


def _key(k, kind):
    """A control's day-of permit item: one key, or one per kind for a common item."""
    pk = k.get("permit_key")
    return pk.get(kind) if isinstance(pk, dict) else pk


PEOPLE = re.compile(r"phone|tel|name$|supervisor$|manager$|signer|sign|approv|성명|이름|연락처|전화|서명|승인|결재", re.I)
# the times: the work-date rows, the sign-off dates, the time answers and their checks (a time is not a hazard fact)
TIME_KEY = re.compile(r"^(?:date|from|to)_\d+$|_date$")
TIME_ANS = ("T", "A1.", "A2.", "A3.")


def work_digest(P, answers):
    """the work facts every confirmation of this permit's checklist stands on (design §7 basis_digest): the permit's
    values (not people, phone numbers, signatures or approvals, not the times) and this permit's answers (question,
    choice, value; not the time answers), with the checklist spec's version and the kind of permit. Every item's
    해당 여부 stands on it, so any change of the work — the head count too — expires every 해당 여부 confirmation, on
    purpose not item by item (Codex final review #3: 「크레인 OH-21-02 아래에서 용접」 written into the work left all 14
    confirmations standing; Codex persona A5: 작업인원 3→5 left them standing). A time-only change expires none."""
    vals = sorted((str(k), augment._v(P["p"], k)) for k, f in P["p"].items()
                  if isinstance(f, dict) and not PEOPLE.search(str(k)) and not PEOPLE.search(str(f.get("name") or ""))
                  and not TIME_KEY.search(str(k)) and augment._v(P["p"], k))
    pid = P["permit_no"]
    said = sorted((str(a.get("qid", "")).split(":")[0], str(a.get("choice") or ""), str(a.get("value") or "").strip())
                  for a in standing(answers) if a.get("qid") not in P.get("stale", ())
                  and (str(a.get("qid", "")).startswith("FREE:") or str(a.get("qid", "")).split(":")[1:2] == [pid])
                  and not str(a.get("qid", "")).startswith(TIME_ANS))
    return hashlib.sha256(json.dumps([SPEC.get("version", 1), P["kind"], vals, said], ensure_ascii=False).encode()).hexdigest()[:12]


METHOD_FIELDS = ("job", "job_detail", "hazards")          # the work's method and equipment, as written


def _inputs(rule, out=None):
    """what a rule reads: {"fields": {keys}, "heads": {keys}, "answers": {prefixes}, "effs": {names}}"""
    out = out if out is not None else {"fields": set(), "heads": set(), "answers": set(), "effs": set()}
    for r in (rule.get("any") or rule.get("all") or []):
        _inputs(r, out)
    if "not" in rule:
        _inputs(rule["not"], out)
    if "head" in rule:
        out["heads"].add(rule["head"])
    if "text" in rule or "denied" in rule:
        out["fields"].update(rule.get("fields") or TEXT_FIELDS)
    if "answer" in rule:
        out["answers"].add(rule["answer"])
    if "eff" in rule:
        out["effs"].add(rule["eff"])
    return out


def _said(c, prefixes):
    return sorted((item, str(a.get("choice") or ""), str(a.get("value") or "").strip()) for item, lst in c.ans.items()
                  for a in lst if any(item == p or item.startswith(p + ".") for p in prefixes))


# answers that do not describe the work's hazards: the times (T…), the head counts, the checking questions
NOT_WORK = ("T", "B1.workers", "B2.workers", "A1.", "A2.", "A3.", "U1.", "C5.", "C6.")


def facts_of(it, c):
    """-> (the facts its 해당 여부 stands on, the facts its safety measures stand on) for one item: the values its rules
    read, the work's text, the answers that describe the work (where, how, with what), the kind (draft adds the whole
    work, work_digest); for the measures, the work's method and equipment, the answers its rules read and the work's
    size: how many work and how high (a lock and a roll call per worker, the fall protection — Codex persona A5)"""
    ins = {"fields": set(), "heads": set(), "answers": set(), "effs": set()}
    for side in ("yes", "no"):
        for r in it.get("prefill", {}).get(side, []):
            _inputs(r, ins)
    vals = lambda keys: sorted((k, augment._v(c.p, k)) for k in keys)
    said = _said(c, ins["answers"])
    work = sorted((item, str(a.get("choice") or ""), str(a.get("value") or "").strip()) for item, lst in c.ans.items()
                  for a in lst if not item.startswith(NOT_WORK))
    app = [c.P["kind"], vals(set(TEXT_FIELDS) | ins["fields"]), sorted((h, c.head(h)) for h in ins["heads"]),
           sorted((e, str(c.eff(e))) for e in ins["effs"]), said, work]
    size = [str(c.eff("workers")), str(c.eff("height")), _said(c, ("B1.workers", "B2.workers"))]
    ctl = [c.P["kind"], vals(METHOD_FIELDS), said, size]
    return app, ctl


def _h(x):
    return hashlib.sha256(json.dumps(x, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()[:12]


def draft(fields, answers):
    """One checklist per permit: {"permits": [{permit_no, kind, label, who, facts, items: [...]}]}"""
    out = []
    perms = augment.effective(fields, answers)
    for P in perms:
        if P["kind"] not in SPEC["kinds"]:
            continue
        c = _Ctx(P, answers, one=len(perms) == 1)
        wd = work_digest(P, answers)
        items = []
        extra = []                                      # another kind's items this work includes (spec "cross")
        for rule, its in cross_for(P["kind"]):
            c.src = {}
            if _match(rule, c)[0] is True:
                extra += [x for x in its if x not in extra]
        own = list(SPEC["kinds"][P["kind"]]["items"])
        for it in own + extra + list(SPEC["common"]):
            c.src = {}
            state, why, sel = evaluate(it, c)
            fa, fc = facts_of(it, c)
            # 해당 여부: the item, croScan's proposal and reasons, the facts its rules read and the work (wd: every
            # work fact but the times and the people); 안전조치: the measures, the work's method·equipment, the answers
            # its rules read and the work's size (design §7)
            # the item's own wording of where it applies (why) too: a widened scope asks again (Codex review #3)
            basis = _h([SPEC.get("version", 1), it["id"], it["title"], it.get("why", ""), state, why, fa, wd])
            basis_ctl = _h([SPEC.get("version", 1), it["id"], [(k["id"], k.get("text")) for k in it.get("controls", [])], fc])
            srcs = [source_of(c.src.get(r, set()) or ({"서류", "반장 답"} if r.startswith("근거가 엇갈림") else {"서류"})) for r in why]
            items.append({"id": it["id"], "basis": basis, "basis_ctl": basis_ctl, "ref": it.get("ref", ""), "title": it["title"], "why": it.get("why", ""),
                          "cases": it.get("cases", []),             # the case book's accidents of the same hazard (reviewed pairing)
                          "common": it in SPEC["common"], "state": state, "auto": state, "reasons": why, "sources": srcs,
                          "controls": [{**k, "permit_key": _key(k, P["kind"]), "on": k["id"] in sel, "pre": k["id"] in it.get("preselect", [])}
                                       for k in it.get("controls", [])], "memo": ""})
        out.append({"permit_no": P["permit_no"], "kind": P["kind"], "label": P["label"], "who": augment._who(P), "facts": wd, "items": items})
    return {"version": SPEC.get("version", 1), "permits": out}


# ---------------------------------------------------------------- the sheet (PDF / HTML), same frame as the 추가검토서
def clean(chk):
    """The checklist as sent by the page, reduced to known items and plain values (anything else is dropped)."""
    out = []
    perms = (chk or {}).get("permits", []) if isinstance(chk, dict) else []
    if not isinstance(perms, list) or len(perms) > MAX_PERMITS:
        raise ValueError(f"허가서는 {MAX_PERMITS}건까지입니다")
    for P in perms:
        if not isinstance(P, dict):
            continue
        if isinstance(P.get("items"), list) and len(P["items"]) > MAX_ITEMS:
            raise ValueError(f"위험요인은 허가서 1건에 {MAX_ITEMS}개까지입니다 (지금 {len(P['items'])}개)")
        known = known_for(P.get("kind"))
        items = []
        for it in [x for x in P.get("items", []) if isinstance(x, dict)] if isinstance(P.get("items"), list) else []:
            base = known.get(it.get("id"))
            if not base and str(it.get("id", "")).startswith("A:"):              # A:…: an AI suggestion the 작업반장 put in (design §7)
                base = next((x for v in SPEC["kinds"].values() for x in v["items"] if x["id"] == str(it["id"])[2:]), None)
            if not base and not str(it.get("id", "")).startswith("U"):          # U…: items the 작업반장 added
                continue
            state = it.get("state") if it.get("state") in STATES else "check"
            ctrls = {k["id"]: k for k in (base or {}).get("controls", [])}
            sel = [k for k in (it.get("controls") if isinstance(it.get("controls"), list) else []) if isinstance(k, dict) and k.get("on")]
            items.append({"id": str(it.get("id")), "title": (base or {}).get("title") or str(it.get("title", ""))[:80],
                          "state": state, "auto": it.get("auto") if it.get("auto") in STATES else None,
                          "reasons": [str(x)[:160] for x in (it.get("reasons") if isinstance(it.get("reasons"), list) else [])][:4],
                          "controls": [ctrls[k["id"]]["text"] if k.get("id") in ctrls else str(k.get("text", ""))[:120] for k in sel][:8],
                          "memo": str(it.get("memo", ""))[:300], "touched": bool(it.get("touched")), "common": bool((base or {}).get("id") in {x["id"] for x in SPEC["common"]}),
                          "ctl_touched": bool(it.get("ctl_touched")) or str(it.get("id", "")).startswith("U"),
                          "sources": [str(x)[:12] for x in (it.get("sources") if isinstance(it.get("sources"), list) else [])][:4]})
        out.append({"permit_no": str(P.get("permit_no", ""))[:40], "kind": P.get("kind"), "items": items})
    return out


def layout(P, when, who):
    e = addendum._e
    B = [{"t": "note", "h": e("작업 전날 croScan이 허가서(추가정보·확인 질문의 답 포함)로 채운 위험요인과 준비할 안전조치(계획)입니다. 작업반장이 확인했는지는 "
                             "항목마다 표시합니다. 당일 작업 시작 전 확인은 "
                             "허가서의 「현장 안전조치 및 추가정보」 칸에 따로 합니다. 이 목록은 TBM 교육이나 조치 이행의 완료 기록이 아닙니다. "
                             "전산승인은 생산부서 승인권한자가, 현장 확인과 (2중점검 Y 작업의) 대면허가는 안전 측이 기존 절차대로 합니다. croScan은 승인하지 않습니다.")}]
    n = {s: sum(1 for it in P["items"] if it["state"] == s) for s in STATES}
    left = sum(1 for it in P["items"] if not it["touched"])
    B.append({"t": "kv", "rows": [("요약", f"해당 {n['yes']} · 안전팀 확인 {n['check']} · 해당 없음 {n['no']} (전체 {len(P['items'])})"),
                                  ("작업반장 확인", f"{len(P['items']) - left} / {len(P['items'])}" + (
                                      addendum._s(f"<br>확인 전 {left}개는 croScan 초안 그대로입니다(반장이 고르지 않음).") if left else ""))]})
    no = 0                                  # QA #90: one run of numbers through both groups, as on the screen
    for title, group in ((f"1. {P['label']} 작업 위험요인" if P.get("label") else "1. 이 작업의 위험요인", [it for it in P["items"] if not it["common"]]),
                         ("2. 공통 위험요인", [it for it in P["items"] if it["common"]])):
        if not group:
            continue
        B.append({"t": "bar", "h": title})
        rows = []
        for it in group:
            no += 1
            st = STATES[it["state"]]
            if not it["touched"]:
                st += addendum._s("<br>(반장 확인 전)")
            elif it["state"] == "yes" and not it.get("ctl_touched"):
                st += addendum._s("<br>(조치 확인 전)")
            if it["auto"] and it["auto"] != it["state"]:
                st += addendum._s(f"<br>(croScan: {STATES[it['auto']]})")
            ctrl = "<br>".join(f"· {e(x)}" for x in it["controls"]) or ("-" if it["state"] == "no" else "(정하지 않음)")
            if it["memo"]:
                ctrl += f"<br>메모: {e(it['memo'])}"
            srcs = it.get("sources") or []
            basis = "<br>".join(e(x) + (f" ({e(srcs[i])})" if i < len(srcs) and srcs[i] else "") for i, x in enumerate(it["reasons"])) \
                or ("작업반장 추가" if it["id"].startswith("U") else "-")
            rows.append([f"{no:02d}", e(it["title"]), st, ctrl, addendum._s(basis)])
        B.append({"t": "table", "w": [0.06, 0.27, 0.13, 0.34, 0.20], "head": ["번호", "위험요인", "해당 여부", "준비할 안전조치(계획)", "근거"],
                  "rows": rows})
    return {"title": "위험 체크리스트 (작업반장)", "head": [("승인번호", e(P["permit_no"])), ("작성", e(who)), ("작성 시각", when)], "blocks": B}


def sheets(chk, fields):
    when = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M")
    perms = {P["permit_no"]: P for P in augment._permits(fields)}
    out, seen = [], set()
    for P in clean(chk):
        if P["permit_no"] not in perms or P["permit_no"] in seen:       # only the permits of this file, once each
            continue
        seen.add(P["permit_no"])
        p = perms[P["permit_no"]]["p"]
        who = " · ".join(x for x in (augment._v(p, "department"), augment._v(p, "supervisor")) if x) or "작업반장"
        if P["kind"] in PK.KINDS:
            who = f"{PK.KINDS[P['kind']]['label']} · {who}"
        out.append(layout(P, when, who))
    return out


def merge(draft, sent):
    """design §7: the server's own base list with the foreman's choices put in (by id, on the same basis); a base
    item he left out or chose on another basis is printed as the draft has it, not yet chosen (확인 전) — a base item
    never drops out of the paper. His own items (U…) and the AI items he put in (A:…) follow, as cleaned."""
    sent_perms = {str(P.get("permit_no")): P for P in clean(sent)}
    stray = set(sent_perms) - {P["permit_no"] for P in draft["permits"]}
    if stray:                                       # a permit of another file: the page and the file disagree
        raise ValueError(f"이 파일에 없는 허가서: {', '.join(sorted(stray))[:80]}")
    raw ={(str(P.get("permit_no")), str(it.get("id"))): it for P in (sent or {}).get("permits", []) if isinstance(P, dict)
           for it in P.get("items", []) if isinstance(it, dict)} if isinstance(sent, dict) else {}
    out = []
    for P in draft["permits"]:
        mine = {it["id"]: it for it in (sent_perms.get(P["permit_no"]) or {}).get("items", [])}
        items = []
        for it in P["items"]:
            o, r = mine.get(it["id"]), raw.get((P["permit_no"], it["id"]), {})
            if o and r.get("basis") == it.get("basis"):
                # measures chosen on other wording (basis_ctl) are printed as not yet confirmed (Codex review #5)
                items.append(o if r.get("basis_ctl") == it.get("basis_ctl") else {**o, "ctl_touched": False})
            else:
                items.append({"id": it["id"], "title": it["title"], "state": it["state"], "auto": it.get("auto"), "reasons": it.get("reasons", [])[:4],
                              "controls": [k["text"] for k in it.get("controls", []) if k.get("on")][:8], "memo": "", "touched": False,
                              "common": it.get("common", False), "ctl_touched": False, "sources": it.get("sources", [])[:4]})
        items += [o for k, o in mine.items() if k.startswith(("U", "A:"))]
        out.append({"permit_no": P["permit_no"], "kind": P.get("kind"), "items": items})
    return {"permits": out}


def pdf(chk, fields) -> bytes:
    import pymupdf
    doc = pymupdf.open()
    for L in sheets(chk, fields):
        addendum._draw(doc, L)
    if not doc.page_count:
        raise ValueError("체크리스트가 비어 있습니다")
    doc.subset_fonts()                                # only the glyphs used (the full Korean font is 5 MB)
    from .workplan_pdf import fix_tounicode           # '·' copies as '·', not '・' (NanumGothic)
    fix_tounicode(doc)
    return doc.tobytes(garbage=3, deflate=True)
