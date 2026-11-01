"""현장 게시용 서류: after the 쌍작업 위험탐지, the coordination the safety team confirmed goes to the field as
  · 현장 게시용 = the original permit pages, unchanged, + 별지 「병행작업 조정·착수조건」
  · 일상작업반 전달문 = the same confirmed data, only that routine work's pairs (it has no permit to post)
The page builds the sheet as plain text (title, 3 head rows, sections of label/value rows) after the safety manager
edited it; this draws it in the frame of the 추가검토서 (addendum._draw). Text is escaped here: nothing from the page is
taken as HTML. Nothing is stored (demo: the confirmed state lives in the browser).

게시 서류 AI 보충 (design §6.1·§6.5·§19.2, WRITE): for a pair on an unissued sheet, a draft of 「우리 반이 할 일」 in the
fixed shape 「우리 반은 {시점·대상}에 {할 일}」 → 착수조건 → 중지·변경 시 연락, from the rule's own wording and this
work's confirmed facts. The model only picks which rule action, which confirmed fact and which start condition; every
sentence is the server's. The same picks give the 추가조치 초안 (three lines) and a TBM 전달 초안. A draft is offered,
never written: the safety manager adopts it (「문안 채택」) into an unissued sheet; the printed sheet says once at its end
what share of it is croScan's wording (「croScan AI 문안 보조 · 문안 상태 · 개정」). Adopting is not sending, not a TBM held,
not a start allowed."""
import html as H
import re

import pymupdf

from . import addendum, llm, safety

MAX_SECTIONS, MAX_ROWS, MAX_TEXT = 40, 14, 2000
SIGN_W = [0.205, 0.25, 0.25, 0.295]


def _t(s, bold=False):
    s = str(s or "")
    if len(s) > MAX_TEXT:                   # refused, never cut: the printed sheet must say what was issued
        raise ValueError(f"한 칸은 {MAX_TEXT}자까지입니다")
    s = H.escape(s).replace("\n", "<br>")
    return f"<b>{s}</b>" if bold and s else s


def layout(sheet):
    """sheet: {title, head: [[k, v]×3], note, sections: [{title, rows: [[label, value, strong?]], sign}], foot} → addendum layout."""
    if not isinstance(sheet, dict):
        raise ValueError("서류 내용 형식이 맞지 않습니다")
    head = [(_t(k), _t(v)) for k, v in (sheet.get("head") or [])[:3]]
    while len(head) < 3:
        head.append(("", ""))
    B = []
    if sheet.get("note"):
        B.append({"t": "note", "h": _t(sheet["note"])})
    secs = sheet.get("sections") or []
    if len(secs) > MAX_SECTIONS or any(len(x.get("rows") or []) > MAX_ROWS for x in secs):
        raise ValueError("쌍이나 줄이 너무 많습니다")
    for sec in secs:
        B.append({"t": "bar", "h": _t(sec.get("title"))})
        rows = [(_t(r[0]), _t(r[1], len(r) > 2 and bool(r[2]))) for r in (sec.get("rows") or []) if isinstance(r, (list, tuple)) and len(r) >= 2]
        if rows:
            B.append({"t": "kv", "rows": rows})
        if sec.get("sign"):
            blank = "&nbsp;<br>&nbsp;"
            B.append({"t": "table", "w": SIGN_W, "head": ["당일 확인", "확인자", "시각", "확인한 것"],
                      "rows": [[_t(s), blank, blank, "상대 작업·시간·위치 / 착수조건 / TBM 전달"] for s in (sec.get("sign_rows") or ["우리 반", "상대 반"])[:2]]})
    if sheet.get("foot"):
        B.append({"t": "full", "h": _t(sheet["foot"])})
    ai = sheet.get("ai") if isinstance(sheet.get("ai"), dict) else None
    if ai and ai.get("state") in AI_STATES:                 # once at the end, as saved (design §19.6)
        B.append({"t": "full", "h": f"<span class='s'>{_t(ai_mark(ai['state'], ai.get('rev')))}</span>"})
    return {"title": _t(sheet.get("title") or "병행작업 조정·착수조건 (별지)"), "head": head, "blocks": B,
            "cont": " · ".join(str(v) for _, v in head[:1] if v)}


AI_STATES = ("초안", "일부 채택", "채택")


def ai_mark(state, rev=None):
    return f"croScan AI 문안 보조 · 문안 상태: {state}" + (f" · 개정 {rev}" if rev else "")


# ---- 게시 서류 AI 보충 (WRITE) ----------------------------------------------------------------------------------
STOP = "시간·위치·공법이 바뀌거나 멈추면 상대 반장과 안전관리자에게 바로 연락합니다"
SYSTEM = ("너는 현장 게시 서류의 문안을 고르는 도우미다. 이 작업 쪽이 할 일 후보, 확인된 반장 답 후보, 착수조건 후보가 번호로 주어진다. "
          "이 작업 쪽에 맞는 할 일 하나(a), 그 할 일에 관계된 확인된 답 하나(f, 없으면 none), 착수조건 하나(c)를 고른다. 문장을 쓰지 않는다.")
_DRAFTS = {}


def _schema(aids, fids, cids):
    return {"type": "object", "additionalProperties": False, "required": ["a", "f", "c"],
            "properties": {"a": {"type": "string", "enum": aids}, "f": {"type": "string", "enum": fids + ["none"]},
                           "c": {"type": "string", "enum": cids}}}


def options(det, key, doc_id, facts=None):
    """what a draft for this work in this pair is chosen from: (pair, side, actions, facts, conditions) or None"""
    p = next((x for x in det.get("pairs") or [] if x["key"] == key), None)
    if not p or doc_id not in (p["a"], p["b"]):
        return None
    R = p["reasons"][0]
    rule = next((r for r in det.get("rules") or [] if r["id"] == R["rule"]), {})
    post = rule.get("post") or {}
    side = "cause" if R["cause"] == doc_id else "exposed"
    acts = [x for x in [post.get(side)] + list(R.get("measures") or rule.get("measures") or []) if x]
    conds = [x for x in [post.get("start"), R.get("ask") and f"{R['ask']}을(를) 확인한 뒤 착수"] if x]
    return p, side, list(dict.fromkeys(acts)), [f for f in facts or [] if f.get("value")], list(dict.fromkeys(conds))


def _when(doc):
    w = doc.get("windows") or []
    return ", ".join(f"{x['start']}~{x['end']}" for x in w) or "작업 시간(서류에 없음)"


def compose(doc, act, fact, cond):
    """the fixed shape (design §19.2 게시 문안): one action sentence, the start condition, whom to call on a change"""
    target = re.sub(r"^대조립\S*공장\s*", "", doc.get("place") or "").strip()
    what = f"{_when(doc)} {target}".strip() + (f" ({fact['value']})" if fact else "")
    act = act.rstrip(". ")
    lines = [f"우리 반은 {what}에 {act}.", f"착수조건: {cond.rstrip('. ')}.", f"중지·변경 시: {STOP}."]
    return lines


async def draft(det, key, doc_id, facts=None, pri=None):
    """-> {status: ok|fixed|none|fail, lines: [do, start, stop], extra: [3 lines], tbm: [lines], picked, sources, why}.
    facts: this work's confirmed facts ([{item, value}], pairs.confirmed_facts of its submission)."""
    got = options(det, key, doc_id, facts)
    if not got:
        return {"status": "none", "lines": [], "why": "그런 작업쌍·작업이 없음"}
    p, side, acts, facts, conds = got
    if not acts or not conds:
        return {"status": "none", "lines": [], "why": "규칙에 할 일·착수조건 문구가 없음"}
    doc = safety.find(doc_id)
    k = (key, doc_id, tuple(acts), tuple((f["item"], f["value"]) for f in facts), tuple(conds), tuple(map(str, doc.get("windows") or [])))
    if k in _DRAFTS:
        return _DRAFTS[k]
    status, ai = "fixed", {"a": 0, "f": None, "c": 0}
    if len(acts) > 1 or len(conds) > 1 or facts:
        aids, fids, cids = [f"A{i}" for i in range(1, len(acts) + 1)], [f"F{i}" for i in range(1, len(facts) + 1)], [f"C{i}" for i in range(1, len(conds) + 1)]
        user = (f"이 작업: {doc.get('title') or doc_id} ({'위험을 주는 쪽' if side == 'cause' else '위험을 받는 쪽'})\n"
                + "할 일 후보:\n" + "\n".join(f"A{i} {a}" for i, a in enumerate(acts, 1))
                + "\n확인된 반장 답 후보:\n" + ("\n".join(f"F{i} {f['item']} {f['value']}" for i, f in enumerate(facts, 1)) or "(없음)")
                + "\n착수조건 후보:\n" + "\n".join(f"C{i} {c}" for i, c in enumerate(conds, 1)))
        try:
            data, _ = await llm.call_json("WRITE", [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
                                          _schema(aids, fids, cids), think=0, out_tokens=40, deadline=45.0,
                                          pri=llm.ASKED if pri is None else pri)
        except llm.LlmFail as e:
            return {"status": "fail", "lines": [], "why": e.code}
        if not (isinstance(data, dict) and data.get("a") in aids and data.get("c") in cids and data.get("f") in fids + ["none"]) \
                or set(data) - {"a", "f", "c"}:
            return {"status": "fail", "lines": [], "why": "schema"}
        status, ai = "ok", {"a": int(data["a"][1:]) - 1, "f": None if data["f"] == "none" else int(data["f"][1:]) - 1, "c": int(data["c"][1:]) - 1}
    act, cond = acts[ai["a"]], conds[ai["c"]]
    fact = facts[ai["f"]] if ai["f"] is not None else None
    lines = compose(doc, act, fact, cond)
    other = p["b"] if p["a"] == doc_id else p["a"]
    extra = [f"{other}과(와) 병행작업: {act.rstrip('. ')}.", f"{cond.rstrip('. ')} 전에는 해당 단계 착수 금지.", f"{STOP}."]
    tbm = [f"오늘 {doc.get('title') or doc_id}: {lines[0][len('우리 반은 '):]}", lines[1], lines[2]]
    src = [{"kind": "규칙 문구", "text": act}, {"kind": "규칙 문구", "text": cond}] + ([{"kind": "반장 답변 확인", "text": f"{fact['item']} {fact['value']}"}] if fact else [])
    out = {"status": status, "lines": lines, "extra": extra, "tbm": tbm, "picked": ai, "sources": src, "why": None}
    _DRAFTS[k] = out
    if len(_DRAFTS) > 500:
        _DRAFTS.clear()
    return out


def pdf(doc_id, kind, sheet):
    """kind 'post': the permit's original pages + the sheet; 'notice': the sheet alone (a routine work's 전달문)."""
    d = safety.find(doc_id)
    page = pymupdf.open()
    addendum._draw(page, layout(sheet))
    page.subset_fonts()
    from .workplan_pdf import fix_tounicode
    fix_tounicode(page)
    if kind == "notice":
        return page.tobytes(garbage=3, deflate=True)
    if kind != "post" or d["type"] != "permit":
        raise KeyError(kind)
    out = pymupdf.open(stream=d["_file"].read_bytes(), filetype="pdf")
    out.insert_pdf(page)
    return out.tobytes(garbage=1, deflate=True)
