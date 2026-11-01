"""Electronic permit PDF -> form model for the web editor.

OpenDataLoader (Hancom, local mode) is the reader: it gives the table, each cell's
row / column / span / box and the paragraphs inside. The PDF's own text layer
(PyMuPDF) only fills in text that OpenDataLoader left out of a cell.
The form spec then turns paragraphs into typed fields.

Output:
  pages[]: width, height (pt), page image, cells[] with box + paragraphs made of
           segments ({"t": "text"} / {"t": "field", "key"} / {"t": "check", "key"}),
           texts outside the table
  fields{}: "p1.permit_no" -> name, type, required, value, original, page, group
"""
import base64
import json
import re
import tempfile
from pathlib import Path

import opendataloader_pdf
import pymupdf

from . import form_spec as S
from . import permit_kinds as PK

TEXT_TYPES = ("paragraph", "heading", "caption", "list item", "text block")
GLYPHS = {"☐": False, "□": False, "■": True, "☑": True}


def _norm(s):
    return re.sub(r"\s+", "", s or "")


def run_odl(pdf_path):
    with tempfile.TemporaryDirectory() as td:
        opendataloader_pdf.convert(input_path=[str(pdf_path)], output_dir=td, format="json", quiet=True)
        return json.loads(next(Path(td).glob("*.json")).read_text(encoding="utf-8"))


def _walk(node, page=None):
    if isinstance(node, dict):
        p = node.get("page number", page)
        yield node, p
        for k in ("kids", "rows", "cells", "list items"):
            for ch in node.get(k) or []:
                yield from _walk(ch, p)
    elif isinstance(node, list):
        for ch in node:
            yield from _walk(ch, page)


def _box(bb, H):
    l, b, r, t = bb
    return [round(l, 2), round(H - t, 2), round(r, 2), round(H - b, 2)]


class Page:
    def __init__(self, no, page, odl_json):
        self.no, self.W, self.H = no, page.rect.width, page.rect.height
        self.cells, self.outside = [], []
        used = set()
        roff = 0
        for tb, p in _walk(odl_json.get("kids", [])):
            if tb.get("type") != "table" or p != no:
                continue
            for el, _ in _walk(tb):
                if el.get("type") != "table cell":
                    continue
                c = {"id": len(self.cells), "r": el["row number"] + roff, "c": el["column number"],
                     "rs": el.get("row span", 1), "cs": el.get("column span", 1),
                     "box": _box(el["bounding box"], self.H), "paras": [], "images": [], "src": []}
                for sub, _ in _walk(el.get("kids", [])):
                    used.add(id(sub))
                    if sub.get("type") == "image" and sub.get("bounding box"):
                        c["images"].append(_box(sub["bounding box"], self.H))
                    elif sub.get("type") in TEXT_TYPES and sub.get("content"):
                        c["paras"].append(sub["content"].strip())
                        c["src"].append("odl")
                self.cells.append(c)
            roff += tb.get("number of rows", 0)
        for el, p in _walk(odl_json.get("kids", [])):
            if p == no and id(el) not in used and el.get("type") in TEXT_TYPES and el.get("content") \
                    and el.get("bounding box") and not self._in_table(_box(el["bounding box"], self.H)):
                self.outside.append({"box": _box(el["bounding box"], self.H), "text": el["content"].strip()})
        self._fill_from_text_layer(page)

    def _in_table(self, box):
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        return any(c["box"][0] <= cx <= c["box"][2] and c["box"][1] <= cy <= c["box"][3] for c in self.cells)

    def _fill_from_text_layer(self, page):
        """Text the PDF text layer has inside a cell but OpenDataLoader did not deliver.
        Works per character: a text-layer line can run across a cell border when two
        cells' texts share a baseline, so only the characters inside the cell count."""
        lines = []
        for b in page.get_text("rawdict")["blocks"]:
            for l in b.get("lines", []):
                lines.append([(ch["c"], ch["bbox"]) for sp in l["spans"] for ch in sp["chars"]])
        for c in self.cells:
            have = _norm(" ".join(c["paras"]))
            x0, y0, x1, y1 = c["box"]
            for chars in lines:
                t = "".join(ch for ch, (a, b_, cc, d) in chars
                            if x0 <= (a + cc) / 2 <= x1 and y0 <= (b_ + d) / 2 <= y1).strip()
                if t and _norm(t) not in have:
                    c["paras"].append(t)
                    c["src"].append("pdf")
                    have += _norm(t)

    # grid relations
    def at(self, r, col):
        for c in self.cells:
            if c["r"] <= r < c["r"] + c["rs"] and c["c"] <= col < c["c"] + c["cs"]:
                return c
        return None

    def below(self, c):
        return self.at(c["r"] + c["rs"], c["c"])

    def right(self, c):
        return self.at(c["r"], c["c"] + c["cs"])

    def find(self, pattern):
        rx = re.compile(pattern)
        for c in self.cells:
            for i, p in enumerate(c["paras"]):
                if rx.search(p):
                    return c, i
        return None, None


VARIANTS = {"submit": "안전부서 제출용", "posting": "현장 게시용"}


def _variant(page, pg):
    """Copy type of a page: the printed header ([안전부서 제출용] / [현장 게시용]) decides;
    without a header, the 안전대면허가 row (printed only on the submitted copy) does.
    Returns (variant, how it was decided)."""
    text = _norm(pg.get_text()) + _norm(" ".join(o["text"] for o in page.outside))
    has_face_row = page.find(r"안전대면허가")[0] is not None
    head = "posting" if "현장게시용" in text else "submit" if "안전부서제출용" in text else None
    if head:
        how = f"머리글 [{VARIANTS[head]}]"
        if (head == "posting") == has_face_row:
            how += " · 칸 구성은 " + ("제출용(안전대면허가 칸 있음)" if has_face_row else "게시용(안전대면허가 칸 없음)") + "과 같음 - 확인 필요"
        return head, how
    v = "submit" if has_face_row else "posting"
    return v, "머리글 없음 → " + ("안전대면허가 칸이 있어 제출용" if has_face_row else "안전대면허가 칸이 없어 게시용") + "으로 판단"


def _permits(pages, fields):
    """Pages grouped by 승인번호: one number on several pages = copies of one permit."""
    groups = {}
    for p in pages:
        no = str(fields.get(f"p{p['no']}.permit_no", {}).get("value", "")).strip().upper()
        groups.setdefault(no or f"(번호 없음 {p['no']}쪽)", []).append(p["no"])
    return [{"permit_no": k, "pages": v, "copies": [pages[i - 1]["variant"] for i in v]} for k, v in groups.items()]


def build(pdf_path, kind, odl=None):
    """kind: the permit kind the applicant picked (key of permit_kinds.KINDS) for every page,
    or a list with one kind per page (tools/check_extract.py grades mixed files)."""
    pdf_path = Path(pdf_path)
    odl = odl if odl is not None else run_odl(pdf_path)
    doc = pymupdf.open(pdf_path)
    names = {k: (n, t, req) for k, n, t, req in S.FIELDS}
    out = {"file": pdf_path.name, "pages": [], "fields": {}}
    for no, pg in enumerate(doc, 1):
        page = Page(no, pg, odl)
        page_kind = kind[no - 1] if isinstance(kind, (list, tuple)) else kind
        # every paragraph starts as plain text; mapping replaces parts with fields
        segs = {c["id"]: [[{"t": "text", "s": p}] for p in c["paras"]] for c in page.cells}
        fields = {}

        def add(key, value, ftype=None, extra=None):
            n, t, req = names.get(key, (key, ftype or "text", False))
            fk = f"p{no}.{key}"
            fields[fk] = {"page": no, "key": key, "name": n, "type": ftype or t, "required": req,
                          "value": value, "original": value, "kind": page_kind, **(extra or {})}
            return fk

        def put_cell(c, key, ftype=None, name=None):
            """The whole cell is the value."""
            if c is None:
                return
            if c["images"] and (ftype or names.get(key, (0, ""))[1]) == "image":
                fk = add(key, "", "image", {"image": c["images"][0]})
            else:
                fk = add(key, " ".join(c["paras"]).strip(), ftype)
                if name:
                    fields[fk]["name"] = name
            segs[c["id"]] = [[{"t": "field", "key": fk}]]

        # inline: label + value (+ fixed tail) in one paragraph
        for key, lab in S.INLINE.items():
            c, i = page.find(lab)
            if c is None:
                continue
            p = c["paras"][i]
            m = re.search(lab, p)
            rest = p[m.end():]
            tail = ""
            if key in S.INLINE_TAIL:
                mt = re.search(r"\s*" + S.INLINE_TAIL[key] + r"\s*$", rest)
                if mt:
                    tail, rest = rest[mt.start():], rest[:mt.start()]
            # the value may continue in the next paragraph of the same cell (wrapped line)
            extra_paras = []
            if key in ("job", "location") and i + 1 < len(c["paras"]):
                extra_paras = c["paras"][i + 1:]
            value = " ".join([rest.strip()] + [e.strip() for e in extra_paras]).strip()
            fk = add(key, value)
            segs[c["id"]][i] = [{"t": "text", "s": p[:m.end()]}, {"t": "field", "key": fk}] + \
                               ([{"t": "text", "s": tail}] if tail else [])
            for j in range(i + 1, i + 1 + len(extra_paras)):
                segs[c["id"]][j] = []
        # value lines of this kind's 추가정보 block: between the printed label and unit
        for key, a, b, vname in PK.values(page_kind):
            c, i = page.find(a)
            if c is None:
                continue
            p = c["paras"][i]
            ma = re.search(a, p)
            mb = re.search(b, p[ma.end():])
            end = ma.end() + (mb.start() if mb else len(p) - ma.end())
            fk = add(key, p[ma.end():end].strip(), "number",
                     {"name": vname, "required": key in PK.KINDS[page_kind]["required"]})
            segs[c["id"]][i] = [{"t": "text", "s": p[:ma.end()]}, {"t": "field", "key": fk},
                                {"t": "text", "s": p[end:]}]
        # whole cells next to a label cell
        for key, lab in S.CELL_BELOW.items():
            c, _ = page.find(lab)
            if c is not None:
                put_cell(page.below(c), key)
        for key, lab in S.CELL_RIGHT.items():
            c, _ = page.find(lab)
            if c is not None:
                put_cell(page.right(c), key)
        for key, lab in S.PHONE_ROW.items():
            c, _ = page.find(lab)
            ph = page.right(c) if c is not None else None
            if ph is None:
                continue
            for i, p in enumerate(ph["paras"]):
                m = re.search(r"연락처\s*:\s*(.*?)\s*(/\s*TRS\s*:.*)?$", p)
                if m:
                    fk = add(key, m.group(1).strip())
                    segs[ph["id"]][i] = [{"t": "text", "s": "연락처: "}, {"t": "field", "key": fk},
                                         {"t": "text", "s": " " + (m.group(2) or "/ TRS:")}]
                    break
        # work-date table: cells under the three headers, down to the hazards band
        heads = [page.find(r"일\s*\(DATE\)")[0], page.find(r"시작\s*\(FROM\)")[0], page.find(r"종료\s*\(TO\)")[0]]
        if all(heads):
            cur = list(heads)
            for row in range(1, S.DATE_ROWS + 1):
                cur = [page.below(h) for h in cur]
                if not all(cur) or any(re.search("유해위험요소", " ".join(c["paras"])) for c in cur):
                    break
                for c, (k, t, n) in zip(cur, (("date", "date", "작업일"), ("from", "time", "시작"), ("to", "time", "종료"))):
                    put_cell(c, f"{k}_{row}", t, f"{row}일차 {n}")
        # sign-off rows
        for lab, keys in S.SIGN_ROWS.items():
            c, _ = page.find(lab)
            if c is None:
                continue
            name_c = page.right(c)
            when_label = page.right(name_c) if name_c else None
            date_c = page.right(when_label) if when_label else None
            sign_label = page.right(date_c) if date_c else None
            sign_c = page.right(sign_label) if sign_label else None
            for cell, key in zip((name_c, date_c, sign_c), keys):
                put_cell(cell, key, "image" if cell is not None and cell["images"] and not cell["paras"] else None)
        # 2중점검 대상 : Y
        c, i = page.find(S.DOUBLE_CHECK)
        if c is not None:
            p = c["paras"][i]
            m = re.search(S.DOUBLE_CHECK, p)
            fk = add("double_check", p[m.end():].strip())
            segs[c["id"]][i] = [{"t": "text", "s": p[:m.end()] + " "}, {"t": "field", "key": fk}]
        c, _ = page.find(S.EXTRA_MEASURES)
        if c is not None:
            put_cell(page.below(c), "extra_measures")
        # checkboxes: glyph + item text, several per paragraph possible
        item_rx = [(k, re.compile(r"([☐□■☑])\s*(" + r"\s*".join(re.escape(ch) for ch in item if not ch.isspace()) + ")"), item, grp)
                   for k, item, grp in S.CHECKS + PK.checks(page_kind)]
        for c in page.cells:
            for i in range(len(c["paras"])):
                new = []
                for sg in segs[c["id"]][i]:       # only plain-text parts (a field may share the line)
                    p = sg.get("s", "")
                    if sg["t"] != "text" or not any(g in p for g in GLYPHS):
                        new.append(sg); continue
                    hits = []
                    for k, rx, item, grp in item_rx:
                        m = rx.search(p)
                        if m and f"p{no}.{k}" not in fields:
                            hits.append((m.start(), m.end(1), k, item, grp, GLYPHS[m.group(1)]))
                    hits.sort()
                    pos = 0
                    for start, gend, k, item, grp, val in hits:
                        if start < pos:
                            continue
                        if start > pos:
                            new.append({"t": "text", "s": p[pos:start]})
                        fk = add(k, val, "check", {"group": grp})
                        fields[fk]["name"] = item
                        new.append({"t": "check", "key": fk})
                        pos = gend
                    if p[pos:]:
                        new.append({"t": "text", "s": p[pos:]})
                segs[c["id"]][i] = new
        # where each editable value sits on the printed page; those glyphs are erased
        # from the background so the input can take their place
        erase = _layout(pg, page, segs, fields)
        for f in fields.values():
            f["value"] = f["original"] = _cast(f["type"], f["value"])
        variant, how = _variant(page, pg)
        out["pages"].append({
            "no": no, "variant": variant, "variant_label": VARIANTS[variant], "variant_how": how,
            "kind": page_kind, "kind_label": PK.KINDS[page_kind]["label"], "kind_title": PK.KINDS[page_kind]["title"],
            "permit_no": fields.get(f"p{no}.permit_no", {}).get("value", ""),
            "width": page.W, "height": page.H,
            "image": _png(pg), "background": _png(pg, erase),
        })
        out["fields"].update(fields)
    out["permits"] = _permits(out["pages"], out["fields"])
    return out


def _cast(ftype, v):
    if ftype == "check":
        return bool(v)
    v = (v or "").strip() if isinstance(v, str) else v
    if ftype == "count":
        m = re.search(r"\d+", v or "")
        return m.group(0) if m else ""
    if ftype == "yn":
        return v.upper() if v and v.upper() in ("Y", "N") else (v or "")
    return v or ""


# ---------------------------------------------------------------- layout on the printed page
READONLY = {"double_check"}      # system-printed next to the QR code: shown as printed
SCALE = 3                        # page images at 3x (216 dpi) so zooming stays sharp


def _png(page, erase=()):
    return "data:image/png;base64," + base64.b64encode(_pixmap(page, erase).tobytes("png")).decode()


def _pixmap(page, erase=()):
    """Page image; with `erase`, those glyph boxes are painted over in the colour of
    the paper around them (the PDF itself is not rewritten, so nothing else changes)."""
    pix = page.get_pixmap(matrix=pymupdf.Matrix(SCALE, SCALE))
    for r in erase:
        x0, y0, x1, y1 = int(r[0] * SCALE) - 1, int(r[1] * SCALE), int(r[2] * SCALE) + 2, int(r[3] * SCALE) + 2
        ring = [(x, y) for x in range(x0, x1, 2) for y in (y0 - 2, y1 + 1)] +                [(x, y) for y in range(y0, y1, 2) for x in (x0 - 2, x1 + 1)]
        ring = [pix.pixel(x, y) for x, y in ring if 0 <= x < pix.width and 0 <= y < pix.height]
        if ring:
            pix.set_rect(pymupdf.IRect(x0, y0, x1, y1), max(set(ring), key=ring.count))
    return pix


def _page_chars(pg):
    out = []
    for b in pg.get_text("rawdict")["blocks"]:
        for l in b.get("lines", []):
            for sp in l["spans"]:
                for ch in sp["chars"]:
                    if ch["c"].strip():
                        out.append({"c": ch["c"], "box": ch["bbox"], "size": sp["size"], "line": tuple(l["bbox"]),
                                    "font": sp["font"], "bold": bool(sp["flags"] & 16) or "bold" in sp["font"].lower()})
    return out


def _same_line(a, b):
    return abs((a["line"][1] + a["line"][3]) - (b["line"][1] + b["line"][3])) < 4


def _layout(pg, page, segs, fields):
    """Walk each cell's text-layer characters in the order of its segments (printed
    text, field values, checkbox glyphs) and give every editable field a box:
    the value's own characters, extended to the next printed word or the cell edge;
    an empty value takes the gap after its label. Returns glyph boxes to erase."""
    chars = _page_chars(pg)
    erase = []
    for c in page.cells:
        seq = [sg for para in segs[c["id"]] for sg in para]
        if c["images"] or not any(sg["t"] != "text" for sg in seq):
            continue
        x0, y0, x1, y1 = c["box"]
        cc = [ch for ch in chars if x0 - 1 <= (ch["box"][0] + ch["box"][2]) / 2 <= x1 + 1
              and y0 - 1 <= (ch["box"][1] + ch["box"][3]) / 2 <= y1 + 1]
        cc.sort(key=lambda ch: (ch["line"][1], ch["line"][0], ch["box"][0]))
        placed, i = [], 0
        for sg in seq:
            if sg["t"] == "text":
                want = _norm(sg["s"])
            elif sg["t"] == "field":
                want = _norm(str(fields[sg["key"]]["value"]))
            else:
                want = "□"
            got = cc[i:i + len(want)]
            i += len(want)
            if sg["t"] != "check" and "".join(ch["c"] for ch in got) != want:
                got = []                              # text layer disagrees: no glyphs to erase here
            placed.append((sg, got))
        whole = len(seq) == 1
        for k, (sg, got) in enumerate(placed):
            if sg["t"] == "text":
                continue
            f = fields[sg["key"]]
            if f["type"] == "image" or f["key"] in READONLY:
                continue
            if sg["t"] == "check":
                if got:
                    f["layout"] = {"box": [round(v, 2) for v in got[0]["box"]], "size": got[0]["size"], "font": got[0]["font"]}
                    erase.append(got[0]["box"])
                continue
            prev = next((g[-1] for _, g in reversed(placed[:k]) if g), None)
            nxt = next((g[0] for _, g in placed[k + 1:] if g), None)
            ref = got[0] if got else prev or nxt
            size = ref["size"] if ref else 8.0
            lay = {"size": size, "align": "left", "pad": 2.0, "multi": False,
                   "font": ref["font"] if ref else "", "bold": bool(got and got[0]["bold"])}
            lines = sorted({ch["line"][1] for ch in got})
            if whole:
                box = [x0 + 1, y0 + 1, x1 - 1, y1 - 1]
                if got:
                    gx0, gx1 = min(ch["box"][0] for ch in got), max(ch["box"][2] for ch in got)
                    if abs((gx0 + gx1) / 2 - (x0 + x1) / 2) < 0.12 * (x1 - x0) and gx0 - x0 > 6:
                        lay["align"] = "center"
                    else:
                        lay["pad"] = max(1.0, gx0 - x0 - 1)
                lay["multi"] = f["type"] == "text" and (len(lines) > 1 or y1 - y0 > 2.6 * size)
                if lay["multi"]:
                    lay["top"] = (got[0]["line"][1] - y0 - 1) if got else 2.0
                    lay["lh"] = (lines[1] - lines[0]) if len(lines) > 1 else size * 1.3
            else:
                if got:
                    bx0 = got[0]["box"][0]
                    by0, by1 = min(ch["line"][1] for ch in got), max(ch["line"][3] for ch in got)
                elif ref:
                    bx0 = prev["box"][2] + 2 if prev else x0 + 2
                    by0, by1 = ref["line"][1], ref["line"][3]
                else:
                    bx0, by0, by1 = x0 + 2, (y0 + y1) / 2 - 5, (y0 + y1) / 2 + 5
                line_ref = got[-1] if got else ref
                bx1 = nxt["box"][0] - 2 if nxt and line_ref and _same_line(nxt, line_ref) else x1 - 2
                lay["pad"] = 1.0
                if len(lines) > 1:                    # value wraps onto the next line(s)
                    lay["multi"] = True
                    lay["lh"] = lines[1] - lines[0]
                    lay["indent"] = bx0 - (x0 + 2)
                    bx0, bx1 = x0 + 2, x1 - 2
                    lay["top"] = 0.0
                box = [bx0 - 1, by0, max(bx1, bx0 + 24), by1]
            lay["box"] = [round(v, 2) for v in box]
            if got:                                   # the value's own glyphs: what a 반영본 replacement removes (QA #37)
                lay["glyphs"] = [[round(v, 2) for v in ch["box"]] for ch in got]
            f["layout"] = lay
            erase += [ch["box"] for ch in got]
    return erase
