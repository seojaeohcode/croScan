"""규칙집: every rule and setting in server/ written out from the code itself, so nothing is left out.

    python tools/gen_rulebook.py            write docs/17_규칙과_설정값_전체.md
    python tools/gen_rulebook.py --check    exit 1 when the document is older than the code (the test)

What is listed: every module-level constant of server/*.py (an UPPER_CASE name: rule lists, word lists, limits, time
limits, priorities, thresholds), every regular expression compiled anywhere in server/ (with the name it is kept
under, or the function it is in), the 36 pair rules of server/pair_rules.json field by field and its scales, the 86
checklist items of server/checklist_spec.json with their proposal rules and controls, and the question catalog of
server/need_catalog.py. Each entry shows its file:line, the value as written in the code, the code's own comment, and
a Korean one-line meaning from tools/rulebook_ko.json (names without one are marked 「설명 준비 중」).
"""
import ast
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRV = ROOT / "server"
OUT = ROOT / "docs" / "17_규칙과_설정값_전체.md"
KO = ROOT / "tools" / "rulebook_ko.json"
LONG = 400                                   # a value longer than this is folded


def is_const(name):
    core = name.lstrip("_")
    return bool(core) and core.isupper() or (core[:1].isupper() and core.replace("_", "").isupper())


def comment_above(lines, lineno):
    out, i = [], lineno - 2
    while i >= 0 and lines[i].strip().startswith("#"):
        out.insert(0, lines[i].strip().lstrip("#").strip())
        i -= 1
    tail = lines[lineno - 1].split("#", 1)
    if len(tail) == 2 and tail[0].count('"') % 2 == 0 and tail[0].count("'") % 2 == 0:
        out.append(tail[1].strip())
    return " ".join(x for x in out if x)


def value_src(src, node):
    return ast.get_source_segment(src, node) or ""


def fence(text):
    return "```text\n" + text.replace("```", "ˋˋˋ") + "\n```"


def constants(path):
    src = path.read_text(encoding="utf-8")
    lines, tree = src.splitlines(), ast.parse(src)
    out = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            names += [e.id for t in node.targets if isinstance(t, ast.Tuple) for e in t.elts if isinstance(e, ast.Name)]
            val = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            names, val = [node.target.id], node.value
        else:
            continue
        names = [n for n in names if is_const(n)]
        if names:
            out.append({"names": names, "line": node.lineno, "value": value_src(src, val) or value_src(src, node),
                        "comment": comment_above(lines, node.lineno)})
    return out


def regexes(path):
    """re.compile(...) anywhere, and the patterns given to re.search/match/fullmatch/sub/split/findall/finditer in functions"""
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    owner = {}
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for n in ast.walk(fn):
                owner.setdefault(id(n), fn.name)
    out = []
    for n in ast.walk(tree):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name)
                and n.func.value.id == "re" and n.args):
            kind = n.func.attr
            if kind not in ("compile", "search", "match", "fullmatch", "sub", "split", "findall", "finditer", "subn"):
                continue
            pat = n.args[0]
            text = pat.value if isinstance(pat, ast.Constant) and isinstance(pat.value, str) else value_src(src, pat)
            out.append({"line": n.lineno, "kind": kind, "where": owner.get(id(n), "(모듈)"), "pattern": text})
    return sorted(out, key=lambda r: r["line"])


def ko_of(ko, mod, name):
    return ko.get(f"{mod}.{name}") or ko.get(name) or ""


def build():
    ko = json.loads(KO.read_text(encoding="utf-8")) if KO.exists() else {}
    files = sorted(p for p in SRV.glob("*.py") if p.name != "__init__.py")
    digest = hashlib.sha256()
    for p in files + [SRV / "pair_rules.json", SRV / "checklist_spec.json", KO]:
        if p.exists():
            digest.update(p.read_bytes())
    mods = [(p, constants(p), regexes(p)) for p in files]
    n_const = sum(len(c) for _, c, _ in mods)
    n_rx = sum(len(r) for _, _, r in mods)
    pr = json.loads((SRV / "pair_rules.json").read_text(encoding="utf-8"))
    cs = json.loads((SRV / "checklist_spec.json").read_text(encoding="utf-8"))
    items = [(k, it) for k in ("common",) for it in cs.get("common", [])] + [(k, it) for k, v in cs.get("kinds", {}).items() for it in (v.get("items", []) if isinstance(v, dict) else v)]
    L = []
    w = L.append
    w("# 17 규칙과 설정값 전체 (자동 생성)\n")
    w("croScan 서버가 쓰는 모든 규칙과 설정값을 코드에서 그대로 뽑아 적은 문서입니다. 사람이 옮겨 적지 않아서 빠진 것이 없습니다. "
      "코드가 바뀌면 `python tools/gen_rulebook.py`로 다시 만듭니다.\n")
    w("**이 문서에서 알 수 있는 것**")
    w(f"- 서버 모듈 {len(files)}개의 모든 상수 {n_const}개: 단어 목록, 한도, 시간 제한, 우선순위, 문턱값")
    w(f"- 서버에서 쓰는 모든 정규식 {n_rx}개와 그것이 쓰이는 곳")
    w(f"- 쌍 규칙 {len(pr['rules'])}개의 모든 항목과 점수 척도, 위험 체크리스트 {len(items)}항목의 제안 규칙과 조치")
    w("- 각 값이 무엇에 쓰이는지 한 줄 설명(한국어)과 코드 위치\n")
    w("> 이 문서는 자동 생성입니다. 손으로 고치지 말고 코드나 `tools/rulebook_ko.json`(설명)을 고친 뒤 다시 만듭니다. "
      "`python tools/gen_rulebook.py --check`가 문서가 코드보다 오래됐는지 검사합니다.\n")
    w(f"<!-- source digest: {digest.hexdigest()[:16]} -->\n")
    w("## 목차")
    w("1. [쌍 규칙 (pair_rules.json)](#1-쌍-규칙-pair_rulesjson)")
    w("2. [위험 체크리스트 명세 (checklist_spec.json)](#2-위험-체크리스트-명세-checklist_specjson)")
    w("3. [모듈별 상수와 정규식](#3-모듈별-상수와-정규식)")
    for p, _, _ in mods:
        w(f"   - [{p.name}](#{p.stem.lower()}py)")
    w("")
    # 1. pair rules
    w("## 1. 쌍 규칙 (pair_rules.json)\n")
    w("규칙 하나는 「위험을 주는 작업 × 위험을 받는 작업」의 조합입니다. 판정 방법은 [06 쌍작업 판정](06_쌍작업_판정.md)에 있습니다.\n")
    for k in ("severity", "exposure", "priority"):
        w(f"**{k}**\n")
        w(fence(json.dumps(pr.get(k), ensure_ascii=False, indent=1)))
        w("")
    w("| id | 이름 | S | 금지 | 원인 태그(cause) | 노출 태그(exposed) | 장소 방식(mode) | 잔류 | 조문 |")
    w("|---|---|---|---|---|---|---|---|---|")
    for r in pr["rules"]:
        cell = lambda v: json.dumps(v, ensure_ascii=False).replace("|", "/") if not isinstance(v, str) else v.replace("|", "/")
        w(f"| `{r['id']}` | {cell(r.get('name', ''))} | {r.get('S', '')} | {'예' if r.get('forbidden') else ''} | {cell(r.get('cause', ''))} | "
          f"{cell(r.get('exposed', ''))} | {cell(r.get('mode', ''))} | {'있음' if r.get('residual') else ''} | {cell(r.get('law', ''))[:80]} |")
    w("")
    for r in pr["rules"]:
        w(f"<details><summary><code>{r['id']}</code> {r.get('name', '')} — 모든 항목</summary>\n")
        w(fence(json.dumps(r, ensure_ascii=False, indent=1)))
        w("\n</details>\n")
    # 2. checklist
    w("## 2. 위험 체크리스트 명세 (checklist_spec.json)\n")
    w("항목마다 「해당」 등을 제안하는 규칙(prefill)과 준비할 조치(controls)가 있습니다. 쓰임은 [07 위험 체크리스트](07_위험체크리스트.md)에 있습니다.\n")
    w("| 종류 | id | 제목 | 제안 규칙 수 | 조치 수 | 사고 사례 |")
    w("|---|---|---|---|---|---|")
    for k, it in items:
        w(f"| {k} | `{it.get('id')}` | {str(it.get('title', '')).replace('|', '/')} | {len(it.get('prefill') or it.get('rules') or [])} | "
          f"{len(it.get('controls') or [])} | {len(it.get('cases') or [])} |")
    w("")
    for k, it in items:
        w(f"<details><summary><code>{it.get('id')}</code> {it.get('title', '')}</summary>\n")
        w(fence(json.dumps(it, ensure_ascii=False, indent=1)))
        w("\n</details>\n")
    rest = {k: v for k, v in cs.items() if k not in ("common", "kinds")}
    w("<details><summary>명세의 나머지 항목 (version · source · cross · case_source)</summary>\n")
    w(fence(json.dumps(rest, ensure_ascii=False, indent=1)))
    w("\n</details>\n")
    # 3. modules
    w("## 3. 모듈별 상수와 정규식\n")
    w("「설명」은 이 값이 무엇에 쓰이는지입니다. 「코드 주석」은 코드에 적힌 영어 주석을 그대로 옮긴 것입니다.\n")
    for p, cons, rxs in mods:
        w(f"### {p.name}\n")
        w(f"[`server/{p.name}`](../server/{p.name}) · 상수 {len(cons)}개 · 정규식 {len(rxs)}개\n")
        if cons:
            w("| 이름 | 줄 | 설명 | 값 |")
            w("|---|---|---|---|")
            folded = []
            for c in cons:
                name = ", ".join(c["names"])
                ko_ = ko_of(ko, p.stem, c["names"][0]) or "설명 준비 중"
                v = c["value"].replace("\n", " ")
                if len(v) > LONG or "|" in v or "`" in v:
                    folded.append(c)
                    shown = "아래 펼침"
                else:
                    shown = f"`{v}`"
                w(f"| `{name}` | [{c['line']}](../server/{p.name}#L{c['line']}) | {ko_.replace('|', '/')} | {shown} |")
            w("")
            for c in folded:
                w(f"<details><summary><code>{', '.join(c['names'])}</code> 값 ({p.name}:{c['line']})</summary>\n")
                w(fence(c["value"]))
                if c["comment"]:
                    w(f"\n코드 주석: {c['comment']}")
                w("\n</details>\n")
            notes = [c for c in cons if c["comment"] and c not in folded]
            if notes:
                w("<details><summary>코드 주석</summary>\n")
                for c in notes:
                    w(f"- `{', '.join(c['names'])}`: {c['comment']}")
                w("\n</details>\n")
        if rxs:
            w(f"<details><summary>정규식 {len(rxs)}개</summary>\n")
            w("| 줄 | 쓰는 곳 | 방식 | 패턴 |")
            w("|---|---|---|---|")
            for r in rxs:
                # inside <code> markdown still runs: '[a](b)' turns into a link, '\(' loses its backslash, '*' starts
                # emphasis, '$' math, so every character markdown reads is written as an entity
                pat = "".join(f"&#{ord(ch)};" if ch in "\\|[]()*_`~$<>&!" else ch for ch in r["pattern"].replace("\n", " "))
                w(f"| {r['line']} | `{r['where']}` | {r['kind']} | <code>{pat}</code> |")
            w("\n</details>\n")
    return "\n".join(L) + "\n"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    text = build()
    if "--check" in sys.argv:
        same = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print("규칙집이 코드와 같습니다" if same else "규칙집이 코드보다 오래됐습니다: python tools/gen_rulebook.py")
        sys.exit(0 if same else 1)
    OUT.write_text(text, encoding="utf-8")
    print(f"{OUT.name}: {len(text):,}자")


if __name__ == "__main__":
    main()
