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
        CREATE TABLE IF NOT EXISTS qa_file (qa_id INTEGER, n INTEGER, name TEXT, mime TEXT, size INTEGER, PRIMARY KEY (qa_id, n));""")
    cols = {r["name"] for r in c.execute("PRAGMA table_info(qa)")}
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


def set_handled(qid, handled, note=None):
    with _db() as c:
        return c.execute("UPDATE qa SET handled = ?, note = COALESCE(?, note) WHERE id = ?", (int(handled), note, qid)).rowcount > 0
