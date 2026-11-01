"""종이 출력 렌더 검사 (design §19.6·§16): a row too long for a page is cut between lines, never cut off — the same
item name with 「(계속)」 on the next page, the document line (number · revision) and the table's head row repeated
there; nothing of the text is lost; the AI mark is drawn once at the end.

  python tools/check_render.py
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pymupdf  # noqa: E402
from server import addendum, posting  # noqa: E402

OK = []


def check(name, cond):
    OK.append(bool(cond))
    print(f"{'PASS' if cond else 'FAIL'} {name}")


def text_of(doc):
    # one middle dot whichever way the PDF library reads the glyph back (PyMuPDF 1.27 gives 「・」)
    return [re.sub(r"\s+", "", p.get_text()).replace("・", "·") for p in doc]


def main():
    long = " ".join(f"조건{i:03d} 화기 반경 안 가연물을 치우고 감시자를 둔다." for i in range(160))     # ~5,000자: more than a page
    rows = [[str(i), f"칸{i}", "(빈칸)", f"값{i} " + "가나다라마바사 " * 6, "반장 답"] for i in range(70)]
    L = {"head": [("승인번호", "AC00-TEST-0001"), ("원본", "테스트"), ("작성", "2026-10-31 10:00")],
         "cont": "croScan 추가검토서 (별지) · 승인번호 AC00-TEST-0001 · 개정 R7",
         "blocks": [{"t": "bar", "h": "1. 반영본에 적은 내용 (파란 글씨)"},
                    {"t": "table", "w": [0.07, 0.17, 0.22, 0.33, 0.21], "head": ["번호", "칸", "원본 값", "반영본 값", "근거"], "rows": rows},
                    {"t": "kv", "rows": [("긴 조건", addendum._e(long))]},
                    {"t": "box", "h": addendum._e(long), "min": 60},
                    {"t": "full", "h": "<span class='s'>croScan AI 문안 보조 · 문안 상태: 채택 · 개정 R7</span>"}]}
    doc = pymupdf.open()
    addendum._draw(doc, L)
    pages = text_of(doc)
    allt = "".join(pages)
    check("한 쪽을 넘는 내용은 여러 쪽으로", len(pages) >= 4)
    check("긴 칸의 모든 문장이 PDF에 있음(잘림 없음)", all(f"조건{i:03d}" in allt for i in range(160)))
    check("표의 모든 행이 PDF에 있음", all(f"값{i}" in allt for i in range(70)))
    check("이어지는 쪽에 문서번호·개정과 (계속)", all("승인번호AC00-TEST-0001·개정R7(계속)" in p for p in pages[1:]))
    check("표가 이어지는 쪽에 표 머리 반복", sum(1 for p in pages if "번호칸원본값반영본값근거" in p) >= 2)
    check("나눈 칸의 항목명 + (계속)", "긴조건(계속)" in allt)
    check("AI 작성 표기는 문서 끝에 한 번", allt.count("croScanAI문안보조") == 1 and "croScanAI문안보조" in pages[-1])
    # every glyph inside the page (nothing drawn past the bottom)
    inside = all(b[3] <= 842 and b[1] >= 0 for p in doc for b in (w[:4] for w in p.get_text("words")))
    check("모든 글자가 쪽 안에", inside)
    # the posting sheet: the same pen, the mark from the saved state
    sheet = {"title": "병행작업 조정·착수조건 (별지)", "head": [["별지 번호", "S-0735/R2 · 쌍 1건"], ["허가번호", "X"], ["작업일", "2026-10-31"]],
             "sections": [{"title": "P01", "rows": [["우리 반이 할 일", long[:1900], True]]}] * 3, "ai": {"state": "일부 채택", "rev": "R2"}}
    d2 = pymupdf.open()
    addendum._draw(d2, posting.layout(sheet))
    t2 = text_of(d2)
    check("게시 별지: AI 표기(일부 채택·개정)가 끝에 한 번", "".join(t2).count("croScanAI문안보조·문안상태:일부채택·개정R2") == 1)
    check("게시 별지: 이어지는 쪽에 별지 번호 (계속)", len(t2) > 1 and all("S-0735/R2" in p and "(계속)" in p for p in t2[1:]))
    sheet["ai"] = {"state": "아무거나"}
    check("저장 상태가 아닌 AI 표기는 그리지 않음", not any(b.get("h", "").count("문안 보조") for b in posting.layout(sheet)["blocks"]))
    print(f"\n{sum(OK)}/{len(OK)}")
    sys.exit(0 if all(OK) else 1)


if __name__ == "__main__":
    main()
