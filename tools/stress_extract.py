"""Stress test of the extractor on permits it has never seen: random values for all five
kinds, both copies (제출용 / 게시용), 1-6 permits of one kind per file (one upload = one
kind picked on the first screen). Nothing here is a sample file; every run draws new permits.

    python tools/stress_extract.py            40 permits, seed 1
    python tools/stress_extract.py 200 7      200 permits, seed 7

Checks per page: every common value, every work-date row, the kind's value lines and
every checkbox. The PDFs are written to a temp folder with the font subset (size does not
change what is read: checked on the 15 MB full-font files, same result).
"""
import atexit
import shutil
import random
import sys
import tempfile
import time
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from make_form import draw_page  # noqa: E402
from server import extract, form_spec, permit_kinds as PK  # noqa: E402

N = int(sys.argv[1]) if len(sys.argv) > 1 else 40
rnd = random.Random(int(sys.argv[2]) if len(sys.argv) > 2 else 1)
KINDS = list(PK.KINDS)

SURN = "김이박최정강조윤장임한오서신권황안송류홍"
PLACES = ["대조립21공장 {b}BAY {c1}-{c2} 칼럼", "대조립 22공장 {b}BAY {c1}-{c2} 칼럼 {blk} 블록", "UNIT2공장 유니트{b}팀",
          "대조립21공장 {b}BAY → 1BAY 반출장", "선행의장 3공장 {b}BAY 정반 {c1}"]
JOBS = ["{blk} 블록 외판 절단·재용접", "{blk} 블록 내부 배관 진입 (비드 확인)", "{blk} 블록 상부 임시 러그 제거",
        "{blk} 블록 반출 인양 (천장크레인 OH-2{b}-0{c1})", "천장크레인 OH-2{b}-0{c1} 제어반 정비", "(준)밀폐공간 내부 작업({blk}, {blk2} 블록)",
        "취부 지그 해체 및 그라인딩"]
DEPTS = ["대조립3부-구조보수1팀", "대조립1부-취부2팀", "설비보전부-전기2팀", "UNIT생산부-생산2과-UNIT4팀", "대조립3부-(주)혁신이엔지"]
HAZ = ["질식, 소음", "추락(4.8m), 낙하물 / 하부 통행 통제", "감전·아크, 재가동 끼임", "인양물 낙하·전도, 협착",
       "불티 비산(화재), 용접흄 / 같은 블록 내부 작업 있음", "화기작업시 개인보호구 착용 , 이면부 확인 , 작업구역 통제 (병행 작업 금지)"]


def blk():
    return rnd.choice("EBFDC") + str(rnd.randint(10, 59)) + rnd.choice(["P", "S", "C", ""])


def name():
    return rnd.choice(SURN) + "XX"


def phone():
    return rnd.choice(["010-XXXX-XXXX", f"010-{rnd.randint(1000, 9999)}-{rnd.randint(1000, 9999)}"])


def permit(kind):
    b, c1 = rnd.randint(1, 4), rnd.randint(1, 30)
    fmt = dict(b=b, c1=c1, c2=c1 + rnd.randint(2, 6), blk=blk(), blk2=blk())
    day0 = rnd.randint(1, 20)
    ndays = rnd.choice([0, 1, 1, 2, 3, 7])
    d = {
        "kind": kind,
        "permit_no": f"BS22-IV-202610{day0:02d}-{rnd.randint(1, 9999):04d}",
        "permit_type": rnd.choice(["[전산허가]", "[안전현장허가]"]),
        "hull_no": rnd.choice(["", f"{rnd.randint(3500, 3699)}-{fmt['blk']}", f"{rnd.randint(3500, 3699)}-157K-COT"]),
        "jsp_no": rnd.choice([f"HHIS-CW-A000{rnd.randint(1000, 9999)}-0{rnd.randint(10, 99)}-00{rnd.randint(1, 9)}",
                              f"HHIS-CN-C6B0-0{rnd.randint(10, 99)}"]),
        "location": rnd.choice(PLACES).format(**fmt),
        "location_detail": rnd.choice(["", rnd.choice(PLACES).format(**fmt)]),
        "job": rnd.choice(JOBS).format(**fmt),
        "job_detail": rnd.choice(["", "진입 2명, 외부 감시 1명", "불량부 절단 후 신규 부재 취부·재용접, 작업높이 3.6m"]),
        "department": rnd.choice(DEPTS),
        "supervisor": name(), "supervisor_phone": phone(), "manager": name(), "manager_phone": phone(),
        "workers": str(rnd.randint(1, 12)),
        "hazards": rnd.choice(HAZ),
        "concurrent": rnd.choice(["", "Y", "N"]),
        "days": [(f"2026-10-{day0 + i:02d}", rnd.choice(["07:30", "08:00", "09:00", "13:00"]),
                  rnd.choice(["11:30", "12:00", "16:59", "17:00"])) for i in range(ndays)],
        "req_name": name(), "req_date": f"2026-10-{max(1, day0 - 1):02d}", "req_sign": name(),
        "double_check": rnd.choice(["Y", "N"]),
    }
    if rnd.random() < 0.3:      # already approved
        d.update(app_name=name(), app_date=d["req_date"], app_sign=name())
    for key, *_ in PK.values(kind):
        d[key] = rnd.choice(["", str(rnd.randint(1, 60)), f"{rnd.randint(1, 9)}.{rnd.randint(0, 9)}"])
    items = [k for k, *_ in form_spec.CHECKS + PK.checks(kind)]
    d["checks"] = {k: "set" for k in rnd.sample(items, rnd.randint(0, 6))}
    return d


def expected(d, kind, copy):
    want = {k: d.get(k, "") for k, _, t, _ in form_spec.FIELDS if t != "image"}
    if copy == "posting":
        want = {k: v for k, v in want.items() if not k.startswith("face_")}
    for i in range(form_spec.DATE_ROWS):
        r = d["days"][i] if i < len(d["days"]) else ("", "", "")
        want.update({f"date_{i + 1}": r[0], f"from_{i + 1}": r[1], f"to_{i + 1}": r[2]})
    for k, *_ in PK.values(kind):
        want[k] = d.get(k, "")
    for k, *_ in form_spec.CHECKS + PK.checks(kind):
        want[k] = k in d["checks"]
    return want


def main():
    tmp = Path(tempfile.mkdtemp(prefix="croscan_stress_"))
    atexit.register(shutil.rmtree, tmp, True)          # the generated PDFs go when the run ends
    files, left = [], N
    while left > 0:                     # one upload: 1-6 permits of the kind picked on screen
        n = min(left, rnd.randint(1, 6)); left -= n
        kind = rnd.choice(KINDS)
        files.append([dict(d=permit(kind), kind=kind, copy=rnd.choice(["submit", "submit", "posting"])) for _ in range(n)])

    total = ok = 0
    misses = []
    t0 = time.time()
    for fi, group in enumerate(files):
        doc = pymupdf.open()
        for p in group:
            draw_page(doc, p["d"], p["copy"], {}, p["kind"])
        path = tmp / f"stress_{fi:03d}.pdf"
        doc.subset_fonts(); doc.save(path, garbage=4, deflate=True)
        got = extract.build(path, group[0]["kind"])
        for no, p in enumerate(group, 1):
            for k, v in expected(p["d"], p["kind"], p["copy"]).items():
                f = got["fields"].get(f"p{no}.{k}")
                if f is None and v in ("", False):
                    continue
                g = None if f is None else f["value"]
                good = g == v or (isinstance(v, str) and str(g).replace(" ", "") == v.replace(" ", ""))
                total += 1; ok += good
                if not good:
                    misses.append(f"{path.name} p{no} [{PK.KINDS[p['kind']]['label']}/{p['copy']}] {k}: want {v!r} got {g!r}")
    print(f"files {len(files)}, permits {N}, {time.time() - t0:.0f}s  ({tmp})")
    print(f"values: {ok}/{total}")
    for m in misses[:40]:
        print("  ", m)
    if len(misses) > 40:
        print(f"   ... {len(misses) - 40} more")


if __name__ == "__main__":
    main()
