"""규칙 밖 「AI 검토 권장」 (PAIR_REVIEW, design §8.2): for two works the rules raised nothing about, the manager may ask
the model once whether a relation the rules do not cover could link them. A person asks for one pair; after a submission
the first BATCH near pairs are reviewed ahead at the lowest order of need (batch(): 20 is a batch size, not a cut —
the rest stay 「미분석」 and can be asked for), and each pair's state is kept: 미분석 · 대기 중 · 처리 중 · 실패 · 검토 완료.

What the model may do: pick a relation kind from a fixed list, one row of facts from each side that shows it, and a
question from a fixed list. What the server does: refuses pairs that are not on the same day or not close in time,
place or shared equipment (the prefilter); checks both rows exist and each is from its own side; has the relation
checked once against the two rows (critique.relation: anything but supports is shown only as 「근거 부족으로 보류」,
not as a recommendation; the review and the check share one DEADLINE, and with too little left for the check the
result is held 「시간 안에 확인하지 못해 보류」, not kept, 실패 until asked again); writes the sentence from a template.
A pair is one pair whichever way round it is asked
(a|b sorted). The result is a separate list 「AI 검토 권장 · 규칙 판정 아님」: it never creates or changes a rule
pair, a priority or a score, and adopting it does not make a rule (design §8.2: rules are made by review, counter
cases and a version). A review that finds nothing is not evidence that nothing links the two.
"""
import asyncio
import hashlib
import json
import re
import time

from . import critique, llm, pairs, safety

LABEL = "AI 검토 권장 · 규칙 판정 아님"
RELS = {"shared_equipment": "같은 설비·계통을 함께 쓰는 관계", "same_path": "같은 통로·이동 경로를 지나는 관계",
        "sequence_residual": "앞 작업이 남긴 것(잔불·가스·잔압·자재)이 다음 작업에 남는 관계", "overhead": "위아래로 겹치는 관계",
        "shared_air": "같은 공기·환기 공간을 쓰는 관계", "none": "관계를 찾지 못함"}
ASKS = {"Q_EQUIP": "두 작업이 같은 설비·계통을 쓰는 시각과 그동안의 차단·전환 계획",
        "Q_PATH": "두 작업의 통로·이동 경로와 그곳을 지나는 시각",
        "Q_RESIDUAL": "앞 작업이 끝난 뒤 남는 것(잔불·가스·잔압·자재)의 정리 계획과 다음 작업의 시작 시각",
        "Q_OVERHEAD": "위아래 작업의 실제 높이와 같은 시간에 있는지",
        "Q_AIR": "두 작업이 같은 공기를 쓰는지(환기·배기 방향, 개구부)"}
REL_ASK = {"shared_equipment": ("Q_EQUIP",), "same_path": ("Q_PATH",), "sequence_residual": ("Q_RESIDUAL",),
           "overhead": ("Q_OVERHEAD",), "shared_air": ("Q_AIR", "Q_RESIDUAL")}
ADJACENT_MIN = 60          # end → start within this many minutes counts as close in time
DEADLINE = 60.0            # seconds for the review and its relation check together (the screen says 최대 60초)
MAX_ROWS = 10              # facts per side given to the model
SYSTEM = ("너는 조선소 작업 사이의 위험 관계를 검토하는 도우미다. 두 작업의 사실 행(F번호)을 보고, croScan 규칙이 다루지 않는 위험 관계가 "
          "있을 수 있는지 고른다.\n규칙: 관계 rel은 보기에서만 고른다. 근거 행은 A쪽 행 하나(a)와 B쪽 행 하나(b)를 고른다. "
          "확인할 질문 ask는 보기에서만 고른다. 근거 행이 없거나 애매하면 rel=none, a=\"\", b=\"\", ask=\"\". 문장은 쓰지 않는다.")
_CACHE = {}
BATCH = 20                 # design §8.2: the batch reviewed ahead after an upload (a size, not an exclusion)
# the state of a pair not done yet: (day, a, b) -> "waiting" | "running"; a failure: (day, a, b) -> (digest, why)
_STATE, _FAIL = {}, {}
STATE_KO = {"not_run": "미분석", "waiting": "대기 중", "running": "처리 중", "fail": "실패", "done": "검토 완료"}


class Refused(Exception):
    pass


def _rows(P, start):
    """the facts of one work as numbered rows: [(F-id, field, value)]"""
    d, out = P["d"], []
    seen = set()
    for f, v in [("작업명", d.get("title") or "")] + list(P["fields"]):
        v = re.sub(r"\s+", " ", str(v or "")).strip()[:80]
        if not v or (f, v) in seen:
            continue
        seen.add((f, v))
        out.append((f, v))
    out = out[:MAX_ROWS - 2]
    out.append(("시간", ", ".join(f"{w['start']}~{w['end']}" for w in d.get("windows") or []) or "시간 없음"))
    out.append(("위치", (d.get("place") or "위치 없음").replace("대조립21공장 ", "")))
    return [(f"F{start + i}", f, v) for i, (f, v) in enumerate(out)]


def _shared(X, Y):
    """the IDs both works name (crane, panel, system, block)"""
    a = set().union(*X["ids"].values())
    b = set().union(*Y["ids"].values())
    return sorted(a & b)


def prefilter(det, a, b):
    """-> (X profile, Y profile, why close [text]) or raises Refused(reason). Same day (the day's documents), not a
    pair the rules already raised, and close: time overlap or end→start within 60 minutes, the same BAY or block, a
    shared equipment·system ID, or a time or a place not written."""
    if a == b:
        raise Refused("같은 작업입니다")
    D = safety.data()
    docs = {d["id"]: d for d in D["permits"] + D["plans"]}
    if a not in docs or b not in docs:
        raise Refused("이 작업일의 문서가 아닙니다")
    for i in (a, b):
        if docs[i]["type"] == "permit" and docs[i].get("works_today") is False:
            raise Refused(f"{i}는 이 작업일에 하지 않는 작업입니다")
    if any({p["a"], p["b"]} == {a, b} for p in det["pairs"]):
        raise Refused("이미 규칙 경보가 있는 작업쌍입니다. 규칙 판정을 보세요")
    X, Y = pairs.profile(docs[a]), pairs.profile(docs[b])
    why = []
    if not X["wins"] or not Y["wins"]:
        why.append("한쪽 작업 시간이 없음")
    else:
        ov = pairs.overlaps(X["wins"], Y["wins"])
        g = [x for x in (pairs.gap_after(X["wins"], Y["wins"]), pairs.gap_after(Y["wins"], X["wins"])) if x is not None]
        if ov:
            why.append("작업 시간이 겹침")
        elif g and min(g) <= ADJACENT_MIN:
            why.append(f"앞 작업이 끝나고 {min(g)}분 안에 이어짐")
    rel = pairs.place_rel(X, Y, True, True)
    if rel["kind"] == "unknown":
        why.append("한쪽 위치(칼럼)가 없음")
    elif rel["kind"] in ("same", "near", "far") and rel.get("bay"):
        why.append(f"같은 {rel['bay']}BAY")
    if X["ids"]["blocks"] & Y["ids"]["blocks"]:
        why.append("같은 블록")
    sh = _shared(X, Y)
    if sh:
        why.append("같은 설비·계통 번호 " + ", ".join(sh))
    if not why:
        raise Refused("시간·위치·공유 설비가 이어지지 않아 AI 검토 대상이 아닙니다")
    return X, Y, why


def _digest(rows):
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False).encode()).hexdigest()[:16]


def _no(d):
    return d.get("permit_no") or d["id"] if d["type"] == "permit" else d["id"]


def _current(det, a, b):
    """-> (X, Y, close, rows of A, rows of B, the documents' digest) of the pair as it is now, or raises Refused"""
    X, Y, close = prefilter(det, a, b)
    ra = _rows(X, 1)
    rb = _rows(Y, len(ra) + 1)
    return X, Y, close, ra, rb, _digest([ra, rb])


async def review(det, a, b, pri=llm.ASKED):
    """-> {status: ok|none|held|fail|refused, label, rel, rel_text, evidence [{doc, no, field, value}], question, why, close}"""
    a, b = sorted((a, b))                              # one pair whichever way round it is asked
    try:
        X, Y, close, ra, rb, dg = _current(det, a, b)
    except Refused as e:
        return {"status": "refused", "why": str(e), "label": LABEL}
    key = (det.get("date"), a, b, dg)
    if key in _CACHE:
        return _CACHE[key]
    sk = (det.get("date"), a, b)
    _STATE[sk] = "running"
    try:
        out = await _review(det, X, Y, close, ra, rb, key, pri)
    finally:
        _STATE.pop(sk, None)
    if out["status"] == "fail" or out.get("critique") == "late":       # not checked in time: not done (실패)
        _FAIL[sk] = (dg, out.get("why"))
    else:
        _FAIL.pop(sk, None)
    return out


async def _review(det, X, Y, close, ra, rb, key, pri):
    lines = ["A 작업 (" + _no(X["d"]) + "):"] + [f"{i} {f}: {v}" for i, f, v in ra]
    lines += ["B 작업 (" + _no(Y["d"]) + "):"] + [f"{i} {f}: {v}" for i, f, v in rb]
    lines += ["관계 보기: " + ", ".join(f"{k}={t}" for k, t in RELS.items()),
              "질문 보기: " + ", ".join(f"{k}={t}" for k, t in ASKS.items())]
    ids_a, ids_b = [i for i, _, _ in ra], [i for i, _, _ in rb]
    schema = {"type": "object", "additionalProperties": False, "required": ["rel", "a", "b", "ask"],
              "properties": {"rel": {"type": "string", "enum": list(RELS)}, "a": {"type": "string", "enum": ids_a + [""]},
                             "b": {"type": "string", "enum": ids_b + [""]}, "ask": {"type": "string", "enum": list(ASKS) + [""]}}}
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": "\n".join(lines)}]
    t0 = time.monotonic()                              # one deadline for the review and its check (Codex persona A12)
    try:
        data, meta = await llm.call_json("PAIR_REVIEW", msgs, schema, think=0, out_tokens=48, deadline=DEADLINE, pri=pri)
    except llm.LlmFail as e:
        return {"status": "fail", "why": e.code, "label": LABEL, "close": close}
    out = judge(data, ra, rb, X["d"], Y["d"], close)
    if out["status"] == "ok":                          # the relation checked against the two rows (design §9), once
        ea, eb = out["evidence"]
        kept, v = await critique.relation(f"{ea['no']} {ea['field']}: {ea['value']}", f"{eb['no']} {eb['field']}: {eb['value']}",
                                          out["rel_text"], pri=pri, deadline=DEADLINE - (time.monotonic() - t0))
        if not kept:
            if v == "fail":                            # a failed check is not kept: asked again next time
                return {"status": "fail", "why": "critique", "label": LABEL, "close": close}
            out = {**{k: out[k] for k in ("label", "rel", "rel_text", "evidence", "close")}, "status": "held", "critique": v,
                   "question": "", "why": critique.HELD_LATE if v == "late" else critique.HELD_REL}
            if v == "late":                            # no time left to check: held, never shown unchecked; not kept
                return out
    out["meta"] = {k: meta.get(k) for k in ("ms", "prompt_n", "gen_n")}
    _CACHE[key] = out
    if len(_CACHE) > 500:
        _CACHE.clear()
    return out


def judge(data, ra, rb, da, db, close):
    """the model's pick checked: a relation from the list, a row of A's and a row of B's that exist, the question
    the relation allows (else the relation's own); the sentence is the server's"""
    rel = data.get("rel") if isinstance(data, dict) else None
    if rel not in RELS:
        return {"status": "fail", "why": "schema", "label": LABEL, "close": close}
    if rel == "none":
        return {"status": "none", "label": LABEL, "rel": "none", "rel_text": RELS["none"], "evidence": [], "question": "", "close": close,
                "why": "AI가 규칙 밖 관계를 찾지 못함 (찾지 못한 것이 관계가 없다는 뜻은 아님)"}
    A = {i: (f, v) for i, f, v in ra}
    B = {i: (f, v) for i, f, v in rb}
    if data.get("a") not in A or data.get("b") not in B:          # both sides' evidence, each from its own side
        return {"status": "none", "label": LABEL, "rel": rel, "rel_text": RELS[rel], "evidence": [], "question": "", "close": close,
                "why": "양쪽 근거 행이 없어 쓰지 않음"}
    ask = data.get("ask") if data.get("ask") in REL_ASK[rel] else REL_ASK[rel][0]
    fa, va = A[data["a"]]
    fb, vb = B[data["b"]]
    ev = [{"doc": da["id"], "no": _no(da), "field": fa, "value": va}, {"doc": db["id"], "no": _no(db), "field": fb, "value": vb}]
    text = f"{_no(da)} {fa} 「{va}」와 {_no(db)} {fb} 「{vb}」 사이에 {RELS[rel]}가 있을 수 있습니다. 규칙 판정이 아니며, 확인할 것: {ASKS[ask]}."
    return {"status": "ok", "label": LABEL, "rel": rel, "rel_text": RELS[rel], "evidence": ev, "question": ASKS[ask], "ask": ask,
            "text": text, "close": close}


def targets(det):
    """the pairs a review can be asked for now: the near pairs that pass the prefilter, each once (a|b sorted)"""
    out = []
    for x in det.get("near") or []:
        a, b = sorted((x["a"], x["b"]))
        if (a, b) in out:
            continue
        try:
            prefilter(det, a, b)
        except Refused:
            continue
        out.append((a, b))
    return out


def states(det):
    """each current target's state, a|b -> {state, ko}: 검토 완료 (a result of the documents as they are now), 처리 중,
    대기 중, 실패 (of these documents), 미분석"""
    day, out = det.get("date"), {}
    for a, b in targets(det):
        try:
            *_, dg = _current(det, a, b)
        except Refused:
            continue
        s = ("done" if (day, a, b, dg) in _CACHE else _STATE.get((day, a, b))
             or ("fail" if (_FAIL.get((day, a, b)) or (None,))[0] == dg else "not_run"))
        out[f"{a}|{b}"] = {"state": s, "ko": STATE_KO[s]}
    return out


def listing(day, det=None):
    """the reviews of this day's documents as they are now (the separate list, design §8.2): only results made from
    the current documents (their digest) for a pair that is still not a rule pair; counts over the current targets.
    Results of an earlier version of the documents are not listed (kept for nothing: asked again they are redone)."""
    items, seen = [], set()
    for k, v in _CACHE.items():
        if k[0] != day or (k[1], k[2]) in seen:
            continue
        if det is not None:
            try:
                *_, dg = _current(det, k[1], k[2])
            except Refused:
                continue                               # a rule pair now, or no longer close: not an AI review item
            if dg != k[3]:
                continue
        seen.add((k[1], k[2]))
        items.append({"a": k[1], "b": k[2], "key": f"{k[1]}|{k[2]}", **v})
    tg = targets(det) if det is not None else []
    done = {(x["a"], x["b"]) for x in items}
    count = {s: sum(x["status"] == s for x in items) for s in ("ok", "none", "held")}
    st = states(det) if det is not None else {}
    by = {s: sum(1 for v in st.values() if v["state"] == s) for s in STATE_KO}
    return {"label": LABEL, "items": items, "states": st,
            "count": {**count, "all": len(items), "targets": len(tg), "done": len(done & set(tg)),
                      "not_run": by["not_run"], "waiting": by["waiting"], "running": by["running"], "fail": by["fail"]}}


async def batch(det, n=BATCH):
    """the batch reviewed ahead (design §8.2): the first n near pairs that pass the prefilter, one by one at the
    lowest order of need (a person's call takes the slot first); one that failed is tried once more at the end.
    -> counts of candidates, done, failed, not done"""
    cands = targets(det)
    day = det.get("date")
    run = cands[:n]
    for a, b in run:
        _STATE.setdefault((day, a, b), "waiting")
    done, failed = 0, []

    async def one(a, b):
        """a review at the lowest order; one that gave the slot to a person (cancelled) counts as failed, to be tried again"""
        try:
            r = await review(det, a, b, pri=llm.WARM)
            return "fail" if r.get("critique") == "late" else r["status"]        # held unchecked: tried again
        except asyncio.CancelledError:
            t = asyncio.current_task()
            if t is None or not hasattr(t, "uncancel") or t.uncancel() > 0:
                raise                                   # cancelled from outside (the server stopping): stop
            return "fail"
    try:
        for a, b in run:
            s = await one(a, b)
            done += s in ("ok", "none", "held")
            if s == "fail":
                failed.append((a, b))
        again = failed
        failed = []
        for a, b in again:                              # one retry each
            s = await one(a, b)
            done += s in ("ok", "none", "held")
            failed += [(a, b)] if s == "fail" else []
    finally:
        for a, b in run:
            if _STATE.get((day, a, b)) == "waiting":
                _STATE.pop((day, a, b), None)
    return {"candidates": len(cands), "done": done, "failed": len(failed), "left": max(0, len(cands) - done - len(failed))}
