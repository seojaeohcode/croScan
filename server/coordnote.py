"""협조 문자의 「협의할 점」 (WRITE, design §6.5·§19.1): one sentence the safety manager may put into the coordination
message for a pair, drawn from a foreman's confirmed fact about his own work on this pair (the evidence row
「작업반장 답변 · 반장 답변 확인」) and one of the things the rule asks to be checked. Only with such a fact: without
one there is nothing to propose (the rule's message stays as it is).

The model only picks which confirmed fact and which of the rule's check items fit together; the sentence is the
server's: 「{문서} 반장 확인 답 「{사실}」에 맞춰 {확인할 것}을 서로 확인해 주세요.」 — so no time, order, name or
number can be made up and nothing is decided (a free sentence let 「4개」 become 「4시」 or put in a name: Codex review
2026-10-31). Nothing goes into the message without the manager's click.
"""
import re

from . import llm, pairs

SYSTEM = ("너는 조선소 안전관리자가 두 작업반장에게 보내는 협조 문자에 넣을 「협의할 점」을 고른다. "
          "주어진 반장 확인 사실 가운데 하나(f)와, 규칙이 확인하라는 것 가운데 그 사실과 가장 관련 있는 하나(c)를 고른다. 문장은 쓰지 않는다.")


def sources(p, no):
    """the confirmed facts on this pair's reasons -> [{doc, no, value}] (once each)"""
    out, seen = [], set()
    for r in p["reasons"]:
        for e in r.get("evidence") or []:
            if e.get("confirmed") and (e["doc"], e["value"]) not in seen:
                seen.add((e["doc"], e["value"]))
                out.append({"doc": e["doc"], "no": no(e["doc"]), "value": e["value"]})
    return out


def items(ask):
    """the rule's things to check, one by one ('상부 작업과 하부 작업의 실제 높이·시간' stays whole; 'A, B' splits)"""
    return [x.strip() for x in re.split(r"\s*[,/;]\s*|\s+및\s+", ask or "") if x.strip()] or ([ask.strip()] if ask and ask.strip() else [])


def sentence(src, item):
    return f"{src['no']} 반장 확인 답 「{src['value']}」에 맞춰 {pairs._josa(item, '을를')} 서로 확인해 주세요."


def model_input(p, no):
    """everything the note is made from (also the key of a note made before)"""
    R = p["reasons"][0]
    return {"cause": R["cause"], "exposed": R["exposed"], "rule": R["rule"], "name": R["name"], "headline": R.get("headline") or "",
            "items": items(R.get("ask")), "sources": sources(p, no)}


async def note(p, no, deadline=30.0, pri=None):
    """-> {status: ok|fixed|none, text, sources, why}"""
    m = model_input(p, no)
    src, its = m["sources"], m["items"]
    if not src or not its:
        return {"status": "none", "text": "", "sources": [], "why": "확인된 반장 답이 없음" if not src else "규칙의 확인할 것이 없음"}
    if len(src) == 1 and len(its) == 1:
        return {"status": "fixed", "text": sentence(src[0], its[0]), "sources": src, "why": "고를 것이 하나뿐"}
    user = (f"작업쌍: {m['cause']} × {m['exposed']} · {m['name']} · {m['headline']}\n반장 확인 사실:\n"
            + "\n".join(f"F{i} {x['no']}: 「{x['value']}」" for i, x in enumerate(src, 1))
            + "\n규칙이 확인하라는 것:\n" + "\n".join(f"C{i} {x}" for i, x in enumerate(its, 1)))
    fs, cs = [f"F{i}" for i in range(1, len(src) + 1)], [f"C{i}" for i in range(1, len(its) + 1)]
    schema = {"type": "object", "additionalProperties": False, "required": ["f", "c"],
              "properties": {"f": {"type": "string", "enum": fs}, "c": {"type": "string", "enum": cs}}}
    try:
        data, meta = await llm.call_json("WRITE", [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
                                         schema, think=0, out_tokens=40, deadline=deadline, pri=pri)
    except llm.LlmFail as e:
        return {"status": "fixed", "text": sentence(src[0], its[0]), "sources": src, "why": e.code}
    if not (isinstance(data, dict) and set(data) == {"f", "c"} and data["f"] in fs and data["c"] in cs):
        return {"status": "fixed", "text": sentence(src[0], its[0]), "sources": src, "why": "schema"}
    s = src[fs.index(data["f"])]
    return {"status": "ok", "text": sentence(s, its[cs.index(data["c"])]), "sources": [s], "why": None}
