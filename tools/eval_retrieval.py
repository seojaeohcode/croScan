"""검색 평가 (design §11.1: 검색 20문항): for each question the passages a reviewer marked as the answer (the cited
article, or the team note's page), and where the search puts them — Recall@3 (what would be handed to the model),
Recall@6 (§11.2 target ≥95%) and Recall@12 (the candidates reviewed). Counts with their denominator. A question
with several required passages is counted twice: 「하나라도」 (any of them within k) and 「전부」 (all of them within k).
A required id matches its passage and the passage's parts (an article split in pieces: law:<law>:<조>, …:<조>#2).

  python tools/eval_retrieval.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server import retrieval  # noqa: E402

# (question as a foreman or manager would put it, ids that answer it: law:<law>:<article> or team:notion:p<page>)
QS = [
    ("용접할 때 화재감시자를 꼭 둬야 하나요", ["law:안전보건규칙:제241조의2"]),
    ("불티 튀는 작업 주변에 가연물 있으면 어떻게 해요", ["law:안전보건규칙:제241조"]),
    ("탱크 안에서 용접할 때 환기 조치", ["law:안전보건규칙:제629조"]),
    ("밀폐공간 들어가기 전에 산소 농도 측정", ["law:안전보건규칙:제619조의2"]),
    ("밀폐공간 작업할 때 바깥에 감시인 두는 규정", ["law:안전보건규칙:제623조"]),
    ("밀폐공간 구조용 공기호흡기 사다리 비치", ["law:안전보건규칙:제625조"]),
    ("아르곤 퍼지 배관 있는 탱크에서 불활성가스 새는 것", ["law:안전보건규칙:제630조"]),
    ("크레인으로 들 때 사람 머리 위로 지나가면 안 되는 것", ["law:안전보건규칙:제146조"]),
    ("크레인 수리할 때 같은 주행로 다른 크레인", ["law:안전보건규칙:제139조"]),
    ("정비할 때 기계 운전 정지하고 잠금장치", ["law:안전보건규칙:제92조"]),
    ("정전 작업 전에 전원 차단하고 꼬리표 다는 것", ["law:안전보건규칙:제319조"]),
    ("위에서 물건 떨어질 위험 낙하물 방지망", ["law:안전보건규칙:제14조"]),
    ("양중기 신호수 신호 방법 정하기", ["law:안전보건규칙:제40조"]),
    ("중량물 취급 작업계획서 작업지휘자", ["law:안전보건규칙:제38조", "law:안전보건규칙:제39조"]),
    ("방사선 투과검사 관리구역 출입 금지", ["law:안전보건규칙:제575조"]),
    ("질소로 기밀시험 할 때 위험", ["law:안전보건규칙:제300조"]),
    ("협력업체끼리 같은 장소에서 작업할 때 원청이 조정", ["law:산업안전보건법:제64조"]),
    ("비상구 비상통로 유지", ["law:안전보건규칙:제18조"]),
    ("지게차 같은 차량계 하역운반기계 접촉 방지", ["law:안전보건규칙:제172조"]),
    ("아르곤 가스 배관 안에 들어갔다가 질식한 사고", ["team:notion:p52"]),
]


def main():
    same = lambda g, w: g == w or g.startswith((w + ":", w + "#"))
    hit, full = {3: 0, 6: 0, 12: 0}, {3: 0, 6: 0, 12: 0}
    for q, want in QS:
        got = [h["id"] for h in retrieval.search(q, k=12)]
        ranks = [next((i + 1 for i, g in enumerate(got) if same(g, w)), None) for w in want]
        first = min((r for r in ranks if r), default=None)
        last = None if None in ranks else max(ranks)
        for k in hit:
            hit[k] += bool(first and first <= k)
            full[k] += bool(last and last <= k)
        print(f"{'O' if first and first <= 3 else '△' if first else 'X'} {ranks} | {q} → {', '.join(want)} | 1위 {got[0] if got else '-'}")
    n, many = len(QS), sum(1 for _, w in QS if len(w) > 1)
    print(f"\n검색 {n}문항(근거 여럿 {many}문항) · 하나라도: Recall@3 {hit[3]}/{n} · @6 {hit[6]}/{n} · @12 {hit[12]}/{n}"
          f" · 전부: Recall@3 {full[3]}/{n} · @6 {full[6]}/{n} · @12 {full[12]}/{n}")


if __name__ == "__main__":
    main()
