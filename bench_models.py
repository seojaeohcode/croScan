"""Speed of the local LLM (Raon-1 mini preview on llama.cpp) on a croScan-sized Korean turn. Standard library only,
so it runs on the server itself:  python3 bench_models.py [http://127.0.0.1:8000] [runs=2]
Prints prompt and reply speed (llama.cpp's own timings), thinking length and the answer."""
import json
import sys
import time
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
RUNS = int(sys.argv[2]) if len(sys.argv) > 2 else 2
PERMIT = """[허가서 내용]
- 승인번호: AC00-IH-20261027-0701 / 허가서 종류: 화기작업 / 작업장소: 대조립1부 용접3팀 (공장·BAY·칼럼 없음)
- 작업내용: 취부 불량부 절단·재용접(B11, F31, E11 블록) / 발판 위 높이 2.5m 구간 포함
- 작업 일시: 2026-10-27~10-30 매일 08:00~16:59 / 작업인원 4명 / 병행여부: (빈 칸) / 호선: (빈 칸)
- 유해위험요소: 용접흄, 소음 / 추가정보: 용접·용단 체크, 고소 화기작업 체크 없음
[규칙 검사 결과]
- [확인 필요] 작업시간이 근무시간 전체로 적혀 실제 위험 시간대를 알 수 없음
- [확인 필요] 장소가 팀 이름이라 BAY·칼럼을 알 수 없음
- [빈 칸] 병행여부, 호선"""
MSGS = [{"role": "system", "content": "너는 조선소 안전팀의 위험작업 허가서 사전검토 담당이다. 상대는 작업반장이다. "
                                       "사실은 아래 내용에만 근거하고, 짧고 정중한 한국어로 답한다.\n\n" + PERMIT},
        {"role": "user", "content": "반장 답변: '실제 절단은 첫날 오전 9시부터 11시 반까지만 하고 나머지는 정리예요. 3BAY 14번 칼럼 근처입니다.' "
                                    "이 답에서 작업 시간대와 위치를 뽑아 JSON 한 줄({\"windows\": [...], \"place\": ...})로만 답해."}]
SAMPLING = {"temperature": 1.0, "top_p": 0.95, "top_k": 20, "min_p": 0.0, "presence_penalty": 1.5,
            "chat_template_kwargs": {"enable_thinking": True, "truncate_history_thinking": False}}

print(json.loads(urllib.request.urlopen(BASE + "/v1/models", timeout=10).read())["data"][0]["id"])
for run in range(RUNS):
    body = json.dumps({"model": "Raon-1-mini-preview", "messages": MSGS, "max_tokens": 4096, **SAMPLING}).encode()
    t0 = time.time()
    r = json.loads(urllib.request.urlopen(urllib.request.Request(BASE + "/v1/chat/completions", body,
                                                                 {"Content-Type": "application/json"}), timeout=1800).read())
    m, tm = r["choices"][0]["message"], r.get("timings", {})
    print(f"=== run {run + 1}: total {time.time() - t0:.1f}s | prompt {tm.get('prompt_n')} tok @ {tm.get('prompt_per_second', 0):.1f} tok/s"
          f" | reply {tm.get('predicted_n')} tok @ {tm.get('predicted_per_second', 0):.1f} tok/s"
          f" | thinking {len(m.get('reasoning_content') or '')} chars")
    print((m.get("content") or "").strip()[:600])
