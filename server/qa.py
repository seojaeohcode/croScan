"""QA reports from the web page: attached files (captures, PDF, Word, Excel, anything; no count or size limit)
+ what is wrong + the screen state. Reports live in one SQLite file; attachments are streamed to
data/qa_files/<id>/ so a large file never sits in memory. Anyone can send a report; reading them back needs the
QA_TOKEN header (tools/qa_pull.py). `handled` (0/1) marks the reports the team has dealt with."""
import json
import os
import shutil
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

DATA = Path(os.environ.get("CROSCAN_DATA", Path(__file__).resolve().parent.parent / "data"))
DB = DATA / "qa.sqlite3"
FILES = DATA / "qa_files"
INCOMING = FILES / ".incoming"                      # attachments land here first, then move under the report id
KST = timezone(timedelta(hours=9))
MAX_TEXT, MAX_CONTEXT = 5000, 2 * 1024 * 1024
FLOOR = int(float(os.environ.get("CROSCAN_DISK_FLOOR_GB", "2")) * 2**30)   # uploads stop when less is free


class DiskFull(OSError):
    pass


def copy_with_floor(src, dst):
    """Stream src (a binary file) to dst in 1 MB pieces; stop when the disk would drop under FLOOR.
    No size limit on purpose (the team wanted none): only the disk itself is protected."""
    if shutil.disk_usage(DATA).free < FLOOR:
        raise DiskFull("서버 저장 공간이 부족합니다")
    n = 0
    with open(dst, "wb") as out:
        while chunk := src.read(1024 * 1024):
            out.write(chunk)
            n += 1
            if n % 64 == 0 and shutil.disk_usage(DATA).free < FLOOR:
                raise DiskFull("서버 저장 공간이 부족합니다")


_ready, _lock = False, threading.Lock()
_runlock = threading.Lock()                         # one 「QA 시작하기」 request at a time (not the setup lock)


def _setup(c):
    """Tables and the one migration, once per process (not on every request); also drops attachments left in
    .incoming by a crash (older than an hour, so a report being saved right now is not touched)."""
    if INCOMING.exists():
        for d in INCOMING.iterdir():
            try:
                if time.time() - d.stat().st_mtime > 3600:
                    shutil.rmtree(d, ignore_errors=True)
            except FileNotFoundError:
                pass
    c.executescript("""
        CREATE TABLE IF NOT EXISTS qa (id INTEGER PRIMARY KEY AUTOINCREMENT, created TEXT, author TEXT, text TEXT,
                                       context TEXT, handled INTEGER NOT NULL DEFAULT 0, note TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS qa_file (qa_id INTEGER, n INTEGER, name TEXT, mime TEXT, size INTEGER, PRIMARY KEY (qa_id, n));
        CREATE TABLE IF NOT EXISTS qa_run (id INTEGER PRIMARY KEY AUTOINCREMENT, requested TEXT, by TEXT, status TEXT,
                                           started TEXT DEFAULT '', finished TEXT DEFAULT '', note TEXT DEFAULT '',
                                           done TEXT DEFAULT '', open_at_request INTEGER DEFAULT 0);""")
    cols = {r["name"] for r in c.execute("PRAGMA table_info(qa)")}
    for col in ("handled_at", "decision"):          # when it was handled · how (수용 · 부분 수용 · 거절 · 보류), shown to the team
        if col not in cols:
            try:
                c.execute(f"ALTER TABLE qa ADD COLUMN {col} TEXT DEFAULT ''")
            except sqlite3.OperationalError as e:   # another worker added it first
                if "duplicate column" not in str(e):
                    raise
    if "handled" not in cols:                       # older DB: open/done status -> handled 0/1
        c.execute("ALTER TABLE qa ADD COLUMN handled INTEGER NOT NULL DEFAULT 0")
        if "status" in cols:
            c.execute("UPDATE qa SET handled = (status != 'open')")
            c.execute("ALTER TABLE qa DROP COLUMN status")
    c.commit()


@contextmanager
def _db():
    """A connection for one operation: committed when the block ends, rolled back on an error, always closed."""
    global _ready
    DATA.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    try:
        if not _ready:
            with _lock:
                if not _ready:
                    _setup(c)
                    _ready = True
        yield c
        c.commit()
    except BaseException:
        c.rollback()
        raise
    finally:
        c.close()


def _path(qid, n):
    return FILES / str(qid) / f"{n:03d}"


def add(text, author, context, files):
    """files: [(name, mime, readable binary file)]. Returns the new report id.
    The attachments are copied first into a folder of this request's own (.incoming/<uuid>), outside any
    transaction; then one short transaction writes the rows and moves the folder under the id before it commits.
    A failure only ever removes this request's own folder, and the database is locked just for the rows."""
    tmp = INCOMING / uuid.uuid4().hex
    tmp.mkdir(parents=True)
    final = None
    try:
        meta = []
        for n, (name, mime, src) in enumerate(files, 1):
            p = tmp / f"{n:03d}"
            copy_with_floor(src, p)
            meta.append((n, name, mime, p.stat().st_size))
        with _db() as c:
            qid = c.execute("INSERT INTO qa (created, author, text, context) VALUES (?, ?, ?, ?)",
                            (datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"), author, text, context)).lastrowid
            c.executemany("INSERT INTO qa_file VALUES (?, ?, ?, ?, ?)", [(qid, *m) for m in meta])
            if meta:
                final = FILES / str(qid)
                shutil.rmtree(final, ignore_errors=True)          # left over from an id an earlier crash never committed
                os.replace(tmp, final)
        return qid
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        if final is not None and final.exists():             # moved, then the commit failed: the id was rolled back
            shutil.rmtree(final, ignore_errors=True)
        raise
    finally:
        if tmp.exists() and not any(tmp.iterdir()):
            tmp.rmdir()


def listing(handled=None):
    """handled: None = every report, True / False = only those."""
    with _db() as c:
        rows = c.execute("SELECT * FROM qa" + (" WHERE handled = ?" if handled is not None else "") + " ORDER BY id",
                         (int(handled),) if handled is not None else ()).fetchall()
        files = c.execute("SELECT * FROM qa_file ORDER BY qa_id, n").fetchall()
    by = {}
    for f in files:
        by.setdefault(f["qa_id"], []).append({k: f[k] for k in ("n", "name", "mime", "size")})
    return [{**dict(r), "handled": bool(r["handled"]), "context": _context(r["context"]), "files": by.get(r["id"], [])} for r in rows]


def _context(raw):
    """One report's screen state; a broken one comes back as a note instead of failing the whole list."""
    try:
        v = json.loads(raw or "{}")
        return v if isinstance(v, dict) else {"_broken": str(raw)[:200]}
    except ValueError:
        return {"_broken": str(raw)[:200]}


def file(qid, n):
    """(name, mime, path on disk) or None."""
    with _db() as c:
        row = c.execute("SELECT name, mime FROM qa_file WHERE qa_id = ? AND n = ?", (qid, n)).fetchone()
    return (row["name"], row["mime"], _path(qid, n)) if row and _path(qid, n).exists() else None


def _now():
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")


DECISIONS = ("수용", "부분 수용", "거절", "보류")


def set_handled(qid, handled, note=None, decision=None):
    """decision: how it was handled (DECISIONS), shown to the team with the note; taken back when marked not handled."""
    if decision is not None and decision not in DECISIONS:
        raise ValueError(decision)
    with _db() as c:
        # a note changed without a decision keeps the decision; marked not handled, both time and decision go
        return c.execute("UPDATE qa SET handled = ?, note = COALESCE(?, note), handled_at = ?, "
                         "decision = CASE WHEN ? = 0 THEN '' ELSE COALESCE(?, decision) END WHERE id = ?",
                         (int(handled), note, _now() if handled else "", int(handled), decision, qid)).rowcount > 0


# ---------------------------------------------------------------- the team's view: what was sent, what is done, who works on it
# The board shows each report's number, time, sender, the start of its text and whether it is handled (newest first);
# the screen state and the attachments stay behind the QA token.
BOARD_TEXT = 300
RUN_STATES = ("requested", "running", "done", "failed")


SCREENS = {"s-login", "s-upload", "s-load", "s-edit", "s-plans", "s-check", "s-submit", "s-safety"}


def board(show="all", limit=300):
    """show: all · open (not handled) · done; filtered before the limit, so an old open report is not lost."""
    where = {"open": " WHERE handled = 0", "done": " WHERE handled = 1"}.get(show, "")
    with _db() as c:
        rows = c.execute("SELECT id, created, author, text, context, handled, note, handled_at, decision FROM qa"
                         + where + " ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        nf = dict(c.execute("SELECT qa_id, COUNT(*) FROM qa_file GROUP BY qa_id").fetchall())
        left = c.execute("SELECT COUNT(*) FROM qa WHERE handled = 0").fetchone()[0]
        total = c.execute("SELECT COUNT(*) FROM qa").fetchone()[0]
    out = []
    for r in rows:
        ctx = _context(r["context"])
        out.append({"id": r["id"], "created": r["created"], "author": r["author"] or "", "text": (r["text"] or "")[:BOARD_TEXT],
                    "more": len(r["text"] or "") > BOARD_TEXT, "screen": ctx.get("screen") if isinstance(ctx.get("screen"), str) and ctx.get("screen") in SCREENS else "",
                    "files": nf.get(r["id"], 0),
                    "handled": bool(r["handled"]), "decision": r["decision"] or "", "note": r["note"] or "", "handled_at": r["handled_at"] or ""})
    return {"reports": out, "left": left, "total": total, "shown": show, "runs": runs()}


def runs(limit=10):
    with _db() as c:
        return [dict(r) for r in c.execute("SELECT * FROM qa_run ORDER BY id DESC LIMIT ?", (limit,)).fetchall()]


def request_run(by=""):
    """「QA 시작하기」: one request at a time — while one is waiting or running, that one is given back (no second);
    nothing to do (no report left) makes none. (None, False) then. Serialised over workers too (BEGIN IMMEDIATE)."""
    with _runlock, _db() as c:
        c.execute("BEGIN IMMEDIATE")
        cur = c.execute("SELECT * FROM qa_run WHERE status IN ('requested', 'running') ORDER BY id DESC LIMIT 1").fetchone()
        if cur:
            return dict(cur), False
        left = c.execute("SELECT COUNT(*) FROM qa WHERE handled = 0").fetchone()[0]
        if not left:
            return None, False
        rid = c.execute("INSERT INTO qa_run (requested, by, status, open_at_request) VALUES (?, ?, 'requested', ?)",
                        (_now(), (by or "")[:40], left)).lastrowid
        return dict(c.execute("SELECT * FROM qa_run WHERE id = ?", (rid,)).fetchone()), True


def set_run(rid, status, note=None, done=None):
    """The session working on it says where it is: running (start time), done / failed (end time, the reports handled)."""
    if status not in RUN_STATES:
        raise ValueError(status)
    with _db() as c:
        sets, vals = ["status = ?"], [status]
        if status == "running":
            sets.append("started = ?"); vals.append(_now())
        if status in ("done", "failed"):
            sets.append("finished = ?"); vals.append(_now())
        if note is not None:
            sets.append("note = ?"); vals.append(note[:2000])
        if done is not None:
            sets.append("done = ?"); vals.append(",".join(str(int(x)) for x in done)[:2000])
        n = c.execute(f"UPDATE qa_run SET {', '.join(sets)} WHERE id = ?", (*vals, rid)).rowcount
        return n > 0
