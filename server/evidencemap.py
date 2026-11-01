"""근거 지도 (design §3.4.1): which basis each checklist item and pair rule has, by authority — the article the app
cites (checked against the current text), the public guides (not collected yet), the shipyards' public reports (terms
and policy only), the team's notes. A blank stays blank (「근거 보강 필요」): the map is the knowledge team's work list.

Three states of a law link are kept apart (Codex 2026-10-31 #20): 원문 수집됨 (the article's current text is in the
corpus), 인용 있음 (the rule or checklist item cites it), 규칙 적합성 검수됨 (a person checked that the article fits the
rule: law_fit 「맞음」 in pair_rules.json — the checklist's references carry no such record, so they show 「검수 기록
없음」). The [조선사] and [팀] columns are search candidates (retrieval), shown as 「검색 후보 · 검수 전」: a passage
found there is not a basis until a person links it; nothing in the app's judgement reads this map.
"""
import json
import re
from pathlib import Path

from . import retrieval

HERE = Path(__file__).parent
LAWS = (("산업안전보건기준에 관한 규칙", "안전보건규칙"), ("안전보건규칙", "안전보건규칙"), ("산업안전보건법", "산업안전보건법"), ("원자력안전법", "원자력안전법"))
ART = re.compile(r"제\d+조(?:의\d+)?")


def cites(text):
    """the articles a citation string names: [(law, 제N조)] in order, each once"""
    out, law = [], None
    for m in re.finditer(r"(산업안전보건기준에\s*관한\s*규칙|안전보건규칙|산업안전보건법|원자력안전법)|(제\d+조(?:의\d+)?)", text or ""):
        if m.group(1):
            law = next(s for k, s in LAWS if re.sub(r"\s", "", k) == re.sub(r"\s", "", m.group(1)))
        elif law and (law, m.group(2)) not in out:
            out.append((law, m.group(2)))
    return out


def _law_cell(text, fit=None, checked=None):
    got = []
    for law, a in cites(text):
        d = retrieval.article(law, a)
        got.append({"ref": f"{law} {a}", "title": d["section"] if d else "", "in_corpus": bool(d),
                    "text": (d["text"][:240] if d else ""), "id": d["id"] if d else None})
    if not got:
        return None
    # what the screen may count as 확인된 근거 (Codex A9): a person checked the fit (「맞음」) and the article's current
    # text is collected; 「약함」 and no fit record are a citation only, shown apart
    status = fit or "미검수"
    return {"links": got, "fit": fit, "checked": (checked or "")[:10], "status": status,
            "confirmed": status == "맞음" and all(x["in_corpus"] for x in got)}


def _candidates(query, authority, synthetic):
    # the filters go into the search itself (before the top k), so made-up passages never push real ones out
    hits = retrieval.search(query, k=2, authority=authority, synthetic="only" if synthetic else False)
    return [{"id": h["id"], "ref": h["ref"], "text": h["text"][:200], "score": h["score"], **({"why": h["synthetic_why"]} if h.get("synthetic_why") else {})}
            for h in hits if h["score"] >= retrieval.MIN_SCORE]


def _row(kind, rid, title, why, law_text, fit=None, checked=None, research=None):
    q = f"{title} {why}"
    return {"kind": kind, "id": rid, "title": title, "why": why,
            "법령": _law_cell(law_text, fit, checked),
            "공공": _candidates(q, "공공", False),             # KOSHA 기술지원규정: search candidates, 검수 전
            "조선사": _candidates(q, "조선사", False),
            # a research reference (HW02 …): linked to the team's words only when written there; else 미연결 with a
            # candidate (검수 전) — research_refs.json from tools/build_corpus.py
            "팀": {"research": research, "research_link": retrieval.research_ref(research) if research else None,
                  "candidates": _candidates(q, "팀", False)},
            "예시": _candidates(q, "팀", True)}


_CACHE = {}


def build():
    """-> {rows, flow, sources}; computed once per corpus build and rules file"""
    key = (retrieval.corpus().get("built"), (HERE / "pair_rules.json").stat().st_mtime_ns, (HERE / "checklist_spec.json").stat().st_mtime_ns)
    if key in _CACHE:
        return _CACHE[key]
    rules = json.loads((HERE / "pair_rules.json").read_text(encoding="utf-8"))["rules"]
    spec = json.loads((HERE / "checklist_spec.json").read_text(encoding="utf-8"))
    rows = [_row("쌍 규칙", r["id"], r["name"], r.get("mechanism") or " ".join(r.get("chain") or [])[:80], r.get("law"), r.get("law_fit"), r.get("law_checked"))
            for r in rules]
    items = [("공통", it) for it in spec["common"]] + [(k["label"], it) for k in spec["kinds"].values() for it in k["items"]]
    for label, it in items:
        ref = it.get("ref") or ""
        law = ref if cites(ref) else ""
        # the checklist keeps no record of a fit check for its law references (only pair_rules.json does): shown as
        # 「검수 기록 없음」; its research references (HW02 …) are linked to the research book's definitions where it defines them (research_refs.json)
        rows.append(_row(f"체크리스트 · {label}", it["id"], it["title"], it.get("why", ""), law, it.get("law_fit"), it.get("law_checked"),
                         research=None if law else (ref or None)))
        if law and it.get("law_articles"):              # each article's own fit (a 「인용 없음」 row says what is not covered)
            rows[-1]["법령"]["articles"] = it["law_articles"]
    C = retrieval.corpus()
    by = {}
    for d in C["docs"]:
        by[d["authority"]] = by.get(d["authority"], 0) + 1
    flow = {"sources": len(C["sources"]), "chunks": len(C["docs"]), "by_authority": by,
            "synthetic": sum(1 for d in C["docs"] if d.get("synthetic")),
            "rows": len(rows), "with_law": sum(1 for r in rows if r["법령"]),
            "law_collected": sum(1 for r in rows if r["법령"] and all(x["in_corpus"] for x in r["법령"]["links"])),
            "law_fit_ok": sum(1 for r in rows if r["법령"] and r["법령"]["fit"] == "맞음"),
            "law_weak": sum(1 for r in rows if r["법령"] and r["법령"]["fit"] == "약함"),
            "law_unchecked": sum(1 for r in rows if r["법령"] and r["법령"]["status"] == "미검수"),
            "law_confirmed": sum(1 for r in rows if r["법령"] and r["법령"]["confirmed"]),     # the only 「확인된」 count
            "with_team_candidate": sum(1 for r in rows if r["팀"]["candidates"]),
            "public": sum(1 for r in rows if r["공공"]), "empty": sum(1 for r in rows if not r["법령"]),       # no article cited: 근거 보강 필요
            "research": sum(1 for r in rows if r["팀"]["research"]),
            "research_linked": sum(1 for r in rows if (r["팀"]["research_link"] or {}).get("status") == "연결")}
    out = {"rows": rows, "flow": flow, "built": C.get("built"),
           "sources": [{k: s.get(k) for k in ("source_id", "title", "authority", "revision", "url", "hash", "fetched")} for s in C["sources"]]}
    _CACHE.clear()
    _CACHE[key] = out
    return out
