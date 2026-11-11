"""대화 저장소·확인·이벤트·작업 (design §2.1·§2.3·§3.6·§12.1·§19.2·§19.4; gap_audit #1 #2 #3 #4 #5 #13 #16 #17).

  python tools/check_dialogue_api.py

Facts carry polarity·modality·phase·version; a confirmation is checked against what the card showed (displayed
digest) and the revision it was shown at, and recorded with who and what; a restart leaves cut-off jobs
「interrupted」 and gives their model calls back; answer changes, what they expired and changes after the close are
events; the dialogue API (GET dialogue, events, confirm, jobs, stage); a proposal's destination (전→후).
Runs on a throwaway database; part B needs the demo day (samples/시연_하루) for the permit 6733.
"""
import asyncio
import copy
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ["CROSCAN_DATA"] = tempfile.mkdtemp(prefix="croscan_dlg_")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from server import store  # noqa: E402

OK = []


def check(name, cond):
    OK.append(bool(cond))
    print(f"{'PASS' if cond else 'FAIL'} {name}")


def raises(name, fn, code):
    try:
        fn()
        check(name, False)
        return None
    except store.StoreError as e:
        check(name, e.code == code)
        return e


def fields(pno="P-1", date="2026-10-31"):
    return {"p1.permit_no": {"key": "permit_no", "page": 1, "value": pno}, "p1.date_1": {"key": "date_1", "page": 1, "value": date}}


F = fields()
QT1 = {"qid": "T1:P-1", "item": "T1", "page": 1, "text": "시간?", "choices": [{"id": "partial", "label": "실제 시간대 입력", "ask": "시간"}]}
QB3 = {"qid": "B3:P-1", "item": "B3", "page": 1, "text": "병행?", "choices": [{"id": "yes", "label": "있음", "ask": "무엇"}, {"id": "no", "label": "없음"}]}
QL1 = {"qid": "L1:P-1", "item": "L1", "page": 1, "text": "위치?", "choices": [{"id": "place", "label": "위치 입력", "ask": "위치"}]}
SRC = {"qid": "T1:P-1", "choice": "partial", "value": "13시부터 15시까지, 옆에서 도장팀이 터치업해요", "q": QT1, "at": 1000}
PROP = {"qid": "B3:P-1", "choice": "yes", "value": "도장팀 터치업", "q": QB3, "by": "T1:P-1", "quote": "옆에서 도장팀이 터치업해요", "when": "plan", "who": "other"}


def ans(sid, answers):
    return store.answers_for(sid, answers, F, store.revision(sid))


def store_part():
    # #1 facts
    sid = store.create()
    ans(sid, [SRC])
    p1 = store.propose(sid, "ai", SRC, [PROP], basis=store.revision(sid))[0][0]
    no = dict(PROP, qid="L1:P-1", q=QL1, choice="no", value="")
    store.propose(sid, "rule", SRC, [no], basis=store.revision(sid))
    fs = {f["fact_id"]: f for f in store.facts(sid, F)}
    t = fs.get("T:T1@1", {})
    check("#1 직접 답은 진술 사실(stated, 양태 asserted, 시점 미지정)", t.get("acceptance") == "stated" and t.get("modality") == "asserted" and t.get("version") == 1)
    f1 = fs.get(p1["pid"], {})
    check("#1 읽기 사실: 긍정·예정(planned)·판1·확인 전, 근거는 원래 답과 구절", f1.get("polarity") == "positive" and f1.get("phase") == "planned"
          and f1.get("version") == 1 and f1.get("status") == "proposed" and f1.get("acceptance") == "unconfirmed"
          and f1["evidence_ids"][0].startswith("answer:T1@1#") and f1["depends_on"][0].startswith("T1@1@"))
    check("#1 「없음」 보기는 부정(negative)", any(f["polarity"] == "negative" for f in fs.values() if f["qid"] == "L1:P-1"))
    store.decide(sid, "r1", reject=[p1["pid"]], fields=F)
    p2 = store.propose(sid, "ai", SRC, [dict(PROP, value="도장팀 3명 터치업")], basis=store.revision(sid))[0][0]
    fs = {f["fact_id"]: f for f in store.facts(sid, F)}
    check("#1 뺀 읽기는 대체됨(superseded)·끝난 시각, 같은 질문의 새 읽기는 판2", fs[p1["pid"]]["status"] == "superseded" and fs[p1["pid"]]["valid_to"]
          and fs[p2["pid"]]["version"] == 2)
    check("#1 대기 중 제안에도 양태·시점·판이 붙음", all(k in store.pending(sid, F)[0] for k in ("polarity", "modality", "phase", "version")))

    # #2 the confirmation contract
    shown = [dict(p2)]
    dg = store.digest(shown)
    e = raises("#2 카드에 보인 내용과 다르면 거절(stale_display)", lambda: store.decide(sid, "c0", adopt=[p2["pid"]], fields=F, displayed="00000000"), "stale_display")
    check("#2 거절에 지금 내용이 붙음", e and e.extra.get("changes") and e.extra["changes"][0]["value"] == "도장팀 3명 터치업")
    rev = store.revision(sid)
    store.propose(sid, "ai", SRC, [dict(PROP, qid="L1:P-1", q=QL1, choice="place", value="3BAY")], basis=rev)    # a reading lands
    r = store.decide(sid, "c1", adopt=[p2["pid"]], fields=F, displayed=dg, expected=rev)
    check("#2 보인 그대로·읽기 저장만 있었으면 확인됨", r["adopted"] and r["adopted"][0]["pid"] == p2["pid"])
    cf = store.confirmations(sid)
    check("#2 확인 기록: 동작 번호·역할·보인 해시·대상과 판", any(x["action_id"] == "c1" and x["digest"] == dg and x["role"] == "foreman"
                                                      and x["targets"][0]["version"] == 2 for x in cf))
    rev = store.revision(sid)
    ans(sid, [SRC, {"qid": "L1:P-1", "choice": "place", "value": "4BAY", "q": QL1}])        # an answer changed meanwhile
    pend = store.pending(sid, F)
    e = raises("#2 카드를 보인 뒤 답이 바뀌면 거절(stale_revision)", lambda: store.decide(sid, "c2", reject=[x["pid"] for x in pend] or ["x"], fields=F,
                                                                         displayed=store.digest(pend), expected=rev), "stale_revision")
    check("#2 거절에 바뀐 내용이 붙음(변경 차이)", e is None or isinstance(e.extra.get("changes"), list))

    # #17 expiry: one change, what it took
    s2 = store.create()
    ans(s2, [SRC])
    pa = store.propose(s2, "rule", SRC, [PROP], basis=store.revision(s2))[0][0]
    store.decide(s2, "a1", adopt=[pa["pid"]], fields=F)
    _, rev2, _ = ans(s2, [dict(SRC, value="13시부터 16시까지, 옆에서 도장팀이 터치업해요")])
    x = store.expiry(s2, rev2)
    check("#17 답이 바뀌면 만료 기록 하나: 바뀐 것(전→후)과 영향(확인했던 읽기)", x and len(x["changes"]) == 1 and "15시" in x["changes"][0]["before"]
          and "16시" in x["changes"][0]["after"] and x["lost"] and x["lost"][0]["was"] == "adopted")
    check("#17 새 답을 더하기만 하면 만료 없음", store.expiry(s2, ans(s2, [dict(SRC, value="13시부터 16시까지, 옆에서 도장팀이 터치업해요"),
                                                                {"qid": "L1:P-1", "choice": "place", "value": "3BAY", "q": QL1}])[1]) is None)

    # #5 after the close
    store.issue(s2, "CLOSE", "close")
    ans(s2, [dict(SRC, value="13시부터 17시까지"), {"qid": "L1:P-1", "choice": "place", "value": "3BAY", "q": QL1}])
    ev = store.events(s2, ("after_close",))
    check("#5 마무리 뒤 답 변경은 수정 이벤트로 남음(전→후)", len(ev) == 1 and "17시" in ev[0]["changes"][0]["after"])
    store.add_event(s2, "note", {"text": "현장에서 시간 변경 들음"}, "n1")
    check("#5 마무리 뒤 기록도 수정 이벤트로", len(store.events(s2, ("after_close",))) == 2)

    # #4 events from the client
    got = store.add_event(sid, "correction", {"qid": "T1:P-1", "before": "13~15시", "after": "13~16시"}, "e1")
    check("#4 정정 기록이 남음", got["n"] >= 1 and not got["again"])
    check("#4 같은 동작 번호는 한 번만", store.add_event(sid, "correction", {"qid": "T1:P-1", "before": "13~15시", "after": "13~16시"}, "e1")["again"])
    raises("#4 같은 번호·다른 내용은 충돌", lambda: store.add_event(sid, "correction", {"qid": "T1:P-1"}, "e1"), "action_conflict")
    raises("#4 서버만 쓰는 종류(after_close)는 받지 않음", lambda: store.add_event(sid, "after_close", {}, "e2"), "bad_event")

    # #3 restart
    s3 = store.create()
    check("#3 분석 작업 시작", store.start_job(s3, "analyze"))
    tok = store.JOB.set("analyze")
    store.charge_llm(s3)
    store.charge_llm(s3)
    store.JOB.reset(tok)
    store.open_job(s3, "turn:T1:x")
    tok = store.JOB.set("turn:T1:x")
    store.charge_llm(s3)
    store.JOB.reset(tok)
    store.finish_job(s3, "turn:T1:x", "done")
    check("#3 작업별로 모델 호출을 셈", store.budget(s3)["llm"] == 3 and store.job_row(s3, "analyze")["llm"] == 2)
    n = store.recover()
    check("#3 재시작: 돌던 작업은 미완료(interrupted), 그 호출은 돌려줌, 끝난 작업은 그대로",
          n >= 1 and store.job_row(s3, "analyze")["status"] == "interrupted" and store.budget(s3)["llm"] == 1
          and store.job_row(s3, "turn:T1:x")["status"] == "done")
    check("#3 미완료 분석은 다시 시작할 수 있음", store.start_job(s3, "analyze") and store.job_row(s3, "analyze")["status"] == "running")
    check("#4 작업 목록에 id(세션~종류)", any(j["id"] == f"{s3}~analyze" for j in store.all_jobs(s3)))


def js_digest_part():
    """the browser's digest is the server's (the confirmation would be refused otherwise)"""
    js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    a, b = js.find("const fnv = "), js.find("// 「들어갈 곳(전→후)」")
    if a < 0 or b < 0:
        check("JS 해시 함수가 app.js에 있음(패치 적용 뒤)", False)
        return
    rows = [{"pid": "Zb9", "choice": "gas", "value": "가스절단 6개"}, {"pid": "Ab1", "choice": "text", "value": "로프로 내림 · 하부"}]
    code = js[a:b] + "\nconsole.log(shownDigest(" + __import__("json").dumps(rows, ensure_ascii=False) + "));"
    try:
        out = subprocess.run(["node", "-e", code], capture_output=True, text=True, encoding="utf-8", timeout=30).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        out = None
    if out is None:
        print("SKIP #2 브라우저 해시: 여기에는 node가 없음(로컬에서 확인)")
        return
    check("#2 브라우저 해시 = 서버 해시(한글 포함)", out == store.digest(rows))


def app_part():
    from fastapi.testclient import TestClient
    from server import app as webapp, understand
    from make_demo_day import DIR, load, permit_name
    from server import extract
    c = TestClient(webapp.app)
    d = next(x for x in load("permits.json")["permits"] if x["permit_no"].endswith("6733"))
    doc = extract.build(DIR / "허가서" / permit_name(d), d["kind"])
    Fx = copy.deepcopy(doc["fields"])
    for x in Fx.values():
        if x["key"] in {f"{a}_{i}" for i in range(1, 8) for a in ("date", "from", "to")} | {"location", "location_detail", "workers"}:
            x["value"] = x["original"] = ""
    sid = c.post("/api/dialogues").json()["session_id"]
    s0 = webapp._augment(Fx, [], sid, store.revision(sid))
    t0 = next(q for q in s0["questions"] if q["item"] == "T0.1")
    say = "장소는 3BAY 12–14입니다. 실제 작업은 13시부터 15시까지이고, 종일 작업은 아닙니다. 작업자 4명과 감시인 1명이 들어갑니다."
    src = {"qid": t0["qid"], "choice": "value", "value": say, "q": t0, "at": 5}
    s1 = webapp._augment(Fx, [src], sid, store.revision(sid))
    props = {p["qid"].split(":")[0]: p for p in s1["proposals"]}
    pl = props.get("L1", {})
    dl = (pl.get("dest") or [{}])[0]
    check("#13 위치 읽기의 들어갈 곳: 반영본 칸 이름·전(빈칸)→후", dl.get("kind") == "field" and "3BAY" in dl.get("after", "") and dl.get("before", "x") == "")
    check("#13 모든 제안에 들어갈 곳 목록이 붙음", s1["proposals"] and all(isinstance(p.get("dest"), list) for p in s1["proposals"]))
    # the dialogue API
    g = c.get(f"/api/dialogues/{sid}")
    j = g.json()
    check("#4 GET 대화: 답·제안·사실·예산·작업·이벤트·확인 기록", g.status_code == 200 and {"typed", "proposals", "facts", "budget", "jobs", "events", "confirmations"} <= set(j))
    pend = j["proposals"]
    body = {"action_id": "k1", "adopt": [pend[0]["pid"]], "fields": Fx}
    check("#2 /confirm: 보인 해시·개정 없으면 422", c.post(f"/api/dialogues/{sid}/confirm", json=body).status_code == 422)
    bad = c.post(f"/api/dialogues/{sid}/confirm", json={**body, "displayed_digest": "deadbeef", "expected_revision": store.revision(sid)})
    check("#2 /confirm: 다른 내용이면 409 stale_display", bad.status_code == 409 and bad.json()["detail"]["code"] == "stale_display")
    good = c.post(f"/api/dialogues/{sid}/confirm", json={**body, "displayed_digest": store.digest([pend[0]]), "expected_revision": store.revision(sid)})
    check("#2 /confirm: 보인 그대로면 확인", good.status_code == 200 and good.json()["adopted"])
    e1 = c.post(f"/api/dialogues/{sid}/events", json={"action_id": "ev1", "kind": "note", "payload": {"text": "감시인은 협력사 인원"}})
    check("#4 POST 이벤트", e1.status_code == 200 and e1.json()["n"] >= 1)
    check("#4 이벤트 종류 검사(422)", c.post(f"/api/dialogues/{sid}/events", json={"action_id": "ev2", "kind": "expiry"}).status_code == 422)
    store.start_job(sid, "analyze")
    jr = c.get(f"/api/jobs/{sid}~analyze")
    check("#4 GET 작업", jr.status_code == 200 and jr.json()["status"] == "running" and jr.json()["id"] == f"{sid}~analyze")
    check("#4 없는 작업은 404", c.get(f"/api/jobs/{sid}~nothing").status_code == 404)
    check("#16 단계: 도는 읽기가 없으면 「끝」", c.get(f"/api/dialogues/{sid}/stage", params={"qid": "T1:x"}).json().get("stage") == "끝")
    # #3 #16: a reading is a job, with its step
    seen = {}
    real = understand.read

    async def fake(fields_, answers_, src_, **kw):
        seen["stage"] = webapp._STAGE.get((sid, src_["qid"]))
        seen["job"] = store.JOB.get()
        seen["running"] = [x for x in store.all_jobs(sid) if x["kind"].startswith("turn:") and x["status"] == "running"]
        await asyncio.sleep(0)
        return {"status": "none", "props": [], "apart": []}
    understand.read = fake
    try:
        st_ = store.state(sid, Fx)
        r = c.post("/api/understand", json={"fields": Fx, "answers": st_["typed"], "qid": src["qid"], "session_id": sid,
                                            "expected_revision": st_["revision"]})
    finally:
        understand.read = real
    check("#16 읽는 동안 단계가 기록됨(대기 중)", seen.get("stage") == "대기 중")
    check("#3 읽기는 그 작업(turn:…)으로 모델 호출을 셈", str(seen.get("job") or "").startswith("turn:") and len(seen.get("running") or []) == 1)
    check("#3 #16 끝나면 작업은 done, 단계는 지움", r.status_code == 200 and (sid, src["qid"]) not in webapp._STAGE
          and all(x["status"] != "running" for x in store.all_jobs(sid) if x["kind"].startswith("turn:")))
    # #17 through the review request
    s2 = webapp._augment(Fx, [dict(src, value=say.replace("15시", "16시"))], sid, store.revision(sid))
    check("#17 답을 바꾼 요청의 응답에 만료 묶음(expired)", s2.get("expired") and s2["expired"]["lost"] and s2["expired"]["changes"])
    # #5 the submission line
    ev = store.events(sid)
    check("#5 이벤트에 답 변경이 남음", any(e["kind"] == "answers" for e in ev))


def material_part():
    """the questions added from the research book (2026-10-31) through the review request: rule questions first, the
    extra ones (T4·L6) last, each with its 「왜 묻나요?」; a T6 「특정 단계만」 answer gives the matching the whole window
    and keeps the stage apart; windows_work is the work's own time (not stretched to the ember check's end)"""
    from fastapi.testclient import TestClient
    from server import app as webapp, extract
    from server.permit_kinds import KINDS
    from foreman_permits import FOREMAN
    c = TestClient(webapp.app)
    d = next(x for x in FOREMAN if x["permit_no"].endswith("4403"))
    doc = extract.build(ROOT / "samples/반장_테스트" / f"{KINDS[d['kind']]['label'].replace('·', '')}_{d['case']}_4403.pdf", d["kind"])
    sid = c.post("/api/dialogues").json()["session_id"]
    r = c.post("/api/augment", json={"fields": doc["fields"], "answers": [], "session_id": sid, "expected_revision": store.revision(sid)}).json()
    items = [q["item"] for q in r["questions"]]
    check(f"자료 보강: 규칙 core(H2) 먼저, extra(T4·L6)는 끝 ({items})", items[0] == "H2" and set(items[-2:]) == {"T4", "L6"})
    check("자료 보강: 새 질문에도 「왜 묻나요?」", all(q.get("why") and q["why"].get("need") for q in r["questions"]))
    t4 = next(q for q in r["questions"] if q["item"] == "T4")
    r2 = c.post("/api/augment", json={"fields": doc["fields"], "session_id": sid, "expected_revision": store.revision(sid),
                                      "answers": [{"qid": t4["qid"], "choice": "time", "value": "16:30", "q": t4}]}).json()
    e = r2["effective"][0]
    check("자료 보강: T4 16:30 → windows는 매칭용으로 16:30까지, windows_work는 작업 시간 그대로",
          e["windows"]["2026-10-27"] == ["13:00~16:30"] and e["windows_work"]["2026-10-27"] == ["13:00~15:30"] and e["residual"] == "16:30")
    check("자료 보강: T4는 다시 묻지 않음", not any(q["qid"] == t4["qid"] for q in r2["questions"]))
    # the store's ask budget through the review request: the asks issued in the order given (rule questions that the
    # rules need first), every answer 「모름」, never more than 12
    from server import need_catalog as N
    d3 = next(x for x in FOREMAN if x["permit_no"].endswith("4676"))
    doc3 = extract.build(ROOT / "samples/반장_테스트" / f"{KINDS[d3['kind']]['label'].replace('·', '')}_{d3['case']}_4676.pdf", d3["kind"])
    sid3, answers, issued = c.post("/api/dialogues").json()["session_id"], [], []
    for _ in range(30):
        r3 = c.post("/api/augment", json={"fields": doc3["fields"], "answers": answers, "session_id": sid3,
                                          "expected_revision": store.revision(sid3)}).json()
        q = next((q for q in r3["questions"] if q.get("tier") != "extra" and not q.get("unasked")), None)
        if not q:
            break
        try:
            store.issue(sid3, store.skey(q["qid"], q), "question")
        except store.StoreError:
            break
        issued.append(q["item"])
        answers.append({"qid": q["qid"], "choice": "unknown", "value": "", "q": q})
    req = [N.row(i)["required"] for i in issued]
    check(f"자료 보강: 4676 질문 발급 {len(issued)}회 ≤ 12, 규칙 필수 질문이 먼저 ({issued})",
          0 < len(issued) <= 12 and req == sorted(req, reverse=True) and "CF3" in issued)


def main():
    store_part()
    js_digest_part()
    app_part()
    material_part()
    print(f"\n{sum(OK)}/{len(OK)}")
    sys.exit(0 if all(OK) else 1)


if __name__ == "__main__":
    main()
