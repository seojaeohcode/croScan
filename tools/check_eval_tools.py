"""평가 도구 자체의 점검 (tools/eval_phase1.py modes·ablations, eval_nl_variants.py, usertest_report.py), with a
made-up model — the runners must measure what they say they measure.

  python tools/check_eval_tools.py
"""
import asyncio
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import eval_nl_variants as NV  # noqa: E402
import eval_phase1 as E  # noqa: E402
import usertest_report as UR  # noqa: E402
from server import augment, llm  # noqa: E402

OK = []


def check(name, cond):
    OK.append(bool(cond))
    print(f"{'PASS' if cond else 'FAIL'} {name}")


def main():
    fields = E._permits()["0735"]
    open_ = augment.questions(fields, [])[0]
    t1 = next(q for q in open_ if q["item"] == "T1")
    src = {"qid": t1["qid"], "choice": "partial", "value": "13시부터 15시까지 해요. 러그는 가스절단으로 6개 떼요.", "q": t1}
    seen = []

    async def fake(kind, messages, schema, **kw):
        seen.append((kind, schema, messages[-1]["content"], kw))
        props = schema["properties"]["props"]["items"]["properties"]
        qmap = {q: None for q in props["q"]["enum"]}
        ht1 = next(f"Q{i}" for i, q in enumerate(E.understand.candidates(fields, [src], src), 1) if q["item"] == "HT1")
        assert ht1 in qmap
        if "s" in props:
            return {"props": [{"q": ht1, "c": "gas", "v": "6", "who": "self", "when": "plan", "s": "S2"}]}, {"gen_n": 20}
        return {"props": [{"q": ht1, "c": "gas", "v": "6", "who": "self", "when": "plan", "quote": "러그는 가스절단으로 6개 떼요"}]}, {"gen_n": 40}
    real = llm.call_json
    llm.call_json = fake
    try:
        out = asyncio.run(E._read_clauses(fields, [src], src))
        kind, schema, user, _ = seen[-1]
        item = schema["properties"]["props"]["items"]
        check("절 번호 시험: 모델은 quote 대신 절 번호(s)를 고름", "quote" not in item["properties"] and item["properties"]["s"]["enum"] == ["S1", "S2"])
        check("절 번호 시험: 답이 [S1]·[S2]로 나뉘어 감", "[S1] 13시부터 15시까지 해요." in user and "[S2] 러그는" in user)
        check("절 번호 시험: 서버가 그 절을 근거로 되살려 같은 검사를 거침", out["props"] and out["props"][0]["quote"].startswith("러그는 가스절단으로 6개"))
        other = asyncio.run(E._second(fields, [src], src))
        check("두 번째 읽기는 온도 0.7로 따로 읽음", seen[-1][3].get("temperature") == 0.7 and other.get("HT1") == "gas")
    finally:
        llm.call_json = real
    # the case file of eval_nl_variants is read back in the TURN shape
    NV.OUT = Path(tempfile.mkdtemp(prefix="croscan_nl_")) / NV.OUT.name     # not into tools/ (read-only on the server)
    NV.main()
    sys.argv = [sys.argv[0], "turn", "--cases", str(NV.OUT)]
    cases = E._cases()
    check("150 × 8 사례 파일을 TURN 형태로 읽음", len(cases) == 150 and all(len(c[4]) == 8 for c in cases))
    c = next(x for x in cases if x[0].startswith("러그 가스절단 6개#3"))
    check("값 변형의 기대값이 문장과 함께 바뀜(6 → 9)", c[5]["HT1"][1]["v"] == ["9"] and "9개" in c[4][0])
    sys.argv = [sys.argv[0]]
    # comparison modes and ablations are switches of the runner, nothing else
    sys.argv = [sys.argv[0], "turn", "--mode", "3", "--no-critique", "--think", "64"]
    o = E._options()
    check("비교군·제거 시험 옵션", o["mode"] == 3 and o["critique"] is False and o["think"] == 64)
    sys.argv = [sys.argv[0]]
    # the user-test report reads the saved files and judges only what a file can tell
    d = Path(tempfile.mkdtemp())
    (d / "a.json").write_text(json.dumps({"who": "A", "runs": [{"task": "R2", "ok": True, "ms": 8000, "clicks": [], "notes": []},
                                                              {"task": "R3", "ok": True, "ms": 9000, "clicks": [], "notes": [{"text": "승인되는 거죠?"}]}]}),
                              encoding="utf-8")
    (d / "b.json").write_text(json.dumps({"who": "B", "runs": [{"task": "R2", "ok": False, "ms": 20000, "clicks": [], "notes": []}]}), encoding="utf-8")
    head, table, v = UR.report(UR.load([d / "a.json", d / "b.json"]))
    check("사용자 시험 집계: 참여자 2명", head.startswith("참여자 2명"))
    check("성공 1/2는 90% 기준 미달, 오해 한 건은 0건 기준 미달", "미달" in v["R2"] and "미달" in v["R3"] and "승인되는 거죠?" in table)
    print(f"\n{sum(OK)}/{len(OK)}")
    sys.exit(0 if all(OK) else 1)


if __name__ == "__main__":
    main()
