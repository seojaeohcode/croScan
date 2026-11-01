"""시연용 하루: 2026-10-29 대조립21공장의 바쁜 하루 (허가서 10건 + 작업계획서 40건 = 50건).

    python tools/make_demo_day.py make-permits   (Windows: the permit form is drawn with 맑은 고딕) 허가서 10건 → PDF
    python tools/make_demo_day.py make-plans     작업계획서 40건 → PDF (the 6 companies' blank forms filled in)
    python tools/make_demo_day.py permits        (server, app image: ODL) read back, the 작업반장's answers, 위험 체크리스트 → DB
    python tools/make_demo_day.py plans          (server) read back → DB

Data (designed with Codex from the research PDF; see demo_day.md):
  samples/시연_하루/permits.json    the 10 permits with the 작업반장's true answers
  samples/시연_하루/skeleton.json   the 40 plans' outline, the clash pairs and near-misses
  samples/시연_하루/workplans.json  the 40 plans with every label filled in
Writes into samples/시연_하루/:
  허가서/      one 안전부서 제출용 permit per file (tools/make_form.py draw_page), 2 per kind, A = careless, B = careful
  작업계획서/  one plan per file (2 pages), the 6 companies' blank forms filled in
  demo_day.sqlite3   the day as the 안전관리자 view will read it:
                     permits    fields as croScan read them back, the 작업반장's answers to the multi-turn
                                questions (from the scenario's true answers), what stayed open, the 위험 체크리스트
                                (croScan's draft from the permit alone, confirmed by the 작업반장), the 추가검토서 layout
                     workplans  the plans as croScan read them back
                     clashes, near_misses   the pairs built into the day (truth for the 안전관리자 demo)
  report.json  read-back check: every value written must come back the same
"""
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "tools"))
_DATA = Path(tempfile.mkdtemp(prefix="croscan_demo_data_"))
os.environ.setdefault("CROSCAN_DATA", str(_DATA))          # plan uploads made here go to a throwaway folder

import pymupdf  # noqa: E402
from server import addendum, augment, checklist, extract, reflect  # noqa: E402
from server import workplan as W  # noqa: E402
from server.permit_kinds import KINDS  # noqa: E402

DIR = APP / "samples" / "시연_하루"
def load(name):
    return json.loads((DIR / name).read_text(encoding="utf-8"))
BLANK = APP / "samples" / "작업계획서" / "빈양식"
FONT = next(p for p in (Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf"), Path("C:/Windows/Fonts/malgun.ttf")) if p.exists())
GRID = ("공간·대상", "위험요소", "방호 상태", "가동·위험 기간", "위험 종료")
HEAD = (("문서번호:", "doc_no"), ("작업번호:", "work_no"), ("개정", "rev"), ("작성·발행:", "issued"), ("계획일:", "plan_date"),
        ("도면 배치 기준:", "drawing_basis"))
PERMIT_EXTRA = {"answers_truth", "case_note", "note", "story", "id"}


# ---------------------------------------------------------------- 작업계획서: a company's blank form, filled in
def fill_plan(wp):
    """The 2-page plan with the scenario's values written in the cells, and what was written (the truth)."""
    d = pymupdf.open(BLANK / f"작업계획서_빈양식_{wp.get('form', wp['company'])}.pdf")
    items, written, grid = wp["items"], {}, []
    rows = {r[0]: r[1:] for r in wp.get("grid", [])}
    for pg in d:
        lines = [ln for b in pg.get_text("dict")["blocks"] for ln in b.get("lines", []) if ln["bbox"][0] < 100]

        def put(x, y_mid, text, size=9.2):
            pg.insert_text((x, y_mid + size * 0.36), text, fontsize=size, fontname="demofill", fontfile=str(FONT))

        for lab, key in HEAD:
            r = pg.search_for(lab)
            if r and wp["head"].get(key):
                put(r[0].x1 + 3, (r[0].y0 + r[0].y1) / 2, wp["head"][key], 10)
        for ln in lines:
            lab = "".join(s["text"] for s in ln["spans"]).strip()
            ymid = (ln["bbox"][1] + ln["bbox"][3]) / 2
            if lab in GRID:
                vals = [str(v) for v in (list(rows.get(lab, [])) + ["", "", ""])[:3]]
                for x, t in zip((129.5, 293.5, 426.5), vals):
                    if t:
                        put(x, ymid, t, 8.8)
                grid.append([lab] + vals)
                continue
            if lab == "확인 항목" or not any("Bold" in s["font"] for s in ln["spans"]) or ln["spans"][0]["size"] > 10:
                continue
            if lab in written:                            # 작업명, 공정 단계 again on page 2: the same value
                v = written[lab]
                if isinstance(items.get(lab), list):
                    put(111.2, ymid - 4.5, items[lab][0], 8.2); put(111.2, ymid + 4.5, items[lab][1], 8.2)
                elif v:
                    put(111.2, ymid, v)
                continue
            v = items.get(lab, "")
            if isinstance(v, list):
                put(111.2, ymid - 4.5, v[0], 8.2)
                put(111.2, ymid + 4.5, v[1], 8.2)
                v = " ".join(v)
            elif v:
                put(111.2, ymid, v)
            written[lab] = v
    d.set_metadata({"title": f"작업계획서 {wp['head']['doc_no']}", "subject": "시연용 합성 작업계획서 (교육·시연용)",
                    "creator": "croScan make_demo_day.py"})
    return d, {"head": wp["head"], "items": written, "grid": grid}


def check_plans(plans, truths):
    by = {p["doc_no"]: p for p in plans}
    bad = []
    for t in truths:
        p = by.get(t["head"]["doc_no"])
        if not p:
            bad.append((t["head"]["doc_no"], "계획서를 못 찾음"))
            continue
        for k, v in t["head"].items():
            if p.get(k) != v:
                bad.append((t["head"]["doc_no"], f"머리 {k}: {p.get(k)!r} != {v!r}"))
        got = {x["label"]: x["value"] for x in p["items"]}
        for lab, v in t["items"].items():
            if got.get(lab, "") != v:
                bad.append((t["head"]["doc_no"], f"{lab}: {got.get(lab, '<없음>')!r} != {v!r}"))
        g = [r for r in (p["grid"] or {}).get("rows", [])]
        if g != t["grid"]:
            bad.append((t["head"]["doc_no"], f"확인 기록 표: {g} != {t['grid']}"))
    return bad


# ---------------------------------------------------------------- 허가서: read back, answer, checklist
def norm(x):
    return re.sub(r"\s+", " ", str(x if x is not None else "")).strip()


def check_permit(doc, t):
    P = augment._permits(doc["fields"])[0]
    bad = []
    for k, v in t.items():
        if k in ("kind", "days", "checks") or not isinstance(v, str) or not v:
            continue
        got = augment._v(P["p"], k)
        if k in P["p"] and norm(got) != norm(v):
            bad.append((t["permit_no"], f"{k}: {got!r} != {v!r}"))
    for i, (day, a, b) in enumerate(t.get("days", []), 1):
        got = tuple(augment._v(P["p"], f"{x}_{i}") for x in ("date", "from", "to"))
        if got != (day, a, b):
            bad.append((t["permit_no"], f"작업일시 {i}: {got} != {(day, a, b)}"))
    return bad


def converse(fields, truth_ans, pno):
    """The 작업반장 answers croScan's questions as the scenario says (a question the scenario has no answer for is
    「모름」), until croScan has nothing more to ask. The same rounds as on the page, without the closing free text."""
    answers, asked, log = [], set(), []
    for _ in range(12):
        s = augment.summary(fields, answers)
        # an optional question (tier extra) is answered only when the scenario has the answer; otherwise skipped
        qs = [q for q in s["questions"] if q["qid"] not in asked
              and (q.get("tier") != "extra" or q["item"] in truth_ans or q["item"].split(".")[0] in truth_ans)]
        if not qs:
            break
        q = qs[0]
        asked.add(q["qid"])
        item = q["item"]
        t = truth_ans.get(item) or truth_ans.get(item.split(".")[0])
        ids = [c["id"] for c in q.get("choices", [])]
        ch = t and (t.get("choice") if t.get("choice") in ids else next((c for c in ("place", "text", "value") if c in ids and t.get("value")), None))
        if ch:
            a = {"qid": q["qid"], "choice": ch, "value": t.get("value", ""), "q": q}
        elif "unknown" in ids:
            a = {"qid": q["qid"], "choice": "unknown", "value": "", "q": q}
        else:
            log.append((pno, item, "답할 보기가 없음", ids))
            continue
        err = augment.check_value(fields, a)
        if err:                                           # the value is not readable: once more as 「모름」
            log.append((pno, item, f"값 오류: {err}", a["value"]))
            if "unknown" in ids:
                a = {"qid": q["qid"], "choice": "unknown", "value": "", "q": q}
            else:
                continue
        answers.append(a)
    s = augment.summary(fields, answers)
    return answers, s, log


SCHEMA = """
  CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
  CREATE TABLE IF NOT EXISTS permits(permit_no TEXT PRIMARY KEY, kind TEXT, label TEXT, case_type TEXT, file TEXT, place TEXT,
    windows TEXT, fields TEXT, answers TEXT, open_questions TEXT, records TEXT, checklist TEXT, addendum TEXT, truth TEXT);
  CREATE TABLE IF NOT EXISTS workplans(doc_no TEXT PRIMARY KEY, company TEXT, file TEXT, title TEXT, start TEXT, end_ TEXT,
    location TEXT, record TEXT, truth TEXT);
  CREATE TABLE IF NOT EXISTS clashes(id TEXT PRIMARY KEY, a TEXT, b TEXT, type TEXT, priority INTEGER, why TEXT, data TEXT);
  CREATE TABLE IF NOT EXISTS near_misses(id TEXT PRIMARY KEY, a TEXT, b TEXT, why TEXT, data TEXT);
"""


def truth(d, kind):
    """What the generator wrote on one page (the same as tools/make_form.py truth, which needs the Windows fonts to import)."""
    t = {k: v for k, v in d.items() if k not in ("checks", "stamp", "days", "kind", "ptw_box", "case", "expect", "core", "extra", "assumed")}
    t["kind"], t["days"], t["checks"] = kind, [list(x) for x in d.get("days", [])], sorted(d.get("checks", {}))
    return t


def permit_name(d):
    return f"{d['permit_no'][-4:]}_{KINDS[d['kind']]['label'].replace('·', '')}_{d.get('case', '')}.pdf"


def demo_qr(text):
    """A QR-looking mark for the PTW box (QA #6: the real permit has one): finder squares and modules from a hash of
    the permit number. It encodes nothing and links to no PTW system (시연용)."""
    import hashlib
    n, cell = 25, 4
    bits = bin(int(hashlib.sha256(text.encode()).hexdigest() * 3, 16))[2:]
    d = pymupdf.open()
    pg = d.new_page(width=n * cell, height=n * cell)
    finder = lambda r, c: any(r0 <= r < r0 + 7 and c0 <= c < c0 + 7 for r0, c0 in ((0, 0), (0, n - 7), (n - 7, 0)))
    for r in range(n):
        for c in range(n):
            if finder(r, c):
                rr, cc = r % (n - 7) if r >= n - 7 else r, c % (n - 7) if c >= n - 7 else c
                on = max(abs(rr - 3), abs(cc - 3)) in (0, 1, 3)
            else:
                on = bits[(r * n + c) % len(bits)] == "1"
            if on:
                pg.draw_rect(pymupdf.Rect(c * cell, r * cell, (c + 1) * cell, (r + 1) * cell), color=None, fill=(0, 0, 0))
    return pg.get_pixmap(dpi=144).tobytes("png")


def make_permits():
    from make_form import draw_page, save
    pdir = DIR / "허가서"
    shutil.rmtree(pdir, ignore_errors=True)
    pdir.mkdir(parents=True, exist_ok=True)          # OneDrive can keep the emptied folder for a moment
    for d in load("permits.json")["permits"]:
        data = {k: v for k, v in d.items() if k not in PERMIT_EXTRA}
        one = pymupdf.open()
        draw_page(one, data, "submit", {"qr": demo_qr(d["permit_no"])})
        one.set_metadata({"title": KINDS[d["kind"]]["title"], "subject": "시연용 합성 허가서 (교육·시연용)", "creator": "croScan make_demo_day.py"})
        save(one, pdir / permit_name(d))
        print("허가서", permit_name(d))


def make_plans():
    wdir = DIR / "작업계획서"
    shutil.rmtree(wdir, ignore_errors=True)
    wdir.mkdir(parents=True)
    truths = {}
    for wp in load("workplans.json")["workplans"]:
        doc, t = fill_plan(wp)
        name = f"{wp['head']['doc_no']}_{wp['company']}.pdf"
        doc.subset_fonts()                            # only the glyphs written (the full Korean font is 7 MB per file)
        doc.save(wdir / name, garbage=4, deflate=True)
        truths[name] = t
    (DIR / "workplans_truth.json").write_text(json.dumps(truths, ensure_ascii=False, indent=1), encoding="utf-8")
    print("작업계획서", len(truths))


def build_permits(db, report):
    day = load("permits.json")
    pdir = DIR / "허가서"
    db.execute("DELETE FROM permits")
    db.executemany("INSERT OR REPLACE INTO meta VALUES (?, ?)", [("date", day["date"]), ("factory", day.get("factory", "")),
                                                                 ("permits", str(len(day["permits"])))])
    for d in day["permits"]:
        data = {k: v for k, v in d.items() if k not in PERMIT_EXTRA}
        kind, name = data["kind"], permit_name(d)
        t = truth(data, kind)
        doc = extract.build(pdir / name, kind)
        bad = check_permit(doc, t)
        report["bad"] += bad
        answers, s, log = converse(doc["fields"], d.get("answers_truth", {}), d["permit_no"])
        report["log"] += log
        ck = checklist.draft(doc["fields"], answers)        # from the permit alone: its values and the answers
        for P in ck["permits"]:
            for it in P["items"]:
                it["touched"] = True                       # the 작업반장 confirmed croScan's draft as it was
        P0 = s["effective"][0]
        s["reflect"] = reflect.plan(doc["fields"], answers)        # the 반영본 as the 작업반장's submit makes it (QA #37)
        sheets = addendum.build(s, doc["fields"])
        db.execute("INSERT INTO permits VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            d["permit_no"], kind, KINDS[kind]["label"], d.get("case", ""), f"허가서/{name}", P0["place"]["text"],
            json.dumps(P0["windows"], ensure_ascii=False), json.dumps(doc["fields"], ensure_ascii=False),
            json.dumps([{**{k: v for k, v in a.items() if k != "q"}, "text": a["q"].get("text", "")} for a in answers], ensure_ascii=False),
            json.dumps(s["questions"], ensure_ascii=False), json.dumps(s["records"], ensure_ascii=False),
            json.dumps(ck, ensure_ascii=False), json.dumps([L for _, _, L in sheets], ensure_ascii=False), json.dumps(t, ensure_ascii=False)))
        n = {x: sum(it["state"] == x for P in ck["permits"] for it in P["items"]) for x in checklist.STATES}
        report["permits"].append({"permit_no": d["permit_no"], "kind": kind, "case": d.get("case"), "file": name, "read_errors": len(bad),
                                  "answers": len(answers), "open": len(s["questions"]), "checklist": n})
        print(f"허가서 {name}: 읽기 오류 {len(bad)}, 답 {len(answers)}, 남은 질문 {len(s['questions'])}, 체크리스트 {n}", flush=True)
    if (DIR / "skeleton.json").exists():
        build_pairs(db, load("skeleton.json"))


def build_pairs(db, sk):
    db.execute("DELETE FROM clashes")
    db.execute("DELETE FROM near_misses")
    for i, c in enumerate(sk.get("clashes", []), 1):
        db.execute("INSERT INTO clashes VALUES (?,?,?,?,?,?,?)", (str(c.get("id") or f"C{i:02d}"), str(c.get("a", "")), str(c.get("b", "")),
                                                                  c.get("type", ""), c.get("priority"), c.get("why", ""), json.dumps(c, ensure_ascii=False)))
    for i, c in enumerate(sk.get("near_misses", []), 1):
        db.execute("INSERT INTO near_misses VALUES (?,?,?,?,?)", (str(c.get("id") or f"N{i:02d}"), str(c.get("a", "")), str(c.get("b", "")),
                                                                  c.get("why", ""), json.dumps(c, ensure_ascii=False)))


def build_plans(db, report):
    wps = load("workplans.json")["workplans"]
    wdir = DIR / "작업계획서"
    tr = load("workplans_truth.json")
    db.execute("DELETE FROM workplans")
    files, truths = [], []
    for wp in wps:
        name = f"{wp['head']['doc_no']}_{wp['company']}.pdf"
        files.append((name, (wdir / name).read_bytes()))
        truths.append(tr[name])
    done = list(W.read_many(files))[-1]
    bad = check_plans(done.get("plans", []), truths)
    report["bad"] += bad
    by = {p["doc_no"]: p for p in done.get("plans", [])}
    for wp, t in zip(wps, truths):
        p = by.get(wp["head"]["doc_no"], {})
        rec = {k: v for k, v in p.items() if k not in ("doc", "head_fk")}
        db.execute("INSERT INTO workplans VALUES (?,?,?,?,?,?,?,?,?)", (
            wp["head"]["doc_no"], wp["company"], f"작업계획서/{wp['head']['doc_no']}_{wp['company']}.pdf", p.get("title", ""),
            p.get("start", ""), p.get("end", ""), p.get("location", ""), json.dumps(rec, ensure_ascii=False), json.dumps(t, ensure_ascii=False)))
        report["workplans"].append({"doc_no": wp["head"]["doc_no"], "company": wp["company"], "read": bool(p)})
    db.execute("INSERT OR REPLACE INTO meta VALUES ('workplans', ?)", (str(len(wps)),))
    if (DIR / "skeleton.json").exists():
        build_pairs(db, load("skeleton.json"))
    print(f"작업계획서 {len(files)}건 → 읽음 {len(by)}건, 값 오류 {len(bad)}", flush=True)


def main():
    part = sys.argv[1] if len(sys.argv) > 1 else "all"
    if part.startswith("make-"):
        (make_permits if part == "make-permits" else make_plans)()
        return 0
    report = {"permits": [], "workplans": [], "bad": [], "log": []}
    db = sqlite3.connect(DIR / "demo_day.sqlite3")
    db.executescript(SCHEMA)
    db.execute("INSERT OR REPLACE INTO meta VALUES ('source', 'samples/시연_하루 (Codex·Claude 합성, 조사자료 기반)')")
    if part in ("permits", "all"):
        build_permits(db, report)
    if part in ("plans", "all"):
        build_plans(db, report)
    db.commit()
    db.close()
    (DIR / f"report_{part}.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    for b in report["bad"][:30]:
        print("  읽기 차이:", b)
    for b in report["log"][:30]:
        print("  대화:", b)
    print(f"끝 ({part}): 허가서 {len(report['permits'])} · 작업계획서 {len(report['workplans'])} · 읽기 차이 {len(report['bad'])}")
    shutil.rmtree(_DATA, ignore_errors=True)
    return 0 if not report["bad"] else 1


if __name__ == "__main__":
    sys.exit(main())
