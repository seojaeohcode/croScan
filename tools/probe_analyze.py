"""Measure 업로드 분석 (server/analyze.py) with the model on the server: time, output and what the server kept.

  python tools/probe_analyze.py [N permits]      # inside the staging container (LLM_URL set)
"""
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from server import analyze, extract  # noqa: E402
from make_demo_day import DIR, load, permit_name  # noqa: E402


async def main(n):
    permits = load("permits.json")
    permits = permits if isinstance(permits, list) else permits.get("permits", [])
    picked, kinds = [], set()
    for d in permits:                                # one of each kind first
        if d["kind"] not in kinds:
            picked.append(d); kinds.add(d["kind"])
    for d in picked[:n]:
        doc = extract.build(DIR / "허가서" / permit_name(d), d["kind"])
        t = time.time()
        r = await analyze.analyze(doc["fields"], [])
        meta = r.get("meta") or {}
        print(json.dumps({"permit": permit_name(d), "kind": d["kind"], "s": round(time.time() - t, 1), "status": r["status"],
                          "why": r.get("why"), "needs": [{k: x[k] for k in ("t", "doc", "name", "quote", "text")} for x in r["needs"]],
                          "dropped": meta.get("dropped"), "tokens": meta.get("usage") or meta.get("tokens")}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 3))
