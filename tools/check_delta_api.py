"""변경 구역 재분석 API (design §1.4 DISCOVER_DELTA, gap_audit #10): /api/analyze/delta on a demo permit (8175 고소).

  python tools/check_delta_api.py

Before the first analysis nothing is read; after it, only the changed fields go to the model (the confirmed 작업계획서
is read beside them, as in the first analysis); a found need becomes a question; nothing changed → no model call;
after the review ended nothing is added. The model is a fake.
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ["CROSCAN_DATA"] = tempfile.mkdtemp(prefix="croscan_delta_")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from fastapi.testclient import TestClient  # noqa: E402
from server import analyze, extract, llm, store  # noqa: E402
from server import app as webapp  # noqa: E402
from make_demo_day import DIR, load, permit_name  # noqa: E402

OK = []


def check(name, cond):
    OK.append(bool(cond))
    print(f"{'PASS' if cond else 'FAIL'} {name}")


def main():
    ps = load("permits.json")
    ps = ps if isinstance(ps, list) else ps.get("permits", [])
    d = next(x for x in ps if permit_name(x).startswith("8175"))
    F = extract.build(DIR / "허가서" / permit_name(d), d["kind"])["fields"]
    F2 = {**F, "p1.job": {**F["p1.job"], "value": "그 크레인으로 블록 반출, 제어반 정비 및 정전"}}
    seen, real = [], llm.call_json

    async def fake(kind, messages, schema, **kw):
        ids = schema["properties"]["needs"]["items"]["properties"]["f"]["enum"]
        seen.append({"kind": kind, "ids": ids, "user": messages[-1]["content"], **kw})
        job = next(r[0] for r in analyze.inputs(F2, [])[0] if r[1] == "p1.job")
        return {"needs": [{"t": "referent", "f": job, "q": "그 크레인으로 블록 반출", "f2": "", "q2": ""}]}, {}

    c = TestClient(webapp.app)
    llm.call_json = fake
    try:
        sid = c.post("/api/dialogues").json()["session_id"]
        r = c.post("/api/analyze/delta", json={"fields": F2, "session_id": sid}).json()
        check("첫 분석 전에는 다시 읽지 않음", r["status"] == "none" and not seen)
        store.put_job(sid, "analyze", "done", {"rowhash": analyze.rowhash(analyze.inputs(F, [])[0])})
        r = c.post("/api/analyze/delta", json={"fields": F2, "session_id": sid}).json()
        check("바뀐 칸만 읽어 질문 후보 1건", r["status"] == "ok" and r["found"] == 1 and r["changed"] == ["p1.job"]
              and seen and seen[-1]["kind"] == "DISCOVER_DELTA" and seen[-1].get("pri") == llm.PREPARED)
        check("기준이 새 내용으로 바뀜(같은 칸을 또 읽지 않음)", store.job(sid, "analyze").get("delta") == 1)
        n = len(seen)
        r = c.post("/api/analyze/delta", json={"fields": F2, "session_id": sid}).json()
        check("바뀐 칸이 없으면 모델을 부르지 않음", r["status"] == "none" and len(seen) == n)
        sid2 = c.post("/api/dialogues").json()["session_id"]
        store.put_job(sid2, "analyze", "done", {"rowhash": analyze.rowhash(analyze.inputs(F, [])[0])})
        store.close_review(sid2)
        r = c.post("/api/analyze/delta", json={"fields": F2, "session_id": sid2}).json()
        check("검토가 끝난 뒤에는 질문을 더하지 않음", r["status"] == "late" and r["found"] == 0)
        calls = []
        orig = webapp._plan_for
        webapp._plan_for = lambda s, f, p: (calls.append(p), (None, {}))[1]
        try:
            sid3 = c.post("/api/dialogues").json()["session_id"]
            store.put_job(sid3, "analyze", "done", {"rowhash": analyze.rowhash(analyze.inputs(F, [])[0])})
            c.post("/api/analyze/delta", json={"fields": F2, "session_id": sid3, "plans": {"token": "t", "idx": [0]}})
        finally:
            webapp._plan_for = orig
        check("확인한 작업계획서 정보가 다시 읽기에도 전달됨", calls == [{"token": "t", "idx": [0]}])
    finally:
        llm.call_json = real
    print(f"\n{sum(OK)}/{len(OK)}")
    sys.exit(0 if all(OK) else 1)


if __name__ == "__main__":
    main()
