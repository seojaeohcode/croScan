"""검색 자료(RAG) 만들기 (design §3.4·§3.4.1): once, offline, into server/knowledge/corpus.json.

  python tools/build_corpus.py      # on a machine that reaches law.go.kr and has the 자료 folder

Layers (authority): [법령] the articles the app cites, from the current text of 국가법령정보센터 (the page, its hash
and the day it was fetched kept); [조선사] the shipyards' own public reports, only passages on terms and policy
(their permit procedures are not public, so nothing here is quoted as a company's permit rule); [팀] the team's
research notes (Notion export, 119 pages). [공공] (KOSHA guides) is not collected yet: the evidence map shows it as
「근거 보강 필요」. The demo's answer sheets (answers_truth, workplans_truth, skeleton, expected pairs) are never in it.

States kept apart (Codex 2026-10-31 #19·#20):
- law: an article is kept whole — one longer than a chunk is cut into consecutive chunks at its 항(①…)/호(1. …)
  boundaries (ids law:<law>:<art>#1, #2 …; retrieval.article joins them). legal_verified means only 「the current
  text was collected from 국가법령정보센터」, not that it fits a rule (that is pair_rules.json's law_fit).
- team/yard: reviewed False — search candidates nobody has linked yet.
- synthetic: by page and section, not by the words of one chunk: the pages that say they are made up (가상·합성·예시)
  and the sections read and marked below (the made-up permits and their explanations) mark every chunk on them;
  a chunk carrying the made-up scenario values (3.6m·4.8m·38톤·380V) is synthetic wherever it stands.

Every chunk carries the metadata of design §3.4 (meta()): source_id, revision, hash (of its source file/page), pdf_page,
printed_page (when the page prints its own number), section, company_scope, work_kind (the permit kinds it speaks
of, by its words; 'common' when none), topic (hazard/control/procedure/term/accident), authority, effective_status,
supersedes, synthetic, estimate (a made-up or rounded value in it), legal_verified, extraction_quality. The filters of
retrieval.search use them before scoring.

The research references of checklist_spec.json (HW02-SPARK …) are the codes of the team's research book (추가본·전체
자료, 412 pages; its text in 자료/BOOK), where each is defined ('HW02-SPARK — 불티·열 전달'): found there → linked to
that page and words; a ref that is not such a code (사례집 번호, 보고서, 멘토 메모) or not defined there → kept
「미연결」 with the best team passage as a candidate (검수 전), in server/knowledge/research_refs.json (design §3.4: an
unlinked ref is not cited). Earlier only the 119-page Notion export was searched, which does not carry the codes.
"""
import datetime
import hashlib
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT.parent / "자료"
OUT = ROOT / "server" / "knowledge" / "corpus.json"
LAWS = {  # name -> (lsiSeq, 시행일, short name used in the app)
    "산업안전보건기준에 관한 규칙": ("273603", "20260302", "안전보건규칙"),
    "산업안전보건법": ("291447", "20261027", "산업안전보건법"),
    "원자력안전법": ("286119", "20260519", "원자력안전법"),
}
# [공공] KOSHA 기술지원규정 (design §3.4.1): downloaded once from portal.kosha.or.kr and kept in 자료/공공_KOSHA
# (url, the day, the file hash recorded). Technical recommendations, not legal minimums; a guide whose currency is
# not confirmed says so.
GUIDES = [
    ("KOSHA_A-G-14-2026_용접용단작업시화재예방.pdf", "A-G-14-2026", "용접·용단 작업 시 화재예방에 관한 기술지원규정", "2026.1.30 공표",
     "https://portal.kosha.or.kr/openapi/v1/file/down/CTC2026012909355295338479/1"),
    ("KOSHA_B-E-12-2026_전기작업안전.pdf", "B-E-12-2026", "전기작업 안전에 관한 기술지원규정", "2026.1 공표",
     "https://portal.kosha.or.kr/openapi/v1/file/down/CTC2026012913315457127282/1"),
    ("KOSHA_B-5-2011_조선업안전점검기술지침.pdf", "B-5-2011", "조선업 안전점검 기술지침", "2011.12 (2026.1 재정비 뒤 현행 여부 미확인)",
     "https://portal.kosha.or.kr/openapi/v1/file/down/FL00015883233/3"),
]
REPORTS = ["HD현대중공업_2024_안전보건경영보고서.pdf", "HD현대중공업_안전보고_한영용어집_2025.pdf",
           "삼성중공업_2023_지속가능경영보고서.pdf", "한화오션_2025_지속가능경영보고서.pdf"]
TERMS = re.compile(r"작업중지권|작업\s*중지|안전작업\s*요구|위험작업\s*허가|작업\s*허가|화기\s*작업|밀폐\s*공간|고소\s*작업|중량물|혼재\s*작업|협력사\s*안전")
ART = re.compile(r"(제\d+조(?:의\d+)?)")
LAW_CHUNK = 700
# the Notion export's made-up sections, read page by page (2026-10-31): 72~79 explain the made-up permits N1~N5
# (「이번 가상 사례」, 「기존 가상 허가서」), 80~99 are the made-up permit forms and the 「허가서 작성 예시 합성」 plan
SYN_SECTIONS = ((72, 79, "가상 허가서 설명(N1~N5)"), (80, 99, "허가서 작성 예시(합성)"))
SYN_PAGE = re.compile(r"가상|합성|예시")
SYN_VALUES = re.compile(r"3\.6\s*m|4\.8\s*m|38\s*톤|38,000\s*kg|380\s*V")
REFS_OUT = ROOT / "server" / "knowledge" / "research_refs.json"
# the team's research book (추가본·전체자료 412쪽, page marks 「===== PAGE n =====」): the checklist's research codes
BOOK = DATA / "팀_조사본_추가본전체자료_412쪽_텍스트.txt"
CODE = r"(?:HW|PE|LU|MV|EL)\d{2}(?:-[A-Z0-9]+)*|R42-\d{2}-[A-Z]+"      # R42: the book's 42 daily works (「[R42-02-SHARP] …」)
# the permit kinds a passage speaks of, by its words (design §3.4 work_kind); 'common' when none
WORK_KIND = {"hot": r"용접|용단|화기|불티|불꽃|화재|가우징|절단|토치",
             "confined": r"밀폐|산소\s*결핍|질식|유해\s*가스|탱크\s*내부|이중저|환기|송기",
             "height": r"고소|추락|비계|안전대|작업\s*발판|개구부|사다리|고소작업대",
             "lifting": r"크레인|양중|인양|중량물|신호수|줄걸이|달기|하물|권상",
             "loto": r"정전|전원|차단기|잠금|LOTO|꼬리표|감전|충전부|전로|분전반",
             "radiation": r"방사선|비파괴|투과\s*검사|\bRT\b",
             "pressure": r"기밀\s*시험|압력\s*시험|불활성|질소|아르곤"}
TOPIC = {"hazard": r"위험|우려|발생할\s*수|떨어|폭발|화재|질식|감전|협착|충돌",
         "control": r"하여야|해야|설치|배치|착용|조치|차단|측정|확인할|금지|비치|게시",
         "procedure": r"허가|승인|신청|절차|결재|작성|서명|대면|전산",
         "term": r"정의|이란|말한다|용어|뜻",
         "accident": r"사고|재해|사망|부상|사례|원인|재해발생"}
ESTIMATE = re.compile(r"약\s*\d|정도|가량|추정|가정|예상\s*\d")
PRINTED = re.compile(r"(?:^|\s)-\s*(\d{1,3})\s*-(?:\s|$)|(?:^|\s)(\d{1,3})\s*/\s*\d{1,3}(?:\s|$)")


def meta(text, *, source_id, revision, hash_, authority, company, effective, quality, pdf_page=None, supersedes=None, synthetic=False):
    """the §3.4 metadata of a chunk, from its words and its source"""
    kinds = [k for k, rx in WORK_KIND.items() if re.search(rx, text)] or ["common"]
    topics = [k for k, rx in TOPIC.items() if re.search(rx, text)]
    pr = PRINTED.search(text)
    return {"source_id": source_id, "revision": revision, "hash": hash_, "pdf_page": pdf_page,
            "printed_page": int(pr.group(1) or pr.group(2)) if pr else None, "company_scope": company, "work_kind": kinds,
            "topic": topics, "authority": authority, "effective_status": effective, "supersedes": supersedes,
            "synthetic": synthetic, "estimate": bool(ESTIMATE.search(text)), "extraction_quality": quality}


def book_lines(text):
    """the book's text as [(page, line)]: page marks, running heads and page numbers left out, and a code the table
    cut over two lines joined again ('HW09-CABLE-ELECT' / 'RIC — 전기 케이블 손상')"""
    out, page = [], 0
    raw = text.split("\n")
    i = 0
    while i < len(raw):
        s = raw[i].strip()
        m = re.match(r"===== PAGE (\d+)", s)
        if m:
            page = int(m.group(1))
        elif s and not re.fullmatch(r"\d{1,3}|Notion 원문 · .*", s):
            nxt = raw[i + 1].strip() if i + 1 < len(raw) else ""
            m = re.match(r"([A-Z0-9]*)\s*(—.*)", nxt)
            if re.fullmatch(rf"{CODE}-?[A-Z0-9]*", s) and m:
                s, i = f"{s}{m.group(1)} {m.group(2)}", i + 1
            out.append((page, s))
        i += 1
    return out


def book_codes(text):
    """the codes the research book defines -> {code: (page, quote)}, the first definition of each, as the book writes
    them: 'HW02-SPARK — 불티·열 전달 …' at a line's start (quoted to the next definition), a section title '1.2 재검토
    보완 — PE15-HEAT 열 축적·온열질환', and a part defined in a sentence of its group, 'PE12-HEARING: 청력 손상 …'
    (quoted from the condition before it to the end of its clause: '산소 과다가 확인되면 PE03-O2HIGH: 착화 시 연소 확대
    위험'). A code only mentioned elsewhere is not a definition."""
    lines = book_lines(text)
    flat, at = "", []                         # the text as one string, and where each line starts (page, offset)
    for page, s in lines:
        at.append((len(flat), page))
        flat += s + "\n"
    page_of = lambda pos: next(pg for off, pg in reversed(at) if off <= pos)
    heads = (list(re.finditer(rf"(?m)^({CODE})\s*—", flat)) + list(re.finditer(rf"—\s*({CODE}-[A-Z0-9]+) (?=\S)", flat))
             + list(re.finditer(r"(?m)^\[(R42-\d{2}-[A-Z]+)\]\s", flat)))
    starts = sorted({flat.rfind("\n", 0, m.start(1)) + 1 for m in heads})     # a definition ends where the next one's line starts
    found = {}
    one = lambda t: re.sub(r"\s+", " ", t.replace("**", "")).strip()
    for m in heads:
        code = m.group(1)
        end = next((x for x in starts if x > m.start(1)), len(flat))
        if code not in found:
            found[code] = (0, page_of(m.start(1)), one(flat[m.start(1):end])[:220])
    for m in re.finditer(rf"({CODE}-[A-Z0-9]+):\s*", flat):
        code = m.group(1)
        if code in found and found[code][0] == 0:
            continue
        before = flat[max(0, m.start() - 160):m.start()].replace("\n", " ")
        cut = max(before.rfind(", "), before.rfind(". "), before.rfind("다."), before.rfind("**"), before.rfind("— "))
        cond = before[cut + 2:] if cut >= 0 else before[-60:]
        after = re.match(r"[^,.]*(?:[,.]|$)", flat[m.end():m.end() + 200].replace("\n", " ")).group(0)
        if code not in found:
            found[code] = (1, page_of(m.start()), one(f"{cond}{code}: {after}")[:220])
    return {c: v[1:] for c, v in found.items()}


def research_refs(docs, book=None):
    """checklist research references -> {ref: {status, page?, quote?, candidate?}}: linked when every code in the ref
    is defined in the research book (a group code 'EL13' with its parts EL13-ELECTRIC … is the group); otherwise
    미연결 with a search candidate (not cited). A part of a ref that is not a code (사례 C23) is kept as such."""
    codes = book_codes(book) if book else {}
    spec = json.loads((ROOT / "server" / "checklist_spec.json").read_text(encoding="utf-8"))
    items = [(None, it) for it in spec["common"]] + [(kk, it) for kk, k in spec["kinds"].items() for it in k["items"]]
    team = [d for d in docs if d["authority"] == "팀" and not d.get("synthetic")]
    out = {}
    sys.path.insert(0, str(ROOT))
    from server import retrieval
    retrieval.CORPUS = OUT
    retrieval._IX.update(ix=None, meta=None)
    for kind, it in items:
        ref = it.get("ref") or ""
        if not ref or re.search(r"규칙|법", ref):
            continue
        parts = [x.strip() for x in ref.split("·")]
        mine = [x for x in parts if re.fullmatch(CODE, x)]
        linked = []
        for x in mine:
            subs = sorted(c for c in codes if c.startswith(x + "-"))
            if x in codes:
                linked.append((x, *codes[x]))
            elif subs and re.fullmatch(r"[A-Z]{2}\d{2}", x):     # a group the book defines by its parts: every part
                linked += [(c, *codes[c]) for c in subs]
        if mine and all(any(c == x or c.startswith(x + "-") for c, *_ in linked) for x in mine):
            pages = sorted({pg for _, pg, _ in linked})
            each = 600 // len(linked)
            out[ref] = {"status": "연결", "item": it["id"], "id": f"team:book412:p{pages[0]}",
                        "ref": f"팀 조사본(412쪽) {'·'.join(map(str, pages))}쪽",
                        "codes": [c for c, _, _ in linked],
                        "quote": " / ".join(q if len(q) <= each else q[:each - 1] + "…" for _, _, q in linked),
                        "match": "조사본 정의 표의 같은 코드",
                        **({"rest": [x for x in parts if x not in mine]} if len(mine) < len(parts) else {})}
            continue
        hit = next((d for d in team if ref in d["text"]), None)
        if hit:
            i = hit["text"].index(ref)
            out[ref] = {"status": "연결", "item": it["id"], "id": hit["id"], "ref": hit["ref"], "quote": hit["text"][max(0, i - 40):i + 80]}
            continue
        hits = retrieval.search(f"{it['title']} {it.get('why', '')}", k=6, authority="팀", synthetic=False,
                                work_kind=kind if kind in WORK_KIND else None, topic=["hazard", "accident", "control"])
        cand = [h for h in hits if not kind or kind not in WORK_KIND or kind in (h.get("work_kind") or [])][:1]   # of that kind itself
        why = ("조사본 코드가 아님(사례집·보고서·멘토 메모 등 다른 자료의 표시)" if not mine
               else f"조사본에 정의가 없는 코드: {', '.join(x for x in mine if not any(c == x or c.startswith(x + '-') for c, *_ in linked))}")
        out[ref] = {"status": "미연결", "item": it["id"], "why": why,
                    "candidate": ({"id": cand[0]["id"], "ref": cand[0]["ref"], "text": cand[0]["text"][:160], "reviewed": False} if cand else None)}
    return out


def cited():
    """the articles the app cites anywhere (rules, checklist, permit kinds, need reasons): {(short law, article)}"""
    text = ""
    for f in ("pair_rules.json", "checklist_spec.json"):
        text += (ROOT / "server" / f).read_text(encoding="utf-8")
    for f in ("permit_kinds.py", "need_catalog.py"):
        text += (ROOT / "server" / f).read_text(encoding="utf-8")
    out = set()
    for m in re.finditer(r"(안전보건규칙|산업안전보건기준에\s*관한\s*규칙|산업안전보건법|원자력안전법)(?=([^\"\n]{0,160}))", text):
        law = {"산업안전보건법": "산업안전보건법", "원자력안전법": "원자력안전법"}.get(m.group(1), "안전보건규칙")
        tail = re.split(r"(?:안전보건규칙|산업안전보건기준에\s*관한\s*규칙|산업안전보건법|원자력안전법)", m.group(2))[0]
        for a in ART.findall(tail):
            out.add((law, a))
    return out


def fetch_law(seq, ef):
    url = f"https://www.law.go.kr/LSW/lsInfoR.do?lsiSeq={seq}&chrClsCd=010202&urlMode=lsInfoP&efYd={ef}&ancYnChk=0"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    raw = urllib.request.urlopen(req, timeout=90).read()
    t = re.sub(r"<[^>]+>", " ", raw.decode("utf-8", "ignore"))
    t = re.sub(r"&lt;", "<", re.sub(r"&gt;", ">", re.sub(r"&nbsp;|&amp;", " ", t)))
    return url, hashlib.sha256(raw).hexdigest()[:16], re.sub(r"\s+", " ", t)


def articles(text):
    """the body's articles: {제N조(의M): (title, text)} — the first full occurrence with a title (the table of contents
    has no body)"""
    out = {}
    for m in re.finditer(r"(제\d+조(?:의\d+)?)\(([^()]{1,40})\)\s(.*?)(?=\s제\d+조(?:의\d+)?\([^()]{1,40}\)\s|$)", text):
        a, title, body = m.group(1), m.group(2), m.group(3).strip()
        body = re.split(r"\s제\d+(?:장|절|관)\s", body)[0]             # not the next part's heading
        if a not in out and len(body) > 30:
            out[a] = (title.strip(), body)                              # whole (cut into chunks below, not truncated)
    return out


def law_parts(body, size=LAW_CHUNK):
    """an article cut into consecutive pieces at its 항(①②…) and 호(1. 2. …) boundaries, none longer than needed:
    a 항 longer than size is cut at its 호; nothing is dropped (joined back, the pieces give the body)"""
    if len(body) <= size:
        return [body]
    units = []
    for hang in re.split(r"(?=\s[①-⑳])", body):
        if len(hang) <= size:
            units.append(hang)
        else:
            units += re.split(r"(?=\s\d{1,2}\.\s)", hang)
    out, cur = [], ""
    for u in units:
        if cur and len(cur) + len(u) > size:
            out.append(cur)
            cur = ""
        cur += u
    if cur:
        out.append(cur)
    assert "".join(out) == body
    return [x.strip() for x in out]


def chunks(text, size=520):
    """pieces of about size letters, cut at a sentence or line end; a table row is not cut in the middle"""
    out, cur = [], ""
    for part in re.split(r"(?<=[.다요])\s+|\n", text):
        part = part.strip()
        if not part:
            continue
        if len(cur) + len(part) > size and cur:
            out.append(cur)
            cur = ""
        cur = (cur + " " + part).strip()
    if cur:
        out.append(cur)
    return [c for c in out if len(c) >= 40]


def main():
    today = datetime.date.today().isoformat()
    docs, sources = [], []
    want = cited()
    for name, (seq, ef, short) in LAWS.items():
        url, h, text = fetch_law(seq, ef)
        arts = articles(text)
        sources.append({"source_id": f"law:{short}", "title": name, "authority": "법령", "revision": f"시행 {ef[:4]}.{int(ef[4:6])}.{int(ef[6:])}",
                        "url": url, "hash": h, "fetched": today})
        for law, a in sorted(want):
            if law != short or a not in arts:
                continue
            title, body = arts[a]
            parts = law_parts(body)
            for n, part in enumerate(parts, 1):
                txt = (f"{a}({title}) " if n == 1 else f"{a}({title}) (이어서) ") + part
                docs.append({"id": f"law:{short}:{a}" + (f"#{n}" if len(parts) > 1 else ""), "authority": "법령",
                             "section": f"{a}({title})" + (f" {n}/{len(parts)}" if len(parts) > 1 else ""), "ref": f"{short} {a}",
                             "text": txt, "legal_verified": True, "reviewed": True,
                             **meta(txt, source_id=f"law:{short}", revision=f"시행 {ef[:4]}.{int(ef[4:6])}.{int(ef[6:])}", hash_=h, authority="법령",
                                    company="공통(법령)", effective="현행", quality="국가법령정보센터 본문 HTML")})
        missing = sorted(a for law, a in want if law == short and a not in arts)
        if missing:
            print(f"{short}: 본문에서 못 찾은 인용 조문 {missing}", file=sys.stderr)
    # the team's research notes, page by page
    note = (DATA / "노션_추가본_전체정보_2026-10-25_텍스트.txt").read_text(encoding="utf-8")
    nh = hashlib.sha256(note.encode()).hexdigest()[:16]
    sources.append({"source_id": "team:notion", "title": "조선소 현장 전산 프로세스·대조립 공정 조사(팀 Notion 추출, 119쪽)", "authority": "팀",
                    "revision": "2026-10-25", "url": "", "hash": nh, "fetched": today})
    for m in re.finditer(r"===== PAGE (\d+)[^\n]*=====\n(.*?)(?=\n===== PAGE |\Z)", note, re.S):
        page, body = int(m.group(1)), m.group(2)
        sec = next((why for a, b, why in SYN_SECTIONS if a <= page <= b), None)
        page_syn = sec or ("쪽에 가상·합성·예시 표시" if SYN_PAGE.search(body) else None)
        for i, c in enumerate(chunks(body)):
            why = page_syn or ("가상 설정값(3.6m·38톤·380V 등)" if SYN_VALUES.search(c) else None)
            docs.append({"id": f"team:notion:p{page}:{i}", "section": f"{page}쪽",
                         "ref": f"팀 조사 {page}쪽", "text": c, **({"synthetic_why": why} if why else {}),
                         "legal_verified": False, "reviewed": False,
                         **meta(c, source_id="team:notion", revision="2026-10-25", hash_=nh, authority="팀", company="조선 3사 공통 조사",
                                effective="예시(가상)" if why else "조사 자료(2026-10-25)", quality="Notion 추출 텍스트", pdf_page=page,
                                synthetic=bool(why))})
    import fitz
    # the public guides, page by page (the table of contents and the cover left out)
    for f, no, title, rev, url in GUIDES:
        p = DATA / "공공_KOSHA" / f
        if not p.exists():
            print(f"{f}: 파일 없음", file=sys.stderr)
            continue
        sid = f"kosha:{no}"
        sources.append({"source_id": sid, "title": f"KOSHA GUIDE {no} {title}", "authority": "공공", "revision": rev, "url": url,
                        "hash": hashlib.sha256(p.read_bytes()).hexdigest()[:16], "fetched": today})
        d = fitz.open(p)
        gh = sources[-1]["hash"]
        for i, page in enumerate(d):
            t = re.sub(r"\s+", " ", page.get_text()).strip()
            if i < 2 or len(t) < 120 or re.search(r"·{8,}", t):
                continue
            for j, c in enumerate(chunks(t, 520)):
                docs.append({"id": f"{sid}:p{i + 1}:{j}", "section": f"{i + 1}쪽",
                             "ref": f"KOSHA {no} {i + 1}쪽", "text": c, "legal_verified": False, "reviewed": False,
                             "use": "기술적 권고(법적 최저기준 아님)",
                             **meta(c, source_id=sid, revision=rev, hash_=gh, authority="공공", company="공통(공공기관)",
                                    effective="현행 여부 미확인" if "미확인" in rev else "현행(2026 공표)",
                                    quality="PDF 글자(띄어쓰기 일부 손실)", pdf_page=i + 1,
                                    supersedes=f"KOSHA {no.rsplit('-', 1)[0]} 이전 판" if no.endswith("2026") else None)})
    # the shipyards' public reports: passages on terms and policy only
    for f in REPORTS:
        p = DATA / "조선3사_공식자료" / f
        if not p.exists():
            continue
        d = fitz.open(p)
        sid = "yard:" + f.split("_")[0] + ":" + f.split("_")[1]
        sources.append({"source_id": sid, "title": f.rsplit(".", 1)[0].replace("_", " "), "authority": "조선사", "revision": f.split("_")[1],
                        "url": "", "hash": hashlib.sha256(p.read_bytes()[:4_000_000]).hexdigest()[:16], "fetched": today})
        n = 0
        for i, page in enumerate(d):
            t = re.sub(r"\s+", " ", page.get_text())
            if not TERMS.search(t):
                continue
            for j, c in enumerate(chunks(t, 480)):
                if TERMS.search(c) and n < 40:
                    docs.append({"id": f"{sid}:p{i + 1}:{j}", "section": f"{i + 1}쪽",
                                 "ref": f"{f.split('_')[0]} {f.split('_')[1]} {i + 1}쪽", "text": c,
                                 "legal_verified": False, "reviewed": False, "use": "용어·정책 설명만(회사 허가 기준 아님)",
                                 **meta(c, source_id=sid, revision=f.split("_")[1], hash_=sources[-1]["hash"], authority="조선사",
                                        company=f.split("_")[0], effective="보고서 발행본", quality="PDF 글자", pdf_page=i + 1)})
                    n += 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"built": today, "sources": sources, "docs": docs}, ensure_ascii=False, indent=0), encoding="utf-8")
    refs = research_refs(docs, BOOK.read_text(encoding="utf-8") if BOOK.exists() else None)
    REFS_OUT.write_text(json.dumps({"built": today, "refs": refs}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{REFS_OUT.name}: 연구 ref {len(refs)}개 · 연결 {sum(1 for r in refs.values() if r['status'] == '연결')}개")
    by = {}
    for x in docs:
        by[x["authority"]] = by.get(x["authority"], 0) + 1
    print(f"{OUT.name}: {len(docs)} 청크 {by} · 인용 조문 {len(want)}개")


if __name__ == "__main__":
    main()
