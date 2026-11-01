"""검색 (RAG, design §3.4): BM25 over Korean letter 2~3-grams and words, with filters on the source's authority,
the standard library only. The corpus is server/knowledge/corpus.json (tools/build_corpus.py); the index is built
once, at the first search.

A search finds passages to show and to check against; it never decides anything. A passage found is not evidence
that a duty applies (the law layer is shown as what the article says, the team layer as research notes, the
shipyards' reports as terms and policy only, synthetic passages marked 「예시」), and a search that finds nothing is
not evidence that nothing applies (design §3.4).
"""
import json
import math
import re
from collections import Counter
from pathlib import Path

CORPUS = Path(__file__).parent / "knowledge" / "corpus.json"
GRADE = {"법령": "법령", "공공": "공공", "조선사": "조선사", "팀": "팀"}
# the yard's spoken words -> the words of the documents (design §3.4: colloquial and synonym expansion)
SYNONYMS = {"용접": ["용접", "용단", "화재위험작업"], "절단": ["용단", "절단"], "불티": ["불티", "불꽃", "비산"], "화기": ["화재위험작업", "용접", "용단"],
            "밀폐": ["밀폐공간", "산소결핍", "유해가스"], "탱크": ["밀폐공간", "탱크"], "질식": ["산소결핍", "질식", "밀폐공간"],
            "크레인": ["크레인", "양중기", "인양"], "인양": ["크레인", "양중기", "인양"], "신호수": ["신호", "신호수"],
            "정전": ["정전전로", "전원 차단", "잠금장치"], "LOTO": ["잠금장치", "꼬리표", "정전전로"], "차단": ["차단", "잠금장치"],
            "추락": ["추락", "고소작업"], "낙하": ["낙하물", "낙하"], "아래": ["하부", "낙하물"], "감시인": ["감시인", "화재감시자"],
            "아르곤": ["불활성기체", "아르곤"], "질소": ["불활성기체", "질소"], "퍼지": ["불활성기체", "퍼지"], "환기": ["환기", "통풍"],
            "방사선": ["방사선", "방사선관리구역"], "RT": ["방사선", "비파괴"], "압력시험": ["기밀시험", "압력"], "혼재": ["혼재", "도급", "협의"],
            "작업중지": ["작업중지권", "작업 중지"], "러그": ["러그", "용단", "절단"], "회수": ["낙하물", "하부"]}
K1, B = 1.4, 0.75
# team notes later corrected by the field (현장 정정 2026-10-29·10-31 D01: 전산승인은 생산부서 승인권한자, 안전 측은
# 검토·지원·현장 확인; D02: 아침 대면허가는 PTW 스캔 때 정해지는 Y/N으로 갈림 — Y면 실제 작업일마다, N이면 대상 아님;
# 허가구분만으로 대면허가 여부를 정하지 않음): never shown or handed on, whatever the filters (kept here so a corpus
# rebuild does not bring them back)
CORRECTED = {"team:notion:p2:0": "안전관리자가 허가서를 최종 승인한다는 설명 → 생산부서 전산승인으로 정정",
             "team:notion:p3:0": "「전산허가는 안전대면허가 불필요」(허가구분으로 대면허가를 정함) → 대면허가는 Y/N으로 정정",
             "team:notion:p9:0": "안전팀이 전산승인한다는 회의록 설명 → 생산부서 전산승인으로 정정"}


def _grams(s):
    s = re.sub(r"\s+", " ", (s or "").lower())
    out = []
    for w in re.findall(r"[가-힣]+|[a-z0-9]+", s):
        out.append("w:" + w)
        if re.match(r"[가-힣]", w):
            out += [w[i:i + n] for n in (2, 3) for i in range(len(w) - n + 1)]
    return out


class _Index:
    def __init__(self, docs):
        self.docs = docs
        self.tf = [Counter(_grams(d["text"] + " " + d.get("section", ""))) for d in docs]
        self.len = [sum(c.values()) for c in self.tf]
        self.avg = sum(self.len) / max(1, len(self.len))
        df = Counter(g for c in self.tf for g in c)
        n = len(docs)
        self.idf = {g: math.log(1 + (n - v + 0.5) / (v + 0.5)) for g, v in df.items()}

    def score(self, i, q):
        tf, s = self.tf[i], 0.0
        for g, w in q.items():
            f = tf.get(g)
            if f:
                s += w * self.idf[g] * f * (K1 + 1) / (f + K1 * (1 - B + B * self.len[i] / self.avg))
        return s


_IX = {"ix": None, "meta": None}


# a local file path in the notes (a teammate's machine: the user name in it) is not shown (staging 2026-10-31)
LOCAL_PATH = re.compile(r"\(\s*(?:/Users|/home|[A-Za-z]:[\/])[^)]*\)|(?:/Users|/home)/[^\s)]+")


def corpus():
    if _IX["meta"] is None:
        data = json.loads(CORPUS.read_text(encoding="utf-8")) if CORPUS.exists() else {"docs": [], "sources": [], "built": None}
        for d in data["docs"]:
            d["text"] = re.sub(r"\s{2,}", " ", LOCAL_PATH.sub("", d["text"]))
        _IX["meta"] = data
        _IX["ix"] = _Index(data["docs"])
    return _IX["meta"]


def expand(query):
    """the query and the documents' words for the yard's words in it"""
    extra = [w for k, ws in SYNONYMS.items() if k.lower() in query.lower() for w in ws]
    return query + (" " + " ".join(extra) if extra else "")


def _as_set(v):
    return {v} if isinstance(v, str) else set(v or [])


def search(query, k=12, authority=None, synthetic=True, exclude=(), reviewed=None, work_kind=None, company=None, topic=None,
           effective=None):
    """-> up to k passages [{id, ref, authority, section, text, score, synthetic, reviewed, source_id, …}], best first.
    authority: a grade or a list of grades to keep; synthetic: True keeps all, False leaves out passages marked made
    up, "only" keeps only those; reviewed: True keeps only reviewed layers (the collected law text); exclude: ids.
    work_kind: permit kinds (hot, confined, height, lifting, loto, …) — a passage of one of them or a common one is
    kept; company: company scopes to keep (a 공통 passage always stays); topic: topics to keep; effective: False
    leaves out what is not in force or not confirmed (예시·현행 여부 미확인). Every filter is applied before scoring
    (design §3.4: 권한·회사·활성 버전·작업 종류 먼저), so a filtered-out passage never takes a place in the top k."""
    corpus()
    ix = _IX["ix"]
    q = Counter(_grams(expand(query)))
    if not q:
        return []
    keep, kinds, comps, tops = _as_set(authority), _as_set(work_kind), _as_set(company), _as_set(topic)
    hits = []
    for i, d in enumerate(ix.docs):
        syn = bool(d.get("synthetic"))
        if ((keep and d["authority"] not in keep) or (synthetic is False and syn) or (synthetic == "only" and not syn)
                or (reviewed and not d.get("reviewed")) or d["id"] in exclude or d["id"] in CORRECTED):
            continue
        if kinds and not (kinds & set(d.get("work_kind") or ["common"]) or "common" in (d.get("work_kind") or ["common"])):
            continue
        if comps and not (d.get("company_scope") in comps or "공통" in str(d.get("company_scope") or "")):
            continue
        if tops and not tops & set(d.get("topic") or []):
            continue
        if effective is False and str(d.get("effective_status") or "").startswith(("예시", "현행 여부 미확인")):
            continue
        s = ix.score(i, q)
        if s > 0:
            hits.append((s, i))
    hits.sort(reverse=True)
    out, seen = [], set()
    for s, i in hits:
        d = ix.docs[i]
        key = re.sub(r"\s+", "", d["text"])[:80]                      # the same passage twice (a repeated page): once
        if key in seen:
            continue
        seen.add(key)
        out.append({**{x: d.get(x) for x in ("id", "ref", "authority", "section", "text", "synthetic", "synthetic_why", "reviewed", "source_id", "use",
                                              "revision", "work_kind", "topic", "company_scope", "effective_status")},
                    "score": round(s, 2)})
        if len(out) >= k:
            break
    return out


def source(sid):
    return next((s for s in corpus()["sources"] if s["source_id"] == sid), None)


def article(law, art):
    """the whole article when its current text was collected (its pieces joined in order), or None"""
    corpus()
    base = f"law:{law}:{art}"
    parts = [d for d in _IX["ix"].docs if d["id"] == base or d["id"].startswith(base + "#")]
    if not parts:
        return None
    parts.sort(key=lambda d: int(d["id"].split("#")[1]) if "#" in d["id"] else 0)
    text = parts[0]["text"] + "".join(" " + re.sub(r"^\S+\([^)]*\) \(이어서\) ", "", d["text"]) for d in parts[1:])
    return {**parts[0], "id": base, "section": parts[0]["section"].split(" ")[0], "text": text, "parts": len(parts)}


MIN_SCORE = 8


# 인용 검사 (design §3.4): a passage shown or handed on is cited as source_id / revision / span (the words as they
# stand in that passage); before use the citation is checked against the corpus as built. A citation that does not
# hold is not shown; what is missing is said as a MissingObservation, never filled with a made-up citation.
def cite(d, words=None):
    """-> {id, source_id, revision, span: [start, end], quote} for words of passage d (all of it by default)"""
    text = d["text"]
    q = (words or text[:160]).strip()
    i = text.find(q)
    return {"id": d["id"], "source_id": d.get("source_id"), "revision": d.get("revision"),
            "span": [i, i + len(q)] if i >= 0 else None, "quote": q}


def check_cite(c):
    """-> (True, '') when the citation holds: the passage exists, its source's revision is the one cited, the quoted
    words stand at the span; else (False, why)"""
    corpus()
    d = next((x for x in _IX["ix"].docs if x["id"] == c.get("id")), None)
    if not d:
        return False, "없는 자료"
    if c.get("source_id") != d.get("source_id"):
        return False, "출처가 다름"
    if (c.get("revision") or None) != (d.get("revision") or None):
        return False, "개정이 다름"
    sp, q = c.get("span"), c.get("quote") or ""
    if not sp or d["text"][sp[0]:sp[1]] != q:
        return False, "구절이 그 자리에 없음"
    return True, ""


def missing(what, where=""):
    """a fact the documents do not give, said as such (not a citation)"""
    return {"type": "MissingObservation", "what": what, "where": where}


_REFS = {"data": None}


def research_ref(ref):
    """a checklist research reference (HW02-SPARK …) -> its record in research_refs.json: 연결 (page and words) or
    미연결 with a candidate passage (not cited), or None"""
    if _REFS["data"] is None:
        p = CORPUS.parent / "research_refs.json"
        _REFS["data"] = json.loads(p.read_text(encoding="utf-8")).get("refs", {}) if p.exists() else {}
    return _REFS["data"].get(ref)


def related(text, k=2):
    """passages related to a question's reason, for 「왜 묻나요?」 (design §3.4): the law layer (current text collected)
    and the team's and shipyards' passages (not reviewed: shown as 검색 후보), never a made-up one; only clear hits.
    -> [{id, ref, grade, text, reviewed}] — a search result to read, not a basis the question stands on."""
    # only for a question about a hazard or equipment (a word of the yard's vocabulary in it), and only passages that
    # speak of that same thing: a time or place question stands on its own reason (staging 2026-10-31: a 작업시간
    # question drew notes about permit types)
    topics = {w for k, ws in SYNONYMS.items() for w in [k, *ws] if len(w) >= 2 and w.lower() in text.lower()}
    if not topics:
        return []
    hits = [h for h in search(text, k=8, synthetic=False) if h["score"] >= MIN_SCORE and any(t.lower() in h["text"].lower() for t in topics)]
    if not hits:
        return []
    # the collected law text first when it is near the best hit (a long reason scores many team notes alike)
    law = next((h for h in hits if h["authority"] == "법령" and h["score"] >= 0.6 * hits[0]["score"]), None)
    out = []
    for h in ([law] if law else []) + [h for h in hits if h is not law][:k - (1 if law else 0)]:
        c = cite(h)
        if not check_cite(c)[0]:                                     # a citation that does not hold is not shown
            continue
        out.append({"id": h["id"], "ref": h["ref"], "grade": GRADE.get(h["authority"], h["authority"]),
                    "text": re.sub(r"\s+", " ", h["text"])[:160], "reviewed": bool(h.get("reviewed")), "cite": c})
    return out


def for_analysis(text, kind=None, k=3):
    """design §3.4 (§1.3 업로드 분석): 2~3 passages to hand to the upload analysis as reference — the collected law text
    and the public guides first, the kinds of this permit, nothing made up or not in force; each checked as cited.
    The model reads them as reference only (they decide nothing)."""
    hits = search(text, k=8, authority=["법령", "공공"], synthetic=False, work_kind=kind, effective=False)
    out = []
    for h in hits:
        if h["score"] < MIN_SCORE:
            continue
        c = cite(h)
        if check_cite(c)[0]:
            out.append({"id": h["id"], "ref": h["ref"], "grade": GRADE.get(h["authority"], h["authority"]),
                        "text": re.sub(r"\s+", " ", h["text"])[:220], "cite": c})
        if len(out) >= k:
            break
    return out
