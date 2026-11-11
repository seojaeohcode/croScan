"""시간·부하 측정 (design §10.6): on the server, with the model.

  python tools/probe_load.py turn200 [--n 200]        # TURN p50/p95, completion, held share
  python tools/probe_load.py dialogues [--n 30] [--human 20] [--warm]   # whole dialogues: model wait + assumed reading/typing
  python tools/probe_load.py cache                    # the same list warmed / cold, session switch (two permits alternating)
  python tools/probe_load.py background               # TURN alone vs TURN while an upload analysis runs
  python tools/probe_load.py concurrent [--n 4]       # N foremen reading at once
  python tools/probe_load.py all
  --fake 0.2   a made-up model that answers after 0.2 s (to check the runner here, without the model)

Times are measured from the request to the checked result, queue included (design §10.1); a failure or a timeout is
counted as such and never taken out of the times. Results go to CROSCAN_DATA/probe_load.json as well.
"""
import asyncio
import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("CROSCAN_DATA", tempfile.mkdtemp(prefix="croscan_load_"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from server import analyze, augment, critique, extract, llm, store, understand  # noqa: E402
from make_demo_day import DIR, load, permit_name  # noqa: E402
from eval_phase1_cases import TURN  # noqa: E402

BANK = {  # answers by the question they answer: what a foreman would type (typed choices only)
    "T1": ("partial", "13시부터 15시까지 해요. 러그는 가스절단으로 6개 떼고 하부는 통제해요."),
    "T0": ("value", "13:00~15:00"),
    "L1": ("place", "3BAY 12-14 칼럼 블록 상부입니다."),
    "B3": ("yes", "옆에서 도장팀이 터치업한다고 들었어요."),
    "HT1": ("gas", "가스절단으로 6개요."),
    "HT2": ("text", "떼어낸 러그는 로프로 내려서 하부에 모아요."),
    "LI1": ("text", "OH-21-03 크레인 한 대로 옮겨요."),
    "LO3": ("text", "MCC-2 패널을 9시에 끊고 11시에 복구해요."),
    "H2": ("text", "산소·LPG로 절단해요."),
    "CF2": ("text", "아르곤 퍼지 배관 밸브를 잠가 둡니다."),
}


def _arg(name, default):
    return type(default)(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default


def _pct(xs, p):
    xs = sorted(xs)
    return xs[max(0, min(len(xs) - 1, int(round(len(xs) * p)) - 1))] if xs else 0


def _fake(delay):
    """a made-up model: answers after delay seconds with nothing to propose (checks the runner, not the model)"""
    async def call(kind, messages, schema, **kw):
        await asyncio.sleep(delay)
        key = next(iter(schema.get("required") or ["props"]))
        return {key: []}, {"ms": int(delay * 1000), "prompt_n": 0, "gen_n": 1, "cache_n": 0}

    async def prefill(kind, messages, **kw):
        await asyncio.sleep(delay / 2)
        return {"ms": int(delay * 500), "prompt_n": 0, "cache_n": 0}
    llm.call_json, llm.prefill = call, prefill


_FIELDS = {}


def fields_of(prefix):
    if prefix not in _FIELDS:
        ps = load("permits.json")
        ps = ps if isinstance(ps, list) else ps.get("permits", [])
        d = next(x for x in ps if permit_name(x).startswith(prefix))
        _FIELDS[prefix] = extract.build(DIR / "허가서" / permit_name(d), d["kind"])["fields"]
    return _FIELDS[prefix]


async def one(fields, q, choice, text, sid=None, answers=()):
    """one answer read as the API does (rules, then the model, then CRITIQUE) -> (seconds, status, proposals, held, meta)"""
    src = {"qid": q["qid"], "choice": choice, "value": text, "q": q}
    t = time.time()
    rule, _ = augment.interpret(fields, list(answers) + [src], src)
    out = await understand.read(fields, list(answers) + [src] + rule, src, sid=sid)
    held = []
    if out.get("props"):
        out["props"], held = await critique.review(fields, src, out["props"], sid=sid)
    return time.time() - t, out["status"], len(out.get("props") or []), len(held) + len(out.get("apart") or []), out.get("meta") or {}


def _cases(n):
    """n (permit, question, choice, text) from the 30 × 2 reviewed answers, in turn"""
    flat = [(pno, item, ch, t) for _, pno, item, ch, texts, _, _ in TURN for t in texts]
    return [flat[i % len(flat)] for i in range(n)]


async def turn200(n):
    times, status, held, props = [], {}, 0, 0
    for pno, item, ch, text in _cases(n):
        f = fields_of(pno)
        q = next((x for x in augment.questions(f, [])[0] if x["item"] == item), None)
        if not q:
            continue
        s, st, p, h, _ = await one(f, q, ch, text)
        times.append(s)
        status[st] = status.get(st, 0) + 1
        props, held = props + p, held + h
    done = status.get("ok", 0) + status.get("none", 0)
    res = {"n": len(times), "p50": statistics.median(times) if times else 0, "p95": _pct(times, 0.95), "max": max(times or [0]),
           "completed": done, "failed": status.get("fail", 0), "proposals": props, "held": held}
    print(f"[TURN {res['n']}] p50 {res['p50']:.1f}s · p95 {res['p95']:.1f}s · 최대 {res['max']:.1f}s · 완료 {done}/{res['n']}"
          f" · 실패 {res['failed']} · 제안 {props} · 보류·따로 {held}")
    return res


async def dialogues(n, human, warm):
    """whole dialogues on the demo permits: the open typed questions answered from BANK in order; the model's wait
    and an assumed reading/typing time per question (human); with --warm each question is warmed when shown"""
    totals, waits, asks = [], [], []
    pnos = ["8175", "6733", "6988", "7618", "7835", "8741", "9488", "9715", "8602"]
    for i in range(n):
        f = fields_of(pnos[i % len(pnos)])
        sid = store.create()
        answers, wait, k = [], 0.0, 0
        for _ in range(12):
            open_ = [q for q in augment.questions(f, answers)[0] if q["item"].split(".")[0] in BANK and not any(a["qid"] == q["qid"] for a in answers)]
            if not open_:
                break
            q = open_[0]
            ch, text = BANK[q["item"].split(".")[0]]
            if not any(c["id"] == ch for c in q["choices"]):
                ch = next((c["id"] for c in q["choices"] if c.get("ask")), q["choices"][0]["id"])
            k += 1
            if warm:
                wt = time.time()
                await understand.warm(f, answers, q, sid)
                wait += max(0.0, (time.time() - wt) - human)           # warming while he reads: only what is left over waits
            s, _, _, _, _ = await one(f, q, ch, text, sid=sid if warm else None, answers=answers)
            wait += s
            answers.append({"qid": q["qid"], "choice": ch, "value": text, "q": q})
        waits.append(wait)
        asks.append(k)
        totals.append(wait + human * k)
    res = {"n": n, "asks_median": statistics.median(asks), "wait_p50": statistics.median(waits), "total_p50": statistics.median(totals),
           "total_p95": _pct(totals, 0.95), "six_min": sum(1 for t in totals if t <= 360)}
    print(f"[대화 {n}] 질문 중앙값 {res['asks_median']} · 모델 대기 중앙값 {res['wait_p50']:.0f}s · 전체(읽기·입력 {human}s/질문 가정) p50 "
          f"{res['total_p50']:.0f}s p95 {res['total_p95']:.0f}s · 6분 안 {res['six_min']}/{n}" + (" · 미리 읽기 켬" if warm else ""))
    return res


async def cache():
    """the same list read cold (cache off) and warmed; then two permits alternating (session switch)"""
    out = {}
    f = fields_of("8175")
    q = next(x for x in augment.questions(f, [])[0] if x["item"] == "T1")
    text = BANK["T1"][1]
    payload = llm._payload
    llm._payload = lambda *a, **k: {**payload(*a, **k), "cache_prompt": False}
    s, *_, m = await one(f, q, "partial", text)
    llm._payload = payload
    out["cold"] = {"s": s, "prompt_n": m.get("prompt_n"), "cache_n": m.get("cache_n")}
    sid = store.create()
    await understand.warm(f, [], q, sid)
    s, *_, m = await one(f, q, "partial", text, sid=sid)
    out["warm"] = {"s": s, "prompt_n": m.get("prompt_n"), "cache_n": m.get("cache_n")}
    sw = []
    g = fields_of("6733")
    q2 = next(x for x in augment.questions(g, [])[0] if x["item"] == "T1")
    for i in range(6):
        ff, qq = (f, q) if i % 2 == 0 else (g, q2)
        s, *_, m = await one(ff, qq, "partial", text)
        sw.append({"s": s, "prompt_n": m.get("prompt_n"), "cache_n": m.get("cache_n")})
    out["switch"] = sw
    print(f"[캐시] 끔 {out['cold']['s']:.1f}s(프롬프트 {out['cold']['prompt_n']}) · 미리 읽기 {out['warm']['s']:.1f}s(프롬프트 {out['warm']['prompt_n']},"
          f" 재사용 {out['warm']['cache_n']}) · 허가서 교대 {[round(x['s'], 1) for x in sw]}")
    return out


async def background():
    f = fields_of("8175")
    q = next(x for x in augment.questions(f, [])[0] if x["item"] == "T1")
    alone = [(await one(f, q, "partial", BANK["T1"][1]))[0] for _ in range(3)]
    job = asyncio.create_task(analyze.analyze(fields_of("6733"), []))
    await asyncio.sleep(0.5)
    busy = [(await one(f, q, "partial", BANK["T1"][1]))[0] for _ in range(3)]
    try:
        res = await job
    except asyncio.CancelledError:
        if not job.cancelled():
            raise
        res = {"status": "preempted"}          # the foreman's answer took the slot from it, as /api/analyze reports
    out = {"alone": statistics.median(alone), "with_analysis": statistics.median(busy), "analysis": res["status"]}
    print(f"[배경 작업] TURN 단독 {out['alone']:.1f}s · 업로드 분석 중 {out['with_analysis']:.1f}s (분석 {res['status']}: 반장 답이 먼저)")
    return out


async def concurrent(n):
    f = fields_of("8175")
    q = next(x for x in augment.questions(f, [])[0] if x["item"] == "T1")
    t = time.time()
    got = await asyncio.gather(*[one(f, q, "partial", BANK["T1"][1]) for _ in range(n)])
    each = [g[0] for g in got]
    out = {"n": n, "wall": time.time() - t, "each_p50": statistics.median(each), "each_max": max(each), "failed": sum(1 for g in got if g[1] == "fail")}
    print(f"[동시 {n}명] 전체 {out['wall']:.1f}s · 1인 중앙값 {out['each_p50']:.1f}s 최대 {out['each_max']:.1f}s · 실패 {out['failed']}"
          f" (슬롯 1개: 나중 사람은 줄을 섬)")
    return out


async def main():
    what = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "all"
    if "--fake" in sys.argv:
        _fake(_arg("--fake", 0.2))
    res = {}
    if what in ("turn200", "all"):
        res["turn200"] = await turn200(_arg("--n", 200) if what == "turn200" else 200)
    if what in ("dialogues", "all"):
        res["dialogues"] = await dialogues(_arg("--n", 30) if what == "dialogues" else 30, _arg("--human", 20.0), "--warm" in sys.argv)
    if what in ("cache", "all"):
        res["cache"] = await cache()
    if what in ("background", "all"):
        res["background"] = await background()
    if what in ("concurrent", "all"):
        res["concurrent"] = await concurrent(_arg("--n", 4) if what == "concurrent" else 4)
    (Path(os.environ["CROSCAN_DATA"]) / "probe_load.json").write_text(json.dumps(res, ensure_ascii=False, default=str), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
