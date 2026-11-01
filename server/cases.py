"""확인 사례 (design §4.5 재학습 없는 개선 루프): a foreman's confirmed or refused readings become candidate examples —
waiting for review → reviewed by a person → de-identified → published as a numbered version — and the published ones
are what the readings may show as examples (understand.examples) and what the regression runs (tools/check_cases.py).

Nothing here changes an answer or a rule. A case is never used before a person reviewed it (status 'reviewed' →
publish); a refused reading is kept as a counter-example only. Names, phone numbers, permit numbers and e-mail
addresses are masked before anything is stored. SQLite in the data volume (qa.DATA / cases.sqlite3).
"""
import contextlib
import json
import re
import secrets
import sqlite3
import threading
import time

from . import qa

DB = qa.DATA / "cases.sqlite3"
_LOCK = threading.Lock()
_SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (id TEXT PRIMARY KEY, created REAL, item TEXT, grp TEXT, questions TEXT, asked TEXT,
    answer TEXT, out TEXT, refused TEXT, status TEXT, reviewer TEXT, note TEXT, version INTEGER, src_key TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
"""
STATUSES = ("queued", "reviewed", "rejected", "published")


@contextlib.contextmanager
def _db():
    qa.DATA.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB, timeout=5, isolation_level=None)
    c.row_factory = sqlite3.Row
    try:
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(_SCHEMA)
        yield c
    finally:
        if c.in_transaction:
            c.rollback()
        c.close()


MASKS = [(re.compile(r"(?<!\d)01[016789][-\s]?\d{3,4}[-\s]?\d{4}(?!\d)"), "[전화]"),
         (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[메일]"),
         (re.compile(r"(?<![A-Z0-9])[A-Z]{2}\d{2}-[A-Z]{2}-\d{8}-\d{4}(?!\d)"), "[허가번호]"),
         (re.compile(r"[가-힣]{2,4}(?=\s*(?:반장|님|씨|대리|과장|주임|기사))"), "[이름]")]


def deidentify(text):
    for rx, to in MASKS:
        text = rx.sub(to, text or "")
    return text


def record(sid, adopted, refused):
    """the foreman's decision on a card (store.decide) -> candidate cases, one per answer read (queued). Returns ids."""
    from . import store
    from .understand import _group
    ids = list(adopted or []) + list(refused or [])
    if not ids:
        return []
    with store._db() as c:
        rows = [dict(r) for r in c.execute(f"SELECT id, src_skey, payload FROM proposals WHERE session_id=? AND id IN ({','.join('?' * len(ids))})",
                                           [sid, *ids])]
        typed = {r["skey"]: json.loads(r["data"]) for r in c.execute("SELECT skey, data FROM typed WHERE session_id=?", (sid,))}
    by_src = {}
    for r in rows:
        by_src.setdefault(r["src_skey"], []).append((r["id"] in (adopted or []), json.loads(r["payload"])))
    out = []
    for sk, items in by_src.items():
        src = typed.get(sk)
        if not src or not (src.get("value") or "").strip():
            continue
        answer = deidentify(src["value"].strip())
        qs, props, bad = [], [], []
        items.sort(key=lambda x: (not x[0], str((x[1].get("q") or {}).get("qid"))))     # the confirmed first: it names the case
        for ok, p in items:
            q = p.get("q") or {}
            if q.get("qid") not in [x.get("qid") for x in qs]:
                qs.append({k: q.get(k) for k in ("qid", "item", "text", "choices")})
            n = next(i for i, x in enumerate(qs, 1) if x.get("qid") == q.get("qid"))
            row = {"q": f"Q{n}", "c": p.get("choice"), "v": deidentify(p.get("value") or ""), "who": p.get("who") or "self",
                   "when": p.get("when") or "none", "quote": deidentify(p.get("quote") or "")}
            (props if ok else bad).append(row)
        if not props and not bad:
            continue
        item = (qs[0].get("item") or "").split(":")[0]
        key = f"{sid}:{sk}:{answer}"
        cid = secrets.token_urlsafe(9)
        with _LOCK, _db() as c:
            try:
                c.execute("INSERT INTO cases (id, created, item, grp, questions, asked, answer, out, refused, status, src_key) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                          (cid, time.time(), item, _group({"item": item}), json.dumps(qs, ensure_ascii=False),
                           deidentify(((src.get("q") or {}).get("text") or "")[:120]), answer, json.dumps(props, ensure_ascii=False),
                           json.dumps(bad, ensure_ascii=False), "queued", key))
                out.append(cid)
            except sqlite3.IntegrityError:
                continue                                   # the same answer recorded before
    return out


def listing(status=None):
    with _db() as c:
        q = "SELECT * FROM cases" + (" WHERE status=?" if status else "") + " ORDER BY created"
        return [dict(r) for r in c.execute(q, (status,) if status else ())]


def review(cid, ok, reviewer, note=""):
    """a person's review of a waiting case: reviewed (ready to publish) or rejected; nobody → refused"""
    if not (reviewer or "").strip():
        raise ValueError("검수자 이름이 필요합니다")
    with _LOCK, _db() as c:
        r = c.execute("SELECT status FROM cases WHERE id=?", (cid,)).fetchone()
        if not r or r["status"] != "queued":
            raise ValueError("검수 대기 사례가 아닙니다")
        c.execute("UPDATE cases SET status=?, reviewer=?, note=? WHERE id=?", ("reviewed" if ok else "rejected", reviewer.strip(), note, cid))


def _valid(case):
    """a case may be an example only when its output holds against its own words: each quote is in the answer and
    each choice is the question's own"""
    qs, answer = json.loads(case["questions"]), case["answer"]
    norm = lambda s: re.sub(r"[\s\"'“”‘’「」.,·…]", "", s or "")
    for p in json.loads(case["out"]):
        n = int(p["q"][1:]) - 1
        if not (0 <= n < len(qs)) or norm(p["quote"]) not in norm(answer):
            return False
        if p["c"] not in [c.get("id") for c in qs[n].get("choices") or []]:
            return False
    return bool(json.loads(case["out"]))


def publish():
    """every reviewed case that holds -> published under a new version number. -> (version, published ids, held ids)"""
    with _LOCK, _db() as c:
        c.execute("BEGIN IMMEDIATE")
        v = int((c.execute("SELECT v FROM meta WHERE k='version'").fetchone() or {"v": 0})["v"]) + 1
        done, held = [], []
        for r in c.execute("SELECT * FROM cases WHERE status='reviewed'").fetchall():
            if _valid(r):
                c.execute("UPDATE cases SET status='published', version=? WHERE id=?", (v, r["id"]))
                done.append(r["id"])
            else:
                c.execute("UPDATE cases SET note=? WHERE id=?", ((r["note"] or "") + " · 발행 보류: 구절·보기가 맞지 않음", r["id"]))
                held.append(r["id"])
        if done:
            c.execute("INSERT OR REPLACE INTO meta (k, v) VALUES ('version', ?)", (str(v),))
        c.execute("COMMIT")
    _CACHE.clear()
    return (v if done else v - 1), done, held


_CACHE = {}


def example(group):
    """the newest published case of a slot group as a prompt example (question list, answer, reply), or None"""
    if group in _CACHE:
        return _CACHE[group]
    with _db() as c:
        r = c.execute("SELECT * FROM cases WHERE status='published' AND grp=? ORDER BY version DESC, created DESC LIMIT 1", (group,)).fetchone()
    ex = None
    if r:
        qs = json.loads(r["questions"])
        lines = []
        for i, q in enumerate(qs, 1):
            ch = ", ".join(f"{c['id']}={c.get('label', c['id'])}{'(값)' if c.get('ask') else ''}" for c in q.get("choices") or [] if c.get("id") != "unknown")
            words = re.sub(r"\s+", " ", q.get("text") or "").strip()[:120]
            lines.append(f"Q{i} {words} 보기: {ch}")
        ex = ("남은 질문:\n" + "\n".join(lines) + f"\n질문: {r['asked']}\n반장의 답: {r['answer']}",
              json.dumps({"props": json.loads(r["out"]), "next": "none"}, ensure_ascii=False, separators=(",", ":")))
    _CACHE[group] = ex
    return ex


def similar(item, text, k=2):
    """published cases of the item most like the text, and its counter-examples (refused readings): for review and
    for the regression"""
    words = set(re.findall(r"[가-힣A-Za-z0-9]{2,}", text or ""))
    with _db() as c:
        rows = [dict(r) for r in c.execute("SELECT * FROM cases WHERE status='published' AND item=?", (item,))]
    rank = lambda r: -len(words & set(re.findall(r"[가-힣A-Za-z0-9]{2,}", r["answer"])))
    rows.sort(key=rank)
    return {"cases": rows[:k], "counter": [r for r in rows if json.loads(r["refused"] or "[]")][:k]}
