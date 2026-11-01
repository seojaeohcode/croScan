"""원본 양식 훼손 점검 (design §16·§19.5): a submitted 허가서 PDF against the uploaded original, page by page in pixels.

  python tools/check_form_intact.py <원본.pdf> <제출본 permit.pdf> <kind>

The 반영본 page may differ from the original only inside the form's own fields (where the blue writing goes) and the
one croScan line at the top margin; everything else — the company's lines, logo, printed labels, the values nobody
changed — must be the same pixels. Pages after the original's are croScan's own 별지, never drawn over the form.
"""
import sys
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server import extract  # noqa: E402

ZOOM, PAD, TOP = 2, 2.0, 24.0      # pixels per point, points of slack round a field, the top margin croScan writes in
OK = []


def check(name, cond):
    OK.append(bool(cond))
    print(f"{'PASS' if cond else 'FAIL'} {name}")


def boxes(fields, page):
    out = []
    for f in fields.values():
        b = (f.get("layout") or {}).get("box")
        if f.get("page") == page and b:
            out.append((b[0] - PAD, b[1] - PAD, b[2] + PAD, b[3] + PAD))
    return out


def main():
    orig, sub, kind = sys.argv[1], sys.argv[2], sys.argv[3]
    fields = extract.build(Path(orig), kind)["fields"]
    o, s = pymupdf.open(orig), pymupdf.open(sub)
    check(f"제출본 쪽 수 ≥ 원본 쪽 수 ({len(s)} ≥ {len(o)})", len(s) >= len(o))
    for i in range(len(o)):
        a = o[i].get_pixmap(matrix=pymupdf.Matrix(ZOOM, ZOOM), alpha=False)
        b = s[i].get_pixmap(matrix=pymupdf.Matrix(ZOOM, ZOOM), alpha=False)
        if (a.width, a.height) != (b.width, b.height):
            check(f"{i + 1}쪽 크기 같음", False)
            continue
        allow = boxes(fields, i + 1)
        n, bad, where = a.n, 0, []
        sa, sb = a.samples, b.samples
        changed = 0
        for y in range(a.height):
            row = y * a.stride
            if sa[row:row + a.width * n] == sb[row:row + a.width * n]:
                continue
            py = y / ZOOM
            for x in range(a.width):
                k = row + x * n
                if sa[k:k + n] == sb[k:k + n]:
                    continue
                changed += 1
                px = x / ZOOM
                if py < TOP or any(x0 <= px <= x1 and y0 <= py <= y1 for x0, y0, x1, y1 in allow):
                    continue
                bad += 1
                if len(where) < 5:
                    where.append((round(px), round(py)))
        print(f"  {i + 1}쪽: 바뀐 픽셀 {changed} · 칸·위 여백 밖 {bad} {where}")
        check(f"{i + 1}쪽: 양식 칸과 위 여백 밖은 원본과 같은 픽셀", bad == 0)
        check(f"{i + 1}쪽: 반영한 내용이 있음(칸 안의 변화)", changed > 0)
    extra = [s[j].get_text()[:40].replace("\n", " ") for j in range(len(o), len(s))]
    check("원본 뒤 쪽은 croScan 별지(양식 위에 그리지 않음)", all("croScan" in t for t in extra))
    print(f"\n{sum(OK)}/{len(OK)}")
    sys.exit(0 if all(OK) else 1)


if __name__ == "__main__":
    main()
