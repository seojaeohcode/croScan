# croScan 홍보 영상 (최종, 2026-10-30)

- 결과물: `out/croscan_promo_완성본.mp4` — 1920×1080, 30fps, 64.5초, H.264(yuv420p) + AAC, −14 LUFS(유튜브 기준), 최대 −1.4 dBFS
- 배경음악: “Getting it Done” Kevin MacLeod (incompetech.com), CC BY 4.0 — 136 BPM(1박 0.441초), 박이 가장 또렷한 후보(측정)로 골랐다. 출처는 끝 화면에 있고, 올릴 때 설명란에도 넣는다.
- 내레이션: edge-tts(오픈소스 클라이언트) + Microsoft 신경망 음성 ko-KR-SunHiNeural, +6%. 대본 `public/audio/narr.tsv`
- 리듬(2026-10-30 보강, 참고: 'seven' ident · 플래니 홍보 · MAKE IT FUNKY NOW): 모든 장면은 박에서 시작하고 박에서 컷된다(`src/beat.ts`).
  카메라 이동은 1박 동안 움직여 박에 도착, 강조 박스·자막은 박에 튀어 들어와 자리 잡음, 장면 전환은 박에서 선명한 컷 + 3% 펀치인.
  인트로(28박)·엔딩(20박)은 Codex 박자표대로 만든 모션그래픽: 박마다 한 칸씩 움직이는 배경 글자, 박에 튀는 구체, 박에 멈추는 숫자,
  두 작업 시간 막대가 겹치고(빨간 테두리 '검토 필요') → 스캔선 → 로고(두 띠가 감쌈) → 첫 시연 화면이 커지며 b28에 그대로 이어짐.
- 화면은 모두 실제 croScan(스테이징, 시연 자료)을 찍은 것이다. 확대·강조 박스·클릭 표시·자막·숫자 카드만 편집으로 얹었다.
- 숫자는 시연 자료 그대로이고 "시연 자료 기준"으로 표기했다(허가서 10 · 작업계획서 40, 445쌍 검토 → 13쌍 경보).
- 콘티와 프레임 검수는 Codex와 두 번 했다. 자막은 Codex 검토안을 따랐다.
- 로고는 사이트의 현재 로고(QA #31 원본)를 썼다.

장면 길이(박): 인트로 28 · 3 14 · 4 18 · 5 16 · 6 14 · 7 22 · 8 14 · 엔딩 20 (내레이션이 들어가는 2박 단위). 아래 표의 시간은 처음(무음 48초)판 기준이고, 1–2·9장면은 인트로·엔딩 모션그래픽으로 바뀌었다.

| # | 시간 | 장면 | 자막 |
|---|---|---|---|
| 1 | 0–4초 | 서류가 쌓이고 0→50건 카운트 | 쌓인 서류, 겹치는 작업은? |
| 2 | 4–7초 | 로고 | 위험작업 AI 사전검토, croScan |
| 3 | 7–12초 | 0731 화기 허가서: 팀 이름뿐인 작업장소, 종일 신청 시간 확대 → croScan의 질문 | 확인이 필요한 칸을 먼저 묻습니다 |
| 4 | 12–19초 | 한 번에 적은 긴 답(크게 표시) → 「함께 읽어 반영」 카드 → 양식의 장소·실제 작업시간 | 긴 답도 시간·장소·인원으로 |
| 5 | 19–24초 | 반영본(제출 PDF 앞장)의 파란 글씨 ①②: 작업장소, 실제 작업시간 | 답변을 맞는 칸에 파란 글씨로 |
| 6 | 24–30초 | 병행여부 칸 고르기 → 입력창 위 「수정할 칸」 → N 입력 → 적용 → 양식에 들어감 | 남은 빈칸도 차례로 수정 |
| 7 | 30–39초 | 안전관리자 3탭 → 결과 카드(13쌍, 1·2·3순위) → 1순위 쌍의 조건 → 원인 → 사고 | 작업 간 위험을 규칙으로 검토 |
| 8 | 39–44초 | 계획 배치도: 고른 시각 10:00 → 같은 시간·같은 곳의 두 작업 | 언제, 어디서 겹치는지 한눈에 |
| 9 | 44–48초 | 로고 | 작업 전 위험 검토, croScan |

## 다시 만들기

- 화면 다시 찍기: 스크래치의 `video/capture.mjs`(스테이징 터널 :8776 + 헤드리스 Edge 2배율 드라이버 :9339). `public/shots/*.png`와 확대할 위치 `rects.json`이 나온다. `src/rects.json`으로 복사한다.
- 미리 보기: `npm run studio`
- 렌더: `npm run render` (Remotion 4.0.539, 자체 ffmpeg 포함. 약 1분 반) → `out/croscan_promo.mp4`
- 마무리(음량 −14 LUFS, 표준 색 범위): pip `imageio-ffmpeg`의 ffmpeg로
  `ffmpeg -i out/croscan_promo.mp4 -vf "scale=in_range=full:out_range=limited,format=yuv420p" -color_range tv -colorspace bt709 -color_primaries bt709 -color_trc bt709 -c:v libx264 -preset slow -crf 18 -af "loudnorm=I=-14:TP=-1.5:LRA=11" -ar 48000 -c:a aac -b:a 192k -movflags +faststart out/croscan_promo_완성본.mp4`
- 내레이션 다시 만들기: `python -m edge_tts --voice ko-KR-SunHiNeural --rate=+6% --text "…" --write-media public/audio/nN.mp3` 후 길이를 `src/Video.tsx`의 NARR·SCENES에 반영
- 장면·자막·시간은 `src/Video.tsx`, 카메라·강조 박스·자막 모양은 `src/lib.tsx`에 있다.
- Remotion은 개인·3인 이하 팀은 무료다. 회사에서 쓰면 라이선스를 확인해야 한다.
