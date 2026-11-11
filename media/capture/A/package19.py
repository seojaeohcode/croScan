"""Copy the rendered foreman clips V01–V11 to final19 with Korean names, cut one representative PNG each, and write
manifest_part.json / manifest_part.md (lengths, caption times, real inputs, real app results, differences, limits).
usage: python package19.py   (after the renders and sheets19.py)
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

W = Path(__file__).parent
OUT = W.parent.parent / "final19"
OUT.mkdir(exist_ok=True)
PRAI = Path("C:/Users/seoco/OneDrive/Desktop/PRAI")
FF = str(PRAI / "node_modules/ffmpeg-static/ffmpeg.exe")
SM = json.loads((W / "scenemap19.json").read_text(encoding="utf-8"))
META = SM.pop("meta")
LOG = {k: {e["k"]: e["v"] for e in json.loads((W / f"cap{k}" / f"log_{k}.json").read_text(encoding="utf-8"))["events"]} for k in "AB"}
A, B = LOG["A"], LOG["B"]
for _k in "AB":
    LOG[_k]["typed"] = json.loads((W / f"cap{_k}" / f"log_{_k}.json").read_text(encoding="utf-8"))["typed"]
PDF = json.loads((W / "pdfshots" / "pdfinfo.json").read_text(encoding="utf-8"))
one = lambda s, n=600: re.sub(r"\s*\n\s*", " / ", str(s or "")).strip()[:n]

CLIPS = {  # proj: (file title, representative scene)
    "v01": ("V01_기존_작업계획서로_시작", "read"),
    "v02": ("V02_허가서_종류와_화기_선택", "orig"),
    "v03": ("V03_시간_위치_공법을_한번에_답변", "card"),
    "v04": ("V04_오타를_넣어_비교", "card"),
    "v05": ("V05_읽은_값_확인과_반영", "compare"),
    "v06": ("V06_핵심정보_재확인", "popup"),
    "v07": ("V07_대표_위험과_준비_조치", "fire"),
    "v08": ("V08_AI의_보완_제안", "quote"),
    "v09": ("V09_위험한_이유와_사례", "why"),
    "v10": ("V10_관련_자료와_출처", "source"),
    "v11": ("V11_제출과_반영본_추가검토서", "permit"),
}
SUB = META["submission"]
INPUTS = {
    "v01": ["역할 「생산부서 작업반장」 → 로그인(데모 로그인, 계정 없음)",
            "작업계획서 2건: WP-1029-01_동성화인텍.pdf(협력사), WP-1029-10_대조립1부-운반1팀.pdf(본청) → 「작업계획서 읽기」",
            "두 계획서의 「확인」을 누름 → 「다음: 허가서 올리기」"],
    "v02": ["허가서 종류 「화기」 선택, 파일 0731_화기_A.pdf → 「검토 시작」"],
    "v03": [f"테이크 A(기본 입력, 직접 입력): {A['typed']}"],
    "v04": [f"테이크 B(오타 입력, 새로 로그인한 같은 시작 상태에서 직접 입력): {B['typed']}"],
    "v05": [f"작업장소 줄 「항목 고치기」: 「{B['fix_before']}」 → 「3BAY 08~10칼럼 E42P 블록 상부」 → 「이 값으로 답하기」",
            "카드의 「확인」 버튼으로 나머지(작업시간·공법·가스) 확인"],
    "v06": ["「다음: 위험 체크리스트」 → 핵심정보 창 → 「확인하고 체크리스트로」",
            f"남은 질문에 버튼으로 답함: {', '.join(B['remaining_answers'])} (「가스 안 씀」은 누르지 않음)"],
    "v07": ["01 불티 항목: 「「해당」 그대로 확인」, 「준비할 안전조치 그대로 확인」(croScan이 고른 조치를 바꾸지 않음)"],
    "v08": [f"AI 제안 줄이 붙은 항목 「{one(B['cand_pick']['text'], 40).split(' / ')[0]}」에서 「「해당」 그대로 확인」"],
    "v09": ["01 불티 항목의 「위험한 이유 보기」"],
    "v10": ["3단계(허가서 검토)로 돌아가 첫 질문(작업일시)의 「왜 묻나요?」 → 닫기"],
    "v11": [f"나머지 항목은 「다음 미완료로 이동」으로 앱 제안 그대로 확인 {B['check_steps']}번(영상에서는 줄임) → 「다음: 제출 확인」 → 「안전팀에 제출」",
            f"제출본 id: {SUB} (PDF: capB/pdf/{SUB}_permit.pdf 1쪽 반영본·2쪽 추가검토서)"],
}
RESULTS = {
    "v01": [f"읽힌 계획서 목록: {one(B['plans_list'])}"],
    "v02": [f"허가서 종류: {one(B['kinds'])}", f"첫 질문: {one(B['first_question'])}"],
    "v03": [f"AI 응답까지 약 {A['ai_wait_s']}초", f"해석 카드: {one(A['card'], 900)}"],
    "v04": [f"AI 응답까지 약 {B['ai_wait_s']}초", f"해석 카드: {one(B['card'], 900)}"],
    "v05": [f"고친 뒤 카드: {one(B['after_fix_card'], 500)}", f"확인 뒤 카드: {one(B['card_after'], 500)}",
            f"답이 들어간 칸: {', '.join(B['fields_after'])}"],
    "v06": [f"핵심정보 창: {one(B['popup'], 900)}"],
    "v07": [f"체크리스트: {one(B['check_bar'])}", f"01 항목: {one(B['fire_item'], 700)}", f"확인 뒤: {one(B['fire_after'], 300)}"],
    "v08": [f"체크리스트 AI: {[B[k] for k in B if k.startswith('ck_ai_try')]}", f"AI 제안 줄 3건: {one(' || '.join(B['ck_marks']), 900)}",
            f"고른 항목 확인 뒤: {one(B['adopted'], 500)}"],
    "v09": [f"위험한 이유: {one(B['why_fire'], 900)}", f"사례 줄: {B['why_case_line']}"],
    "v10": [f"질문과 관련 자료: {one(B['refs_question'], 900)}"],
    "v11": [f"완료: {one(B['check_bar_done'])}", f"제출 결과: {one(B['sent'][B['sent'].find('안전팀에 제출했습니다'):], 500)}",
            f"반영본 1쪽 파란 글씨: {' / '.join(t for t in PDF['PDF_p1']['boxes']['blue_text'] if t not in ('HD HYUNDAI',))}",
            f"추가검토서 2쪽: {one(' / '.join(t for t, _ in PDF['PDF_p2']['boxes']['lines']), 1400)}"],
}
DIFF = {
    "v01": ["콘티 4번(수정본)대로 대표 작업 1건(동성화인텍 E42P 도장 13:30~15:00)만 자세히 보이고, 본청 계획서는 확인 표시로 축약했다.",
            "V01·V02·V04~V11 화면은 모두 같은 테이크 B(한 번의 연속 조작)에서 찍었다. V03만 테이크 A다."],
    "v02": ["허가서 종류 화면의 실제 명칭은 「밀폐 · 화기 · 고소 · 중량물인양 · 정전·LOTO」다(앱 표기 그대로, 강조 라벨은 「위험작업 허가서 종류 5가지」)."],
    "v03": ["테이크 A(기본 입력). 입력은 연속 녹화가 아니라 입력 직후 화면 + 결과 화면을 잇고 문장을 「입력 내용 재현」 카드로 보였다.",
            f"테이크 A 결과의 장소 끝에 말끝 「고」가 남았다(…블록 상부고). V05 이후는 테이크 B로 이어지므로 이 값은 고치지 않은 채 V03에서만 보인다."],
    "v04": ["같은 질문·새로 로그인한 같은 시작 상태(테이크 B). 오타 3곳(자겁·상부구요·예정임니다)은 입력 재현 카드 제목에 적어 강조했다.",
            "13:00~15:00 비교: 테이크 B 결과 → 테이크 A 카드의 작업시간으로 잠깐 바꿔 보인 뒤 테이크 B 카드로 돌아와 V05로 이어진다."],
    "v05": [f"테이크 B에서 작업장소 값 끝에 오타 말끝 「{META['tail_b']}」가 남아(…블록 상부{META['tail_b']}) 반장이 「항목 고치기」로 지웠다(실제 수정이 필요한 경우).",
            "카드의 「확인」 버튼을 누르는 순간은 따로 찍히지 않았다(그 화면에서 카드가 스크롤 밖). 「이 값으로 답하기」 다음에 확인된 카드(「확인한 우리 작업 정보」)로 바로 잇는다.",
            "화면 양식에서 파란 글씨로 보이는 것은 작업내용(상세) 칸의 ②다. 작업장소 ①은 화면 양식에는 점선 표시만 되고, 제출 PDF 반영본(V11)에서 파란 글씨로 확인된다."],
    "v06": ["창은 「다음: 위험 체크리스트」를 누를 때 뜬다. 미확인은 병행작업·작업 중 통제 범위 2건(모름)이며 안전팀 확인으로 넘어간다."],
    "v07": ["준비할 안전조치는 croScan이 고른 2개(불티 차단덮개, 화재감시자 배치)를 바꾸지 않고 「그대로 확인」했다."],
    "v08": [f"이번 촬영의 체크리스트 AI는 새 후보 항목 0건, 기본 항목에 붙은 「AI 제안」 줄 3건(08·10·16)을 돌려줬다. 영상은 10번 「작업 뒤 남은 불씨에서 화재」의 AI 제안(근거 「{META['v08_quote'][0]}」({META['v08_quote'][1]}))을 썼다.",
            "16번(근거 「아크 가우징하고 CO2 용접할 예정임니다」)도 같은 화면에 있었으나 촬영 스크립트가 10번을 골랐다. 반장 답을 근거로 한 점은 같다.",
            "21번 「사람이 선택」은 후보 채택이 아니라 이 항목의 「해당」을 반장이 확인한 장면이다."],
    "v09": ["사례는 「조선업 중대재해 사례집 86쪽」 출처가 함께 표시된 실제 연결 사례다. 「아직 확인할 것: 조치 이행은 현장에서 따로 확인」도 함께 보였다."],
    "v10": ["체크리스트 항목에는 관련 자료 결과가 없어, 3단계로 돌아가 결과가 있는 첫 질문(작업일시)의 「왜 묻나요?」를 열었다(화면에 무엇의 자료인지 표시).",
            "관련 자료는 앱 표기대로 「검색 후보(근거 확정 아님)」, 검수 상태 「검수 전」이다."],
    "v11": [f"제출본 {SUB}(테이크 B). 27번 화면의 앱 문구: 「안전관리자 화면 … 작업 목록에 연결 … (시연: 전산·결재로 보내지 않음)」.",
            "수정 콘티 5번대로 끝에 원래 신청시간 08:00~16:59(반영본 1쪽 원본 칸)과 반장이 확인한 실제 시간 13:00~15:00·위치 3BAY 08~10칼럼·E42P(추가검토서 「3. 확인된 작업 범위」), 작업번호 0731을 차례로 보인다(자막 없음).",
            "확인 질문 요약은 「답 6건 · 모름 2건 · AI 미완료 1」이다. 「AI 분석을 마치지 못함(규칙 질문으로만 확인)」은 실제 결과이며 추가검토서 「4. 안전팀 확인 필요」에도 적혀 있다."],
}
LIMITS = [
    "입력 장면(V03·V04)은 연속 화면 녹화가 아니다. 실제로 입력한 직후 화면과 실제 해석 결과 화면을 잇고, 입력 문장을 「입력 내용 재현」 카드로 보였다. AI 대기 시간은 줄였고 실제 대기 시간을 강조 라벨에 적었다. 처리 속도나 오타 일반 처리 성능을 주장하지 않는다.",
    "체크리스트 반복 확인(V11)은 앱 제안을 그대로 확인하는 과정을 줄였다. 28/28은 확인 완료이지 안전팀 확인 16건의 해결이 아니다.",
    "제출은 시연 제출이다(앱 문구: 전산·결재로 보내지 않음). 승인·외부 전송이 아니다.",
    "AI 응답은 공유 CPU 모델이라 결과가 촬영마다 다를 수 있다. 같은 테이크 B 이전 촬영(r3, 제출본 y1e3ciQFHXNA9cuK)에서는 체크리스트 AI가 4번 모두 실패해 그 촬영은 쓰지 않고 다시 찍었다(기록: work19/A/_old/capB_r3/).",
    "음악은 지난번 work/groove.mp3(PRAI 생성 CC0)를 작게 깔았다. 내레이션 없음. 영상은 아직 사람이 소리를 켜고 끝까지 보지 않았다.",
]


def secs(mp4):
    r = subprocess.run([FF, "-i", str(mp4)], capture_output=True, text=True, encoding="utf-8", errors="ignore")
    h, m, s = r.stderr.split("Duration:")[1].split(",")[0].strip().split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


man = {"made_with": "PRAI · croScan 스테이징(localhost:8776) 실제 화면 캡처 · 1920×1080 · 30fps · H.264+AAC · −14 LUFS · 내레이션 없음",
       "captions_source": "work19/croScan_최종자막_57개_수정반영본_2026-11-02.md (자막 1~29)", "submission_take_B": SUB,
       "takes": {"A": {"use": "V03(및 V04 비교 장면 한 컷)", "submission_not_used": A["submission"]["id"]},
                 "B": {"use": "V01·V02·V04~V11", "submission": SUB}},
       "clips": []}
md = ["## 반장 클립 V01~V11 (담당 A · 자막 1~29)", "",
      f"- 테이크 B 제출본 id: **{SUB}** (V11 제출 · 반영본·추가검토서 PDF의 출처, 안전관리자 V14B에서 이어 씀)",
      f"- 테이크 A 제출본 {A['submission']['id']}는 영상에 쓰지 않았다(V03 화면만 사용).",
      "- 자막 원문: `work19/croScan_최종자막_57개_수정반영본_2026-11-02.md`. 시각은 클립 안 초(0.6초 = 1박).", ""]
for v, (title, still) in CLIPS.items():
    src = PRAI / "out" / v / f"{v}.mp4"
    mp4 = OUT / f"croScan_{title}.mp4"
    shutil.copy(src, mp4)
    dur = secs(mp4)
    rows = [r for r in SM[v] if "scene" in r]
    sc = next(r for r in rows if r["scene"] == still)
    t = sc.get("cap_start_s", sc["start_s"]) + 1.6
    png = OUT / f"croScan_{title}_대표화면.png"
    subprocess.run([FF, "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", str(mp4), "-frames:v", "1", str(png)], check=True)
    caps = [{"no": r["caption"], "start_s": r["cap_start_s"], "end_s": r["cap_end_s"], "main": r["headline"], "sub": r["sub"], "scene": r["scene"],
             "marks": r["marks"]} for r in rows if r["caption"]]
    e = {"clip": "V" + v[1:], "file": mp4.name, "png": png.name, "sheet": f"work19/sheets/V{v[1:]}_sheet.png", "seconds": round(dur, 2),
         "captions": caps, "scenes": rows, "inputs": INPUTS[v], "results": RESULTS[v], "differences": DIFF[v]}
    man["clips"].append(e)
    md += [f"### V{v[1:]} · `{mp4.name}` · {dur:.1f}초", "", "| 자막 | 시작 | 끝 | 주자막 | 보조자막 |", "|---|---|---|---|---|"]
    md += [f"| {c['no']} | {c['start_s']:.1f}초 | {c['end_s']:.1f}초 | {c['main']} | {c['sub'] or '—'} |" for c in caps]
    md += ["", "**실제 입력**", ""] + [f"- {x}" for x in INPUTS[v]] + ["", "**실제 앱 결과(로그 발췌)**", ""] + [f"- {x}" for x in RESULTS[v]]
    md += ["", "**콘티와 달라진 점**", ""] + [f"- {x}" for x in DIFF[v]] + [""]
    print(v, mp4.name, f"{dur:.1f}s")
man["known_limits"] = LIMITS
md += ["### 반장 클립 공통 · 알려진 한계", ""] + [f"- {x}" for x in LIMITS]
(W / "manifest_part.json").write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")
(W / "manifest_part.md").write_text("\n".join(md) + "\n", encoding="utf-8")
print("manifest_part written")
