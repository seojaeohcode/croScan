"""croScan demo server.
  POST /api/parse   PDF upload + the permit kind picked on screen -> form model (OpenDataLoader) + rule findings
  POST /api/review  current field values -> rule findings
  POST /api/augment field values + answers so far -> open questions, pairs, 추가검토서 (page 2) HTML
  POST /api/submit  original PDF + field values + answers -> original pages + 추가검토서 as one PDF
  POST /api/checklist  field values + answers (the permit alone) -> the 위험 체크리스트 draft, per permit
  POST /api/checklist/pdf  field values + the checklist as confirmed -> its PDF (preview)
  (the 제출 is a demo: nothing is stored; the page asks for each of the three PDFs above when its button is pressed)
  POST /api/chat    field values + chat history -> streamed reply of the local model (Raon-1 mini preview)
  GET  /api/llm     is the local model up
  POST /api/workplans  작업계획서 PDFs (many files, bundles too) -> NDJSON progress, then one record per plan
  GET  /api/workplans/{token}/{file}/{page}.png  a plan page image (?bg=1: values erased, for the editor)
  POST /api/workplans/{token}/edits  save the values changed on screen;  GET …/plan/{i}.pdf, …/all.pdf  the 수정본
  POST /api/qa      QA report from the page: any attached files + text + screen state -> saved in data/qa.sqlite3
  GET  /api/qa      QA reports, ?handled=false for the ones still to do (header X-QA-Token = env QA_TOKEN);
                    /api/qa/{id}/file/{n}, POST /api/qa/{id}/handled
  GET  /api/qa/board QA 현황 for the team: newest first, handled or not, the QA session's runs (no token; text start only)
  POST /api/qa/run   「QA 시작하기」: one request for the team's QA session; POST /api/qa/run/{id} its state (token)
  GET  /api/safety/overview  안전관리자: every document sent in for the demo day (demo DB, read-only, no answer key)
  POST /api/safety/detect  쌍작업 위험탐지: every 일상×비일상 and 비일상×비일상 pair judged by rules (pair_rules.json)
  POST /api/safety/sheet.pdf  현장 게시용(허가서 원본 + 병행작업 조정 별지) or 일상작업반 전달문, from the edited sheet
  GET  /api/safety/doc/{id}  one permit (form, answers, checklist) or plan (its items)
  GET  /api/safety/pdf/{id}/{part}.pdf  original | full (permit + 추가검토서) | checklist
  GET  /api/health  liveness check (Docker HEALTHCHECK)
Run:  uvicorn server.app:app --port 8765   (from croScan_app/)
"""
import asyncio
import json
import hashlib
import hmac
import inspect
import os
import re
import tempfile
from pathlib import Path

import httpx
import pymupdf
from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import addendum, analyze, augment, checklist, coordnote, critique, evidencemap, explain, extract, link, llm, need_catalog, pairs, posting, qa, reflect, retrieval, review, safety, store, submissions, understand, workplan
from . import permit_kinds as PK

ROOT = Path(__file__).resolve().parent.parent
# local LLM: KRAFTON Raon-1 mini preview on llama.cpp's OpenAI-compatible server (docker compose: http://llm:8000/...)
LLM_URL = os.environ.get("LLM_URL", "http://127.0.0.1:8000/v1/chat/completions")
LLM_MODEL = os.environ.get("LLM_MODEL", "Raon-1-mini-preview")
# the model card's recommended sampling; thinking stays on (KRAFTON advises against turning it off) and is not shown
LLM_SAMPLING = {"temperature": 1.0, "top_p": 0.95, "top_k": 20, "min_p": 0.0, "repeat_penalty": 1.0,
                "frequency_penalty": 0.0, "presence_penalty": 1.5,
                "chat_template_kwargs": {"enable_thinking": True, "truncate_history_thinking": False}}
LLM_MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", "4096"))     # thinking + answer

app = FastAPI(title="croScan")

# 접근 통제 (설계 §12.3 운영 인증의 자리): croScan keeps no accounts. In front of it the company's sign-in gateway (SSO)
# says who is asking, in a header only the gateway sets: CROSCAN_AUTH=proxy makes the manager's side (the day's
# documents and pairs, the submitted documents, the evidence map) open only to the role 안전관리자, and a foreman's
# review only to a signed-in user. The app must then be reachable only through that gateway (bind it to 127.0.0.1).
# Without it (demo, the default) everything is open and the screens say 「시연 모드 · 인증 없음」.
AUTH = os.environ.get("CROSCAN_AUTH", "demo")
if AUTH not in ("demo", "proxy"):                       # a typo must not run open while meant to be closed
    raise RuntimeError(f"CROSCAN_AUTH는 demo 또는 proxy여야 합니다: {AUTH!r}")
USER_HEADER = os.environ.get("CROSCAN_USER_HEADER", "x-croscan-user")
ROLE_HEADER = os.environ.get("CROSCAN_ROLE_HEADER", "x-croscan-role")
MANAGER_ONLY = ("/api/safety/", "/api/knowledge/")


def _needs(path, method):
    """the role a request needs under the gateway: 'manager', 'user' or None (open). A submitted document is the
    manager's or its own foreman's (checked where it is served)."""
    if path.startswith(MANAGER_ONLY):
        return "manager"
    if path.startswith("/api/") and path != "/api/health":
        return "user"
    return None


@app.middleware("http")
async def _gate(request: Request, call_next):
    if AUTH == "proxy":
        need = _needs(request.url.path, request.method)
        # the team PC's QA tools (qa_pull, qa_watch) come with the QA token, not through the company login
        want = os.environ.get("QA_TOKEN", "")
        if request.url.path.startswith("/api/qa") and want and hmac.compare_digest(request.headers.get("X-QA-Token", "").encode("utf-8", "replace"), want.encode()):
            need = None
        role = (request.headers.get(ROLE_HEADER) or "").strip().lower()
        if need == "manager" and role != "manager" or need == "user" and role not in ("manager", "foreman"):
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": "로그인이 필요합니다" if not role else "안전관리자만 볼 수 있습니다"}, status_code=401 if not role else 403)
        user = (request.headers.get(USER_HEADER) or "").strip()
        if need == "user" and not user:
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": "로그인 정보(사용자)가 없습니다"}, status_code=401)
        store.OWNER.set(user or None)                   # a session is its own foreman's (a manager sees all)
        store.MANAGER.set(role == "manager")
    return await call_next(request)


def _steps(pdf_path, kind):
    """NDJSON progress: one line per real stage as it finishes, then the document."""
    import time
    t0 = time.time()

    def ev(**kw):
        return json.dumps({**kw, "t": round(time.time() - t0, 1)}, ensure_ascii=False) + "\n"
    try:
        import pymupdf
        d = pymupdf.open(pdf_path)
        text = sum(len(p.get_text().strip()) for p in d)
        yield ev(step="open", msg=f"PDF {len(d)}쪽 확인 (글자 층 {'있음' if text else '없음'})")
        if not text:
            yield ev(step="error", msg="글자 층이 없는 PDF입니다(사진·스캔본). 전산 허가서 PDF를 올려 주세요.")
            return
        odl = extract.run_odl(pdf_path)
        n_cells = sum(1 for el, _ in extract._walk(odl.get("kids", [])) if el.get("type") == "table cell")
        yield ev(step="odl", msg=f"한컴 OpenDataLoader: 표 칸 {n_cells}개 읽음")
        doc = extract.build(pdf_path, kind, odl)
        fs = doc["fields"]
        filled = sum(1 for f in fs.values() if f["type"] not in ("check", "image") and str(f["value"]).strip())
        values = sum(1 for f in fs.values() if f["type"] not in ("check", "image"))
        checks = sum(1 for f in fs.values() if f["type"] == "check")
        pages = ", ".join(f"{p['no']}쪽 {p['kind_label']}({p['variant_label'].split()[-1]})" for p in doc["pages"])
        permits = doc["permits"]
        kinds = "서로 다른 허가서 %d건" % len(permits) if len(permits) > 1 else \
            ("같은 허가서의 사본 %d장" % len(permits[0]["pages"]) if permits and len(permits[0]["pages"]) > 1 else "허가서 1건")
        yield ev(step="map", msg=f"{pages} → {kinds} · 값 {filled}/{values}칸, 체크 항목 {checks}개")
        doc["findings"] = review.check(fs)
        yield ev(step="review", msg=f"규칙 검사: 확인할 곳 {len(doc['findings'])}건")
        yield ev(step="done", doc=doc)
    except Exception as e:      # shown on the loading screen instead of a broken page
        yield ev(step="error", msg=f"읽기 실패: {e}")


def _stream_file(data, name, kind):
    def gen():
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / Path(name or "upload.pdf").name
            p.write_bytes(data)
            yield from _steps(p, kind)
    return StreamingResponse(gen(), media_type="application/x-ndjson")


@app.post("/api/parse")
async def parse(file: UploadFile = File(...), kind: str = Form(...)):
    if kind not in PK.KINDS:
        raise HTTPException(400, f"허가서 종류를 먼저 고르세요 ({', '.join(PK.KINDS)})")
    return _stream_file(await file.read(), file.filename, kind)


@app.post("/api/workplans")
def workplans(files: list[UploadFile] = File(...)):
    # the uploads are streamed to disk by read_many (no copy held in memory); a plain def runs in the thread pool
    try:
        staged = workplan.stage([(Path(f.filename or "plan.pdf").name, f.file) for f in files])
    except OSError as e:          # the disk floor (qa.FLOOR) or a full disk
        raise HTTPException(507, f"서버에 저장하지 못했습니다: {e.strerror or e}")

    def gen():
        try:
            for ev in workplan.read_staged(*staged):
                yield json.dumps(ev, ensure_ascii=False) + "\n"
        except Exception as e:      # shown on the loading screen
            yield json.dumps({"step": "wp_error", "msg": f"작업계획서 읽기 실패: {e}"}, ensure_ascii=False) + "\n"
    return StreamingResponse(gen(), media_type="application/x-ndjson")


from . import docsum, mapcell, permitsignal  # noqa: E402  (G2: 문서·계획서 AI)


class PlanPrep(BaseModel):
    idx: list = []           # the plans to read ahead (all of the upload when empty)
    session_id: str = ""     # the review it is for, when there is one (its model calls are counted there)


# design §1.3(1)·§13: while the foreman checks his plans, each is read ahead (reading links to offer, passages it
# calls on); kept per plan digest, so the later steps do not wait for it
@app.post("/api/workplans/{token}/prepare")
async def workplan_prepare(token: str, body: PlanPrep):
    plans = workplan.load_plans(token)
    if plans is None:
        raise HTTPException(404, "작업계획서가 만료됐습니다. 다시 올려 주세요.")
    idx = [i for i in body.idx if isinstance(i, int)] or list(range(len(plans)))
    try:
        return {"plans": await mapcell.prepare(plans, idx, workplan.load_maps(token), sid=body.session_id or None)}
    except asyncio.CancelledError:
        return {"plans": {}, "why": "preempted"}


class PlanMap(BaseModel):
    plan: int
    label: str
    key: str
    accept: bool             # 「연결」 or 「아님」


# 읽기 연결 정정 (design §6.4): the foreman says a label is (or is not) that item; kept apart from his value edits
@app.post("/api/workplans/{token}/maps")
def workplan_map(token: str, body: PlanMap):
    try:
        maps = workplan.save_map(token, body.plan, body.label, body.key, body.accept)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if maps is None:
        raise HTTPException(404, "작업계획서가 만료됐습니다. 다시 올려 주세요.")
    plans = workplan.load_plans(token)
    p = plans[body.plan]
    return {"maps": maps, "plan": {k: p.get(k) for k in ("title", "company", "start", "end", "location", "target")}}


class PlanEdits(BaseModel):
    edits: dict              # {plan index: {field key: value}}


@app.post("/api/workplans/{token}/edits")
def workplan_save(token: str, body: PlanEdits):
    try:
        saved = workplan.save_edits(token, body.edits)
    except ValueError as e:
        raise HTTPException(400, f"수정 내용 형식이 맞지 않습니다: {e}")
    if not saved:
        raise HTTPException(404, "작업계획서가 만료됐습니다. 다시 올려 주세요.")
    return {"saved": saved}


@app.get("/api/workplans/{token}/edits")
def workplan_edits(token: str):
    return workplan.load_edits(token)


def _pdf_response(got):
    if not got:
        raise HTTPException(404, "작업계획서가 만료됐습니다. 다시 올려 주세요.")
    from urllib.parse import quote
    pdf, name = got
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})


@app.get("/api/workplans/{token}/plan/{i}.pdf")
def workplan_pdf_one(token: str, i: int):
    return _pdf_response(workplan.edited_pdf(token, i))


@app.get("/api/workplans/{token}/all.pdf")
def workplan_pdf_all(token: str):
    return _pdf_response(workplan.edited_pdf(token))


@app.get("/api/workplans/{token}/{fi}/{page}.png")
def workplan_page(token: str, fi: int, page: int, bg: int = 0):
    png = workplan.page_png(token, fi, page, bool(bg))
    if png is None:
        raise HTTPException(404, "작업계획서 원본이 만료됐습니다. 다시 올려 주세요.")
    return Response(png, media_type="image/png", headers={"Cache-Control": "private, max-age=43200"})


@app.get("/api/kinds")
def kinds():
    return [{"id": k, "label": v["label"], "title": v["title"]} for k, v in PK.KINDS.items()]


@app.get("/api/health")
def health():
    return {"ok": True, "auth": AUTH}


class Fields(BaseModel):
    fields: dict


@app.post("/api/review")
def do_review(body: Fields):
    return review.check(body.fields)


class Augment(BaseModel):
    fields: dict
    answers: list = []       # [{"qid", "choice", "value", "q": the question as asked}]
    session_id: str = ""     # the review session (design §2): derived answers come from it, never from the client
    expected_revision: int | None = None   # the session revision the client last saw: an older one is refused (409)


def _answers(answers):
    """Answers as the rules expect them: a dict with a text qid, choice and value; one per qid (the last wins,
    in the place it was first given), so a double send never makes two rows on page 2."""
    def bad(why):
        raise HTTPException(400, f"답변(answers) 형식이 맞지 않습니다: {why}")
    if not isinstance(answers, list):
        bad("목록이 아님")
    out = {}
    for a in answers:
        if not (isinstance(a, dict) and isinstance(a.get("qid"), str) and a["qid"].strip()):
            bad("qid 없음")
        if not all(isinstance(a.get(k), (str, type(None))) for k in ("choice", "value")):
            bad("choice·value는 글자")
        q = a.get("q", {})
        if not isinstance(q, dict) or not isinstance(q.get("choices", []), list) or not isinstance(q.get("keys", []), list):
            bad("q의 구조")
        if not all(isinstance(c, dict) and isinstance(c.get("id"), str) for c in q.get("choices", [])) \
                or not all(isinstance(k, str) for k in q.get("keys", [])):
            bad("q의 보기·칸")
        # 'oh-21-01' typed in lower case is the crane OH-21-01 (QA #11): IDs are read in capitals everywhere after this
        out[a["qid"]] = {**a, "q": q, "choice": a.get("choice") or "", "value": augment.norm_ids(a.get("value") or "")}
    return list(out.values())


def _fields(fields):
    """The field values as the rules expect them (key -> dict); anything else is refused with 400, not a 500."""
    if not isinstance(fields, dict) or not all(isinstance(f, dict) for f in fields.values()):
        raise HTTPException(400, "양식 값(fields) 형식이 맞지 않습니다")
    return fields


def _store_error(e):
    return HTTPException(e.status, {"code": e.code, "message": e.detail, **e.extra})


def _calc_answers(answers, sid, fields, expected=None, write=True):
    """What the rules calculate with -> (answers, revision, dropped): the foreman's own answers (question, choice and
    value only: what the client says it read, or that an answer was read from another, is not taken) and, with a
    session, the readings he confirmed there. The review's own steps write the typed answers to the session (write);
    the checklist, the preview and the submission only read it, as of the revision the client saw."""
    if sid:
        try:
            if write:
                return _unlinked(sid, *store.answers_for(sid, answers, fields, expected))
            return _unlinked(sid, *store.current(sid, fields, expected))
        except store.StoreError as e:
            raise _store_error(e)
    return store.typed_of(answers), None, []


def _long(a):
    return not a.get("pid") and len((a.get("value") or "").strip()) >= 8 and a.get("choice") != "unknown"


def _normalize(fields, answers):
    """-> (the answers that hold, each long one with its own part read; errors; [(answer, what it says for other
    open questions)]). The same for every path (augment, checklist, preview, submission): a long answer's own part is
    its value (read), worked out here every time; nothing the client says it read is taken."""
    # a long answer to the 작업인원 question: its number is its value (checked as a count), the rest is read below
    for a in answers:
        if _long(a) and a["qid"].split(":")[0] in ("B1.workers", "B2.workers") and a.get("choice") == "value":
            n = augment.own_count(a.get("value", ""))
            if n and n != (a.get("value") or "").strip():
                a["read"] = n
    errors = {a["qid"]: m for a in answers if (m := augment.check_value(fields, a))}
    ok = [a for a in answers if a["qid"] not in errors]
    # QA #39 → design §2·§4.2 (2026-10-31): what a long answer (or a free one) also says for other open questions is
    # read with the clause it came from, and kept as a proposal until the foreman confirms it
    found = []
    live = augment.live_answers(ok)                  # a withdrawn answer (C6 「서류가 맞음」) proposes nothing (#11)
    gone = augment.withdrawn(ok)
    for a in [a for a in ok if _long(a) and a["qid"] not in gone]:
        got, own = augment.interpret(fields, live, a)
        got = [d for d in got if d["qid"] not in {x["qid"] for x in ok}]
        if got:
            found.append((a, got))
        if own:
            a["read"] = own
    return ok, errors, found


def _with_ai(sid, fields, answers, qs):
    """the AI's stored needs as questions (design §1.3·§3.1), unless answered; one whose words are no longer in the
    permit (the form was edited) is not asked"""
    perms = augment.effective(fields, answers)
    if len(perms) != 1:
        return qs
    P, done = perms[0], {a["qid"] for a in answers}
    read = (store.job(sid, "analyze") or {}).get("plan") or {}
    refused = {(v.get("title") or "") for v in store.jobs(sid, "link:").values() if v["status"] == "refused"}
    not_this = bool(read.get("title")) and read.get("title") in refused        # the plan read is one he said is not this work
    for n in store.needs(sid):
        q = analyze.question(n, P)
        gone = not_this and any(str(x or "").startswith("plan:") for x in (n.get("key"), n.get("key2")))
        for key, quote in ((n["key"], n["quote"]), (n.get("key2"), n.get("quote2"))):
            if key and not key.startswith("plan:"):
                f = fields.get(key)
                gone = gone or f is None or analyze._norm(quote) not in analyze._norm(str(f.get("value") or ""))
        if q["qid"] in done or gone:
            continue
        q["why"] = {"observe": q["signal"], "need": n["need"], "basis": []}
        qs.append(q)
    return qs


def _budget(sid, s):
    """the budget, what was not asked because of it, and what is left for the safety team (one list for the chat's
    closing line, the 별지 and the submission; design §3.5·§3.7)"""
    b = store.budget(sid)
    asked, bases = set(b.pop("asked")), store.clarified(sid)
    full = b["used"] >= b["max"]
    for q in s["questions"]:
        k = store.skey(q["qid"], q)
        if k in asked:
            continue
        if full:
            q["unasked"] = "질문 한도로 묻지 않음"
        elif q["item"].startswith(need_catalog.CHECKING) and (b["clarify"] >= b["clarify_max"] or store.clarify_base(k) in bases):
            q["unasked"] = "다시 묻기 한도로 묻지 않음"
    job = store.job(sid, "analyze")
    s["analysis"] = job and {k: job.get(k) for k in ("status", "why", "found", "plan")}
    if job and job["status"] in ("running", "fail", "late", "stale"):
        s["analysis_note"] = {"running": "AI 분석이 끝나기 전에 대화를 마침", "fail": "AI 분석을 마치지 못함(규칙 질문으로만 확인)",
                              "late": "대화를 마친 뒤 끝난 AI 분석은 묻지 않음", "stale": "분석 중 허가서가 바뀌어 쓰지 않음"}[job["status"]]
    left = {}
    for q in s["questions"]:
        if q.get("tier") != "extra":
            left[store.skey(q["qid"], q)] = q.get("unasked") or "답하지 않음"
    for r in s.get("pending", []):
        left.setdefault(r["qid"], "모름·미확인")
    for p in s.get("proposals", []):
        left.setdefault(f"P:{p.get('pid')}", "확인하지 않은 읽기")
    if s.get("analysis_note"):
        left["AI"] = s["analysis_note"]
    s["budget"], s["unresolved"] = b, [{"key": k, "why": w} for k, w in left.items()]


_REFS = {}


def _dest(fields, answers, props, before=None):
    """each proposal's destination once confirmed (design §4.3): the form field with its value before and after, the
    별지, or what is left to be checked"""
    for p in props:
        try:
            p["dest"] = reflect.destination(fields, answers, p, before)
        except (KeyError, TypeError, ValueError, AttributeError, IndexError) as e:
            print(f"dest: {type(e).__name__}: {e}", flush=True)
            p["dest"] = []


def _augment(fields, answers, sid="", expected=None, write=True):
    fields = _fields(fields)
    answers, rev, dropped = _calc_answers(_answers(answers), sid, fields, expected, write)
    expired = store.expiry(sid, rev) if sid and write and rev is not None else None
    if sid and write and dropped and not expired:           # values a link brought from a plan changed since
        lk = sorted({x["qid"] for x in _stale_imports(sid)} & set(dropped))
        expired = {"rev": rev, "changes": [], "form": False, "plan": True,
                   "lost": [{"qid": q, "was": "link", "why": "연결한 뒤 작업계획서가 고쳐짐"} for q in lk]} if lk else None
    try:
        ok, errors, found = _normalize(fields, answers)
        derived, read = [], {a["qid"]: a["read"] for a in ok if a.get("read") and _long(a)}
        for a, got in found:
            if sid and write:
                try:
                    got, rev = store.propose(sid, "rule", a, got, basis=rev)
                except store.StoreError as e:
                    raise _store_error(e)
            derived += got
        s = augment.summary(fields, ok)
        if sid:
            s["questions"] = _with_ai(sid, fields, ok, s["questions"])
        s["questions"] = need_catalog.order(s["questions"])
        for q in s.get("questions", []):             # 「왜 묻나요?」: the observation, the need and its basis (§3.3)
            q["why"] = q.get("why") or need_catalog.why(q)
            if q["why"] is not None and "refs" not in q["why"]:          # related passages: search candidates, shown as such
                k = (q["why"]["need"], q.get("text", ""))
                if k not in _REFS:
                    _REFS[k] = retrieval.related(f"{k[0]} {k[1]}")
                    if len(_REFS) > 2000:
                        _REFS.clear()
                q["why"]["refs"] = _REFS[k]
        s["errors"] = errors
        s["derived"], s["read"] = [], read                 # nothing is taken without a confirmation any more
        gone = augment.withdrawn(ok)                   # a reading of a withdrawn answer is not offered (#11)
        s["proposals"] = [p for p in (store.pending(sid, fields) if sid else derived) if p.get("by") not in gone]
        for p in s["proposals"]:                          # the card names the slot in words (not 「HT1」)
            if not p.get("slot") and p.get("q"):
                p["slot"] = understand._slot(p["q"])
        if sid:
            _budget(sid, s)                                # again: the proposals are known now
        s["adopted"] = [a for a in ok if a.get("pid")]
        # dropped: checking answers whose base changed, and answers given on form values the foreman changed since
        s["revision"], s["dropped"] = rev, sorted(set(dropped or []) | set(s.get("stale_answers") or []))
        s["protected"] = sorted(reflect.NEVER)               # fields croScan never writes: shown, not edited (QA #41)
        s["reflect"] = reflect.plan(fields, ok)              # QA #37: what goes into which field of the 반영본
        _dest(fields, ok, s["proposals"], s["reflect"])        # the card's 「들어갈 곳(전→후)」 (design §4.3·§19.2)
        s["expired"] = expired                               # design §19.2 개정 만료: one notice for this change
        s["sheets"] = addendum.build(s, fields)
    except (KeyError, TypeError, AttributeError, ValueError) as e:     # a field without its parts (page, type …)
        print(f"augment: bad input {type(e).__name__}: {e}", flush=True)
        raise HTTPException(400, "양식 값(fields) 형식이 맞지 않습니다")
    return s


@app.post("/api/augment")
def do_augment(body: Augment):
    return _augment(body.fields, body.answers, body.session_id, body.expected_revision)


# the review session (design §2) ----------------------------------------------------------------------------------
@app.post("/api/dialogues")
def new_dialogue():
    return {"session_id": store.create(), "revision": 0}


class DialogueGet(BaseModel):
    fields: dict = {}        # to give the answer ids with the 승인번호 of now


@app.post("/api/dialogues/{sid}/state")
def get_dialogue(sid: str, body: DialogueGet):
    try:
        return {"session_id": sid, **store.state(sid, body.fields)}
    except store.StoreError as e:
        raise _store_error(e)


class Decide(BaseModel):
    action_id: str
    adopt: list = []         # proposal ids the foreman confirmed (as shown on the card)
    reject: list = []        # proposal ids he took out
    withdraw: list = []      # confirmed ones he takes back (「이것 빼기」 after the confirmation)
    fields: dict = {}        # the form as shown: a reading made against other form values is not adopted
    displayed_digest: str | None = None   # what the card showed (store.digest): a card changed since is refused
    expected_revision: int | None = None  # the revision the card was shown at


@app.post("/api/dialogues/{sid}/decide")
def decide_dialogue(sid: str, body: Decide):
    if not all(isinstance(x, str) for x in body.adopt + body.reject + body.withdraw) or not body.action_id:
        raise HTTPException(422, {"code": "bad_ids", "message": "제안 번호 형식이 맞지 않습니다"})
    try:
        out = store.decide(sid, body.action_id, body.adopt, body.reject, body.withdraw, body.fields or None,
                           displayed=body.displayed_digest, expected=body.expected_revision)
    except store.StoreError as e:
        raise _store_error(e)
    try:                                                       # a case candidate is a side record: it never fails the decision
        from . import cases
        cases.record(sid, body.adopt, body.reject)
    except Exception as e:                                     # noqa: BLE001
        print(f"cases: {type(e).__name__}: {e}", flush=True)
    return out


@app.post("/api/dialogues/{sid}/confirm")
def confirm_dialogue(sid: str, body: Decide):
    """design §2.3: expected_revision + proposal_ids + displayed_digest + action_id; a card shown before a change is
    refused (409) with what changed"""
    if body.displayed_digest is None or body.expected_revision is None:
        raise HTTPException(422, {"code": "confirm_contract", "message": "보인 내용의 해시와 개정 번호가 필요합니다"})
    return decide_dialogue(sid, body)


_STAGE = {}                  # (session, question) -> the step its reading is at (design §19.4)


@app.get("/api/dialogues/{sid}")
def dialogue_view(sid: str):
    """design §12.1: the review as the server keeps it — answers, readings, facts, budgets, jobs, events, confirmations"""
    try:
        b = store.budget(sid)
        return {"session_id": sid, **store.state(sid), "facts": store.facts(sid), "budget": {k: v for k, v in b.items() if k != "asked"},
                "jobs": store.all_jobs(sid), "events": store.events(sid), "confirmations": store.confirmations(sid),
                "stages": {q: s_ for (i, q), s_ in _STAGE.items() if i == sid}}
    except store.StoreError as e:
        raise _store_error(e)


@app.get("/api/dialogues/{sid}/stage")
def dialogue_stage(sid: str, qid: str):
    """design §19.4: the step a reading of this answer is at — 대기 중 / 답 해석 중 / 결과 검사 중 — or 끝"""
    try:
        store.revision(sid)                                  # the review exists (and is the asker's)
    except store.StoreError as e:
        raise _store_error(e)
    return {"qid": qid, "stage": _STAGE.get((sid, qid), "끝")}


class EventIn(BaseModel):
    action_id: str
    kind: str                # correction | withdraw | note (what changed is kept by the answers themselves)
    payload: dict = {}


@app.post("/api/dialogues/{sid}/events")
def dialogue_event(sid: str, body: EventIn):
    """design §12.1·§3.6: a correction, a withdrawal or a note the foreman records (after the review closed, it is kept
    as a 수정 이벤트 too); the same action twice is recorded once"""
    if not body.action_id:
        raise HTTPException(422, {"code": "bad_event", "message": "동작 번호가 없습니다"})
    payload = {str(k)[:40]: (v if isinstance(v, (int, float, bool)) or v is None else str(v)[:300]) for k, v in list(body.payload.items())[:12]}
    try:
        return store.add_event(sid, body.kind, payload, body.action_id)
    except store.StoreError as e:
        raise _store_error(e)


@app.get("/api/jobs/{job_id:path}")
def job_view(job_id: str):
    """design §12.1: a job of a review (its id is 〈session〉~〈kind〉): status, times, model calls it was charged"""
    sid, _, kind = job_id.partition("~")
    try:
        got = store.job_row(sid, kind) if sid and kind else None
    except store.StoreError as e:
        raise _store_error(e)
    if not got:
        raise HTTPException(404, "그런 작업이 없습니다")
    return got


class Ask(BaseModel):
    what: str                # question | retry (asked again: the answer could not be read) | card | close
    qid: str = ""
    q: dict = {}
    fields: dict = {}


@app.post("/api/dialogues/{sid}/ask")
def ask_dialogue(sid: str, body: Ask):
    """the client shows this to the foreman now: counted once (design §3.5); refused past the budget (409)"""
    try:
        if body.what == "close":
            try:
                return store.issue(sid, "CLOSE", "close")
            except store.StoreError as e:
                if e.code == "budget":                     # the end without the closing request: recorded all the same
                    store.close_review(sid)
                raise
        if not body.qid:
            raise HTTPException(422, {"code": "bad_ask", "message": "무엇을 묻는지 없음"})
        k = store.skey(body.qid, body.q)
        res = _reserve(sid, body, k)
        if body.what == "retry":
            return store.issue(sid, f"RETRY:{k}", "clarify", k, reserve=res)
        if body.what == "card":                            # one card per answer as said: its key and words as stored
            st_ = store.state(sid, body.fields or None)
            a = next((x for x in st_["typed"] if x["qid"] == body.qid), None)
            if not a:
                raise HTTPException(409, {"code": "card_source", "message": "원래 답이 없습니다"})
            return store.issue(sid, f"CARD:{store.skey(a['qid'], a.get('q'))}:{store.said_hash(a)}", "card", reserve=res)
        if body.what == "link":                            # a link suggestion asks the foreman too (design §3.5)
            return store.issue(sid, f"LINK:{body.qid}", "card", reserve=res)
        if body.what == "question":
            item = body.qid.split(":")[0]
            if item.startswith(need_catalog.CHECKING):
                return store.issue(sid, k, "clarify", store.clarify_base(k), reserve=res)
            if item.startswith("AI"):                      # an AI question: after the rule questions' asks
                return store.issue(sid, k, "question", reserve=res)
            return store.issue(sid, k, "question")
        raise HTTPException(422, {"code": "bad_ask", "message": "알 수 없는 요청"})
    except store.StoreError as e:
        raise _store_error(e)


def _reserve(sid, body, k):
    """the open rule questions not asked yet (but the one being asked): the asks they still need. Without the form
    nothing can be counted, so nothing that is not a rule question is let through then."""
    if not body.fields:
        return store.ASKS
    try:
        fields = _fields(body.fields)
        answers, _, _ = store.current(sid, fields, store.revision(sid))
        open_, _, _, _ = augment.questions(fields, answers)
    except (store.StoreError, KeyError, TypeError, ValueError, AttributeError):
        return store.ASKS
    asked = set(store.budget(sid)["asked"])
    return sum(1 for q in open_ if q.get("tier") != "extra" and not q["item"].startswith(need_catalog.CHECKING)
               and store.skey(q["qid"], q) not in asked and store.skey(q["qid"], q) != k)


class DeltaIn(BaseModel):
    fields: dict
    session_id: str
    plans: dict = {}         # as for /api/analyze: the plan's rows stay in, so a changed field is read against it


_DELTA = set()


# 변경 구역 재분석 (DISCOVER_DELTA, design §1.4): the permit was edited after the analysis — only the changed fields are
# read again (prepared, gives way to a foreman's answer), within the same new-need limits; nothing else is redone
@app.post("/api/analyze/delta")
async def analyze_delta(body: DeltaIn):
    fields, sid = _fields(body.fields), body.session_id
    try:
        answers, _, _ = _unlinked(sid, *store.current(sid, fields, store.revision(sid)))
    except store.StoreError as e:
        raise _store_error(e)
    prev = store.job(sid, "analyze") or {}
    if prev.get("status") != "done" or not prev.get("rowhash"):
        return {"status": "none", "found": 0, "why": "첫 분석 전"}
    if sid in _DELTA:
        return {"status": "busy", "found": 0, "why": "다시 읽는 중"}
    _DELTA.add(sid)
    try:
        ctx0 = store.page_contexts(fields)
        plan, edits = _plan_for(sid, fields, body.plans)
        res = await analyze.delta(fields, answers, prev["rowhash"], plan, edits, sid=sid)
    except asyncio.CancelledError:
        return {"status": "fail", "found": 0, "why": "preempted"}
    finally:
        _DELTA.discard(sid)
    status, found = res["status"], []
    if status in ("ok", "none"):
        if store.form(sid) not in (None, ctx0):
            return {"status": "stale", "found": 0, "why": "읽는 동안 허가서가 또 바뀜"}
        found = store.add_needs(sid, res["needs"])
        if found is None:
            return {"status": "late", "found": 0, "why": "검토가 끝남"}
        keep = {k: v for k, v in prev.items() if k != "status"}
        store.put_job(sid, "analyze", "done", {**keep, "rowhash": res["rowhash"], "delta": (prev.get("delta") or 0) + 1})
    return {"status": status, "found": len(found), "changed": res.get("changed", []), "why": res.get("why")}


class AnalyzeIn(BaseModel):
    fields: dict
    answers: list = []
    session_id: str
    expected_revision: int | None = None
    plans: dict = {}         # {token, idx: [confirmed plan indices]}: the 작업계획서 confirmed in step 1


def _plan_for(sid, fields, body_plans):
    """the one 작업계획서 the analysis reads beside the permit (the link he confirmed, else the related one) -> (plan, edits)"""
    plan, edits = None, {}
    tok, idx = str(body_plans.get("token") or ""), [i for i in body_plans.get("idx") or [] if isinstance(i, int)]
    if tok and idx and workplan._touch(tok):
        try:
            plans = workplan.load_plans(tok)                # with the reading links the foreman confirmed (§6.4)
            if plans is None:
                raise ValueError("gone")
            saved = workplan.load_edits(tok)                # the values as the foreman corrected them, before choosing
            links = store.jobs(sid, "link:").values()
            no = {v["plan"] for v in links if v["status"] == "refused"}
            yes = [v["plan"] for v in links if v["status"] == "confirmed" and v["plan"] in idx and v.get("token") == tok
                   and 0 <= v["plan"] < len(plans) and v.get("digest") in (None, workplan.plan_digest(plans[v["plan"]], saved.get(str(v["plan"]))))]
            i = yes[0] if yes else analyze.related_plan(plans, [x for x in idx if x not in no], fields, saved)
            if i is not None:
                plan, edits = plans[i], saved.get(str(i), {})
        except (OSError, ValueError):
            plan = None                                  # the plans are gone (7 days): the permit alone, said so
    return plan, edits


# 업로드 분석 (design §1.3): once per review, in the background while the foreman reads the first question; a
# foreground model call (his answer being read) takes the slot from it. Its result is checked against the form as it
# is when it ends and is not used after the closing request was shown.
@app.post("/api/analyze")
async def do_analyze(body: AnalyzeIn):
    fields, sid = _fields(body.fields), body.session_id
    try:
        answers, rev, _ = _unlinked(sid, *store.current(sid, fields, body.expected_revision))
        if not store.start_job(sid, "analyze"):
            return {"status": "done_before", **(store.job(sid, "analyze") or {})}
    except store.StoreError as e:
        raise _store_error(e)
    plan, edits = _plan_for(sid, fields, body.plans)
    ctx0 = store.page_contexts(fields)
    tok = store.JOB.set("analyze")                           # its model calls are counted on the job (a restart gives them back)
    job = asyncio.create_task(analyze.analyze(fields, answers, plan, edits, sid=sid))
    store.JOB.reset(tok)
    try:
        res = await job
    except asyncio.CancelledError:
        if not job.cancelled():
            raise
        res = {"status": "fail", "needs": [], "why": "preempted"}
    except (KeyError, TypeError, AttributeError, ValueError) as e:
        print(f"analyze: bad input {type(e).__name__}: {e}", flush=True)
        res = {"status": "fail", "needs": [], "why": "input"}
    status, found = res["status"], []
    if status in ("ok", "none"):
        if store.form(sid) not in (None, ctx0):
            status = "stale"                              # the permit was edited while it was read
        found = store.add_needs(sid, res["needs"]) if status in ("ok", "none") else []
        if found is None:
            status, found = "late", []                    # the review ended meanwhile: not asked any more
    summary = {"why": res.get("why"), "found": len(found), "plan": res.get("plan"), "digest": res.get("digest"),
               "ms": (res.get("meta") or {}).get("ms"), "rowhash": res.get("rowhash"), "refs": res.get("refs")}
    store.finish_job(sid, "analyze", "done" if status in ("ok", "none") else status, summary)
    return {"status": status, **summary}


class LinkIn(BaseModel):
    fields: dict
    plans: dict = {}         # {token, idx: [confirmed plan indices]} as for /api/analyze


# 계획서 연결 제안 (LINK, design §6.3): which confirmed 작업계획서 is the same work as this permit — a suggestion the
# foreman confirms or not; prepared ahead (it gives way to a foreman's answer being read)
@app.post("/api/dialogues/{sid}/link")
async def dialogue_link(sid: str, body: LinkIn):
    fields = _fields(body.fields)
    try:
        store.revision(sid)                                  # the review exists
    except store.StoreError as e:
        raise _store_error(e)
    tok, idx = str(body.plans.get("token") or ""), [i for i in body.plans.get("idx") or [] if isinstance(i, int)]
    if not (tok and idx and workplan._touch(tok)):
        return {"status": "none", "links": [], "why": "확정한 작업계획서가 없음"}
    try:
        plans = workplan.load_plans(tok)
        if plans is None:
            raise ValueError("gone")
        saved = workplan.load_edits(tok)
    except (OSError, ValueError):
        return {"status": "none", "links": [], "why": "작업계획서 보관 기간이 지남"}
    try:
        try:                                                 # the permit's open rule questions: what a link may answer
            answers, _, _ = _unlinked(sid, *store.current(sid, fields, store.revision(sid)))
            open_qs = augment.questions(fields, answers)[0]
        except store.StoreError:
            open_qs = []
        return await link.suggest(fields, plans, idx, saved, sid=sid, open_qs=open_qs)
    except asyncio.CancelledError:
        return {"status": "fail", "links": [], "why": "preempted"}


class LinkConfirm(BaseModel):
    plan: int                # the plan's index as suggested
    token: str = ""          # the plans' upload it is in (a new upload is new plans)
    title: str = ""
    rel: str                 # the relation suggested (link.LINKED)
    accept: bool             # 「같은 작업으로 연결」 or 「아님」
    evidence: dict = {}      # the two rows shown
    digest: str = ""         # the plan as it was shown (workplan.plan_digest): a changed plan makes the link expire
    imports: list = []       # the values the foreman ticked: [{qid, choice, value}]


# the foreman's answer to a link suggestion (design §6.3): kept with the review; a link is never made without it
@app.post("/api/dialogues/{sid}/link/confirm")
def dialogue_link_confirm(sid: str, body: LinkConfirm):
    if body.rel not in link.LINKED:
        raise HTTPException(422, "알 수 없는 관계")
    ev = {k: str(v)[:200] for k, v in (body.evidence or {}).items() if k in ("permit", "plan")}
    try:
        store.put_job(sid, f"link:{body.token}:{body.plan}", "confirmed" if body.accept else "refused",
                      {"plan": body.plan, "token": body.token, "title": body.title[:120], "rel": body.rel, "evidence": ev,
                       "digest": body.digest[:32] or None,
                       "imports": [{**{k: str(x.get(k))[:200] for k in ("qid", "choice", "value")},
                                    **({"at": x["at"]} if type(x.get("at")) in (int, float) else {})} for x in body.imports[:8]
                                   if isinstance(x, dict)] if body.accept else []})
    except store.StoreError as e:
        raise _store_error(e)
    return {"ok": True, "links": store.jobs(sid, "link:")}


def _links_now(sid):
    """the review's links, each with whether its plan changed since it was linked (design §2.3: expired)"""
    out = {}
    for k, v in store.jobs(sid, "link:").items():
        plans = workplan.load_plans(v.get("token") or "") if v.get("token") else None
        i = v.get("plan")
        now = workplan.plan_digest(plans[i], workplan.load_edits(v["token"]).get(str(i))) if plans and isinstance(i, int) and 0 <= i < len(plans) else None
        out[k] = {**v, "digest_now": now, "expired": bool(v.get("digest") and now and now != v["digest"]),
                  "gone": plans is None and bool(v.get("token"))}
    return out


def _stale_imports(sid):
    """the values links brought from a plan changed since it was linked (design §2.3), until the foreman confirms them
    again on the changed plan (「그대로 둠」: a new digest) or takes them out"""
    try:
        return [x for v in _links_now(sid).values() if v["status"] == "confirmed" and v["expired"] for x in v.get("imports") or []]
    except (OSError, ValueError, KeyError, TypeError):
        return []


def _unlinked(sid, answers, rev, dropped):
    """(answers, revision, dropped) without the typed answers a link brought from a plan changed since: like a checking
    answer whose base changed (store._project), they stop counting (rules, analysis, checklist, submission) and are
    reported in dropped; their question is open again. The same words typed again later are his own answer."""
    stale = _stale_imports(sid) if sid else []
    if not stale:
        return answers, rev, dropped

    def brought(a):
        return not a.get("pid") and any(x.get("qid") == a["qid"] and x.get("choice") == a.get("choice") and x.get("at") in (None, a.get("at"))
                                        and augment.norm_ids(x.get("value") or "").strip() == (a.get("value") or "").strip() for x in stale)
    gone = [a["qid"] for a in answers if brought(a)]
    return [a for a in answers if not brought(a)], rev, list(dropped or []) + gone


# a linked plan changed since (design §2.3): the link and the values it brought are to be checked again
@app.post("/api/dialogues/{sid}/links/check")
def dialogue_links_check(sid: str):
    try:
        return {"links": list(_links_now(sid).values())}
    except store.StoreError as e:
        raise _store_error(e)


class Understand(BaseModel):
    fields: dict
    answers: list = []
    qid: str                 # the answer to read (a typed answer of at least 8 letters)
    session_id: str = ""     # the proposals are kept there with ids; without it they are only shown
    expected_revision: int | None = None
    deadline: float = 60     # measurement only (CROSCAN_MEASURE=1): otherwise 60 s
    think: int = 0           # measurement only: otherwise thinking off (measured 2026-10-31)


MEASURE = os.environ.get("CROSCAN_MEASURE") == "1"


# AI 답 이해 (design §4): proposals only, each checked here; the foreman confirms them before they are answers.
# A browser that goes away (「기다리지 않고 다음 질문」, its own time limit) cancels the model call: the slot is freed.
@app.post("/api/understand")
async def do_understand(body: Understand, request: Request):
    fields = _fields(body.fields)
    answers, rev, _ = _calc_answers(_answers(body.answers), body.session_id, fields, body.expected_revision)
    gone = augment.withdrawn(answers)                # understand.py stays as it is: the caller gives it the live answers
    answers = augment.live_answers(answers)
    src = next((a for a in answers if a["qid"] == body.qid and not a.get("pid")), None)
    if not src or len((src.get("value") or "").strip()) < 8 or src.get("choice") == "unknown" or body.qid in gone:
        return {"status": "none", "props": [], "apart": [], "why": "읽을 답이 없음"}
    # the rules' proposals waiting on the card are not asked of the model again
    answers = answers + [p for p in (store.pending(body.session_id, fields) if body.session_id else []) if p["by"] == src["qid"]]
    deadline, think = (max(10.0, min(180.0, body.deadline)), max(0, min(256, body.think))) if MEASURE else (60.0, 0)
    form0 = store.form_of(body.session_id) if body.session_id else None
    sk = (body.session_id, body.qid)
    jk = f"turn:{body.qid}:{os.urandom(4).hex()}" if body.session_id else None
    if jk:
        store.open_job(body.session_id, jk)
    _STAGE[sk] = "대기 중"
    loop = asyncio.get_running_loop()
    t_end = loop.time() + deadline

    async def turn():
        """the reading and its check of what would lower a signal, under one deadline and one cancellation"""
        out = await understand.read(fields, answers, src, deadline=deadline, think=think, sid=body.session_id or None)
        _STAGE[sk] = "결과 검사 중"
        if out.get("props"):
            left = t_end - loop.time()
            kw = {"deadline": left} if "deadline" in inspect.signature(critique.review).parameters else {}
            out["props"], held = await critique.review(fields, src, out["props"], sid=body.session_id or None, **kw)
            out["apart"] = (out.get("apart") or []) + held
            if not out["props"] and not out["apart"]:
                out["status"] = "none"
        return out
    tok = store.JOB.set(jk)                                  # the reading's model calls are counted on its job
    job = asyncio.create_task(turn())
    store.JOB.reset(tok)
    try:
        while not job.done():
            await asyncio.wait({job}, timeout=0.5)
            if _STAGE.get(sk) == "대기 중" and llm._HOLDER.get("task") is job:
                _STAGE[sk] = "답 해석 중"                      # the model took it: no longer waiting
            if not job.done() and (await request.is_disconnected() or loop.time() > t_end + 5):
                job.cancel()
                return {"status": "fail", "props": [], "apart": [], "why": "cancelled"}
        out = job.result()
        if body.session_id and out.get("next_qid"):
            _NEXT[body.session_id] = out["next_qid"]
        if body.session_id and out.get("props"):
            try:
                # only the questions still open now (one answered or gone meanwhile gets no reading), and only when
                # the answer read is the same answer given at the same time
                now, _, _ = store.current(body.session_id, fields, store.revision(body.session_id))
                open_now = {q["qid"] for q in augment.questions(fields, now)[0]}
                out["props"] = [p for p in out["props"] if p["qid"] in open_now]
                out["props"], rev = store.propose(body.session_id, "ai", src, out["props"], basis=rev, form=form0, src_at=src.get("at"))
                _dest(fields, now, out["props"])
            except store.StoreError as e:                 # refused when the review moved on while the model read it
                return {"status": "fail", "props": [], "apart": [], "why": e.code, "revision": e.extra.get("revision")}
        return {**out, "revision": rev}
    except (KeyError, TypeError, AttributeError, ValueError) as e:
        print(f"understand: bad input {type(e).__name__}: {e}", flush=True)
        raise HTTPException(400, "양식 값(fields) 형식이 맞지 않습니다")
    finally:
        if not job.done():
            job.cancel()
        _STAGE.pop(sk, None)
        if jk:
            store.finish_job(body.session_id, jk, "done" if job.done() and not job.cancelled() else "cancelled")


_NEXT = {}                   # session -> the open question its last reading named as next (PHRASE goes there first)


class PhraseIn(BaseModel):
    fields: dict
    session_id: str
    qids: list = []          # the questions the client will ask next, in its order


# PHRASE (design §1.4·§10.5): the wording of the next 1~2 questions, prepared in the background (it gives way to
# everything else); the model picks one of the server's wordings, the client shows it when the question is still the
# same; none prepared → the rule wording
@app.post("/api/understand/phrase")
async def understand_phrase(body: PhraseIn):
    fields = _fields(body.fields)
    try:
        answers, _, _ = store.current(body.session_id, fields, store.revision(body.session_id))
    except store.StoreError as e:
        return {"status": "none", "phrased": {}, "why": e.code}
    open_ = {q["qid"]: q for q in augment.questions(fields, answers)[0]}
    want = [x for x in ([_NEXT.get(body.session_id)] + [str(x) for x in body.qids]) if x]
    targets = []
    for qid in want:
        if qid in open_ and open_[qid] not in targets and not qid.split(":")[0].startswith(need_catalog.CHECKING):
            targets.append(open_[qid])
    out = await understand.phrase(answers, targets[:2], sid=body.session_id)
    return {"status": "ok" if out else "none", "phrased": out}


class Warm(BaseModel):
    fields: dict
    qid: str                 # the question being shown
    session_id: str


# design §10.7: the question being shown is read into the model's cache while the foreman reads and answers it
@app.post("/api/understand/warm")
async def understand_warm(body: Warm):
    fields = _fields(body.fields)
    try:                                                     # the session as it is now (a cache warm-up writes nothing)
        answers, _, _ = store.current(body.session_id, fields, store.revision(body.session_id))
    except store.StoreError as e:
        return {"status": "none", "why": e.code}
    open_, _, _, _ = augment.questions(fields, [a for a in answers if a["qid"] != body.qid])
    q = next((x for x in open_ if x["qid"] == body.qid), None)
    if not q or not any(len(c.get("ask") or "") for c in q["choices"]):
        return {"status": "none"}                            # a question without a typed answer: nothing to read later
    if (body.session_id, body.qid) in understand._WARM:
        return {"status": "ok", "again": True}               # warmed already for this question
    try:
        store.warm(body.session_id, body.qid)
    except store.StoreError as e:
        return {"status": "none", "why": e.code}
    return await understand.warm(fields, answers, q, body.session_id)


def _rev(body):
    r = body.get("expected_revision")
    return r if isinstance(r, int) and not isinstance(r, bool) else None


@app.post("/api/submit")
async def submit(file: UploadFile = File(...), payload: str = Form(...)):
    try:
        body = json.loads(payload)
        assert isinstance(body, dict) and isinstance(body.get("fields"), dict)
    except (ValueError, AssertionError):
        raise HTTPException(400, "제출 내용(payload)을 읽을 수 없습니다")
    s = _augment(body["fields"], body.get("answers", []), body.get("session_id") or "", _rev(body), write=False)   # not a list: 400
    data = await file.read()
    try:
        pymupdf.open(stream=data, filetype="pdf").close()
    except Exception:
        raise HTTPException(400, "원본 PDF를 열 수 없습니다. 허가서 파일을 다시 올려 주세요.")
    out = addendum.pdf(data, s["sheets"], body["fields"], s["reflect"])
    name = Path(file.filename or "permit.pdf").stem + "_추가검토.pdf"
    from urllib.parse import quote
    return Response(out, media_type="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})


# 제출 (design §2.3·§12.2): the review as it is now, made once and kept; the documents are drawn from it afterwards
@app.post("/api/submissions")
async def submit_snapshot(file: UploadFile = File(...), payload: str = Form(...)):
    try:
        body = json.loads(payload)
        assert isinstance(body, dict) and isinstance(body.get("fields"), dict) and body.get("session_id")
    except (ValueError, AssertionError):
        raise HTTPException(400, "제출 내용(payload)을 읽을 수 없습니다")
    data = await file.read()
    try:
        pymupdf.open(stream=data, filetype="pdf").close()
    except Exception:
        raise HTTPException(400, "원본 PDF를 열 수 없습니다. 허가서 파일을 다시 올려 주세요.")
    fields, sid, rev = _fields(body["fields"]), body["session_id"], _rev(body)
    s = _augment(fields, [], sid, rev, write=False)           # the session at the revision the foreman saw (409 if behind)
    answers, _, _ = _calc_answers([], sid, fields, rev, write=False)
    try:
        ok, _, _ = _normalize(fields, answers)
        from . import checkai
        # the AI items he put in are checked against the suggestion kept for the work as it is now (design §7)
        ck = submissions.confirm_checklist(checkai.attach(checklist.draft(fields, ok), sid, fields, ok, body.get("checklist")), body.get("checklist"),
                                           marks=checkai.marks_cached(sid, fields, ok))
    except submissions.Refused as e:
        raise HTTPException(409, {"code": e.code, "message": e.detail, **e.extra})
    except (KeyError, TypeError, AttributeError, ValueError) as e:
        raise HTTPException(400, f"체크리스트를 확인할 수 없습니다: {e}")
    except Exception as e:                                # checkai.Stale: the work changed after it was put in
        if type(e).__name__ != "Stale":
            raise
        raise HTTPException(409, {"code": "checklist_changed", "message": "작업 내용이 바뀌어 AI 추가 후보를 다시 확인해야 합니다", "items": [str(e)]})
    if len(s["effective"]) != 1:
        raise HTTPException(400, "허가서 한 건씩 제출합니다")
    P = s["effective"][0]
    # the 작업계획서 as confirmed in step 1, with the edits saved now (their 수정본 is drawn now, not at download)
    plans = body.get("plans") if isinstance(body.get("plans"), dict) else {}
    tok = str(plans.get("token") or "")
    plan_key = [tok, workplan.load_edits(tok) if tok else {}, sorted(i for i in plans.get("checked") or [] if isinstance(i, int))]
    key = submissions.key_of(sid, rev, [hashlib.sha256(data).hexdigest(), fields, answers, ck, plan_key])
    again = submissions.find(sid, rev, key)
    if again:
        return {**again, "manager": safety.placement(again["summary"].get("permit_no"), again["summary"].get("dates"))}
    snap = {"session_id": sid, "links": _links_now(sid), "events": store.events(sid), "confirmations": store.confirmations(sid),
            "fields": fields, "answers": answers, "sheets": s["sheets"], "reflect": s["reflect"], "checklist": ck,
            "unresolved": s.get("unresolved", []), "records": s.get("records", []), "budget": s.get("budget"),
            "analysis": s.get("analysis"), "revision": rev, "plans": {"token": tok, "checked": plan_key[2]}}
    snap["plan_values"] = safety.plan_values(tok, plan_key[1], plan_key[2])       # Codex A6: for the manager's input
    snap["answers_read"] = ok
    cnt = {k: sum(1 for Q in ck["permits"] for it in Q["items"] if it["state"] == k) for k in ("yes", "no", "check")}
    summary = {"permit_no": P["permit_no"], "label": P["label"], "who": P["who"], "revision": rev,
               "dates": safety.spanned_dates(P.get("windows") or {}),       # a night window is on the next date too
               "answers": len([a for a in answers if not a.get("pid")]), "adopted": len([a for a in answers if a.get("pid")]),
               "unresolved": len({x["key"] for x in s.get("unresolved", [])}),
               "left": [x["why"] for x in s.get("unresolved", [])][:6], "checklist": cnt,
               "after_close": len(store.events(sid, ("after_close",)))}
    import time as _t
    created = _t.time()
    # the documents drawn once, now: a later download gives these bytes (no new time, catalogue or font)
    files = {"original": data, "permit": await asyncio.to_thread(addendum.pdf, data, s["sheets"], fields, s["reflect"]),
             "checklist": await asyncio.to_thread(checklist.pdf, ck, fields)}
    if tok:
        got = await asyncio.to_thread(workplan.edited_pdf, tok)
        if got:
            files["plans"] = got[0]
    out = submissions.create(sid, rev, key, files, snap, summary, created)
    if not out.get("again"):
        _later(_warm_manager())                 # design §10.7: the manager's view of the day made now, behind
    return {**out, "manager": safety.placement(summary["permit_no"], summary["dates"]), "summary": {**summary, "created": out["created"], "files": sorted(k for k, v in files.items() if v)}}


SUB_FILES = {"permit": "추가검토", "checklist": "위험체크리스트", "plans": "작업계획서"}


@app.get("/api/submissions/{sub_id}/{name}.pdf")
def submitted_file(sub_id: str, name: str):
    """a document of a submission, as drawn at 제출"""
    got = submissions.get(sub_id) if name in SUB_FILES else None
    if not got:
        raise HTTPException(404, "그런 제출 문서가 없습니다")
    payload, hashes, summ = got
    if AUTH == "proxy" and not store.MANAGER.get():       # a foreman: his own submission only
        sid = (payload or {}).get("session_id")
        if not sid or store.owner_of(sid) != store.OWNER.get():
            raise HTTPException(404, "그런 제출 문서가 없습니다")
    out = submissions.file(hashes, name)
    if out is None:
        raise HTTPException(410, "보관 기간이 지나 제출 문서가 없습니다")
    from urllib.parse import quote
    return Response(out, media_type="application/pdf",
                    headers={"Content-Disposition": f"inline; filename*=UTF-8''{quote(summ['permit_no'] + '_' + SUB_FILES[name] + '.pdf')}"})


@app.get("/api/safety/submissions")
def safety_submissions():
    """the foremen's latest submission per permit number, for the safety manager's document view"""
    try:
        D = safety.data()
    except FileNotFoundError:
        return {**submissions.latest(), "_outside": [], "_versions": {}}
    # Codex A6: a submission whose number is not in the day's list is listed apart, never dropped
    return safety.submission_view(D, submissions.latest(D["date"]), submissions.latest(), submissions.get)


@app.post("/api/reflect/preview")
async def reflect_preview(file: UploadFile = File(...), payload: str = Form(...)):
    """The 반영본 pages as the PDF will have them (PNG data URLs), for the web preview: the same plan and drawing."""
    try:
        body = json.loads(payload)
        assert isinstance(body, dict) and isinstance(body.get("fields"), dict)
    except (ValueError, AssertionError):
        raise HTTPException(400, "미리 보기 내용(payload)을 읽을 수 없습니다")
    s = _augment(body["fields"], body.get("answers", []), body.get("session_id") or "", _rev(body), write=False)
    try:
        doc = pymupdf.open(stream=await file.read(), filetype="pdf")
    except Exception:
        raise HTTPException(400, "원본 PDF를 열 수 없습니다")
    import base64
    with doc:
        if reflect.apply(doc, body["fields"], s["reflect"]):
            addendum._tidy(doc)
        pages = ["data:image/png;base64," + base64.b64encode(pg.get_pixmap(dpi=110).tobytes("png")).decode() for pg in doc]
    return {"pages": pages, "reflect": s["reflect"]}


class ChecklistIn(BaseModel):
    fields: dict
    answers: list = []       # the 작업계획서 are not sent: the checklist comes from the permit alone
    session_id: str = ""
    expected_revision: int | None = None
    keep: list = []          # ai-suggest: the AI items he put in ({id, quote}), checked again against the work now


@app.post("/api/checklist")
def do_checklist(body: ChecklistIn):
    fields = _fields(body.fields)
    answers, _, _ = _calc_answers(_answers(body.answers), body.session_id, fields, body.expected_revision, write=False)
    try:
        ok, _, _ = _normalize(fields, answers)              # the same reading of each answer as the review's
        return checklist.draft(fields, ok)
    except (KeyError, TypeError, AttributeError, ValueError) as e:
        print(f"checklist: bad input {type(e).__name__}: {e}", flush=True)
        raise HTTPException(400, "양식 값(fields) 형식이 맞지 않습니다")


# 체크리스트 AI 추가 위험요인 (design §7): catalog items of other kinds of work found in this work's own words, offered to
# put in. Made once per review and work facts (kept; asked again, the kept one), in the model slot's 「prepared」 order;
# the page asks for it ahead when the dialogue ends (design §10.7), so the checklist step finds it made.
@app.post("/api/checklist/ai-suggest")
async def checklist_ai(body: ChecklistIn):
    from . import checkai
    if not body.session_id:
        return {"status": "none", "items": [], "why": "검토 세션 없음"}
    fields = _fields(body.fields)
    answers, _, _ = _calc_answers(_answers(body.answers), body.session_id, fields, body.expected_revision, write=False)
    try:
        ok, _, _ = _normalize(fields, answers)
        return await checkai.suggest(fields, ok, body.session_id, keep=body.keep[:12])
    except (KeyError, TypeError, AttributeError, ValueError) as e:
        print(f"checklist ai: bad input {type(e).__name__}: {e}", flush=True)
        raise HTTPException(400, "양식 값(fields) 형식이 맞지 않습니다")


class ChecklistPdf(BaseModel):
    fields: dict
    checklist: dict
    answers: list = []
    session_id: str = ""
    expected_revision: int | None = None


@app.post("/api/checklist/pdf")
def checklist_pdf(body: ChecklistPdf):              # plain def: the PDF is drawn in the thread pool
    fields = _fields(body.fields)
    answers, _, _ = _calc_answers(_answers(body.answers), body.session_id, fields, body.expected_revision, write=False)
    try:
        ok, _, _ = _normalize(fields, answers)
        # the server's base list, his choices put in (design §7): no base item can drop out of the paper
        out = checklist.pdf(checklist.merge(checklist.draft(fields, ok), body.checklist), fields)
    except (KeyError, TypeError, AttributeError, ValueError) as e:
        raise HTTPException(400, f"체크리스트를 만들 수 없습니다: {e}")
    return Response(out, media_type="application/pdf", headers={"Content-Disposition": "inline; filename=checklist.pdf"})


@app.get("/api/safety/overview")
def safety_overview():
    try:
        return safety.overview()
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


# design §5.5: the safety manager does not set the schedule, so the public check takes no schedule to try (the
# times are the documents'); pairs.detect(overrides) stays for the tests only
@app.post("/api/safety/detect")
def safety_detect():                                  # plain def: 445 pairs are judged in the thread pool
    try:
        return _detect()
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


_DET = {"key": None, "out": None}


def _detect():
    """the day's judgement with the foremen's confirmed answers (쌍 하이브리드, design §8.1), and how it differs from
    the documents alone; computed again only when the day's database or a submission changed"""
    db, _ = safety._home()
    D = safety.data()
    latest = submissions.latest(D["date"])                  # this day's work only
    key = (str(db), db.stat().st_mtime_ns, D["date"], tuple(sorted((k, v["id"]) for k, v in latest.items())))
    if key != _DET["key"]:
        # Codex A6: the confirmed facts and the place and times the latest submission confirms (its plans too)
        confirmed, submitted, versions = safety.hybrid_inputs(D, latest, submissions.get)
        mix = bool(confirmed or submitted)
        base = pairs.detect()
        # the answers may add or raise an alarm, never take one away or lower it (a reading does not lift an alarm)
        raw = pairs.detect(confirmed=confirmed, submitted=submitted) if mix else base
        out = pairs.floor(base, raw) if mix else dict(base)
        by_id = {p["id"]: confirmed[p["permit_no"]] for p in D["permits"] if confirmed.get(p.get("permit_no"))}
        for i, v in versions.items():                   # what made a change: the submitted place and times too
            if v["values"]:
                by_id[i] = by_id.get(i, []) + [{"item": f"제출본 {k}", "value": x} for k, x in v["values"].items()]
        out["hybrid"] = {"permits": sorted(confirmed), "answers": sum(len(v) for v in confirmed.values()),
                         "submitted": sorted(submitted), "versions": versions,
                         "changes": pairs.compare(base, raw, by_id) if mix else {"new": [], "kept": [], "gone": []}}
        pairs.annotate(out, {d["id"]: d for d in D["permits"] + D["plans"]})   # display only (§8.4 선후 계획)
        _DET.update(key=key, out=out)
    return _DET["out"]


_TASKS = set()


def _later(coro):
    """run coro behind the request (kept until done)"""
    t = asyncio.create_task(coro)
    _TASKS.add(t)
    t.add_done_callback(_TASKS.discard)
    return t


def _doc_no(i):
    return i if any(d["id"] == i and d["type"] == "permit" for d in safety.data()["permits"]) else "WP-" + str(i)[-2:]


def _note_key(p, det):
    return (p["key"], det.get("date"), json.dumps(coordnote.model_input(p, _doc_no), ensure_ascii=False, sort_keys=True))


def _keep_note(k, out):
    if out["status"] == "ok" or out["why"] in ("확인된 반장 답이 없음", "규칙의 확인할 것이 없음", "고를 것이 하나뿐"):
        _NOTES[k] = out
    if len(_NOTES) > 500:
        _NOTES.clear()


WARM_NOTES = 5


async def _warm_manager():
    """design §10.7: when a submission comes in, the day's judgement is made again now, and the notes of the first
    pairs (1순위, at most WARM_NOTES) are written while the model is idle (they give way to anyone waiting), so that
    the manager opening the day or a pair does not wait for them"""
    try:
        det = await asyncio.to_thread(_detect)
    except Exception as e:                      # the day's data missing: nothing to prepare
        print(f"warm: {type(e).__name__}", flush=True)
        return
    for p in [x for x in det["pairs"] if x["priority"] == 1][:WARM_NOTES]:
        k = _note_key(p, det)
        if k not in _NOTES:
            _keep_note(k, await coordnote.note(p, _doc_no, pri=llm.WARM))
    # the first near pairs' AI review, kept for when the manager asks for it (shown only on his request, design §8.2)
    from . import pairreview
    await pairreview.batch(det)


class NoteIn(BaseModel):
    key: str                 # the pair as listed ("a|b")


_NOTES = {}


# 협조 문자의 「협의할 점」 (design §6.5): one sentence from a foreman's confirmed answer about this pair, offered under
# the message; the manager puts it in or not
@app.post("/api/safety/coord-note")
async def safety_coord_note(body: NoteIn):
    try:
        det = await asyncio.to_thread(_detect)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    p = next((x for x in det["pairs"] if x["key"] == body.key), None)
    if not p:
        raise HTTPException(404, "그런 작업쌍이 없습니다")
    k = _note_key(p, det)
    if k not in _NOTES:
        out = await coordnote.note(p, _doc_no, pri=llm.ASKED)
        _keep_note(k, out)
        return out
    return _NOTES[k]


from . import holdq, pairreview  # noqa: E402


class PairReviewIn(BaseModel):
    a: str                   # the two works (document ids), as the manager opened them
    b: str


# 규칙 밖 「AI 검토 권장」 (design §8.2): one pair the manager asks about; a separate result, never a rule pair
@app.post("/api/safety/pair-review")
async def safety_pair_review(body: PairReviewIn):
    try:
        det = await asyncio.to_thread(_detect)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    out = await pairreview.review(det, body.a, body.b)
    if out["status"] == "refused":
        raise HTTPException(422, out["why"])
    return out


@app.get("/api/safety/pair-reviews")
def safety_pair_reviews():
    try:
        det = _detect()
        return pairreview.listing(det["date"], det)              # only results of the documents as they are now
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


# 판정보류 쌍의 담당별 질문 (design §8.3): what each foreman is asked about his own work; croScan sends nothing
@app.get("/api/safety/hold-questions")
def safety_hold_questions():
    try:
        return holdq.build(_detect())
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


class HoldMarkIn(BaseModel):
    key: str
    state: str               # 미전달 · 전달함 · 응답 받음


@app.post("/api/safety/hold-questions/mark")
def safety_hold_mark(body: HoldMarkIn):
    try:
        return holdq.mark(_detect(), body.key, body.state)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except holdq.HoldError as e:
        raise HTTPException(e.status, e.detail)


class ExplainIn(BaseModel):
    key: str                 # the pair as listed ("a|b")
    which: str = ""          # one of the fixed questions: seq | used | defer
    question: str = ""       # or the manager's own words (the model, checked)


_EXPLAINED = {}


# 요청형 「왜?」 (design §5.5): about the pair the manager has open; the fixed questions at once, his own words once
# through the model (the same words for the same pair are answered from memory)
@app.post("/api/safety/explain")
async def safety_explain(body: ExplainIn):
    try:
        det = await asyncio.to_thread(_detect)
        D = safety.data()
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    p = next((x for x in det["pairs"] if x["key"] == body.key), None)
    if not p:
        raise HTTPException(404, "그런 작업쌍이 없습니다")
    docs = {d["id"]: d for d in D["permits"] + D["plans"]}
    c = explain.claims(p, docs)
    qs = explain.applicable(p)
    if body.which:
        if body.which not in {q["id"] for q in qs}:
            raise HTTPException(422, "이 작업쌍에 맞지 않는 질문입니다")
        frame, chk = explain.verify(explain.fixed(c, body.which), c, docs)
        return {"status": "fixed", "question": explain.FIXED[body.which], "frame": frame, "questions": qs, "verify": chk}
    q = re.sub(r"\s+", " ", body.question or "").strip()
    if not q or len(q) > 200:
        raise HTTPException(422, "질문을 200자 안에서 적어 주세요")
    k = (body.key, q, json.dumps(c, ensure_ascii=False, sort_keys=True))
    if k not in _EXPLAINED:
        frame, status, why = await explain.ask(c, q, {x["id"] for x in qs})
        if status != "fail":                               # a failed or refused reading is not kept
            _EXPLAINED[k] = (frame, status, why)
        if len(_EXPLAINED) > 500:
            _EXPLAINED.clear()
    else:
        frame, status, why = _EXPLAINED[k]
    frame, chk = explain.verify(frame, c, docs)
    return {"status": status, "why": why, "question": q, "frame": frame, "questions": qs, "verify": chk}


class XQuery(BaseModel):
    target: dict             # {kind: pair|question|checklist|change|revision, …} what the explanation is about
    fields: dict = {}
    session_id: str = ""
    which: str = ""          # pair: one of the fixed questions
    question: str = ""       # pair: the manager's own words


def _x_answers(fields, sid):
    """the review's answers as they are now (an explanation reads, it writes nothing)"""
    if not sid:
        return []
    try:
        answers, _, _ = store.current(sid, fields, store.revision(sid))
    except store.StoreError as e:
        raise _store_error(e)
    ok, _, _ = _normalize(fields, answers)
    return ok


# 설명 질의 (design §12.1·§5.2): one door for the 「왜?」 of a pair, a question, a checklist item, a change in the 반영본
# or a revision; fixed explanations from the server's own data (no model but the pair's own words), each verified (§5.4)
@app.post("/api/explanations/query")
async def explanations_query(body: XQuery):
    t = body.target if isinstance(body.target, dict) else {}
    kind = t.get("kind")
    if kind == "pair":
        if AUTH == "proxy" and not store.MANAGER.get():          # a pair is the manager's view (the gate sees only the path)
            raise HTTPException(403, "안전관리자만 볼 수 있습니다")
        return await safety_explain(ExplainIn(key=str(t.get("key") or ""), which=body.which, question=body.question))
    fields = _fields(body.fields) if body.fields else {}
    try:
        if kind == "question":
            q = t.get("q") if isinstance(t.get("q"), dict) else {}
            if not q.get("item"):
                raise HTTPException(422, "질문이 없습니다")
            w = need_catalog.why(q)
            if w:
                w["refs"] = retrieval.related(f"{w['need']} {q.get('text', '')}")
            c = explain.question(q, w)
        elif kind == "checklist":
            if not fields:
                raise HTTPException(422, "양식 값이 없습니다")
            ck = checklist.draft(fields, _x_answers(fields, body.session_id))
            P = next((x for x in ck["permits"] if x["permit_no"] == t.get("permit")), None)
            it = next((x for x in (P or {}).get("items", []) if x["id"] == t.get("item")), None)
            if not it:
                raise HTTPException(404, "그런 체크리스트 항목이 없습니다")
            now = t.get("now") if isinstance(t.get("now"), dict) else {}
            it = {**it, "touched": bool(now.get("touched")), **({"state": now["state"]} if now.get("state") in ("yes", "no", "check") else {})}
            on = {str(x) for x in now.get("on") or []}
            it["controls"] = [{**k, "on": k["id"] in on} for k in it["controls"]] if "on" in now else it["controls"]
            c = explain.checklist(it, P["permit_no"])
        elif kind == "change":
            if not fields or not body.session_id:
                raise HTTPException(422, "양식 값이 없습니다")
            s = _augment(body.fields, [], body.session_id, store.revision(body.session_id), write=False)
            fill = next((x for R in (s.get("reflect") or {}).values() for x in R.get("fills") or [] if t.get("key") in x.get("keys", [])), None)
            extra = None if fill else next((e for R in (s.get("reflect") or {}).values() for e in R.get("extra") or [] if e[0] == t.get("label")), None)
            if not fill and not extra:
                raise HTTPException(404, "반영본에 그런 변경이 없습니다")
            c = explain.change(fill, extra, next(iter(s.get("reflect") or {}), ""))
        elif kind == "revision":
            qids = [str(x) for x in t.get("qids") or []][:20]
            c = explain.revision([{"qid": q, "slot": addendum.ITEM.get(q.split(":")[0].split(".")[0]) or q.split(":")[0]} for q in qids])
        else:
            raise HTTPException(422, "알 수 없는 설명 대상")
    except store.StoreError as e:
        raise _store_error(e)
    except (KeyError, TypeError, AttributeError, ValueError) as e:
        print(f"explain: bad input {type(e).__name__}: {e}", flush=True)
        raise HTTPException(400, "설명할 대상을 읽을 수 없습니다")
    frame, chk = explain.verify(explain.frame_of(c), c, None)
    return {"status": "fixed", "kind": kind, "frame": frame, "verify": chk}


@app.get("/api/safety/doc-summaries")
async def safety_doc_summaries():
    try:
        det = await asyncio.to_thread(_detect)
        D = safety.data()
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    picks = {}
    for (pid, cl), kind in [kv for v in list(permitsignal._AI.values()) for kv in v.items()]:
        picks[(pid, cl)] = kind                              # what the model picked already (no call while waiting)
    if not _SIG_WARM.get(D["date"]):
        _SIG_WARM[D["date"]] = True
        _later(_warm_signals(D))
    return await asyncio.to_thread(docsum.build, D, det, picks)


_SIG_WARM = {}


async def _warm_signals(D):
    """the plans' lines the rules could not place, given to the model while it is idle (WARM): the next summary has them"""
    for p in D["plans"]:
        try:
            await permitsignal.suggest_ai(p)
        except asyncio.CancelledError:
            raise
        except Exception as e:                               # one plan failing does not stop the others
            print(f"signal warm: {type(e).__name__}", flush=True)


class PostDraftIn(BaseModel):
    key: str                 # the pair ("a|b")
    doc: str                 # the work the sheet is for


# 게시 서류 AI 보충 (design §6.5·§19.2): a draft for an unissued sheet; the manager adopts it or not
@app.post("/api/safety/post-draft")
async def safety_post_draft(body: PostDraftIn):
    try:
        det = await asyncio.to_thread(_detect)
        D = safety.data()
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    d = next((x for x in D["permits"] + D["plans"] if x["id"] == body.doc), None)
    if not d:
        raise HTTPException(404, "그런 서류가 없습니다")
    facts = []
    if d["type"] == "permit":
        sub = submissions.latest(D["date"]).get(d["permit_no"])
        got = submissions.get(sub["id"]) if sub else None
        facts = pairs.confirmed_facts(got[0].get("answers")) if got else []
    return await posting.draft(det, body.key, body.doc, facts)


class SheetIn(BaseModel):
    doc_id: str
    kind: str                  # post: 허가서 원본 + 별지 · notice: 일상작업반 전달문
    sheet: dict


@app.post("/api/safety/sheet.pdf")
def safety_sheet(body: SheetIn):                     # plain def: drawn in the thread pool
    try:
        out = posting.pdf(body.doc_id, body.kind, body.sheet)
    except (KeyError, FileNotFoundError):
        raise HTTPException(404, "그런 서류가 없습니다")
    except (ValueError, TypeError, AttributeError) as e:
        raise HTTPException(400, f"서류를 만들 수 없습니다: {e}")
    from urllib.parse import quote
    name = f"{body.doc_id}_" + ("현장게시용" if body.kind == "post" else "일상작업반_전달문") + ".pdf"
    return Response(out, media_type="application/pdf", headers={"Content-Disposition": f"inline; filename*=UTF-8''{quote(name)}"})


@app.get("/api/safety/doc/{doc_id}")
def safety_doc(doc_id: str):
    try:
        return safety.detail(doc_id)
    except (KeyError, FileNotFoundError):
        raise HTTPException(404, "그런 서류가 없습니다")


@app.get("/api/safety/pdf/{doc_id}/{part}.pdf")
def safety_pdf(doc_id: str, part: str):            # plain def: the PDF is drawn in the thread pool
    try:
        out = safety.pdf(doc_id, part)
    except (KeyError, FileNotFoundError):
        raise HTTPException(404, "그런 서류가 없습니다")
    from urllib.parse import quote
    name = f"{doc_id}_" + {"original": "원본", "full": "허가서_추가검토서", "checklist": "위험체크리스트"}[part] + ".pdf"
    return Response(out, media_type="application/pdf", headers={"Content-Disposition": f"inline; filename*=UTF-8''{quote(name)}"})


@app.post("/api/qa")
def qa_add(text: str = Form(""), author: str = Form(""), context: str = Form("{}"), files: list[UploadFile] = File([])):
    # no count or size limit on files: they are streamed to disk (a plain def runs in the thread pool)
    if not text.strip() and not files:
        raise HTTPException(400, "파일이나 설명 중 하나는 넣어 주세요")
    if len(text) > qa.MAX_TEXT or len(context) > qa.MAX_CONTEXT:
        raise HTTPException(400, "내용이 너무 깁니다")
    try:
        if not isinstance(json.loads(context or "{}"), dict):
            raise ValueError
    except ValueError:
        raise HTTPException(400, "화면 정보(context)는 JSON 객체여야 합니다")
    got = [(Path(f.filename or "file").name[:200], f.content_type or "application/octet-stream", f.file) for f in files]
    try:
        return {"id": qa.add(text.strip(), author.strip()[:40], context, got)}
    except OSError as e:          # e.g. the server disk is full
        raise HTTPException(507, f"서버에 저장하지 못했습니다: {e.strerror or e}")


def _qa_auth(token):
    want = os.environ.get("QA_TOKEN", "")
    if not want or not hmac.compare_digest((token or "").encode("utf-8", "replace"), want.encode()):
        raise HTTPException(403, "QA 토큰이 필요합니다")


@app.get("/api/qa")
def qa_list(handled: bool | None = None, x_qa_token: str | None = Header(None)):
    _qa_auth(x_qa_token)
    return qa.listing(handled)


@app.get("/api/qa/{qid}/file/{n}")
def qa_file(qid: int, n: int, x_qa_token: str | None = Header(None)):
    _qa_auth(x_qa_token)
    row = qa.file(qid, n)
    if not row:
        raise HTTPException(404)
    name, mime, path = row
    return FileResponse(path, media_type=mime, filename=name)


# the team's QA board (QA 현황): newest first, handled or not, and whether the QA session is on it. No token: the text
# shown is the report's start only; the screen state and attachments stay behind the QA token (GET /api/qa).
@app.get("/api/qa/board")
def qa_board(show: str = "all"):
    return qa.board(show if show in ("all", "open", "done") else "all")


class QARunReq(BaseModel):
    by: str = ""


@app.post("/api/qa/run")
def qa_run_request(body: QARunReq):
    """「QA 시작하기」: asks the team's QA session (a Claude Code session on a team PC watching this) to work through
    the reports. One at a time; nothing runs on this server."""
    run, made = qa.request_run(body.by.strip())
    if run is None:
        raise HTTPException(409, "미처리 QA가 없습니다")
    return {"run": run, "made": made}


class QARunState(BaseModel):
    status: str
    note: str | None = None
    done: list[int] | None = None


@app.post("/api/qa/run/{rid}")
def qa_run_state(rid: int, body: QARunState, x_qa_token: str | None = Header(None)):
    _qa_auth(x_qa_token)
    try:
        ok = qa.set_run(rid, body.status, body.note, body.done)
    except ValueError:
        raise HTTPException(422, "status: requested · running · done · failed")
    if not ok:
        raise HTTPException(404)
    return {"ok": True}


class QAHandled(BaseModel):
    handled: bool = True
    note: str | None = None
    decision: str | None = None          # 수용 · 부분 수용 · 거절 · 보류


@app.post("/api/qa/{qid}/handled")
def qa_handled(qid: int, body: QAHandled, x_qa_token: str | None = Header(None)):
    _qa_auth(x_qa_token)
    try:
        ok = qa.set_handled(qid, body.handled, body.note, body.decision)
    except ValueError:
        raise HTTPException(422, "decision: " + " · ".join(qa.DECISIONS))
    if not ok:
        raise HTTPException(404)
    return {"ok": True}


class Chat(BaseModel):
    fields: dict
    messages: list = []      # [{"role": "user"|"assistant", "content": str}]


SYSTEM = """너는 조선소 안전팀의 '위험작업 허가서 사전검토' 담당 AI다. 상대는 신고서를 올린 작업반장이다.
할 일: 허가서를 먼저 검토하고, 빠지거나 의심스러운 부분을 반장에게 물어 확인한다. 특히 빈 칸, 작업 시간, 작업 공간(정확한 위치, 같은 시간·장소의 다른 작업)을 묻는다.
규칙:
- 사실은 아래 [허가서 내용]과 [규칙 검사 결과]에만 근거한다. 없는 값이나 규정을 지어내지 않는다.
- 한 번에 질문은 1~2개만, 가장 위험에 큰 영향을 주는 것부터 묻는다.
- 답을 들으면 짧게 정리하고 다음 확인할 것으로 넘어간다. 모든 확인이 끝나면 그렇다고 말한다.
- '※ 당일 작업시작 전 기입(사전 작성금지)' 칸(현장 안전조치 확인사항 등)은 지금 비어 있는 것이 정상이니 채우라고 하지 않는다.
- 이름·전화번호의 X는 개인정보 가림 처리이니 문제 삼지 않는다.
- 짧고 정중한 한국어 존댓말. 목록이 필요할 때만 '-' 를 쓴다. 마크다운 제목은 쓰지 않는다."""


def _doc_text(fields):
    pages = {}
    for f in fields.values():
        pages.setdefault(f["page"], []).append(f)
    lines = []
    for no, fs in sorted(pages.items()):
        lines.append(f"## {no}쪽 허가서")
        checks_on = [f["name"] for f in fs if f["type"] == "check" and f["value"]]
        for f in fs:
            if f["type"] in ("check", "image"):
                continue
            v = f["value"] if str(f["value"]).strip() else "(빈 칸)"
            lines.append(f"- {f['name']}: {v}")
        lines.append(f"- 체크된 항목: {', '.join(checks_on) or '없음'}")
        imgs = [f["name"] for f in fs if f["type"] == "image"]
        if imgs:
            lines.append(f"- 손글씨/서명 이미지 칸(글자로는 읽지 않음): {', '.join(imgs)}")
    return "\n".join(lines)


def _findings_text(findings):
    if not findings:
        return "(문제 없음)"
    kind = {"blank": "빈 칸", "format": "형식", "logic": "논리", "question": "확인 필요"}
    return "\n".join(f"- [{kind[x['kind']]}] {'공통' if x['page'] == 0 else str(x['page']) + '쪽'}: {x['msg']}" for x in findings)


@app.get("/api/llm")
async def llm_status():
    base = LLM_URL.split("/v1/")[0]
    try:
        async with httpx.AsyncClient(timeout=3) as cl:
            h = await cl.get(base + "/health")
            m = await cl.get(base + "/v1/models")
        return {"ok": h.status_code == 200, "model": LLM_MODEL,
                "status": h.json().get("status") if h.status_code == 200 else h.status_code,
                "served": [x.get("id") for x in m.json().get("data", [])] if m.status_code == 200 else []}
    except httpx.HTTPError as e:
        return {"ok": False, "model": LLM_MODEL, "status": f"연결 안 됨: {e.__class__.__name__}"}


LEGACY_CHAT = os.environ.get("CROSCAN_LEGACY_CHAT") == "1"


@app.post("/api/chat")
async def chat(body: Chat):
    # the old free chat (design §1.4: every model call is a typed, budgeted job): off unless asked for by its setting
    if not LEGACY_CHAT:
        raise HTTPException(410, "자유 대화 기능은 꺼져 있습니다")
    findings = review.check(body.fields)
    system = f"{SYSTEM}\n\n[허가서 내용]\n{_doc_text(body.fields)}\n\n[규칙 검사 결과]\n{_findings_text(findings)}"
    msgs = [{"role": "system", "content": system}]
    if not body.messages:   # the AI opens the conversation
        msgs.append({"role": "user", "content": "(검토를 시작하세요. 먼저 한두 문장으로 검토 요약을 하고, 가장 중요한 확인 질문부터 하세요.)"})
    msgs += [m for m in body.messages if m.get("role") in ("user", "assistant")]
    payload = {"model": LLM_MODEL, "messages": msgs, "stream": True, "max_tokens": LLM_MAX_TOKENS, **LLM_SAMPLING}

    async def gen():
        buf, in_think = "", False
        try:
            async with httpx.AsyncClient(timeout=None) as cl:
                async with cl.stream("POST", LLM_URL, json=payload) as r:
                    if r.status_code >= 400:
                        yield f"(모델 서버 오류 {r.status_code}: {(await r.aread()).decode('utf-8', 'replace')[:200]})"
                        return
                    async for line in r.aiter_lines():       # server-sent events: "data: {...}" … "data: [DONE]"
                        if not line.startswith("data:") or line[5:].strip() == "[DONE]":
                            continue
                        delta = (json.loads(line[5:]).get("choices") or [{}])[0].get("delta") or {}
                        buf += delta.get("content") or ""     # the thinking comes apart, in "reasoning_content"
                        # drop any <think>...</think> block the model still emits
                        out = ""
                        while buf:
                            if in_think:
                                k = buf.find("</think>")
                                if k < 0:
                                    buf = buf[-8:]; break
                                buf, in_think = buf[k + 8:], False
                            else:
                                k = buf.find("<think>")
                                if k < 0:
                                    keep = 7 if "<" in buf[-7:] else 0
                                    out += buf[:len(buf) - keep]; buf = buf[len(buf) - keep:]; break
                                out += buf[:k]; buf, in_think = buf[k + 7:], True
                        if out:
                            yield out
            if buf and not in_think:
                yield buf
        except httpx.HTTPError as e:
            yield f"\n(모델 서버에 연결하지 못했습니다: {e})"
    return StreamingResponse(gen(), media_type="text/plain; charset=utf-8")


# 근거 지도·검색 (design §3.4·§3.4.1): what each checklist item and pair rule stands on, and the passages behind it
@app.get("/api/knowledge/map")
def knowledge_map():
    return evidencemap.build()


@app.get("/api/knowledge/search")
def knowledge_search(q: str, k: int = 6, authority: str = ""):
    return {"query": q, "hits": retrieval.search(q[:200], k=max(1, min(12, k)), authority=[a for a in authority.split(",") if a] or None)}


@app.on_event("startup")
def _recover():
    """design §2.1: the jobs a restart cut off are 「interrupted」 (not done) and their model calls given back"""
    n = store.recover()
    if n:
        print(f"recover: {n} unfinished jobs", flush=True)


app.mount("/static", StaticFiles(directory=ROOT / "web"), name="static")


@app.get("/")
def index():
    return FileResponse(ROOT / "web" / "index.html")
