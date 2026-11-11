"""V12–V19 + V14B + V17B (21-clip conti, captions 30–57): copy PRAI renders to final19 with Korean names, one representative PNG,
2-second frame sheets (work19/sheets), manifest_part.json/.md.   usage: python package21.py [v12 v14b ...]
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
SM = json.loads((S / "scenemap21.json").read_text(encoding="utf-8"))
SMAP, CHOICE = SM["clips"], SM["choice"]


def load(p):
    return json.loads(p.read_text(encoding="utf-8"))["events"] if p.exists() else []


L1, LF, L2 = load(S / "cap1" / "log_S21_1.json"), load(S / "capF" / "log_F.json"), load(S / "cap2" / "log_S21_2.json")
ev = lambda L, k: next((e["v"] for e in L if e["k"] == k), None)
TYPED_F = json.loads((S / "capF" / "log_F.json").read_text(encoding="utf-8")).get("typed_first")


def one(s, n=600):
    s = s if isinstance(s, str) else json.dumps(s, ensure_ascii=False)
    s = " / ".join(x.strip() for x in s.splitlines() if x.strip())
    return s if len(s) <= n else s[:n] + "…"


NAMES = {
    "v12": ("V12", "같은_구역의_화기와_도장", "같은 구역의 화기와 도장"),
    "v13": ("V13", "판정에_사용한_서류로_돌아가기", "판정에 사용한 서류로 돌아가기"),
    "v14": ("V14", "필요한_설명을_직접_질문", "필요한 설명을 직접 질문"),
    "v14b": ("V14B", "담당_반장에게_확인하고_재제출", "부족한 정보는 담당 반장에게 확인하고 재제출"),
    "v15": ("V15", "선택적_AI_추가_검토", "선택적 AI 추가 검토 — 독립 삽입용"),
    "v16": ("V16", "같은_시각의_배치_확인", "조율 전에 같은 시각의 배치 확인"),
    "v17": ("V17", "협조_문자_작성과_복사", "작업 조율 협조 문자 작성과 복사"),
    "v17b": ("V17B", "일정_조율과_승인_완료_연결", "문자 전달 후 일정 조율·기존 승인 완료를 연결"),
    "v18": ("V18", "AI_게시_문안_제안과_별지_반영", "AI의 현장 게시 문안 제안과 별지 반영"),
    "v19": ("V19", "할_일_착수조건_중지조건_확인", "우리 반의 할 일·착수조건·중지조건 확인"),
}
REP = {"v12": "pair_time", "v13": "docs", "v14": "answer", "v14b": "review", "v15": "result", "v16": "map", "v17": "copy", "v17b": "approved",
       "v18": "take", "v19": "whole"}
ex = ev(L1, "explain_api") or {}
fr = ex.get("frame", {})
rv = ev(L2, "pair_review_api") or {}
dr = ev(L2, "post_draft_api") or {}
s0731 = (ev(L1, "submissions_api_start") or {}).get("0731") or {}
sub_new = (ev(LF, "submission") or {}).get("id")
sub_old = ((ev(L1, "submissions_api_phase1_end") or {}).get("0735") or {}).get("id")      # when the manager asked (before any resubmission)
rem = ev(LF, "remaining") or []
INPUTS = {
    "v12": ["로그인: 역할 「안전관리자」 선택 후 「로그인」(데모 로그인)", "문서 목록 → 0731 행 선택(요약 카드) → 위험 쌍 → 1순위 → P02(0731 × WP-01) → 「입력 보강 전후」 펼침"],
    "v13": ["P02 상세에서 「판정 근거·원문」 펼침", "판정 근거의 문서 열기: WP-1029-01 계획서, 0731 허가서"],
    "v14": [f"자유 질문 입력(키보드로 실제 입력): 「{ev(L1, 'free_question_typed')}」 → 「묻기」"],
    "v14b": [f"안전관리자: 3순위 P21(0732 × 0735) → 「담당별 확인」의 0735 반장 질문 → 「질문 복사」 (복사된 글: {one(ev(L1, 'hq_clipboard'))})",
             "0735 작업반장(반장 화면, 새 브라우저): 작업계획서 WP-1029-04(삼녹) → 고소 · 0735_고소_A.pdf → 첫 질문에 직접 입력: 「" + (TYPED_F or "") + "」",
             "AI 읽기 카드: 시간·장소 2줄만 확인, 준비 자료와 다른 「그라인더·기계절단」 줄과 「3명, 2시간」 줄은 「이것 빼기」",
             "남은 질문(준비 자료 samples/시연_하루/permits.json 0735 answers_truth 값만): " + "; ".join(f"{(r.get('chose') or r.get('clicked'))}{(' + 「' + r['typed'] + '」') if r.get('typed') else ''}" for r in rem),
             "위험 체크리스트: 앱 제안 그대로 확인 → 「안전팀에 제출」(재제출)",
             "안전관리자(새 브라우저): P21 다시 열기 → 「입력 보강 전후」 → 1순위 P02로 돌아옴"],
    "v15": [f"검토 통과 인접 작업 중 아직 AI 검토를 하지 않은 쌍: {(ev(L2, 'pair_review_before') or {}).get('chosen')}", "「AI 검토 요청」 한 번"],
    "v16": ["P02 상세 → 「배치도에서 보기」 → 시각 13:30"],
    "v17": ["P02 「작업 조정 문자 작성」 → 빈칸 3개(협의 상대 번호, 보내는 사람 이름·번호)는 가린 시연 값(010-XXXX-XXXX, 이XX)",
            f"「협의할 점」 예시: P02는 제안 없음이라 {(ev(L2, 'example_pair') or {}).get('id')}(0735 × WP-08)에서 「문자에 넣기」 → 「문자 복사」"],
    "v17b": ["입력 없음. 앱 화면이 아닌 PRAI 모션 블록(제목·칩)으로 만든 시나리오 전환 화면"],
    "v18": ["현장 게시 서류 → ② 서류 발행 → 0731 「미리 보기·편집」 → 「AI 문안 보충 보기」 → 「문안 채택」",
            "사전 준비(화면 밖, 이 브라우저): 문서 목록에서 0731의 허가서·추가검토서·위험 체크리스트를 「확인」 처리(발행 조건): " + ", ".join(ev(L2, "docs_confirmed_before_issue_offscreen") or [])],
    "v19": ["현장 게시 서류 → 0731 「발행」 → 「보기」(발행본 전체 별지)"],
}
RESULTS = {
    "v12": [f"홈: {one(ev(L1, 'nav'), 300)}", f"0731 요약 카드: {one(ev(L1, 'doc_sum_0731'), 300)}", f"위험 쌍: {one(ev(L1, 'res'))}",
            f"P02 판정 자료 줄: {ev(L1, 'pair_ver_line')}", f"P02 입력 보강 전후: {one(ev(L1, 'pair_hybrid_p02'), 500)}"],
    "v13": [f"판정: {one(ev(L1, 'judgement'), 400)}", f"WP-1029-01 패널: {one(ev(L1, 'doc_panel_WP-1029-01'), 400)}", f"0731 패널: {one(ev(L1, 'doc_panel_0731'), 600)}"],
    "v14": [f"설명 API(status {ex.get('status')}, 질문 종류 {ex.get('why')}, 응답 {(ev(L1, 'explain_seconds') or {}).get('secs')}초): 판정 「{fr.get('judge')}」",
            "사용한 사실: " + " / ".join(f["text"] for f in fr.get("facts", [])),
            "아직 확인할 것: " + " / ".join(f["text"] for f in fr.get("left", [])),
            f"설명 틀 fallback={fr.get('fallback')} · 앱 자체 검증 ok={ex.get('verify', {}).get('ok')} (실패: " + ", ".join(f"{c['name']} — {c['why']}" for c in ex.get("verify", {}).get("checks", []) if not c["ok"]) + ")"],
    "v14b": [f"P21 판정 자료(전): {ev(L1, 'hq_pair_ver_before')}", f"담당별 확인 0735 카드: {one(ev(L1, 'hq_card_0735'))}", f"복사 버튼: {ev(L1, 'hq_copy_button')}",
             f"반장 첫 질문: {one(ev(LF, 'first_question'))}", f"AI 읽기 카드(확인 전): {one(ev(LF, 'first_card'), 500)}",
             f"재제출: {sub_old} → {sub_new} · {one((ev(LF, 'submission') or {}).get('summary'), 300)}",
             f"P21 판정 자료(후): {ev(L2, 'hq_pair_ver_after')}", f"P21 입력 보강 전후(후): {one(ev(L2, 'hq_pair_hybrid_after'), 600)}",
             "0735 담당별 확인 질문 상태(후): " + ", ".join(f"{q['text'][:20]}… {q['state']}" for q in (ev(L2, 'hold_questions_0735_after') or {}).get("questions", []))],
    "v15": [f"AI 검토 API(약 {(ev(L2, 'pair_review_seconds') or {}).get('secs')}초): status {rv.get('status')} · {rv.get('why')} · AI가 고른 관계 「{rv.get('rel_text')}」",
            f"화면: {one(ev(L2, 'pair_review_screen'), 600)}", f"검토 집계 후: {json.dumps(ev(L2, 'pair_review_after'), ensure_ascii=False)}"],
    "v16": [f"배치도: {ev(L2, 'map_now')}", f"표시된 막대: {' / '.join(ev(L2, 'map_bars') or [])}"],
    "v17": [f"P02 협의할 점 API: {json.dumps(ev(L2, 'coord_note_api_P02'), ensure_ascii=False)}", f"P22 협의할 점 API: {json.dumps(ev(L2, 'coord_note_api_example'), ensure_ascii=False)}",
            f"복사 안내: {ev(L2, 'toast')}"],
    "v17b": ["앱 결과 없음(시나리오 가정 화면)"],
    "v18": [f"AI 문안 API(status {dr.get('status')}, 응답 {(ev(L2, 'post_draft_seconds') or {}).get('secs')}초): " + " / ".join(dr.get("lines", [])),
            f"채택 안내: {ev(L2, 'toast_take')}", f"채택 뒤 별지: {one(ev(L2, 'sheet_after_take'), 700)}"],
    "v19": [f"발행 안내: {ev(L2, 'toast_publish')}", f"발행 카드: {one(ev(L2, 'issued_card'))}", f"발행본: {one(ev(L2, 'issued_view'), 1000)}"],
}
DIFF = {
    "v12": ["30번 장면은 문서 목록의 0731 요약 카드(장소 3BAY 08–10 · E42P 상부, 시간 13:00–15:00, 추가 답변 3건)로 반장 확인 값을 보여 줍니다.",
            "32번 장면에서 판정 자료 줄(0731 제출본 반영 · 시간 13:00~15:00 / WP-01 서류 기준)과 「입력 보강 전후」(답 반영 전후 모두 1순위 9점)를 보여 줍니다. 90분 겹침이 답 때문에 새로 생겼다고 말하지 않습니다."],
    "v13": ["대응 서류 대조는 문서 패널(WP-1029-01 「먼저 볼 것」 시간·장소, 0731 허가서의 원본 장소 칸과 답변 반영 칸)로 보여 줍니다. 원본 PDF 화면은 열지 않았습니다."],
    "v14": ["입력 장면은 연속 녹화가 아니어서 입력 문장을 큰 글씨로 재현하고 「입력 내용 재현 · 실제 입력한 질문」이라고 표시했습니다."],
    "v14b": ["0731 주 사례의 담당별 확인 질문(불티가 닿는 범위)은 준비 자료로 답할 수 없어서, 실제 미확인이 남은 P21(0732 × 0735)의 0735 반장 질문 「작업 위치·시간과 인원 배치」를 「추가 확인 예시」로 썼고, 끝에서 P02로 돌아옵니다.",
             "반장 화면은 같은 순간의 연속 녹화가 아니라 0735 반장 흐름을 따로 실제로 진행해 찍은 화면입니다. 입력 문장은 큰 글씨로 재현하고 「입력 내용 재현」이라고 표시했습니다.",
             "재제출 뒤 P21은 「0735 제출본 반영(위치·시간·확인한 답 1건)」으로 다시 판정됐고 순위·점수는 3순위 그대로입니다. 40번은 완료형 문구를 썼습니다(재제출 id와 관리자 화면 반영을 로그로 확인).",
             "「전달함·답변 받음」 표시는 누르지 않았습니다(질문 상태는 미전달 그대로). 판정 변경은 표시가 아니라 재제출본으로 일어납니다."],
    "v15": [f"실제 결과가 「{rv.get('why')}」(status {rv.get('status')})라서 42번은 「{CHOICE['42']['caption']}」를 썼습니다. 보조자막 「기존 검토 결과는 유지」는 그대로입니다.",
            "주 사례와 다른 쌍을 썼고 화면 위쪽에 「추가 검토 예시 · 별도 작업쌍」 표시를 계속 띄웠습니다. 기다린 구간은 줄였습니다(화면에 실제 걸린 초 표시)."],
    "v16": ["콘티 4번 「협조 문자 작성 화면 열기」는 V17 첫 화면으로 이어집니다. 배치도는 계획 서류 기준의 대략적 위치입니다."],
    "v17": ["P02는 「협의할 점」 제안이 없어서(확인된 반장 답 없음) 46~48번은 제안이 실제로 나온 P22(0735 × WP-08, 3순위)로 보여 주고 「다른 작업쌍 예시 · P22」라고 표시했습니다. 제안의 출처는 V14B에서 재제출한 0735 반장 답 「가스절단 3개」입니다.",
            "문자는 「문자 복사」까지만 했습니다(croScan은 문자를 보내지 않음)."],
    "v17b": ["앱 밖의 문자 전달 → 반장 간 일정 조율 → 생산부서 전산승인을 순서대로 보이고 「앱 외부 진행 · 협의·승인 완료를 가정」을 함께 표시했습니다. 합성 승인 화면·서명은 만들지 않았습니다.",
             "앞은 V17의 실제 복사 결과 화면에서 이어지고, 끝은 「협의·승인 후 현장 전달 자료 준비」로 V18에 넘깁니다. 일정 변경 시간은 제시하지 않으므로 V18~V19에서 겹침 감소를 보여 주지 않습니다."],
    "v18": ["첫 장면 위쪽에 「가정: 반장 간 협의·생산부서 전산승인을 마친 뒤」를 표시했습니다.",
            "AI 문안의 근거 표시는 「규칙 문구」 2건이고, 문안의 시간·위치(13:00~15:00 · 3BAY 08-10 칼럼 E42P 블록 상부)는 0731 제출본(반장 확인) 값입니다. 52번 강조는 이 근거 줄을 짚었습니다."],
    "v19": ["발행은 서류 발행입니다. 승인·게시·이행이 아닙니다. 「전달·수신 확인·게시(교체) 완료」는 누르지 않았습니다.",
            "56번은 「중지·해제 조건」 칸과 「상대 반장·연락처」 칸(연락할 대상)을 짚었습니다. 57번은 발행본 전체 별지(P02·P17)에서 세 항목 위치를 보이며 끝냅니다."],
}
LIMITS = {
    "v12": ["숫자(위험 쌍 26 등)는 촬영 시점의 시연 자료 기준입니다."],
    "v13": ["0731 쪽 장소·시간은 반장 답을 반영한 제출본 값입니다. 원본 허가서의 장소 칸은 팀 이름(대조립3부 용접2팀)입니다."],
    "v14": [f"설명 본문은 앱이 서류 사실로 만든 틀입니다(fallback={fr.get('fallback')}). AI는 질문을 「어떤 서류 값·반장 답을 썼나요?」 설명으로 읽었습니다.",
            "앱 자체 검증 「구절 존재」 1건 실패: F7 0731 위치(제출본 반영) 「3BAY 08~10칼럼 E42P 블록 상부」가 현재 서류 표기(08-10 칼럼)와 글자가 달라 「현재 서류에 없는 값」으로 나옵니다. 화면에 그대로 보입니다."],
    "v14b": ["재제출에서 「작업시간 120분 참고시간보다 짧음」 질문 1건은 준비 자료로 답할 수 없어 「모름」으로 답했습니다.",
             "촬영 자동화 과정에서 0735 재제출은 두 번 일어났습니다(첫 재제출 KVOB1agnwpD1SNSU는 시간·장소만 반영하고 나머지 「모름」, 영상의 재제출은 마지막 " + str(sub_new) + "). 두 번째도 같은 준비 자료 값만 썼습니다.",
             "답 반영 뒤에도 P21의 순위·점수는 그대로입니다. 경보 해소를 약속하지 않습니다."],
    "v15": ["AI 추가 검토는 규칙 판정이 아니며 위험 쌍 목록·순위·점수에 들어가지 않습니다(화면 문구). 추가 제안이 실제로 반환되는 사례는 이번 촬영에 없습니다."],
    "v16": ["13:30 배치도에는 일상 13건 · 비일상 3건이 있고 영상은 P02 두 작업 막대만 확대합니다."],
    "v17": ["이름·번호는 가린 값(김XX·박XX·강XX, 010-XXXX-XXXX)입니다. 실제 전송 기능은 없습니다."],
    "v17b": ["시나리오 가정 화면이므로 실제 연락·협의·전산승인이 있었다는 증거가 아닙니다."],
    "v18": [f"AI 문안 응답은 약 {(ev(L2, 'post_draft_seconds') or {}).get('secs')}초였습니다. 채택한 문안은 미발행 서류에 들어가며 발행 전 고칠 수 있습니다."],
    "v19": ["발행 시각은 촬영 시각입니다. 별지 상태는 이 브라우저에 저장됩니다(서버 저장 아님)."],
}


def secs(mp4):
    r = subprocess.run([FF, "-i", str(mp4)], capture_output=True, text=True, encoding="utf-8", errors="ignore")
    h, m, s = r.stderr.split("Duration:")[1].split(",")[0].strip().split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def sheet(tag, mp4):
    SHEETS.mkdir(exist_ok=True)
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
    part = {"clips": {}}
    if pf.exists():
        old = json.loads(pf.read_text(encoding="utf-8"))
        if old.get("conti") == "21":
            part = old
    part["conti"] = "21"
    for v, (tag, short, title) in NAMES.items():
        if only and v not in only:
            continue
        src = PRAI / "out" / v / f"{v}.mp4"
        if not src.exists():
            print(v, "no render"); continue
        dst = FINAL / f"croScan_{tag}_{short}.mp4"
        dst.write_bytes(src.read_bytes())
        dur = secs(dst)
        rows = [r for r in SMAP[v] if "scene" in r]
        rep = next(r for r in rows if r["scene"] == REP[v])
        t = min(dur - 0.3, (rep["cap_start_s"] + rep["cap_end_s"]) / 2 if rep.get("cap_start_s") is not None else dur - 1)
        png = FINAL / f"croScan_{tag}_{short}_대표화면.png"
        subprocess.run([FF, "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", str(dst), "-frames:v", "1", str(png)], check=True)
        n = sheet(tag, dst)
        caps = [{"no": r["caption"], "start_s": r["cap_start_s"], "end_s": min(r["cap_end_s"], round(dur, 2)), "headline": r["headline"], "sub": r["sub"], "scene": r["scene"],
                 "shots": r["shots"]} for r in rows if r["caption"]]
        part["clips"][v] = {"clip": tag, "title": title, "file": dst.name, "png": png.name, "sheet": f"work19/sheets/{tag}_sheet.png", "seconds": round(dur, 2),
                            "captions": caps, "scenes": [{"scene": r["scene"], "start_s": r["start_s"], "caption": r["caption"], "shots": r["shots"]} for r in rows],
                            "inputs": INPUTS[v], "actual_results": RESULTS[v], "changes_from_conti": DIFF[v], "known_limits": LIMITS[v]}
        print(v, dst.name, f"{dur:.2f}s", "sheet", n, "png @", f"{t:.1f}s")
    order = list(NAMES)
    part["clips"] = {k: part["clips"][k] for k in order if k in part["clips"]}
    part["common"] = {"app": "스테이징 http://localhost:8776/ (데모 로그인)", "logs": ["work19/S/cap1/log_S21_1.json (V12–V14, V14B 질문 복사)",
                      "work19/S/capF/log_F.json (V14B 0735 반장 재제출)", "work19/S/cap2/log_S21_2.json (V14B 재검토, V15–V19)"],
                      "submission_0731": s0731.get("id"), "submission_0735_before": sub_old, "submission_0735_after": sub_new, "choice": CHOICE,
                      "spec": "work19/S/build21.py + scenes21.py + scenes21b.py → v12..v19, v14b, v17b /prai.json, scenemap21.json",
                      "render": "PRAI render (−14 LUFS, bt709), 한 번에 하나씩"}
    pf.write_text(json.dumps(part, ensure_ascii=False, indent=1), encoding="utf-8")
    c = part["common"]
    L = ["## 안전관리자 편 V12~V19 · V14B · V17B (자막 30~57, 작업 S)", "",
         f"촬영 2026-11-02 · {c['app']} · 0731 제출본 `{c['submission_0731']}`(반장 담당 A의 테이크 B 제출본) · 0735 재제출 `{c['submission_0735_before']}` → `{c['submission_0735_after']}`",
         "로그: " + " · ".join(f"`{x}`" for x in c["logs"]), "",
         f"결과에 따라 고른 자막: 42번 「{CHOICE['42']['caption']}」(AI 추가 검토 status {CHOICE['42']['status']}) · 40번 「{CHOICE['40']['caption']}」(재제출 반영 확인 {CHOICE['40']['resubmitted']})", ""]
    for v, x in part["clips"].items():
        L += [f"### {x['clip']} · {x['title']}", "", f"- 파일 `{x['file']}` · 대표 화면 `{x['png']}` · 프레임 시트 `{x['sheet']}`", f"- 길이 {x['seconds']:.1f}초", "",
              "| 자막 | 시작 | 끝 | 주자막 | 보조자막 |", "|---|---|---|---|---|"]
        L += [f"| {k['no']} | {k['start_s']:.1f}초 | {k['end_s']:.1f}초 | {k['headline']} | {k['sub'] or '—'} |" for k in x["captions"]]
        for h, key in (("실제 입력", "inputs"), ("실제 앱 결과 (촬영 로그 발췌)", "actual_results"), ("콘티와 달라진 점", "changes_from_conti"), ("알려진 한계", "known_limits")):
            L += ["", f"**{h}**", ""] + [f"- {y}" for y in x[key]]
        L.append("")
    (S / "manifest_part.md").write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1:])
