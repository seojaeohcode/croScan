"""Draw the 기타위험(밀폐)작업 허가서 as an electronic PDF, laid out after the printed
permit photographed in the domain-mentoring file (cell grid, wording, typos such as
'REQUSTED' kept as printed). Hand additions on the paper (highlighter, pen underlines)
are not part of the form and are not drawn. Names and numbers stay masked (XX).

    python tools/make_form.py
      -> samples/반장_테스트/<kind>_<A|B>_07xx.pdf     작업반장 test set: 2 permits per kind, the way the 실물 were filled in
         samples/시연/06xx_<kind>.pdf                 5 synthetic 대조립 permits that clash (for the later 안전관리자 view)
         samples/보관/합성_대조립_허가신청_5건.pdf     archive: the same 5 in one file
         samples/보관/위험작업신고서_양식.pdf          archive: the two photographed permits (밀폐)
         samples/보관/위험작업허가서_빈양식_5종.pdf     archive: blank form of each kind
         samples/_truth.json                          what was written, for tools/check_extract.py

Photographed permits: page 1 = [안전부서 제출용], page 2 = [현장 게시용] (no 안전대면허가 row).
Boxes: □ empty, ■ set by the system. The pen ticks on the printout's day-of-work
sections ("당일 작업시작 전 기입(사전 작성금지)") were made on site after printing, so
the electronic form leaves those boxes empty. Location "28-32 칼럼": the glyph matches
the printed 8 in "A0000948", not the B in "2BAY".
Handwriting, signatures and QR codes are the image crops from the earlier restored PDF.
"""
import json
import sys
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from server.permit_kinds import KINDS  # noqa: E402  (one definition for the generator and the extractor)
FONTS = Path("C:/Windows/Fonts")
REG = pymupdf.Font(fontfile=str(FONTS / "malgun.ttf"))
BOLD = pymupdf.Font(fontfile=str(FONTS / "malgunbd.ttf"))
SYM = pymupdf.Font(fontfile=str(FONTS / "seguisym.ttf"))
LOGO = ROOT / "web" / "croscan_logo.png"

BLACK, WHITE = (0, 0, 0), (1, 1, 1)
BLUE = (0.13, 0.36, 0.71)
HEAD = (0.88, 0.89, 0.90)          # shaded header rows
LABEL = (0.94, 0.94, 0.95)         # shaded label cells of the sign-off block

# grid (pt) - A4, table 30..565
L, R = 30, 565
XA, XB, XC = 208, 401, 497          # title | 승인번호 | 허가구분 label | value ;  left block | date block
XD1, XD2 = 457, 509                 # 일 | 시작 | 종료
XP = 499                            # 병행여부 column
XS = 287                            # site safety two columns
XE1, XE2 = 176, 329                 # 추가정보 three columns
XI = [30, 87, 172, 247, 318, 396, 462, 565]   # 발행 columns


class Writer:
    """Text with per-character font fallback (Malgun Gothic, then Segoe UI Symbol)."""

    def __init__(self, page):
        self.page = page
        self.tw = {}

    def width(self, s, size, bold=False):
        f = BOLD if bold else REG
        return sum((f if f.has_glyph(ord(c)) else SYM).text_length(c, size) for c in s)

    def put(self, x, y, s, size=8.5, bold=False, color=BLACK, font=None):
        tw = self.tw.setdefault(color, pymupdf.TextWriter(self.page.rect, color=color))
        base = font or (BOLD if bold else REG)
        run, rf = "", None
        for c in s:
            f = base if base.has_glyph(ord(c)) or c == " " else SYM
            if f is not rf and run:
                x = tw.append((x, y), run, font=rf, fontsize=size)[1].x
                run = ""
            run, rf = run + c, f
        if run:
            x = tw.append((x, y), run, font=rf, fontsize=size)[1].x
        return x

    def cell(self, rect, s, size=8.5, bold=False, align="left", color=BLACK, pad=3, dy=0):
        x0, y0, x1, y1 = rect
        lines = s.split("\n")
        lh = size * 1.25
        top = (y0 + y1) / 2 - lh * len(lines) / 2
        for i, ln in enumerate(lines):
            w = self.width(ln, size, bold)
            x = x0 + pad if align == "left" else x1 - pad - w if align == "right" else (x0 + x1 - w) / 2
            self.put(x, top + lh * i + size * 0.98 + dy, ln, size, bold, color)

    def fit(self, rect, s, size=8.5, bold=False, align="left", pad=3, min_size=6.0):
        """One line, shrunk until it fits; if it still does not, wrapped onto two lines.
        A cell tall enough for two lines wraps first and keeps the size."""
        avail = rect[2] - rect[0] - 2 * pad
        if rect[3] - rect[1] >= 2.4 * size:
            min_size = size
        while size > min_size and self.width(s, size, bold) > avail:
            size -= 0.25
        if self.width(s, size, bold) <= avail:
            return self.cell(rect, s, size, bold, align, pad=pad)
        words, a = s.split(" "), ""
        for k in range(len(words), 0, -1):
            a = " ".join(words[:k])
            if self.width(a, size, bold) <= avail:
                break
        return self.cell(rect, a + "\n" + s[len(a):].strip(), size, bold, align, pad=pad)

    def flush(self):
        for tw in self.tw.values():
            tw.write_text(self.page)


SEGMENTS = {}      # page -> set of border segments, drawn once per page as plain lines


def box(page, rect, fill=None):
    """A table cell: background as a fill-only rectangle, borders as separate line
    segments (a stroked + filled rectangle is read as decoration, not as a table)."""
    x0, y0, x1, y1 = (round(v, 2) for v in rect)
    if fill is not None:
        page.draw_rect(pymupdf.Rect(x0, y0, x1, y1), color=None, fill=fill, width=0)
    seg = SEGMENTS.setdefault(page, set())
    seg |= {((x0, y0), (x1, y0)), ((x0, y1), (x1, y1)), ((x0, y0), (x0, y1)), ((x1, y0), (x1, y1))}


def borders(page):
    for a, b in sorted(SEGMENTS.pop(page, ())):
        page.draw_line(a, b, color=BLACK, width=0.6)


def logo(page, w):
    """croScan logo where the printout has its company mark: same top-left corner and height (28.8 pt)."""
    page.insert_image(pymupdf.Rect(33.0, 31.6, 33.0 + 28.8 * 538 / 128, 60.4), filename=str(LOGO))


def checkbox(v):
    return "■" if v == "set" else "□"


def draw_page(doc, d, copy, images, kind=None):
    """d: values of one permit (empty dict = blank form); copy: 'submit' | 'posting';
    kind: key of server.permit_kinds.KINDS (title and 추가정보 block)."""
    K = KINDS[kind or d.get("kind", "confined")]
    title_ko, title_en = K["title"], K["title_en"]
    page = doc.new_page(width=595, height=842)
    w = Writer(page)
    g = lambda k, dflt="": d.get(k, dflt)
    ck = d.get("checks", {})
    cb = lambda k: checkbox(ck.get(k))

    # logo + copy label
    logo(page, w)
    label = "[안전부서 제출용]" if copy == "submit" else "[현장 게시용]"
    w.put(R - w.width(label, 8.5, True), 73, label, 8.5, bold=True)

    # header block
    y = 78
    box(page, (L, y, XA, y + 69), BLUE)
    title_size = 13
    while title_ko and w.width(title_ko, title_size, True) > XA - L - 10:
        title_size -= 0.25
    w.cell((L, y + 4, XA, y + 34), title_ko, title_size, True, "center", WHITE)
    en_size = 9.5
    while title_en and w.width(title_en, en_size, True) > XA - L - 10:
        en_size -= 0.25
    w.cell((L, y + 36, XA, y + 64), title_en, en_size, True, "center", WHITE)
    for (x0, x1, yy, h) in [(XA, XB, y, 23), (XB, XC, y, 23), (XC, R, y, 23), (XA, R, y + 23, 23), (XA, R, y + 46, 23)]:
        box(page, (x0, yy, x1, yy + h))
    w.cell((XA, y, XB, y + 23), "승인번호(PERMIT NO.):", 8.5)
    w.fit((XA + 94, y, XB, y + 23), g("permit_no"), 8.5, pad=1)
    w.cell((XB, y, XC, y + 23), "허가구분(PERMIT TYPE)", 8.5, align="center")
    w.fit((XC, y, R, y + 23), g("permit_type"), 8, align="center", pad=2)
    w.cell((XA, y + 23, R, y + 46), "호선/공사(HULL NO):", 8.5)
    w.cell((XA + 94, y + 23, R, y + 46), g("hull_no"), 8.5)
    w.cell((XA, y + 46, R, y + 69), "작업표준(JSP NO.):", 8.5)
    w.cell((XA + 94, y + 46, R, y + 69), g("jsp_no"), 8.5)

    # location / job / people  |  work date block
    y = 147
    box(page, (L, y, XB, y + 22)); w.cell((L, y, XB, y + 22), "작업장소(LOCATION):", 8.5)
    w.fit((134, y, XB, y + 22), g("location"), 8.5, pad=0)
    box(page, (L, y + 22, XB, y + 61)); w.fit((L, y + 22, XB, y + 61), g("location_detail"), 8.5)
    box(page, (XB, y, R, y + 44))
    w.cell((XB, y + 4, R, y + 22), "작업 일시(WORK DATE/TIME)", 8.5, True, "center")
    w.cell((XB, y + 22, R, y + 42), f"{cb('day')} 주간(DAY)  {cb('night')} 야간(NIGHT)", 8.5, True, "center")
    for (x0, x1, t) in [(XB, XD1, "일(DATE)"), (XD1, XD2, "시작(FROM)"), (XD2, R, "종료(TO)")]:
        box(page, (x0, y + 44, x1, y + 61)); w.cell((x0, y + 44, x1, y + 61), t, 8.5, True, "center")
    y = 208
    days = d.get("days", [])
    for i in range(7):
        yy = y + 20 * i
        row = days[i] if i < len(days) else ("", "", "")
        for (x0, x1), v in zip([(XB, XD1), (XD1, XD2), (XD2, R)], row):
            box(page, (x0, yy, x1, yy + 20)); w.cell((x0, yy, x1, yy + 20), v, 8.5, align="center")
    box(page, (L, y, XB, y + 20)); w.cell((L, y, XB, y + 20), "작업내용(JOB DESCRIPTION):", 8.5)
    w.fit((168, y, XB, y + 20), g("job"), 8.5, pad=0)
    box(page, (L, y + 20, XB, y + 60)); w.cell((L, y + 22, XB, y + 36), g("job_detail"), 8.5)
    rows = [("작업부서(DEPARTMENT):", None), ("작업책임자(SUPERVISOR):", "supervisor"),
            ("관리자(MANAGER):", "manager"), ("작업인원(NO. OF WORKER):", "workers")]
    for i, (lab, key) in enumerate(rows):
        yy = y + 60 + 20 * i
        box(page, (L, yy, XA, yy + 20)); box(page, (XA, yy, XB, yy + 20))
        w.cell((L, yy, XA, yy + 20), lab, 8.5)
        if key in ("supervisor", "manager"):
            w.cell((150, yy, XA, yy + 20), g(key), 8.5, align="center")
            ph = g(key + "_phone")
            w.cell((XA, yy, XB, yy + 20), "연락처 :", 8.5)
            w.cell((XA + 46, yy, XB, yy + 20), ph, 8.5, pad=0)
            w.cell((XA + 110, yy, XB, yy + 20), "/ TRS :", 8.5, pad=0)
        elif key == "workers":
            w.cell((150, yy, 190, yy + 20), g("workers"), 8.5, align="center")
            w.cell((190, yy, XA, yy + 20), "명", 8.5, align="center", pad=0)
        else:
            w.cell((XA, yy, XB, yy + 20), g("department"), 8.5, True)

    # hazards
    y = 348
    box(page, (L, y, XP, y + 20), HEAD); box(page, (XP, y, R, y + 20), HEAD)
    w.cell((L, y, XP, y + 20), "유해위험요소/추가전달사항 (HAZARDS AND OTHER REQUESTS) [작업부서 작성 BY WORK PARTY]", 8.5, True)
    w.cell((XP, y, R, y + 20), "병행여부", 8.5, True, "center")
    box(page, (L, y + 20, XP, y + 46)); box(page, (XP, y + 20, R, y + 46))
    w.fit((L, y + 21, XP, y + 45), g("hazards"), 8.5)
    w.cell((XP, y + 20, R, y + 46), g("concurrent"), 8.5, align="center")

    # site safety check
    y = 394
    box(page, (L, y, R, y + 19), HEAD)
    w.cell((L, y, R, y + 19), "현장 안전조치 확인사항(SITE SAFETY CHECK) [작업부서 작성 BY WORK PARTY]", 8.5, True)
    w.cell((350, y, R, y + 19), "※ 당일 작업시작 전 기입(사전 작성금지)", 8.5, True, pad=0)
    site = [("notice_sign", "공지문/경고표지 부착 (POSTED NOTICE/WARNING SIGNS)", "area_control", "작업구역 통제조치 실시 (AREA CONTROL)"),
            ("loto", "전원차단 및 브레이커 잠금 실시 (LOTO)", "simops", "병행작업 확인 (SIMOPS CONTROL)"),
            ("flammables", "인화성물질 제거(REMOVAL OF FLAMMABLES)", "fire_equipment", "소화장비 배치 (FIRE FIGHTING EQUIPMENT)"),
            ("accessway", "통행로 확보 (SAFE ACCESSWAY)", "night_lighting", "야간 작업시 조명 설치 (LIGHTING)")]
    for i, (k1, t1, k2, t2) in enumerate(site):
        yy = y + 19 + 18 * i
        box(page, (L, yy, XS, yy + 18)); box(page, (XS, yy, R, yy + 18))
        w.cell((L, yy, XS, yy + 18), f"{cb(k1)} {t1}", 8.2)
        w.cell((XS, yy, R, yy + 18), f"{cb(k2)} {t2}", 8.2)

    # additional information
    y = 485
    box(page, (L, y, R, y + 19), HEAD)
    w.cell((L, y, R, y + 19), "추가정보(ADDITIONAL INFORMATION) [작업부서 작성 BY WORK PARTY]", 8.5, True)
    w.cell((350, y, R, y + 19), "※ 작업당일 작업시작 전 체크(대면접수시 작성금지)", 8.5, True, pad=0)
    y += 19
    for (x0, x1), (k, t) in zip([(L, XE1), (XE1, XE2), (XE2, R)], K["heads"]):
        box(page, (x0, y, x1, y + 18)); w.fit((x0, y, x1, y + 18), f"{cb(k)} {t}", 8.2, True)
    y += 18
    col1, col2 = K["col1"], K["col2"]
    box(page, (L, y, XE1, y + 75)); box(page, (XE1, y, XE2, y + 75))
    for i in range(5):
        yy = y + 15 * i
        w.fit((L, yy, XE1, yy + 15), f"{cb(col1[i][0])} {col1[i][1]}", 8.2)
        w.fit((XE1, yy, XE2, yy + 15), f"{cb(col2[i][0])} {col2[i][1]}", 8.2)
    ak, alabel = K["a"]
    box(page, (XE2, y, R, y + 16)); w.fit((XE2, y, R, y + 16), f"{cb(ak)} {alabel}", 8.2, True)
    ck_, clabel, lines = K["c"]
    box(page, (XE2, y + 16, R, y + 59))
    w.cell((XE2, y + 17, R, y + 30), f"{cb(ck_)} {clabel}", 8.2, True)
    for j, (key, lab, unit, _name) in enumerate(lines):
        r = (XE2, y + 30 + 14 * j, R, y + 44 + 14 * j)
        w.cell(r, lab, 8.2); w.cell((470, r[1], 520, r[3]), g(key), 8.2, align="right", pad=0); w.cell(r, unit, 8.2, align="right")
    dk, dlabel, (vkey, unit, _name) = K["d"]
    r = (XE2, y + 59, R, y + 75)
    box(page, r)
    w.cell(r, f"{cb(dk)} {dlabel}", 8.2, True)
    w.cell((470, r[1], 520, r[3]), g(vkey), 8.2, align="right", pad=0)
    w.cell(r, unit, 8.2, align="right")

    # pledge
    y = 597
    box(page, (L, y, R, y + 25))
    w.cell((L, y, R, y + 25), "* 작업에 대한 안전규정, 작업표준(위험성평가서) 및 안전조치사항을 준수하여 작업하겠습니다.\n"
                              "* 작업종료 후 청소/정리정돈을 하고 잔존위험을 확실히 확인하겠습니다.", 7.8, True, "center")

    # issue / sign-off
    y = 622
    sign = [("허가신청\n(REQUESTED BY)", "req"), ("전산승인\n(APPROVED BY)", "app")]
    if copy == "submit":
        sign.append(("안전대면허가\n(APPROVED BY)", "face"))
    n = len(sign)
    box(page, (XI[0], y, XI[1], y + 31 * n), LABEL)
    w.cell((XI[0], y, XI[1], y + 31 * n), "발행\n(ISSUE)", 8.5, True, "center")
    for i, (lab, k) in enumerate(sign):
        yy = y + 31 * i
        cells = [(XI[c], yy, XI[c + 1], yy + 31) for c in range(1, 7)]
        for c, rect in enumerate(cells):
            box(page, rect, LABEL if c in (0, 2, 4) else None)
        w.cell(cells[0], lab, 8.5, True, "center")
        w.cell(cells[2], "일시\n(DATE/TIME)", 8.5, True, "center")
        w.cell(cells[4], "서명\n(SIGNED)", 8.5, True, "center")
        for rect, key in ((cells[1], "name"), (cells[3], "date"), (cells[5], "sign")):
            img = images.get(f"{k}_{key}")
            if img is not None:
                page.insert_image(pymupdf.Rect(rect) + (5, 2, -5, -2), stream=img, keep_proportion=True)
            else:
                w.cell(rect, g(f"{k}_{key}"), 9 if key != "date" else 8.5, key != "date", "center")

    # PTW check
    y += 31 * n
    box(page, (XI[0], y, XI[1], y + 75), LABEL)
    w.cell((XI[0], y, XI[1], y + 75), "PTW점검\n(PTW CHECK)", 8.5, True, "center")
    box(page, (XI[1], y, XI[2], y + 75))
    if images.get("qr") is not None:
        page.insert_image(pymupdf.Rect(XI[1] + 20, y + 5, XI[2] - 20, y + 55), stream=images["qr"], keep_proportion=True)
    if d:
        w.cell((XI[1], y + 57, XI[2], y + 72), f"2중점검 대상 : {g('double_check')}", 7.5, align="center")
    if copy == "submit":
        box(page, (XI[2], y, XI[6], y + 28)); box(page, (XI[2], y + 28, XI[6], y + 75))
        w.cell((XI[2], y, XI[6], y + 28), "작업허가 전 추가조치 요청사항(ADDITIONAL MEASURES REQUSTED)\n[안전요원 작성 BY SAFETY REPRESENTATIVE]", 8.2, True, "center")
        box(page, (XI[6], y, R, y + 28)); box(page, (XI[6], y + 28, R, y + 75))
        w.cell((XI[6], y, R, y + 28), g("ptw_box", "안전현장허가"), 8.5, True, "center")
        if images.get("extra") is not None:
            page.insert_image(pymupdf.Rect(XI[2] + 6, y + 30, XI[6] - 6, y + 73), stream=images["extra"], keep_proportion=True)
    else:
        box(page, (XI[2], y, R, y + 28)); box(page, (XI[2], y + 28, R, y + 75))
        w.cell((XI[2], y, R, y + 28), "추가조치 요청사항(ADDITIONAL MEASURES REQUSTED)", 8.5, True, "center")
    if g("stamp"):
        w.put(L + 4, y + 86, g("stamp"), 6.5, bold=True)
    borders(page)
    w.flush()
    return page


# values as printed on the two permits (names / phone numbers / staff numbers masked)
P1 = {
    "permit_no": "BS22-IV-20261012-1317", "permit_type": "[안전현장허가]", "hull_no": "", "jsp_no": "HHIS-CN-C6B0-014",
    "location": "UNIT2공장  유니트4팀", "location_detail": "유니트4팀",
    "job": "배관 내 사람이 들어가는 작업", "job_detail": "파이프 내부 진입",
    "department": "UNIT생산부-생산2과-UNIT4팀", "supervisor": "최XX", "supervisor_phone": "010-XXXX-XXXX",
    "manager": "최XX", "manager_phone": "010-XXXX-XXXX", "workers": "2", "hazards": "질식,소음",
    "days": [(f"2026-10-{d}", "08:00", "16:59") for d in range(12, 18)],
    "req_name": "최XX", "req_date": "2026-10-08", "req_sign": "최XX",
    "app_name": "최XX", "app_date": "2026-10-08", "app_sign": "최XX",
    "double_check": "Y", "stamp": "2026-10-08 06:51/최XX/XXXXXX",
    "checks": {"day": "set", "confined_space": "set", "argon": "set"},
}
P2 = {
    "permit_no": "BS22-IV-20261014-1305", "permit_type": "[전산허가]", "hull_no": "3595-157K-COT",
    "jsp_no": "HHIS-CW-A0000948-044-009",
    "location": "대조립21공장 3595 157K-COT 대조립 21공장 2BAY 28-32 칼럼", "location_detail": "대조립 21공장 2BAY 28-32 칼럼",
    "job": "(준)밀폐공간 내부 작업(B11, F31, E11, E18, E21, E22, E27, E33, E52 블록)",
    "job_detail": "혁신 3595 E170(A) / 밀폐공간 내부 작업",
    "department": "대조립3부-(주)혁신이엔지", "supervisor": "김XX", "supervisor_phone": "010-XXXX-XXXX",
    "manager": "오XX", "manager_phone": "010XXXXXXXX", "workers": "4",
    "hazards": "화기작업시 개인보호구 착용 , 이면부 확인 , 작업구역 통제 (병행 작업 금지) , 밀폐공간 출입 전 사전 안전조치 확인 조도 및 환기 조치 점검",
    "days": [(f"2026-10-{d}", "08:00", "16:59") for d in range(14, 18)],
    "req_name": "김XX", "req_date": "2026-10-13", "req_sign": "김XX",
    "app_name": "오XX", "app_date": "2026-10-13", "app_sign": "오XX",
    "double_check": "N", "stamp": "2026-10-13 14:30/C8W0948/XXXXXX/정XX",
    "checks": {"day": "set", "confined_space": "set"},
}


def old_images():
    """Handwriting / signature / QR crops from the earlier restored PDF, by position."""
    src = ROOT / "samples" / "보관" / "_restored_source.pdf"
    out = {1: {}, 2: {}}
    if not src.exists():
        return out
    d = pymupdf.open(src)
    for no, pg in enumerate(d, 1):
        for im in pg.get_images(full=True):
            bb = pg.get_image_bbox(im)
            if bb.is_empty or bb.x0 < 0:
                continue
            data = d.extract_image(im[0])["image"]
            if bb.height > 40 and bb.width < 60:
                out[no]["qr"] = data
            elif bb.width > 200:
                out[no]["extra"] = data
            elif bb.x0 < 300:
                out[no]["face_name"] = data
            elif bb.x0 < 450:
                out[no]["face_date"] = data
            else:
                out[no]["face_sign"] = data
    return out


def save(doc, path):
    """Keep the full embedded font as written (no subsetting), like the uploads we expect."""
    doc.save(path, garbage=4, deflate=True)


def truth(d, kind):
    """What the generator wrote on one page, for tools/check_extract.py."""
    t = {k: v for k, v in d.items() if k not in ("checks", "stamp", "days", "kind", "ptw_box", "case", "expect", "core", "extra", "assumed")}
    t["kind"], t["days"], t["checks"] = kind, [list(x) for x in d.get("days", [])], sorted(d.get("checks", {}))
    return t


def main():
    from foreman_permits import FOREMAN
    from synthetic_permits import SYN

    out = ROOT / "samples"
    demo, keep = out / "시연", out / "보관"
    demo.mkdir(exist_ok=True); keep.mkdir(exist_ok=True)
    imgs = old_images()
    manifest = {}

    filled = pymupdf.open()
    draw_page(filled, P1, "submit", imgs[1])
    draw_page(filled, P2, "posting", imgs[2])
    filled.set_metadata({"title": "기타위험 밀폐 작업 허가서", "subject": "위험작업신고서 2건 (출력물 기준 재작성, 개인정보 가림)",
                         "creator": "croScan make_form.py"})
    save(filled, keep / "위험작업신고서_양식.pdf")
    manifest["보관/위험작업신고서_양식.pdf"] = [truth(P1, "confined"), truth(P2, "confined")]

    # 합성 신청 5건: one bundle (a day's batch as the safety team receives it) and one file each
    bundle = pymupdf.open()
    for d in SYN:
        draw_page(bundle, d, "submit", {})
        single = pymupdf.open()
        draw_page(single, d, "submit", {})
        name = f"{d['permit_no'][-4:]}_{KINDS[d['kind']]['label'].replace('·', '')}.pdf"
        single.set_metadata({"title": KINDS[d["kind"]]["title"], "subject": "합성 예시 (교육·시연용)", "creator": "croScan make_form.py"})
        save(single, demo / name)
        manifest[f"시연/{name}"] = [truth(d, d["kind"])]
    bundle.set_metadata({"title": "대조립 위험작업 허가 신청 2026-10-27 (5건)", "subject": "합성 예시 (교육·시연용)",
                         "creator": "croScan make_form.py"})
    save(bundle, keep / "합성_대조립_허가신청_5건.pdf")
    manifest["보관/합성_대조립_허가신청_5건.pdf"] = [truth(d, d["kind"]) for d in SYN]

    # 작업반장 test set: one permit per file, two per kind, written the way the 실물 were (tools/foreman_permits.py)
    fdir = out / "반장_테스트"
    fdir.mkdir(exist_ok=True)
    for d in FOREMAN:
        single = pymupdf.open()
        draw_page(single, d, "submit", {})
        name = f"{KINDS[d['kind']]['label'].replace('·', '')}_{d['case']}_{d['permit_no'][-4:]}.pdf"
        single.set_metadata({"title": KINDS[d["kind"]]["title"], "subject": "작업반장 테스트용 합성 (실물 작성 습관 반영)", "creator": "croScan make_form.py"})
        save(single, fdir / name)
        manifest[f"반장_테스트/{name}"] = [truth(d, d["kind"])]

    # blank forms: one 안전부서 제출용 page per kind
    blank = pymupdf.open()
    for kind in KINDS:
        draw_page(blank, {}, "submit", {}, kind)
    blank.set_metadata({"title": "기타위험 작업 허가서 빈 양식 5종", "creator": "croScan make_form.py"})
    save(blank, keep / "위험작업허가서_빈양식_5종.pdf")
    manifest["보관/위험작업허가서_빈양식_5종.pdf"] = [truth({}, k) for k in KINDS]

    (out / "_truth.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print("saved", out)


if __name__ == "__main__":
    main()
