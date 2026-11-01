"""The review session kept by the server (design §2): the foreman's own answers, and what was read from them for other
questions (proposals, by the rules or the AI) until the foreman confirms them. Only confirmed proposals are answers.

A session is a random id. The answers change only through the review itself (/api/augment, /api/understand): the
client sends its typed answers with the revision it last saw; other answers on an older revision are refused (409),
and a change without a revision is refused (428), so a late request or another tab never writes over newer answers.
The checklist, the preview and the submission only read the session. Of a typed answer only its question, choice,
value and the time it was given are kept; anything else the client says (read, by, ai, ids) is not taken.

Keys do not depend on the 승인번호: a question is its item on its page (and the other permit's page for a pair
question). Answer ids are rebuilt with the numbers of now. The session keeps the form it last saw (a hash per page):
a proposal is tied to the answer it was read from and to that form; when either changes, it goes (invalidated), and
the same words later give a new proposal (a new id) to confirm again.

A checking answer (A1·A2·A3·U1 asked about an answer, C5 about an answer against a free one) is tied to what it checked
(and C5 to the free answers): when that changes, the checking answer stops counting for good — the same words coming
back do not revive it; only a new answer (given again, at another time) does. What a checking answer itself was
asked about goes with it. The answers that stopped counting are reported, for the client to drop them.

One question has at most one adopted reading; a typed answer to it wins. A refused or withdrawn proposal is not
offered again for the same words. SQLite in the data volume (qa.DATA / review.sqlite3), WAL; every check and change is
in one transaction; nothing is held while the model runs. Sessions not used for 30 days are removed.
"""
import contextlib
import contextvars
import hashlib
import json
import re
import secrets
import sqlite3
import threading
import time

from . import qa

DB = qa.DATA / "review.sqlite3"
KEEP_DAYS = 30
CHECKING = ("A1.", "A2.", "A3.", "U1.", "C5.", "C6.")
STALE = "!stale"
_LOCK = threading.Lock()
_READY = False
_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, created REAL, used REAL, revision INTEGER DEFAULT 0, ctx TEXT,
    llm_calls INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS typed (session_id TEXT, skey TEXT, qid TEXT, hash TEXT, base_hash TEXT, data TEXT, PRIMARY KEY (session_id, skey));
CREATE TABLE IF NOT EXISTS proposals (id TEXT PRIMARY KEY, session_id TEXT, skey TEXT, origin TEXT, src_skey TEXT, src_hash TEXT,
    ctx TEXT, payload TEXT, status TEXT, created REAL, decided REAL);
CREATE INDEX IF NOT EXISTS proposals_session ON proposals (session_id, status);
CREATE TABLE IF NOT EXISTS actions (session_id TEXT, action_id TEXT, kind TEXT, request TEXT, result TEXT, created REAL,
    PRIMARY KEY (session_id, action_id));
CREATE TABLE IF NOT EXISTS asks (session_id TEXT, key TEXT, kind TEXT, base TEXT, created REAL, PRIMARY KEY (session_id, key));
CREATE TABLE IF NOT EXISTS needs (session_id TEXT, n INTEGER, mkey TEXT, payload TEXT, created REAL, PRIMARY KEY (session_id, n));
CREATE TABLE IF NOT EXISTS jobs (session_id TEXT, kind TEXT, status TEXT, started REAL, finished REAL, result TEXT,
    PRIMARY KEY (session_id, kind));
CREATE TABLE IF NOT EXISTS revlog (session_id TEXT, rev INTEGER, kind TEXT, PRIMARY KEY (session_id, rev));
CREATE TABLE IF NOT EXISTS events (session_id TEXT, n INTEGER, kind TEXT, rev INTEGER, payload TEXT, actor TEXT, action_id TEXT,
    created REAL, PRIMARY KEY (session_id, n));
CREATE TABLE IF NOT EXISTS confirmations (session_id TEXT, action_id TEXT, actor TEXT, role TEXT, digest TEXT, targets TEXT,
    scope TEXT, created REAL, PRIMARY KEY (session_id, action_id));
"""
_COLUMNS = (("sessions", "ctx", "TEXT"), ("typed", "base_hash", "TEXT"), ("proposals", "ctx", "TEXT"), ("sessions", "llm_calls", "INTEGER DEFAULT 0"),
            ("sessions", "warm_calls", "INTEGER DEFAULT 0"), ("sessions", "owner", "TEXT"), ("jobs", "llm", "INTEGER DEFAULT 0"))
# who is asking, set per request by the app under the company gateway (CROSCAN_AUTH=proxy): a session is opened
# only by its own foreman or a 안전관리자; None (demo) checks nothing
OWNER = contextvars.ContextVar("owner", default=None)
MANAGER = contextvars.ContextVar("manager", default=False)
# the job a model call is made for (analyze, turn:…): its calls are counted on the job, so that a restart can give
# back what an unfinished job charged (design §2.1)
JOB = contextvars.ContextVar("job", default=None)
NEG_CHOICES = ("no", "none", "na")
EVENT_KINDS = ("correction", "withdraw", "note")          # the ones a client may record; the others the server writes
Q_KEYS = ("qid", "item", "page", "permit_no", "who", "keys", "signal", "text", "choices", "tier", "other", "original", "fp", "fp_keys")


class StoreError(Exception):
    def __init__(self, status, code, detail="", **extra):
        super().__init__(f"{code}: {detail}")
        self.status, self.code, self.detail, self.extra = status, code, detail, extra


def _migrate(c):
    """an older database: the columns added since, readings without a form context invalidated, then the index"""
    for table, col, typ in _COLUMNS:
        if col not in {r[1] for r in c.execute(f"PRAGMA table_info({table})")}:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
    c.execute("UPDATE proposals SET status='invalidated' WHERE ctx IS NULL AND status IN ('proposed','adopted')")
    # two adopted readings of one question (before the index): the later one goes
    c.execute("""UPDATE proposals SET status='invalidated' WHERE status='adopted' AND EXISTS (SELECT 1 FROM proposals p2
                 WHERE p2.session_id=proposals.session_id AND p2.skey=proposals.skey AND p2.status='adopted' AND p2.created < proposals.created)""")
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS one_adopted ON proposals (session_id, skey) WHERE status = 'adopted'")


@contextlib.contextmanager
def _db():
    """one connection per call, closed after; a transaction left open by an error is rolled back"""
    global _READY
    qa.DATA.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB, timeout=5, isolation_level=None)
    c.row_factory = sqlite3.Row
    try:
        c.execute("PRAGMA busy_timeout=5000")
        if not _READY:
            c.execute("PRAGMA journal_mode=WAL")
            c.executescript(_SCHEMA)
            _migrate(c)
            _READY = True
        yield c
    finally:
        if c.in_transaction:
            c.rollback()
        c.close()


def _hash(*parts):
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


def said_hash(a):
    """what was said for a question: its choice and value; for a checking answer also when it was given (asked again
    after its base changed, the same words are a new answer)"""
    at = a.get("at") if a["qid"].startswith(CHECKING) else None
    return _hash(a.get("choice") or "", (a.get("value") or "").strip(), at)


def skey(qid, q=None):
    """a question without the 승인번호: item @ page (> other page). A free answer keeps its own number."""
    if qid.startswith("FREE:"):
        return qid
    q = q or {}
    page = q.get("page")
    if page is None:
        return qid
    return f"{qid.split(':')[0]}@{page}" + (f">{q['other']}" if q.get("other") is not None else "")


def page_contexts(fields):
    """a hash of each page's form values (the 승인번호 aside): what a reading of that page was made against"""
    pages = {}
    for f in (fields or {}).values():
        if isinstance(f, dict) and f.get("key") != "permit_no":
            pages.setdefault(str(f.get("page")), []).append((str(f.get("key")), str(f.get("value") or "")))
    return {pg: _hash(sorted(v)) for pg, v in pages.items()}


def _pctx(ctx, page, other=None):
    """the form context of a question: its page, and the other permit's page for a pair question"""
    return _hash((ctx or {}).get(str(page)), (ctx or {}).get(str(other)) if other is not None else None)


def permit_numbers(fields):
    out = {}
    for f in (fields or {}).values():
        if isinstance(f, dict) and f.get("key") == "permit_no":
            out[f.get("page")] = (str(f.get("value") or "").strip().upper()) or f"#{f.get('page')}"
    return out


def _qid_now(item, page, other, nums):
    if not item or page is None or not nums:
        return None
    pno = nums.get(page) or f"#{page}"
    return f"{item}:{pno}" + (f">{nums.get(other) or f'#{other}'}" if other is not None else "")


def _renum(a, nums):
    """a typed answer with the 승인번호 of now"""
    q = dict(a.get("q") or {})
    qid = _qid_now(a["qid"].split(":")[0], q.get("page"), q.get("other"), nums) if not a["qid"].startswith("FREE:") else None
    if qid:
        a = {**a, "qid": qid}
        q.update({"qid": qid, "permit_no": qid.split(":")[1].split(">")[0]})
        a["q"] = q
    return a


def _base_keys(sk, a):
    """what a checking answer depends on, as keys: A1.T1@3 → [T1@3] (A1.T1.2: the second unclear part of T1, so
    T1 too), A3.F2 → [FREE:2], C5.X → [X, every free answer], C5.concurrent → [every free answer]"""
    item, _, rest = sk.partition("@")
    page = f"@{rest}" if rest else ""
    base = item.split(".", 1)[1]
    if item.startswith("C5."):
        return ["FREE:*"] + ([] if base == "concurrent" else [f"{base}{page}"])
    if re.fullmatch(r"F\d+", base):
        return [f"FREE:{base[1:]}"]
    keys = [f"{base}{page}"]
    if re.search(r"\.\d+$", base):                     # an unclear part numbered .2 …: its source without the number
        keys.append(re.sub(r"\.\d+$", "", base) + page)
    return keys


def _deps_hash(sk, a, typed_h, adopted_h, ctx):
    """the hash of what a checking answer depends on, now; None when that is not there"""
    keys = _base_keys(sk, a)
    vals = []
    if "FREE:*" in keys:
        vals.append(sorted((x, h) for x, h in typed_h.items() if x.startswith("FREE:")))
    own = [k for k in keys if k != "FREE:*"]
    if own:
        hit = next((k for k in own if k in typed_h or k in adopted_h), None)
        if hit is None:
            return None
        vals.append(typed_h.get(hit) or adopted_h.get(hit))
    if sk.startswith("C5.concurrent"):                   # whether anything else is there: the form says it too
        vals.append((ctx or {}).get(sk.partition("@")[2].split(">")[0]))
    return _hash(vals)


def _session(c, sid):
    r = c.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
    if not r:
        raise StoreError(404, "session_missing", "검토 세션이 없습니다")
    who = OWNER.get()
    if who is not None and not MANAGER.get() and r["owner"] not in (None, who):
        raise StoreError(404, "session_missing", "검토 세션이 없습니다")          # another foreman's review: not there
    return r


def owner_of(sid):
    with _db() as c:
        r = c.execute("SELECT owner FROM sessions WHERE id=?", (sid,)).fetchone()
        return r["owner"] if r else None


def create():
    sid = secrets.token_urlsafe(18)
    with _LOCK, _db() as c:
        now = time.time()
        c.execute("BEGIN IMMEDIATE")
        c.execute("DELETE FROM sessions WHERE used < ?", (now - KEEP_DAYS * 86400,))
        for t in ("typed", "proposals", "actions", "asks", "needs", "jobs", "revlog", "events", "confirmations"):
            c.execute(f"DELETE FROM {t} WHERE session_id NOT IN (SELECT id FROM sessions)")
        c.execute("INSERT INTO sessions (id, created, used, revision, ctx, owner) VALUES (?,?,?,0,NULL,?)", (sid, now, now, OWNER.get()))
        c.execute("COMMIT")
    return sid


def exists(sid):
    with _db() as c:
        return bool(c.execute("SELECT 1 FROM sessions WHERE id=?", (sid,)).fetchone())


def clean(a):
    """a typed answer as kept: question, choice, value, when it was given, and the question as asked (known parts)"""
    q = a.get("q") if isinstance(a.get("q"), dict) else {}
    out = {"qid": a["qid"], "choice": a.get("choice") or "", "value": a.get("value") or "", "q": {k: q[k] for k in Q_KEYS if k in q}}
    if a.get("at") is not None:
        out["at"] = a["at"]
    return out


def typed_of(answers):
    """the foreman's own answers in what the client sent, cleaned: anything read from another answer is left out"""
    return [clean(a) for a in answers if not a.get("by") and not a.get("ai") and not a.get("pid")]


def _adopted_hashes(c, sid):
    return {r["skey"]: _hash(json.loads(r["payload"]).get("choice"), json.loads(r["payload"]).get("value"))
            for r in c.execute("SELECT skey, payload FROM proposals WHERE session_id=? AND status='adopted'", (sid,))}


def _sync(c, sid, answers, fields, expected):
    """inside a transaction: keep the typed answers and the form, invalidate what no longer holds -> revision"""
    ses = _session(c, sid)
    typed = {skey(a["qid"], a["q"]): a for a in typed_of(answers)}
    old = {r["skey"]: r for r in c.execute("SELECT skey, hash, base_hash, data FROM typed WHERE session_id=?", (sid,))}
    new = {k: said_hash(a) for k, a in typed.items()}
    ctx = page_contexts(fields)
    changed = {k: r["hash"] for k, r in old.items()} != new or json.loads(ses["ctx"] or "null") != ctx
    if changed and expected is None:
        raise StoreError(428, "revision_required", "개정 번호가 없습니다")
    if changed and expected != ses["revision"] and not _only_readings(c, sid, expected, ses["revision"]):
        raise StoreError(409, "stale_revision", "다른 화면에서 바뀐 내용이 있습니다", revision=ses["revision"])
    now = time.time()
    moved = [{"skey": k, "qid": json.loads(r["data"] or "{}").get("qid") or k, "before": _said(json.loads(r["data"] or "{}")),
              "after": _said(typed[k]) if k in typed else None} for k, r in old.items() if new.get(k) != r["hash"]]
    form_moved = json.loads(ses["ctx"] or "null") not in (None, ctx)
    lost = []
    # the readings that no longer hold: their answer changed or went, their form changed, or the question now has
    # a typed answer
    for r in c.execute("SELECT id, skey, src_skey, src_hash, ctx, payload, status FROM proposals WHERE session_id=? AND status IN ('proposed','adopted')", (sid,)).fetchall():
        p = json.loads(r["payload"])
        if new.get(r["src_skey"]) != r["src_hash"] or r["skey"] in new or r["ctx"] != _pctx(ctx, p.get("page"), p.get("other")):
            c.execute("UPDATE proposals SET status='invalidated', decided=? WHERE id=?", (now, r["id"]))
            changed = True
            if not (r["skey"] in new and r["skey"] not in old):           # answered by typing just now: not a loss
                lost.append({"qid": p.get("qid"), "slot": p.get("slot") or ((p.get("q") or {}).get("text") or p.get("item") or "")[:24], "was": r["status"],
                             "why": "원래 답이 바뀜" if new.get(r["src_skey"]) != r["src_hash"] else "양식이 바뀜" if r["skey"] not in new else "직접 답함"})
    adopted = _adopted_hashes(c, sid)
    rows = []
    for k, a in typed.items():
        base = None
        if a["qid"].startswith(CHECKING):
            dep = _deps_hash(k, a, new, adopted, ctx)
            prev = old.get(k)
            if prev is not None and prev["hash"] == new[k]:
                base = prev["base_hash"] if prev["base_hash"] in (STALE, dep) else STALE      # changed once: for good
            else:
                base = dep or STALE                     # a new answer counts against what is there now
            if prev is not None and base != prev["base_hash"]:
                changed = True
                if base == STALE:
                    lost.append({"qid": a["qid"], "slot": a["qid"].split(":")[0], "was": "check", "why": "확인한 답이 바뀜"})
        rows.append((sid, k, a["qid"], new[k], base, json.dumps(a, ensure_ascii=False)))
    c.execute("DELETE FROM typed WHERE session_id=?", (sid,))
    c.executemany("INSERT INTO typed (session_id, skey, qid, hash, base_hash, data) VALUES (?,?,?,?,?,?)", rows)
    c.execute("UPDATE sessions SET used=?, ctx=?, revision=revision+? WHERE id=?", (now, json.dumps(ctx), 1 if changed else 0, sid))
    rev = c.execute("SELECT revision FROM sessions WHERE id=?", (sid,)).fetchone()["revision"]
    if moved:
        _event(c, sid, "answers", rev, {"changes": moved})
    if lost:                                       # design §19.2 개정 만료: one notice for what one change expired
        _event(c, sid, "expiry", rev, {"changes": moved, "form": form_moved, "lost": lost})
    if moved and closed(c, sid):                   # design §3.6: after the review closed, a change is a 수정 이벤트
        _event(c, sid, "after_close", rev, {"changes": moved})
    return rev


def _said(a):
    """an answer as the foreman would read it: its choice's label and its value"""
    if not a:
        return None
    ch = next((x.get("label") for x in (a.get("q") or {}).get("choices", []) if x.get("id") == a.get("choice")), a.get("choice") or "")
    v = (a.get("value") or "").strip()
    return f"{ch}: {v}" if ch and v and v not in str(ch) else (v or str(ch))


def _event(c, sid, kind, rev, payload, action_id=None):
    n = c.execute("SELECT COALESCE(MAX(n),0)+1 FROM events WHERE session_id=?", (sid,)).fetchone()[0]
    c.execute("INSERT INTO events (session_id, n, kind, rev, payload, actor, action_id, created) VALUES (?,?,?,?,?,?,?,?)",
              (sid, n, kind, rev, json.dumps(payload, ensure_ascii=False), OWNER.get(), action_id, time.time()))
    return n


def _only_readings(c, sid, expected, rev):
    """every revision after expected came from a reading being stored (propose), nothing else"""
    if not isinstance(expected, int) or expected >= rev:
        return False
    n = c.execute("SELECT COUNT(*) FROM revlog WHERE session_id=? AND rev>? AND rev<=? AND kind='propose'", (sid, expected, rev)).fetchone()[0]
    return n == rev - expected


def _answer(r, nums=None):
    p = json.loads(r["payload"])
    q = dict(p.get("q") or {})
    qid = _qid_now(p.get("item"), p.get("page"), p.get("other"), nums) or p.get("qid")
    if q and qid and ":" in qid:
        q.update({"qid": qid, "permit_no": qid.split(":")[1].split(">")[0]})
    by = p.get("by")
    if nums and by and not by.startswith("FREE:") and p.get("by_page") is not None:
        by = _qid_now(by.split(":")[0], p.get("by_page"), p.get("by_other"), nums) or by
    return {"qid": qid, "choice": p.get("choice"), "value": p.get("value") or "", "q": q, "by": by,
            "quote": p.get("quote"), "ai": r["origin"] == "ai", "who": p.get("who"), "when": p.get("when"), "pid": r["id"],
            "origin": r["origin"], "slot": p.get("slot"), "label": p.get("label"), "verbatim": p.get("verbatim"), "status": r["status"],
            **({"weak": p["weak"]} if p.get("weak") else {}),
            **{k: p.get(k) for k in ("polarity", "modality", "phase", "version")}}


def _project(c, ses, fields):
    """-> (answers to calculate with, the qids of checking answers that stopped counting). The typed answers whose
    checks still hold (and not those asked about one that stopped), the adopted readings whose form still holds —
    the session's form, and the form given (when given: a form edited since the last review step counts too); all
    with the 승인번호 of now."""
    sid, nums = ses["id"], permit_numbers(fields)
    ctxs = [json.loads(ses["ctx"] or "{}")] + ([page_contexts(fields)] if fields else [])
    typed = [(r["skey"], r["base_hash"], json.loads(r["data"])) for r in c.execute("SELECT * FROM typed WHERE session_id=? ORDER BY rowid", (sid,))]   # as given
    bad = {k for k, b, a in typed if a["qid"].startswith(CHECKING) and b == STALE}
    for _ in range(8):                                   # a check of a check goes with it
        more = {k for k, _, a in typed if a["qid"].startswith(CHECKING) and k not in bad and any(x in bad for x in _base_keys(k, a))}
        if not more:
            break
        bad |= more
    out = [_renum(a, nums) for k, _, a in typed if k not in bad]
    dropped = [_renum(a, nums)["qid"] for k, _, a in typed if k in bad]
    have = {k for k, _, _ in typed if k not in bad}
    for r in c.execute("SELECT * FROM proposals WHERE session_id=? AND status='adopted' ORDER BY created", (sid,)):
        p = json.loads(r["payload"])
        if r["skey"] not in have and all(r["ctx"] == _pctx(x, p.get("page"), p.get("other")) for x in ctxs):
            out.append(_answer(r, nums))
    return out, dropped


def answers_for(sid, answers, fields, expected=None):
    """the review's own request: sync and project in one transaction -> (answers, revision, dropped)"""
    with _LOCK, _db() as c:
        c.execute("BEGIN IMMEDIATE")
        rev = _sync(c, sid, answers, fields, expected)
        out, dropped = _project(c, _session(c, sid), fields)
        c.execute("COMMIT")
    return out, rev, dropped


def current(sid, fields, expected):
    """for the checklist, the preview and the submission: the session as it is, nothing written. Made from the
    revision the client last saw: one that is behind is refused (409), none at all too (428)."""
    if expected is None:
        raise StoreError(428, "revision_required", "개정 번호가 없습니다")
    with _db() as c:
        c.execute("BEGIN")
        ses = _session(c, sid)
        if expected != ses["revision"]:
            raise StoreError(409, "stale_revision", "다른 화면에서 바뀐 내용이 있습니다", revision=ses["revision"])
        out, dropped = _project(c, ses, fields)
        c.execute("COMMIT")
    return out, ses["revision"], dropped


def form(sid):
    """the form the session last saw (a hash per page), or None"""
    with _db() as c:
        return json.loads(_session(c, sid)["ctx"] or "null")


def revision(sid):
    with _db() as c:
        return _session(c, sid)["revision"]


def state(sid, fields=None):
    """for a reload: the typed answers that count, the adopted readings, the waiting proposals, the revision"""
    with _db() as c:
        c.execute("BEGIN")
        ses = _session(c, sid)
        nums = permit_numbers(fields) if fields else {}
        out, dropped = _project(c, ses, fields or {})
        res = {"revision": ses["revision"], "typed": [a for a in out if not a.get("pid")], "dropped": dropped,
               "adopted": [a for a in out if a.get("pid")],
               "proposals": [_answer(r, nums) for r in c.execute("SELECT * FROM proposals WHERE session_id=? AND status='proposed' ORDER BY created", (sid,))]}
        c.execute("COMMIT")
    return res


def form_of(sid):
    """the form the session last saw (its ctx), to tell later whether only answers moved on"""
    with _db() as c:
        r = c.execute("SELECT ctx FROM sessions WHERE id=?", (sid,)).fetchone()
        return r["ctx"] if r else None


def propose(sid, origin, src, items, basis=None, form=None, src_at=None):
    """store proposals read from the typed answer src (by the rules or the AI) against the session's form ->
    (the stored ones, with ids; the revision after). basis: the revision the reading started from (a reading that took long is refused
    when the review moved on — unless form, the form as it was then, is still the session's: then only other
    answers came meanwhile, and the source answer itself is checked below). The same reading of the same words is not stored twice; one refused or withdrawn is
    not offered again; one that went invalid comes back as a new proposal; a question already answered or with an
    adopted reading gets none."""
    src = clean(src)
    sk, h, out = skey(src["qid"], src["q"]), said_hash(src), []
    with _LOCK, _db() as c:
        c.execute("BEGIN IMMEDIATE")
        ses = _session(c, sid)
        if basis is not None and basis != ses["revision"] and (form is None or form != ses["ctx"]):
            raise StoreError(409, "stale_revision", "읽는 동안 답이 바뀌었습니다", revision=ses["revision"])
        cur = c.execute("SELECT hash, data FROM typed WHERE session_id=? AND skey=?", (sid, sk)).fetchone()
        if not cur or cur["hash"] != h:
            raise StoreError(409, "stale_answer", "원래 답이 바뀌었습니다")
        if src_at is not None and json.loads(cur["data"] or "{}").get("at") != src_at:
            raise StoreError(409, "stale_answer", "원래 답이 바뀌었다가 다시 같은 말이 됐습니다")
        ctx = json.loads(ses["ctx"] or "{}")
        now, mutated = time.time(), False
        typed = {r["skey"] for r in c.execute("SELECT skey FROM typed WHERE session_id=?", (sid,))}
        taken = {r["skey"] for r in c.execute("SELECT skey FROM proposals WHERE session_id=? AND status='adopted'", (sid,))}
        for it in items:
            q = it.get("q") or {}
            tk = skey(it["qid"], q)
            if tk in typed or tk in taken:
                continue
            payload = {k: it.get(k) for k in ("choice", "value", "quote", "slot", "label", "who", "when", "verbatim", "weak") if k in it}
            payload.update(_fact_of(it))
            payload["version"] = 1 + c.execute("SELECT COUNT(*) FROM proposals WHERE session_id=? AND skey=?", (sid, tk)).fetchone()[0]
            payload.update({"q": {k: q[k] for k in Q_KEYS if k in q}, "qid": it["qid"], "item": it["qid"].split(":")[0],
                            "page": q.get("page"), "other": q.get("other"), "by": src["qid"],
                            "by_page": src["q"].get("page"), "by_other": src["q"].get("other")})
            pc = _pctx(ctx, q.get("page"), q.get("other"))
            same = [r for r in c.execute("SELECT id, status, payload FROM proposals WHERE session_id=? AND skey=? AND src_skey=? AND src_hash=? AND origin=?",
                                         (sid, tk, sk, h, origin))
                    if json.loads(r["payload"]).get("value") == payload.get("value") and json.loads(r["payload"]).get("choice") == payload.get("choice")]
            if any(r["status"] in ("rejected", "withdrawn") for r in same):
                continue                                       # refused or withdrawn: not again for the same words
            live = next((r for r in same if r["status"] == "proposed"), None)
            if live:
                out.append({**it, "pid": live["id"], "status": "proposed", "origin": origin})
                continue
            pid = secrets.token_urlsafe(9)                     # new, or the same words after it went invalid: a new id
            c.execute("INSERT INTO proposals (id, session_id, skey, origin, src_skey, src_hash, ctx, payload, status, created) VALUES (?,?,?,?,?,?,?,?,?,?)",
                      (pid, sid, tk, origin, sk, h, pc, json.dumps(payload, ensure_ascii=False), "proposed", now))
            out.append({**it, "pid": pid, "status": "proposed", "origin": origin})
            mutated = True
        if mutated:
            c.execute("UPDATE sessions SET used=?, revision=revision+1 WHERE id=?", (now, sid))
            nrev = c.execute("SELECT revision FROM sessions WHERE id=?", (sid,)).fetchone()["revision"]
            c.execute("INSERT OR REPLACE INTO revlog (session_id, rev, kind) VALUES (?,?,?)", (sid, nrev, "propose"))
        rev = ses["revision"] + (1 if mutated else 0)
        c.execute("COMMIT")
    return out, rev


def _fact_of(it):
    """design §2.1: what a reading says of the fact — a no (polarity), how sure it was said (modality: a hedged or
    conditional sentence is not proposed at all, so a proposal is asserted unless told), planned or said done (phase)"""
    ch = it.get("choice") or ""
    return {"polarity": "negative" if ch in NEG_CHOICES else "positive",
            "modality": it.get("modality") or ("unknown" if ch == "unknown" else "asserted"),
            "phase": {"plan": "planned", "done": "reported_done", "ongoing": "ongoing"}.get(it.get("when"), "unspecified")}


def pending(sid, fields=None):
    with _db() as c:
        nums = permit_numbers(fields) if fields else {}
        return [_answer(r, nums) for r in c.execute("SELECT * FROM proposals WHERE session_id=? AND status='proposed' ORDER BY created", (sid,))]


def adopted(sid, fields=None):
    with _db() as c:
        nums = permit_numbers(fields) if fields else {}
        return [_answer(r, nums) for r in c.execute("SELECT * FROM proposals WHERE session_id=? AND status='adopted' ORDER BY created", (sid,))]


def digest(rows):
    """what a card showed of proposals: their ids, choices and values (FNV-1a 32 over UTF-8 — the same in the browser,
    which has no crypto on plain http) -> 8 hex digits"""
    s = "\x1e".join(f"{r['pid']}\x1f{r.get('choice') or ''}\x1f{r.get('value') or ''}" for r in sorted(rows, key=lambda r: r["pid"]))
    h = 0x811c9dc5
    for b in s.encode("utf-8"):
        h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
    return f"{h:08x}"


def decide(sid, action_id, adopt=(), reject=(), withdraw=(), fields=None, displayed=None, expected=None, role=None):
    """the foreman's decision on proposals shown to him: all or nothing, against the session's own form; the same
    action twice gives the first result. displayed: the digest of what the card showed (design §2.3): a card whose
    proposals changed since is refused (409 stale_display, with what is there now). expected: the revision the card
    was shown at — refused when the review moved on by anything but readings stored meanwhile."""
    req = json.dumps([sorted(adopt), sorted(reject), sorted(withdraw)])
    with _LOCK, _db() as c:
        c.execute("BEGIN IMMEDIATE")
        ses = _session(c, sid)
        done = c.execute("SELECT request, result FROM actions WHERE session_id=? AND action_id=?", (sid, action_id)).fetchone()
        if done:
            c.execute("COMMIT")
            if done["request"] != req:
                raise StoreError(409, "action_conflict", "같은 동작 번호에 다른 내용")
            return json.loads(done["result"])
        rows = {r["id"]: r for r in c.execute("SELECT * FROM proposals WHERE session_id=?", (sid,))}
        if expected is not None and expected != ses["revision"] and not _only_readings(c, sid, expected, ses["revision"]):
            since = [json.loads(r["payload"]) for r in c.execute("SELECT payload FROM events WHERE session_id=? AND kind='answers' AND rev>? ORDER BY n",
                                                                 (sid, expected))]
            raise StoreError(409, "stale_revision", "카드를 보인 뒤 답이 바뀌었습니다", revision=ses["revision"],
                             changes=[x for e in since for x in e.get("changes", [])])
        if displayed is not None:
            shown = [{"pid": p, **json.loads(rows[p]["payload"])} for p in list(adopt) + list(reject) if p in rows]
            if len(shown) != len(list(adopt) + list(reject)) or digest(shown) != displayed:
                raise StoreError(409, "stale_display", "카드에 보인 내용과 지금 내용이 다릅니다",
                                 changes=[{"pid": x["pid"], "slot": x.get("slot"), "choice": x.get("choice"), "value": x.get("value"),
                                           "status": rows[x["pid"]]["status"]} for x in shown])
        typed = {r["skey"]: r["hash"] for r in c.execute("SELECT skey, hash FROM typed WHERE session_id=?", (sid,))}
        ctx = json.loads(ses["ctx"] or "{}")
        for pid in list(adopt) + list(reject):
            r = rows.get(pid)
            p = json.loads(r["payload"]) if r else {}
            if (not r or r["status"] != "proposed" or typed.get(r["src_skey"]) != r["src_hash"] or r["skey"] in typed
                    or r["ctx"] != _pctx(ctx, p.get("page"), p.get("other"))):
                raise StoreError(409, "stale_proposal", "바뀐 내용이 있어 다시 확인해야 합니다")
        for pid in withdraw:
            r = rows.get(pid)
            if not r or r["status"] != "adopted":
                raise StoreError(409, "stale_proposal", "이미 바뀐 답입니다")
        keys = [rows[p]["skey"] for p in adopt]
        busy = {r["skey"] for r in rows.values() if r["status"] == "adopted" and r["id"] not in withdraw}
        if len(set(keys)) != len(keys) or busy & set(keys):
            raise StoreError(409, "same_question", "같은 질문에 이미 확인한 답이 있습니다")
        now = time.time()
        for pid in withdraw:
            c.execute("UPDATE proposals SET status='withdrawn', decided=? WHERE id=?", (now, pid))
        for pid in adopt:
            c.execute("UPDATE proposals SET status='adopted', decided=? WHERE id=?", (now, pid))
            # the other proposals for the same question (another reading) give way
            c.execute("UPDATE proposals SET status='rejected', decided=? WHERE session_id=? AND skey=? AND status='proposed' AND id<>?",
                      (now, sid, rows[pid]["skey"], pid))
        for pid in reject:
            c.execute("UPDATE proposals SET status='rejected', decided=? WHERE id=?", (now, pid))
        c.execute("UPDATE sessions SET used=?, revision=revision+1 WHERE id=?", (now, sid))
        rev = c.execute("SELECT revision FROM sessions WHERE id=?", (sid,)).fetchone()["revision"]
        nums = permit_numbers(fields) if fields else {}
        result = {"revision": rev, "adopted": [_answer(r, nums) for r in c.execute("SELECT * FROM proposals WHERE session_id=? AND status='adopted' ORDER BY created", (sid,))]}
        c.execute("INSERT INTO actions (session_id, action_id, kind, request, result, created) VALUES (?,?,?,?,?,?)",
                  (sid, action_id, "decide", req, json.dumps(result, ensure_ascii=False), now))
        # design §2.1 Confirmation: who, in what role, what was shown, which targets in which version
        targets = [{"pid": p, "skey": rows[p]["skey"], "version": json.loads(rows[p]["payload"]).get("version")} for p in list(adopt) + list(reject) + list(withdraw)]
        c.execute("INSERT OR REPLACE INTO confirmations (session_id, action_id, actor, role, digest, targets, scope, created) VALUES (?,?,?,?,?,?,?,?)",
                  (sid, action_id, OWNER.get(), role or ("manager" if MANAGER.get() else "foreman"), displayed, json.dumps(targets),
                   json.dumps({"adopt": list(adopt), "reject": list(reject), "withdraw": list(withdraw)}), now))
        c.execute("COMMIT")
    return result


# the budgets of a review (design §3.5·§3.7) -----------------------------------------------------------------------
# One ask is one request for the foreman's answer as it is shown: a question, a clarification (A1·A2·A3·U1·C5, and a
# question asked again because its answer could not be read), one card of readings to confirm, the closing request for
# anything more. Shown again (a reload, another tab, a re-send, the same question asked again after the foreman took
# his answer back) it is the same ask, not counted again. At most ASKS in a review, of them at most CLARIFY
# clarifications and one per need, and the closing request once. The model is called at most LLM_CALLS times.
ASKS, CLARIFY, LLM_CALLS = 12, 3, 30
WARM_CALLS = 16          # design §10.7: cache warm-ups per review (they write nothing; counted apart from LLM_CALLS)
MAX_NEEDS, NEEDS_PER_CALL = 8, 2


def _used(c, sid):
    rows = c.execute("SELECT kind, base FROM asks WHERE session_id=?", (sid,)).fetchall()
    return len(rows), sum(1 for r in rows if r["kind"] == "clarify"), rows


def budget(sid):
    with _db() as c:
        ses = _session(c, sid)
        used, clar, rows = _used(c, sid)
        keys = [r[0] for r in c.execute("SELECT key FROM asks WHERE session_id=?", (sid,))]
        return {"used": used, "max": ASKS, "clarify": clar, "clarify_max": CLARIFY, "close": closed(c, sid),
                "llm": ses["llm_calls"] or 0, "llm_max": LLM_CALLS, "asked": keys}


def clarify_base(k):
    """the answer a clarification is about, as one key: A1.T1@1 and A1.T1.2@1 (its second unclear part) -> T1@1;
    A3.F2 -> FREE:2; C5.B3@1 -> B3@1; C5.concurrent@1 -> itself"""
    own = [x for x in _base_keys(k, {}) if x != "FREE:*"]
    return re.sub(r"\.\d+(?=@|$)", "", own[0]) if own else k


def clarified(sid):
    """the bases already clarified once (a second clarification of the same answer is not asked)"""
    with _db() as c:
        return {r[0] for r in c.execute("SELECT base FROM asks WHERE session_id=? AND kind='clarify'", (sid,))}


def closed(c, sid):
    return bool(c.execute("SELECT 1 FROM asks WHERE session_id=? AND kind='close' UNION SELECT 1 FROM jobs WHERE session_id=? AND kind='closed'",
                          (sid, sid)).fetchone())


def close_review(sid):
    """the review ended without the closing request (the budget was used up): recorded, so a late analysis adds nothing"""
    with _LOCK, _db() as c:
        c.execute("INSERT OR IGNORE INTO jobs (session_id, kind, status, started, finished) VALUES (?,?,?,?,?)",
                  (sid, "closed", "done", time.time(), time.time()))


def issue(sid, key, kind, base=None, reserve=0):
    """the foreman is shown this ask now -> {key, used, max, again} (again: shown before, not counted), or refused
    (StoreError 409 with code budget / clarify / close_once). One transaction: the check and the count together."""
    if kind not in ("question", "clarify", "card", "close"):
        raise StoreError(422, "bad_kind", "알 수 없는 요청 종류")
    with _LOCK, _db() as c:
        c.execute("BEGIN IMMEDIATE")
        _session(c, sid)
        used, clar, rows = _used(c, sid)
        if c.execute("SELECT 1 FROM asks WHERE session_id=? AND key=?", (sid, key)).fetchone():
            c.execute("COMMIT")
            return {"key": key, "used": used, "max": ASKS, "again": True}
        if kind == "close" and any(r["kind"] == "close" for r in rows):
            raise StoreError(409, "close_once", "마무리 요청은 한 번만")
        if kind != "close" and any(r["kind"] == "close" for r in rows):
            # design §3.6: after the review closed, new information is a change of its answers, not a new round of
            # asking (an ask already shown is shown again; nothing new is asked)
            raise StoreError(409, "closed", "마무리한 검토에는 새로 묻지 않습니다", used=used)
        if used >= ASKS:
            raise StoreError(409, "budget", f"질문 한도 {ASKS}회", used=used)
        if reserve and used + 1 + reserve > ASKS:
            # design §3.5 (Codex 2026-10-31): a card, a clarification, an AI question or a link card never takes an ask
            # an open rule question still needs
            raise StoreError(409, "reserved", f"남은 규칙 질문 {reserve}개 몫으로 남겨 둠", used=used)
        if kind == "clarify":
            if clar >= CLARIFY:
                raise StoreError(409, "clarify", f"다시 묻기 한도 {CLARIFY}회", used=used)
            if base and any(r["kind"] == "clarify" and r["base"] == base for r in rows):
                raise StoreError(409, "clarify", "같은 내용은 한 번만 다시 묻습니다", used=used)
        c.execute("INSERT INTO asks (session_id, key, kind, base, created) VALUES (?,?,?,?,?)", (sid, key, kind, base, time.time()))
        c.execute("COMMIT")
    return {"key": key, "used": used + 1, "max": ASKS, "again": False}


def charge_llm(sid):
    """one model call of this review, counted before it runs; refused past LLM_CALLS (the rules alone go on)"""
    with _LOCK, _db() as c:
        c.execute("BEGIN IMMEDIATE")
        ses = _session(c, sid)
        if (ses["llm_calls"] or 0) >= LLM_CALLS:
            raise StoreError(409, "llm_budget", f"모델 호출 한도 {LLM_CALLS}회")
        c.execute("UPDATE sessions SET llm_calls=COALESCE(llm_calls,0)+1 WHERE id=?", (sid,))
        if JOB.get():                              # counted on its job too: a restart gives back an unfinished job's calls
            c.execute("UPDATE jobs SET llm=COALESCE(llm,0)+1 WHERE session_id=? AND kind=? AND status='running'", (sid, JOB.get()))
        c.execute("COMMIT")


def warm(sid, qid):
    """one cache warm-up for the question shown, counted; refused past WARM_CALLS (the reading then reads it all)"""
    with _LOCK, _db() as c:
        c.execute("BEGIN IMMEDIATE")
        ses = _session(c, sid)
        if (ses["warm_calls"] or 0) >= WARM_CALLS:
            raise StoreError(409, "warm_budget", f"미리 읽기 한도 {WARM_CALLS}회")
        c.execute("UPDATE sessions SET warm_calls=COALESCE(warm_calls,0)+1 WHERE id=?", (sid,))
        c.execute("COMMIT")


def start_job(sid, kind):
    """a job done once per review (the upload analysis): True when this call starts it"""
    with _LOCK, _db() as c:
        c.execute("BEGIN IMMEDIATE")
        _session(c, sid)
        r = c.execute("SELECT status FROM jobs WHERE session_id=? AND kind=?", (sid, kind)).fetchone()
        if r and r["status"] == "interrupted":           # left unfinished by a restart: done again
            c.execute("UPDATE jobs SET status='running', started=?, finished=NULL, llm=0 WHERE session_id=? AND kind=?", (time.time(), sid, kind))
            c.execute("COMMIT")
            return True
        if r:
            c.execute("COMMIT")
            return False
        c.execute("INSERT INTO jobs (session_id, kind, status, started) VALUES (?,?,?,?)", (sid, kind, "running", time.time()))
        c.execute("COMMIT")
    return True


def open_job(sid, kind):
    """a job of one request (a reading: turn:…), recorded while it runs"""
    with _LOCK, _db() as c:
        c.execute("BEGIN IMMEDIATE")
        _session(c, sid)
        c.execute("INSERT OR REPLACE INTO jobs (session_id, kind, status, started, llm) VALUES (?,?,?,?,0)", (sid, kind, "running", time.time()))
        c.execute("COMMIT")


def recover():
    """at start (design §2.1): a job a restart cut off is 「interrupted」, not done, and the model calls it was charged
    are given back to its review. -> how many"""
    with _LOCK, _db() as c:
        c.execute("BEGIN IMMEDIATE")
        now, n = time.time(), 0
        for r in c.execute("SELECT session_id, kind, llm FROM jobs WHERE status='running'").fetchall():
            c.execute("UPDATE jobs SET status='interrupted', finished=? WHERE session_id=? AND kind=?", (now, r["session_id"], r["kind"]))
            if r["llm"]:
                c.execute("UPDATE sessions SET llm_calls=MAX(0, COALESCE(llm_calls,0)-?) WHERE id=?", (r["llm"], r["session_id"]))
            n += 1
        c.execute("COMMIT")
    return n


def job_row(sid, kind):
    """a job as recorded: {id, kind, status, started, finished, llm, result}, or None"""
    with _db() as c:
        _session(c, sid)
        r = c.execute("SELECT * FROM jobs WHERE session_id=? AND kind=?", (sid, kind)).fetchone()
        return _job(r) if r else None


def all_jobs(sid):
    with _db() as c:
        _session(c, sid)
        return [_job(r) for r in c.execute("SELECT * FROM jobs WHERE session_id=? ORDER BY started", (sid,))]


def _job(r):
    return {"id": f"{r['session_id']}~{r['kind']}", "kind": r["kind"], "status": r["status"], "started": r["started"], "finished": r["finished"],
            "llm": r["llm"] or 0, "result": json.loads(r["result"] or "{}")}


# events (design §12.1 POST /api/dialogues/{id}/events, §3.6): the answers' changes, what they expired, a change after
# the review closed (the server's), and a correction·withdrawal·note the foreman records (the client's)
def add_event(sid, kind, payload, action_id):
    if kind not in EVENT_KINDS:
        raise StoreError(422, "bad_event", "알 수 없는 기록 종류")
    with _LOCK, _db() as c:
        c.execute("BEGIN IMMEDIATE")
        ses = _session(c, sid)
        r = c.execute("SELECT n, kind, payload FROM events WHERE session_id=? AND action_id=?", (sid, action_id)).fetchone()
        if r:
            c.execute("COMMIT")
            if r["kind"] != kind or json.loads(r["payload"]) != payload:
                raise StoreError(409, "action_conflict", "같은 동작 번호에 다른 내용")
            return {"n": r["n"], "again": True}
        n = _event(c, sid, kind, ses["revision"], payload, action_id)
        if closed(c, sid):
            _event(c, sid, "after_close", ses["revision"], {"record": kind, **payload})
        c.execute("COMMIT")
    return {"n": n, "again": False}


def events(sid, kinds=None):
    with _db() as c:
        _session(c, sid)
        out = [{"n": r["n"], "kind": r["kind"], "rev": r["rev"], "actor": r["actor"], "created": r["created"], **json.loads(r["payload"])}
               for r in c.execute("SELECT * FROM events WHERE session_id=? ORDER BY n", (sid,))]
    return [e for e in out if not kinds or e["kind"] in kinds]


def expiry(sid, rev):
    """what one change at this revision expired (the grouped 「다시 확인」 notice), or None"""
    with _db() as c:
        r = c.execute("SELECT payload FROM events WHERE session_id=? AND kind='expiry' AND rev=? ORDER BY n DESC", (sid, rev)).fetchone()
    return {"rev": rev, **json.loads(r["payload"])} if r else None


def confirmations(sid):
    with _db() as c:
        _session(c, sid)
        return [{"action_id": r["action_id"], "actor": r["actor"], "role": r["role"], "digest": r["digest"], "targets": json.loads(r["targets"]),
                 "scope": json.loads(r["scope"]), "created": r["created"]} for r in c.execute("SELECT * FROM confirmations WHERE session_id=? ORDER BY created", (sid,))]


def facts(sid, fields=None):
    """design §2.1 Fact: the typed answers (stated) and every reading (proposed, confirmed, superseded), each with its
    version, polarity, modality, phase, origin, evidence, what it depends on and when it held"""
    with _db() as c:
        c.execute("BEGIN")
        ses = _session(c, sid)
        nums = permit_numbers(fields) if fields else {}
        out_, _ = _project(c, ses, fields or {})
        changes = {}
        for r in c.execute("SELECT payload FROM events WHERE session_id=? AND kind='answers'", (sid,)):
            for x in json.loads(r["payload"]).get("changes", []):
                changes[x["skey"]] = changes.get(x["skey"], 0) + 1
        out = []
        for a in [x for x in out_ if not x.get("pid")]:
            k = skey(a["qid"], a.get("q"))
            out.append({"fact_id": f"T:{k}", "version": 1 + changes.get(k, 0), "slot_id": k, "qid": a["qid"],
                        "typed_value": {"choice": a.get("choice"), "value": a.get("value")},
                        "polarity": "negative" if a.get("choice") in NEG_CHOICES else "positive",
                        "modality": "unknown" if a.get("choice") == "unknown" else "asserted", "phase": "unspecified",
                        "origin": "typed", "evidence_ids": [f"answer:{k}"], "status": "current", "acceptance": "stated",
                        "depends_on": [], "valid_from": (a.get("at") or 0) / 1000 if a.get("at") else None, "valid_to": None})
        state_of = {"proposed": "proposed", "adopted": "current"}
        for r in c.execute("SELECT * FROM proposals WHERE session_id=? ORDER BY created", (sid,)):
            p, a = json.loads(r["payload"]), _answer(r, nums)
            out.append({"fact_id": r["id"], "version": p.get("version") or 1, "slot_id": r["skey"], "qid": a["qid"],
                        "typed_value": {"choice": p.get("choice"), "value": p.get("value")},
                        "polarity": p.get("polarity") or ("negative" if p.get("choice") in NEG_CHOICES else "positive"),
                        "modality": p.get("modality") or "asserted", "phase": p.get("phase") or "unspecified",
                        "origin": r["origin"], "evidence_ids": [f"answer:{r['src_skey']}" + (f"#{p.get('quote')}" if p.get("quote") else "")],
                        "status": state_of.get(r["status"], "superseded"), "acceptance": "confirmed" if r["status"] == "adopted" else "unconfirmed",
                        "depends_on": [f"{r['src_skey']}@{r['src_hash']}", f"form:{r['ctx']}"], "valid_from": r["created"],
                        "valid_to": r["decided"] if r["status"] not in ("proposed", "adopted") else None})
        c.execute("COMMIT")
    return out


def finish_job(sid, kind, status, result=None):
    with _LOCK, _db() as c:
        c.execute("UPDATE jobs SET status=?, finished=?, result=? WHERE session_id=? AND kind=?",
                  (status, time.time(), json.dumps(result or {}, ensure_ascii=False), sid, kind))


def put_job(sid, kind, status, result=None):
    """a record of the review kept by kind (a confirmed link: link:<plan>), replaced when given again"""
    with _LOCK, _db() as c:
        c.execute("BEGIN IMMEDIATE")
        _session(c, sid)
        c.execute("INSERT OR REPLACE INTO jobs (session_id, kind, status, started, finished, result) VALUES (?,?,?,?,?,?)",
                  (sid, kind, status, time.time(), time.time(), json.dumps(result or {}, ensure_ascii=False)))
        c.execute("COMMIT")


def jobs(sid, prefix):
    with _db() as c:
        return {r["kind"]: {"status": r["status"], **json.loads(r["result"] or "{}")}
                for r in c.execute("SELECT kind, status, result FROM jobs WHERE session_id=? AND kind LIKE ?", (sid, prefix + "%"))}


def job(sid, kind):
    with _db() as c:
        r = c.execute("SELECT status, result FROM jobs WHERE session_id=? AND kind=?", (sid, kind)).fetchone()
        return {"status": r["status"], **json.loads(r["result"] or "{}")} if r else None


def add_needs(sid, items):
    """the AI's needs of one analysis, after the server's checks -> the ones stored (at most NEEDS_PER_CALL of a call,
    MAX_NEEDS in a review; one with the same meaning key as any before — answered, dropped or not — is not added;
    a place, once used, is not given back), or None when the review has ended (checked in the same transaction)"""
    out = []
    with _LOCK, _db() as c:
        c.execute("BEGIN IMMEDIATE")
        _session(c, sid)
        if closed(c, sid):
            c.execute("COMMIT")
            return None
        have = {r["mkey"] for r in c.execute("SELECT mkey FROM needs WHERE session_id=?", (sid,))}
        n = c.execute("SELECT COALESCE(MAX(n),0) FROM needs WHERE session_id=?", (sid,)).fetchone()[0]
        for it in items[:NEEDS_PER_CALL]:
            if n >= MAX_NEEDS or it["mkey"] in have:
                continue
            n += 1
            have.add(it["mkey"])
            c.execute("INSERT INTO needs (session_id, n, mkey, payload, created) VALUES (?,?,?,?,?)",
                      (sid, n, it["mkey"], json.dumps(it, ensure_ascii=False), time.time()))
            out.append({**it, "n": n})
        c.execute("COMMIT")
    return out


def needs(sid):
    with _db() as c:
        return [{**json.loads(r["payload"]), "n": r["n"]} for r in c.execute("SELECT n, payload FROM needs WHERE session_id=? ORDER BY n", (sid,))]
