"""요청형 「왜?」 (EXPLAIN, design §5.3~§5.5·§19.2): the safety manager asks about one pair's judgement; the answer
is built from claims the server makes out of the rule result (the judgement, the facts it used, the rule, what is
still to be checked), each with an id. The three questions of phase 1 are answered from the claims alone, at once:
why a pair that does not overlap still needs a check, which document values or foreman answers were used, what is
missing for a 판정보류. A question in his own words goes to the model, which only says which of these explanations
it asks for and which facts matter first; every sentence shown is the server's, and every claim still to be checked is
always shown. Times moved, changed or a work stopped are not calculated (the foremen settle time and order between
them): such a question is answered so, without the model.

The answer frame (§19.2): 판단 한 줄 → 사용한 사실 → 적용한 규칙 → 아직 확인할 것 → 근거 보기.
"""
import hashlib
import json
import re

from . import llm, pairs

PRI = {1: "1순위", 2: "2순위", 3: "3순위"}
FIXED = {
    "seq": "겹치지 않는데 왜 확인이 필요한가요?",
    "used": "어떤 서류 값·반장 답을 썼나요?",
    "defer": "무엇이 부족해 판정보류인가요?",
}
# a question about moving, changing, cancelling or stopping a work: croScan does not work that out (design §5.5)
WHAT_IF = re.compile(r"만약|가정|옮기|옮겨|미루|미뤄|당기|당겨|늦추|늦춰|앞당|바꾸|바꿔|바뀌면|변경|조정하면|취소|중단|중지|멈추|멈춰|쉬면|쉬어|휴무|"
                     r"빼면|없으면|안\s*하면|하지\s*않으면|줄이면|늘리면|몇\s*시로|언제\s*하면|\d+\s*시로|하루")
SYSTEM = ("너는 조선소 위험 작업쌍 판정을 설명하는 도우미다. 안전관리자의 질문이 아래 셋 중 무엇을 묻는지 고르고, "
          "그 답에 쓸 주장 id를 중요한 순서로 고른다. 문장은 쓰지 않는다.\n"
          "의도: seq(시간이 겹치지 않는데 왜 확인이 필요한가), used(어떤 서류 값·반장 답을 근거로 썼나), "
          "defer(무엇이 부족해 판정보류인가), none(이 셋이 아님: 일정 변경 효과, 안전 여부 판단 등).")


def _no(d):
    """as the screen numbers documents (sfNo): a permit by its number, a plan as WP-nn"""
    return d.get("id", "") if d.get("type") == "permit" else "WP-" + str(d.get("id", ""))[-2:]


def claims(p, docs):
    """the claims of a pair's top reason -> {J: [...], F: [...], R: [...], U: [...]} as [{id, text}]"""
    R = p["reasons"][0]
    w = R["when"]
    rule = next((r for r in pairs.rules()["rules"] if r["id"] == R["rule"]), {})
    C, X = docs.get(R["cause"], {}), docs.get(R["exposed"], {})
    concl = ("서류상 동시에 하면 안 되는 조합이 확인됐습니다" if R["priority"] == 1 and R["forbidden"] and R["E"] == 3
             else "작업시간은 겹치지 않지만, 앞 작업의 잔류위험이 없어졌다는 확인 기록이 없습니다" if w["kind"] == "sequence"
             else "한쪽 작업 시간이 없어 겹침을 확정할 정보가 부족합니다" if w["kind"] == "unknown"
             else "필요한 통제·차단 조치를 확인한 뒤 함께 할지 판단합니다" if R["priority"] == 2
             else "작업 관계와 추가 조건을 확인한 뒤 판단합니다")
    J = [{"id": "J1", "text": f"{R['score']}점 · {PRI.get(R['priority'], '')}: {concl}."}]
    F = []
    if w["kind"] == "overlap":
        seg = ", ".join(f"{a}–{b}" for a, b in w.get("segments") or [[w["start"], w["end"]]])
        F.append(f"서류 기준 겹침: {seg} ({w['min']}분)")
    elif w["kind"] == "sequence":
        F.append(f"서류 기준: {w['start']}에 앞 작업이 끝나고 {w['gap']}분 뒤 다음 작업 시작 (겹치지 않음)")
    else:
        F.append("서류 기준: 한쪽 작업 시간이 없어 겹치는지 알 수 없음")
    for e in R.get("evidence") or []:
        no = _no(docs.get(e["doc"], {}) or {"id": e["doc"]})
        F.append(f"{no} · 작업반장 답변 「{e['value']}」" if e.get("quote") else f"{no} · {e['field']}: {e['value']}")
    F = [{"id": f"F{i}", "text": t} for i, t in enumerate(F, 1)]
    Rs = [{"id": "R1", "text": f"규칙 「{R['name']}」" + (" (동시 작업 금지 조합 규칙)" if R["forbidden"] else "")
                               + f": 강도 {R['S']} × 노출 {R['E']} = {R['score']}점"}]
    if rule.get("law_fit") == "맞음" and rule.get("law_checked"):
        Rs.append({"id": "R2", "text": f"관련 조문: {rule['law']} (국가법령정보센터 현행본 대조)"})
    U = list(R.get("gaps") if R.get("gaps") is not None else [t for t in R.get("why_E") or [] if not t.startswith("같은 시간에")])
    left = pairs._residual(rule, (R.get("sequence") or {}).get("first", "A")) if w["kind"] == "sequence" else None
    if left:                                          # what is left depends on which work came first (화기 → 잔불, 도장 → 증기)
        U.append(f"앞 작업 뒤 남는 위험({left})이 없어졌는지")
    if R.get("ask"):
        U.append(f"확인할 것: {R['ask']}")
    U = [{"id": f"U{i}", "text": t} for i, t in enumerate(dict.fromkeys(U), 1)]
    refs = [{"doc": d.get("id"), "no": _no(d), "title": d.get("title", "")} for d in (C, X) if d]
    # where each fact came from (for the verifier, §5.4 ②): the evidence row it was written from, if any
    src = {f"F{i}": None for i in range(1, len(F) + 1)}
    for i, e in enumerate(R.get("evidence") or [], 2):
        src[f"F{i}"] = {"doc": e["doc"], "field": e["field"], "value": e["value"], "quote": bool(e.get("quote")),
                        "confirmed": bool(e.get("confirmed")) or str(e["field"]).startswith(pairs.CONFIRMED)}
    return {"J": J, "F": F, "R": Rs, "U": U, "refs": refs, "src": src, "rev": pair_rev(p, docs),
            "pair": {"cause": R["cause"], "exposed": R["exposed"], "score": R["score"], "priority": R["priority"], "when": w}}


def pair_rev(p, docs):
    """the version of what a pair's explanation stands on: its reasons, the two documents and the rules (§5.4 ⑥)"""
    R = p["reasons"][0]
    keep = [{k: r.get(k) for k in ("rule", "cause", "exposed", "S", "E", "score", "priority", "when", "gaps", "evidence")} for r in p["reasons"]]
    ds = [docs.get(i) or {} for i in (R["cause"], R["exposed"])]
    return hashlib.sha256(json.dumps([keep, ds, pairs.rules().get("version")], ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()[:16]


def applicable(p):
    """the fixed questions that fit this pair"""
    R = p["reasons"][0]
    out = ["used"]
    if R["when"]["kind"] == "sequence":
        out.insert(0, "seq")
    if p.get("judgement") == "판정보류" or R["E"] == 1:
        out.append("defer")
    return [{"id": k, "text": FIXED[k]} for k in out]


def _frame(c, judge, facts, rules, focus=None):
    return {"judge": focus or judge, "facts": facts, "rules": rules, "left": c["U"], "refs": c["refs"], "rev": c.get("rev")}


def fixed(c, which):
    """one of the three questions, from the claims alone"""
    F, U = c["F"], c["U"]
    if which == "seq":
        return _frame(c, "작업시간은 겹치지 않지만, 앞 작업 뒤 남는 위험이 없어졌다는 확인 기록이 없어 확인이 필요합니다.",
                      [F[0]] + [f for f in F[1:] if "시간" in f["text"] or "위치" in f["text"]], c["R"])
    if which == "defer":
        miss = [u["text"] for u in U if not u["text"].startswith("확인할 것")]
        return _frame(c, "아래 정보가 서류에 없어 노출을 확정하지 못했습니다(판정보류)." if miss else "판정에 필요한 정보는 서류에 있습니다.",
                      F, c["R"][:1])
    return _frame(c, "이 판정은 아래 서류 값" + ("·작업반장 답변" if any("작업반장 답변" in f["text"] for f in F) else "") + "으로 계산했습니다.",
                  F, c["R"])


OUT_OF_SCOPE = "croScan의 「왜?」는 겹치지 않는데 확인하는 이유, 쓴 서류 값·반장 답, 판정보류의 부족 정보 세 가지를 설명합니다."


async def ask(c, question, intents, deadline=30.0):
    """a question in the manager's own words -> (frame, status ok|fixed|fail, why). The model only says which of
    this pair's explanations it asks for and which facts come first; every sentence is the server's (a free line
    could turn 「15분」 into 「15시」 or 「예정」 into 「완료」: Codex review 2026-10-31)."""
    if WHAT_IF.search(question or ""):
        f = _frame(c, "croScan은 작업 시간을 옮기거나 바꾸거나 멈추는 경우를 계산하지 않습니다. 시간·순서는 두 작업반장이 협의해 정합니다.", c["F"][:1], c["R"][:1])
        return f, "fixed", "what_if"
    allowed = [i for i in ("seq", "used", "defer") if i in intents]
    user = ("이 쌍에서 고를 수 있는 의도: " + ", ".join(allowed + ["none"]) + "\n주장:\n"
            + "\n".join(f"{x['id']} {x['text']}" for x in c["F"]) + f"\n질문: {question.strip()[:200]}")
    schema = {"type": "object", "additionalProperties": False, "required": ["intent", "facts"], "properties": {
        "intent": {"type": "string", "enum": allowed + ["none"]},
        "facts": {"type": "array", "maxItems": 6, "items": {"type": "string", "enum": [x["id"] for x in c["F"]]}}}}
    try:
        data, meta = await llm.call_json("EXPLAIN", [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
                                         schema, think=0, out_tokens=120, deadline=deadline, pri=llm.ASKED)
    except llm.LlmFail as e:
        return fixed(c, "used"), "fail", e.code
    ids = {x["id"]: x for x in c["F"]}
    if not (isinstance(data, dict) and set(data) == {"intent", "facts"} and data["intent"] in allowed + ["none"]
            and isinstance(data["facts"], list) and all(isinstance(i, str) and i in ids for i in data["facts"])):
        return fixed(c, "used"), "fail", "schema"
    if data["intent"] == "none":
        return _frame(c, OUT_OF_SCOPE, c["F"][:1], c["R"][:1]), "fixed", "out_of_scope"
    f = fixed(c, data["intent"])
    first = [ids[i] for i in dict.fromkeys(data["facts"])]
    f["facts"] = first + [x for x in f["facts"] if x not in first]       # the model's order first, nothing left out
    return f, "ok", data["intent"]


# 설명 검증기 (design §5.4): every answer frame is checked before it is shown; a block that fails is replaced by the
# claims themselves (the evidence table), which pass by construction. The seven checks:
#   ① ids: every fact, rule and open item is one of the claims given, word for word
#   ② passages: a fact written from a document row is in that document as it is now (a foreman's confirmed answer
#      is checked against its own record by the detection)
#   ③ numbers: the score and priority in the judgement, the times of the facts and the cause/exposed works match the rule result
#   ④ no conversion: unknown → none, planned → done, no alarm → safe (and an open item never said away)
#   ⑤ every open item and residual risk is rendered
#   ⑥ the version: the frame's revision is the claims' and the claims' is the current one
#   ⑦ text only: every value is plain text (no markup kept; angle brackets are turned into look-alikes)
NO_CONVERT = re.compile(r"안전합니다|안전함|안전하다|문제\s*없(?:습|음|다)|위험\s*없(?:습|음|다)|완료(?:됐|되었|함|했)|이행(?:됐|되었|함|했)|"
                        r"확인(?:됐|되었)습니다|승인(?:됐|되었|함)|해당\s*없(?:습|음)")
ALLOWED_JUDGE = {
    "작업시간은 겹치지 않지만, 앞 작업 뒤 남는 위험이 없어졌다는 확인 기록이 없어 확인이 필요합니다.",
    "아래 정보가 서류에 없어 노출을 확정하지 못했습니다(판정보류).", "판정에 필요한 정보는 서류에 있습니다.",
    "이 판정은 아래 서류 값으로 계산했습니다.", "이 판정은 아래 서류 값·작업반장 답변으로 계산했습니다.",
    "croScan은 작업 시간을 옮기거나 바꾸거나 멈추는 경우를 계산하지 않습니다. 시간·순서는 두 작업반장이 협의해 정합니다.",
}
_IDS = re.compile(r"(?:OH-\d+-\d+|(?:MCC|DB|PNL|LP|PP)-\d+|(?<![A-Za-z0-9-])[A-Z]\d{2,3}[A-Z]?(?:\([A-Z]\))?(?![A-Za-z0-9]|-\d|\s*(?:축|칼럼|밸브|번\s*밸브|열|라인|펌프))|(?<![A-Za-z0-9-])[A-Z]-\d{2}(?=\s*블록))")  # block numbers as pairs.BLOCK_ID
_TIME = re.compile(r"\b\d{1,2}:\d{2}\b")


def _norm(s):
    return re.sub(r"[\s·,.\"'「」()]", "", str(s or ""))


def _in_doc(value, doc, field=""):
    """a document value as it is now: the whole value, or every part of it, is in the document. The time row is the
    document's windows (each HH:MM in it is one of them); the place row its place and route as written."""
    hay = _norm(json.dumps(doc, ensure_ascii=False, default=str))
    if field == "시간":
        return all(_norm(t) in hay for t in _TIME.findall(str(value)))
    if field == "위치":
        return all(_norm(x) in hay for x in re.split(r"\s*/\s*경로:\s*", str(value)) if _norm(x))
    v = _norm(value)
    if not v or v in hay:
        return True
    parts = [x for x in re.split(r"[\s,·/]+", str(value)) if len(_norm(x)) >= 2]
    return bool(parts) and all(_norm(x) in hay for x in parts)


def verify(frame, c, docs=None):
    """-> (frame to show, {ok, checks: [{n, name, ok, why}]}). A failed check replaces the frame by the claims."""
    checks = []

    def ck(n, name, ok, why=""):
        checks.append({"n": n, "name": name, "ok": bool(ok), "why": "" if ok else why})

    blocks = {"facts": c["F"], "rules": c["R"], "left": c["U"]}
    bad = [k for k, allowed in blocks.items() if any(x not in allowed for x in frame.get(k) or [])]
    ck(1, "참조 ID", not bad and (frame.get("judge") in ALLOWED_JUDGE | {j["text"] for j in c["J"]} or frame.get("judge") == OUT_OF_SCOPE),
       "제공되지 않은 주장: " + ", ".join(bad) if bad else "서버 틀이 아닌 판단 문장")
    miss = []
    for x in frame.get("facts") or []:
        s = (c.get("src") or {}).get(x["id"])
        if s and not s["confirmed"] and docs is not None and not _in_doc(s["value"], docs.get(s["doc"]) or {}, s["field"]):
            miss.append(x["id"])
    ck(2, "구절 존재", not miss, "현재 서류에 없는 값: " + ", ".join(miss))
    P = c.get("pair") or {}
    nums_ok = True
    if P:
        j = frame.get("judge") or ""
        if re.match(r"\d+점", j) and not j.startswith(f"{P['score']}점"):
            nums_ok = False
        w = P.get("when") or {}
        allowed_t = {t for t in (w.get("start"), w.get("end")) if t} | {t for seg in w.get("segments") or [] for t in seg}
        for x in frame.get("facts") or []:
            if x["id"] == "F1" and any(t not in allowed_t for t in _TIME.findall(x["text"])):
                nums_ok = False
        if {r["doc"] for r in frame.get("refs") or []} - {P["cause"], P["exposed"]}:
            nums_ok = False
        if docs is not None:
            have = set(_IDS.findall(json.dumps([docs.get(P["cause"]), docs.get(P["exposed"])], ensure_ascii=False, default=str)))
            for x in frame.get("facts") or []:
                s = (c.get("src") or {}).get(x["id"])
                if s and not s["confirmed"] and set(_IDS.findall(x["text"])) - have:
                    nums_ok = False
    ck(3, "숫자·시간·설비·작업 일치", nums_ok, "규칙 결과와 다른 숫자·시각·설비·작업")
    said = " ".join([frame.get("judge") or ""] + [x["text"] for x in frame.get("facts") or []])
    conv = NO_CONVERT.search(said) and not any(NO_CONVERT.search(x["text"]) for x in c["F"])
    away = bool(c["U"]) and frame.get("judge") == "판정에 필요한 정보는 서류에 있습니다." and any(not u["text"].startswith("확인할 것") for u in c["U"])
    ck(4, "미상·계획·무경보 변환 금지", not conv and not away, "미상→없음·계획→완료·무경보→안전 표현")
    ck(5, "필수 미확인 모두 표시", all(u in (frame.get("left") or []) for u in c["U"]), "아직 확인할 것이 빠짐")
    ck(6, "개정 일치", frame.get("rev") == c.get("rev"), "설명이 다른 판의 판정에 기대고 있음")
    plain = all(isinstance(v, str) for k in ("judge",) for v in [frame.get(k)]) and all(
        isinstance(x.get("text"), str) for k in ("facts", "rules", "left") for x in frame.get(k) or []) and not ({"html", "markup"} & set(frame))
    ck(7, "텍스트로만 표시", plain, "글이 아닌 값")
    ok = all(x["ok"] for x in checks)
    out = dict(frame)
    if not ok:                                   # the claims themselves: the evidence table
        out = {"judge": c["J"][0]["text"] if c["J"] else "아래 근거 표를 보세요.", "facts": c["F"], "rules": c["R"], "left": c["U"],
               "refs": c["refs"], "rev": c.get("rev"), "fallback": True}
    for k in ("facts", "rules", "left"):
        out[k] = [{**x, "text": x["text"].replace("<", "‹").replace(">", "›")} for x in out.get(k) or []]
    out["judge"] = str(out.get("judge") or "").replace("<", "‹").replace(">", "›")
    return out, {"ok": ok, "checks": checks}


# 설명 대상 확장 (design §5.2): a checklist item, a change in the 반영본, a revision that made answers count no more, a
# question's reason — each from the server's own data, with the same frame and the same verifier (no model)
def _claims(J, F, R, U, refs=None, src=None, rev=None):
    ids = lambda p, xs: [{"id": f"{p}{i}", "text": t} for i, t in enumerate(dict.fromkeys(t for t in xs if t), 1)]
    c = {"J": ids("J", [J]), "F": ids("F", F), "R": ids("R", R), "U": ids("U", U), "refs": refs or [], "src": src or {}}
    c["rev"] = rev or hashlib.sha256(json.dumps([J, F, R, U], ensure_ascii=False).encode()).hexdigest()[:16]
    return c


def frame_of(c):
    return {"judge": c["J"][0]["text"], "facts": c["F"], "rules": c["R"], "left": c["U"], "refs": c["refs"], "rev": c["rev"]}


CK_STATE = {"yes": "해당", "no": "해당 없음", "check": "안전팀 확인"}


def checklist(it, permit_no=""):
    """a checklist item: the work facts → the hazard item → the controls, with what is still open (§5.2)"""
    auto = CK_STATE.get(it.get("auto") or it.get("state"), "")
    J = f"「{it.get('title', '')}」 항목은 croScan 규칙이 「{auto}」으로 제안했습니다." if auto else f"「{it.get('title', '')}」 항목입니다."
    F = [f"근거: {r}" for r in it.get("reasons") or []] or ["허가서에 이 항목을 해당으로 볼 기재가 없어 규칙 제안이 없습니다"]
    if it.get("why"):
        F.append(f"이 위험이 생기는 때: {it['why']}")
    R = [f"체크리스트 명세 {it.get('id', '')}" + (f" · 근거 {it['ref']}" if it.get("ref") else "")]
    # the same hazard in the case book (KOSHA 부산광역본부 조선업 중대재해 사례집): what happened, its page — a reference
    for c in (it.get("cases") or [])[:3]:
        R.append(f"참고 사고 사례(조선업 중대재해 사례집 {c.get('page')}쪽): {c.get('title', '')}")
    on = [k.get("text") for k in it.get("controls") or [] if k.get("on")]
    if on:
        R.append("고른 조치: " + " · ".join(on))
    U = []
    if (it.get("state") or "check") == "check":
        U.append("해당 여부를 안전팀이 확인해야 합니다")
    if (it.get("state") == "yes") and not on:
        U.append("해당인데 고른 조치가 없습니다")
    if not it.get("touched"):
        U.append("작업반장이 이 항목을 아직 확인하지 않았습니다")
    U.append("조치 이행은 현장에서 따로 확인합니다(체크리스트는 계획입니다)")
    return _claims(J, F, R, U, [{"doc": permit_no, "no": permit_no, "title": it.get("title", "")}])


MODE_KO = {"fill": "빈칸에 기입", "append": "덧붙임", "replace": "바꿈"}


def change(fill=None, extra=None, permit_no=""):
    """a change in the 반영본 (a fill) or a line sent to the 별지 (extra: (label, text)): before, after, where, why"""
    if fill:
        J = f"「{fill.get('name', '')}」 칸: 「{fill.get('original') or '빈칸'}」 → 「{fill.get('final') or fill.get('text', '')}」 ({MODE_KO.get(fill.get('mode'), fill.get('mode', ''))})"
        F = [f"이 값을 쓴 근거: {s}" for s in fill.get("src") or []]
        R = ["확인한 답·고친 값만 그 칸에 들어갑니다. 업로드한 원본 파일은 바뀌지 않습니다"]
        U = ["반영본은 내부 초안이며 승인·발행이 아닙니다"]
    else:
        label, text = (extra or ("", ""))[:2]
        J = f"「{label}」은 양식에 맞는 칸이 없어 별지에 적었습니다."
        F = [f"별지에 적은 내용: {text}"]
        R = ["양식 칸이 없거나 보호 칸(서명·승인·당일 확인)이면 별지로 보냅니다"]
        U = ["별지 내용도 원문 그대로이며 승인이 아닙니다"]
    return _claims(J, F, R, U, [{"doc": permit_no, "no": permit_no, "title": "반영본"}])


def revision(dropped):
    """answers that count no more because what they checked changed (§2.3): what changed and what expired"""
    J = f"앞 답이 바뀌어 그 답을 확인한 답 {len(dropped)}건이 다시 확인이 필요합니다."
    F = [f"{x.get('slot') or x.get('qid')}: 기대던 답이 바뀜" for x in dropped]
    R = ["확인 질문의 답은 확인한 그 답에 묶입니다. 그 답이 바뀌면 같은 말이 돌아와도 다시 셉니다"]
    U = [f"{x.get('slot') or x.get('qid')}을 다시 확인" for x in dropped] or ["다시 확인할 답이 없습니다"]
    return _claims(J, F, R, U)


def question(q, why):
    """a question's reason: what was seen, why it is asked, the basis (the stored 「왜 묻나요?」 as a frame)"""
    J = f"이 질문은 {why['need']}." if why else "이 질문의 이유가 기록되어 있지 않습니다."
    F = [f"관측: {why['observe']}"] if why and why.get("observe") else []
    R = [f"[{b['grade']}] {b['ref']}" + (f" ({b.get('title')})" if b.get("title") else "") for b in (why or {}).get("basis") or []]
    U = [f"관련 자료(검색 후보, 근거 확정 아님): {r['ref']}" for r in (why or {}).get("refs") or []]
    return _claims(J, F, R or ["croScan 질문 규칙"], U)
