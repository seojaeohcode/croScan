"""V12–V19: copy PRAI renders to final19 with Korean names, representative PNG, 2-second frame sheets, manifest_part.json/.md.
usage: python package19.py [v12 v13 ...]   (default: every clip whose render exists)
"""
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

S = Path(__file__).parent
W19 = S.parent
FINAL = W19.parent / "final19"
SHEETS = W19 / "sheets"
PRAI = Path("C:/Users/seoco/OneDrive/Desktop/PRAI")
FF = str(PRAI / "node_modules/ffmpeg-static/ffmpeg.exe")
SMAP = json.loads((S / "scenemap19.json").read_text(encoding="utf-8"))
LOG = json.loads((S / "cap" / "log_S19.json").read_text(encoding="utf-8"))["events"]


def ev(k):
    return next((e["v"] for e in LOG if e["k"] == k), None)


def one(s, n=600):
    s = s if isinstance(s, str) else json.dumps(s, ensure_ascii=False)
    s = " / ".join(x.strip() for x in s.splitlines() if x.strip())
    return s if len(s) <= n else s[:n] + "…"


NAMES = {
    "v12": "V12_같은_구역의_화기와_도장", "v13": "V13_판정에_사용한_서류로_돌아가기", "v14": "V14_필요한_설명을_직접_질문",
    "v15": "V15_선택적_AI_추가_검토", "v16": "V16_같은_시각의_배치_확인", "v17": "V17_협조_문자_작성과_복사",
    "v18": "V18_AI_현장_게시_내용과_별지_반영", "v19": "V19_할_일_착수조건_중지조건_확인",
}
TITLES = {
    "v12": "같은 구역의 화기와 도장", "v13": "판정에 사용한 서류로 돌아가기", "v14": "필요한 설명을 직접 질문",
    "v15": "선택적 AI 추가 검토 — 독립 삽입용", "v16": "조율 전에 같은 시각의 배치 확인", "v17": "작업 조율 협조 문자 작성과 복사",
    "v18": "AI의 현장 게시 내용 작성과 별지 반영", "v19": "우리 반의 할 일·착수조건·중지조건 확인",
}
ex = ev("explain_api") or {}
fr = ex.get("frame", {})
pr = ev("pair_review_api") or {}
dr = ev("post_draft_api") or {}
INPUTS = {
    "v12": ["로그인: 역할 「안전관리자」 선택 후 「로그인」(데모 로그인)", "문서 목록 → 위험 쌍 → 1순위 탭 → P02(0731 × WP-01) 선택"],
    "v13": ["P02 상세에서 「판정 근거·원문」 펼침", "문서 목록에서 WP-1029-01 계획서와 0731 허가서 문서 패널 열기"],
    "v14": [f"자유 질문 입력(키보드로 실제 입력): 「{ev('free_question_typed')}」 → 「묻기」"],
    "v15": [f"검토 통과 인접 작업 중 아직 AI 검토를 하지 않은 쌍 선택: {(ev('pair_review_before') or {}).get('chosen')} (0738 × WP-22)", "「AI 검토 요청」 한 번"],
    "v16": ["P02 상세 → 「배치도에서 보기」 → 시각 13:30"],
    "v17": ["P02 「작업 조정 문자 작성」 → 빈칸 3개(협의 상대 번호, 보내는 사람 이름·번호)는 가린 시연 값(010-XXXX-XXXX, 이XX)으로 채움",
            f"협의할 점 AI 제안 예시: P02는 제안 없음이라 다른 작업쌍 {(ev('example_pair') or {}).get('id')}(0735 × WP-08)에서 「문자에 넣기」 → 「문자 복사」"],
    "v18": ["현장 게시 서류 → 0731 「미리 보기·편집」 → 「AI 문안 보충 보기」 → 「문안 채택」",
            "사전 준비(화면 밖): 문서 목록에서 0731의 허가서·추가검토서·위험 체크리스트를 「확인」 처리(발행 조건): " + ", ".join(ev("docs_confirmed_before_issue_offscreen") or [])],
    "v19": ["현장 게시 서류 → 0731 「발행」 → 「보기」"],
}
RESULTS = {
    "v12": [f"홈: {one(ev('nav'), 400)}", f"위험 쌍: {one(ev('res'))}", f"1순위 목록(일부): {one((ev('p1_rows') or [])[:3])}", f"P02 상세: {one(ev('pair_detail'), 700)}"],
    "v13": [f"판정: {one(ev('judgement'), 500)}", f"WP-1029-01 패널: {one(ev('doc_panel_WP-1029-01'), 500)}", f"0731 패널: {one(ev('doc_panel_0731'), 500)}"],
    "v14": [f"설명 API(status {ex.get('status')}, 질문 종류 {ex.get('why')}, 응답 {(ev('explain_seconds') or {}).get('secs')}초): 판정 「{fr.get('judge')}」",
            "사용한 사실: " + " / ".join(f["text"] for f in fr.get("facts", [])),
            "아직 확인할 것: " + " / ".join(f["text"] for f in fr.get("left", [])),
            f"설명 틀 fallback={fr.get('fallback')} · 앱 자체 검증 ok={ex.get('verify', {}).get('ok')} (실패 항목: " + ", ".join(f"{c['name']} — {c['why']}" for c in ex.get("verify", {}).get("checks", []) if not c["ok"]) + ")"],
    "v15": [f"AI 검토 API(약 {(ev('pair_review_seconds') or {}).get('secs')}초, 모델 {pr.get('meta', {}).get('ms')}ms): status {pr.get('status')} · {pr.get('why')} · AI가 고른 관계 「{pr.get('rel_text')}」",
            f"화면: {one(ev('pair_review_screen'), 700)}", f"검토 집계 전 {json.dumps((ev('pair_review_before') or {}).get('count'), ensure_ascii=False)} → 후 {json.dumps(ev('pair_review_after'), ensure_ascii=False)}"],
    "v16": [f"배치도: {ev('map_now')}", f"표시된 막대: {' / '.join(ev('map_bars') or [])}"],
    "v17": [f"P02 협의할 점 API: {json.dumps(ev('coord_note_api_P02'), ensure_ascii=False)}", f"P02 문자 패널: {one(ev('post_panel_P02'), 700)}",
            f"P22 협의할 점 API: {json.dumps(ev('coord_note_api_example'), ensure_ascii=False)}", f"복사 안내: {ev('toast')}"],
    "v18": [f"AI 문안 API(status {dr.get('status')}, 응답 {(ev('post_draft_seconds') or {}).get('secs')}초): " + " / ".join(dr.get("lines", [])),
            f"채택 안내: {ev('toast_take')}", f"채택 뒤 별지(P02 부분): {one(ev('sheet_after_take'), 900)}"],
    "v19": [f"발행 안내: {ev('toast_publish')}", f"발행 카드: {one(ev('issued_card'))}", f"발행본: {one(ev('issued_view'), 1200)}"],
}
DIFF = {
    "v12": ["30번 「관리자 화면에 같은 0731」은 안전관리자 문서 목록의 0731 화기 행으로 보여 줍니다(비일상 10건 · 일상 40건).",
            "도넛과 순위별 목록은 홈의 위험 쌍 요약(26쌍 = 1순위 8 · 2순위 2 · 3순위 16)으로 짧게 보여 줍니다(시연 자료 기준)."],
    "v13": ["대응 서류 대조는 문서 목록의 문서 패널(WP-1029-01 계획서 「먼저 볼 것」 시간·장소, 0731 허가서 패널)로 보여 줍니다. 원본 PDF 화면은 열지 않았습니다.",
            "콘티 4번 「남은 확인 사항으로 돌아온다」는 V14 끝의 「아직 확인할 것」으로 이어집니다(이 클립 안에는 넣지 않음)."],
    "v14": ["질문은 「왜 1순위인가요?」 한 건입니다. 입력 장면은 연속 녹화가 아니어서 입력 문장을 큰 글씨로 재현하고 「입력 내용 재현 · 실제 입력한 질문」이라고 표시했습니다.",
            "앱 응답이 약 2.2초로 빨라 기다리는 화면은 짧습니다."],
    "v15": ["실제 결과가 「근거 부족으로 보류」(status held)라서 39번은 콘티 표의 「근거가 부족한 내용은 보류로 남깁니다.」를 썼습니다. 보조자막 「기존 검토 결과는 유지」는 그대로입니다(화면에도 「규칙 판정은 그대로입니다」).",
            "주 사례(P02)와 다른 쌍 0738 × WP-22를 썼고, 화면 위쪽에 「추가 검토 예시 · 별도 작업쌍 0738 × WP-22」 표시를 계속 띄웠습니다. 실제 응답은 약 30초였고 기다린 구간은 줄였습니다(화면에 표시)."],
    "v16": ["콘티 4번 「두 작업 상세로 돌아와 협조 문자 작성 화면 열기」는 V17 첫 화면(문자 작성 화면)으로 이어집니다.",
            "배치도는 계획 서류 기준의 대략적 위치입니다. 실시간 위치가 아닙니다."],
    "v17": ["P02에서는 「협의할 점」 AI 제안이 나오지 않았습니다(API status none · 확인된 반장 답이 없음). 그래서 42번은 P02 문자 화면, 43~45번은 제안이 실제로 나온 다른 쌍 P22(0735 × WP-08, 3순위)로 보여 주고 화면 위쪽에 「다른 작업쌍 예시 · P22」라고 표시했습니다.",
            "문자는 「문자 복사」까지만 했습니다. croScan은 문자를 보내지 않습니다(복사 안내 원문 그대로)."],
    "v18": ["AI 문안의 근거는 「규칙 문구」 2건입니다. 콘티의 「확인 답 근거」는 이번 결과에 없어서 47번 강조는 규칙 문구 근거만 짚었습니다.",
            "발행 조건(자료 확인) 준비는 화면 밖에서 했습니다."],
    "v19": ["발행은 서류 발행입니다. 승인·게시·이행이 아닙니다. 「전달·수신 확인·게시(교체) 완료」 버튼은 누르지 않았습니다.",
            "별지의 착수조건 칸은 V18에서 채택한 AI 문안이 그대로 들어간 발행본(S-0731/R1)입니다."],
}
LIMITS = {
    "v12": ["숫자(위험 쌍 26 등)는 촬영 시점의 시연 자료 기준입니다."],
    "v13": ["0731 쪽 장소·시간은 반장 답을 반영한 제출본 값(제출본 0DMvF7, 이전 촬영에서 만든 제출본)입니다. 원본 허가서 기재와 다릅니다."],
    "v14": [f"설명의 본문(사용한 사실·아직 확인할 것)은 앱이 서류 사실로 만든 틀입니다(fallback={fr.get('fallback')}). AI는 질문을 「어떤 서류 값·반장 답을 썼나요?」 설명으로 읽었습니다.",
            "앱 자체 검증에서 「구절 존재」 1건이 실패했습니다: 0731 위치(제출본 반영) 값 「…E42P 블록 상부고」가 현재 서류에 없다고 나옵니다(이전 반장 답 촬영의 말끝 「고」가 남은 값). 화면에 그대로 보입니다."],
    "v15": ["AI 추가 검토는 규칙 판정이 아니며 위험 쌍 목록·순위·점수에 들어가지 않습니다(화면 문구). 추가 제안이 실제로 반환되는 사례는 이번 촬영에 없습니다."],
    "v16": ["13:30 배치도에는 일상 13건 · 비일상 3건이 있고 영상은 P02 두 작업 막대만 확대합니다."],
    "v17": ["이름·번호는 가린 값(김XX·박XX·강XX, 010-XXXX-XXXX)입니다. 실제 전송 기능은 없습니다."],
    "v18": ["AI 문안 응답은 약 2.1초였습니다. 채택한 문안은 미발행 서류에 들어가며 발행 전 고칠 수 있습니다."],
    "v19": ["발행 시각 14:11은 촬영 시각입니다. 「착수조건」 칸은 V18 채택 문안 기준입니다(중지·해제 조건 칸은 규칙 문구)."],
}
REP = {"v12": "pair_why", "v13": "docs", "v14": "answer", "v15": "result", "v16": "map", "v17": "copy", "v18": "take", "v19": "stop"}


def secs(mp4):
    r = subprocess.run([FF, "-i", str(mp4)], capture_output=True, text=True, encoding="utf-8", errors="ignore")
    h, m, s = r.stderr.split("Duration:")[1].split(",")[0].strip().split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def sheet(v, mp4):
    SHEETS.mkdir(exist_ok=True)
    tag = v.upper()
    for f in SHEETS.glob(f"{tag}_f*.png"):
        f.unlink()
    subprocess.run([FF, "-y", "-loglevel", "error", "-i", str(mp4), "-vf", r"select=not(mod(n\,60)),scale=640:-1", "-vsync", "vfr", str(SHEETS / f"{tag}_f%03d.png")], check=True)
    frames = sorted(SHEETS.glob(f"{tag}_f[0-9][0-9][0-9].png"))
    font = ImageFont.truetype("C:/Windows/Fonts/malgunbd.ttf", 22)
    cols = 4
    im = Image.new("RGB", (640 * cols, 360 * ((len(frames) + cols - 1) // cols)), "#111")
    d = ImageDraw.Draw(im)
    for i, f in enumerate(frames):
        x, y = (i % cols) * 640, (i // cols) * 360
        im.paste(Image.open(f), (x, y))
        d.rectangle([x, y, x + 74, y + 30], fill="black")
        d.text((x + 6, y + 2), f"{i * 2:d}초", fill="#FFE14D", font=font)
        f.unlink()
    im.save(SHEETS / f"{tag}_sheet.png")
    return len(frames)


def main(only):
    FINAL.mkdir(exist_ok=True)
    pf = S / "manifest_part.json"
    part = json.loads(pf.read_text(encoding="utf-8")) if pf.exists() else {"clips": {}}
    for v in NAMES:
        if only and v not in only:
            continue
        src = PRAI / "out" / v / f"{v}.mp4"
        if not src.exists():
            print(v, "no render"); continue
        dst = FINAL / f"croScan_{NAMES[v]}.mp4"
        dst.write_bytes(src.read_bytes())
        dur = secs(dst)
        rows = [r for r in SMAP[v] if "scene" in r]
        planned = SMAP[v][-1]["total_s"]
        rep = next(r for r in rows if r["scene"] == REP[v])
        t = min(dur - 0.3, (rep["cap_start_s"] + rep["cap_end_s"]) / 2 if rep.get("cap_start_s") else dur - 1)
        png = FINAL / f"croScan_{NAMES[v]}_대표화면.png"
        subprocess.run([FF, "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", str(dst), "-frames:v", "1", str(png)], check=True)
        n = sheet(v, dst)
        caps = [{"no": r["caption"], "start_s": r["cap_start_s"], "end_s": min(r["cap_end_s"], round(dur, 2)), "headline": r["headline"], "sub": r["sub"], "scene": r["scene"],
                 "shots": r["shots"]} for r in rows if r["caption"]]
        part["clips"][v] = {"clip": v.upper(), "title": TITLES[v], "file": dst.name, "png": png.name, "sheet": f"work19/sheets/{v.upper()}_sheet.png",
                            "seconds": round(dur, 2), "planned_seconds": planned, "captions": caps, "scenes": [{"scene": r["scene"], "start_s": r["start_s"], "caption": r["caption"]} for r in rows],
                            "inputs": INPUTS[v], "actual_results": RESULTS[v], "changes_from_conti": DIFF[v], "known_limits": LIMITS[v]}
        print(v, dst.name, f"{dur:.2f}s (plan {planned}s)", "sheet", n, "frames", "png @", f"{t:.1f}s")
    part["clips"] = dict(sorted(part["clips"].items()))
    part["common"] = {"app": "스테이징 http://localhost:8776/ (안전관리자 데모 로그인)", "capture_log": "work19/S/cap/log_S19.json",
                      "capture_time": "2026-11-02 14:08~14:12", "submission_0731": ev("submissions_api_0731_end"),
                      "spec": "work19/S/build19.py → v12..v19/prai.json, scenemap19.json", "render": "PRAI render (−14 LUFS, bt709), 한 번에 하나씩"}
    pf.write_text(json.dumps(part, ensure_ascii=False, indent=1), encoding="utf-8")
    write_md(part)


def write_md(part):
    L = ["## 안전관리자 편 V12~V19 (작업 S)", "",
         f"촬영: {part['common']['capture_time']} · {part['common']['app']} · 로그 `{part['common']['capture_log']}` · 0731 제출본 `{part['common']['submission_0731']}`", ""]
    for v, c in part["clips"].items():
        L += [f"### {c['clip']} · {c['title']}", "", f"- 파일 `{c['file']}` · 대표 화면 `{c['png']}` · 프레임 시트 `{c['sheet']}`", f"- 길이 {c['seconds']:.1f}초", "",
              "| 자막 | 시작 | 끝 | 주자막 | 보조자막 |", "|---|---|---|---|---|"]
        L += [f"| {x['no']} | {x['start_s']:.1f}초 | {x['end_s']:.1f}초 | {x['headline']} | {x['sub'] or '—'} |" for x in c["captions"]]
        L += ["", "**실제 입력**", ""] + [f"- {x}" for x in c["inputs"]]
        L += ["", "**실제 앱 결과 (촬영 로그 발췌)**", ""] + [f"- {x}" for x in c["actual_results"]]
        L += ["", "**콘티와 달라진 점**", ""] + [f"- {x}" for x in c["changes_from_conti"]]
        L += ["", "**알려진 한계**", ""] + [f"- {x}" for x in c["known_limits"]] + [""]
    (S / "manifest_part.md").write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1:])
