"""제출본 → 관리자 보기 (Codex A6, design §6·§8.1): the safety manager's submission list and the day's judgement
read the foremen's latest submissions.

  python tools/check_submit_link.py        # needs the demo day (samples/시연_하루); runs on a throwaway database

A submission whose permit number is not in the day's list (0701) is listed apart with its documents, never dropped;
a submission of a permit in the list adds the place and times its answers corrected through the hybrid path (new
alarms can appear, the documents' alarms stay: pairs.floor) and every document says which version it used.
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ["CROSCAN_DATA"] = tempfile.mkdtemp(prefix="croscan_link_")
sys.path.insert(0, str(ROOT))
from fastapi.testclient import TestClient  # noqa: E402
from server import app as A, pairs, safety, submissions, workplan  # noqa: E402

OK = []


def check(name, cond):
    OK.append(bool(cond))
    print(f"{'PASS' if cond else 'FAIL'} {name}")


def main():
    D = safety.data()
    day = D["date"]
    p32 = next(p for p in D["permits"] if p["id"] == "0732")
    no = p32["permit_no"]
    ans = [{"qid": f"L1:{no}", "choice": "place", "value": "3BAY 08-10 칼럼 E42P 블록 상부"},
           {"qid": f"T2:{no}", "choice": "partial", "value": "13:00~14:00"}]
    t = time.time()
    s1 = submissions.create("sess1", 1, "k1", {"permit": b"%PDF a", "checklist": b"%PDF b"}, {"fields": p32["_fields"], "answers": ans},
                            {"permit_no": no, "label": p32["label"], "who": "test", "dates": [day]}, t)
    out_no = no[:-4] + "0701"
    s2 = submissions.create("sess2", 1, "k2", {"permit": b"%PDF c"}, {"fields": {}, "answers": []},
                            {"permit_no": out_no, "label": "화기", "who": "test", "dates": [day]}, t + 1)
    c = TestClient(A.app)
    v = c.get("/api/safety/submissions").json()
    out = {x["permit_no"]: x for x in v.get("_outside", [])}
    check("0701 제출은 관리자 목록에 「이 날 작업 목록에 없는 제출」로 (버리지 않음)", out.get(out_no, {}).get("why") == safety.OUTSIDE
          and out[out_no]["id"] == s2["id"] and out[out_no]["files"] == ["permit"])
    check("작업 목록 안의 제출본은 판정 자료 판(제출본 반영)과 함께", v.get(no, {}).get("id") == s1["id"] and v[no]["used"]["version"] == safety.VERSION_SUB
          and v[no]["used"]["values"]["위치"] == "3BAY 08-10 칼럼 E42P 블록 상부")
    det = c.post("/api/safety/detect").json()
    base = pairs.detect()
    keys = lambda R: {(p["key"], r["rule"], r["cause"], r["exposed"]) for p in R["pairs"] for r in p["reasons"]}  # noqa: E731
    check("판정: 0732의 제출본 위치·시간으로 새 경보(0732 × WP-1029-01)", any(p["key"] == "0732|WP-1029-01" for p in det["pairs"]))
    check("판정: 서류 기준 경보는 모두 남음(floor)", keys(det) >= keys(base))
    check("판정: 문서마다 판정 자료 판(제출본 반영 / 서류 기준)", det["hybrid"]["versions"]["0732"]["version"] == safety.VERSION_SUB
          and "0732" in det["hybrid"]["submitted"] and not any(k.endswith("0701") for k in det["hybrid"]["versions"]))
    check("변경 기록: 새 경보에 제출본 위치·시간이 붙음", any(x["key"] == "0732|WP-1029-01" and any(f["item"].startswith("제출본") for f in x["from"])
                                                    for x in det["hybrid"]["changes"]["new"]))
    # Codex final A6: a place he corrected in the permit's own field (no answer) counts as well — against the uploaded original
    import copy
    f2 = copy.deepcopy(p32["_fields"])
    loc = next(k for k, f in f2.items() if isinstance(f, dict) and f.get("key") == "location")
    f2[loc]["original"] = f2[loc].get("original", f2[loc]["value"])
    f2[loc]["value"] = "3BAY 08-10 칼럼"
    sv = safety.submitted_values({"fields": f2, "answers": []}, day, no)
    check("칸을 직접 고친 위치도 관리자 입력에 들어감(답 없이)", (sv.get("place") or "").startswith("3BAY 08-10 칼럼"))
    check("고치지 않은 제출본은 바뀐 값 없음", safety.submitted_values({"fields": p32["_fields"], "answers": []}, day, no) == {})
    # the corrected plan values kept at 제출 (the upload and its edits do not last)
    tok = "a" * 32
    d = workplan.CACHE / tok
    d.mkdir(parents=True)
    rec = {"doc_no": "WP-1029-02", "title": "시험", "location": "2BAY", "start": f"{day}T09:00", "end": f"{day}T10:00",
           "items": [{"key": "location", "value": "2BAY", "fk": "p1.r0"}, {"key": "start", "value": f"{day} 09:00", "fk": "p1.r1"},
                     {"key": "end", "value": f"{day} 10:00", "fk": "p1.r2"}]}
    (d / "plans.json").write_text(json.dumps([rec]), encoding="utf-8")
    pv = safety.plan_values(tok, {"0": {"p1.r0": "3BAY 08-10 칼럼 E42P 블록", "p1.r1": f"{day} 13:00"}}, [0])
    check("제출 때 고친 계획서 값(위치·시작)을 스냅숏에 남김", pv == [{"doc_no": "WP-1029-02", "title": "시험", "place": "3BAY 08-10 칼럼 E42P 블록",
                                                        "start": f"{day}T13:00", "end": f"{day}T10:00", "changed": ["location", "start"]}])
    check("확인하지 않은 계획서·없는 업로드는 넣지 않음", safety.plan_values(tok, {}, []) == [] and safety.plan_values("b" * 32, {}, [0]) == [])
    check("제출 안내: 0701은 관리자 작업 목록에 연결 안 됨", safety.placement(out_no, [day]) == {"day": day, "listed": False})
    print(f"\n{sum(OK)}/{len(OK)}")
    sys.exit(0 if all(OK) else 1)


if __name__ == "__main__":
    main()
