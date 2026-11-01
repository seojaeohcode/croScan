"""작업계획서 as a PDF again, from a plan's fields (the edited values): the 수정본 download, and the clean form.

It is the same form the plans come in (same items, order, sections, header lines, company logo, footer), drawn
tidily: one frame width for header, tables and footer; titles and values centred in their bars and cells; single
rules; long values wrap inside their cell; 공정 단계 as a table like every other section. server/workplan.py
reads it back to the same values (tools/stress_workplan.py checks the round trip).
"""
import re
from pathlib import Path

import pymupdf

FONTS = [(Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf"), Path("/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf")),
         (Path("C:/Windows/Fonts/malgun.ttf"), Path("C:/Windows/Fonts/malgunbd.ttf"))]
W, H = 595.0, 842.0
X0, X1, XL = 38.6, 556.6, 108.3                    # frame, end of the label column
BOTTOM = 792.0
SIZE, SMALL, TITLE = 9.2, 8.4, 10.9
ROW, BAR, GAP, PAD = 19.0, 21.0, 7.0, 4.5
LINE, INK, GREY_LINE, BAR_FILL = 0.6, (0, 0, 0), (0.35, 0.35, 0.35), (0.878, 0.89, 0.902)     # bar #E0E3E6
RED = (0.86, 0.0, 0.0)
GRID_COLS = [X0, 126.6, 290.6, 423.6, X1]          # 확인 항목 | 확인값 | 확인시각 | 유효범위
HEAD_LINES = [[("문서번호:", "doc_no", 96), ("/ 작업번호:", "work_no", 36), ("/ 개정", "rev", 64)],
              [("작성·발행:", "issued", 62), ("/ 계획일:", "plan_date", 62), ("/ 도면 배치 기준:", "drawing_basis", 50)]]
NOTICE = "합성 시연 계획입니다. 회사 공식 발행·현장 관측 기록이 아닙니다."


class _Doc:
    def __init__(self):
        reg, bold = next(((r, b) for r, b in FONTS if r.exists() and b.exists()), (None, None))
        self.f = {False: pymupdf.Font(fontfile=str(reg)) if reg else pymupdf.Font("korea"),
                  True: pymupdf.Font(fontfile=str(bold)) if bold else pymupdf.Font("korea")}
        self.pdf = pymupdf.open()
        self.page = None

    def new_page(self):
        self.page = self.pdf.new_page(width=W, height=H)
        for name, f in (("kr", self.f[False]), ("krb", self.f[True])):
            self.page.insert_font(fontname=name, fontbuffer=f.buffer)
        return self.page

    def width(self, t, size, bold=False):
        return self.f[bold].text_length(t, fontsize=size)

    def text(self, x, cy, t, size=SIZE, bold=False, align="left", w=0, color=INK):
        """One line whose glyphs are centred on cy (centre of the em box between ascender and descender)."""
        if not t:
            return
        f = self.f[bold]
        tw = self.width(t, size, bold)
        if align == "center":
            x += (w - tw) / 2
        elif align == "right":
            x -= tw
        base = cy + (f.ascender + f.descender) / 2 * size
        self.page.insert_text((x, base), t, fontsize=size, fontname="krb" if bold else "kr", color=color)

    def hline(self, y, x0=X0, x1=X1, w=LINE, color=GREY_LINE):
        self.page.draw_line((x0, y), (x1, y), color=color, width=w)

    def vline(self, x, y0, y1):
        self.page.draw_line((x, y0), (x, y1), color=GREY_LINE, width=LINE)

    def wrap(self, t, width, size):
        """Lines of t that fit width (break between words; a word longer than the line breaks by letters)."""
        lines, cur = [], ""
        for word in re.findall(r"\S+", t or ""):
            cand = f"{cur} {word}" if cur else word
            if self.width(cand, size) <= width:
                cur = cand
                continue
            if cur:
                lines.append(cur)
            cur = ""
            while self.width(word, size) > width:
                k = len(word)
                while k > 1 and self.width(word[:k], size) > width:
                    k -= 1
                lines.append(word[:k])
                word = word[k:]
            cur = word
        return lines + [cur] if cur else lines or [""]


def _value_lines(d, v, width):
    """(lines, size, row height): one line at 9.2pt, or wrapped lines at 8.4pt in a taller row."""
    if d.width(v, SIZE) <= width:
        return [v], SIZE, ROW
    lines = d.wrap(v, width, SMALL)
    return lines, SMALL, max(ROW, len(lines) * SMALL * 1.25 + 7)


def render(plans, logos=None, notes=None):
    """plans: [(record, values)] where values = {field key: value} (edits applied). logos: [(png/jpeg bytes, w, h) or None].
    notes: footer note per plan (e.g. '수정본 … · 화면 수정 3건'). -> PDF bytes, every plan on its own pages."""
    d = _Doc()
    for n, (rec, values) in enumerate(plans):
        _plan(d, rec, values, (logos or [None] * len(plans))[n], (notes or [None] * len(plans))[n])
    d.pdf.subset_fonts()
    fix_tounicode(d.pdf)
    return d.pdf.tobytes(garbage=3, deflate=True)


LOOKALIKE = [(rb"<30[fF][bB]>", b"<00B7>"),          # '・' -> '·'
             (rb"<00[aA]0>", b"<0020>")]              # no-break space -> space


def fix_tounicode(pdf):
    """NanumGothic draws some characters with one shared glyph ('·' and '・', space and no-break space), and a subset
    font's text layer then reads the glyph back as the other one. Our forms only write '·' and plain spaces: point
    those glyphs back to them, so copied or searched text is what was written."""
    for x in range(1, pdf.xref_length()):
        kind, ref = pdf.xref_get_key(x, "ToUnicode")
        if kind != "xref":
            continue
        tu = int(ref.split()[0])
        cmap = pdf.xref_stream(tu)
        new = cmap
        for pat, rep in LOOKALIKE:
            new = re.sub(pat, rep, new) if new else new
        if new != cmap:
            pdf.update_stream(tu, new)


def _plan(d, rec, values, logo, note):
    doc = rec["doc"]
    F = doc["fields"]
    val = lambda fk: str(values.get(fk, F[fk]["value"]) if fk in F else "")
    first_page = len(d.pdf)
    pages = sorted({f["page"] for f in F.values()})
    head = {k.split("_", 1)[1]: fk for fk in F if (k := fk.split(".", 1)[1]).startswith("h_") and F[fk]["page"] == pages[0]}
    grid = rec.get("grid") or {}
    gfks = grid.get("fks") or {}
    y = 0

    def page_top():
        nonlocal y
        p = d.new_page()
        if logo:                                                # at most 24pt high and 140pt wide: the title stays put
            data, w, h = logo
            lh = min(24.0, 140.0 * h / w)
            p.insert_image(pymupdf.Rect(X0, 55.8 - lh / 2, X0 + lh * w / h, 55.8 + lh / 2), stream=data)
        d.text(X0 + 154, 55.8, "선박 작업계획서", TITLE)
        d.text(X1, 55.8, "작업계획서", TITLE, align="right")
        p.draw_rect(pymupdf.Rect(X0, 71.4, X1, 74.6), color=None, fill=RED, width=0)
        for row, cy in zip(HEAD_LINES, (89.7, 108.1)):
            x = X0 + 1
            for label, key, blank in row:
                d.text(x, cy, label + " ", 10)                       # a real space: the text layer keeps label and value apart
                x += d.width(label + " ", 10) + 1
                v = val(head[key]) if key in head else ""
                d.text(x, cy, v, 10)
                x += (d.width(v, 10) if v else blank) + 6         # a blank value keeps room to write in
        y = 119.8

    def room(h):
        nonlocal y
        if y + h > BOTTOM:
            page_top()
            return True
        return False

    def bar(title):
        nonlocal y
        room(GAP + BAR + ROW)
        y += GAP
        d.page.draw_rect(pymupdf.Rect(X0, y, X1, y + BAR), color=None, fill=BAR_FILL, width=0)
        d.hline(y, w=1.6, color=(0.33, 0.33, 0.33))
        d.hline(y + BAR, w=1.0, color=(0.33, 0.33, 0.33))
        d.text(X0 + 6, y + BAR / 2, title, TITLE, bold=True)
        y += BAR

    def kv(label, v, tall=None):
        nonlocal y
        lines, size, h = _value_lines(d, v, X1 - XL - 2 * PAD)
        h = max(h, tall or 0)
        if room(h):
            d.hline(y)
        d.text(X0, y + h / 2, label, SIZE, bold=True, align="center", w=XL - X0)
        lh = size * 1.25
        for i, t in enumerate(lines):
            d.text(XL + PAD, y + h / 2 + (i - (len(lines) - 1) / 2) * lh, t, size)
        d.vline(XL, y, y + h)
        d.hline(y + h)
        y += h

    def grid_table():
        nonlocal y
        cols = grid.get("columns") or []
        rows = grid.get("rows") or []
        widths = [GRID_COLS[i + 1] - GRID_COLS[i] - 2 * PAD for i in range(4)]

        def line(cells, bold):
            nonlocal y
            fitted = [_value_lines(d, c, widths[i]) for i, c in enumerate(cells[:4])]
            h = max(f[2] for f in fitted)
            if room(h):
                d.hline(y)
            for i, (lines, size, _) in enumerate(fitted):
                for k, t in enumerate(lines):
                    d.text(GRID_COLS[i] + PAD, y + h / 2 + (k - (len(lines) - 1) / 2) * size * 1.25, t, size, bold=bold)
                if i:
                    d.vline(GRID_COLS[i], y, y + h)
            d.hline(y + h)
            y += h
        line(cols, True)
        for ri, r in enumerate(rows):
            line([r[0]] + [val(gfks[f"{ri}_{ci}"]) if f"{ri}_{ci}" in gfks else (r[ci] if ci < len(r) else "") for ci in range(1, 4)], False)

    grid_page = F[next(iter(gfks.values()))]["page"] if gfks else None
    for k in pages:
        page_top()
        rows = [(fk, f) for fk, f in F.items() if f["page"] == k and re.match(r"r\d+$", fk.split(".", 1)[1])]
        section, grid_done = "", k != grid_page
        for fk, f in rows:
            sec = f.get("section")
            if sec is None:                                           # 작업명: its own row under the header
                d.hline(y)
                kv(f["name"], val(fk), tall=30)
                continue
            if sec != section:
                bar(sec)
                section = sec
            if not grid_done and sec == grid.get("section"):         # the grid opens its section (확인 기록 표)
                grid_table()
                grid_done = True
            kv(f["name"], val(fk))
        if not grid_done:                                             # a section that is only the grid
            bar(grid["section"])
            grid_table()
    total = len(d.pdf) - first_page
    for i in range(total):
        p = d.pdf[first_page + i]
        d.page = p
        d.text(X0, 816, rec.get("notice") or NOTICE, 6.5)
        right = f"문서 {i + 1} / {total}쪽"
        d.text(X1, 816, right, 7.5, align="right")
        if note:
            d.text(X1 - d.width(right, 7.5) - 12, 816, note, 6.5, align="right", color=(0.35, 0.35, 0.35))
