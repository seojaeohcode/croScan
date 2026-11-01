"""관리자 요약 (design §6.5·§19.1): for each document of the day, what the safety manager reads first — 시간 · 장소 ·
대상 · 공유 설비 · 단계 · 상충 · 미확인 — and what croScan's AI did with it (문서별 AI 읽기 결과): the foreman's
confirmed answers and readings in his submission, what the upload analysis found and what is still open, and for a
작업계획서 its 허가 검토 신호 (permitsignal) and the labels croScan could not read. Made from the documents, the
submissions and the rules only; nothing here is written into a document or changes a pair.
"""
import re

from . import pairs, permitsignal, submissions, workplan

ORDER = ("시간", "장소", "대상", "공유 설비", "단계", "상충", "미확인")


def _times(d):
    w = d.get("windows") or []
    if not w:
        return "시간 없음", True
    t = ", ".join(f"{x['start']}~{x['end']}" + (" (다음 날)" if x.get("next_day") else "") for x in w)
    if d.get("move"):
        t += f" (실제 이동 {d['move']['start']}~{d['move']['end']})"
    return t, False


def rows(d, det=None):
    """[(label, text, flag)] in the order the manager reads; flag: 'warn' for what is not known or in conflict"""
    out = []
    t, unk = _times(d)
    out.append(("시간", t, "warn" if unk else ""))
    sp = d.get("spans") or []
    out.append(("장소", (d.get("place") or "장소 없음") + ("" if sp else " · BAY·칼럼 미확인"), "" if sp else "warn"))
    prof = pairs.profile(d)
    ids = prof["ids"]
    tgt = sorted(ids["blocks"]) + ([d["target"]] if d.get("type") == "plan" and d.get("target") else [])
    out.append(("대상", ", ".join(dict.fromkeys(tgt)) or "대상 번호 없음", "" if tgt else "warn"))
    eq = [f"크레인 {x}" for x in sorted(ids["crane_use"])] + [f"크레인 정전 {x}" for x in sorted(ids["crane_loto"])] \
        + [f"전원 {x}" for x in sorted(ids["power_use"])] + [f"전원 차단 {x}" for x in sorted(ids["power_loto"])] \
        + [f"계통 {x}" for x in sorted(ids["systems"])]
    out.append(("공유 설비", ", ".join(eq) or "적힌 설비 번호 없음", ""))
    if d.get("type") == "plan":
        steps = [x["value"] for x in d.get("_items") or [] if re.fullmatch(r"\d+\s*단계", x.get("label") or "") and x.get("value")]
        out.append(("단계", " → ".join(steps) or "단계 없음", ""))
    else:
        st = [x for x in (d.get("isolation") and f"차단·복구 {d['isolation']}", d.get("route") and f"이동 경로 {d['route']}") if x]
        out.append(("단계", " · ".join(st) or "-", ""))
    mine = [p for p in (det or {}).get("pairs") or [] if d["id"] in (p["a"], p["b"])]
    conf = []
    said_none = (d.get("concurrent") or "") if d.get("type") == "permit" else next(
        (x["value"] for x in d.get("_items") or [] if x.get("label") == "혼재작업"), "")
    if mine and ("없" in said_none):
        conf.append(f"서류의 병행·혼재 「{said_none}」 · 규칙 위험 쌍 {len(mine)}쌍")
    out.append(("상충", " / ".join(conf) or "없음", "warn" if conf else ""))
    unk = []
    if d.get("type") == "permit":
        if d.get("unconfirmed"):
            unk.append(f"미확인 답변 {d['unconfirmed']}건")
        if d.get("open_questions"):
            unk.append(f"답하지 않은 질문 {d['open_questions']}건")
        if (d.get("checklist") or {}).get("check"):
            unk.append(f"체크리스트 안전팀 확인 {d['checklist']['check']}개")
    if not d.get("windows"):
        unk.append("작업 시간")
    if not sp:
        unk.append("BAY·칼럼")
    out.append(("미확인", ", ".join(unk) or "없음", "warn" if unk else ""))
    return out


def ai_reading(d, sub=None):
    """문서별 AI 읽기 결과: for a permit, its latest submission (the foreman's confirmed answers and readings, the
    upload analysis, what is left to the safety team); for a plan, the labels not read. -> {lines: [str], state}"""
    if d.get("type") == "plan":
        unknown = workplan.unknown_labels({"items": d.get("_items") or []})
        lines = [f"읽지 못한 칸 {len(unknown)}개: " + ", ".join(x["label"] for x in unknown[:4])] if unknown else []
        return {"lines": lines, "state": "읽기 확인 필요" if unknown else ""}
    if not sub:
        return {"lines": ["croScan 제출본 없음 · AI 읽기 결과 없음"], "state": "미분석"}
    got = submissions.get(sub["id"])
    payload = got[0] if got else {}
    ans = payload.get("answers") or []
    adopted = [a for a in ans if a.get("pid")]
    ai = [a for a in adopted if a.get("ai")]
    facts = pairs.confirmed_facts(ans)
    an = payload.get("analysis") or {}
    lines = [f"작업반장 답 {len([a for a in ans if not a.get('pid')])}건 · 확인한 읽기 {len(adopted)}건(AI 읽음 {len(ai)}건)"]
    if facts:
        lines.append("위험 쌍 입력에 더한 확인 사실: " + ", ".join(f"{x['item']} {x['value']}" for x in facts[:4]))
    if an:
        st = an.get("status")
        lines.append("업로드 분석: " + ("완료" if st in ("ok", "none", "done") else "AI 결과를 준비하지 못함" if st in ("fail", "preempted") else
                                   "대화가 끝난 뒤 끝나 묻지 않음" if st == "late" else "허가서가 바뀌어 쓰지 않음" if st == "stale" else str(st or "-"))
                     + (f" · 찾은 확인할 것 {an.get('found')}건" if an.get("found") else ""))
    un = payload.get("unresolved") or []
    if un:
        lines.append(f"안전팀 확인 필요 {len(un)}건")
    return {"lines": lines, "state": "확인함" if adopted else "AI 읽음" if ai else ""}


def build(D, det=None, ai_kinds=None):
    """{doc id: {rows, ai, signals}} for every document of the day"""
    subs = submissions.latest(D.get("date"))
    sig = {}
    for s in permitsignal.signals(D, ai_kinds):
        sig.setdefault(s["plan"], []).append(s)
    out = {}
    for d in D["permits"] + D["plans"]:
        out[d["id"]] = {"rows": [list(r) for r in rows(d, det)],
                        "ai": ai_reading(d, subs.get(d.get("permit_no")) if d.get("type") == "permit" else None),
                        "signals": sig.get(d["id"], [])}
    return out
