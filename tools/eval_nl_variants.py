"""자연어 평가셋 150 × 8 만들기 (design §11.1 「자연어 150 시나리오 × 8 표현」): from the 30 reviewed scenarios of
tools/eval_phase1_cases.py, 5 value variants each (counts, column numbers, crane and panel IDs changed together in the
words and in the expectation) = 150 scenarios, and 8 phrasings of each (the two reviewed phrasings and transforms of
them that keep the meaning: number words, a filler, clause order, clock times, no spaces in places, a polite lead-in,
range words). Generated, so marked synthetic; the expectation follows the substitution by construction.

  python tools/eval_nl_variants.py            # -> tools/eval_nl_cases.json (1,200 answers)
  python tools/eval_phase1.py turn --cases tools/eval_nl_cases.json --out nl.jsonl --resume     # on the server

Split by scenario (design §11.1: 같은 시나리오의 표현 변형을 학습과 시험에 섞지 않는다): nothing here is used as an example
in any prompt.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_phase1_cases import TURN  # noqa: E402

OUT = Path(__file__).resolve().parent / "eval_nl_cases.json"
VARIANTS, PHRASINGS = 5, 8
KO = {2: "두", 3: "세", 4: "네", 5: "다섯", 6: "여섯", 7: "일곱", 8: "여덟", 9: "아홉"}
WORD = {v: k for k, v in KO.items()}
COUNT = re.compile(r"(?<![\d.-])([2-9])(\s*(?:개|군데))")
COUNT_WORD = re.compile(r"(?<![가-힣])(두|세|네|다섯|여섯|일곱|여덟|아홉)(\s*(?:개|군데))")
COL = re.compile(r"(?<![\d-])(\d{2})(?=(?:\s*[-~]\s*\d{2})?\s*칼럼)|(?<=[-~])(\d{2})(?=\s*칼럼)")
CRANE = re.compile(r"OH-21-0([1-3])")
PANEL = re.compile(r"MCC-(\d)")


def cnt(n, k):
    return (n - 2 + k) % 8 + 2                          # a bijection of 2..9: 「4개가 아니라 6개」 stays two numbers


def sub(text, k):
    """the words with variant k's values (k = 0: as reviewed)"""
    if k == 0:
        return text
    text = COUNT.sub(lambda m: f"{cnt(int(m.group(1)), k)}{m.group(2)}", text)
    text = COUNT_WORD.sub(lambda m: f"{KO[cnt(WORD[m.group(1)], k)]}{m.group(2)}", text)
    text = COL.sub(lambda m: f"{min(38, int(m.group(1) or m.group(2)) + 2 * k):02d}", text)
    text = CRANE.sub(lambda m: f"OH-21-0{(int(m.group(1)) - 1 + k) % 3 + 1}", text)
    return PANEL.sub(lambda m: f"MCC-{(int(m.group(1)) + k - 1) % 9 + 1}", text)


def sub_token(t, k):
    """an expected value token under variant k (the same substitution as the words)"""
    if k == 0:
        return t
    if re.fullmatch(r"[2-9]", t):
        return str(cnt(int(t), k))
    if re.fullmatch(r"\d{2}", t):
        return f"{min(38, int(t) + 2 * k):02d}"
    return PANEL.sub(lambda m: f"MCC-{(int(m.group(1)) + k - 1) % 9 + 1}", CRANE.sub(lambda m: f"OH-21-0{(int(m.group(1)) - 1 + k) % 3 + 1}", t))


TRANSFORMS = [
    ("검수 문장 1", lambda t: t),
    ("검수 문장 2", lambda t: t),
    ("숫자를 말로", lambda t: COUNT.sub(lambda m: f"{KO[int(m.group(1))]}{m.group(2)}", t)),
    ("말머리", lambda t: "음, " + t),
    ("절 순서 바꿈", lambda t: (lambda p: " ".join(p[1:] + p[:1]) if len(p) > 1 else t)(re.split(r"(?<=[.?!])\s+", t))),
    ("시각 표기", lambda t: re.sub(r"(\d{1,2})시\s*(?:부터|~)\s*(\d{1,2})시(?:\s*까지)?", lambda m: f"{int(m.group(1)):02d}:00~{int(m.group(2)):02d}:00", t)),
    ("붙여 쓰기", lambda t: re.sub(r"(BAY)\s+(\d)", r"\1\2", re.sub(r"\s+(칼럼)", r"\1", t))),
    ("공손한 말머리", lambda t: "말씀드리면 " + t),
]


def main():
    cases, seeds = [], 0
    for name, pno, item, choice, texts, want, never in TURN:
        seeds += 1
        for k in range(VARIANTS):
            w = {}
            for it, x in want.items():
                if isinstance(x, str):
                    w[it] = x
                else:
                    c, d = x
                    w[it] = [c, {**d, **({"v": [sub_token(t, k) for t in d["v"]]} if d.get("v") else {})}]
            out = []
            for i, (label, fn) in enumerate(TRANSFORMS):
                base = sub(texts[1 if i == 1 or (i >= 2 and i % 2) else 0], k)
                t = fn(base)
                for lead in ("", "그러니까, ", "네, ", "아 그거요, ", "일단 "):         # a transform with nothing to change: another wording
                    if lead + t not in out:
                        out.append(lead + t)
                        break
            cases.append({"name": f"{name}#{k}", "seed": name, "variant": k, "pno": pno, "item": item, "choice": choice,
                          "texts": out, "phrasings": [t[0] for t in TRANSFORMS], "want": w, "never": sorted(never), "synthetic": True})
    # by construction the expected numbers and IDs are in every phrasing (as digits or as words)
    norm = lambda s: re.sub(r"\s", "", s).upper()
    bad = []
    for c in cases:
        for it, x in c["want"].items():
            if isinstance(x, list) and x[1].get("v"):
                for t in x[1]["v"]:
                    for p in c["texts"]:
                        if norm(t) not in norm(p) and not (t.isdigit() and int(t) in KO and KO[int(t)] in p):
                            bad.append((c["name"], t, p[:40]))
    OUT.write_text(json.dumps(cases, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{OUT.name}: 시나리오 {len(cases)}개(원 {seeds} × 값 변형 {VARIANTS}) × 표현 {PHRASINGS} = {len(cases) * PHRASINGS}건"
          f" · 기대 제안 {sum(len(c['want']) for c in cases) * PHRASINGS} · 값 대응 불일치 {len(bad)}")
    for b in bad[:10]:
        print("  불일치", b)
    return bad


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
