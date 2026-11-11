"""추가검토서 (별지): one sheet per permit, added after the 사전검토 반영본 (the original pages with the values that fit
written into their fields: server/reflect.py; the uploaded file itself is not changed).
The sheet is built once as a layout (header + blocks of cells) and drawn twice from it: as HTML for the web page
and straight onto an A4 page for the PDF, in the same frame, lines, colours and logo as page 1.
(PyMuPDF's HTML engine ignores column widths and vertical centring, so the PDF draws the cells itself and only
uses HTML for the text inside a cell.)"""
import html as H
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pymupdf

ITEM = {"T0": "작업일시", "D1": "대상 블록·설비", "D2": "사용 크레인", "D3": "가스·공급 방식", "D4": "정전 범위·복구", "D5": "진입 구획 공급 계통",
        "L6": "작업 중 통제 범위", "T1": "작업시간", "T2": "날짜별 작업", "T3": "인양 단계 시각", "T4": "종료 후 잔류위험", "L1": "작업장소", "L2": "실제 작업점",
        "L3": "높이·위치", "L4": "블록 작업 순서", "L5": "이동 경로", "B3": "병행여부", "B4": "호선/공사", "C1": "유해위험요소",
        "C2": "추가정보 분류", "C2h": "추가정보 분류", "C3": "병행여부", "X1": "사용 크레인", "X2": "가스 공급 연결", "X3": "내부 인원 확인",
        "X4": "절단 부재 지지", "X5": "차단 전원 연결", "X6": "협의한 시간대",
        "T5": "종료 시각", "T6": "시간 참고 비교", "L7": "칼럼 범위의 뜻", "C4": "중량·정격하중", "H1": "보수 범위·개수", "H2": "공법·가스",
        "H3": "분리물 지지·회수", "CF1": "내부 작업·진입 방식", "CF2": "연결 계통·차단", "HT1": "러그 수량·절단 방법",
        "HT2": "러그 회수·하부", "LI1": "크레인·인양 방법", "LI2": "블록 안·위 작업", "LO1": "작업 범위", "LO3": "차단·복구·시험",
        "LO4": "접근 위치", "FREE": "추가 전달(자유 입력)", "A1": "시간 오전·오후 확인", "A2": "시간 날짜 확인",
        "A3": "숫자 없는 시간 확인", "U1": "알아듣지 못한 말 확인", "W1": "감시·입회 인원",
        # the questions added from the research material (2026-11-01)
        "T7": "주간·야간 체크와 시간", "T8": "야간·교대 지원·인계", "T9": "대기·중단 중 유지", "CF3": "환기·송기·조명 전원",
        "CF4": "밀폐 안 화기", "CF5": "도장 구획의 남은 화기", "D6": "수전구역 통전·시운전", "D7": "압력시험 매체·가압 시각",
        "LI3": "같은 크레인 정비·주행로", "LO5": "통전 상태 측정", "LO6": "같은 주행로·다른 팀", "A4": "칼럼 범위 순서 확인"}
FIT = {"fit": "참고 범위 안", "long": "참고보다 김 → 질문함", "short": "참고보다 짧음 → 질문함"}
LEVEL = {1: "1순위 즉시 조정", 2: "2순위 확인 후 판단", 3: "3순위 정보 부족", 9: "기록"}
FIXED = {"허가구분": "허가구분 및<br>2중점검 기준"}       # fixed_pending text prefix -> its row label
NOTE = ("업로드한 원본 파일은 바꾸지 않았습니다. 앞의 반영본에는 작업반장이 답하거나 화면에서 고친 내용 중 그 칸의 용도에 맞는 것만 "
        "파란 글씨(①…)로 적었고, 변경 내역과 양식에 넣지 않은 내용은 아래에 적었습니다. 당일 작성·서명·승인 칸에는 적지 않습니다. "
        "전산 원본의 정정·전산승인은 생산부서 승인권한자가, 현장 확인과 (2중점검 Y 작업의) 대면허가는 안전 측이 기존 절차대로 합니다. croScan은 승인하지 않습니다.")
ROOT = Path(__file__).resolve().parent.parent
LOGO = ROOT / "web" / "croscan_logo.png"
FONTS = [(Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf"), Path("/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf")),
         (Path("C:/Windows/Fonts/malgun.ttf"), Path("C:/Windows/Fonts/malgunbd.ttf"))]

# page 1 geometry (pt): frame x 30–565 from y 78, logo at the same place, 0.6pt black lines
X0, X1, TOP, BOTTOM, LINE = 30, 565, 78, 812, 0.6
LOGO_RECT = pymupdf.Rect(33, 31.6, 33 + 28.8 * 538 / 128, 60.4)     # croScan logo (538×128 px) at the height of page 1's mark
BLUE, GRAY = (0.13, 0.36, 0.71), (0.878, 0.89, 0.902)          # #215CB5, #E0E3E6
LABEL_W, SUB_W, PAD_X, PAD_Y = 0.205, 0.188, 5, 4               # label column, sub-label column (fractions of the frame)
TITLE_W, HEAD_LABEL_W, HEAD_ROW = 0.367, 0.101, 21


def _e(x):
    return H.escape(str(x if x is not None else ""))


def _item(r):
    i = r["item"]
    if i.startswith(("B1.", "B2.")):
        return "빈칸: " + (r["signal"].split("'")[1] if "'" in r["signal"] else i)
    if i.startswith("C5."):
        return "상충 확인: " + ITEM.get(i[3:], {"concurrent": "병행여부"}.get(i[3:], i[3:]))
    if i.startswith(("A1.", "A2.", "A3.", "A4.", "U1.", "T0.")):
        return ITEM[i[:2]]
    if i.startswith("C6."):                             # the answer and the document disagree (asked once)
        return "서류와 답 확인: " + ITEM.get(i[3:], i[3:])
    if re.fullmatch(r"AI\d+", i):                       # a question the AI found in the documents (별지 only)
        return "추가 확인 질문"
    return ITEM.get(i, i)


def _s(x):
    return f"<span class='s'>{x}</span>"


def layout(s, P, when):
    """One permit's sheet: {"head": [(label, value)], "blocks": [...]}; every text is an HTML fragment.
    Blocks: bar (section title), note / full (one cell across), kv (label | value rows), table (column header + rows),
    group (one label beside several rows, each a text or a sub-label | text), box (one cell with a minimum height)."""
    pno = P["permit_no"]
    recs = [r for r in s["records"] if r["permit_no"] == pno or (r["item"] == "FREE" and r["permit_no"] is None)]
    mine = [x for x in s["pairs"] if pno in (x["a_no"], x["b_no"])]
    open_q = [q for q in s["questions"] if q["permit_no"] == pno]
    B = [{"t": "note", "h": _e(NOTE)}]

    R = (s.get("reflect") or {}).get(pno) or {"fills": [], "extra": [], "pending": []}
    # 1. what the 반영본 has in its fields (QA #37), by change number
    B.append({"t": "bar", "h": "1. 반영본에 적은 내용 (파란 글씨)"})
    MODE = {"fill": "빈칸에 기입", "append": "덧붙임", "replace": "바꿈"}
    if R["fills"]:
        B.append({"t": "table", "w": [0.07, 0.17, 0.22, 0.33, 0.21], "head": ["번호", "칸", "원본 값", "반영본 값", "근거"],
                  "rows": [[x["mark"], _e(x["name"]), _e(x["original"]) or "(빈칸)", _e(x["text"]) + _s(f"<br>{MODE[x['mode']]}"),
                            _e(", ".join(x["src"]))] for x in R["fills"]]})
        if any(x["mode"] == "replace" for x in R["fills"]):
            B.append({"t": "full", "h": _s("'바꿈'은 원본과 다른 값입니다. 전산 원본 정정은 기존 전산 절차(신청자·생산부서 승인권한자)에 따릅니다.")})
    else:
        B.append({"t": "full", "h": "반영본에 적은 칸이 없습니다 (원본 양식 그대로)."})
    # 2. what was said but has no field of its own on the form (or did not fit): kept here, word for word in meaning
    sup = [(_e(a), _e(b)) for a, b in R["extra"]]
    sup += [(_e(x["name"]), f"{_e(x['value'])} ({_e(x['why'])}, 규칙 추정)") for x in s.get("assumed", []) if x["permit_no"] == pno]
    B.append({"t": "bar", "h": "2. 양식 밖 보충 (신청자 답변)"})
    B.append({"t": "kv", "rows": sup} if sup else {"t": "full", "h": "없음"})

    # 3. the values the cross-permit check uses
    B.append({"t": "bar", "h": "3. 확인된 작업 범위"})
    groups = {}                                         # days with the same windows on one line
    for d, w in P["windows"].items():
        groups.setdefault(", ".join(w), []).append(d)
    win = [(f"{ds[0]}~{ds[-1][5:]} ({len(ds)}일)" if len(ds) > 1 else ds[0]) + f": {w}" for w, ds in groups.items()] or ["(없음)"]
    pl = P["place"]
    place = " ".join(x for x in (pl["factory"] and f"{pl['factory']}공장", pl["bays"] and "/".join(pl["bays"]) + "BAY", pl["cols"], pl["layer"]) if x) or "(위치 미상)"
    kv = [("위험시간대", "<br>".join(_e(x) for x in win) + f" ({_e(P['windows_src'])})" + _s("<br>" + _e(_tag(s, pno, ("T0", "T1", "T2"), P["windows_src"]))))]
    if P["residual"]:
        kv.append(("종료 후 잔류", _e(P["residual"])))
    if P["moments"]:
        kv.append(("위험 순간", _e(", ".join(P["moments"]))))
    kv.append(("위치", f"{_e(place)}<br>(자세한 정도 {pl['level']}{', 공장 전체' if pl['whole'] else ''} · 원문 '{_e(pl['text'])}')"
               + _s("<br>" + _e(_tag(s, pno, ("L1", "L7", "L2"), "")))))
    kv.append(("대상·설비 ID", _e(", ".join(P["targets"]) or "(없음)") + (_s("<br>서류 기재 · 예정") if P["targets"] else "")))
    f = P.get("fit") or {}
    if f.get("state") in FIT:
        kv.append(("시간 참고 비교", f"신청 {f['minutes']}분 / 참고 작업시간 {f['lo']}~{f['hi']}분 → {FIT[f['state']]}"
                   + _s(f"<br>비교 조건 {_e(f['model'])} · 출처 {_e(f['src'])}. 조사자료의 추정값이며 현장 평균·표준시간·안전 기준이 아닙니다.")))
    elif f.get("why"):
        kv.append(("시간 참고 비교", f"비교하지 않음: {_e(f['why'])}"))
    B.append({"t": "kv", "rows": kv})

    # pairs, highest priority first: only in the 안전관리자 view (the 작업반장 files one permit)
    if s.get("manager"):
        B.append({"t": "bar", "h": "작업쌍 검토"})
        if mine:
            prs = []
            for x in mine:
                other = x["b_who"] if x["a_no"] == pno else x["a_who"]
                basis = _e(x["why"]) + (f"<br>시간 {_e(x['when'])}" if x["when"] else "") + \
                    (_s(f"<br>연결: {_e(x['link'])} · 전달: {_e(x['modes'])} · 조사자료 {x['kinds']}({x['status']})") if x["link"] else "")
                act = _e(x["action"]) if x["level"] <= 2 else ("장소·시간 확인 후 다시 판단" if x["level"] == 3 else "-")
                lv = f"<span class='lv{x['level']}'>{LEVEL[x['level']]}</span>"
                prs.append([lv, _e(other), basis, act])
            B.append({"t": "table", "w": [0.15, 0.22, 0.33, 0.30], "head": ["순위", "상대 작업", "판단 근거", "조치 초안"], "rows": prs})
        else:
            B.append({"t": "full", "h": "시간·장소가 겹치는 다른 허가서가 없습니다."})

    # 4. what the safety team still has to check: 「모름」, not reflected, not answered
    B.append({"t": "bar", "h": "4. 안전팀 확인 필요"})
    kv = [(_e(a), _e(b)) for a, b in R["pending"]]
    kv += [(_e(_item(q)), f"{_e(q.get('unasked') or '답하지 않음')} · {_e(q['text'])}") for q in open_q if q.get("tier") != "extra"]
    if s.get("analysis_note"):                             # the AI analysis that did not finish is said, not hidden
        kv.append(("AI 분석", _e(s["analysis_note"])))
    kv += [(_e(x["name"]), _e(x["text"])) for x in s.get("deferred", []) if x["permit_no"] == pno]
    for t in s["fixed_pending"]:
        lab = next((v for k, v in FIXED.items() if t.startswith(k)), "확인 사항")
        kv.append((lab, _e(t).replace(": ", ":<br>", 1)))
    extra = [q for q in open_q if q.get("tier") == "extra"]
    if kv:
        B.append({"t": "kv", "rows": kv})
    if extra:
        B.append({"t": "group", "label": "선택 보강<br>(반장이 넘김)",
                  "rows": [{"h": "답이 있으면 다른 작업과의 겹침을 더 정확히 볼 수 있는 항목입니다."}]
                  + [{"l": _e(ITEM.get(q["item"], q["item"])), "h": _e(q["text"])} for q in extra]})
    if not kv and not extra:
        B.append({"t": "full", "h": "없음"})

    # 4. draft for the safety representative's 추가조치 box
    acts = [x["action"] for x in mine if x["level"] <= 2 and x["action"]]
    acts += [f"{_item(r)}: {r['value']}" for r in recs if r["item"] == "C1" and r["value"]]
    B.append({"t": "bar", "h": "5. 작업허가 전 추가조치 초안 (안전요원 수기란 참고용)"})
    B.append({"t": "box", "h": "<br>".join(f"· {_e(a)}" for a in dict.fromkeys(acts)) or "없음", "min": 60})
    mark = _ai_state(s, pno)
    if mark:
        B.append({"t": "full", "h": _s(_e(f"croScan AI 문안 보조 · 문안 상태: {mark}" + (f" · 개정 R{s['revision']}" if s.get("revision") is not None else "")))})
    # the plan travels with the sheet: a stored sheet (안전관리자 DB) draws the same 반영본
    return {"head": [("승인번호", _e(pno)), ("원본", _e(P["who"])), ("작성", when)], "blocks": B, "pno": pno, "reflect": R,
            "cont": f"croScan 추가검토서 (별지) · 승인번호 {pno}" + (f" · 개정 R{s['revision']}" if s.get("revision") is not None else "")}


AI_WHEN = {"plan": "예정", "done": "했다고 답함", "none": "시점 미확인"}


def _tag(s, pno, items, src):
    """where a value of block 3 comes from and when: 서류 기재 · 예정 / 반장 답변 · 예정 / 반장 답변 확인 · 했다고 답함 …"""
    mine = lambda a: str(a.get("qid", "")).split(":")[0].split(".")[0] in items and pno in str(a.get("qid", ""))
    ad = next((a for a in s.get("adopted") or [] if mine(a)), None)
    if ad:                                               # a reading of another answer the foreman confirmed
        return f"반장 답변 확인{' (AI 읽음)' if ad.get('ai') else ''} · {AI_WHEN.get(ad.get('when') or 'plan', '시점 미확인')}"
    # a withdrawn answer (C6 「서류가 맞음」) is history, not a source of the value (#11)
    said = any(r["item"].split(".")[0] in items and r.get("value") and r.get("permit_no") in (pno, None) and not r.get("withdrawn")
               for r in s.get("records") or [])
    if said or "답변" in (src or ""):
        return "반장 답변 · 예정"
    return "서류 기재 · 예정"


def _ai_state(s, pno):
    """the share of croScan's AI in this sheet, as the review stands: '' none; 채택 (what it read was confirmed);
    일부 채택 (some readings still wait for the foreman); 초안 (only questions or notes of its own)"""
    of = lambda a: pno in str(a.get("qid", "")) or str(a.get("qid", "")).startswith("FREE:")
    used = [a for a in s.get("adopted") or [] if a.get("ai") and of(a)]
    waiting = [p for p in s.get("proposals") or [] if (p.get("ai") or p.get("origin") == "ai") and of(p)]
    asked = [r for r in s.get("records") or [] if re.fullmatch(r"AI\d+", r.get("item") or "") and r.get("permit_no") in (pno, None)]
    if used:
        return "일부 채택" if waiting else "채택"
    if waiting or asked or s.get("analysis_note"):
        return "초안"
    return ""


# ---- HTML (web page) ----
def _cols(ws):
    return "<colgroup>" + "".join(f"<col style='width:{w * 100:.1f}%'>" for w in ws) + "</colgroup>"


def html(L):
    o = ["<div class='a2'><img class='a2-logo' src='/static/croscan_logo.png' alt='croScan'>",
         f"<table>{_cols([TITLE_W, HEAD_LABEL_W, 1 - TITLE_W - HEAD_LABEL_W])}"]
    for i, (k, v) in enumerate(L["head"]):
        title = "<td class='a2-title' rowspan='3'>croScan 추가검토서 (별지)</td>" if i == 0 else ""
        o.append(f"<tr>{title}<td class='lab'>{k}</td><td>{v}</td></tr>")
    o.append("</table>")
    for b in L["blocks"]:
        t = b["t"]
        if t in ("bar", "note", "full", "box"):
            cls = {"bar": "bar", "note": "note", "box": "box"}.get(t, "")
            o.append(f"<table><tr><td class='{cls}'>{b['h']}</td></tr></table>")
        elif t == "kv":
            o.append(f"<table>{_cols([LABEL_W, 1 - LABEL_W])}" + "".join(f"<tr><td class='lab'>{k}</td><td>{v}</td></tr>" for k, v in b["rows"]) + "</table>")
        elif t == "table":
            o.append(f"<table>{_cols(b['w'])}<tr>" + "".join(f"<td class='th'>{h}</td>" for h in b["head"]) + "</tr>"
                     + "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in b["rows"]) + "</table>")
        elif t == "group":
            o.append(f"<table>{_cols([LABEL_W, SUB_W, 1 - LABEL_W - SUB_W])}")
            for i, r in enumerate(b["rows"]):
                lab = f"<td class='lab' rowspan='{len(b['rows'])}'>{b['label']}</td>" if i == 0 else ""
                cells = f"<td class='lab'>{r['l']}</td><td>{r['h']}</td>" if "l" in r else f"<td colspan='2'>{r['h']}</td>"
                o.append(f"<tr>{lab}{cells}</tr>")
            o.append("</table>")
    o.append("</div>")
    return "\n".join(o)


# ---- PDF (drawn cell by cell) ----
TAG = re.compile(r"<br\s*/?>|<span class='([^']*)'>|</span>|<b>|</b>")
SIZE, LEAD = 8.5, 1.32                                            # page 1: 8.5pt Malgun Gothic
STYLE = {"s": {"color": (0.33, 0.33, 0.33)}, "lv1": {"color": (0.69, 0, 0.13), "bold": True},
         "lv2": {"color": (0.54, 0.35, 0), "bold": True}, "b": {"bold": True}, "t": {"color": (1, 1, 1), "bold": True, "size": 12},
         "note": {"size": 8}}


class _Pen:
    """Draws cells: border, fill, and the cell's text (an HTML fragment with <br>, <b> and <span class>), wrapped
    with the font's own glyph widths and centred vertically like page 1."""
    def __init__(self, doc):
        reg, bold = next(((r, b) for r, b in FONTS if r.exists() and b.exists()), (None, None))
        self.font = {False: pymupdf.Font(fontfile=str(reg)) if reg else pymupdf.Font("korea"),
                     True: pymupdf.Font(fontfile=str(bold)) if bold else pymupdf.Font("korea")}
        self.doc, self.page, self.y = doc, None, BOTTOM
        self.cont, self.thead, self.pages = "", None, 0

    def _runs(self, h, cls):
        """[[(text, style)], ...] one list per <br> line; style = {color, bold, size}."""
        base = {"color": (0, 0, 0), "bold": False, "size": SIZE}
        for c in cls.split():
            base.update(STYLE.get(c, {}))
        lines, stack, pos = [[]], [base], 0
        for m in TAG.finditer(h + "<br>"):
            if m.start() > pos:
                lines[-1].append((H.unescape(h[pos:m.start()]), stack[-1]))
            tag = m.group(0)
            if tag.startswith("<br"):
                lines.append([])
            elif tag in ("</span>", "</b>"):
                stack = stack[:-1] or stack
            else:
                st = dict(stack[-1])
                for c in (m.group(1) or "b").split():
                    st.update(STYLE.get(c, {}))
                stack.append(st)
            pos = m.end()
        return lines[:-1]

    def _wrap(self, h, cls, w):
        """Lines that fit in width w: [[(x_offset, text, style)], width]."""
        out = []
        for line in self._runs(h, cls):
            cur, x = [], 0.0
            for text, st in line:
                f, sz = self.font[st["bold"]], st["size"]
                for tok in re.findall(r"\S+|\s+", text):
                    tw = f.text_length(tok, fontsize=sz)
                    if x + tw > w and x > 0 and not tok.isspace():        # wrap before this word
                        out.append((cur, x)); cur, x = [], 0.0
                    if tok.isspace() and x == 0:
                        continue
                    while tw > w:                                        # a word longer than the cell: break by letters
                        k = max(1, int(len(tok) * (w - x) / tw))
                        while k > 1 and f.text_length(tok[:k], fontsize=sz) > w - x:
                            k -= 1
                        cur.append((x, tok[:k], st)); out.append((cur, w)); cur, x = [], 0.0
                        tok = tok[k:]; tw = f.text_length(tok, fontsize=sz)
                    cur.append((x, tok, st)); x += tw
            out.append((cur, x))
        return out

    def _lead(self, lines):
        return [max([st["size"] for _, _, st in ln] or [SIZE]) * LEAD for ln, _ in lines]

    def height(self, h, w, cls=""):
        return sum(self._lead(self._wrap(h, cls, w - 2 * PAD_X))) + 2 * PAD_Y

    def text(self, r, h, cls="", middle=True):
        self._put(r, self._wrap(h, cls, r.width - 2 * PAD_X), cls, middle)

    def _put(self, r, lines, cls="", middle=True):
        leads = self._lead(lines)
        y = r.y0 + (max(PAD_Y, (r.height - sum(leads)) / 2) if middle else PAD_Y)
        center = "c" in cls.split() or "t" in cls.split()
        for (ln, width), lead in zip(lines, leads):
            x0 = r.x0 + PAD_X + ((r.width - 2 * PAD_X - width) / 2 if center else 0)
            for dx, t, st in ln:
                self.page.insert_text((x0 + dx, y + lead * 0.5 + st["size"] * 0.36), t, fontsize=st["size"],
                                      fontname="krb" if st["bold"] else "kr", fontfile=None, color=st["color"])
            y += lead

    def cell(self, r, h, fill=None, cls="", middle=True):
        if fill:
            self.page.draw_rect(r, color=None, fill=fill, width=0)
        self.page.draw_rect(r, color=(0, 0, 0), width=LINE)
        if h:
            self.text(r, h, cls, middle)

    def new_page(self):
        self.page = self.doc.new_page(width=595, height=842)
        self.pages += 1
        for name, f in (("kr", self.font[False]), ("krb", self.font[True])):
            self.page.insert_font(fontname=name, fontbuffer=f.buffer)

    def _next(self):
        """a following page: the document line again (number · revision · (계속)), then the open table's head row"""
        self.new_page()
        self.y = 30
        if self.cont:
            r = pymupdf.Rect(X0, self.y, X1, self.y + 16)
            self.text(r, H.escape(self.cont) + " (계속)", "s")
            self.y += 18
        if self.thead:
            hgt = max(self.height(h, x1 - x0, cls) for x0, x1, h, _, cls in self.thead)
            for x0, x1, h, fill, cls in self.thead:
                self.cell(pymupdf.Rect(x0, self.y, x1, self.y + hgt), h, fill, cls)
            self.y += hgt

    def _top(self):
        """where the first row of a following page starts"""
        y = 30 + (18 if self.cont else 0)
        if self.thead:
            y += max(self.height(h, x1 - x0, cls) for x0, x1, h, _, cls in self.thead)
        return y

    def room(self, need):
        if self.y + need > BOTTOM:                                      # next A4 page
            self._next()

    def row(self, cells, middle=True):
        """cells: [(x0, x1, html, fill, cls)] in one row; height from the tallest. A row taller than a page is cut
        between lines (never in a line, nothing left out): its first cell says 「(계속)」 on the following pages."""
        hgt = max(self.height(h, x1 - x0, cls) for x0, x1, h, _, cls in cells)
        if hgt <= BOTTOM - self._top():
            self.room(hgt)
            for x0, x1, h, fill, cls in cells:
                self.cell(pymupdf.Rect(x0, self.y, x1, self.y + hgt), h, fill, cls, middle)
            self.y += hgt
            return
        wraps = [self._wrap(h, cls, x1 - x0 - 2 * PAD_X) for x0, x1, h, _, cls in cells]
        leads = [self._lead(w) for w in wraps]
        pos, first, line = [0] * len(cells), True, SIZE * LEAD
        while first or any(p < len(w) for p, w in zip(pos, wraps)):
            if BOTTOM - self.y < 3 * line + 2 * PAD_Y:
                self._next()
            avail = BOTTOM - self.y - 2 * PAD_Y
            take = []
            for p, ld in zip(pos, leads):
                n, tot = 0, 0.0
                while p + n < len(ld) and tot + ld[p + n] <= avail:
                    tot += ld[p + n]
                    n += 1
                take.append(max(n, 1 if p < len(ld) else 0))
            hgt = max(sum(ld[p:p + n]) for p, n, ld in zip(pos, take, leads)) + 2 * PAD_Y
            for i, (x0, x1, h, fill, cls) in enumerate(cells):
                r = pymupdf.Rect(x0, self.y, x1, self.y + hgt)
                if fill:
                    self.page.draw_rect(r, color=None, fill=fill, width=0)
                self.page.draw_rect(r, color=(0, 0, 0), width=LINE)
                if i == 0 and not first and len(cells) > 1:          # the label again, said to go on
                    self.text(r, h + " (계속)", cls, middle)
                else:
                    self._put(r, wraps[i][pos[i]:pos[i] + take[i]], cls, middle and len(cells) > 1)
            pos = [p + n for p, n in zip(pos, take)]
            self.y += hgt
            first = False


def _draw(doc, L):
    pen = _Pen(doc)
    pen.cont = H.unescape(re.sub(r"<[^>]+>", "", L.get("cont") or ""))
    pen.new_page()
    if LOGO.exists():
        pen.page.insert_image(LOGO_RECT, filename=str(LOGO))
    W = X1 - X0
    xt, xl = X0 + W * TITLE_W, X0 + W * (TITLE_W + HEAD_LABEL_W)
    pen.cell(pymupdf.Rect(X0, TOP, xt, TOP + 3 * HEAD_ROW), L.get("title", "croScan 추가검토서 (별지)"), BLUE, "t")
    for i, (k, v) in enumerate(L["head"]):
        y = TOP + i * HEAD_ROW
        pen.cell(pymupdf.Rect(xt, y, xl, y + HEAD_ROW), k, None, "c b")
        pen.cell(pymupdf.Rect(xl, y, X1, y + HEAD_ROW), v)
    pen.y = TOP + 3 * HEAD_ROW
    xs = X0 + W * LABEL_W
    for b in L["blocks"]:
        t = b["t"]
        if t == "bar":
            pen.row([(X0, X1, b["h"], GRAY, "b")])
        elif t in ("note", "full"):
            pen.row([(X0, X1, b["h"], None, "note" if t == "note" else "")])
        elif t == "box":
            h = max(b["min"], pen.height(b["h"], W))
            if h > BOTTOM - pen._top():                                  # longer than a page: as a row, cut between lines
                pen.row([(X0, X1, b["h"], None, "")], middle=False)
                continue
            pen.room(h)
            pen.cell(pymupdf.Rect(X0, pen.y, X1, pen.y + h), b["h"], middle=False)
            pen.y += h
        elif t == "kv":
            for k, v in b["rows"]:
                pen.row([(X0, xs, k, None, "c b"), (xs, X1, v, None, "")])
        elif t == "table":
            edges = [X0]
            for w in b["w"]:
                edges.append(edges[-1] + W * w)
            edges[-1] = X1
            head = [(edges[i], edges[i + 1], h, GRAY, "b") for i, h in enumerate(b["head"])]
            pen.room(max(pen.height(h, x1 - x0, cls) for x0, x1, h, _, cls in head) + 3 * SIZE * LEAD)   # not a head alone at a page end
            pen.row(head)
            pen.thead = head                                             # repeated on a following page
            for r in b["rows"]:
                pen.row([(edges[i], edges[i + 1], c, None, "") for i, c in enumerate(r)])
            pen.thead = None
        elif t == "group":
            xm = X0 + W * (LABEL_W + SUB_W)
            hs = [max(pen.height(r["l"], xm - xs, "c b") if "l" in r else 0, pen.height(r["h"], X1 - (xm if "l" in r else xs))) for r in b["rows"]]
            total = max(sum(hs), pen.height(b["label"], xs - X0, "c b"))
            hs[-1] += total - sum(hs)
            if total > BOTTOM - pen._top():                              # longer than a page: one row per item
                for k, r in enumerate(b["rows"]):
                    lab = b["label"] if k == 0 else b["label"] + " (계속)"
                    body = (f"<b>{r['l']}</b><br>{r['h']}" if "l" in r else r["h"])
                    pen.row([(X0, xs, lab, None, "c b"), (xs, X1, body, None, "")])
                continue
            pen.room(total)
            pen.cell(pymupdf.Rect(X0, pen.y, xs, pen.y + total), b["label"], None, "c b")
            for r, h in zip(b["rows"], hs):
                if "l" in r:
                    pen.cell(pymupdf.Rect(xs, pen.y, xm, pen.y + h), r["l"], None, "c b")
                    pen.cell(pymupdf.Rect(xm, pen.y, X1, pen.y + h), r["h"])
                else:
                    pen.cell(pymupdf.Rect(xs, pen.y, X1, pen.y + h), r["h"])
                pen.y += h


def build(s, fields):
    """[(permit_no, html, layout)] for every permit; the on-screen edits come in through the 반영본 plan (s["reflect"])."""
    when = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M")     # KST: the server runs in UTC
    out = []
    for P in s["effective"]:
        L = layout(s, P, when)
        out.append((P["permit_no"], html(L), L))
    return out


def _tidy(doc):
    """After writing on the original pages: only the glyphs used of the inserted font, and its look-alike glyphs read
    back as what was written ('·', spaces)."""
    from .workplan_pdf import fix_tounicode
    try:
        doc.subset_fonts()
    except Exception as e:                       # an original font that cannot be subset: keep it whole
        print(f"subset_fonts: {e}", flush=True)
    fix_tounicode(doc)


def pdf(original: bytes, sheets, fields=None, rplan=None) -> bytes:
    """The 사전검토 반영본 (the original pages with the planned values written in their fields), then one 추가검토서 per
    permit (A4, as many pages as it needs). The uploaded bytes are not changed: this is a new, derived PDF."""
    sheet = pymupdf.open()
    for _, _, L in sheets:
        _draw(sheet, L)
    sheet.subset_fonts()                               # only the added sheet; the original pages keep their fonts
    from .workplan_pdf import fix_tounicode
    fix_tounicode(sheet)
    out = pymupdf.open(stream=original, filetype="pdf")
    if fields and rplan:
        from . import reflect
        if reflect.apply(out, fields, rplan):
            _tidy(out)
    out.insert_pdf(sheet)
    return out.tobytes(garbage=1, deflate=True)
