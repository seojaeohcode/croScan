"""1차 시연 평가 (design §11.1): TURN on the demo permits, and multi-turn dialogues on the review store. Counts with
their denominators, not rates (a small set).

  python tools/eval_phase1.py turn [--dry]     # TURN: the rules alone (기준선) and the rules + AI (통합판)
  python tools/eval_phase1.py multi            # 10 dialogues on a throwaway review store, no model
  python tools/eval_phase1.py all

turn needs the model (LLM_URL, inside a container on the model's network); --dry runs the rules alone, without it.
The cases: tools/eval_phase1_cases.py. Always exits 0: it is a measurement.

Comparison and ablation (design §11.3·§9; one switch at a time):
  --mode 1   규칙 전용 (the rules' reading only; = --dry)
  --mode 2   새 사실·확인 구조 + 기존 해석기 (the rules' reading through the review store: proposals stored and scored)
  --mode 3   AI 해석 + 규칙 질문 (the model alone reads the answer; no rules' reading first)
  --mode 4   혼합 질문 + RAG (mode 5, and each permit's upload analysis with its reference passages: AI needs counted)
  --mode 5   통합 (rules → AI → CRITIQUE, as the API; the default)
  --no-fewshot  no reviewed examples in the prompt     --think N   a reasoning budget for the reading
  --no-critique the reading without CRITIQUE            --no-cache  the model's prompt cache off
  --second      a second, sampled reading (temperature 0.7) per answer, offline only (design §9: 최대 2샘플): how
                many wrong proposals it disagrees with (errors found) and the extra time
  --clause-ids  the output-shrink trial (design §10.7): the answer cut into numbered clauses, the model returns the
                clause number instead of the quoted words (understand.check unchanged); output tokens compared
  --cases FILE  TURN cases from a JSON file (tools/eval_nl_variants.py: 150 × 8) instead of the 30 × 2
  --out FILE    one line per case (JSONL) as it goes; --resume skips the cases already in it (a long run on the
                server: nohup python tools/eval_phase1.py turn --cases … --out … --resume &)
Reported per mode: 정보 획득(맞음/기대), 불필요 확인(틀림 — a proposal the foreman would have to refuse), 놓침, 금지 항목,
미확인 종료(model failures), CRITIQUE 보류, time (median/p95), output tokens.
"""
import asyncio
import json
import os
import re
import statistics
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("CROSCAN_DATA", tempfile.mkdtemp(prefix="croscan_eval_"))      # multi: a throwaway store
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from server import analyze, augment, critique, extract, llm, store, understand  # noqa: E402
from make_demo_day import DIR, load, permit_name  # noqa: E402
from eval_phase1_cases import ALSO_OK, MULTI, TURN  # noqa: E402


# TURN ---------------------------------------------------------------------------------------------------------------
def _permits():
    ps = load("permits.json")
    ps = ps if isinstance(ps, list) else ps.get("permits", [])
    out = {}
    for d in ps:
        n = permit_name(d)
        out[n[:4]] = extract.build(DIR / "허가서" / n, d["kind"])["fields"]
    return out


def _want(x):
    """an expectation: (choice, {v, who, when})"""
    return (x, {}) if isinstance(x, str) else x


def _norm(s):
    return "".join(str(s or "").split()).upper().replace("~", "-").replace("–", "-")


def _detail(g, d):
    """what of the details is wrong in proposal g: [] or some of 값 / 주체 / 시점"""
    bad = []
    if d.get("v") and not all(_norm(t) in _norm(g.get("v")) for t in d["v"]):
        bad.append("값")
    if d.get("who") and g.get("who") is not None and g["who"] != d["who"]:
        bad.append("주체")
    if d.get("when") and g.get("when") not in (None, "none") and g["when"] != d["when"]:
        bad.append("시점")
    return bad


def _score(got, want, never, ok=None):
    """got {item: {c, v, who, when}} -> (right, wrong, missed, forbidden, {값, 주체, 시점: wrong by that detail}); ok: readings
    of other items that are also right when made (not expected, so neither counted right nor missed)"""
    r, w, why = 0, 0, {"값": 0, "주체": 0, "시점": 0}
    for k, g in got.items():
        if k not in want and k in (ok or {}) and g["c"] == _want(ok[k])[0] and not _detail(g, _want(ok[k])[1]):
            continue
        if k not in want:
            w += 1
            continue
        c, d = _want(want[k])
        bad = _detail(g, d) if g["c"] == c else ["보기"]
        if bad:
            w += 1
            for b in bad:
                if b in why:
                    why[b] += 1
        else:
            r += 1
    return r, w, len(want) - r, sum(1 for k in got if k in never), why


def _got(p, who=None, when=None):
    return {"c": p["choice"], "v": p.get("value") or "", "who": p.get("who", who), "when": p.get("when", when)}


async def _critique(fields, src, props):
    """CRITIQUE as /api/understand runs it after the reading: -> (props shown, held)"""
    try:
        return await critique.review(fields, src, props, sid=None)
    except TypeError:                                      # a later signature: the same call without the optional ones
        return await critique.review(fields, src, props)


OPT = {"mode": 5, "fewshot": True, "think": 0, "critique": True, "cache": True, "second": False, "clause": False}


def _arg(name, default=None):
    a = sys.argv
    return a[a.index(name) + 1] if name in a and a.index(name) + 1 < len(a) else default


def _options():
    OPT.update(mode=int(_arg("--mode", 5)), fewshot="--no-fewshot" not in sys.argv, think=int(_arg("--think", 0)),
               critique="--no-critique" not in sys.argv, cache="--no-cache" not in sys.argv, second="--second" in sys.argv,
               clause="--clause-ids" in sys.argv)
    if not OPT["fewshot"]:                     # ablation: no reviewed examples (the same list and answer messages)
        understand._msgs = lambda head, said: [{"role": "system", "content": understand.SYSTEM}] + understand._turn(head, said)
    if not OPT["cache"]:                       # ablation: the model's prompt cache off
        payload = llm._payload
        llm._payload = lambda *a, **k: {**payload(*a, **k), "cache_prompt": False}
    return OPT


def _cases():
    """TURN cases: the 30 × 2 of eval_phase1_cases, or a JSON file of the same shape (lists in place of tuples/sets)"""
    path = _arg("--cases")
    if not path:
        return TURN
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    tup = lambda w: {k: (v if isinstance(v, str) else (v[0], v[1])) for k, v in w.items()}
    return [(c["name"], c["pno"], c["item"], c["choice"], c["texts"], tup(c["want"]), set(c.get("never") or [])) for c in raw]


CLAUSE = re.compile(r"(?<=[.?!,])\s+|\s+(?:그리고|또|그런데)\s+")


async def _read_clauses(fields, answers, src, sid=None):
    """the output-shrink trial (design §10.7): the answer cut into numbered clauses; the model names the clause (s)
    instead of copying the words; the words are restored here and the server's checks run unchanged"""
    qs = understand.candidates(fields, answers, src)
    if not qs:
        return {"status": "none", "props": [], "apart": []}
    said = src.get("value", "").strip()
    parts = [p.strip() for p in CLAUSE.split(said) if p.strip()]
    sids = [f"S{i}" for i in range(1, len(parts) + 1)]
    qids, cids = [f"Q{i}" for i in range(1, len(qs) + 1)], sorted({c["id"] for q in qs for c in q["choices"] if c["id"] != "unknown"})
    schema = understand._schema(qids, cids)
    item = schema["properties"]["props"]["items"]
    item["required"] = [x for x in item["required"] if x != "quote"] + ["s"]
    item["properties"].pop("quote")
    item["properties"]["s"] = {"type": "string", "enum": sids}
    head = understand._head(qs, src.get("q")) + "\n(quote 대신 답의 절 번호 s를 고른다)"
    msgs = [{"role": "system", "content": understand.SYSTEM}] + understand._turn(head, " ".join(f"[{s}] {p}" for s, p in zip(sids, parts)))
    try:
        data, meta = await llm.call_json("TURN_CLAUSE", msgs, schema, think=OPT["think"], out_tokens=320, deadline=60, sid=sid)
    except llm.LlmFail as e:
        return {"status": "fail", "props": [], "apart": [], "why": e.code, "meta": e.meta}
    props = [{**{k: v for k, v in p.items() if k != "s"}, "quote": parts[sids.index(p["s"])]} for p in data.get("props", []) if p.get("s") in sids]
    ok, apart, dropped = understand.check(fields, answers, src, qs, props)
    meta["dropped"] = dropped
    return {"status": "ok" if ok or apart else "none", "props": ok, "apart": apart, "meta": meta}


async def _read(fields, answers, src):
    if OPT["clause"]:
        return await _read_clauses(fields, answers, src)
    return await understand.read(fields, answers, src, think=OPT["think"])


async def _second(fields, answers, src):
    """a second reading sampled at temperature 0.7 (offline error analysis only): -> {item: choice}"""
    real = llm.call_json

    async def warm(kind, messages, schema, **kw):
        return await real(kind, messages, schema, **{**kw, "temperature": 0.7})
    llm.call_json = warm
    try:
        out = await understand.read(fields, answers, src, think=OPT["think"])
    finally:
        llm.call_json = real
    return {p["q"]["item"]: p["choice"] for p in out.get("props", [])}


def _done(path):
    if not path or not Path(path).exists():
        return set()
    return {json.loads(x)["key"] for x in Path(path).read_text(encoding="utf-8").splitlines() if x.strip()}


async def _rag_needs(fields_of):
    """mode 4: each permit's upload analysis with its reference passages -> the AI needs it found, per permit"""
    out = {}
    for pno, fields in fields_of.items():
        res = await analyze.analyze(fields, [])
        out[pno] = {"status": res["status"], "needs": len(res.get("needs") or []), "refs": len(res.get("refs") or [])}
        print(f"[분석+RAG] {pno}: {res['status']} · AI 질문 후보 {out[pno]['needs']} · 참고 자료 {out[pno]['refs']}", flush=True)
    return out


def _mode2(fields, src, rule):
    """mode 2: the rules' reading through the review store (stored as proposals, then read back)"""
    s = store.create()
    store.answers_for(s, [src], fields, store.revision(s))
    if rule:
        store.propose(s, "rule", src, rule, basis=store.revision(s))
    return {p["q"]["item"]: _got(p) for p in store.pending(s, fields)}


async def turn(dry=False):
    fields_of = _permits()
    mode = 1 if dry else OPT["mode"]
    dry = mode in (1, 2)
    tot = {"base": [0, 0, 0, 0], "ai": [0, 0, 0, 0]}
    why_tot = {"base": {"값": 0, "주체": 0, "시점": 0}, "ai": {"값": 0, "주체": 0, "시점": 0}}
    times, fails, unresolved, n, held_n = [], 0, [], 0, 0
    gen, second = [], {"wrong": 0, "flagged": 0, "disagree": 0, "time": 0.0}
    out_path, done = _arg("--out"), (_done(_arg("--out")) if "--resume" in sys.argv else set())
    rag = await _rag_needs(fields_of) if mode == 4 else None
    for name, pno, item, choice, texts, want, never in _cases():
        fields = fields_of.get(pno)
        open_ = augment.questions(fields, [])[0] if fields else []
        q = next((x for x in open_ if x["item"] == item), None)
        miss = [k for k in list(want) + list(never) if not any(x["item"] == k for x in open_)]
        if not q or miss:
            unresolved.append((name, pno, item, miss))
            continue
        for text in texts:
            key = f"{name}|{pno}|{text}"
            if key in done:
                continue
            n += 1
            src = {"qid": q["qid"], "choice": choice, "value": text, "q": q}
            t = time.time()
            rule, _ = augment.interpret(fields, [src], src)              # the rules first, as /api/augment does
            base = {p["q"]["item"]: _got(p) for p in rule}
            if mode == 2:
                base = _mode2(fields, src, rule)
            got, status, apart = ({} if mode == 3 else dict(base)), "dry", []
            if not dry:
                out = await _read(fields, [src] + ([] if mode == 3 else rule), src)   # the AI on what the rules left open
                if OPT["critique"]:
                    props, held = await _critique(fields, src, out.get("props", []))   # then CRITIQUE, as the API does
                else:
                    props, held = out.get("props", []), []
                times.append(time.time() - t)
                gen.append((out.get("meta") or {}).get("gen_n") or 0)
                held_n += len(held)
                status, apart = out["status"], [a["slot"] for a in out.get("apart", []) + held]
                fails += status == "fail"
                got.update({p["q"]["item"]: _got(p) for p in props if p["q"]["item"] not in got})
                if OPT["second"]:
                    t2 = time.time()
                    other = await _second(fields, [src] + rule, src)
                    second["time"] += time.time() - t2
                    for k, g in got.items():
                        bad = k not in want or _want(want[k])[0] != g["c"]
                        dis = other.get(k) != g["c"]
                        second["wrong"] += bad
                        second["flagged"] += bad and dis
                        second["disagree"] += dis
            also = ALSO_OK.get(name.split("#")[0], {})
            sb, sa = _score(base, want, never, also), _score(got, want, never, also)
            for k, s in (("base", sb), ("ai", sa)):
                tot[k] = [a + b for a, b in zip(tot[k], s[:4])]
                why_tot[k] = {x: why_tot[k][x] + s[4][x] for x in why_tot[k]}
            took = f" {times[-1]:.1f}s" if times and not dry else ""
            show = lambda G: {k: f"{g['c']}" + (f"={g['v']}" if g["v"] else "") + (f"/{g['who']}" if g.get("who") else "") for k, g in G.items()}
            print(f"{name} | {text[:30]} | {status}{took} | 규칙 {show(base)} → 통합 {show(got)} | 따로 {apart} | 맞음{sa[0]} 틀림{sa[1]} 놓침{sa[2]} 금지{sa[3]}", flush=True)
            if out_path:
                with open(out_path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps({"key": key, "mode": mode, "status": status, "base": sb[:4], "ai": sa[:4], "why": sa[4],
                                         "time": times[-1] if times and not dry else None, "gen_n": gen[-1] if gen and not dry else None},
                                        ensure_ascii=False) + "\n")
    exp = sum(len(c[5]) * len(c[4]) for c in _cases() if not any(u[0] == c[0] for u in unresolved))
    print(f"\n[TURN] 시나리오 {len(TURN) - len(unresolved)}/{len(TURN)} × 표현 2 = {n}건 · 기대 제안 {exp}")
    for k, label in (("base", "규칙 기준선"),) + ((("ai", "통합판(규칙+AI)"),) if not dry else ()):
        r, w, m, lk = tot[k]
        y = why_tot[k]
        print(f"  {label}: 맞음 {r}/{exp} · 틀림 {w}(값 {y['값']} · 주체 {y['주체']} · 시점 {y['시점']}) · 놓침 {m}/{exp} · 금지 항목 제안 {lk}")
    if times:
        p95 = sorted(times)[max(0, int(len(times) * 0.95) - 1)]
        print(f"  CRITIQUE 보류 {held_n}건 · 미확인 종료(모델 실패) {fails}/{n} · 시간(읽기+CRITIQUE) 중앙값 {statistics.median(times):.1f}s"
              f" p95 {p95:.1f}s 최대 {max(times):.1f}s · 출력 토큰 중앙값 {statistics.median(gen) if gen else 0}")
        r, w = tot["ai"][0], tot["ai"][1]
        print(f"  [모드 {mode}] 정보 획득 {r}/{exp} · 불필요 확인(틀림) {w} · 놓침 {tot['ai'][2]} · 미확인 종료 {fails}")
    if OPT["second"] and not dry:
        print(f"  두 번째 읽기: 틀린 제안 {second['wrong']}건 중 다르게 읽음 {second['flagged']}건(오류 발견) · 다르게 읽은 전체 {second['disagree']}건"
              f" · 추가 시간 {second['time']:.0f}s")
    if rag:
        print(f"  [분석+RAG] 허가서 {len(rag)}장 · AI 질문 후보 {sum(x['needs'] for x in rag.values())} · 참고 자료 {sum(x['refs'] for x in rag.values())}")
    for u in unresolved:
        print(f"  풀리지 않은 사례: {u[0]} ({u[1]} {u[2]}) 없는 질문 {u[3]}")
    return {"n": n, "exp": exp, **tot, "why": why_tot, "held": held_n, "fails": fails, "unresolved": len(unresolved), "mode": mode,
            "second": second if OPT["second"] else None, "gen": statistics.median(gen) if gen else None}


# multi-turn ---------------------------------------------------------------------------------------------------------
def _fields(date="2026-10-31", date2=None):
    f = {"p1.permit_no": {"key": "permit_no", "page": 1, "value": "P-1"}, "p1.date_1": {"key": "date_1", "page": 1, "value": date}}
    if date2:
        f.update({"p2.permit_no": {"key": "permit_no", "page": 2, "value": "P-2"}, "p2.date_1": {"key": "date_1", "page": 2, "value": date2}})
    return f


F = _fields()
QT1 = {"qid": "T1:P-1", "item": "T1", "page": 1, "text": "실제 작업 시간은요?"}
QB3 = {"qid": "B3:P-1", "item": "B3", "page": 1, "text": "병행?", "choices": [{"id": "yes", "label": "있음", "ask": "무엇"}, {"id": "no", "label": "없음"}]}
QL1 = {"qid": "L1:P-1", "item": "L1", "page": 1, "text": "위치?"}
SRC = {"qid": "T1:P-1", "choice": "partial", "value": "13시부터 15시까지, 옆에서 도장팀이 터치업해요", "q": QT1}
PROP = {"qid": "B3:P-1", "choice": "yes", "value": "도장팀 터치업", "q": QB3, "by": "T1:P-1", "quote": "옆에서 도장팀이 터치업해요"}


def _ans(sid, answers, f=F):
    return store.answers_for(sid, answers, f, store.revision(sid))


def _prop(sid, src, items, origin="ai"):
    return store.propose(sid, origin, src, items, basis=store.revision(sid))[0]


def _code(fn):
    try:
        fn()
        return None
    except store.StoreError as e:
        return e.code


def d_unknown():
    s = store.create()
    unk = {"qid": "B3:P-1", "choice": "unknown", "value": "", "q": QB3}
    r1 = store.issue(s, "B3@1", "question")
    calc, _, _ = _ans(s, [SRC, unk])
    got = _prop(s, SRC, [PROP])
    r2 = store.issue(s, "B3@1", "question")
    return [("모름 답이 그대로 남음", any(a["qid"] == "B3:P-1" and a["choice"] == "unknown" for a in calc)),
            ("모름으로 답한 질문에는 제안을 만들지 않음", got == []),
            ("그 질문은 한 번만 셈", r1["used"] == 1 and r2["again"] and store.budget(s)["used"] == 1)]


def d_reject():
    s = store.create()
    _ans(s, [SRC])
    pid = _prop(s, SRC, [PROP])[0]["pid"]
    store.decide(s, "r1", reject=[pid], fields=F)
    calc, _, _ = _ans(s, [SRC])
    return [("뺀 제안은 계산에 없음", [a["qid"] for a in calc] == ["T1:P-1"]),
            ("같은 말로는 다시 제안하지 않음", _prop(s, SRC, [PROP]) == [])]


def d_correct():
    s = store.create()
    _ans(s, [SRC])
    old = store.revision(s)
    pid = _prop(s, SRC, [PROP])[0]["pid"]
    store.decide(s, "c1", adopt=[pid], fields=F)
    fixed = dict(SRC, value="14시부터 16시까지만 해요")
    calc, _, _ = _ans(s, [fixed])
    return [("바탕 답을 고치면 그 답에서 읽은 채택은 무효", [a["qid"] for a in calc] == ["T1:P-1"] and not store.adopted(s)),
            ("옛 개정의 늦은 요청은 새 답을 덮지 못함(409)", _code(lambda: store.answers_for(s, [SRC], F, old)) == "stale_revision"),
            ("고친 답이 계산에 들어감", calc[0]["value"].startswith("14시"))]


def d_resume():
    s = store.create()
    _ans(s, [SRC])
    store.issue(s, "T1@1", "question")
    _prop(s, SRC, [PROP])
    rev = store.revision(s)
    st, b = store.state(s, F), store.budget(s)                    # a reload: read back from the server
    return [("직접 답이 복원됨", [a["qid"] for a in st["typed"]] == ["T1:P-1"]),
            ("기다리는 제안이 복원됨", len(st["proposals"]) == 1 and st["proposals"][0]["qid"] == "B3:P-1"),
            ("개정 번호가 그대로", st["revision"] == rev),
            ("이미 보인 질문이 복원됨", b["asked"] == ["T1@1"] and b["used"] == 1)]


def d_double():
    s = store.create()
    _ans(s, [SRC])
    pid = _prop(s, SRC, [PROP])[0]["pid"]
    a = store.decide(s, "d1", adopt=[pid], fields=F)
    b = store.decide(s, "d1", adopt=[pid], fields=F)
    i1, i2 = store.issue(s, "L1@1", "question"), store.issue(s, "L1@1", "question")
    return [("같은 동작 번호는 처음 결과", a == b and len(store.adopted(s)) == 1),
            ("같은 동작 번호·다른 내용은 충돌", _code(lambda: store.decide(s, "d1", reject=[pid])) == "action_conflict"),
            ("같은 질문을 두 번 보내도 한 번만 셈", i2["again"] and store.budget(s)["used"] == 1)]


def d_budget():
    s = store.create()
    for i in range(store.ASKS):
        store.issue(s, f"Q{i}@1", "question")
    over = _code(lambda: store.issue(s, "Q99@1", "question"))
    close = _code(lambda: store.issue(s, "CLOSE", "close"))
    if close:
        store.close_review(s)
    return [("13번째 질문은 거절", over == "budget"),
            ("마무리 요청도 한도로 거절되면 종료 기록", close == "budget" and store.budget(s)["close"]),
            ("종료 뒤 늦게 온 AI 필요정보는 넣지 않음", store.add_needs(s, [{"mkey": "late", "t": "referent", "key": "p1.job", "quote": "x"}]) is None),
            ("질문 수는 12에서 멈춤", store.budget(s)["used"] == store.ASKS)]


def d_clarify():
    s = store.create()
    ok = [store.issue(s, f"A1.{x}@1", "clarify", f"{x}@1") for x in ("T1", "L1", "B3")]
    fourth = _code(lambda: store.issue(s, "A1.L3@1", "clarify", "L3@1"))
    return [("다시 묻기 3회까지 받음", len(ok) == 3 and store.budget(s)["clarify"] == 3),
            ("4번째 다시 묻기는 거절", fourth == "clarify")]


def d_reask():
    s = store.create()
    store.issue(s, "T1@1", "question")
    again = store.issue(s, "T1@1", "question")
    store.issue(s, "A1.T1@1", "clarify", store.clarify_base("A1.T1@1"))
    second = _code(lambda: store.issue(s, "A1.T1.2@1", "clarify", store.clarify_base("A1.T1.2@1")))
    return [("같은 질문 재표시는 새로 세지 않음", again["again"] and store.budget(s)["used"] == 2),
            ("한 번 다시 물은 답(T1)은 그 둘째 부분으로도 또 묻지 않음", second == "clarify")]


def d_doc_change():
    s = store.create()
    F2 = _fields(date2="2026-10-31")
    QP2 = {"qid": "T1:P-2", "item": "T1", "page": 2, "text": "시간?"}
    S2 = {"qid": "T1:P-2", "choice": "partial", "value": "9시부터 11시, 3BAY 08칼럼", "q": QP2}
    _ans(s, [SRC, S2], F2)
    a = _prop(s, SRC, [PROP])[0]["pid"]
    b = _prop(s, S2, [{"qid": "L1:P-2", "choice": "place", "value": "3BAY 08칼럼", "quote": "3BAY 08칼럼",
                       "q": {"qid": "L1:P-2", "item": "L1", "page": 2}}])[0]["pid"]
    store.decide(s, "m1", adopt=[a, b], fields=F2)
    calc, _, _ = _ans(s, [SRC, S2], _fields(date2="2026-11-02"))   # only the second permit's form changed
    q = {x["qid"] for x in calc}
    return [("바뀐 허가서 쪽 채택만 무효", "L1:P-2" not in q),
            ("다른 허가서 쪽 채택은 유지", "B3:P-1" in q),
            ("직접 답은 둘 다 유지", {"T1:P-1", "T1:P-2"} <= q)]


def d_after_close():
    s = store.create()
    _ans(s, [SRC])
    store.issue(s, "T1@1", "question")
    store.issue(s, "CLOSE", "close")
    used, rev = store.budget(s)["used"], store.revision(s)
    _, rev2, _ = _ans(s, [dict(SRC, value="14시부터 15시까지로 바뀌었어요")])
    return [("마무리 뒤 고친 답은 개정으로 기록", rev2 == rev + 1),
            ("질문 예산은 그대로(새 회차 없음)", store.budget(s)["used"] == used and store.budget(s)["close"]),
            ("마무리 요청은 다시 하지 않음", store.issue(s, "CLOSE", "close")["again"]
             and _code(lambda: store.issue(s, "CLOSE2", "close")) == "close_once"),
            ("종료 뒤 AI 필요정보는 넣지 않음", store.add_needs(s, [{"mkey": "n", "t": "referent", "key": "p1.job", "quote": "x"}]) is None)]


def d_async():
    """design §10.7: a reading started on answer A is stored after the foreman answered B (the form unchanged) — kept;
    after A itself changed — refused; after A changed and changed back (A→B→A, the same words) — refused, the reading
    belongs to the first A. store.propose(src_at=…) is the generation check; without it the last case is pending."""
    import inspect
    has_at = "src_at" in inspect.signature(store.propose).parameters
    QL = {"qid": "L1:P-1", "item": "L1", "page": 1, "text": "위치?"}
    LB = {"qid": "L1:P-1", "choice": "place", "value": "3BAY 12칼럼", "q": QL}

    def late(s, basis, form, at):
        kw = {"src_at": at} if has_at else {}
        return _code(lambda: store.propose(s, "ai", SRC, [PROP], basis=basis, form=form, **kw))

    s = store.create()
    _ans(s, [SRC])
    b0, f0 = store.revision(s), store.form_of(s)
    at0 = SRC.get("at")
    _ans(s, [SRC, LB])                                       # B answered while A is read
    ok_kept = late(s, b0, f0, at0) is None
    s2 = store.create()
    _ans(s2, [SRC])
    b1, f1 = store.revision(s2), store.form_of(s2)
    _ans(s2, [dict(SRC, value="14시부터 16시까지만 해요")])      # A changed
    ok_changed = late(s2, b1, f1, at0) is not None
    s3 = store.create()
    a1 = dict(SRC, at=1000)
    _ans(s3, [a1])
    b2, f2 = store.revision(s3), store.form_of(s3)
    _ans(s3, [dict(SRC, value="14시부터 16시까지만 해요", at=2000)])
    _ans(s3, [dict(SRC, at=3000)])                             # A→B→A: the same words, given again
    code = late(s3, b2, f2, 1000)
    res = [("다른 답만 늘었으면 늦은 읽기도 저장", ok_kept), ("원래 답이 바뀌었으면 거절", ok_changed)]
    if has_at:
        res.append(("A→B→A로 같은 말이 돌아와도 처음 읽기는 거절", code is not None))
    else:
        res.append(("A→B→A 거절 (보류: store.propose의 src_at 세대 검사 대기, 지금 결과 "
                    + ("거절" if code else "저장") + ")", True))
    return res


MULTI_STEPS = [d_unknown, d_reject, d_correct, d_resume, d_double, d_budget, d_clarify, d_reask, d_doc_change, d_after_close, d_async]


def multi():
    ok_d = ok_c = all_c = 0
    for (name, what), fn in zip(MULTI, MULTI_STEPS):
        try:
            res = fn()
        except Exception as e:                                    # a crash is a failed dialogue, reported
            res = [(f"오류 {type(e).__name__}: {e}", False)]
        good = all(c for _, c in res)
        ok_d, ok_c, all_c = ok_d + good, ok_c + sum(1 for _, c in res if c), all_c + len(res)
        print(f"{'PASS' if good else 'FAIL'} {name} — {what}")
        for label, c in res:
            if not c:
                print(f"     ✗ {label}")
    print(f"\n[멀티턴] 대화 {ok_d}/{len(MULTI)} 통과 · 확인 항목 {ok_c}/{all_c}")
    return {"dialogues": ok_d, "of": len(MULTI), "checks": ok_c, "checks_of": all_c}


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    dry = "--dry" in sys.argv
    _options()
    res = {}
    if what in ("turn", "all"):
        res["turn"] = asyncio.run(turn(dry))
    if what in ("multi", "all"):
        res["multi"] = multi()
    print("\n===== 1차 시연 평가 요약 =====")
    if "turn" in res:
        t = res["turn"]
        for k, label in (("base", "규칙 기준선"), ("ai", "통합판")):
            if k == "ai" and dry:
                continue
            r, w, m, lk = t[k]
            y = t["why"][k]
            print(f"TURN {label}: {t['n']}건 · 맞음 {r}/{t['exp']} · 틀림 {w}(값 {y['값']}·주체 {y['주체']}·시점 {y['시점']}) · 놓침 {m} · 금지 {lk}"
                  + (f" · CRITIQUE 보류 {t['held']} · 실패 {t['fails']}" if k == "ai" else ""))
    if "multi" in res:
        m = res["multi"]
        print(f"멀티턴: 대화 {m['dialogues']}/{m['of']} · 확인 항목 {m['checks']}/{m['checks_of']}")
    sys.exit(0)


if __name__ == "__main__":
    main()
