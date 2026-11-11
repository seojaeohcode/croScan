"""Where a TURN's time goes on the CPU server (design §10): prompt reading vs writing, and how much of the prompt
the model's cache kept — a TURN after a TURN, and a TURN after another kind of call (the analysis) took the slot.

  python tools/probe_timing.py      # in a container on the model's network (LLM_URL set)
"""
import asyncio
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("CROSCAN_DATA", tempfile.mkdtemp(prefix="croscan_probe_"))     # a throwaway review store

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from server import augment, extract, llm, store, understand  # noqa: E402
from make_demo_day import DIR, load, permit_name  # noqa: E402

TEXTS = ["13시부터 15시까지 해요. 러그는 가스절단으로 6개 떼요.", "1시~3시요. 자른 러그는 로프에 묶어 아래로 내리고 하부는 통행 막아요.",
         "13~15시입니다. 위치는 3BAY 12-14 칼럼 블록 상부요."]


async def main():
    ps = load("permits.json")
    ps = ps if isinstance(ps, list) else ps.get("permits", [])
    d = next(x for x in ps if permit_name(x).startswith("8175"))
    fields = extract.build(DIR / "허가서" / permit_name(d), d["kind"])["fields"]
    open_, _, _, _ = augment.questions(fields, [])
    t1 = next(q for q in open_ if q["item"] == "T1")
    real = llm.call_json

    async def spy(kind, messages, schema, **kw):
        data, meta = await real(kind, messages, schema, **kw)
        print(f"  {kind}: 전체 {meta['ms']}ms · 프롬프트 {meta.get('prompt_n')}토큰 {meta.get('prompt_ms') and round(meta['prompt_ms'])}ms"
              f" (캐시 재사용 {meta.get('cache_n')}) · 쓰기 {meta.get('gen_n')}토큰 {meta.get('gen_ms') and round(meta['gen_ms'])}ms", flush=True)
        return data, meta
    llm.call_json = spy
    for i, t in enumerate(TEXTS):
        src = {"qid": t1["qid"], "choice": "partial", "value": t, "q": t1}
        print(f"TURN {i + 1}{' (다른 종류 호출 뒤)' if i == 2 else ''}")
        await understand.read(fields, [src], src)
        if i == 1:                     # another kind of prompt takes the slot in between
            print("다른 종류 호출(짧은 분석 흉내)")
            await llm.call_json("OTHER", [{"role": "system", "content": "JSON으로 답하라. " * 40}, {"role": "user", "content": "작업 위치는? 3BAY"}],
                                {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]}, think=0, out_tokens=32)


async def warm_case():
    """the question shown first is warmed (design §10.7); the answer comes after: only his words are read then. A real
    review session, so the reading takes the list stored by the warm-up (understand._WARM) as the API does."""
    ps = load("permits.json")
    ps = ps if isinstance(ps, list) else ps.get("permits", [])
    d = next(x for x in ps if permit_name(x).startswith("8175"))
    fields = extract.build(DIR / "허가서" / permit_name(d), d["kind"])["fields"]
    open_, _, _, _ = augment.questions(fields, [])
    t1 = next(q for q in open_ if q["item"] == "T1")
    for t in ["13시~15시입니다. 하부는 로프로 통제하고 러그는 그라인더로 3개 잘라요.", "오후 1시부터 3시까지, 위치는 3BAY 12-14칼럼 블록 위에요."]:
        sid = store.create()                                       # one review per answer: its own warm-up
        meta = (await understand.warm(fields, [], t1, sid)).get("meta") or {}
        print(f"미리 읽기: {meta.get('ms')}ms · 프롬프트 {meta.get('prompt_n')}토큰 (캐시 재사용 {meta.get('cache_n')})"
              f" · 저장된 목록 {len(understand._WARM.get((sid, t1['qid'])) or [])}개", flush=True)
        src = {"qid": t1["qid"], "choice": "partial", "value": t, "q": t1}
        out = await understand.read(fields, [src], src, sid=sid)
        m = out.get("meta") or {}
        print(f"  미리 읽은 뒤 TURN: 전체 {m.get('ms')}ms · 프롬프트 {m.get('prompt_n')}토큰 {m.get('prompt_ms') and round(m['prompt_ms'])}ms"
              f" (캐시 재사용 {m.get('cache_n')}) · 쓰기 {m.get('gen_n')}토큰 {m.get('gen_ms') and round(m['gen_ms'])}ms · {out['status']}", flush=True)


if __name__ == "__main__":
    if sys.argv[1:] == ["warm"]:
        asyncio.run(warm_case())
        sys.exit(0)
    asyncio.run(main())
