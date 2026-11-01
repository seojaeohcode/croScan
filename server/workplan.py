"""작업계획서 (daily work plan) PDFs -> one record per plan, for many files at once.

OpenDataLoader reads every file (one Java run per batch, page headers and footers included). The form's own
context does the rest: printed section titles, label | value table rows, the 확인 기록 grid, the header lines
(문서번호: … / 작업번호: … / 개정 …) and the footer ("문서 n / m쪽"). A value cell OpenDataLoader leaves empty is
filled from the PDF text layer inside that cell's box. Labels the spec does not know are kept under their own
name, so a changed or longer form still comes through. Pages are joined into plans by 문서번호, across files too.

Every value also gets a box on its page (the same page model as the permit editor: page image, background with
the values erased, one input per value), so a plan can be checked and edited on the form itself. The uploaded
files stay in a short-lived cache and the page images are drawn when the page is opened (page_png).
"""
import io
import json
import math
import os
import re
import shutil
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import opendataloader_pdf
import pymupdf

from . import workplan_pdf
from .extract import _page_chars, _pixmap
from .qa import DATA, KST, copy_with_floor

# printed labels of the form -> keys (only the ones later steps compute with need a key; the rest keep their label)
SECTIONS = ["문서와 수행업체", "작업 일정과 범위", "작업 위치와 연결", "인원 장비와 작업사양", "계획한 작업 순서", "공정 단계",
            "선행작업과 혼재 협의", "예비 확인 기록", "출입 대피와 이전 상태", "작업 종료와 검토 인계"]
KEYS = {"작업명": "title", "수행업체": "company", "작성자": "author", "책임자": "manager", "호선": "hull",
        "시작일시": "start", "종료일시": "end", "시간대": "tz", "작업상태": "status", "작업범위": "scope",
        "작업위치": "location", "대상ID": "target", "연결정보": "link", "도면자료": "drawing",
        "작업인원": "workers", "담당배치": "roles", "작업장비": "equipment", "사용물질": "material", "작업사양": "spec", "작업높이": "height",
        "공정단계": "process", "분류근거": "process_basis",
        "선행작업": "prior", "선행조건": "precondition", "혼재작업": "simops", "방호조치": "protection",
        "확인자": "checker", "기록근거": "record_basis", "유효조건": "valid_if",
        "출입구": "access", "통로대피": "evacuation", "이전상태": "transfer",
        "종료기록": "end_record", "해제기록": "release", "후속요건": "follow_up", "검토승인": "review"}
HEAD = {"문서번호": "doc_no", "작업번호": "work_no", "개정": "rev", "작성·발행": "issued", "계획일": "plan_date", "도면 배치 기준": "drawing_basis"}
INLINE = ["작업명", "공정단계", "분류근거"]                      # label and value printed in one line, outside a table
STEP = re.compile(r"^(\d+)\s*단계$")
NOTE = re.compile(r"\s*\[[^\]]*\]\s*$")                         # "[합성 계획]" after a section title
FOOT = re.compile(r"문서\s*(\d+)\s*/\s*(\d+)\s*쪽")
DT = re.compile(r"(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{1,2}):(\d{2}))?")
BATCH, WORKERS = 10, 4                                          # files per Java run, Java runs at once
CACHE, KEEP_H = DATA / "workplans", 24 * 7                       # uploads, plans and saved edits, kept 7 days
TOKEN = re.compile(r"^[0-9a-f]{32}$")


def _text(node):
    if node.get("content"):
        return node["content"].replace("・", "·").strip()          # same glyph in NanumGothic; the forms mean '·'
    return " ".join(t for k in node.get("kids") or [] if (t := _text(k)))


def _box(bb, H):
    l, b, r, t = bb
    return pymupdf.Rect(l, H - t, r, H - b)


def _head_fields(text):
    """'문서번호: X / 작업번호: Y / 개정 Z 작성·발행: …' -> {key: value} by the printed labels."""
    pat = re.compile("|".join(re.escape(k) + (r"\s*:" if k != "개정" else r"(?![가-힣])") for k in HEAD))
    hits = list(pat.finditer(text))
    out = {}
    for i, m in enumerate(hits):
        end = hits[i + 1].start() if i + 1 < len(hits) else len(text)
        label = re.sub(r"\s*:$", "", m.group(0)).strip()
        out[HEAD[label]] = re.sub(r"[\s/]+$", "", text[m.end():end]).strip()
    return out


def _section(text):
    t = NOTE.sub("", text).strip()
    return t if t in SECTIONS else None


class _Plan:
    def __init__(self, file):
        self.files, self.pages, self.head, self.items, self.grid, self.notes = [], [], {}, [], None, []
        self.add_file(file)

    def add_file(self, f):
        if f not in self.files:
            self.files.append(f)

    def put(self, section, label, value, page, src="odl", ref=None):
        label = re.sub(r"\s+", " ", label).strip()
        value = re.sub(r"\s+", " ", value or "").strip()
        same = [x for x in self.items if x["label"] == label]
        raw = {"value": value, "page": page, "src": src, "section": section}
        if same:                                                 # repeated on page 2 (작업명, 공정 단계): keep one
            same[0]["refs"].append(ref)
            same[0].setdefault("raw", []).append(raw)            # design §6.4: each cell as read, kept
            if value and not same[0]["value"]:
                same[0].update(value=value, page=page, src=src)
            elif value and value != same[0]["value"]:
                self.notes.append(f"'{label}' 값이 쪽마다 다름: '{same[0]['value']}' / '{value}'")
            return
        m = STEP.match(label)
        self.items.append({"section": section, "label": label, "value": value, "page": page, "src": src,
                           "key": KEYS.get(label) or (f"step{m.group(1)}" if m else None), "refs": [ref], "raw": [raw]})

    def doc(self, token):
        """The plan as an editor document: pages (images drawn on request) and one field per printed value.
        A value printed on several pages (작업명, header) is one field per page, linked through "same"."""
        pages = sorted(self.pages, key=lambda x: (x["of"] or (0, 0))[0])
        num = {id(x["P"]): k for k, x in enumerate(pages, 1)}
        fields, by_ref = {}, {}

        def add(fk, k, name, value, lay, section=None):
            fields[fk] = {"page": k, "key": fk.split(".", 1)[1], "name": name, "type": "text", "required": False,
                          "value": value, "original": value, "section": section}
            if lay:
                fields[fk]["layout"] = lay
            return fk

        heads = {}
        for x in pages:
            P, k = x["P"], num[id(x["P"])]
            for key, lab in ((v, l) for l, v in HEAD.items()):
                if key in P["head"] or key in P["head_lay"]:
                    heads.setdefault(key, []).append(add(f"p{k}.h_{key}", k, lab, P["head"].get(key, ""), P["head_lay"].get(key)))
            for i, r in enumerate(P["rows"]):
                by_ref[(id(P), i)] = add(f"p{k}.r{i}", k, re.sub(r"\s+", " ", r[1]).strip(),
                                          re.sub(r"\s+", " ", r[2] or "").strip(), r[4], r[0])
            if P["grid"]:
                for ri, (row, lays) in enumerate(zip(P["grid"]["rows"], P["grid"]["lays"])):
                    for ci, (v, lay) in enumerate(zip(row[1:], lays), 1):
                        fk = add(f"p{k}.g{ri}_{ci}", k, f"{row[0]} · {P['grid']['columns'][ci] if ci < len(P['grid']['columns']) else ci}",
                                 v, lay, P["grid"]["section"])
                        if P["grid"] is self.grid:
                            self.grid.setdefault("fks", {})[f"{ri}_{ci}"] = fk
        links = list(heads.values())
        for it in self.items:
            fks = [by_ref[r] for r in it["refs"] if r in by_ref]
            it["fk"] = fks[0] if fks else None
            links.append(fks)
        for fks in links:
            for fk in fks:
                fields[fk]["same"] = [o for o in fks if o != fk]
        self.head_fk = {k: v[0] for k, v in heads.items()}
        return {"pages": [{"no": num[id(x["P"])], "width": x["P"]["width"], "height": x["P"]["height"], "file": x["file"],
                           "src_page": x["page"], "of": x["of"],
                           "image": f"/api/workplans/{token}/{x['fi']}/{x['page']}.png",
                           "background": f"/api/workplans/{token}/{x['fi']}/{x['page']}.png?bg=1"} for x in pages],
                "fields": fields}

    def record(self, token=None):
        doc = self.doc(token) if token else None
        v = {x["key"]: x["value"] for x in self.items if x["key"]}
        pages = [{k: x[k] for k in ("file", "page", "of")} for x in sorted(self.pages, key=lambda x: (x["of"] or (0, 0))[0])]
        pages = [{**x, "fi": y["fi"]} for x, y in zip(pages, sorted(self.pages, key=lambda x: (x["of"] or (0, 0))[0]))]
        rec = {"files": self.files, "pages": pages, **{k: self.head.get(k, "") for k in HEAD.values()},
               "notice": next((x["P"]["notice"] for x in self.pages if x["P"].get("notice")), ""),
               "title": v.get("title", ""), "company": v.get("company", "").split(" / ")[0].strip(),
               "start": _iso(v.get("start")), "end": _iso(v.get("end")), "location": v.get("location", ""), "target": v.get("target", ""),
               "steps": [x["value"] for x in self.items if x["key"] and x["key"].startswith("step")],
               "items": [{k: x[k] for k in x if k != "refs"} for x in self.items],
               "grid": {k: g for k, g in (self.grid or {}).items() if k != "lays"} or None, "warnings": list(self.notes)}
        if doc:
            rec["doc"], rec["head_fk"] = doc, self.head_fk
        filled = sum(1 for x in self.items if x["value"])
        if not filled:
            rec["warnings"].append("빈 양식: 채워진 칸이 없음")
        for k, lab in (("start", "시작일시"), ("end", "종료일시")):
            if v.get(k) and not rec[k]:
                rec["warnings"].append(f"{lab} 형식을 읽지 못함: '{v[k]}'")
        if rec["start"] and rec["end"] and rec["end"] < rec["start"]:
            rec["warnings"].append("종료일시가 시작일시보다 빠름")
        return rec


def _iso(s):
    m = DT.search(s or "")
    if not m:
        return ""
    y, mo, d, h, mi = m.groups()
    try:
        return datetime(int(y), int(mo), int(d), int(h or 0), int(mi or 0)).strftime("%Y-%m-%dT%H:%M" if h else "%Y-%m-%d")
    except ValueError:
        return ""


def _pages(odl):
    """ODL top-level nodes grouped by page (header and footer kids flattened in place)."""
    pages = {}
    for n in odl.get("kids", []):
        p = n.get("page number")
        if n.get("type") in ("header", "footer"):
            for k in n.get("kids") or []:
                pages.setdefault(k.get("page number", p), []).append(k)
        else:
            pages.setdefault(p, []).append(n)
    return pages


def _lines(pg):
    """Text-layer words grouped into lines by their vertical centre (a value written as its own text object still
    lands on its label's line), left to right."""
    lines = []
    for w in sorted(pg.get_text("words"), key=lambda w: ((w[1] + w[3]) / 2, w[0])):
        yc, h = (w[1] + w[3]) / 2, w[3] - w[1]
        for L in lines:
            if abs(L["yc"] - yc) < 0.35 * max(h, L["h"]):
                L["w"].append(w)
                break
        else:
            lines.append({"yc": yc, "h": h, "w": [w]})
    for L in lines:
        L["w"].sort(key=lambda w: w[0])
        L["text"] = " ".join(w[4] for w in L["w"]).replace("・", "·")
    return sorted(lines, key=lambda L: L["yc"])


def _words_in(pg, rect):
    """Text-layer words whose centre lies in rect (a word only touching the cell edge belongs to the next cell)."""
    ws = [w for w in pg.get_text("words") if rect.contains(pymupdf.Point((w[0] + w[2]) / 2, (w[1] + w[3]) / 2))]
    return " ".join(w[4] for w in sorted(ws, key=lambda w: (round((w[1] + w[3]) / 2), w[0]))).replace("・", "·")


def _inside(r, ch):
    """Glyph centre inside rect r (plain numbers: Rect.contains is slow for thousands of glyphs)."""
    return r[0] <= ch["cx"] <= r[2] and r[1] <= ch["cy"] <= r[3]


def _chars(pg):
    cs = _page_chars(pg)
    for ch in cs:
        b = ch["box"]
        ch["cx"], ch["cy"] = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    return cs


def _lay(rect, chars, ref):
    """Input box for a value region: the value's own glyphs (centre inside the region) give size, font, indent and
    line pitch; an empty region takes them from `ref` (the label's glyphs). -> (layout, glyph boxes to erase)."""
    r = tuple(rect)
    got = [ch for ch in chars if _inside(r, ch)]
    src = got[0] if got else (ref[0] if ref else None)
    size = src["size"] if src else 9.0
    lines = sorted({round(ch["line"][1], 1) for ch in got})
    lay = {"box": [round(v, 2) for v in (rect.x0 + 1, rect.y0 + 1, rect.x1 - 1, rect.y1 - 1)], "size": size,
           "font": src["font"] if src else "", "bold": False, "align": "left",
           "pad": round(max(1.0, min(ch["box"][0] for ch in got) - rect.x0 - 1), 2) if got else 2.0, "multi": len(lines) > 1}
    if lay["multi"]:
        lay["lh"] = round(lines[1] - lines[0], 2)
        lay["top"] = round(max(0.0, min(ch["line"][1] for ch in got) - rect.y0 - 1), 2)
    bands = []                                              # one thin band through the middle of each value line
    for ch in sorted(got, key=lambda c: c["cy"]):
        if bands and abs(bands[-1][-1]["cy"] - ch["cy"]) < 0.4 * ch["size"]:
            bands[-1].append(ch)
        else:
            bands.append([ch])
    erase = []
    for cs in bands:
        cs.sort(key=lambda c: c["box"][0])
        first, last = cs[0]["box"], cs[-1]["box"]
        cy, h = sum(c["cy"] for c in cs) / len(cs), max(c["box"][3] - c["box"][1] for c in cs)
        erase.append([round(first[0] + 0.1 * (first[2] - first[0]), 2), round(cy - 0.12 * h, 2),
                      round(last[2] - 0.1 * (last[2] - last[0]), 2), round(cy + 0.12 * h, 2)])
    return lay, erase


def _frame(pg):
    """Right edge of the form and its vertical rules, measured on the page."""
    rects = [d["rect"] for d in pg.get_drawings()]
    wide = [r for r in rects if r.width > 0.5 * pg.rect.width]
    vert = sorted({round(r.x0, 1) for r in rects if r.width < 2 and r.height > 8})
    return (max(r.x1 for r in wide) if wide else pg.rect.width - 30), vert


def _line_chars(chars, L):
    return sorted([ch for ch in chars if abs(ch["cy"] - L["yc"]) < 0.5 * max(L["h"], ch["size"])],
                  key=lambda ch: ch["box"][0])


def _head_layout(chars, L, right):
    """Boxes of the header values: from a label's end to the next label (or its '/' separator), on that line."""
    cs = _line_chars(chars, L)
    text, idx = "", []
    for k, ch in enumerate(cs):
        if k and ch["box"][0] - cs[k - 1]["box"][2] > 0.25 * ch["size"]:
            text += " "; idx.append(None)
        text += ch["c"]; idx.append(ch)
    pat = re.compile("|".join(re.escape(k) + (r"\s*:" if k != "개정" else r"(?![가-힣])") for k in HEAD))
    hits = list(pat.finditer(text))
    out, erase = {}, []
    y0, y1 = min(ch["box"][1] for ch in cs) - 1, max(ch["box"][3] for ch in cs) + 1
    for i, m in enumerate(hits):
        key = HEAD[re.sub(r"\s*:$", "", m.group(0)).strip()]
        end = hits[i + 1].start() if i + 1 < len(hits) else len(text)
        seg = [c for c in idx[m.end():end] if c]
        while seg and seg[-1]["c"] == "/":                  # the '/' before the next label is printed text
            seg.pop()
        lab_end = max(c["box"][2] for c in idx[m.start():m.end()] if c)
        nxt = next((c for c in idx[m.end():end] if c and c["c"] == "/"), None) if i + 1 < len(hits) else None
        x1 = (nxt["box"][0] if nxt and (not seg or nxt["box"][0] >= seg[-1]["box"][2]) else
              min(c["box"][0] for c in idx[hits[i + 1].start():hits[i + 1].end()] if c) if i + 1 < len(hits) else right)
        rect = pymupdf.Rect(lab_end + 1, y0, max(x1 - 2, lab_end + 20), y1)
        lay, er = _lay(rect, seg, [c for c in idx[m.start():m.end()] if c])
        out[key] = lay
        erase += er
    return out, erase


def _inline_layout(chars, L, lab, right, vert):
    """작업명 / 공정단계 / 분류근거: the value runs from the next vertical rule (or just after the label) to the frame."""
    cs = _line_chars(chars, L)
    n = len(lab.replace(" ", ""))
    lab_cs, val_cs = cs[:n], cs[n:]
    lab_end = max(c["box"][2] for c in lab_cs) if lab_cs else L["w"][0][2]
    x0 = next((x for x in vert if lab_end < x < lab_end + 60), lab_end + 4)
    y0 = min([c["box"][1] for c in cs] or [L["yc"] - 6]) - 2
    y1 = max([c["box"][3] for c in cs] or [L["yc"] + 6]) + 2
    return _lay(pymupdf.Rect(x0 + 1, y0, right, y1), val_cs, lab_cs)


def _read_file(pdf_path, name, odl):
    """-> (pages: [{"no", "head", "foot", "is_plan", "rows": [(section, label, value, src)], "grid"}], error).
    Tables come from OpenDataLoader; the lines outside the tables (header, 작업명, 공정 단계, footer) and the section
    titles come from the text layer by position."""
    doc = pymupdf.open(pdf_path)
    nodes_of = _pages(odl)
    out = []
    for no in range(1, doc.page_count + 1):
        pg, H = doc[no - 1], doc[no - 1].rect.height
        P = {"no": no, "head": {}, "head_lay": {}, "foot": None, "is_plan": False, "rows": [], "grid": None,
             "erase": [], "width": pg.rect.width, "height": H, "notice": ""}
        chars = _chars(pg)
        right, vert = _frame(pg)
        titles = []                                                       # (y, section) on this page
        inline = []
        section = None
        for L in _lines(pg):
            text = L["text"]
            if "작업계획서" in text and len(text) < 40:
                P["is_plan"] = True
            if (m := FOOT.search(text)):
                P["foot"] = (int(m.group(1)), int(m.group(2)))
                P["notice"] = text[:m.start()].strip()                   # the footer's own sentence, kept for the 수정본
            if "문서번호" in text or "작성·발행" in text:
                P["head"].update(_head_fields(text))
                lays, er = _head_layout(chars, L, right)
                P["head_lay"].update(lays)
                P["erase"] += er
                continue
            if (sec := _section(text)):
                section = sec
                titles.append((L["yc"], sec))
                continue
            for lab in INLINE:
                if text == lab or text.startswith(lab + " "):
                    lay, er = _inline_layout(chars, L, lab, right, vert)
                    P["erase"] += er
                    inline.append((None if lab == "작업명" else section, lab, text[len(lab):], "text", lay))
                    break
        table_rows = []
        for n in nodes_of.get(no, []):
            if n.get("type") != "table":
                continue
            top = H - n["bounding box"][3] if n.get("bounding box") else 0
            section = next((sec for y, sec in reversed(titles) if y < top + 2), None)
            header = None
            for r in n.get("rows") or []:
                cells = sorted(r.get("cells") or [], key=lambda c: c.get("column number", 0))
                texts = [_text(c) for c in cells]
                boxes = [_box(c["bounding box"], H) if c.get("bounding box") else None for c in cells]
                lab_cs = [ch for ch in chars if boxes[0] and _inside(tuple(boxes[0]), ch)]
                if len(cells) == 2:                                       # label | value
                    val, src = texts[1], "odl"
                    if not val and boxes[1]:                              # ODL left it out: text layer in that cell
                        val, src = _words_in(pg, boxes[1]), "text"
                    if texts[0]:
                        lay = None
                        if boxes[1]:
                            lay, er = _lay(boxes[1], chars, lab_cs)
                            P["erase"] += er
                        table_rows.append((section, texts[0], val, src, lay))
                elif len(cells) > 2 and header is None:                   # a grid: first row names the columns
                    header = texts
                    P["grid"] = {"section": section, "columns": header, "rows": [], "lays": []}
                elif len(cells) > 2:
                    P["grid"]["rows"].append(texts)
                    lays = []
                    for b in boxes[1:]:
                        lay = None
                        if b:
                            lay, er = _lay(b, chars, lab_cs)
                            P["erase"] += er
                        lays.append(lay)
                    P["grid"]["lays"].append(lays)
        # 작업명 / 공정 단계 drawn as a table row: the cell (all its lines) wins over the text line beside the label
        in_table = {r[1] for r in table_rows}
        inline = [r for r in inline if r[1] not in in_table]
        P["rows"] = [r for r in inline if r[1] == "작업명"] + table_rows + [r for r in inline if r[1] != "작업명"]
        P["is_plan"] = P["is_plan"] or bool(P["head"])
        out.append(P)
    if not any(p["is_plan"] and (p["rows"] or p["head"]) for p in out):
        return out, "작업계획서 양식을 찾지 못함 (허가서나 다른 문서인지 확인)"
    return out, None


def _odl_batch(paths, td):
    opendataloader_pdf.convert(input_path=[str(p) for p in paths], output_dir=str(td), format="json", quiet=True,
                               include_header_footer=True, image_output="off")
    return {p: json.loads((Path(td) / f"{p.stem}.json").read_text(encoding="utf-8")) for p in paths}


def _odl_safe(chunk, out_dir):
    """ODL for a batch; if the batch fails, file by file so one bad PDF does not stop the rest."""
    out_dir.mkdir()
    try:
        return _odl_batch(chunk, out_dir)
    except Exception:
        got = {}
        for p in chunk:
            try:
                got.update(_odl_batch([p], out_dir))
            except Exception:
                pass
        return got


def stage(files):
    """Copy the uploads into a new token folder now (bytes, or an open binary file streamed to disk).
    -> (token, [(path, name)]). Done before the response streams, while the upload files are still open."""
    _clean_cache()
    token = uuid.uuid4().hex
    keep = CACHE / token
    keep.mkdir(parents=True)
    staged = []
    try:
        for i, (name, data) in enumerate(files):
            p = keep / f"wp{i:04d}.pdf"                                     # plain names: no clashes, no odd characters
            copy_with_floor(io.BytesIO(data) if isinstance(data, (bytes, bytearray)) else data, p)
            staged.append((p, name))
    except BaseException:
        shutil.rmtree(keep, ignore_errors=True)                             # nothing half-uploaded stays behind
        raise
    return token, staged


def read_many(files):
    """files: [(name, bytes or binary file)]. Same events as read_staged."""
    yield from read_staged(*stage(files))


def read_staged(token, staged):
    """Yields {"step": "wp_file", ...} as files are read, then {"step": "wp_done", "plans": [...], "files": [...]}.
    Several OpenDataLoader runs go side by side (one Java process reads its files one after another); plans keep
    the order of the uploaded files."""
    keep = CACHE / token
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        paths = [p for p, _ in staged]
        names = dict(staged)
        workers = max(1, min(WORKERS, os.cpu_count() or 1, len(paths)))
        size = max(1, min(BATCH, math.ceil(len(paths) / workers)))
        chunks = [paths[b:b + size] for b in range(0, len(paths), size)]
        read, seen, done = {}, set(), 0
        with ThreadPoolExecutor(workers) as ex:
            jobs = [ex.submit(_odl_safe, c, td / f"odl{k}") for k, c in enumerate(chunks)]
            for job in as_completed(jobs):
                odl = job.result()
                for p in chunks[jobs.index(job)]:
                    done += 1
                    if p not in odl:
                        read[p] = ([], "PDF를 읽지 못함")
                    else:
                        try:
                            read[p] = _read_file(p, names[p], odl[p])
                        except Exception as e:
                            read[p] = ([], f"읽기 실패: {e}")
                    pages, err = read[p]
                    seen |= {P["head"].get("doc_no") or f"{p}#{P['no']}" for P in pages if P["is_plan"] and not err and (P["foot"] or (1,))[0] == 1}
                    yield {"step": "wp_file", "i": done, "n": len(paths), "name": names[p], "plans": len(seen), "error": err}
        plans, order, report = {}, [], []
        for p in paths:                                                     # join in upload order
            pages, err = read[p]
            n0 = len(order)
            for P in pages:
                P["fi"] = int(p.stem[2:])
            if not err:
                _join(pages, names[p], plans, order)
            report.append({"name": names[p], "pages": len(pages), "plans": len(order) - n0, "error": err})
        erase = {f"{P['fi']}_{P['no']}": P["erase"] for pages, _ in read.values() for P in pages}
        (keep / "erase.json").write_text(json.dumps(erase), encoding="utf-8")
        recs = [plans[k].record(token) for k in order]
        (keep / "plans.json").write_text(json.dumps(recs, ensure_ascii=False), encoding="utf-8")
        yield {"step": "wp_done", "token": token, "plans": recs, "files": report}


_tok_lock = threading.Lock()      # cleanup and "this token is in use" never interleave (one server process)


def _touch(token):
    """A request uses this token: restart its KEEP_H under the cleanup lock. -> its folder, or None if gone.
    Cleanup re-reads the time under the same lock, so a folder touched here is never deleted afterwards."""
    if not TOKEN.match(token or ""):
        return None
    d = CACHE / token
    with _tok_lock:
        if not d.exists():
            return None
        os.utime(d)
    return d


def _clean_cache():
    """Delete token folders no request has used for KEEP_H (a vanished folder is skipped, not an error)."""
    if not CACHE.exists():
        return
    with _tok_lock:
        for d in list(CACHE.iterdir()):
            try:
                if time.time() - d.stat().st_mtime > KEEP_H * 3600:
                    shutil.rmtree(d, ignore_errors=True)
            except FileNotFoundError:
                pass


def page_png(token, fi, page, background):
    """A page of an uploaded 작업계획서 as PNG; background=True erases the values (the inputs sit there)."""
    if not _touch(token):
        return None
    done = CACHE / token / f"wp{int(fi):04d}_{page}{'_bg' if background else ''}.png"
    if done.exists():                                       # drawn before: no PDF to open
        return done.read_bytes()
    f = CACHE / token / f"wp{int(fi):04d}.pdf"
    if not f.exists():
        return None
    with pymupdf.open(f) as doc:
        if not 1 <= page <= doc.page_count:
            return None
        pg = doc[page - 1]
        if background:      # the value glyphs leave the page itself (rules, logo and labels stay), then it is drawn
            for b in json.loads((CACHE / token / "erase.json").read_text(encoding="utf-8")).get(f"{fi}_{page}", []):
                pg.add_redact_annot(pymupdf.Rect(b), fill=False)
            pg.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                                text=pymupdf.PDF_REDACT_TEXT_REMOVE)
        png = _pixmap(pg).tobytes("png")
    tmp = done.with_name(f"{done.name}.{uuid.uuid4().hex[:8]}.tmp")    # a whole file or none: another request may read it
    tmp.write_bytes(png)
    os.replace(tmp, done)
    return png


def _join(pages, name, plans, order):
    """Pages -> plans: same 문서번호 = same plan (also across files); without one, the footer's '문서 1 / n쪽' starts a plan."""
    cur = None
    for P in pages:
        if not P["is_plan"]:
            continue
        key = P["head"].get("doc_no") or None
        starts = P["foot"] and P["foot"][0] == 1
        if key and key in plans:
            cur = plans[key]
        elif key or cur is None or starts:
            key = key or f"{name}#{P['no']}"
            plans[key] = cur = _Plan(name)
            order.append(key)
        if P["foot"] and any(x["of"] == P["foot"] for x in cur.pages):          # the same page uploaded twice
            cur.notes.append(f"같은 쪽({P['foot'][0]}/{P['foot'][1]})이 또 들어와 뺌: {name} {P['no']}쪽")
            continue
        cur.add_file(name)
        cur.pages.append({"file": name, "page": P["no"], "of": P["foot"], "fi": P.get("fi"), "P": P})
        for k, v in P["head"].items():
            cur.head.setdefault(k, v)
        for i, (sec, lab, val, src, _) in enumerate(P["rows"]):
            cur.put(sec, lab, val, P["no"], src, (id(P), i))
        if P["grid"] and not cur.grid:
            cur.grid = P["grid"]


# ---------------------------------------------------------------- saved edits and the 수정본
def _dir(token):
    d = _touch(token)
    return d if d and (d / "plans.json").exists() else None


def save_edits(token, edits):
    """edits: {plan index: {field key: value}} (every changed value, sent whole each time). -> saved time or None.
    Only plans and fields that exist in this upload are accepted; anything else leaves the saved edits as they were."""
    d = _dir(token)
    if not d:
        return None
    if not all(str(i).isdigit() and isinstance(fs, dict) for i, fs in edits.items()):
        raise ValueError("{계획서 번호: {칸: 값}} 꼴이어야 합니다")
    recs = json.loads((d / "plans.json").read_text(encoding="utf-8"))
    for i, fs in edits.items():
        if int(i) >= len(recs):
            raise ValueError(f"계획서 {i}번이 없습니다")
        unknown = [k for k in fs if k not in recs[int(i)]["doc"]["fields"]]
        if unknown:
            raise ValueError(f"계획서 {i}번에 없는 칸: {', '.join(map(str, unknown[:3]))}")
    clean = {str(int(i)): {str(k): str(v) for k, v in fs.items()} for i, fs in edits.items()}
    tmp = d / f"edits.json.{uuid.uuid4().hex[:8]}.tmp"
    tmp.write_text(json.dumps(clean, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, d / "edits.json")                       # never a half-written file for the 수정본
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")


def load_edits(token):
    d = _dir(token)
    f = d / "edits.json" if d else None
    return json.loads(f.read_text(encoding="utf-8")) if f and f.exists() else {}


# ---------------------------------------------------------------- 읽기 연결 정정 (design §6.4, MAP_CELL)
# A label the form spec does not know keeps its own name (KEY None). What it means — which known item it is — is a
# reading of croScan's, corrected by the foreman: kept apart from his edits of values (another event), per upload.
TARGETS = {v: k for k, v in KEYS.items()}                       # key -> its printed label (the nodes a label can join)
STAMP = lambda: datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")


def unknown_labels(rec):
    """the plan's labels the spec does not know, with a value: [{label, value, section, page}]"""
    return [{"label": x["label"], "value": x["value"], "section": x.get("section"), "page": x.get("page")}
            for x in rec.get("items") or [] if not x.get("key") and x.get("value") and not STEP.match(x["label"])]


def load_maps(token):
    d = _dir(token)
    f = d / "maps.json" if d else None
    return json.loads(f.read_text(encoding="utf-8")) if f and f.exists() else {}


def save_map(token, plan, label, key, accept):
    """the foreman's answer to a reading link: label (of plan, an index) is the item key — or not. -> the maps of
    the upload, or None when it is gone. Only a label the plan has and a key of the spec are taken."""
    d = _dir(token)
    if not d:
        return None
    recs = json.loads((d / "plans.json").read_text(encoding="utf-8"))
    if not (isinstance(plan, int) and 0 <= plan < len(recs)) or key not in TARGETS:
        raise ValueError("없는 계획서나 칸입니다")
    if not any(x["label"] == label and not x.get("key") for x in recs[plan].get("items") or []):
        raise ValueError("그 계획서에 없는 칸 이름입니다")
    with _MAPS:
        maps = load_maps(token)
        maps.setdefault(str(plan), {})[label] = {"key": key, "status": "confirmed" if accept else "refused", "at": STAMP()}
        tmp = d / f"maps.json.{uuid.uuid4().hex[:8]}.tmp"
        tmp.write_text(json.dumps(maps, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, d / "maps.json")
    return maps


_MAPS = threading.Lock()


def mapped(rec, maps):
    """the plan record with the reading links the foreman confirmed: the label's value becomes that item's value
    where the item has none read directly (a value printed under the known label always stays)"""
    conf = {lab: m["key"] for lab, m in (maps or {}).items() if m.get("status") == "confirmed"}
    if not conf:
        return rec
    rec = {**rec, "items": [dict(x) for x in rec.get("items") or []]}
    have = {x["key"] for x in rec["items"] if x.get("key") and x.get("value")}
    for x in rec["items"]:
        k = conf.get(x["label"])
        if k and not x.get("key") and k not in have and x.get("value"):
            x["key"], x["mapped"] = k, True
            have.add(k)
    v = {x["key"]: x["value"] for x in rec["items"] if x.get("key")}
    for k in ("title", "location", "target"):
        if not rec.get(k) and v.get(k):
            rec[k] = v[k]
    if not rec.get("company") and v.get("company"):
        rec["company"] = v["company"].split(" / ")[0].strip()
    for k in ("start", "end"):
        if not rec.get(k) and v.get(k):
            rec[k] = _iso(v[k])
    return rec


def load_plans(token):
    """the upload's plans with the confirmed reading links applied (what later steps read), or None"""
    d = _dir(token)
    if not d:
        return None
    recs = json.loads((d / "plans.json").read_text(encoding="utf-8"))
    maps = load_maps(token)
    return [mapped(r, maps.get(str(i))) for i, r in enumerate(recs)]


def edited(rec, edits):
    """the plan record as the foreman corrected it in step 1 (his saved edits of its fields, as the 수정본 draws them):
    its fields, its items and what is read from them (title, place, start, end, steps). What links, imports and the
    analysis read from a plan is this one, never the values as first read."""
    if not edits:
        return rec
    F = (rec.get("doc") or {}).get("fields") or {}

    def val(fk, old):                                       # an edit of the field or of the same value on another page
        for k in [fk, *((F.get(fk) or {}).get("same") or [])] if fk else []:
            if k in edits:
                return re.sub(r"\s+", " ", str(edits[k])).strip()
        return old
    rec = {**rec, "items": [dict(x) for x in rec.get("items") or []]}
    if rec.get("doc"):
        rec["doc"] = {**rec["doc"], "fields": {k: {**f, "value": str(edits[k])} if k in edits else f for k, f in F.items()}}
    for x in rec["items"]:
        x["value"] = val(x.get("fk"), x.get("value"))
    for k, fk in (rec.get("head_fk") or {}).items():
        rec[k] = val(fk, rec.get(k, ""))
    v = {x["key"]: x["value"] for x in rec["items"] if x.get("key")}
    for k in ("title", "location", "target"):
        if k in v:
            rec[k] = v[k]
    if "company" in v:
        rec["company"] = v["company"].split(" / ")[0].strip()
    for k in ("start", "end"):
        if k in v:
            rec[k] = _iso(v[k])                             # a corrected time that cannot be read is no time
    rec["steps"] = [x["value"] for x in rec["items"] if x.get("key") and x["key"].startswith("step")] if rec["items"] else rec.get("steps") or []
    return rec


def plan_digest(rec, edits=None):
    """what a reading, a link and the values taken from a plan were made from: its fields as corrected and its
    items. A changed plan (an edit, a new reading link) gives another digest: what was made from it expires."""
    import hashlib
    f = {k: (edits or {}).get(k, v.get("value")) for k, v in ((rec.get("doc") or {}).get("fields") or {}).items()}
    it = [(x.get("label"), x.get("key"), x.get("value")) for x in rec.get("items") or []]
    return hashlib.sha256(json.dumps([f, it], ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


def _logo(d, rec):
    """The company logo from the plan's first uploaded page: (bytes, width, height) or None."""
    p0 = rec["pages"][0]
    src = pymupdf.open(d / f"wp{int(p0['fi']):04d}.pdf")[p0["page"] - 1]
    imgs = sorted(src.get_images(full=True), key=lambda im: (src.get_image_rects(im[0]) or [pymupdf.Rect(0, 1e9, 0, 1e9)])[0].y0)
    if not imgs or not src.get_image_rects(imgs[0][0]) or src.get_image_rects(imgs[0][0])[0].y0 > 120:
        return None
    xref, smask = imgs[0][0], imgs[0][1]
    pix = pymupdf.Pixmap(src.parent, xref)
    if smask:                                               # transparency kept in a separate mask image
        pix = pymupdf.Pixmap(pix, pymupdf.Pixmap(src.parent, smask))
    elif pix.n - pix.alpha > 3:                             # CMYK
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
    return pix.tobytes("png"), pix.width, pix.height


def _edit_count(rec, fs):
    F, seen, n = rec["doc"]["fields"], set(), 0
    for k, v in fs.items():
        if k in seen or k not in F or str(v) == str(F[k]["original"]):
            continue
        n += 1
        seen |= {k, *F[k].get("same", [])}
    return n


def edited_pdf(token, which=None):
    """The 수정본: one plan (index) or all, drawn with the saved edits. -> (pdf bytes, file name) or None."""
    d = _dir(token)
    if not d:
        return None
    recs = json.loads((d / "plans.json").read_text(encoding="utf-8"))
    idx = list(range(len(recs))) if which is None else [which]
    if any(not 0 <= i < len(recs) for i in idx):
        return None
    edits = load_edits(token)
    when = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    items, logos, notes = [], [], []
    for i in idx:
        fs = edits.get(str(i), {})
        items.append((recs[i], fs))
        logos.append(_logo(d, recs[i]))
        n = _edit_count(recs[i], fs)
        notes.append(f"수정본 {when} · 화면 수정 {n}건" if n else None)
    pdf = workplan_pdf.render(items, logos, notes)
    r = recs[idx[0]]
    name = (f"작업계획서_{r.get('work_no') or i}_{r.get('company') or ''}_수정본.pdf" if which is not None
            else f"작업계획서_{len(idx)}건_수정본.pdf")
    return pdf, re.sub(r"[\\/:*?\"<>|\s]+", "_", name)
