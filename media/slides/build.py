"""Join parts/NN_*.html into deck.html, numbering pages and footers.

Each part holds <section class="slide ..."> blocks. A footer placeholder {{FT}} becomes the standard footer with the page
number; {{FT:0:40–1:20}} also shows the planned speaking window.
"""
import re
from pathlib import Path

W = Path(__file__).parent
EVENT = "2026 K-조선 해커톤 · croScan"
parts = sorted((W / "parts").glob("[0-9][0-9]_*.html"))
html = "\n".join(p.read_text(encoding="utf-8") for p in parts)

n = 0
def page(m):
    global n
    n += 1
    return m.group(0)
html = re.sub(r'<section class="slide', page, html)  # count only

i = 0
def foot(m):
    global i
    i += 1
    tm = f'<span class="tm">발표 {m.group(1)}</span>' if m.group(1) else ""
    return f'<div class="ft"><span>{EVENT}</span>{tm}<span class="pg">{i}</span></div>'
# number by order of appearance: every slide must carry exactly one {{FT}}
blocks = re.split(r'(?=<section class="slide)', html)
import json
CORE = json.loads((W / "times.json").read_text(encoding="utf-8"))["core"]
used = set()


def title_of(b):
    m = re.search(r"<h1[^>]*>([\s\S]*?)</h1>", b)
    t = re.sub(r"<[^>]+>", " | ", m.group(1)) if m else ""
    return re.sub(r"\s*\|\s*(\|\s*)*", " | ", re.sub(r"\s+", " ", t)).strip(" |")


def window(b, first_cover):
    """10-minute cut: the time window for a core slide, '' for dividers/plan/appendix, None for extended slides."""
    head = b[:120]
    if re.search(r'class="slide[^"]*\b(apx|plan|part)\b', head):
        return ""
    if first_cover:
        return dict(CORE)["@cover"]
    if re.search(r'class="slide[^"]*\bcover\b', head):
        return dict(CORE)["@end"]
    t = title_of(b)
    for key, tm in CORE:
        if not key.startswith("@") and key not in used and t.startswith(key):
            used.add(key)
            return tm
    return None


def ref_key(b, first_cover):
    """{{P:}} 찾기용 이름: h1 제목, 없으면 'PART 구분장 제목' · '@cover' · '@end' · '@APPENDIX' · '@A00'."""
    t = title_of(b)
    if t:
        return t
    head = b[:160]
    if re.search(r'class="slide[^"]*\bapx\b[^"]*\bpart\b', head):
        return "@A00"
    if re.search(r'class="slide[^"]*\bblk\b', head):
        return "@APPENDIX"
    m = re.search(r'class="pt"[^>]*>([^<]*)', b)
    if re.search(r'class="slide[^"]*\bpart\b', head) and m:
        return "PART " + m.group(1).strip()
    if re.search(r'class="slide[^"]*\bcover\b', head):
        return "@cover" if first_cover else "@end"
    return ""


out = []
TITLES, MISS = [], []
seen_cover = False
for b in blocks:
    if b.startswith("<section"):
        i += 1
        is_cover = bool(re.search(r'class="slide[^"]*\bcover\b', b[:120])) and not seen_cover
        seen_cover = seen_cover or is_cover
        w = window(b, is_cover)
        tm = ""   # 전체본만 낸다(사용자 지시 11-02): 시간 구간·10분판 표시는 붙이지 않는다
        b = re.sub(r"\{\{FT(?::([^}]*))?\}\}", lambda m: f'<div class="ft"><span>{EVENT}</span>{tm}<span class="pg">{i}</span></div>', b)
        b = b.replace("{{PG}}", str(i))
        TITLES.append((i, ref_key(b, is_cover)))
    out.append(b)
html = "".join(out)


def page_ref(m):
    """{{P:제목앞부분}} → 그 제목으로 시작하는 장들의 쪽 번호(여러 장이면 첫–끝), {{P:앞~뒤}} → '7–8'. 구분장·목차 쪽 번호 자동화(디자인 담당)."""
    nums = []
    for key in m.group(1).split("~"):
        key = key.strip()
        hits = [k for k, t in TITLES if t == key] or [k for k, t in TITLES if t.startswith(key)]   # 제목이 똑같은 장이 있으면 그 장만
        if not hits:
            MISS.append(key)
            return "?"
        nums += [hits[0], hits[-1]]   # 앞부분이 같은 장이 여러 장이면 첫 장–끝 장
    nums = [nums[0], nums[-1]]
    return str(nums[0]) if len(nums) == 1 or nums[0] == nums[-1] else f"{nums[0]}–{nums[-1]}"


html = re.sub(r"\{\{P:([^}]+)\}\}", page_ref, html)

doc = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>croScan 발표 구성안</title>
<link rel="stylesheet" href="parts/deck.css"></head><body>
{html}
</body></html>"""
(W / "deck.html").write_text(doc, encoding="utf-8")
print(f"deck.html: {i} slides")
if MISS:
    print("쪽 번호 못 찾음({{P:}}):", MISS)
