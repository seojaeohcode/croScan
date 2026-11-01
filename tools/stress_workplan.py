"""Stress test for server/workplan.py: fill the blank 작업계획서 forms with random values (long, two-line, empty cells,
other companies and times), split them into files in different ways and check every value comes back.

  python tools/stress_workplan.py [plans=30] [seed=1]

Scenarios: one file per plan / a few bundles / every page its own file in shuffled order (pages joined by 문서번호
across files) / blank forms / a permit PDF dropped in by mistake.
"""
import atexit
import os
import random
import shutil
import sys
import tempfile
import time
from pathlib import Path

import pymupdf

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
# uploads made by this run go to a throwaway data folder (the app keeps uploads 7 days; a test run must not pile up)
_DATA = Path(tempfile.mkdtemp(prefix="croscan_test_data_"))
os.environ["CROSCAN_DATA"] = str(_DATA)
atexit.register(shutil.rmtree, _DATA, True)
from server import workplan as W  # noqa: E402

BLANKS = sorted((APP / "samples/작업계획서/빈양식").glob("작업계획서_빈양식_*.pdf"))
BLANKS = [b for b in BLANKS if not b.stem.endswith("6사")]
FONT = next(p for p in (Path("C:/Windows/Fonts/malgun.ttf"), Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf")) if p.exists())
N, SEED = (int(sys.argv[1]) if len(sys.argv) > 1 else 30), (int(sys.argv[2]) if len(sys.argv) > 2 else 1)
R = random.Random(SEED)
WORDS = ("블록 취부 용접 연마 도장 배관 점검 시운전 정리 설치 해체 인양 질소 압축공기 기밀시험 비파괴 절단 보강 "
         "탱크 기관실 상부 하부 갑판 격벽 구역 통제 화기 환기 감시 확인 계획 기록 완료 미기재 조공 신호수 "
         "용접사 비계 발판 크레인 지게차 펌프 밸브 전원 차단 잠금 가스 측정").split()
COMPANIES = ["현대힘스", "삼녹", "세진중공업", "한국카본", "동화엔텍", "동성화인텍", "대한조선기계", "미래엔지니어링"]


def phrase(lo, hi):
    return " ".join(R.choice(WORDS) for _ in range(R.randint(lo, hi)))


def value(label):
    if label in ("시작일시", "종료일시"):
        return None                                       # set per plan
    r = R.random()
    if r < 0.08:
        return ""                                         # empty cell
    if label == "작업인원":
        return f"{R.randint(1, 12)}명"
    if label == "대상ID":
        return f"SYN-{R.choice('ABCDEFG')}{R.randint(1, 9)}-{R.randint(100, 999)} / 구역 {R.choice(['G-2ND', 'G-3RD', 'G-UPPER'])}"
    if r < 0.18:
        return [phrase(4, 7), phrase(4, 7)]               # two lines in one cell (smaller font)
    if r < 0.3:
        return phrase(8, 11)                              # long single line
    return phrase(1, 5) + (f" / {R.randint(1, 30)}m" if R.random() < 0.3 else "")


def fill(company_blank, plan_no):
    """One filled plan (2 pages) + its truth."""
    d = pymupdf.open(company_blank)
    day = R.randint(1, 28)
    h0, m0 = R.randint(6, 20), R.choice([0, 10, 20, 30, 40, 50])
    dur = R.randint(30, 300)
    start = f"2026-11-{day:02d} {h0:02d}:{m0:02d}"
    e = h0 * 60 + m0 + dur
    end = f"2026-11-{day + e // 1440:02d} {e % 1440 // 60:02d}:{e % 60:02d}"
    head = {"doc_no": f"WP-{SEED}-{plan_no:04d}", "work_no": f"{R.choice('ABCDEFGHKL')}{R.randint(1, 9)}", "rev": f"R{R.randint(0, 9)}",
            "issued": "2026-10-2" + str(R.randint(0, 9)), "plan_date": start[:10], "drawing_basis": f"D{R.randint(1, 99):02d}"}
    company = R.choice(COMPANIES)
    truth = {"head": head, "items": {}, "grid": []}
    title = phrase(2, 4)
    grid_rows = None
    for pg in d:
        words = pg.get_text("words")
        labels = {}
        for w in words:
            if w[0] < 100 and 120 < w[1] < 800:
                labels.setdefault(w[4], []).append(pymupdf.Rect(w[:4]))
        lines = [ln for b in pg.get_text("dict")["blocks"] for ln in b.get("lines", []) if ln["bbox"][0] < 100]

        def put(x, y_mid, text, size=9.2):
            pg.insert_text((x, y_mid + size * 0.36), text, fontsize=size, fontname="stressfill", fontfile=str(FONT))   # own name: the form may already hold a subset "kr"

        # header values right after their labels
        for lab, key in (("문서번호:", "doc_no"), ("작업번호:", "work_no"), ("개정", "rev"), ("작성·발행:", "issued"), ("계획일:", "plan_date"), ("도면 배치 기준:", "drawing_basis")):
            r = pg.search_for(lab)
            if r:
                put(r[0].x1 + 3, (r[0].y0 + r[0].y1) / 2, head[key], 10)
        for ln in lines:
            lab = "".join(s["text"] for s in ln["spans"]).strip()
            ymid = (ln["bbox"][1] + ln["bbox"][3]) / 2
            if lab in ("확인 항목", "공간·대상", "위험요소", "방호 상태", "가동·위험 기간", "위험 종료"):
                if lab == "확인 항목":
                    continue
                row = [lab] + [phrase(1, 3) for _ in range(3)]
                if R.random() < 0.1:
                    row[2] = ""
                for x, t in zip((129.5, 293.5, 426.5), row[1:]):
                    if t:
                        put(x, ymid, t, 8.8)
                truth["grid"].append(row)
                continue
            if not any("Bold" in s["font"] for s in ln["spans"]) or ln["spans"][0]["size"] > 10:    # labels are bold, section titles larger
                continue
            v = {"작업명": title, "수행업체": f"{company} / 협력사", "시작일시": start, "종료일시": end}.get(lab, None)
            if v is None:
                v = value(lab)
            if lab in truth["items"]:                     # 작업명, 공정 단계 again on page 2: same value
                v = truth["items"][lab]
            if isinstance(v, list):
                put(111.2, ymid - 4.5, v[0], 8.2)
                put(111.2, ymid + 4.5, v[1], 8.2)
                v = " ".join(v)
            elif v:
                put(111.2, ymid, v)
            truth["items"][lab] = v
    return d, truth


def check(plans, truths):
    by = {p["doc_no"]: p for p in plans}
    bad = []
    for t in truths:
        p = by.get(t["head"]["doc_no"])
        if not p:
            bad.append((t["head"]["doc_no"], "계획서를 못 찾음"))
            continue
        for k, v in t["head"].items():
            if p[k] != v:
                bad.append((t["head"]["doc_no"], f"머리 {k}: {p[k]!r} != {v!r}"))
        got = {x["label"]: x["value"] for x in p["items"]}
        for lab, v in t["items"].items():
            if got.get(lab, "<없음>") != v:
                bad.append((t["head"]["doc_no"], f"{lab}: {got.get(lab, '<없음>')!r} != {v!r}"))
        g = [r for r in (p["grid"] or {}).get("rows", [])]
        if g != t["grid"]:
            bad.append((t["head"]["doc_no"], f"확인 기록 표: {g} != {t['grid']}"))
    return bad


def run(name, files, truths, expect_plans):
    t0 = time.time()
    ev = list(W.read_many(files))
    done = ev[-1]
    bad = check(done["plans"], truths)
    n_err = sum(1 for f in done["files"] if f["error"])
    ok = not bad and len(done["plans"]) == expect_plans
    print(f"{'PASS' if ok else 'FAIL'} {name}: 파일 {len(files)}개 → 계획서 {len(done['plans'])}건 (기대 {expect_plans}), "
          f"값 오류 {len(bad)}, 파일 오류 {n_err}, {time.time() - t0:.1f}s")
    for b in bad[:8]:
        print("   ", b)
    return ok, done


docs, truths = [], []
for i in range(N):
    d, t = fill(R.choice(BLANKS), i)
    docs.append(d)
    truths.append(t)
labels = sum(len(t["items"]) for t in truths)
print(f"합성 {N}건, 값 {labels}개 + 머리 {6 * N} + 확인 기록 {sum(len(t['grid']) for t in truths) * 3}칸 (seed {SEED})")

results = []
one = [(f"plan_{i:03d}.pdf", d.tobytes()) for i, d in enumerate(docs)]
results.append(run("한 파일에 한 건", one, truths, N)[0])

bundles = []
for b in range(0, N, 10):
    m = pymupdf.open()
    for d in docs[b:b + 10]:
        m.insert_pdf(d)
    bundles.append((f"bundle_{b // 10}.pdf", m.tobytes()))
results.append(run("묶음 파일", bundles, truths, N)[0])

pages = []
for i, d in enumerate(docs):
    for k in range(d.page_count):
        m = pymupdf.open()
        m.insert_pdf(d, from_page=k, to_page=k)
        pages.append((f"p_{i:03d}_{k + 1}.pdf", m.tobytes()))
R.shuffle(pages)
results.append(run("쪽마다 따로, 순서 섞음", pages, truths, N)[0])

# the 수정본: change some values on "screen", download every plan as one PDF, read it again
ok, done = run("한 파일에 한 건 (수정본용)", one, truths, N)
edited = [{"head": dict(t["head"]), "items": dict(t["items"]), "grid": [list(r) for r in t["grid"]]} for t in truths]
by_no = {t["head"]["doc_no"]: k for k, t in enumerate(edited)}
edits = {}
for i, p in enumerate(done["plans"]):
    if i % 3:
        continue
    F = p["doc"]["fields"]
    rows = [fk for fk in F if fk.split(".", 1)[1].startswith("r")]
    fk = R.choice(rows)
    new = phrase(2, 6) + " 수정"
    edits[str(i)] = {k: new for k in [fk, *F[fk].get("same", [])]}
    edited[by_no[p["doc_no"]]]["items"][F[fk]["name"]] = new
W.save_edits(done["token"], edits)
pdf, name = W.edited_pdf(done["token"])
ok, done2 = run(f"수정본 다시 읽기 ({name}, 수정 {len(edits)}건)", [(name, pdf)], edited, N)
results.append(ok)

ok, done = run("같은 파일을 두 번 넣음", one[:10] + one[:5], truths[:10], 10)
ok = ok and all(len(p["pages"]) == 2 for p in done["plans"])
results.append(ok)

blank = [(b.name, b.read_bytes()) for b in BLANKS[:2]]
ok, done = run("빈 양식", blank, [], 2)
ok = ok and all("빈 양식: 채워진 칸이 없음" in p["warnings"] for p in done["plans"])
print("   빈 양식 경고:", [p["warnings"] for p in done["plans"]])
results.append(ok)

permit = next((APP / "samples/시연").glob("*.pdf"))
ev = list(W.read_many([(permit.name, permit.read_bytes()), one[0]]))
f = ev[-1]["files"]
ok = f[0]["error"] and not f[1]["error"] and len(ev[-1]["plans"]) == 1
print(f"{'PASS' if ok else 'FAIL'} 허가서를 잘못 넣음: {f[0]['error']!r}, 계획서 {len(ev[-1]['plans'])}건")
results.append(ok)

print(f"\n{sum(results)}/{len(results)} 시나리오 통과")
