"""제출 스냅숏 (design §2.3 「제출은 문서·사실·연결·체크리스트·배치 계획의 버전을 고정한다. 다운로드 때 모델을 다시
실행하지 않는다」, §12.2 「반장 결과 → 관리자 보기」).

At 「제출」 the server makes, once, what the review is at that moment: the permit file (by its hash), the form values,
the answers that count (the session's, at the revision the foreman saw), the 반영 plan and the 추가검토서, what is
left for the safety team, and the 위험 체크리스트 as drafted by the server from those answers with the foreman's own
choice on every item (an item whose croScan basis changed since he chose is refused, not taken). The PDFs are drawn
from that snapshot afterwards, as often as asked, without the model and without the session (which may move on).
The same review at the same revision submitted again gives the same snapshot. The safety manager's view lists the
latest snapshot per permit number. Demo: nothing is sent to 전산·결재; this is croScan's own record.
"""
import hashlib
import json
import os
import secrets
import time

from . import checklist, qa, store

PDFS = qa.DATA / "submitted"
# 시연판 (2026-11-03 사용자 결정): 제출은 DB·디스크에 남기지 않는다. 반장 화면은 제출된 것처럼 이어지고(그 문서는 이
# 프로세스 메모리에 최근 몇 건만), 안전관리자 화면은 미리 만든 시연 자료만으로 계산한다(latest가 비어 있다).
# CROSCAN_KEEP_SUBMISSIONS=1 이면 예전처럼 저장하고 관리자 화면에 합친다(시험용).
KEEP = os.environ.get("CROSCAN_KEEP_SUBMISSIONS") == "1"
HELD_MAX = 6
_HELD = {}          # id -> (payload, {name: PDF bytes}, summary, (session_id, revision, key)), oldest first
_SCHEMA = """CREATE TABLE IF NOT EXISTS submissions (id TEXT PRIMARY KEY, session_id TEXT, revision INTEGER, permit_no TEXT,
    created REAL, pdf_hash TEXT, digest TEXT, summary TEXT, payload TEXT);
CREATE INDEX IF NOT EXISTS submissions_permit ON submissions (permit_no, created);"""
STATES = ("yes", "no", "check")


class Refused(Exception):
    def __init__(self, code, detail, **extra):
        super().__init__(detail)
        self.code, self.detail, self.extra = code, detail, extra


def confirm_checklist(draft, sent, marks=None):
    """the server's draft with the foreman's choices -> the checklist as confirmed (the page's format), or Refused.
    Every item of the draft must have been chosen, on the croScan proposal it was chosen against; an item that is
    해당 also needs its safety measures confirmed (ctl_touched) on the measures' own basis (basis_ctl, design §7);
    the safety measures are the draft's own (by id); an item he added himself (U…) is kept as written.
    marks: the AI's readings of the base items (checkai.marks_cached): a 「해당 없음」 he chose where the AI found
    words that the hazard is there must have been chosen again after that was shown (ai_ack) — a model never changes
    his choice, but a possible miss is not passed silently either."""
    mine = {}
    for P in (sent or {}).get("permits", []) if isinstance(sent, dict) else []:
        for it in P.get("items", []) if isinstance(P, dict) and isinstance(P.get("items"), list) else []:
            if isinstance(it, dict):
                mine[(str(P.get("permit_no")), str(it.get("id")))] = it
    out, left, changed, seen = [], [], [], []
    for P in draft["permits"]:
        items = []
        for it in P["items"]:
            o = mine.get((P["permit_no"], it["id"]))
            if not o or not o.get("touched") or o.get("state") not in STATES:
                left.append(it["id"]); continue
            if o.get("auto") != it["auto"] or o.get("basis") != it.get("basis"):
                changed.append(it["id"]); continue
            if o["state"] == "yes":                       # 해당: the measures confirmed too, on their own basis
                if it.get("basis_ctl") and o.get("basis_ctl") != it["basis_ctl"]:
                    changed.append(it["id"]); continue
                if not o.get("ctl_touched"):
                    left.append(it["id"]); continue
            mk = (marks or {}).get(it["id"])
            if mk and mk.get("m") == "support" and o["state"] == "no" and o.get("ai_ack") != mk.get("id"):
                seen.append(it["id"]); continue
            on = {k.get("id") for k in o.get("controls", []) if isinstance(k, dict) and k.get("on")}
            items.append({**it, "state": o["state"], "touched": True, "ctl_touched": o["state"] == "yes", "memo": str(o.get("memo") or "")[:300],
                          "controls": [{**k, "on": k["id"] in on} for k in it["controls"]]})
        for (pno, iid), o in mine.items():
            if pno == P["permit_no"] and iid.startswith("U") and o.get("state") in STATES:
                items.append({"id": iid, "title": str(o.get("title", ""))[:80], "state": o["state"], "auto": None, "touched": True, "ctl_touched": True,
                              "reasons": [], "memo": str(o.get("memo") or "")[:300], "common": False,
                              "controls": [{"id": str(k.get("id")), "text": str(k.get("text", ""))[:120], "on": True}
                                           for k in o.get("controls", []) if isinstance(k, dict) and k.get("on")][:8]})
        out.append({**{k: P[k] for k in ("permit_no", "kind", "label", "who")}, "items": items})
    if changed:
        raise Refused("checklist_changed", f"허가서나 답이 바뀌어 위험 체크리스트 {len(changed)}개 항목을 다시 확인해야 합니다", items=changed)
    if seen:
        raise Refused("checklist_changed", f"작업 내용에 해당 근거가 있는 항목 {len(seen)}개를 「해당 없음」으로 골랐습니다. 다시 확인해 주세요", items=seen)
    if left:
        raise Refused("checklist_left", f"위험 체크리스트에 확인하지 않은 항목(해당 여부 또는 준비할 안전조치)이 {len(left)}개 있습니다", items=left)
    checklist.clean({"permits": out})                    # the same limits as the PDF has
    return {"version": draft.get("version"), "permits": out}


KEEP_DAYS = 30


def key_of(session_id, revision, inputs):
    """what makes a submission the same one: the review, its revision and the confirmed inputs (never a time)"""
    return hashlib.sha256(json.dumps([session_id, revision, inputs], ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


def find(session_id, revision, key):
    if not KEEP:
        for sid, (_, _, summ, k) in _HELD.items():
            if k == (session_id, revision, key):
                return {"id": sid, "created": summ["created"], "digest": key, "again": True, "summary": summ}
        return None
    with store._db() as c:
        c.executescript(_SCHEMA)
        r = c.execute("SELECT id, created, summary FROM submissions WHERE session_id=? AND revision=? AND digest=?", (session_id, revision, key)).fetchone()
    return {"id": r["id"], "created": r["created"], "digest": key, "again": True, "summary": json.loads(r["summary"])} if r else None


def _put(data):
    h = hashlib.sha256(data).hexdigest()
    f = PDFS / f"{h}.pdf"
    if not f.exists():
        tmp = f.with_name(f"{h}.{secrets.token_hex(4)}.tmp")
        tmp.write_bytes(data)
        tmp.replace(f)
    return h


def create(session_id, revision, key, files, payload, summary, created):
    """-> {id, created, digest, again}: the submission made once — files {name: PDF bytes} drawn at 제출 (the original
    permit, the 추가검토서, the checklist, the plans) kept as they are; a second request with the same key is the first"""
    if not KEEP:                                    # 시연판: held in memory for the foreman's downloads only
        again = find(session_id, revision, key)
        if again:
            return {k: again[k] for k in ("id", "created", "digest", "again")}
        sid = secrets.token_urlsafe(12)
        kept = {k: v for k, v in files.items() if v}
        _HELD[sid] = (payload, kept, {**summary, "created": created, "files": sorted(kept)}, (session_id, revision, key))
        while len(_HELD) > HELD_MAX:
            _HELD.pop(next(iter(_HELD)))
        return {"id": sid, "created": created, "digest": key, "again": False}
    PDFS.mkdir(parents=True, exist_ok=True)
    hashes = {k: _put(v) for k, v in files.items() if v}
    with store._LOCK, store._db() as c:
        c.executescript(_SCHEMA)
        c.execute("BEGIN IMMEDIATE")
        r = c.execute("SELECT id, created FROM submissions WHERE session_id=? AND revision=? AND digest=?", (session_id, revision, key)).fetchone()
        if r:
            c.execute("COMMIT")
            return {"id": r["id"], "created": r["created"], "digest": key, "again": True}
        sid = secrets.token_urlsafe(12)
        c.execute("INSERT INTO submissions (id, session_id, revision, permit_no, created, pdf_hash, digest, summary, payload) VALUES (?,?,?,?,?,?,?,?,?)",
                  (sid, session_id, revision, summary.get("permit_no"), created, json.dumps(hashes), key,
                   json.dumps({**summary, "created": created, "files": sorted(hashes)}, ensure_ascii=False),
                   json.dumps(payload, ensure_ascii=False, sort_keys=True)))
        # kept as long as the review sessions: older submissions and the files no submission uses any more go
        c.execute("DELETE FROM submissions WHERE created < ?", (time.time() - KEEP_DAYS * 86400,))
        used = set()
        for row in c.execute("SELECT pdf_hash FROM submissions"):
            try:
                used |= set(json.loads(row[0]).values())
            except (ValueError, AttributeError):
                used.add(row[0])
        c.execute("COMMIT")
    for f in PDFS.glob("*.pdf"):
        if f.stem not in used and time.time() - f.stat().st_mtime > 3600:
            f.unlink(missing_ok=True)
    return {"id": sid, "created": created, "digest": key, "again": False}


def get(sub_id):
    """-> (payload, {name: hash}, summary) or None"""
    if sub_id in _HELD:
        return _HELD[sub_id][:3]
    with store._db() as c:
        c.executescript(_SCHEMA)
        r = c.execute("SELECT * FROM submissions WHERE id=?", (sub_id,)).fetchone()
    if not r:
        return None
    return json.loads(r["payload"]), json.loads(r["pdf_hash"]), json.loads(r["summary"])


def file(hashes, name):
    """a document of a submission as it was made at 제출, or None (gone after the keeping time)"""
    h = (hashes or {}).get(name)
    if isinstance(h, bytes):                        # 시연판: the bytes held in memory
        return h
    f = PDFS / f"{h}.pdf" if h else None
    return f.read_bytes() if f and f.exists() else None


def latest(day=None):
    """the latest submission of each permit number: {permit_no: summary with id}; with a day, only those whose work
    is on that day (a permit number's submission for another day says nothing of this one)"""
    if not KEEP:                                    # 시연판: the manager's view is the prepared demo data alone
        return {}
    with store._db() as c:
        c.executescript(_SCHEMA)
        rows = c.execute("SELECT id, permit_no, summary FROM submissions ORDER BY created").fetchall()
    out = {}
    for r in rows:
        s = json.loads(r["summary"])
        if r["permit_no"] and (day is None or day in (s.get("dates") or [])):
            out[r["permit_no"]] = {**s, "id": r["id"]}
    return out
